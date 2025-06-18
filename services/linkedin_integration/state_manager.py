"""
LinkedIn OAuth State Manager

This module provides utilities for managing OAuth state tokens using JWT,
following KiwiQ's established patterns for secure token handling.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import uuid

from kiwi_app.auth import security
from kiwi_app.auth.schemas import TokenData
from kiwi_app.auth.exceptions import CredentialsException
from kiwi_app.utils import get_kiwi_logger
from kiwi_app.settings import settings

logger = get_kiwi_logger("linkedin_integration.state_manager")


class LinkedInStateManager:
    """
    Manages OAuth state tokens for LinkedIn integration.
    
    This class provides methods to create and verify state tokens used
    during the OAuth flow for CSRF protection and session management.
    """
    
    # Token expiration times
    STATE_TOKEN_EXPIRE_MINUTES = 10  # Short-lived for OAuth flow
    OAUTH_SESSION_TOKEN_EXPIRE_MINUTES = 30  # Longer for incomplete flows
    
    @classmethod
    def create_state_token(
        cls,
        user_id: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a state token for OAuth flow.
        
        Args:
            user_id: Optional user ID for logged-in flows
            additional_data: Optional additional data to include in token
            
        Returns:
            Encoded JWT state token
        """
        # Generate unique identifier for this OAuth attempt
        state_id = str(uuid.uuid4())
        
        token_data = {
            "state_id": state_id,
            "logged_in_flow": user_id is not None
        }
        
        if user_id:
            token_data["user_id"] = user_id
            
        if additional_data:
            token_data.update(additional_data)
        
        # Create token with short expiration
        token = security.create_access_token(
            subject=state_id,
            expires_delta=timedelta(minutes=cls.STATE_TOKEN_EXPIRE_MINUTES),
            additional_claims=token_data,
            token_type="oauth_state"
        )
        
        logger.debug(f"Created OAuth state token: {state_id}")
        return token
    
    @classmethod
    def verify_state_token(cls, state_token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode an OAuth state token.
        
        Args:
            state_token: The state token to verify
            
        Returns:
            Decoded token data if valid, None otherwise
        """
        try:
            # Decode and validate the token
            token_data = security.decode_access_token(
                state_token,
                expected_token_type="oauth_state"
            )
            
            # Extract claims
            claims = {
                "state_id": str(token_data.sub),
                **token_data.additional_claims,
                "csrf_token": token_data.csrf_token,
            }
            
            logger.debug(f"Verified OAuth state token: {claims.get('state_id')}")
            return claims
            
        except CredentialsException as e:
            logger.warning(f"Invalid state token: {e.detail}")
            return None
        except Exception as e:
            logger.error(f"Error verifying state token: {e}")
            return None
    
    @classmethod
    def create_oauth_session_token(
        cls,
        linkedin_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        email_verified: bool = False
    ) -> str:
        """
        Create a longer-lived session token for incomplete OAuth flows.
        
        This token is used when additional user action is required after
        the initial OAuth callback (e.g., registration, verification).
        It only contains non-sensitive information, referencing the full
        OAuth data stored in the database via the linkedin_id.
        
        Args:
            linkedin_id: LinkedIn user ID (sub), references the DB record
            email: User's email from LinkedIn
            name: User's name from LinkedIn
            email_verified: Whether email is verified by LinkedIn
            
        Returns:
            Encoded JWT session token
        """
        token_data = {
            "email": email,
            "name": name,
            "email_verified": email_verified,
        }
        
        # Create token with longer expiration for incomplete flows
        token = security.create_access_token(
            subject=linkedin_id,
            expires_delta=timedelta(minutes=cls.OAUTH_SESSION_TOKEN_EXPIRE_MINUTES),
            additional_claims=token_data,
            token_type="oauth_session"
        )
        
        logger.debug(f"Created OAuth session token for LinkedIn ID: {linkedin_id}")
        return token
    
    @classmethod
    def verify_oauth_session_token(cls, session_token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode an OAuth session token.
        
        Args:
            session_token: The session token to verify
            
        Returns:
            Decoded token data if valid, None otherwise
        """
        try:
            # Decode and validate the token
            token_data = security.decode_access_token(
                session_token,
                expected_token_type="oauth_session"
            )
            
            # Extract claims
            claims = {
                "linkedin_id": str(token_data.sub),
                **token_data.additional_claims,
                "csrf_token": token_data.csrf_token,
            }
            
            logger.debug(f"Verified OAuth session token for LinkedIn ID: {claims.get('linkedin_id')}")
            return claims
            
        except CredentialsException as e:
            logger.warning(f"Invalid session token: {e.detail}")
            return None
        except Exception as e:
            logger.error(f"Error verifying session token: {e}")
            return None
    
    @classmethod
    def create_email_verification_token(
        cls,
        user_id: str,
        email: str,
        linkedin_id: str,
        csrf_token: str
    ) -> str:
        """
        Create a token for email verification in LinkedIn OAuth flow.
        
        Args:
            user_id: KIWIQ user ID
            email: Email to verify
            linkedin_id: LinkedIn ID to link after verification
            csrf_token: The CSRF token to embed in the JWT for validation.
            
        Returns:
            Encoded JWT verification token
        """
        token_data = {
            "user_id": user_id,
            "email": email,
            "linkedin_id": linkedin_id,
            "csrf_token": csrf_token,
            "purpose": "linkedin_email_verification"
        }
        
        # Use same expiration as regular email verification
        token = security.create_access_token(
            subject=user_id,
            expires_delta=timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES),
            additional_claims=token_data,
            token_type="linkedin_verification"
        )
        
        logger.debug(f"Created email verification token for LinkedIn flow: {user_id}")
        return token
    
    @classmethod
    def verify_email_verification_token(cls, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode a LinkedIn email verification token.
        
        Args:
            token: The verification token to verify
            
        Returns:
            Decoded token data if valid, None otherwise
        """
        try:
            token_data = security.decode_access_token(
                token,
                expected_token_type="linkedin_verification"
            )
            
            claims = {
                "user_id": str(token_data.sub),
                **token_data.additional_claims,
                "csrf_token": token_data.csrf_token,
            }
            
            logger.debug(f"Verified LinkedIn email verification token for user: {claims.get('user_id')}")
            return claims
            
        except CredentialsException as e:
            logger.warning(f"Invalid LinkedIn email verification token: {e.detail}")
            return None
        except Exception as e:
            logger.error(f"Error verifying LinkedIn email verification token: {e}")
            return None 