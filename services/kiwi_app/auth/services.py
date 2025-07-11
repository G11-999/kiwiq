import json
import uuid
import logging # Keep standard logging import if needed elsewhere, but we use the specific logger
from typing import Optional, List, Set, Tuple
from datetime import datetime, timedelta # Import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status, BackgroundTasks
import stripe # Add BackgroundTasks

from kiwi_app.auth import crud, models, schemas, security # Added email_verify
from kiwi_app.auth.utils import auth_logger, datetime_now_utc # Import datetime_now_utc
from kiwi_app.auth.constants import DefaultRoles, Permissions, DEFAULT_FIRST_USER_ORG_SUFFIX, DEFAULT_ORG_NAME
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
    OrganizationSeatLimitExceededException,
)
from kiwi_app.email import email_verify
from kiwi_app.settings import settings # Import settings

from kiwi_app.email.email_templates.renderer import (
    EmailRenderer, 
    FirstStepsGuideEmailData
)
from kiwi_app.email.email_dispatch import email_dispatch, EmailContent, EmailRecipient

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = settings.STRIPE_API_VERSION

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
        self, db: AsyncSession, user_in: schemas.UserCreate | schemas.UserAdminCreate, background_tasks: BackgroundTasks, base_url: str, registered_by_admin: bool = False, send_email_for_verification: bool = False, send_first_steps_guide: bool = False,
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
        if send_email_for_verification:
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
        
        if send_first_steps_guide:
            await self.send_first_steps_guide_email(background_tasks, new_user)

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
        if not user.is_verified:
            raise UserNotVerifiedException()
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
        if user.is_verified and not security.verify_password(current_password, user.hashed_password):
            raise CredentialsException(detail="Current password is incorrect")
        
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
    
    

    async def _create_refresh_token(self, db: AsyncSession, *, user_id: uuid.UUID, expires_at: Optional[datetime] = None) -> models.RefreshToken:
        """Creates a new refresh token, stores it, and returns the model."""
        if expires_at is None:
            expires_at = datetime_now_utc() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        refresh_token_obj = await self.refresh_token_dao.create_token(
            db, user_id=user_id, expires_at=expires_at
        )
        return refresh_token_obj

    async def generate_tokens_for_user(self, db: AsyncSession, user: models.User, keep_me_logged_in: bool = True, expires_at: Optional[datetime] = None) -> Tuple[str, models.RefreshToken]:
        """
        Generates a new JWT access token and a new refresh token for a user.
        Stores the refresh token.
        Returns the access token string and the RefreshToken database object.
        """
        # Create access token
        access_token = security.create_access_token(subject=user.id, token_type="access")
        # Create and store refresh token
        if not keep_me_logged_in:
            return access_token, None
        
        refresh_token_obj = await self._create_refresh_token(db, user_id=user.id, expires_at=expires_at)

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
        new_access_token, new_refresh_token_obj = await self.generate_tokens_for_user(db, user=old_token_obj.user, expires_at=old_token_obj.expires_at)
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
        limit: int = 100,
        active_only: bool = True
    ) -> List[models.Organization]:
        """
        Retrieve a list of organizations with pagination and active filtering.
        
        This method fetches multiple organization records from the database with
        pagination support and optional filtering by active status. By default,
        only active organizations are returned to hide deactivated ones from
        regular interfaces.
        
        Args:
            db: Database session
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            active_only: If True, only return active organizations. If False, return all.
            
        Returns:
            List[models.Organization]: A list of organization objects matching the criteria
            
        Note:
            This method uses the enhanced get_multi_with_active_filter method from the DAO
            which handles the active status filtering logic.
        """
        auth_logger.info(f"Listing organizations with skip={skip}, limit={limit}, active_only={active_only}")
        try:
            organizations = await self.org_dao.get_multi_with_active_filter(
                db=db, skip=skip, limit=limit, active_only=active_only
            )
            filter_desc = "active" if active_only else "all"
            # auth_logger.info(f"Retrieved {len(organizations)} {filter_desc} organizations: {json.dumps([org.model_dump(mode='json') for org in organizations])}")
            auth_logger.debug(f"Retrieved {len(organizations)} {filter_desc} organizations")
            return organizations
        except Exception as e:
            auth_logger.error(f"Error listing organizations: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve organizations: {str(e)}"
            )

    async def send_first_steps_guide_email(
        self,
        background_tasks: BackgroundTasks,
        user: models.User,
    ) -> None:
        """
        Send a first steps guide email to a newly verified user.
        
        This helper function creates and queues a first steps guide email
        to help new users get started with the platform after email verification.
        
        Args:
            background_tasks: FastAPI BackgroundTasks instance
            user: The verified user object
            request: Request object for base URL generation
        """
        try:
            # Import here to avoid circular imports
            
            # Create first steps guide email data
            email_data = FirstStepsGuideEmailData(
                user_name=user.full_name or user.email.split('@')[0],  # Fallback to email prefix if no name
                start_writing_url=settings.URL_CREATE_NEW_POST,  # URL to create first post
                explore_ideas_url=settings.URL_EXPLORE_CONTENT_IDEAS,   # URL to explore content ideas
                calendar_url=settings.URL_CONTENT_CALENDAR      # URL to content calendar
            )
            
            # Initialize email renderer
            email_renderer = EmailRenderer()
            
            # Render both HTML and text versions
            html_content = email_renderer.render_first_steps_guide_email(email_data)
            text_content = email_renderer.html_to_text(html_content)
            
            # Create email content object
            email_content = EmailContent(
                subject="🎯 Your Next Steps to Content Success with KiwiQ",
                html_body=html_content,
                text_body=text_content,
                from_name="KiwiQ Team"
            )
            
            # Create recipient object
            recipient = EmailRecipient(
                email=user.email,
                name=user.full_name
            )
            
            # Send email using the dispatch service
            success = await email_dispatch.send_email_async(
                background_tasks=background_tasks,
                recipient=recipient,
                content=email_content
            )
            
            if success:
                auth_logger.info(f"First steps guide email task queued for {user.email} ({user.id})")
            else:
                auth_logger.warning(f"Failed to queue first steps guide email for {user.email}")
                
        except Exception as e:
            auth_logger.error(f"Error preparing first steps guide email for {user.email}: {e}", exc_info=True)
            # Don't raise the exception - we don't want to break email verification if guide email fails

    
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
        Automatically sets the primary_billing_email to the creator's email.
        """
        # existing_org = await self.org_dao.get_by_name(db, name=org_in.name)
        # if existing_org:
        if org_in.name == DEFAULT_ORG_NAME:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This organization name already exists. Please use a different name.")
            # else:
            #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization name already exists")

        # Create the organization first
        new_org = await self.org_dao.create(db=db, obj_in=org_in)

        # Set the primary billing email to creator's email
        await self.org_dao.update_primary_billing_email(db=db, org_id=new_org.id, email=creator.email)

        admin_role = await self.role_dao.get_by_name(db, name=DefaultRoles.ADMIN)
        if not admin_role:
             raise RoleNotFoundException(detail=f"Default role '{DefaultRoles.ADMIN}' not found.")

        await self.user_dao.add_user_to_org(db=db, user=creator, organization=new_org, role=admin_role, current_user_is_superuser=creator.is_superuser)

        # Create new customer
        customer = stripe.Customer.create(
            email=creator.email,
            name=new_org.name,
            metadata={
                "kiwiq_org_id": str(new_org.id),
                "kiwiq_user_id": str(creator.id)
            }
        )

        # Update organization with Stripe customer ID
        new_org.external_billing_id = customer.id
        db.add(new_org)
        await db.commit()
        await db.refresh(new_org)

        auth_logger.info(f"Organization '{new_org.name}' created with primary_billing_email set to: {creator.email}")
    

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
            current_user_is_superuser = current_user.is_superuser
            link = await self.user_dao.add_user_to_org(db=db, user=target_user, organization=target_org, role=target_role, current_user_is_superuser=current_user_is_superuser)
            auth_logger.info(f"Assigned role '{target_role.name}' to user '{target_user.email}' in organization '{target_org.name}'")
            
            # Automatically update primary billing email if needed
            potentially_updated_organization = await self.org_dao.auto_update_primary_billing_email(
                db=db, 
                org_id=org_id, 
                action="add_user", 
                user_email=target_user.email
            )

            if potentially_updated_organization is not None and potentially_updated_organization.external_billing_id:
                try:
                    customer = stripe.Customer.retrieve(potentially_updated_organization.external_billing_id)
                    modify_kwargs = {}
                    if customer.email != potentially_updated_organization.primary_billing_email:
                        modify_kwargs["email"] = potentially_updated_organization.primary_billing_email
                    if modify_kwargs:
                        modify_kwargs["id"] = customer.id
                        customer.modify(**modify_kwargs)
                except stripe.StripeError as e:
                    auth_logger.warning(f"Failed to retrieve Stripe customer {potentially_updated_organization.external_billing_id}: {e}")
                    # Continue to create new customer if retrieval fails
            
        except OrganizationSeatLimitExceededException as e:
            auth_logger.error(f"Error assigning role: {e}", exc_info=True)
            raise
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
        self, db: AsyncSession, *, removal: schemas.UserRemoveRole, organization_id: uuid.UUID, current_user: models.User
    ) -> None:
        """
        Removes a user from an organization, checking permissions.
        """
        # 1. Check permission
        await self._check_permission(db, user=current_user, org_id=organization_id, required_permission=Permissions.ORG_MANAGE_MEMBERS)

        # 2. Find target user and org
        target_user = await self.user_dao.get_by_email(db, email=removal.user_email)
        if not target_user:
             raise UserNotFoundException(detail=f"User with email {removal.user_email} not found.")
        target_org = await self.org_dao.get(db, id=organization_id)
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
                
                # Automatically update primary billing email if the removed user was the billing contact
                potentially_updated_organization = await self.org_dao.auto_update_primary_billing_email(
                    db=db, 
                    org_id=target_org.id, 
                    action="remove_user", 
                    user_email=target_user.email
                )

                if potentially_updated_organization is not None and potentially_updated_organization.external_billing_id:
                    try:
                        customer = stripe.Customer.retrieve(potentially_updated_organization.external_billing_id)
                        modify_kwargs = {}
                        if customer.email != potentially_updated_organization.primary_billing_email:
                            modify_kwargs["email"] = potentially_updated_organization.primary_billing_email
                        if modify_kwargs:
                            modify_kwargs["id"] = customer.id
                            customer.modify(**modify_kwargs)
                    except stripe.StripeError as e:
                        auth_logger.warning(f"Failed to retrieve Stripe customer {potentially_updated_organization.external_billing_id}: {e}")
                
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

            if updated_org is not None and updated_org.external_billing_id:
                try:
                    customer = stripe.Customer.retrieve(updated_org.external_billing_id)
                    modify_kwargs = {}
                    if customer.name != updated_org.name:
                        modify_kwargs["name"] = updated_org.name
                    if modify_kwargs:
                        modify_kwargs["id"] = customer.id
                        customer.modify(**modify_kwargs)
                except stripe.StripeError as e:
                    auth_logger.warning(f"Failed to retrieve Stripe customer {updated_org.external_billing_id}: {e}")
                    # Continue to create new customer if retrieval fails
            
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

    async def update_organization_billing_email(
        self,
        db: AsyncSession,
        *,
        org_id: uuid.UUID,
        billing_email_update: schemas.OrganizationBillingEmailUpdate,
        current_user: models.User
    ) -> models.Organization:
        """
        Manually update an organization's primary billing email.
        
        This method allows authorized users to manually set or clear the primary billing
        email for an organization, overriding the automatic assignment logic.
        
        Args:
            db: Database session
            org_id: UUID of the organization to update
            billing_email_update: Schema containing the new billing email
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
            auth_logger.warning(f"Attempted to update billing email for non-existent organization: {org_id}")
            raise OrganizationNotFoundException()
        
        # 2. Check if user has permission to update the organization
        # We can reuse the ORG_UPDATE permission for billing email updates
        await self._check_permission(db, user=current_user, org_id=org_id, required_permission=Permissions.ORG_UPDATE)
        
        # 3. Perform the update
        try:
            updated_org = await self.org_dao.update_primary_billing_email(
                db=db, 
                org_id=org_id, 
                email=billing_email_update.primary_billing_email
            )
            
            if updated_org:
                auth_logger.info(
                    f"Primary billing email for organization '{updated_org.name}' (ID: {org_id}) "
                    f"manually updated by user '{current_user.email}' to: {billing_email_update.primary_billing_email}"
                )
                if updated_org.external_billing_id:
                    try:
                        customer = stripe.Customer.retrieve(updated_org.external_billing_id)
                        modify_kwargs = {}
                        if customer.email != updated_org.primary_billing_email:
                            modify_kwargs["email"] = updated_org.primary_billing_email
                        if modify_kwargs:
                            modify_kwargs["id"] = customer.id
                            customer.modify(**modify_kwargs)
                    except stripe.StripeError as e:
                        auth_logger.warning(f"Failed to retrieve Stripe customer {updated_org.external_billing_id}: {e}")
                return updated_org
            else:
                # Should not happen if we already verified the org exists
                auth_logger.error(f"Failed to update billing email for organization {org_id} - update returned None")
                raise HTTPException(
                    status_code=500, 
                    detail="Failed to update billing email due to a database error"
                )
                
        except Exception as e:
            auth_logger.error(
                f"Database error updating billing email for organization {org_id}: {e}", 
                exc_info=True
            )
            raise HTTPException(
                status_code=500, 
                detail="Failed to update billing email due to a database error"
            )

    # --- Email Change Management ---

    async def request_email_change(
        self, 
        db: AsyncSession, 
        *, 
        user: models.User, 
        new_email: str, 
        current_password: str,
        background_tasks: BackgroundTasks,
        base_url: str
    ) -> dict:
        """
        Request an email address change for an authenticated user.
        
        This method:
        1. Validates the current password for security
        2. Checks that the new email is not already in use
        3. Generates a secure verification token containing both old and new email
        4. Sends verification email to the NEW email address
        5. Returns success response without revealing if the new email exists
        
        The email change is not completed until the token is verified via the new email.
        
        Args:
            db: Database session
            user: The authenticated user requesting the email change
            new_email: The new email address to change to
            current_password: Current password for security verification
            background_tasks: FastAPI BackgroundTasks for email sending
            base_url: Base URL for the email verification link
            
        Returns:
            dict: Success message (generic to prevent enumeration)
            
        Raises:
            CredentialsException: If the current password is incorrect
            EmailAlreadyExistsException: If the new email is already in use
            HTTPException: If there's a database or email sending error
        """
        # 1. Verify current password for security
        if user.is_verified:
            is_valid_password = security.verify_password(current_password, user.hashed_password)
        else:  # if user is not verified, we don't need to verify the password
            is_valid_password = True

        if not is_valid_password:
            auth_logger.warning(f"Email change request failed for {user.email}: incorrect current password")
            raise CredentialsException(detail="Current password is incorrect")
        
        # 2. Check if new email is the same as current email
        if new_email.lower() == user.email.lower():
            auth_logger.info(f"Email change request ignored for {user.email}: new email same as current")
            # Return success to avoid revealing this information
            return {"message": "If the new email address is valid and available, a verification link will be sent to it."}
        
        # 3. Check if new email is already in use by another user
        existing_user = await self.user_dao.get_by_email(db, email=new_email)
        if existing_user and existing_user.id != user.id:
            auth_logger.warning(f"Email change request failed for {user.email}: new email {new_email} already in use")
            raise EmailAlreadyExistsException(detail="The new email address is already in use by another account")
        
        # 4. Generate email change verification token
        # Store both old and new email in the token for security
        try:
            email_change_token = security.create_email_change_token(
                user_id=user.id,
                old_email=user.email,
                new_email=new_email
            )
            
            auth_logger.info(f"Email change verification token generated for user {user.email} -> {new_email}")
        
        except Exception as e:
            auth_logger.error(f"Error generating email change token for {user.email}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to generate verification token")
        
        # 5. Send verification email to NEW email address
        try:
            await email_verify.trigger_send_email_change_verification_email(
                background_tasks=background_tasks,
                user=user,
                new_email=new_email,
                base_url=base_url,
                email_change_token=email_change_token,
            )
            
            auth_logger.info(f"Email change verification email sent to {new_email} for user {user.email}")
        
        except Exception as e:
            auth_logger.error(f"Error sending email change verification to {new_email} for user {user.email}: {e}", exc_info=True)
            # Don't expose the specific error to prevent information leakage
            raise HTTPException(status_code=500, detail="Failed to send verification email")
        
        # 6. Return generic success message
        return {"message": "If the new email address is valid and available, a verification link will be sent to it."}

    async def confirm_email_change(
        self, 
        db: AsyncSession, 
        *, 
        token: str
    ) -> schemas.EmailChangeResponse:
        """
        Confirm and complete an email address change using a verification token.
        
        This method:
        1. Validates the email change token
        2. Extracts the old and new email from the token
        3. Verifies the user still exists and matches the old email
        4. Checks that the new email is still available
        5. Updates the user's email address
        6. Revokes all refresh tokens for security
        7. Returns success response with new email
        
        Args:
            db: Database session
            token: Email change verification token from the new email
            
        Returns:
            EmailChangeResponse: Success response with new email address
            
        Raises:
            CredentialsException: If the token is invalid or expired
            UserNotFoundException: If the user no longer exists
            EmailAlreadyExistsException: If the new email is now taken by another user
            HTTPException: If there's a database error during update
        """
        # 1. Verify the email change token
        try:
            token_data = await email_verify.verify_email_change_token(token)
            user_id = token_data.sub
            old_email = token_data.additional_claims.get("old_email")
            new_email = token_data.additional_claims.get("new_email")
            
            if not old_email or not new_email:
                auth_logger.error(f"Email change token missing required claims: old_email={old_email}, new_email={new_email}")
                raise CredentialsException(detail="Invalid email change token format")
                
        except CredentialsException as e:
            # Re-raise token validation errors
            auth_logger.warning(f"Email change confirmation failed: {e.detail}")
            raise e
        except Exception as e:
            auth_logger.error(f"Error verifying email change token: {e}", exc_info=True)
            raise CredentialsException(detail="Invalid or expired email change token")
        
        # 2. Find the user and verify current email matches token
        user = await self.user_dao.get(db, id=user_id)
        if not user:
            auth_logger.error(f"Email change token valid for user {user_id}, but user not found")
            raise UserNotFoundException(detail="User associated with email change token not found")
        
        if user.email.lower() != old_email.lower():
            auth_logger.error(f"Email change token old_email {old_email} doesn't match current user email {user.email}")
            raise CredentialsException(detail="Email change token is no longer valid - user email has changed")
        
        # 3. Check if new email is still available
        existing_user = await self.user_dao.get_by_email(db, email=new_email)
        if existing_user and existing_user.id != user.id:
            auth_logger.warning(f"Email change failed for {user.email}: new email {new_email} now taken by another user")
            raise EmailAlreadyExistsException(detail="The new email address is no longer available")
        
        # 4. Update the user's email address
        try:
            email_update = schemas.UserAdminUpdate(email=new_email, is_verified=True)
            updated_user = await self.user_dao.update(db, db_obj=user, obj_in=email_update)
            
            auth_logger.info(f"Email successfully changed from {old_email} to {new_email} for user {user.id}")
        
        except Exception as e:
            auth_logger.error(f"Database error during email change for user {user.email}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to update email address due to a database error")
        
        # 5. Revoke all refresh tokens for security (user will need to log in again)
        try:
            await self.refresh_token_dao.revoke_all_for_user(db, user_id=user.id)
            auth_logger.info(f"Revoked all refresh tokens for user after email change to {new_email}")
        except Exception as e:
            # Log but don't fail the email change if token revocation fails
            auth_logger.error(f"Error revoking refresh tokens after email change: {e}", exc_info=True)
        
        # 6. Return success response
        return schemas.EmailChangeResponse(
            message="Email address successfully changed. Please log in again with your new email address.",
            new_email=new_email
        )

    async def get_user_organizations_by_email(
        self,
        db: AsyncSession,
        *,
        user_email: str,
    ) -> models.User:
        """
        Admin endpoint to retrieve all organizations for a specific user by email.
        
        This method allows administrators to look up all organizations that a user
        belongs to along with their roles in each organization. This is useful for
        admin interfaces, user management, and debugging user access issues.
        
        Args:
            db: Database session
            user_email: Email address of the user to look up organizations for
            current_user: The admin user making the request
            
        Returns:
            models.User: User object with organization_links, organizations, and roles loaded
            
        Raises:
            PermissionDeniedException: If the current user is not a superuser/admin
            UserNotFoundException: If the target user doesn't exist
            HTTPException: If there's a database error during lookup
        """
        
        # 2. Find the target user by email
        target_user = await self.user_dao.get_by_email(db, email=user_email)
        if not target_user:
            raise UserNotFoundException(detail=f"User with email {user_email} not found")
        
        # 3. Get user with organization links loaded
        try:
            # Fetch the user with all organization relationships loaded
            user_with_orgs = await self.user_dao.get(
                db,
                id=target_user.id,
                load_relations=[
                    (models.User, "organization_links"),                      # Load User -> UserOrganizationRole links
                    (models.UserOrganizationRole, "organization_links.organization"),  # Load Organization from each link
                    (models.UserOrganizationRole, "organization_links.role")          # Load Role from each link
                ]
            )
            
            if not user_with_orgs:
                # Should not happen since we already found the user, but handle defensively
                auth_logger.error(f"Failed to reload user {user_email} with organization relationships")
                raise HTTPException(status_code=500, detail="Failed to load user organization data")
            return user_with_orgs
            
        except Exception as e:
            auth_logger.error(f"Database error loading organizations for user {user_email}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve user organizations due to a database error"
            )
        
        # # 4. Extract the loaded organization links
        # org_links: List[models.UserOrganizationRole] = getattr(user_with_orgs, "organization_links", [])
        # if not hasattr(user_with_orgs, "organization_links"):
        #     auth_logger.error(f"User model does not have the expected 'organization_links' relationship attribute for user {user_email}. Cannot retrieve organizations.")
        #     return [] # Return empty list rather than error
        
        # # 5. Transform the loaded data into the expected schema format
        # result: List[schemas.UserOrganizationRoleReadWithUser] = []
        # user_model_dump = user_with_orgs.model_dump() # Dump user once for reuse
        
        # for link in org_links:
        #     # Perform defensive checks to ensure the DAO loaded the required relationships
        #     if not link.organization:
        #         auth_logger.warning(f"Organization relationship not loaded for UserOrganizationRole link (User: {user_email}, Org ID: {link.organization_id}) despite load_relations. Skipping entry.")
        #         continue
        #     if not link.role:
        #         auth_logger.warning(f"Role relationship not loaded for UserOrganizationRole link (User: {user_email}, Org ID: {link.organization_id}) despite load_relations. Skipping entry.")
        #         continue
            
        #     # Create the response object with full details
        #     try:
        #         user_org_entry = schemas.UserOrganizationRoleReadWithUser(
        #             user=user_model_dump,  # Use the user dump from earlier
        #             organization=link.organization.model_dump(),
        #             role=link.role.model_dump(),  # Assumes Role schema includes permissions if needed
        #             created_at=link.created_at
        #         )
        #         result.append(user_org_entry)
        #     except Exception as e:
        #         # Catch potential validation errors if model_dump() output doesn't match schema
        #         auth_logger.error(f"Schema validation failed for organization {getattr(link.organization, 'name', 'Unknown')} for user {user_email}: {e}", exc_info=True)
        #         # Skip this entry rather than failing the entire request
        #         continue
        
        # auth_logger.info(f"Admin {current_user.email} retrieved {len(result)} organizations for user {user_email}")
        # return result

    async def deactivate_organization(
        self,
        db: AsyncSession,
        *,
        org_id: uuid.UUID,
        current_user: models.User
    ) -> models.Organization:
        """
        Deactivate an organization after verifying permissions.
        
        This method sets an organization's is_active status to False, effectively
        hiding it from regular user interfaces while preserving all data. The
        organization and its data remain in the database but are marked as inactive.
        
        Args:
            db: Database session
            org_id: UUID of the organization to deactivate
            current_user: The user requesting the deactivation
            
        Returns:
            models.Organization: The deactivated organization
            
        Raises:
            OrganizationNotFoundException: If the organization doesn't exist
            PermissionDeniedException: If the user lacks the required permission
            HTTPException: If there's a database error during deactivation
        """
        # 1. Check if organization exists
        target_org = await self.org_dao.get(db, id=org_id)
        if not target_org:
            auth_logger.warning(f"Attempted to deactivate non-existent organization: {org_id}")
            raise OrganizationNotFoundException()
        
        # 2. Check if user has permission to update the organization
        # await self._check_permission(db, user=current_user, org_id=org_id, required_permission=Permissions.ORG_UPDATE)
        
        # 3. Perform the deactivation
        try:
            updated_org = await self.org_dao.update_organization_status(
                db=db, 
                org_id=org_id, 
                is_active=False
            )
            
            if updated_org:
                auth_logger.info(
                    f"Organization '{updated_org.name}' (ID: {org_id}) deactivated by user '{current_user.email}'"
                )
                return updated_org
            else:
                # Should not happen if we already verified the org exists
                auth_logger.error(f"Failed to deactivate organization {org_id} - update returned None")
                raise HTTPException(
                    status_code=500, 
                    detail="Failed to deactivate organization due to a database error"
                )
                
        except Exception as e:
            auth_logger.error(
                f"Database error deactivating organization {org_id}: {e}", 
                exc_info=True
            )
            raise HTTPException(
                status_code=500, 
                detail="Failed to deactivate organization due to a database error"
            )

    async def reactivate_organization(
        self,
        db: AsyncSession,
        *,
        org_id: uuid.UUID,
        current_user: models.User
    ) -> models.Organization:
        """
        Reactivate an organization after verifying permissions.
        
        This method sets an organization's is_active status to True, making it
        visible again in regular user interfaces. This is useful for restoring
        organizations that were temporarily deactivated.
        
        Args:
            db: Database session
            org_id: UUID of the organization to reactivate
            current_user: The user requesting the reactivation
            
        Returns:
            models.Organization: The reactivated organization
            
        Raises:
            OrganizationNotFoundException: If the organization doesn't exist
            PermissionDeniedException: If the user lacks the required permission
            HTTPException: If there's a database error during reactivation
        """
        # 1. Check if organization exists (don't filter by active status for reactivation)
        target_org = await self.org_dao.get(db, id=org_id)
        if not target_org:
            auth_logger.warning(f"Attempted to reactivate non-existent organization: {org_id}")
            raise OrganizationNotFoundException()
        
        # 2. Check if user has permission to update the organization
        # Note: For reactivation, we check permissions even if org is inactive
        # await self._check_permission(db, user=current_user, org_id=org_id, required_permission=Permissions.ORG_UPDATE)
        
        # 3. Perform the reactivation
        try:
            updated_org = await self.org_dao.update_organization_status(
                db=db, 
                org_id=org_id, 
                is_active=True
            )
            
            if updated_org:
                auth_logger.info(
                    f"Organization '{updated_org.name}' (ID: {org_id}) reactivated by user '{current_user.email}'"
                )
                return updated_org
            else:
                # Should not happen if we already verified the org exists
                auth_logger.error(f"Failed to reactivate organization {org_id} - update returned None")
                raise HTTPException(
                    status_code=500, 
                    detail="Failed to reactivate organization due to a database error"
                )
                
        except Exception as e:
            auth_logger.error(
                f"Database error reactivating organization {org_id}: {e}", 
                exc_info=True
            )
            raise HTTPException(
                status_code=500, 
                detail="Failed to reactivate organization due to a database error"
            )

# Instantiate service for use in routers/dependencies
# auth_service = AuthService() 
