from typing import List, Any, Optional, AsyncGenerator
import uuid
import logging # Keep standard logging import if needed elsewhere

# from fastapi.responses import Response as FastAPIResponse

from fastapi import APIRouter, Depends, HTTPException, status, Body, Query, Request, Security, BackgroundTasks, Cookie, Response, Path

from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm # Special form for username/password
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_async_session, get_async_db_dependency # Added get_async_db_dependency
# Change relative to absolute imports
from kiwi_app.email import email_verify
from kiwi_app.auth import crud, models, schemas, security, dependencies, utils, services # Added email_verify
from kiwi_app.auth.csrf import setup_auth_cookies_with_csrf, clear_auth_cookies, validate_csrf_protection, set_csrf_cookie, generate_csrf_token # Import CSRF utilities
# from kiwi_app.auth.utils import auth_logger
from kiwi_app.utils import get_kiwi_logger

auth_logger = get_kiwi_logger(name="kiwi_app.auth")

from kiwi_app.auth.constants import Permissions, ALL_PERMISSIONS
from kiwi_app.auth.exceptions import (
    EmailAlreadyExistsException,
    UserNotFoundException,
    CredentialsException,
    InactiveUserException,
    UserNotVerifiedException,
    InvalidTokenException,
    OrganizationNotFoundException,
    RoleNotFoundException,
    PermissionDeniedException,
    OrganizationSeatLimitExceededException,
    CSRFTokenException,
)
from kiwi_app.settings import settings # Import settings for cookie config
# Keep schema imports as they are if direct
from kiwi_app.auth.schemas import (
    UserReadWithOrgs, UserRead, UserCreate, OrganizationRead, OrganizationCreate, RoleRead, RoleCreate, UserAssignRole, RequestEmailVerification,
    # Add new password schemas
    AccessTokenResponse, UserChangePassword, RequestPasswordReset, ResetPassword,
    UserAdminCreate, UserReadWithSuperuserStatus, # Added for admin user creation
    OrganizationBillingEmailUpdate # Added for billing email updates
)

# Create an API Router
# Prefix all routes in this module with /auth
# Add tags for OpenAPI documentation grouping
# NOTE: change settings.AUTH_TOKEN_URL if this URL path changes!
router = APIRouter(
    prefix="/auth",
    # tags=["Authentication & Authorization"],
)

# Get the instantiated service (REMOVED - Use Dependency Injection)
# auth_service = services.auth_service


def _get_base_url(request: Request, dev_env_suffix: str = ""):
    URL = f"{str(request.base_url).rstrip('/')}{settings.API_V1_PREFIX}{dev_env_suffix}"
    return URL

# === Email/Password Authentication Endpoints ===

