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

from kiwi_app.auth.security import get_password_hash, verify_password
from kiwi_app.auth.constants import Permissions, DefaultRoles
from kiwi_app.auth import models, schemas
from kiwi_app.auth.utils import auth_logger, datetime_now_utc # Import the auth_logger and datetime_now_utc
from kiwi_app.auth.crud_util import build_load_options

# --- Base DAO Class --- #
ModelType = TypeVar("ModelType", bound=SQLModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=SQLModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=SQLModel)

class BaseDAO(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """Generic Base Data Access Object for CRUD operations.
    # TODO: FIXME: handle db commit / refresh centrally from service as part of transaction context to reduce DB round trips
    """
    def __init__(self, model: Type[ModelType]):
        self.model = model

    async def get(self, db: AsyncSession, id: uuid.UUID, load_relations: Optional[List[str]] = None) -> Optional[ModelType]:
        """Get a single record by ID, optionally loading relationships."""
        statement = select(self.model).where(self.model.id == id)
        options = None
        if load_relations:
            if not isinstance(load_relations[0], str):
                # load_relations = [(self.model, r) for r in load_relations]
                # since relationships in link objects require full qualified path here from the original object like `organization_links.organization`!
                options = build_load_options(load_relations)
            else:
                options = [selectinload(getattr(self.model, rel)) for rel in load_relations if hasattr(self.model, rel)]
            if options:
                 statement = statement.options(*options)
        # Use exec instead of execute for direct Pydantic model return
        result = await db.exec(statement)
        result_scalars = result.scalars()
        
        if options is not None:
            # THis is to group multi fetch many-to-many queries, check with Gemini!
            result_scalars = result_scalars.unique()

        return result_scalars.first()

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> Sequence[ModelType]:
        """Get multiple records with pagination."""
        statement = select(self.model).offset(skip).limit(limit)
        # Use exec instead of execute for direct Pydantic model return
        result = await db.exec(statement)
        return result.scalars().all()

    async def create(self, db: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType:
        """Create a new record."""
        # Use model_validate to handle potential nested schemas or defaults
        db_obj = self.model.model_validate(obj_in)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self, db: AsyncSession, *, db_obj: ModelType, obj_in: UpdateSchemaType
    ) -> ModelType:
        """Update an existing record."""
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj
    
    async def delete(self, db: AsyncSession, *, db_obj: ModelType) -> bool:
        """
        Delete a record by ID.
        
        Args:
            db: Database session
            id: UUID of the record to delete
            
        Returns:
            bool: True if the record was found and deleted, False otherwise
            
        Note:
            This is similar to remove() but returns a boolean instead of the object.
            Useful when you only need to know if deletion succeeded but don't need the object.
        """
        if db_obj is not None and isinstance(db_obj, self.model):
            await db.delete(db_obj)
            await db.commit()
            return True
        return False

    async def remove(self, db: AsyncSession, *, id: uuid.UUID) -> Optional[ModelType]:
        """Delete a record by ID."""
        obj = await self.get(db, id=id)
        if obj:
            await db.delete(obj)
            await db.commit()
        return obj

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
        hashed_password = get_password_hash(user_in.password)
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
            return {p.value for p in Permissions}

        if user.organization_links:
            for link in user.organization_links:
                 if link.role and link.role.permissions:
                    for perm in link.role.permissions:
                        all_permissions.add(perm.name)
        return all_permissions

    async def add_user_to_org(self, db: AsyncSession, *, user: models.User, organization: models.Organization, role: models.Role) -> models.UserOrganizationRole:
        """Adds a user to an organization with a specific role."""
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
        result = await db.execute(statement)
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
        result = await db.execute(statement)
        await db.commit()
        return result.rowcount

# Instantiate DAOs for use in services/dependencies
# user_dao = UserDAO()
# permission_dao = PermissionDAO()
# role_dao = RoleDAO()
# organization_dao = OrganizationDAO()
