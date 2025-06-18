"""
CSRF (Cross-Site Request Forgery) Protection Utilities

This module provides comprehensive CSRF protection for the authentication system,
including token generation, validation, and cookie management.

Key Features:
    - Secure CSRF token generation using cryptographically secure random values
    - Token validation with timing-safe comparison to prevent timing attacks
    - Cookie management for CSRF tokens with proper security attributes
    - Integration with existing JWT authentication system
    - Modular design for reuse across different authentication flows

Security Considerations:
    - CSRF tokens are generated using secrets.token_urlsafe for cryptographic security
    - Tokens are validated using hmac.compare_digest for timing attack protection
    - CSRF cookie is NOT HttpOnly to allow JavaScript access for AJAX requests
    - CSRF cookie uses SameSite=Lax for balanced security and functionality
    - Token expiration matches access token expiration for consistency

Design Decisions:
    - CSRF tokens are separate from JWT tokens for clarity and security
    - Cookie name uses standard XSRF-TOKEN convention for frontend compatibility
    - Validation function is separate from authentication dependencies for modularity
    - Functions are designed to be reusable across login, refresh, and OAuth flows
"""

import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import HTTPException, status, Response, Header, Cookie
from fastapi.security.utils import get_authorization_scheme_param

from kiwi_app.settings import settings
from kiwi_app.auth.utils import auth_logger
from kiwi_app.auth.exceptions import CredentialsException


def generate_csrf_token() -> str:
    """
    Generate a cryptographically secure CSRF token.
    
    Uses secrets.token_urlsafe to generate a random token that is safe for use
    in URLs and cookies. The token is generated with sufficient entropy to
    prevent guessing attacks.
    
    Returns:
        str: A URL-safe base64-encoded random token
        
    Security Notes:
        - Uses secrets module for cryptographically secure random generation
        - Token length provides sufficient entropy (32 bytes = 256 bits)
        - URL-safe encoding ensures compatibility with HTTP headers and cookies
    """
    return secrets.token_urlsafe(settings.CSRF_TOKEN_LENGTH)


def validate_csrf_token(cookie_token: Optional[str], header_token: Optional[str]) -> bool:
    """
    Validate CSRF token by comparing cookie and header values.
    
    Implements the double-submit cookie pattern for CSRF protection:
    1. CSRF token is stored in a cookie (readable by JavaScript)
    2. Client must include the same token in a request header
    3. Server validates that both tokens match
    
    This prevents CSRF attacks because:
    - Malicious sites cannot read cookies from other domains
    - Malicious sites cannot set custom headers for cross-origin requests
    
    Args:
        cookie_token: CSRF token from the XSRF-TOKEN cookie
        header_token: CSRF token from the X-XSRF-TOKEN header
        
    Returns:
        bool: True if tokens are present and match, False otherwise
        
    Security Notes:
        - Uses hmac.compare_digest for timing-safe comparison
        - Requires both tokens to be present (not None or empty)
        - Prevents timing attacks by using constant-time comparison
    """
    # Both tokens must be present and non-empty
    if not cookie_token or not header_token:
        auth_logger.warning("CSRF validation failed: missing token in cookie or header")
        return False
    
    # Use timing-safe comparison to prevent timing attacks
    # This ensures that the comparison takes the same amount of time
    # regardless of where the tokens differ
    is_valid = hmac.compare_digest(cookie_token, header_token)
    
    if not is_valid:
        auth_logger.warning("CSRF validation failed: token mismatch")
    
    return is_valid


def set_csrf_cookie(response: Response, csrf_token: str, max_age_seconds: int) -> None:
    """
    Set CSRF token cookie with proper security attributes.
    
    Sets the XSRF-TOKEN cookie with appropriate security settings:
    - NOT HttpOnly (JavaScript needs to read it)
    - SameSite=Lax (balance between security and functionality)
    - Secure flag based on environment (HTTPS in production)
    - Proper domain and path settings
    
    Args:
        response: FastAPI Response object to set cookie on
        csrf_token: The CSRF token to store in the cookie
        max_age_seconds: Cookie expiration time in seconds
        
    Security Notes:
        - Cookie is NOT HttpOnly because JavaScript needs to read it for AJAX requests
        - SameSite=Lax prevents CSRF while allowing legitimate cross-site navigation
        - Secure flag ensures cookie is only sent over HTTPS in production
        - Domain and path settings match other authentication cookies
    """
    response.set_cookie(
        key=settings.CSRF_TOKEN_COOKIE_NAME,
        value=csrf_token,
        max_age=max_age_seconds,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=False,  # NOT HttpOnly - JavaScript needs to read this
        samesite=settings.COOKIE_SAMESITE,
        path="/"
    )


def delete_csrf_cookie(response: Response) -> None:
    """
    Delete CSRF token cookie by setting it to expire immediately.
    
    Removes the CSRF token cookie from the client by setting its max_age to 0.
    This is used during logout or when authentication fails.
    
    Args:
        response: FastAPI Response object to delete cookie from
        
    Note:
        - Must match the exact same attributes used when setting the cookie
        - Uses max_age=0 and expires=0 for reliable deletion across browsers
    """
    response.set_cookie(
        key=settings.CSRF_TOKEN_COOKIE_NAME,
        value="",
        max_age=0,
        expires=0,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=False,
        samesite=settings.COOKIE_SAMESITE,
        path="/"
    )


