# TODO: CRITICAL: handle lifecycle of connections dependencies!

import uuid
from typing import Set, List, Optional, AsyncGenerator, Tuple
import logging # Keep standard logging import if needed elsewhere

from fastapi import Depends, HTTPException, status, Request, Security, Header, Path, Cookie # Added Header, Path
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import select, selectinload

from db.session import get_async_session, get_async_db_dependency # Adjust import path if necessary
from kiwi_app.auth import crud, models, schemas, security, services # Import services
from kiwi_app.auth.utils import auth_logger # Import the specific logger
from kiwi_app.auth.constants import Permissions # Import Permissions enum
from kiwi_app.auth.exceptions import (
    CredentialsException,
    UserNotFoundException,
    InactiveUserException,
    UserNotVerifiedException,
    PermissionDeniedException,
    CSRFTokenException,
    # InvalidOrgHeaderException,
    RoleNotFoundException,
)
from kiwi_app.auth.csrf import validate_csrf_protection, validate_csrf_token # Import CSRF utilities
from kiwi_app.settings import settings 
from kiwi_app.auth.schemas import TokenData

# --- DAO Dependency Factories --- #
# These simply return new instances of the DAOs.
# Could add session management here if DAOs held the session.

def get_user_dao() -> crud.UserDAO:
    return crud.UserDAO()

def get_permission_dao() -> crud.PermissionDAO:
    return crud.PermissionDAO()

def get_role_dao() -> crud.RoleDAO:
    return crud.RoleDAO()

def get_organization_dao() -> crud.OrganizationDAO:
    return crud.OrganizationDAO()

def get_refresh_token_dao() -> crud.RefreshTokenDAO:
    return crud.RefreshTokenDAO()

# --- Service Dependency Factory --- #
def get_auth_service(
    user_dao: crud.UserDAO = Depends(get_user_dao),
    org_dao: crud.OrganizationDAO = Depends(get_organization_dao),
    role_dao: crud.RoleDAO = Depends(get_role_dao),
    permission_dao: crud.PermissionDAO = Depends(get_permission_dao),
    refresh_token_dao: crud.RefreshTokenDAO = Depends(get_refresh_token_dao)
) -> services.AuthService:
    """Dependency function to instantiate AuthService with its DAO dependencies."""
    return services.AuthService(
        user_dao=user_dao,
        org_dao=org_dao,
        role_dao=role_dao,
        permission_dao=permission_dao,
        refresh_token_dao=refresh_token_dao
    )

# Get instantiated service (REMOVED - use dependency injection)
# auth_service = services.auth_service

# Get instantiated DAOs (REMOVED - use dependency injection where needed, e.g., in service)
# user_dao = crud.user_dao

# --- Shared Permission Check Logic --- #
async def _check_permissions_for_org(
    db: AsyncSession,
    user_dao: crud.UserDAO,
    user: models.User,
    org_id: uuid.UUID,
    required_permissions: List[Permissions]
) -> None:
    """
    Core logic to check if a user has a specific permission within an organization.
    Fetches necessary data efficiently and raises PermissionDeniedException if check fails.

    Args:
        db: The database session.
        user_dao: Instance of UserDAO.
        user: The authenticated user model.
        org_id: The UUID of the organization to check permissions against.
        required_permissions: The Permissions enum members required.

    Raises:
        PermissionDeniedException: If the user lacks the required permission.
    """
    if user.is_superuser:
        return # Superusers bypass org-specific checks

    # Fetch the specific role link for this user and org
    # DAO method loads role and permissions efficiently
    link = await user_dao.get_user_org_role(db, user_id=user.id, org_id=org_id)

    if not link or not link.role or not link.role.permissions:
        # Handle cases where user is not in org, has no role, or role has no permissions defined
        detail = f"User does not have the required permissions '{', '.join([p.value for p in required_permissions])}' in organization {org_id}. (Reason: Membership/Role/Permissions not found)"
        auth_logger.warning(f"Permission check failed for user '{user.email}': {detail}")
        raise PermissionDeniedException(detail=detail)

    # Check if the required permission name is present in the role's permissions
    user_permissions_in_org = {perm.name for perm in link.role.permissions}
    # auth_logger.warning("\n\n\n\n USER PERMISSIONS IN ORG:: "+ str(user_permissions_in_org) + "\n\n\n\n")
    # auth_logger.warning("\n\n\n\n REQUIRED PERMISSIONS:: "+ str(required_permissions) + "\n\n\n\n")
    if not any(required_permission.value in user_permissions_in_org for required_permission in required_permissions):
        detail = f"Missing required permissions '{', '.join([p.value for p in required_permissions])}' in organization {org_id}."
        auth_logger.warning(f"Permission check failed for user '{user.email}': {detail}")
        raise PermissionDeniedException(detail=detail)

