"""
Billing services for KiwiQ system.

This module defines the service layer for billing operations, including subscription management,
credit tracking, usage events, and Stripe integration. It follows KiwiQ's established patterns
for service layer architecture with dependency injection.
"""

import uuid
import stripe
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from kiwi_app.billing import crud, models, schemas
from kiwi_app.billing.models import CreditType, SubscriptionStatus, CreditSourceType, PaymentStatus
from kiwi_app.billing.exceptions import (
    InsufficientCreditsException,
    SubscriptionNotFoundException,
    SubscriptionPlanNotFoundException,
    InvalidSubscriptionStateException,
    PaymentMethodRequiredException,
    StripeIntegrationException,
    PromotionCodeNotFoundException,
    PromotionCodeExpiredException,
    PromotionCodeExhaustedException,
    PromotionCodeAlreadyUsedException,
    PromotionCodeNotAllowedException,
    CreditPurchaseNotFoundException,
    OveragePolicyViolationException,
    SeatLimitExceededException,
    BillingConfigurationException,
    BillingException
)
from kiwi_app.auth.models import Organization, User
from kiwi_app.auth.utils import datetime_now_utc
from kiwi_app.settings import settings
from kiwi_app.utils import get_kiwi_logger

# Get logger for billing operations
billing_logger = get_kiwi_logger(name="kiwi_app.billing")

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = settings.STRIPE_API_VERSION


