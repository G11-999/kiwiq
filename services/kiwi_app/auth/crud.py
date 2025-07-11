from typing import Optional, List, Sequence, Type, TypeVar, Generic, Set
import uuid
from datetime import datetime

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
# TODO: FIXME: switch to below and remove scalars() call!
# from sqlmodel import select
from sqlalchemy.orm import selectinload, joinedload
from sqlmodel import SQLModel
from sqlalchemy import func

from kiwi_app.auth.security import get_password_hash, verify_password
from kiwi_app.auth.constants import Permissions, DefaultRoles, ALL_PERMISSIONS
from kiwi_app.auth import models, schemas
from kiwi_app.auth.utils import auth_logger, datetime_now_utc # Import the auth_logger and datetime_now_utc
from kiwi_app.auth.crud_util import build_load_options
from kiwi_app.settings import settings
from kiwi_app.auth.base_crud import BaseDAO

from kiwi_app.auth.exceptions import OrganizationSeatLimitExceededException

# --- Base DAO Class --- #
ModelType = TypeVar("ModelType", bound=SQLModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=SQLModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=SQLModel)

# class BaseDAO(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
#     """Generic Base Data Access Object for CRUD operations.
#     # TODO: FIXME: handle db commit / refresh centrally from service as part of transaction context to reduce DB round trips
#     """
#     def __init__(self, model: Type[ModelType]):
#         self.model = model

#     async def get(self, db: AsyncSession, id: uuid.UUID, load_relations: Optional[List[str]] = None) -> Optional[ModelType]:
#         """Get a single record by ID, optionally loading relationships."""
#         statement = select(self.model).where(self.model.id == id)
#         options = None
#         if load_relations:
#             if not isinstance(load_relations[0], str):
#                 # load_relations = [(self.model, r) for r in load_relations]
#                 # since relationships in link objects require full qualified path here from the original object like `organization_links.organization`!
#                 options = build_load_options(load_relations)
#             else:
#                 options = [selectinload(getattr(self.model, rel)) for rel in load_relations if hasattr(self.model, rel)]
#             if options:
#                  statement = statement.options(*options)
#         # Use exec instead of execute for direct Pydantic model return
#         result = await db.exec(statement)
#         result_scalars = result.scalars()
        
#         if options is not None:
#             # THis is to group multi fetch many-to-many queries, check with Gemini!
#             result_scalars = result_scalars.unique()

#         return result_scalars.first()

#     async def get_multi(
#         self, db: AsyncSession, *, skip: int = 0, limit: int = 100
#     ) -> Sequence[ModelType]:
#         """Get multiple records with pagination."""
#         statement = select(self.model).offset(skip).limit(limit)
#         # Use exec instead of execute for direct Pydantic model return
#         result = await db.exec(statement)
#         return result.scalars().all()

#     async def create(self, db: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType:
#         """Create a new record."""
#         # Use model_validate to handle potential nested schemas or defaults
#         db_obj = self.model.model_validate(obj_in)
#         db.add(db_obj)
#         await db.commit()
#         await db.refresh(db_obj)
#         return db_obj

#     async def update(
#         self, db: AsyncSession, *, db_obj: ModelType, obj_in: UpdateSchemaType
#     ) -> ModelType:
#         """Update an existing record."""
#         update_data = obj_in.model_dump(exclude_unset=True)
#         for field, value in update_data.items():
#             setattr(db_obj, field, value)
#         db.add(db_obj)
#         await db.commit()
#         await db.refresh(db_obj)
#         return db_obj
    
#     async def delete(self, db: AsyncSession, *, db_obj: ModelType) -> bool:
#         """
#         Delete a record by ID.
        
#         Args:
#             db: Database session
#             id: UUID of the record to delete
            
#         Returns:
#             bool: True if the record was found and deleted, False otherwise
            
#         Note:
#             This is similar to remove() but returns a boolean instead of the object.
#             Useful when you only need to know if deletion succeeded but don't need the object.
#         """
#         if db_obj is not None and isinstance(db_obj, self.model):
#             await db.delete(db_obj)
#             await db.commit()
#             return True
#         return False

#     async def remove(self, db: AsyncSession, *, id: uuid.UUID) -> Optional[ModelType]:
#         """Delete a record by ID."""
#         obj = await self.get(db, id=id)
#         if obj:
#             await db.delete(obj)
#             await db.commit()
#         return obj

