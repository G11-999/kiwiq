import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Set, Dict, Any
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import String as SQLAlchemyString, Index, ForeignKey, Boolean, JSON, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel, Column
from sqlalchemy import String as SQLAlchemyString

from kiwi_app.auth.utils import datetime_now_utc
from kiwi_app.settings import settings

# Importing these for type hints and relationships
from kiwi_app.auth.models import User, Organization

table_prefix = f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_LINKEDIN_PREFIX}"


# --- Enums --- #
class LinkedinAccountType(str, Enum):
    """
    Represents the type of LinkedIn account.
    
    Types:
        - PERSON: Individual LinkedIn member account
        - ORGANIZATION: LinkedIn organization/company page
    """
    PERSON = "person"
    ORGANIZATION = "organization"


class OrgLinkedinAccountStatus(str, Enum):
    """
    Represents the status of an organization LinkedIn account.
    
    States:
        - ACTIVE: Integration is active and tokens are valid
        - EXPIRED: Tokens have expired and need re-authentication
        - REVOKED: User or system revoked the OAuth connection
    """
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


# --- OAuth State Enum --- #
class LinkedinOauthState(str, Enum):
    """
    Represents the state of the LinkedIn OAuth connection.
    
    States:
        - PENDING: OAuth flow initiated, pending completion
        - ACTIVE: Connection is active and tokens are valid
        - EXPIRED: Tokens have expired and need re-authentication
        - REVOKED: User or system revoked the OAuth connection
        - ERROR: Error state with details in state_metadata
        - VERIFICATION_REQUIRED: User needs to verify email or account ownership
        - REGISTRATION_REQUIRED: User needs to complete registration
        - PENDING_DELETION: User has initiated deletion process
    """
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ERROR = "error"
    VERIFICATION_REQUIRED = "verification_required"
    REGISTRATION_REQUIRED = "registration_required"
    PENDING_DELETION = "pending_deletion"


