import asyncio
import os
import uuid
import logging

from sqlalchemy.ext.asyncio import AsyncSession

# Keep external/absolute imports
from db.session import get_async_db_as_manager, async_engine, init_db
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

async def set_all_orgs_active():
    """
    Updates all existing organizations to set is_active = True.
    
    This script is useful when adding the is_active field to an existing database
    where organizations should default to active status.
    """
    auth_logger.info("Starting organization activation update...")

    async with get_async_db_as_manager() as db:
        try:
            auth_logger.info("1. Fetching all organizations...")
            org_dao = OrganizationDAO()
            
            # Get all organizations without filtering by active status
            # Using get_multi_with_active_filter with active_only=False to get all orgs
            all_orgs = await org_dao.get_multi_with_active_filter(
                db=db, 
                skip=0, 
                limit=1000,  # Adjust if you have more than 1000 orgs
                active_only=False
            )
            
            auth_logger.info(f"   Found {len(all_orgs)} organizations to process.")
            
            if not all_orgs:
                auth_logger.info("   No organizations found. Nothing to update.")
                return
            
            auth_logger.info("2. Updating organizations to set is_active = True...")
            updated_count = 0
            
            for org in all_orgs:
                # Check if the organization is already active
                if org.is_active:
                    auth_logger.debug(f"   Organization '{org.name}' (ID: {org.id}) is already active. Skipping.")
                    continue
                
                # Update the organization to be active
                try:
                    updated_org = await org_dao.update_organization_status(
                        db=db,
                        org_id=org.id,
                        is_active=True
                    )
                    
                    if updated_org:
                        auth_logger.info(f"   Updated organization '{org.name}' (ID: {org.id}) to active status.")
                        updated_count += 1
                    else:
                        auth_logger.warning(f"   Failed to update organization '{org.name}' (ID: {org.id})")
                        
                except Exception as e:
                    auth_logger.error(f"   Error updating organization '{org.name}' (ID: {org.id}): {e}")
                    continue
            
            auth_logger.info(f"3. Organization activation update completed. Updated {updated_count} organizations.")
            
            if updated_count == 0:
                auth_logger.info("   All organizations were already active.")
            else:
                auth_logger.info(f"   Successfully activated {updated_count} organizations.")

        except Exception as e:
            auth_logger.exception("An error occurred during organization activation update", exc_info=e)
            # Consider rollback if necessary, though get_async_db handles session rollback on exception
            raise # Re-raise the exception after logging

async def main():
    """Main function to run the organization activation script."""
    try:
        await set_all_orgs_active()
        auth_logger.info("Script completed successfully.")
    except Exception as e:
        auth_logger.error(f"Script failed with error: {e}")
        raise

if __name__ == "__main__":
    auth_logger.info("Starting organization activation script...")
    asyncio.run(main())
