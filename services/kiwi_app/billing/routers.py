"""
Billing routers for KiwiQ system.

This module defines the FastAPI routers for billing-related endpoints,
including subscription management, credit operations, and webhook handling.
It follows KiwiQ's established patterns for API design and error handling.
"""

import uuid
from typing import List, Optional, Annotated
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks, Query, Path, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

import stripe

from db.session import get_async_db_dependency

from kiwi_app.utils import get_kiwi_logger
from kiwi_app.settings import settings
from kiwi_app.auth.models import User
from kiwi_app.auth.utils import datetime_now_utc
from kiwi_app.auth.dependencies import get_current_active_verified_user, get_active_org_id, get_current_active_superuser

from kiwi_app.billing import schemas, services, dependencies
from kiwi_app.billing.models import CreditType
from kiwi_app.billing.exceptions import (
    InsufficientCreditsException,
    SubscriptionNotFoundException,
    SubscriptionPlanNotFoundException,
    InvalidSubscriptionStateException,
    PromotionCodeNotFoundException,
    PromotionCodeExpiredException,
    PromotionCodeExhaustedException,
    PromotionCodeAlreadyUsedException,
    PromotionCodeNotAllowedException,
    StripeIntegrationException,
    BillingException,
    SeatLimitExceededException,
    BillingConfigurationException
)

# Get logger for billing operations
billing_logger = get_kiwi_logger(name="kiwi_app.billing")

# Create router instances
billing_router = APIRouter(prefix="/billing", tags=["billing"])
billing_dashboard_router = APIRouter(prefix="/billing/dashboard", tags=["billing-dashboard"])
billing_admin_router = APIRouter(prefix="/billing/admin", tags=["billing-admin"])
billing_webhook_router = APIRouter(prefix="/billing/webhooks", tags=["billing-webhooks"])


def _get_base_url(request: Request, dev_env_suffix: str = ""):
    URL = f"{str(request.base_url).rstrip('/')}{settings.API_V1_PREFIX}{dev_env_suffix}"
    # return URL
    return f"{settings.REDIRECT_BASE_URL}{dev_env_suffix}" if settings.APP_ENV == "PROD" else URL


# --- Subscription Management Endpoints --- #

@billing_router.get("/plans", response_model=List[schemas.SubscriptionPlanRead], tags=["billing-subscription"])
async def get_subscription_plans(
    active_only: bool = Query(True, description="Whether to return only active plans"),
    current_user: User = Depends(get_current_active_verified_user),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get available subscription plans.
    
    This endpoint returns all available subscription plans that organizations
    can subscribe to. It follows KiwiQ's pattern of requiring organization context.
    """
    try:
        plans = await billing_service.get_subscription_plans(
            db=db,
            active_only=active_only
        )
        billing_logger.info(f"User {current_user.id} listed {len(plans)} subscription plans")
        return plans
    except Exception as e:
        billing_logger.error(f"Error fetching subscription plans: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch subscription plans"
        )


@billing_router.post("/checkout/dollar-credits/session", response_model=schemas.CheckoutSessionResponse)
async def create_flexible_dollar_credit_checkout_session(
    request: Request,
    purchase_request: schemas.FlexibleDollarCreditPurchaseRequest,
    # success_url: Optional[str] = Query(None, description="Custom success URL"),
    # cancel_url: Optional[str] = Query(None, description="Custom cancel URL"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireBillingReadActiveOrg),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Create a Stripe Checkout session for flexible dollar credit purchase (returns JSON).
    
    This endpoint is for API clients (mobile apps, SPAs) that need the checkout URL
    programmatically rather than being redirected. It returns the session details as JSON.
    
    The amount of credits received is calculated based on the dollar amount
    and the configured pricing ratio.
    
    Requires `billing:read` permission on the active organization.
    """
    try:
        # Construct success and cancel URLs using the auth pattern
        base_url = _get_base_url(request, "/billing/checkout-result")
        
        # Default URLs if not provided
        # if not success_url:
            # Include session_id placeholder that Stripe will replace
        success_url = f"{base_url}?success=true&session_id={{CHECKOUT_SESSION_ID}}"
        
        # if not cancel_url:
        cancel_url = f"{base_url}?canceled=true"
        
        result = await billing_service.create_flexible_dollar_credit_checkout_session(
            db=db,
            org_id=active_org_id,
            user=current_user,
            dollar_amount=purchase_request.dollar_amount,
            success_url=success_url,
            cancel_url=cancel_url
        )
        
        billing_logger.info(
            f"User {current_user.id} created flexible dollar credit checkout session "
            f"for org {active_org_id} with amount ${purchase_request.dollar_amount} (API response)"
        )
        
        return result
        
    except StripeIntegrationException as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=e.detail
        )
    except Exception as e:
        billing_logger.error(f"Error creating flexible dollar credit checkout session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )



# --- Credit Management Endpoints --- #

@billing_dashboard_router.get("/credits", response_model=List[schemas.CreditBalance])
async def get_credit_balances(
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireCreditReadActiveOrg),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get current credit balances for the active organization.
    
    Returns balances for all credit types including expiration information.
    Requires `credit:read` permission on the active organization.
    """
    try:
        balances = await billing_service.get_credit_balances(
            db=db,
            org_id=active_org_id
        )
        billing_logger.info(f"User {current_user.id} retrieved credit balances for org {active_org_id}")
        return balances
    except Exception as e:
        billing_logger.error(f"Error fetching credit balances: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch credit balances"
        )


@billing_dashboard_router.get("/credits/list", response_model=List[schemas.OrganizationCreditsRead])
async def get_organization_credits_by_type(
    credit_type: CreditType = Query(None, description="Type of credits to retrieve"),
    include_expired: bool = Query(False, description="Whether to include expired credit records"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireCreditReadActiveOrg),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get detailed credit records for the active organization by credit type.
    
    This endpoint returns individual credit allocation records showing the source,
    expiration, and detailed information for each credit allocation. Unlike the
    general credits endpoint which provides aggregated totals, this shows the
    itemized breakdown of all credit sources.
    
    Requires `credit:read` permission on the active organization.
    
    Args:
        credit_type (Optional): Type of credits to retrieve (workflows, web_searches, dollar_credits)
        include_expired: Whether to include expired credit records in the response
    
    Returns:
        List of detailed credit allocation records
    """
    try:
        credit_records = await billing_service.get_organization_credits_by_type(
            db=db,
            org_id=active_org_id,
            credit_type=credit_type,
            include_expired=include_expired
        )
        
        billing_logger.info(
            f"User {current_user.id} retrieved {len(credit_records)} {credit_type.value if credit_type else 'all'} "
            f"credit records for org {active_org_id} (include_expired={include_expired})"
        )
        
        return credit_records
        
    except BillingException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail
        )
    except Exception as e:
        billing_logger.error(f"Error fetching organization credits by type: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch {credit_type.value if credit_type else 'all'} credit records"
        )


