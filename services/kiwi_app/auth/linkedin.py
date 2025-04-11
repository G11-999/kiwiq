import os
from typing import Optional, Dict, Any

from fastapi import Request, HTTPException, status
from fastapi_sso.sso.linkedin import LinkedInSSO
from pydantic import BaseModel, HttpUrl, Field, EmailStr

from urllib.parse import urlencode
from global_config.settings import global_settings
from kiwi_app.settings import settings
from kiwi_app.auth.utils import auth_logger
from kiwi_app.auth.schemas import LinkedInUser

# Load configuration from settings
LINKEDIN_CLIENT_ID = global_settings.LINKEDIN_CLIENT_ID
LINKEDIN_CLIENT_SECRET = global_settings.LINKEDIN_CLIENT_SECRET
LINKEDIN_REDIRECT_URL = global_settings.LINKEDIN_REDIRECT_URL
# LINKEDIN_AUTHORIZATION_URL = "https://www.linkedin.com/oauth/v2/authorization"
# LINKEDIN_ACCESS_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
# LINKEDIN_USER_INFO_URL = "https://api.linkedin.com/v2/userinfo"
# LINKEDIN_SCOPE = "profile email openid w_member_social"

# Allow insecure transport for local development if needed (e.g., http://localhost)
# Set environment variable OAUTHLIB_INSECURE_TRANSPORT=1 if running locally without HTTPS
# Alternatively, set allow_insecure_http=True here, but be cautious in production.
allow_insecure = os.getenv("OAUTHLIB_INSECURE_TRANSPORT") == "1"

# Basic validation
if not all([LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REDIRECT_URL]):
    # You might want to raise a more specific configuration error or log a warning
    print("Warning: LinkedIn OAuth2 credentials or redirect URI not fully configured.")
    # Depending on your setup, you might want to disable LinkedIn login if not configured.
    # For now, we'll allow the SSO object creation, but it will fail at runtime.
    linkedin_sso = None
else:
    linkedin_sso = LinkedInSSO(
        client_id=LINKEDIN_CLIENT_ID,
        client_secret=LINKEDIN_CLIENT_SECRET,
        redirect_uri=LINKEDIN_REDIRECT_URL,
        allow_insecure_http=allow_insecure,
        # Specify required scopes. 'openid', 'profile', 'email' are common for user info.
        # Check LinkedIn documentation for available scopes: https://learn.microsoft.com/en-us/linkedin/shared/integrations/people/profile-api?context=linkedin/consumer/context#scopes
        scope=["openid", "profile", "email"],
        # Use 'state' for CSRF protection (recommended)
        # fastapi-sso handles state generation and verification internally
        use_state=True,
    )

async def get_linkedin_login_url() -> Optional[str]:
    """
    Generates the LinkedIn authorization URL.

    Returns:
        The URL to redirect the user to for LinkedIn login, or None if not configured.
    """
    if not linkedin_sso:
        return None
    # The library handles state generation internally when use_state=True
    return await linkedin_sso.get_login_redirect()

async def verify_linkedin_callback(request) -> Optional[LinkedInUser]:
    """
    Verifies the callback request from LinkedIn and processes user information.

    Args:
        request: The Starlette request object containing callback parameters.

    Returns:
        A LinkedInUser object with the authenticated user's details, or None if not configured.

    Raises:
        HTTPException: If the verification fails (e.g., state mismatch, invalid code).
                       The exception is raised by `linkedin_sso.verify_and_process`.
    """
    if not linkedin_sso:
        # Should ideally not happen if login URL wasn't generated,
        # but handle defensively.
        return None

    # verify_and_process handles:
    # 1. Checking for errors from LinkedIn (e.g., user denied access)
    # 2. Validating the state parameter (CSRF protection)
    # 3. Exchanging the authorization code for an access token
    # 4. Fetching user information using the access token
    # It returns a Pydantic model (or dict) matching the provider's response.
    try:
        sso_user = await linkedin_sso.verify_and_process(request)
        # Validate/parse the received user info using our Pydantic model
        # Note: Email might be missing if user hasn't set a primary email or scope wasn't granted
        linkedin_user = LinkedInUser.model_validate(sso_user)
        # You might need additional logic here if email is crucial and missing
        if not linkedin_user.email:
             print(f"Warning: LinkedIn user {linkedin_user.id} ({linkedin_user.display_name}) missing email.")
             # Decide how to handle users without email (e.g., raise error, prompt user)
             # For now, we'll proceed but log a warning.
        return linkedin_user
    except Exception as e:
        # Log the error for debugging
        print(f"LinkedIn SSO verification failed: {e}")
        # Re-raise the exception (it's likely an HTTPException from fastapi-sso)
        raise e 
