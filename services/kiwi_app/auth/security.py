import os
from typing_extensions import Annotated, Doc
import uuid
import logging # Import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any, Dict, List, cast

import jwt # Using PyJWT now
from jwt import PyJWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes, OAuth2AuthorizationCodeBearer, OAuth2
from pydantic import ValidationError, EmailStr

from kiwi_app.settings import settings
from kiwi_app.auth.schemas import TokenData
from kiwi_app.auth.exceptions import CredentialsException
from kiwi_app.auth.constants import Permissions, get_permission_description
from kiwi_app.auth.utils import auth_logger # Import the specific logger

# Get a logger for this module
# logger = logging.getLogger(__name__)

# Password Hashing Context
# Using bcrypt as the scheme
# TODO: FIXME: bcrypt is Acceptable password hashing for your software and your servers (but you should really use argon2id or scrypt)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


# --- Custom OAuth2 Password Bearer with Refresh URL --- #

# from fastapi.openapi.models import OAuthFlows as OAuthFlowsModel
# from fastapi.security.utils import get_authorization_scheme_param
# from starlette.requests import Request
# from starlette.status import HTTP_401_UNAUTHORIZED

# class OAuth2PasswordBearerRefreshCustom(OAuth2):
#     def __init__(
#         self,
#         tokenUrl: Annotated[
#             str,
#             Doc(
#                 """
#                 The URL to obtain the OAuth2 token. This would be the *path operation*
#                 that has `OAuth2PasswordRequestForm` as a dependency.
#                 """
#             ),
#         ],
#         refreshUrl: Annotated[
#             Optional[str],
#             Doc(
#                 """
#                 The URL to refresh the token and obtain a new one.
#                 """
#             ),
#         ] = None,
#         scheme_name: Annotated[
#             Optional[str],
#             Doc(
#                 """
#                 Security scheme name.

#                 It will be included in the generated OpenAPI (e.g. visible at `/docs`).
#                 """
#             ),
#         ] = None,
#         scopes: Annotated[
#             Optional[Dict[str, str]],
#             Doc(
#                 """
#                 The OAuth2 scopes that would be required by the *path operations* that
#                 use this dependency.
#                 """
#             ),
#         ] = None,
#         description: Annotated[
#             Optional[str],
#             Doc(
#                 """
#                 Security scheme description.

#                 It will be included in the generated OpenAPI (e.g. visible at `/docs`).
#                 """
#             ),
#         ] = None,
#         auto_error: Annotated[
#             bool,
#             Doc(
#                 """
#                 By default, if no HTTP Authorization header is provided, required for
#                 OAuth2 authentication, it will automatically cancel the request and
#                 send the client an error.

#                 If `auto_error` is set to `False`, when the HTTP Authorization header
#                 is not available, instead of erroring out, the dependency result will
#                 be `None`.

#                 This is useful when you want to have optional authentication.

#                 It is also useful when you want to have authentication that can be
#                 provided in one of multiple optional ways (for example, with OAuth2
#                 or in a cookie).
#                 """
#             ),
#         ] = True,
#     ):
#         if not scopes:
#             scopes = {}
#         flows = OAuthFlowsModel(
#             password=cast(Any, {"tokenUrl": tokenUrl, "scopes": scopes, "refreshUrl": refreshUrl})
#         )
#         super().__init__(
#             flows=flows,
#             scheme_name=scheme_name,
#             description=description,
#             auto_error=auto_error,
#         )

#     async def __call__(self, request: Request) -> Optional[str]:
#         authorization = request.headers.get("Authorization")
#         scheme, param = get_authorization_scheme_param(authorization)
#         if not authorization or scheme.lower() != "bearer":
#             if self.auto_error:
#                 raise HTTPException(
#                     status_code=HTTP_401_UNAUTHORIZED,
#                     detail="Not authenticated",
#                     headers={"WWW-Authenticate": "Bearer"},
#                 )
#             else:
#                 return None
#         return param




