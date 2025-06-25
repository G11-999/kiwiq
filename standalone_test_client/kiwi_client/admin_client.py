"""
# poetry run python -m kiwi_client.admin_client

Admin API Test client for Admin endpoints (/auth/admin/*, etc.).

Provides admin functionality for managing users, organizations, and roles.
Requires superuser authentication.

Tests:
- List Users  
- Delete Users
- List Organizations
- Admin User Registration
- List User Organizations
- Create Roles
- And other admin operations
"""
import asyncio
import json
import httpx
import logging
import uuid
from typing import Dict, Any, Optional, List, Union, TypeVar, Tuple
from datetime import datetime

# Import authenticated client and config
from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from kiwi_client.test_config import (
    API_BASE_URL,
    CLIENT_LOG_LEVEL,
    # Admin URLs
    ADMIN_REGISTER_URL,
    ORGANIZATIONS_URL,
    ORG_DETAIL_URL,
)

# Import pydantic for validation
from pydantic import ValidationError, TypeAdapter

# Import schemas
from kiwi_client.schemas.auth_schemas import (
    UserAdminCreate,
    UserReadWithSuperuserStatus,
    UserDeleteRequest,
    OrganizationRead,
    UserReadWithOrgs,
    RoleCreate,
    RoleRead,
)
from kiwi_client.schemas.billing_schemas import (
    PromotionCodeCreate,
    PromotionCodeRead,
    PromotionCodeQuery,
    PaginatedPromotionCodes,
    PromotionCodeDeleteResult,
    PromotionCodeDeactivateRequest,
    PromotionCodeDeactivateResult,
    PromotionCodeBulkDeleteRequest,
    PromotionCodeBulkDeleteResult,
    CreditType,
    SortOrder,
)

# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)

# Create TypeAdapters for validating lists of schemas
try:
    UserReadListAdapter = TypeAdapter(List[UserReadWithSuperuserStatus])
    OrganizationReadListAdapter = TypeAdapter(List[OrganizationRead])
except (AttributeError, NameError):
    logger.warning("TypeAdapter for admin schemas could not be created")
    UserReadListAdapter = None
    OrganizationReadListAdapter = None


