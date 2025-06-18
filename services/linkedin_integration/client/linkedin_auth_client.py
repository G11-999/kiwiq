import os, sys
from typing import Optional, List, ClassVar
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv, find_dotenv
from linkedin_api.clients.auth.client import AuthClient
from linkedin_api.clients.restli.client import RestliClient
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
import uvicorn
from pydantic import BaseModel, Field

from kiwi_app.settings import settings

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LinkedInAccessTokenSchema(BaseModel):
    """
    Schema for LinkedIn OAuth2 access token response.
    
    This schema represents the complete access token response from LinkedIn's OAuth2 API,
    including both access and refresh tokens with their expiration information.
    
    Design decisions:
    - Uses Pydantic for automatic validation and serialization
    - Includes computed fields for expiration timestamps
    - Provides secure token handling with length validation
    - Supports both access and refresh token workflows
    
    Caveats:
    - Access tokens are ~500 characters but schema allows up to 1000 for future expansion
    - All tokens must be kept secure as per LinkedIn API Terms of Use
    - Refresh tokens may not always be present depending on application configuration
    """

    DATETIME_NOW_KEY: ClassVar[str] = "_datetime_now_"
    
    access_token: str = Field(
        ..., 
        min_length=1, 
        max_length=1000,
        description="The access token for LinkedIn API calls. Must be kept secure."
    )
    
    refresh_token: Optional[str] = Field(
        None, 
        min_length=1, 
        max_length=1000,
        description="Refresh token for obtaining new access tokens. Must be kept secure."
    )
    
    scope: Optional[str] = Field(
        None,
        description="URL-encoded, space-delimited list of authorized permissions"
    )
    
    # Computed fields for easier expiration handling
    token_expires_at: Optional[datetime] = Field(
        None,
        description="Calculated expiration timestamp for access token"
    )
    
    refresh_token_expires_at: Optional[datetime] = Field(
        None,
        description="Calculated expiration timestamp for refresh token"
    )

    expires_in: int = Field(
        ..., 
        gt=0,
        description="Number of seconds until access token expires (typically 60 days)"
    )

    refresh_token_expires_in: Optional[int] = Field(
        None, 
        gt=0,
        description="Number of seconds until refresh token expires"
    )
    
    def __init__(self, **data):
        """
        Initialize the schema with computed expiration timestamps.
        
        This constructor automatically calculates the actual expiration timestamps
        based on the expires_in values, making it easier to check token validity.
        """
        datetime_now = datetime.now(tz=timezone.utc)
        if LinkedInAccessTokenSchema.DATETIME_NOW_KEY in data:
            datetime_now = data.pop(LinkedInAccessTokenSchema.DATETIME_NOW_KEY)
        
        super().__init__(**data)
        
        # Calculate access token expiration timestamp
        if self.expires_in:
            self.token_expires_at = datetime_now + timedelta(seconds=self.expires_in - 1)
        
        # Calculate refresh token expiration timestamp if available
        if self.refresh_token_expires_in:
            self.refresh_token_expires_at = datetime_now + timedelta(seconds=self.refresh_token_expires_in - 1)
    
    def is_access_token_expired(self) -> bool:
        """
        Check if the access token has expired.
        
        Returns:
            bool: True if token is expired, False otherwise
        """
        if not self.token_expires_at:
            return False
        return datetime.now(tz=timezone.utc) >= self.token_expires_at
    
    def is_refresh_token_expired(self) -> bool:
        """
        Check if the refresh token has expired.
        
        Returns:
            bool: True if refresh token is expired, False otherwise
        """
        if not self.refresh_token_expires_at:
            return False
        return datetime.now(tz=timezone.utc) >= self.refresh_token_expires_at
    
    def get_scopes_list(self) -> List[str]:
        """
        Parse the scope string into a list of individual scopes.
        
        Returns:
            List[str]: List of individual scope permissions
        """
        return self.scope.split() if self.scope else []


# LinkedIn OAuth2 scopes for comprehensive API access
# These scopes provide access to member profile data, organization management,
# social feed operations, analytics, and advertising capabilities
LINKEDIN_SCOPES = [
    "email",                       # Access to email address
    "openid",                      # OpenID Connect authentication
    "profile",                     # Access to profile information

    "r_basicprofile",              # Read basic profile information
    "w_member_social",             # Write member social content (posts, comments, likes)
    "r_1st_connections_size",      # Read first-degree connections count
    "w_member_social_feed",        # Write to member social feed
    "r_member_postAnalytics",      # Read member post analytics data
    "r_member_profileAnalytics",   # Read member profile analytics data
    
    "r_organization_admin",        # Read organization admin permissions
    "rw_organization_admin",       # Read/write organization admin permissions
    "r_organization_social_feed",  # Read organization social feed content
    "w_organization_social_feed",  # Write to organization social feed
    "r_organization_social",       # Read organization social content
    "w_organization_social",       # Write organization social content
    "r_organization_followers",    # Read organization follower data
    # "r_ads",                       # Read advertising data
    # "rw_ads",                      # Read/write advertising campaigns
    # "r_ads_reporting",             # Read advertising reports and analytics
]


load_dotenv(find_dotenv())

CLIENT_ID = settings.LINKEDIN_CLIENT_ID
CLIENT_SECRET = settings.LINKEDIN_CLIENT_SECRET
OAUTH2_REDIRECT_URL = settings.LINKEDIN_REDIRECT_URL

