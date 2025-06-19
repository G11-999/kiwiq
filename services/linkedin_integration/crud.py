"""
LinkedIn OAuth CRUD Operations

This module defines Data Access Objects (DAOs) for LinkedIn OAuth-related database operations,
following KiwiQ's established patterns for CRUD operations with dependency injection.
"""

from typing import Optional, List
from datetime import datetime, timedelta
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import and_, or_, delete, update, func

from kiwi_app.auth.base_crud import BaseDAO
from global_utils import datetime_now_utc
from kiwi_app.utils import get_kiwi_logger
from linkedin_integration import models

logger = get_kiwi_logger("linkedin_integration.crud")


class LinkedinOauthDAO(BaseDAO[models.LinkedinUserOauth, None, None]):
    """
    Data Access Object for LinkedIn OAuth operations.
    
    This DAO handles all database operations related to LinkedIn OAuth records,
    including token management, user linking, and access validation.
    """
    
    def __init__(self):
        super().__init__(models.LinkedinUserOauth)
    
    async def get_by_user_id(
        self, 
        db: AsyncSession, 
        user_id: uuid.UUID
    ) -> Optional[models.LinkedinUserOauth]:
        """
        Get LinkedIn OAuth record by KIWIQ user ID.
        
        Args:
            db: Database session
            user_id: KIWIQ user UUID
            
        Returns:
            LinkedinUserOauth record or None if not found
        """
        try:
            statement = select(self.model).where(self.model.user_id == user_id)
            result = await db.execute(statement)
            return result.scalars().first()
        except Exception as e:
            logger.error(f"Error getting LinkedIn OAuth by user ID {user_id}: {e}")
            raise
    
    async def create_or_update(
        self,
        db: AsyncSession,
        linkedin_id: str,
        user_id: Optional[uuid.UUID] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        scope: Optional[str] = None,
        expires_in: Optional[int] = None,
        refresh_token_expires_in: Optional[int] = None,
        oauth_state: Optional[models.LinkedinOauthState] = None,
        state_metadata: Optional[dict] = None,
        create: bool = True,
        commit: bool = True
    ) -> models.LinkedinUserOauth:
        """Create or update LinkedIn OAuth record with state tracking"""
        try:
            # Check if record exists
            existing = await self.get(db, linkedin_id)
            
            if existing:
                # Update existing record
                existing.user_id = user_id or existing.user_id
                existing.access_token = access_token or existing.access_token
                existing.refresh_token = refresh_token or existing.refresh_token
                existing.scope = scope or existing.scope
                existing.expires_in = expires_in or existing.expires_in
                existing.refresh_token_expires_in = refresh_token_expires_in or existing.refresh_token_expires_in
                existing.update_expiration_timestamps()
                existing.oauth_state = oauth_state or existing.oauth_state
                existing.state_metadata = state_metadata or existing.state_metadata
                # existing.updated_at = datetime_now_utc()
                
                db.add(existing)
                if commit:
                    await db.commit()
                    await db.refresh(existing)
                
                logger.info(f"Updated LinkedIn OAuth for user {user_id}, state: {existing.oauth_state}")
                return existing
            elif create:
                # Create new record
                # if oauth_state is None:
                #     raise ValueError("OAuth state is required for new OAuth records")
                
                oauth_record = models.LinkedinUserOauth(
                    id=linkedin_id,
                    user_id=user_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    scope=scope,
                    expires_in=expires_in,
                    refresh_token_expires_in=refresh_token_expires_in,
                    oauth_state=oauth_state,
                    state_metadata=state_metadata
                )
                oauth_record.update_expiration_timestamps()
                
                db.add(oauth_record)
                if commit:
                    await db.commit()
                    await db.refresh(oauth_record)
                
                logger.info(f"Created LinkedIn OAuth for user {user_id}, state: {oauth_record.oauth_state}")
                return oauth_record
                
        except Exception as e:
            # if commit:
            #     await db.rollback()
            logger.error(f"Error creating/updating LinkedIn OAuth: {e}")
            raise
    
    async def unlink_from_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        commit: bool = True
    ) -> bool:
        """
        Remove LinkedIn OAuth association for a user.
        
        Args:
            db: Database session
            user_id: KIWIQ user UUID
            commit: Whether to commit the transaction
            
        Returns:
            True if unlinked, False if no record found
        """
        try:
            oauth_record = await self.get_by_user_id(db, user_id)
            if oauth_record:
                await db.delete(oauth_record)
                if commit:
                    await db.commit()
                logger.info(f"Unlinked LinkedIn OAuth from user {user_id}")
                return True
            return False
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error unlinking LinkedIn OAuth: {e}")
            raise
    
    async def update_tokens(
        self,
        db: AsyncSession,
        linkedin_id: str,
        access_token: str,
        refresh_token: Optional[str],
        expires_in: int,
        refresh_token_expires_in: Optional[int],
        commit: bool = True
    ) -> Optional[models.LinkedinUserOauth]:
        """
        Update OAuth tokens for a LinkedIn account.
        
        This method is used for token refresh operations and updates
        both the tokens and their expiration timestamps.
        
        Args:
            db: Database session
            linkedin_id: LinkedIn user ID (sub)
            access_token: New access token
            refresh_token: New refresh token (if provided)
            expires_in: Access token expiration in seconds
            refresh_token_expires_in: Refresh token expiration in seconds
            commit: Whether to commit the transaction
            
        Returns:
            Updated LinkedinUserOauth record or None if not found
        """
        return await self.create_or_update(
            db,
            linkedin_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            refresh_token_expires_in=refresh_token_expires_in,
            commit=commit,
            create=False,
        )
    
    async def update_state(
        self,
        db: AsyncSession,
        linkedin_id: str,
        oauth_state: models.LinkedinOauthState,
        state_metadata: Optional[dict] = None,
        commit: bool = True
    ) -> Optional[models.LinkedinUserOauth]:
        """Update the OAuth state for a LinkedIn connection"""
        try:
            oauth_record = await self.get(db, linkedin_id)
            if oauth_record:
                oauth_record.oauth_state = oauth_state
                oauth_record.state_metadata = state_metadata
                    
                db.add(oauth_record)
                if commit:
                    await db.commit()
                    await db.refresh(oauth_record)
                
                logger.info(f"Updated OAuth state to {oauth_state} for LinkedIn ID {linkedin_id}")
                return oauth_record
            return None
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error updating OAuth state: {e}")
            raise
    
    async def get_expiring_tokens(
        self,
        db: AsyncSession,
        hours_ahead: int = 24
    ) -> List[models.LinkedinUserOauth]:
        """
        Get OAuth records with tokens expiring within specified hours.
        
        This method is useful for proactive token refresh operations
        to prevent API call failures due to expired tokens.
        
        Args:
            db: Database session
            hours_ahead: Number of hours to look ahead
            
        Returns:
            List of LinkedinUserOauth records with expiring tokens
        """
        try:
            expiry_threshold = datetime_now_utc() + timedelta(hours=hours_ahead)
            
            statement = select(self.model).where(
                and_(
                    self.model.token_expires_at.isnot(None),
                    self.model.token_expires_at <= expiry_threshold,
                    self.model.token_expires_at > datetime_now_utc()
                )
            )
            
            result = await db.execute(statement)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting expiring tokens: {e}")
            raise
    
    async def get_by_user_ids(
        self,
        db: AsyncSession,
        user_ids: List[uuid.UUID]
    ) -> List[models.LinkedinUserOauth]:
        """
        Get LinkedIn OAuth records for multiple users.
        
        Args:
            db: Database session
            user_ids: List of KIWIQ user UUIDs
            
        Returns:
            List of LinkedinUserOauth records
        """
        try:
            statement = select(self.model).where(self.model.user_id.in_(user_ids))
            result = await db.execute(statement)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting LinkedIn OAuth records by user IDs: {e}")
            raise
    
    async def count_by_organization(
        self,
        db: AsyncSession,
        org_id: uuid.UUID
    ) -> int:
        """
        Count LinkedIn connections within an organization.
        
        This method joins with the user and user_organization_role tables
        to count how many users in an organization have LinkedIn connected.
        
        Args:
            db: Database session
            org_id: Organization UUID
            
        Returns:
            Number of LinkedIn connections in the organization
        """
        try:
            from kiwi_app.auth.models import User, UserOrganizationRole
            
            statement = (
                select(func.count(self.model.id))
                .join(User, User.id == self.model.user_id)
                .join(UserOrganizationRole, UserOrganizationRole.user_id == User.id)
                .where(UserOrganizationRole.organization_id == org_id)
            )
            
            result = await db.execute(statement)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting LinkedIn connections by organization: {e}")
            raise
    
    async def mark_token_as_expired(
        self,
        db: AsyncSession,
        linkedin_id: str,
        commit: bool = True
    ) -> bool:
        """
        Mark a LinkedIn OAuth token as expired.
        
        This is used when we detect an expired token during API calls
        to prevent further failed attempts.
        
        Args:
            db: Database session
            linkedin_id: LinkedIn user ID (sub)
            commit: Whether to commit the transaction
            
        Returns:
            True if marked as expired, False if not found
        """
        try:
            oauth_record = await self.get(db, linkedin_id)
            if oauth_record:
                # Set expiration to past time to force refresh
                oauth_record.token_expires_at = datetime_now_utc() - timedelta(minutes=1)
                oauth_record.updated_at = datetime_now_utc()
                
                db.add(oauth_record)
                if commit:
                    await db.commit()
                
                logger.info(f"Marked token as expired for LinkedIn ID {linkedin_id}")
                return True
            return False
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error marking token as expired: {e}")
            raise
    
    async def get_by_state(
        self,
        db: AsyncSession,
        oauth_state: models.LinkedinOauthState,
        limit: Optional[int] = None
    ) -> List[models.LinkedinUserOauth]:
        """Get all OAuth records with a specific state"""
        statement = select(self.model).where(
            self.model.oauth_state == oauth_state
        )
        
        if limit:
            statement = statement.limit(limit)
        
        result = await db.execute(statement)
        return result.scalars().all()
    
    async def get_pending_verifications(
        self,
        db: AsyncSession,
        hours_old: int = 24
    ) -> List[models.LinkedinUserOauth]:
        """Get OAuth records that are stuck in verification state"""
        cutoff_time = datetime_now_utc() - timedelta(hours=hours_old)
        
        statement = select(self.model).where(
            and_(
                self.model.oauth_state == models.LinkedinOauthState.VERIFICATION_REQUIRED,
                self.model.created_at <= cutoff_time
            )
        )
        
        result = await db.execute(statement)
        return result.scalars().all()
    
    async def mark_expired_tokens(
        self,
        db: AsyncSession,
        commit: bool = True
    ) -> int:
        """Mark OAuth records with expired tokens as EXPIRED state"""
        try:
            # Get all active records with expired tokens
            statement = select(self.model).where(
                and_(
                    self.model.oauth_state == models.LinkedinOauthState.ACTIVE,
                    self.model.token_expires_at.isnot(None),
                    self.model.token_expires_at <= datetime_now_utc()
                )
            )
            
            result = await db.execute(statement)
            expired_records = result.scalars().all()
            
            count = 0
            for record in expired_records:
                # Check if we can refresh
                if record.refresh_token and not record.is_refresh_token_expired():
                    # Keep as ACTIVE, will be refreshed on next use
                    continue
                else:
                    # Mark as EXPIRED
                    record.oauth_state = models.LinkedinOauthState.EXPIRED
                    record.state_metadata = {
                        "reason": "access_token_expired",
                        "expired_at": datetime_now_utc().isoformat()
                    }
                    db.add(record)
                    count += 1
            
            if commit and count > 0:
                await db.commit()
            
            logger.info(f"Marked {count} OAuth records as expired")
            return count
            
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error marking expired tokens: {e}")
            raise
    
    async def get_organization_linkedin_connections(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        active_only: bool = True
    ) -> List[models.LinkedinUserOauth]:
        """Get all LinkedIn connections for users in an organization"""
        from kiwi_app.auth.models import User, UserOrganizationRole
        
        statement = select(self.model).join(
            User, self.model.user_id == User.id
        ).join(
            UserOrganizationRole, User.id == UserOrganizationRole.user_id
        ).where(
            UserOrganizationRole.organization_id == organization_id
        )
        
        if active_only:
            statement = statement.where(
                self.model.oauth_state == models.LinkedinOauthState.ACTIVE
            )
        
        result = await db.execute(statement)
        return result.scalars().all()
    
    async def admin_delete_by_linkedin_id(
        self,
        db: AsyncSession,
        linkedin_id: str,
        commit: bool = True
    ) -> bool:
        """
        Admin method to delete LinkedIn OAuth record by LinkedIn ID.
        
        This method is for administrative purposes and includes detailed logging
        for audit purposes. It permanently removes the OAuth connection.
        
        Args:
            db: Database session
            linkedin_id: LinkedIn user ID (sub)
            commit: Whether to commit the transaction
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            Exception: For database errors
        """
        try:
            oauth_record = await self.get(db, linkedin_id)
            if oauth_record:
                # Get user info for logging before deletion
                user_info = f"user_id={oauth_record.user_id}" if oauth_record.user_id else "no_user_linked"
                
                await db.delete(oauth_record)
                if commit:
                    await db.commit()
                
                logger.warning(f"ADMIN: Deleted LinkedIn OAuth record {linkedin_id} ({user_info})")
                return True
            
            logger.info(f"ADMIN: LinkedIn OAuth record {linkedin_id} not found for deletion")
            return False
            
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"ADMIN: Error deleting LinkedIn OAuth by LinkedIn ID {linkedin_id}: {e}")
            raise
    
    async def admin_delete_by_user_id(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        commit: bool = True
    ) -> bool:
        """
        Admin method to delete LinkedIn OAuth record by KIWIQ user ID.
        
        This method is for administrative purposes and includes detailed logging
        for audit purposes. It permanently removes the OAuth connection for a user.
        
        Args:
            db: Database session
            user_id: KIWIQ user UUID
            commit: Whether to commit the transaction
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            Exception: For database errors
        """
        try:
            oauth_record = await self.get_by_user_id(db, user_id)
            if oauth_record:
                linkedin_id = oauth_record.id
                
                await db.delete(oauth_record)
                if commit:
                    await db.commit()
                
                logger.warning(f"ADMIN: Deleted LinkedIn OAuth record for user {user_id} (linkedin_id={linkedin_id})")
                return True
            
            logger.info(f"ADMIN: No LinkedIn OAuth record found for user {user_id}")
            return False
            
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"ADMIN: Error deleting LinkedIn OAuth by user ID {user_id}: {e}")
            raise
    
    async def admin_get_all_oauth_records(
        self,
        db: AsyncSession,
        limit: Optional[int] = 100,
        offset: int = 0,
        include_user_info: bool = False
    ) -> List[models.LinkedinUserOauth]:
        """
        Admin method to get all LinkedIn OAuth records with pagination.
        
        This method is for administrative overview and includes optional
        user information joining.
        
        Args:
            db: Database session
            limit: Maximum number of records to return
            offset: Number of records to skip
            include_user_info: Whether to include user relationship data
            
        Returns:
            List of LinkedinUserOauth records
        """
        try:
            statement = select(self.model)
            
            if include_user_info:
                from kiwi_app.auth.models import User
                statement = statement.options(selectinload(self.model.user))
            
            if limit:
                statement = statement.limit(limit)
            
            statement = statement.offset(offset)
            
            result = await db.execute(statement)
            records = result.scalars().all()
            
            logger.info(f"ADMIN: Retrieved {len(records)} LinkedIn OAuth records (limit={limit}, offset={offset})")
            return records
            
        except Exception as e:
            logger.error(f"ADMIN: Error retrieving LinkedIn OAuth records: {e}")
            raise