# --- Authentication Dependencies --- #

async def get_current_user(
    db: AsyncSession = Depends(get_async_db_dependency),
    # token: str = Depends(security.oauth2_scheme),  # oauth2_authorization_code_scheme  oauth2_scheme
    access_token: Optional[str] = Cookie(None, alias=settings.ACCESS_TOKEN_COOKIE_NAME),
    csrf_validation: None = Depends(validate_csrf_protection),
    user_dao: crud.UserDAO = Depends(get_user_dao)
) -> models.User:
    """
    Dependency to get the current user from the JWT token (UUID sub) with CSRF protection.
    
    This function validates both the JWT access token and CSRF protection before
    returning the authenticated user. CSRF validation ensures that requests are
    coming from the legitimate frontend application.
    
    Loads basic user info, but *not* detailed org/role/permission links by default.
    Those are loaded dynamically by permission checkers when needed.
    
    Args:
        db: Database session
        access_token: JWT access token from cookie
        csrf_validation: CSRF validation dependency
        user_dao: User data access object
        
    Returns:
        models.User: The authenticated user
        
    Raises:
        CredentialsException: If token is missing or invalid
        HTTPException: If CSRF validation fails (403 Forbidden)
        UserNotFoundException: If user associated with token not found
        
    Security Notes:
        - Validates JWT token signature and expiration
        - Validates CSRF tokens match between cookie and header
        - CSRF validation prevents cross-site request forgery attacks
        - Returns 403 for CSRF failures (authorization issue, not authentication)
    """
    # Validate access token first
    if not access_token:
        raise CredentialsException(detail="No token found in cookie.")
    try:
        token_data = security.decode_access_token(access_token, expected_token_type="access")
    except CredentialsException as e:
        raise e

    # Fetch user by UUID using the injected DAO
    # Do not load relationships here by default for performance.
    user = await user_dao.get(db, id=token_data.sub)

    # Explicit relationship loading removed - handled by permission checks if needed

    if user is None:
        raise UserNotFoundException(detail="User associated with token not found")
    return user


async def get_current_user_from_token_non_dependency(
    db: AsyncSession,
    token: str,  # oauth2_authorization_code_scheme  oauth2_scheme
    expected_token_type: str = "access",
    csrf_validation_token: Optional[str] = None,
    check_active: bool = True,
    check_verified: bool = True
) -> Tuple[models.User, TokenData]:
    """
    Dependency to get the current user from the JWT token (UUID sub).
    Loads basic user info, but *not* detailed org/role/permission links by default.
    Those are loaded dynamically by permission checkers when needed.
    """
    try:
        token_data = security.decode_access_token(token, expected_token_type=expected_token_type)
    except CredentialsException as e:
        raise e
    
    if csrf_validation_token is not None:
        if not (token_data.csrf_token and validate_csrf_token(cookie_token=csrf_validation_token, header_token=token_data.csrf_token)):
            raise CSRFTokenException()


    # Fetch user by UUID using the injected DAO
    # Do not load relationships here by default for performance.
    user_dao = get_user_dao()
    user = await user_dao.get(db, id=token_data.sub)

    if check_active and not user.is_active:
        raise InactiveUserException()
    if check_verified and not user.is_verified:
        raise UserNotVerifiedException()

    # Explicit relationship loading removed - handled by permission checks if needed

    if user is None:
        raise UserNotFoundException(detail="User associated with token not found")
    return user, token_data


