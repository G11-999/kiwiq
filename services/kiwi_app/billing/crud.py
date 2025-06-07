"""
Billing CRUD operations for KiwiQ system.

This module defines Data Access Objects (DAOs) for billing-related database operations,
following KiwiQ's established patterns for CRUD operations with dependency injection.
"""

import uuid
from typing import Optional, List, Sequence, Dict, Any, Union
from datetime import datetime, timedelta, date

import sqlalchemy as sa
from sqlalchemy import delete, update, and_, or_, func, desc, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import SQLModel

from global_utils import datetime_now_utc
from kiwi_app.utils import get_kiwi_logger
from kiwi_app.auth.base_crud import BaseDAO
from kiwi_app.billing.models import CreditType, SubscriptionStatus, CreditSourceType, PaymentStatus
from kiwi_app.billing.exceptions import InsufficientCreditsException
from kiwi_app.billing import models, schemas
from kiwi_app.settings import settings

# Get logger for billing operations
billing_logger = get_kiwi_logger(name="kiwi_app.billing.crud")


class SubscriptionPlanDAO(BaseDAO[models.SubscriptionPlan, schemas.SubscriptionPlanCreate, schemas.SubscriptionPlanUpdate]):
    """Data Access Object for subscription plan operations."""
    
    def __init__(self):
        super().__init__(models.SubscriptionPlan)
    
    async def get_by_stripe_product_id(self, db: AsyncSession, stripe_product_id: str) -> Optional[models.SubscriptionPlan]:
        """Get subscription plan by Stripe product ID."""
        statement = select(self.model).where(self.model.stripe_product_id == stripe_product_id)
        result = await db.exec(statement)
        return result.scalars().first()
    
    async def get_by_name(self, db: AsyncSession, name: str) -> Optional[models.SubscriptionPlan]:
        """Get subscription plan by name."""
        statement = select(self.model).where(self.model.name == name)
        result = await db.exec(statement)
        return result.scalars().first()
    
    async def get_active_plans(self, db: AsyncSession) -> Sequence[models.SubscriptionPlan]:
        """Get all active subscription plans."""
        statement = select(self.model).where(self.model.is_active == True).order_by(self.model.monthly_price)
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def get_trial_eligible_plans(self, db: AsyncSession) -> Sequence[models.SubscriptionPlan]:
        """Get all plans that support trial periods."""
        statement = select(self.model).where(
            and_(self.model.is_active == True, self.model.is_trial_eligible == True)
        ).order_by(self.model.monthly_price)
        result = await db.exec(statement)
        return result.scalars().all()


