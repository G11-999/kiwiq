"""
LinkedIn OAuth Routers

This module defines all API endpoints for LinkedIn OAuth operations,
following KiwiQ's established patterns from the auth and billing routers.
"""

from typing import Optional, Dict, Any
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Query, Body, BackgroundTasks, Cookie, Header
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_async_db_dependency
from kiwi_app.auth.models import User
from kiwi_app.auth.dependencies import get_current_active_user, get_current_active_verified_user, get_auth_service, OptionalCurrentUserChecker
from kiwi_app.auth.csrf import setup_auth_cookies_with_csrf, clear_auth_cookies, generate_csrf_token, set_csrf_cookie, validate_csrf_protection, validate_csrf_token
from kiwi_app.auth.exceptions import CredentialsException, EmailAlreadyExistsException
from kiwi_app.auth.services import AuthService
from kiwi_app.settings import settings
from kiwi_app.utils import get_kiwi_logger

from linkedin_integration import schemas, services, dependencies, exceptions
from linkedin_integration.state_manager import LinkedInStateManager
from linkedin_integration.client.linkedin_auth_client import LINKEDIN_SCOPES

logger = get_kiwi_logger("linkedin_integration.routers")

# Create router with prefix
linkedin_oauth_router = APIRouter(prefix="/linkedin", tags=["linkedin-oauth"])


def _set_linkedin_oauth_state_cookie(response: Response, state_token: str):
    """Sets the LinkedIn OAuth state cookie."""
    response.set_cookie(
        key="linkedin_oauth_state",
        value=state_token,
        max_age=LinkedInStateManager.OAUTH_SESSION_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE
    )

def _clear_linkedin_oauth_state_cookie(response: Response):
    """Clears the LinkedIn OAuth state cookie."""
    response.set_cookie(
        key="linkedin_oauth_state",
        value="",
        max_age=0,
        expires=0,
        path="/",
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE
    )


def _get_base_url(request: Request, dev_env_suffix: str = ""):
    """Get base URL for redirects"""
    URL = f"{str(request.base_url).rstrip('/')}{settings.API_V1_PREFIX}{dev_env_suffix}"
    return URL


# OAuth Flow Endpoints
@linkedin_oauth_router.get("/auth/initiate", response_model=schemas.LinkedInInitiateResponse)
async def initiate_linkedin_oauth(
    request: Request,
    response: Response,
    csrf_cookie: Optional[str] = Cookie(None, alias=settings.CSRF_TOKEN_COOKIE_NAME),
    csrf_header: Optional[str] = Header(None, alias=settings.CSRF_TOKEN_HEADER_NAME),
    current_user: Optional[User] = Depends(OptionalCurrentUserChecker(check_active=True, check_verified=False)),
    service: services.LinkedinOauthService = Depends(dependencies.get_linkedin_oauth_service)
):
    """
    Initiate LinkedIn OAuth flow.
    
    This endpoint generates the LinkedIn authorization URL with a dynamic
    redirect URI and a predefined set of scopes. For non-logged-in users,
    it also sets a CSRF cookie for protection during the OAuth flow.
    """
    user_id = str(current_user.id) if current_user else None
    
    # For non-logged-in users, set a CSRF cookie for the OAuth flow
    if not current_user:
        csrf_cookie = generate_csrf_token()
        set_csrf_cookie(response, csrf_cookie, settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)  # 30 minutes for OAuth flow
    else:
        if not validate_csrf_token(csrf_cookie, csrf_header):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed. Ensure X-XSRF-TOKEN header matches XSRF-TOKEN cookie."
            )
    
    redirect_uri = settings.LINKEDIN_OAUTH_CALLBACK_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else _get_base_url(request, settings.LINKEDIN_AUTH_CALLBACK_URL)  # _get_base_url(request, settings.LINKEDIN_AUTH_CALLBACK_URL)
    
    initiate_response = await service.initiate_oauth_flow(
        user_id=user_id,
        redirect_uri=redirect_uri,
        csrf_token=csrf_cookie,
    )
    
    return initiate_response