class OptionalCurrentUserChecker:
    """
    Dependency class to get current user if authenticated, None otherwise.
    
    This dependency is used for endpoints that support both authenticated
    and unauthenticated access, such as the OAuth initiation endpoint.
    
    Design decisions:
    - Parameterized class allows for flexible configuration of user checks
    - Maintains same interface as original function for easy migration
    - Supports both authenticated and unauthenticated access patterns
    """
    
    def __init__(self, check_active: bool = True, check_verified: bool = True):
        """
        Initialize the dependency with user validation settings.
        
        Args:
            check_active: Whether to check if user is active
            check_verified: Whether to check if user is verified
        """
        self.check_active = check_active
        self.check_verified = check_verified
    
    async def __call__(
        self,
        access_token: Optional[str] = Cookie(None, alias=settings.ACCESS_TOKEN_COOKIE_NAME),
        csrf_cookie: Optional[str] = Cookie(None, alias=settings.CSRF_TOKEN_COOKIE_NAME),
        csrf_header: Optional[str] = Header(None, alias=settings.CSRF_TOKEN_HEADER_NAME),
        db: AsyncSession = Depends(get_async_db_dependency),
    ) -> Optional[models.User]:
        """
        Get current user if authenticated, None otherwise.
        
        Args:
            access_token: JWT access token from cookie
            csrf_cookie: CSRF token from cookie
            csrf_header: CSRF token from header
            db: Database session
            
        Returns:
            Optional[models.User]: User object if authenticated, None otherwise
            
        Raises:
            CSRFTokenException: If CSRF validation fails
        """
        # Validate CSRF protection if cookie is present
        if csrf_cookie:
            if not validate_csrf_token(cookie_token=csrf_cookie, header_token=csrf_header):
                raise CSRFTokenException()
        
        # Return None if no access token (unauthenticated)
        if not access_token:
            return None
        
        # Get user from token with configured validation settings
        try:
            user, token_data = await get_current_user_from_token_non_dependency(
                db, 
                access_token, 
                expected_token_type="access", 
                check_active=self.check_active, 
                check_verified=self.check_verified
            )
            
            return user
        
        except (CredentialsException, InactiveUserException, UserNotVerifiedException, UserNotFoundException) as e:
            auth_logger.exception(f"Unexpected error in OptionalCurrentUserChecker for user {access_token}", exc_info=e)
            return None
        except Exception as e:
            auth_logger.exception(f"Unexpected error in OptionalCurrentUserChecker for user {access_token}", exc_info=e)
            raise e        


# async def get_current_active_verified_user_non_dependency(
#     db: AsyncSession,
#     token: str,
#     expected_token_type: str = "access"
# ) -> models.User:
#     """
#     Dependency to get the current active verified user from the JWT token (UUID sub).
#     """

