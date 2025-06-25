"""
Billing schemas for KiwiQ system.

This module defines Pydantic schemas for request/response validation
in the billing API. It follows KiwiQ's established patterns for schema
definition and validation.
"""
from enum import Enum
import uuid
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Union
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, ConfigDict

from kiwi_app.auth.utils import datetime_now_utc

from kiwi_app.billing.models import (
    CreditType, 
    SubscriptionStatus, 
    CreditSourceType, 
    PaymentStatus
)

# --- Base Schemas --- #

class BillingBaseSchema(BaseModel):
    """Base schema for billing-related models."""
    model_config = ConfigDict(from_attributes=True)

# --- Subscription Plan Schemas --- #

class SubscriptionPlanBase(BillingBaseSchema):
    """Base schema for subscription plans."""
    name: str = Field(..., description="Plan name")
    description: Optional[str] = Field(None, description="Plan description")
    max_seats: int = Field(1, ge=1, description="Maximum number of users allowed")
    monthly_credits: Dict[str, float] = Field(
        default={"workflows": 100.0, "web_searches": 500.0, "dollar_credits": 25.0},
        description="Monthly credit allocations by type"
    )
    monthly_price: float = Field(..., ge=0, description="Monthly price in dollars")
    annual_price: float = Field(..., ge=0, description="Annual price in dollars")
    features: Dict[str, Any] = Field(default={}, description="Plan features and capabilities")
    is_trial_eligible: bool = Field(True, description="Whether this plan supports trial periods")
    trial_days: int = Field(14, ge=0, description="Number of trial days for this plan")

class SubscriptionPlanCreate(SubscriptionPlanBase):
    """Schema for creating a new subscription plan."""
    stripe_product_id: Optional[str] = Field(None, description="Stripe Product ID (auto-generated if not provided)")
    is_active: bool = Field(True, description="Whether this plan is available for new subscriptions")
    
    @field_validator('monthly_credits')
    def validate_monthly_credits(cls, v):
        """Validate that monthly_credits contains valid credit types."""
        valid_types = {ct.value for ct in CreditType}
        for credit_type in v.keys():
            if credit_type not in valid_types:
                raise ValueError(f"Invalid credit type: {credit_type}. Valid types: {valid_types}")
        return v

class SubscriptionPlanUpdate(BillingBaseSchema):
    """Schema for updating a subscription plan."""
    name: Optional[str] = None
    description: Optional[str] = None
    stripe_product_id: Optional[str] = None
    stripe_price_id_monthly: Optional[str] = None
    stripe_price_id_annual: Optional[str] = None
    max_seats: Optional[int] = Field(None, ge=1)
    monthly_credits: Optional[Dict[str, float]] = None
    monthly_price: Optional[float] = Field(None, ge=0)
    annual_price: Optional[float] = Field(None, ge=0)
    features: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_trial_eligible: Optional[bool] = None
    trial_days: Optional[int] = Field(None, ge=0)

class SubscriptionPlanRead(SubscriptionPlanBase):
    """Schema for reading subscription plan data."""
    id: uuid.UUID
    stripe_product_id: str
    stripe_price_id_monthly: Optional[str]
    stripe_price_id_annual: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

# --- Subscription Schemas --- #

class SubscriptionBase(BillingBaseSchema):
    """Base schema for subscriptions."""
    seats_count: int = Field(1, ge=1, description="Number of active seats")
    is_annual: bool = Field(False, description="Annual vs monthly billing")

class SubscriptionCreate(SubscriptionBase):
    """Schema for creating a new subscription."""
    plan_id: uuid.UUID = Field(..., description="ID of the subscription plan")
    payment_method_id: Optional[str] = Field(None, description="Stripe Payment Method ID")
    trial_days: Optional[int] = Field(None, ge=0, description="Override trial days for this subscription")

class SubscriptionUpdate(BillingBaseSchema):
    """Schema for updating a subscription."""
    subscription_id: Optional[uuid.UUID] = Field(None, description="ID of the subscription to update")
    plan_id: Optional[uuid.UUID] = None
    seats_count: Optional[int] = Field(None, ge=1)
    cancel_at_period_end: Optional[bool] = None

