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