# @billing_router.post("/purchase-credits", response_model=schemas.CreditPurchaseRead)
# async def purchase_credits(
#     purchase_request: schemas.CreditPurchaseRequest,
#     active_org_id: uuid.UUID = Depends(get_active_org_id),
#     current_user: User = Depends(dependencies.RequireBillingManageActiveOrg),
#     db: AsyncSession = Depends(get_async_db_dependency),
#     billing_service: services.BillingService = Depends(dependencies.get_billing_service)
# ):
#     """
#     Purchase additional credits through Stripe.
    
#     Creates a payment intent and processes the credit purchase.
#     Credits are allocated upon successful payment.
#     Requires `billing:manage` permission on the active organization.
#     """
#     try:
#         purchase = await billing_service.purchase_credits(
#             db=db,
#             org_id=active_org_id,
#             user_id=current_user.id,
#             purchase_request=purchase_request
#         )
        
#         billing_logger.info(f"User {current_user.id} created credit purchase for org {active_org_id}: {purchase.id}")
#         return purchase
        
#     except StripeIntegrationException as e:
#         raise HTTPException(
#             status_code=status.HTTP_402_PAYMENT_REQUIRED,
#             detail=e.detail
#         )
#     except Exception as e:
#         billing_logger.error(f"Error purchasing credits: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to purchase credits"
#         )

# --- Promotion Code Endpoints --- #

@billing_router.post("/promo-codes/apply", response_model=schemas.PromotionCodeApplyResult)
async def apply_promotion_code(
    code_application: schemas.PromotionCodeApply,
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireBillingManageActiveOrg),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Apply a promotion code to grant credits to the organization.
    
    Validates the promotion code and applies credits if eligible.
    Requires `billing:manage` permission on the active organization.
    """
    try:
        result = await billing_service.apply_promotion_code(
            db=db,
            org_id=active_org_id,
            user_id=current_user.id,
            code_application=code_application
        )
        
        billing_logger.info(f"User {current_user.id} applied promotion code {code_application.code} to org {active_org_id}")
        return result
        
    except PromotionCodeNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion code not found"
        )
    except PromotionCodeExpiredException:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Promotion code has expired"
        )
    except PromotionCodeExhaustedException:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Promotion code has reached its usage limit"
        )
    except PromotionCodeAlreadyUsedException:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Promotion code has already been used by this organization"
        )
    except PromotionCodeNotAllowedException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is not allowed to use this promotion code"
        )
    except Exception as e:
        billing_logger.error(f"Error applying promotion code: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to apply promotion code"
        )


# --- Usage Analytics Endpoints --- #

@billing_dashboard_router.get("/usage", response_model=schemas.UsageSummary)
async def get_usage_summary(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireBillingReadActiveOrg),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get usage summary for the active organization.
    
    Returns usage statistics for a specified date range.
    Defaults to the current billing period if no dates provided.
    Requires `billing:read` permission on the active organization.
    """
    try:
        # Default to current month if no dates provided
        if not start_date or not end_date:
            now = datetime_now_utc()
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if now.month == 12:
                end_date = start_date.replace(year=now.year + 1, month=1) - timedelta(days=1)
            else:
                end_date = start_date.replace(month=now.month + 1) - timedelta(days=1)
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        summary = await billing_service.get_usage_summary(
            db=db,
            org_id=active_org_id,
            start_date=start_date,
            end_date=end_date
        )
        
        billing_logger.info(f"User {current_user.id} retrieved usage summary for org {active_org_id}")
        return summary
    except Exception as e:
        billing_logger.error(f"Error fetching usage summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch usage summary"
        )


