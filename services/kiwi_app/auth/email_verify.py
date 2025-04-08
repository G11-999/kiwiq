import uuid
import smtplib # Import smtplib
import ssl # Import SSL for STARTTLS
from email.message import EmailMessage # Import EmailMessage
from typing import Optional
from datetime import datetime, timedelta, timezone # Import datetime utilities

from fastapi import BackgroundTasks
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select # Keep select for user lookup by ID

# from global_config.settings import LOG_ROOT
from kiwi_app.settings import settings

from kiwi_app.auth import models, crud, schemas
from kiwi_app.auth.utils import auth_logger
# Import JWT functions and exception
from kiwi_app.auth.security import create_access_token, decode_access_token
from kiwi_app.auth.exceptions import CredentialsException
# Import TokenData schema to check for password_reset claim
from kiwi_app.auth.schemas import TokenData


# Get loggers for different parts of a hypothetical application


# --- Email Verification Utilities --- #

# EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES = settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES # Setting used directly now
# EMAIL_FROM_ADDRESS is now handled by ConnectionConfig

# Removed generate_verification_token() as JWT creation handles uniqueness and expiry.

# def generate_verification_token() -> str:
#     """
#     Generates a secure, unique token for email verification.
#
#     Returns:
#         A unique string token.
#     """
#     return str(uuid.uuid4())

# TODO: CRITICAL: FIXME: change URLs to not redirect customers to API but the SPA and SPA can call backend for verification!

def send_verification_email_sync(
    email_to: EmailStr,
    username: Optional[str],
    verification_link: str
):
    """
    Synchronous function to construct and send the verification email.
    Designed to be run in a background task.

    Args:
        email_to: The recipient's email address.
        username: The recipient's name (for personalization).
        verification_link: The full URL the user needs to click (contains JWT).
    """
    # Check if essential mail server settings are configured
    # Simplified the check slightly
    # RB Corx: REMOVED Check - This check is already done in the calling function `trigger_send_verification_email`
    # if not all([
    #     settings.GMAIL_SMTP_SERVER,
    #     settings.GMAIL_SMTP_PORT,
    #     settings.GMAIL_SMTP_FROM
    #     # Credentials might be optional depending on server/method
    # ]) or (settings.USE_CREDENTIALS and not all([settings.GMAIL_SMTP_USERNAME, settings.GMAIL_SMTP_PASSWORD])):
    #     auth_logger.warning("Mail server details not fully configured in settings or USE_CREDENTIALS is True but credentials missing. Skipping email sending.")
    #     return

    message = EmailMessage()
    message["To"] = email_to
    # Ensure MAIL_FROM_NAME is used if available, otherwise default to the from address
    from_name = settings.MAIL_FROM_NAME or settings.GMAIL_SMTP_FROM
    message["From"] = f"{from_name} <{settings.GMAIL_SMTP_FROM}>"
    message["Subject"] = "Verify Your Email Address for KiwiQ"

    # Simple HTML body
    user_greeting = f" {username}" if username else ""
    html_body = f"""
    <html>
      <body>
        <p>Hi{user_greeting},</p>
        <p>Thank you for registering with KiwiQ!</p>
        <p>Please click the link below to verify your email address:</p>
        <p><a href="{verification_link}">{verification_link}</a></p>
        <p>This link will expire in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES} minutes.</p>
        <p>If you did not request this, please ignore this email.</p>
        <p>Thanks,<br>The KiwiQ Team</p>
      </body>
    </html>
    """
    message.set_content("Please enable HTML emails to view this message.") # Plain text fallback
    message.add_alternative(html_body, subtype="html")

    # Connect to SMTP server and send
    # Use SSL context for security
    context = ssl.create_default_context()
    server = None # Initialize server to None for finally block

    try:
        auth_logger.debug(f"Attempting to send verification email to {email_to} via {settings.GMAIL_SMTP_SERVER}:{settings.GMAIL_SMTP_PORT}")
        # Choose connection type based on settings
        if settings.MAIL_SSL_TLS:
            # Use SMTP_SSL for implicit TLS (usually port 465)
            auth_logger.debug("Connecting using SMTP_SSL (implicit TLS)...")
            server = smtplib.SMTP_SSL(settings.GMAIL_SMTP_SERVER, settings.GMAIL_SMTP_PORT, context=context)
        else:
            # Use standard SMTP (usually port 587 or 25)
            auth_logger.debug("Connecting using standard SMTP...")
            server = smtplib.SMTP(settings.GMAIL_SMTP_SERVER, settings.GMAIL_SMTP_PORT)
            if settings.MAIL_STARTTLS:
                # Secure the connection with STARTTLS
                auth_logger.debug("Attempting STARTTLS...")
                server.starttls(context=context)
                auth_logger.debug("STARTTLS successful.")

        # Login if credentials are provided and required by settings
        if settings.USE_CREDENTIALS and settings.GMAIL_SMTP_USERNAME and settings.GMAIL_SMTP_PASSWORD:
            auth_logger.debug(f"Logging in as {settings.GMAIL_SMTP_USERNAME}...")
            server.login(settings.GMAIL_SMTP_USERNAME, settings.GMAIL_SMTP_PASSWORD)
            auth_logger.debug("SMTP login successful.")
        else:
             auth_logger.debug("Skipping SMTP login (USE_CREDENTIALS is False or credentials not set).")

        # Send the email
        server.send_message(message)
        auth_logger.info(f"Verification email successfully sent to {email_to}")

    except smtplib.SMTPAuthenticationError as e:
         auth_logger.error(f"SMTP Authentication Error for {settings.GMAIL_SMTP_USERNAME}: {e}", exc_info=True)
    except smtplib.SMTPException as e:
        # Log specific SMTP errors
        auth_logger.error(f"SMTP Error sending verification email to {email_to}: {e}", exc_info=True)
        # Consider adding more specific error handling or re-queueing logic here
    except Exception as e:
        # Catch any other unexpected errors during email sending
        auth_logger.error(f"Unexpected error sending verification email to {email_to}: {e}", exc_info=True)
    finally:
        if server:
            try:
                # Always try to quit the server connection gracefully
                server.quit()
                auth_logger.debug("SMTP server connection closed.")
            except Exception as e:
                # Log if quitting fails, but don't raise further errors
                auth_logger.warning(f"Error quitting SMTP server connection: {e}", exc_info=True)