class OrganizationSubscriptionDAO(BaseDAO[models.OrganizationSubscription, schemas.SubscriptionCreate, schemas.SubscriptionUpdate]):
    """Data Access Object for organization subscription operations."""
    
    def __init__(self):
        super().__init__(models.OrganizationSubscription)
    
    async def create(
        self, 
        db: AsyncSession, 
        obj_in: Union[schemas.SubscriptionCreate, models.OrganizationSubscription],
        commit: bool = True
    ) -> models.OrganizationSubscription:
        """
        Create a new organization subscription.
        
        This method handles both schema and model instances. When a model instance
        is provided, it preserves all fields including org_id which is not present
        in the SubscriptionCreate schema.
        """
        if isinstance(obj_in, models.OrganizationSubscription):
            # Direct model instance - preserve all fields
            db_obj = obj_in
        else:
            # Schema instance - create model from schema
            obj_data = obj_in.model_dump(exclude_unset=True)
            db_obj = self.model(**obj_data)
        
        db.add(db_obj)
        if commit:
            await db.commit()
            await db.refresh(db_obj)
        return db_obj
    
    async def get_by_org_id(self, db: AsyncSession, org_id: uuid.UUID) -> List[models.OrganizationSubscription]:
        """Get active subscription for an organization."""
        statement = select(self.model).options(
            selectinload(self.model.plan)
        ).where(self.model.org_id == org_id)
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def get_by_stripe_subscription_id(self, db: AsyncSession, stripe_subscription_id: str) -> Optional[models.OrganizationSubscription]:
        """Get subscription by Stripe subscription ID."""
        statement = select(self.model).options(
            selectinload(self.model.plan)
        ).where(self.model.stripe_subscription_id == stripe_subscription_id)
        result = await db.exec(statement)
        return result.scalars().first()
    
    # async def get_by_stripe_customer_id(self, db: AsyncSession, stripe_customer_id: str) -> Optional[models.OrganizationSubscription]:
    #     """Get subscription by Stripe customer ID using organization's external_billing_id."""
    #     from kiwi_app.auth.models import Organization
        
    #     statement = select(self.model).options(
    #         selectinload(self.model.plan)
    #     ).join(Organization).where(Organization.external_billing_id == stripe_customer_id)
    #     result = await db.exec(statement)
    #     return result.scalars().first()
    
    async def get_active_subscriptions(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> Sequence[models.OrganizationSubscription]:
        """Get all active subscriptions."""
        statement = select(self.model).options(
            selectinload(self.model.plan)
        ).where(self.model.status == SubscriptionStatus.ACTIVE).offset(skip).limit(limit)
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def get_trial_subscriptions(self, db: AsyncSession) -> Sequence[models.OrganizationSubscription]:
        """Get all trial subscriptions."""
        statement = select(self.model).options(
            selectinload(self.model.plan)
        ).where(self.model.is_trial_active == True)
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def get_expiring_trials(self, db: AsyncSession, days_ahead: int = 3) -> Sequence[models.OrganizationSubscription]:
        """Get trials expiring within specified days."""
        cutoff_date = datetime_now_utc() + timedelta(days=days_ahead)
        statement = select(self.model).options(
            selectinload(self.model.plan)
        ).where(
            and_(
                self.model.is_trial_active == True,
                self.model.trial_end <= cutoff_date
            )
        )
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def get_total_seat_count_for_org(self, db: AsyncSession, org_id: uuid.UUID) -> int:
        """
        Get the total number of seats across all subscriptions for an organization.
        
        This method sums up the seat counts from all subscriptions (active, trial, etc.)
        for the specified organization. Returns 0 if no subscriptions exist.
        
        The query uses SQL aggregation with COALESCE to handle the case where no
        subscriptions exist, ensuring we always return 0 instead of NULL.
        
        Args:
            db: Database session
            org_id: Organization ID
            
        Returns:
            Total number of seats across all subscriptions, 0 if no subscriptions
            
        Example:
            # Organization with 2 subscriptions: one with 5 seats, one with 3 seats
            total_seats = await dao.get_total_seat_count_for_org(db, org_id)
            # Returns: 8
            
            # Organization with no subscriptions
            total_seats = await dao.get_total_seat_count_for_org(db, org_id)
            # Returns: 0
        """
        try:
            # Use a single aggregation query to sum all seat counts for the organization
            statement = select(func.coalesce(func.sum(self.model.seats_count), 0)).where(
                self.model.org_id == org_id
            )
            
            result = await db.exec(statement)
            total_seats = result.scalar()
            
            billing_logger.debug(f"Total seat count for org {org_id}: {total_seats}")
            return int(total_seats or 0)
            
        except Exception as e:
            billing_logger.error(f"Error getting total seat count for org {org_id}: {e}", exc_info=True)
            raise


class OrganizationCreditsDAO(BaseDAO[models.OrganizationCredits, SQLModel, SQLModel]):
    """
    Data Access Object for organization credits audit records.
    
    This DAO handles the audit trail records in OrganizationCredits table,
    which track individual credit allocations from different sources.
    """
    
    def __init__(self):
        super().__init__(models.OrganizationCredits)
    
    async def get_by_org_and_type(
        self, 
        db: AsyncSession, 
        org_id: uuid.UUID, 
        credit_type: CreditType,
        include_expired: bool = False,
        expiry_datetime: Optional[datetime] = None
    ) -> Sequence[models.OrganizationCredits]:
        """Get all credit records for an organization by type."""
        conditions = [
            self.model.org_id == org_id,
            self.model.credit_type == credit_type
        ]
        
        if not include_expired:
            # Check both is_expired flag and actual expiration datetime
            conditions.extend([
                self.model.is_expired == False,
                or_(
                    self.model.expires_at.is_(None),
                    self.model.expires_at > (expiry_datetime or datetime_now_utc())
                )
            ])
        
        statement = select(self.model).where(and_(*conditions)).order_by(self.model.expires_at.asc())
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def get_active_credits_summary(self, db: AsyncSession, org_id: uuid.UUID) -> Dict[str, Dict[str, float]]:
        """Get summary of active credits by type for an organization."""
        now = datetime_now_utc()
        statement = select(
            self.model.credit_type,
            func.sum(self.model.credits_granted).label('total_granted')
        ).where(
            and_(
                self.model.org_id == org_id,
                self.model.is_expired == False,
                or_(
                    self.model.expires_at.is_(None),
                    self.model.expires_at > now
                )
            )
        ).group_by(self.model.credit_type)
        
        result = await db.exec(statement)
        summary = {}
        
        for row in result:
            summary[row.credit_type.value] = {
                'granted': float(row.total_granted or 0)
            }
        
        return summary
    
    async def get_expiring_credits(
        self, 
        db: AsyncSession, 
        org_id: uuid.UUID, 
        days_ahead: int = 7
    ) -> Sequence[models.OrganizationCredits]:
        """Get credits expiring within specified days."""
        cutoff_date = datetime_now_utc() + timedelta(days=days_ahead)
        now = datetime_now_utc()
        statement = select(self.model).where(
            and_(
                self.model.org_id == org_id,
                self.model.is_expired == False,
                self.model.expires_at.is_not(None),
                self.model.expires_at > now,
                self.model.expires_at <= cutoff_date,
                self.model.credits_granted > 0
            )
        ).order_by(self.model.expires_at.asc())
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def get_expiring_credits_by_cutoff(
        self,
        db: AsyncSession,
        org_id: Optional[uuid.UUID] = None,
        cutoff_datetime: Optional[datetime] = None
    ) -> Sequence[models.OrganizationCredits]:
        """
        Get all expiring credits based on cutoff datetime.
        
        Args:
            db: Database session
            org_id: Organization ID (None for all organizations)
            cutoff_datetime: Cutoff datetime for expiration (defaults to current time)
            
        Returns:
            Sequence of expiring credit records
        """
        if cutoff_datetime is None:
            cutoff_datetime = datetime_now_utc()
        
        conditions = [
            self.model.is_expired == False,
            self.model.expires_at.is_not(None),
            self.model.expires_at <= cutoff_datetime
        ]
        
        if org_id:
            conditions.append(self.model.org_id == org_id)
        
        statement = select(self.model).where(and_(*conditions))
        result = await db.execute(statement)
        return result.scalars().all()
    
    async def mark_credits_expired_by_cutoff(
        self,
        db: AsyncSession,
        org_id: Optional[uuid.UUID] = None,
        cutoff_datetime: Optional[datetime] = None,
        credit_type: Optional[CreditType] = None
    ) -> int:
        """
        Mark credits as expired based on cutoff datetime.
        
        Args:
            db: Database session
            org_id: Organization ID (None for all organizations)
            cutoff_datetime: Cutoff datetime for expiration
            credit_type: Credit type to filter by (None for all types)
            
        Returns:
            Number of credit records updated
        """
        if cutoff_datetime is None:
            cutoff_datetime = datetime_now_utc()
        
        conditions = [
            self.model.is_expired == False,
            self.model.expires_at.is_not(None),
            self.model.expires_at <= cutoff_datetime
        ]
        
        if org_id:
            conditions.append(self.model.org_id == org_id)
        
        if credit_type:
            conditions.append(self.model.credit_type == credit_type)
        
        update_query = (
            update(models.OrganizationCredits)
            .where(and_(*conditions))
            .values(
                is_expired=True,
                # updated_at=func.now()
            )
        )
        
        result = await db.execute(update_query)
        return result.rowcount
    
    async def get_subscription_credits_by_subscription_id(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        subscription_id: uuid.UUID,
        include_expired: bool = False
    ) -> Sequence[models.OrganizationCredits]:
        """
        Get all credits allocated from a specific subscription.
        
        Args:
            db: Database session
            org_id: Organization ID
            subscription_id: Subscription ID
            include_expired: Whether to include expired credits
            
        Returns:
            Sequence of credit records from the subscription
        """
        conditions = [
            self.model.org_id == org_id,
            self.model.source_type == CreditSourceType.SUBSCRIPTION,
            self.model.source_id == str(subscription_id)
        ]
        
        if not include_expired:
            conditions.append(self.model.is_expired == False)
        
        statement = select(self.model).where(and_(*conditions))
        result = await db.execute(statement)
        return result.scalars().all()
    
    async def mark_subscription_credits_expired(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        subscription_id: uuid.UUID
    ) -> int:
        """
        Mark all existing subscription credits as expired for a specific subscription.
        
        Args:
            db: Database session
            org_id: Organization ID
            subscription_id: Subscription ID
            
        Returns:
            Number of credit records updated
        """
        update_query = (
            update(models.OrganizationCredits)
            .where(
                and_(
                    self.model.org_id == org_id,
                    self.model.source_type == CreditSourceType.SUBSCRIPTION,
                    self.model.source_id == str(subscription_id),
                    self.model.is_expired == False
                )
            )
            .values(
                is_expired=True,
                # updated_at=func.now()
            )
        )
        
        result = await db.execute(update_query)
        return result.rowcount
    
    async def allocate_credits(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_type: CreditType,
        amount: float,
        source_type: CreditSourceType,
        source_id: Optional[str] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
        period_start: Optional[datetime] = None,
        commit: bool = True,
    ) -> models.OrganizationCredits:
        """
        Create an audit record for credit allocation.
        
        This method only creates the audit trail record. The actual net credits
        are managed by OrganizationNetCreditsDAO.
        """
        try:
            now = datetime_now_utc()
            
            # Create audit record in OrganizationCredits table
            credit_record = models.OrganizationCredits(
                org_id=org_id,
                credit_type=credit_type,
                credits_granted=amount,
                source_type=source_type,
                source_id=source_id,
                source_metadata=source_metadata or {},
                expires_at=expires_at,
                is_expired=False,
                period_start=period_start or now,
                created_at=now,
                updated_at=now
            )
            
            db.add(credit_record)
            if commit:
                await db.commit()
                await db.refresh(credit_record)
            
            billing_logger.info(
                f"Created audit record for {amount} {credit_type.value} credits "
                f"for org {org_id} from source {source_type.value} (ID: {source_id})"
            )
            
            return credit_record
            
        except Exception as e:
            billing_logger.error(f"Error creating credit allocation audit record: {e}", exc_info=True)
            raise


class OrganizationNetCreditsDAO(BaseDAO[models.OrganizationNetCredits, SQLModel, SQLModel]):
    """
    Data Access Object for organization net credits with atomic operations.
    
    This DAO implements high-performance credit consumption using atomic
    UPDATE queries with race-condition safety for maximum scalability.
    """
    
    def __init__(self):
        super().__init__(models.OrganizationNetCredits)
    
    async def get_net_credits_by_org_and_type(
        self, 
        db: AsyncSession, 
        org_id: uuid.UUID, 
        credit_type: CreditType
    ) -> Optional[models.OrganizationNetCredits]:
        """
        Get net credits for an organization by credit type.
        
        This method handles potential duplicate records by selecting the most
        recent record if duplicates exist (which should not happen but could
        occur during race conditions or data migrations).
        
        Args:
            db: Database session
            org_id: Organization ID
            credit_type: Type of credits
            
        Returns:
            OrganizationNetCredits record or None if not found
        """
        try:
            query = (
                select(models.OrganizationNetCredits)
                .where(
                    models.OrganizationNetCredits.org_id == org_id,
                    models.OrganizationNetCredits.credit_type == credit_type
                )
                .order_by(models.OrganizationNetCredits.updated_at.desc())
            )
            result = await db.execute(query)
            records = result.scalars().all()
            
            if not records:
                return None
            
            if len(records) > 1:
                # Log warning about duplicate records
                billing_logger.warning(
                    f"Found {len(records)} duplicate net credits records for org {org_id}, "
                    f"credit_type {credit_type}. Using most recent record. "
                    f"This indicates a data consistency issue that should be investigated."
                )
                
                # Clean up duplicates by keeping the most recent record
                primary_record = records[0]  # Most recent due to ordering
                duplicate_ids = [record.id for record in records[1:]]
                
                # Delete duplicates
                delete_stmt = delete(models.OrganizationNetCredits).where(
                    models.OrganizationNetCredits.id.in_(duplicate_ids)
                )
                await db.execute(delete_stmt)
                await db.commit()
                
                billing_logger.info(
                    f"Cleaned up {len(duplicate_ids)} duplicate net credits records "
                    f"for org {org_id}, credit_type {credit_type}"
                )
                
                return primary_record
            
            return records[0]
            
        except Exception as e:
            billing_logger.error(f"Error getting net credits: {e}", exc_info=True)
            raise
    
    async def get_net_credits_read(
        self, 
        db: AsyncSession, 
        org_id: uuid.UUID, 
        credit_type: CreditType
    ) -> Optional[schemas.OrganizationNetCreditsRead]:
        """
        Get net credits as a read schema with calculated fields.
        
        Args:
            db: Database session
            org_id: Organization ID
            credit_type: Type of credits
            
        Returns:
            OrganizationNetCreditsRead schema or None if not found
        """
        net_credits = await self.get_net_credits_by_org_and_type(db, org_id, credit_type)
        
        if not net_credits:
            return None
        
        current_balance = max(0, net_credits.credits_granted - net_credits.credits_consumed)
        is_overage = net_credits.credits_consumed > net_credits.credits_granted
        overage_amount = max(0, net_credits.credits_consumed - net_credits.credits_granted)
        
        return schemas.OrganizationNetCreditsRead(
            id=net_credits.id,
            org_id=net_credits.org_id,
            credit_type=net_credits.credit_type,
            credits_granted=net_credits.credits_granted,
            credits_consumed=net_credits.credits_consumed,
            current_balance=current_balance,
            is_overage=is_overage,
            overage_amount=overage_amount,
            created_at=net_credits.created_at,
            updated_at=net_credits.updated_at
        )
    
    def _calculate_credit_price_in_dollars(self, credit_type: CreditType, amount: float) -> float:
        """Calculate the price in dollars for purchasing credits."""
        if credit_type == CreditType.DOLLAR_CREDITS:
            return amount
        return amount * settings.CREDIT_PRICE_IN_DOLLARS.get(credit_type.value, settings.CREDIT_PRICE_IN_DOLLARS["default"])
    
    async def consume_credits_atomic(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_type: CreditType,
        credits_to_consume: float,
        max_overage_allowed_fraction: float = 0.0,
        commit: bool = True,
        allow_dollar_fallback: bool = True,
        # max_overage_allowed_abs: float = 0
    ) -> schemas.AtomicCreditConsumptionResult:
        """
        Atomically consume credits using race-condition safe UPDATE query.
        
        This method provides high-performance credit consumption with overage
        handling directly in the database using atomic operations.
        
        Args:
            db: Database session
            org_id: Organization ID
            credit_type: Type of credits to consume
            credits_to_consume: Number of credits to consume
            max_overage_allowed_fraction: Maximum overage as fraction of granted credits (e.g., 0.1 = 10%)
            commit: Whether to commit the transaction
            allow_dollar_fallback: Whether to allow dollar credit fallback
            # max_overage_allowed_abs: Maximum absolute overage credits allowed
            
        Returns:
            AtomicCreditConsumptionResult: Consumption result schema
            
        Raises:
            InsufficientCreditsException: If not enough credits available
        """
        try:
            # Calculate maximum allowed total consumption
            # We'll use the fraction-based overage for now as requested
            
            # First ensure the record exists
            # await self._ensure_net_credits_record_exists(db, org_id, credit_type)
            
            # Atomic update with race-condition safety and RETURNING clause
            # This will only update if the consumption limit is not exceeded
            conditions = [
                models.OrganizationNetCredits.org_id == org_id,
                models.OrganizationNetCredits.credit_type == credit_type,
            ]
            if credits_to_consume > 0:
                allowed_overage = func.least(
                    models.OrganizationNetCredits.credits_granted * max_overage_allowed_fraction,
                    settings.MAX_OVERAGE_ABSOLUTE.get(credit_type.value, settings.MAX_OVERAGE_ABSOLUTE["default"])
                )
                conditions.append(
                    # Race-condition safe check: ensure consumption doesn't exceed limit
                    models.OrganizationNetCredits.credits_consumed + credits_to_consume <= 
                        models.OrganizationNetCredits.credits_granted + allowed_overage
                )
            update_stmt = (
                update(models.OrganizationNetCredits)
                .where(
                    and_(*conditions)
                )
                .values(
                    credits_consumed=models.OrganizationNetCredits.credits_consumed + credits_to_consume,
                    # updated_at=func.now()
                )
                .execution_options(synchronize_session=False)
                .returning(
                    models.OrganizationNetCredits.credits_granted,
                    models.OrganizationNetCredits.credits_consumed,
                    models.OrganizationNetCredits.id
                )
            )
            
            result = await db.execute(update_stmt)
            
            # Get the returned row from the update
            updated_row = result.fetchone()
            
            consumed_in_dollar_credits = 0
            # Check if the update was successful (row returned)
            if updated_row is None:
                # Update failed - either record doesn't exist or limit exceeded
                # Get current state to provide detailed error
                success = False
                if credit_type != CreditType.DOLLAR_CREDITS and allow_dollar_fallback:
                    try:
                        dollar_credits_alternative_to_consume = self._calculate_credit_price_in_dollars(credit_type, credits_to_consume)
                        consumed_in_dollar_credits = dollar_credits_alternative_to_consume
                        dollar_credits_consumption_result = await self.consume_credits_atomic(
                            db=db,
                            org_id=org_id,
                            credit_type=CreditType.DOLLAR_CREDITS,
                            credits_to_consume=dollar_credits_alternative_to_consume,
                            max_overage_allowed_fraction=max_overage_allowed_fraction,
                            commit=commit,
                            # max_overage_allowed_abs: float = 0
                        )
                        dollar_credits_consumption_result.consumed_in_dollar_credits = consumed_in_dollar_credits
                        success = dollar_credits_consumption_result.success
                        if success:
                            return dollar_credits_consumption_result
                    except Exception as e:
                        billing_logger.error(f"Error consuming dollar credits alternative to consume {credit_type.value}: {credits_to_consume} credits: {e}", exc_info=True)
                        consumed_in_dollar_credits = 0
                        raise
                
                if not success:
                    current_state = await self.get_net_credits_by_org_and_type(db, org_id, credit_type)
                    if not current_state:
                        raise InsufficientCreditsException(
                            credit_type=credit_type,
                            required=credits_to_consume,
                            available=0,
                            detail=f"No credits record found for {credit_type.value}"
                        )
                    
                    
                    max_allowed = current_state.credits_granted * (1 + max_overage_allowed_fraction)
                    available = max_allowed - current_state.credits_consumed
                    
                    raise InsufficientCreditsException(
                        credit_type=credit_type,
                        required=credits_to_consume,
                        available=available,
                        detail=f"Insufficient {credit_type.value} credits. "
                        f"Requested: {credits_to_consume}, Available: {available} "
                        f"(including {max_overage_allowed_fraction*100:.1f}% overage grace)"
                    )
            
            if commit:
                await db.commit()
            
            # Extract values from the returned row
            updated_credits_granted = updated_row.credits_granted
            updated_credits_consumed = updated_row.credits_consumed
            
            # Calculate result metrics using the returned values
            current_balance = max(0, updated_credits_granted - updated_credits_consumed)
            is_overage = updated_credits_consumed > updated_credits_granted
            overage_amount = max(0, updated_credits_consumed - updated_credits_granted)
            
            return schemas.AtomicCreditConsumptionResult(
                success=True,
                credit_type=credit_type,
                credits_consumed=credits_to_consume,
                remaining_balance=current_balance,
                total_consumed=updated_credits_consumed,
                total_granted=updated_credits_granted,
                is_overage=is_overage,
                overage_amount=overage_amount,
                was_locked=True,
                consumed_in_dollar_credits=consumed_in_dollar_credits
            )
            
        except InsufficientCreditsException:
            raise
        except Exception as e:
            billing_logger.error(f"Error in atomic credit consumption: {e}", exc_info=True)
            raise
    
    async def _ensure_net_credits_record_exists(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_type: CreditType
    ) -> None:
        """
        Ensure a net credits record exists for the organization and credit type.
        
        This method is race-condition safe using INSERT ... ON CONFLICT.
        """
        try:
            # Use upsert pattern for PostgreSQL
            insert_stmt = insert(models.OrganizationNetCredits).values(
                org_id=org_id,
                credit_type=credit_type,
                credits_granted=0,
                credits_consumed=0,
                created_at=datetime_now_utc(),
                updated_at=datetime_now_utc()
            )
            
            # On conflict, do nothing (record already exists)
            upsert_stmt = insert_stmt.on_conflict_do_nothing(
                index_elements=['org_id', 'credit_type']
            )
            
            await db.execute(upsert_stmt)
            await db.commit()
            
        except Exception as e:
            billing_logger.error(f"Error ensuring net credits record exists: {e}", exc_info=True)
            raise
    
    async def allocate_credits_for_operation(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_type: CreditType,
        estimated_credits: float,
        operation_id: str,
        max_overage_allowed_fraction: float = 0.0,
        commit: bool = True
    ) -> schemas.CreditAllocationResult:
        """
        Allocate credits for a long-running operation by consuming estimated amount.
        
        This pre-allocates credits to reserve them for an operation,
        preventing race conditions in concurrent usage scenarios.
        """
        try:
            # Use atomic consumption to allocate (reserve) credits
            consumption_result = await self.consume_credits_atomic(
                db=db,
                org_id=org_id,
                credit_type=credit_type,
                credits_to_consume=estimated_credits,
                max_overage_allowed_fraction=max_overage_allowed_fraction,
                commit=commit,
                # NOTE: no dollar fallback for allocation! Since adjustment and allocation have to be in sync and work with same currency!
                allow_dollar_fallback=False,
            )
            
            billing_logger.debug(
                f"Allocated {estimated_credits} {credit_type.value} credits for operation {operation_id}"
            )
            
            return schemas.CreditAllocationResult(
                success=consumption_result.success,
                credit_type=consumption_result.credit_type,
                operation_id=operation_id,
                allocated_credits=consumption_result.credits_consumed,
                remaining_balance=consumption_result.remaining_balance,
                is_overage=consumption_result.is_overage,
                allocation_token=f"alloc_{operation_id}_{org_id}"
            )
            
        except Exception as e:
            billing_logger.error(f"Error allocating credits for operation: {e}", exc_info=True)
            raise
    
    async def adjust_allocation_with_actual(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_type: CreditType,
        operation_id: str,
        actual_credits: float,
        allocated_credits: float,
        max_overage_allowed_fraction: float = 0.0,
        commit: bool = True,
    ) -> schemas.CreditAdjustmentResult:
        """
        Adjust allocated credits with actual consumption using atomic operations.
        
        This method handles the difference between estimated and actual
        credit consumption by adjusting the credits_consumed amount atomically.
        """
        try:
            credit_difference = actual_credits - allocated_credits
            
            if credit_difference == 0:
                # No adjustment needed
                return schemas.CreditAdjustmentResult(
                    success=True,
                    operation_id=operation_id,
                    adjustment_needed=False,
                    credit_difference=0,
                    final_credits_consumed=actual_credits,
                    allocated_credits=allocated_credits,
                    adjustment_type="none"
                )
            
            # Use atomic UPDATE for the adjustment
            additional_consumption = await self.consume_credits_atomic(
                db=db,
                org_id=org_id,
                credit_type=credit_type,
                credits_to_consume=credit_difference,
                max_overage_allowed_fraction=max_overage_allowed_fraction,  # No additional overage for adjustments
                commit=commit,
                allow_dollar_fallback=False,
            )
            if credit_difference > 0:
                # Need to consume more credits - use the atomic consumption method
                adjustment_type = "consume"
            else:
                # Return excess credits (credit_difference is negative)
                adjustment_type = "return"
            
            billing_logger.info(
                f"Adjusted operation {operation_id}: {credit_difference} {credit_type.value} credits "
                f"(allocated: {allocated_credits}, actual: {actual_credits})"
            )
            
            return schemas.CreditAdjustmentResult(
                success=True,
                operation_id=operation_id,
                adjustment_needed=True,
                credit_difference=credit_difference,
                final_credits_consumed=actual_credits,
                allocated_credits=allocated_credits,
                adjustment_type=adjustment_type
            )
            
        except Exception as e:
            billing_logger.error(f"Error adjusting credit allocation: {e}", exc_info=True)
            raise
    
    async def add_credits(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_type: CreditType,
        credits_to_add: float,
        source_type: CreditSourceType,
        source_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        commit: bool = True
    ) -> schemas.CreditAdditionResult:
        """
        Add credits to organization using atomic operations.
        
        This method adds new credits without overage adjustment. Any existing
        overage will be handled automatically through the billing system's
        reduced limits and charging mechanisms.
        """
        try:
            # Ensure record exists
            await self._ensure_net_credits_record_exists(db, org_id, credit_type)
            
            # Get current state before update for result calculation
            current_state = await self.get_net_credits_by_org_and_type(db, org_id, credit_type)
            
            # Atomic update - simply add credits without overage adjustment
            update_stmt = (
                update(models.OrganizationNetCredits)
                .where(
                    and_(
                        models.OrganizationNetCredits.org_id == org_id,
                        models.OrganizationNetCredits.credit_type == credit_type
                    )
                )
                .values(
                    credits_granted=models.OrganizationNetCredits.credits_granted + credits_to_add,
                    # updated_at=func.now()
                )
            )
            
            await db.execute(update_stmt)
            if commit:
                await db.commit()
            
            billing_logger.info(
                f"Added {credits_to_add} {credit_type.value} credits to org {org_id}"
            )
            
            return schemas.CreditAdditionResult(
                success=True,
                credits_added=credits_to_add,
                new_total_granted=(current_state.credits_granted if current_state else 0) + credits_to_add,
                allocation_id=None  # This is handled by OrganizationCreditsDAO
            )
            
        except Exception as e:
            billing_logger.error(f"Error adding credits: {e}", exc_info=True)
            raise
    
    async def expire_credits_and_adjust_consumption(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_type: CreditType,
        expired_credits: float,
        modify_granted_only: bool = False,
        commit: bool = True
    ) -> schemas.CreditExpirationResult:
        """
        Handle credit expiration by reducing both granted and consumed credits atomically.
        
        When credits expire, we reduce both the granted total and consumed
        total to maintain accurate balances, ensuring consumed never goes below 0.
        """
        try:
            # Ensure record exists first
            await self._ensure_net_credits_record_exists(db, org_id, credit_type)
            
            # Single atomic UPDATE query with RETURNING clause
            conditions = [
                models.OrganizationNetCredits.org_id == org_id,
                models.OrganizationNetCredits.credit_type == credit_type
            ]
            values = {
                "credits_granted": func.greatest(0, models.OrganizationNetCredits.credits_granted - expired_credits),
            }
            if not modify_granted_only:
                values["credits_consumed"] = func.least(
                    models.OrganizationNetCredits.credits_consumed,
                    func.greatest(0, models.OrganizationNetCredits.credits_consumed - expired_credits)
                )
            update_stmt = (
                update(models.OrganizationNetCredits)
                .where(
                    and_(*conditions)
                )
                .values(
                    **values,
                    # credits_granted=func.greatest(0, models.OrganizationNetCredits.credits_granted - expired_credits),
                    # credits_consumed=func.least(
                    #     models.OrganizationNetCredits.credits_consumed,
                    #     func.greatest(0, models.OrganizationNetCredits.credits_consumed - expired_credits)
                    # ),
                    # # updated_at=func.now()
                )
                .execution_options(synchronize_session=False)
                .returning(
                    models.OrganizationNetCredits.credits_granted,
                    models.OrganizationNetCredits.credits_consumed,
                    models.OrganizationNetCredits.id
                )
            )
            
            result = await db.execute(update_stmt)
            
            # Get the returned row from the update
            updated_row = result.fetchone()
            
            if updated_row is None:
                billing_logger.warning(f"No net credits found for expiration: org {org_id}, type {credit_type}")
                return schemas.CreditExpirationResult(
                    success=False,
                    expired_credits=0,
                    granted_reduction=0,
                    consumed_reduction=0,
                    credits_granted_before=0,
                    credits_consumed_before=0,
                    credits_granted_after=0,
                    credits_consumed_after=0
                )
            
            if commit:
                await db.commit()
            
            # Extract values from the returned row
            credits_granted_after = updated_row.credits_granted
            credits_consumed_after = updated_row.credits_consumed
            
            # Calculate before values from the after values and logic
            # credits_granted_after = max(0, credits_granted_before - expired_credits)
            # So: credits_granted_before = credits_granted_after + min(expired_credits, original_granted)
            credits_granted_before = credits_granted_after
            if not modify_granted_only:
                credits_granted_before = expired_credits if credits_granted_after == 0 else credits_granted_after + expired_credits
            
            # credits_consumed_after = min(credits_consumed_before, credits_granted_after)
            # Since we know the consumed was reduced to not exceed granted_after
            # The consumed reduction is limited by both expired_credits and original consumed amount
            credits_consumed_before = credits_consumed_after if credits_consumed_after < 0 else (expired_credits if credits_consumed_after == 0 else credits_consumed_after + expired_credits)
            
            # Calculate actual reductions
            granted_reduction = credits_granted_before - credits_granted_after
            consumed_reduction = credits_consumed_before - credits_consumed_after
            
            billing_logger.info(
                f"Expired {expired_credits} {credit_type.value} credits for org {org_id}: "
                f"reduced granted by {granted_reduction}, consumed by {consumed_reduction}"
            )
            
            return schemas.CreditExpirationResult(
                success=True,
                expired_credits=expired_credits,
                granted_reduction=granted_reduction,
                consumed_reduction=consumed_reduction,
                credits_granted_before=credits_granted_before,
                credits_consumed_before=credits_consumed_before,
                credits_granted_after=credits_granted_after,
                credits_consumed_after=credits_consumed_after
            )
            
        except Exception as e:
            billing_logger.error(f"Error expiring credits: {e}", exc_info=True)
            raise
    
    async def batch_add_credits(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_additions: List[schemas.CreditAdditionBatch],
        commit: bool = True
    ) -> List[schemas.CreditAdditionResult]:
        """
        Batch add credits for multiple credit types or sources.
        
        Args:
            db: Database session
            org_id: Organization ID
            credit_additions: List of credit additions to process
            
        Returns:
            List of CreditAdditionResult for each addition
        """
        try:
            results = []
            
            for addition in credit_additions:
                result = await self.add_credits(
                    db=db,
                    org_id=org_id,
                    credit_type=addition.credit_type,
                    credits_to_add=addition.credits_to_add,
                    source_type=addition.source_type,
                    source_id=addition.source_id,
                    expires_at=addition.expires_at,
                    commit=commit
                )
                results.append(result)
            
            billing_logger.info(f"Batch added credits for org {org_id}: {len(credit_additions)} operations")
            return results
            
        except Exception as e:
            billing_logger.error(f"Error in batch add credits: {e}", exc_info=True)
            raise
    
    async def batch_expire_credits_and_adjust_consumption(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_expirations: List[schemas.CreditExpirationBatch],
        commit: bool = True,
        modify_granted_only: bool = False
    ) -> List[schemas.CreditExpirationResult]:
        """
        Batch expire credits for multiple credit types.
        
        Args:
            db: Database session
            org_id: Organization ID
            credit_expirations: List of credit expirations to process
            commit: Whether to commit the transaction
            modify_granted_only: Whether to modify only the granted credits
            
        Returns:
            List of CreditExpirationResult for each expiration
        """
        try:
            results = []
            
            for expiration in credit_expirations:
                result = await self.expire_credits_and_adjust_consumption(
                    db=db,
                    org_id=org_id,
                    credit_type=expiration.credit_type,
                    expired_credits=expiration.expired_credits,
                    commit=commit,
                    modify_granted_only=modify_granted_only
                )
                results.append(result)
            
            billing_logger.info(f"Batch expired credits for org {org_id}: {len(credit_expirations)} operations")
            return results
            
        except Exception as e:
            billing_logger.error(f"Error in batch expire credits: {e}", exc_info=True)
            raise
    
    async def get_all_organizations_with_credits(
        self,
        db: AsyncSession
    ) -> List[uuid.UUID]:
        """
        Get all organization IDs that have net credits records.
        
        Returns:
            List of organization IDs
        """
        try:
            query = select(models.OrganizationNetCredits.org_id).distinct()
            result = await db.execute(query)
            return [row.org_id for row in result]
        except Exception as e:
            billing_logger.error(f"Error getting organizations with credits: {e}", exc_info=True)
            raise
    
    async def get_credit_summary_by_org_and_types(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_types: Optional[List[CreditType]] = None
    ) -> Dict[CreditType, schemas.OrganizationNetCreditsRead]:
        """
        Get credit summaries for multiple credit types for an organization.
        
        Args:
            db: Database session
            org_id: Organization ID
            credit_types: List of credit types to fetch (None for all types)
            
        Returns:
            Dictionary mapping credit types to their net credits data
        """
        try:
            if credit_types is None:
                credit_types = list(CreditType)
            
            summary = {}
            for credit_type in credit_types:
                net_credits = await self.get_net_credits_read(db, org_id, credit_type)
                if net_credits:
                    summary[credit_type] = net_credits
            
            return summary
        except Exception as e:
            billing_logger.error(f"Error getting credit summary: {e}", exc_info=True)
            raise


class UsageEventDAO(BaseDAO[models.UsageEvent, SQLModel, SQLModel]):
    """Data Access Object for usage event operations."""
    
    def __init__(self):
        super().__init__(models.UsageEvent)
    
    async def create_usage_event(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        event_type: str,
        credit_type: CreditType,
        credits_consumed: float,
        usage_metadata: Optional[Dict[str, Any]] = None,
        is_overage: bool = False,
        commit: bool = True
    ) -> models.UsageEvent:
        """Create a new usage event record."""
        usage_event = models.UsageEvent(
            org_id=org_id,
            user_id=user_id,
            event_type=event_type,
            credit_type=credit_type,
            credits_consumed=credits_consumed,
            usage_metadata=usage_metadata or {},
            is_overage=is_overage,
            created_at=datetime_now_utc()
        )
        
        db.add(usage_event)
        if commit:
            await db.commit()
            await db.refresh(usage_event)
        
        return usage_event
    
    async def get_by_org_and_period(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
        event_type: Optional[str] = None,
        credit_type: Optional[CreditType] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Sequence[models.UsageEvent]:
        """Get usage events for an organization within a date range."""
        conditions = [
            self.model.org_id == org_id,
            self.model.created_at >= start_date,
            self.model.created_at <= end_date
        ]
        
        if event_type:
            conditions.append(self.model.event_type == event_type)
        
        if credit_type:
            conditions.append(self.model.credit_type == credit_type)
        
        statement = select(self.model).where(
            and_(*conditions)
        ).order_by(desc(self.model.created_at)).offset(skip).limit(limit)
        
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def get_usage_summary(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get usage summary for an organization within a date range."""
        # Total events and credits consumed by type
        statement = select(
            self.model.credit_type,
            self.model.event_type,
            func.count(self.model.id).label('event_count'),
            func.sum(self.model.credits_consumed).label('total_credits'),
            func.sum(case((self.model.is_overage == True, 1), else_=0)).label('overage_event_count')
        ).where(
            and_(
                self.model.org_id == org_id,
                self.model.created_at >= start_date,
                self.model.created_at <= end_date
            )
        ).group_by(self.model.credit_type, self.model.event_type)
        
        result = await db.exec(statement)
        
        summary = {
            'total_events': 0,
            'events_by_type': {},
            'credits_by_type': {},
            'overage_events': 0
        }
        
        for row in result:
            credit_type = row.credit_type.value
            event_type = row.event_type
            event_count = int(row.event_count)
            total_credits = float(row.total_credits or 0)
            overage_event_count = int(row.overage_event_count or 0)
            
            summary['total_events'] += event_count
            summary['events_by_type'][event_type] = summary['events_by_type'].get(event_type, 0) + event_count
            summary['credits_by_type'][credit_type] = summary['credits_by_type'].get(credit_type, 0) + total_credits
            summary['overage_events'] += overage_event_count
        
        return summary
    
    async def query_usage_events(
        self,
        db: AsyncSession,
        query_params: schemas.UsageEventQuery
    ) -> schemas.PaginatedUsageEvents:
        """
        Query usage events with filtering, sorting, and pagination.
        
        Args:
            db: Database session
            query_params: Query parameters for filtering and pagination
            
        Returns:
            Paginated usage events response
        """
        # Build base query
        query = select(models.UsageEvent)
        
        # Apply filters
        filters = []
        filters_applied = {}
        
        if query_params.org_id is not None:
            filters.append(models.UsageEvent.org_id == query_params.org_id)
            filters_applied["org_id"] = str(query_params.org_id)
            
        if query_params.user_id is not None:
            filters.append(models.UsageEvent.user_id == query_params.user_id)
            filters_applied["user_id"] = str(query_params.user_id)
            
        if query_params.event_type is not None:
            filters.append(models.UsageEvent.event_type == query_params.event_type)
            filters_applied["event_type"] = query_params.event_type
            
        if query_params.credit_type is not None:
            filters.append(models.UsageEvent.credit_type == query_params.credit_type)
            filters_applied["credit_type"] = query_params.credit_type.value
            
        if query_params.is_overage is not None:
            filters.append(models.UsageEvent.is_overage == query_params.is_overage)
            filters_applied["is_overage"] = query_params.is_overage
            
        if query_params.created_after:
            filters.append(models.UsageEvent.created_at >= query_params.created_after)
            filters_applied["created_after"] = query_params.created_after
            
        if query_params.created_before:
            filters.append(models.UsageEvent.created_at <= query_params.created_before)
            filters_applied["created_before"] = query_params.created_before
            
        if query_params.metadata_search:
            # Use PostgreSQL's JSONB search capabilities
            search_condition = func.cast(models.UsageEvent.usage_metadata, sa.String).contains(query_params.metadata_search)
            filters.append(search_condition)
            filters_applied["metadata_search"] = query_params.metadata_search
        
        if filters:
            query = query.where(and_(*filters))
        
        # Get total count for pagination
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # Apply sorting
        valid_sort_fields = ['created_at', 'credits_consumed', 'event_type']
        if query_params.sort_by not in valid_sort_fields:
            query_params.sort_by = 'created_at'
            
        sort_column = getattr(models.UsageEvent, query_params.sort_by, models.UsageEvent.created_at)
        if query_params.sort_order == schemas.SortOrder.DESC:
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
        
        # Apply pagination
        query = query.offset(query_params.skip).limit(query_params.limit)
        
        # Execute query
        result = await db.execute(query)
        usage_events = result.scalars().all()
        
        # Calculate pagination info
        page = (query_params.skip // query_params.limit) + 1
        pages = (total + query_params.limit - 1) // query_params.limit
        
        return schemas.PaginatedUsageEvents(
            items=[schemas.UsageEventRead.model_validate(event) for event in usage_events],
            total=total,
            page=page,
            per_page=query_params.limit,
            pages=pages,
            filters_applied=filters_applied
        )


class CreditPurchaseDAO(BaseDAO[models.CreditPurchase, schemas.CreditPurchaseRequest, SQLModel]):
    """Data Access Object for credit purchase operations."""
    
    def __init__(self):
        super().__init__(models.CreditPurchase)
    
    async def create_purchase(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        stripe_checkout_id: str,
        credit_type: CreditType,
        credits_amount: float,
        amount_paid: float,
        currency: str = "usd",
        expires_at: Optional[datetime] = None
    ) -> models.CreditPurchase:
        """Create a new credit purchase record."""
        purchase = models.CreditPurchase(
            org_id=org_id,
            user_id=user_id,
            stripe_checkout_id=stripe_checkout_id,
            credit_type=credit_type,
            credits_amount=credits_amount,
            amount_paid=amount_paid,
            currency=currency,
            status=PaymentStatus.PENDING,
            expires_at=expires_at,
            created_at=datetime_now_utc(),
            updated_at=datetime_now_utc()
        )
        
        db.add(purchase)
        await db.commit()
        await db.refresh(purchase)
        
        return purchase
    
    async def get_by_stripe_checkout_id(
        self, 
        db: AsyncSession, 
        stripe_checkout_id: str
    ) -> Optional[models.CreditPurchase]:
        """Get credit purchase by Stripe payment intent ID."""
        statement = select(self.model).where(self.model.stripe_checkout_id == stripe_checkout_id)
        result = await db.exec(statement)
        return result.scalars().first()
    
    async def get_by_org_id(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100
    ) -> Sequence[models.CreditPurchase]:
        """Get credit purchases for an organization."""
        statement = select(self.model).where(
            self.model.org_id == org_id
        ).order_by(desc(self.model.created_at)).offset(skip).limit(limit)
        
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def update_payment_status(
        self,
        db: AsyncSession,
        purchase: models.CreditPurchase,
        status: PaymentStatus,
        stripe_invoice_id: Optional[str] = None
    ) -> models.CreditPurchase:
        """Update payment status of a credit purchase."""
        purchase.status = status
        purchase.updated_at = datetime_now_utc()
        
        if stripe_invoice_id:
            purchase.stripe_invoice_id = stripe_invoice_id
        
        db.add(purchase)
        await db.commit()
        await db.refresh(purchase)
        
        return purchase
    
    async def update_receipt_url(
        self,
        db: AsyncSession,
        purchase: models.CreditPurchase,
        receipt_url: str
    ) -> models.CreditPurchase:
        """Update receipt URL for a credit purchase."""
        purchase.receipt_url = receipt_url
        purchase.updated_at = datetime_now_utc()
        
        db.add(purchase)
        await db.commit()
        await db.refresh(purchase)
        
        billing_logger.info(f"Updated receipt URL for purchase {purchase.id}")
        return purchase


class PromotionCodeDAO(BaseDAO[models.PromotionCode, schemas.PromotionCodeCreate, schemas.PromotionCodeUpdate]):
    """Data Access Object for promotion code operations."""
    
    def __init__(self):
        super().__init__(models.PromotionCode)
    
    async def get_by_code(self, db: AsyncSession, code: str) -> Optional[models.PromotionCode]:
        """Get promotion code by code string."""
        statement = select(self.model).where(self.model.code == code)
        result = await db.exec(statement)
        return result.scalars().first()
    
    async def get_active_codes(self, db: AsyncSession) -> Sequence[models.PromotionCode]:
        """Get all active promotion codes."""
        now = datetime_now_utc()
        statement = select(self.model).where(
            and_(
                self.model.is_active == True,
                or_(
                    self.model.expires_at.is_(None),
                    self.model.expires_at > now
                ),
                # Ensure we only get codes that haven't reached global usage limit
                or_(
                    self.model.max_uses.is_(None),
                    self.model.uses_count < self.model.max_uses
                )
            )
        )
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def check_usage_eligibility(
        self,
        db: AsyncSession,
        promo_code: models.PromotionCode,
        org_id: uuid.UUID
    ) -> tuple[bool, Optional[str]]:
        """
        Check if an organization can use a promotion code.
        
        Returns:
            tuple: (is_eligible, reason_if_not_eligible)
        """
        now = datetime_now_utc()
        
        # Check if code is active
        if not promo_code.is_active:
            return False, "Promotion code is not active"
        
        # Check expiration
        if promo_code.expires_at and promo_code.expires_at <= now:
            return False, "Promotion code has expired"
        
        # Check global usage limit
        if promo_code.max_uses and promo_code.uses_count >= promo_code.max_uses:
            return False, "Promotion code has reached its usage limit"
        
        # Check organization restrictions
        if promo_code.allowed_org_ids:
            if str(org_id) not in promo_code.allowed_org_ids:
                return False, "Organization is not allowed to use this promotion code"
        
        # Check per-organization usage limit
        usage_count = await self.get_org_usage_count(db, promo_code.id, org_id)
        if usage_count >= promo_code.max_uses_per_org:
            return False, "Organization has already used this promotion code the maximum number of times"
        
        return True, None
    
    async def get_org_usage_count(self, db: AsyncSession, promo_code_id: uuid.UUID, org_id: uuid.UUID) -> int:
        """Get the number of times an organization has used a promotion code."""
        statement = select(func.count(models.PromotionCodeUsage.id)).where(
            and_(
                models.PromotionCodeUsage.promo_code_id == promo_code_id,
                models.PromotionCodeUsage.org_id == org_id
            )
        )
        result = await db.exec(statement)
        return result.scalar() or 0

    async def query_promotion_codes(
        self,
        db: AsyncSession,
        query_params: schemas.PromotionCodeQuery
    ) -> schemas.PaginatedPromotionCodes:
        """
        Query promotion codes with filtering, sorting, and pagination.
        
        Args:
            db: Database session
            query_params: Query parameters for filtering and pagination
            
        Returns:
            Paginated promotion codes response
        """
        # Build base query
        query = select(models.PromotionCode)
        
        # Apply filters
        filters = []
        filters_applied = {}
        
        if query_params.is_active is not None:
            filters.append(models.PromotionCode.is_active == query_params.is_active)
            filters_applied["is_active"] = query_params.is_active
            
        if query_params.credit_type is not None:
            filters.append(models.PromotionCode.credit_type == query_params.credit_type)
            filters_applied["credit_type"] = query_params.credit_type.value
            
        if query_params.search_text:
            search_pattern = f"%{query_params.search_text}%"
            filters.append(
                or_(
                    models.PromotionCode.code.ilike(search_pattern),
                    models.PromotionCode.description.ilike(search_pattern)
                )
            )
            filters_applied["search_text"] = query_params.search_text
            
        if query_params.expires_after:
            filters.append(models.PromotionCode.expires_at >= query_params.expires_after)
            filters_applied["expires_after"] = query_params.expires_after
            
        if query_params.expires_before:
            filters.append(models.PromotionCode.expires_at <= query_params.expires_before)
            filters_applied["expires_before"] = query_params.expires_before
            
        if query_params.has_usage_limit is not None:
            if query_params.has_usage_limit:
                filters.append(models.PromotionCode.max_uses.is_not(None))
            else:
                filters.append(models.PromotionCode.max_uses.is_(None))
            filters_applied["has_usage_limit"] = query_params.has_usage_limit
        
        if filters:
            query = query.where(and_(*filters))
        
        # Get total count for pagination
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # Apply sorting
        sort_column = getattr(models.PromotionCode, query_params.sort_by, models.PromotionCode.created_at)
        if query_params.sort_order == schemas.SortOrder.DESC:
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
        
        # Apply pagination
        query = query.offset(query_params.skip).limit(query_params.limit)
        
        # Execute query
        result = await db.execute(query)
        promotion_codes = result.scalars().all()
        
        # Calculate pagination info
        page = (query_params.skip // query_params.limit) + 1
        pages = (total + query_params.limit - 1) // query_params.limit
        
        return schemas.PaginatedPromotionCodes(
            items=[schemas.PromotionCodeRead.model_validate(code) for code in promotion_codes],
            total=total,
            page=page,
            per_page=query_params.limit,
            pages=pages,
            filters_applied=filters_applied
        )

    async def delete_promotion_code(
        self,
        db: AsyncSession,
        promo_code_id: uuid.UUID,
        commit: bool = True
    ) -> bool:
        """
        Delete a promotion code by ID.
        
        Args:
            db: Database session
            promo_code_id: ID of the promotion code to delete
            commit: Whether to commit the transaction
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            ValueError: If there are existing usage records that prevent deletion
        """
        # First check if the promotion code exists
        promo_code = await self.get(db, promo_code_id)
        if not promo_code:
            return False
        
        # Check if there are any usage records
        usage_count = await db.scalar(
            select(func.count(models.PromotionCodeUsage.id))
            .where(models.PromotionCodeUsage.promotion_code_id == promo_code_id)
        )
        
        if usage_count > 0:
            raise ValueError(
                f"Cannot delete promotion code '{promo_code.code}' because it has {usage_count} usage record(s). "
                "Consider deactivating it instead."
            )
        
        # Delete the promotion code
        await db.delete(promo_code)
        
        if commit:
            await db.commit()
            
        return True

    async def deactivate_promotion_codes(
        self,
        db: AsyncSession,
        deactivate_request: schemas.PromotionCodeDeactivateRequest,
        commit: bool = True
    ) -> schemas.PromotionCodeDeactivateResult:
        """
        Deactivate promotion codes based on various targeting criteria.
        
        Supports deactivation by:
        - Specific promotion code IDs
        - Specific promotion code strings
        - Query filters (same as get_promotion_codes)
        - Deactivate all (with explicit confirmation)
        
        Args:
            db: Database session
            deactivate_request: Deactivation targeting criteria
            commit: Whether to commit the transaction
            
        Returns:
            PromotionCodeDeactivateResult with operation details
            
        Raises:
            ValueError: If no targeting criteria provided without explicit deactivate_all flag
        """
        # Build filters based on request
        filters = []
        filters_applied = {}
        
        # Direct targeting by IDs
        if deactivate_request.promo_code_ids:
            filters.append(models.PromotionCode.id.in_(deactivate_request.promo_code_ids))
            filters_applied["promo_code_ids"] = [str(id) for id in deactivate_request.promo_code_ids]
        
        # Direct targeting by codes
        if deactivate_request.codes:
            filters.append(models.PromotionCode.code.in_(deactivate_request.codes))
            filters_applied["codes"] = deactivate_request.codes
        
        # Query-based targeting
        if deactivate_request.is_active is not None:
            filters.append(models.PromotionCode.is_active == deactivate_request.is_active)
            filters_applied["is_active"] = deactivate_request.is_active
            
        if deactivate_request.credit_type is not None:
            filters.append(models.PromotionCode.credit_type == deactivate_request.credit_type)
            filters_applied["credit_type"] = deactivate_request.credit_type.value
            
        if deactivate_request.search_text:
            search_pattern = f"%{deactivate_request.search_text}%"
            filters.append(
                or_(
                    models.PromotionCode.code.ilike(search_pattern),
                    models.PromotionCode.description.ilike(search_pattern)
                )
            )
            filters_applied["search_text"] = deactivate_request.search_text
            
        if deactivate_request.expires_after:
            filters.append(models.PromotionCode.expires_at >= deactivate_request.expires_after)
            filters_applied["expires_after"] = deactivate_request.expires_after
            
        if deactivate_request.expires_before:
            filters.append(models.PromotionCode.expires_at <= deactivate_request.expires_before)
            filters_applied["expires_before"] = deactivate_request.expires_before
            
        if deactivate_request.has_usage_limit is not None:
            if deactivate_request.has_usage_limit:
                filters.append(models.PromotionCode.max_uses.is_not(None))
            else:
                filters.append(models.PromotionCode.max_uses.is_(None))
            filters_applied["has_usage_limit"] = deactivate_request.has_usage_limit
        
        # Safety check: if no filters and deactivate_all not explicitly set
        if not filters and not deactivate_request.deactivate_all:
            raise ValueError(
                "No targeting criteria provided. To deactivate all promotion codes, "
                "set 'deactivate_all' to true explicitly."
            )
        
        # Build and execute query to find codes to deactivate
        query = select(models.PromotionCode)
        if filters:
            query = query.where(and_(*filters))
        
        result = await db.execute(query)
        promotion_codes = result.scalars().all()
        
        # Deactivate the codes
        deactivated_codes = []
        for promo_code in promotion_codes:
            if promo_code.is_active:  # Only deactivate if currently active
                promo_code.is_active = False
                deactivated_codes.append(promo_code.code)
        
        if commit:
            await db.commit()
        
        return schemas.PromotionCodeDeactivateResult(
            success=True,
            message=f"Successfully deactivated {len(deactivated_codes)} promotion codes",
            deactivated_count=len(deactivated_codes),
            deactivated_codes=deactivated_codes,
            filters_applied=filters_applied
        )

    async def bulk_delete_promotion_codes(
        self,
        db: AsyncSession,
        delete_request: schemas.PromotionCodeBulkDeleteRequest,
        commit: bool = True
    ) -> schemas.PromotionCodeBulkDeleteResult:
        """
        Bulk delete promotion codes based on various targeting criteria.
        
        Supports deletion by:
        - Specific promotion code IDs
        - Specific promotion code strings
        - Query filters (same as get_promotion_codes)
        - Delete all (with explicit confirmation)
        
        Args:
            db: Database session
            delete_request: Deletion targeting criteria
            commit: Whether to commit the transaction
            
        Returns:
            PromotionCodeBulkDeleteResult with operation details
            
        Raises:
            ValueError: If no targeting criteria provided without explicit delete_all flag
        """
        # Build filters based on request
        filters = []
        filters_applied = {}
        
        # Direct targeting by IDs
        if delete_request.promo_code_ids:
            filters.append(models.PromotionCode.id.in_(delete_request.promo_code_ids))
            filters_applied["promo_code_ids"] = [str(id) for id in delete_request.promo_code_ids]
        
        # Direct targeting by codes
        if delete_request.codes:
            filters.append(models.PromotionCode.code.in_(delete_request.codes))
            filters_applied["codes"] = delete_request.codes
        
        # Query-based targeting
        if delete_request.is_active is not None:
            filters.append(models.PromotionCode.is_active == delete_request.is_active)
            filters_applied["is_active"] = delete_request.is_active
            
        if delete_request.credit_type is not None:
            filters.append(models.PromotionCode.credit_type == delete_request.credit_type)
            filters_applied["credit_type"] = delete_request.credit_type.value
            
        if delete_request.search_text:
            search_pattern = f"%{delete_request.search_text}%"
            filters.append(
                or_(
                    models.PromotionCode.code.ilike(search_pattern),
                    models.PromotionCode.description.ilike(search_pattern)
                )
            )
            filters_applied["search_text"] = delete_request.search_text
            
        if delete_request.expires_after:
            filters.append(models.PromotionCode.expires_at >= delete_request.expires_after)
            filters_applied["expires_after"] = delete_request.expires_after
            
        if delete_request.expires_before:
            filters.append(models.PromotionCode.expires_at <= delete_request.expires_before)
            filters_applied["expires_before"] = delete_request.expires_before
            
        if delete_request.has_usage_limit is not None:
            if delete_request.has_usage_limit:
                filters.append(models.PromotionCode.max_uses.is_not(None))
            else:
                filters.append(models.PromotionCode.max_uses.is_(None))
            filters_applied["has_usage_limit"] = delete_request.has_usage_limit
        
        # Safety check: if no filters and delete_all not explicitly set
        if not filters and not delete_request.delete_all:
            raise ValueError(
                "No targeting criteria provided. To delete all promotion codes, "
                "set 'delete_all' to true explicitly."
            )
        
        # Build and execute query to find codes to delete
        query = select(models.PromotionCode)
        if filters:
            query = query.where(and_(*filters))
        
        result = await db.execute(query)
        promotion_codes = result.scalars().all()
        
        # Process deletion with usage record checking
        deleted_codes = []
        skipped_codes = []
        
        for promo_code in promotion_codes:
            # Check if there are any usage records
            usage_count = await db.scalar(
                select(func.count(models.PromotionCodeUsage.id))
                .where(models.PromotionCodeUsage.promotion_code_id == promo_code.id)
            )
            
            if usage_count > 0 and not delete_request.force_delete_used:
                # Skip codes with usage records unless force deletion is enabled
                skipped_codes.append(promo_code.code)
            else:
                # Delete the promotion code
                await db.delete(promo_code)
                deleted_codes.append(promo_code.code)
        
        if commit:
            await db.commit()
        
        return schemas.PromotionCodeBulkDeleteResult(
            success=True,
            message=f"Successfully deleted {len(deleted_codes)} promotion codes, skipped {len(skipped_codes)} codes with usage records",
            deleted_count=len(deleted_codes),
            skipped_count=len(skipped_codes),
            deleted_codes=deleted_codes,
            skipped_codes=skipped_codes,
            filters_applied=filters_applied
        )


class PromotionCodeUsageDAO(BaseDAO[models.PromotionCodeUsage, SQLModel, SQLModel]):
    """Data Access Object for promotion code usage operations."""
    
    def __init__(self):
        super().__init__(models.PromotionCodeUsage)
    
    async def create_usage(
        self,
        db: AsyncSession,
        promo_code_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        credits_applied: float
    ) -> models.PromotionCodeUsage:
        """Create a new promotion code usage record."""
        usage = models.PromotionCodeUsage(
            promo_code_id=promo_code_id,
            org_id=org_id,
            user_id=user_id,
            credits_applied=credits_applied,
            created_at=datetime_now_utc()
        )
        
        db.add(usage)
        await db.commit()
        await db.refresh(usage)
        
        return usage
    
    async def get_by_org_and_code(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        promo_code_id: uuid.UUID
    ) -> Sequence[models.PromotionCodeUsage]:
        """Get all usage records for an organization and promotion code."""
        statement = select(self.model).where(
            and_(
                self.model.org_id == org_id,
                self.model.promo_code_id == promo_code_id
            )
        ).order_by(desc(self.model.created_at))
        
        result = await db.exec(statement)
        return result.scalars().all()


class StripeEventDAO(BaseDAO[models.StripeEvent, schemas.StripeEventCreate, SQLModel]):
    """
    Data Access Object for Stripe event audit operations.
    
    This DAO provides comprehensive querying, filtering, and sorting capabilities
    for Stripe event audit logs, primarily intended for admin use.
    """
    
    def __init__(self):
        super().__init__(models.StripeEvent)
    
    async def create_event_log(
        self,
        db: AsyncSession,
        stripe_event_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        org_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        plan_id: Optional[uuid.UUID] = None,
        event_timestamp: Optional[datetime] = None,
        livemode: bool = True,
        api_version: Optional[str] = None,
        processed_successfully: bool = True,
        processing_error: Optional[str] = None,
        commit: bool = True
    ) -> models.StripeEvent:
        """
        Create a Stripe event audit log entry.
        
        This method extracts context from event metadata and creates a comprehensive
        audit record for later analysis and debugging.
        
        Args:
            db: Database session
            stripe_event_id: Stripe's unique event ID
            event_type: Type of Stripe event
            event_data: Complete Stripe event data
            org_id: Organization ID (extracted from metadata)
            user_id: User ID (extracted from metadata)
            plan_id: Plan ID (extracted from metadata)
            event_timestamp: When the event occurred (from Stripe)
            livemode: Whether event is from live mode
            api_version: Stripe API version
            processed_successfully: Whether processing succeeded
            processing_error: Error message if processing failed
            commit: Whether to commit the transaction
            
        Returns:
            Created StripeEvent record
        """
        try:
            # Check for duplicate events (idempotency)
            existing_event = await self.get_by_stripe_event_id(db, stripe_event_id)
            if existing_event:
                billing_logger.debug(f"Stripe event {stripe_event_id} already logged, skipping duplicate")
                return existing_event
            
            stripe_event = models.StripeEvent(
                stripe_event_id=stripe_event_id,
                event_type=event_type,
                org_id=org_id,
                user_id=user_id,
                plan_id=plan_id,
                event_timestamp=event_timestamp,
                event_data=event_data,
                livemode=livemode,
                api_version=api_version,
                processed_successfully=processed_successfully,
                processing_error=processing_error,
                created_at=datetime_now_utc()
            )
            
            db.add(stripe_event)
            if commit:
                await db.commit()
                await db.refresh(stripe_event)
            
            billing_logger.debug(f"Logged Stripe event: {event_type} (ID: {stripe_event_id})")
            return stripe_event
            
        except Exception as e:
            billing_logger.error(f"Error creating Stripe event log: {e}", exc_info=True)
            raise
    
    async def get_by_stripe_event_id(
        self, 
        db: AsyncSession, 
        stripe_event_id: str
    ) -> Optional[models.StripeEvent]:
        """Get Stripe event by Stripe event ID."""
        try:
            statement = select(self.model).where(self.model.stripe_event_id == stripe_event_id)
            result = await db.execute(statement)
            return result.scalars().first()
        except Exception as e:
            billing_logger.error(f"Error getting Stripe event by ID: {e}", exc_info=True)
            raise
    
    async def query_events(
        self,
        db: AsyncSession,
        query_params: schemas.StripeEventQuery
    ) -> schemas.PaginatedStripeEvents:
        """
        Query Stripe events with comprehensive filtering and sorting.
        
        This method provides extensive filtering capabilities for admin users
        to analyze Stripe events across various dimensions.
        
        Args:
            db: Database session
            query_params: Query parameters with filters and sorting
            
        Returns:
            Paginated Stripe events with applied filters
        """
        try:
            # Build base query
            query = select(self.model)
            count_query = select(func.count(self.model.id))
            
            # Apply filters
            conditions = []
            filters_applied = {}
            
            # Event type filtering
            if query_params.event_types:
                conditions.append(self.model.event_type.in_(query_params.event_types))
                filters_applied["event_types"] = query_params.event_types
            
            # Organization filtering
            if query_params.org_id:
                conditions.append(self.model.org_id == query_params.org_id)
                filters_applied["org_id"] = str(query_params.org_id)
            
            # User filtering
            if query_params.user_id:
                conditions.append(self.model.user_id == query_params.user_id)
                filters_applied["user_id"] = str(query_params.user_id)
            
            # Plan filtering
            if query_params.plan_id:
                conditions.append(self.model.plan_id == query_params.plan_id)
                filters_applied["plan_id"] = str(query_params.plan_id)
            
            # Livemode filtering
            if query_params.livemode is not None:
                conditions.append(self.model.livemode == query_params.livemode)
                filters_applied["livemode"] = query_params.livemode
            
            # Processing status filtering
            if query_params.processed_successfully is not None:
                conditions.append(self.model.processed_successfully == query_params.processed_successfully)
                filters_applied["processed_successfully"] = query_params.processed_successfully
            
            # Event timestamp range filtering
            if query_params.event_timestamp_from:
                conditions.append(self.model.event_timestamp >= query_params.event_timestamp_from)
                filters_applied["event_timestamp_from"] = query_params.event_timestamp_from
            
            if query_params.event_timestamp_to:
                conditions.append(self.model.event_timestamp <= query_params.event_timestamp_to)
                filters_applied["event_timestamp_to"] = query_params.event_timestamp_to
            
            # Created timestamp range filtering
            if query_params.created_at_from:
                conditions.append(self.model.created_at >= query_params.created_at_from)
                filters_applied["created_at_from"] = query_params.created_at_from
            
            if query_params.created_at_to:
                conditions.append(self.model.created_at <= query_params.created_at_to)
                filters_applied["created_at_to"] = query_params.created_at_to
            
            # Search text in event data (PostgreSQL JSONB search)
            if query_params.search_text:
                # Use PostgreSQL's JSONB search capabilities
                search_condition = func.cast(self.model.event_data, sa.String).contains(query_params.search_text)
                conditions.append(search_condition)
                filters_applied["search_text"] = query_params.search_text
            
            # Apply all conditions
            if conditions:
                filter_condition = and_(*conditions)
                query = query.where(filter_condition)
                count_query = count_query.where(filter_condition)
            
            # Get total count
            count_result = await db.execute(count_query)
            total = count_result.scalar() or 0
            
            # Apply sorting
            sort_column = getattr(self.model, query_params.sort_by)
            if query_params.sort_order == "desc":
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(sort_column)
            
            # Apply pagination
            query = query.offset(query_params.skip).limit(query_params.limit)
            
            # Execute query
            result = await db.execute(query)
            events = result.scalars().all()
            
            # Calculate pagination info
            page = (query_params.skip // query_params.limit) + 1
            per_page = query_params.limit
            pages = (total + per_page - 1) // per_page
            
            # Convert to read schemas
            event_reads = [schemas.StripeEventRead.model_validate(event) for event in events]
            
            billing_logger.debug(
                f"Queried Stripe events: {len(events)} results, {total} total, "
                f"filters: {list(filters_applied.keys())}"
            )
            
            return schemas.PaginatedStripeEvents(
                items=event_reads,
                total=total,
                page=page,
                per_page=per_page,
                pages=pages,
                filters_applied=filters_applied
            )
            
        except Exception as e:
            billing_logger.error(f"Error querying Stripe events: {e}", exc_info=True)
            raise
    
    async def get_event_statistics(
        self,
        db: AsyncSession,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        org_id: Optional[uuid.UUID] = None
    ) -> schemas.StripeEventStats:
        """
        Get comprehensive statistics about Stripe events.
        
        Args:
            db: Database session
            date_from: Start date for analysis
            date_to: End date for analysis
            org_id: Optional organization filter
            
        Returns:
            Comprehensive statistics about Stripe events
        """
        try:
            # Build base conditions
            conditions = []
            if date_from:
                conditions.append(self.model.created_at >= date_from)
            if date_to:
                conditions.append(self.model.created_at <= date_to)
            if org_id:
                conditions.append(self.model.org_id == org_id)
            
            base_condition = and_(*conditions) if conditions else True
            
            # Total events
            total_query = select(func.count(self.model.id)).where(base_condition)
            total_result = await db.execute(total_query)
            total_events = total_result.scalar() or 0
            
            # Events by type
            type_query = (
                select(self.model.event_type, func.count(self.model.id).label('count'))
                .where(base_condition)
                .group_by(self.model.event_type)
                .order_by(desc('count'))
            )
            type_result = await db.execute(type_query)
            events_by_type = {row.event_type: row.count for row in type_result}
            
            # Events by date (daily aggregation)
            date_query = (
                select(
                    func.date(self.model.created_at).label('event_date'), 
                    func.count(self.model.id).label('count')
                )
                .where(base_condition)
                .group_by(func.date(self.model.created_at))
                .order_by('event_date')
            )
            date_result = await db.execute(date_query)
            events_by_date = {str(row.event_date): row.count for row in date_result}
            
            # Processing success rate
            success_query = (
                select(
                    func.count(self.model.id).label('total'),
                    func.sum(case((self.model.processed_successfully == True, 1), else_=0)).label('successful')
                )
                .where(base_condition)
            )
            success_result = await db.execute(success_query)
            success_row = success_result.first()
            processing_success_rate = (
                (success_row.successful / success_row.total * 100) 
                if success_row.total > 0 else 100.0
            )
            
            # Livemode vs test mode
            mode_query = (
                select(
                    func.sum(case((self.model.livemode == True, 1), else_=0)).label('livemode'),
                    func.sum(case((self.model.livemode == False, 1), else_=0)).label('testmode')
                )
                .where(base_condition)
            )
            mode_result = await db.execute(mode_query)
            mode_row = mode_result.first()
            livemode_events = mode_row.livemode or 0
            test_mode_events = mode_row.testmode or 0
            
            # Unique organizations and users
            org_query = (
                select(func.count(func.distinct(self.model.org_id)))
                .where(and_(base_condition, self.model.org_id.is_not(None)))
            )
            org_result = await db.execute(org_query)
            unique_organizations = org_result.scalar() or 0
            
            user_query = (
                select(func.count(func.distinct(self.model.user_id)))
                .where(and_(base_condition, self.model.user_id.is_not(None)))
            )
            user_result = await db.execute(user_query)
            unique_users = user_result.scalar() or 0
            
            # Time range
            time_range_query = (
                select(
                    func.min(self.model.created_at).label('earliest'),
                    func.max(self.model.created_at).label('latest')
                )
                .where(base_condition)
            )
            time_result = await db.execute(time_range_query)
            time_row = time_result.first()
            time_range = {
                "earliest": time_row.earliest,
                "latest": time_row.latest
            }
            
            return schemas.StripeEventStats(
                total_events=total_events,
                events_by_type=events_by_type,
                events_by_date=events_by_date,
                processing_success_rate=processing_success_rate,
                livemode_events=livemode_events,
                test_mode_events=test_mode_events,
                unique_organizations=unique_organizations,
                unique_users=unique_users,
                time_range=time_range
            )
            
        except Exception as e:
            billing_logger.error(f"Error getting event statistics: {e}", exc_info=True)
            raise
    
    async def get_events_by_org(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        event_types: Optional[List[str]] = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[models.StripeEvent]:
        """
        Get Stripe events for a specific organization.
        
        Args:
            db: Database session
            org_id: Organization ID
            event_types: Optional list of event types to filter
            limit: Maximum number of events to return
            skip: Number of events to skip
            
        Returns:
            List of Stripe events for the organization
        """
        try:
            conditions = [self.model.org_id == org_id]
            
            if event_types:
                conditions.append(self.model.event_type.in_(event_types))
            
            query = (
                select(self.model)
                .where(and_(*conditions))
                .order_by(desc(self.model.created_at))
                .offset(skip)
                .limit(limit)
            )
            
            result = await db.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            billing_logger.error(f"Error getting events by organization: {e}", exc_info=True)
            raise
    
    async def get_failed_events(
        self,
        db: AsyncSession,
        hours_back: int = 24,
        limit: int = 100
    ) -> List[models.StripeEvent]:
        """
        Get recent failed Stripe events for debugging.
        
        Args:
            db: Database session
            hours_back: How many hours back to look
            limit: Maximum number of events to return
            
        Returns:
            List of failed Stripe events
        """
        try:
            cutoff_time = datetime_now_utc() - timedelta(hours=hours_back)
            
            query = (
                select(self.model)
                .where(
                    and_(
                        self.model.processed_successfully == False,
                        self.model.created_at >= cutoff_time
                    )
                )
                .order_by(desc(self.model.created_at))
                .limit(limit)
            )
            
            result = await db.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            billing_logger.error(f"Error getting failed events: {e}", exc_info=True)
            raise
    
    async def extract_context_from_event(
        self,
        event_data: Dict[str, Any]
    ) -> Dict[str, Optional[uuid.UUID]]:
        """
        Extract organization, user, and plan IDs from Stripe event metadata.
        
        This method searches for KiwiQ-specific metadata in various parts of
        the Stripe event to extract contextual information for indexing.
        
        Args:
            event_data: Complete Stripe event data
            
        Returns:
            Dictionary with extracted org_id, user_id, and plan_id
        """
        try:
            context = {
                "org_id": None,
                "user_id": None,
                "plan_id": None
            }
            
            # Helper function to safely extract UUID from string
            def safe_uuid(value: Any) -> Optional[uuid.UUID]:
                if not value:
                    return None
                try:
                    return uuid.UUID(str(value))
                except (ValueError, TypeError):
                    return None

            # Check event object metadata first
            if event_data.get("object", {}).get("metadata"):
                metadata = event_data["object"]["metadata"]
                context["org_id"] = safe_uuid(metadata.get("kiwiq_org_id"))
                context["user_id"] = safe_uuid(metadata.get("kiwiq_user_id"))
                context["plan_id"] = safe_uuid(metadata.get("kiwiq_plan_id"))
            
            subscription_item = event_data.get("object", {}).get("items", {}).get("data", [{}])
            subscription_item = subscription_item[0] if subscription_item else None
            plan_id = subscription_item.get("plan", {}).get("metadata", {}).get("kiwiq_plan_id", {}) if subscription_item else None
            context["plan_id"] = context["plan_id"] or safe_uuid(plan_id)
            
            # For subscription events, check subscription metadata
            if event_data.get("type", "").startswith("customer.subscription"):
                subscription = event_data.get("object", {})
                if subscription.get("metadata"):
                    metadata = subscription["metadata"]
                    context["org_id"] = context["org_id"] or safe_uuid(metadata.get("kiwiq_org_id"))
                    context["user_id"] = context["user_id"] or safe_uuid(metadata.get("kiwiq_user_id"))
                    context["plan_id"] = context["plan_id"] or safe_uuid(metadata.get("kiwiq_plan_id"))
            
            # For invoice events, check payment_intent metadata
            if event_data.get("type", "").startswith("invoice."):
                invoice = event_data.get("object", {})
                if invoice.get("payment_intent"):
                    # Would need to look up payment intent separately if needed
                    pass
            
            # For checkout session events
            if event_data.get("type", "").startswith("checkout.session"):
                session = event_data.get("object", {})
                if session.get("metadata"):
                    metadata = session["metadata"]
                    context["org_id"] = context["org_id"] or safe_uuid(metadata.get("kiwiq_org_id"))
                    context["user_id"] = context["user_id"] or safe_uuid(metadata.get("kiwiq_user_id"))
                    context["plan_id"] = context["plan_id"] or safe_uuid(metadata.get("kiwiq_plan_id"))
            
            return context
            
        except Exception as e:
            billing_logger.warning(f"Error extracting context from event: {e}")
            return {"org_id": None, "user_id": None, "plan_id": None}
    
    async def delete_events_by_query(
        self,
        db: AsyncSession,
        query_params: schemas.StripeEventQuery,
        commit: bool = True
    ) -> int:
        """
        Delete Stripe events based on comprehensive query filters.
        
        This method uses the same filtering logic as query_events but performs
        bulk deletion instead of retrieval. It's designed for admin cleanup
        and maintenance operations.
        
        Args:
            db: Database session
            query_params: Query parameters with filters
            commit: Whether to commit the transaction
            
        Returns:
            Number of events deleted
            
        Raises:
            Exception: If deletion fails
        """
        try:
            # Build base query for deletion
            delete_query = delete(self.model)
            
            # Apply the same filters as query_events
            conditions = []
            
            # Event type filtering
            if query_params.event_types:
                conditions.append(self.model.event_type.in_(query_params.event_types))
            
            # Organization filtering
            if query_params.org_id:
                conditions.append(self.model.org_id == query_params.org_id)
            
            # User filtering
            if query_params.user_id:
                conditions.append(self.model.user_id == query_params.user_id)
            
            # Plan filtering
            if query_params.plan_id:
                conditions.append(self.model.plan_id == query_params.plan_id)
            
            # Livemode filtering
            if query_params.livemode is not None:
                conditions.append(self.model.livemode == query_params.livemode)
            
            # Processing status filtering
            if query_params.processed_successfully is not None:
                conditions.append(self.model.processed_successfully == query_params.processed_successfully)
            
            # Event timestamp range filtering
            if query_params.event_timestamp_from:
                conditions.append(self.model.event_timestamp >= query_params.event_timestamp_from)
            
            if query_params.event_timestamp_to:
                conditions.append(self.model.event_timestamp <= query_params.event_timestamp_to)
            
            # Created timestamp range filtering
            if query_params.created_at_from:
                conditions.append(self.model.created_at >= query_params.created_at_from)
            
            if query_params.created_at_to:
                conditions.append(self.model.created_at <= query_params.created_at_to)
            
            # Search text in event data (PostgreSQL JSONB search)
            if query_params.search_text:
                search_condition = func.cast(self.model.event_data, sa.String).contains(query_params.search_text)
                conditions.append(search_condition)
            
            # Apply all conditions
            if conditions:
                filter_condition = and_(*conditions)
                delete_query = delete_query.where(filter_condition)
            
            # Execute deletion
            result = await db.execute(delete_query)
            deleted_count = result.rowcount
            
            if commit:
                await db.commit()
            
            billing_logger.info(
                f"Bulk deleted {deleted_count} Stripe events with filters: "
                f"event_types={query_params.event_types}, org_id={query_params.org_id}, "
                f"date_range={query_params.created_at_from} to {query_params.created_at_to}"
            )
            
            return deleted_count
            
        except Exception as e:
            if commit:
                await db.rollback()
            billing_logger.error(f"Error bulk deleting Stripe events: {e}", exc_info=True)
            raise
    
    async def delete_events_by_time_window(
        self,
        db: AsyncSession,
        hours_back: Optional[int] = None,
        days_back: Optional[int] = None,
        org_id: Optional[uuid.UUID] = None,
        event_types: Optional[List[str]] = None,
        only_failed: bool = False,
        commit: bool = True
    ) -> int:
        """
        Delete Stripe events within a specified time window.
        
        This method provides time-based cleanup functionality for audit logs,
        allowing deletion of events older than a specified time period.
        
        Args:
            db: Database session
            hours_back: Delete events from last N hours (takes precedence over days_back)
            days_back: Delete events from last N days 
            org_id: Optional organization filter
            event_types: Optional list of event types to delete
            only_failed: If True, only delete failed processing events
            commit: Whether to commit the transaction
            
        Returns:
            Number of events deleted
            
        Raises:
            ValueError: If neither hours_back nor days_back is provided
            Exception: If deletion fails
        """
        try:
            if hours_back is None and days_back is None:
                raise ValueError("Either hours_back or days_back must be specified")
            
            # Calculate cutoff time
            now = datetime_now_utc()
            if hours_back is not None:
                cutoff_time = now - timedelta(hours=hours_back)
                time_desc = f"{hours_back} hours"
            else:
                cutoff_time = now - timedelta(days=days_back)
                time_desc = f"{days_back} days"
            
            # Build delete query
            delete_query = delete(self.model)
            conditions = [self.model.created_at <= cutoff_time]
            
            # Optional filters
            if org_id:
                conditions.append(self.model.org_id == org_id)
            
            if event_types:
                conditions.append(self.model.event_type.in_(event_types))
            
            if only_failed:
                conditions.append(self.model.processed_successfully == False)
            
            # Apply all conditions
            filter_condition = and_(*conditions)
            delete_query = delete_query.where(filter_condition)
            
            # Execute deletion
            result = await db.execute(delete_query)
            deleted_count = result.rowcount
            
            if commit:
                await db.commit()
            
            billing_logger.info(
                f"Time-based deleted {deleted_count} Stripe events older than {time_desc} "
                f"(org_id={org_id}, event_types={event_types}, only_failed={only_failed})"
            )
            
            return deleted_count
            
        except Exception as e:
            if commit:
                await db.rollback()
            billing_logger.error(f"Error time-based deleting Stripe events: {e}", exc_info=True)
            raise 