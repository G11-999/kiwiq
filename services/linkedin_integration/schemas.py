"""
LinkedIn OAuth Schemas

This module defines Pydantic schemas for LinkedIn OAuth operations,
following KiwiQ's established patterns for request/response models.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid

from pydantic import BaseModel, Field, EmailStr, field_validator, ConfigDict

from kiwi_app.auth.models import User
from linkedin_integration.models import LinkedinUserOauth, LinkedinAccountType, OrgLinkedinAccountStatus


# Enums
class OauthAction(str, Enum):
    """OAuth flow action types for different user scenarios"""
    LOGIN_SUCCESS = "login_success"
    ACCOUNT_LINKED = "account_linked"
    REGISTRATION_REQUIRED = "registration_required"
    VERIFICATION_REQUIRED = "verification_required"
    CONFLICT_RESOLUTION = "conflict_resolution"
    ERROR = "error"


# Request Schemas
class LinkedinOauthCallback(BaseModel):
    """Schema for LinkedIn OAuth callback parameters"""
    code: str = Field(..., description="Authorization code from LinkedIn")
    state: Optional[str] = Field(None, description="State parameter for CSRF protection")
    error: Optional[str] = Field(None, description="Error code from LinkedIn")
    error_description: Optional[str] = Field(None, description="Error description from LinkedIn")


class CompleteLinkedinRegistration(BaseModel):
    """Schema for completing registration with LinkedIn data"""
    full_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    organization_name: Optional[str] = Field(None, max_length=200)
    # agree_to_terms: bool = Field(..., description="User agreement to terms")


class LinkExistingAccount(BaseModel):
    """Schema for linking LinkedIn to existing KIWIQ account"""
    email: EmailStr = Field(..., description="Email of existing KIWIQ account")
    password: Optional[str] = Field(None, description="Password for verification (Optional, circumvents email verification)")


class LinkLinkedinAccount(BaseModel):
    """Schema for linking LinkedIn account to logged-in user"""
    redirect_url: Optional[str] = Field(None, description="URL to redirect after linking")


class UnlinkLinkedinAccount(BaseModel):
    """Schema for unlinking LinkedIn account"""
    confirm: bool = Field(..., description="Confirmation flag")


class RequestVerificationEmail(BaseModel):
    """Schema for requesting a verification email."""
    pass


class ProvideEmail(BaseModel):
    """Schema for providing an email address manually."""
    email: EmailStr = Field(..., description="User-provided email address")


# Response Schemas
class LinkedinConnectionStatus(BaseModel):
    """Status of LinkedIn connection for a user"""
    is_connected: bool
    linkedin_id: Optional[str] = None
    email: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_expired: bool = False
    scopes: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    redirect_url: Optional[str] = None
    user_info: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)


class OauthStateInfo(BaseModel):
    """Information from OAuth state token"""
    linkedin_id: str
    email: Optional[str]
    name: Optional[str]
    expires_at: datetime
    action_required: OauthAction


class LinkedinOauthRead(BaseModel):
    """Read schema for LinkedIn OAuth connection"""
    id: str = Field(..., description="LinkedIn ID (sub)")
    user_id: uuid.UUID
    linkedin_email: Optional[str] = None
    scopes: List[str]
    token_expires_at: Optional[datetime]
    refresh_token_expires_at: Optional[datetime]
    is_expired: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class OauthCallbackResult(BaseModel):
    """Result of OAuth callback processing"""
    success: bool
    action: OauthAction
    user: Optional[User] = None
    linkedin_oauth: Optional[LinkedinUserOauth] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    message: str
    requires_action: bool
    redirect_url: Optional[str] = None
    user_info: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)


class StateTokenData(BaseModel):
    """Data contained in OAuth state tokens"""
    user_id: Optional[str] = None
    logged_in_flow: bool = False
    linkedin_id: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    email_verified: bool = False
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    exp: int
    iat: int


class LinkedInTokenRefreshRequest(BaseModel):
    """Request to refresh LinkedIn access token"""
    refresh_token: str = Field(..., description="LinkedIn refresh token")


class LinkedInTokenRefreshResponse(BaseModel):
    """Response from LinkedIn token refresh"""
    access_token: str
    expires_in: int
    refresh_token: Optional[str] = None
    refresh_token_expires_in: Optional[int] = None


# Additional schemas for completeness
class LinkedInProfileUpdate(BaseModel):
    """Schema for updating LinkedIn profile information in KIWIQ"""
    sync_profile_data: bool = Field(True, description="Whether to sync profile data from LinkedIn")
    sync_profile_picture: bool = Field(True, description="Whether to sync profile picture")


class LinkedInSyncStatus(BaseModel):
    """Status of LinkedIn data synchronization"""
    last_sync_at: Optional[datetime] = None
    sync_enabled: bool = True
    sync_errors: List[str] = Field(default_factory=list)
    next_sync_at: Optional[datetime] = None


class ProvideEmailResult(BaseModel):
    """Result of providing an email address."""
    success: bool
    message: str
    action_required: OauthAction



class OauthCallbackResponse(BaseModel):
    """Response for OAuth callback endpoints"""
    success: bool
    action: OauthAction
    redirect_url: str = Field(..., description="URL to redirect the user to")
    message: str = Field(..., description="Status message for the user")
    error_code: Optional[str] = Field(None, description="Error code if applicable")
    user_info: Optional[Dict[str, Any]] = Field(None, description="Additional user information")
    requires_cookies: bool = Field(False, description="Whether auth cookies were set")
    
    model_config = ConfigDict(from_attributes=True)


class OauthVerificationResponse(BaseModel):
    """Response for OAuth verification endpoints"""
    success: bool
    redirect_url: str = Field(..., description="URL to redirect the user to")
    message: str = Field(..., description="Status message for the user")
    error_code: Optional[str] = Field(None, description="Error code if applicable")
    requires_cookies: bool = Field(False, description="Whether auth cookies were set")
    
    model_config = ConfigDict(from_attributes=True)


class LinkedInInitiateResponse(BaseModel):
    """Response for initiating the LinkedIn OAuth flow."""
    authorization_url: str = Field(..., description="The URL to redirect the user to for LinkedIn authorization.")


# Admin schemas for LinkedIn OAuth management
class AdminDeleteLinkedinOauthByLinkedinId(BaseModel):
    """Schema for admin deletion of LinkedIn OAuth by LinkedIn ID"""
    linkedin_id: str = Field(..., description="LinkedIn user ID (sub) to delete")
    confirm: bool = Field(..., description="Confirmation flag - must be true")
    reason: Optional[str] = Field(None, max_length=500, description="Optional reason for deletion")


class AdminDeleteLinkedinOauthByUserId(BaseModel):
    """Schema for admin deletion of LinkedIn OAuth by user ID"""
    user_id: uuid.UUID = Field(..., description="KIWIQ user ID to delete LinkedIn OAuth for")
    confirm: bool = Field(..., description="Confirmation flag - must be true")
    reason: Optional[str] = Field(None, max_length=500, description="Optional reason for deletion")


class AdminDeleteLinkedinOauthResponse(BaseModel):
    """Response schema for admin LinkedIn OAuth deletion"""
    success: bool = Field(..., description="Whether the deletion was successful")
    deleted: bool = Field(..., description="Whether a record was actually deleted")
    linkedin_id: Optional[str] = Field(None, description="LinkedIn ID that was deleted")
    user_id: Optional[uuid.UUID] = Field(None, description="User ID that was affected")
    message: str = Field(..., description="Status message")
    
    model_config = ConfigDict(from_attributes=True)


class AdminLinkedinOauthListItem(BaseModel):
    """Schema for admin list view of LinkedIn OAuth records"""
    id: str = Field(..., description="LinkedIn ID (sub)")
    user_id: Optional[uuid.UUID] = Field(None, description="Associated KIWIQ user ID")
    user_email: Optional[str] = Field(None, description="Associated user email")
    user_full_name: Optional[str] = Field(None, description="Associated user full name")
    oauth_state: str = Field(..., description="Current OAuth state")
    scopes: List[str] = Field(default_factory=list, description="LinkedIn permissions")
    token_expires_at: Optional[datetime] = Field(None, description="Access token expiration")
    is_expired: bool = Field(..., description="Whether the access token is expired")
    created_at: datetime = Field(..., description="OAuth record creation time")
    updated_at: datetime = Field(..., description="Last update time")
    
    model_config = ConfigDict(from_attributes=True)


class AdminLinkedinOauthListResponse(BaseModel):
    """Response schema for admin LinkedIn OAuth list"""
    records: List[AdminLinkedinOauthListItem] = Field(default_factory=list)
    total_count: int = Field(..., description="Total number of records (for pagination)")
    limit: int = Field(..., description="Records per page limit")
    offset: int = Field(..., description="Number of records skipped")
    has_more: bool = Field(..., description="Whether there are more records available")
    
    model_config = ConfigDict(from_attributes=True)


# LinkedIn Integration Schemas

class LinkedinIntegrationBase(BaseModel):
    """Base schema for LinkedIn integrations."""
    linkedin_id: str = Field(..., description="LinkedIn sub/ID of the integration owner")
    scope: Optional[str] = Field(None, description="OAuth scopes for the integration")
    integration_state: str = Field(..., description="Current state of the integration")
    linkedin_orgs_roles: Optional[Dict[str, Any]] = Field(None, description="LinkedIn organizations and roles")
    
    model_config = ConfigDict(from_attributes=True)


class LinkedinIntegrationCreate(BaseModel):
    """Schema for creating a LinkedIn integration."""
    pass  # Created through OAuth callback process


class LinkedinIntegrationRead(LinkedinIntegrationBase):
    """Read schema for LinkedIn integration."""
    id: uuid.UUID
    user_id: uuid.UUID
    is_expired: Optional[bool] = Field(None, description="Whether the access token is expired")
    token_expires_at: Optional[datetime]
    last_sync_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class LinkedinIntegrationUpdate(BaseModel):
    """Schema for updating LinkedIn integration."""
    linkedin_orgs_roles: Optional[Dict[str, Any]] = Field(None, description="Updated organizations and roles")


class LinkedinAccountBase(BaseModel):
    """Base schema for LinkedIn accounts."""
    id: str = Field(..., description="LinkedIn identifier (person or org ID)")
    account_type: LinkedinAccountType = Field(..., description="Type of LinkedIn account (person or organization)")
    name: Optional[str] = Field(None, description="Account name")
    vanity_name: Optional[str] = Field(None, description="LinkedIn vanity name/username (e.g., company URL slug)")
    profile_data: Optional[Dict[str, Any]] = Field(None, description="Cached profile data")
    
    model_config = ConfigDict(from_attributes=True)


class LinkedinAccountCreate(BaseModel):
    """Schema for creating a LinkedIn account."""
    id: str = Field(..., description="LinkedIn identifier")
    account_type: LinkedinAccountType = Field(..., description="Type of LinkedIn account (person or organization)")
    name: Optional[str] = Field(None, description="Account name")
    vanity_name: Optional[str] = Field(None, description="LinkedIn vanity name/username")
    profile_data: Optional[Dict[str, Any]] = Field(None, description="Profile data")


class LinkedinAccountRead(LinkedinAccountBase):
    """Read schema for LinkedIn account."""
    last_updated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class OrgLinkedinAccountBase(BaseModel):
    """Base schema for org LinkedIn accounts."""
    linkedin_account_id: str = Field(..., description="LinkedIn account ID")
    linkedin_integration_id: uuid.UUID = Field(..., description="Integration ID")
    role_in_linkedin_entity: Optional[str] = Field(None, description="Role in the LinkedIn entity (e.g., ADMINISTRATOR, DIRECT_SPONSORED_CONTENT_POSTER)")
    is_shared: bool = Field(True, description="Whether shared with org")
    is_active: bool = Field(True, description="Whether the account is active")
    status: OrgLinkedinAccountStatus = Field(OrgLinkedinAccountStatus.ACTIVE, description="Current status of the LinkedIn account integration")
    
    model_config = ConfigDict(from_attributes=True)


class OrgLinkedinAccountCreate(BaseModel):
    """Schema for creating an org LinkedIn account."""
    linkedin_account_id: str = Field(..., description="LinkedIn account ID to share")
    linkedin_integration_id: uuid.UUID = Field(..., description="Integration to use")
    is_shared: bool = Field(True, description="Whether to share with org")


class OrgLinkedinAccountRead(OrgLinkedinAccountBase):
    """Read schema for org LinkedIn account."""
    id: uuid.UUID
    managed_by_user_id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    
    # Nested data
    linkedin_account: Optional[LinkedinAccountRead] = None
    linkedin_integration: Optional[LinkedinIntegrationRead] = None
    
    model_config = ConfigDict(from_attributes=True)


class OrgLinkedinAccountUpdate(BaseModel):
    """Schema for updating org LinkedIn account."""
    is_shared: Optional[bool] = Field(None, description="Update sharing status")
    is_active: Optional[bool] = Field(None, description="Update active status")


class LinkedinIntegrationInitiateResponse(BaseModel):
    """Response for initiating LinkedIn integration flow."""
    authorization_url: str = Field(..., description="URL to redirect user for LinkedIn authorization")


class LinkedinIntegrationCallbackResponse(BaseModel):
    """Response for LinkedIn integration callback."""
    success: bool
    integration_id: Optional[uuid.UUID] = Field(None, description="Created integration ID")
    message: str
    linkedin_orgs_roles: Optional[Dict[str, Any]] = Field(None, description="Available organizations and roles")


class LinkedinIntegrationListResponse(BaseModel):
    """Response for listing user's LinkedIn integrations."""
    integrations: List[LinkedinIntegrationRead]
    total: int
    
    model_config = ConfigDict(from_attributes=True)