class AdminClient:
    """
    Provides methods to test admin endpoints that require superuser privileges.
    
    This client wraps admin-only API endpoints for:
    - User management (list, create, delete users)
    - Organization management (list organizations)
    - Role management (create roles)
    - User organization relationships
    
    All methods require the authenticated user to have superuser privileges.
    """
    
    def __init__(self, auth_client: AuthenticatedClient):
        """
        Initializes the AdminClient.

        Args:
            auth_client (AuthenticatedClient): An authenticated client instance with superuser privileges.
        """
        self._auth_client = auth_client
        self._client: httpx.AsyncClient = auth_client.client
        logger.info("AdminClient initialized.")

    async def admin_register_user(
        self,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        is_verified: bool = True,
        is_superuser: bool = False
    ) -> Optional[UserReadWithSuperuserStatus]:
        """
        Register a new user with admin privileges.
        
        This method allows superusers to create new users with specified
        verification status and superuser privileges. Email verification
        is skipped for admin-created users.
        
        Args:
            email: Email address for the new user
            password: Password for the new user
            full_name: Optional full name for the user
            is_verified: Whether the user's email should be considered verified
            is_superuser: Whether the user should have superuser privileges
            
        Returns:
            Optional[UserReadWithSuperuserStatus]: The newly created user data or None on failure
        """
        logger.info(f"Admin registering new user: {email} (verified={is_verified}, superuser={is_superuser})")
        
        # Create user data using the UserAdminCreate schema
        user_data = UserAdminCreate(
            email=email,
            password=password,
            full_name=full_name,
            is_verified=is_verified,
            is_superuser=is_superuser
        ).model_dump()
        
        try:
            response = await self._client.post(ADMIN_REGISTER_URL, json=user_data)
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response against UserReadWithSuperuserStatus schema
            validated_user = UserReadWithSuperuserStatus.model_validate(response_json)
            logger.info(f"Successfully registered user {email} with admin privileges")
            logger.debug(f"Admin register response validated: {validated_user.model_dump_json(indent=2)}")
            return validated_user
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error admin registering user {email}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error admin registering user {email}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error admin registering user {email}: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception(f"Unexpected error admin registering user {email}")
            
        return None

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> Optional[List[UserReadWithSuperuserStatus]]:
        """
        List all users in the system (admin interface).
        
        This endpoint is restricted to superusers only and provides a paginated
        list of all users with their superuser status.
        
        Args:
            skip: Number of users to skip (for pagination)
            limit: Maximum number of users to return (for pagination)
            
        Returns:
            Optional[List[UserReadWithSuperuserStatus]]: List of users or None on failure
        """
        logger.info(f"Admin listing users (skip={skip}, limit={limit})...")
        
        try:
            # The endpoint uses POST with query parameters
            params = {"skip": skip, "limit": limit}
            response = await self._client.post(f"{API_BASE_URL}/auth/admin/users", params=params)
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response list against List[UserReadWithSuperuserStatus]
            if UserReadListAdapter:
                validated_users = UserReadListAdapter.validate_python(response_json)
                logger.info(f"Successfully listed and validated {len(validated_users)} users.")
                logger.debug(f"List users response (first item): {validated_users[0].model_dump() if validated_users else 'None'}")
                return validated_users
            else:
                # Fallback if schemas weren't imported
                logger.warning("Schema validation skipped for list_users due to import failure.")
                return response_json
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing users: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error listing users: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error listing users: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error listing users")
            
        return None

    async def delete_user(
        self,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        email: Optional[str] = None
    ) -> bool:
        """
        Delete a user account (superuser only).
        
        This is a destructive operation that removes the user's personal data,
        organization memberships, and other associated data.
        
        Args:
            user_id: UUID of the user to delete (optional)
            email: Email of the user to delete (optional)
            
        Note: Either user_id or email must be provided.
            
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        if not user_id and not email:
            logger.error("Either user_id or email must be provided for user deletion")
            return False
        
        user_identifier = str(user_id) if user_id else email
        logger.info(f"Admin deleting user: {user_identifier}")
        
        # Create deletion request using the UserDeleteRequest schema
        delete_data = UserDeleteRequest(
            user_id=uuid.UUID(user_id) if user_id and isinstance(user_id, str) else user_id,
            email=email
        ).model_dump(exclude_none=True)  # Only include fields that were provided
        
        try:
            # For DELETE requests with JSON body, we use the request method
            response = await self._client.request(
                method="DELETE",
                url=f"{API_BASE_URL}/auth/admin/users",
                json=delete_data
            )
            response.raise_for_status()
            
            logger.info(f"Successfully deleted user: {user_identifier}")
            return True
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error deleting user {user_identifier}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error deleting user {user_identifier}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error deleting user {user_identifier}")
            
        return False

    async def list_organizations(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> Optional[List[OrganizationRead]]:
        """
        List all organizations with pagination (admin interface).
        
        This endpoint provides a paginated list of all organizations in the system.
        
        Args:
            skip: Number of organizations to skip (for pagination)
            limit: Maximum number of organizations to return (for pagination)
            
        Returns:
            Optional[List[OrganizationRead]]: List of organizations or None on failure
        """
        logger.info(f"Admin listing organizations (skip={skip}, limit={limit})...")
        
        try:
            # The endpoint uses POST with query parameters
            params = {"skip": skip, "limit": limit}
            response = await self._client.post(f"{API_BASE_URL}/auth/admin/organizations", params=params)
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response list against List[OrganizationRead]
            if OrganizationReadListAdapter:
                validated_orgs = OrganizationReadListAdapter.validate_python(response_json)
                logger.info(f"Successfully listed and validated {len(validated_orgs)} organizations.")
                logger.debug(f"List organizations response (first item): {validated_orgs[0].model_dump() if validated_orgs else 'None'}")
                return validated_orgs
            else:
                # Fallback if schemas weren't imported
                logger.warning("Schema validation skipped for list_organizations due to import failure.")
                return response_json
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing organizations: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error listing organizations: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error listing organizations: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error listing organizations")
            
        return None

    async def list_user_organizations(
        self,
        user_email: str
    ) -> Optional[UserReadWithOrgs]:
        """
        List all organizations a user is a member of, including their role.
        
        This is an admin endpoint that allows superusers to view any user's
        organization memberships and roles.
        
        Args:
            user_email: Email of the user to lookup
            
        Returns:
            Optional[UserReadWithOrgs]: User with organization details or None on failure
        """
        logger.info(f"Admin listing organizations for user: {user_email}")
        
        try:
            params = {"user_email": user_email}
            response = await self._client.get(f"{API_BASE_URL}/auth/admin/users/organizations", params=params)
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response against UserReadWithOrgs schema
            validated_user = UserReadWithOrgs.model_validate(response_json)
            logger.info(f"Successfully retrieved organizations for user {user_email}")
            logger.debug(f"User organizations response validated: {validated_user.model_dump_json(indent=2)}")
            return validated_user
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing organizations for user {user_email}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error listing organizations for user {user_email}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error listing organizations for user {user_email}: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception(f"Unexpected error listing organizations for user {user_email}")
            
        return None

    async def create_role(
        self,
        name: str,
        description: str,
        permissions: List[str]
    ) -> Optional[RoleRead]:
        """
        Create a new global role template (requires superuser).
        
        Creates a role template that can be used when assigning roles within organizations.
        Links the specified permissions by name.
        
        Args:
            name: Name of the role
            description: Description of the role
            permissions: List of permission names to associate with this role
            
        Returns:
            Optional[RoleRead]: The created role or None on failure
        """
        logger.info(f"Admin creating role: {name} with {len(permissions)} permissions")
        
        # Create role data using the RoleCreate schema
        role_data = RoleCreate(
            name=name,
            description=description,
            permissions=permissions
        ).model_dump()
        
        try:
            response = await self._client.post(f"{API_BASE_URL}/auth/admin/roles", json=role_data)
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response against RoleRead schema
            validated_role = RoleRead.model_validate(response_json)
            logger.info(f"Successfully created role: {name}")
            logger.debug(f"Create role response validated: {validated_role.model_dump_json(indent=2)}")
            return validated_role
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error creating role {name}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error creating role {name}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error creating role {name}: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception(f"Unexpected error creating role {name}")
            
        return None

    async def create_promotion_code(
        self,
        code: str,
        description: Optional[str],
        credit_type: CreditType,
        credits_amount: float,
        max_uses: Optional[int] = None,
        max_uses_per_org: int = 1,
        expires_at: Optional[datetime] = None,
        is_active: bool = True,
        allowed_org_ids: Optional[List[str]] = None,
        granted_credits_expire_days: Optional[int] = None
    ) -> Optional[PromotionCodeRead]:
        """
        Create a new promotion code (Admin only).
        
        Creates a promotion code that organizations can use to receive free credits.
        Supports various configuration options for usage limits, expiration, and
        organization restrictions.
        
        Args:
            code: The promotion code string
            description: Optional description of the promotion code
            credit_type: Type of credits to grant (workflows, web_searches, dollar_credits)
            credits_amount: Number of credits to grant per use
            max_uses: Maximum total uses across all organizations (None = unlimited)
            max_uses_per_org: Maximum uses per organization (default: 1)
            expires_at: Optional expiration date for the code
            is_active: Whether the code is active (default: True)
            allowed_org_ids: Optional list of organization IDs that can use this code
            granted_credits_expire_days: Optional number of days until granted credits expire
            
        Returns:
            Optional[PromotionCodeRead]: The created promotion code or None on failure
        """
        logger.info(f"Admin creating promotion code: {code} ({credit_type.value}, {credits_amount} credits)")
        
        # Create promotion code data using the PromotionCodeCreate schema
        promo_code_data = PromotionCodeCreate(
            code=code,
            description=description,
            credit_type=credit_type,
            credits_amount=credits_amount,
            max_uses=max_uses,
            max_uses_per_org=max_uses_per_org,
            expires_at=expires_at,
            is_active=is_active,
            allowed_org_ids=allowed_org_ids,
            granted_credits_expire_days=granted_credits_expire_days
        ).model_dump(mode='json', exclude_none=True)
        
        try:
            response = await self._client.post(f"{API_BASE_URL}/billing/admin/promo-codes", json=promo_code_data)
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response against PromotionCodeRead schema
            validated_promo_code = PromotionCodeRead.model_validate(response_json)
            logger.info(f"Successfully created promotion code: {code}")
            logger.debug(f"Create promotion code response validated: {validated_promo_code.model_dump_json(indent=2)}")
            return validated_promo_code
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error creating promotion code {code}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error creating promotion code {code}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error creating promotion code {code}: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception(f"Unexpected error creating promotion code {code}")
            
        return None

    async def list_promotion_codes(
        self,
        is_active: Optional[bool] = None,
        credit_type: Optional[CreditType] = None,
        search_text: Optional[str] = None,
        expires_after: Optional[datetime] = None,
        expires_before: Optional[datetime] = None,
        has_usage_limit: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: SortOrder = SortOrder.DESC,
        skip: int = 0,
        limit: int = 100
    ) -> Optional[PaginatedPromotionCodes]:
        """
        List/query promotion codes with filtering and pagination (Admin only).
        
        Provides comprehensive promotion code querying capabilities with support for:
        - Active status filtering
        - Credit type filtering  
        - Text search in code/description
        - Expiration date range filtering
        - Usage limit filtering
        - Flexible sorting and pagination
        
        Args:
            is_active: Filter by active status
            credit_type: Filter by credit type
            search_text: Search in code or description
            expires_after: Filter codes that expire after this date
            expires_before: Filter codes that expire before this date
            has_usage_limit: Filter codes with/without usage limits
            sort_by: Field to sort by (default: "created_at")
            sort_order: Sort order (default: DESC)
            skip: Number of records to skip for pagination
            limit: Maximum number of records to return
            
        Returns:
            Optional[PaginatedPromotionCodes]: Paginated promotion codes or None on failure
        """
        logger.info(f"Admin listing promotion codes (skip={skip}, limit={limit}, filters applied)")
        
        # Build query parameters using PromotionCodeQuery schema
        query_params = PromotionCodeQuery(
            is_active=is_active,
            credit_type=credit_type,
            search_text=search_text,
            expires_after=expires_after,
            expires_before=expires_before,
            has_usage_limit=has_usage_limit,
            sort_by=sort_by,
            sort_order=sort_order,
            skip=skip,
            limit=limit
        ).model_dump(mode='json', exclude_none=True)
        
        try:
            response = await self._client.post(f"{API_BASE_URL}/billing/admin/promo-codes/query", json=query_params)
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response against PaginatedPromotionCodes schema
            validated_promo_codes = PaginatedPromotionCodes.model_validate(response_json)
            logger.info(f"Successfully listed {len(validated_promo_codes.items)} promotion codes (total: {validated_promo_codes.total})")
            logger.debug(f"List promotion codes response validated: filters={validated_promo_codes.filters_applied}")
            return validated_promo_codes
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing promotion codes: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error listing promotion codes: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error listing promotion codes: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error listing promotion codes")
            
        return None

    async def delete_promotion_code(
        self,
        promo_code_id: uuid.UUID
    ) -> Optional[PromotionCodeDeleteResult]:
        """
        Delete a promotion code by ID (Admin only).
        
        This method safely deletes a promotion code with the following safeguards:
        - Verifies the promotion code exists
        - Prevents deletion if there are existing usage records to maintain audit trail
        - Provides detailed feedback about the deletion attempt
        
        **Important Notes:**
        - If a promotion code has been used, it cannot be deleted to preserve billing audit trails
        - Consider deactivating the code instead if it has usage history
        - This operation is irreversible
        
        Args:
            promo_code_id: UUID of the promotion code to delete
            
        Returns:
            Optional[PromotionCodeDeleteResult]: Deletion result or None on failure
        """
        logger.info(f"Admin deleting promotion code: {promo_code_id}")
        
        try:
            response = await self._client.delete(f"{API_BASE_URL}/billing/admin/promo-codes/{promo_code_id}")
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response against PromotionCodeDeleteResult schema
            validated_result = PromotionCodeDeleteResult.model_validate(response_json)
            logger.info(f"Successfully deleted promotion code: {validated_result.code} (ID: {promo_code_id})")
            logger.debug(f"Delete promotion code response validated: {validated_result.model_dump_json(indent=2)}")
            return validated_result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error deleting promotion code {promo_code_id}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error deleting promotion code {promo_code_id}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error deleting promotion code {promo_code_id}: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception(f"Unexpected error deleting promotion code {promo_code_id}")
            
        return None

    async def deactivate_promotion_codes(
        self,
        promo_code_ids: Optional[List[uuid.UUID]] = None,
        codes: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
        credit_type: Optional[CreditType] = None,
        search_text: Optional[str] = None,
        expires_after: Optional[datetime] = None,
        expires_before: Optional[datetime] = None,
        has_usage_limit: Optional[bool] = None,
        deactivate_all: bool = False
    ) -> Optional[PromotionCodeDeactivateResult]:
        """
        Deactivate promotion codes with flexible targeting (Admin only).
        
        This method provides comprehensive deactivation capabilities with support for:
        - **Direct Targeting**: Specific promotion code IDs or code strings
        - **Query-Based Targeting**: Filter-based targeting
        - **Bulk Operations**: Deactivate multiple codes at once
        - **Safety Controls**: Explicit confirmation required for mass operations
        
        **Benefits of Deactivation over Deletion:**
        - Preserves complete audit trail and billing history
        - Safe operation with no risk of data loss
        - Can be reversed by reactivating codes
        - Maintains referential integrity
        
        Args:
            promo_code_ids: List of specific promotion code UUIDs
            codes: List of specific promotion code strings
            is_active: Filter by current active status
            credit_type: Filter by credit type
            search_text: Search within code names or descriptions
            expires_after/expires_before: Filter by expiration date ranges
            has_usage_limit: Filter codes with/without usage limits
            deactivate_all: Explicit flag to deactivate all codes (if no other filters)
            
        Returns:
            Optional[PromotionCodeDeactivateResult]: Deactivation result or None on failure
        """
        logger.info(f"Admin deactivating promotion codes (direct IDs: {len(promo_code_ids or [])}, direct codes: {len(codes or [])})")
        
        # Create deactivation request using PromotionCodeDeactivateRequest schema
        deactivate_request = PromotionCodeDeactivateRequest(
            promo_code_ids=promo_code_ids,
            codes=codes,
            is_active=is_active,
            credit_type=credit_type,
            search_text=search_text,
            expires_after=expires_after,
            expires_before=expires_before,
            has_usage_limit=has_usage_limit,
            deactivate_all=deactivate_all
        ).model_dump(mode='json', exclude_none=True)
        
        try:
            response = await self._client.patch(f"{API_BASE_URL}/billing/admin/promo-codes/deactivate", json=deactivate_request)
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response against PromotionCodeDeactivateResult schema
            validated_result = PromotionCodeDeactivateResult.model_validate(response_json)
            logger.info(f"Successfully deactivated {validated_result.deactivated_count} promotion codes")
            logger.debug(f"Deactivate promotion codes response validated: {validated_result.model_dump_json(indent=2)}")
            return validated_result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error deactivating promotion codes: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error deactivating promotion codes: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error deactivating promotion codes: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error deactivating promotion codes")
            
        return None

    async def bulk_delete_promotion_codes(
        self,
        promo_code_ids: Optional[List[uuid.UUID]] = None,
        codes: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
        credit_type: Optional[CreditType] = None,
        search_text: Optional[str] = None,
        expires_after: Optional[datetime] = None,
        expires_before: Optional[datetime] = None,
        has_usage_limit: Optional[bool] = None,
        delete_all: bool = False,
        force_delete_used: bool = False
    ) -> Optional[PromotionCodeBulkDeleteResult]:
        """
        Bulk delete promotion codes with flexible targeting (Admin only).
        
        This method provides comprehensive bulk deletion capabilities with support for:
        - **Direct Targeting**: Specific promotion code IDs or code strings
        - **Query-Based Targeting**: Filter-based targeting
        - **Bulk Operations**: Delete multiple codes at once with safety controls
        - **Usage Protection**: Automatic skipping of codes with usage history
        - **Force Deletion**: Override protection for complete cleanup (dangerous)
        
        **⚠️ DANGER ZONE:**
        Setting `force_delete_used=True` will delete promotion codes that have been used,
        potentially breaking audit trails and billing history. Use with extreme caution.
        
        **Recommended Workflow:**
        1. First run with `force_delete_used=False` (default) to see what would be skipped
        2. Consider deactivating used codes instead of deleting them
        3. Only use `force_delete_used=True` if you absolutely need to purge everything
        
        Args:
            promo_code_ids: List of specific promotion code UUIDs
            codes: List of specific promotion code strings
            is_active: Filter by current active status
            credit_type: Filter by credit type
            search_text: Search within code names or descriptions
            expires_after/expires_before: Filter by expiration date ranges
            has_usage_limit: Filter codes with/without usage limits
            delete_all: Explicit flag to delete all codes (if no other filters)
            force_delete_used: Allow deletion of codes with usage records (DANGEROUS)
            
        Returns:
            Optional[PromotionCodeBulkDeleteResult]: Bulk deletion result or None on failure
        """
        logger.warning(f"Admin bulk deleting promotion codes (direct IDs: {len(promo_code_ids or [])}, direct codes: {len(codes or [])}, force_delete_used: {force_delete_used})")
        
        # Create bulk delete request using PromotionCodeBulkDeleteRequest schema
        delete_request = PromotionCodeBulkDeleteRequest(
            promo_code_ids=promo_code_ids,
            codes=codes,
            is_active=is_active,
            credit_type=credit_type,
            search_text=search_text,
            expires_after=expires_after,
            expires_before=expires_before,
            has_usage_limit=has_usage_limit,
            delete_all=delete_all,
            force_delete_used=force_delete_used
        ).model_dump(mode='json', exclude_none=True)
        
        try:
            # Use request method for DELETE with JSON body
            response = await self._client.request(
                method="DELETE",
                url=f"{API_BASE_URL}/billing/admin/promo-codes/bulk",
                json=delete_request
            )
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response against PromotionCodeBulkDeleteResult schema
            validated_result = PromotionCodeBulkDeleteResult.model_validate(response_json)
            logger.warning(f"Successfully bulk deleted {validated_result.deleted_count} promotion codes, skipped {validated_result.skipped_count} codes")
            logger.debug(f"Bulk delete promotion codes response validated: {validated_result.model_dump_json(indent=2)}")
            return validated_result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error bulk deleting promotion codes: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error bulk deleting promotion codes: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error bulk deleting promotion codes: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error bulk deleting promotion codes")
            
        return None

    async def delete_organization(
        self,
        org_id: Union[str, uuid.UUID]
    ) -> bool:
        """
        Delete an organization and all its associated data (superuser only).
        
        This is a destructive operation that removes the organization,
        all user-organization links, and potentially other associated data.
        
        Args:
            org_id: UUID of the organization to delete
            
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        org_id_str = str(org_id)
        logger.info(f"Admin deleting organization: {org_id_str}")
        
        try:
            response = await self._client.delete(ORG_DETAIL_URL(org_id_str))
            response.raise_for_status()
            
            logger.info(f"Successfully deleted organization: {org_id_str}")
            return True
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error deleting organization {org_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error deleting organization {org_id_str}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error deleting organization {org_id_str}")
            
        return False


# --- Example Usage --- (for testing this module directly)
async def main():
    """Demonstrates using the AdminClient for admin operations."""
    print("--- Starting Admin API Test ---")
    temp_user_email: Optional[str] = None
    temp_org_id: Optional[uuid.UUID] = None
    
    try:
        async with AuthenticatedClient() as auth_client:
            print("Authenticated as admin.")
            admin_client = AdminClient(auth_client)

            # Test 1: List Users
            print("\n1. Listing Users...")
            users = await admin_client.list_users(limit=5)
            if users:
                print(f"   Found {len(users)} users.")
                for user in users[:3]:  # Show first 3
                    print(f"   - {user.email} (ID: {user.id}, Superuser: {user.is_superuser})")
            else:
                print("   Failed to list users.")

            # Test 2: List Organizations  
            print("\n2. Listing Organizations...")
            orgs = await admin_client.list_organizations(limit=5)
            if orgs:
                print(f"   Found {len(orgs)} organizations.")
                for org in orgs[:3]:  # Show first 3
                    print(f"   - {org.name} (ID: {org.id})")
                    if not temp_org_id:  # Store first org for potential testing
                        temp_org_id = org.id
            else:
                print("   Failed to list organizations.")

            # Test 3: Create a Test User
            print("\n3. Creating Test User...")
            test_email = f"test_admin_user_{uuid.uuid4().hex[:8]}@example.com"
            created_user = await admin_client.admin_register_user(
                email=test_email,
                password="TestPassword123!",
                full_name="Test Admin User",
                is_verified=True,
                is_superuser=False
            )
            if created_user:
                temp_user_email = created_user.email
                print(f"   Successfully created test user: {created_user.email}")
                print(f"   User ID: {created_user.id}, Verified: {created_user.is_verified}")
            else:
                print("   Failed to create test user.")

            # Test 4: List User Organizations (if we have a user)
            if temp_user_email:
                print(f"\n4. Listing Organizations for User: {temp_user_email}")
                user_orgs = await admin_client.list_user_organizations(temp_user_email)
                if user_orgs:
                    print(f"   User has {len(user_orgs.organization_links)} organization memberships.")
                    for link in user_orgs.organization_links:
                        print(f"   - Org: {link.organization.name if link.organization else 'Unknown'}")
                        print(f"     Role: {link.role.name if link.role else 'Unknown'}")
                else:
                    print("   Failed to list user organizations or user has no org memberships.")

            # Test 5: Create a Test Promotion Code
            print("\n5. Creating Test Promotion Code...")
            test_promo_code = f"TEST_PROMO_{uuid.uuid4().hex[:8].upper()}"
            created_promo = await admin_client.create_promotion_code(
                code=test_promo_code,
                description="Test promotion code created by admin client",
                credit_type=CreditType.WORKFLOWS,
                credits_amount=100.0,
                max_uses=10,
                max_uses_per_org=1,
                expires_at=None,  # No expiration for testing
                is_active=True
            )
            if created_promo:
                print(f"   Successfully created promotion code: {created_promo.code}")
                print(f"   Code ID: {created_promo.id}, Credits: {created_promo.credits_amount} {created_promo.credit_type.value}")
                print(f"   Max Uses: {created_promo.max_uses}, Uses Count: {created_promo.uses_count}")
            else:
                print("   Failed to create test promotion code.")

            # Test 6: List Promotion Codes
            print("\n6. Listing Promotion Codes...")
            promo_codes = await admin_client.list_promotion_codes(
                is_active=True,
                limit=5
            )
            if promo_codes:
                print(f"   Found {len(promo_codes.items)} active promotion codes (total: {promo_codes.total})")
                for promo in promo_codes.items[:3]:  # Show first 3
                    print(f"   - {promo.code} ({promo.credit_type.value}): {promo.credits_amount} credits")
                    print(f"     Uses: {promo.uses_count}/{promo.max_uses or 'unlimited'}, Active: {promo.is_active}")
            else:
                print("   Failed to list promotion codes.")

            # Test 7: Search Promotion Codes by Credit Type
            print("\n7. Searching Promotion Codes by Credit Type...")
            workflow_promos = await admin_client.list_promotion_codes(
                credit_type=CreditType.WORKFLOWS,
                search_text="TEST",
                limit=10
            )
            if workflow_promos:
                print(f"   Found {len(workflow_promos.items)} workflow promotion codes with 'TEST' in name")
                for promo in workflow_promos.items:
                    print(f"   - {promo.code}: {promo.credits_amount} workflow credits")
            else:
                print("   No workflow promotion codes found with 'TEST' in name.")

            # Test 8: Delete Test Promotion Code (cleanup)
            if created_promo:
                print(f"\n8. Deleting Test Promotion Code: {created_promo.code}")
                delete_result = await admin_client.delete_promotion_code(created_promo.id)
                if delete_result and delete_result.success:
                    print(f"   Successfully deleted promotion code: {delete_result.code}")
                else:
                    print("   Failed to delete test promotion code or code had usage records.")

            # Test 9: Demonstrate Bulk Operations (commented out for safety)
            print("\n9. Bulk Operations Demo (Deactivation)")
            print("   Creating multiple test codes for bulk operation demo...")
            
            test_codes = []
            for i in range(3):
                bulk_test_code = f"BULK_TEST_{uuid.uuid4().hex[:6].upper()}_{i+1}"
                bulk_promo = await admin_client.create_promotion_code(
                    code=bulk_test_code,
                    description=f"Bulk test promotion code #{i+1}",
                    credit_type=CreditType.WEB_SEARCHES,
                    credits_amount=50.0,
                    max_uses=5,
                    max_uses_per_org=1,
                    is_active=True
                )
                if bulk_promo:
                    test_codes.append(bulk_promo)
                    print(f"   Created: {bulk_promo.code}")

            if test_codes:
                print(f"   Deactivating {len(test_codes)} test codes...")
                deactivate_result = await admin_client.deactivate_promotion_codes(
                    codes=[code.code for code in test_codes]
                )
                if deactivate_result and deactivate_result.success:
                    print(f"   Successfully deactivated {deactivate_result.deactivated_count} codes")
                    print(f"   Deactivated codes: {deactivate_result.deactivated_codes}")
                else:
                    print("   Failed to deactivate test codes.")

                # Clean up by deleting the test codes
                print("   Cleaning up test codes...")
                cleanup_result = await admin_client.bulk_delete_promotion_codes(
                    codes=[code.code for code in test_codes],
                    force_delete_used=False  # Safe deletion
                )
                if cleanup_result and cleanup_result.success:
                    print(f"   Cleaned up {cleanup_result.deleted_count} test codes, skipped {cleanup_result.skipped_count}")
                else:
                    print("   Failed to clean up some test codes.")

            # Test 6: Delete Test User (cleanup)
            if temp_user_email and created_user:
                print(f"\n10. Deleting Test User: {temp_user_email}")
                deleted = await admin_client.delete_user(email=temp_user_email)
                if deleted:
                    print("   Successfully deleted test user.")
                    temp_user_email = None  # Clear for cleanup
                else:
                    print("   Failed to delete test user.")

            # Note: We're not testing organization deletion as it's very destructive
            # and would require careful setup to avoid deleting important data
            print("\n   Note: Organization deletion test skipped (too destructive for demo)")
            print("\n--- Promotion Code Management Features Demonstrated ---")
            print("✓ Create promotion codes with flexible configuration")
            print("✓ List and query promotion codes with filtering")
            print("✓ Search promotion codes by credit type and text")
            print("✓ Delete individual promotion codes")
            print("✓ Bulk deactivate promotion codes")
            print("✓ Bulk delete promotion codes with safety controls")

    except AuthenticationError as e:
        print(f"Authentication Error: {e}")
        print("Note: Admin endpoints require superuser privileges.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        logger.exception("Main test execution error:")
    finally:
        # Cleanup any remaining test data
        if temp_user_email:
            print(f"\nAttempting cleanup: Deleting test user {temp_user_email}...")
            try:
                async with AuthenticatedClient() as cleanup_auth_client:
                    cleanup_admin = AdminClient(cleanup_auth_client)
                    await cleanup_admin.delete_user(email=temp_user_email)
                    print("   Cleanup successful.")
            except Exception as cleanup_e:
                print(f"   Cleanup failed: {cleanup_e}")

        print("--- Admin API Test Finished ---")


if __name__ == "__main__":
    # Ensure API server is running and you're authenticated as a superuser
    # Run with: PYTHONPATH=. python -m kiwi_client.admin_client
    print("Running AdminClient test...")
    asyncio.run(main())