@router.post("/register", response_model=schemas.UserReadWithOrgs, status_code=status.HTTP_201_CREATED, tags=["auth"])
async def register_user_endpoint(
    *, # Enforce keyword arguments
    db: AsyncSession = Depends(get_async_db_dependency),
    user_in: schemas.UserCreate,
    request: Request, # Need request to get base URL
    background_tasks: BackgroundTasks, # Inject BackgroundTasks
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Register a new user. Creates a default organization and sends verification email
    using background tasks.
    """
    # Get base URL for verification link
    base_url = settings.VERIFY_EMAIL_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else _get_base_url(request, settings.AUTH_VERIFY_EMAIL_URL)
    try:
        # Service method now handles adding email task to background
        user = await auth_service.register_new_user(
            db=db,
            user_in=user_in, # Pass data as dict
            background_tasks=background_tasks, # Pass background tasks
            base_url=base_url,
            registered_by_admin=False # Explicitly false for regular registration
        )
        auth_logger.info(f"User successfully registered: {user.email}")
        return user
    except EmailAlreadyExistsException as e:
        raise e # Re-raise specific exception
    except RoleNotFoundException as e:
        # Critical setup issue if default role is missing
        raise HTTPException(status_code=500, detail=f"Server setup error: {e.detail}")
    except Exception as e:
        auth_logger.exception(f"Unexpected error during registration for email: {user_in.email}", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred during registration.")

# NOTE: change settings.AUTH_TOKEN_URL if this URL path changes!
# "/login/token
@router.post("/login", response_model=schemas.AccessTokenResponse, tags=["auth"]) # Response model now implicitly just the access token
async def login_for_access_token_endpoint(
    response: Response, # Inject Response object to set cookie
    db: AsyncSession = Depends(get_async_db_dependency),
    keep_me_logged_in: bool = Query(True, description="If True, will keep user logged in for 30 days"),
    refresh_token_from_cookie: Optional[str] = Cookie(None, alias=settings.REFRESH_COOKIE_NAME),
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
) -> schemas.AccessTokenResponse: # Use a specific response schema for clarity
    """
    Authenticate user with CSRF protection, return status and set secure cookies.
    
    This endpoint:
    1. Authenticates the user with email/password
    2. Generates JWT access and refresh tokens
    3. Sets secure HttpOnly cookies for tokens
    4. Sets CSRF token cookie (readable by JavaScript)
    5. Returns success status
    
    The CSRF token cookie enables the frontend to include the token in request headers
    for CSRF protection on subsequent authenticated requests.
    
    Returns:
        AccessTokenResponse with status="success"
        
    Cookies Set:
        - access_token: HttpOnly, secure JWT access token
        - refresh_token: HttpOnly, secure JWT refresh token (if keep_me_logged_in=True)
        - XSRF-TOKEN: Secure CSRF token (readable by JavaScript)
        
    Security Features:
        - CSRF protection via double-submit cookie pattern
        - HttpOnly cookies prevent XSS attacks on tokens
        - Secure flag ensures HTTPS-only transmission in production
        - SameSite=Lax prevents CSRF while allowing legitimate navigation
    """
    try:
        user = await auth_service.authenticate_user(db=db, email=form_data.username, password=form_data.password)
        
        try:
            if refresh_token_from_cookie:
                # If refresh token is provided and keep_me_logged_in is False, invalidate the refresh token
                await auth_service.invalidate_refresh_token(db=db, token_uuid=uuid.UUID(refresh_token_from_cookie))
        except Exception as e:
            auth_logger.exception(f"Error invalidating refresh token during login for user: {user.email}", exc_info=e)

        # Generate both tokens
        access_token_str, refresh_token_obj = await auth_service.generate_tokens_for_user(db=db, user=user, keep_me_logged_in=keep_me_logged_in)
        auth_logger.info(f"User successfully authenticated: {user.email}")

        # Set up all authentication cookies with CSRF protection
        csrf_token = setup_auth_cookies_with_csrf(
            response=response,
            access_token=access_token_str,
            refresh_token_obj=refresh_token_obj,
            keep_me_logged_in=keep_me_logged_in
        )

        auth_logger.info(f"Authentication cookies set with CSRF protection for user: {user.email}")

        # Return success status (CSRF token is available in cookie for frontend)
        return {"status": "success"}

    except (CredentialsException, InactiveUserException, UserNotVerifiedException) as e:
        # Clear any potentially set cookies on authentication failure
        clear_auth_cookies(response)
        raise e # Re-raise authentication specific exceptions
    except Exception as e:
        # Clear any potentially set cookies on unexpected error
        clear_auth_cookies(response)
        auth_logger.exception(f"Unexpected error during login for user: {form_data.username}", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred during login.")

@router.post("/request-magic-login", status_code=status.HTTP_202_ACCEPTED, tags=["auth"])
async def request_magic_login_email(
    response: Response,  # Inject Response to set CSRF cookie
    request_data: schemas.RequestEmailVerification,  # Reuse this schema as it only contains email
    request: Request,  # Need request for base_url
    background_tasks: BackgroundTasks,
    keep_me_logged_in: bool = Query(True, description="If True, will keep user logged in for 30 days after magic login"),
    db: AsyncSession = Depends(get_async_db_dependency),
    user_dao: crud.UserDAO = Depends(dependencies.get_user_dao)
):
    """
    Request a magic login link to be sent via email (Requires Cookies enabled for CSRF token checks).
    
    This endpoint:
    1. Validates the user exists and can receive magic login links
    2. Generates a magic link token with CSRF protection
    3. Sets the CSRF token cookie for browser validation
    4. Sends the magic login email via background tasks
    5. Returns success response without revealing if user exists
    
    The magic link must be used in the same browser where it was requested
    due to CSRF token validation requirements.
    
    Args:
        request_data: Contains the email address to send magic link to
        keep_me_logged_in: Whether to keep user logged in for extended period
        
    Returns:
        202 Accepted with generic message (prevents email enumeration)
        
    Cookies Set:
        - XSRF-TOKEN: CSRF token that must match the token in the magic link
        
    Security Features:
        - Generic response prevents email enumeration attacks
        - CSRF token prevents magic link use across different browsers
        - Token expiration provides time-bound security
        - Comprehensive error logging for security monitoring
    """
    
    response = JSONResponse(
        content={"message": "If an account with this email exists, a magic login link will be sent."}, 
        status_code=status.HTTP_202_ACCEPTED
    )

    csrf_token = generate_csrf_token()
    # Set CSRF cookie for browser validation
    # Use access token expiration time for consistency
    csrf_cookie_max_age = settings.MAGIC_LINK_TOKEN_EXPIRE_MINUTES * 60

    set_csrf_cookie(response, csrf_token, csrf_cookie_max_age)

    try:
        # Find user by email
        user = await user_dao.get_by_email(db, email=request_data.email)
        if not user:
            # Don't reveal if email exists - return generic success message
            auth_logger.info(f"Magic login requested for non-existent email: {request_data.email}")
            raise UserNotFoundException()
        
        # Check if user is active (can be unverified but must be active)
        if not user.is_active:
            auth_logger.warning(f"Magic login requested for inactive user: {user.email}")
            # Still return generic message to prevent enumeration
            raise InactiveUserException()
        # check if user is verified
        if not user.is_verified:
            auth_logger.warning(f"Magic login requested for unverified user: {user.email}")
            raise UserNotVerifiedException()
        
        # Generate magic link token with CSRF protection
        magic_token, csrf_token = security.create_magic_link_token(
            subject=user.id,
            csrf_token=csrf_token,
            keep_me_logged_in=keep_me_logged_in
        )

        # Construct base URL pointing to the magic login verification endpoint
        base_url = settings.MAGIC_LOGIN_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else _get_base_url(request, settings.MAGIC_LOGIN_URL)
        
        # Send magic login email via background tasks
        await email_verify.trigger_send_magic_login_email(
            background_tasks=background_tasks,
            user=user,
            base_url=base_url,
            magic_token=magic_token,
        )
        
        auth_logger.info(f"Magic login email requested and queued for user: {user.email}")
        
        # Return generic success message
        return response
        
    except Exception as e:
        # Log the error but still return generic success to prevent enumeration
        auth_logger.exception(f"Error requesting magic login for {request_data.email}", exc_info=e)
        
        return response

# --- NEW: Refresh Token Endpoint --- #
# NOTE: change `kiwi_app.settings.AUTH_REFRESH_URL` if changing this path!
@router.post("/refresh", response_model=schemas.AccessTokenResponse, tags=["auth"])
async def refresh_token_endpoint(
    response: Response, # Inject Response to set new cookie
    # user: models.User = Depends(dependencies.get_current_active_user),  # This won't work since access token is probably expired!
    # csrf_validation: None = Depends(validate_csrf_protection),
    refresh_token_from_cookie: Optional[str] = Cookie(None, alias=settings.REFRESH_COOKIE_NAME), # Get from cookie
    db: AsyncSession = Depends(get_async_db_dependency),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
) -> schemas.AccessTokenResponse:
    """
    Get new access and CSRF tokens using the refresh token stored in HttpOnly cookie.
    
    This endpoint:
    1. Validates the refresh token from the cookie
    2. Implements refresh token rotation (old token revoked, new token issued)
    3. Generates new access token
    4. Sets new secure cookies with CSRF protection
    5. Returns success status
    
    The new CSRF token enables continued protection for subsequent authenticated requests.
    
    Returns:
        AccessTokenResponse with status="success"
        
    Cookies Set:
        - access_token: New HttpOnly, secure JWT access token
        - refresh_token: New HttpOnly, secure JWT refresh token
        - XSRF-TOKEN: New secure CSRF token (readable by JavaScript)
        
    Security Features:
        - Refresh token rotation prevents token replay attacks
        - New CSRF token issued with each refresh
        - All cookies cleared on any validation failure
        - Comprehensive error logging for security monitoring
    """
    if not refresh_token_from_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token cookie")

    try:
        # Convert cookie string to UUID
        try:
            old_token_uuid = uuid.UUID(refresh_token_from_cookie)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token format")

        # Service handles validation, rotation, and generation
        new_access_token_str, new_refresh_token_obj = await auth_service.rotate_refresh_token(
            db=db, old_token_uuid=old_token_uuid
        )

        # Set up all authentication cookies with new CSRF protection
        csrf_token = setup_auth_cookies_with_csrf(
            response=response,
            access_token=new_access_token_str,
            refresh_token_obj=new_refresh_token_obj,
            keep_me_logged_in=True  # Refresh implies user wants to stay logged in
        )

        auth_logger.info("Token refresh successful with new CSRF protection")

        # Return success status (new CSRF token is available in cookie for frontend)
        return {"status": "success"}

    except CredentialsException as e:
        # If refresh fails (invalid, expired, revoked), clear all cookies
        clear_auth_cookies(response)
        auth_logger.warning(f"Refresh token validation failed: {e.detail}")
        # Return an error response with the modified response object to include cookie headers
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": e.detail or "Invalid refresh token"},
            headers=response.headers
        )
    except Exception as e:
        # Log unexpected errors
        auth_logger.exception(f"Unexpected error during token refresh", exc_info=e)
        # Clear potentially compromised/invalid cookies on error
        clear_auth_cookies(response)
        # Return an error response with the modified response object to include cookie headers
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal error occurred during token refresh."},
            headers=response.headers
        )

# --- Logout Endpoint --- #
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["auth"])
async def logout_endpoint(
    response: Response,  # Inject Response to clear cookie
    refresh_token_from_cookie: Optional[str] = Cookie(None, alias=settings.REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_async_db_dependency),
    current_user: models.User = Depends(dependencies.get_current_user),  # Verify user is authenticated
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Logout the current user by invalidating their refresh token and clearing the cookie.
    
    This endpoint:
    1. Invalidates the current refresh token in the database (if it exists)
    2. Clears the refresh token cookie from the client
    
    Returns:
        204 No Content on successful logout
    """
    try:
        # If there's a refresh token in the cookie, try to invalidate it
        if refresh_token_from_cookie:
            try:
                token_uuid = uuid.UUID(refresh_token_from_cookie)
                # Invalidate the token in the database (service handles this)
                await auth_service.invalidate_refresh_token(db=db, token_uuid=token_uuid)
                auth_logger.info(f"Refresh token invalidated during logout for user: {current_user.email}")
            except ValueError:
                # Invalid UUID format in cookie - just log and continue with logout
                auth_logger.warning(f"Invalid refresh token format in cookie during logout: {current_user.email}")
            except Exception as e:
                # Log but continue with logout process even if token invalidation fails
                auth_logger.exception(f"Error invalidating refresh token during logout: {current_user.email}", exc_info=e)
        
        # Always clear all cookies, even if token invalidation had an issue
        clear_auth_cookies(response)
        
        auth_logger.info(f"User successfully logged out: {current_user.email}")
        # Don't return a new Response object - let FastAPI use the modified response
        response.status_code = status.HTTP_204_NO_CONTENT
        return response
        
    except Exception as e:
        # Log unexpected errors
        auth_logger.exception(f"Unexpected error during logout for user: {current_user.email}", exc_info=e)
        # Still try to clear all cookies on error
        clear_auth_cookies(response)
        # Don't return a new Response object - let FastAPI use the modified response
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

# --- Optional: Email Verification Endpoints ---
@router.post("/request-verify-email", status_code=status.HTTP_202_ACCEPTED, tags=["auth"])
async def request_email_verification_endpoint(
    request_data: schemas.RequestEmailVerification,
    request: Request,
    background_tasks: BackgroundTasks, # Inject BackgroundTasks
    db: AsyncSession = Depends(get_async_db_dependency),
    user_dao: crud.UserDAO = Depends(dependencies.get_user_dao)
):
    """
    Request a new email verification link.
    Adds the email sending task to the background.
    """
    try:
        user = await user_dao.get_by_email(db, email=request_data.email)
        if not user:
            # Don't reveal if email exists
            return JSONResponse(content={"message": "If an account with this email exists, a verification link will be sent."}, status_code=status.HTTP_202_ACCEPTED)
        if user.is_verified:
            return JSONResponse(content={"message": "Email is already verified."}, status_code=status.HTTP_200_OK)

        base_url = settings.VERIFY_EMAIL_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else _get_base_url(request, settings.AUTH_VERIFY_EMAIL_URL)
        # Use the trigger function which adds to background tasks
        await email_verify.trigger_send_verification_email(background_tasks=background_tasks, db=db, user=user, base_url=base_url)
        # Message returned is generic, log action
        auth_logger.info(f"Email verification requested for: {request_data.email}")
        return JSONResponse(content={"message": "If an account with this email exists and is not verified, a new verification link will be sent."}, status_code=status.HTTP_202_ACCEPTED)
    except Exception as e:
        auth_logger.exception(f"Error requesting email verification for: {request_data.email}", exc_info=e)
        # Return generic success to avoid leaking info, but log error
        return JSONResponse(content={"message": "If an account with this email exists, a verification link will be sent."}, status_code=status.HTTP_202_ACCEPTED)

@router.get("/verify-email", status_code=status.HTTP_200_OK, tags=["auth"])
async def verify_email_endpoint(
    background_tasks: BackgroundTasks, # Add background tasks for first steps email
    token: str = Query(...),
    db: AsyncSession = Depends(get_async_db_dependency),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service) # Inject service
):
    """
    Verify user's email address using the provided token.
    After successful verification, sends a first steps guide email.
    """
    try:
        user = await auth_service.verify_user_email(db=db, token=token)
        auth_logger.info(f"Email successfully verified for user: {user.email}")
        
        # Send first steps guide email after successful verification
        await auth_service.send_first_steps_guide_email(
            background_tasks=background_tasks,
            user=user,
        )
        
        # Optional: Redirect to a frontend page on success?
        # return RedirectResponse(url="/login?verified=true")
        return {"message": "Email successfully verified."}
    except InvalidTokenException as e:
        raise e # Re-raise
    except Exception as e:
        auth_logger.exception(f"Unexpected error during email verification with token: {token[:8]}...", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred during email verification.")

@router.get("/magic-login", status_code=status.HTTP_200_OK, tags=["auth"])
async def magic_login_endpoint(
    response: Response,
    token: str = Query(..., description="The magic link token from the email"),
    csrf_cookie: Optional[str] = Cookie(None, alias=settings.CSRF_TOKEN_COOKIE_NAME),
    db: AsyncSession = Depends(get_async_db_dependency),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service),
):
    """
    Logs a user in using a magic link token.

    This endpoint verifies the magic link token, and if valid, logs the user in
    by generating new access and refresh tokens and setting them in secure cookies.
    """
    try:
        
        # The dependency has already decoded the token and extracted the CSRF token.
        # Now we decode it again to get the user ID.
        if not csrf_cookie:
            raise CSRFTokenException()
        
        user, token_data = await dependencies.get_current_user_from_token_non_dependency(db=db, token=token, expected_token_type="magic_link", csrf_validation_token=csrf_cookie)

        access_token_str, refresh_token_obj = await auth_service.generate_tokens_for_user(db=db, user=user)

        setup_auth_cookies_with_csrf(
            response=response,
            access_token=access_token_str,
            refresh_token_obj=refresh_token_obj,
            keep_me_logged_in=token_data.additional_claims.get("keep_me_logged_in", True),
        )

        auth_logger.info(f"User {user.email} successfully logged in via magic link.")
        return {"status": "success"}
    except (CredentialsException, UserNotFoundException, InactiveUserException, UserNotVerifiedException) as e:
        # clear_auth_cookies(response)
        raise e
    except CSRFTokenException as e:
        raise CSRFTokenException(detail="CSRF token mismatch, magic link must be used in the same browser it was requested from.")
    except Exception as e:
        # clear_auth_cookies(response)
        auth_logger.exception(f"Unexpected error during magic link login", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred during magic link login.")

# --- Password Management Endpoints ---

@router.post("/users/me/change-password", status_code=status.HTTP_204_NO_CONTENT, tags=["auth"])
async def change_password_endpoint(
    password_data: schemas.UserChangePassword,
    db: AsyncSession = Depends(get_async_db_dependency),
    # Requires an active, logged-in user
    current_user: models.User = Depends(dependencies.get_current_active_user),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Allows an authenticated user to change their own password.
    Requires the user's current password for verification.
    """
    try:
        success = await auth_service.change_password(
            db=db,
            user=current_user,
            current_password=password_data.current_password,
            new_password=password_data.new_password
        )
        if success:
            # Consider what to return. 204 No Content is typical for successful updates
            # with no body. We might also force a re-login by not returning new tokens.
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        else:
            # Should not happen if change_password raises exceptions correctly
            raise HTTPException(status_code=500, detail="Password change failed unexpectedly.")
    except CredentialsException as e:
        # Specifically catch incorrect current password
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)
    except Exception as e:
        auth_logger.exception(f"Error changing password for user {current_user.email}", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred while changing password.")

@router.post("/request-password-reset", status_code=status.HTTP_202_ACCEPTED, tags=["auth"])
async def request_password_reset_endpoint(
    request_data: schemas.RequestPasswordReset,
    request: Request, # Need request for base_url
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db_dependency),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Initiates the password reset process by sending an email with a reset link.
    Always returns a 202 Accepted response to prevent email enumeration.
    """
    # Return the generic message from the service
    response = JSONResponse(content={"message": "If an account with this email exists, a password reset link will be sent."}, status_code=status.HTTP_202_ACCEPTED)
    
    try:
        base_url = settings.VERIFY_PASSWORD_RESET_TOKEN_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else _get_base_url(request, settings.AUTH_VERIFY_PASSWORD_RESET_TOKEN_URL)  # API base URL 
        result = await auth_service.request_password_reset(
            db=db,
            email=request_data.email,
            background_tasks=background_tasks,
            base_url=base_url,
            # csrf_token=csrf_token,
        )

        return response
    except Exception as e:
        # Log the error but still return 202
        auth_logger.exception(f"Error requesting password reset for {request_data.email}", exc_info=e)
        return response

@router.get("/verify-password-reset-token", status_code=status.HTTP_200_OK, tags=["auth"])
async def verify_password_reset_token_endpoint(
    token: str = Query(...),
    # No DB session or service needed here, just token validation
):
    """
    Verifies if a password reset token is valid (not expired, correct type).
    Useful for frontend to check token validity before showing reset form.
    Does NOT actually reset the password.
    """
    try:
        # Use the verification function directly
        await email_verify.verify_password_reset_token(token)
        # If verify doesn't raise an exception, the token is valid
        return {"message": "Password reset token is valid.", "allow_password_reset": True}
    except CredentialsException as e:
        # Token is invalid (expired, wrong type, bad signature)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)
    except Exception as e:
        auth_logger.exception(f"Unexpected error verifying password reset token: {token[:8]}...", exc_info=e)
        raise HTTPException(status_code=500, detail="Error verifying password reset token.")

@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT, tags=["auth"])
async def reset_password_endpoint(
    reset_data: schemas.ResetPassword,
    db: AsyncSession = Depends(get_async_db_dependency),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Resets the user's password using the token provided (typically from the email link).
    """
    try:
        success = await auth_service.reset_password_with_token(
            db=db,
            token=reset_data.token,
            new_password=reset_data.new_password
        )
        if success:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        else:
            # Should not happen if service raises exceptions
            raise HTTPException(status_code=500, detail="Password reset failed unexpectedly.")
    except CredentialsException as e:
        # Invalid/expired token
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)
    except UserNotFoundException as e:
        # Should be rare if token was valid, but handle defensively
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except Exception as e:
        auth_logger.exception(f"Error resetting password with token: {reset_data.token[:8]}...", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred during password reset.")

# --- Email Change Management Endpoints ---

@router.post("/users/me/request-email-change", status_code=status.HTTP_202_ACCEPTED, tags=["auth"])
async def request_email_change_endpoint(
    email_change_request: schemas.RequestEmailChange,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db_dependency),
    current_user: models.User = Depends(dependencies.get_current_active_user),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Request an email address change for the current authenticated user.
    
    This endpoint:
    1. Validates the current password for security
    2. Checks that the new email is not already in use
    3. Generates a secure verification token
    4. Sends verification email to the NEW email address
    5. Returns success response (generic to prevent enumeration)
    
    The email change is not completed until the verification token is confirmed.
    
    Args:
        email_change_request: Contains new email and current password
        
    Returns:
        202 Accepted with generic message
        
    Security Features:
        - Current password verification required
        - Verification sent only to new email address
        - Generic response prevents email enumeration
        - Token contains both old and new email for validation
        - Comprehensive error logging for security monitoring
    """
    try:
        # Get base URL for verification link
        base_url = settings.VERIFY_EMAIL_CHANGE_SPA_URL if settings.APP_ENV in ["PROD", "STAGE"] else _get_base_url(request, settings.AUTH_VERIFY_EMAIL_CHANGE_URL)
        # auth_logger.info(f"Base URL {settings.APP_ENV} for email change: {base_url}")
        
        # Service handles all validation and email sending
        result = await auth_service.request_email_change(
            db=db,
            user=current_user,
            new_email=email_change_request.new_email,
            current_password=email_change_request.current_password,
            background_tasks=background_tasks,
            base_url=base_url
        )
        
        auth_logger.info(f"Email change requested by user {current_user.email} to {email_change_request.new_email}")
        return JSONResponse(content=result, status_code=status.HTTP_202_ACCEPTED)
        
    except CredentialsException as e:
        # Current password incorrect
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)
    except EmailAlreadyExistsException as e:
        # New email already in use
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.detail)
    except Exception as e:
        auth_logger.exception(f"Error requesting email change for {current_user.email}", exc_info=e)
        # Return generic success to prevent information leakage
        return JSONResponse(
            content={"message": "If the new email address is valid and available, a verification link will be sent to it."},
            status_code=status.HTTP_202_ACCEPTED
        )