async def trigger_send_verification_email(
    background_tasks: BackgroundTasks, # Use FastAPI BackgroundTasks
    db: AsyncSession,
    # user_dao: crud.UserDAO, # DAO no longer needed to save token
    user: models.User,
    base_url: str
) -> Optional[str]:
    """
    Generates a JWT verification token, constructs the link,
    and adds the actual email sending to background tasks.
    The token itself is NOT saved to the database.

    Args:
        background_tasks: FastAPI BackgroundTasks instance.
        db: The database session (kept for potential future use, but not used currently).
        user: The user object.
        base_url: Base URL for link generation.

    Returns:
        The verification JWT if generated, otherwise None.
    """
    if user.is_verified:
        auth_logger.debug(f"User {user.email} ({user.id}) is already verified. No verification email needed.")
        return None

    # Generate JWT for email verification
    try:
        # Set expiry time from settings
        expires_delta = timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES)
        # Create JWT with user ID as subject
        # No additional claims needed for verification currently
        token = create_access_token(subject=user.id, expires_delta=expires_delta)
        auth_logger.debug(f"Generated verification JWT for user {user.email} ({user.id}). Expires in {expires_delta}.")
    except Exception as e:
        # Catch potential errors during JWT creation (e.g., config issues)
        auth_logger.error(f"Error generating verification JWT for {user.email}: {e}", exc_info=True)
        return None # Cannot proceed without a token

    # Removed database update for saving token
    # try:
    #     await user_dao.update(db, db_obj=user, obj_in=schemas.UserAdminUpdate(email_verification_token=token))
    # except Exception as e:
    #     auth_logger.error(f"DB Error saving verification token for {user.email}: {e}", exc_info=True)
    #     return None # Don't proceed if token couldn't be saved

    # Construct the verification URL with the JWT
    URL = f"{base_url.rstrip('/')}{settings.API_V1_PREFIX}{settings.AUTH_VERIFY_EMAIL_URL}"
    verification_link = f"{URL}?token={token}"
    if settings.VERIFY_EMAIL_SPA_URL:
        verification_link = f"{settings.VERIFY_EMAIL_SPA_URL}?token={token}"

    # Check if mail is configured before adding task
    # Simplified the check slightly
    if not all([
        settings.GMAIL_SMTP_SERVER,
        settings.GMAIL_SMTP_PORT,
        settings.GMAIL_SMTP_FROM
    ]) or (settings.USE_CREDENTIALS and not all([settings.GMAIL_SMTP_USERNAME, settings.GMAIL_SMTP_PASSWORD])):
         auth_logger.warning(f"Mail not configured, skipping background task for {user.email}. Token generated but not sent.")
         # Still return the token - useful for testing or manual verification if needed
         return token

    # Add the synchronous email sending function to background tasks
    background_tasks.add_task(
        send_verification_email_sync,
        email_to=user.email,
        username=user.full_name, # Pass user's name for personalization
        verification_link=verification_link
    )
    auth_logger.info(f"Verification email task added for {user.email} ({user.id})")

    return token # Return the generated JWT

