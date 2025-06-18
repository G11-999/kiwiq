import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Set
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import String as SQLAlchemyString, Text, JSON, Boolean, Index, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel, Column

from kiwi_app.auth.utils import datetime_now_utc
from kiwi_app.settings import settings
from kiwi_app.auth.models import User, Organization

table_prefix = f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_LINKEDIN_PREFIX}"


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
    user: User = Relationship()
    
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


LinkedinUserOauth.model_rebuild()

