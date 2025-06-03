"""
Billing CRUD operations for KiwiQ system.

This module defines Data Access Objects (DAOs) for billing-related database operations,
following KiwiQ's established patterns for CRUD operations with dependency injection.
"""

import uuid
from typing import Optional, List, Sequence, Dict, Any, Union
from datetime import datetime, timedelta, date

from sqlalchemy import delete, update, and_, or_, func, desc, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import SQLModel

from kiwi_app.auth.crud import BaseDAO
from kiwi_app.billing import models, schemas
from kiwi_app.billing.models import CreditType, SubscriptionStatus, CreditSourceType, PaymentStatus
from kiwi_app.billing.exceptions import InsufficientCreditsException
from kiwi_app.auth.utils import datetime_now_utc
from kiwi_app.utils import get_kiwi_logger

# Get logger for billing operations
billing_logger = get_kiwi_logger(name="kiwi_app.billing")


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
    
    async def get_by_org_id(self, db: AsyncSession, org_id: uuid.UUID) -> Optional[models.OrganizationSubscription]:
        """Get active subscription for an organization."""
        statement = select(self.model).options(
            selectinload(self.model.plan)
        ).where(self.model.org_id == org_id)
        result = await db.exec(statement)
        return result.scalars().first()
    
    async def get_by_stripe_subscription_id(self, db: AsyncSession, stripe_subscription_id: str) -> Optional[models.OrganizationSubscription]:
        """Get subscription by Stripe subscription ID."""
        statement = select(self.model).options(
            selectinload(self.model.plan)
        ).where(self.model.stripe_subscription_id == stripe_subscription_id)
        result = await db.exec(statement)
        return result.scalars().first()
    
    async def get_by_stripe_customer_id(self, db: AsyncSession, stripe_customer_id: str) -> Optional[models.OrganizationSubscription]:
        """Get subscription by Stripe customer ID."""
        statement = select(self.model).options(
            selectinload(self.model.plan)
        ).where(self.model.stripe_customer_id == stripe_customer_id)
        result = await db.exec(statement)
        return result.scalars().first()
    
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
        period_start: Optional[datetime] = None
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
    
    async def consume_credits_atomic(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_type: CreditType,
        credits_to_consume: float,
        max_overage_allowed_fraction: float = 0.0,
        commit: bool = True,
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
                conditions.append(
                    # Race-condition safe check: ensure consumption doesn't exceed limit
                    models.OrganizationNetCredits.credits_consumed + credits_to_consume <= 
                    models.OrganizationNetCredits.credits_granted * (1 + max_overage_allowed_fraction)
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
            
            # Check if the update was successful (row returned)
            if updated_row is None:
                # Update failed - either record doesn't exist or limit exceeded
                # Get current state to provide detailed error
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
                credits_consumed=credits_to_consume,
                remaining_balance=current_balance,
                total_consumed=updated_credits_consumed,
                total_granted=updated_credits_granted,
                is_overage=is_overage,
                overage_amount=overage_amount,
                was_locked=True
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
                commit=commit
            )
            
            billing_logger.debug(
                f"Allocated {estimated_credits} {credit_type.value} credits for operation {operation_id}"
            )
            
            return schemas.CreditAllocationResult(
                success=True,
                operation_id=operation_id,
                allocated_credits=estimated_credits,
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
        commit: bool = True
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
                max_overage_allowed_fraction=0.0,  # No additional overage for adjustments
                commit=commit
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
            
            update_stmt = (
                update(models.OrganizationNetCredits)
                .where(
                    and_(*conditions)
                )
                .values(
                    credits_granted=func.greatest(0, models.OrganizationNetCredits.credits_granted - expired_credits),
                    credits_consumed=func.least(
                        models.OrganizationNetCredits.credits_consumed,
                        func.greatest(0, models.OrganizationNetCredits.credits_consumed - expired_credits)
                    ),
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
        commit: bool = True
    ) -> List[schemas.CreditExpirationResult]:
        """
        Batch expire credits for multiple credit types.
        
        Args:
            db: Database session
            org_id: Organization ID
            credit_expirations: List of credit expirations to process
            
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
                    commit=commit
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


class CreditPurchaseDAO(BaseDAO[models.CreditPurchase, schemas.CreditPurchaseRequest, SQLModel]):
    """Data Access Object for credit purchase operations."""
    
    def __init__(self):
        super().__init__(models.CreditPurchase)
    
    async def create_purchase(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        stripe_payment_intent_id: str,
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
            stripe_payment_intent_id=stripe_payment_intent_id,
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
    
    async def get_by_stripe_payment_intent_id(
        self, 
        db: AsyncSession, 
        stripe_payment_intent_id: str
    ) -> Optional[models.CreditPurchase]:
        """Get credit purchase by Stripe payment intent ID."""
        statement = select(self.model).where(self.model.stripe_payment_intent_id == stripe_payment_intent_id)
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