"""
LinkedIn OAuth Exception Classes

This module defines custom exceptions for LinkedIn OAuth operations,
following KiwiQ's established error handling patterns.
"""

from typing import Optional


class LinkedInOauthException(Exception):
    """
    Base exception for LinkedIn OAuth operations.
    
    This is the parent class for all LinkedIn OAuth-related exceptions,
    providing a consistent interface for error handling.
    
    Attributes:
        message: Human-readable error message
        status_code: HTTP status code for API responses
    """
    
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class LinkedInAccountConflictException(LinkedInOauthException):
    """
    Exception raised when a LinkedIn account is already linked to a different KIWIQ user.
    
    This exception occurs when attempting to link a LinkedIn account that is already
    associated with another KIWIQ user, enforcing the 1:1 mapping constraint.
    
    Attributes:
        linkedin_id: The LinkedIn ID (sub) that caused the conflict
        existing_user_email: Email of the KIWIQ user already linked to this LinkedIn account
    """
    
    def __init__(self, linkedin_id: str, existing_user_email: str):
        message = (
            f"This LinkedIn account is already linked to another KIWIQ account ({existing_user_email}). "
            f"Please login to that account and unlink LinkedIn from settings."
        )
        super().__init__(message, status_code=409)
        self.linkedin_id = linkedin_id
        self.existing_user_email = existing_user_email


class LinkedInTokenExpiredException(LinkedInOauthException):
    """
    Exception raised when LinkedIn access token has expired.
    
    This exception is used when attempting to use an expired access token
    for LinkedIn API calls. The client should attempt to refresh the token
    or re-authenticate the user.
    """
    
    def __init__(self, message: str = "LinkedIn access token has expired"):
        super().__init__(message, status_code=401)


class LinkedInAPIException(LinkedInOauthException):
    """
    Exception for LinkedIn API errors.
    
    This exception wraps errors returned by the LinkedIn API, providing
    additional context about the API failure.
    
    Attributes:
        api_error_code: LinkedIn API error code if available
    """
    
    def __init__(self, message: str, api_error_code: Optional[str] = None):
        super().__init__(message, status_code=502)
        self.api_error_code = api_error_code


class LinkedInStateException(LinkedInOauthException):
    """
    Exception for OAuth state token validation errors.
    
    This exception is raised when state token validation fails during
    the OAuth callback process, indicating potential CSRF attacks or
    expired state tokens.
    """
    
    def __init__(self, message: str = "Invalid or expired OAuth state token"):
        super().__init__(message, status_code=400)


class LinkedInEmailVerificationException(LinkedInOauthException):
    """
    Exception for LinkedIn email verification issues.
    
    This exception is raised when LinkedIn returns an unverified email
    or no email at all, requiring additional verification steps.
    """
    
    def __init__(
        self, 
        message: str = "LinkedIn email not verified or not available",
        linkedin_id: str = None,
        email: Optional[str] = None
    ):
        super().__init__(message, status_code=422)
        self.linkedin_id = linkedin_id
        self.email = email 