# OAuth2 Scheme
# tokenUrl points to the endpoint that issues the token
# Scopes are defined based on our Permissions enum
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=settings.API_V1_PREFIX + settings.AUTH_TOKEN_URL,
    # scopes don't make any sense here, there are on ORG level!
    # scopes={perm.value: get_permission_description(perm) for perm in Permissions}
)

# # OAuth2 Authorization Code Bearer
# oauth2_scheme = OAuth2PasswordBearerRefreshCustom(
#     # authorizationUrl=settings.API_V1_PREFIX + settings.AUTH_TOKEN_URL,
#     tokenUrl=settings.API_V1_PREFIX + settings.AUTH_TOKEN_URL,
#     refreshUrl=settings.API_V1_PREFIX + settings.AUTH_REFRESH_URL,
# )

# JWT Configuration
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES

def verify_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    """
    Verifies a plain password against its hashed version.
    Handles cases where hashed_password might be None (e.g., OAuth-only users).
    """
    if hashed_password is None:
        return False # No password set for this user
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    Hashes a plain password using the configured context.

    Args:
        password: The plain password to hash.

    Returns:
        The hashed password string.
    """
    return pwd_context.hash(password)

def create_access_token(
    subject: Union[str, Any], # Subject is now UUID
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[Dict[str, Any]] = None
) -> str:
    """
    Creates a JWT access token.

    Args:
        subject: The subject of the token (user ID - UUID).
        expires_delta: Optional timedelta for token expiration.
        additional_claims: Optional dictionary of extra data to include in the payload.

    Returns:
        The encoded JWT access token string.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # Convert UUID subject to string for JWT standard compatibility
    subject_str = str(subject)

    to_encode = {
        "exp": expire,
        "sub": subject_str,
    }
    if additional_claims:
        to_encode.update(additional_claims)

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> TokenData:
    """
    Decodes a JWT access token and validates its claims using PyJWT.

    Args:
        token: The encoded JWT access token string.

    Raises:
        CredentialsException: If the token is invalid, expired, or claims are malformed.

    Returns:
        The validated token data (payload) as a TokenData object.
    """
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            # options={"verify_aud": False} # Add audience verification if needed
        )

        # PyJWT raises specific exceptions for expiration, invalid signature etc.

        # Extract claims
        token_sub_str: Optional[str] = payload.get("sub")
        token_password_reset: Optional[bool] = payload.get("password_reset", None)
        if token_sub_str is None:
            raise CredentialsException(detail="Token subject (sub) is missing.")

        # Convert subject back to UUID
        try:
            token_sub_uuid = uuid.UUID(token_sub_str)
        except ValueError:
            auth_logger.warning(f"Invalid UUID format in token subject: {token_sub_str}")
            raise CredentialsException(detail="Invalid subject (sub) format in token.")

        # Validate expiration (PyJWT does this, but double-checking doesn't hurt if needed)
        # ... (expiration check commented out as PyJWT handles it)

        # Use Pydantic model for validation of expected structure
        # Pass only the sub field now
        token_data = TokenData(sub=token_sub_uuid, password_reset=token_password_reset)

    except jwt.ExpiredSignatureError:
        auth_logger.info(f"Attempted use of expired token. Sub: {payload.get('sub', 'N/A') if 'payload' in locals() else 'ErrorBeforePayload'}")
        raise CredentialsException(detail="Token has expired.")
    except jwt.InvalidTokenError as e:
        auth_logger.warning(f"Invalid JWT token error: {e}", exc_info=True)
        raise CredentialsException(detail=f"Could not validate credentials: Invalid token ({e})")
    except (ValidationError, Exception) as e:
        auth_logger.error(f"Unexpected token decode error: {e}", exc_info=True)
        raise CredentialsException(detail=f"Could not validate credentials: {e}")

    return token_data

# --- Dependency for checking Scopes/Permissions --- #

# REMOVED - check_scopes function is no longer needed as scopes are not in JWT
# async def check_scopes(...) 
