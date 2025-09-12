import asyncio
import os
import uuid
import logging # Keep standard logging import

from sqlalchemy.ext.asyncio import AsyncSession

# Keep external/absolute imports
from db.session import get_async_db_as_manager, init_db
from global_config.settings import global_settings

# Change imports for this module to absolute
from kiwi_app.auth.crud import UserDAO, OrganizationDAO, RoleDAO, PermissionDAO
from kiwi_app.auth import models, schemas, security
from kiwi_app.auth.utils import auth_logger
from kiwi_app.auth.constants import (
    ALL_PERMISSIONS,
    DefaultRoles,
    DEFAULT_ROLE_PERMISSIONS,
    DEFAULT_ORG_NAME,
    DEFAULT_SUPERUSER_EMAIL_ENV,
    DEFAULT_SUPERUSER_PASSWORD_ENV,
)
# this import is required so User / Org models correctly reconcile relationships to linkedin integration models
from linkedin_integration.models import *

# --- Logging Setup for Script --- #
# REMOVED: Specific basicConfig for this script, use the imported logger
# logger = logging.getLogger(__name__)

async def setup_auth_defaults():
    """
    Initializes default permissions, roles, organizations, and the superuser.
    Uses environment variables for default superuser credentials and log level.
    The superuser flag `is_superuser` is set, but no specific 'superuser' role is created.
    """
    auth_logger.info("Starting default auth setup...")

    # Get superuser credentials from environment
    superuser_email = os.getenv(DEFAULT_SUPERUSER_EMAIL_ENV)
    superuser_password = os.getenv(DEFAULT_SUPERUSER_PASSWORD_ENV)

    if not superuser_email or not superuser_password:
        auth_logger.error(f"Environment variables {DEFAULT_SUPERUSER_EMAIL_ENV} and {DEFAULT_SUPERUSER_PASSWORD_ENV} must be set.")
        return

    # Ensure tables exist (optional, depends if migrations handle this)
    # await init_db() # Assumes this creates tables if they don't exist

    async with get_async_db_as_manager() as db: # Use the async session context manager
        try:
            auth_logger.info("1. Ensuring default permissions exist...")
            permission_inputs = [
                schemas.PermissionCreate(name=p.value, description=p.name.replace("_", " ").title())
                for p in ALL_PERMISSIONS
            ]
            # Use DAO class directly for script context
            permissions_map = {p.name: p for p in await PermissionDAO().get_or_create_multi(db, permissions=permission_inputs)}
            auth_logger.info(f"   Ensured {len(permissions_map)} permissions exist.")

            auth_logger.info("2. Ensuring default roles (excluding SUPERUSER) exist and linking permissions...")
            roles_map = {}
            role_dao = RoleDAO() # Instantiate DAO for repeated use in loop
            for role_enum in DefaultRoles:
                role_name = role_enum.value
                role = await role_dao.get_by_name(db, name=role_name)
                required_permission_names = [p.value for p in DEFAULT_ROLE_PERMISSIONS.get(role_enum, [])]
                required_permissions = [permissions_map[p_name] for p_name in required_permission_names if p_name in permissions_map]

                if not role:
                    auth_logger.info(f"   Creating role: {role_name}")
                    role_in = schemas.RoleCreate(
                        name=role_name,
                        description=f"Default {role_name.title()} Role",
                        # permissions field handled by create_with_permissions
                    )
                    role = await role_dao.create_with_permissions(
                        db, obj_in=role_in, permissions=required_permissions
                    )
                else:
                    auth_logger.debug(f"   Role '{role_name}' exists. Checking permissions...")
                    current_perms_set = {p.id for p in role.permissions}
                    auth_logger.debug(f"   CURRENT PERMS SET:: "+ str(current_perms_set))
                    required_perms_set = {p.id for p in required_permissions}
                    auth_logger.debug(f"   REQUIRED PERMS SET:: "+ str(required_perms_set))
                    if current_perms_set != required_perms_set:
                        auth_logger.info(f"   Updating permissions for role '{role_name}'")
                        role = await role_dao.update_permissions(
                             db, db_role=role, new_permissions=required_permissions
                        )
                roles_map[role_name] = role
            auth_logger.info(f"   Ensured {len(roles_map)} default roles exist with correct permissions.")

            auth_logger.info("3. Ensuring default organization exists...")
            org_dao = OrganizationDAO()
            default_org = await org_dao.get_by_name(db, name=DEFAULT_ORG_NAME)
            if not default_org:
                auth_logger.info(f"   Creating organization: {DEFAULT_ORG_NAME}")
                org_in = schemas.OrganizationCreate(name=DEFAULT_ORG_NAME, description="Default KiwiQ AI system organization.")
                default_org = await org_dao.create(db, obj_in=org_in)
            else:
                auth_logger.debug(f"   Default organization '{DEFAULT_ORG_NAME}' already exists.")

            auth_logger.info("4. Ensuring default superuser exists (with is_superuser flag)...")
            user_dao = UserDAO()
            superuser = await user_dao.get_by_email(db, email=superuser_email)
            if not superuser:
                auth_logger.info(f"   Creating superuser: {superuser_email}")
                user_in = schemas.UserCreate(
                    email=superuser_email,
                    password=superuser_password,
                    full_name="Default Admin"
                )
                # Use DAO method directly
                superuser = await user_dao.create_user(db=db, user_in=user_in)
                # Mark as superuser and verified
                superuser = await user_dao.update(db, db_obj=superuser, obj_in=schemas.UserAdminUpdate(is_superuser=True, is_verified=True))
                auth_logger.info(f"   Superuser created.")
            else:
                auth_logger.debug(f"   Superuser '{superuser_email}' already exists.")
                # Ensure existing user is superuser and verified
                update_needed = False
                update_payload = schemas.UserAdminUpdate()
                if not superuser.is_superuser:
                    update_payload.is_superuser = True
                    update_needed = True
                if not superuser.is_verified:
                    update_payload.is_verified = True
                    update_needed = True
                if update_needed:
                    auth_logger.info(f"   Updating superuser '{superuser_email}' flags.")
                    superuser = await user_dao.update(db, db_obj=superuser, obj_in=update_payload)

            auth_logger.info("5. Assigning superuser ADMIN role in default organization...")
            admin_role = roles_map.get(DefaultRoles.ADMIN)
            if not admin_role:
                 auth_logger.critical("Default admin role not found! Cannot assign to superuser.")
                 return # Abort if admin role wasn't created

            await user_dao.add_user_to_org(db=db, user=superuser, organization=default_org, role=admin_role)
            auth_logger.info(f"   Assigned '{superuser.email}' as '{admin_role.name}' in '{default_org.name}'.")

            auth_logger.info("Default auth setup completed successfully.")

        except Exception as e:
            auth_logger.exception("An error occurred during auth setup", exc_info=e)
            # Consider rollback if necessary, though get_async_db handles session rollback on exception
            raise # Re-raise the exception after logging

async def main():
    # Example of how to run the setup
    await setup_auth_defaults()

if __name__ == "__main__":
    # Check for environment variables before running
    superuser_email = os.getenv(DEFAULT_SUPERUSER_EMAIL_ENV)
    superuser_password = os.getenv(DEFAULT_SUPERUSER_PASSWORD_ENV)
    if not superuser_email or not superuser_password:
         auth_logger.error(f"Environment variables {DEFAULT_SUPERUSER_EMAIL_ENV} and {DEFAULT_SUPERUSER_PASSWORD_ENV} must be set to run the setup script.")
    else:
        asyncio.run(main()) 
