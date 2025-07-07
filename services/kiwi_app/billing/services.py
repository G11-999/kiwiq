"""
Billing services for KiwiQ system.

This module defines the service layer for billing operations, including subscription management,
credit tracking, usage events, and Stripe integration. It follows KiwiQ's established patterns
for service layer architecture with dependency injection.
"""

import uuid
import stripe
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

# from kiwi_app.auth import crud as auth_crud
from kiwi_app.auth.models import Organization, User
from kiwi_app.auth.utils import datetime_now_utc
from kiwi_app.settings import settings
from kiwi_app.utils import get_kiwi_logger
from global_config.logger import get_prefect_or_regular_python_logger

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
        promotion_code_usage_dao: crud.PromotionCodeUsageDAO,
        stripe_event_dao: crud.StripeEventDAO,
        org_dao,  # : auth_crud.OrganizationDAO
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
        self.stripe_event_dao = stripe_event_dao
        self.org_dao = org_dao
        self.logger = get_prefect_or_regular_python_logger(name="kiwi_app.billing", return_non_prefect_logger=False) or get_kiwi_logger(name="kiwi_app.billing")
    
    # --- Credit Management --- #
    
    async def get_credit_balances(
        self,
        db: AsyncSession,
        org_id: uuid.UUID
    ) -> List[schemas.CreditBalance]:
        """
        Get credit balances for an organization.
        
        This method aggregates credits from all sources and provides current
        available balances with overage information for each credit type.
        
        Args:
            db: Database session
            org_id: Organization ID
            
        Returns:
            List of credit balances by type
        """
        try:
            balances = []
            
            # Check each credit type
            for credit_type in CreditType:
                net_credits = await self.org_net_credits_dao.get_net_credits_read(
                    db, org_id, credit_type
                )
                
                if net_credits:
                    balance = schemas.CreditBalance(
                        credit_type=credit_type,
                        credits_balance=net_credits.current_balance,
                        credits_granted=net_credits.credits_granted,
                        credits_consumed=net_credits.credits_consumed,
                        is_overage=net_credits.is_overage,
                        overage_amount=net_credits.overage_amount
                    )
                else:
                    # No credits allocated yet for this type
                    balance = schemas.CreditBalance(
                        credit_type=credit_type,
                        credits_balance=0.0,
                        credits_granted=0.0,
                        credits_consumed=0.0,
                        is_overage=False,
                        overage_amount=0.0
                    )
                
                balances.append(balance)
            
            return balances
            
        except Exception as e:
            self.logger.error(f"Error getting credit balances for org {org_id}: {e}", exc_info=True)
            raise
    
    async def get_organization_credits_by_type(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        credit_type: Optional[CreditType] = None,
        include_expired: bool = False
    ) -> List[schemas.OrganizationCreditsRead]:
        """
        Get detailed credit records for an organization by credit type.
        
        This method returns individual credit allocation records showing
        the source, expiration, and detailed information for each credit
        allocation. Unlike get_credit_balances which provides aggregated
        totals, this shows the itemized breakdown.
        
        Args:
            db: Database session
            org_id: Organization ID
            credit_type: Type of credits to retrieve (None for all types)
            include_expired: Whether to include expired credits
            
        Returns:
            List of detailed credit records
            
        Raises:
            BillingException: If there's an error retrieving credit records
        """
        try:
            credit_list = []
            
            # Determine which credit types to query
            credit_types_to_query = [credit_type] if credit_type else list(CreditType)
            
            for current_credit_type in credit_types_to_query:
                # Use the CRUD method to get detailed credit records for each type
                credit_records = await self.org_credits_dao.get_by_org_and_type(
                    db=db,
                    org_id=org_id,
                    credit_type=current_credit_type,
                    include_expired=include_expired
                )
                
                # Convert to response schemas
                for record in credit_records:
                    # Calculate remaining balance for this specific record
                    # Note: This shows the granted amount for this allocation - consumed is tracked globally
                    credits_balance = max(0.0, record.credits_granted)
                    
                    # Calculate period_end - use expires_at if available, otherwise use a default period
                    period_end = record.expires_at
                    if not period_end:
                        # If no expiration, assume a monthly period from period_start
                        period_end = record.period_start + timedelta(days=30)
                    
                    credit_read = schemas.OrganizationCreditsRead(
                        id=record.id,
                        org_id=record.org_id,
                        credit_type=record.credit_type,
                        credits_balance=credits_balance,  # This record's granted amount
                        credits_consumed=0.0,  # Consumption is tracked globally, not per allocation
                        credits_granted=record.credits_granted,
                        source_type=record.source_type,
                        source_id=record.source_id,
                        source_metadata=record.source_metadata,
                        expires_at=record.expires_at,
                        is_expired=record.is_expired,
                        period_start=record.period_start,
                        period_end=period_end,
                        created_at=record.created_at,
                        updated_at=record.updated_at
                    )
                    credit_list.append(credit_read)
            
            # Sort by credit type and then by creation date for consistent ordering
            credit_list.sort(key=lambda x: (x.credit_type.value, x.created_at))
            
            self.logger.info(
                f"Retrieved {len(credit_list)} credit records for org {org_id}, "
                f"type {credit_type.value if credit_type else 'all'}, include_expired={include_expired}"
            )
            
            return credit_list
            
        except Exception as e:
            self.logger.error(
                f"Error getting organization credits for org {org_id}, "
                f"type {credit_type.value if credit_type else 'all'}: {e}", exc_info=True
            )
            raise BillingException(
                status_code=500,
                detail=f"Failed to retrieve {credit_type.value if credit_type else 'all'} credit records"
            )
    
    async def consume_credits(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        consumption_request: schemas.CreditConsumptionRequest,
        allow_dollar_fallback: bool = True,
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
            allow_dollar_fallback: Whether to allow dollar credit fallback
            
        Returns:
            CreditConsumptionResult: Consumption result with balance info
            
        Raises:
            InsufficientCreditsException: If not enough credits available
        """
        try:
            # Store original request details for result
            original_credit_type = consumption_request.credit_type
            original_credits_requested = consumption_request.credits_consumed
            
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
                commit=False,
                allow_dollar_fallback=allow_dollar_fallback,
            )

            dollar_fallback_occurred = False
            consumed_in_dollar_credits = 0.0
            
            if consumption_result.credit_type != consumption_request.credit_type:
                # Dollar credit fallback occurred
                dollar_fallback_occurred = True
                consumed_in_dollar_credits = consumption_result.consumed_in_dollar_credits
                
                # Update consumption request for event logging
                consumption_request.credit_type = consumption_result.credit_type
                consumption_request.credits_consumed = consumption_result.consumed_in_dollar_credits
                consumption_request.event_type = f"dollar_credit_fallback_for__{consumption_request.event_type}"
                if consumption_request.metadata is not None:
                    consumption_request.metadata["dollar_credit_fallback"] = True
                    consumption_request.metadata["consumed_in_dollar_credits"] = consumption_result.consumed_in_dollar_credits
                    consumption_request.metadata["original_credit_type"] = original_credit_type.value
                    consumption_request.metadata["original_credits_requested"] = original_credits_requested
            
            # Create usage event for audit and analytics
            await self._create_usage_event(
                db=db,
                org_id=org_id,
                user_id=user_id,
                consumption_request=consumption_request,
                is_overage=consumption_result.is_overage,
                commit=False,
            )
            
            # Commit the transaction
            await db.commit()
            
            # Prepare result with proper credit type information
            result = schemas.CreditConsumptionResult(
                success=True,
                credit_type=original_credit_type if not dollar_fallback_occurred else CreditType.DOLLAR_CREDITS,
                credits_consumed=original_credits_requested if not dollar_fallback_occurred else consumed_in_dollar_credits,
                remaining_balance=consumption_result.remaining_balance,
                is_overage=consumption_result.is_overage,
                grace_credits_used=consumption_result.overage_amount,
                warning="Using overage grace credits" if consumption_result.is_overage else None,
                dollar_credit_fallback=dollar_fallback_occurred,
                consumed_in_dollar_credits=consumed_in_dollar_credits
            )
            
            # Log consumption for monitoring
            self.logger.debug(
                f"Consumed {original_credits_requested} {original_credit_type.value} "
                f"credits for org {org_id} (event: {consumption_request.event_type}, "
                f"overage: {consumption_result.is_overage}, dollar_fallback: {dollar_fallback_occurred})"
            )
            
            return result
            
        except InsufficientCreditsException:
            # Re-raise insufficient credits exceptions
            raise
        except Exception as e:
            # Safely attempt rollback
            self.logger.error(f"--> Error consuming credits: {e}", exc_info=True)
            await self._safe_rollback(db, "credit consumption")
            
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
        # Convert operation_id to string to ensure consistency
        operation_id = str(operation_id)
        
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
                is_overage=allocation_result.is_overage,
                commit=False,
            )
            
            # Commit the transaction
            await db.commit()
            
            self.logger.debug(
                f"Allocated {estimated_credits} {credit_type.value} credits for operation {operation_id} "
                f"(org: {org_id}, overage: {allocation_result.is_overage})"
            )
            
            return allocation_result
            
        except InsufficientCreditsException:
            # Re-raise insufficient credits exceptions without rollback
            # as they are business logic exceptions, not DB errors
            raise
        except Exception as e:
            # Safely attempt rollback
            self.logger.error(f"--> Error allocating credits for operation {operation_id}: {e}", exc_info=True)
            await self._safe_rollback(db, f"credit allocation for operation {operation_id}")
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
            operation_id = str(operation_id)
            # Perform the adjustment using atomic operation
            overage_settings = await self._get_overage_settings(org_id, credit_type)
            max_overage_allowed_fraction = overage_settings.get("overage_percentage", 10) / 100.0
            adjustment_result = await self.org_net_credits_dao.adjust_allocation_with_actual(
                db=db,
                org_id=org_id,
                credit_type=credit_type,
                operation_id=operation_id,
                actual_credits=actual_credits,
                allocated_credits=allocated_credits,
                commit=False,
                max_overage_allowed_fraction=max_overage_allowed_fraction,
            )
            
            # Create usage event for the adjustment
            if adjustment_result.adjustment_needed:
                adjustment_event = schemas.CreditConsumptionRequest(
                    credit_type=credit_type,
                    credits_consumed=adjustment_result.credit_difference,  # Use absolute value
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
                    is_overage=False,  # Adjustments don't create new overage
                    commit=False,
                )
            
            # Commit the transaction
            await db.commit()
            
            return adjustment_result
            
        except Exception as e:
            # Safely attempt rollback
            self.logger.error(f"--> Error adjusting allocated credits: {e}", exc_info=True)
            await self._safe_rollback(db, f"credit adjustment for operation {operation_id}")
            
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
                expires_at=expires_at,
                commit=False,
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
            
            self.logger.info(
                f"Added {credits_to_add} {credit_type.value} credits to org {org_id} "
                f"from {source_type.value}"
            )
            
            return result
            
        except Exception as e:
            # Safely attempt rollback
            self.logger.error(f"--> Error adding credits to organization: {e}", exc_info=True)
            await self._safe_rollback(db, "adding credits to organization")
            
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
            self.logger.warning(f"Error getting overage settings, using defaults: {e}")
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
                source_metadata={"promo_code_id": str(promo_code.id), "code": promo_code.code},
                expires_at=expires_at,
                commit=False,
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
            
            self.logger.info(f"Applied promotion code {code_application.code} to org {org_id}")
            
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
            # Safely attempt rollback
            self.logger.error(f"--> Error applying promotion code: {e}", exc_info=True)
            await self._safe_rollback(db, f"applying promotion code {code_application.code}")
            
            raise BillingException(
                status_code=500,
                detail=f"Failed to apply promotion code: {str(e)}"
            )
    
    async def create_promotion_code(
        self,
        db: AsyncSession,
        promo_code_data: schemas.PromotionCodeCreate
    ) -> schemas.PromotionCodeRead:
        """
        Create a new promotion code.
        
        This method creates a new promotion code that can be used by organizations
        to receive free credits. It validates the input data and creates the code
        with proper configuration for usage limits and expiration.
        
        Args:
            db: Database session
            promo_code_data: Promotion code creation data
            
        Returns:
            PromotionCodeRead: Created promotion code details
            
        Raises:
            BillingException: If creation fails
        """
        try:
            # Check if code already exists
            existing_code = await self.promotion_code_dao.get_by_code(db, promo_code_data.code)
            if existing_code:
                raise BillingException(
                    status_code=400,
                    detail=f"Promotion code '{promo_code_data.code}' already exists"
                )
            
            # Create the promotion code
            promotion_code = await self.promotion_code_dao.create(db, obj_in=promo_code_data)
            
            self.logger.info(
                f"Created promotion code '{promotion_code.code}': "
                f"{promotion_code.credits_amount} {promotion_code.credit_type.value} credits"
            )
            
            # Convert to read schema
            return schemas.PromotionCodeRead.model_validate(promotion_code)
            
        except BillingException:
            # Re-raise billing exceptions
            raise
        except Exception as e:
            self.logger.error(f"Error creating promotion code: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to create promotion code: {str(e)}"
            )

    async def get_promotion_codes(
        self,
        db: AsyncSession,
        query_params: schemas.PromotionCodeQuery
    ) -> schemas.PaginatedPromotionCodes:
        """
        Get promotion codes with filtering and pagination.
        
        This method provides comprehensive promotion code querying capabilities
        for admin users with extensive filtering options including active status,
        credit type, search text, expiration dates, and usage limits.
        
        Args:
            db: Database session
            query_params: Query parameters for filtering and pagination
            
        Returns:
            PaginatedPromotionCodes: Paginated promotion codes response
            
        Raises:
            BillingException: If query fails or invalid parameters provided
        """
        try:
            # Validate query parameters
            if query_params.limit <= 0 or query_params.limit > 1000:
                raise BillingException(
                    status_code=400,
                    detail="Limit must be between 1 and 1000"
                )
            
            if query_params.skip < 0:
                raise BillingException(
                    status_code=400,
                    detail="Skip must be non-negative"
                )
            
            # Validate sort field exists on model
            valid_sort_fields = ['created_at', 'updated_at', 'code', 'is_active', 'expires_at', 'credit_type']
            if query_params.sort_by not in valid_sort_fields:
                raise BillingException(
                    status_code=400,
                    detail=f"Invalid sort field. Must be one of: {valid_sort_fields}"
                )
            
            # Execute query through DAO
            result = await self.promotion_code_dao.query_promotion_codes(db, query_params)
            
            self.logger.info(
                f"Retrieved {len(result.items)} promotion codes "
                f"(page {result.page} of {result.pages}) with filters: {result.filters_applied}"
            )
            
            return result
            
        except BillingException:
            # Re-raise billing exceptions
            raise
        except Exception as e:
            self.logger.error(f"Error getting promotion codes: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to get promotion codes: {str(e)}"
            )
    
    async def delete_promotion_code(
        self,
        db: AsyncSession,
        promo_code_id: uuid.UUID
    ) -> schemas.PromotionCodeDeleteResult:
        """
        Delete a promotion code by ID.
        
        This method safely deletes a promotion code with the following safeguards:
        - Verifies the promotion code exists
        - Prevents deletion if there are existing usage records
        - Provides detailed feedback about the deletion attempt
        
        If a promotion code has been used, it cannot be deleted to maintain
        audit trail integrity. In such cases, consider deactivating the code instead.
        
        Args:
            db: Database session
            promo_code_id: ID of the promotion code to delete
            
        Returns:
            Result indicating success/failure with details
            
        Raises:
            PromotionCodeNotFoundException: If the promotion code doesn't exist
            BillingException: If deletion is prevented due to existing usage
        """
        try:
            # First get the promotion code to check if it exists and get details
            promo_code = await self.promotion_code_dao.get(db, promo_code_id)
            if not promo_code:
                raise PromotionCodeNotFoundException(f"Promotion code with ID {promo_code_id} not found")
            
            # Store code for response
            code_name = promo_code.code
            
            # Attempt deletion
            deleted = await self.promotion_code_dao.delete_promotion_code(
                db=db,
                promo_code_id=promo_code_id,
                commit=True
            )
            
            if deleted:
                self.logger.info(f"Successfully deleted promotion code: {code_name} (ID: {promo_code_id})")
                return schemas.PromotionCodeDeleteResult(
                    success=True,
                    message=f"Promotion code '{code_name}' deleted successfully",
                    code=code_name,
                    promo_code_id=promo_code_id
                )
            else:
                # This shouldn't happen since we checked existence above
                raise PromotionCodeNotFoundException(f"Promotion code with ID {promo_code_id} not found")
                
        except PromotionCodeNotFoundException:
            raise
        except ValueError as e:
            # This catches the case where deletion is prevented due to usage records
            self.logger.warning(f"Cannot delete promotion code {promo_code_id}: {e}")
            raise BillingException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e)
            ) from e
        except Exception as e:
            self.logger.error(f"Error deleting promotion code {promo_code_id}: {e}", exc_info=True)
            raise BillingException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete promotion code"
            ) from e

    async def deactivate_promotion_codes(
        self,
        db: AsyncSession,
        deactivate_request: schemas.PromotionCodeDeactivateRequest
    ) -> schemas.PromotionCodeDeactivateResult:
        """
        Deactivate promotion codes based on various targeting criteria.
        
        This method provides flexible deactivation capabilities supporting:
        - Direct targeting by promotion code IDs or code strings
        - Query-based targeting using filters (same as get_promotion_codes)
        - Bulk deactivation with safety controls
        - Deactivate all codes with explicit confirmation
        
        Deactivation is a safe operation that preserves all data and audit trails
        while preventing further use of the promotion codes.
        
        Args:
            db: Database session
            deactivate_request: Deactivation targeting criteria and options
            
        Returns:
            PromotionCodeDeactivateResult with operation details
            
        Raises:
            BillingException: If invalid request parameters or operation fails
        """
        try:
            # Validate request
            has_targeting_criteria = any([
                deactivate_request.promo_code_ids,
                deactivate_request.codes,
                deactivate_request.is_active is not None,
                deactivate_request.credit_type is not None,
                deactivate_request.search_text,
                deactivate_request.expires_after,
                deactivate_request.expires_before,
                deactivate_request.has_usage_limit is not None
            ])
            
            if not has_targeting_criteria and not deactivate_request.deactivate_all:
                raise BillingException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No targeting criteria provided. To deactivate all promotion codes, set 'deactivate_all' to true explicitly."
                )
            
            # Execute deactivation through DAO
            result = await self.promotion_code_dao.deactivate_promotion_codes(
                db=db,
                deactivate_request=deactivate_request,
                commit=True
            )
            
            self.logger.info(
                f"Successfully deactivated {result.deactivated_count} promotion codes "
                f"with filters: {result.filters_applied}"
            )
            
            return result
            
        except BillingException:
            raise
        except ValueError as e:
            self.logger.warning(f"Cannot deactivate promotion codes: {e}")
            raise BillingException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            ) from e
        except Exception as e:
            self.logger.error(f"Error deactivating promotion codes: {e}", exc_info=True)
            raise BillingException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to deactivate promotion codes"
            ) from e

    async def bulk_delete_promotion_codes(
        self,
        db: AsyncSession,
        delete_request: schemas.PromotionCodeBulkDeleteRequest
    ) -> schemas.PromotionCodeBulkDeleteResult:
        """
        Bulk delete promotion codes based on various targeting criteria.
        
        This method provides flexible bulk deletion capabilities supporting:
        - Direct targeting by promotion code IDs or code strings
        - Query-based targeting using filters (same as get_promotion_codes)
        - Bulk deletion with usage record protection
        - Force deletion of used codes (dangerous, requires explicit flag)
        - Delete all codes with explicit confirmation
        
        **Safety Features:**
        - By default, skips promotion codes that have usage records
        - Requires explicit force_delete_used flag to delete used codes
        - Provides detailed feedback about deleted vs skipped codes
        - Comprehensive logging for audit purposes
        
        Args:
            db: Database session
            delete_request: Deletion targeting criteria and options
            
        Returns:
            PromotionCodeBulkDeleteResult with operation details
            
        Raises:
            BillingException: If invalid request parameters or operation fails
        """
        try:
            # Validate request
            has_targeting_criteria = any([
                delete_request.promo_code_ids,
                delete_request.codes,
                delete_request.is_active is not None,
                delete_request.credit_type is not None,
                delete_request.search_text,
                delete_request.expires_after,
                delete_request.expires_before,
                delete_request.has_usage_limit is not None
            ])
            
            if not has_targeting_criteria and not delete_request.delete_all:
                raise BillingException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No targeting criteria provided. To delete all promotion codes, set 'delete_all' to true explicitly."
                )
            
            # Execute bulk deletion through DAO
            result = await self.promotion_code_dao.bulk_delete_promotion_codes(
                db=db,
                delete_request=delete_request,
                commit=True
            )
            
            self.logger.warning(
                f"Bulk deleted {result.deleted_count} promotion codes, skipped {result.skipped_count} codes "
                f"with usage records. Filters: {result.filters_applied}"
            )
            
            return result
            
        except BillingException:
            raise
        except ValueError as e:
            self.logger.warning(f"Cannot bulk delete promotion codes: {e}")
            raise BillingException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            ) from e
        except Exception as e:
            self.logger.error(f"Error bulk deleting promotion codes: {e}", exc_info=True)
            raise BillingException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to bulk delete promotion codes"
            ) from e


    async def reset_organization_credits_to_zero(
        self,
        db: AsyncSession,
        admin_user_id: uuid.UUID,
        reset_request: schemas.AdminCreditResetRequest
    ) -> schemas.AdminCreditResetResponse:
        """
        Reset organization's net credits to zero for specified credit types.
        
        This is an admin-only operation that sets all specified credit types to zero
        for an organization while creating comprehensive audit records. The operation
        is performed atomically per credit type.
        
        Args:
            db: Database session
            admin_user_id: Admin user performing the reset
            reset_request: Reset request with organization and parameters
            
        Returns:
            AdminCreditResetResponse with detailed results
            
        Raises:
            Exception: If reset operation fails
        """
        try:
            # Verify organization exists
            organization = await self.org_dao.get(db, reset_request.org_id)
            if not organization:
                raise ValueError(f"Organization {reset_request.org_id} not found")
            
            self.logger.info(
                f"Admin {admin_user_id} initiating credit reset for org {reset_request.org_id} "
                f"with reason: {reset_request.reason}"
            )
            
            # Perform the reset using the DAO method
            reset_results = await self.org_net_credits_dao.reset_organization_credits_to_zero(
                db=db,
                org_id=reset_request.org_id,
                admin_user_id=admin_user_id,
                credit_types=reset_request.credit_types,
                reason=reset_request.reason,
                commit=True
            )
            
            # Calculate summary statistics
            total_credit_types_processed = len(reset_results)
            successful_resets = sum(1 for result in reset_results.values() if result.success)
            failed_resets = total_credit_types_processed - successful_resets
            overall_success = failed_resets == 0
            
            # Convert CreditType keys to strings for response serialization
            reset_results_serializable = {
                credit_type.value: result 
                for credit_type, result in reset_results.items()
            }
            
            response = schemas.AdminCreditResetResponse(
                success=overall_success,
                org_id=reset_request.org_id,
                admin_user_id=admin_user_id,
                reason=reset_request.reason,
                reset_results=reset_results_serializable,
                total_credit_types_processed=total_credit_types_processed,
                successful_resets=successful_resets,
                failed_resets=failed_resets
            )
            
            self.logger.info(
                f"Credit reset completed for org {reset_request.org_id}: "
                f"{successful_resets}/{total_credit_types_processed} successful resets"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(
                f"Error resetting organization credits for org {reset_request.org_id}: {e}", 
                exc_info=True
            )
            raise

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
    
    async def get_usage_events(
        self,
        db: AsyncSession,
        query_params: schemas.UsageEventQuery
    ) -> schemas.PaginatedUsageEvents:
        """
        Get usage events with filtering and pagination.
        
        This method provides comprehensive usage event querying capabilities
        with extensive filtering options including organization, user, event type,
        credit type, date ranges, and metadata search.
        
        Args:
            db: Database session
            query_params: Query parameters for filtering and pagination
            
        Returns:
            PaginatedUsageEvents: Paginated usage events response
            
        Raises:
            BillingException: If query fails or invalid parameters provided
        """
        try:
            # Validate query parameters
            if query_params.limit <= 0 or query_params.limit > 1000:
                raise BillingException(
                    status_code=400,
                    detail="Limit must be between 1 and 1000"
                )
            
            if query_params.skip < 0:
                raise BillingException(
                    status_code=400,
                    detail="Skip must be non-negative"
                )
            
            # Validate date range if both provided
            if query_params.created_after and query_params.created_before:
                if query_params.created_after >= query_params.created_before:
                    raise BillingException(
                        status_code=400,
                        detail="created_after must be before created_before"
                    )
            
            # Execute query through DAO
            result = await self.usage_event_dao.query_usage_events(db, query_params)
            
            self.logger.info(
                f"Retrieved {len(result.items)} usage events "
                f"(page {result.page} of {result.pages}) with filters: {result.filters_applied}"
            )
            
            return result
            
        except BillingException:
            # Re-raise billing exceptions
            raise
        except Exception as e:
            self.logger.error(f"Error getting usage events: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to get usage events: {str(e)}"
            )
    
    async def get_billing_dashboard(
        self,
        db: AsyncSession,
        org_id: uuid.UUID
    ) -> schemas.BillingDashboard:
        """Get comprehensive billing dashboard data for an organization."""
        # Get subscription with plan details
        subscriptions = await self.org_subscription_dao.get_by_org_id(db, org_id)
        
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
        upcoming_renewals = []
        for subscription in subscriptions:
            if subscription.status == SubscriptionStatus.ACTIVE:
                upcoming_renewals.append(subscription.current_period_end)
        
        return schemas.BillingDashboard(
            org_id=org_id,
            subscriptions=subscriptions,
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
            upcoming_renewals=upcoming_renewals,
            overage_warnings=overage_warnings
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
            
            self.logger.info(
                f"Expired credits for {len(total_organizations)} organizations: "
                f"{total_expired} total credits expired"
            )
            
            return summary
            
        except Exception as e:
            # Safely attempt rollback
            self.logger.error(f"--> Error expiring organization credits: {e}", exc_info=True)
            await self._safe_rollback(db, "expiring organization credits")
            
            raise BillingException(
                status_code=500,
                detail=f"Failed to expire organization credits: {str(e)}"
            )
    
    async def create_flexible_dollar_credit_checkout_session(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        user: User,
        dollar_amount: int,
        success_url: str,
        cancel_url: str
    ) -> Dict[str, Any]:
        """
        Create a Stripe Checkout session for flexible dollar credit purchase.
        
        This method allows users to purchase any amount of dollar credits
        using Stripe's dynamic pricing with line_items. It creates a purchase
        record with PENDING status immediately for tracking.
        
        Args:
            db: Database session
            org_id: Organization ID
            user: User initiating the checkout
            dollar_amount: Dollar amount to spend on credits
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect after cancelled payment
            
        Returns:
            Dict containing checkout session URL and ID
        """
        try:
            # Get or create Stripe customer
            stripe_customer = await self._get_or_create_stripe_customer(db, org_id, user)
            
            # Calculate the amount of credits the user will receive
            credits_amount = dollar_amount
            
            # Convert dollar amount to cents for Stripe
            amount_cents = int(dollar_amount * 100)
            
            # Calculate expiration for purchased credits
            expires_at = None
            if settings.PURCHASED_CREDITS_EXPIRE_DAYS:
                expires_at = datetime_now_utc() + timedelta(days=settings.PURCHASED_CREDITS_EXPIRE_DAYS)
            
            # Create purchase record with PENDING status BEFORE creating checkout session
            purchase = await self.credit_purchase_dao.create_purchase(
                db=db,
                org_id=org_id,
                user_id=user.id,
                stripe_checkout_id="",  # Will be updated with actual session ID
                credit_type=CreditType.DOLLAR_CREDITS,
                credits_amount=credits_amount,
                amount_paid=dollar_amount,
                currency="usd",
                expires_at=expires_at
            )
            
            # Prepare checkout session parameters with dynamic pricing
            checkout_params = {
                "customer": stripe_customer.id,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "mode": "payment",
                "line_items": [{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"${credits_amount:.2f} Dollar Credits",
                            "description": f"Purchase ${credits_amount:.2f} in dollar credits for ${dollar_amount:.2f}",
                            "metadata": {
                                "kiwiq_type": "dollar_credits"
                            }
                        },
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }],
                "payment_intent_data": {
                    "metadata": {
                        "kiwiq_org_id": str(org_id),
                        "kiwiq_user_id": str(user.id),
                        "kiwiq_type": "flexible_dollar_credit_purchase",
                        "kiwiq_purchase_id": str(purchase.id),
                        "credit_type": CreditType.DOLLAR_CREDITS.value,
                        "credits_amount": str(credits_amount),
                        "dollar_amount": str(dollar_amount)
                    }
                },
                "metadata": {
                    "kiwiq_org_id": str(org_id),
                    "kiwiq_user_id": str(user.id),
                    "kiwiq_type": "flexible_dollar_credit_purchase",
                    "kiwiq_purchase_id": str(purchase.id)
                }
            }
            
            # Create checkout session
            session = stripe.checkout.Session.create(**checkout_params)
            
            # Update purchase record with actual checkout session ID and add session ID to payment intent metadata
            purchase.stripe_checkout_id = session.id
            purchase.updated_at = datetime_now_utc()
            db.add(purchase)
            
            # # Update the payment intent with the checkout session ID for easier lookup in webhooks
            # if session.payment_intent:
            #     try:
            #         stripe.PaymentIntent.modify(
            #             session.payment_intent,
            #             metadata={
            #                 "checkout_session_id": session.id,
            #                 "kiwiq_org_id": str(org_id),
            #                 "kiwiq_user_id": str(user.id),
            #                 "kiwiq_type": "flexible_dollar_credit_purchase",
            #                 "kiwiq_purchase_id": str(purchase.id),
            #                 "credit_type": CreditType.DOLLAR_CREDITS.value,
            #                 "credits_amount": str(credits_amount),
            #                 "dollar_amount": str(dollar_amount)
            #             }
            #         )
            #     except stripe.StripeError as e:
            #         self.logger.warning(f"Failed to update payment intent metadata: {e}")
            
            await db.commit()
            await db.refresh(purchase)
            
            self.logger.info(
                f"Created flexible dollar credit checkout session {session.id} for org {org_id}: "
                f"${dollar_amount} for {credits_amount:.2f} credits (purchase ID: {purchase.id})"
            )
            
            return {
                "checkout_url": session.url,
                "session_id": session.id,
                "purchase_id": str(purchase.id),
                "expires_at": datetime.fromtimestamp(session.expires_at, tz=timezone.utc)
            }
            
        except stripe.StripeError as e:
            # If Stripe fails after we created the purchase record, mark it as failed
            if 'purchase' in locals():
                purchase.status = PaymentStatus.FAILED
                purchase.updated_at = datetime_now_utc()
                db.add(purchase)
                await db.commit()
            
            self.logger.error(f"Stripe error creating flexible dollar credit checkout session: {e}")
            raise StripeIntegrationException(
                detail="Failed to create checkout session",
                stripe_error_code=e.code,
                stripe_error_message=str(e)
            )
        except Exception as e:
            # If any other error occurs after creating purchase record, mark it as failed
            if 'purchase' in locals():
                purchase.status = PaymentStatus.FAILED
                purchase.updated_at = datetime_now_utc()
                db.add(purchase)
                await db.commit()
            
            self.logger.error(f"Error creating flexible dollar credit checkout session: {e}")
            raise BillingException(
                status_code=500,
                detail=f"Failed to create checkout session: {str(e)}"
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
        in sync with Stripe's state, and logs all events for audit purposes.
        """
        processing_successful = True
        processing_error = None
        event_type = webhook_event.type
        event_data = webhook_event.data
        context = {}
        event_timestamp = None
        
        try:
            self.logger.info(f"Processing Stripe webhook: {event_type} (ID: {webhook_event.id})")
            
            # Extract contextual information for audit logging
            context = await self.stripe_event_dao.extract_context_from_event(event_data)
            
            # Convert webhook_event timestamp to datetime
            event_timestamp = webhook_event.created
            
            # Handle checkout session events
            if event_type in ["checkout.session.completed", "checkout.session.async_payment_succeeded"]:
                session = event_data["object"]
                mode = session.get("mode")
                
                if mode == "payment":
                    # One-time payment checkout
                    await self._handle_payment_session_succeeded(db, event_data)
                elif mode == "subscription":
                    # Subscription checkout - subscription will be created via customer.subscription.created
                    self.logger.info(f"Subscription checkout completed: {session['id']}")
                    
            elif event_type in ["checkout.session.async_payment_failed", "checkout.session.expired"]:
                await self._handle_payment_session_failed(db, event_data)
                
            # Handle subscription lifecycle events
            elif event_type == "customer.subscription.created":
                await self._handle_subscription_created(db, event_data)
                
            elif event_type == "customer.subscription.updated":
                await self._handle_subscription_updated(db, event_data)
                
            elif event_type == "customer.subscription.deleted":
                await self._handle_subscription_deleted(db, event_data)
                
            # Handle trial ending event (sent 3 days before trial ends)
            elif event_type == "customer.subscription.trial_will_end":
                await self._handle_subscription_trial_ending(db, event_data)
                
            # # Handle invoice events for subscription renewals and payments
            # elif event_type == "invoice.payment_succeeded":
            #     await self._handle_invoice_payment_succeeded(db, event_data)
                
            # elif event_type == "invoice.payment_failed":
            #     await self._handle_invoice_payment_failed(db, event_data)
                
            # # Handle charge events for receipts and initial payments
            # elif event_type == "charge.succeeded":
            #     await self._handle_charge_succeeded(db, event_data)
                
            # # Handle pending subscription updates
            # elif event_type == "customer.subscription.pending_update_applied":
            #     # This fires when a scheduled update (like seat decrease) takes effect
            #     await self._handle_subscription_updated(db, event_data)
                
            # # Handle subscription resumption
            # elif event_type == "customer.subscription.resumed":
            #     # This fires when a paused subscription is resumed
            #     await self._handle_subscription_updated(db, event_data)
                
            else:
                self.logger.info(f"Unhandled webhook event type: {event_type}")
                
            
            return True
            
        except Exception as e:
            processing_successful = False
            if processing_error is None:
                processing_error = str(e)
            self.logger.error(f"Error processing webhook {webhook_event.id}: {e}", exc_info=True)
            return False
            
        finally:
            # Always log the event to audit table, regardless of processing success/failure
            try:
                await self.stripe_event_dao.create_event_log(
                    db=db,
                    stripe_event_id=webhook_event.id,
                    event_type=event_type,
                    event_data=event_data,
                    org_id=context.get("org_id"),
                    user_id=context.get("user_id"),
                    plan_id=context.get("plan_id"),
                    event_timestamp=event_timestamp,
                    livemode=webhook_event.livemode,
                    api_version=None,  # Not available in webhook_event schema
                    processed_successfully=processing_successful,
                    processing_error=processing_error,
                    commit=True
                )
                self.logger.debug(f"Logged Stripe event {webhook_event.id} to audit table")
            except Exception as audit_error:
                # Don't fail the webhook processing if audit logging fails
                self.logger.error(f"Failed to log Stripe event {webhook_event.id} to audit table: {audit_error}", exc_info=True)
    
    # --- Webhook Event Handlers --- #
    
    
    
    async def _handle_payment_session_succeeded(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
        """Handle successful payment intent webhook (for credit purchases)."""
        checkout_session_object = event_data["object"]
        
        # Check payment status for checkout.session.completed events
        payment_status = checkout_session_object.get("payment_status")
        if payment_status == "unpaid":
            # Session completed but payment failed - delegate to failure handler
            await self._handle_payment_session_failed(db, event_data)
            return
        
        # Check if this is a flexible dollar credit purchase from metadata
        kiwiq_type = checkout_session_object.get("metadata", {}).get("kiwiq_type")
        
        if kiwiq_type == "flexible_dollar_credit_purchase":
            # Handle flexible dollar credit purchase by updating existing purchase record
            metadata = checkout_session_object.get("metadata", {})
            purchase_id = metadata.get("kiwiq_purchase_id")
            
            if not purchase_id:
                self.logger.error(f"Missing purchase_id in metadata for flexible dollar credit purchase: {checkout_session_object['id']}")
                return
            
            # Get existing purchase record
            try:
                purchase = await self.credit_purchase_dao.get(db, uuid.UUID(purchase_id))
                if not purchase:
                    self.logger.error(f"Purchase record not found for ID {purchase_id} (checkout session: {checkout_session_object['id']})")
                    return
                
                # Update status to succeeded
                purchase = await self.credit_purchase_dao.update_payment_status(
                    db, purchase, PaymentStatus.SUCCEEDED
                )
                
                # Allocate credits
                await self._allocate_purchased_credits(db, purchase)
                
                self.logger.info(
                    f"Processed flexible dollar credit purchase: ${purchase.amount_paid} for {purchase.credits_amount} credits "
                    f"(org: {purchase.org_id}, purchase ID: {purchase.id}, checkout_session: {checkout_session_object['id']})"
                )
                
            except Exception as e:
                self.logger.error(f"Error processing flexible dollar credit purchase success: {e}", exc_info=True)
                return
        else:
            # Handle regular credit purchase (existing logic)
            purchase = await self.credit_purchase_dao.get_by_stripe_checkout_id(
                db, checkout_session_object["id"]
            )
            
            if purchase and purchase.status == PaymentStatus.PENDING:
                # Update purchase status and allocate credits
                purchase = await self.credit_purchase_dao.update_payment_status(
                    db, purchase, PaymentStatus.SUCCEEDED
                )
                await self._allocate_purchased_credits(db, purchase)
    
    async def _handle_payment_session_failed(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
        """Handle failed payment session webhook (for credit purchases)."""
        checkout_session_object = event_data["object"]
        
        # Check if this is a flexible dollar credit purchase from metadata
        kiwiq_type = checkout_session_object.get("metadata", {}).get("kiwiq_type")
        
        if kiwiq_type == "flexible_dollar_credit_purchase":
            # Handle flexible dollar credit purchase failure by updating existing purchase record
            metadata = checkout_session_object.get("metadata", {})
            purchase_id = metadata.get("kiwiq_purchase_id")
            
            if not purchase_id:
                self.logger.error(f"Missing purchase_id in metadata for failed flexible dollar credit purchase: {checkout_session_object['id']}")
                return
            
            # Get existing purchase record
            try:
                purchase = await self.credit_purchase_dao.get(db, uuid.UUID(purchase_id))
                if not purchase:
                    self.logger.error(f"Purchase record not found for ID {purchase_id} (failed checkout session: {checkout_session_object['id']})")
                    return
                
                # Update status to failed
                purchase = await self.credit_purchase_dao.update_payment_status(
                    db, purchase, PaymentStatus.FAILED
                )
                
                self.logger.info(
                    f"Marked flexible dollar credit purchase as failed: ${purchase.amount_paid} for {purchase.credits_amount} credits "
                    f"(org: {purchase.org_id}, purchase ID: {purchase.id}, checkout_session: {checkout_session_object['id']})"
                )
                
            except Exception as e:
                self.logger.error(f"Error processing flexible dollar credit purchase failure: {e}", exc_info=True)
                return
        else:
            # Handle regular credit purchase failure (existing logic)
            purchase = await self.credit_purchase_dao.get_by_stripe_checkout_id(
                db, checkout_session_object["id"]
            )
            
            if purchase and purchase.status == PaymentStatus.PENDING:
                await self.credit_purchase_dao.update_payment_status(
                    db, purchase, PaymentStatus.FAILED
                )
                
                self.logger.info(f"Marked credit purchase as failed (checkout session: {checkout_session_object['id']})")
    
    # async def _handle_charge_succeeded(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
    #     """Handle charge succeeded webhook to update receipt URL for credit purchases."""
    #     try:
    #         charge_object = event_data["object"]
            
    #         # Extract key information from the charge
    #         metadata = charge_object.get("metadata", {})
    #         kiwiq_purchase_id = metadata.get("kiwiq_purchase_id")
    #         receipt_url = charge_object.get("receipt_url")
            
    #         if not receipt_url:
    #             self.logger.warning(f"No receipt URL found in charge.succeeded event")
    #             return
            
    #         # Get payment intent to find the checkout session
    #         if kiwiq_purchase_id:
    #             try:
    #                 if kiwiq_purchase_id:
    #                     # Find the purchase record
    #                     purchase = await self.credit_purchase_dao.get(db, uuid.UUID(kiwiq_purchase_id))
    #                     if purchase:
    #                         # Update receipt URL
    #                         await self.credit_purchase_dao.update_receipt_url(
    #                             db=db,
    #                             purchase=purchase,
    #                             receipt_url=receipt_url
    #                         )
                            
    #                         self.logger.info(
    #                             f"Updated receipt URL for purchase {purchase.id} "
    #                             f"from charge {charge_object['id']}"
    #                         )
    #                     else:
    #                         self.logger.warning(
    #                             f"No purchase found for purchase ID {kiwiq_purchase_id} "
    #                             f"from charge {charge_object['id']}"
    #                         )
    #                 else:
    #                     self.logger.warning(
    #                         f"No purchase ID found for charge {charge_object['id']}"
    #                     )
                        
    #             except stripe.StripeError as e:
    #                 self.logger.error(f"Error retrieving purchase {kiwiq_purchase_id}: {e}")
    #         else:
    #             self.logger.warning(f"No purchase ID found in charge.succeeded event")
                
    #     except Exception as e:
    #         self.logger.error(f"Error handling charge.succeeded event: {e}", exc_info=True)
    
    async def _create_usage_event(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        consumption_request: schemas.CreditConsumptionRequest,
        is_overage: bool,
        commit: bool = True,
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
            is_overage=is_overage,
            commit=commit
        )

    # --- Private Helper Methods --- #
    
    async def _safe_rollback(self, db: AsyncSession, operation_context: str = "operation") -> None:
        """
        Safely attempt to rollback a database transaction.
        
        This method checks the session state before attempting rollback to avoid
        the IllegalStateChangeError that occurs when trying to rollback a session
        that's already in the middle of a commit or other operation.
        
        Args:
            db: Database session
            operation_context: Description of the operation for logging
        """
        try:
            # db.get_transaction()
            # Only attempt rollback if the session is in a valid state
            if db.in_transaction():
                await db.rollback()
                self.logger.info(f"Rolled back transaction for {operation_context}")
            else:
                self.logger.warning(f"No active transaction to rollback for {operation_context}")
            # if hasattr(db, '_transaction') and db._transaction is not None:
            #     # Check if we can safely rollback
            #     if not db._transaction.is_closed and not db._transaction._prepared:
            #         await db.rollback()
            #         self.logger.info(f"Rolled back transaction for {operation_context}")
            #     else:
            #         self.logger.warning(
            #             f"Cannot rollback transaction for {operation_context}: "
            #             f"transaction is in state that doesn't allow rollback"
            #         )
            # else:
            #     self.logger.warning(f"No active transaction to rollback for {operation_context}")
        except Exception as rollback_error:
            # Log rollback error but don't let it mask the original error
            self.logger.error(
                f"Error during rollback for {operation_context}: {rollback_error}",
                exc_info=True
            )
    
    async def _get_or_create_stripe_customer(self, db: AsyncSession, org_id: uuid.UUID, user: User) -> stripe.Customer:
        """Get or create a Stripe customer for an organization using external_billing_id."""
        # Get the organization 
        organization = await self.org_dao.get(db, org_id)
        if not organization:
            raise BillingException(
                status_code=404,
                detail="Organization not found"
            )
        
        # Check if customer already exists using external_billing_id
        if organization.external_billing_id:
            try:
                customer = stripe.Customer.retrieve(organization.external_billing_id)
                # NOTE: this is managed in organization service directly
                # modify_kwargs = {}
                # if customer.email != user.email:
                #     modify_kwargs["email"] = user.email
                # if customer.name != organization.name:
                #     modify_kwargs["name"] = organization.name
                # if modify_kwargs:
                #     modify_kwargs["id"] = customer.id
                #     customer.modify(**modify_kwargs)
                return customer
            except stripe.StripeError as e:
                self.logger.warning(f"Failed to retrieve Stripe customer {organization.external_billing_id}: {e}")
                # Continue to create new customer if retrieval fails
        
        # Create new customer
        customer = stripe.Customer.create(
            email=user.email,
            name=organization.name,
            metadata={
                "kiwiq_org_id": str(org_id),
                "kiwiq_user_id": str(user.id)
            }
        )
        
        # Update organization with Stripe customer ID
        organization.external_billing_id = customer.id
        db.add(organization)
        await db.commit()
        
        self.logger.info(f"Created and linked Stripe customer {customer.id} for org {org_id}")
        
        return customer
    
    async def _allocate_purchased_credits(
        self,
        db: AsyncSession,
        purchase: models.CreditPurchase
    ) -> None:
        """Allocate credits from a successful purchase."""
        # Create audit record
        try:
            await self.org_credits_dao.allocate_credits(
                db=db,
                org_id=purchase.org_id,
                credit_type=purchase.credit_type,
                amount=purchase.credits_amount,
                source_type=CreditSourceType.PURCHASE,
                source_id=purchase.stripe_checkout_id,
                source_metadata={"purchase_id": str(purchase.id)},
                expires_at=purchase.expires_at,
                commit=False,
            )
            
            # Add to net credits
            await self.org_net_credits_dao.add_credits(
                db=db,
                org_id=purchase.org_id,
                credit_type=purchase.credit_type,
                credits_to_add=purchase.credits_amount,
                source_type=CreditSourceType.PURCHASE,
                source_id=purchase.stripe_checkout_id,
                expires_at=purchase.expires_at,
                commit=False,
            )

            await db.commit()
            
        except Exception as e:
            # Safely attempt rollback
            self.logger.error(f"--> Error allocating purchased credits: {e}", exc_info=True)
            await self._safe_rollback(db, "allocating purchased credits")
            
            raise
    

    
    ### TODO ###
    ################################################
    # --- Subscription Management --- #
    ################################################
    
    async def rotate_subscription_credits(
        self,
        db: AsyncSession,
        subscription_id: uuid.UUID,
        new_credits: Dict[CreditType, int],
        new_expires_at: datetime,
        is_overdue: bool = False
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
            is_overdue: Whether the subscription is overdue
            
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
                    commit=False,
                    modify_granted_only=is_overdue
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
                    source_id=str(subscription.id),
                    source_metadata={
                        "subscription_id": str(subscription.id),
                        "stripe_subscription_id": subscription.stripe_subscription_id,
                        "plan_id": str(subscription.plan_id),
                        "billing_period": "trial" if subscription.is_trial_active else "monthly",
                        "period_start": subscription.current_period_start.isoformat(),
                        "period_end": subscription.current_period_end.isoformat(),
                        "is_renewal": False
                    },
                    expires_at=new_expires_at,
                    commit=False,
                )
                
                # Add to net credits
                addition_result = await self.org_net_credits_dao.add_credits(
                    db=db,
                    org_id=subscription.org_id,
                    credit_type=credit_type,
                    credits_to_add=amount,
                    source_type=CreditSourceType.SUBSCRIPTION,
                    source_id=str(subscription.id),
                    expires_at=new_expires_at,
                    commit=False,
                )
                addition_results.append(addition_result)
            
            # Commit the transaction
            await db.commit()
            
            # Prepare summary
            total_expired = sum(r.expired_credits for r in expiration_results)
            total_added = sum(new_credits.values())
            
            summary = {
                "success": True,
                "subscription_id": subscription.id,
                "org_id": subscription.org_id,
                "total_expired_credits": total_expired,
                "total_added_credits": total_added,
                "expired_by_type": {ct.value: expiration_batches.get(ct, 0) for ct in all_credit_types},
                "added_by_type": {ct.value: amount for ct, amount in new_credits.items()},
                "expiration_results": expiration_results,
                "addition_results": addition_results,
                "new_expires_at": new_expires_at
            }
            
            self.logger.info(
                f"Rotated subscription credits for org {subscription.org_id}: "
                f"expired {total_expired}, added {total_added}"
            )
            
            return summary
            
        except Exception as e:
            # Rollback transaction on error
            self.logger.error(f"--> Error rotating subscription credits: {e}", exc_info=True)
            try:
                await db.rollback()
            except Exception as rollback_error:
                self.logger.error(f"--> Error during rollback: {rollback_error}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to rotate subscription credits: {str(e)}"
            )



    async def _handle_checkout_session_completed(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
        """Handle checkout session completed webhook."""
        session = event_data["object"]
        mode = session.get("mode")
        
        if mode == "subscription":
            # Subscription checkout completed - the subscription will be created by Stripe
            # and we'll handle it in the customer.subscription.created webhook
            self.logger.info(f"Subscription checkout completed: {session['id']}")
        elif mode == "payment":
            # One-time payment checkout completed
            payment_intent_id = session.get("payment_intent")
            if payment_intent_id:
                # The payment will be handled by payment_intent.succeeded webhook
                self.logger.info(f"Payment checkout completed: {session['id']}")

    # async def _handle_subscription_created(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
    #     """Handle subscription created webhook from checkout.session.completed with mode=subscription.
        
    #     The Stripe subscription object documented here: https://docs.stripe.com/api/subscriptions/object
    #     """
    #     stripe_subscription = event_data["object"]
        
    #     # Extract metadata
    #     org_id = stripe_subscription["metadata"].get("kiwiq_org_id")
    #     plan_id = stripe_subscription["metadata"].get("kiwiq_plan_id")
        
    #     if not org_id or not plan_id:
    #         self.logger.error(f"Missing metadata in subscription: {stripe_subscription['id']}")
    #         return
        
    #     # Check if subscription already exists
    #     existing_subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(
    #         db, stripe_subscription["id"]
    #     )
        
    #     if existing_subscription:
    #         self.logger.info(f"Subscription already exists: {stripe_subscription['id']}")
    #         return
        
    #     # Get the plan
    #     plan = await self.subscription_plan_dao.get(db, uuid.UUID(plan_id))
    #     if not plan:
    #         self.logger.error(f"Plan not found: {plan_id}")
    #         return
        
    #     # Ensure organization has the correct external_billing_id
    #     organization = await self.org_dao.get(db, uuid.UUID(org_id))
    #     if organization and not organization.external_billing_id:
    #         organization.external_billing_id = stripe_subscription["customer"]
    #         db.add(organization)
    #         self.logger.info(f"Updated organization {org_id} with Stripe customer ID {stripe_subscription['customer']}")
        
    #     # Create subscription record
    #     now = datetime_now_utc()
    #     trial_end = None
    #     is_trial_active = False
        
    #     # Handle trial period
    #     if stripe_subscription.get("trial_end"):
    #         trial_end = datetime.fromtimestamp(stripe_subscription["trial_end"], tz=timezone.utc)
    #         is_trial_active = trial_end > now
        

    #     plan_details = {}
    #     if stripe_subscription.get("items") and stripe_subscription["items"]["data"]:
    #         plan_details = stripe_subscription["items"]["data"][0]
        
    #     # Extract seat count from subscription items
    #     seats_count = 1  # Default
    #     seats_count = plan_details.get("quantity", 1)
        
    #     # Determine billing interval (annual vs monthly)
    #     is_annual = False
    #     if plan_details:
    #         price_interval = plan_details["price"]["recurring"]["interval"]
    #         is_annual = price_interval == "year"
        
    #     # Determine subscription status
    #     stripe_status = stripe_subscription["status"]
    #     if stripe_status == "trialing":
    #         status = SubscriptionStatus.TRIAL
    #     elif stripe_status == "active":
    #         status = SubscriptionStatus.ACTIVE
    #     elif stripe_status == "past_due":
    #         status = SubscriptionStatus.PAST_DUE
    #     elif stripe_status == "canceled":
    #         status = SubscriptionStatus.CANCELED
    #     else:
    #         status = SubscriptionStatus.PAUSED
        
    #     default_current_period_end = datetime_now_utc() + timedelta(days=settings.SUBSCRIPTION_CREDITS_EXPIRE_DAYS_ANNUAL if is_annual else settings.SUBSCRIPTION_CREDITS_EXPIRE_DAYS)
        
    #     subscription = models.OrganizationSubscription(
    #         org_id=uuid.UUID(org_id),
    #         plan_id=uuid.UUID(plan_id),
    #         stripe_subscription_id=stripe_subscription["id"],
    #         status=status,
    #         current_period_start=datetime.fromtimestamp(plan_details["current_period_start"], tz=timezone.utc) if plan_details else datetime_now_utc(),
    #         current_period_end=datetime.fromtimestamp(plan_details["current_period_end"], tz=timezone.utc) if plan_details else default_current_period_end,
    #         seats_count=seats_count,
    #         is_annual=is_annual,
    #         trial_start=now if is_trial_active else None,
    #         trial_end=trial_end,
    #         is_trial_active=is_trial_active,
    #         cancel_at_period_end=stripe_subscription.get("cancel_at_period_end", False),
    #         created_at=now,
    #         updated_at=now
    #     )
        
    #     subscription = await self.org_subscription_dao.create(db, obj_in=subscription)
        
    #     # Allocate initial credits (trial or regular)
    #     await self._allocate_subscription_credits(db, subscription, plan)
        
    #     self.logger.info(
    #         f"Created subscription from webhook: {subscription.id} "
    #         f"(status: {status.value}, trial: {is_trial_active}, seats: {seats_count})"
    #     )
    
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
    
    # async def _handle_payment_succeeded(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
    #     """Handle successful payment webhook."""
    #     invoice = event_data["object"]
    #     subscription_id = invoice.get("subscription")
        
    #     if subscription_id:
    #         subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(db, subscription_id)
    #         if subscription and subscription.plan:
    #             # Allocate credits for the new billing period
    #             await self._allocate_subscription_credits(db, subscription, subscription.plan)
    
    # async def _handle_payment_failed(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
    #     """Handle failed payment webhook."""
    #     invoice = event_data["object"]
    #     subscription_id = invoice.get("subscription")
        
    #     if subscription_id:
    #         subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(db, subscription_id)
    #         if subscription:
    #             subscription.status = SubscriptionStatus.PAST_DUE
    #             subscription.updated_at = datetime_now_utc()
                
    #             await self.org_subscription_dao.update(db, db_obj=subscription, obj_in=schemas.SubscriptionUpdate())
    
    # async def process_subscription_renewal(
    #     self,
    #     db: AsyncSession,
    #     subscription: models.OrganizationSubscription
    # ) -> Dict[str, Any]:
    #     """
    #     Process subscription renewal by rotating credits.
        
    #     This method handles both trial-to-paid transitions and regular renewals.
    #     """
    #     try:
    #         # Get the subscription plan
    #         plan = subscription.plan
    #         if not plan:
    #             raise SubscriptionPlanNotFoundException()
            
    #         # Update subscription period info (this would typically come from Stripe webhook)
    #         old_period_end = subscription.current_period_end
    #         subscription.current_period_start = old_period_end
            
    #         if subscription.is_annual:
    #             subscription.current_period_end = old_period_end + timedelta(days=365)
    #         else:
    #             subscription.current_period_end = old_period_end + timedelta(days=30)
            
    #         # Handle trial-to-paid transition
    #         was_trial_active = subscription.is_trial_active and datetime_now_utc() >= subscription.trial_end
            
    #         if was_trial_active:
    #             subscription.is_trial_active = False
    #             subscription.status = SubscriptionStatus.ACTIVE
    #             self.logger.info(f"Trial ended for subscription {subscription.id}, transitioning to paid")
            
    #         subscription.updated_at = datetime_now_utc()
    #         await self.org_subscription_dao.update(db, db_obj=subscription, obj_in=schemas.SubscriptionUpdate())
            
    #         # Allocate new credits using rotation
    #         await self._allocate_subscription_credits(db, subscription, plan, is_renewal=True)
            
    #         return {
    #             "success": True,
    #             "subscription_id": subscription.id,
    #             "org_id": subscription.org_id,
    #             "renewal_type": "trial_to_paid" if was_trial_active else "regular",
    #             "new_period_start": subscription.current_period_start,
    #             "new_period_end": subscription.current_period_end
    #         }
            
    #     except Exception as e:
    #         self.logger.error(f"Error processing subscription renewal: {e}", exc_info=True)
    #         raise BillingException(
    #             status_code=500,
    #             detail=f"Failed to process subscription renewal: {str(e)}"
    #         )
    
    
    
    # async def _allocate_subscription_credits(
    #     self,
    #     db: AsyncSession,
    #     subscription: models.OrganizationSubscription,
    #     plan: models.SubscriptionPlan,
    #     is_renewal: bool = False
    # ) -> None:
    #     """
    #     Allocate monthly credits for a subscription, with optional credit rotation for renewals.
        
    #     Credits are multiplied by the number of seats in the subscription.
    #     """
    #     now = datetime_now_utc()
    #     period_end = subscription.current_period_end
        
    #     # Determine expiration based on subscription type
    #     if subscription.is_trial_active:
    #         expires_at = now + timedelta(days=settings.TRIAL_CREDITS_EXPIRE_DAYS)
    #     else:
    #         expires_at = period_end + timedelta(days=settings.SUBSCRIPTION_CREDITS_EXPIRE_DAYS)
        
    #     # If this is a renewal and not a trial, use credit rotation
    #     if is_renewal and not subscription.is_trial_active:
    #         # Use credit rotation for subscription renewals
    #         new_credits = {}
    #         for credit_type_str, base_amount in plan.monthly_credits.items():
    #             credit_type = CreditType(credit_type_str)
    #             # Multiply by seat count
    #             total_amount = base_amount * subscription.seats_count * (12 if subscription.is_annual else 1)
    #             new_credits[credit_type] = total_amount
            
    #         rotation_result = await self.rotate_subscription_credits(
    #             db=db,
    #             subscription_id=subscription.id,
    #             new_credits=new_credits,
    #             new_expires_at=expires_at
    #         )
            
    #         self.logger.info(
    #             f"Rotated subscription credits for subscription {subscription.id}: "
    #             f"expired {rotation_result['total_expired_credits']}, "
    #             f"added {rotation_result['total_added_credits']} credits "
    #             f"(seats: {subscription.seats_count})"
    #         )
    #     else:
    #         # For new subscriptions or trial-to-paid transitions, allocate fresh credits
    #         try:
    #             for credit_type_str, base_amount in plan.monthly_credits.items():
    #                 credit_type = CreditType(credit_type_str)
                    
    #                 # Multiply by seat count
    #                 total_amount = base_amount * subscription.seats_count * (12 if subscription.is_annual else 1)
                    
    #                 # Create audit record
    #                 await self.org_credits_dao.allocate_credits(
    #                     db=db,
    #                     org_id=subscription.org_id,
    #                     credit_type=credit_type,
    #                     amount=total_amount,
    #                     source_type=CreditSourceType.SUBSCRIPTION,
    #                     source_id=str(subscription.id),
    #                     source_metadata={
    #                         "subscription_id": str(subscription.id),
    #                         "stripe_subscription_id": subscription.stripe_subscription_id,
    #                         "plan_id": str(subscription.plan_id),
    #                         "billing_period": "trial" if subscription.is_trial_active else "monthly",
    #                         "period_start": now.isoformat(),
    #                         "period_end": period_end.isoformat(),
    #                         "is_renewal": is_renewal,
    #                         "seats_count": subscription.seats_count,
    #                         "base_amount": base_amount,
    #                         "total_amount": total_amount
    #                     },
    #                     expires_at=expires_at,
    #                     commit=False,
    #                 )
                    
    #                 # Add to net credits
    #                 await self.org_net_credits_dao.add_credits(
    #                     db=db,
    #                     org_id=subscription.org_id,
    #                     credit_type=credit_type,
    #                     credits_to_add=total_amount,
    #                     source_type=CreditSourceType.SUBSCRIPTION,
    #                     source_id=str(subscription.id),
    #                     expires_at=expires_at,
    #                     commit=False,
    #                 )
                    
    #                 self.logger.info(
    #                     f"Allocated {total_amount} {credit_type.value} credits to org {subscription.org_id} "
    #                     f"from subscription {subscription.id} (base: {base_amount} x {subscription.seats_count} seats, "
    #                     f"expires: {expires_at})"
    #                 )
                
    #             await db.commit()

    #         except Exception as e:
    #             await db.rollback()
    #             self.logger.error(f"Error allocating subscription credits: {e}", exc_info=True)
    #             raise
    
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
            
            self.logger.info(f"Created subscription plan: {plan.name} (ID: {plan.id})")
            return plan
            
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating plan: {e}")
            raise StripeIntegrationException(
                detail="Failed to create subscription plan",
                stripe_error_code=e.code,
                stripe_error_message=str(e)
            )
    
    # async def process_subscription_renewal(
    #     self,
    #     db: AsyncSession,
    #     subscription: models.OrganizationSubscription
    # ) -> Dict[str, Any]:
    #     """
    #     Process subscription renewal by rotating credits.
        
    #     This method handles both trial-to-paid transitions and regular renewals.
    #     """
    #     try:
    #         # Get the subscription plan
    #         plan = subscription.plan
    #         if not plan:
    #             raise SubscriptionPlanNotFoundException()
            
    #         # Update subscription period info (this would typically come from Stripe webhook)
    #         old_period_end = subscription.current_period_end
    #         subscription.current_period_start = old_period_end
            
    #         if subscription.is_annual:
    #             subscription.current_period_end = old_period_end + timedelta(days=365)
    #         else:
    #             subscription.current_period_end = old_period_end + timedelta(days=30)
            
    #         # Handle trial-to-paid transition
    #         was_trial_active = subscription.is_trial_active and datetime_now_utc() >= subscription.trial_end
            
    #         if was_trial_active:
    #             subscription.is_trial_active = False
    #             subscription.status = SubscriptionStatus.ACTIVE
    #             self.logger.info(f"Trial ended for subscription {subscription.id}, transitioning to paid")
            
    #         subscription.updated_at = datetime_now_utc()
    #         await self.org_subscription_dao.update(db, db_obj=subscription, obj_in=schemas.SubscriptionUpdate())
            
    #         # Allocate new credits using rotation
    #         await self._allocate_subscription_credits(db, subscription, plan, is_renewal=True)
            
    #         return {
    #             "success": True,
    #             "subscription_id": subscription.id,
    #             "org_id": subscription.org_id,
    #             "renewal_type": "trial_to_paid" if was_trial_active else "regular",
    #             "new_period_start": subscription.current_period_start,
    #             "new_period_end": subscription.current_period_end
    #         }
            
    #     except Exception as e:
    #         self.logger.error(f"Error processing subscription renewal: {e}", exc_info=True)
    #         raise BillingException(
    #             status_code=500,
    #             detail=f"Failed to process subscription renewal: {str(e)}"
    #         )
    
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
    
    # async def create_subscription(
    #     self,
    #     db: AsyncSession,
    #     org_id: uuid.UUID,
    #     subscription_data: schemas.SubscriptionCreate,
    #     user: User
    # ) -> models.OrganizationSubscription:
    #     """
    #     Create a new subscription for an organization.
        
    #     This method handles the complete subscription creation process including
    #     Stripe customer creation, subscription setup, and initial credit allocation.
    #     """
    #     # Get the subscription plan
    #     plan = await self.subscription_plan_dao.get(db, subscription_data.plan_id)
    #     if not plan:
    #         raise SubscriptionPlanNotFoundException()
        
    #     # Check if organization already has a subscription
    #     existing_subscriptions = await self.org_subscription_dao.get_by_org_id(db, org_id)
    #     if existing_subscriptions:
    #         raise InvalidSubscriptionStateException("Organization already has an active subscription")
        
    #     try:
    #         # Create or get Stripe customer
    #         stripe_customer = await self._get_or_create_stripe_customer(db, org_id, user)
            
    #         # Attach payment method if provided
    #         if subscription_data.payment_method_id:
    #             stripe.PaymentMethod.attach(
    #                 subscription_data.payment_method_id,
    #                 customer=stripe_customer.id
    #             )
                
    #             # Set as default payment method
    #             stripe.Customer.modify(
    #                 stripe_customer.id,
    #                 invoice_settings={"default_payment_method": subscription_data.payment_method_id}
    #             )
            
    #         # Determine trial period
    #         trial_days = subscription_data.trial_days or plan.trial_days
    #         trial_end = None
    #         if trial_days > 0 and plan.is_trial_eligible:
    #             trial_end = datetime_now_utc() + timedelta(days=trial_days)
            
    #         # Create Stripe subscription
    #         stripe_price_id = plan.stripe_price_id_annual if subscription_data.is_annual else plan.stripe_price_id_monthly
            
    #         stripe_subscription_params = {
    #             "customer": stripe_customer.id,
    #             "items": [{"price": stripe_price_id, "quantity": subscription_data.seats_count}],
    #             "metadata": {
    #                 "kiwiq_org_id": str(org_id),
    #                 "kiwiq_plan_id": str(plan.id),
    #                 "kiwiq_user_id": str(user.id)
    #             }
    #         }
            
    #         if trial_end:
    #             stripe_subscription_params["trial_end"] = int(trial_end.timestamp())
            
    #         stripe_subscription = stripe.Subscription.create(**stripe_subscription_params)
            
    #         # Create subscription record in database
    #         now = datetime_now_utc()
    #         subscription = models.OrganizationSubscription(
    #             org_id=org_id,
    #             plan_id=plan.id,
    #             stripe_subscription_id=stripe_subscription.id,
    #             status=SubscriptionStatus.TRIAL if trial_end else SubscriptionStatus.ACTIVE,
    #             current_period_start=datetime.fromtimestamp(stripe_subscription.current_period_start, tz=timezone.utc),
    #             current_period_end=datetime.fromtimestamp(stripe_subscription.current_period_end, tz=timezone.utc),
    #             seats_count=subscription_data.seats_count,
    #             is_annual=subscription_data.is_annual,
    #             trial_start=now if trial_end else None,
    #             trial_end=trial_end,
    #             is_trial_active=bool(trial_end),
    #             created_at=now,
    #             updated_at=now
    #         )
            
    #         subscription = await self.org_subscription_dao.create(db, obj_in=subscription)
            
    #         # Allocate initial credits
    #         await self._allocate_subscription_credits(db, subscription, plan)
            
    #         self.logger.info(f"Created subscription for org {org_id}: {subscription.id}")
    #         return subscription
            
    #     except stripe.StripeError as e:
    #         self.logger.error(f"Stripe error creating subscription: {e}")
    #         raise StripeIntegrationException(
    #             detail="Failed to create subscription",
    #             stripe_error_code=e.code,
    #             stripe_error_message=str(e)
    #         )
    
    async def get_organization_subscription(
        self,
        db: AsyncSession,
        org_id: uuid.UUID
    ) -> List[models.OrganizationSubscription]:
        """Get the active subscription for an organization."""
        return await self.org_subscription_dao.get_by_org_id(db, org_id)
    
    # async def update_subscription(
    #     self,
    #     db: AsyncSession,
    #     org_id: uuid.UUID,
    #     subscription_update: schemas.SubscriptionUpdate
    # ) -> models.OrganizationSubscription:
    #     """
    #     Update an existing subscription with proper proration handling.
        
    #     This method handles:
    #     - Plan changes with immediate proration
    #     - Seat increases with immediate effect and proration
    #     - Seat decreases scheduled for next billing period
    #     - Subscription cancellation
    #     """
    #     subscriptions = await self.org_subscription_dao.get_by_org_id(db, org_id)
    #     if not subscriptions:
    #         raise SubscriptionNotFoundException()
        
    #     current_subscription = None
    #     for subscription in subscriptions:
    #         if subscription_update.subscription_id is None or subscription.id == subscription_update.subscription_id:
    #             current_subscription = subscription
    #             break
        
    #     if not current_subscription:
    #         raise SubscriptionNotFoundException()
        
    #     subscription = current_subscription

    #     try:
    #         # Get the subscription items from Stripe
    #         stripe_subscription = stripe.Subscription.retrieve(
    #             subscription.stripe_subscription_id,
    #             expand=['items']
    #         )
    #         subscription_item_id = stripe_subscription['items']['data'][0]['id']
            
    #         # Handle plan changes
    #         if subscription_update.plan_id and subscription_update.plan_id != subscription.plan_id:
    #             new_plan = await self.subscription_plan_dao.get(db, subscription_update.plan_id)
    #             if not new_plan:
    #                 raise SubscriptionPlanNotFoundException()
                
    #             # Check seat limits for new plan
    #             if subscription.seats_count > new_plan.max_seats:
    #                 raise SeatLimitExceededException(
    #                     f"Current seat count ({subscription.seats_count}) exceeds new plan limit ({new_plan.max_seats})"
    #                 )
                
    #             # Update Stripe subscription with new price
    #             stripe_price_id = new_plan.stripe_price_id_annual if subscription.is_annual else new_plan.stripe_price_id_monthly
                
    #             # Use subscription item update for plan change
    #             stripe.SubscriptionItem.modify(
    #                 subscription_item_id,
    #                 price=stripe_price_id,
    #                 proration_behavior="always_invoice"
    #             )
                
    #             subscription.plan_id = new_plan.id
                
    #             # Allocate credits for new plan with rotation
    #             await self._allocate_subscription_credits(db, subscription, new_plan, is_renewal=False)
            
    #         # Handle seat count changes
    #         if subscription_update.seats_count and subscription_update.seats_count != subscription.seats_count:
    #             # Check against plan limits
    #             current_plan = subscription.plan or await self.subscription_plan_dao.get(db, subscription.plan_id)
    #             if subscription_update.seats_count > current_plan.max_seats:
    #                 raise SeatLimitExceededException(
    #                     f"Requested seats ({subscription_update.seats_count}) exceeds plan limit ({current_plan.max_seats})"
    #                 )
                
    #             if subscription_update.seats_count > subscription.seats_count:
    #                 # Seat increase - apply immediately with proration
    #                 stripe.SubscriptionItem.modify(
    #                     subscription_item_id,
    #                     quantity=subscription_update.seats_count,
    #                     proration_behavior="always_invoice"
    #                 )
                    
    #                 self.logger.info(
    #                     f"Increased seats for subscription {subscription.id} from "
    #                     f"{subscription.seats_count} to {subscription_update.seats_count} (immediate)"
    #                 )
                    
    #                 subscription.seats_count = subscription_update.seats_count
                    
    #             else:
    #                 # Seat decrease - schedule for next billing period
    #                 # Use pending updates API to schedule the change
    #                 stripe.Subscription.modify(
    #                     subscription.stripe_subscription_id,
    #                     pending_update={
    #                         "subscription_items": [{
    #                             "id": subscription_item_id,
    #                             "quantity": subscription_update.seats_count
    #                         }]
    #                     },
    #                     proration_behavior="none"  # No proration for decreases
    #                 )
                    
    #                 self.logger.info(
    #                     f"Scheduled seat decrease for subscription {subscription.id} from "
    #                     f"{subscription.seats_count} to {subscription_update.seats_count} "
    #                     f"(effective at period end: {subscription.current_period_end})"
    #                 )
                    
    #                 # Note: Don't update local seats_count yet - it will be updated
    #                 # when the change takes effect via webhook
            
    #         # Handle cancellation
    #         if subscription_update.cancel_at_period_end is not None:
    #             if subscription_update.cancel_at_period_end:
    #                 stripe.Subscription.modify(
    #                     subscription.stripe_subscription_id,
    #                     cancel_at_period_end=True
    #                 )
    #                 subscription.cancel_at_period_end = True
    #                 self.logger.info(f"Scheduled subscription {subscription.id} for cancellation at period end")
    #             else:
    #                 # Reactivate subscription if it was scheduled for cancellation
    #                 stripe.Subscription.modify(
    #                     subscription.stripe_subscription_id,
    #                     cancel_at_period_end=False
    #                 )
    #                 subscription.cancel_at_period_end = False
    #                 self.logger.info(f"Removed cancellation for subscription {subscription.id}")
            
    #         subscription.updated_at = datetime_now_utc()
    #         subscription = await self.org_subscription_dao.update(db, db_obj=subscription, obj_in=subscription_update)
            
    #         self.logger.info(f"Updated subscription for org {org_id}: {subscription.id}")
    #         return subscription
            
    #     except stripe.StripeError as e:
    #         self.logger.error(f"Stripe error updating subscription: {e}")
    #         raise StripeIntegrationException(
    #             detail="Failed to update subscription",
    #             stripe_error_code=e.code,
    #             stripe_error_message=str(e)
    #         )
    
    async def create_checkout_session(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        user: User,
        plan_id: Optional[uuid.UUID] = None,
        is_annual: bool = False,
        seats_count: int = 1,
        price_id: Optional[str] = None,
        success_url: str = None,
        cancel_url: str = None
    ) -> Dict[str, Any]:
        """
        Create a Stripe Checkout session for subscription or one-time purchase.
        
        This method handles both subscription creation and one-time credit purchases
        through Stripe Checkout, providing a consistent payment flow.
        
        Args:
            db: Database session
            org_id: Organization ID
            user: User initiating the checkout
            plan_id: Subscription plan ID (for subscriptions)
            is_annual: Whether to use annual billing (for subscriptions)
            seats_count: Number of seats to purchase (for subscriptions)
            price_id: Stripe price ID (for one-time purchases)
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect after cancelled payment
            
        Returns:
            Dict containing checkout session URL and ID
        """
        try:
            # Get or create Stripe customer
            stripe_customer = await self._get_or_create_stripe_customer(db, org_id, user)
            
            # Prepare checkout session parameters
            checkout_params = {
                "customer": stripe_customer.id,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {
                    "kiwiq_org_id": str(org_id),
                    "kiwiq_user_id": str(user.id)
                }
            }
            
            if plan_id:
                # Subscription checkout
                plan = await self.subscription_plan_dao.get(db, plan_id)
                if not plan:
                    raise SubscriptionPlanNotFoundException()
                
                # Validate seat count against plan limits
                if seats_count > plan.max_seats:
                    raise SeatLimitExceededException(
                        current_seats=seats_count,
                        max_seats=plan.max_seats
                    )
                
                stripe_price_id = plan.stripe_price_id_annual if is_annual else plan.stripe_price_id_monthly
                
                # Validate that we have a valid Stripe price ID
                if not stripe_price_id:
                    self.logger.error(
                        f"No Stripe price ID found for plan {plan.name} (ID: {plan_id}), "
                        f"is_annual={is_annual}, price_id_annual={plan.stripe_price_id_annual}, "
                        f"price_id_monthly={plan.stripe_price_id_monthly}"
                    )
                    raise BillingConfigurationException(
                        f"Subscription plan '{plan.name}' is not properly configured with Stripe price IDs"
                    )
                
                checkout_params.update({
                    "mode": "subscription",
                    "line_items": [{
                        "price": stripe_price_id,
                        "quantity": seats_count
                    }],
                    "subscription_data": {
                        "metadata": {
                            "kiwiq_org_id": str(org_id),
                            "kiwiq_plan_id": str(plan_id),
                            "kiwiq_seats_count": str(seats_count)
                        }
                    }
                })
                
                # Add trial period if eligible
                if plan.is_trial_eligible and plan.trial_days > 0:
                    checkout_params["subscription_data"]["trial_period_days"] = plan.trial_days
                
                self.logger.info(
                    f"Creating subscription checkout for plan {plan.name} with {seats_count} seats"
                )
                
            elif price_id:
                # One-time purchase checkout
                checkout_params.update({
                    "mode": "payment",
                    "line_items": [{
                        "price": price_id,
                        "quantity": 1
                    }],
                    "payment_intent_data": {
                        "metadata": {
                            "kiwiq_org_id": str(org_id),
                            "kiwiq_user_id": str(user.id),
                            "kiwiq_type": "credit_purchase"
                        }
                    }
                })
            else:
                raise BillingConfigurationException("Either plan_id or price_id must be provided")
            
            # Create checkout session
            session = stripe.checkout.Session.create(**checkout_params)
            
            self.logger.info(f"Created checkout session {session.id} for org {org_id}")
            
            return {
                "checkout_url": session.url,
                "session_id": session.id,
                "expires_at": datetime.fromtimestamp(session.expires_at, tz=timezone.utc)
            }
            
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating checkout session: {e}")
            raise StripeIntegrationException(
                detail="Failed to create checkout session",
                stripe_error_code=e.code,
                stripe_error_message=str(e)
            )
    
    
    

    # async def purchase_credits(
    #     self,
    #     db: AsyncSession,
    #     org_id: uuid.UUID,
    #     user_id: uuid.UUID,
    #     purchase_request: schemas.CreditPurchaseRequest
    # ) -> models.CreditPurchase:
    #     """
    #     Purchase additional credits through Stripe.
        
    #     This method creates a payment intent for one-time credit purchases,
    #     allowing organizations to buy credits outside of their subscription.
        
    #     Args:
    #         db: Database session
    #         org_id: Organization ID
    #         user_id: User ID initiating the purchase
    #         purchase_request: Credit purchase details
            
    #     Returns:
    #         CreditPurchase record with payment intent details
    #     """
    #     try:
    #         # Get or create Stripe customer
    #         user = await db.get(User, user_id)
    #         if not user:
    #             raise BillingException(
    #                 status_code=404,
    #                 detail="User not found"
    #             )
            
    #         stripe_customer = await self._get_or_create_stripe_customer(db, org_id, user)
            
    #         # Calculate price for the credits
    #         amount_dollars = self._calculate_credit_price(
    #             purchase_request.credit_type,
    #             purchase_request.credits_amount
    #         )
    #         amount_cents = int(amount_dollars * 100)
            
    #         # Create payment intent
    #         payment_intent = stripe.PaymentIntent.create(
    #             amount=amount_cents,
    #             currency="usd",
    #             customer=stripe_customer.id,
    #             payment_method=purchase_request.payment_method_id,
    #             confirm=True,
    #             metadata={
    #                 "kiwiq_org_id": str(org_id),
    #                 "kiwiq_user_id": str(user_id),
    #                 "kiwiq_type": "credit_purchase",
    #                 "credit_type": purchase_request.credit_type.value,
    #                 "credits_amount": str(purchase_request.credits_amount)
    #             }
    #         )
            
    #         # Calculate expiration (purchased credits expire after configured days)
    #         expires_at = None
    #         if settings.PURCHASED_CREDITS_EXPIRE_DAYS:
    #             expires_at = datetime_now_utc() + timedelta(days=settings.PURCHASED_CREDITS_EXPIRE_DAYS)
            
    #         # Create purchase record
    #         purchase = await self.credit_purchase_dao.create_purchase(
    #             db=db,
    #             org_id=org_id,
    #             user_id=user_id,
    #             stripe_checkout_id=payment_intent.id,
    #             credit_type=purchase_request.credit_type,
    #             credits_amount=purchase_request.credits_amount,
    #             amount_paid=amount_dollars,
    #             currency="usd",
    #             expires_at=expires_at
    #         )
            
    #         # If payment is immediately successful, allocate credits
    #         if payment_intent.status == "succeeded":
    #             await self._allocate_purchased_credits(db, purchase)
    #             purchase = await self.credit_purchase_dao.update_payment_status(
    #                 db, purchase, PaymentStatus.SUCCEEDED
    #             )
            
    #         self.logger.info(
    #             f"Created credit purchase for org {org_id}: "
    #             f"{purchase_request.credits_amount} {purchase_request.credit_type.value} credits"
    #         )
            
    #         return purchase
            
    #     except stripe.StripeError as e:
    #         self.logger.error(f"Stripe error purchasing credits: {e}")
    #         raise StripeIntegrationException(
    #             detail="Failed to process credit purchase",
    #             stripe_error_code=e.code,
    #             stripe_error_message=str(e)
    #         )
    
    async def create_customer_portal_session(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        return_url: str
    ) -> Dict[str, str]:
        """
        Create a Stripe Customer Portal session using KiwiQ-managed configuration.
        
        This allows customers to manage their subscription, update payment methods,
        and view invoices through Stripe's hosted portal with our custom configuration
        that includes:
        - Subscription plan changes with proper proration
        - Seat count adjustments
        - Subscription cancellation at period end
        - Invoice history
        - Payment method updates
        
        Args:
            db: Database session
            org_id: Organization ID
            return_url: URL to return to after portal session
            
        Returns:
            Dict with portal URL
        """
        try:
            # Get organization to find customer ID
            organization = await self.org_dao.get(db, org_id)
            if not organization or not organization.external_billing_id:
                raise SubscriptionNotFoundException("No Stripe customer found for organization")
            
            # Find KiwiQ-managed portal configuration
            kiwiq_config_id = None
            try:
                # List portal configurations and find our managed one
                configurations = stripe.billing_portal.Configuration.list(limit=100)
                for config in configurations.auto_paging_iter():
                    if config.metadata.get("kiwiq_managed") == "true" and config.active:
                        kiwiq_config_id = config.id
                        self.logger.debug(f"Found KiwiQ portal configuration: {kiwiq_config_id}")
                        break
                
                if not kiwiq_config_id:
                    self.logger.warning(
                        "No active KiwiQ-managed portal configuration found, "
                        "using Stripe default configuration"
                    )
            except stripe.StripeError as e:
                self.logger.warning(f"Error finding portal configuration: {e}, using default")
            
            # Create portal session with configuration if found
            session_params = {
                "customer": organization.external_billing_id,
                "return_url": return_url
            }
            
            if kiwiq_config_id:
                session_params["configuration"] = kiwiq_config_id
            
            session = stripe.billing_portal.Session.create(**session_params)
            
            self.logger.info(
                f"Created customer portal session for org {org_id} "
                f"(config: {'KiwiQ-managed' if kiwiq_config_id else 'default'})"
            )
            
            return {
                "portal_url": session.url
            }
            
        except stripe.StripeError as e:
            self.logger.error(f"Stripe error creating portal session: {e}")
            raise StripeIntegrationException(
                detail="Failed to create customer portal session",
                stripe_error_code=e.code,
                stripe_error_message=str(e)
            )
    
    # async def update_subscription_seats(
    #     self,
    #     db: AsyncSession,
    #     org_id: uuid.UUID,
    #     seat_update: schemas.SubscriptionSeatUpdate
    # ) -> models.OrganizationSubscription:
    #     """
    #     Update subscription seat count with proper handling of increases vs decreases.
        
    #     Seat increases:
    #     - Take effect immediately
    #     - Generate prorated invoice for the current period
        
    #     Seat decreases:
    #     - Scheduled for the next billing period
    #     - No proration or immediate charges
        
    #     Args:
    #         db: Database session
    #         org_id: Organization ID
    #         seat_update: Seat update request
            
    #     Returns:
    #         Updated subscription
            
    #     Raises:
    #         SubscriptionNotFoundException: If no active subscription
    #         SeatLimitExceededException: If requested seats exceed plan limit
    #     """
    #     # Use the general update method with seat-specific logic
    #     subscription_update = schemas.SubscriptionUpdate(
    #         seats_count=seat_update.seats_count
    #     )
        
    #     return await self.update_subscription(db, org_id, subscription_update)
    
    async def _handle_subscription_trial_ending(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
        """
        Handle subscription trial ending webhook (sent 3 days before trial ends).
        
        This is a good time to:
        - Send reminder emails
        - Ensure payment method is on file
        - Prepare for transition to paid subscription
        """
        stripe_subscription = event_data["object"]
        subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(
            db, stripe_subscription["id"]
        )
        
        if subscription:
            self.logger.info(
                f"Trial ending soon for subscription {subscription.id} "
                f"(trial ends: {subscription.trial_end})"
            )
            # TODO: Trigger notification service to send trial ending email
    
    # async def _handle_invoice_payment_succeeded(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
    #     """
    #     Handle successful invoice payment webhook.
        
    #     This is triggered for:
    #     - Subscription renewals
    #     - Subscription upgrades/downgrades with proration
    #     - Seat count changes with immediate billing
    #     """
    #     invoice = event_data["object"]
    #     subscription_id = invoice.get("subscription")
        
    #     if not subscription_id:
    #         # Not a subscription invoice
    #         self.logger.debug(f"Non-subscription invoice paid: {invoice['id']}")
    #         return
        
    #     subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(db, subscription_id)
    #     if not subscription:
    #         self.logger.error(f"Subscription not found for invoice: {subscription_id}")
    #         return
        
    #     # Check if this is a renewal (invoice for a new billing period)
    #     billing_reason = invoice.get("billing_reason", "")
        
    #     if billing_reason == "subscription_cycle":
    #         # This is a regular subscription renewal
    #         self.logger.info(
    #             f"Subscription renewal payment succeeded for {subscription.id} "
    #             f"(invoice: {invoice['id']}, amount: ${invoice['amount_paid']/100:.2f})"
    #         )
    #         # Note: Credit rotation happens in subscription.updated webhook
    #         # when the period changes
            
    #     elif billing_reason in ["subscription_update", "subscription_create"]:
    #         # This is from a subscription change or initial creation
    #         self.logger.info(
    #             f"Subscription update payment succeeded for {subscription.id} "
    #             f"(invoice: {invoice['id']}, reason: {billing_reason})"
    #         )
        
    #     # Update subscription payment status if needed
    #     if subscription.status == SubscriptionStatus.PAST_DUE:
    #         subscription.status = SubscriptionStatus.ACTIVE
    #         subscription.updated_at = datetime_now_utc()
    #         await self.org_subscription_dao.update(db, db_obj=subscription, obj_in=schemas.SubscriptionUpdate())
    #         self.logger.info(f"Subscription {subscription.id} recovered from past_due status")
    
    # async def _handle_invoice_payment_failed(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
    #     """
    #     Handle failed invoice payment webhook.
        
    #     This updates the subscription status to past_due and may trigger
    #     dunning management processes.
    #     """
    #     invoice = event_data["object"]
    #     subscription_id = invoice.get("subscription")
        
    #     if not subscription_id:
    #         self.logger.debug(f"Non-subscription invoice payment failed: {invoice['id']}")
    #         return
        
    #     subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(db, subscription_id)
    #     if subscription:
    #         subscription.status = SubscriptionStatus.PAST_DUE
    #         subscription.updated_at = datetime_now_utc()
            
    #         await self.org_subscription_dao.update(db, db_obj=subscription, obj_in=schemas.SubscriptionUpdate())
            
    #         self.logger.warning(
    #             f"Invoice payment failed for subscription {subscription.id} "
    #             f"(invoice: {invoice['id']}, amount: ${invoice['amount_due']/100:.2f})"
    #         )
    #         # TODO: Trigger notification service for payment failure
    



    # # --- Unified Subscription Lifecycle Management --- #
    
    async def sync_subscription_from_stripe(
        self,
        db: AsyncSession,
        stripe_subscription: Dict[str, Any],
        create_if_not_exists: bool = False
    ) -> Tuple[models.OrganizationSubscription, models.OrganizationSubscription, Dict[str, Any]]:
        """
        Sync subscription state from Stripe to database.
        
        This unified function handles subscription creation and updates based on
        Stripe subscription object, detecting changes and returning a summary.
        
        Args:
            db: Database session
            stripe_subscription: Stripe subscription object
            create_if_not_exists: Whether to create new subscription if not found
            
        Returns:
            Tuple of (subscription, changes_dict) where changes_dict contains
            what was changed
            
        Raises:
            SubscriptionNotFoundException: If subscription not found and create_if_not_exists is False
        """
        try:
            stripe_sub_id = stripe_subscription["id"]
            
            # Try to find existing subscription
            existing_subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(
                db, stripe_sub_id
            )
            
            changes = {}
            is_new_subscription = False
            
            if not existing_subscription:
                if not create_if_not_exists:
                    raise SubscriptionNotFoundException(f"Subscription {stripe_sub_id} not found")
                
                # Create new subscription
                is_new_subscription = True
                
                # Extract metadata
                metadata = stripe_subscription.get("metadata", {})
                org_id = metadata.get("kiwiq_org_id")
                plan_id = metadata.get("kiwiq_plan_id")
                
                if not org_id or not plan_id:
                    raise BillingException(
                        status_code=400,
                        detail=f"Missing required metadata in Stripe subscription {stripe_sub_id}"
                    )
                
                # Get plan
                plan = await self.subscription_plan_dao.get(db, uuid.UUID(plan_id))
                if not plan:
                    raise SubscriptionPlanNotFoundException()
                
                # Ensure organization has correct external_billing_id
                organization = await self.org_dao.get(db, uuid.UUID(org_id))
                if organization and not organization.external_billing_id:
                    organization.external_billing_id = stripe_subscription["customer"]
                    db.add(organization)
                
                # Extract subscription details
                now = datetime_now_utc()
                
                # Get trial info
                trial_end = None
                is_trial_active = False
                if stripe_subscription.get("trial_end"):
                    trial_end = datetime.fromtimestamp(stripe_subscription["trial_end"], tz=timezone.utc)
                    is_trial_active = trial_end > now
                
                # Get subscription items
                items_data = stripe_subscription.get("items", {}).get("data", [])
                if not items_data:
                    raise BillingException(
                        status_code=400,
                        detail=f"No subscription items found in Stripe subscription {stripe_sub_id}"
                    )
                
                subscription_item = items_data[0]
                seats_count = subscription_item.get("quantity", 1)
                
                # Determine billing interval
                price_data = subscription_item.get("price", {})
                new_is_annual = price_data.get("recurring", {}).get("interval") == "year"
                
                # Map Stripe status to our status
                status = self._map_stripe_status_to_subscription_status(stripe_subscription["status"])
                
                # Create subscription
                subscription = models.OrganizationSubscription(
                    org_id=uuid.UUID(org_id),
                    plan_id=uuid.UUID(plan_id),
                    stripe_subscription_id=stripe_sub_id,
                    status=status,
                    current_period_start=datetime.fromtimestamp(
                        subscription_item["current_period_start"], tz=timezone.utc
                    ),
                    current_period_end=datetime.fromtimestamp(
                        subscription_item["current_period_end"], tz=timezone.utc
                    ),
                    seats_count=seats_count,
                    is_annual=new_is_annual,
                    trial_start=now if is_trial_active else None,
                    trial_end=trial_end,
                    is_trial_active=is_trial_active,
                    cancel_at_period_end=stripe_subscription.get("cancel_at_period_end", False),
                    created_at=now,
                    updated_at=now
                )
                
                subscription = await self.org_subscription_dao.create(db, obj_in=subscription)
                changes["created"] = True
                changes["initial_status"] = status.value
                changes["seats_count"] = seats_count
                changes["is_annual"] = new_is_annual
                
                self.logger.info(
                    f"Created subscription {subscription.id} from Stripe {stripe_sub_id}"
                )
                
            else:
                # Update existing subscription
                # Create a copy of the existing subscription to track changes
                subscription = existing_subscription
                existing_subscription = models.OrganizationSubscription(**existing_subscription.model_dump())
                
                # Check for status changes
                old_status = subscription.status
                new_status = self._map_stripe_status_to_subscription_status(stripe_subscription["status"])
                
                if old_status != new_status:
                    subscription.status = new_status
                    changes["status"] = {"old": old_status.value, "new": new_status.value}
                    
                    # Handle trial to active transition
                    if old_status == SubscriptionStatus.TRIAL and new_status == SubscriptionStatus.ACTIVE:
                        subscription.is_trial_active = False
                        changes["trial_ended"] = True
                

                # Check for seat changes
                items_data = stripe_subscription.get("items", {}).get("data", [])
                subscription_item = items_data[0] if items_data else None
                if not subscription_item:
                    raise BillingException(
                        status_code=400,
                        detail=f"No subscription items found in Stripe subscription {stripe_sub_id}"
                    )

                old_plan_id = subscription.plan_id
                new_plan_id = subscription_item.get("plan", {}).get("metadata", {}).get("kiwiq_plan_id", {})
                if old_plan_id != new_plan_id:
                    subscription.plan_id = new_plan_id
                    changes["plan_id"] = {"old": old_plan_id, "new": new_plan_id}
                
                # Check for seat changes
                new_seats = subscription_item.get("quantity", 1)
                if subscription.seats_count != new_seats:
                    changes["seats_count"] = {"old": subscription.seats_count, "new": new_seats}
                    subscription.seats_count = new_seats
                
                # Determine billing interval changes
                price_data = subscription_item.get("price", {})
                new_is_annual = price_data.get("recurring", {}).get("interval") == "year"
                if subscription.is_annual != new_is_annual:
                    subscription.is_annual = new_is_annual
                    changes["is_annual"] = new_is_annual
                
                # Check for period changes (renewal)
                new_period_start = datetime.fromtimestamp(
                    subscription_item["current_period_start"], tz=timezone.utc
                )
                new_period_end = datetime.fromtimestamp(
                    subscription_item["current_period_end"], tz=timezone.utc
                )
                
                if subscription.current_period_end != new_period_end:
                    subscription.current_period_start = new_period_start
                    subscription.current_period_end = new_period_end
                    changes["period_renewed"] = {
                        "old_end": subscription.current_period_end,
                        "new_start": new_period_start,
                        "new_end": new_period_end
                    }
                
                # Check for trial changes
                if stripe_subscription.get("trial_end"):
                    new_trial_end = datetime.fromtimestamp(
                        stripe_subscription["trial_end"], tz=timezone.utc
                    )
                    if subscription.trial_end != new_trial_end:
                        subscription.trial_end = new_trial_end
                        changes["trial_end"] = new_trial_end
                
                # Check for cancellation changes
                cancel_at_period_end = stripe_subscription.get("cancel_at_period_end", False)
                if subscription.cancel_at_period_end != cancel_at_period_end:
                    subscription.cancel_at_period_end = cancel_at_period_end
                    changes["cancel_at_period_end"] = cancel_at_period_end
                    
                    if cancel_at_period_end:
                        subscription.canceled_at = datetime_now_utc()
                
                # Always update timestamp
                subscription.updated_at = datetime_now_utc()
                
                # Save changes
                await self.org_subscription_dao.update(
                    db, db_obj=subscription, obj_in=schemas.SubscriptionUpdate()
                )
                
                if changes:
                    self.logger.info(
                        f"Updated subscription {subscription.id} with changes: {changes}"
                    )
            
            return existing_subscription, subscription, changes
            
        except (SubscriptionNotFoundException, SubscriptionPlanNotFoundException, BillingException):
            raise
        except Exception as e:
            self.logger.error(f"Error syncing subscription from Stripe: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to sync subscription: {str(e)}"
            )
    
    def _map_stripe_status_to_subscription_status(self, stripe_status: str) -> SubscriptionStatus:
        """Map Stripe subscription status to our SubscriptionStatus enum."""
        status_mapping = {
            "trialing": SubscriptionStatus.TRIAL,
            "active": SubscriptionStatus.ACTIVE,
            "past_due": SubscriptionStatus.PAST_DUE,
            "canceled": SubscriptionStatus.CANCELED,
            "incomplete": SubscriptionStatus.PAUSED,
            "incomplete_expired": SubscriptionStatus.CANCELED,
            "unpaid": SubscriptionStatus.PAST_DUE,
            "paused": SubscriptionStatus.PAUSED
        }
        return status_mapping.get(stripe_status, SubscriptionStatus.PAUSED)
    
    async def calculate_subscription_credits(
        self,
        subscription: models.OrganizationSubscription,
        plan: models.SubscriptionPlan,
        proration_factor: Optional[float] = None
    ) -> Dict[CreditType, float]:
        """
        Calculate credits for a subscription based on plan and billing period.
        
        This handles:
        - Monthly vs annual billing
        - Seat multipliers
        - Pro-rated credits for partial periods
        
        Args:
            subscription: Subscription object
            plan: Subscription plan
            proration_factor: Override billing period for pro-ration (0-1)
            
        Returns:
            Dictionary of credit types to amounts
        """
        credits = {}
        
        # Base credits from plan (monthly allocation)
        base_credits = plan.monthly_credits

        seats_multiplier = subscription.seats_count

        subscription_duration_multiplier = 1
        # Handle annual subscriptions (give all credits upfront)
        if subscription.is_annual:
            subscription_duration_multiplier = 12  # Give full year's worth of credits

        if subscription.is_trial_active:
            if proration_factor is None:
                proration_factor = settings.TRIAL_CREDITS_PRORATION_FACTOR
            seats_multiplier = min(seats_multiplier, 1)
            # For trial, we give all credits upfront
            subscription_duration_multiplier = 1

        # Multiply by seats
        for credit_type_str, base_amount in base_credits.items():
            credit_type = CreditType(credit_type_str)
            total_amount = base_amount * seats_multiplier * subscription_duration_multiplier
            
            # Handle pro-ration if specific period provided
            if proration_factor is not None:
                # Pro-rate based on factor (0-1)
                total_amount *= proration_factor
            
            credits[credit_type] = total_amount
            
            if subscription.is_trial_active:
                max_trial_credits = settings.MAX_TRIAL_CREDITS.get(credit_type.value, settings.MAX_TRIAL_CREDITS["default"])
                credits[credit_type] = min(total_amount, max_trial_credits)
                # print(f"credit_type: {credit_type}, total_amount FINAL: {credits[credit_type]}")
        
        return credits
    
    async def apply_subscription_credits(
        self,
        db: AsyncSession,
        subscription: models.OrganizationSubscription,
        plan: models.SubscriptionPlan,
        credits_to_allocate: Optional[Dict[CreditType, float]] = None,
        is_renewal: bool = False,
        is_proration: bool = False,
        proration_factor: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Apply credits for a subscription with proper handling of renewals and prorations.
        
        This unified function handles:
        - Initial credit allocation
        - Renewal credit rotation
        - Pro-rated credits for mid-cycle changes
        - Trial vs paid credit allocation
        
        Args:
            db: Database session
            subscription: Subscription object
            plan: Subscription plan
            credits_to_allocate: Credits to allocate (for prorations)
            is_renewal: Whether this is a renewal
            is_proration: Whether this is a proration adjustment
            proration_factor: Factor for proration (0-1)
            
        Returns:
            Dictionary with credit allocation summary
        """
        try:
            # Calculate credits
            if credits_to_allocate is None:
                credits_to_allocate = await self.calculate_subscription_credits(
                    subscription, plan, proration_factor
                )
            
            # Determine expiration
            now = datetime_now_utc()
            if subscription.is_trial_active:
                expires_at = subscription.trial_end or (now + timedelta(days=settings.TRIAL_CREDITS_EXPIRE_DAYS))
            elif subscription.is_annual:
                expires_at = subscription.current_period_end + timedelta(days=settings.SUBSCRIPTION_CREDITS_EXPIRE_DAYS_ANNUAL)
            else:
                expires_at = subscription.current_period_end + timedelta(days=settings.SUBSCRIPTION_CREDITS_EXPIRE_DAYS)
            
            # Handle different allocation scenarios
            if is_renewal and not subscription.is_trial_active:
                # Use credit rotation for renewals
                rotation_result = await self.rotate_subscription_credits(
                    db=db,
                    subscription_id=subscription.id,
                    new_credits=credits_to_allocate,
                    new_expires_at=expires_at
                )
                
                return {
                    "success": True,
                    "allocation_type": "renewal_rotation",
                    "credits_allocated": credits_to_allocate,
                    "expires_at": expires_at,
                    "rotation_result": rotation_result
                }
                
            elif is_proration:
                # For prorations, just add the additional credits without rotation
                addition_results = []
                
                for credit_type, amount in credits_to_allocate.items():
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
                            "plan_id": str(plan.id),
                            "is_proration": True,
                            "proration_factor": proration_factor,
                            "period_start": subscription.current_period_start.isoformat(),
                            "period_end": subscription.current_period_end.isoformat()
                        },
                        expires_at=expires_at,
                        commit=False
                    )
                    
                    # Add to net credits
                    result = await self.org_net_credits_dao.add_credits(
                        db=db,
                        org_id=subscription.org_id,
                        credit_type=credit_type,
                        credits_to_add=amount,
                        source_type=CreditSourceType.SUBSCRIPTION,
                        source_id=str(subscription.id),
                        expires_at=expires_at,
                        commit=False
                    )
                    addition_results.append(result)
                
                await db.commit()
                
                return {
                    "success": True,
                    "allocation_type": "proration",
                    "credits_allocated": credits_to_allocate,
                    "proration_factor": proration_factor,
                    "expires_at": expires_at,
                    "addition_results": addition_results
                }
                
            else:
                # Initial allocation or trial allocation
                addition_results = []
                
                for credit_type, amount in credits_to_allocate.items():
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
                            "plan_id": str(plan.id),
                            "is_trial": subscription.is_trial_active,
                            "period_start": subscription.current_period_start.isoformat(),
                            "period_end": subscription.current_period_end.isoformat()
                        },
                        expires_at=expires_at,
                        commit=False
                    )
                    
                    # Add to net credits
                    result = await self.org_net_credits_dao.add_credits(
                        db=db,
                        org_id=subscription.org_id,
                        credit_type=credit_type,
                        credits_to_add=amount,
                        source_type=CreditSourceType.SUBSCRIPTION,
                        source_id=str(subscription.id),
                        expires_at=expires_at,
                        commit=False
                    )
                    addition_results.append(result)
                
                await db.commit()
                
                return {
                    "success": True,
                    "allocation_type": "initial" if not subscription.is_trial_active else "trial",
                    "credits_allocated": credits_to_allocate,
                    "expires_at": expires_at,
                    "addition_results": addition_results
                }
                
        except Exception as e:
            self.logger.error(f"--> Error applying subscription credits: {e}", exc_info=True)
            try:
                await db.rollback()
            except Exception as rollback_error:
                self.logger.error(f"--> Error during rollback: {rollback_error}", exc_info=True)
            
            raise BillingException(
                status_code=500,
                detail=f"Failed to apply subscription credits: {str(e)}"
            )
    
    async def process_subscription_payment_confirmed(
        self,
        db: AsyncSession,
        subscription: models.OrganizationSubscription,
        is_renewal: bool = False,
        # invoice_data: Optional[Dict[str, Any]] = None,
        is_first_payment: bool = False
    ) -> Dict[str, Any]:
        """
        Process confirmed payment for subscription and allocate credits.
        
        This is called when payment is confirmed via:
        - invoice.payment_succeeded for renewals
        - charge.succeeded for initial subscription payment
        
        Args:
            db: Database session
            subscription: Subscription object
            # invoice_data: Invoice data from Stripe (for renewals)
            is_first_payment: Whether this is the first payment
            
        Returns:
            Dictionary with processing summary
        """
        try:
            # Get the plan
            plan = subscription.plan or await self.subscription_plan_dao.get(db, subscription.plan_id)
            if not plan:
                raise SubscriptionPlanNotFoundException()
            
            # Determine if this is a renewal based on invoice data
            # is_renewal = False
            # if invoice_data:
            #     billing_reason = invoice_data.get("billing_reason", "")
            #     is_renewal = billing_reason == "subscription_cycle"
            
            # Apply credits
            result = await self.apply_subscription_credits(
                db=db,
                subscription=subscription,
                plan=plan,
                is_renewal=is_renewal,
                is_proration=False
            )
            
            # Update subscription payment status if needed
            if subscription.status == SubscriptionStatus.PAST_DUE:
                subscription.status = SubscriptionStatus.ACTIVE
                subscription.updated_at = datetime_now_utc()
                await self.org_subscription_dao.update(
                    db, db_obj=subscription, obj_in=schemas.SubscriptionUpdate()
                )
                result["status_updated"] = "past_due_to_active"
            
            self.logger.info(
                f"Processed subscription payment for {subscription.id}: "
                f"type={result['allocation_type']}, credits={result['credits_allocated']}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing subscription payment: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to process subscription payment: {str(e)}"
            )
    
    async def process_subscription_update(
        self,
        db: AsyncSession,
        old_subscription_state: models.OrganizationSubscription,
        new_subscription_state: models.OrganizationSubscription,
        changes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process subscription updates and apply credit adjustments.
        
        This handles all subscription changes holistically to avoid double-counting:
        - Seat count changes (with proration)
        - Plan changes
        - Billing period changes (monthly to annual, annual to monthly)
        - Status changes
        - Multiple simultaneous changes
        
        Args:
            db: Database session
            old_subscription_state: Previous subscription state
            new_subscription_state: New subscription state
            changes: Dictionary of changes detected
            
        Returns:
            Dictionary with update processing summary
        """
        try:
            result = {"success": True, "changes_processed": changes}
            
            # Get the plans (old and new)
            new_plan = new_subscription_state.plan or await self.subscription_plan_dao.get(
                db, new_subscription_state.plan_id
            )
            if not new_plan:
                raise SubscriptionPlanNotFoundException()
            
            old_plan = old_subscription_state.plan or await self.subscription_plan_dao.get(
                db, old_subscription_state.plan_id
            )
            if not old_plan:
                old_plan = new_plan  # Fallback if old plan not found
            
            if new_subscription_state.status == SubscriptionStatus.PAST_DUE:
                # Expire all subscription credits!
                # TODO: handle overrage more graciously!
                rotation_result = await self.rotate_subscription_credits(
                    db=db,
                    subscription_id=new_subscription_state.id,
                    new_credits={},
                    new_expires_at=new_subscription_state.current_period_end,
                    is_overdue=True
                )
                result["rotation_result"] = rotation_result
                return result
            
            
            # Determine if this is a true billing renewal (new billing cycle)
            is_billing_renewal = False
            new_start = None
            old_end = None
            if "period_renewed" in changes:
                period_change = changes["period_renewed"]
                old_end = period_change["old_end"]
                new_start = period_change["new_start"]
                new_end = period_change["new_end"]
                
                # Log the period change analysis
                self.logger.info(
                    f"Period change detected for subscription {new_subscription_state.id}: "
                    f"old_end={old_end}, new_start={new_start}, new_end={new_end}, "
                    f"is_billing_renewal={is_billing_renewal}"
                )
            
            # Check if this is a new billing cycle (not just a period adjustment)
            # A true renewal means the old period ended and a new one started
            is_billing_renewal = (
                (changes.get("trial_ended", False) or (old_end is not None and new_start >= old_end) or old_subscription_state.status == SubscriptionStatus.PAST_DUE) and  # Either a trial transition or New period starts after old one ended
                # NOTE: trial transition can come in between the finish of the trial!
                # Either the trial ended or previous subscription was active and this is normal renewal or previous subscription was PAST_DUE and this is paid now!
                (changes.get("trial_ended", False) or old_subscription_state.status == SubscriptionStatus.ACTIVE or old_subscription_state.status == SubscriptionStatus.PAST_DUE) and  # Was already active
                new_subscription_state.status == SubscriptionStatus.ACTIVE  # Still active
            )
            
            # Handle true billing renewals with credit rotation
            if is_billing_renewal:
                # For true renewals, we need to rotate credits
                self.logger.info(
                    f"Processing billing renewal for subscription {new_subscription_state.id}"
                )
                
                # Process the renewal with credit rotation
                renewal_result = await self.process_subscription_payment_confirmed(
                    db=db,
                    subscription=new_subscription_state,
                    is_renewal=True,
                    is_first_payment=False
                )
                result["renewal_result"] = renewal_result
                
                return result
                
                # # Check if there are other changes that need handling AFTER renewal
                # # (e.g., seat count changes that happened with the renewal)
                # other_changes = {k: v for k, v in changes.items() 
                #                if k not in ["period_renewed", "status", "updated_at"]}
                
                # if not other_changes:
                #     # No other changes, just return the renewal result
                #     return result
                # else:
                #     # Continue processing other changes after renewal
                #     self.logger.info(
                #         f"Processing additional changes after renewal: {other_changes}"
                #     )
            
            # Check if we need to calculate credit adjustments for non-renewal changes
            needs_credit_adjustment = any([
                "seats_count" in changes,
                "is_annual" in changes,
                "plan_id" in changes and old_subscription_state.plan_id != new_subscription_state.plan_id,
                changes.get("trial_ended", False)  # Trial transitions need credit handling
            ])
            
            if needs_credit_adjustment:
                # # For billing renewals with other changes, we only handle the other changes
                # # since renewal already handled the base credit rotation
                # if is_billing_renewal:
                #     # After renewal, they have the new period's base credits
                #     # We only need to adjust for changes like seat count differences
                #     self.logger.info(
                #         f"Calculating post-renewal adjustments for subscription {new_subscription_state.id}"
                #     )
                    
                #     # For post-renewal adjustments, the entire period is "remaining"
                #     now = datetime_now_utc()
                #     days_remaining = max(0, (new_subscription_state.current_period_end - now).days)
                #     days_in_period = (new_subscription_state.current_period_end - new_subscription_state.current_period_start).days
                    
                #     # Calculate only the DIFFERENCE from what renewal gave them
                #     credits_to_add = {}
                    
                #     # If seats changed, we need to adjust for the difference
                #     if "seats_count" in changes:
                #         old_seats = changes["seats_count"]["old"]
                #         new_seats = changes["seats_count"]["new"]
                #         seat_difference = new_seats - old_seats
                        
                #         if seat_difference != 0:
                #             for credit_type_str, base_amount in new_plan.monthly_credits.items():
                #                 credit_type = CreditType(credit_type_str)
                                
                #                 # Calculate credits for the seat difference
                #                 if new_subscription_state.is_annual:
                #                     # Annual: difference for full year
                #                     adjustment = base_amount * seat_difference * 12
                #                 else:
                #                     # Monthly: difference for one month
                #                     adjustment = base_amount * seat_difference
                                
                #                 if abs(adjustment) > 0.01:
                #                     credits_to_add[credit_type] = adjustment
                    
                #     # If plan changed during renewal, adjust for the credit difference
                #     if "plan_id" in changes and old_plan.id != new_plan.id:
                #         for credit_type_str, new_base_amount in new_plan.monthly_credits.items():
                #             credit_type = CreditType(credit_type_str)
                #             old_base_amount = old_plan.monthly_credits.get(credit_type_str, 0)
                            
                #             # Calculate the difference in base credits
                #             base_difference = new_base_amount - old_base_amount
                            
                #             if base_difference != 0:
                #                 if new_subscription_state.is_annual:
                #                     # Annual: difference for full year
                #                     adjustment = base_difference * new_subscription_state.seats_count * 12
                #                 else:
                #                     # Monthly: difference for one month
                #                     adjustment = base_difference * new_subscription_state.seats_count
                                
                #                 # Add to existing adjustment if any
                #                 current_adjustment = credits_to_add.get(credit_type, 0)
                #                 credits_to_add[credit_type] = current_adjustment + adjustment
                
                # else:
                # Not a billing renewal - calculate adjustments for mid-period changes
                now = datetime_now_utc()
                timedelta_remaining = (new_subscription_state.current_period_end - now)
                seconds_remaining = max(0, timedelta_remaining.total_seconds())
                timedelta_in_period = (new_subscription_state.current_period_end - new_subscription_state.current_period_start)
                seconds_in_period = timedelta_in_period.total_seconds()
                
                # Calculate what credits they SHOULD have for the remaining period with all changes
                credits_to_add = {}
                
                for credit_type_str, new_base_amount in new_plan.monthly_credits.items():
                    credit_type = CreditType(credit_type_str)
                    old_base_amount = old_plan.monthly_credits.get(credit_type_str, 0)
                    
                    # Calculate old total credits for the period
                    if old_subscription_state.is_annual:
                        # Annual: had 12 months worth
                        old_period_credits = old_base_amount * old_subscription_state.seats_count * 12
                    else:
                        # Monthly: had 1 month worth
                        old_period_credits = old_base_amount * old_subscription_state.seats_count
                    
                    # Calculate new total credits for the period
                    if new_subscription_state.is_annual:
                        # Annual: should have 12 months worth
                        new_period_credits = new_base_amount * new_subscription_state.seats_count * 12
                    else:
                        # Monthly: should have 1 month worth
                        new_period_credits = new_base_amount * new_subscription_state.seats_count
                    
                    # Calculate pro-rated credit adjustment using simplified formula:
                    # (new_price - old_price) × remaining_seconds / total_seconds
                    # This gives us the proportional adjustment needed for the remaining period
                    credit_difference = new_period_credits - old_period_credits
                    
                    if seconds_in_period > 0:
                        # Apply proration based on remaining time in period
                        adjustment = credit_difference * (seconds_remaining / seconds_in_period)
                    else:
                        adjustment = 0
                    
                    if credit_type != CreditType.DOLLAR_CREDITS:
                        adjustment = int(round(adjustment))
                    
                    if abs(adjustment) > 0.01:  # Only add if significant
                        credits_to_add[credit_type] = adjustment
                
                # Apply the credit adjustments if any
                if credits_to_add:
                    # Filter out negative adjustments (we don't remove credits mid-period)
                    positive_adjustments = {ct: amt for ct, amt in credits_to_add.items() if amt > 0}
                    
                    if positive_adjustments:
                        self.logger.info(
                            f"Applying credit adjustments for subscription {new_subscription_state.id}: "
                            f"{positive_adjustments}"
                        )
                        
                        # Apply the adjustments as a proration
                        adjustment_result = await self.apply_subscription_credits(
                            db=db,
                            subscription=new_subscription_state,
                            plan=new_plan,
                            credits_to_allocate=positive_adjustments,
                            is_renewal=False,
                            is_proration=True,
                            # proration_factor=seconds_remaining / seconds_in_period
                        )
                        
                        result["credit_adjustments"] = {
                            "days_remaining": round(seconds_remaining / 86400, 1),
                            "days_in_period": round(seconds_in_period / 86400, 1),
                            "credits_adjusted": positive_adjustments,
                            "adjustment_result": adjustment_result,
                            "changes_applied": {
                                "plan_changed": "plan_id" in changes,
                                "seats_changed": "seats_count" in changes,
                                "billing_changed": "is_annual" in changes
                            }
                        }
                
                # Log specific change details
                if "is_annual" in changes:
                    result["billing_period_change"] = {
                        "from": "annual" if old_subscription_state.is_annual else "monthly",
                        "to": "annual" if new_subscription_state.is_annual else "monthly"
                    }
                
                if "seats_count" in changes:
                    result["seat_change"] = {
                        "from": changes["seats_count"]["old"],
                        "to": changes["seats_count"]["new"]
                    }
                
                if "plan_id" in changes:
                    result["plan_change"] = {
                        "from": str(old_subscription_state.plan_id),
                        "to": str(new_subscription_state.plan_id)
                    }
            
            # Handle trial ending
            if changes.get("trial_ended"):
                self.logger.info(
                    f"Trial ended for subscription {new_subscription_state.id}, "
                    f"transitioning to paid status"
                )
                result["trial_transition"] = True
            
            # Handle status changes
            if "status" in changes:
                result["status_change"] = changes["status"]
            
            # Handle cancellation changes
            if "cancel_at_period_end" in changes:
                result["cancellation_change"] = {
                    "cancel_at_period_end": changes["cancel_at_period_end"]
                }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing subscription update: {e}", exc_info=True)
            raise BillingException(
                status_code=500,
                detail=f"Failed to process subscription update: {str(e)}"
            )
    
    # # --- Refactored Webhook Handlers Using Unified Lifecycle Functions --- #
    
    async def _handle_subscription_created(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
        """
        Handle subscription created webhook using unified lifecycle management.
        
        This is called when a new subscription is created via:
        - Checkout session completion
        - Direct API creation
        """
        stripe_subscription = event_data["object"]
        
        try:
            # Use unified sync function to create subscription
            prev_subscription, subscription, changes = await self.sync_subscription_from_stripe(
                db=db,
                stripe_subscription=stripe_subscription,
                create_if_not_exists=True
            )
            
            if changes.get("created"):
                # Get the plan for initial credit allocation
                plan = subscription.plan or await self.subscription_plan_dao.get(db, subscription.plan_id)
                if not plan:
                    self.logger.error(f"Plan not found for new subscription {subscription.id}")
                    return
                
                # Note: Don't allocate credits immediately for non-trial subscriptions
                # Wait for the first payment confirmation
                # if subscription.is_trial_active:
                    # For trials, allocate credits immediately
                allocation_result = await self.apply_subscription_credits(
                    db=db,
                    subscription=subscription,
                    plan=plan,
                    is_renewal=False,
                    is_proration=False
                )
                    
                self.logger.info(
                    f"Allocated trial credits for new subscription {subscription.id}: "
                    f"{allocation_result['credits_allocated']}"
                )
                # else:
                #     self.logger.info(
                #         f"Created subscription {subscription.id} - waiting for payment confirmation "
                #         f"before allocating credits"
                #     )
            
        except Exception as e:
            self.logger.error(f"Error handling subscription created webhook: {e}", exc_info=True)
    
    async def _handle_subscription_updated(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
        """
        Handle subscription updated webhook using unified lifecycle management.
        
        This handles all subscription state changes by comparing before/after states.
        """
        stripe_subscription = event_data["object"]
        
        try:
            # Get the current subscription state before sync
            # existing_subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(
            #     db, stripe_subscription["id"]
            # )
            
            # Sync the subscription state
            # NOTE: this will raise exception if subscription doesn't already exist in DB!
            existing_subscription, subscription, changes = await self.sync_subscription_from_stripe(
                db=db,
                stripe_subscription=stripe_subscription,
                create_if_not_exists=False
            )

            # Create a copy of the old state for comparison
            old_state = existing_subscription
            
            if changes:
                # Process the changes
                update_result = await self.process_subscription_update(
                    db=db,
                    old_subscription_state=old_state,
                    new_subscription_state=subscription,
                    changes=changes
                )
                
                self.logger.info(
                    f"Processed subscription update for {subscription.id}: {update_result}"
                )
            
        except Exception as e:
            self.logger.error(f"Error handling subscription updated webhook: {e}", exc_info=True)
    
    # async def _handle_subscription_deleted(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
    #     """
    #     Handle subscription deleted webhook.
        
    #     This is called when a subscription is fully canceled (not just scheduled for cancellation).
    #     """
    #     stripe_subscription = event_data["object"]
        
    #     try:
    #         subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(
    #             db, stripe_subscription["id"]
    #         )
            
    #         if subscription:
    #             subscription.status = SubscriptionStatus.CANCELED
    #             subscription.canceled_at = datetime_now_utc()
    #             subscription.updated_at = datetime_now_utc()
                
    #             await self.org_subscription_dao.update(
    #                 db, db_obj=subscription, obj_in=schemas.SubscriptionUpdate()
    #             )
                
    #             self.logger.info(f"Marked subscription {subscription.id} as canceled")
                
    #             # Note: We don't expire credits immediately - they remain valid until their natural expiration
                
    #     except Exception as e:
    #         self.logger.error(f"Error handling subscription deleted webhook: {e}", exc_info=True)
    
    # async def _handle_invoice_payment_succeeded(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
    #     """
    #     Handle successful invoice payment webhook for subscription renewals.
        
    #     This is the key event that triggers credit allocation/rotation for paid subscriptions.
    #     """
    #     invoice = event_data["object"]
    #     subscription_id = invoice.get("subscription")
        
    #     if not subscription_id:
    #         # Not a subscription invoice
    #         self.logger.debug(f"Non-subscription invoice paid: {invoice['id']}")
    #         return
        
    #     try:
    #         subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(
    #             db, subscription_id
    #         )
    #         if not subscription:
    #             self.logger.error(f"Subscription not found for invoice: {subscription_id}")
    #             return
            
    #         # Process the payment confirmation and allocate credits
    #         result = await self.process_subscription_payment_confirmed(
    #             db=db,
    #             subscription=subscription,
    #             invoice_data=invoice,
    #             is_first_payment=invoice.get("billing_reason") == "subscription_create"
    #         )
            
    #         self.logger.info(
    #             f"Processed invoice payment for subscription {subscription.id}: "
    #             f"{result}"
    #         )
            
    #     except Exception as e:
    #         self.logger.error(f"Error handling invoice payment succeeded webhook: {e}", exc_info=True)
    
    # async def _handle_charge_succeeded(self, db: AsyncSession, event_data: Dict[str, Any]) -> None:
    #     """
    #     Handle charge succeeded webhook.
        
    #     This can be used for:
    #     - First subscription payment (if no invoice.payment_succeeded is sent)
    #     - Credit purchase receipts
    #     """
    #     try:
    #         charge_object = event_data["object"]
            
    #         # Extract metadata
    #         metadata = charge_object.get("metadata", {})
    #         kiwiq_type = metadata.get("kiwiq_type")
            
    #         if kiwiq_type == "initial_subscription_payment":
    #             # Handle initial subscription payment
    #             subscription_id = metadata.get("subscription_id")
    #             if subscription_id:
    #                 subscription = await self.org_subscription_dao.get_by_stripe_subscription_id(
    #                     db, subscription_id
    #                 )
    #                 if subscription and subscription.status != SubscriptionStatus.ACTIVE:
    #                     # Process initial payment
    #                     result = await self.process_subscription_payment_confirmed(
    #                         db=db,
    #                         subscription=subscription,
    #                         is_first_payment=True
    #                     )
                        
    #                     self.logger.info(
    #                         f"Processed initial subscription payment via charge.succeeded: {result}"
    #                     )
            
    #         # Handle credit purchase receipts (existing logic)
    #         await self._handle_credit_purchase_charge(db, charge_object)
            
    #     except Exception as e:
    #         self.logger.error(f"Error handling charge.succeeded event: {e}", exc_info=True)
    
    async def _handle_credit_purchase_charge(self, db: AsyncSession, charge_object: Dict[str, Any]) -> None:
        """
        Handle charge succeeded for credit purchases (extracted from _handle_charge_succeeded).
        """
        # Extract key information from the charge
        metadata = charge_object.get("metadata", {})
        kiwiq_purchase_id = metadata.get("kiwiq_purchase_id")
        receipt_url = charge_object.get("receipt_url")
        
        if not receipt_url:
            self.logger.warning(f"No receipt URL found in charge.succeeded event")
            return
        
        # Get payment intent to find the checkout session
        if kiwiq_purchase_id:
            try:
                if kiwiq_purchase_id:
                    # Find the purchase record
                    purchase = await self.credit_purchase_dao.get(db, uuid.UUID(kiwiq_purchase_id))
                    if purchase:
                        # Update receipt URL
                        await self.credit_purchase_dao.update_receipt_url(
                            db=db,
                            purchase=purchase,
                            receipt_url=receipt_url
                        )
                        
                        self.logger.info(
                            f"Updated receipt URL for purchase {purchase.id} "
                            f"from charge {charge_object['id']}"
                        )
                    else:
                        self.logger.warning(
                            f"No purchase found for purchase ID {kiwiq_purchase_id} "
                            f"from charge {charge_object['id']}"
                        )
                else:
                    self.logger.warning(
                        f"No purchase ID found for charge {charge_object['id']}"
                    )
                    
            except stripe.StripeError as e:
                self.logger.error(f"Error retrieving purchase {kiwiq_purchase_id}: {e}")
        else:
            self.logger.warning(f"No purchase ID found in charge.succeeded event")
