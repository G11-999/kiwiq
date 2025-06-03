"""
Billing models for KiwiQ system.

This module defines the database models for subscription management, credit tracking,
and usage events. It integrates with the existing auth system and follows KiwiQ's
established patterns for model definition.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import String as SQLAlchemyString, Text, JSON, Boolean, Index, ForeignKey, Enum as SQLAlchemyEnum, CheckConstraint, Float
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel, Column

# Import existing auth models and utilities
from kiwi_app.auth.models import Organization, User
from global_utils import datetime_now_utc
from kiwi_app.settings import settings

# Define table prefix following KiwiQ patterns
table_prefix = f"{settings.DB_TABLE_NAMESPACE_PREFIX}billing_"

# --- Enums --- #

class CreditType(str, Enum):
    """Types of credits in the KiwiQ system."""
    WORKFLOWS = "workflows"
    WEB_SEARCHES = "web_searches" 
    DOLLAR_CREDITS = "dollar_credits"

class SubscriptionStatus(str, Enum):
    """Subscription status values."""
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    PAUSED = "paused"

class CreditSourceType(str, Enum):
    """Source types for credit allocations."""
    PROMOTION = "01_promotion"
    SUBSCRIPTION = "02_subscription"
    PURCHASE = "03_purchase"

class PaymentStatus(str, Enum):
    """Payment status for credit purchases."""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"

# --- Models --- #

class SubscriptionPlan(SQLModel, table=True):
    """
    Subscription plan templates with credit allocations and pricing.
    
    This model defines the available subscription tiers that organizations
    can subscribe to. Each plan includes credit allocations, pricing, and
    feature definitions.
    """
    __tablename__ = f"{table_prefix}subscription_plan"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    name: str = Field(sa_column=Column(SQLAlchemyString, unique=True, index=True))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Stripe integration fields
    stripe_product_id: str = Field(
        sa_column=Column(SQLAlchemyString, unique=True, index=True),
        description="Stripe Product ID for this plan"
    )
    stripe_price_id_monthly: Optional[str] = Field(
        default=None, 
        sa_column=Column(SQLAlchemyString, unique=True, nullable=True),
        description="Stripe Price ID for monthly billing"
    )
    stripe_price_id_annual: Optional[str] = Field(
        default=None, 
        sa_column=Column(SQLAlchemyString, unique=True, nullable=True),
        description="Stripe Price ID for annual billing"
    )
    
    # Plan limits and allocations
    max_seats: int = Field(default=1, description="Maximum number of users allowed")
    monthly_credits: Dict[str, float] = Field(
        sa_column=Column(JSON),
        description="Monthly credit allocations by type",
        default={CreditType.WORKFLOWS.value: 100.0, CreditType.WEB_SEARCHES.value: 500.0, CreditType.DOLLAR_CREDITS.value: 25.0}
    )
    
    # Pricing in dollars (changed from cents)
    monthly_price: float = Field(sa_column=Column(Float), description="Monthly price in dollars")
    annual_price: float = Field(sa_column=Column(Float), description="Annual price in dollars")
    
    # Features and metadata
    features: Dict[str, Any] = Field(
        sa_column=Column(JSON),
        default={},
        description="Plan features and capabilities"
    )
    
    # Plan status
    is_active: bool = Field(default=True, index=True, description="Whether this plan is available for new subscriptions")
    is_trial_eligible: bool = Field(default=True, description="Whether this plan supports trial periods")
    trial_days: int = Field(default=14, description="Number of trial days for this plan")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(
        default_factory=datetime_now_utc, 
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc)
    )
    
    # Relationships
    subscriptions: List["OrganizationSubscription"] = Relationship(back_populates="plan")

class OrganizationSubscription(SQLModel, table=True):
    """
    Organization's active subscription details.
    
    This model tracks the current subscription state for each organization,
    including Stripe subscription details, billing periods, and seat counts.
    """
    __tablename__ = f"{table_prefix}org_subscription"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    
    # Foreign keys to existing auth models
    org_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}org.id", 
        index=True,
        nullable=True,
    )
    plan_id: uuid.UUID = Field(
        default=None,
        foreign_key=f"{table_prefix}subscription_plan.id", 
        index=True,
        nullable=True,
    )
    
    # Stripe integration fields
    stripe_subscription_id: str = Field(
        sa_column=Column(SQLAlchemyString, unique=True, index=True),
        description="Stripe Subscription ID"
    )
    stripe_subscription_item_id: Optional[str] = Field(
        default=None, 
        sa_column=Column(SQLAlchemyString, nullable=True),
        description="Stripe Subscription Item ID for seat-based billing"
    )
    stripe_customer_id: str = Field(
        sa_column=Column(SQLAlchemyString, index=True),
        description="Stripe Customer ID for the organization"
    )
    
    # Subscription status and timing
    status: SubscriptionStatus = Field(
        sa_column=Column(SQLAlchemyEnum(SubscriptionStatus, name=f"{table_prefix}subscription_status_enum"), index=True)
    )
    current_period_start: datetime = Field(description="Current billing period start", sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    current_period_end: datetime = Field(description="Current billing period end", sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    
    # Billing configuration
    seats_count: int = Field(default=1, description="Number of active seats")
    is_annual: bool = Field(default=False, description="Annual vs monthly billing")
    next_billing_date: Optional[datetime] = Field(default=None, description="UTC timestamp when the next billing period starts", sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True, index=True))
    
    # Trial information
    trial_start: Optional[datetime] = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True))
    trial_end: Optional[datetime] = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True))
    is_trial_active: bool = Field(default=False, index=True)
    
    # Cancellation information
    canceled_at: Optional[datetime] = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True))
    cancel_at_period_end: bool = Field(default=False, description="Whether to cancel at end of current period")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(
        default_factory=datetime_now_utc, 
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc)
    )
    
    # Relationships
    organization: Organization = Relationship()
    plan: SubscriptionPlan = Relationship(back_populates="subscriptions")


class CreditPurchase(SQLModel, table=True):
    """
    One-time credit purchases through Stripe.
    
    This model tracks credit purchases made outside of subscriptions,
    including payment status and credit allocation details.
    """
    __tablename__ = f"{table_prefix}credit_purchase"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    
    # Foreign keys
    org_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}org.id", 
        index=True,
        nullable=True,
    )
    user_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}user.id", 
        index=True,
        nullable=True,
        description="User who initiated the purchase"
    )
    
    # Stripe integration
    stripe_payment_intent_id: str = Field(
        sa_column=Column(SQLAlchemyString, unique=True, index=True),
        description="Stripe Payment Intent ID"
    )
    stripe_invoice_id: Optional[str] = Field(
        default=None,
        sa_column=Column(SQLAlchemyString, nullable=True),
        description="Stripe Invoice ID if applicable"
    )
    
    # Purchase details
    credit_type: CreditType = Field(
        sa_column=Column(SQLAlchemyEnum(CreditType, name=f"{table_prefix}purchase_credit_type_enum"), index=True)
    )
    credits_amount: float = Field(sa_column=Column(Float), description="Number of credits purchased")
    amount_paid: float = Field(sa_column=Column(Float), description="Amount paid in dollars")
    currency: str = Field(default="usd", description="Currency code")
    
    # Status and timing
    status: PaymentStatus = Field(
        sa_column=Column(SQLAlchemyEnum(PaymentStatus, name=f"{table_prefix}payment_status_enum"), index=True)
    )
    expires_at: Optional[datetime] = Field(
        default=None, 
        description="When purchased credits expire",
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True)
    )
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(
        default_factory=datetime_now_utc, 
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc)
    )
    
    # Relationships
    organization: Organization = Relationship()
    user: User = Relationship()


class PromotionCode(SQLModel, table=True):
    """
    Promotion codes for credit grants.
    
    This model manages promotional credit codes that can be applied
    by organizations to receive free credits.
    """
    __tablename__ = f"{table_prefix}promotion_code"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    
    # Code details
    code: str = Field(sa_column=Column(SQLAlchemyString, unique=True, index=True))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Credit allocation
    credit_type: CreditType = Field(
        sa_column=Column(SQLAlchemyEnum(CreditType, name=f"{table_prefix}promo_credit_type_enum"), index=True)
    )
    credits_amount: float = Field(sa_column=Column(Float), description="Number of credits granted per use")
    
    # Usage limits
    max_uses: Optional[int] = Field(
        default=None, 
        nullable=True, 
        description="Maximum number of times this code can be used (null = unlimited)"
    )
    uses_count: int = Field(default=0, description="Number of times this code has been used")
    max_uses_per_org: int = Field(default=1, description="Maximum uses per organization")
    
    # Validity period
    expires_at: Optional[datetime] = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True, index=True))
    is_active: bool = Field(default=True, index=True)
    
    # Restrictions
    allowed_org_ids: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="List of organization IDs that can use this code (null = all orgs)"
    )
    
    # Credit expiration for granted credits
    granted_credits_expire_days: Optional[int] = Field(
        default=None,
        nullable=True,
        description="Days until granted credits expire (null = no expiration)"
    )
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    
    updated_at: datetime = Field(
        default_factory=datetime_now_utc, 
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc),
    )
    
    # Relationships
    usages: List["PromotionCodeUsage"] = Relationship(back_populates="promotion_code")


class PromotionCodeUsage(SQLModel, table=True):
    """
    Tracking of promotion code usage by organizations.
    
    This model tracks when and how promotion codes are used,
    providing audit trail and preventing duplicate usage.
    """
    __tablename__ = f"{table_prefix}promotion_code_usage"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    
    # Foreign keys
    promo_code_id: uuid.UUID = Field(
        foreign_key=f"{table_prefix}promotion_code.id", 
        index=True
    )
    org_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}org.id", 
        index=True,
        nullable=True,
    )
    user_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}user.id", 
        index=True,
        nullable=True,
        description="User who applied the promotion code"
    )
    
    # Usage details
    credits_applied: float = Field(sa_column=Column(Float), description="Number of credits granted")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    
    # Relationships
    promotion_code: PromotionCode = Relationship(back_populates="usages")
    organization: Organization = Relationship()
    user: User = Relationship()


class OrganizationNetCredits(SQLModel, table=True):
    """
    Total net credits for an organization.
    
    This model tracks the aggregate credit balances for each organization
    by credit type. Each organization can have only one record per credit type,
    ensuring unique tracking of net credits across all sources.
    
    This table is designed for high-performance credit consumption using
    direct UPDATE queries with transaction locks for scalability.
    """
    __tablename__ = f"{table_prefix}org_net_credits"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    
    # Foreign keys - org_id + credit_type combination must be unique
    org_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}org.id", 
        index=True,
        nullable=True,
    )

    # Credit details - credit_type is part of the unique constraint
    credit_type: CreditType = Field(
        sa_column=Column(SQLAlchemyEnum(CreditType, name=f"{table_prefix}credit_type_enum"), index=True)
    )
    
    # Core credit tracking
    credits_granted: float = Field(default=0.0, sa_column=Column(Float), ge=0, description="Total credits granted from all sources")
    credits_consumed: float = Field(default=0.0, sa_column=Column(Float), description="Total credits consumed")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(
        default_factory=datetime_now_utc, 
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc),
    )

    # Relationships
    organization: Organization = Relationship()
    
    # Table constraints - ensure one record per organization per credit type
    __table_args__ = (
        Index(f"idx_{table_prefix}org_net_credits_org_credit_type", "org_id", "credit_type", unique=True),
    )


class OrganizationCredits(SQLModel, table=True):
    """
    Credit balances and allocations for organizations.
    
    This model tracks credit balances by type and source, supporting
    multiple credit sources (subscriptions, purchases, promotions) with
    different expiration policies.
    """
    __tablename__ = f"{table_prefix}org_credits"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    
    # Foreign keys
    org_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}org.id", 
        index=True,
        nullable=True,
    )
    
    # Credit details
    credit_type: CreditType = Field(
        sa_column=Column(SQLAlchemyEnum(CreditType, name=f"{table_prefix}credit_type_enum"), index=True)
    )
    # credits_consumed: float = Field(default=0.0, sa_column=Column(Float), description="Total consumed in this allocation")
    credits_granted: float = Field(default=0.0, sa_column=Column(Float), description="Total granted in this allocation")
    
    # Source tracking
    source_type: CreditSourceType = Field(
        sa_column=Column(SQLAlchemyEnum(CreditSourceType, name=f"{table_prefix}credit_source_type_enum"), index=True)
    )
    source_id: Optional[str] = Field(
        default=None, 
        nullable=True, 
        description="Reference to source (subscription_id, payment_intent_id, promo_code, etc.)"
    )
    source_metadata: Dict[str, Any] = Field(
        sa_column=Column(JSON),
        default={},
        description="Additional metadata about the credit source"
    )
    
    # Expiration and period tracking
    expires_at: Optional[datetime] = Field(default=None, description="UTC timestamp when these credits expire.", sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True, index=True))
    is_expired: bool = Field(default=False, index=True)
    
    # Period tracking for subscription credits
    period_start: datetime = Field(description="Period UTC timestamp when these credits became available", sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(
        default_factory=datetime_now_utc, 
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc),
    )
    
    # Relationships
    organization: Organization = Relationship()

class UsageEvent(SQLModel, table=True):
    """
    Individual usage events for audit and analytics.
    
    This model provides detailed tracking of all credit consumption
    events for auditing, analytics, and debugging purposes.
    """
    __tablename__ = f"{table_prefix}usage_event"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    
    # Foreign keys to existing auth models
    # Make this optional so if user is deleted, it is set to null
    org_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}org.id", 
        index=True,
        nullable=True,
    )
    
    # Make this optional so if user is deleted, it is set to null
    user_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{settings.DB_TABLE_NAMESPACE_PREFIX}{settings.DB_TABLE_AUTH_PREFIX}user.id", 
        index=True,
        nullable=True,
    )
    
    # Event details
    event_type: str = Field(
        index=True, 
        description="Type of usage event (workflow_run, web_search, llm_call, etc.)"
    )
    credit_type: CreditType = Field(
        sa_column=Column(SQLAlchemyEnum(CreditType, name=f"{table_prefix}usage_credit_type_enum"), index=True)
    )
    credits_consumed: float = Field(sa_column=Column(Float), description="Number of credits consumed")
    
    # Detailed tracking metadata
    usage_metadata: Dict[str, Any] = Field(
        sa_column=Column(JSON),
        default={},
        description="Event-specific metadata (workflow_id, model_used, execution_time, etc.)"
    )
    
    # Overage tracking
    is_overage: bool = Field(
        default=False, 
        index=True, 
        description="Whether this consumption used overage grace credits"
    )
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True))
    
    # Relationships
    organization: Organization = Relationship()
    user: User = Relationship()


# Update forward references after all models are defined
SubscriptionPlan.model_rebuild()
OrganizationSubscription.model_rebuild()
OrganizationCredits.model_rebuild()
UsageEvent.model_rebuild()
CreditPurchase.model_rebuild()
PromotionCode.model_rebuild()
PromotionCodeUsage.model_rebuild() 