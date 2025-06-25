"""
Billing schemas for KiwiQ standalone test client.

This module defines Pydantic schemas for billing-related operations
in the standalone test client, specifically for promotion code management
and other billing functionality.
"""
from enum import Enum
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, ConfigDict


# --- Enums --- #

class CreditType(str, Enum):
    """Enum for different types of credits."""
    WORKFLOWS = "workflows"
    WEB_SEARCHES = "web_searches"
    DOLLAR_CREDITS = "dollar_credits"


class SortOrder(str, Enum):
    """Enum for sort order options."""
    ASC = "asc"
    DESC = "desc"


class CreditSourceType(str, Enum):
    """Enum for credit source types."""
    SUBSCRIPTION = "subscription"
    PURCHASE = "purchase"
    PROMOTION = "promotion"
    ADMIN_GRANT = "admin_grant"
    TRIAL = "trial"


class SubscriptionStatus(str, Enum):
    """Enum for subscription status."""
    ACTIVE = "active"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    PAST_DUE = "past_due"
    TRIALING = "trialing"
    UNPAID = "unpaid"


class PaymentStatus(str, Enum):
    """Enum for payment status."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"


# --- Base Schemas --- #

class BillingBaseSchema(BaseModel):
    """Base schema for billing-related models."""
    model_config = ConfigDict(from_attributes=True)


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


class PaginatedPromotionCodes(BillingBaseSchema):
    """Schema for paginated promotion codes response."""
    items: List[PromotionCodeRead]
    total: int
    page: int
    per_page: int
    pages: int
    filters_applied: Dict[str, Any] = Field(description="Summary of applied filters")


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


# --- Subscription Plan Schemas --- #

class SubscriptionPlanRead(BillingBaseSchema):
    """Schema for reading subscription plan data."""
    id: uuid.UUID
    name: str
    description: Optional[str]
    stripe_product_id: str
    stripe_price_id_monthly: Optional[str]
    stripe_price_id_annual: Optional[str]
    max_seats: int
    monthly_credits: Dict[str, float]
    monthly_price: float
    annual_price: float
    features: Dict[str, Any]
    is_active: bool
    is_trial_eligible: bool
    trial_days: int
    created_at: datetime
    updated_at: datetime


# --- Usage Event Schemas --- #

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


# --- Checkout and Payment Schemas --- #

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


# --- Flexible Dollar Credit Purchase Schemas --- #

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
        # Default minimum from typical billing systems
        minimum_amount = 5
        if v < minimum_amount:
            raise ValueError(f"Minimum purchase amount is ${minimum_amount:.2f}")
        return v


# --- Dashboard and Analytics Schemas --- #

class UsageSummary(BillingBaseSchema):
    """Schema for usage summary data."""
    org_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    credit_balances: List[CreditBalance]
    total_events: int
    events_by_type: Dict[str, int]
    overage_events: int


class BillingDashboard(BillingBaseSchema):
    """Schema for billing dashboard data."""
    org_id: uuid.UUID
    subscriptions: List[Dict[str, Any]]  # Would be List[SubscriptionReadWithPlan] with full schemas
    credit_balances: List[CreditBalance]
    recent_usage: List[UsageEventRead]
    recent_purchases: List[Dict[str, Any]]  # Would be List[CreditPurchaseRead] with full schemas
    upcoming_renewals: List[datetime]
    overage_warnings: List[str]


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