@billing_dashboard_router.get("/usage/events", response_model=schemas.PaginatedUsageEvents)
async def get_usage_events(
    org_id: Optional[uuid.UUID] = Query(None, description="Filter by organization ID (admin only)"),
    user_id: Optional[uuid.UUID] = Query(None, description="Filter by user ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    credit_type: Optional[CreditType] = Query(None, description="Filter by credit type"),
    is_overage: Optional[bool] = Query(None, description="Filter by overage status"),
    created_after: Optional[datetime] = Query(None, description="Filter events created after this date"),
    created_before: Optional[datetime] = Query(None, description="Filter events created before this date"),
    metadata_search: Optional[str] = Query(None, description="Search text in usage metadata JSON"),
    sort_by: str = Query("created_at", description="Field to sort by (created_at, credits_consumed, event_type)"),
    sort_order: schemas.SortOrder = Query(schemas.SortOrder.DESC, description="Sort order"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireBillingReadActiveOrg),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get usage events with comprehensive filtering and pagination.
    
    This endpoint provides detailed usage event querying capabilities with:
    - Filtering by user, event type, credit type, and overage status
    - Date range filtering for time-based analysis
    - Metadata search for finding specific events
    - Sorting and pagination for efficient data retrieval
    
    Regular users can only query their organization's events.
    Superusers can query any organization by providing org_id.
    
    Requires `billing:read` permission on the active organization.
    """
    try:
        # Determine which org_id to use
        # For regular users, always use their active org and ignore org_id parameter
        if not current_user.is_superuser:
            query_org_id = active_org_id
            if org_id and org_id != active_org_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only query usage events for your active organization"
                )
        else:
            # Superusers can query any org, default to active org if not specified
            query_org_id = org_id or active_org_id
        
        # Build query parameters
        query_params = schemas.UsageEventQuery(
            org_id=query_org_id,
            user_id=user_id,
            event_type=event_type,
            credit_type=credit_type,
            is_overage=is_overage,
            created_after=created_after,
            created_before=created_before,
            metadata_search=metadata_search,
            sort_by=sort_by,
            sort_order=sort_order,
            skip=skip,
            limit=limit
        )
        
        # Execute query
        result = await billing_service.get_usage_events(
            db=db,
            query_params=query_params
        )
        
        billing_logger.info(
            f"User {current_user.id} retrieved {len(result.items)} usage events "
            f"for org {query_org_id} (page {result.page} of {result.pages})"
        )
        
        return result
        
    except BillingException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail
        )
    except HTTPException:
        raise
    except Exception as e:
        billing_logger.error(f"Error fetching usage events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch usage events"
        )


@billing_dashboard_router.get("/dashboard", response_model=schemas.BillingDashboard)
async def get_billing_dashboard(
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireBillingReadActiveOrg),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get comprehensive billing dashboard data for the active organization.
    
    Returns subscription details, credit balances, recent usage, and warnings.
    Requires `billing:read` permission on the active organization.
    """
    try:
        dashboard = await billing_service.get_billing_dashboard(
            db=db,
            org_id=active_org_id
        )
        
        billing_logger.info(f"User {current_user.id} retrieved billing dashboard for org {active_org_id}")
        return dashboard
    except Exception as e:
        billing_logger.error(f"Error fetching billing dashboard: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch billing dashboard"
        )


# --- Webhook Endpoints --- #

@billing_webhook_router.post("/stripe")
async def handle_stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Handle Stripe webhook events.
    
    This endpoint processes Stripe webhooks to keep the billing system
    in sync with Stripe's state. It includes signature verification and
    idempotency handling.
    """
    try:
        # Get raw body for signature verification
        raw_body = await request.body()
        stripe_signature = request.headers.get("stripe-signature")
        
        if not stripe_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing Stripe signature"
            )
        
        # Verify webhook signature
        
        try:
            event = stripe.Webhook.construct_event(
                raw_body,
                stripe_signature,
                settings.STRIPE_WEBHOOK_SECRET
            )
            billing_logger.info(f"Received Stripe webhook: {event['type']} (ID: {event['id']})")
            # billing_logger.info(f"Event DATA: {event['data']}")
            # return {"status": "received"}
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payload"
            )
        except stripe.SignatureVerificationError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature"
            )
        
        # Convert to our schema
        webhook_event = schemas.StripeWebhookEvent(
            id=event["id"],
            type=event["type"],
            created=datetime.fromtimestamp(event["created"], tz=timezone.utc),
            data=event["data"],
            livemode=event["livemode"]
        )
        
        # Process webhook in background to avoid timeout
        background_tasks.add_task(
            process_webhook_background,
            webhook_event,
            billing_service
        )
        
        billing_logger.info(f"Received Stripe webhook: {event['type']} (ID: {event['id']})")
        
        return {"status": "received"}
        
    except HTTPException:
        raise
    except Exception as e:
        billing_logger.error(f"Error handling Stripe webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook"
        )


async def process_webhook_background(
    webhook_event: schemas.StripeWebhookEvent,
    billing_service: services.BillingService
):
    """
    Background task to process webhook events.
    
    This function handles the actual webhook processing in the background
    to avoid blocking the webhook response.
    """
    try:
        # Get database session
        async for db in get_async_db_dependency():
            success = await billing_service.process_stripe_webhook(db, webhook_event)
            
            if success:
                billing_logger.info(f"Successfully processed webhook: {webhook_event.id}")
            else:
                billing_logger.error(f"Failed to process webhook: {webhook_event.id}")
            
            break  # Exit the async generator
            
    except Exception as e:
        billing_logger.error(f"Error in webhook background processing: {e}", exc_info=True)



# --- Admin Endpoints --- #

@billing_admin_router.post("/plans", response_model=schemas.SubscriptionPlanRead)
async def create_subscription_plan(
    plan_data: schemas.SubscriptionPlanCreate,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Create a new subscription plan (Admin only).
    
    Creates both the database record and corresponding Stripe product/prices.
    Requires superuser permissions.
    """
    try:
        plan = await billing_service.create_subscription_plan(db, plan_data)
        billing_logger.info(f"Admin {current_user.id} created subscription plan: {plan.name} (ID: {plan.id})")
        return plan
    except StripeIntegrationException as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=e.detail
        )
    except Exception as e:
        billing_logger.error(f"Error creating subscription plan: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create subscription plan"
        )


@billing_admin_router.get("/plans", response_model=List[schemas.SubscriptionPlanRead])
async def get_all_subscription_plans(
    active_only: bool = Query(False, description="Whether to return only active plans"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get all subscription plans (Admin only).
    
    Returns all plans including inactive ones for administrative purposes.
    Requires superuser permissions.
    """
    try:
        plans = await billing_service.get_subscription_plans(db, active_only=active_only)
        billing_logger.info(f"Admin {current_user.id} retrieved {len(plans)} subscription plans")
        return plans
    except Exception as e:
        billing_logger.error(f"Error fetching admin subscription plans: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch subscription plans"
        )


@billing_admin_router.post("/promo-codes", response_model=schemas.PromotionCodeRead, tags=["billing-admin"])
async def create_promotion_code(
    promo_code_data: schemas.PromotionCodeCreate,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Create a new promotion code (Admin only).
    
    Creates a promotion code that organizations can use to receive free credits.
    Supports configuration of:
    - Credit type and amount
    - Usage limits (total and per organization)
    - Expiration date
    - Organization restrictions
    - Credit expiration period
    
    Requires superuser permissions.
    """
    try:
        promotion_code = await billing_service.create_promotion_code(db, promo_code_data)
        billing_logger.info(f"Admin {current_user.id} created promotion code: {promotion_code.code}")
        return promotion_code
    except BillingException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail
        )
    except Exception as e:
        billing_logger.error(f"Error creating promotion code: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create promotion code"
        )


@billing_admin_router.post("/promo-codes/query", response_model=schemas.PaginatedPromotionCodes, tags=["billing-admin"])
async def get_promotion_codes(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    credit_type: Optional[CreditType] = Query(None, description="Filter by credit type"),
    search_text: Optional[str] = Query(None, description="Search in code or description"),
    expires_after: Optional[datetime] = Query(None, description="Filter codes that expire after this date"),
    expires_before: Optional[datetime] = Query(None, description="Filter codes that expire before this date"),
    has_usage_limit: Optional[bool] = Query(None, description="Filter codes with/without usage limits"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: schemas.SortOrder = Query(schemas.SortOrder.DESC, description="Sort order"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get promotion codes with filtering and pagination (Admin only).
    
    Provides comprehensive promotion code querying capabilities with support for:
    - Active status filtering
    - Credit type filtering
    - Text search in code/description
    - Expiration date range filtering
    - Usage limit filtering
    - Flexible sorting and pagination
    
    Useful for admin management of promotion codes including monitoring usage,
    finding expired codes, and searching for specific promotions.
    
    Requires superuser permissions.
    """
    try:
        # Build query parameters
        query_params = schemas.PromotionCodeQuery(
            is_active=is_active,
            credit_type=credit_type,
            search_text=search_text,
            expires_after=expires_after,
            expires_before=expires_before,
            has_usage_limit=has_usage_limit,
            sort_by=sort_by,
            sort_order=sort_order,
            skip=skip,
            limit=limit
        )
        
        promotion_codes = await billing_service.get_promotion_codes(db, query_params)
        
        billing_logger.info(
            f"Admin {current_user.id} retrieved {len(promotion_codes.items)} promotion codes "
            f"with filters: {promotion_codes.filters_applied}"
        )
        
        return promotion_codes
        
    except BillingException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail
        )
    except Exception as e:
        billing_logger.error(f"Error getting promotion codes: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get promotion codes"
        )




@billing_admin_router.delete("/promo-codes/bulk", response_model=schemas.PromotionCodeBulkDeleteResult, tags=["billing-admin"])
async def bulk_delete_promotion_codes(
    delete_request: schemas.PromotionCodeBulkDeleteRequest,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Bulk delete promotion codes with flexible targeting (Admin only).
    
    This endpoint provides comprehensive bulk deletion capabilities with support for:
    - **Direct Targeting**: Specific promotion code IDs or code strings
    - **Query-Based Targeting**: All the same filters as the GET endpoint
    - **Bulk Operations**: Delete multiple codes at once with safety controls
    - **Usage Protection**: Automatic skipping of codes with usage history
    - **Force Deletion**: Override protection for complete cleanup (dangerous)
    
    **Targeting Options:**
    - `promo_code_ids`: List of specific promotion code UUIDs
    - `codes`: List of specific promotion code strings
    - `is_active`: Filter by current active status
    - `credit_type`: Filter by credit type (workflows, web_searches, dollar_credits)
    - `search_text`: Search within code names or descriptions
    - `expires_after/expires_before`: Filter by expiration date ranges
    - `has_usage_limit`: Filter codes with/without usage limits
    - `delete_all`: Explicit flag to delete all codes (if no other filters)
    - `force_delete_used`: Allow deletion of codes with usage records (DANGEROUS)
    
    **Safety Features:**
    - **Default Protection**: Automatically skips codes with usage records
    - **Explicit Confirmation**: Requires `delete_all` flag for mass deletion
    - **Force Override**: `force_delete_used` flag for complete cleanup
    - **Detailed Reporting**: Shows deleted vs skipped codes with reasons
    - **Comprehensive Logging**: Full audit trail for compliance
    
    **⚠️ DANGER ZONE:**
    Setting `force_delete_used=true` will delete promotion codes that have been used,
    potentially breaking audit trails and billing history. Use with extreme caution
    and only when you're certain about the consequences.
    
    **Recommended Workflow:**
    1. First run with `force_delete_used=false` (default) to see what would be skipped
    2. Consider deactivating used codes instead of deleting them
    3. Only use `force_delete_used=true` if you absolutely need to purge everything
    
    Requires superuser permissions.
    
    Returns:
        PromotionCodeBulkDeleteResult with operation details including:
        - Number of codes deleted and skipped
        - Lists of deleted/skipped promotion code strings
        - Summary of applied targeting filters
    """
    try:
        result = await billing_service.bulk_delete_promotion_codes(
            db=db,
            delete_request=delete_request
        )
        
        billing_logger.warning(
            f"Admin {current_user.id} bulk deleted {result.deleted_count} promotion codes, "
            f"skipped {result.skipped_count} codes with usage records. "
            f"Filters: {result.filters_applied}"
        )
        
        return result
        
    except BillingException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail
        )
    except Exception as e:
        billing_logger.error(f"Error bulk deleting promotion codes: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to bulk delete promotion codes"
        )


@billing_admin_router.delete("/promo-codes/{promo_code_id}", response_model=schemas.PromotionCodeDeleteResult, tags=["billing-admin"])
async def delete_promotion_code(
    promo_code_id: uuid.UUID = Path(..., description="ID of the promotion code to delete"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Delete a promotion code by ID (Admin only).
    
    This endpoint safely deletes a promotion code with the following safeguards:
    - Verifies the promotion code exists
    - Prevents deletion if there are existing usage records to maintain audit trail
    - Provides detailed feedback about the deletion attempt
    
    **Important Notes:**
    - If a promotion code has been used, it cannot be deleted to preserve billing audit trails
    - Consider deactivating the code instead if it has usage history
    - This operation is irreversible
    
    **Safety Measures:**
    - Only unused promotion codes can be deleted
    - Deletion preserves referential integrity
    - Comprehensive logging for audit purposes
    
    Requires superuser permissions.
    
    Args:
        promo_code_id: UUID of the promotion code to delete
        
    Returns:
        PromotionCodeDeleteResult with success status and details
        
    Raises:
        - 404: If the promotion code doesn't exist
        - 409: If deletion is prevented due to existing usage records
        - 500: If there's an internal server error during deletion
    """
    try:
        result = await billing_service.delete_promotion_code(
            db=db,
            promo_code_id=promo_code_id
        )
        
        billing_logger.info(
            f"Admin {current_user.id} successfully deleted promotion code {promo_code_id} "
            f"(code: {result.code})"
        )
        
        return result
        
    except PromotionCodeNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Promotion code with ID {promo_code_id} not found"
        )
    except BillingException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail
        )
    except Exception as e:
        billing_logger.error(f"Error deleting promotion code {promo_code_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete promotion code"
        )


@billing_admin_router.patch("/promo-codes/deactivate", response_model=schemas.PromotionCodeDeactivateResult, tags=["billing-admin"])
async def deactivate_promotion_codes(
    deactivate_request: schemas.PromotionCodeDeactivateRequest,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Deactivate promotion codes with flexible targeting (Admin only).
    
    This endpoint provides comprehensive deactivation capabilities with support for:
    - **Direct Targeting**: Specific promotion code IDs or code strings
    - **Query-Based Targeting**: All the same filters as the GET endpoint
    - **Bulk Operations**: Deactivate multiple codes at once
    - **Safety Controls**: Explicit confirmation required for mass operations
    
    **Targeting Options:**
    - `promo_code_ids`: List of specific promotion code UUIDs
    - `codes`: List of specific promotion code strings
    - `is_active`: Filter by current active status
    - `credit_type`: Filter by credit type (workflows, web_searches, dollar_credits)
    - `search_text`: Search within code names or descriptions
    - `expires_after/expires_before`: Filter by expiration date ranges
    - `has_usage_limit`: Filter codes with/without usage limits
    - `deactivate_all`: Explicit flag to deactivate all codes (if no other filters)
    
    **Benefits of Deactivation over Deletion:**
    - Preserves complete audit trail and billing history
    - Safe operation with no risk of data loss
    - Can be reversed by reactivating codes
    - Maintains referential integrity
    
    **Use Cases:**
    - Expire seasonal or time-limited promotions
    - Disable compromised or misused codes
    - Clean up inactive promotional campaigns
    - Prepare for new promotion cycles
    
    Requires superuser permissions.
    
    Returns:
        PromotionCodeDeactivateResult with operation details including:
        - Number of codes deactivated
        - List of deactivated promotion code strings
        - Summary of applied targeting filters
    """
    try:
        result = await billing_service.deactivate_promotion_codes(
            db=db,
            deactivate_request=deactivate_request
        )
        
        billing_logger.info(
            f"Admin {current_user.id} deactivated {result.deactivated_count} promotion codes "
            f"with filters: {result.filters_applied}"
        )
        
        return result
        
    except BillingException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail
        )
    except Exception as e:
        billing_logger.error(f"Error deactivating promotion codes: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate promotion codes"
        )



### TODO ###
################################################
# --- Subscription Management --- #
################################################



# @billing_router.post("/subscribe", response_model=schemas.SubscriptionRead, tags=["billing-subscription"])
# async def create_subscription(
#     subscription_data: schemas.SubscriptionCreate,
#     active_org_id: uuid.UUID = Depends(get_active_org_id),
#     current_user: User = Depends(dependencies.RequireBillingManageActiveOrg),
#     db: AsyncSession = Depends(get_async_db_dependency),
#     billing_service: services.BillingService = Depends(dependencies.get_billing_service)
# ):
#     """
#     Create a new subscription for the active organization.
    
#     This endpoint handles the complete subscription creation process including
#     Stripe integration and initial credit allocation.
    
#     Requires `billing:manage` permission on the active organization.
#     """
#     try:
#         subscription = await billing_service.create_subscription(
#             db=db,
#             org_id=active_org_id,
#             subscription_data=subscription_data,
#             user=current_user
#         )
        
#         billing_logger.info(f"User {current_user.id} created subscription for org {active_org_id}: {subscription.id}")
#         return subscription
        
#     except SubscriptionPlanNotFoundException:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Subscription plan not found"
#         )
#     except InvalidSubscriptionStateException as e:
#         raise HTTPException(
#             status_code=status.HTTP_409_CONFLICT,
#             detail=str(e)
#         )
#     except StripeIntegrationException as e:
#         raise HTTPException(
#             status_code=status.HTTP_402_PAYMENT_REQUIRED,
#             detail=e.detail
#         )
#     except Exception as e:
#         billing_logger.error(f"Error creating subscription: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to create subscription"
#         )


@billing_router.get("/subscription", response_model=List[schemas.SubscriptionReadWithPlan], tags=["billing-subscription"])
async def get_current_subscription(
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireBillingReadActiveOrg),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get the current subscription for the active organization.
    
    Returns subscription details including plan information and current status.
    Requires `billing:read` permission on the active organization.
    """
    try:
        subscription = await billing_service.get_organization_subscription(
            db=db,
            org_id=active_org_id
        )
        if subscription:
            billing_logger.info(f"User {current_user.id} retrieved subscription for org {active_org_id}")
        return subscription
    except Exception as e:
        billing_logger.error(f"Error fetching subscription: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch subscription"
        )


# @billing_router.put("/subscription", response_model=schemas.SubscriptionRead, tags=["billing-subscription"])
# async def update_subscription(
#     subscription_update: schemas.SubscriptionUpdate,
#     active_org_id: uuid.UUID = Depends(get_active_org_id),
#     current_user: User = Depends(dependencies.RequireBillingManageActiveOrg),
#     db: AsyncSession = Depends(get_async_db_dependency),
#     billing_service: services.BillingService = Depends(dependencies.get_billing_service)
# ):
#     """
#     Update the current subscription for the active organization.
    
#     Supports plan changes, seat count updates, and cancellation scheduling.
#     Requires `billing:manage` permission on the active organization.
#     """
#     try:
#         subscription = await billing_service.update_subscription(
#             db=db,
#             org_id=active_org_id,
#             subscription_update=subscription_update
#         )
        
#         billing_logger.info(f"User {current_user.id} updated subscription for org {active_org_id}: {subscription.id}")
#         return subscription
        
#     except SubscriptionNotFoundException:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="No active subscription found"
#         )
#     except SubscriptionPlanNotFoundException:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Target subscription plan not found"
#         )
#     except StripeIntegrationException as e:
#         raise HTTPException(
#             status_code=status.HTTP_402_PAYMENT_REQUIRED,
#             detail=e.detail
#         )
#     except Exception as e:
#         billing_logger.error(f"Error updating subscription: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to update subscription"
#         )


# @billing_router.put("/subscription/seats", response_model=schemas.SubscriptionRead, tags=["billing-subscription"])
# async def update_subscription_seats(
#     seat_update: schemas.SubscriptionSeatUpdate,
#     active_org_id: uuid.UUID = Depends(get_active_org_id),
#     current_user: User = Depends(dependencies.RequireBillingManageActiveOrg),
#     db: AsyncSession = Depends(get_async_db_dependency),
#     billing_service: services.BillingService = Depends(dependencies.get_billing_service)
# ):
#     """
#     Update subscription seat count with proper handling of increases vs decreases.
    
#     **Important Seat Management Rules:**
#     - **Seat Increases**: Take effect immediately and generate a prorated invoice
#     - **Seat Decreases**: Only take effect at the next billing period (no immediate charges)
    
#     This endpoint ensures fair billing by:
#     - Charging immediately for additional seats when scaling up
#     - Allowing graceful scaling down without losing access until the period ends
    
#     Requires `billing:manage` permission on the active organization.
    
#     Raises:
#         - 404: If no active subscription exists
#         - 400: If requested seats exceed plan limits
#         - 402: If there's a payment issue with the seat increase
#     """
#     try:
#         subscription = await billing_service.update_subscription_seats(
#             db=db,
#             org_id=active_org_id,
#             seat_update=seat_update
#         )
        
#         action = "increased" if seat_update.seats_count > subscription.seats_count else "decreased"
#         billing_logger.info(
#             f"User {current_user.id} {action} subscription seats for org {active_org_id} "
#             f"to {seat_update.seats_count}"
#         )
        
#         return subscription
        
#     except SubscriptionNotFoundException:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="No active subscription found"
#         )
#     except InvalidSubscriptionStateException as e:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail=str(e)
#         )
#     except StripeIntegrationException as e:
#         raise HTTPException(
#             status_code=status.HTTP_402_PAYMENT_REQUIRED,
#             detail=e.detail
#         )
#     except Exception as e:
#         billing_logger.error(f"Error updating subscription seats: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to update subscription seats"
#         )


@billing_router.post("/checkout/subscription/session", response_model=schemas.CheckoutSessionResponse, tags=["billing-subscription"])
async def create_subscription_checkout_session(
    request: Request,
    plan_id: uuid.UUID,
    is_annual: bool = Query(False, description="Whether to use annual billing"),
    seats_count: int = Query(1, ge=1, description="Number of seats to purchase"),
    # success_url: Optional[str] = Query(None, description="Custom success URL"),
    # cancel_url: Optional[str] = Query(None, description="Custom cancel URL"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireBillingReadActiveOrg),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Create a Stripe Checkout session for subscription (returns JSON).
    
    This endpoint is for API clients that need the checkout URL programmatically.
    It returns the session details as JSON.
    
    Args:
        plan_id: ID of the subscription plan
        is_annual: Whether to use annual billing
        seats_count: Number of seats to purchase (default: 1)
        success_url: Custom success URL
        cancel_url: Custom cancel URL
    
    Requires `billing:read` permission on the active organization.
    """
    try:
        # Construct success and cancel URLs using the auth pattern
        base_url = _get_base_url(request, "/billing/checkout-result")
        
        # Default URLs if not provided
        # if not success_url:
            # Include session_id placeholder that Stripe will replace
        success_url = f"{base_url}?success=true&session_id={{CHECKOUT_SESSION_ID}}"
        
        # if not cancel_url:
        cancel_url = f"{base_url}?canceled=true"
        
        result = await billing_service.create_checkout_session(
            db=db,
            org_id=active_org_id,
            user=current_user,
            plan_id=plan_id,
            is_annual=is_annual,
            seats_count=seats_count,
            success_url=success_url,
            cancel_url=cancel_url
        )
        
        billing_logger.info(f"User {current_user.id} created subscription checkout session for org {active_org_id} with {seats_count} seats (API response)")
        return result
        
    except SubscriptionPlanNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription plan not found"
        )
    except SeatLimitExceededException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except BillingConfigurationException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except StripeIntegrationException as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=e.detail
        )
    except Exception as e:
        billing_logger.error(f"Error creating checkout session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )


# @billing_router.post("/checkout/credits")
# async def create_credit_purchase_checkout(
#     request: Request,
#     price_id: str = Query(..., description="Stripe price ID for the credit pack"),
#     success_url: Optional[str] = Query(None, description="Custom success URL"),
#     cancel_url: Optional[str] = Query(None, description="Custom cancel URL"),
#     active_org_id: uuid.UUID = Depends(get_active_org_id),
#     current_user: User = Depends(dependencies.RequireBillingReadActiveOrg),
#     db: AsyncSession = Depends(get_async_db_dependency),
#     billing_service: services.BillingService = Depends(dependencies.get_billing_service)
# ):
#     """
#     Create a Stripe Checkout session for credit purchase and redirect to Stripe.
    
#     This endpoint creates a checkout session for one-time credit purchases
#     using Stripe's hosted checkout page and immediately redirects the user.
    
#     Requires `billing:read` permission on the active organization.
#     """
#     try:
#         # Construct success and cancel URLs using the auth pattern
#         base_url = _get_base_url(request, "/billing/checkout-result")
        
#         # Default URLs if not provided
#         if not success_url:
#             # Include session_id placeholder that Stripe will replace
#             success_url = f"{base_url}?success=true&session_id={{CHECKOUT_SESSION_ID}}"
        
#         if not cancel_url:
#             cancel_url = f"{base_url}?canceled=true"
        
#         result = await billing_service.create_checkout_session(
#             db=db,
#             org_id=active_org_id,
#             user=current_user,
#             price_id=price_id,
#             success_url=success_url,
#             cancel_url=cancel_url
#         )
        
#         billing_logger.info(f"User {current_user.id} created credit purchase checkout session for org {active_org_id}")
        
#         # Redirect to Stripe checkout page
#         return RedirectResponse(url=result["checkout_url"], status_code=303)
        
#     except StripeIntegrationException as e:
#         raise HTTPException(
#             status_code=status.HTTP_402_PAYMENT_REQUIRED,
#             detail=e.detail
#         )
#     except Exception as e:
#         billing_logger.error(f"Error creating checkout session: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to create checkout session"
#         )


# @billing_router.post("/checkout/credits/session", response_model=schemas.CheckoutSessionResponse)
# async def create_credit_purchase_checkout_session(
#     request: Request,
#     price_id: str = Query(..., description="Stripe price ID for the credit pack"),
#     success_url: Optional[str] = Query(None, description="Custom success URL"),
#     cancel_url: Optional[str] = Query(None, description="Custom cancel URL"),
#     active_org_id: uuid.UUID = Depends(get_active_org_id),
#     current_user: User = Depends(dependencies.RequireBillingReadActiveOrg),
#     db: AsyncSession = Depends(get_async_db_dependency),
#     billing_service: services.BillingService = Depends(dependencies.get_billing_service)
# ):
#     """
#     Create a Stripe Checkout session for credit purchase (returns JSON).
    
#     This endpoint is for API clients that need the checkout URL programmatically.
#     It returns the session details as JSON.
    
#     Requires `billing:read` permission on the active organization.
#     """
#     try:
#         # Construct success and cancel URLs using the auth pattern
#         base_url = _get_base_url(request, "/billing/checkout-result")
        
#         # Default URLs if not provided
#         if not success_url:
#             # Include session_id placeholder that Stripe will replace
#             success_url = f"{base_url}?success=true&session_id={{CHECKOUT_SESSION_ID}}"
        
#         if not cancel_url:
#             cancel_url = f"{base_url}?canceled=true"
        
#         result = await billing_service.create_checkout_session(
#             db=db,
#             org_id=active_org_id,
#             user=current_user,
#             price_id=price_id,
#             success_url=success_url,
#             cancel_url=cancel_url
#         )
        
#         billing_logger.info(f"User {current_user.id} created credit purchase checkout session for org {active_org_id} (API response)")
#         return result
        
#     except StripeIntegrationException as e:
#         raise HTTPException(
#             status_code=status.HTTP_402_PAYMENT_REQUIRED,
#             detail=e.detail
#         )
#     except Exception as e:
#         billing_logger.error(f"Error creating checkout session: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to create checkout session"
#         )

@billing_router.post("/portal", response_model=schemas.CustomerPortalResponse, tags=["billing-subscription"])
async def create_customer_portal_session(
    # return_url: str,
    request: Request,
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireBillingManageActiveOrg),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Create a Stripe Customer Portal session.
    
    This endpoint creates a portal session that allows customers to manage
    their subscription, update payment methods, and view invoices.
    Requires `billing:manage` permission on the active organization.
    """
    return_url = _get_base_url(request, "/billing/checkout-result")
    try:
        result = await billing_service.create_customer_portal_session(
            db=db,
            org_id=active_org_id,
            return_url=return_url
        )
        
        billing_logger.info(f"User {current_user.id} created customer portal session for org {active_org_id}")
        return result
        
    except SubscriptionNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found"
        )
    except StripeIntegrationException as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=e.detail
        )
    except Exception as e:
        billing_logger.error(f"Error creating portal session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create portal session"
        )




# --- Checkout Result Endpoints --- #

@billing_router.get("/checkout-result", response_model=schemas.CheckoutResultResponse)
async def handle_checkout_result(
    request: Request,
    success: Optional[bool] = Query(None, description="Whether the checkout was successful"),
    canceled: Optional[bool] = Query(None, description="Whether the checkout was canceled"),
    session_id: Optional[str] = Query(None, description="Stripe checkout session ID"),
    redirect: Optional[bool] = Query(False, description="Whether to redirect to frontend after processing"),
    # current_user: User = Depends(get_current_active_verified_user),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Handle Stripe Checkout result (success or cancel).
    
    This endpoint is called after a user completes or cancels a Stripe Checkout session.
    For successful checkouts, it retrieves the session details from Stripe.
    
    Query Parameters:
        - success=true&session_id={CHECKOUT_SESSION_ID}: For successful checkouts
        - canceled=true: For canceled checkouts
        - redirect=true: To redirect to frontend after processing (optional)
    """
    try:
        # Handle canceled checkout
        if canceled:
            billing_logger.info(f"User canceled checkout")
            
            if redirect:
                # Redirect to frontend billing page with canceled status
                frontend_url = f"{settings.REDIRECT_BASE_URL}/billing?canceled=true"
                return RedirectResponse(url=frontend_url)
            
            return schemas.CheckoutResultResponse(
                success=False,
                message="Checkout was canceled",
                session_id=None
            )
        
        # Handle successful checkout
        if success and session_id:
            # Retrieve session details from Stripe
            import stripe
            stripe.api_key = settings.STRIPE_SECRET_KEY
            
            try:
                session = stripe.checkout.Session.retrieve(session_id)
                
                # Log successful checkout
                billing_logger.info(
                    f"User completed checkout session {session_id} "
                    f"(mode: {session.mode}, status: {session.status})"
                )
                
                if redirect:
                    # Redirect to frontend billing page with success status
                    frontend_url = f"{settings.REDIRECT_BASE_URL}/billing?success=true&session_id={session_id}"
                    return RedirectResponse(url=frontend_url)
                
                # Return success response with session details
                return schemas.CheckoutResultResponse(
                    success=True,
                    message="Checkout completed successfully",
                    session_id=session_id,
                    session_status=session.status,
                    customer_email=session.customer_email,
                    payment_status=session.payment_status
                )
                
            except stripe.StripeError as e:
                billing_logger.error(f"Error retrieving checkout session {session_id}: {e}")
                
                if redirect:
                    # Redirect to frontend with error status
                    frontend_url = f"{settings.REDIRECT_BASE_URL}/billing?error=invalid_session"
                    return RedirectResponse(url=frontend_url)
                
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired checkout session"
                )
        
        # Invalid request - neither success nor canceled
        if redirect:
            # Redirect to frontend billing page without status
            frontend_url = f"{settings.REDIRECT_BASE_URL}/billing"
            return RedirectResponse(url=frontend_url)
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid checkout result parameters"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        billing_logger.error(f"Error handling checkout result: {e}", exc_info=True)
        
        if redirect:
            # Redirect to frontend with error status
            frontend_url = f"{settings.REDIRECT_BASE_URL}/billing?error=internal"
            return RedirectResponse(url=frontend_url)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process checkout result"
        )


# # --- Error Handlers --- #

# @router.exception_handler(BillingException)
# async def billing_exception_handler(request: Request, exc: BillingException):
#     """
#     Global exception handler for billing-related exceptions.
    
#     Provides consistent error responses for all billing exceptions.
#     """
#     billing_logger.warning(f"Billing exception: {exc.detail}")
#     return HTTPException(
#         status_code=exc.status_code,
#         detail=exc.detail
#     )



# Set router prefixes (these will be set when including in main app)
# router.prefix = "/billing"
# admin_router.prefix = "/billing/admin"
# webhook_router.prefix = "/billing/webhooks" 

# --- Admin Endpoints (Superuser only) --- #

@billing_admin_router.post("/stripe-events/query", response_model=schemas.PaginatedStripeEvents, tags=["billing-admin"])
async def query_stripe_events(
    query_params: schemas.StripeEventQuery,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Query Stripe events with comprehensive filtering and sorting (Superuser only).
    
    This endpoint provides extensive filtering capabilities for admin users
    to analyze Stripe events across various dimensions including:
    
    - Event types and processing status
    - Organization, user, and plan filtering
    - Date range filtering (both event timestamp and created timestamp)
    - Text search within event data
    - Flexible sorting and pagination
    
    Requires superuser privileges.
    """
    try:
        # Access the stripe_event_dao through the billing service
        stripe_event_dao = billing_service.stripe_event_dao
        
        result = await stripe_event_dao.query_events(
            db=db,
            query_params=query_params
        )
        
        billing_logger.info(
            f"Superuser {current_user.id} queried Stripe events: {len(result.items)} results, "
            f"{result.total} total, filters: {list(result.filters_applied.keys())}"
        )
        
        return result
        
    except Exception as e:
        billing_logger.error(f"Error querying Stripe events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query Stripe events"
        )


@billing_admin_router.post("/stripe-events/statistics", response_model=schemas.StripeEventStats, tags=["billing-admin"])
async def get_stripe_event_statistics(
    date_from: Optional[datetime] = Query(None, description="Start date for analysis"),
    date_to: Optional[datetime] = Query(None, description="End date for analysis"),
    org_id: Optional[uuid.UUID] = Query(None, description="Optional organization filter"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get comprehensive Stripe event statistics (Superuser only).
    
    Returns detailed analytics about Stripe events including:
    - Total events and breakdown by type
    - Daily event distribution
    - Processing success rates
    - Live mode vs test mode events
    - Unique organizations and users
    - Time range analysis
    
    Requires superuser privileges.
    """
    try:
        # Access the stripe_event_dao through the billing service
        stripe_event_dao = billing_service.stripe_event_dao
        
        stats = await stripe_event_dao.get_event_statistics(
            db=db,
            date_from=date_from,
            date_to=date_to,
            org_id=org_id
        )
        
        billing_logger.info(
            f"Superuser {current_user.id} retrieved Stripe event statistics: "
            f"{stats.total_events} events analyzed"
        )
        
        return stats
        
    except Exception as e:
        billing_logger.error(f"Error getting Stripe event statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get Stripe event statistics"
        )


@billing_admin_router.post("/stripe-events/failed", response_model=List[schemas.StripeEventRead], tags=["billing-admin"])
async def get_failed_stripe_events(
    hours_back: int = Query(24, ge=1, le=720, description="How many hours back to look (max 7 days)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get recent failed Stripe events for debugging (Superuser only).
    
    Returns Stripe events that failed to process, useful for debugging
    webhook processing issues and system health monitoring.
    
    Requires superuser privileges.
    """
    try:
        # Access the stripe_event_dao through the billing service
        stripe_event_dao = billing_service.stripe_event_dao
        
        failed_events = await stripe_event_dao.get_failed_events(
            db=db,
            hours_back=hours_back,
            limit=limit
        )
        
        # Convert to read schemas
        event_reads = [schemas.StripeEventRead.model_validate(event) for event in failed_events]
        
        billing_logger.info(
            f"Superuser {current_user.id} retrieved {len(failed_events)} failed Stripe events "
            f"from last {hours_back} hours"
        )
        
        return event_reads
        
    except Exception as e:
        billing_logger.error(f"Error getting failed Stripe events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get failed Stripe events"
        )


@billing_admin_router.post("/stripe-events/organization/{org_id}", response_model=List[schemas.StripeEventRead], tags=["billing-admin"])
async def get_stripe_events_by_organization(
    org_id: uuid.UUID = Path(..., description="Organization ID"),
    event_types: Optional[List[str]] = Query(None, description="Filter by event types"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return"),
    skip: int = Query(0, ge=0, description="Number of events to skip"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get Stripe events for a specific organization (Superuser only).
    
    Returns all Stripe events associated with a particular organization,
    useful for debugging organization-specific billing issues.
    
    Requires superuser privileges.
    """
    try:
        # Access the stripe_event_dao through the billing service
        stripe_event_dao = billing_service.stripe_event_dao
        
        events = await stripe_event_dao.get_events_by_org(
            db=db,
            org_id=org_id,
            event_types=event_types,
            limit=limit,
            skip=skip
        )
        
        # Convert to read schemas
        event_reads = [schemas.StripeEventRead.model_validate(event) for event in events]
        
        billing_logger.info(
            f"Superuser {current_user.id} retrieved {len(events)} Stripe events "
            f"for organization {org_id}"
        )
        
        return event_reads
        
    except Exception as e:
        billing_logger.error(f"Error getting Stripe events by organization: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get Stripe events for organization"
        )


@billing_admin_router.post("/stripe-events/{event_id}", response_model=schemas.StripeEventRead, tags=["billing-admin"])
async def get_stripe_event_by_id(
    event_id: str = Path(..., description="Stripe Event ID"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Get a specific Stripe event by Stripe Event ID (Superuser only).
    
    Returns detailed information about a specific Stripe event,
    useful for debugging specific webhook processing issues.
    
    Requires superuser privileges.
    """
    try:
        # Access the stripe_event_dao through the billing service
        stripe_event_dao = billing_service.stripe_event_dao
        
        event = await stripe_event_dao.get_by_stripe_event_id(
            db=db,
            stripe_event_id=event_id
        )
        
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stripe event {event_id} not found"
            )
        
        billing_logger.info(
            f"Superuser {current_user.id} retrieved Stripe event {event_id}"
        )
        
        return schemas.StripeEventRead.model_validate(event)
        
    except HTTPException:
        raise
    except Exception as e:
        billing_logger.error(f"Error getting Stripe event by ID: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get Stripe event"
        )


@billing_admin_router.delete("/stripe-events/bulk", response_model=schemas.StripeEventDeleteResult, tags=["billing-admin"])
async def delete_stripe_events_by_query(
    query_params: schemas.StripeEventQuery,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Delete Stripe events with comprehensive filtering (Superuser only).
    
    This endpoint performs bulk deletion of Stripe events based on the same
    filtering capabilities as the query endpoint. Use with caution as this
    operation is irreversible.
    
    Supports all the same filters as the query endpoint:
    - Event types and processing status
    - Organization, user, and plan filtering  
    - Date range filtering (both event timestamp and created timestamp)
    - Text search within event data
    
    **WARNING**: This operation permanently deletes audit data and cannot be undone.
    
    Requires superuser privileges.
    """
    try:
        # Access the stripe_event_dao through the billing service
        stripe_event_dao = billing_service.stripe_event_dao
        
        # Extract filters for response
        filters_applied = {}
        if query_params.event_types:
            filters_applied["event_types"] = query_params.event_types
        if query_params.org_id:
            filters_applied["org_id"] = str(query_params.org_id)
        if query_params.user_id:
            filters_applied["user_id"] = str(query_params.user_id)
        if query_params.plan_id:
            filters_applied["plan_id"] = str(query_params.plan_id)
        if query_params.livemode is not None:
            filters_applied["livemode"] = query_params.livemode
        if query_params.processed_successfully is not None:
            filters_applied["processed_successfully"] = query_params.processed_successfully
        if query_params.event_timestamp_from:
            filters_applied["event_timestamp_from"] = query_params.event_timestamp_from
        if query_params.event_timestamp_to:
            filters_applied["event_timestamp_to"] = query_params.event_timestamp_to
        if query_params.search_text:
            filters_applied["search_text"] = query_params.search_text
        
        # Perform bulk deletion
        deleted_count = await stripe_event_dao.delete_events_by_query(
            db=db,
            query_params=query_params,
            commit=True
        )
        
        billing_logger.warning(
            f"Superuser {current_user.id} bulk deleted {deleted_count} Stripe events "
            f"with filters: {list(filters_applied.keys())}"
        )
        
        return schemas.StripeEventDeleteResult(
            success=True,
            deleted_count=deleted_count,
            filters_applied=filters_applied,
            deletion_type="query_based"
        )
        
    except Exception as e:
        billing_logger.error(f"Error bulk deleting Stripe events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete Stripe events"
        )


@billing_admin_router.delete("/stripe-events/time-window", response_model=schemas.StripeEventDeleteResult, tags=["billing-admin"])
async def delete_stripe_events_by_time_window(
    deletion_params: schemas.StripeEventTimeWindowDelete,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    billing_service: services.BillingService = Depends(dependencies.get_billing_service)
):
    """
    Delete Stripe events within a time window (Superuser only).
    
    This endpoint deletes Stripe events older than a specified time period.
    Useful for regular cleanup and maintenance of audit logs.
    
    Time window options:
    - `hours_back`: Delete events from last N hours (takes precedence)
    - `days_back`: Delete events from last N days
    
    Optional filters:
    - `org_id`: Only delete events for specific organization
    - `event_types`: Only delete specific event types
    - `only_failed`: Only delete events that failed processing
    
    **WARNING**: This operation permanently deletes audit data and cannot be undone.
    
    Requires superuser privileges.
    """
    try:
        # Access the stripe_event_dao through the billing service
        stripe_event_dao = billing_service.stripe_event_dao
        
        # Extract filters for response
        filters_applied = {}
        if deletion_params.org_id:
            filters_applied["org_id"] = str(deletion_params.org_id)
        if deletion_params.event_types:
            filters_applied["event_types"] = deletion_params.event_types
        if deletion_params.only_failed:
            filters_applied["only_failed"] = deletion_params.only_failed
        
        # Add time window to filters
        if deletion_params.hours_back:
            filters_applied["hours_back"] = deletion_params.hours_back
        elif deletion_params.days_back:
            filters_applied["days_back"] = deletion_params.days_back
        
        # Perform time-window deletion
        deleted_count = await stripe_event_dao.delete_events_by_time_window(
            db=db,
            hours_back=deletion_params.hours_back,
            days_back=deletion_params.days_back,
            org_id=deletion_params.org_id,
            event_types=deletion_params.event_types,
            only_failed=deletion_params.only_failed,
            commit=True
        )
        
        billing_logger.warning(
            f"Superuser {current_user.id} time-window deleted {deleted_count} Stripe events "
            f"with filters: {list(filters_applied.keys())}"
        )
        
        return schemas.StripeEventDeleteResult(
            success=True,
            deleted_count=deleted_count,
            filters_applied=filters_applied,
            deletion_type="time_window"
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        billing_logger.error(f"Error time-window deleting Stripe events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete Stripe events"
        ) 