class OrgLinkedinAccountListResponse(BaseModel):
    """Response for listing organization's LinkedIn accounts."""
    accounts: List[OrgLinkedinAccountRead]
    total: int
    
    model_config = ConfigDict(from_attributes=True)


# New schemas for sync and listing user's accessible accounts

class LinkedinAccountWithRole(BaseModel):
    """LinkedIn account with user's role information."""
    account: LinkedinAccountRead
    role: Optional[str] = Field(None, description="User's role in this LinkedIn entity")
    integration_id: uuid.UUID = Field(..., description="Integration ID used to access this account")
    integration_state: str = Field(..., description="State of the integration")
    can_post: bool = Field(..., description="Whether user can post on behalf of this account")
    
    model_config = ConfigDict(from_attributes=True)


class UserAccessibleLinkedinAccountsResponse(BaseModel):
    """Response for listing all user's accessible LinkedIn accounts."""
    personal_account: Optional[LinkedinAccountWithRole] = Field(None, description="User's personal LinkedIn account")
    organization_accounts: List[LinkedinAccountWithRole] = Field(default_factory=list, description="Organization accounts user has access to")
    total: int = Field(..., description="Total number of accessible accounts")
    
    model_config = ConfigDict(from_attributes=True)


class SyncIntegrationRequest(BaseModel):
    """Request to sync a LinkedIn integration."""
    integration_id: uuid.UUID = Field(..., description="Integration ID to sync")
    
    
class SyncIntegrationResponse(BaseModel):
    """Response for syncing LinkedIn integration."""
    success: bool
    integration_id: uuid.UUID
    message: str
    accounts_synced: int = Field(0, description="Number of accounts synced")
    new_accounts: int = Field(0, description="Number of new accounts discovered")
    updated_accounts: int = Field(0, description="Number of accounts updated")
    errors: List[str] = Field(default_factory=list, description="Any errors encountered during sync")
    
    model_config = ConfigDict(from_attributes=True)


class RefreshAllIntegrationsResponse(BaseModel):
    """Response for refreshing all user's LinkedIn integrations."""
    success: bool
    message: str
    integrations_processed: int = Field(0, description="Number of integrations processed")
    accounts_synced: int = Field(0, description="Total number of accounts synced")
    errors: Dict[str, List[str]] = Field(default_factory=dict, description="Errors by integration ID")
    
    model_config = ConfigDict(from_attributes=True)