# --- Specific DAOs --- #

class PermissionDAO(BaseDAO[models.Permission, schemas.PermissionCreate, SQLModel]): # Update schema not defined
    def __init__(self):
        super().__init__(models.Permission)

    async def get_by_name(self, db: AsyncSession, name: str) -> Optional[models.Permission]:
        statement = select(self.model).where(self.model.name == name)
        result = await db.exec(statement)
        return result.scalars().first()

    async def get_or_create_multi(self, db: AsyncSession, permissions: List[schemas.PermissionCreate]) -> List[models.Permission]:
        """Get or create multiple permissions by name."""
        existing_perms_list = []
        perms_to_create_map = {p.name: p for p in permissions}

        # Fetch existing permissions
        perm_names = [p.name for p in permissions]
        if perm_names:
            statement = select(self.model).where(self.model.name.in_(perm_names))
            result = await db.exec(statement)
            existing_perms = result.scalars().all()
            existing_perms_list.extend(existing_perms)
            # import ipdb; ipdb.set_trace()
            for p in existing_perms:
                if p.name in perms_to_create_map:
                    del perms_to_create_map[p.name]

        # Create new permissions
        new_perms_list = []
        if perms_to_create_map:
            new_db_objs = [self.model.model_validate(p) for p in perms_to_create_map.values()]
            db.add_all(new_db_objs)
            await db.commit()
            for obj in new_db_objs:
                 await db.refresh(obj) # Refresh individually if needed
                 new_perms_list.append(obj)

        return existing_perms_list + new_perms_list


class RoleDAO(BaseDAO[models.Role, schemas.RoleCreate, schemas.RoleUpdate]):
    def __init__(self):
        super().__init__(models.Role)

    async def get_by_name(self, db: AsyncSession, name: str) -> Optional[models.Role]:
        statement = select(self.model).options(selectinload(self.model.permissions)).where(self.model.name == name)
        result = await db.exec(statement)
        return result.scalars().first()

    async def get_by_name_list(self, db: AsyncSession, names: List[str]) -> Sequence[models.Role]:
        statement = select(self.model).where(self.model.name.in_(names))
        result = await db.exec(statement)
        return result.scalars().all()

    async def create_with_permissions(
        self, db: AsyncSession, *, obj_in: schemas.RoleCreate, permissions: List[models.Permission]
    ) -> models.Role:
        """Create a role and associate it with given permissions."""
        role_data = obj_in.model_dump(exclude={"permissions"})
        db_role = self.model(**role_data)
        db_role.permissions = permissions # Assign permission objects directly
        db.add(db_role)
        await db.commit()
        await db.refresh(db_role)
        # Eager load permissions for the returned object
        await db.refresh(db_role, attribute_names=["permissions"])
        return db_role

    async def update_permissions(
        self, db: AsyncSession, *, db_role: models.Role, new_permissions: List[models.Permission]
    ) -> models.Role:
        """Replace the permissions associated with a role."""
        db_role.permissions = new_permissions
        db.add(db_role)
        await db.commit()
        await db.refresh(db_role)
        await db.refresh(db_role, attribute_names=["permissions"])
        return db_role