@linkedin_oauth_router.get("/auth/callback", response_model=schemas.OauthCallbackResponse)
async def linkedin_oauth_callback(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    code: Optional[str] = Query(None, description="Authorization code from LinkedIn"),
    state: Optional[str] = Query(None, description="State parameter for CSRF protection"),
    error: Optional[str] = Query(None, description="Error from LinkedIn"),
    error_description: Optional[str] = Query(None, description="Error description"),
    csrf_cookie: Optional[str] = Cookie(None, alias=settings.CSRF_TOKEN_COOKIE_NAME),
    # csrf_header: Optional[str] = Header(None, alias=settings.CSRF_TOKEN_HEADER_NAME),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: services.LinkedinOauthService = Depends(dependencies.get_linkedin_oauth_service),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Handle LinkedIn OAuth callback.
    
    This endpoint processes the OAuth callback from LinkedIn. For logged-in users,
    it validates CSRF protection. For non-logged-in users, it sets up CSRF protection
    for subsequent requests.
    
    Args:
        code: Authorization code from LinkedIn
        state: State token for CSRF validation
        error: OAuth error code if authorization failed
        error_description: Detailed error description
        
    Returns:
        OauthCallbackResponse with action details and redirect URL
    """
    # Construct the redirect_uri used in the initial request
    redirect_uri = settings.LINKEDIN_OAUTH_CALLBACK_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else str(request.url_for('linkedin_oauth_callback'))

    # Handle OAuth errors
    if error:
        logger.error(f"LinkedIn OAuth error: {error} - {error_description}")
        redirect_url = f"{settings.LINKEDIN_LOGIN_SPA_URL}?error=linkedin_oauth_failed&message={error}" if settings.APP_ENV in ["PROD", "STAGE"] else f"{_get_base_url(request)}/login?error=linkedin_oauth_failed&message={error}"
        return schemas.OauthCallbackResponse(
            success=False,
            action=schemas.OauthAction.ERROR,
            redirect_url=redirect_url,
            message=f"LinkedIn authentication failed: {error_description or error}",
            error_code="linkedin_oauth_failed"
        )
    
    # Validate required parameters
    if not code:
        redirect_url = f"{settings.LINKEDIN_LOGIN_SPA_URL}?error=missing_code" if settings.APP_ENV in ["PROD", "STAGE"] else f"{_get_base_url(request)}/login?error=missing_code"
        return schemas.OauthCallbackResponse(
            success=False,
            action=schemas.OauthAction.ERROR,
            redirect_url=redirect_url,
            message="Authorization code is missing",
            error_code="missing_code"
        )
    
    try:

        # Process OAuth callback
        result = await service.process_oauth_callback(db, code, redirect_uri, state, csrf_cookie, error, error_description)

        csrf_token = generate_csrf_token()
        # Set CSRF cookie for browser validation
        # Use access token expiration time for consistency
        csrf_cookie_max_age = LinkedInStateManager.OAUTH_SESSION_TOKEN_EXPIRE_MINUTES * 60
        set_csrf_cookie(response, csrf_token, csrf_cookie_max_age)
        
        # For flows that require further action, create and set a state cookie
        if result.requires_action:
            if result.action == schemas.OauthAction.REGISTRATION_REQUIRED:
                # Create state token for registration flow
                state_token = LinkedInStateManager.create_oauth_session_token(
                    linkedin_id=result.user_info['linkedin_id'],
                    email=result.user_info.get('email'),
                    name=result.user_info.get('name'),
                    email_verified=result.user_info.get('email') is not None
                )
                _set_linkedin_oauth_state_cookie(response, state_token)
            elif result.action == schemas.OauthAction.VERIFICATION_REQUIRED:
                # Create state token for verification flow
                state_token = LinkedInStateManager.create_oauth_session_token(
                    linkedin_id=result.user_info['linkedin_id'],
                    email=result.user_info.get('email'),
                    name=result.user_info.get('name'),
                    email_verified=False
                )
                _set_linkedin_oauth_state_cookie(response, state_token)

        if result.success:
            if result.action == schemas.OauthAction.LOGIN_SUCCESS:
                # Direct login - set auth cookies
                access_token, refresh_token = await auth_service.generate_tokens_for_user(
                    db=db,
                    user=result.user,
                    keep_me_logged_in=True
                )
                
                setup_auth_cookies_with_csrf(
                    response=response,
                    access_token=access_token,
                    refresh_token_obj=refresh_token,
                    keep_me_logged_in=True
                )
                
                # Return success response with redirect URL
                redirect_url = settings.LINKEDIN_DASHBOARD_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else f"{_get_base_url(request)}/dashboard"
                return schemas.OauthCallbackResponse(
                    success=True,
                    action=schemas.OauthAction.LOGIN_SUCCESS,
                    redirect_url=redirect_url,
                    message="Successfully logged in with LinkedIn",
                    requires_cookies=True
                )
                
            elif result.action == schemas.OauthAction.ACCOUNT_LINKED:
                # Account linked - set auth cookies if not already logged in
                if not result.user:
                    raise exceptions.LinkedInOauthException("User not found after linking")
                
                access_token, refresh_token = await auth_service.generate_tokens_for_user(
                    db=db,
                    user=result.user,
                    keep_me_logged_in=True
                )
                
                setup_auth_cookies_with_csrf(
                    response=response,
                    access_token=access_token,
                    refresh_token_obj=refresh_token,
                    keep_me_logged_in=True
                )
                
                redirect_url = f"{settings.LINKEDIN_SETTINGS_SPA_URL}?linkedin=connected" if settings.APP_ENV in ["PROD", "STAGE"] else f"{_get_base_url(request)}/settings?linkedin=connected"
                return schemas.OauthCallbackResponse(
                    success=True,
                    action=schemas.OauthAction.ACCOUNT_LINKED,
                    redirect_url=redirect_url,
                    message="LinkedIn account successfully linked",
                    requires_cookies=True
                )
                
            elif result.action == schemas.OauthAction.REGISTRATION_REQUIRED:
                # Return registration required response
                redirect_url = f"{settings.LINKEDIN_REGISTER_SPA_URL}?linkedin=true" if settings.APP_ENV in ["PROD", "STAGE"] else f"{_get_base_url(request)}/register?linkedin=true"
                return schemas.OauthCallbackResponse(
                    success=True,
                    action=schemas.OauthAction.REGISTRATION_REQUIRED,
                    redirect_url=redirect_url,
                    message="Please complete your registration",
                    user_info=result.user_info,
                    requires_cookies=True
                )
                
            elif result.action == schemas.OauthAction.VERIFICATION_REQUIRED:
                # Return verification required response
                base_redirect = f"{settings.LINKEDIN_VERIFY_ACCOUNT_SPA_URL}?linkedin=true" if settings.APP_ENV in ["PROD", "STAGE"] else f"{_get_base_url(request)}/verify-account?linkedin=true"
                redirect_url = base_redirect
                if result.user_info and result.user_info.get("existing_account_email"):
                    redirect_url += f"&email={result.user_info['existing_account_email']}"
                
                return schemas.OauthCallbackResponse(
                    success=True,
                    action=schemas.OauthAction.VERIFICATION_REQUIRED,
                    redirect_url=redirect_url,
                    message="Please verify your account to continue",
                    user_info=result.user_info,
                    requires_cookies=True
                )
                
            elif result.action == schemas.OauthAction.CONFLICT_RESOLUTION:
                # LinkedIn already linked to different account
                base_conflict_url = settings.LINKEDIN_CONFLICT_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else f"{_get_base_url(request)}/linkedin-conflict"
                redirect_url = (
                    f"{base_conflict_url}"
                    f"?email={result.user_info.get('conflict_email', '')}"
                )
                return schemas.OauthCallbackResponse(
                    success=False,
                    action=schemas.OauthAction.CONFLICT_RESOLUTION,
                    redirect_url=redirect_url,
                    message="This LinkedIn account is already linked to another KIWIQ account",
                    error_code="account_conflict",
                    user_info=result.user_info
                )
        else:
            # OAuth processing failed
            redirect_url = f"{settings.LINKEDIN_LOGIN_SPA_URL}?error=oauth_failed" if settings.APP_ENV in ["PROD", "STAGE"] else f"{_get_base_url(request)}/login?error=oauth_failed"
            return schemas.OauthCallbackResponse(
                success=False,
                action=result.action,
                redirect_url=redirect_url,
                message=result.message,
                error_code="oauth_failed",
                user_info=result.user_info,
            )
            
    except exceptions.LinkedInOauthException as e:
        logger.error(f"LinkedIn OAuth exception: {e}")
        redirect_url = f"{settings.LINKEDIN_LOGIN_SPA_URL}?error=oauth_failed&message={e.message}" if settings.APP_ENV in ["PROD", "STAGE"] else f"{_get_base_url(request)}/login?error=oauth_failed&message={e.message}"
        return schemas.OauthCallbackResponse(
            success=False,
            action=schemas.OauthAction.ERROR,
            redirect_url=redirect_url,
            message=f"LinkedIn OAuth error: {e.message}",
            error_code="oauth_exception"
        )
    except Exception as e:
        logger.error(f"Unexpected error in OAuth callback: {e}", exc_info=True)
        redirect_url = f"{settings.LINKEDIN_LOGIN_SPA_URL}?error=internal" if settings.APP_ENV in ["PROD", "STAGE"] else f"{_get_base_url(request)}/login?error=internal"
        return schemas.OauthCallbackResponse(
            success=False,
            action=schemas.OauthAction.ERROR,
            redirect_url=redirect_url,
            message="An unexpected error occurred during authentication",
            error_code="internal_error"
        )


@linkedin_oauth_router.post("/auth/complete-registration")
async def complete_linkedin_registration(
    registration_data: schemas.CompleteLinkedinRegistration,
    response: Response,
    request: Request,
    background_tasks: BackgroundTasks,
    state_data: Dict[str, Any] = Depends(dependencies.get_verified_linkedin_oauth_state),
    csrf_check: None = Depends(validate_csrf_protection),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: services.LinkedinOauthService = Depends(dependencies.get_linkedin_oauth_service),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Complete registration with LinkedIn data.
    
    This endpoint creates a new KIWIQ account using data from LinkedIn OAuth
    and links the LinkedIn account to the new user. It relies on a state
    cookie set during the initial OAuth callback.
    
    Args:
        registration_data: Registration form data
        state_data: Verified state data from the OAuth cookie
        
    Returns:
        JSON response with status "success"
        
    Raises:
        HTTPException: 400 for invalid state or registration errors
    """
    try:
        # Get base URL for email verification
        base_url = settings.VERIFY_EMAIL_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else _get_base_url(request, settings.AUTH_VERIFY_EMAIL_URL)
        
        # Complete registration
        user, oauth_record = await service.complete_registration(
            db, registration_data, state_data, background_tasks, base_url
        )
        
        # Generate auth tokens
        access_token, refresh_token = await auth_service.generate_tokens_for_user(
            db=db,
            user=user,
            keep_me_logged_in=True
        )
        
        # Set auth cookies
        setup_auth_cookies_with_csrf(
            response=response,
            access_token=access_token,
            refresh_token_obj=refresh_token,
            keep_me_logged_in=True
        )
        
        # Clear OAuth state cookie
        _clear_linkedin_oauth_state_cookie(response)
        
        logger.info(f"Completed LinkedIn registration for user {user.id}")
        return {"status": "success"}
        
    except exceptions.LinkedInStateException as e:
        # This can still be raised by the service layer for logic errors
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
    except EmailAlreadyExistsException as e:
        raise
    except exceptions.LinkedInOauthException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error completing LinkedIn registration: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete registration"
        )