class SubscriptionSeatUpdate(BillingBaseSchema):
    """
    Schema for updating subscription seats.
    
    Seat increases take effect immediately with prorated charges.
    Seat decreases only take effect at the next billing period.
    """
    seats_count: int = Field(..., ge=1, description="New number of seats")
    effective_immediately: bool = Field(
        default=True, 
        description="For increases only. Decreases always apply at period end."
    )
    
    @field_validator('seats_count')
    def validate_seats(cls, v):
        """Validate seat count is positive."""
        if v < 1:
            raise ValueError("Seat count must be at least 1")
        return v

class SubscriptionRead(SubscriptionBase):
    """Schema for reading subscription data."""
    id: uuid.UUID
    org_id: uuid.UUID
    plan_id: uuid.UUID
    stripe_subscription_id: str
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    trial_start: Optional[datetime]
    trial_end: Optional[datetime]
    is_trial_active: bool
    canceled_at: Optional[datetime]
    cancel_at_period_end: bool
    next_billing_date: Optional[date]
    created_at: datetime
    updated_at: datetime

class SubscriptionReadWithPlan(SubscriptionRead):
    """Schema for reading subscription data with plan details."""
    plan: SubscriptionPlanRead

# --- Credit Schemas --- #

class CreditBalance(BillingBaseSchema):
    """Credit balance information for an organization."""
    credit_type: CreditType
    credits_balance: float = Field(description="Current available credits")
    credits_granted: float = Field(description="Total credits granted")
    credits_consumed: float = Field(description="Total credits consumed")
    is_overage: bool = Field(default=False, description="Whether consumption exceeds granted credits")
    overage_amount: float = Field(default=0, description="Amount of overage credits used")

class OrganizationCreditsRead(BillingBaseSchema):
    """Schema for reading organization credit data."""
    id: uuid.UUID
    org_id: uuid.UUID
    credit_type: CreditType
    credits_balance: float
    credits_consumed: float
    credits_granted: float
    source_type: CreditSourceType
    source_id: Optional[str]
    source_metadata: Dict[str, Any]
    expires_at: Optional[datetime]
    is_expired: bool
    period_start: datetime
    period_end: datetime
    created_at: datetime
    updated_at: datetime

# --- Usage Event Schemas --- #

class CreditConsumptionRequest(BillingBaseSchema):
    """Schema for requesting credit consumption."""
    credit_type: CreditType = Field(..., description="Type of credits to consume")
    credits_consumed: float = Field(..., description="Number of credits to consume (can be 0 or negative for edge cases)")
    event_type: str = Field(..., description="Type of usage event")
    metadata: Dict[str, Any] = Field(default={}, description="Event-specific metadata")

class CreditConsumptionResult(BillingBaseSchema):
    """Result of credit consumption operation."""
    success: bool
    credit_type: CreditType = Field(..., description="Type of credits consumed (may differ from requested if fallback occurred)")
    credits_consumed: float = Field(..., description="Number of credits consumed in the original unit")
    remaining_balance: float
    is_overage: bool = Field(default=False)
    grace_credits_used: float = Field(default=0)
    warning: Optional[str] = Field(default=None)
    dollar_credit_fallback: bool = Field(default=False, description="Whether dollar credit fallback was used")
    consumed_in_dollar_credits: float = Field(default=0, description="Amount of dollar credits consumed if fallback occurred")

class UsageEventRead(BillingBaseSchema):
    """Schema for reading usage event data."""
    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID
    event_type: str
    credit_type: CreditType
    credits_consumed: float
    usage_metadata: Dict[str, Any]
    is_overage: bool
    grace_credits_used: float = Field(default=0, description="Amount of grace credits used")
    cost: Optional[float] = Field(default=None, description="Cost in dollars if applicable")
    created_at: datetime

# --- Credit Purchase Schemas --- #

class CreditPurchaseRequest(BillingBaseSchema):
    """Schema for requesting credit purchase."""
    credit_type: CreditType = Field(..., description="Type of credits to purchase")
    credits_amount: float = Field(..., gt=0, description="Number of credits to purchase")
    payment_method_id: str = Field(..., description="Stripe Payment Method ID")

class FlexibleDollarCreditPurchaseRequest(BillingBaseSchema):
    """
    Schema for requesting flexible dollar credit purchase.
    
    Allows users to specify any dollar amount (with minimum) to purchase dollar credits.
    The actual credit amount is calculated based on the dollar amount and pricing ratio.
    """
    dollar_amount: int = Field(
        ..., 
        gt=0, 
        description="Dollar amount to spend on credits (minimum $5)"
    )
    
    @field_validator('dollar_amount')
    def validate_minimum_amount(cls, v):
        """Validate that the dollar amount meets the minimum requirement."""
        from kiwi_app.settings import settings
        if v < settings.MINIMUM_DOLLAR_CREDITS_PURCHASE:
            raise ValueError(
                f"Minimum purchase amount is ${settings.MINIMUM_DOLLAR_CREDITS_PURCHASE:.2f}"
            )
        return v

