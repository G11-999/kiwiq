from typing import List, Any, Optional, AsyncGenerator
import uuid
import logging # Keep standard logging import if needed elsewhere

from fastapi import APIRouter, Depends, HTTPException, status, Body, Query, Request, Security, BackgroundTasks, Cookie, Response, Path
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm # Special form for username/password
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.src.db.session import get_async_session, get_async_db_dependency # Added get_async_db_dependency
# Change relative to absolute imports
from kiwi_app.auth import crud, models, schemas, security, dependencies, linkedin, utils, services, email_verify # Added email_verify
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
)
from kiwi_app.settings import settings # Import settings for cookie config
# Keep schema imports as they are if direct
from kiwi_app.auth.schemas import (
    Token, UserReadWithOrgs, UserRead, UserCreate, OrganizationRead, OrganizationCreate, RoleRead, RoleCreate, UserAssignRole, RequestEmailVerification,
    # Add new password schemas
    AccessTokenResponse, UserChangePassword, RequestPasswordReset, ResetPassword
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

# Helper function to set the refresh token cookie
def _set_refresh_cookie(response: Response, token: str):
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=token,
        httponly=settings.REFRESH_COOKIE_HTTPONLY,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600 # In seconds
    )

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
    base_url = str(request.base_url)
    try:
        # Service method now handles adding email task to background
        user = await auth_service.register_new_user(
            db=db,
            user_in=user_in,
            background_tasks=background_tasks, # Pass background tasks
            base_url=base_url
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
@router.post("/login/token", response_model=schemas.AccessTokenResponse, tags=["auth"]) # Response model now implicitly just the access token
async def login_for_access_token_endpoint(
    response: Response, # Inject Response object to set cookie
    db: AsyncSession = Depends(get_async_db_dependency),
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
) -> schemas.AccessTokenResponse: # Use a specific response schema for clarity
    """
    Authenticate user, return access token in body and refresh token in secure HttpOnly cookie.
    """
    try:
        user = await auth_service.authenticate_user(db=db, email=form_data.username, password=form_data.password)
        # Generate both tokens
        access_token_str, refresh_token_obj = await auth_service.generate_tokens_for_user(db=db, user=user)
        auth_logger.info(f"User successfully authenticated: {user.email}")

        # Set refresh token in HttpOnly cookie
        _set_refresh_cookie(response, str(refresh_token_obj.token))

        # Return access token in response body
        return schemas.AccessTokenResponse(access_token=access_token_str, token_type="bearer")

    except (CredentialsException, InactiveUserException, UserNotVerifiedException) as e:
        raise e # Re-raise authentication specific exceptions
    except Exception as e:
        auth_logger.exception(f"Unexpected error during login for user: {form_data.username}", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred during login.")

# --- NEW: Refresh Token Endpoint --- #
# NOTE: change `kiwi_app.settings.AUTH_REFRESH_URL` if changing this path!
@router.post("/refresh", response_model=schemas.AccessTokenResponse, tags=["auth"])
async def refresh_token_endpoint(
    response: Response, # Inject Response to set new cookie
    # user: models.User = Depends(dependencies.get_current_active_user),  # This won't work since access token is probably expired!
    refresh_token_from_cookie: Optional[str] = Cookie(None, alias=settings.REFRESH_COOKIE_NAME), # Get from cookie
    db: AsyncSession = Depends(get_async_db_dependency),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
) -> schemas.AccessTokenResponse:
    """
    Get a new access token using the refresh token stored in the HttpOnly cookie.
    Implements refresh token rotation.
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

        # Set the *new* refresh token in the cookie
        _set_refresh_cookie(response, str(new_refresh_token_obj.token))

        # Return the *new* access token
        return schemas.AccessTokenResponse(access_token=new_access_token_str, token_type="bearer")

    except CredentialsException as e:
        # If refresh fails (invalid, expired, revoked), clear the cookie
        response.delete_cookie(key=settings.REFRESH_COOKIE_NAME)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.detail or "Invalid refresh token")
    except Exception as e:
        # Log unexpected errors
        auth_logger.exception(f"Unexpected error during token refresh", exc_info=e)
        # Clear potentially compromised/invalid cookie on error
        response.delete_cookie(key=settings.REFRESH_COOKIE_NAME)
        raise HTTPException(status_code=500, detail="An internal error occurred during token refresh.")

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

        base_url = str(request.base_url)
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
    token: str = Query(...),
    db: AsyncSession = Depends(get_async_db_dependency),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service) # Inject service
):
    """
    Verify user's email address using the provided token.
    """
    try:
        user = await auth_service.verify_user_email(db=db, token=token)
        auth_logger.info(f"Email successfully verified for user: {user.email}")
        # Optional: Redirect to a frontend page on success?
        # return RedirectResponse(url="/login?verified=true")
        return {"message": "Email successfully verified."}
    except InvalidTokenException as e:
        raise e # Re-raise
    except Exception as e:
        auth_logger.exception(f"Unexpected error during email verification with token: {token[:8]}...", exc_info=e)
        raise HTTPException(status_code=500, detail="An internal error occurred during email verification.")

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
    try:
        base_url = str(request.base_url) # API base URL
        result = await auth_service.request_password_reset(
            db=db,
            email=request_data.email,
            background_tasks=background_tasks,
            base_url=base_url
        )
        # Return the generic message from the service
        return JSONResponse(content=result, status_code=status.HTTP_202_ACCEPTED)
    except Exception as e:
        # Log the error but still return 202
        auth_logger.exception(f"Error requesting password reset for {request_data.email}", exc_info=e)
        return JSONResponse(content={"message": "If an account with this email exists, a password reset link will be sent."}, status_code=status.HTTP_202_ACCEPTED)

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

# === LinkedIn OAuth Endpoints ===

@router.get("/linkedin/login", include_in_schema=False, tags=["auth"]) # Hide from OpenAPI UI if desired
async def linkedin_login_redirect_endpoint():
    """
    Redirects the user to LinkedIn for authentication.
    """
    if not linkedin.linkedin_sso:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="LinkedIn Login not configured")
    login_url = await linkedin.get_linkedin_login_url()
    if not login_url:
        raise HTTPException(status_code=500, detail="Could not generate LinkedIn login URL")
    return RedirectResponse(login_url)

@router.get("/linkedin/callback", include_in_schema=False, tags=["auth"]) # Removed response_model=schemas.Token
async def linkedin_callback_endpoint(
    request: Request,
    response: Response, # Inject Response
    db: AsyncSession = Depends(get_async_db_dependency),
    auth_service: services.AuthService = Depends(dependencies.get_auth_service)
) -> schemas.AccessTokenResponse:
    """
    Handles LinkedIn callback, returns access token in body, refresh token in cookie.
    """
    if not linkedin.linkedin_sso:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="LinkedIn Login not configured")
    try:
        linkedin_user_data = await linkedin.verify_linkedin_callback(request)
        if not linkedin_user_data:
             raise HTTPException(status_code=400, detail="Could not verify LinkedIn callback.")

        # Assuming linkedin_user_data is dict-like or can be validated
        linkedin_user = schemas.LinkedInUser.model_validate(linkedin_user_data)

        user = await auth_service.handle_linkedin_callback(db=db, linkedin_user=linkedin_user)
        # Generate tokens
        access_token_str, refresh_token_obj = await auth_service.generate_tokens_for_user(db=db, user=user)
        auth_logger.info(f"User successfully authenticated via LinkedIn: {user.email}")

        # Set refresh token cookie
        _set_refresh_cookie(response, str(refresh_token_obj.token))

        # Return access token
        return schemas.AccessTokenResponse(access_token=access_token_str, token_type="bearer")
    except HTTPException as e:
        raise e
    except Exception as e:
        auth_logger.exception(f"Unexpected error during LinkedIn callback processing", exc_info=e)
        raise HTTPException(status_code=500, detail="Error processing LinkedIn login")

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

    links_to_return = current_user_with_orgs.organization_links

    # Option 2: Use a specific DAO method if created for this purpose
    # links = await crud.user_dao.get_user_organizations_with_roles(db, user_id=current_user.id)

    return links_to_return # FastAPI handles conversion to the response_model

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
    Assign a role to a user within a specific organization.
    Requires the current user to have 'org:manage_members' permission *in that specific org*.
    The org_id is taken from the URL path.
    """
    # if org_id != assignment.organization_id:
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization ID in path and body mismatch.")
    try:
        link = await auth_service.assign_role_to_user_in_org(db=db, org_id=org_id, assignment=assignment, current_user=current_user)
        return link
    except (UserNotFoundException, OrganizationNotFoundException, RoleNotFoundException, PermissionDeniedException) as e:
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


# === Admin/Superuser Endpoints (Example) ===

@router.post("/roles", response_model=schemas.RoleCreate, status_code=status.HTTP_201_CREATED, tags=["admin"])
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