# --- LinkedIn OAuth Token Model --- #
class LinkedinUserOauth(SQLModel, table=True):
    """
    LinkedIn OAuth token model for storing user OAuth credentials.
    
    This model stores LinkedIn OAuth2 access tokens and refresh tokens for users,
    enabling API access to LinkedIn's services. The model has a 1:1 relationship
    with the User model, using LinkedIn's 'sub' field as the primary key.
    
    Design Notes:
        - Primary key uses LinkedIn's 'sub' field from UserInfo response
        - Stores both access and refresh tokens with expiration tracking
        - Includes scope information for permission management
        - Follows OAuth2 security best practices for token storage
        - All token fields are encrypted at rest (implementation dependent)
        - Tracks OAuth flow state for proper lifecycle management
    
    Key Features:
        - Automatic expiration timestamp calculation
        - Secure token storage with length validation
        - Scope parsing for permission verification
        - 1:1 relationship with User model for seamless integration
        - State tracking for OAuth flow management
    
    Security Considerations:
        - All tokens must be kept secure as per LinkedIn API Terms of Use
        - Access tokens are typically ~500 characters but schema allows expansion
        - Refresh tokens enable long-term access without re-authentication
        - Regular token rotation is recommended for security
    """
    __tablename__ = f"{table_prefix}oauth"

    # Use LinkedIn's 'sub' field as primary key for 1:1 mapping with LinkedIn identity
    id: str = Field(
        sa_column=Column(SQLAlchemyString(255), primary_key=True, index=True),
        description="LinkedIn 'sub' identifier from UserInfo - unique LinkedIn user identifier"
    )
    
    # Foreign key relationship to User model (1:1)
    user_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}user.id"), unique=True, index=True),
        description="Foreign key to User model - ensures 1:1 relationship"
    )
    
    # OAuth state tracking
    oauth_state: LinkedinOauthState = Field(
        default=LinkedinOauthState.PENDING,
        sa_column=Column(SQLAlchemyString(50), nullable=False, index=True),
        description="Current state of the OAuth connection lifecycle"
    )
    
    state_metadata: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Additional metadata for the current state (e.g., error details, pending actions)"
    )
    
    # OAuth token fields from LinkedInAccessTokenSchema
    access_token: str = Field(
        sa_column=Column(SQLAlchemyString(1000), nullable=False),
        description="LinkedIn access token for API calls - must be kept secure"
    )
    
    refresh_token: Optional[str] = Field(
        default=None,
        sa_column=Column(SQLAlchemyString(1000), nullable=True),
        description="LinkedIn refresh token for obtaining new access tokens - must be kept secure"
    )
    
    scope: str = Field(
        sa_column=Column(Text, nullable=False),
        description="URL-encoded, space-delimited list of authorized LinkedIn permissions"
    )
    
    expires_in: int = Field(
        sa_column=Column(sa.Integer, nullable=False),
        description="Number of seconds until access token expires (typically 60 days)"
    )
    
    refresh_token_expires_in: Optional[int] = Field(
        default=None,
        sa_column=Column(sa.Integer, nullable=True),
        description="Number of seconds until refresh token expires"
    )
    
    # Computed expiration timestamps for easier expiration handling
    token_expires_at: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True, index=True),
        description="Calculated expiration timestamp for access token"
    )
    
    refresh_token_expires_at: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True, index=True),
        description="Calculated expiration timestamp for refresh token"
    )
    
    # Metadata fields
    created_at: datetime = Field(
        default_factory=datetime_now_utc, 
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
        description="Timestamp when the OAuth record was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime_now_utc, 
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc),
        description="Timestamp when the OAuth record was last updated"
    )
    
    # 1:1 Relationship to User model
    user: User = Relationship(back_populates="linkedin_oauth")
    
    def is_access_token_expired(self) -> bool:
        """
        Check if the access token has expired.
        
        Returns:
            bool: True if token is expired, False otherwise
        """
        if not self.token_expires_at:
            return False
        return datetime_now_utc() >= self.token_expires_at
    
    def is_refresh_token_expired(self) -> bool:
        """
        Check if the refresh token has expired.
        
        Returns:
            bool: True if refresh token is expired, False otherwise
        """
        if not self.refresh_token_expires_at:
            return False
        return datetime_now_utc() >= self.refresh_token_expires_at
    
    def get_scopes_list(self) -> List[str]:
        """
        Parse the scope string into a list of individual scopes.
        
        Returns:
            List[str]: List of individual scope permissions
        """
        return self.scope.split() if self.scope else []
    
    def update_expiration_timestamps(self) -> None:
        """
        Update expiration timestamps based on expires_in values.
        
        This method recalculates the expiration timestamps when token data is updated,
        ensuring accurate expiration tracking for token refresh workflows.
        """
        current_time = datetime_now_utc()
        
        # Calculate access token expiration timestamp
        if self.expires_in:
            self.token_expires_at = current_time + timedelta(seconds=self.expires_in)
        
        # Calculate refresh token expiration timestamp if available
        if self.refresh_token_expires_in:
            self.refresh_token_expires_at = current_time + timedelta(seconds=self.refresh_token_expires_in)
    
    def is_active(self) -> bool:
        """
        Check if the OAuth connection is active and usable.
        
        Returns:
            bool: True if the connection is active and tokens are valid
        """
        return (
            self.oauth_state == LinkedinOauthState.ACTIVE and
            not self.is_access_token_expired()
        )
    
    def needs_refresh(self) -> bool:
        """
        Check if the access token needs to be refreshed.
        
        Returns:
            bool: True if token is expired but refresh token is still valid
        """
        return (
            self.is_access_token_expired() and
            self.refresh_token is not None and
            not self.is_refresh_token_expired()
        )