def validate_csrf_protection(
    csrf_cookie: Optional[str] = Cookie(None, alias=settings.CSRF_TOKEN_COOKIE_NAME),
    csrf_header: Optional[str] = Header(None, alias=settings.CSRF_TOKEN_HEADER_NAME)
) -> None:
    """
    Validate CSRF protection and raise exception if validation fails.
    
    FastAPI dependency that validates CSRF tokens and raises an HTTP exception
    if validation fails. This provides a clean way to add CSRF protection to
    any endpoint that needs it.
    
    Args:
        csrf_cookie: CSRF token from the XSRF-TOKEN cookie
        csrf_header: CSRF token from the X-XSRF-TOKEN header
        
    Raises:
        HTTPException: 403 Forbidden if CSRF validation fails
        
    Usage:
        Use as a FastAPI dependency:
        ```python
        @router.post("/protected-endpoint")
        async def protected_endpoint(
            csrf_check: None = Depends(validate_csrf_protection)
        ):
            # Endpoint logic here
            pass
        ```
        
    Security Notes:
        - Logs failed attempts for monitoring and debugging
        - Returns 403 Forbidden (not 401) as this is an authorization issue
        - Provides clear error message for debugging
    """
    if not validate_csrf_token(csrf_cookie, csrf_header):
        auth_logger.warning(
            f"CSRF validation failed for request. "
            f"Cookie present: {csrf_cookie is not None}, "
            f"Header present: {csrf_header is not None}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed. Ensure X-XSRF-TOKEN header matches XSRF-TOKEN cookie."
        )


def setup_auth_cookies_with_csrf(
    response: Response,
    access_token: str,
    refresh_token_obj: Optional[object] = None,
    keep_me_logged_in: bool = True
) -> str:
    """
    Set up all authentication cookies including CSRF protection.
    
    This function provides a centralized way to set up all authentication-related
    cookies when a user logs in or refreshes their tokens. It handles:
    - Access token cookie (HttpOnly)
    - Refresh token cookie (HttpOnly, optional)
    - CSRF token cookie (readable by JavaScript)
    
    Args:
        response: FastAPI Response object to set cookies on
        access_token: JWT access token string
        refresh_token_obj: RefreshToken database object (optional)
        keep_me_logged_in: Whether to set long-term refresh token
        
    Returns:
        str: The generated CSRF token (for potential use in response body)
        
    Usage:
        This function is designed to be used across different authentication flows:
        - Email/password login
        - Token refresh
        - OAuth login (LinkedIn, etc.)
        
        Example:
        ```python
        csrf_token = setup_auth_cookies_with_csrf(
            response=response,
            access_token=access_token_str,
            refresh_token_obj=refresh_token_obj,
            keep_me_logged_in=True
        )
        ```
        
    Security Notes:
        - Access and refresh tokens are HttpOnly for XSS protection
        - CSRF token is NOT HttpOnly so JavaScript can read it
        - All cookies use same domain, secure, and SameSite settings
        - Token expiration times are consistent across all cookies
    """
    # Generate CSRF token
    csrf_token = generate_csrf_token()
    
    # Calculate expiration times
    access_token_max_age = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    
    # Set access token cookie (HttpOnly)
    response.set_cookie(
        key=settings.ACCESS_TOKEN_COOKIE_NAME,
        value=access_token,
        max_age=access_token_max_age,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=settings.COOKIE_HTTPONLY,
        samesite=settings.COOKIE_SAMESITE,
        path="/"
    )
    
    # Set refresh token cookie if provided (HttpOnly)
    if refresh_token_obj and keep_me_logged_in:
        refresh_token_max_age = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        response.set_cookie(
            key=settings.REFRESH_COOKIE_NAME,
            value=str(refresh_token_obj.token),
            max_age=refresh_token_max_age,
            domain=settings.COOKIE_DOMAIN,
            secure=settings.COOKIE_SECURE,
            httponly=settings.COOKIE_HTTPONLY,
            samesite=settings.COOKIE_SAMESITE,
            path="/"
        )
    else:
        # Clear refresh token cookie
        response.set_cookie(
            key=settings.REFRESH_COOKIE_NAME,
            value="",
            max_age=0,
            expires=0,
            domain=settings.COOKIE_DOMAIN,
            secure=settings.COOKIE_SECURE,
            httponly=settings.COOKIE_HTTPONLY,
            samesite=settings.COOKIE_SAMESITE,
            path="/"
        )
    
    # Set CSRF token cookie (NOT HttpOnly - JavaScript needs to read it)
    # CSRF token expires with access token for consistency
    set_csrf_cookie(response, csrf_token, access_token_max_age)
    
    auth_logger.info("Authentication cookies set up successfully with CSRF protection")
    return csrf_token


def clear_auth_cookies(response: Response) -> None:
    """
    Clear all authentication cookies including CSRF token.
    
    This function provides a centralized way to clear all authentication-related
    cookies when a user logs out or when authentication fails. It handles:
    - Access token cookie
    - Refresh token cookie  
    - CSRF token cookie
    
    Args:
        response: FastAPI Response object to clear cookies from
        
    Usage:
        Used during logout or authentication failure:
        ```python
        clear_auth_cookies(response)
        ```
        
    Note:
        - Must match exact same attributes used when setting cookies
        - Uses both max_age=0 and expires=0 for reliable deletion
        - Clears all cookies even if some weren't set (safe operation)
    """
    # Clear access token cookie
    response.set_cookie(
        key=settings.ACCESS_TOKEN_COOKIE_NAME,
        value="",
        max_age=0,
        expires=0,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=settings.COOKIE_HTTPONLY,
        samesite=settings.COOKIE_SAMESITE,
        path="/"
    )
    
    # Clear refresh token cookie
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value="",
        max_age=0,
        expires=0,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=settings.COOKIE_HTTPONLY,
        samesite=settings.COOKIE_SAMESITE,
        path="/"
    )
    
    # Clear CSRF token cookie
    delete_csrf_cookie(response)
    
    auth_logger.info("All authentication cookies cleared")