async def get_current_active_user_with_orgs(
    db: AsyncSession = Depends(get_async_db_dependency),
    # token: str = Depends(security.oauth2_scheme),  # oauth2_authorization_code_scheme  oauth2_scheme
    access_token: Optional[str] = Cookie(None, alias=settings.ACCESS_TOKEN_COOKIE_NAME),
    csrf_validation: None = Depends(validate_csrf_protection),
    user_dao: crud.UserDAO = Depends(get_user_dao)
) -> models.User:
    """
    Dependency to get the current active user with all organization relationships loaded and CSRF protection.
    
    This dependency directly validates the token, CSRF protection, and loads the user with organization
    relationships, rather than building on get_current_active_user. It performs token
    validation, CSRF validation, user lookup, and relationship loading in a single function.
    
    Args:
        db: Database session
        access_token: JWT access token from cookie
        csrf_validation: CSRF validation dependency
        user_dao: User data access object
        
    Returns:
        models.User: User object with organization_links, organizations, and roles loaded
        
    Raises:
        CredentialsException: If the token is invalid
        HTTPException: If CSRF validation fails (403 Forbidden)
        UserNotFoundException: If the user cannot be found
        InactiveUserException: If the user is not active
        UserNotVerifiedException: If the user is not verified
        
    Security Notes:
        - Validates JWT token signature and expiration
        - Validates CSRF tokens match between cookie and header
        - CSRF validation prevents cross-site request forgery attacks
        - Returns 403 for CSRF failures (authorization issue, not authentication)
    """
    # Validate access token first
    if not access_token:
        raise CredentialsException(detail="No token found in cookie.")
    try:
        token_data = security.decode_access_token(access_token, expected_token_type="access")
    except CredentialsException as e:
        raise e
    
    user_with_orgs = await user_dao.get(
        db, 
        id=token_data.sub, 
        load_relations=[
            (models.User, "organization_links"), 
            (models.UserOrganizationRole, "organization_links.organization"),   # UserOrganizationRole
            (models.UserOrganizationRole, "organization_links.role"),
            # "organization_links.role.permissions"
        ]
    )
    # print("\n\n\n\nOrganization: ", user_with_orgs.organization_links[0].organization, "\n\n\n\n")
    # print("\n\n\n\nRole: ", user_with_orgs.organization_links[0].role, "\n\n\n\n")
    # import ipdb; ipdb.set_trace()
    # print(user_with_orgs.organization_links[0].organization)
    # print(user_with_orgs.organization_links[0].role)
    
    if user_with_orgs is None:
        # This should not happen since we already verified the user exists in get_current_active_user
        raise UserNotFoundException(detail="User not found when loading organization relationships")
    if not user_with_orgs.is_active:
        raise InactiveUserException()
    if not user_with_orgs.is_verified:
        raise UserNotVerifiedException()
    return user_with_orgs