class CreditPurchaseRead(BillingBaseSchema):
    """Schema for reading credit purchase data."""
    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID
    stripe_checkout_id: str
    credit_type: CreditType
    credits_amount: float
    amount_paid: float
    currency: str
    status: PaymentStatus
    receipt_url: Optional[str] = Field(None, description="Stripe receipt URL")
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

# --- Promotion Code Schemas --- #

class PromotionCodeBase(BillingBaseSchema):
    """Base schema for promotion codes."""
    code: str = Field(..., description="Promotion code")
    description: Optional[str] = Field(None, description="Code description")
    credit_type: CreditType = Field(..., description="Type of credits granted")
    credits_amount: float = Field(..., gt=0, description="Number of credits granted per use")
    max_uses: Optional[int] = Field(None, ge=1, description="Maximum total uses")
    max_uses_per_org: int = Field(1, ge=1, description="Maximum uses per organization")
    expires_at: Optional[datetime] = Field(None, description="Code expiration date")
    is_active: bool = Field(True, description="Whether the promotion code is active")
    allowed_org_ids: Optional[List[str]] = Field(None, description="Restricted organization IDs")
    granted_credits_expire_days: Optional[int] = Field(None, ge=1, description="Days until granted credits expire")

class PromotionCodeCreate(PromotionCodeBase):
    """Schema for creating a promotion code."""
    pass

class PromotionCodeUpdate(BillingBaseSchema):
    """Schema for updating a promotion code."""
    description: Optional[str] = None
    max_uses: Optional[int] = Field(None, ge=1)
    max_uses_per_org: Optional[int] = Field(None, ge=1)
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None
    allowed_org_ids: Optional[List[str]] = None
    granted_credits_expire_days: Optional[int] = Field(None, ge=1)

class PromotionCodeRead(PromotionCodeBase):
    """Schema for reading promotion code data."""
    id: uuid.UUID
    uses_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

class PromotionCodeApply(BillingBaseSchema):
    """Schema for applying a promotion code."""
    code: str = Field(..., description="Promotion code to apply")

class PromotionCodeApplyResult(BillingBaseSchema):
    """Schema for promotion code application result."""
    success: bool = Field(..., description="Whether application was successful")
    credits_applied: float = Field(..., ge=0, description="Number of credits granted")
    credit_type: CreditType = Field(..., description="Type of credits granted")
    message: str = Field(..., description="Result message")

class PromotionCodeDeleteResult(BillingBaseSchema):
    """Schema for promotion code deletion result."""
    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Result message")
    code: str = Field(..., description="The promotion code that was deleted")
    promo_code_id: uuid.UUID = Field(..., description="ID of the deleted promotion code")

class PromotionCodeDeactivateRequest(BillingBaseSchema):
    """Schema for deactivating promotion codes with query support."""
    # Direct targeting
    promo_code_ids: Optional[List[uuid.UUID]] = Field(None, description="Specific promotion code IDs to deactivate")
    codes: Optional[List[str]] = Field(None, description="Specific promotion code strings to deactivate")
    
    # Query-based targeting (same as PromotionCodeQuery but without pagination)
    is_active: Optional[bool] = Field(None, description="Filter by active status")
    credit_type: Optional[CreditType] = Field(None, description="Filter by credit type")
    search_text: Optional[str] = Field(None, description="Search in code or description")
    expires_after: Optional[datetime] = Field(None, description="Filter codes that expire after this date")
    expires_before: Optional[datetime] = Field(None, description="Filter codes that expire before this date")
    has_usage_limit: Optional[bool] = Field(None, description="Filter codes with/without usage limits")
    
    # Safety flags
    deactivate_all: bool = Field(False, description="Explicitly confirm deactivating all codes if no filters provided")

class PromotionCodeDeactivateResult(BillingBaseSchema):
    """Schema for promotion code deactivation result."""
    success: bool = Field(..., description="Whether deactivation was successful")
    message: str = Field(..., description="Result message")
    deactivated_count: int = Field(..., description="Number of promotion codes deactivated")
    deactivated_codes: List[str] = Field(..., description="List of promotion code strings that were deactivated")
    filters_applied: Dict[str, Any] = Field(description="Summary of applied filters")