@linkedin_oauth_router.post("/auth/link-existing")
async def link_existing_account(
    link_data: schemas.LinkExistingAccount,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    state_data: Dict[str, Any] = Depends(dependencies.get_verified_linkedin_oauth_state),
    csrf_check: None = Depends(validate_csrf_protection),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: services.LinkedinOauthService = Depends(dependencies.get_linkedin_oauth_service),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Link LinkedIn to existing KIWIQ account.
    
    This endpoint links a LinkedIn account to an existing KIWIQ account
    after verifying the user's credentials (password). It relies on a
    state cookie from the OAuth callback.
    
    Args:
        link_data: Account linking request with credentials
        state_data: Verified state data from the OAuth cookie
        
    Returns:
        JSON response with status "success"
        
    Raises:
        HTTPException: 401 for invalid credentials, 409 for conflicts
    """
    try:
        # Link to existing account
        if link_data.password:
            user, oauth_record = await service.link_existing_account(db, link_data, state_data)
        
        
            # Generate auth tokens
            access_token, refresh_token = await auth_service.generate_tokens_for_user(
                db=db,
                user=user,
                keep_me_logged_in=True
            )
            
            # Set auth cookies
            setup_auth_cookies_with_csrf(
                response=response,
                access_token=access_token,
                refresh_token_obj=refresh_token,
                keep_me_logged_in=True
            )
            
            # Clear OAuth state cookie
            _clear_linkedin_oauth_state_cookie(response)
            
            logger.info(f"Linked LinkedIn to existing account {user.id}")
            return {"status": "success"}
        else:
            email = link_data.email
            linkedin_id = state_data.get("linkedin_id")

            if not email or not linkedin_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid state: email or LinkedIn ID missing."
                )

            # Create a CSRF token and set it as a cookie for the verification step
            csrf_token = generate_csrf_token()
            set_csrf_cookie(response, csrf_token, settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)

            base_url = settings.LINKEDIN_VERIFY_LINKING_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else _get_base_url(request, settings.LINKEDIN_AUTH_VERIFY_LINKING_URL)

            success = await service.send_linkedin_verification_email(
                db, background_tasks, base_url, 
                email=email, 
                linkedin_id=str(linkedin_id), 
                csrf_token=csrf_token
            )
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Could not send verification email. The email may not be associated with a KIWIQ account."
                )
            return {"message": "Verification email sent."}
        
    except exceptions.LinkedInAccountConflictException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except CredentialsException as e:
        raise
    except exceptions.LinkedInStateException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
    except exceptions.LinkedInOauthException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error linking existing account: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to link account"
        )


@linkedin_oauth_router.post("/auth/request-verification", status_code=status.HTTP_202_ACCEPTED)
async def request_verification_for_linkedin_unverified_email(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    state_data: Dict[str, Any] = Depends(dependencies.get_verified_linkedin_oauth_state),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: services.LinkedinOauthService = Depends(dependencies.get_linkedin_oauth_service)
):
    """
    Request a verification email to link a LinkedIn account via LinkedIn's email which is unverified.
    
    This endpoint is used during an interactive flow where the user's state
    is managed by a secure cookie.

    Only used when the user's email is unverified.
    """
    base_url = settings.LINKEDIN_VERIFY_LINKING_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else _get_base_url(request, settings.LINKEDIN_AUTH_VERIFY_LINKING_URL)
    
    email = state_data.get("email")
    linkedin_id = state_data.get("linkedin_id")

    if not email or not linkedin_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state: email or LinkedIn ID missing."
        )

    # Create a CSRF token and set it as a cookie for the verification step
    csrf_token = generate_csrf_token()
    set_csrf_cookie(response, csrf_token, settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    success = await service.send_linkedin_verification_email(
        db, background_tasks, base_url, 
        email=email, 
        linkedin_id=str(linkedin_id), 
        csrf_token=csrf_token
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not send verification email. The email may not be associated with a KIWIQ account."
        )
    return {"message": "Verification email sent."}


@linkedin_oauth_router.get("/auth/verify-linking", response_model=schemas.OauthVerificationResponse)
async def verify_linkedin_linking(
    request: Request,
    response: Response,
    token: str = Query(..., description="LinkedIn linking verification token"),
    csrf_cookie: Optional[str] = Cookie(None, alias=settings.CSRF_TOKEN_COOKIE_NAME),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: services.LinkedinOauthService = Depends(dependencies.get_linkedin_oauth_service),
    auth_service: AuthService = Depends(get_auth_service)
):
    """Verify linking token from email and log the user in."""
    try:

        # logger.info(f"Verifying LinkedIn linking token: {token}")
        user, _ = await service.verify_linking_token(db, token, csrf_cookie)
        
        access_token, refresh_token = await auth_service.generate_tokens_for_user(
            db=db, user=user, keep_me_logged_in=True
        )
        
        setup_auth_cookies_with_csrf(
            response=response,
            access_token=access_token,
            refresh_token_obj=refresh_token,
            keep_me_logged_in=True
        )
        
        redirect_url = f"{settings.LINKEDIN_SETTINGS_SPA_URL}?linkedin=connected" if settings.APP_ENV in ["PROD", "STAGE"] else f"{_get_base_url(request)}/settings?linkedin=connected"
        return schemas.OauthVerificationResponse(
            success=True,
            redirect_url=redirect_url,
            message="LinkedIn account successfully linked and verified",
            requires_cookies=True
        )
        
    except (exceptions.LinkedInOauthException, exceptions.LinkedInStateException) as e:
        redirect_url = f"{settings.LINKEDIN_LOGIN_SPA_URL}?error=linkedin_link_failed&message={e.message}" if settings.APP_ENV in ["PROD", "STAGE"] else f"{_get_base_url(request)}/login?error=linkedin_link_failed&message={e.message}"
        return schemas.OauthVerificationResponse(
            success=False,
            redirect_url=redirect_url,
            message=f"LinkedIn linking verification failed: {e.message}",
            error_code="verification_failed"
        )


@linkedin_oauth_router.post("/auth/provide-email", response_model=schemas.ProvideEmailResult)
async def provide_email_for_linkedin(
    request: Request,
    provide_email_data: schemas.ProvideEmail,
    background_tasks: BackgroundTasks,
    response: Response,
    state_data: Dict[str, Any] = Depends(dependencies.get_verified_linkedin_oauth_state),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: services.LinkedinOauthService = Depends(dependencies.get_linkedin_oauth_service)
):
    """Provide email address manually when not available from LinkedIn."""
    base_url = settings.LINKEDIN_VERIFY_LINKING_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else _get_base_url(request, settings.LINKEDIN_AUTH_VERIFY_LINKING_URL)
    
    # Generate a CSRF token for the subsequent email verification step and set it as a cookie
    csrf_token = generate_csrf_token()
    set_csrf_cookie(response, csrf_token, settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    result = await service.handle_provided_email(
        db, background_tasks, base_url, provide_email_data, state_data, csrf_token_for_email=csrf_token
    )
    
    # If the service indicates registration is required, update the state cookie
    if result.action_required == schemas.OauthAction.REGISTRATION_REQUIRED:
        # Create a new state token with the provided email
        new_state_token = LinkedInStateManager.create_oauth_session_token(
            linkedin_id=state_data['linkedin_id'],
            email=provide_email_data.email,
            name=state_data.get('name'),
            email_verified=False
        )
        _set_linkedin_oauth_state_cookie(response, new_state_token)
        
    return result


# Account Management Endpoints
@linkedin_oauth_router.get("/me/connection", response_model=schemas.LinkedinConnectionStatus)
async def get_linkedin_connection(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: services.LinkedinOauthService = Depends(dependencies.get_linkedin_oauth_service)
):
    """
    Get LinkedIn connection status for current user.
    
    Returns:
        LinkedinConnectionStatus with connection details
    """
    connection_status = await service.get_user_linkedin_connection(db, current_user.id)
    
    if not connection_status:
        return schemas.LinkedinConnectionStatus(is_connected=False)
    
    return connection_status


@linkedin_oauth_router.delete("/me/unlink", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_linkedin_account(
    confirmation: schemas.UnlinkLinkedinAccount,
    current_user: User = Depends(dependencies.RequireLinkedinConnection()),
    # csrf_check: None = Depends(validate_csrf_protection),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: services.LinkedinOauthService = Depends(dependencies.get_linkedin_oauth_service)
):
    """
    Unlink LinkedIn account from current user.
    
    Args:
        confirmation: Confirmation request with confirm=true
        
    Returns:
        204 No Content on success
        
    Raises:
        HTTPException: 400 if confirmation not provided
    """
    if not confirmation.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required to unlink LinkedIn account"
        )
    
    success = await service.unlink_linkedin_account(db, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LinkedIn account not found"
        )
    
    logger.info(f"Unlinked LinkedIn account from user {current_user.id}")


@linkedin_oauth_router.post("/me/refresh-token", response_model=schemas.LinkedinConnectionStatus)
async def refresh_linkedin_token(
    current_user: User = Depends(dependencies.RequireLinkedinConnection()),
    # csrf_check: None = Depends(validate_csrf_protection),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: services.LinkedinOauthService = Depends(dependencies.get_linkedin_oauth_service)
):
    """
    Refresh LinkedIn access token.
    
    This endpoint uses the stored refresh token to obtain a new access token
    from LinkedIn. Requires an active LinkedIn connection with a valid refresh token.
    
    Returns:
        Updated LinkedinConnectionStatus
        
    Raises:
        HTTPException: 400 if no refresh token, 401 if refresh fails
    """
    try:
        await service.refresh_access_token(db, current_user.id)
        
        # Return updated connection status
        return await service.get_user_linkedin_connection(db, current_user.id)
        
    except exceptions.LinkedInTokenExpiredException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except exceptions.LinkedInOauthException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error refreshing LinkedIn token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh token"
        ) 