@router.post("/verify-email-change", response_model=schemas.EmailChangeResponse, tags=["auth"])
async def confirm_email_change_endpoint(
    confirmation_data: schemas.ConfirmEmailChange,
    response: Response,
    db: AsyncSession = Depends(get_async_db_dependency),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Confirm and complete an email address change using a verification token.
    
    This endpoint:
    1. Validates the email change token from the new email
    2. Extracts and validates old/new email information
    3. Verifies the user still exists and matches the old email
    4. Checks that the new email is still available
    5. Updates the user's email address in the database
    6. Revokes all refresh tokens for security (forces re-login)
    7. Returns success response with new email
    
    Args:
        confirmation_data: Contains the verification token from new email
        
    Returns:
        EmailChangeResponse: Success message and new email address
        
    Security Features:
        - Token validation with signature and expiry checks
        - Old/new email validation against current state
        - Availability check to prevent race conditions
        - All refresh tokens revoked (forces re-login)
        - Comprehensive error logging for security monitoring
        
    Note:
        After successful email change, the user must log in again with their new email.
    """
    try:
        # Service handles all token validation and email updating
        result = await auth_service.confirm_email_change(
            db=db,
            token=confirmation_data.token
        )
        
        # Clear all authentication cookies since refresh tokens are revoked
        clear_auth_cookies(response)
        
        auth_logger.info(f"Email change confirmed successfully: token ending in ...{confirmation_data.token[-8:]}")
        return result
        
    except CredentialsException as e:
        # Invalid/expired token or validation failure
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)
    except UserNotFoundException as e:
        # User no longer exists
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except EmailAlreadyExistsException as e:
        # New email now taken by another user
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.detail)
    except Exception as e:
        auth_logger.exception(f"Error confirming email change with token: {confirmation_data.token[:8]}...", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred during email change confirmation.")

# === User Management Endpoints ===

@router.get("/users/me", response_model=schemas.UserReadWithSuperuserStatus, tags=["users"])
async def read_users_me_endpoint(
    # Depends on get_current_user which loads necessary relationships
    current_user: models.User = Depends(dependencies.get_current_active_user)
):
    """Get the details of the currently authenticated user."""
    return current_user

@router.patch("/users/me", response_model=schemas.UserRead, tags=["users"])
async def update_users_me_endpoint(
    user_in: schemas.UserUpdate,
    db: AsyncSession = Depends(get_async_db_dependency),
    current_user: models.User = Depends(dependencies.get_current_active_user),
    user_dao: crud.UserDAO = Depends(dependencies.get_user_dao) # Inject DAO for direct update
):
    """Update the current user's profile (e.g., full_name)."""
    # Use the UserAdminUpdate schema for DAO compatibility, but only pass allowed fields
    update_data = schemas.UserAdminUpdate(**user_in.model_dump(exclude_unset=True))
    # Add specific logic here if certain fields need extra validation/handling
    updated_user = await user_dao.update(db=db, db_obj=current_user, obj_in=update_data)
    return updated_user

@router.get("/users/me/organizations", response_model=schemas.UserReadWithOrgs, tags=["users"])
async def list_my_organizations(
    current_user_with_orgs: models.User = Depends(dependencies.get_current_active_user_with_orgs),
    # No specific permission needed to list own memberships
    db: AsyncSession = Depends(get_async_db_dependency), # Need DB session to reload
    user_dao: crud.UserDAO = Depends(dependencies.get_user_dao) # Inject DAO for direct update
):
    """
    List all organizations the current user is a member of, including their role.
    Requires the user's relationships to be loaded.
    """
    # # The get_current_user dependency might not load relationships by default anymore
    # # We need to ensure they are loaded here for the response model.
    # # Option 1: Reload the user with relationships
    # user_with_orgs = await user_dao.get(db, id=current_user.id, load_relations=["organization_links", "organization_links.organization", "organization_links.role"])
    # if not user_with_orgs:
    #     raise HTTPException(status_code=404, detail="User not found") # Should not happen

    # # Need to iterate to load nested relations if not handled by DAO get
    # # This can be inefficient (N+1 problem if not handled carefully by SQLModel/SQLAlchemy relationship loading)
    # links_to_return = []
    # if user_with_orgs.organization_links:
    #     for link in user_with_orgs.organization_links:
    #         # Ensure nested organization and role->permissions are loaded
    #         await db.refresh(link, relationship_names=["organization", "role"])
    #         if link.role:
    #             await db.refresh(link.role, relationship_names=["permissions"])
    #         links_to_return.append(link)

    # print(current_user_with_orgs.organization_links)
    # import ipdb; ipdb.set_trace()

    return current_user_with_orgs


# === Organization & Role Management Endpoints ===

@router.post("/organizations", response_model=schemas.OrganizationRead, status_code=status.HTTP_201_CREATED, tags=["organizations"])
async def create_organization_endpoint(
    org_in: schemas.OrganizationCreate,
    # Change variable name and type hint to reflect the injected session directly
    db: AsyncSession = Depends(get_async_db_dependency),
    current_user: models.User = Depends(dependencies.get_current_active_verified_user),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service) # Inject service
):
    """
    Create a new organization. The creator is automatically assigned as admin.
    """
    try:
        # Remove the 'async with' block, use 'db' directly.
        # The commit/rollback is handled by the get_async_db_dependency dependency's finally block.
        organization = await auth_service.create_organization(db=db, org_in=org_in, creator=current_user)
        auth_logger.info(f"Organization '{organization.name}' created by user '{current_user.email}'")
        return organization
    except HTTPException as e:
         raise e # Re-raise validation errors (e.g., name exists)
    except RoleNotFoundException as e:
         raise HTTPException(status_code=500, detail=f"Server setup error: {e.detail}")
    except Exception as e:
        auth_logger.exception(f"Unexpected error creating organization '{org_in.name}' by user '{current_user.email}'", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred.")

@router.get("/organizations/{org_id}/users", response_model=List[schemas.UserOrganizationRoleReadWithUser], tags=["organizations"])
async def get_organization_users_endpoint(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db_dependency),
    # Check permission using the SpecificOrgPermissionChecker for the org_id in path
    current_user: models.User = Depends(dependencies.SpecificOrgPermissionChecker([Permissions.ORG_VIEW_MEMBERS])),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Get all users in a specific organization with their roles.
    
    Requires the current user to have 'org:view_members' permission in that specific organization.
    The org_id is taken from the URL path.
    
    Returns:
        List[UserOrganizationRoleReadWithUser]: List of users with their roles in the organization
    """
    try:
        users = await auth_service.get_organization_users(db=db, org_id=org_id)
        return users
    except OrganizationNotFoundException as e:
        raise e  # Re-raise specific known errors
    except PermissionDeniedException as e:
        raise e  # Re-raise permission errors
    except Exception as e:
        auth_logger.exception(f"Error retrieving users for org {org_id} by user {current_user.email}", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred.")

@router.delete("/organizations/{org_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["organizations"])
async def delete_organization_endpoint(
    org_id: uuid.UUID = Path(..., description="The ID of the organization to delete"),
    db: AsyncSession = Depends(get_async_db_dependency),
    active_org_id: uuid.UUID = Depends(dependencies.get_active_org_id),
    # Only superusers can delete organizations
    current_user: models.User = Depends(dependencies.SpecificOrgPermissionChecker([Permissions.ORG_DELETE])),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Delete an organization and all its associated data.
    
    This is a destructive operation that can only be performed by superusers.
    It removes the organization, all user-organization links, and potentially
    other associated data depending on the implementation in the service layer.
    
    Args:
        org_id: UUID of the organization to delete
        
    Returns:
        204 No Content on successful deletion
        
    Raises:
        HTTPException: 
            - 404 if organization not found
            - 403 if user lacks permission (handled by dependency)
            - 500 for unexpected errors
    """
    if active_org_id == org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete the active organization.")
    if active_org_id is None and (not current_user.is_superuser):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active organization not set and user is not a superuser.")
    try:
        await auth_service.delete_organization(db=db, org_id=org_id, current_user=current_user)
        auth_logger.info(f"Organization {org_id} deleted by superuser '{current_user.email}'")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except OrganizationNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except Exception as e:
        auth_logger.exception(f"Error deleting organization {org_id} by superuser {current_user.email}", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred while deleting the organization.")



@router.post("/organizations/{org_id}/users", response_model=schemas.UserOrganizationRoleReadWithUser, status_code=status.HTTP_201_CREATED, tags=["organizations"])
async def add_user_to_organization_endpoint(
    org_id: uuid.UUID,
    assignment: schemas.UserAssignRole,
    db: AsyncSession = Depends(get_async_db_dependency),
    # Check permission using the SpecificOrgPermissionChecker for the org_id in path
    current_user: models.User = Depends(dependencies.SpecificOrgPermissionChecker([Permissions.ORG_MANAGE_MEMBERS])),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Assign a role to a user within a specific organization. The user is specified by email and must have signed up with KiwiQ already (doesn't need to be verified or active user).
    Requires the current user to have 'org:manage_members' permission *in that specific org*.
    The org_id is taken from the URL path.
    """
    # if org_id != assignment.organization_id:
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization ID in path and body mismatch.")
    try:
        link = await auth_service.assign_role_to_user_in_org(db=db, org_id=org_id, assignment=assignment, current_user=current_user)
        return link
    except (UserNotFoundException, OrganizationNotFoundException, RoleNotFoundException, PermissionDeniedException, OrganizationSeatLimitExceededException) as e:
        raise e # Re-raise specific known errors
    except Exception as e:
        auth_logger.exception(f"Error assigning role in org {org_id} by user {current_user.email}", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred.")

@router.delete("/organizations/{org_id}/users", status_code=status.HTTP_204_NO_CONTENT, tags=["organizations"])
async def remove_user_from_organization_endpoint(
    org_id: uuid.UUID,
    removal: schemas.UserRemoveRole,
    db: AsyncSession = Depends(get_async_db_dependency),
    # Require org-specific permission to remove users, checked against org_id in path
    current_user: models.User = Depends(dependencies.SpecificOrgPermissionChecker([Permissions.ORG_MANAGE_MEMBERS])),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Remove a user from an organization.
    Requires 'org:manage_members' permission for the organization specified in the path.
    """
    if org_id != removal.organization_id:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization ID in path and body mismatch.")
    try:
        await auth_service.remove_user_from_organization(db=db, removal=removal, current_user=current_user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (UserNotFoundException, OrganizationNotFoundException, PermissionDeniedException) as e:
        raise e
    except Exception as e:
        auth_logger.exception(f"Error removing user from org {org_id} by user {current_user.email}", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred.")

@router.patch("/organizations/{org_id}", response_model=schemas.OrganizationRead, tags=["organizations"])
async def update_organization_endpoint(
    org_id: uuid.UUID = Path(..., description="The ID of the organization to update"),
    org_update: schemas.OrganizationUpdate = Body(..., description="The updated organization details"),
    db: AsyncSession = Depends(get_async_db_dependency),
    # Check permission using the SpecificOrgPermissionChecker for the org_id in path
    # Using ORG_UPDATE instead of the incorrect ORG_EDIT from the service implementation
    current_user: models.User = Depends(dependencies.SpecificOrgPermissionChecker([Permissions.ORG_UPDATE])),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Update an organization's details.
    
    This endpoint allows updating an organization's name and description. The user must have
    the 'org:update' permission within that organization to perform this operation.
    
    Args:
        org_id: UUID of the organization to update
        org_update: The fields to update (name and/or description)
        
    Returns:
        OrganizationRead: The updated organization
        
    Raises:
        HTTPException: 
            - 404 if organization not found
            - 403 if user lacks permission (handled by dependency)
            - 500 for unexpected errors
    """
    try:
        # Call the service method to handle the update logic
        updated_org = await auth_service.update_organization(
            db=db, 
            org_id=org_id, 
            org_update=org_update, 
            current_user=current_user
        )
        
        auth_logger.info(f"Organization {org_id} updated by user '{current_user.email}'")
        return updated_org
        
    except OrganizationNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Organization not found"
        )
    except Exception as e:
        auth_logger.exception(f"Error updating organization {org_id} by user {current_user.email}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the organization"
        )

@router.patch("/organizations/{org_id}/billing-email", response_model=schemas.OrganizationRead, tags=["organizations"])
async def update_organization_billing_email_endpoint(
    org_id: uuid.UUID = Path(..., description="The ID of the organization to update billing email for"),
    billing_email_update: schemas.OrganizationBillingEmailUpdate = Body(..., description="The new billing email details"),
    db: AsyncSession = Depends(get_async_db_dependency),
    # Check permission using the SpecificOrgPermissionChecker for the org_id in path
    # Using ORG_UPDATE permission for billing email updates
    current_user: models.User = Depends(dependencies.SpecificOrgPermissionChecker([Permissions.ORG_UPDATE])),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Update an organization's primary billing email.
    
    This endpoint allows authorized users to manually set or clear the primary billing
    email for an organization. The user must have the 'org:update' permission within
    that organization to perform this operation.
    
    The primary billing email is automatically managed when users are added/removed
    from organizations, but this endpoint allows for manual override when needed.
    
    Args:
        org_id: UUID of the organization to update
        billing_email_update: The new billing email (or null to clear)
        
    Returns:
        OrganizationRead: The updated organization with the new billing email
        
    Raises:
        HTTPException: 
            - 404 if organization not found
            - 403 if user lacks permission (handled by dependency)
            - 400 for invalid email format
            - 500 for unexpected errors
    """
    try:
        # Call the service method to handle the update logic
        updated_org = await auth_service.update_organization_billing_email(
            db=db, 
            org_id=org_id, 
            billing_email_update=billing_email_update, 
            current_user=current_user
        )
        
        auth_logger.info(f"Billing email for organization {org_id} updated by user '{current_user.email}'")
        return updated_org
        
    except OrganizationNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Organization not found"
        )
    except PermissionDeniedException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.detail
        )
    except Exception as e:
        auth_logger.exception(f"Error updating billing email for organization {org_id} by user {current_user.email}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the organization billing email"
        )

# === Admin/Superuser Endpoints (Example) ===


@router.delete("/admin/users", status_code=status.HTTP_204_NO_CONTENT, tags=["admin"])
async def delete_user_account_endpoint(
    delete_request: schemas.UserDeleteRequest,
    db: AsyncSession = Depends(get_async_db_dependency),
    superuser: models.User = Depends(dependencies.get_current_active_superuser),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Delete a user account.
    
    This endpoint allows superusers to delete user accounts. This is a destructive operation
    that removes the user's personal data, organization memberships, and other associated data
    depending on the implementation in the service layer.
    
    Returns:
        204 No Content on successful deletion
        
    Raises:
        HTTPException: 
            - 500 for unexpected errors during deletion process
    """
    try:
        # Call the service method to handle the deletion logic
        await auth_service.delete_user(db=db, user_id=delete_request.user_id, email=delete_request.email)
        
        # Log the successful deletion
        auth_logger.info(f"User account deleted: {delete_request.email or delete_request.user_id}")
        
        # Return 204 No Content on successful deletion
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        # Log the error but don't expose details to the client
        auth_logger.exception(f"Error deleting user account {delete_request.email or delete_request.user_id}", exc_info=e)
        # TODO: remove exception from error message once API accessible to regular users!
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"An error occurred while deleting your account: {str(e)}"
        )

@router.post("/admin/users/register", response_model=schemas.UserReadWithSuperuserStatus, status_code=status.HTTP_201_CREATED, tags=["admin"])
async def admin_register_user_endpoint(
    *,
    db: AsyncSession = Depends(get_async_db_dependency),
    user_admin_in: schemas.UserAdminCreate, # Use UserAdminCreate schema for input
    request: Request, # For base_url, though not used for email in this flow
    background_tasks: BackgroundTasks, # Required by the service method
    current_admin: models.User = Depends(dependencies.get_current_active_superuser),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    Admin endpoint to register a new user. 
    Allows setting is_verified and is_superuser status. 
    Email verification is skipped.
    """
    auth_logger.info(f"Admin {current_admin.email} attempting to register user: {user_admin_in.email}")
    
    # base_url is required by register_new_user, though not used if email is skipped.
    # Providing a dummy or actual base_url is fine.
    # base_url = _get_base_url(request, settings.AUTH_VERIFY_EMAIL_URL) 

    try:
        user = await auth_service.register_new_user(
            db=db,
            user_in=user_admin_in, # Pass data as dict
            background_tasks=background_tasks,
            base_url=None, # Pass base_url, though email won't be sent
            registered_by_admin=True # Explicitly true for admin registration
        )
        auth_logger.info(f"User {user.email} successfully registered by admin {current_admin.email}. Verified: {user.is_verified}, Superuser: {user.is_superuser}")
        return user
    except EmailAlreadyExistsException as e:
        auth_logger.warning(f"Admin {current_admin.email} failed to register user {user_admin_in.email}: email already exists.")
        raise e
    except RoleNotFoundException as e:
        auth_logger.critical(f"Admin {current_admin.email} failed to register user {user_admin_in.email} due to missing default role: {e.detail}")
        # Critical setup issue if default role is missing
        raise HTTPException(status_code=500, detail=f"Server setup error: {e.detail}")
    except ValueError as ve:
        # Catch specific ValueErrors, like missing password from service layer
        auth_logger.error(f"Admin {current_admin.email} failed to register user {user_admin_in.email} due to ValueError: {ve}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        auth_logger.exception(f"Unexpected error during admin registration of user {user_admin_in.email} by admin {current_admin.email}", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred during admin user registration.")

@router.post("/admin/users", response_model=List[schemas.UserReadWithSuperuserStatus], tags=["admin"])
async def list_users_endpoint(
    skip: int = Query(0, ge=0, description="Number of users to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of users to return"),
    db: AsyncSession = Depends(get_async_db_dependency),
    current_user: models.User = Depends(dependencies.get_current_active_superuser),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    List all users in the system (for admin interface).
    
    This endpoint is restricted to superusers only and provides a paginated list of all users.
    
    Args:
        skip: Number of users to skip (for pagination)
        limit: Maximum number of users to return (for pagination)
        db: Database session
        current_user: The authenticated superuser making the request
        auth_service: Service for user-related operations
        
    Returns:
        List[UserRead]: A list of user objects with their basic information
        
    Raises:
        HTTPException: 
            - 403 if the user is not a superuser (handled by dependency)
            - 500 for unexpected errors
    """
    try:
        users = await auth_service.list_users(db=db, skip=skip, limit=limit)
        auth_logger.info(f"User list retrieved by superuser: {current_user.email}")
        return users
    except Exception as e:
        auth_logger.exception(f"Error listing users by superuser {current_user.email}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the user list"
        )

@router.post("/admin/organizations", response_model=List[schemas.OrganizationRead], tags=["admin"])
async def list_organizations_endpoint(
    skip: int = Query(0, ge=0, description="Number of organizations to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of organizations to return"),
    db: AsyncSession = Depends(get_async_db_dependency),
    current_user: models.User = Depends(dependencies.get_current_active_superuser),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
):
    """
    List all organizations with pagination, for admin interface.
    
    This endpoint provides a paginated list of all organizations in the system.
    
    Args:
        skip: Number of organizations to skip (for pagination)
        limit: Maximum number of organizations to return (for pagination)
        db: Database session
        current_user: The authenticated user making the request
        auth_service: Service for organization-related operations
        
    Returns:
        List[OrganizationRead]: A list of organization objects with their basic information
        
    Raises:
        HTTPException: 
            - 401 if the user is not authenticated (handled by dependency)
            - 500 for unexpected errors
    """
    try:
        organizations = await auth_service.list_organizations(db=db, skip=skip, limit=limit)
        auth_logger.info(f"Organization list retrieved by user: {current_user.email}")
        return organizations
    except Exception as e:
        auth_logger.exception(f"Error listing organizations for user {current_user.email}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the organization list"
        )


@router.post("/admin/roles", response_model=schemas.RoleCreate, status_code=status.HTTP_201_CREATED, tags=["admin"])
async def create_role_endpoint(
    role_in: schemas.RoleCreate,
    db: AsyncSession = Depends(get_async_db_dependency),
    # Requires global superuser status - Checked by this dependency
    current_user: models.User = Depends(dependencies.get_current_active_superuser),
    # DAOs needed to find permissions and create the role
    permission_dao: crud.PermissionDAO = Depends(dependencies.get_permission_dao),
    role_dao: crud.RoleDAO = Depends(dependencies.get_role_dao)
):
    """
    Create a new global role template (requires superuser).
    Links permissions provided by name.
    This role template can then be used when assigning roles within organizations.
    """
    # Permission check is handled by the get_current_active_superuser dependency.
    try:
        # Find permission objects from names provided
        # Fetch all existing permissions defined in the system
        permissions = await permission_dao.get_or_create_multi(db, permissions=[
            schemas.PermissionCreate(name=p.value, description="") # Create dummy PermissionCreate if needed
            for p in ALL_PERMISSIONS # Iterate through all defined Permissions enum members
        ])
        permission_map = {p.name: p for p in permissions}
        linked_permissions = []
        invalid_perms = []
        for perm_name in role_in.permissions:
            if perm_name in permission_map:
                linked_permissions.append(permission_map[perm_name])
            else:
                # Should not happen if Permissions enum is the source of truth
                # but good defensive check.
                invalid_perms.append(perm_name)

        if invalid_perms:
            raise HTTPException(status_code=400, detail=f"Invalid permission names provided: {', '.join(invalid_perms)}")

        # Check if role name already exists globally
        existing_role = await role_dao.get_by_name(db, name=role_in.name)
        if existing_role:
            raise HTTPException(status_code=400, detail="A role template with this name already exists")

        # Create the role using the DAO
        role = await role_dao.create_with_permissions(
            db=db,
            obj_in=role_in,
            permissions=linked_permissions
        )
        auth_logger.info(f"Global role template '{role.name}' created by superuser '{current_user.email}'")
        return role
    except HTTPException as e:
        raise e # Re-raise validation errors
    except Exception as e:
        auth_logger.exception(f"Error creating role template '{role_in.name}' by superuser '{current_user.email}'", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred while creating the role template.")

# Add more admin endpoints: list users, update any user, manage roles/permissions globally etc.
# Protect them with `Depends(dependencies.get_current_active_superuser)`

# === Test Route for Permissions ===
# @router.delete(
#     "/organizations/{org_id}/test-delete",
#     status_code=status.HTTP_204_NO_CONTENT,
#     summary="Test ORG_DELETE Permission",
#     description="(TEST ROUTE) Checks if the current user has ORG_DELETE permission for the specified org."
# )
# async def test_org_delete_permission(
#     org_id: uuid.UUID,
#     # Use the specific org checker with the required permission
#     current_user: models.User = Depends(dependencies.SpecificOrgPermissionChecker([Permissions.ORG_DELETE]))
# ):
#     """
#     Test endpoint to verify ORG_DELETE permission for a given organization.
#     Only returns 204 if the user has the permission, otherwise raises 403.
#     Does not actually delete anything.
#     """
#     # If the dependency check passes, the user has the permission.
#     # No actual deletion logic needed here, just return success.
#     auth_logger.info(f"User {current_user.email} has ORG_DELETE permission for org {org_id}. (Test Route)")
#     return Response(status_code=status.HTTP_204_NO_CONTENT)