class PromotionCodeBulkDeleteRequest(BillingBaseSchema):
    """Schema for bulk deleting promotion codes with query support."""
    # Direct targeting
    promo_code_ids: Optional[List[uuid.UUID]] = Field(None, description="Specific promotion code IDs to delete")
    codes: Optional[List[str]] = Field(None, description="Specific promotion code strings to delete")
    
    # Query-based targeting (same as PromotionCodeQuery but without pagination)
    is_active: Optional[bool] = Field(None, description="Filter by active status")
    credit_type: Optional[CreditType] = Field(None, description="Filter by credit type")
    search_text: Optional[str] = Field(None, description="Search in code or description")
    expires_after: Optional[datetime] = Field(None, description="Filter codes that expire after this date")
    expires_before: Optional[datetime] = Field(None, description="Filter codes that expire before this date")
    has_usage_limit: Optional[bool] = Field(None, description="Filter codes with/without usage limits")
    
    # Safety flags
    delete_all: bool = Field(False, description="Explicitly confirm deleting all codes if no filters provided")
    force_delete_used: bool = Field(False, description="Allow deletion of codes with usage records (dangerous)")

class PromotionCodeBulkDeleteResult(BillingBaseSchema):
    """Schema for bulk promotion code deletion result."""
    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Result message")
    deleted_count: int = Field(..., description="Number of promotion codes deleted")
    skipped_count: int = Field(..., description="Number of promotion codes skipped due to usage records")
    deleted_codes: List[str] = Field(..., description="List of promotion code strings that were deleted")
    skipped_codes: List[str] = Field(..., description="List of promotion code strings that were skipped")
    filters_applied: Dict[str, Any] = Field(description="Summary of applied filters")

# --- Usage Analytics Schemas --- #

class UsageSummary(BillingBaseSchema):
    """Schema for usage summary data."""
    org_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    credit_balances: List[CreditBalance]
    total_events: int
    events_by_type: Dict[str, int]
    overage_events: int

class UsageAnalytics(BillingBaseSchema):
    """Schema for detailed usage analytics."""
    org_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    daily_usage: List[Dict[str, Any]]
    user_usage: List[Dict[str, Any]]
    credit_consumption_trends: Dict[str, List[Dict[str, Any]]]

# --- Billing Dashboard Schemas --- #

class BillingDashboard(BillingBaseSchema):
    """Schema for billing dashboard data."""
    org_id: uuid.UUID
    subscriptions: List[SubscriptionReadWithPlan]
    credit_balances: List[CreditBalance]
    recent_usage: List[UsageEventRead]
    recent_purchases: List[CreditPurchaseRead]
    upcoming_renewals: List[datetime]
    overage_warnings: List[str]

# --- Webhook Schemas --- #

class StripeEventRead(BillingBaseSchema):
    """Schema for reading Stripe event audit data."""
    id: uuid.UUID
    stripe_event_id: str
    event_type: str
    org_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None
    plan_id: Optional[uuid.UUID] = None
    event_timestamp: Optional[datetime] = None
    event_data: Dict[str, Any]
    livemode: bool
    api_version: Optional[str] = None
    processed_successfully: bool
    processing_error: Optional[str] = None
    created_at: datetime

class StripeEventCreate(BillingBaseSchema):
    """Schema for creating Stripe event audit records."""
    stripe_event_id: str = Field(..., description="Stripe Event ID")
    event_type: str = Field(..., description="Stripe event type")
    org_id: Optional[uuid.UUID] = Field(None, description="Organization ID from event metadata")
    user_id: Optional[uuid.UUID] = Field(None, description="User ID from event metadata")
    plan_id: Optional[uuid.UUID] = Field(None, description="Plan ID from event metadata")
    event_timestamp: Optional[datetime] = Field(None, description="Timestamp from Stripe event")
    event_data: Dict[str, Any] = Field(..., description="Complete Stripe event data")
    livemode: bool = Field(True, description="Whether event is from live mode")
    api_version: Optional[str] = Field(None, description="Stripe API version")
    processed_successfully: bool = Field(True, description="Processing success status")
    processing_error: Optional[str] = Field(None, description="Processing error message")


class StripeEventSortBy(str, Enum):
    """Enum for Stripe event sorting fields."""
    CREATED_AT = "created_at"
    EVENT_TIMESTAMP = "event_timestamp"
    EVENT_TYPE = "event_type"
    STRIPE_EVENT_ID = "stripe_event_id"