class BillingService:
    """Service layer for billing operations."""
    
    def __init__(
        self,
        subscription_plan_dao: crud.SubscriptionPlanDAO,
        org_subscription_dao: crud.OrganizationSubscriptionDAO,
        org_credits_dao: crud.OrganizationCreditsDAO,
        org_net_credits_dao: crud.OrganizationNetCreditsDAO,
        usage_event_dao: crud.UsageEventDAO,
        credit_purchase_dao: crud.CreditPurchaseDAO,
        promotion_code_dao: crud.PromotionCodeDAO,
        promotion_code_usage_dao: crud.PromotionCodeUsageDAO
    ):
        """Initialize service with DAO instances."""
        self.subscription_plan_dao = subscription_plan_dao
        self.org_subscription_dao = org_subscription_dao
        self.org_credits_dao = org_credits_dao
        self.org_net_credits_dao = org_net_credits_dao
        self.usage_event_dao = usage_event_dao
        self.credit_purchase_dao = credit_purchase_dao
        self.promotion_code_dao = promotion_code_dao
        self.promotion_code_usage_dao = promotion_code_usage_dao
    
    # --- Subscription Plan Management --- #
    
    async def create_subscription_plan(
        self,
        db: AsyncSession,
        plan_data: schemas.SubscriptionPlanCreate
    ) -> models.SubscriptionPlan:
        """
        Create a new subscription plan with Stripe integration.
        
        This method creates both the database record and the corresponding
        Stripe product and price objects for billing integration.
        """
        try:
            # Create Stripe product if not provided
            if not plan_data.stripe_product_id:
                stripe_product = stripe.Product.create(
                    name=plan_data.name,
                    description=plan_data.description,
                    metadata={
                        "kiwiq_plan": "true",
                        "max_seats": str(plan_data.max_seats),
                        "trial_days": str(plan_data.trial_days)
                    }
                )
                plan_data.stripe_product_id = stripe_product.id
            
            # Create the plan in database
            plan = await self.subscription_plan_dao.create(db, obj_in=plan_data)
            
            # Create Stripe prices for monthly and annual billing
            # Convert dollars to cents for Stripe
            monthly_price = stripe.Price.create(
                product=plan.stripe_product_id,
                unit_amount=int(plan.monthly_price * 100),  # Convert dollars to cents
                currency="usd",
                recurring={"interval": "month"},
                metadata={"kiwiq_plan_id": str(plan.id), "billing_period": "monthly"}
            )
            
            annual_price = stripe.Price.create(
                product=plan.stripe_product_id,
                unit_amount=int(plan.annual_price * 100),  # Convert dollars to cents
                currency="usd",
                recurring={"interval": "year"},
                metadata={"kiwiq_plan_id": str(plan.id), "billing_period": "annual"}
            )
            
            # Update plan with Stripe price IDs
            plan_update = schemas.SubscriptionPlanUpdate(
                stripe_price_id_monthly=monthly_price.id,
                stripe_price_id_annual=annual_price.id
            )
            plan = await self.subscription_plan_dao.update(db, db_obj=plan, obj_in=plan_update)
            
            billing_logger.info(f"Created subscription plan: {plan.name} (ID: {plan.id})")
            return plan
            
        except stripe.StripeError as e:
            billing_logger.error(f"Stripe error creating plan: {e}")
            raise StripeIntegrationException(
                detail="Failed to create subscription plan",
                stripe_error_code=e.code,
                stripe_error_message=str(e)
            )
    
    async def get_subscription_plans(
        self,
        db: AsyncSession,
        active_only: bool = True
    ) -> List[models.SubscriptionPlan]:
        """Get available subscription plans."""
        if active_only:
            return await self.subscription_plan_dao.get_active_plans(db)
        else:
            return await self.subscription_plan_dao.get_multi(db)
    
    # --- Subscription Management --- #
    
    async def create_subscription(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        subscription_data: schemas.SubscriptionCreate,
        user: User
    ) -> models.OrganizationSubscription:
        """
        Create a new subscription for an organization.
        
        This method handles the complete subscription creation process including
        Stripe customer creation, subscription setup, and initial credit allocation.
        """
        # Get the subscription plan
        plan = await self.subscription_plan_dao.get(db, subscription_data.plan_id)
        if not plan:
            raise SubscriptionPlanNotFoundException()
        
        # Check if organization already has a subscription
        existing_subscription = await self.org_subscription_dao.get_by_org_id(db, org_id)
        if existing_subscription:
            raise InvalidSubscriptionStateException("Organization already has an active subscription")
        
        try:
            # Create or get Stripe customer
            stripe_customer = await self._get_or_create_stripe_customer(db, org_id, user)
            
            # Attach payment method if provided
            if subscription_data.payment_method_id:
                stripe.PaymentMethod.attach(
                    subscription_data.payment_method_id,
                    customer=stripe_customer.id
                )
                
                # Set as default payment method
                stripe.Customer.modify(
                    stripe_customer.id,
                    invoice_settings={"default_payment_method": subscription_data.payment_method_id}
                )
            
            # Determine trial period
            trial_days = subscription_data.trial_days or plan.trial_days
            trial_end = None
            if trial_days > 0 and plan.is_trial_eligible:
                trial_end = datetime_now_utc() + timedelta(days=trial_days)
            
            # Create Stripe subscription
            stripe_price_id = plan.stripe_price_id_annual if subscription_data.is_annual else plan.stripe_price_id_monthly
            
            stripe_subscription_params = {
                "customer": stripe_customer.id,
                "items": [{"price": stripe_price_id, "quantity": subscription_data.seats_count}],
                "metadata": {
                    "kiwiq_org_id": str(org_id),
                    "kiwiq_plan_id": str(plan.id),
                    "kiwiq_user_id": str(user.id)
                }
            }
            
            if trial_end:
                stripe_subscription_params["trial_end"] = int(trial_end.timestamp())
            
            stripe_subscription = stripe.Subscription.create(**stripe_subscription_params)
            
            # Create subscription record in database
            now = datetime_now_utc()
            subscription = models.OrganizationSubscription(
                org_id=org_id,
                plan_id=plan.id,
                stripe_subscription_id=stripe_subscription.id,
                stripe_subscription_item_id=stripe_subscription.items.data[0].id,
                stripe_customer_id=stripe_customer.id,
                status=SubscriptionStatus.TRIAL if trial_end else SubscriptionStatus.ACTIVE,
                current_period_start=datetime.fromtimestamp(stripe_subscription.current_period_start),
                current_period_end=datetime.fromtimestamp(stripe_subscription.current_period_end),
                seats_count=subscription_data.seats_count,
                is_annual=subscription_data.is_annual,
                trial_start=now if trial_end else None,
                trial_end=trial_end,
                is_trial_active=bool(trial_end),
                created_at=now,
                updated_at=now
            )
            
            subscription = await self.org_subscription_dao.create(db, obj_in=subscription)
            
            # Allocate initial credits
            await self._allocate_subscription_credits(db, subscription, plan)
            
            billing_logger.info(f"Created subscription for org {org_id}: {subscription.id}")
            return subscription
            
        except stripe.StripeError as e:
            billing_logger.error(f"Stripe error creating subscription: {e}")
            raise StripeIntegrationException(
                detail="Failed to create subscription",
                stripe_error_code=e.code,
                stripe_error_message=str(e)
            )
    
    async def get_organization_subscription(
        self,
        db: AsyncSession,
        org_id: uuid.UUID
    ) -> Optional[models.OrganizationSubscription]:
        """Get the active subscription for an organization."""
        return await self.org_subscription_dao.get_by_org_id(db, org_id)
    
    async def update_subscription(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        subscription_update: schemas.SubscriptionUpdate
    ) -> models.OrganizationSubscription:
        """Update an existing subscription."""
        subscription = await self.org_subscription_dao.get_by_org_id(db, org_id)
        if not subscription:
            raise SubscriptionNotFoundException()
        
        try:
            # Handle plan changes
            if subscription_update.plan_id and subscription_update.plan_id != subscription.plan_id:
                new_plan = await self.subscription_plan_dao.get(db, subscription_update.plan_id)
                if not new_plan:
                    raise SubscriptionPlanNotFoundException()
                
                # Update Stripe subscription
                stripe_price_id = new_plan.stripe_price_id_annual if subscription.is_annual else new_plan.stripe_price_id_monthly
                stripe.SubscriptionItem.modify(
                    subscription.stripe_subscription_item_id,
                    price=stripe_price_id,
                    proration_behavior="create_prorations"
                )
                
                subscription.plan_id = new_plan.id
                
                # Allocate credits for new plan
                await self._allocate_subscription_credits(db, subscription, new_plan)
            
            # Handle seat count changes
            if subscription_update.seats_count and subscription_update.seats_count != subscription.seats_count:
                stripe.SubscriptionItem.modify(
                    subscription.stripe_subscription_item_id,
                    quantity=subscription_update.seats_count,
                    proration_behavior="create_prorations"
                )
                subscription.seats_count = subscription_update.seats_count
            
            # Handle cancellation
            if subscription_update.cancel_at_period_end is not None:
                if subscription_update.cancel_at_period_end:
                    stripe.Subscription.modify(
                        subscription.stripe_subscription_id,
                        cancel_at_period_end=True
                    )
                else:
                    stripe.Subscription.modify(
                        subscription.stripe_subscription_id,
                        cancel_at_period_end=False
                    )
                subscription.cancel_at_period_end = subscription_update.cancel_at_period_end
            
            subscription.updated_at = datetime_now_utc()
            subscription = await self.org_subscription_dao.update(db, db_obj=subscription, obj_in=subscription_update)
            
            billing_logger.info(f"Updated subscription for org {org_id}: {subscription.id}")
            return subscription
            
        except stripe.StripeError as e:
            billing_logger.error(f"Stripe error updating subscription: {e}")
            raise StripeIntegrationException(
                detail="Failed to update subscription",
                stripe_error_code=e.code,
                stripe_error_message=str(e)
            )
    
    # --- Credit Management --- #
    
    async def get_credit_balances(
        self,
        db: AsyncSession,
        org_id: uuid.UUID
    ) -> List[schemas.CreditBalance]:
        """
        Get current credit balances with optimized net credits query.
        
        This method uses the OrganizationNetCredits table for fast balance
        retrieval without complex aggregations.
        
        Args:
            db: Database session
            org_id: Organization ID
            
        Returns:
            List of credit balances by type
        """
        try:
            balances = []
            
            # Get net credits for all credit types
            for credit_type in CreditType:
                net_credits = await self.org_net_credits_dao.get_net_credits_by_org_and_type(
                    db=db,
                    org_id=org_id,
                    credit_type=credit_type
                )
                
                if net_credits:
                    current_balance = max(0, net_credits.credits_granted - net_credits.credits_consumed)
                    is_overage = net_credits.credits_consumed > net_credits.credits_granted
                    overage_amount = max(0, net_credits.credits_consumed - net_credits.credits_granted)
                    
                    balance = schemas.CreditBalance(
                        credit_type=credit_type,
                        credits_balance=current_balance,
                        credits_granted=net_credits.credits_granted,
                        credits_consumed=net_credits.credits_consumed,
                        is_overage=is_overage,
                        overage_amount=overage_amount
                    )
                else:
                    # No credits allocated yet
                    balance = schemas.CreditBalance(
                        credit_type=credit_type,
                        credits_balance=0,
                        credits_granted=0,
                        credits_consumed=0,
                        is_overage=False,
                        overage_amount=0
                    )
                
                balances.append(balance)
            
            return balances
            
        except Exception as e:
            billing_logger.error(f"Error getting credit balances: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail="Failed to retrieve credit balances"
            )
    
    async def consume_credits(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        consumption_request: schemas.CreditConsumptionRequest
    ) -> schemas.CreditConsumptionResult:
        """
        Consume credits with optimized atomic updates and overage handling.
        
        This method uses the new high-performance credit consumption approach
        with direct UPDATE queries and transaction locks for better scalability.
        
        Args:
            db: Database session
            org_id: Organization ID
            user_id: User ID consuming credits
            consumption_request: Credit consumption details
            
        Returns:
            CreditConsumptionResult: Consumption result with balance info
            
        Raises:
            InsufficientCreditsException: If not enough credits available
        """
        try:
            # Get overage policy for this organization and credit type
            overage_settings = await self._get_overage_settings(org_id, consumption_request.credit_type)
            max_overage_allowed_fraction = overage_settings.get("overage_percentage", 10) / 100.0
            
            # Use atomic credit consumption
            consumption_result = await self.org_net_credits_dao.consume_credits_atomic(
                db=db,
                org_id=org_id,
                credit_type=consumption_request.credit_type,
                credits_to_consume=consumption_request.credits_consumed,
                max_overage_allowed_fraction=max_overage_allowed_fraction,
                commit=False
            )
            
            # Create usage event for audit and analytics
            await self._create_usage_event(
                db=db,
                org_id=org_id,
                user_id=user_id,
                consumption_request=consumption_request,
                is_overage=consumption_result.is_overage
            )
            
            # Commit the transaction
            await db.commit()
            
            # Prepare result
            result = schemas.CreditConsumptionResult(
                success=True,
                credits_consumed=consumption_result.credits_consumed,
                remaining_balance=consumption_result.remaining_balance,
                is_overage=consumption_result.is_overage,
                grace_credits_used=consumption_result.overage_amount,
                warning="Using overage grace credits" if consumption_result.is_overage else None
            )
            
            # Log consumption for monitoring
            billing_logger.info(
                f"Consumed {consumption_request.credits_consumed} {consumption_request.credit_type.value} "
                f"credits for org {org_id} (event: {consumption_request.event_type}, "
                f"overage: {consumption_result.is_overage})"
            )
            
            return result
            
        except InsufficientCreditsException:
            # Re-raise insufficient credits exceptions
            raise
        except Exception as e:
            # Rollback transaction on error
            await db.rollback()
            billing_logger.error(f"Error consuming credits: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to consume credits: {str(e)}"
            )
    
    async def allocate_credits_for_operation(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        credit_type: CreditType,
        estimated_credits: float,
        operation_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> schemas.CreditAllocationResult:
        """
        Allocate credits for a long-running operation.
        
        This method pre-allocates credits to prevent race conditions in
        concurrent usage scenarios, particularly useful for long-running
        operations like complex workflows or batch processing.
        
        Args:
            db: Database session
            org_id: Organization ID
            user_id: User ID performing the operation
            credit_type: Type of credits to allocate
            estimated_credits: Estimated credits needed
            operation_id: Unique operation identifier
            metadata: Optional operation metadata
            
        Returns:
            CreditAllocationResult: Allocation result with tracking info
        """
        try:
            # Get overage policy
            overage_settings = await self._get_overage_settings(org_id, credit_type)
            max_overage_allowed_fraction = overage_settings.get("overage_percentage", 10) / 100.0
            
            # Allocate credits using atomic operation
            allocation_result = await self.org_net_credits_dao.allocate_credits_for_operation(
                db=db,
                org_id=org_id,
                credit_type=credit_type,
                estimated_credits=estimated_credits,
                operation_id=operation_id,
                max_overage_allowed_fraction=max_overage_allowed_fraction,
                commit=False
            )
            
            # Create usage event for the allocation
            allocation_event = schemas.CreditConsumptionRequest(
                credit_type=credit_type,
                credits_consumed=estimated_credits,
                event_type="credit_allocation",
                metadata={
                    "operation_id": operation_id,
                    "is_allocation": True,
                    "estimated_credits": estimated_credits,
                    **(metadata or {})
                }
            )
            
            await self._create_usage_event(
                db=db,
                org_id=org_id,
                user_id=user_id,
                consumption_request=allocation_event,
                is_overage=allocation_result.is_overage
            )
            
            # Commit the transaction
            await db.commit()
            
            return allocation_result
            
        except InsufficientCreditsException:
            raise
        except Exception as e:
            # Rollback transaction on error
            await db.rollback()
            billing_logger.error(f"Error allocating credits: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to allocate credits: {str(e)}"
            )
    
    async def adjust_allocated_credits(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        credit_type: CreditType,
        operation_id: str,
        actual_credits: float,
        allocated_credits: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> schemas.CreditAdjustmentResult:
        """
        Adjust allocated credits with actual consumption.
        
        This method handles the final adjustment between estimated and actual
        credit consumption, ensuring accurate billing for long-running operations.
        
        Args:
            db: Database session
            org_id: Organization ID
            user_id: User ID
            credit_type: Type of credits
            operation_id: Operation identifier
            actual_credits: Actual credits consumed
            allocated_credits: Previously allocated credits
            metadata: Optional adjustment metadata
            
        Returns:
            CreditAdjustmentResult: Adjustment result
        """
        try:
            # Perform the adjustment using atomic operation
            adjustment_result = await self.org_net_credits_dao.adjust_allocation_with_actual(
                db=db,
                org_id=org_id,
                credit_type=credit_type,
                operation_id=operation_id,
                actual_credits=actual_credits,
                allocated_credits=allocated_credits,
                commit=False
            )
            
            # Create usage event for the adjustment
            if adjustment_result.adjustment_needed:
                adjustment_event = schemas.CreditConsumptionRequest(
                    credit_type=credit_type,
                    credits_consumed=abs(adjustment_result.credit_difference),  # Use absolute value
                    event_type="credit_adjustment",
                    metadata={
                        "operation_id": operation_id,
                        "is_adjustment": True,
                        "allocated_credits": allocated_credits,
                        "actual_credits": actual_credits,
                        "credit_difference": adjustment_result.credit_difference,
                        "adjustment_type": adjustment_result.adjustment_type,
                        **(metadata or {})
                    }
                )
                
                await self._create_usage_event(
                    db=db,
                    org_id=org_id,
                    user_id=user_id,
                    consumption_request=adjustment_event,
                    is_overage=False  # Adjustments don't create new overage
                )
            
            # Commit the transaction
            await db.commit()
            
            return adjustment_result
            
        except Exception as e:
            # Rollback transaction on error
            await db.rollback()
            billing_logger.error(f"Error adjusting allocated credits: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to adjust allocated credits: {str(e)}"
            )
    
    async def add_credits_to_organization(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_type: CreditType,
        credits_to_add: float,
        source_type: CreditSourceType,
        source_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> schemas.CreditAdditionResult:
        """
        Add credits to organization with automatic overage adjustment.
        
        This method uses the optimized credit addition logic that automatically
        handles overage adjustments when new credits are added.
        
        Args:
            db: Database session
            org_id: Organization ID
            credit_type: Type of credits to add
            credits_to_add: Number of credits to add
            source_type: Source of the credits
            source_id: Source identifier
            expires_at: Expiration date
            metadata: Additional metadata
            
        Returns:
            CreditAdditionResult: Addition result with overage adjustment info
        """
        try:
            # Create audit record for the allocation
            await self.org_credits_dao.allocate_credits(
                db=db,
                org_id=org_id,
                credit_type=credit_type,
                amount=credits_to_add,
                source_type=source_type,
                source_id=source_id,
                source_metadata=metadata,
                expires_at=expires_at
            )
            
            # Use the optimized credit addition
            result = await self.org_net_credits_dao.add_credits(
                db=db,
                org_id=org_id,
                credit_type=credit_type,
                credits_to_add=credits_to_add,
                source_type=source_type,
                source_id=source_id,
                expires_at=expires_at,
                commit=False
            )
            
            # Commit the transaction
            await db.commit()
            
            billing_logger.info(
                f"Added {credits_to_add} {credit_type.value} credits to org {org_id} "
                f"from {source_type.value}"
            )
            
            return result
            
        except Exception as e:
            # Rollback transaction on error
            await db.rollback()
            billing_logger.error(f"Error adding credits to organization: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to add credits: {str(e)}"
            )
    
    async def _get_overage_settings(
        self,
        org_id: uuid.UUID,
        credit_type: CreditType
    ) -> Dict[str, Any]:
        """
        Get overage settings for organization and credit type.
        
        This method determines the overage policy for credit consumption,
        including grace periods and maximum allowed overage.
        
        Args:
            org_id: Organization ID
            credit_type: Type of credits
            
        Returns:
            dict: Overage settings
        """
        try:
            # For now, use default overage settings
            # In production, these could be stored per organization or plan
            default_overage_percentage = 10  # 10% grace period
            
            # Calculate overage based on current granted credits
            # This would ideally be cached or stored in the organization settings
            base_credits = 100  # Default base for calculation
            
            max_overage_credits = int(base_credits * (default_overage_percentage / 100))
            
            return {
                "allow_overage": True,
                "overage_percentage": default_overage_percentage,
                "max_overage_credits": max_overage_credits,
                "grace_period_days": 3
            }
            
        except Exception as e:
            billing_logger.warning(f"Error getting overage settings, using defaults: {e}")
            return {
                "allow_overage": True,
                "overage_percentage": 10,
                "max_overage_credits": 10,
                "grace_period_days": 3
            }
    
    # --- Promotion Code Management --- #
    
    async def apply_promotion_code(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        code_application: schemas.PromotionCodeApply
    ) -> schemas.PromotionCodeApplyResult:
        """Apply a promotion code to grant credits to an organization."""
        try:
            # Get the promotion code
            promo_code = await self.promotion_code_dao.get_by_code(db, code_application.code)
            if not promo_code:
                raise PromotionCodeNotFoundException(code_application.code)
            
            # Check eligibility
            is_eligible, reason = await self.promotion_code_dao.check_usage_eligibility(db, promo_code, org_id)
            if not is_eligible:
                if "expired" in reason.lower():
                    raise PromotionCodeExpiredException(code_application.code)
                elif "usage limit" in reason.lower():
                    raise PromotionCodeExhaustedException(code_application.code)
                elif "already used" in reason.lower():
                    raise PromotionCodeAlreadyUsedException(code_application.code)
                elif "not allowed" in reason.lower():
                    raise PromotionCodeNotAllowedException(code_application.code)
                elif "not active" in reason.lower():
                    raise PromotionCodeNotAllowedException(code_application.code)
                else:
                    raise HTTPException(status_code=400, detail=reason)
            
            # Calculate expiration for granted credits
            expires_at = None
            if promo_code.granted_credits_expire_days:
                expires_at = datetime_now_utc() + timedelta(days=promo_code.granted_credits_expire_days)
            
            # Create audit record for the allocation
            await self.org_credits_dao.allocate_credits(
                db=db,
                org_id=org_id,
                credit_type=promo_code.credit_type,
                amount=promo_code.credits_amount,
                source_type=CreditSourceType.PROMOTION,
                source_id=code_application.code,
                source_metadata={"promo_code_id": str(promo_code.id)},
                expires_at=expires_at
            )
            
            # Add to net credits
            await self.org_net_credits_dao.add_credits(
                db=db,
                org_id=org_id,
                credit_type=promo_code.credit_type,
                credits_to_add=promo_code.credits_amount,
                source_type=CreditSourceType.PROMOTION,
                source_id=code_application.code,
                expires_at=expires_at,
                commit=False
            )
            
            # Record usage
            await self.promotion_code_usage_dao.create_usage(
                db=db,
                promo_code_id=promo_code.id,
                org_id=org_id,
                user_id=user_id,
                credits_applied=promo_code.credits_amount
            )
            
            # Update promotion code usage count
            promo_code.uses_count += 1
            promo_code.updated_at = datetime_now_utc()
            await self.promotion_code_dao.update(db, db_obj=promo_code, obj_in=schemas.PromotionCodeUpdate())
            
            # Commit the transaction
            await db.commit()
            
            billing_logger.info(f"Applied promotion code {code_application.code} to org {org_id}")
            
            return schemas.PromotionCodeApplyResult(
                success=True,
                credits_applied=promo_code.credits_amount,
                credit_type=promo_code.credit_type,
                message=f"Successfully applied {promo_code.credits_amount} {promo_code.credit_type.value} credits"
            )
            
        except (PromotionCodeNotFoundException, PromotionCodeExpiredException, 
                PromotionCodeExhaustedException, PromotionCodeAlreadyUsedException,
                PromotionCodeNotAllowedException, HTTPException):
            # Re-raise promotion code specific exceptions
            raise
        except Exception as e:
            # Rollback transaction on error
            await db.rollback()
            billing_logger.error(f"Error applying promotion code: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to apply promotion code: {str(e)}"
            )
    
    # --- Usage Analytics --- #
    
    async def get_usage_summary(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime
    ) -> schemas.UsageSummary:
        """Get usage summary for an organization within a date range."""
        # Get usage summary from DAO
        summary_data = await self.usage_event_dao.get_usage_summary(db, org_id, start_date, end_date)
        
        # Get current credit balances
        credit_balances = await self.get_credit_balances(db, org_id)
        
        return schemas.UsageSummary(
            org_id=org_id,
            period_start=start_date,
            period_end=end_date,
            credit_balances=credit_balances,
            total_events=summary_data['total_events'],
            events_by_type=summary_data['events_by_type'],
            overage_events=summary_data['overage_events']
        )
    
    async def get_billing_dashboard(
        self,
        db: AsyncSession,
        org_id: uuid.UUID
    ) -> schemas.BillingDashboard:
        """Get comprehensive billing dashboard data for an organization."""
        # Get subscription with plan details
        subscription = await self.org_subscription_dao.get_by_org_id(db, org_id)
        
        # Get credit balances
        credit_balances = await self.get_credit_balances(db, org_id)
        
        # Get recent usage events (last 30 days)
        end_date = datetime_now_utc()
        start_date = end_date - timedelta(days=30)
        recent_usage = await self.usage_event_dao.get_by_org_and_period(
            db, org_id, start_date, end_date, limit=10
        )
        
        # Get recent credit purchases
        recent_purchases = await self.credit_purchase_dao.get_by_org_id(db, org_id, limit=5)
        
        # Check for overage warnings
        overage_warnings = []
        for balance in credit_balances:
            if balance.credits_balance == 0:
                overage_warnings.append(f"No {balance.credit_type.value} credits remaining")
            elif balance.credits_balance < 10:  # Low balance warning
                overage_warnings.append(f"Low {balance.credit_type.value} credits: {balance.credits_balance} remaining")
        
        # Get upcoming renewal date
        upcoming_renewal = None
        if subscription and subscription.status == SubscriptionStatus.ACTIVE:
            upcoming_renewal = subscription.current_period_end
        
        return schemas.BillingDashboard(
            org_id=org_id,
            subscription=subscription,
            credit_balances=credit_balances,
            recent_usage=[
                schemas.UsageEventRead(
                    id=event.id,
                    org_id=event.org_id,
                    user_id=event.user_id,
                    event_type=event.event_type,
                    credit_type=event.credit_type,
                    credits_consumed=event.credits_consumed,
                    usage_metadata=event.usage_metadata,
                    is_overage=event.is_overage,
                    grace_credits_used=0,  # Default value for events without this field
                    cost_cents=None,  # Default value for events without this field
                    created_at=event.created_at
                ) for event in recent_usage
            ],
            recent_purchases=[schemas.CreditPurchaseRead.model_validate(purchase) for purchase in recent_purchases],
            upcoming_renewal=upcoming_renewal,
            overage_warnings=overage_warnings
        )
    
    # --- Webhook Processing --- #
    
    async def process_stripe_webhook(
        self,
        db: AsyncSession,
        webhook_event: schemas.StripeWebhookEvent
    ) -> bool:
        """
        Process Stripe webhook events.
        
        This method handles various Stripe events to keep the billing system
        in sync with Stripe's state.
        """
        try:
            event_type = webhook_event.type
            event_data = webhook_event.data
            
            billing_logger.info(f"Processing Stripe webhook: {event_type} (ID: {webhook_event.id})")
            
            if event_type == "customer.subscription.updated":
                await self._handle_subscription_updated(db, event_data)
            elif event_type == "customer.subscription.deleted":
                await self._handle_subscription_deleted(db, event_data)
            elif event_type == "invoice.payment_succeeded":
                await self._handle_payment_succeeded(db, event_data)
            elif event_type == "invoice.payment_failed":
                await self._handle_payment_failed(db, event_data)
            elif event_type == "payment_intent.succeeded":
                await self._handle_payment_intent_succeeded(db, event_data)
            elif event_type == "payment_intent.payment_failed":
                await self._handle_payment_intent_failed(db, event_data)
            else:
                billing_logger.info(f"Unhandled webhook event type: {event_type}")
            
            return True
            
        except Exception as e:
            billing_logger.error(f"Error processing webhook {webhook_event.id}: {e}", exc_info=True)
            return False
    
    # --- Private Helper Methods --- #
    
    async def _get_or_create_stripe_customer(self, db: AsyncSession, org_id: uuid.UUID, user: User) -> stripe.Customer:
        """Get or create a Stripe customer for an organization."""
        # Check if customer already exists
        existing_subscription = await self.org_subscription_dao.get_by_org_id(db, org_id)
        if existing_subscription and existing_subscription.stripe_customer_id:
            return stripe.Customer.retrieve(existing_subscription.stripe_customer_id)
        
        # Create new customer
        customer = stripe.Customer.create(
            email=user.email,
            name=user.full_name or user.email,
            metadata={
                "kiwiq_org_id": str(org_id),
                "kiwiq_user_id": str(user.id)
            }
        )
        
        return customer
    
    async def _allocate_subscription_credits(
        self,
        db: AsyncSession,
        subscription: models.OrganizationSubscription,
        plan: models.SubscriptionPlan,
        is_renewal: bool = False
    ) -> None:
        """Allocate monthly credits for a subscription, with optional credit rotation for renewals."""
        now = datetime_now_utc()
        period_end = subscription.current_period_end
        
        # Determine expiration based on subscription type
        if subscription.is_trial_active:
            expires_at = now + timedelta(days=settings.TRIAL_CREDITS_EXPIRE_DAYS)
        else:
            expires_at = period_end + timedelta(days=settings.SUBSCRIPTION_CREDITS_EXPIRE_DAYS)
        
        # If this is a renewal and not a trial, use credit rotation
        if is_renewal and not subscription.is_trial_active:
            # Use credit rotation for subscription renewals
            new_credits = {CreditType(credit_type): amount for credit_type, amount in plan.monthly_credits.items()}
            
            rotation_result = await self.rotate_subscription_credits(
                db=db,
                subscription_id=subscription.id,
                new_credits=new_credits,
                new_expires_at=expires_at
            )
            
            billing_logger.info(
                f"Rotated subscription credits for subscription {subscription.id}: "
                f"expired {rotation_result['total_expired_credits']}, "
                f"added {rotation_result['total_added_credits']} credits"
            )
        else:
            # For new subscriptions or trial-to-paid transitions, allocate fresh credits
            for credit_type_str, amount in plan.monthly_credits.items():
                credit_type = CreditType(credit_type_str)
                
                # Create audit record
                await self.org_credits_dao.allocate_credits(
                    db=db,
                    org_id=subscription.org_id,
                    credit_type=credit_type,
                    amount=amount,
                    source_type=CreditSourceType.SUBSCRIPTION,
                    source_id=str(subscription.id),
                    source_metadata={
                        "subscription_id": str(subscription.id),
                        "stripe_subscription_id": subscription.stripe_subscription_id,
                        "plan_id": str(subscription.plan_id),
                        "billing_period": "trial" if subscription.is_trial_active else "monthly",
                        "period_start": now.isoformat(),
                        "period_end": period_end.isoformat(),
                        "is_renewal": is_renewal
                    },
                    expires_at=expires_at
                )
                
                # Add to net credits
                await self.org_net_credits_dao.add_credits(
                    db=db,
                    org_id=subscription.org_id,
                    credit_type=credit_type,
                    credits_to_add=amount,
                    source_type=CreditSourceType.SUBSCRIPTION,
                    source_id=str(subscription.id),
                    expires_at=expires_at,
                    commit=False
                )
                
                billing_logger.info(
                    f"Allocated {amount} {credit_type.value} credits to org {subscription.org_id} "
                    f"from subscription {subscription.id} (expires: {expires_at})"
                )
    
    async def _allocate_purchased_credits(
        self,
        db: AsyncSession,
        purchase: models.CreditPurchase
    ) -> None:
        """Allocate credits from a successful purchase."""
        # Create audit record
        await self.org_credits_dao.allocate_credits(
            db=db,
            org_id=purchase.org_id,
            credit_type=purchase.credit_type,
            amount=purchase.credits_amount,
            source_type=CreditSourceType.PURCHASE,
            source_id=purchase.stripe_payment_intent_id,
            source_metadata={"purchase_id": str(purchase.id)},
            expires_at=purchase.expires_at
        )
        
        # Add to net credits
        await self.org_net_credits_dao.add_credits(
            db=db,
            org_id=purchase.org_id,
            credit_type=purchase.credit_type,
            credits_to_add=purchase.credits_amount,
            source_type=CreditSourceType.PURCHASE,
            source_id=purchase.stripe_payment_intent_id,
            expires_at=purchase.expires_at,
            commit=False
        )
    
    def _calculate_credit_price(self, credit_type: CreditType, amount: float) -> float:
        """Calculate the price in dollars for purchasing credits."""
        if credit_type == CreditType.WORKFLOWS:
            return amount * settings.CREDIT_PRICE_WORKFLOWS_DOLLARS
        elif credit_type == CreditType.WEB_SEARCHES:
            return amount * settings.CREDIT_PRICE_WEB_SEARCHES_DOLLARS
        elif credit_type == CreditType.DOLLAR_CREDITS:
            # Dollar credits are priced with a markup ratio
            return amount * settings.CREDIT_PRICE_DOLLAR_CREDITS_RATIO
        else:
            raise BillingConfigurationException(f"No pricing configured for credit type: {credit_type}")
    
    # --- Webhook Event Handlers --- #
    
    async def _handle_subscription_updated(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
        """Handle subscription updated webhook."""
        stripe_subscription = event_data["object"]
        subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(
            db, stripe_subscription["id"]
        )
        
        if subscription:
            # Update subscription status and period
            subscription.status = SubscriptionStatus(stripe_subscription["status"])
            subscription.current_period_start = datetime.fromtimestamp(stripe_subscription["current_period_start"])
            subscription.current_period_end = datetime.fromtimestamp(stripe_subscription["current_period_end"])
            subscription.cancel_at_period_end = stripe_subscription.get("cancel_at_period_end", False)
            subscription.updated_at = datetime_now_utc()
            
            await self.org_subscription_dao.update(db, db_obj=subscription, obj_in=schemas.SubscriptionUpdate())
    
    async def _handle_subscription_deleted(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
        """Handle subscription deleted webhook."""
        stripe_subscription = event_data["object"]
        subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(
            db, stripe_subscription["id"]
        )
        
        if subscription:
            subscription.status = SubscriptionStatus.CANCELED
            subscription.canceled_at = datetime_now_utc()
            subscription.updated_at = datetime_now_utc()
            
            await self.org_subscription_dao.update(db, db_obj=subscription, obj_in=schemas.SubscriptionUpdate())
    
    async def _handle_payment_succeeded(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
        """Handle successful payment webhook."""
        invoice = event_data["object"]
        subscription_id = invoice.get("subscription")
        
        if subscription_id:
            subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(db, subscription_id)
            if subscription and subscription.plan:
                # Allocate credits for the new billing period
                await self._allocate_subscription_credits(db, subscription, subscription.plan)
    
    async def _handle_payment_failed(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
        """Handle failed payment webhook."""
        invoice = event_data["object"]
        subscription_id = invoice.get("subscription")
        
        if subscription_id:
            subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(db, subscription_id)
            if subscription:
                subscription.status = SubscriptionStatus.PAST_DUE
                subscription.updated_at = datetime_now_utc()
                
                await self.org_subscription_dao.update(db, db_obj=subscription, obj_in=schemas.SubscriptionUpdate())
    
    async def _handle_payment_intent_succeeded(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
        """Handle successful payment intent webhook (for credit purchases)."""
        payment_intent = event_data["object"]
        purchase = await self.credit_purchase_dao.get_by_stripe_payment_intent_id(
            db, payment_intent["id"]
        )
        
        if purchase and purchase.status == PaymentStatus.PENDING:
            # Update purchase status and allocate credits
            purchase = await self.credit_purchase_dao.update_payment_status(
                db, purchase, PaymentStatus.SUCCEEDED
            )
            await self._allocate_purchased_credits(db, purchase)
    
    async def _handle_payment_intent_failed(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
        """Handle failed payment intent webhook."""
        payment_intent = event_data["object"]
        purchase = await self.credit_purchase_dao.get_by_stripe_payment_intent_id(
            db, payment_intent["id"]
        )
        
        if purchase and purchase.status == PaymentStatus.PENDING:
            await self.credit_purchase_dao.update_payment_status(
                db, purchase, PaymentStatus.FAILED
            )
    
    async def _create_usage_event(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        consumption_request: schemas.CreditConsumptionRequest,
        is_overage: bool
    ) -> None:
        """Create a usage event for the given consumption request."""
        await self.usage_event_dao.create_usage_event(
            db=db,
            org_id=org_id,
            user_id=user_id,
            event_type=consumption_request.event_type,
            credit_type=consumption_request.credit_type,
            credits_consumed=consumption_request.credits_consumed,
            usage_metadata=consumption_request.metadata,
            is_overage=is_overage
        )
    
    async def process_subscription_renewal(
        self,
        db: AsyncSession,
        subscription: models.OrganizationSubscription
    ) -> Dict[str, Any]:
        """
        Process subscription renewal by rotating credits.
        
        This method handles both trial-to-paid transitions and regular renewals.
        """
        try:
            # Get the subscription plan
            plan = subscription.plan
            if not plan:
                raise SubscriptionPlanNotFoundException()
            
            # Update subscription period info (this would typically come from Stripe webhook)
            old_period_end = subscription.current_period_end
            subscription.current_period_start = old_period_end
            
            if subscription.is_annual:
                subscription.current_period_end = old_period_end + timedelta(days=365)
            else:
                subscription.current_period_end = old_period_end + timedelta(days=30)
            
            # Handle trial-to-paid transition
            was_trial_active = subscription.is_trial_active and datetime_now_utc() >= subscription.trial_end
            
            if was_trial_active:
                subscription.is_trial_active = False
                subscription.status = SubscriptionStatus.ACTIVE
                billing_logger.info(f"Trial ended for subscription {subscription.id}, transitioning to paid")
            
            subscription.updated_at = datetime_now_utc()
            await self.org_subscription_dao.update(db, db_obj=subscription, obj_in=schemas.SubscriptionUpdate())
            
            # Allocate new credits using rotation
            await self._allocate_subscription_credits(db, subscription, plan, is_renewal=True)
            
            return {
                "success": True,
                "subscription_id": subscription.id,
                "org_id": subscription.org_id,
                "renewal_type": "trial_to_paid" if was_trial_active else "regular",
                "new_period_start": subscription.current_period_start,
                "new_period_end": subscription.current_period_end
            }
            
        except Exception as e:
            billing_logger.error(f"Error processing subscription renewal: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to process subscription renewal: {str(e)}"
            )
    
    # --- New Credit Management Methods --- #
    
    async def expire_organization_credits(
        self,
        db: AsyncSession,
        org_id: Optional[uuid.UUID] = None,
        cutoff_datetime: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Expire all expiring organization credits based on current timestamp and update net credits.
        
        This method processes all expiring credits for an organization (or all organizations)
        and updates the net credits accordingly using batch operations.
        
        Args:
            db: Database session
            org_id: Organization ID (None for all organizations)
            cutoff_datetime: Cutoff datetime for expiration (defaults to current time)
            
        Returns:
            Dictionary with expiration summary
        """
        try:
            if cutoff_datetime is None:
                cutoff_datetime = datetime_now_utc()
            
            # Get all expiring credits using CRUD method
            expiring_credits = await self.org_credits_dao.get_expiring_credits_by_cutoff(
                db=db,
                org_id=org_id,
                cutoff_datetime=cutoff_datetime
            )

            if not expiring_credits:
                return {
                    "success": True,
                    "total_expired_credits": 0,
                    "total_organizations_affected": 0,
                    "organizations_processed": [],
                    "expiration_details": [],
                    "cutoff_datetime": cutoff_datetime
                }

            # Mark credits as expired in audit table using CRUD method
            await self.org_credits_dao.mark_credits_expired_by_cutoff(
                db=db,
                org_id=org_id,
                cutoff_datetime=cutoff_datetime,
            )
            
            # Group by organization and credit type to calculate totals
            expiration_batches = {}
            for credit in expiring_credits:
                key = (credit.org_id, credit.credit_type)
                if key not in expiration_batches:
                    expiration_batches[key] = 0
                expiration_batches[key] += credit.credits_granted
            
            # Process expirations using batch operations by organization
            total_expired = 0
            total_organizations = set()
            all_expiration_results = []
            
            # Group by organization for batch processing
            org_expiration_data = {}
            for (batch_org_id, credit_type), expired_amount in expiration_batches.items():
                if batch_org_id not in org_expiration_data:
                    org_expiration_data[batch_org_id] = {}
                org_expiration_data[batch_org_id][credit_type] = expired_amount
                total_expired += expired_amount
                total_organizations.add(batch_org_id)
            
            # Use batch expire for each organization
            for batch_org_id, expiration_data in org_expiration_data.items():
                # Convert to CreditExpirationBatch list
                credit_expirations = [
                    schemas.CreditExpirationBatch(
                        credit_type=credit_type,
                        expired_credits=expired_amount
                    )
                    for credit_type, expired_amount in expiration_data.items()
                ]
                
                expiration_results = await self.org_net_credits_dao.batch_expire_credits_and_adjust_consumption(
                    db=db,
                    org_id=batch_org_id,
                    credit_expirations=credit_expirations,
                    commit=False
                )
                all_expiration_results.extend(expiration_results)
            
            # Commit the transaction
            await db.commit()
            
            summary = {
                "success": True,
                "total_expired_credits": total_expired,
                "total_organizations_affected": len(total_organizations),
                "organizations_processed": list(total_organizations),
                "expiration_details": all_expiration_results,
                "cutoff_datetime": cutoff_datetime
            }
            
            billing_logger.info(
                f"Expired credits for {len(total_organizations)} organizations: "
                f"{total_expired} total credits expired"
            )
            
            return summary
            
        except Exception as e:
            # Rollback transaction on error
            await db.rollback()
            billing_logger.error(f"Error expiring organization credits: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to expire organization credits: {str(e)}"
            )
    
    async def rotate_subscription_credits(
        self,
        db: AsyncSession,
        subscription_id: uuid.UUID,
        new_credits: Dict[CreditType, int],
        new_expires_at: datetime
    ) -> Dict[str, Any]:
        """
        Rotate subscription credits by expiring previous period credits and adding new ones.
        
        This method handles subscription renewal by:
        1. Expiring all previous subscription credits for this subscription
        2. Adding new credits for the current period
        
        Args:
            db: Database session
            subscription_id: Subscription ID
            new_credits: Dictionary of credit types and amounts to add
            new_expires_at: Expiration date for new credits
            
        Returns:
            Dictionary with rotation summary
        """
        try:
            # Get subscription details using CRUD method
            subscription = await self.org_subscription_dao.get(db, subscription_id)
            if not subscription:
                raise SubscriptionNotFoundException()
            
            # Step 1: Find all existing subscription credits for this subscription using CRUD method
            existing_credits = await self.org_credits_dao.get_subscription_credits_by_subscription_id(
                db=db,
                org_id=subscription.org_id,
                subscription_id=subscription_id,
                include_expired=False
            )
            
            # Group existing credits by credit type for expiration
            expiration_batches = {}
            for credit in existing_credits:
                credit_type = credit.credit_type
                if credit_type not in expiration_batches:
                    expiration_batches[credit_type] = 0
                expiration_batches[credit_type] += credit.credits_granted
            
            # Step 2: Mark existing credits as expired using CRUD method
            if existing_credits:
                await self.org_credits_dao.mark_subscription_credits_expired(
                    db=db,
                    org_id=subscription.org_id,
                    subscription_id=subscription_id
                )
            
            # Step 3: Process expirations for ALL credit types using batch operations
            all_credit_types = set(expiration_batches.keys())
            all_credit_types.update(new_credits.keys())
            
            expiration_results = []
            if expiration_batches:
                # Convert to CreditExpirationBatch list
                credit_expirations = [
                    schemas.CreditExpirationBatch(
                        credit_type=credit_type,
                        expired_credits=expired_amount
                    )
                    for credit_type, expired_amount in expiration_batches.items()
                ]
                
                expiration_results = await self.org_net_credits_dao.batch_expire_credits_and_adjust_consumption(
                    db=db,
                    org_id=subscription.org_id,
                    credit_expirations=credit_expirations,
                    commit=False
                )
            
            # Step 4: Add new credits using individual operations with commit=False
            addition_results = []
            for credit_type, amount in new_credits.items():
                # Create audit record
                await self.org_credits_dao.allocate_credits(
                    db=db,
                    org_id=subscription.org_id,
                    credit_type=credit_type,
                    amount=amount,
                    source_type=CreditSourceType.SUBSCRIPTION,
                    source_id=str(subscription_id),
                    source_metadata={
                        "subscription_id": str(subscription_id),
                        "rotation": True,
                        "period_start": subscription.current_period_start.isoformat(),
                        "period_end": subscription.current_period_end.isoformat()
                    },
                    expires_at=new_expires_at,
                    period_start=subscription.current_period_start
                )
                
                # Add to net credits
                addition_result = await self.org_net_credits_dao.add_credits(
                    db=db,
                    org_id=subscription.org_id,
                    credit_type=credit_type,
                    credits_to_add=amount,
                    source_type=CreditSourceType.SUBSCRIPTION,
                    source_id=str(subscription_id),
                    expires_at=new_expires_at,
                    commit=False
                )
                addition_results.append(addition_result)
            
            # Commit the transaction
            await db.commit()
            
            # Prepare summary
            total_expired = sum(r.expired_credits for r in expiration_results)
            total_added = sum(new_credits.values())
            
            summary = {
                "success": True,
                "subscription_id": subscription_id,
                "org_id": subscription.org_id,
                "total_expired_credits": total_expired,
                "total_added_credits": total_added,
                "expired_by_type": {ct.value: expiration_batches.get(ct, 0) for ct in all_credit_types},
                "added_by_type": {ct.value: amount for ct, amount in new_credits.items()},
                "expiration_results": expiration_results,
                "addition_results": addition_results,
                "new_expires_at": new_expires_at
            }
            
            billing_logger.info(
                f"Rotated subscription credits for org {subscription.org_id}: "
                f"expired {total_expired}, added {total_added}"
            )
            
            return summary
            
        except Exception as e:
            # Rollback transaction on error
            await db.rollback()
            billing_logger.error(f"Error rotating subscription credits: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to rotate subscription credits: {str(e)}"
            ) 