class OrganizationDAO(BaseDAO[models.Organization, schemas.OrganizationCreate, schemas.OrganizationUpdate]):
    def __init__(self):
        super().__init__(models.Organization)

    async def get_by_name(self, db: AsyncSession, name: str) -> Optional[models.Organization]:
        statement = select(self.model).where(self.model.name == name)
        result = await db.exec(statement)
        return result.scalars().first()

    async def update_primary_billing_email(
        self, 
        db: AsyncSession, 
        *, 
        org_id: uuid.UUID, 
        email: Optional[str]
    ) -> Optional[models.Organization]:
        """
        Update the primary billing email for an organization.
        
        Args:
            db: Database session
            org_id: Organization ID to update
            email: New primary billing email (can be None to clear)
            
        Returns:
            Updated organization or None if not found
            
        Raises:
            Exception: If there's a database error during update
        """
        try:
            # Get the organization
            org = await self.get(db, id=org_id)
            if not org:
                auth_logger.warning(f"Attempted to update primary_billing_email for non-existent organization: {org_id}")
                return None
            
            # Update the primary billing email
            org.primary_billing_email = email
            db.add(org)
            await db.commit()
            await db.refresh(org)
            
            auth_logger.info(f"Updated primary_billing_email for organization {org_id} to: {email}")
            return org
            
        except Exception as e:
            auth_logger.error(f"Error updating primary_billing_email for organization {org_id}: {e}", exc_info=True)
            raise

    async def get_admin_users_in_org(
        self, 
        db: AsyncSession, 
        org_id: uuid.UUID
    ) -> Sequence[models.UserOrganizationRole]:
        """
        Get all admin users in an organization.
        
        This method retrieves UserOrganizationRole records for users with admin roles
        in a specific organization, eagerly loading the associated user information.
        
        Args:
            db: Database session
            org_id: Organization ID to get admin users for
            
        Returns:
            Sequence of UserOrganizationRole objects with loaded user relationships
            
        Example:
            admin_links = await dao.get_admin_users_in_org(db, org_id)
            for admin_link in admin_links:
                print(f"Admin: {admin_link.user.email}")
        """
        try:
            from kiwi_app.auth.constants import DefaultRoles
            
            statement = select(models.UserOrganizationRole).options(
                # Eagerly load user details
                selectinload(models.UserOrganizationRole.user),
                # Eagerly load role details
                selectinload(models.UserOrganizationRole.role)
            ).join(
                models.Role, models.UserOrganizationRole.role_id == models.Role.id
            ).where(
                models.UserOrganizationRole.organization_id == org_id,
                models.Role.name == DefaultRoles.ADMIN  # Only get admin users
            ).order_by(models.UserOrganizationRole.created_at.asc())
            
            result = await db.exec(statement)
            admin_links = result.scalars().all()
            
            auth_logger.debug(f"Retrieved {len(admin_links)} admin users for organization {org_id}")
            return admin_links
            
        except Exception as e:
            auth_logger.error(f"Error getting admin users for organization {org_id}: {e}", exc_info=True)
            raise

    async def auto_update_primary_billing_email(
        self, 
        db: AsyncSession, 
        *, 
        org_id: uuid.UUID,
        action: str,
        user_email: Optional[str] = None
    ) -> Optional[models.Organization]:
        """
        Automatically update primary billing email based on organization changes.
        
        This method implements the business logic for automatically setting/updating
        the primary billing email when users are added or removed from organizations.
        
        Logic:
        - If no primary_billing_email exists, set it to the first available admin user
        - If the current primary_billing_email user is removed, replace with another admin
        - If adding a user and no primary_billing_email exists, use the new user's email
        
        Args:
            db: Database session
            org_id: Organization ID to update
            action: Type of action ('create', 'add_user', 'remove_user')
            user_email: Email of user being added/removed (for add_user/remove_user actions)
            
        Returns:
            Updated organization or None if not found/no update needed
        """
        try:
            org = await self.get(db, id=org_id)
            if not org:
                return None
            
            auth_logger.debug(f"Auto-updating primary_billing_email for org {org_id}, action: {action}, user_email: {user_email}")
            
            if action == "create":
                # For new organizations, primary_billing_email should be set to creator's email
                # This is handled in the service layer when creating the org
                return org
                
            elif action == "add_user":
                # If no primary billing email exists, set it to the new user's email
                if not org.primary_billing_email and user_email:
                    return await self.update_primary_billing_email(db, org_id=org_id, email=user_email)
                    
            elif action == "remove_user":
                # If the removed user was the primary billing contact, find a replacement
                if org.primary_billing_email == user_email:
                    # Get admin users to find a replacement
                    admin_links = await self.get_admin_users_in_org(db, org_id)
                    
                    # Find the first admin that's not the user being removed
                    replacement_email = None
                    for admin_link in admin_links:
                        if admin_link.user and admin_link.user.email != user_email:
                            replacement_email = admin_link.user.email
                            break
                    
                    # Update to replacement email (could be None if no other admins)
                    return await self.update_primary_billing_email(db, org_id=org_id, email=replacement_email)
            
            # No update needed
            return org
            
        except Exception as e:
            auth_logger.error(f"Error auto-updating primary_billing_email for org {org_id}: {e}", exc_info=True)
            raise

    async def get_user_count_in_org(self, db: AsyncSession, org_id: uuid.UUID) -> int:
        """
        Get the total count of users in an organization.
        
        This method efficiently counts the number of UserOrganizationRole records
        for a specific organization without loading the actual user data, making
        it suitable for pagination calculations and dashboard statistics.
        
        Uses COALESCE to ensure we always return 0 instead of NULL when no users exist.
        
        Args:
            db: Database session
            org_id: Organization ID to count users for
            
        Returns:
            Total number of users in the organization, 0 if no users exist
            
        Example:
            # Get total user count for pagination
            total_users = await dao.get_user_count_in_org(db, org_id)
            total_pages = (total_users + page_size - 1) // page_size
        """
        try:
            statement = select(func.coalesce(func.count(models.UserOrganizationRole.user_id), 0)).where(
                models.UserOrganizationRole.organization_id == org_id
            ).group_by(models.UserOrganizationRole.organization_id)
            
            result = await db.exec(statement)
            user_count = result.scalar()
            
            auth_logger.debug(f"User count for organization {org_id}: {user_count}")
            return int(user_count or 0)
            
        except Exception as e:
            auth_logger.error(f"Error counting users for organization {org_id}: {e}", exc_info=True)
            raise

    async def get_active_organizations(
        self, 
        db: AsyncSession, 
        *, 
        skip: int = 0, 
        limit: int = 100
    ) -> Sequence[models.Organization]:
        """
        Get multiple active organizations with pagination.
        
        This method fetches only organizations where is_active=True, which is useful
        for regular user interfaces where inactive organizations should be hidden.
        
        Args:
            db: Database session
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            
        Returns:
            Sequence of active organization objects
        """
        try:
            statement = select(self.model).where(
                self.model.is_active == True
            ).offset(skip).limit(limit).order_by(self.model.created_at.desc())
            
            result = await db.exec(statement)
            organizations = result.scalars().all()
            
            auth_logger.debug(f"Retrieved {len(organizations)} active organizations")
            return organizations
            
        except Exception as e:
            auth_logger.error(f"Error getting active organizations: {e}", exc_info=True)
            raise

    async def get_multi_with_active_filter(
        self, 
        db: AsyncSession, 
        *, 
        skip: int = 0, 
        limit: int = 100,
        active_only: bool = True
    ) -> Sequence[models.Organization]:
        """
        Get multiple organizations with optional active filtering and pagination.
        
        This method provides flexible organization retrieval with the ability to
        filter by active status. Useful for admin interfaces where you might want
        to see all organizations or just active ones.
        
        Args:
            db: Database session
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            active_only: If True, only return active organizations. If False, return all.
            
        Returns:
            Sequence of organization objects matching the filter criteria
        """
        try:
            statement = select(self.model)
            
            if active_only:
                statement = statement.where(self.model.is_active == True)
                
            statement = statement.offset(skip).limit(limit).order_by(self.model.created_at.desc())
            
            result = await db.exec(statement)
            organizations = result.scalars().all()
            
            filter_desc = "active" if active_only else "all"
            auth_logger.debug(f"Retrieved {len(organizations)} {filter_desc} organizations")
            return organizations
            
        except Exception as e:
            auth_logger.error(f"Error getting organizations with filter: {e}", exc_info=True)
            raise

    async def update_organization_status(
        self, 
        db: AsyncSession, 
        *, 
        org_id: uuid.UUID, 
        is_active: bool
    ) -> Optional[models.Organization]:
        """
        Update an organization's active status.
        
        This method allows setting an organization as active or inactive.
        Inactive organizations are typically hidden from regular user interfaces
        but remain accessible to administrators.
        
        Args:
            db: Database session
            org_id: Organization ID to update
            is_active: New active status (True for active, False for inactive)
            
        Returns:
            Updated organization or None if not found
            
        Raises:
            Exception: If there's a database error during update
        """
        try:
            # Get the organization
            org = await self.get(db, id=org_id)
            if not org:
                auth_logger.warning(f"Attempted to update status for non-existent organization: {org_id}")
                return None
            
            # Update the active status
            org.is_active = is_active
            db.add(org)
            await db.commit()
            await db.refresh(org)
            
            status_text = "active" if is_active else "inactive"
            auth_logger.info(f"Updated organization {org_id} status to: {status_text}")
            return org
            
        except Exception as e:
            auth_logger.error(f"Error updating organization status for {org_id}: {e}", exc_info=True)
            raise