class SortOrder(str, Enum):
    """Enum for sort order options."""
    ASC = "asc"
    DESC = "desc"


class StripeEventQuery(BillingBaseSchema):
    """Schema for querying Stripe events with extensive filtering."""
    # Filtering options
    event_types: Optional[List[str]] = Field(None, description="Filter by event types")
    org_id: Optional[uuid.UUID] = Field(None, description="Filter by organization ID")
    user_id: Optional[uuid.UUID] = Field(None, description="Filter by user ID")
    plan_id: Optional[uuid.UUID] = Field(None, description="Filter by plan ID")
    livemode: Optional[bool] = Field(None, description="Filter by live mode")
    processed_successfully: Optional[bool] = Field(None, description="Filter by processing status")
    
    # Date range filtering
    event_timestamp_from: Optional[datetime] = Field(None, description="Event timestamp range start")
    event_timestamp_to: Optional[datetime] = Field(None, description="Event timestamp range end")
    created_at_from: Optional[datetime] = Field(None, description="Created timestamp range start")
    created_at_to: Optional[datetime] = Field(None, description="Created timestamp range end")
    
    # Sorting options
    sort_by: StripeEventSortBy = Field(
        StripeEventSortBy.CREATED_AT, 
        description="Field to sort by"
    )
    sort_order: SortOrder = Field(
        SortOrder.DESC, 
        description="Sort order"
    )
    
    # Pagination
    skip: int = Field(0, ge=0, description="Number of records to skip")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of records to return")
    
    # Search in event data
    search_text: Optional[str] = Field(None, description="Search text in event data JSON")

class PaginatedStripeEvents(BillingBaseSchema):
    """Schema for paginated Stripe events response."""
    items: List[StripeEventRead]
    total: int
    page: int
    per_page: int
    pages: int
    filters_applied: Dict[str, Any] = Field(description="Summary of applied filters")

class StripeEventStats(BillingBaseSchema):
    """Schema for Stripe event statistics."""
    total_events: int
    events_by_type: Dict[str, int]
    events_by_date: Dict[str, int]  # Date string to count
    processing_success_rate: float
    livemode_events: int
    test_mode_events: int
    unique_organizations: int
    unique_users: int
    time_range: Dict[str, Optional[datetime]]  # earliest and latest events

class StripeEventDeleteResult(BillingBaseSchema):
    """Schema for Stripe event deletion results."""
    success: bool = Field(..., description="Whether deletion was successful")
    deleted_count: int = Field(..., description="Number of events deleted")
    filters_applied: Dict[str, Any] = Field(description="Summary of applied filters")
    deletion_type: str = Field(..., description="Type of deletion performed")
    timestamp: datetime = Field(default_factory=datetime_now_utc, description="When deletion was performed")

class StripeEventTimeWindowDelete(BillingBaseSchema):
    """Schema for time-window based Stripe event deletion."""
    hours_back: Optional[int] = Field(None, ge=1, le=8760, description="Delete events from last N hours (max 1 year)")
    days_back: Optional[int] = Field(None, ge=1, le=365, description="Delete events from last N days (max 1 year)")
    org_id: Optional[uuid.UUID] = Field(None, description="Optional organization filter")
    event_types: Optional[List[str]] = Field(None, description="Optional event types to delete")
    only_failed: bool = Field(False, description="Only delete failed processing events")
    
    @field_validator('hours_back', 'days_back')
    def validate_time_window(cls, v, info):
        """Validate that at least one time parameter is provided."""
        values = info.data
        hours_back = values.get('hours_back')
        days_back = values.get('days_back')
        
        # If this is the second field being validated, check both are not None
        if info.field_name == 'days_back' and hours_back is None and v is None:
            raise ValueError("Either hours_back or days_back must be specified")
        
        return v

class StripeWebhookEvent(BillingBaseSchema):
    """Schema for Stripe webhook events."""
    id: str = Field(..., description="Stripe event ID")
    type: str = Field(..., description="Event type")
    created: datetime = Field(..., description="Event creation timestamp")
    data: Dict[str, Any] = Field(..., description="Event data")
    livemode: bool = Field(..., description="Whether event is from live mode")

# --- Error Schemas --- #

class BillingError(BillingBaseSchema):
    """Schema for billing error responses."""
    error_code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")