async def verify_email_token(db: AsyncSession, token: str) -> Optional[models.User]:
    """
    Validates an email verification JWT and finds the corresponding user.
    Checks token signature, expiry, and extracts user ID from the subject ('sub') claim.

    Args:
        db: Database session, used to fetch the user by ID.
        token: The email verification JWT string.

    Returns:
        The verified user object if the token is valid and the user exists, otherwise None.
    """
    if not token:
        auth_logger.debug("Verification attempt with empty token.")
        return None

    try:
        # Decode and validate the JWT using the security utility
        # This handles signature verification and expiry check
        token_data = decode_access_token(token)
        user_id = token_data.sub # Extract user ID (UUID) from 'sub' claim

        if not user_id:
             # Should not happen if decode_access_token works correctly, but good to check
             auth_logger.error("Token decoded successfully but 'sub' claim (user_id) is missing.")
             return None

        auth_logger.debug(f"Successfully decoded verification token for user ID: {user_id}")

        # Find the user in the database by the ID from the token
        result = await db.execute(
            select(models.User).where(models.User.id == user_id)
        )
        user = result.scalars().first()

        if not user:
            # This could happen if the user was deleted after the token was issued
            auth_logger.warning(f"Verification token is valid for user ID {user_id}, but user not found in DB.")
            return None

        # Optional: Add check if user is already verified?
        # if user.is_verified:
        #     auth_logger.info(f"User {user.email} ({user_id}) is already verified. Verification via token successful but redundant.")
        #     # Return the user anyway, the endpoint handler can decide what to do

        auth_logger.info(f"Email verification successful for user {user.email} ({user_id}) via JWT.")
        return user

    except CredentialsException as e:
        # Handle specific exceptions from decode_access_token (e.g., expired, invalid signature)
        auth_logger.warning(f"Invalid or expired email verification token provided: {e.detail}")
        # Log first few chars of token for debugging without exposing full token
        auth_logger.debug(f"Token (start): {token[:10]}...")
        return None
    except Exception as e:
        # Catch unexpected database or other errors
        auth_logger.error(f"Unexpected error during email token verification: {e}", exc_info=True)
        return None 


# --- Password Reset Email Utilities --- #

def send_password_reset_email_sync(
    email_to: EmailStr,
    username: Optional[str],
    reset_link: str
):
    """
    Synchronous function to construct and send the password reset email.
    Designed to be run in a background task.

    Args:
        email_to: The recipient's email address.
        username: The recipient's name (for personalization).
        reset_link: The full URL the user needs to click (contains password reset JWT).
    """
    # Configuration check (already done in trigger function)

    message = EmailMessage()
    message["To"] = email_to
    from_name = settings.MAIL_FROM_NAME or settings.GMAIL_SMTP_FROM
    message["From"] = f"{from_name} <{settings.GMAIL_SMTP_FROM}>"
    message["Subject"] = "Reset Your KiwiQ Password"

    user_greeting = f" {username}" if username else ""
    html_body = f"""
    <html>
      <body>
        <p>Hi{user_greeting},</p>
        <p>We received a request to reset your password for your KiwiQ account.</p>
        <p>Please click the link below to set a new password:</p>
        <p><a href="{reset_link}">{reset_link}</a></p>
        <p>This link will expire in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.</p>
        <p>If you did not request a password reset, please ignore this email or contact support if you have concerns.</p>
        <p>Thanks,<br>The KiwiQ Team</p>
      </body>
    </html>
    """
    message.set_content("Please enable HTML emails to view this message.") # Plain text fallback
    message.add_alternative(html_body, subtype="html")

    # Connect and send (identical logic to send_verification_email_sync)
    context = ssl.create_default_context()
    server = None
    try:
        auth_logger.debug(f"Attempting to send password reset email to {email_to} via {settings.GMAIL_SMTP_SERVER}:{settings.GMAIL_SMTP_PORT}")
        if settings.MAIL_SSL_TLS:
            server = smtplib.SMTP_SSL(settings.GMAIL_SMTP_SERVER, settings.GMAIL_SMTP_PORT, context=context)
        else:
            server = smtplib.SMTP(settings.GMAIL_SMTP_SERVER, settings.GMAIL_SMTP_PORT)
            if settings.MAIL_STARTTLS:
                server.starttls(context=context)

        if settings.USE_CREDENTIALS and settings.GMAIL_SMTP_USERNAME and settings.GMAIL_SMTP_PASSWORD:
            server.login(settings.GMAIL_SMTP_USERNAME, settings.GMAIL_SMTP_PASSWORD)

        server.send_message(message)
        auth_logger.info(f"Password reset email successfully sent to {email_to}")

    except smtplib.SMTPAuthenticationError as e:
         auth_logger.error(f"SMTP Authentication Error for {settings.GMAIL_SMTP_USERNAME}: {e}", exc_info=True)
    except smtplib.SMTPException as e:
        auth_logger.error(f"SMTP Error sending password reset email to {email_to}: {e}", exc_info=True)
    except Exception as e:
        auth_logger.error(f"Unexpected error sending password reset email to {email_to}: {e}", exc_info=True)
    finally:
        if server:
            try:
                server.quit()
            except Exception as e:
                auth_logger.warning(f"Error quitting SMTP server connection: {e}", exc_info=True)

