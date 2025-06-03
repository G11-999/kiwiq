"""
Billing exceptions for KiwiQ system.

This module defines custom exceptions for billing-related operations,
following KiwiQ's established patterns for exception handling.
"""

from typing import Optional, Dict, Any
from fastapi import HTTPException, status

from kiwi_app.billing.models import CreditType


class BillingException(HTTPException):
    """Base exception for billing-related errors."""
    
    def __init__(
        self, 
        status_code: int = status.HTTP_400_BAD_REQUEST,
        detail: str = "Billing error occurred",
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class InsufficientCreditsException(BillingException):
    """
    Exception raised when an organization has insufficient credits for an operation.
    
    This exception is raised when attempting to consume more credits than available,
    and overage policies don't allow the consumption.
    """
    
    def __init__(
        self,
        credit_type: CreditType,
        required: float,
        available: float,
        detail: Optional[str] = None
    ):
        self.credit_type = credit_type
        self.required = required
        self.available = available
        
        if detail is None:
            detail = (
                f"Insufficient {credit_type.value} credits. "
                f"Required: {required}, Available: {available}"
            )
        
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail
        )


class SubscriptionNotFoundException(BillingException):
    """Exception raised when a subscription is not found."""
    
    def __init__(self, detail: str = "Subscription not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )


class SubscriptionPlanNotFoundException(BillingException):
    """Exception raised when a subscription plan is not found."""
    
    def __init__(self, detail: str = "Subscription plan not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )


class InvalidSubscriptionStateException(BillingException):
    """Exception raised when attempting an operation on a subscription in an invalid state."""
    
    def __init__(self, detail: str = "Invalid subscription state for this operation"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail
        )


class PaymentMethodRequiredException(BillingException):
    """Exception raised when a payment method is required but not provided."""
    
    def __init__(self, detail: str = "Payment method required for this operation"):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail
        )


class StripeIntegrationException(BillingException):
    """Exception raised when Stripe API operations fail."""
    
    def __init__(
        self, 
        detail: str = "Payment processing error",
        stripe_error_code: Optional[str] = None,
        stripe_error_message: Optional[str] = None
    ):
        self.stripe_error_code = stripe_error_code
        self.stripe_error_message = stripe_error_message
        
        if stripe_error_message:
            detail = f"{detail}: {stripe_error_message}"
        
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail
        )


class PromotionCodeException(BillingException):
    """Base exception for promotion code related errors."""
    pass


class PromotionCodeNotFoundException(PromotionCodeException):
    """Exception raised when a promotion code is not found."""
    
    def __init__(self, code: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Promotion code '{code}' not found"
        )


class PromotionCodeExpiredException(PromotionCodeException):
    """Exception raised when attempting to use an expired promotion code."""
    
    def __init__(self, code: str):
        super().__init__(
            status_code=status.HTTP_410_GONE,
            detail=f"Promotion code '{code}' has expired"
        )


class PromotionCodeExhaustedException(PromotionCodeException):
    """Exception raised when a promotion code has reached its usage limit."""
    
    def __init__(self, code: str):
        super().__init__(
            status_code=status.HTTP_410_GONE,
            detail=f"Promotion code '{code}' has reached its usage limit"
        )


class PromotionCodeAlreadyUsedException(PromotionCodeException):
    """Exception raised when an organization has already used a promotion code."""
    
    def __init__(self, code: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Promotion code '{code}' has already been used by this organization"
        )


class PromotionCodeNotAllowedException(PromotionCodeException):
    """Exception raised when an organization is not allowed to use a promotion code."""
    
    def __init__(self, code: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Organization is not allowed to use promotion code '{code}'"
        )


class CreditPurchaseException(BillingException):
    """Base exception for credit purchase related errors."""
    pass


class CreditPurchaseNotFoundException(CreditPurchaseException):
    """Exception raised when a credit purchase is not found."""
    
    def __init__(self, detail: str = "Credit purchase not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )


class InvalidCreditPurchaseStateException(CreditPurchaseException):
    """Exception raised when attempting an operation on a credit purchase in an invalid state."""
    
    def __init__(self, detail: str = "Invalid credit purchase state for this operation"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail
        )


class SeatLimitExceededException(BillingException):
    """Exception raised when attempting to exceed the seat limit for a subscription."""
    
    def __init__(self, current_seats: int, max_seats: int):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Seat limit exceeded. Current: {current_seats}, Maximum: {max_seats}"
        )


class BillingConfigurationException(BillingException):
    """Exception raised when there's a billing configuration error."""
    
    def __init__(self, detail: str = "Billing configuration error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )


class WebhookProcessingException(BillingException):
    """Exception raised when webhook processing fails."""
    
    def __init__(
        self, 
        detail: str = "Webhook processing failed",
        webhook_id: Optional[str] = None,
        webhook_type: Optional[str] = None
    ):
        self.webhook_id = webhook_id
        self.webhook_type = webhook_type
        
        if webhook_id and webhook_type:
            detail = f"{detail} (ID: {webhook_id}, Type: {webhook_type})"
        
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )


class DuplicateWebhookException(BillingException):
    """Exception raised when attempting to process a duplicate webhook."""
    
    def __init__(self, webhook_id: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Webhook {webhook_id} has already been processed"
        )


class OveragePolicyViolationException(BillingException):
    """Exception raised when usage violates overage policies."""
    
    def __init__(
        self,
        credit_type: CreditType,
        attempted_consumption: float,
        overage_limit: float,
        detail: Optional[str] = None
    ):
        self.credit_type = credit_type
        self.attempted_consumption = attempted_consumption
        self.overage_limit = overage_limit
        
        if detail is None:
            detail = (
                f"Overage limit exceeded for {credit_type.value}. "
                f"Attempted: {attempted_consumption}, Limit: {overage_limit}"
            )
        
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )


class CreditExpiredException(BillingException):
    """Exception raised when attempting to use expired credits."""
    
    def __init__(self, credit_type: CreditType, expired_amount: float):
        super().__init__(
            status_code=status.HTTP_410_GONE,
            detail=f"{expired_amount} {credit_type.value} credits have expired"
        )


class BillingPermissionDeniedException(BillingException):
    """Exception raised when user lacks billing permissions."""
    
    def __init__(self, detail: str = "Insufficient permissions for billing operation"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )


class InvalidBillingPeriodException(BillingException):
    """Exception raised when billing period calculations are invalid."""
    
    def __init__(self, detail: str = "Invalid billing period"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


class ProrationCalculationException(BillingException):
    """Exception raised when proration calculations fail."""
    
    def __init__(self, detail: str = "Proration calculation failed"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )


class UsageTrackingException(BillingException):
    """Exception raised when usage tracking operations fail."""
    
    def __init__(self, detail: str = "Usage tracking error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )


class CreditAllocationException(BillingException):
    """Exception raised when credit allocation operations fail."""
    
    def __init__(self, detail: str = "Credit allocation failed"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )


class BillingDataInconsistencyException(BillingException):
    """Exception raised when billing data inconsistencies are detected."""
    
    def __init__(self, detail: str = "Billing data inconsistency detected"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )


class RateLimitExceededException(BillingException):
    """Exception raised when API rate limits are exceeded."""
    
    def __init__(self, detail: str = "Rate limit exceeded"):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail
        ) 