class InsufficientCreditsError(BillingError):
    """Schema for insufficient credits error."""
    error_code: str = Field("INSUFFICIENT_CREDITS", description="Error code")
    credit_type: CreditType = Field(..., description="Credit type that was insufficient")
    required: float = Field(..., description="Credits required")
    available: float = Field(..., description="Credits available")

# --- Pagination Schemas --- #

class PaginatedUsageEvents(BillingBaseSchema):
    """Schema for paginated usage events."""
    items: List[UsageEventRead]
    total: int
    page: int
    per_page: int
    pages: int
    filters_applied: Dict[str, Any] = Field(description="Summary of applied filters")

class PaginatedCreditPurchases(BillingBaseSchema):
    """Schema for paginated credit purchases."""
    items: List[CreditPurchaseRead]
    total: int
    page: int
    per_page: int
    pages: int

# --- Settings and Configuration Schemas --- #

class BillingSettings(BillingBaseSchema):
    """Schema for billing settings."""
    org_id: uuid.UUID
    billing_email: Optional[str] = Field(None, description="Billing contact email")
    auto_recharge_enabled: bool = Field(False, description="Enable automatic credit recharge")
    auto_recharge_threshold: Optional[float] = Field(None, description="Credit threshold for auto-recharge")
    auto_recharge_amount: Optional[float] = Field(None, description="Amount to recharge automatically")
    overage_notifications_enabled: bool = Field(True, description="Enable overage notifications")

class OveragePolicy(BillingBaseSchema):
    """Schema for overage policy configuration."""
    credit_type: CreditType
    allow_overage: bool = Field(True, description="Whether to allow overage usage")
    grace_percentage: float = Field(10, ge=0, le=100, description="Percentage of monthly allocation allowed as grace")
    max_grace_credits: float = Field(..., ge=0, description="Maximum grace credits allowed")
    hard_limit_enabled: bool = Field(False, description="Whether to enforce hard limits")
    notification_thresholds: List[float] = Field([75, 90, 100], description="Usage percentage thresholds for notifications")

# --- Stripe Integration Schemas --- #

class StripeCustomerCreate(BillingBaseSchema):
    """Schema for creating Stripe customers."""
    email: str = Field(..., description="Customer email")
    name: str = Field(..., description="Customer name")
    metadata: Dict[str, str] = Field(default={}, description="Customer metadata")

class StripePaymentMethodAttach(BillingBaseSchema):
    """Schema for attaching payment methods."""
    payment_method_id: str = Field(..., description="Stripe Payment Method ID")
    set_as_default: bool = Field(True, description="Set as default payment method")

class CheckoutSessionResponse(BillingBaseSchema):
    """Schema for checkout session response."""
    checkout_url: str = Field(..., description="URL to redirect user to Stripe Checkout")
    session_id: str = Field(..., description="Stripe Checkout Session ID")
    purchase_id: Optional[str] = Field(None, description="Purchase record ID for tracking (if applicable)")
    expires_at: datetime = Field(..., description="When the checkout session expires")

class CustomerPortalResponse(BillingBaseSchema):
    """Schema for customer portal session response."""
    portal_url: str = Field(..., description="URL to redirect user to Stripe Customer Portal")

class CheckoutResultResponse(BillingBaseSchema):
    """Schema for checkout result response."""
    success: bool = Field(..., description="Whether the checkout was successful")
    message: str = Field(..., description="Human-readable message about the result")
    session_id: Optional[str] = Field(None, description="Stripe checkout session ID")
    session_status: Optional[str] = Field(None, description="Stripe session status")
    customer_email: Optional[str] = Field(None, description="Customer email from session")
    payment_status: Optional[str] = Field(None, description="Payment status from session")

# --- Admin Schemas --- #

class AdminBillingOverview(BillingBaseSchema):
    """Schema for admin billing overview."""
    total_organizations: int
    active_subscriptions: int
    trial_subscriptions: int
    total_revenue: float
    monthly_recurring_revenue: float
    churn_rate: float
    average_revenue_per_user: float

class AdminUsageMetrics(BillingBaseSchema):
    """Schema for admin usage metrics."""
    total_events: int
    events_by_type: Dict[str, int]
    credits_consumed_by_type: Dict[str, float]
    overage_usage_percentage: float
    top_consuming_orgs: List[Dict[str, Any]]

