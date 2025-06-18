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
from linkedin_integration.models import LinkedinUserOauth


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
    agree_to_terms: bool = Field(..., description="User agreement to terms")
    
    @field_validator('agree_to_terms')
    def terms_must_be_accepted(cls, v):
        if not v:
            raise ValueError('Terms must be accepted')
        return v


class LinkExistingAccount(BaseModel):
    """Schema for linking LinkedIn to existing KIWIQ account"""
    email: EmailStr = Field(..., description="Email of existing KIWIQ account")
    password: str = Field(..., description="Password for verification")


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