class LinkedinIntegrationDAO(BaseDAO[models.LinkedinIntegration, None, None]):
    """
    Data Access Object for LinkedIn Integration operations.
    
    This DAO handles database operations for LinkedIn integrations that users
    add to manage multiple LinkedIn accounts (separate from OAuth login).
    """
    
    def __init__(self):
        super().__init__(models.LinkedinIntegration)
    
    async def get_by_user_and_linkedin_id(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        linkedin_id: str
    ) -> Optional[models.LinkedinIntegration]:
        """Get integration by user ID and LinkedIn ID."""
        try:
            statement = select(self.model).where(
                and_(
                    self.model.user_id == user_id,
                    self.model.linkedin_id == linkedin_id
                )
            )
            result = await db.execute(statement)
            return result.scalars().first()
        except Exception as e:
            logger.error(f"Error getting integration for user {user_id}, linkedin {linkedin_id}: {e}")
            raise
    
    async def get_by_user_id(
        self,
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> List[models.LinkedinIntegration]:
        """Get all integrations for a user."""
        try:
            statement = select(self.model).where(self.model.user_id == user_id)
            result = await db.execute(statement)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting integrations for user {user_id}: {e}")
            raise
    
    async def create_integration(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        linkedin_id: str,
        access_token: str,
        refresh_token: Optional[str],
        scope: str,
        expires_in: int,
        refresh_token_expires_in: Optional[int],
        linkedin_orgs_roles: Optional[dict] = None,
        commit: bool = True
    ) -> models.LinkedinIntegration:
        """Create a new LinkedIn integration."""
        try:
            integration = models.LinkedinIntegration(
                user_id=user_id,
                linkedin_id=linkedin_id,
                access_token=access_token,
                refresh_token=refresh_token,
                scope=scope,
                expires_in=expires_in,
                refresh_token_expires_in=refresh_token_expires_in,
                linkedin_orgs_roles=linkedin_orgs_roles,
                integration_state=models.LinkedinOauthState.ACTIVE,
                last_sync_at=datetime_now_utc()
            )
            integration.update_expiration_timestamps()
            
            db.add(integration)
            if commit:
                await db.commit()
                await db.refresh(integration)
            
            logger.info(f"Created LinkedIn integration {integration.id} for user {user_id}")
            return integration
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error creating LinkedIn integration: {e}")
            raise
    
    async def update_tokens(
        self,
        db: AsyncSession,
        integration_id: uuid.UUID,
        access_token: str,
        refresh_token: Optional[str],
        expires_in: int,
        refresh_token_expires_in: Optional[int],
        commit: bool = True
    ) -> Optional[models.LinkedinIntegration]:
        """Update tokens for an integration."""
        try:
            integration = await self.get(db, integration_id)
            if not integration:
                return None
            
            integration.access_token = access_token
            if refresh_token:
                integration.refresh_token = refresh_token
            integration.expires_in = expires_in
            integration.refresh_token_expires_in = refresh_token_expires_in
            integration.update_expiration_timestamps()
            integration.last_sync_at = datetime_now_utc()
            
            db.add(integration)
            if commit:
                await db.commit()
                await db.refresh(integration)
            
            return integration
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error updating integration tokens: {e}")
            raise
    
    async def update_linkedin_orgs_roles(
        self,
        db: AsyncSession,
        integration_id: uuid.UUID,
        linkedin_orgs_roles: dict,
        commit: bool = True
    ) -> Optional[models.LinkedinIntegration]:
        """Update LinkedIn organizations and roles data."""
        try:
            integration = await self.get(db, integration_id)
            if not integration:
                return None
            
            integration.linkedin_orgs_roles = linkedin_orgs_roles
            integration.last_sync_at = datetime_now_utc()
            
            db.add(integration)
            if commit:
                await db.commit()
                await db.refresh(integration)
            
            return integration
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error updating LinkedIn orgs/roles: {e}")
            raise
    
    async def update_state(
        self,
        db: AsyncSession,
        integration_id: uuid.UUID,
        integration_state: models.LinkedinOauthState,
        commit: bool = True
    ) -> Optional[models.LinkedinIntegration]:
        """Update integration state."""
        try:
            integration = await self.get(db, integration_id)
            if not integration:
                return None
            
            integration.integration_state = integration_state.value
            
            db.add(integration)
            if commit:
                await db.commit()
                await db.refresh(integration)
            
            return integration
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error updating integration state: {e}")
            raise


class LinkedinAccountDAO(BaseDAO[models.LinkedinAccount, None, None]):
    """
    Data Access Object for LinkedIn Account operations.
    
    This DAO handles database operations for LinkedIn accounts (persons or organizations).
    """
    
    def __init__(self):
        super().__init__(models.LinkedinAccount)
    
    async def create_or_update(
        self,
        db: AsyncSession,
        linkedin_id: str,
        account_type: str,
        name: Optional[str] = None,
        vanity_name: Optional[str] = None,
        profile_data: Optional[dict] = None,
        commit: bool = True
    ) -> models.LinkedinAccount:
        """Create or update a LinkedIn account."""
        try:
            existing = await self.get(db, linkedin_id)
            
            if existing:
                # Update existing
                if name:
                    existing.name = name
                if vanity_name is not None:
                    existing.vanity_name = vanity_name
                if profile_data:
                    existing.profile_data = profile_data
                existing.last_updated_at = datetime_now_utc()
                
                db.add(existing)
                if commit:
                    await db.commit()
                    await db.refresh(existing)
                
                return existing
            else:
                # Create new
                account = models.LinkedinAccount(
                    id=linkedin_id,
                    account_type=account_type,
                    name=name,
                    vanity_name=vanity_name,
                    profile_data=profile_data,
                    last_updated_at=datetime_now_utc()
                )
                
                db.add(account)
                if commit:
                    await db.commit()
                    await db.refresh(account)
                
                logger.info(f"Created LinkedIn account {linkedin_id} ({account_type})")
                return account
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error creating/updating LinkedIn account: {e}")
            raise
    
    async def update(
        self,
        db: AsyncSession,
        linkedin_id: str,
        name: Optional[str] = None,
        vanity_name: Optional[str] = None,
        profile_data: Optional[dict] = None,
        commit: bool = True
    ) -> Optional[models.LinkedinAccount]:
        """Update a LinkedIn account."""
        try:
            account = await self.get(db, linkedin_id)
            if not account:
                return None
            
            if name is not None:
                account.name = name
            if vanity_name is not None:
                account.vanity_name = vanity_name
            if profile_data is not None:
                account.profile_data = profile_data
            account.last_updated_at = datetime_now_utc()
            
            db.add(account)
            if commit:
                await db.commit()
                await db.refresh(account)
            
            return account
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error updating LinkedIn account {linkedin_id}: {e}")
            raise
    
    async def get_by_type(
        self,
        db: AsyncSession,
        account_type: str
    ) -> List[models.LinkedinAccount]:
        """Get all accounts of a specific type."""
        try:
            statement = select(self.model).where(self.model.account_type == account_type)
            result = await db.execute(statement)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting accounts by type {account_type}: {e}")
            raise


class OrgLinkedinAccountDAO(BaseDAO[models.OrgLinkedinAccount, None, None]):
    """
    Data Access Object for Org LinkedIn Account operations.
    
    This DAO handles database operations for LinkedIn accounts shared within organizations.
    """
    
    def __init__(self):
        super().__init__(models.OrgLinkedinAccount)
    
    async def create_org_linkedin_account(
        self,
        db: AsyncSession,
        linkedin_account_id: str,
        linkedin_integration_id: uuid.UUID,
        managed_by_user_id: uuid.UUID,
        organization_id: uuid.UUID,
        role_in_linkedin_entity: Optional[str] = None,
        is_shared: bool = True,
        commit: bool = True
    ) -> models.OrgLinkedinAccount:
        """Create a new org LinkedIn account."""
        try:
            org_account = models.OrgLinkedinAccount(
                linkedin_account_id=linkedin_account_id,
                linkedin_integration_id=linkedin_integration_id,
                managed_by_user_id=managed_by_user_id,
                organization_id=organization_id,
                role_in_linkedin_entity=role_in_linkedin_entity,
                is_shared=is_shared,
                is_active=True,
                status=models.OrgLinkedinAccountStatus.ACTIVE
            )
            
            db.add(org_account)
            if commit:
                await db.commit()
                await db.refresh(org_account)
            
            logger.info(f"Created org LinkedIn account {org_account.id} for org {organization_id}")
            return org_account
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error creating org LinkedIn account: {e}")
            raise
    
    async def get_by_organization(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        active_only: bool = True,
        shared_only: bool = True
    ) -> List[models.OrgLinkedinAccount]:
        """Get all LinkedIn accounts for an organization."""
        try:
            statement = select(self.model).where(
                self.model.organization_id == organization_id
            )
            
            if active_only:
                statement = statement.where(self.model.is_active == True)
            
            if shared_only:
                statement = statement.where(self.model.is_shared == True)
            
            result = await db.execute(statement)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting org LinkedIn accounts: {e}")
            raise
    
    async def get_by_user_in_org(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        organization_id: uuid.UUID
    ) -> List[models.OrgLinkedinAccount]:
        """Get LinkedIn accounts managed by a specific user in an organization."""
        try:
            statement = select(self.model).where(
                and_(
                    self.model.managed_by_user_id == user_id,
                    self.model.organization_id == organization_id
                )
            )
            result = await db.execute(statement)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting user's org LinkedIn accounts: {e}")
            raise
    
    async def update_sharing_status(
        self,
        db: AsyncSession,
        org_account_id: uuid.UUID,
        is_shared: bool,
        commit: bool = True
    ) -> Optional[models.OrgLinkedinAccount]:
        """Update the sharing status of an org LinkedIn account."""
        try:
            org_account = await self.get(db, org_account_id)
            if not org_account:
                return None
            
            org_account.is_shared = is_shared
            
            db.add(org_account)
            if commit:
                await db.commit()
                await db.refresh(org_account)
            
            return org_account
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error updating sharing status: {e}")
            raise
    
    async def deactivate_by_integration(
        self,
        db: AsyncSession,
        integration_id: uuid.UUID,
        commit: bool = True
    ) -> int:
        """Deactivate all org accounts using a specific integration."""
        try:
            statement = update(self.model).where(
                self.model.linkedin_integration_id == integration_id
            ).values(is_active=False)
            
            result = await db.execute(statement)
            if commit:
                await db.commit()
            
            count = result.rowcount
            logger.info(f"Deactivated {count} org LinkedIn accounts for integration {integration_id}")
            return count
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error deactivating org accounts: {e}")
            raise
    
    async def get_by_integration(
        self,
        db: AsyncSession,
        integration_id: uuid.UUID
    ) -> List[models.OrgLinkedinAccount]:
        """Get all org LinkedIn accounts using a specific integration."""
        try:
            statement = select(self.model).where(
                self.model.linkedin_integration_id == integration_id
            )
            result = await db.execute(statement)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting org accounts by integration: {e}")
            raise
    
    async def delete_org_linkedin_account(
        self,
        db: AsyncSession,
        org_account_id: uuid.UUID,
        commit: bool = True
    ) -> bool:
        """
        Delete an org LinkedIn account.
        
        Args:
            db: Database session
            org_account_id: ID of the org LinkedIn account to delete
            commit: Whether to commit the transaction
            
        Returns:
            True if deleted, False if not found
        """
        try:
            org_account = await self.get(db, org_account_id)
            if not org_account:
                return False
            
            await db.delete(org_account)
            
            if commit:
                await db.commit()
            
            logger.info(f"Deleted org LinkedIn account {org_account_id}")
            return True
        except Exception as e:
            if commit:
                await db.rollback()
            logger.error(f"Error deleting org LinkedIn account: {e}")
            raise 