class CreditAllocationResult(BillingBaseSchema):
    """Result of credit allocation for long-running operations."""
    success: bool
    credit_type: CreditType = Field(description="Type of credits allocated")
    operation_id: str = Field(description="Unique operation identifier")
    allocated_credits: float = Field(description="Number of credits allocated")
    remaining_balance: float = Field(description="Remaining credit balance after allocation")
    is_overage: bool = Field(default=False, description="Whether allocation used overage credits")
    allocation_token: str = Field(description="Token for later adjustment operations")

class CreditAdjustmentResult(BillingBaseSchema):
    """Result of credit allocation adjustment."""
    success: bool
    operation_id: str = Field(description="Operation identifier")
    adjustment_needed: bool = Field(description="Whether any adjustment was necessary")
    credit_difference: float = Field(description="Difference between allocated and actual credits")
    final_credits_consumed: float = Field(description="Final actual credits consumed")
    allocated_credits: float = Field(description="Originally allocated credits")
    adjustment_type: str = Field(description="Type of adjustment: 'consume', 'return', or 'none'")

class CreditAllocationRequest(BillingBaseSchema):
    """Request to allocate credits for a long-running operation."""
    credit_type: CreditType
    estimated_credits: float = Field(gt=0, description="Estimated credits needed for operation")
    operation_id: str = Field(description="Unique identifier for the operation")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional operation metadata")

class CreditAdjustmentRequest(BillingBaseSchema):
    """Request to adjust allocated credits with actual consumption."""
    operation_id: str = Field(description="Operation identifier from allocation")
    actual_credits: float = Field(ge=0, description="Actual credits consumed")
    allocated_credits: float = Field(gt=0, description="Previously allocated credits")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional adjustment metadata")

# --- Credit Operations Result Schemas --- #

class AtomicCreditConsumptionResult(BillingBaseSchema):
    """Result of atomic credit consumption operation."""
    success: bool = Field(description="Whether the consumption was successful")
    credit_type: CreditType = Field(description="Type of credits consumed")
    credits_consumed: float = Field(description="Number of credits consumed")
    remaining_balance: float = Field(description="Remaining credit balance after consumption")
    total_consumed: float = Field(description="Total credits consumed by organization")
    total_granted: float = Field(description="Total credits granted to organization")
    is_overage: bool = Field(default=False, description="Whether consumption used overage credits")
    overage_amount: float = Field(default=0, description="Amount of overage credits used")
    was_locked: bool = Field(default=True, description="Whether transaction lock was used")
    consumed_in_dollar_credits: float = Field(default=0, description="Number of dollar credits consumed (Only for non-dollar credits)")

class CreditAdditionResult(BillingBaseSchema):
    """Result of adding credits."""
    success: bool = Field(description="Whether credits were successfully added")
    credits_added: float = Field(description="Number of credits added")
    new_total_granted: float = Field(description="New total granted credits")
    allocation_id: Optional[uuid.UUID] = Field(default=None, description="ID of allocation record created")

class CreditExpirationResult(BillingBaseSchema):
    """Result of credit expiration adjustment."""
    success: bool = Field(description="Whether expiration was processed successfully")
    expired_credits: float = Field(description="Number of credits that expired")
    granted_reduction: float = Field(description="Amount reduced from granted credits")
    consumed_reduction: float = Field(description="Amount reduced from consumed credits")
    credits_granted_before: float = Field(description="Granted credits before expiration")
    credits_consumed_before: float = Field(description="Consumed credits before expiration")
    credits_granted_after: float = Field(description="Granted credits after expiration")
    credits_consumed_after: float = Field(description="Consumed credits after expiration")

class OrganizationNetCreditsRead(BillingBaseSchema):
    """Schema for reading organization net credits data."""
    id: uuid.UUID
    org_id: uuid.UUID
    credit_type: CreditType
    credits_granted: float = Field(description="Total credits granted from all sources")
    credits_consumed: float = Field(description="Total credits consumed")
    current_balance: float = Field(description="Current available balance (granted - consumed)")
    is_overage: bool = Field(description="Whether consumed exceeds granted")
    overage_amount: float = Field(description="Amount of overage if any")
    created_at: datetime
    updated_at: datetime

# --- Batch Operation Schemas --- #

class CreditAdditionBatch(BillingBaseSchema):
    """Schema for batch credit addition operations."""
    credit_type: CreditType = Field(description="Type of credits to add")
    credits_to_add: float = Field(gt=0, description="Number of credits to add")
    source_type: CreditSourceType = Field(description="Source of the credits")
    source_id: Optional[str] = Field(default=None, description="Source identifier")
    expires_at: Optional[datetime] = Field(default=None, description="When these credits expire")

