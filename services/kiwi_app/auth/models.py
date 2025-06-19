import uuid
from datetime import datetime
from typing import List, Optional, Set, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import String as SQLAlchemyString, Text, JSON, Boolean, Index, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel, Column

from kiwi_app.auth.utils import datetime_now_utc
from kiwi_app.settings import settings

# Type checking imports to avoid circular imports
if TYPE_CHECKING:
    from linkedin_integration.models import LinkedinUserOauth, LinkedinIntegration, OrgLinkedinAccount

table_prefix = f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}"

# Forward declaration needed if RolePermission is defined after its use
# class RolePermission:
#     pass

# --- RolePermission Link Table (Define before use in Role/Permission) --- #
# Define the link model WITHOUT table=True
class RolePermission(SQLModel, table=True):
    """
    Link table for many-to-many relationship between roles and permissions.
    
    This model establishes the relationship between roles and their associated
    permissions, allowing flexible role-based access control (RBAC).
    """
    __tablename__ = f"{table_prefix}role_permission_link"

    role_id: uuid.UUID = Field(foreign_key=f"{table_prefix}role.id", primary_key=True)
    permission_id: uuid.UUID = Field(foreign_key=f"{table_prefix}permission.id", primary_key=True)

# --- Permission Model --- #
class Permission(SQLModel, table=True):
    """
    Permission model for role-based access control.
    
    Defines individual permissions that can be assigned to roles.
    Permissions are granular actions or access rights within the system.
    """
    __tablename__ = f"{table_prefix}permission"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    name: str = Field(sa_column=Column(SQLAlchemyString, unique=True, index=True))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))

    # Use the RolePermission class (without table=True) as the link_model
    #     heroes: list["Hero"] = Relationship(back_populates="teams", link_model=HeroTeamLink)
    roles: List["Role"] = Relationship(back_populates="permissions", link_model=RolePermission)

# --- Role Model --- #
class Role(SQLModel, table=True):
    """
    Role model for role-based access control.
    
    Defines roles that can be assigned to users within organizations.
    Each role contains a collection of permissions that determine what
    actions a user can perform.
    """
    __tablename__ = f"{table_prefix}role"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    name: str = Field(sa_column=Column(SQLAlchemyString, unique=True, index=True))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Can store default roles or system roles marker if needed
    is_system_role: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc))

    # Use the RolePermission class (without table=True) as the link_model
    permissions: List[Permission] = Relationship(back_populates="roles", link_model=RolePermission)

    # Relationship to UserOrganizationRole Link Table
    user_assignments: List["UserOrganizationRole"] = Relationship(back_populates="role")

# --- UserOrganizationRole Link Table (User <-> Org <-> Role) --- #
# Keep table=True for this link table as it has extra fields (created_at)
class UserOrganizationRole(SQLModel, table=True):
    """
    Link table for user-organization-role relationships.
    
    This model establishes the many-to-many relationship between users,
    organizations, and roles. A user can have different roles in different
    organizations, enabling flexible multi-tenant access control.
    """
    __tablename__ = f"{table_prefix}user_org_role"

    user_id: uuid.UUID = Field(foreign_key=f"{table_prefix}user.id", primary_key=True)
    organization_id: uuid.UUID = Field(foreign_key=f"{table_prefix}org.id", primary_key=True)
    role_id: uuid.UUID = Field(foreign_key=f"{table_prefix}role.id") # Role within this specific org

    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))

    # Relationships to access linked objects
    user: "User" = Relationship(back_populates="organization_links")
    organization: "Organization" = Relationship(back_populates="user_links")
    role: Role = Relationship(back_populates="user_assignments")