async def trigger_send_password_reset_email(
    background_tasks: BackgroundTasks,
    # db: AsyncSession, # No DB needed here
    user: models.User,
    base_url: str
) -> Optional[str]:
    """
    Generates a short-lived JWT for password reset, constructs the link,
    and adds the actual email sending to background tasks.

    Args:
        background_tasks: FastAPI BackgroundTasks instance.
        user: The user object.
        base_url: Base URL for link generation (e.g., frontend URL).

    Returns:
        The password reset JWT if generated and email task added, otherwise None.
    """
    # Generate JWT specifically for password reset
    try:
        expires_delta = timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
        # Add the password_reset claim
        additional_claims = {"password_reset": True}
        token = create_access_token(
            subject=user.id,
            expires_delta=expires_delta,
            additional_claims=additional_claims
        )
        auth_logger.debug(f"Generated password reset JWT for user {user.email} ({user.id}). Expires in {expires_delta}.")
    except Exception as e:
        auth_logger.error(f"Error generating password reset JWT for {user.email}: {e}", exc_info=True)
        return None

    # Construct the reset link (likely pointing to a frontend page)
    # Example: http://frontend.com/reset-password?token=JWT_HERE
    # The frontend will then use this token to call the backend /reset-password endpoint.
    # ADJUST THE BASE_URL/PATH AS NEEDED FOR YOUR FRONTEND ROUTING
    URL = f"{base_url.rstrip('/')}{settings.API_V1_PREFIX}{settings.AUTH_VERIFY_PASSWORD_RESET_TOKEN_URL}"
    reset_link = f"{URL}?token={token}"
    if settings.VERIFY_PASSWORD_RESET_TOKEN_SPA_URL:
        reset_link = f"{settings.VERIFY_PASSWORD_RESET_TOKEN_SPA_URL}?token={token}"
    # If no frontend, you could link directly to the verify endpoint:
    # reset_link = f"{base_url.rstrip('/')}{settings.API_V1_PREFIX}{settings.AUTH_VERIFY_PASSWORD_RESET_TOKEN_URL}?token={token}"

    # Check mail config
    if not all([
        settings.GMAIL_SMTP_SERVER,
        settings.GMAIL_SMTP_PORT,
        settings.GMAIL_SMTP_FROM
    ]) or (settings.USE_CREDENTIALS and not all([settings.GMAIL_SMTP_USERNAME, settings.GMAIL_SMTP_PASSWORD])):
         auth_logger.warning(f"Mail not configured, skipping password reset background task for {user.email}. Token generated but not sent.")
         return token # Return token for testing/manual use

    # Add the sync email sending task
    background_tasks.add_task(
        send_password_reset_email_sync,
        email_to=user.email,
        username=user.full_name,
        reset_link=reset_link
    )
    auth_logger.info(f"Password reset email task added for {user.email} ({user.id})")

    return token

async def verify_password_reset_token(token: str) -> TokenData:
    """
    Validates a password reset JWT.
    Checks signature, expiry, and presence of 'password_reset: True' claim.

    Args:
        token: The password reset JWT string.

    Returns:
        The validated TokenData containing user ID and password_reset flag.

    Raises:
        CredentialsException: If the token is invalid, expired, malformed, or not
                              specifically for password reset.
    """
    if not token:
        raise CredentialsException(detail="Password reset token is missing.")

    try:
        # Decode and validate the JWT (handles signature, expiry)
        token_data = decode_access_token(token)

        # Crucially, check if this token was intended for password reset
        if not token_data.password_reset:
            auth_logger.warning(f"Token valid but not marked for password reset. User ID: {token_data.sub}")
            raise CredentialsException(detail="Invalid token type. Not for password reset.")

        auth_logger.info(f"Password reset token successfully verified for user ID: {token_data.sub}")
        return token_data

    except CredentialsException as e:
        # Re-raise specific exceptions from decode_access_token or our check
        auth_logger.warning(f"Invalid or expired password reset token provided: {e.detail}")
        auth_logger.debug(f"Token (start): {token[:10]}...")
        raise e # Re-raise the specific CredentialsException
    except Exception as e:
        # Catch unexpected errors
        auth_logger.error(f"Unexpected error during password reset token verification: {e}", exc_info=True)
        raise CredentialsException(detail="Could not validate password reset token due to an internal error.") 