class CreditExpirationBatch(BillingBaseSchema):
    """Schema for batch credit expiration operations."""
    credit_type: CreditType = Field(description="Type of credits to expire")
    expired_credits: float = Field(gt=0, description="Number of credits that expired")


class PromotionCodeQuery(BillingBaseSchema):
    """Schema for querying promotion codes with filtering."""
    # Filtering options
    is_active: Optional[bool] = Field(None, description="Filter by active status")
    credit_type: Optional[CreditType] = Field(None, description="Filter by credit type")
    search_text: Optional[str] = Field(None, description="Search in code or description")
    expires_after: Optional[datetime] = Field(None, description="Filter codes that expire after this date")
    expires_before: Optional[datetime] = Field(None, description="Filter codes that expire before this date")
    has_usage_limit: Optional[bool] = Field(None, description="Filter codes with/without usage limits")
    
    # Sorting options
    sort_by: str = Field("created_at", description="Field to sort by")
    sort_order: SortOrder = Field(SortOrder.DESC, description="Sort order")
    
    # Pagination
    skip: int = Field(0, ge=0, description="Number of records to skip")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of records to return")


class UsageEventQuery(BillingBaseSchema):
    """Schema for querying usage events with filtering."""
    # Filtering options
    org_id: Optional[uuid.UUID] = Field(None, description="Filter by organization ID")
    user_id: Optional[uuid.UUID] = Field(None, description="Filter by user ID")
    event_type: Optional[str] = Field(None, description="Filter by event type")
    credit_type: Optional[CreditType] = Field(None, description="Filter by credit type")
    is_overage: Optional[bool] = Field(None, description="Filter by overage status")
    
    # Date range filtering
    created_after: Optional[datetime] = Field(None, description="Filter events created after this date")
    created_before: Optional[datetime] = Field(None, description="Filter events created before this date")
    
    # Metadata search
    metadata_search: Optional[str] = Field(None, description="Search text in usage metadata JSON")
    
    # Sorting options
    sort_by: str = Field("created_at", description="Field to sort by (created_at, credits_consumed, event_type)")
    sort_order: SortOrder = Field(SortOrder.DESC, description="Sort order")
    
    # Pagination
    skip: int = Field(0, ge=0, description="Number of records to skip")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of records to return")


class PaginatedPromotionCodes(BillingBaseSchema):
    """Schema for paginated promotion codes response."""
    items: List[PromotionCodeRead]
    total: int
    page: int
    per_page: int
    pages: int
    filters_applied: Dict[str, Any] = Field(description="Summary of applied filters")


class AdminCreditResetRequest(BillingBaseSchema):
    """Schema for admin credit reset request."""
    org_id: uuid.UUID = Field(..., description="Organization ID to reset credits for")
    credit_types: Optional[List[CreditType]] = Field(None, description="Credit types to reset (null for all types)")
    reason: str = Field("Admin credit reset", description="Reason for the reset (for audit purposes)")


class CreditResetResult(BillingBaseSchema):
    """Result of credit reset operation for a single credit type."""
    success: bool = Field(description="Whether the reset was successful")
    credit_type: CreditType = Field(description="Credit type that was reset")
    credits_granted_before: float = Field(description="Granted credits before reset")
    credits_consumed_before: float = Field(description="Consumed credits before reset")
    credits_granted_after: float = Field(description="Granted credits after reset")
    credits_consumed_after: float = Field(description="Consumed credits after reset")
    adjustment_amount: float = Field(description="Amount adjusted to reach zero")
    error_message: Optional[str] = Field(None, description="Error message if reset failed")


class AdminCreditResetResponse(BillingBaseSchema):
    """Schema for admin credit reset response."""
    success: bool = Field(description="Whether the overall reset operation was successful")
    org_id: uuid.UUID = Field(description="Organization ID that was reset")
    admin_user_id: uuid.UUID = Field(description="Admin user who performed the reset")
    reason: str = Field(description="Reason for the reset")
    reset_results: Dict[str, CreditResetResult] = Field(description="Results by credit type")
    total_credit_types_processed: int = Field(description="Number of credit types processed")
    successful_resets: int = Field(description="Number of successful resets")
    failed_resets: int = Field(description="Number of failed resets")
    timestamp: datetime = Field(default_factory=datetime_now_utc, description="When the reset was performed") 