# --- Organization Model --- #
class Organization(SQLModel, table=True):
    """
    Organization model for multi-tenant architecture.
    
    Represents organizations/companies that users belong to.
    Each organization can have multiple users with different roles,
    enabling isolated workspaces and billing contexts.
    """
    __tablename__ = f"{table_prefix}org"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    external_billing_id: Optional[str] = Field(default=None, sa_column=Column(SQLAlchemyString, unique=True, nullable=True, index=True))
    primary_billing_email: Optional[str] = Field(default=None, sa_column=Column(SQLAlchemyString, nullable=True, index=True))
    name: str = Field(sa_column=Column(SQLAlchemyString, index=True))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc))

    # Relationships
    user_links: List[UserOrganizationRole] = Relationship(back_populates="organization", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    
    # LinkedIn accounts shared within the organization
    linkedin_accounts: List["OrgLinkedinAccount"] = Relationship(back_populates="organization", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

# --- User Model --- #
class User(SQLModel, table=True):
    """
    User model for authentication and authorization.
    
    Core user entity supporting multiple authentication methods (email/password, LinkedIn OAuth).
    Users can belong to multiple organizations with different roles in each.
    Includes email verification and account status tracking.
    """
    __tablename__ = f"{table_prefix}user"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    email: str = Field(sa_column=Column(SQLAlchemyString, unique=True, index=True))
    hashed_password: Optional[str] = Field(sa_column=Column(SQLAlchemyString, nullable=True))
    full_name: Optional[str] = Field(default=None, sa_column=Column(SQLAlchemyString))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, default=True, index=True))
    is_verified: bool = Field(default=False, sa_column=Column(Boolean, default=False, index=True))
    is_superuser: bool = Field(default=False, sa_column=Column(Boolean, default=False, index=True))
    linkedin_id: Optional[str] = Field(default=None, sa_column=Column(SQLAlchemyString, unique=True, nullable=True, index=True))
    email_verification_token: Optional[str] = Field(default=None, sa_column=Column(SQLAlchemyString, index=True, nullable=True))
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc))

    organization_links: List[UserOrganizationRole] = Relationship(back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    refresh_tokens: List["RefreshToken"] = Relationship(back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    linkedin_oauth: Optional["LinkedinUserOauth"] = Relationship(back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    
    # LinkedIn Integrations (1:many mapping for managing multiple LinkedIn accounts)
    linkedin_integrations: List["LinkedinIntegration"] = Relationship(back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

# --- NEW: Refresh Token Model --- #
class RefreshToken(SQLModel, table=True):
    """
    Refresh token model for JWT authentication.
    
    Stores refresh tokens for secure token-based authentication.
    Refresh tokens have longer expiration times than access tokens
    and can be revoked for security purposes.
    """
    __tablename__ = f"{table_prefix}refresh_token"

    token: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), server_default=text("gen_random_uuid()"), primary_key=True, unique=True, index=True)
    )
    user_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{table_prefix}user.id"), index=True))
    expires_at: datetime = Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    revoked_at: Optional[datetime] = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True))

    user: "User" = Relationship(back_populates="refresh_tokens")

# Define Update Forward Refs after all models are defined
# Needed for relationships defined using string type hints
Permission.model_rebuild()
Role.model_rebuild()
UserOrganizationRole.model_rebuild()
Organization.model_rebuild()
RefreshToken.model_rebuild()
User.model_rebuild()

# --- Schemas for API Interaction (Often placed in schemas.py) ---
# We will create these in a separate schemas.py file later,
# but defining basic Read schemas here can be useful for relationships.

# class RoleRead(RoleBase):
#     id: int
#     created_at: datetime
#     updated_at: datetime

# class OrganizationRead(OrganizationBase):
#     id: int
#     created_at: datetime
#     updated_at: datetime

# class UserOrganizationRoleRead(SQLModel):
#     organization: OrganizationRead
#     role: RoleRead
#     created_at: datetime

# class UserRead(UserBase):
#     id: int
#     linkedin_id: Optional[str]
#     is_verified: bool
#     created_at: datetime
#     updated_at: datetime
#     organizations: List[UserOrganizationRoleRead] = [] # Include related orgs/roles 
