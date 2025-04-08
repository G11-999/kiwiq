import uuid
from datetime import datetime
from typing import List, Optional, Set

from sqlalchemy import String as SQLAlchemyString, Text, JSON, Boolean, Index, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel, Column

from kiwi_app.auth.utils import datetime_now_utc
from kiwi_app.settings import settings

table_prefix = f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}"

# Forward declaration needed if RolePermission is defined after its use
# class RolePermission:
#     pass

# --- RolePermission Link Table (Define before use in Role/Permission) --- #
# Define the link model WITHOUT table=True
class RolePermission(SQLModel, table=True):
    __tablename__ = f"{table_prefix}role_permission_link"

    role_id: uuid.UUID = Field(foreign_key=f"{table_prefix}role.id", primary_key=True)
    permission_id: uuid.UUID = Field(foreign_key=f"{table_prefix}permission.id", primary_key=True)

# --- Permission Model --- #
class Permission(SQLModel, table=True):
    __tablename__ = f"{table_prefix}permission"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    name: str = Field(sa_column=Column(SQLAlchemyString, unique=True, index=True))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)

    # Use the RolePermission class (without table=True) as the link_model
    #     heroes: list["Hero"] = Relationship(back_populates="teams", link_model=HeroTeamLink)
    roles: List["Role"] = Relationship(back_populates="permissions", link_model=RolePermission)

# --- Role Model --- #
class Role(SQLModel, table=True):
    __tablename__ = f"{table_prefix}role"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    name: str = Field(sa_column=Column(SQLAlchemyString, unique=True, index=True))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Can store default roles or system roles marker if needed
    is_system_role: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=datetime_now_utc, nullable=False, sa_column_kwargs={"onupdate": datetime_now_utc})

    # Use the RolePermission class (without table=True) as the link_model
    permissions: List[Permission] = Relationship(back_populates="roles", link_model=RolePermission)

    # Relationship to UserOrganizationRole Link Table
    user_assignments: List["UserOrganizationRole"] = Relationship(back_populates="role")

# --- UserOrganizationRole Link Table (User <-> Org <-> Role) --- #
# Keep table=True for this link table as it has extra fields (created_at)
class UserOrganizationRole(SQLModel, table=True):
    __tablename__ = f"{table_prefix}user_org_role"

    user_id: uuid.UUID = Field(foreign_key=f"{table_prefix}user.id", primary_key=True)
    organization_id: uuid.UUID = Field(foreign_key=f"{table_prefix}org.id", primary_key=True)
    role_id: uuid.UUID = Field(foreign_key=f"{table_prefix}role.id") # Role within this specific org

    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)

    # Relationships to access linked objects
    user: "User" = Relationship(back_populates="organization_links")
    organization: "Organization" = Relationship(back_populates="user_links")
    role: Role = Relationship(back_populates="user_assignments")

# --- Organization Model --- #
class Organization(SQLModel, table=True):
    __tablename__ = f"{table_prefix}org"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    name: str = Field(sa_column=Column(SQLAlchemyString, index=True))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=datetime_now_utc, nullable=False, sa_column_kwargs={"onupdate": datetime_now_utc})

    # Relationships
    user_links: List[UserOrganizationRole] = Relationship(back_populates="organization")

# --- User Model --- #
class User(SQLModel, table=True):
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
    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=datetime_now_utc, nullable=False, sa_column_kwargs={"onupdate": datetime_now_utc})

    organization_links: List[UserOrganizationRole] = Relationship(back_populates="user")
    refresh_tokens: List["RefreshToken"] = Relationship(back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

# --- NEW: Refresh Token Model --- #
class RefreshToken(SQLModel, table=True):
    __tablename__ = f"{table_prefix}refresh_token"

    token: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), server_default=text("gen_random_uuid()"), primary_key=True, unique=True, index=True)
    )
    user_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{table_prefix}user.id"), index=True))
    expires_at: datetime = Field(nullable=False)
    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)
    revoked_at: Optional[datetime] = Field(default=None, nullable=True)

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
