import uuid
from typing import Any, Dict, List, Literal, Optional, Set, Union
from pydantic import BaseModel, EmailStr, Field, HttpUrl, model_validator, ConfigDict # Use Field for validation
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
    primary_billing_email: Optional[EmailStr] = None
    is_active: bool

class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class OrganizationBillingEmailUpdate(BaseModel):
    """
    Schema for updating an organization's primary billing email.
    
    This schema is used when manually updating the billing contact email
    for an organization, separate from the automatic updates that happen
    when users are added/removed.
    
    Attributes:
        primary_billing_email: The new primary billing email address, 
                              or None to clear the current email
    """
    primary_billing_email: EmailStr = Field(..., description="Primary billing email address for the organization.")

# --- UserOrganizationRole Link Schemas ---
class UserOrganizationRoleRead(BaseModel):
    organization: OrganizationRead
    role: RoleRead # Embed role details, which includes permissions
    created_at: datetime

class UserDeleteRequest(BaseModel):
    """
    Schema for requesting user deletion.
    
    This schema is used when a user or admin requests to delete a user account.
    It supports deletion by either email or user_id, with at least one required.
    
    Attributes:
        email: Optional email address of the user to delete
        user_id: Optional UUID of the user to delete
        permanent: Whether to permanently delete the user or just deactivate
        confirmation: Required confirmation string to prevent accidental deletions
    """
    email: Optional[EmailStr] = None
    user_id: Optional[uuid.UUID] = None
    # permanent: bool = False  # Default to soft delete (deactivation)
    # confirmation: str = Field(
    #     ...,  # Required field
    #     description="Type 'DELETE' to confirm this destructive action"
    # )
    
    # @field_validator('confirmation')
    # def validate_confirmation(cls, v):
    #     """Validates that the confirmation field contains the expected value."""
    #     if v != "DELETE":
    #         raise ValueError("Confirmation must be exactly 'DELETE' to proceed with user deletion")
    #     return v
    
    @model_validator(mode='before')
    def check_email_or_id_present(cls, values):
        """Validates that at least one identifier (email or user_id) is provided."""
        email = values.get('email')
        user_id = values.get('user_id')
        if not email and not user_id:
            raise ValueError("Either email or user_id must be provided")
        if email and user_id:
            raise ValueError("Only one of email or user_id should be provided")
        return values


class UserAssignRole(BaseModel):
    user_email: EmailStr # Assign by email for easier API use
    # organization_id: uuid.UUID
    role_name: str # Assign by role name for easier API use

class UserRemoveRole(BaseModel):
    user_email: EmailStr
    # organization_id: uuid.UUID

# --- User Schemas ---
class UserCreate(BaseModel):
    email: EmailStr
    password: Optional[str] = Field(None, min_length=8)
    full_name: Optional[str] = None
    # User creates account, org is created automatically

class UserAdminCreate(UserCreate):
    is_verified: bool = True
    is_superuser: bool = False

class UserRead(UUIDModel, TimestampModel):
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool
    is_verified: bool
    # is_superuser: bool
    linkedin_id: Optional[str] = None

class UserReadWithSuperuserStatus(UserRead):
    is_superuser: bool

# --- UserOrganizationRole Link Schemas with User ---
class UserOrganizationRoleReadWithUser(BaseModel):
    user: UserRead
    organization: OrganizationRead
    role: RoleRead # Embed role details, which includes permissions
    created_at: datetime

class UserReadWithOrgs(UserRead):
    # Include organization memberships with roles
    organization_links: List[UserOrganizationRoleRead] = []

class UserReadWithOrgsFiltered(UserRead):
    """
    User read schema with filtered organization links.
    
    This schema is used when we need to return a user with a filtered subset
    of their organization links (e.g., only active organizations) without
    modifying the underlying ORM object.
    """
    # Include organization memberships with roles
    organization_links: List[UserOrganizationRoleRead] = []
    
    @classmethod
    def from_orm_with_filter(cls, user: Any, show_inactive: bool = False) -> "UserReadWithOrgsFiltered":
        """
        Create instance from ORM object with optional organization filtering.
        
        Args:
            user: The ORM User object with loaded organization_links
            show_inactive: If True, include all orgs. If False, only include active orgs.
            
        Returns:
            UserReadWithOrgsFiltered instance with appropriately filtered links
        """
        # Convert base user fields
        user_data = {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "linkedin_id": user.linkedin_id,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "organization_links": []
        }
        
        # Filter organization links if needed
        if hasattr(user, 'organization_links') and user.organization_links:
            for link in user.organization_links:
                # Include all links if show_inactive=True, otherwise only active orgs
                if show_inactive or (link.organization and link.organization.is_active):
                    user_data["organization_links"].append(UserOrganizationRoleRead(
                        organization=OrganizationRead.model_validate(link.organization.model_dump()),
                        role=RoleRead.model_validate(link.role.model_dump()),
                        created_at=link.created_at
                    ))
        
        return cls(**user_data)

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


class TokenData(BaseModel):
    # Use user *ID* (UUID) in the token subject for uniqueness
    token_type: Literal["access", "password_reset", "email_verification", "magic_link", "email_change", "linkedin_verification", "oauth_session", "oauth_state"] = "access"
    sub: Union[uuid.UUID, str] # Changed from email to UUID
    csrf_token: Optional[str] = None
    additional_claims: Dict[str, Any] = {}
    # Optional claim to specifically allow password reset
    # password_reset: Optional[bool] = None

class AccessTokenResponse(BaseModel):
    """Response containing only the access token."""
    status: str
    # access_token: str
    # token_type: str = "bearer"

# --- LinkedIn User Schema --- (Moved from linkedin.py)
class LinkedInUser(BaseModel):
    """Schema representing user information obtained from LinkedIn SSO."""
    id: str # LinkedIn's unique ID for the user
    display_name: Optional[str] = Field(None)
    email: Optional[EmailStr] = None # Email might require specific permissions/scopes
    picture: Optional[HttpUrl] = None # Profile picture URL
    provider: str = "linkedin" # Added by fastapi-sso

    model_config = ConfigDict(
        populate_by_name=True,  # Handles aliases if LinkedIn uses different field names
        extra="ignore"
    )

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

# --- Email Change Management Schemas ---

class RequestEmailChange(BaseModel):
    """
    Schema for requesting an email address change.
    
    Requires current password for security verification before sending
    verification email to the new address.
    
    Attributes:
        new_email: The new email address to change to
        current_password: Current password for security verification
    """
    new_email: EmailStr = Field(..., description="New email address to change to")
    current_password: Optional[str] = Field(None, description="Current password for security verification")

class ConfirmEmailChange(BaseModel):
    """
    Schema for confirming an email address change using a verification token.
    
    The token is sent to the new email address and must be used to complete
    the email change process.
    
    Attributes:
        token: Verification token from the new email address
    """
    token: str = Field(..., description="Email change verification token from the new email")

class EmailChangeResponse(BaseModel):
    """
    Response schema for successful email change operations.
    
    Attributes:
        message: Success message
        new_email: The new email address that was set
    """
    message: str
    new_email: EmailStr