# --- LinkedIn Integration Model --- #
class LinkedinIntegration(SQLModel, table=True):
    """
    LinkedIn Integration model for managing multiple LinkedIn accounts per user.
    
    This is separate from LinkedinUserOauth which is used for authentication.
    A user can have multiple integrations to manage different LinkedIn accounts/orgs.
    """
    __tablename__ = f"{table_prefix}integration"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True, index=True),
        description="Unique identifier for the integration"
    )
    
    user_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}user.id", ondelete="CASCADE"), nullable=False, index=True),
        description="User who owns this integration"
    )
    
    linkedin_id: str = Field(
        sa_column=Column(SQLAlchemyString(255), nullable=False, index=True),
        description="LinkedIn sub/ID of the integration owner"
    )
    
    access_token: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="LinkedIn access token - must be kept secure"
    )
    
    refresh_token: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="LinkedIn refresh token - must be kept secure"
    )
    
    scope: Optional[str] = Field(
        default=None,
        sa_column=Column(SQLAlchemyString, nullable=True),
        description="OAuth scopes for the integration"
    )
    
    expires_in: Optional[int] = Field(
        default=None,
        sa_column=Column(sa.Integer, nullable=True),
        description="Number of seconds until access token expires"
    )
    
    refresh_token_expires_in: Optional[int] = Field(
        default=None,
        sa_column=Column(sa.Integer, nullable=True),
        description="Number of seconds until refresh token expires"
    )
    
    token_expires_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(sa.DateTime(timezone=True), nullable=True),
        description="Calculated expiration timestamp for access token"
    )
    
    refresh_token_expires_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(sa.DateTime(timezone=True), nullable=True),
        description="Calculated expiration timestamp for refresh token"
    )
    
    integration_state: str = Field(
        default=LinkedinOauthState.ACTIVE.value,
        sa_column=Column(SQLAlchemyString(50), nullable=False, default=LinkedinOauthState.ACTIVE.value, index=True),
        description="Current state of the integration"
    )
    
    linkedin_orgs_roles: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="JSON with user's different orgs and roles"
    )
    
    last_sync_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(sa.DateTime(timezone=True), nullable=True),
        description="Last synchronization timestamp"
    )
    
    created_at: datetime = Field(
        default_factory=datetime_now_utc,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
        description="Creation timestamp"
    )
    
    updated_at: datetime = Field(
        default_factory=datetime_now_utc,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc),
        description="Last update timestamp"
    )
    
    # Relationships
    user: User = Relationship(back_populates="linkedin_integrations")
    org_linkedin_accounts: List["OrgLinkedinAccount"] = Relationship(back_populates="linkedin_integration", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    
    # Unique constraint
    __table_args__ = (
        sa.UniqueConstraint("user_id", "linkedin_id", name="uq_user_linkedin_integration"),
    )
    
    def get_scopes_list(self) -> List[str]:
        """Return the list of OAuth scopes."""
        return self.scope.split(',') if self.scope else []
    
    def is_access_token_expired(self) -> bool:
        """Check if the access token is expired."""
        if not self.token_expires_at:
            return False
        return datetime_now_utc() >= self.token_expires_at
    
    def is_refresh_token_expired(self) -> bool:
        """Check if the refresh token is expired."""
        if not self.refresh_token_expires_at:
            return False
        return datetime_now_utc() >= self.refresh_token_expires_at
    
    def update_expiration_timestamps(self):
        """Update the expiration timestamps based on expires_in values."""
        now = datetime_now_utc()
        if self.expires_in:
            self.token_expires_at = now + timedelta(seconds=self.expires_in)
        if self.refresh_token_expires_in:
            self.refresh_token_expires_at = now + timedelta(seconds=self.refresh_token_expires_in)
    
    def get_linkedin_orgs(self) -> Dict[str, Any]:
        """Get the LinkedIn organizations and roles."""
        return self.linkedin_orgs_roles or {}


# --- LinkedIn Account Model --- #
class LinkedinAccount(SQLModel, table=True):
    """
    LinkedIn Account model representing unique LinkedIn entities.
    
    Can be either a LinkedIn person or organization.
    ID is the LinkedIn identifier.
    """
    __tablename__ = f"{table_prefix}account"
    
    id: str = Field(
        sa_column=Column(SQLAlchemyString(255), primary_key=True),
        description="LinkedIn identifier (person or org ID)"
    )
    
    account_type: LinkedinAccountType = Field(
        sa_column=Column(SQLAlchemyString(50), nullable=False),
        description="Type of LinkedIn account (person or organization)"
    )
    
    name: Optional[str] = Field(
        default=None,
        sa_column=Column(SQLAlchemyString(500), nullable=True),
        description="Account name"
    )
    
    vanity_name: Optional[str] = Field(
        default=None,
        sa_column=Column(SQLAlchemyString(255), nullable=True, index=True),
        description="LinkedIn vanity name/username (e.g., company URL slug)"
    )
    
    profile_data: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Cached profile data"
    )
    
    last_updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(sa.DateTime(timezone=True), nullable=True),
        description="Last time profile data was updated"
    )
    
    created_at: datetime = Field(
        default_factory=datetime_now_utc,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
        description="Creation timestamp"
    )
    
    updated_at: datetime = Field(
        default_factory=datetime_now_utc,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc),
        description="Last update timestamp"
    )
    
    # Relationships
    org_linkedin_accounts: List["OrgLinkedinAccount"] = Relationship(back_populates="linkedin_account", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    
    def is_organization(self) -> bool:
        """Check if this is an organization account."""
        return self.account_type == LinkedinAccountType.ORGANIZATION
    
    def is_person(self) -> bool:
        """Check if this is a person account."""
        return self.account_type == LinkedinAccountType.PERSON


# --- Org LinkedIn Account Model --- #
class OrgLinkedinAccount(SQLModel, table=True):
    """
    Org LinkedIn Account model for sharing LinkedIn entities within KiwiQ organizations.
    
    Represents a user sharing their LinkedIn entities (personal or org pages)
    via their LinkedIn integrations within a KiwiQ organization.
    """
    __tablename__ = f"{table_prefix}org_account"
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True, index=True),
        description="Unique identifier for the org LinkedIn account"
    )
    
    linkedin_account_id: str = Field(
        sa_column=Column(SQLAlchemyString(255), ForeignKey(f"{table_prefix}account.id", ondelete="CASCADE"), nullable=False, index=True),
        description="LinkedIn account being shared"
    )
    
    linkedin_integration_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{table_prefix}integration.id", ondelete="CASCADE"), nullable=False, index=True),
        description="Integration used to access this account"
    )
    
    managed_by_user_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}user.id", ondelete="CASCADE"), nullable=False, index=True),
        description="User who manages this shared account"
    )
    
    organization_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}org.id", ondelete="CASCADE"), nullable=False, index=True),
        description="Organization this account is shared with"
    )
    
    role_in_linkedin_entity: Optional[str] = Field(
        default=None,
        sa_column=Column(SQLAlchemyString(100), nullable=True),
        description="Role of integration in the LinkedIn entity (e.g., ADMINISTRATOR, DIRECT_SPONSORED_CONTENT_POSTER)"
    )
    
    is_shared: bool = Field(
        default=True,
        sa_column=Column(Boolean, default=True, index=True),
        description="True if shared with org, False if private to user"
    )
    
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, default=True, index=True),
        description="Whether the account is active"
    )
    
    status: OrgLinkedinAccountStatus = Field(
        default=OrgLinkedinAccountStatus.ACTIVE,
        sa_column=Column(SQLAlchemyString(50), nullable=False, default=OrgLinkedinAccountStatus.ACTIVE.value, index=True),
        description="Current status of the LinkedIn account integration"
    )
    
    created_at: datetime = Field(
        default_factory=datetime_now_utc,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
        description="Creation timestamp"
    )
    
    updated_at: datetime = Field(
        default_factory=datetime_now_utc,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc),
        description="Last update timestamp"
    )
    
    # Relationships
    linkedin_account: LinkedinAccount = Relationship(back_populates="org_linkedin_accounts")
    linkedin_integration: LinkedinIntegration = Relationship(back_populates="org_linkedin_accounts")
    managed_by_user: User = Relationship(sa_relationship_kwargs={"foreign_keys": "[OrgLinkedinAccount.managed_by_user_id]"})
    organization: Organization = Relationship(back_populates="linkedin_accounts")
    
    # Unique constraint
    __table_args__ = (
        sa.UniqueConstraint("linkedin_account_id", "organization_id", "linkedin_integration_id", name="uq_org_linkedin_account"),
    )
    
    def can_be_used_by_org(self) -> bool:
        """Check if this account can be used by the organization."""
        return self.is_shared and self.is_active and self.status == OrgLinkedinAccountStatus.ACTIVE


LinkedinUserOauth.model_rebuild()
LinkedinIntegration.model_rebuild()
LinkedinAccount.model_rebuild()
OrgLinkedinAccount.model_rebuild()
User.model_rebuild()
Organization.model_rebuild()
