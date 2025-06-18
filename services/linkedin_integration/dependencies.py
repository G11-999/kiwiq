"""
LinkedIn OAuth Dependencies

This module provides dependency injection functions for LinkedIn OAuth operations,
following KiwiQ's established patterns from the billing and auth modules.
"""

from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status, Cookie
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_async_db_dependency
from kiwi_app.auth.models import User
from kiwi_app.auth import crud as auth_crud
from kiwi_app.auth.dependencies import (
    get_current_user,
    get_current_active_user,
    get_current_active_verified_user,
    get_user_dao,
    get_organization_dao,
    get_auth_service
)
from kiwi_app.auth.services import AuthService
from kiwi_app.utils import get_kiwi_logger

from linkedin_integration import crud, services, models, exceptions
from linkedin_integration.state_manager import LinkedInStateManager

logger = get_kiwi_logger("linkedin_integration.dependencies")


def get_linkedin_oauth_dao() -> crud.LinkedinOauthDAO:
    """Get LinkedinOauthDAO instance"""
    return crud.LinkedinOauthDAO()


def get_linkedin_oauth_service(
    linkedin_oauth_dao: crud.LinkedinOauthDAO = Depends(get_linkedin_oauth_dao),
    user_dao: auth_crud.UserDAO = Depends(get_user_dao),
    org_dao: auth_crud.OrganizationDAO = Depends(get_organization_dao),
    auth_service: AuthService = Depends(get_auth_service)
) -> services.LinkedinOauthService:
    """
    Get LinkedinOauthService with all dependencies injected.
    
    This function creates a LinkedinOauthService instance with all required
    DAOs and services injected, following the dependency injection pattern.
    """
    return services.LinkedinOauthService(
        linkedin_oauth_dao=linkedin_oauth_dao,
        user_dao=user_dao,
        org_dao=org_dao,
        auth_service=auth_service
    )


class RequireLinkedinConnection:
    """
    Dependency to ensure user has LinkedIn connected.
    
    This dependency class checks that the current user has an active
    LinkedIn connection before allowing access to the endpoint.
    """
    
    async def __call__(
        self,
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_async_db_dependency),
        linkedin_oauth_dao: crud.LinkedinOauthDAO = Depends(get_linkedin_oauth_dao)
    ) -> User:
        """
        Verify user has LinkedIn connected and attach OAuth record.
        
        Args:
            current_user: The authenticated user
            db: Database session
            linkedin_oauth_dao: LinkedIn OAuth DAO
            
        Returns:
            User with linkedin_oauth attribute attached
            
        Raises:
            HTTPException: 403 if LinkedIn not connected
        """
        oauth_record = await linkedin_oauth_dao.get_by_user_id(db, current_user.id)
        
        if not oauth_record:
            logger.warning(f"User {current_user.email} attempted to access LinkedIn-required endpoint without connection")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="LinkedIn account not connected. Please connect your LinkedIn account in settings."
            )
        
        # Check if token is expired
        if oauth_record.is_access_token_expired():
            logger.info(f"LinkedIn token expired for user {current_user.email}")
            # Could attempt refresh here or return specific error
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="LinkedIn access token has expired. Please reconnect your LinkedIn account."
            )
        
        # # Attach OAuth record to user for convenience
        # current_user.linkedin_oauth = oauth_record
        return current_user


class RequireNoLinkedinConnection:
    """
    Dependency to ensure user has NO LinkedIn connected.
    
    This dependency is used for endpoints where having an existing
    LinkedIn connection would be a conflict, such as initial connection flows.
    """
    
    async def __call__(
        self,
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_async_db_dependency),
        linkedin_oauth_dao: crud.LinkedinOauthDAO = Depends(get_linkedin_oauth_dao)
    ) -> User:
        """
        Verify user has no LinkedIn connected.
        
        Args:
            current_user: The authenticated user
            db: Database session
            linkedin_oauth_dao: LinkedIn OAuth DAO
            
        Returns:
            User without LinkedIn connection
            
        Raises:
            HTTPException: 409 if LinkedIn already connected
        """
        oauth_record = await linkedin_oauth_dao.get_by_user_id(db, current_user.id)
        
        if oauth_record:
            logger.info(f"User {current_user.email} attempted to connect LinkedIn but already has connection")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="LinkedIn account already connected. Please disconnect it first in settings."
            )
        
        return current_user


async def get_linkedin_oauth_state_from_cookie(
    linkedin_oauth_state: Optional[str] = Cookie(None)
) -> Optional[str]:
    """
    Get LinkedIn OAuth state token from cookie.
    
    This dependency extracts the OAuth state token from cookies,
    used during the registration/linking flow after OAuth callback.
    
    Args:
        linkedin_oauth_state: Cookie value
        
    Returns:
        State token string or None if not present
    """
    return linkedin_oauth_state


class RequireValidLinkedinState:
    """
    Dependency to validate LinkedIn OAuth state from cookie.
    
    This dependency ensures that a valid OAuth state token is present
    in cookies, typically used for registration/linking endpoints.
    """
    
    async def __call__(
        self,
        state_token: Optional[str] = Depends(get_linkedin_oauth_state_from_cookie)
    ) -> str:
        """
        Validate OAuth state token from cookie.
        
        Args:
            state_token: State token from cookie
            
        Returns:
            Valid state token
            
        Raises:
            HTTPException: 400 if state token missing or invalid
        """
        if not state_token:
            logger.warning("LinkedIn OAuth state token missing from cookie")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="LinkedIn OAuth state not found. Please restart the connection process."
            )
        
        # Additional validation could be done here
        # For now, just ensure it exists
        return state_token


async def get_linkedin_connected_users_in_org(
    org_id: str,
    db: AsyncSession = Depends(get_async_db_dependency),
    linkedin_oauth_dao: crud.LinkedinOauthDAO = Depends(get_linkedin_oauth_dao),
    current_user: User = Depends(get_current_active_verified_user)
) -> int:
    """
    Get count of LinkedIn-connected users in an organization.
    
    This dependency is useful for analytics and limits checking.
    
    Args:
        org_id: Organization ID
        db: Database session
        linkedin_oauth_dao: LinkedIn OAuth DAO
        current_user: Current authenticated user
        
    Returns:
        Number of LinkedIn connections in the organization
    """
    # Verify user has access to this organization
    # This would need additional checks in production
    
    count = await linkedin_oauth_dao.count_by_organization(db, org_id)
    return count


async def get_verified_linkedin_oauth_state(
    state_token: Optional[str] = Cookie(None, alias="linkedin_oauth_state")
) -> Dict[str, Any]:
    """
    FastAPI dependency to get and verify the LinkedIn OAuth state from cookie.

    This dependency extracts the state token from the `linkedin_oauth_state`
    cookie, verifies it, and returns the decoded claims. It ensures that
    any endpoint using it is part of a valid, ongoing OAuth flow.

    Args:
        state_token: The state token from the cookie.

    Returns:
        The dictionary of claims from the verified token.

    Raises:
        HTTPException: 400 Bad Request if the token is missing, invalid, or expired.
    """
    if not state_token:
        logger.warning("LinkedIn OAuth state token missing from cookie")
        raise exceptions.LinkedInStateException(
            "OAuth state cookie not found. Please start the process again."
        )

    state_data = LinkedInStateManager.verify_oauth_session_token(state_token)
    if not state_data:
        logger.warning("Invalid or expired LinkedIn OAuth state token provided.")
        raise exceptions.LinkedInStateException(
            "Invalid or expired OAuth state. Please try again."
        )
    
    return state_data 