# Global variable to store structured access token for testing purposes
# In production, this should be stored securely (database, secure session, etc.)
access_token_data: Optional[LinkedInAccessTokenSchema] = None

# Initialize LinkedIn OAuth2 authentication client
# This client handles the OAuth2 flow for LinkedIn API access


# Generate the LinkedIn authorization URL with required scopes
# Users will be redirected to this URL to grant permissions
# linkedin_redirect_url = auth_client.generate_member_auth_url(scopes=LINKEDIN_SCOPES)
    
# print(f"LinkedIn Authorization URL: {linkedin_redirect_url}")

# Initialize FastAPI application for handling OAuth callback
app = FastAPI(title="LinkedIn OAuth Handler", description="Handles LinkedIn OAuth2 callback")

@app.get("/oauth")
async def oauth_callback(request: Request):
    """
    Handle LinkedIn OAuth2 callback.
    
    This endpoint receives the authorization code from LinkedIn after user consent
    and exchanges it for an access token that can be used for API calls.
    
    Args:
        request: FastAPI request object containing query parameters
        
    Returns:
        RedirectResponse: Redirects to root path after successful token exchange
        
    Query Parameters:
        code: Authorization code from LinkedIn OAuth2 flow
        state: Optional state parameter for CSRF protection
        error: Error code if authorization was denied
        error_description: Human-readable error description
    """
    global access_token_data
    datetime_now = datetime.now(tz=timezone.utc)
    # Extract query parameters from the callback URL
    query_params = request.query_params
    auth_code = query_params.get("code")
    error = query_params.get("error")
    error_description = query_params.get("error_description")
    
    # Handle authorization errors (user denied access, etc.)
    if error:
        logger.error(f"OAuth Error: {error}")
        if error_description:
            logger.error(f"Error Description: {error_description}")
        return {"error": error, "description": error_description}
    
    # Exchange authorization code for access token
    logger.info(f"Processing auth code: {auth_code[:10]}..." if auth_code else "No auth code")
    if auth_code:
        try:
            # Call LinkedIn API to exchange auth code for access token
            auth_client = AuthClient(
                client_id=CLIENT_ID, 
                client_secret=CLIENT_SECRET, 
                redirect_url=OAUTH2_REDIRECT_URL
            )
            
            # Exchange the authorization code for access token
            token_response = auth_client.exchange_auth_code_for_access_token(auth_code)
            
            # Check if the token exchange was successful
            if token_response.status_code != 200:
                logger.error(f"Token exchange failed with status {token_response.status_code}: {token_response.response.content}")
                return {"error": "token_exchange_failed", "description": token_response.response.content}
            
            # Convert the LinkedIn API response to our structured schema
            access_token_data = LinkedInAccessTokenSchema(
                access_token=token_response.access_token,
                expires_in=token_response.expires_in,
                refresh_token=token_response.refresh_token,
                refresh_token_expires_in=token_response.refresh_token_expires_in,
                scope=token_response.scope,
                _datetime_now_=datetime_now,
            )
            
            logger.info(f"Successfully obtained and structured access token")
            logger.info(f"Token expires at: {access_token_data.token_expires_at}")
            logger.info(f"Authorized scopes: {len(access_token_data.get_scopes_list())} scopes")
            
            # In production, you would typically:
            # 1. Store the structured token data securely (database, encrypted session)
            # 2. Associate it with the user's account
            # 3. Set up token refresh workflows using the refresh token
            # 4. Implement token expiration monitoring
            
            return RedirectResponse(url="/", status_code=302)
            
        except Exception as e:
            logger.error(f"Error exchanging auth code for token: {str(e)}", exc_info=True)
            return {"error": "token_exchange_failed", "description": str(e)}
    else:
        return {"error": "missing_auth_code", "description": "No authorization code provided"}

@app.get("/")
async def root():
    """
    Root endpoint showing current authentication status.
    
    Returns:
        dict: Current authentication status and available actions
    """
    if access_token_data:
        return {
            "status": "authenticated",
            "message": "LinkedIn access token obtained successfully",
            "token_info": {
                "access_token": access_token_data.access_token[:20] + "..." if access_token_data.access_token else None,
                "expires_at": access_token_data.token_expires_at.isoformat() if access_token_data.token_expires_at else None,
                "is_expired": access_token_data.is_access_token_expired(),
                "scopes": access_token_data.get_scopes_list(),
                "has_refresh_token": bool(access_token_data.refresh_token),
                "refresh_token_expires_at": access_token_data.refresh_token_expires_at.isoformat() if access_token_data.refresh_token_expires_at else None,
            },
            "next_steps": "You can now use the access token to make LinkedIn API calls"
        }
    else:
        auth_client = AuthClient(
            client_id=CLIENT_ID, 
            client_secret=CLIENT_SECRET, 
            redirect_url=OAUTH2_REDIRECT_URL
        )
        linkedin_redirect_url = auth_client.generate_member_auth_url(scopes=LINKEDIN_SCOPES)
        return {
            "status": "not_authenticated", 
            "message": "No access token available",
            "auth_url": linkedin_redirect_url,
            "instructions": "Visit the auth_url to start LinkedIn OAuth flow"
        }


if __name__ == "__main__":
    uvicorn.run("linkedin_auth_client:app", host="localhost", port=3002, reload=True)
