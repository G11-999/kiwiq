import uuid
from typing import List, Optional, Set
from pydantic import BaseModel, EmailStr, Field, HttpUrl # Use Field for validation
from datetime import datetime

# Import base models from models.py to inherit from
# from .models import UserBase, OrganizationBase, RoleBase, UserOrganizationRoleRead

# --- Base Schemas (used for consistency) ---
class UUIDModel(BaseModel):
    id: uuid.UUID

class TimestampModel(BaseModel):
    created_at: datetime
    updated_at: datetime

# --- Permission Schemas ---
class PermissionBase(BaseModel):
    name: str
    description: Optional[str] = None

class PermissionCreate(PermissionBase):
    pass

class PermissionRead(PermissionBase, UUIDModel):
    created_at: datetime

# --- Role Schemas ---
class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None

class RoleCreate(RoleBase):
    permissions: List[str] = [] # List of permission *names* to link

class RoleRead(RoleBase, UUIDModel, TimestampModel):
    # permissions: Optional[List[PermissionRead]] = [] # Embed permission details
    is_system_role: bool

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None # Allow updating linked permissions by name

# --- Organization Schemas ---
class OrganizationBase(BaseModel):
    name: str
    description: Optional[str] = None

class OrganizationCreate(OrganizationBase):
    # Optionally, allow specifying initial admin during creation?
    pass

class OrganizationRead(OrganizationBase, UUIDModel, TimestampModel):
    pass # Add relationships later if needed, e.g., list of members

class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

# --- UserOrganizationRole Link Schemas ---
class UserOrganizationRoleRead(BaseModel):
    organization: OrganizationRead
    role: RoleRead # Embed role details, which includes permissions
    created_at: datetime


class UserAssignRole(BaseModel):
    user_email: EmailStr # Assign by email for easier API use
    # organization_id: uuid.UUID
    role_name: str # Assign by role name for easier API use

class UserRemoveRole(BaseModel):
    user_email: EmailStr
    organization_id: uuid.UUID

# --- User Schemas ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    # User creates account, org is created automatically

class UserRead(UUIDModel, TimestampModel):
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool
    is_verified: bool
    # is_superuser: bool
    linkedin_id: Optional[str] = None


# --- UserOrganizationRole Link Schemas with User ---
class UserOrganizationRoleReadWithUser(BaseModel):
    user: UserRead
    organization: OrganizationRead
    role: RoleRead # Embed role details, which includes permissions
    created_at: datetime

class UserReadWithOrgs(UserRead):
    # Include organization memberships with roles
    organization_links: List[UserOrganizationRoleRead] = []

class UserUpdate(BaseModel):
    # Fields users can update about themselves
    full_name: Optional[str] = None
    # Other fields like email change require specific logic/verification

class UserAdminUpdate(BaseModel):
    # Fields admins/superusers can update
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    is_superuser: Optional[bool] = None
    email_verification_token: Optional[str] = None
    hashed_password: Optional[str] = None
    # Password update should be a separate flow/endpoint

class UserLogin(BaseModel):
    username: EmailStr # Using email as the username
    password: str

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    # Use user *ID* (UUID) in the token subject for uniqueness
    sub: uuid.UUID # Changed from email to UUID
    # Optional claim to specifically allow password reset
    password_reset: Optional[bool] = None

class AccessTokenResponse(BaseModel):
    """Response containing only the access token."""
    access_token: str
    token_type: str = "bearer"

# --- LinkedIn User Schema --- (Moved from linkedin.py)
class LinkedInUser(BaseModel):
    """Schema representing user information obtained from LinkedIn SSO."""
    id: str # LinkedIn's unique ID for the user
    display_name: Optional[str] = Field(None)
    email: Optional[EmailStr] = None # Email might require specific permissions/scopes
    picture: Optional[HttpUrl] = None # Profile picture URL
    provider: str = "linkedin" # Added by fastapi-sso

    class Config:
        populate_by_name = True # Handles aliases if LinkedIn uses different field names
        extra = "ignore"

# --- Email Verification Schema ---
class RequestEmailVerification(BaseModel):
    email: EmailStr

# --- Password Management Schemas ---

class UserChangePassword(BaseModel):
    """Schema for authenticated users changing their own password."""
    current_password: str
    new_password: str = Field(..., min_length=8)

class RequestPasswordReset(BaseModel):
    """Schema for requesting a password reset email."""
    email: EmailStr

class ResetPassword(BaseModel):
    """Schema for resetting the password using a token."""
    token: str
    new_password: str = Field(..., min_length=8)