class UserDAO(BaseDAO[models.User, schemas.UserCreate, schemas.UserAdminUpdate]): # Use AdminUpdate for full updates
    def __init__(self):
        super().__init__(models.User)

    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[models.User]:
        """Get user by email, loading organization links and roles."""
        statement = select(self.model).options(
            selectinload(self.model.organization_links).selectinload(models.UserOrganizationRole.organization),
            selectinload(self.model.organization_links).selectinload(models.UserOrganizationRole.role).selectinload(models.Role.permissions)
        ).where(self.model.email == email)
        result = await db.exec(statement)
        return result.scalars().first()

    async def get_by_email_with_active_orgs(self, db: AsyncSession, email: str) -> Optional[models.User]:
        """
        Get user by email, loading only active organization links and roles.
        
        This method is similar to get_by_email but filters out inactive organizations
        from the loaded relationships, which is useful for regular user interfaces
        where inactive organizations should be hidden.
        
        Args:
            db: Database session
            email: User email to search for
            
        Returns:
            User object with only active organization links loaded, or None if user not found
        """
        statement = select(self.model).options(
            selectinload(self.model.organization_links)
            .selectinload(models.UserOrganizationRole.organization)
            .where(models.Organization.is_active == True),
            selectinload(self.model.organization_links)
            .selectinload(models.UserOrganizationRole.role)
            .selectinload(models.Role.permissions)
        ).where(self.model.email == email)
        result = await db.exec(statement)
        user = result.scalars().first()
        
        # Additional filtering to ensure organization_links only include active organizations
        if user and user.organization_links:
            user.organization_links = [
                link for link in user.organization_links 
                if link.organization and link.organization.is_active
            ]
        
        return user

    async def get_by_linkedin_id(self, db: AsyncSession, linkedin_id: str) -> Optional[models.User]:
        """Get user by LinkedIn ID, loading organization links and roles."""
        statement = select(self.model).options(
            selectinload(self.model.organization_links).selectinload(models.UserOrganizationRole.organization),
            selectinload(self.model.organization_links).selectinload(models.UserOrganizationRole.role).selectinload(models.Role.permissions)
        ).where(self.model.linkedin_id == linkedin_id)
        result = await db.exec(statement)
        return result.scalars().first()

    async def create_user(self, db: AsyncSession, *, user_in: schemas.UserCreate) -> models.User:
        """Create user, hashing the password."""
        if user_in.password:
            hashed_password = get_password_hash(user_in.password)
        else:
            hashed_password = None
        user_data = user_in.model_dump(exclude={"password"})
        db_user = self.model(**user_data, hashed_password=hashed_password)
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user

    async def create_oauth_user(self, db: AsyncSession, *, email: str, full_name: Optional[str], linkedin_id: str) -> models.User:
        """Create a user from OAuth data (no password initially)."""
        db_user = self.model(
            email=email,
            full_name=full_name,
            linkedin_id=linkedin_id,
            is_active=True,
            is_verified=True, # Assume verified via OAuth provider
            hashed_password=None # No password set
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user

    async def update(self, db: AsyncSession, *, db_obj: models.User, obj_in: schemas.UserAdminUpdate | schemas.UserUpdate) -> models.User:
        """Override update to handle UserUpdate vs UserAdminUpdate."""
        # Note: Consider password update logic separately
        return await super().update(db, db_obj=db_obj, obj_in=obj_in)

    async def authenticate(self, db: AsyncSession, *, email: str, password: str) -> Optional[models.User]:
        """Authenticate user with email and password."""
        user = await self.get_by_email(db, email=email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def get_user_permissions(self, user: models.User) -> Set[str]:
        """Get a flat set of all permission names for a user across all their org roles."""
        # Assumes user object has organization_links.role.permissions preloaded
        # or handles lazy loading (which can be inefficient).
        # Prefer preloading as done in get_by_email.
        all_permissions: Set[str] = set()
        if user.is_superuser:
            # Superusers implicitly have all permissions
            return {p.value for p in ALL_PERMISSIONS}

        if user.organization_links:
            for link in user.organization_links:
                 if link.role and link.role.permissions:
                    for perm in link.role.permissions:
                        all_permissions.add(perm.name)
        return all_permissions

    async def add_user_to_org(self, db: AsyncSession, *, user: models.User, organization: models.Organization, role: models.Role, current_user_is_superuser: bool = False) -> models.UserOrganizationRole:
        """Adds a user to an organization with a specific role.
        # TODO: move logic to service!
        """
        # Check if exists first
        link = await self.get_user_org_role(db, user_id=user.id, org_id=organization.id)
        if link:
            # If link exists, update the role if different
            if link.role_id != role.id:
                link.role_id = role.id
                db.add(link)
                await db.commit()
                await db.refresh(link)
            return link
        else:
            # Create new link
            if not current_user_is_superuser:
                from kiwi_app.billing.crud import OrganizationSubscriptionDAO
                subscription_dao = OrganizationSubscriptionDAO()
                seats_allowed = await subscription_dao.get_total_seat_count_for_org(db, org_id=organization.id)
                seats_allowed = max(seats_allowed, settings.MIN_SEATS_ALLOWED_WITHOUT_SUBSCRIPTION)
                current_user_count = await OrganizationDAO().get_user_count_in_org(db, org_id=organization.id)
                if current_user_count >= seats_allowed:
                    raise OrganizationSeatLimitExceededException(f"Cannot add user to organization. Current users: {current_user_count}, Seats allowed: {seats_allowed}")
            
            new_link = models.UserOrganizationRole(user_id=user.id, organization_id=organization.id, role_id=role.id)
            db.add(new_link)
            await db.commit()
            await db.refresh(new_link)
            return new_link

    async def remove_user_from_org(self, db: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID) -> bool:
        """Removes a user's link to an organization."""
        statement = delete(models.UserOrganizationRole)\
            .where(models.UserOrganizationRole.user_id == user_id)\
            .where(models.UserOrganizationRole.organization_id == org_id)
        # Keep execute for delete where we need rowcount
        result = await db.exec(statement)
        await db.commit()
        return result.rowcount > 0 # Return True if a row was deleted

    async def get_user_org_role(self, db: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID) -> Optional[models.UserOrganizationRole]:
        """Get the specific link object for a user and org."""
        statement = select(models.UserOrganizationRole)\
            .options(joinedload(models.UserOrganizationRole.role).selectinload(models.Role.permissions))\
            .where(models.UserOrganizationRole.user_id == user_id)\
            .where(models.UserOrganizationRole.organization_id == org_id)
        result = await db.exec(statement)
        return result.scalars().first()

# --- NEW: Refresh Token DAO --- #
class RefreshTokenDAO(BaseDAO[models.RefreshToken, SQLModel, SQLModel]): # No specific create/update schemas needed yet
    def __init__(self):
        super().__init__(models.RefreshToken)

    async def get_valid_token(self, db: AsyncSession, token: uuid.UUID) -> Optional[models.RefreshToken]:
        """
        Get a token by its UUID, ensuring it's not expired or revoked.
        Also loads the associated user object.
        
        Args:
            db: Database session
            token: UUID of the refresh token to find
            
        Returns:
            The valid refresh token with user loaded, or None if not found/invalid
        """
        now = datetime_now_utc()
        statement = select(self.model).where(
            self.model.token == token,
            self.model.expires_at > now,
            self.model.revoked_at == None # Check if None using == for SQL translation
        ).options(
            joinedload(self.model.user)  # Eagerly load the user relationship
        )
        result = await db.exec(statement)
        return result.scalars().first()

    async def create_token(self, db: AsyncSession, *, user_id: uuid.UUID, expires_at: datetime) -> models.RefreshToken:
        """Create a new refresh token record."""
        db_token = self.model(user_id=user_id, expires_at=expires_at)
        db.add(db_token)
        await db.commit()
        await db.refresh(db_token)
        return db_token

    async def revoke_token(self, db: AsyncSession, *, token_obj: models.RefreshToken) -> models.RefreshToken:
        """Mark a refresh token as revoked."""
        if not token_obj.revoked_at:
            token_obj.revoked_at = datetime_now_utc()
            db.add(token_obj)
            await db.commit()
            await db.refresh(token_obj)
        return token_obj

    async def revoke_all_for_user(self, db: AsyncSession, *, user_id: uuid.UUID) -> int:
        """Revoke all non-revoked, non-expired tokens for a user. Returns count revoked."""
        now = datetime_now_utc()
        statement = (
            update(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.expires_at > now,
                self.model.revoked_at == None
            )
            .values(revoked_at=now)
            .execution_options(synchronize_session=False) # Important for bulk updates
        )
        result = await db.exec(statement)
        await db.commit()
        return result.rowcount

# Instantiate DAOs for use in services/dependencies
# user_dao = UserDAO()
# permission_dao = PermissionDAO()
# role_dao = RoleDAO()
# organization_dao = OrganizationDAO()
