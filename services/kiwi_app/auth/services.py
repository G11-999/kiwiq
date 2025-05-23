import uuid
import logging # Keep standard logging import if needed elsewhere, but we use the specific logger
from typing import Optional, List, Set, Tuple
from datetime import datetime, timedelta # Import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status, BackgroundTasks # Add BackgroundTasks

from kiwi_app.auth import crud, models, schemas, security # Added email_verify
from kiwi_app.auth.utils import auth_logger, datetime_now_utc # Import datetime_now_utc
from kiwi_app.auth.constants import DefaultRoles, Permissions, DEFAULT_FIRST_USER_ORG_SUFFIX
from kiwi_app.auth.exceptions import (
    EmailAlreadyExistsException,
    UserNotFoundException,
    CredentialsException,
    InactiveUserException,
    InvalidTokenException,
    OrganizationNotFoundException,
    RoleNotFoundException,
    PermissionDeniedException,
    UserNotVerifiedException,
)
from kiwi_app.email import email_verify
from kiwi_app.settings import settings # Import settings

class AuthService:
    """Service layer for authentication and user management logic."""

    def __init__(self,
                 user_dao: crud.UserDAO,
                 org_dao: crud.OrganizationDAO,
                 role_dao: crud.RoleDAO,
                 permission_dao: crud.PermissionDAO,
                 refresh_token_dao: crud.RefreshTokenDAO): # Inject RefreshTokenDAO
        """Initialize service with DAO instances."""
        self.user_dao = user_dao
        self.org_dao = org_dao
        self.role_dao = role_dao
        self.permission_dao = permission_dao
        self.refresh_token_dao = refresh_token_dao # Store DAO instance

    async def register_new_user(
        self, db: AsyncSession, user_in: schemas.UserCreate | schemas.UserAdminCreate, background_tasks: BackgroundTasks, base_url: str, registered_by_admin: bool = False
    ) -> models.User:
        """
        Handles user registration, creates a default organization, assigns admin role,
        and triggers email verification via background tasks if not registered by admin.
        If registered by admin, user is marked as verified.
        """
        existing_user = await self.user_dao.get_by_email(db, email=user_in.email)
        if existing_user:
            raise EmailAlreadyExistsException()

        # 1. Create the user
        if not registered_by_admin and isinstance(user_in, schemas.UserAdminCreate):
            raise HTTPException(status_code=400, detail="Admin registration not allowed for regular users.")
        new_user = await self.user_dao.create_user(db=db, user_in=user_in)

        # 2. Create a default organization for the user
        org_name = f"{new_user.full_name or new_user.email.split('@')[0]}{DEFAULT_FIRST_USER_ORG_SUFFIX}"
        # Ensure org name is unique if necessary, add retry/suffix logic if needed
        default_org = await self.org_dao.create(db=db, obj_in=schemas.OrganizationCreate(name=org_name))

        # 3. Get or create the default 'admin' role
        admin_role = await self.role_dao.get_by_name(db, name=DefaultRoles.ADMIN)
        if not admin_role:
            # This should ideally be seeded by auth_setup.py, but handle defensively
            raise RoleNotFoundException(detail=f"Default role '{DefaultRoles.ADMIN}' not found. Please run setup.")

        # 4. Assign the user as admin in their default organization
        await self.user_dao.add_user_to_org(db=db, user=new_user, organization=default_org, role=admin_role)

        # 5. Trigger verification email using background tasks
        if not registered_by_admin:
            try:
                await email_verify.trigger_send_verification_email(
                    background_tasks=background_tasks,
                    db=db,
                    user=new_user,
                    base_url=base_url
                )
            except Exception as e:
                # Log error if triggering background task fails
                auth_logger.error(f"Failed to trigger verification email for {new_user.email}: {e}", exc_info=True)
                # Decide if registration should fail if email task cannot be added
                # For now, we continue registration but log the error.
        else:
            auth_logger.info(f"User {new_user.email} registered by admin, skipping email verification.")

        # Reload user with relationships for the response
        # (get_by_email in DAO already loads relations)
        reloaded_user = await self.user_dao.get_by_email(db, email=new_user.email)
        if not reloaded_user:
            # Should not happen, but handle defensively
             raise UserNotFoundException(detail="Failed to reload user after registration.")
        return reloaded_user

    async def authenticate_user(
        self, db: AsyncSession, *, email: str, password: str
    ) -> models.User:
        """
        Authenticates a user via email and password.
        Raises appropriate exceptions on failure.
        """
        user = await self.user_dao.authenticate(db, email=email, password=password)
        if not user:
            raise CredentialsException(detail="Incorrect email or password")
        if not user.is_active:
            raise InactiveUserException()
        # NOTE: We don't check verification here anymore, separate endpoints handle it.
        return user
    
    async def change_password(
        self, 
        db: AsyncSession, 
        *, 
        user: models.User, 
        current_password: str, 
        new_password: str
    ) -> bool:
        """
        Changes a user's password after verifying the current password.
        
        Args:
            db: Database session
            user: The user model whose password is being changed
            current_password: The user's current password for verification
            new_password: The new password to set
            
        Returns:
            bool: True if password was successfully changed
            
        Raises:
            CredentialsException: If current password verification fails
            HTTPException: If database update fails
        """
        # 1. Verify the current password
        # user = await self.user_dao.authenticate(db, email=user.email, password=current_password)
        # if not user:
        #     auth_logger.warning(f"Failed password change attempt for user {user.email}: current password verification failed")
        #     raise CredentialsException(detail="Current password is incorrect")
        
        # 2. Hash the new password
        hashed_password = security.get_password_hash(new_password)
        
        # 3. Update the user's password in the database
        try:
            # Create update schema with just the password field
            password_update = schemas.UserAdminUpdate(hashed_password=hashed_password)
            
            # Update the user record
            updated_user = await self.user_dao.update(db, db_obj=user, obj_in=password_update)
            
            # Log the successful password change
            auth_logger.info(f"Password successfully changed for user {user.email}")
            
            # 4. Optional: Revoke all refresh tokens for this user for security
            # This forces re-login on all devices after password change
            await self.refresh_token_dao.revoke_all_for_user(db, user_id=user.id)
            
            return True
            
        except Exception as e:
            # Log the error and re-raise as HTTP exception
            auth_logger.error(f"Database error during password change for user {user.email}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to update password")
    
    

    async def _create_refresh_token(self, db: AsyncSession, *, user_id: uuid.UUID) -> models.RefreshToken:
        """Creates a new refresh token, stores it, and returns the model."""
        expires_at = datetime_now_utc() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        refresh_token_obj = await self.refresh_token_dao.create_token(
            db, user_id=user_id, expires_at=expires_at
        )
        return refresh_token_obj

    async def generate_tokens_for_user(self, db: AsyncSession, user: models.User) -> Tuple[str, models.RefreshToken]:
        """
        Generates a new JWT access token and a new refresh token for a user.
        Stores the refresh token.
        Returns the access token string and the RefreshToken database object.
        """
        # Create access token
        access_token = security.create_access_token(subject=user.id)
        # Create and store refresh token
        refresh_token_obj = await self._create_refresh_token(db, user_id=user.id)

        return access_token, refresh_token_obj

    async def rotate_refresh_token(
        self, db: AsyncSession, *, old_token_uuid: uuid.UUID
    ) -> Tuple[str, models.RefreshToken]:
        """
        Validates an old refresh token, revokes it, creates new access and refresh tokens.
        Raises CredentialsException if the old token is invalid, expired, or revoked.
        Returns the new access token string and the new RefreshToken database object.
        """
        # 1. Validate old token
        old_token_obj = await self.refresh_token_dao.get_valid_token(db, token=old_token_uuid)
        if not old_token_obj:
            auth_logger.warning(f"Attempt to refresh with invalid/expired/revoked token: {old_token_uuid}")
            raise CredentialsException(detail="Invalid or expired refresh token")

        # NOTE: this is already handled in permissions, active user dependency, etc
        # # 2. Check user validity (optional but recommended)
        # user = await self.user_dao.get(db, id=old_token_obj.user_id)
        # if not user or not user.is_active:
        #      auth_logger.warning(f"Refresh token user invalid/inactive: {old_token_obj.user_id} for token {old_token_uuid}")
        #      # Revoke the potentially compromised/stale token
        #      await self.refresh_token_dao.revoke_token(db, token_obj=old_token_obj)
        #      raise CredentialsException(detail="User associated with token is invalid or inactive")

        # 3. Revoke the old token
        await self.refresh_token_dao.revoke_token(db, token_obj=old_token_obj)

        # 4. Generate new tokens
        new_access_token, new_refresh_token_obj = await self.generate_tokens_for_user(db, user=old_token_obj.user)
        auth_logger.info(f"Refresh token rotated successfully for user {old_token_obj.user.email} (Old: {old_token_uuid}, New: {new_refresh_token_obj.token})")

        return new_access_token, new_refresh_token_obj

    async def delete_user(
        self, 
        db: AsyncSession, 
        *,
        user_id: Optional[uuid.UUID] = None,
        email: Optional[str] = None,
        user: Optional[models.User] = None
    ) -> models.User:
        """
        Deletes a user from the system by either ID, email, or user object.
        
        This method will completely remove the user and all associated data from the database,
        including removing the user from all organizations they belong to.
        Exactly one of user_id, email, or user must be provided.
        
        Args:
            db: Database session
            user_id: UUID of the user to delete
            email: Email of the user to delete
            user: User object to delete
            
        Returns:
            models.User: The deleted user object
            
        Raises:
            ValueError: If no identifier or multiple identifiers are provided
            UserNotFoundException: If the user cannot be found
            HTTPException: If there's a database error during deletion
        """
        # Validate that exactly one identifier is provided
        provided_params = sum(1 for param in [user_id, email, user] if param is not None)
        
        if provided_params == 0:
            raise ValueError("At least one of user_id, email, or user must be provided")
        elif provided_params > 1:
            raise ValueError("Only one of user_id, email, or user should be provided")
        
        # Get the user object if not already provided
        db_user = user
        if not db_user:
            if user_id:
                db_user = await self.user_dao.get(db, id=user_id, load_relations=["organization_links"])
            elif email:
                db_user = await self.user_dao.get_by_email(db, email=email)
                
        # Check if user exists
        if not db_user:
            identifier = user_id or email or "provided user object"
            auth_logger.warning(f"Attempted to delete non-existent user: {identifier}")
            raise UserNotFoundException(detail=f"User not found with the provided identifier: {identifier}")
        
        try:
            # First revoke all refresh tokens for this user
            await self.refresh_token_dao.revoke_all_for_user(db, user_id=db_user.id)
            auth_logger.info(f"Revoked all refresh tokens for user {db_user.email} before deletion")
            
            # Remove user from all organizations they belong to
            if hasattr(db_user, 'organization_links') and db_user.organization_links:
                for link in db_user.organization_links:
                    await self.user_dao.remove_user_from_org(
                        db=db, 
                        user_id=db_user.id, 
                        org_id=link.organization_id
                    )
                auth_logger.info(f"Removed user {db_user.email} from all organizations")
            
            # Delete the user
            deleted_user = await self.user_dao.remove(db, id=db_user.id)
            
            if deleted_user:
                auth_logger.info(f"User '{deleted_user.email}' (ID: {deleted_user.id}) successfully deleted")
                return deleted_user
            else:
                # This should not happen if we already verified the user exists
                auth_logger.error(f"Failed to delete user {db_user.email} - delete operation returned None")
                raise HTTPException(
                    status_code=500, 
                    detail="Failed to delete user due to a database error"
                )
                
        except Exception as e:
            auth_logger.error(
                f"Database error deleting user {db_user.email}: {e}", 
                exc_info=True
            )
            # Forward the exception message
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to delete user: {str(e)}"
            )


    async def list_users(
        self, 
        db: AsyncSession, 
        *, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[models.User]:
        """
        Retrieve a list of users with pagination.
        
        This method fetches multiple user records from the database with
        pagination support. It's useful for admin interfaces or when
        displaying user listings.
        
        Args:
            db: Database session
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            
        Returns:
            List[models.User]: A list of user objects
            
        Note:
            This method uses the base get_multi method from the DAO pattern
            which handles the pagination logic.
        """
        auth_logger.info(f"Listing users with skip={skip}, limit={limit}")
        try:
            users = await self.user_dao.get_multi(db=db, skip=skip, limit=limit)
            auth_logger.debug(f"Retrieved {len(users)} users")
            return users
        except Exception as e:
            auth_logger.error(f"Error listing users: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve users: {str(e)}"
            )
    
    async def list_organizations(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100
    ) -> List[models.Organization]:
        """
        Retrieve a list of organizations with pagination.
        
        This method fetches multiple organization records from the database with
        pagination support. It's useful for admin interfaces or when
        displaying organization listings.
        
        Args:
            db: Database session
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            
        Returns:
            List[models.Organization]: A list of organization objects
            
        Note:
            This method uses the base get_multi method from the DAO pattern
            which handles the pagination logic.
        """
        auth_logger.info(f"Listing organizations with skip={skip}, limit={limit}")
        try:
            organizations = await self.org_dao.get_multi(db=db, skip=skip, limit=limit)
            auth_logger.debug(f"Retrieved {len(organizations)} organizations")
            return organizations
        except Exception as e:
            auth_logger.error(f"Error listing organizations: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve organizations: {str(e)}"
            )


    async def handle_linkedin_callback(self, db: AsyncSession, linkedin_user: schemas.LinkedInUser) -> models.User:
        """
        Handles user lookup/creation after successful LinkedIn OAuth.
        Returns the local user model.
        """
        if not linkedin_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid LinkedIn user data (missing ID)")

        user_email = linkedin_user.email
        if not user_email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Primary email not found for LinkedIn account.")

        # Check by LinkedIn ID first
        db_user = await self.user_dao.get_by_linkedin_id(db, linkedin_id=linkedin_user.id)

        if not db_user:
            # If not found by LinkedIn ID, check by email
            db_user = await self.user_dao.get_by_email(db, email=user_email)
            if db_user:
                # User exists via email, link LinkedIn ID
                if not db_user.linkedin_id:
                    await self.user_dao.update(db, db_obj=db_user, obj_in=schemas.UserAdminUpdate(linkedin_id=linkedin_user.id))
                # If linkedin_id exists but differs, potential conflict - decide strategy
            else:
                # User does not exist, create new OAuth user
                db_user = await self.user_dao.create_oauth_user(
                    db=db,
                    email=user_email,
                    full_name=linkedin_user.display_name,
                    linkedin_id=linkedin_user.id
                )
                # Create a default organization and assign admin role for new OAuth user
                org_name = f"{db_user.full_name or db_user.email.split('@')[0]}{DEFAULT_FIRST_USER_ORG_SUFFIX}"
                try:
                    default_org = await self.org_dao.create(db=db, obj_in=schemas.OrganizationCreate(name=org_name))
                    admin_role = await self.role_dao.get_by_name(db, name=DefaultRoles.ADMIN)
                    if not admin_role:
                         # Log critical error, setup script should handle this
                         auth_logger.critical(f"Default role '{DefaultRoles.ADMIN}' not found during LinkedIn signup for {user_email}")
                         raise RoleNotFoundException(detail=f"Default role '{DefaultRoles.ADMIN}' not found.")
                    await self.user_dao.add_user_to_org(db=db, user=db_user, organization=default_org, role=admin_role)
                except Exception as e:
                     # Log failure to create org/assign role, but user is already created
                     auth_logger.error(f"Failed to create default org/assign role for LinkedIn user {user_email}: {e}", exc_info=True)
                     # User creation succeeded, proceed without default org/role setup in this case?
                     # Or raise a 500 error?
                     # For now, log and continue.

        if not db_user.is_active:
            raise InactiveUserException()

        return db_user # Return the found or created user

    async def verify_user_email(self, db: AsyncSession, token: str) -> models.User:
        """
        Verifies an email using a token.
        """
        user = await email_verify.verify_email_token(db, token=token)
        if not user:
            raise InvalidTokenException(detail="Invalid or expired verification token.")

        if not user.is_verified:
            auth_logger.info(f"Verifying email for user: {user.email}")
            # Mark user as verified and clear the token
            try:
                await self.user_dao.update(db, db_obj=user, obj_in=schemas.UserAdminUpdate(is_verified=True, email_verification_token=None))
                await db.refresh(user) # Refresh needed to get updated state
            except Exception as e:
                auth_logger.error(f"DB Error marking user {user.email} as verified: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to update user verification status.")
        else:
             auth_logger.debug(f"User {user.email} email was already verified.")
        return user

    async def create_organization(self, db: AsyncSession, org_in: schemas.OrganizationCreate, creator: models.User) -> models.Organization:
        """
        Creates a new organization and assigns the creator as admin.
        """
        existing_org = await self.org_dao.get_by_name(db, name=org_in.name)
        if existing_org:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization name already exists")

        new_org = await self.org_dao.create(db=db, obj_in=org_in)

        admin_role = await self.role_dao.get_by_name(db, name=DefaultRoles.ADMIN)
        if not admin_role:
             raise RoleNotFoundException(detail=f"Default role '{DefaultRoles.ADMIN}' not found.")

        await self.user_dao.add_user_to_org(db=db, user=creator, organization=new_org, role=admin_role)

        return new_org
    async def get_organization_users(
        self, 
        db: AsyncSession, 
        org_id: uuid.UUID
    ) -> List[schemas.UserOrganizationRoleReadWithUser]:
        """
        Retrieves all users in a specific organization with their roles.
        
        This method fetches the Organization and eagerly loads its associated 
        UserOrganizationRole links, along with the related User and Role for each link.
        It uses the generic `org_dao.get` method with a specific `load_relations` strategy.

        Args:
            db: The database session
            org_id: UUID of the organization to get users for
            
        Returns:
            List[schemas.UserOrganizationRoleReadWithUser]: List of user-organization-role 
            relationships with full user, organization and role details
            
        Raises:
            OrganizationNotFoundException: If the organization doesn't exist
        """
        # 1. Fetch the Organization and eagerly load related user/role links.
        # NOTE: Assumes the relationship on Organization model to UserOrganizationRole is named 'user_links'. Verify in models.py.
        organization = await self.org_dao.get(
            db,
            id=org_id,
            load_relations=[
                (models.Organization, "user_links"),             # Load Org -> UserOrganizationRole links
                (models.UserOrganizationRole, "user_links.user"), # Load User from each link
                (models.UserOrganizationRole, "user_links.role")  # Load Role from each link
            ]
        )

        if not organization:
            auth_logger.warning(f"Attempted to get users for non-existent organization: {org_id}")
            raise OrganizationNotFoundException()

        # 2. Extract the loaded links (assuming the relationship name is correct)
        # If the relationship name is different, adjust "user_links" below.
        user_org_links: List[models.UserOrganizationRole] = getattr(organization, "user_links", [])
        if not hasattr(organization, "user_links"):
             auth_logger.error(f"Organization model does not have the expected 'user_links' relationship attribute for org {org_id}. Cannot retrieve users.")
             return [] # Or raise an error

        # 3. Transform the loaded data into the expected schema format
        result: List[schemas.UserOrganizationRoleReadWithUser] = []
        org_model_dump = organization.model_dump() # Dump org once

        for link in user_org_links:
            # Perform defensive checks to ensure the DAO loaded the required relationships.
            # If these fail, it might indicate an issue in the DAO's loading strategy or the load_relations definition.
            if not link.user:
                auth_logger.warning(f"User relationship not loaded for UserOrganizationRole link (User ID: {link.user_id}, Org ID: {link.organization_id}) despite load_relations. Skipping entry.")
                continue
            if not link.role:
                auth_logger.warning(f"Role relationship not loaded for UserOrganizationRole link (User ID: {link.user_id}, Org ID: {link.organization_id}) despite load_relations. Skipping entry.")
                continue
                
            # Create the response object with full details
            try:
                user_role_entry = schemas.UserOrganizationRoleReadWithUser(
                    user=link.user.model_dump(),
                    organization=org_model_dump, # Use the org dump from earlier
                    role=link.role.model_dump(), # Assumes Role schema includes permissions if needed
                    created_at=link.created_at
                )
                result.append(user_role_entry)
            except Exception as e:
                # Catch potential validation errors if model_dump() output doesn't match schema
                auth_logger.error(f"Schema validation failed for user {getattr(link.user, 'email', 'Unknown')} in org {organization.id}: {e}", exc_info=True)
                # Decide whether to skip or raise - skipping for now.
                continue
            
        auth_logger.debug(f"Retrieved and formatted {len(result)} users for organization {org_id} ('{organization.name}')")
        return result

    async def assign_role_to_user_in_org(
        self, db: AsyncSession, *, org_id: uuid.UUID, assignment: schemas.UserAssignRole, current_user: models.User
    ) -> schemas.UserOrganizationRoleReadWithUser:
        """
        Assigns a role to a user within an organization, checking permissions.
        """
        # 1. Check if current_user has permission to manage members in this org
        await self._check_permission(db, user=current_user, org_id=org_id, required_permission=Permissions.ORG_MANAGE_MEMBERS)

        # 2. Find target user, org, and role
        target_user = await self.user_dao.get_by_email(db, email=assignment.user_email)
        if not target_user:
             raise UserNotFoundException(detail=f"User with email {assignment.user_email} not found.")

        target_org = await self.org_dao.get(db, id=org_id)
        if not target_org:
             raise OrganizationNotFoundException()

        target_role = await self.role_dao.get_by_name(db, name=assignment.role_name)
        if not target_role:
             raise RoleNotFoundException(detail=f"Role '{assignment.role_name}' not found.")

        # 3. Perform the assignment
        try:
            link = await self.user_dao.add_user_to_org(db=db, user=target_user, organization=target_org, role=target_role)
            auth_logger.info(f"Assigned role '{target_role.name}' to user '{target_user.email}' in organization '{target_org.name}'")
        except Exception as e:
            auth_logger.error(f"DB error assigning role: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Database error assigning role.")
        
        # 4. Return the link with details for response
        return schemas.UserOrganizationRoleReadWithUser(
            user=target_user.model_dump(),
            organization=target_org.model_dump(),
            role=target_role.model_dump(),
            created_at=link.created_at
        )
        
        # # 4. Reload link with details for response (DAO methods should handle loading)
        # reloaded_link = await self.user_dao.get_user_org_role(db, user_id=target_user.id, org_id=target_org.id)
        # if not reloaded_link:
        #      raise HTTPException(status_code=500, detail="Failed to retrieve assignment details after creation")
        # return reloaded_link
    
    async def delete_organization(
        self, 
        db: AsyncSession, 
        *, 
        org_id: uuid.UUID, 
        current_user: models.User
    ) -> None:
        """
        Deletes an organization after verifying the user has appropriate permissions.
        
        This method checks if the current user has the ORG_DELETE permission within the
        organization, then proceeds to delete the organization and all associated data.
        
        Args:
            db: Database session
            org_id: UUID of the organization to delete
            current_user: The user requesting the deletion
            
        Returns:
            None
            
        Raises:
            OrganizationNotFoundException: If the organization doesn't exist
            PermissionDeniedException: If the user lacks the required permission
            HTTPException: If there's a database error during deletion
        """
        # 1. Check if organization exists
        # target_org = await self.org_dao.get(db, id=org_id)
        # if not target_org:
        #     auth_logger.warning(f"Attempted to delete non-existent organization: {org_id}")
        #     raise OrganizationNotFoundException()
        
        # 3. Perform the deletion
        try:
            # The DAO should handle cascading deletions of related records
            # (user-org links, org-specific data, etc.)
            deleted = await self.org_dao.remove(db, id=org_id)
            
            if deleted:
                auth_logger.info(
                    f"Organization '{deleted.name}' (ID: {org_id}) deleted by user '{current_user.email}'"
                )
            else:
                # This should not happen if we already verified the org exists
                auth_logger.error(
                    f"Failed to delete organization {org_id} - delete operation returned False"
                )
                raise HTTPException(
                    status_code=500, 
                    detail="Failed to delete organization due to a database error"
                )
                
        except Exception as e:
            auth_logger.error(
                f"Database error deleting organization {org_id}: {e}", 
                exc_info=True
            )
            raise HTTPException(
                status_code=500, 
                detail="Failed to delete organization due to a database error"
            )

    async def remove_user_from_organization(
        self, db: AsyncSession, *, removal: schemas.UserRemoveRole, current_user: models.User
    ) -> None:
        """
        Removes a user from an organization, checking permissions.
        """
        # 1. Check permission
        await self._check_permission(db, user=current_user, org_id=removal.organization_id, required_permission=Permissions.ORG_MANAGE_MEMBERS)

        # 2. Find target user and org
        target_user = await self.user_dao.get_by_email(db, email=removal.user_email)
        if not target_user:
             raise UserNotFoundException(detail=f"User with email {removal.user_email} not found.")
        target_org = await self.org_dao.get(db, id=removal.organization_id)
        if not target_org:
             raise OrganizationNotFoundException()

        # Prevent removing self? Or last admin? Add specific business logic if needed.
        if target_user.id == current_user.id:
            # Add logic here to check if they are the last admin etc.
            # raise HTTPException(status_code=400, detail="Cannot remove yourself from the organization via this endpoint.")
            pass # Allow removing self for now

        # 3. Perform removal
        try:
            deleted = await self.user_dao.remove_user_from_org(db=db, user_id=target_user.id, org_id=target_org.id)
            if deleted:
                auth_logger.info(f"Removed user '{target_user.email}' from organization '{target_org.name}'")
            else:
                # This might mean the user wasn't in the org to begin with
                auth_logger.warning(f"Attempted to remove user {target_user.email} from org {target_org.id}, but they were not found (or deletion failed).",)
        except Exception as e:
            auth_logger.error(f"DB error removing user from org: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Database error removing user from organization.")

    async def _check_permission(self, db: AsyncSession, user: models.User, org_id: uuid.UUID, required_permission: Permissions) -> None:
        """
        Helper to check if a user has a specific permission within an organization.
        Raises PermissionDeniedException if permission is not granted.
        """
        if user.is_superuser:
            return # Superusers bypass org-specific checks

        link = await self.user_dao.get_user_org_role(db, user_id=user.id, org_id=org_id)
        if not link or not link.role or not link.role.permissions:
            raise PermissionDeniedException(detail="User does not belong to this organization or has no role/permissions assigned.")

        user_permissions_in_org = {perm.name for perm in link.role.permissions}

        if required_permission.value not in user_permissions_in_org:
             raise PermissionDeniedException(detail=f"Missing required permission: {required_permission.value}")

    # --- Password Reset Logic ---

    async def request_password_reset(self, db: AsyncSession, email: str, background_tasks: BackgroundTasks, base_url: str):
        """
        Finds user by email and triggers the password reset email.
        Does not reveal if the email exists.
        """
        user = await self.user_dao.get_by_email(db, email=email)
        if user:
            # User found, trigger the email (which runs in background)
            # The base_url here might be the API base, but the link generated
            # inside trigger_send_password_reset_email uses FRONTEND_URL setting.
            await email_verify.trigger_send_password_reset_email(
                background_tasks=background_tasks,
                user=user,
                base_url=base_url # Base URL passed for consistency, but might not be used directly for link
            )
            auth_logger.info(f"Password reset requested for email: {email}")
        else:
            # User not found, log but don't inform the requester
            auth_logger.info(f"Password reset requested for non-existent email: {email}")
        # Always return a generic success response to prevent email enumeration
        return {"message": "If an account with this email exists, a password reset link will be sent."}

    async def reset_password_with_token(self, db: AsyncSession, token: str, new_password: str) -> bool:
        """
        Resets the user's password using a valid password reset token.

        Args:
            db: Database session.
            token: The password reset JWT.
            new_password: The new password to set.

        Returns:
            True if password was successfully reset.

        Raises:
            CredentialsException: If the token is invalid or expired.
            UserNotFoundException: If the user associated with the token doesn't exist.
            HTTPException: If there's a database error during update.
        """
        # 1. Verify the token (checks expiry, signature, and password_reset claim)
        try:
            token_data = await email_verify.verify_password_reset_token(token)
        except CredentialsException as e:
            # Re-raise specific token validation errors
            raise e

        # 2. Find the user associated with the token
        user = await self.user_dao.get(db, id=token_data.sub)
        if not user:
            # Should not happen if token was valid, but handle defensively
            auth_logger.error(f"Password reset token valid for user {token_data.sub}, but user not found.")
            raise UserNotFoundException(detail="User associated with reset token not found.")

        # 3. Hash the new password
        hashed_password = security.get_password_hash(new_password)

        # 4. Update the user's password in the database
        try:
            password_update = schemas.UserAdminUpdate(hashed_password=hashed_password)
            await self.user_dao.update(db, db_obj=user, obj_in=password_update)
            auth_logger.info(f"Password successfully reset via token for user {user.email}")

            # 5. Revoke all refresh tokens for this user for security
            await self.refresh_token_dao.revoke_all_for_user(db, user_id=user.id)
            auth_logger.info(f"Revoked all refresh tokens for user {user.email} after password reset.")

            return True

        except Exception as e:
            auth_logger.error(f"Database error during password reset for user {user.email}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to reset password due to a database error.")

    async def invalidate_refresh_token(self, db: AsyncSession, token_uuid: uuid.UUID) -> bool:
        """
        Invalidates a specific refresh token by marking it as revoked.
        
        Args:
            db: Database session
            token_uuid: UUID of the refresh token to invalidate
            
        Returns:
            bool: True if token was successfully invalidated, False if token not found/already revoked
            
        Raises:
            HTTPException: If there's a database error during update
        """
        try:
            # Find the token
            token_obj = await self.refresh_token_dao.get_valid_token(db, token=token_uuid)
            
            # If token exists and is valid, revoke it
            if token_obj:
                await self.refresh_token_dao.revoke_token(db, token_obj=token_obj)
                auth_logger.info(f"Refresh token {token_uuid} invalidated for user {token_obj.user.email}")
                return True
            else:
                # Token not found or already invalid - this is not an error
                auth_logger.debug(f"Attempted to invalidate non-existent or already invalid token: {token_uuid}")
                return False
                
        except Exception as e:
            auth_logger.error(f"Database error invalidating refresh token {token_uuid}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Failed to invalidate refresh token due to a database error"
            )

    async def update_organization(
        self,
        db: AsyncSession,
        *,
        org_id: uuid.UUID,
        org_update: schemas.OrganizationUpdate,
        current_user: models.User
    ) -> models.Organization:
        """
        Updates an organization's details after verifying permissions.
        
        This method checks if the current user has the ORG_UPDATE permission within the
        organization, then updates the organization details.
        
        Args:
            db: Database session
            org_id: UUID of the organization to update
            org_update: Schema containing the fields to update
            current_user: The user requesting the update
            
        Returns:
            models.Organization: The updated organization
            
        Raises:
            OrganizationNotFoundException: If the organization doesn't exist
            PermissionDeniedException: If the user lacks the required permission
            HTTPException: If there's a database error during update
        """
        # 1. Check if organization exists
        target_org = await self.org_dao.get(db, id=org_id)
        if not target_org:
            auth_logger.warning(f"Attempted to update non-existent organization: {org_id}")
            raise OrganizationNotFoundException()
        
        # # 2. Check if user has permission to update the organization
        # await self._check_permission(db, user=current_user, org_id=org_id, required_permission=Permissions.ORG_UPDATE)
        
        # 3. Perform the update
        try:
            # Update the organization with the provided data
            updated_org = await self.org_dao.update(db, db_obj=target_org, obj_in=org_update)
            
            auth_logger.info(
                f"Organization '{updated_org.name}' (ID: {org_id}) updated by user '{current_user.email}'"
            )
            return updated_org
                
        except Exception as e:
            auth_logger.error(
                f"Database error updating organization {org_id}: {e}", 
                exc_info=True
            )
            raise HTTPException(
                status_code=500, 
                detail="Failed to update organization due to a database error"
            )

# Instantiate service for use in routers/dependencies
# auth_service = AuthService() 