async def get_current_active_user(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    """Dependency to get the current *active* user."""
    if not current_user.is_active:
        raise InactiveUserException()
    return current_user

async def get_current_active_verified_user(
    current_user: models.User = Depends(get_current_active_user)
) -> models.User:
    """Dependency to get the current *active* and *verified* user."""
    if not current_user.is_verified:
        raise UserNotVerifiedException()
    return current_user

async def get_current_active_superuser(
    current_user: models.User = Depends(get_current_active_user)
) -> models.User:
    """Dependency to get the current *active* superuser."""
    if not current_user.is_superuser:
        raise PermissionDeniedException(detail="Requires superuser privileges")
    return current_user

# --- Active Organization Context Dependency --- #

async def get_active_org_id(
    x_active_org: Optional[str] = Header(None, alias="X-Active-Org", description="UUID of the organization context for the request.")
) -> Optional[uuid.UUID]:
    """
    Dependency to extract the active organization ID from the X-Active-Org header.

    Returns:
        The UUID of the active organization, or None if header is missing.
        Raises HTTPException if the header value is not a valid UUID.
    """
    if not x_active_org:
        return None
    try:
        return uuid.UUID(x_active_org)
    except ValueError:
        auth_logger.warning(f"Invalid X-Active-Org header received: {x_active_org}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-Active-Org header format. Must be a valid UUID.")

# --- Unified Permission Checking Dependencies (Class-Based) --- #

class PermissionChecker:
    """
    Dependency class to check user permissions against the Active Organization context.

    Usage:
        @app.get("/some/path", dependencies=[Depends(PermissionChecker(Permissions.WORKFLOW_READ))])
        async def some_endpoint(...):
            ...
    """
    def __init__(self, required_permissions: List[Permissions]):
        self.required_permissions = required_permissions

    async def __call__(
        self,
        user: models.User = Depends(get_current_active_verified_user),
        active_org_id: Optional[uuid.UUID] = Depends(get_active_org_id),
        db: AsyncSession = Depends(get_async_db_dependency),
        user_dao: crud.UserDAO = Depends(get_user_dao)
    ) -> models.User:
        """
        Checks if the user has the required permission in the active organization (from X-Active-Org header).
        Delegates the core check to the shared helper function.
        Returns the user if authorized, otherwise raises Exception.
        """
        if user.is_superuser:
            return user # Superusers always have permission

        if active_org_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Active-Org header is required for this operation.")

        # Delegate the check to the shared function
        try:
            await _check_permissions_for_org(
                db=db,
                user_dao=user_dao,
                user=user,
                org_id=active_org_id,
                required_permissions=self.required_permissions
            )
        except PermissionDeniedException as e:
            # Already logged in helper, just re-raise
            raise e
        except Exception as e:
            auth_logger.exception(f"Unexpected error in PermissionChecker for user {user.email}, org {active_org_id}, perm {', '.join([p.value for p in self.required_permissions])}", exc_info=e)
            raise PermissionDeniedException(detail="Permission check failed due to an internal error.")

        # If _check_permissions_for_org didn't raise an exception, permission is granted
        return user

class SpecificOrgPermissionChecker:
    """
    Dependency class to check user permissions against a Specific Organization
    identified by a path parameter.

    Usage:
        @app.delete("/organizations/{org_id}/users", dependencies=[Depends(SpecificOrgPermissionChecker(Permissions.ORG_MANAGE_MEMBERS))])
        async def remove_user(org_id: uuid.UUID, ...):
             ...
    """
    def __init__(self, required_permissions: List[Permissions]):
        self.required_permissions = required_permissions

    async def __call__(
        self,
        org_id: uuid.UUID = Path(..., description="The target organization ID"),
        user: models.User = Depends(get_current_active_verified_user),
        db: AsyncSession = Depends(get_async_db_dependency),
        user_dao: crud.UserDAO = Depends(get_user_dao)
    ) -> models.User:
        """
        Checks if the user has the required permission in the specified organization (from path).
        Delegates the core check to the shared helper function.
        Returns the user if authorized, otherwise raises Exception.
        """
        # Delegate the check to the shared function using org_id from path
        try:
            await _check_permissions_for_org(
                db=db,
                user_dao=user_dao,
                user=user,
                org_id=org_id,
                required_permissions=self.required_permissions
            )
        except PermissionDeniedException as e:
            # Already logged in helper, just re-raise
            raise e
        except Exception as e:
            auth_logger.exception(f"Unexpected error in SpecificOrgPermissionChecker for user {user.email}, org {org_id}, perm {', '.join([p.value for p in self.required_permissions])}", exc_info=e)
            raise PermissionDeniedException(detail="Permission check failed due to an internal error.")
        return user

# # --- REMOVED Old Permission Dependencies --- #
# # def require_permission(...)
# # async def _get_user_for_org_permission_check(...)
# # def require_org_permission(...)

# # --- Permission Checking Dependency --- #

# def require_permissions(required_permissions: List[str]):
#     """
#     Factory function to create a dependency that checks user permissions.

#     This dependency retrieves the user's roles within a specific organization
#     (requires organization_id from the path or query) and checks if their
#     combined permissions include all the required ones.

#     Args:
#         required_permissions: A list of permission strings that the user must possess.

#     Returns:
#         An asynchronous dependency function.
#     """
#     async def _check_permissions(
#         org_id: int, # Assuming org_id is available in the path/query
#         db: AsyncSession = Depends(get_async_db_dependency),
#         current_user: models.User = Depends(get_current_active_verified_user) # Or active_user if verification not needed
#     ) -> models.User:
#         """
#         The actual dependency function that performs the permission check.
#         """
#         user_role = await crud.get_user_roles_in_organization(db, user_id=current_user.id, org_id=org_id)

#         if not user_role:
#             raise PermissionDeniedException(detail="User not part of this organization or no role assigned.")

#         # Assumes permissions are stored as a comma-separated string in the Role model
#         # Adjust parsing logic if using JSON or another format
#         user_permissions = set(p.strip() for p in user_role.permissions.split(',') if p.strip())

#         missing_permissions = set(required_permissions) - user_permissions
#         if missing_permissions:
#             raise PermissionDeniedException(detail=f"Missing required permissions: {', '.join(missing_permissions)}")

#         return current_user # Return the user if permissions are sufficient

#     return _check_permissions 
