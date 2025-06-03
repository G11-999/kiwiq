"""
Billing schemas for KiwiQ system.

This module defines Pydantic schemas for request/response validation
in the billing API. It follows KiwiQ's established patterns for schema
definition and validation.
"""

import uuid
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Union
from decimal import Decimal

from pydantic import BaseModel, Field, validator, ConfigDict

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
    
    @validator('monthly_credits')
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
    plan_id: Optional[uuid.UUID] = None
    seats_count: Optional[int] = Field(None, ge=1)
    cancel_at_period_end: Optional[bool] = None

class SubscriptionRead(SubscriptionBase):
    """Schema for reading subscription data."""
    id: uuid.UUID
    org_id: uuid.UUID
    plan_id: uuid.UUID
    stripe_subscription_id: str
    stripe_customer_id: str
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
    credits_consumed: float = Field(..., ge=0, description="Number of credits to consume (can be 0 for edge cases)")
    event_type: str = Field(..., description="Type of usage event")
    metadata: Dict[str, Any] = Field(default={}, description="Event-specific metadata")

class CreditConsumptionResult(BillingBaseSchema):
    """Result of credit consumption operation."""
    success: bool
    credits_consumed: float
    remaining_balance: float
    is_overage: bool = Field(default=False)
    grace_credits_used: float = Field(default=0)
    warning: Optional[str] = Field(default=None)

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

class CreditPurchaseRead(BillingBaseSchema):
    """Schema for reading credit purchase data."""
    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID
    stripe_payment_intent_id: str
    stripe_invoice_id: Optional[str]
    credit_type: CreditType
    credits_amount: float
    amount_paid: float
    currency: str
    status: PaymentStatus
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
    subscription: Optional[SubscriptionReadWithPlan]
    credit_balances: List[CreditBalance]
    recent_usage: List[UsageEventRead]
    recent_purchases: List[CreditPurchaseRead]
    upcoming_renewal: Optional[datetime]
    overage_warnings: List[str]

# --- Webhook Schemas --- #

class StripeWebhookEvent(BillingBaseSchema):
    """Schema for Stripe webhook events."""
    id: str = Field(..., description="Stripe event ID")
    type: str = Field(..., description="Event type")
    created: int = Field(..., description="Event creation timestamp")
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
    credits_consumed: float = Field(description="Number of credits consumed")
    remaining_balance: float = Field(description="Remaining credit balance after consumption")
    total_consumed: float = Field(description="Total credits consumed by organization")
    total_granted: float = Field(description="Total credits granted to organization")
    is_overage: bool = Field(default=False, description="Whether consumption used overage credits")
    overage_amount: float = Field(default=0, description="Amount of overage credits used")
    was_locked: bool = Field(default=True, description="Whether transaction lock was used")

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