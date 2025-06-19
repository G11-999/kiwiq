"""
LinkedIn OAuth Service Layer

This module implements the business logic for LinkedIn OAuth operations,
following KiwiQ's established service patterns with dependency injection.
"""

import asyncio
import uuid
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status, BackgroundTasks, Request

from kiwi_app.auth.models import User
from kiwi_app.auth.services import AuthService
from kiwi_app.auth import crud as auth_crud
from kiwi_app.auth import schemas as auth_schemas
from kiwi_app.auth.csrf import generate_csrf_token, setup_auth_cookies_with_csrf, validate_csrf_token
from kiwi_app.auth import security
from kiwi_app.auth.exceptions import CredentialsException
from kiwi_app.utils import get_kiwi_logger
from kiwi_app.settings import settings
from kiwi_app.email import email_verify
from kiwi_app.email.email_dispatch import email_dispatch, EmailContent, EmailRecipient
from kiwi_app.email.email_templates.renderer import EmailRenderer, AccountConfirmationEmailData
from global_utils import datetime_now_utc

from linkedin_integration.client.linkedin_auth_client import LinkedInAccessTokenSchema, AuthClient, LINKEDIN_SCOPES
from linkedin_integration.client.linkedin_client import LinkedInClient, UserInfo, OrganizationRolesResponse, OrganizationRolesResponse, LinkedinOrganization, LinkedinMemberProfile

from linkedin_integration import crud, models, schemas, exceptions
from linkedin_integration.state_manager import LinkedInStateManager

logger = get_kiwi_logger("linkedin_integration.services")


class LinkedinOauthService:
    """
    Service layer for LinkedIn OAuth operations.
    
    This service handles the complete LinkedIn OAuth flow including:
    - OAuth authorization and callback processing
    - User registration and account linking
    - Token management and refresh
    - Profile synchronization
    """
    
    def __init__(
        self,
        linkedin_oauth_dao: crud.LinkedinOauthDAO,
        user_dao: auth_crud.UserDAO,
        org_dao: auth_crud.OrganizationDAO,
        auth_service: AuthService
    ):
        self.linkedin_oauth_dao = linkedin_oauth_dao
        self.user_dao = user_dao
        self.org_dao = org_dao
        self.auth_service = auth_service
        self.email_renderer = EmailRenderer()
    
    async def initiate_oauth_flow(
        self,
        redirect_uri: str,
        user_id: Optional[str] = None,
        csrf_token: Optional[str] = None,
    ) -> schemas.LinkedInInitiateResponse:
        """
        Generate the LinkedIn authorization URL for initiating the OAuth flow.
        
        The state token is embedded in the authorization URL for CSRF protection
        but is not returned to the client.
        """
        kwargs = {}
        if csrf_token:
            kwargs["additional_data"] = {"csrf_token": csrf_token}
        state_token = LinkedInStateManager.create_state_token(user_id=user_id, **kwargs)
        
        # The redirect URI must match what's configured in the LinkedIn App
        # and what will be used in the callback.
        

        auth_client = self._get_auth_client(redirect_uri=redirect_uri)
        
        # The library method handles URL encoding and construction.
        # authorization_url = auth_client.generate_member_auth_url(
        #     scopes=LINKEDIN_SCOPES,
        #     state=state_token
        # )
        authorization_url = await asyncio.to_thread(auth_client.generate_member_auth_url, scopes=LINKEDIN_SCOPES, state=state_token)
        
        logger.info(f"Generated LinkedIn auth URL for user: {user_id or 'anonymous'}")
        
        return schemas.LinkedInInitiateResponse(
            authorization_url=authorization_url
        )
    
    def _get_auth_client(self, redirect_uri: Optional[str] = None) -> AuthClient:
        """Initializes and returns a LinkedIn AuthClient."""
        return AuthClient(
            client_id=settings.LINKEDIN_CLIENT_ID,
            client_secret=settings.LINKEDIN_CLIENT_SECRET,
            redirect_url=redirect_uri
        )
    
    def _get_linkedin_client(self, access_token: str) -> LinkedInClient:
        """
        Create a LinkedIn API client with a specific access token.
        
        Args:
            access_token: The user's access token
            
        Returns:
            LinkedInClient configured with the access token
        """
        return LinkedInClient(
            client_id=settings.LINKEDIN_CLIENT_ID,
            client_secret=settings.LINKEDIN_CLIENT_SECRET,
            access_token=access_token
        )
    
    async def process_oauth_callback(
        self,
        db: AsyncSession,
        code: str,
        redirect_uri: str,
        state: Optional[str] = None,
        csrf_cookie: Optional[str] = None,
        error: Optional[str] = None,
        error_description: Optional[str] = None
    ) -> schemas.OauthCallbackResult:
        """
        Process LinkedIn OAuth callback.
        
        This method handles the OAuth callback from LinkedIn, including:
        - State token validation for CSRF protection
        - Authorization code exchange for tokens
        - User information retrieval
        - Account creation or linking based on the flow type
        
        Args:
            db: Database session
            code: Authorization code from LinkedIn
            redirect_uri: The redirect URI used in the initial auth request.
            state: State token for CSRF protection
            csrf_cookie: CSRF token from cookie
            error: Error code from LinkedIn (if authorization failed)
            error_description: Error description from LinkedIn
            
        Returns:
            OauthCallbackResult with action details and user information
            
        Raises:
            LinkedInOauthException: For OAuth-specific errors
            LinkedInStateException: For state token validation errors
        """
        # Handle OAuth errors from LinkedIn
        if error:
            logger.error(f"LinkedIn OAuth error: {error} - {error_description}")
            raise exceptions.LinkedInOauthException(
                f"LinkedIn authorization failed: {error}",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Verify state if provided
            state_data = None
            if state:
                state_data = LinkedInStateManager.verify_state_token(state)
                csrf_token = state_data.get("csrf_token")
                if csrf_token or csrf_cookie:
                    if not validate_csrf_token(csrf_cookie, csrf_token):
                        raise exceptions.LinkedInStateException(f"CSRF token mismatch: {'state token null' if csrf_token is None else ('csrf token mismatch' if csrf_cookie else 'csrf token null')}")
                if not state_data:
                    raise exceptions.LinkedInStateException()
            
            # Exchange code for tokens
            auth_client = self._get_auth_client(redirect_uri)
            token_response = await asyncio.to_thread(auth_client.exchange_auth_code_for_access_token, code)
            # token_response = auth_client.exchange_auth_code_for_access_token(code)
            
            if token_response.status_code != 200:
                logger.error(f"Token exchange failed: {str(token_response.response)}")
                raise exceptions.LinkedInOauthException(
                    "Failed to exchange authorization code",
                    status_code=status.HTTP_502_BAD_GATEWAY
                )
        
            token_data = LinkedInAccessTokenSchema(
                access_token=token_response.access_token,
                expires_in=token_response.expires_in,
                refresh_token=token_response.refresh_token,
                refresh_token_expires_in=token_response.refresh_token_expires_in,
                scope=token_response.scope,
                # _datetime_now_=datetime_now,
            )
            
            # Create LinkedIn client with user's access token
            linkedin_client = self._get_linkedin_client(token_data.access_token)
            
            # Get LinkedIn user info
            success, user_info = await linkedin_client.get_member_info_including_email()
            if not success:
                raise exceptions.LinkedInAPIException(
                    "Failed to retrieve LinkedIn user info"
                )
            
            # Log user info for debugging
            logger.info(f"LinkedIn user info retrieved: sub={user_info.sub}, email={user_info.email}, verified={user_info.email_verified}")
            
            # Check if this is a logged-in user flow
            if state_data and state_data.get("logged_in_flow"):
                return await self._handle_logged_in_user_flow(
                    db, user_info, token_data, state_data["user_id"]
                )
            
            # Standard OAuth flow for logged-out users
            return await self._handle_standard_oauth_flow(
                db, user_info, token_data
            )
            
        except exceptions.LinkedInOauthException:
            raise
        except Exception as e:
            logger.error(f"Error processing OAuth callback: {e}", exc_info=True)
            raise exceptions.LinkedInOauthException(
                "Failed to process OAuth callback",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    async def _handle_standard_oauth_flow(
        self,
        db: AsyncSession,
        user_info: UserInfo,
        token_data: LinkedInAccessTokenSchema
    ) -> schemas.OauthCallbackResult:
        """Handle standard OAuth flow for logged-out users."""
        
        # Check if LinkedIn account is already mapped
        existing_oauth = await self.linkedin_oauth_dao.get(
            db, user_info.sub
        )
        
        if existing_oauth:
            # LinkedIn account already mapped - login to that account
            user = await self.user_dao.get(db, existing_oauth.user_id)
            if not user:
                raise exceptions.LinkedInOauthException(
                    "Mapped user account not found",
                    status_code=status.HTTP_404_NOT_FOUND
                )
            
            # Update tokens
            await self.linkedin_oauth_dao.update_tokens(
                db,
                linkedin_id=user_info.sub,
                access_token=token_data.access_token,
                refresh_token=token_data.refresh_token,
                expires_in=token_data.expires_in,
                refresh_token_expires_in=token_data.refresh_token_expires_in
            )
            
            # Update state to ACTIVE
            await self.linkedin_oauth_dao.update_state(
                db,
                linkedin_id=user_info.sub,
                oauth_state=models.LinkedinOauthState.ACTIVE
            )
            
            logger.info(f"LinkedIn login successful for user: {user.email}")
            
            return schemas.OauthCallbackResult(
                success=True,
                action=schemas.OauthAction.LOGIN_SUCCESS,
                user=user,
                linkedin_oauth=existing_oauth,
                access_token=token_data.access_token,
                message="Successfully logged in with LinkedIn",
                requires_action=False
            )
        
        # No existing mapping - check email verification
        if user_info.email and user_info.email_verified:
            return await self._handle_verified_email_flow(
                db, user_info, token_data
            )
        else:
            return await self._handle_unverified_email_flow(
                db, user_info, token_data
            )
    
    async def _handle_verified_email_flow(
        self,
        db: AsyncSession,
        user_info: UserInfo,
        token_data: LinkedInAccessTokenSchema
    ) -> schemas.OauthCallbackResult:
        """Handle flow when LinkedIn email is verified."""
        
        # Check if KIWIQ account exists with this email
        existing_user = await self.user_dao.get_by_email(db, user_info.email)
        
        if existing_user:
            if not existing_user.is_active:
                logger.warning(f"LinkedIn login attempt for inactive user: {existing_user.email}")
                raise exceptions.LinkedInOauthException(
                    "This account is inactive. Please contact support.",
                    status_code=status.HTTP_403_FORBIDDEN
                )

            # Check if this user already has a different LinkedIn account linked
            existing_user_oauth = await self.linkedin_oauth_dao.get_by_user_id(db, existing_user.id)
            if existing_user_oauth and existing_user_oauth.id != user_info.sub:
                logger.warning(f"User {existing_user.email} already has different LinkedIn account linked")
                # We'll allow relinking to the new LinkedIn account
            
            # Link LinkedIn to existing account and login
            oauth_record = await self.linkedin_oauth_dao.create_or_update(
                db,
                linkedin_id=user_info.sub,
                user_id=existing_user.id,
                access_token=token_data.access_token,  # Should be encrypted
                refresh_token=token_data.refresh_token,
                scope=token_data.scope,
                expires_in=token_data.expires_in,
                refresh_token_expires_in=token_data.refresh_token_expires_in,
                oauth_state=models.LinkedinOauthState.ACTIVE
            )

            if not existing_user.is_verified:
                await self.user_dao.update(db, db_obj=existing_user, obj_in=auth_schemas.UserUpdate(is_verified=True))
            
            logger.info(f"LinkedIn account linked to existing user: {existing_user.email}")
            
            return schemas.OauthCallbackResult(
                success=True,
                action=schemas.OauthAction.ACCOUNT_LINKED,
                user=existing_user,
                linkedin_oauth=oauth_record,
                access_token=token_data.access_token,
                message="LinkedIn account linked to existing account",
                requires_action=False
            )
        else:
            # No existing account - prepare for registration by creating a pending record
            await self.linkedin_oauth_dao.create_or_update(
                db,
                linkedin_id=user_info.sub,
                access_token=token_data.access_token,
                refresh_token=token_data.refresh_token,
                scope=token_data.scope,
                expires_in=token_data.expires_in,
                refresh_token_expires_in=token_data.refresh_token_expires_in,
                oauth_state=models.LinkedinOauthState.REGISTRATION_REQUIRED,
                state_metadata={"reason": "new_user_registration"}
            )

            logger.info(f"New user registration required for email: {user_info.email}")
            
            return schemas.OauthCallbackResult(
                success=True,
                action=schemas.OauthAction.REGISTRATION_REQUIRED,
                message="Please complete registration",
                requires_action=True,
                user_info={
                    "email": user_info.email,
                    "name": user_info.name,
                    "linkedin_id": user_info.sub
                }
            )
    
    async def _handle_unverified_email_flow(
        self,
        db: AsyncSession,
        user_info: UserInfo,
        token_data: LinkedInAccessTokenSchema
    ) -> schemas.OauthCallbackResult:
        """Handle flow when LinkedIn email is unverified or missing."""
        
        # Create a pending OAuth record to store tokens securely
        await self.linkedin_oauth_dao.create_or_update(
            db,
            linkedin_id=user_info.sub,
            access_token=token_data.access_token,
            refresh_token=token_data.refresh_token,
            scope=token_data.scope,
            expires_in=token_data.expires_in,
            refresh_token_expires_in=token_data.refresh_token_expires_in,
            oauth_state=models.LinkedinOauthState.VERIFICATION_REQUIRED,
            state_metadata={"reason": "unverified_linkedin_email"}
        )
        
        # Check if account exists with unverified email
        existing_user = None
        if user_info.email:
            existing_user = await self.user_dao.get_by_email(db, user_info.email)
        
        logger.info(f"Email verification required for LinkedIn user: {user_info.sub}")
        
        return schemas.OauthCallbackResult(
            success=True,
            action=schemas.OauthAction.VERIFICATION_REQUIRED,
            message="Email verification required",
            requires_action=True,
            user_info={
                "email": user_info.email,
                "name": user_info.name,
                "linkedin_id": user_info.sub,
                "existing_account_email": existing_user.email if existing_user else None,
                "linkedin_email_verified": user_info.email_verified,
            }
        )
    
    async def _handle_logged_in_user_flow(
        self,
        db: AsyncSession,
        user_info: UserInfo,
        token_data: LinkedInAccessTokenSchema,
        current_user_id: str
    ) -> schemas.OauthCallbackResult:
        """Handle OAuth flow for logged-in users connecting LinkedIn."""
        
        # Get current user
        current_user = await self.user_dao.get(db, uuid.UUID(current_user_id))
        if not current_user:
            raise exceptions.LinkedInOauthException(
                "Current user not found",
                status_code=status.HTTP_404_NOT_FOUND
            )
        
        # Check if LinkedIn account is already mapped
        existing_oauth = await self.linkedin_oauth_dao.get(
            db, user_info.sub
        )
        
        if existing_oauth:
            if existing_oauth.user_id == current_user.id:
                # Already linked to same user - update tokens
                await self.linkedin_oauth_dao.update_tokens(
                    db,
                    linkedin_id=user_info.sub,
                    access_token=token_data.access_token,
                    refresh_token=token_data.refresh_token,
                    expires_in=token_data.expires_in,
                    refresh_token_expires_in=token_data.refresh_token_expires_in
                )
                
                logger.info(f"LinkedIn already linked for user: {current_user.email}")
                
                return schemas.OauthCallbackResult(
                    success=True,
                    action=schemas.OauthAction.ACCOUNT_LINKED,
                    user=current_user,
                    linkedin_oauth=existing_oauth,
                    message="LinkedIn account already linked",
                    requires_action=False
                )
            else:
                # Linked to different user - conflict
                conflict_user = await self.user_dao.get(db, existing_oauth.user_id)
                
                logger.warning(f"LinkedIn conflict: {user_info.sub} linked to {conflict_user.email}, not {current_user.email}")
                
                return schemas.OauthCallbackResult(
                    success=False,
                    action=schemas.OauthAction.CONFLICT_RESOLUTION,
                    message=f"This LinkedIn account is already linked to another KIWIQ account ({conflict_user.email}). "
                            f"Please login to that account and unlink LinkedIn from settings.",
                    requires_action=True,
                    user_info={
                        "conflict_email": conflict_user.email,
                        "linkedin_id": user_info.sub
                    }
                )
        
        # Check if current user already has LinkedIn linked
        current_user_oauth = await self.linkedin_oauth_dao.get_by_user_id(
            db, current_user.id
        )
        
        if current_user_oauth:
            # Update to new LinkedIn account
            logger.info(f"Updating LinkedIn link from {current_user_oauth.id} to {user_info.sub} for user {current_user.email}")
            await self.linkedin_oauth_dao.unlink_from_user(db, current_user.id)
        
        # Link LinkedIn account to current user
        oauth_record = await self.linkedin_oauth_dao.create_or_update(
            db,
            linkedin_id=user_info.sub,
            user_id=current_user.id,
            access_token=token_data.access_token,
            refresh_token=token_data.refresh_token,
            scope=token_data.scope,
            expires_in=token_data.expires_in,
            refresh_token_expires_in=token_data.refresh_token_expires_in,
            oauth_state=models.LinkedinOauthState.ACTIVE
        )
        
        logger.info(f"LinkedIn account {user_info.sub} linked to user {current_user.email}")
        
        return schemas.OauthCallbackResult(
            success=True,
            action=schemas.OauthAction.ACCOUNT_LINKED,
            user=current_user,
            linkedin_oauth=oauth_record,
            message="Successfully linked LinkedIn account",
            requires_action=False
        )
    
    async def send_linkedin_verification_email(
        self,
        db: AsyncSession,
        background_tasks: BackgroundTasks,
        base_url: str,
        email: str,
        linkedin_id: str,
        csrf_token: str
    ) -> bool:
        """
        Sends a verification email to link a LinkedIn account.

        This method creates a self-contained JWT for an email link that allows
        a user to prove ownership of their email address and link it to a pending
        LinkedIn OAuth connection. It does not rely on any cookie-based state.
        """
        if not email or not linkedin_id:
            logger.warning("Attempted to send verification email with missing email or linkedin_id.")
            return False

        user = await self.user_dao.get_by_email(db, email)
        if not user:
            logger.warning(f"Verification requested for non-existent email: {email}")
            return False

        if not user.is_active:
            logger.warning(f"Verification requested for inactive user: {user.email}")
            return False

        verification_jwt = LinkedInStateManager.create_email_verification_token(
            user_id=str(user.id),
            email=user.email,
            linkedin_id=linkedin_id,
            csrf_token=csrf_token
        )
        
        verification_link = f"{base_url}?token={verification_jwt}"

        email_render_data = AccountConfirmationEmailData(
            opening_message="We're almost done linking your LinkedIn account!",
            user_name=user.full_name or user.email.split('@')[0],
            confirmation_url=verification_link,
            expiry_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
            additional_message="For your security, this link will only work in the same browser you used to start the LinkedIn account linking process.",
            is_email_confirmation=True
        )
        
        html_content = self.email_renderer.render_account_confirmation_email(email_render_data)
        
        email_content = EmailContent(
            subject="Verify Your Account to Link with LinkedIn",
            html_body=html_content,
            text_body=self.email_renderer.html_to_text(html_content),
            from_name="KiwiQ Team"
        )
        
        recipient = EmailRecipient(email=user.email, name=user.full_name)
        
        success = await email_dispatch.send_email_async(background_tasks, recipient, email_content)
        if success:
            logger.info(f"LinkedIn linking verification email queued for {user.email}")
        else:
            logger.warning(f"Failed to queue LinkedIn linking verification email for {user.email}")

        return success

    async def verify_linking_token(
        self, db: AsyncSession, token: str, csrf_cookie: Optional[str] = None
    ) -> Tuple[User, models.LinkedinUserOauth]:
        """
        Verify the self-contained JWT from the email and link the LinkedIn account.
        
        This method is triggered by a user clicking a link in an email and
        is therefore independent of any browser/cookie state. The JWT contains
        all necessary information to securely associate a user with a pending
        LinkedIn OAuth record. It also validates the CSRF token.
        """
        token_data = LinkedInStateManager.verify_email_verification_token(token)
        if not token_data:
            raise exceptions.LinkedInStateException("Invalid or expired verification token.")

        # Perform CSRF check
        jwt_csrf_token = token_data.get("csrf_token")
        # logger.info(f"JWT CSRF token: {jwt_csrf_token} -- token_data: {token_data}")
        if not validate_csrf_token(cookie_token=csrf_cookie, header_token=jwt_csrf_token):
            raise exceptions.LinkedInStateException(f"CSRF token mismatch: {'state token null' if jwt_csrf_token is None else ('csrf token mismatch' if csrf_cookie else 'csrf token null')}")

        user_id = uuid.UUID(token_data["user_id"])
        linkedin_id = token_data["linkedin_id"]

        user = await self.user_dao.get(db, user_id)
        if not user:
            raise exceptions.LinkedInOauthException(
                "User not found for this verification token.", status_code=status.HTTP_404_NOT_FOUND
            )
        
        if not user.is_active:
            raise exceptions.LinkedInOauthException(
                "Cannot link to an inactive account.", status_code=status.HTTP_403_FORBIDDEN
            )

        # Check for conflicts
        existing_oauth = await self.linkedin_oauth_dao.get(db, linkedin_id)
        if existing_oauth and existing_oauth.user_id and existing_oauth.user_id != user.id:
            raise exceptions.LinkedInAccountConflictException(
                linkedin_id=linkedin_id,
                existing_user_email="another user"
            )
        
        if not existing_oauth:
            raise exceptions.LinkedInOauthException(
                "No pending LinkedIn OAuth record found for this verification.",
                status_code=status.HTTP_404_NOT_FOUND
            )

        oauth_record = await self.linkedin_oauth_dao.create_or_update(
            db=db,
            linkedin_id=linkedin_id,
            user_id=user.id,
            oauth_state=models.LinkedinOauthState.ACTIVE,
            state_metadata={"linked_via_email_verification": True},
            create=False  # Ensure we only update the existing record
        )

        if not user.is_verified:
            await self.user_dao.update(db, db_obj=user, obj_in=auth_schemas.UserUpdate(is_verified=True))

        logger.info(f"Successfully linked LinkedIn account {linkedin_id} to user {user.email} via email token.")
        return user, oauth_record

    async def handle_provided_email(
        self,
        db: AsyncSession,
        background_tasks: BackgroundTasks,
        base_url: str,
        provide_email_data: schemas.ProvideEmail,
        state_data: Dict[str, Any],
        csrf_token_for_email: str
    ) -> schemas.ProvideEmailResult:
        """
        Handles a user-provided email during an interactive OAuth flow.
        
        If the email belongs to an existing user, it triggers a separate,
        stateless email verification flow. If the user is new, it returns an
        updated state token to continue the interactive registration flow.
        """
        existing_user = await self.user_dao.get_by_email(db, provide_email_data.email)
        linkedin_id = state_data['linkedin_id']

        if existing_user:
            # User exists. Trigger the email verification flow, which is
            # independent of the current cookie-based flow.
            await self.send_linkedin_verification_email(
                db,
                background_tasks,
                base_url,
                email=provide_email_data.email,
                linkedin_id=linkedin_id,
                csrf_token=csrf_token_for_email
            )
            return schemas.ProvideEmailResult(
                success=True,
                message="Verification email sent. Please check your inbox to link your account.",
                action_required=schemas.OauthAction.VERIFICATION_REQUIRED
            )
        else:
            # New user. Continue the interactive flow by issuing a new state
            # token that includes the provided email for the registration step.
            new_state_token = LinkedInStateManager.create_oauth_session_token(
                linkedin_id=linkedin_id,
                email=provide_email_data.email,
                name=state_data.get('name'),
                email_verified=False
            )
            return schemas.ProvideEmailResult(
                success=True,
                message="Email accepted. Please complete your registration.",
                action_required=schemas.OauthAction.REGISTRATION_REQUIRED
            )

    async def complete_registration(
        self,
        db: AsyncSession,
        registration_data: schemas.CompleteLinkedinRegistration,
        state_data: Dict[str, Any],
        background_tasks: BackgroundTasks,
        base_url: str
    ) -> Tuple[User, models.LinkedinUserOauth, bool]:
        """
        Complete registration with LinkedIn data.
        
        This method creates a new KIWIQ user account and links their LinkedIn
        profile, handling organization creation if requested.
        
        Args:
            db: Database session
            registration_data: Registration form data
            state_data: Verified state data from the OAuth cookie
            background_tasks: FastAPI background tasks for email sending
            base_url: Base URL for email links
            
        Returns:
            Tuple of (User, LinkedinUserOauth, needs_email_verification (bool))
            
        Raises:
            LinkedInOauthException: For registration errors
            LinkedInStateException: For invalid state tokens
        """
        # State data is already verified by the dependency
        linkedin_id = state_data['linkedin_id']
        oauth_record_pending = await self.linkedin_oauth_dao.get(db, linkedin_id)
        if not oauth_record_pending:
            raise exceptions.LinkedInOauthException("Pending LinkedIn OAuth record not found.")
        
        skip_email = state_data.get("email_verified", False)
        user_provided_email_verified = registration_data.email == state_data.get("email") and skip_email
        needs_email_verification = not user_provided_email_verified
        
        # Create user registration data
        user_create = auth_schemas.UserAdminCreate(
            email=registration_data.email,
            full_name=registration_data.full_name,
            password=None,  # No password for OAuth users
            is_verified=user_provided_email_verified,
            # agree_to_terms=registration_data.agree_to_terms
        )
        
        # Register new user (skip email verification if LinkedIn verified)
        # logger.info(f"\n\n$$$$$ DEBUG: state_data: {state_data}\n\n")
        
        user = await self.auth_service.register_new_user(
            db=db,
            user_in=user_create,
            background_tasks=background_tasks,
            base_url=base_url,
            registered_by_admin=True,
            send_email_for_verification=needs_email_verification,
            send_first_steps_guide=not needs_email_verification,
        )
        
        # if user_provided_email_verified and not user.is_verified:
        #     await self.user_dao.update(db, db_obj=user, obj_in=auth_schemas.UserUpdate(is_verified=True))
        
        # Create organization if provided
        if registration_data.organization_name:
            org_create = auth_schemas.OrganizationCreate(
                name=registration_data.organization_name
            )
            org = await self.auth_service.create_organization(
                db=db,
                org_in=org_create,
                creator=user
            )
            logger.info(f"Created organization '{org.name}' for new LinkedIn user {user.email}")
        
        # Link LinkedIn account by updating the pending record
        oauth_record = await self.linkedin_oauth_dao.create_or_update(
            db,
            linkedin_id=linkedin_id,
            user_id=user.id,
            oauth_state=models.LinkedinOauthState.ACTIVE,
            state_metadata={"registration_completed": True},
            create=False # We must update the existing record
        )
        
        logger.info(f"Completed LinkedIn registration for user {user.email}")
        
        return user, oauth_record, needs_email_verification
    
    async def link_existing_account(
        self,
        db: AsyncSession,
        link_data: schemas.LinkExistingAccount,
        state_data: Dict[str, Any]
    ) -> Tuple[User, models.LinkedinUserOauth]:
        """
        Link LinkedIn to existing KIWIQ account after verification.
        
        Args:
            db: Database session
            link_data: Account linking request data
            state_data: Verified state data from the OAuth cookie
            
        Returns:
            Tuple of (User, LinkedinUserOauth)
            
        Raises:
            LinkedInAccountConflictException: If LinkedIn already linked elsewhere
            LinkedInStateException: For invalid state tokens
        """
        # State data is already verified by the dependency
        
        # Verify user credentials
        user = await self.auth_service.authenticate_user(
            db, email=link_data.email, password=link_data.password
        )
        if not user:
            raise exceptions.LinkedInOauthException(
                "Invalid email or password",
                status_code=status.HTTP_401_UNAUTHORIZED
            )
        
        if not user.is_active:
            raise exceptions.LinkedInOauthException(
                "This account is inactive. Please contact support.",
                status_code=status.HTTP_403_FORBIDDEN
            )
        
        linkedin_id = state_data['linkedin_id']
        # Check if LinkedIn account already linked elsewhere
        existing_oauth = await self.linkedin_oauth_dao.get(
            db, linkedin_id
        )
        
        if existing_oauth and existing_oauth.user_id and existing_oauth.user_id != user.id:
            conflict_user = await self.user_dao.get(db, existing_oauth.user_id)
            raise exceptions.LinkedInAccountConflictException(
                linkedin_id=linkedin_id,
                existing_user_email=conflict_user.email
            )
        
        # Link LinkedIn account by updating the pending record
        oauth_record = await self.linkedin_oauth_dao.create_or_update(
            db,
            linkedin_id=linkedin_id,
            user_id=user.id,
            oauth_state=models.LinkedinOauthState.ACTIVE,
            state_metadata={"linked_to_existing": True},
            create=False # We must update the existing record
        )
        
        logger.info(f"LinkedIn account linked to existing user {user.email}")
        
        return user, oauth_record
    
    async def unlink_linkedin_account(
        self,
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> bool:
        """
        Unlink LinkedIn account from user.
        
        Args:
            db: Database session
            user_id: KIWIQ user ID
            
        Returns:
            True if unlinked, False if no link existed
        """
        result = await self.linkedin_oauth_dao.unlink_from_user(db, user_id)
        if result:
            logger.info(f"LinkedIn account unlinked from user {user_id}")
        return result
    
    async def get_user_linkedin_connection(
        self,
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> Optional[schemas.LinkedinConnectionStatus]:
        """
        Get LinkedIn connection status for user.
        
        Args:
            db: Database session
            user_id: KIWIQ user ID
            
        Returns:
            LinkedinConnectionStatus or None if not connected
        """
        oauth_record = await self.linkedin_oauth_dao.get_by_user_id(db, user_id)
        
        if not oauth_record:
            return schemas.LinkedinConnectionStatus(
                is_connected=False
            )
        
        return schemas.LinkedinConnectionStatus(
            is_connected=True,
            linkedin_id=oauth_record.id,
            email=None,  # Could fetch from LinkedIn API if needed
            expires_at=oauth_record.token_expires_at,
            is_expired=oauth_record.is_access_token_expired(),
            scopes=oauth_record.get_scopes_list(),
            created_at=oauth_record.created_at,
            updated_at=oauth_record.updated_at
        )
    
    async def refresh_access_token(
        self,
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> LinkedInAccessTokenSchema:
        """
        Refresh LinkedIn access token for user.
        
        Args:
            db: Database session
            user_id: KIWIQ user ID
            
        Returns:
            Updated token data
            
        Raises:
            LinkedInOauthException: If refresh fails
            LinkedInTokenExpiredException: If refresh token expired
        """
        oauth_record = await self.linkedin_oauth_dao.get_by_user_id(db, user_id)
        
        if not oauth_record:
            raise exceptions.LinkedInOauthException(
                "LinkedIn account not linked",
                status_code=status.HTTP_404_NOT_FOUND
            )
        
        if not oauth_record.refresh_token:
            raise exceptions.LinkedInOauthException(
                "No refresh token available",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        if oauth_record.is_refresh_token_expired():
            raise exceptions.LinkedInTokenExpiredException(
                "LinkedIn refresh token has expired. Please re-authenticate."
            )
        
        try:
            # Use LinkedIn auth client to refresh token
            auth_client = self._get_auth_client()
            # response = auth_client.exchange_refresh_token_for_access_token(
            #     oauth_record.refresh_token
            # )
            response = await asyncio.to_thread(auth_client.exchange_refresh_token_for_access_token, oauth_record.refresh_token)
            
            if response.status_code != 200:
                logger.error(f"Token refresh failed: {str(response.response)}")
                raise exceptions.LinkedInOauthException(
                    "Failed to refresh access token",
                    status_code=status.HTTP_502_BAD_GATEWAY
                )
            
            new_token_data = LinkedInAccessTokenSchema(
                access_token=response.access_token,
                expires_in=response.expires_in,
                refresh_token=response.refresh_token,
                refresh_token_expires_in=response.refresh_token_expires_in,
            )
            
            # Update tokens in database
            await self.linkedin_oauth_dao.update_tokens(
                db,
                linkedin_id=oauth_record.id,
                access_token=new_token_data.access_token,
                refresh_token=new_token_data.refresh_token or oauth_record.refresh_token,
                expires_in=new_token_data.expires_in,
                refresh_token_expires_in=new_token_data.refresh_token_expires_in
            )
            
            logger.info(f"Successfully refreshed LinkedIn token for user {user_id}")
            return new_token_data
            
        except Exception as e:
            logger.error(f"Error refreshing LinkedIn token: {e}", exc_info=True)
            
            # Mark token as expired to prevent further attempts
            await self.linkedin_oauth_dao.mark_token_as_expired(db, oauth_record.id)
            
            raise exceptions.LinkedInOauthException(
                "Failed to refresh LinkedIn access token",
                status_code=status.HTTP_502_BAD_GATEWAY
            )
    
    async def get_linkedin_client_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> Optional[LinkedInClient]:
        """
        Get a LinkedIn API client configured with user's access token.
        
        This method checks token expiry and refreshes if necessary.
        
        Args:
            db: Database session
            user_id: KIWIQ user ID
            
        Returns:
            Configured LinkedInClient or None if not connected
        """
        oauth_record = await self.linkedin_oauth_dao.get_by_user_id(db, user_id)
        
        if not oauth_record:
            return None
        
        # Check if token needs refresh
        if oauth_record.is_access_token_expired():
            try:
                await self.refresh_access_token(db, user_id)
                # Reload record to get new token
                oauth_record = await self.linkedin_oauth_dao.get_by_user_id(db, user_id)
            except Exception as e:
                logger.error(f"Failed to refresh token for user {user_id}: {e}")
                return None
        
        # Create client with user's token
        client = LinkedInClient(
            client_id=settings.LINKEDIN_CLIENT_ID,
            client_secret=settings.LINKEDIN_CLIENT_SECRET,
            access_token=oauth_record.access_token
        )
        
        return client

    async def admin_delete_oauth_by_linkedin_id(
        self,
        db: AsyncSession,
        linkedin_id: str,
        reason: Optional[str] = None
    ) -> schemas.AdminDeleteLinkedinOauthResponse:
        """
        Admin method to delete LinkedIn OAuth record by LinkedIn ID.
        
        This method is for administrative purposes and includes comprehensive
        logging and validation for audit trails.
        
        Args:
            db: Database session
            linkedin_id: LinkedIn user ID (sub)
            reason: Optional reason for deletion
            
        Returns:
            AdminDeleteLinkedinOauthResponse with deletion status
        """
        try:
            # Get the record first to capture details for response
            oauth_record = await self.linkedin_oauth_dao.get(db, linkedin_id)
            
            if oauth_record:
                user_id = oauth_record.user_id
                
                # Log the admin action with reason
                log_message = f"ADMIN: Deleting LinkedIn OAuth {linkedin_id}"
                if user_id:
                    log_message += f" for user {user_id}"
                if reason:
                    log_message += f" - Reason: {reason}"
                
                logger.warning(log_message)
                
                # Perform the deletion
                deleted = await self.linkedin_oauth_dao.admin_delete_by_linkedin_id(
                    db, linkedin_id
                )
                
                return schemas.AdminDeleteLinkedinOauthResponse(
                    success=True,
                    deleted=deleted,
                    linkedin_id=linkedin_id,
                    user_id=user_id,
                    message=f"LinkedIn OAuth record {linkedin_id} deleted successfully"
                )
            else:
                logger.info(f"ADMIN: LinkedIn OAuth record {linkedin_id} not found for deletion")
                return schemas.AdminDeleteLinkedinOauthResponse(
                    success=True,
                    deleted=False,
                    linkedin_id=linkedin_id,
                    message=f"LinkedIn OAuth record {linkedin_id} not found"
                )
                
        except Exception as e:
            logger.error(f"ADMIN: Error deleting LinkedIn OAuth {linkedin_id}: {e}", exc_info=True)
            return schemas.AdminDeleteLinkedinOauthResponse(
                success=False,
                deleted=False,
                linkedin_id=linkedin_id,
                message=f"Failed to delete LinkedIn OAuth record: {str(e)}"
            )
    
    async def admin_delete_oauth_by_user_id(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        reason: Optional[str] = None
    ) -> schemas.AdminDeleteLinkedinOauthResponse:
        """
        Admin method to delete LinkedIn OAuth record by user ID.
        
        This method is for administrative purposes and includes comprehensive
        logging and validation for audit trails.
        
        Args:
            db: Database session
            user_id: KIWIQ user UUID
            reason: Optional reason for deletion
            
        Returns:
            AdminDeleteLinkedinOauthResponse with deletion status
        """
        try:
            # Get the record first to capture details for response
            oauth_record = await self.linkedin_oauth_dao.get_by_user_id(db, user_id)
            
            if oauth_record:
                linkedin_id = oauth_record.id
                
                # Log the admin action with reason
                log_message = f"ADMIN: Deleting LinkedIn OAuth for user {user_id} (linkedin_id={linkedin_id})"
                if reason:
                    log_message += f" - Reason: {reason}"
                
                logger.warning(log_message)
                
                # Perform the deletion
                deleted = await self.linkedin_oauth_dao.admin_delete_by_user_id(
                    db, user_id
                )
                
                return schemas.AdminDeleteLinkedinOauthResponse(
                    success=True,
                    deleted=deleted,
                    linkedin_id=linkedin_id,
                    user_id=user_id,
                    message=f"LinkedIn OAuth record for user {user_id} deleted successfully"
                )
            else:
                logger.info(f"ADMIN: No LinkedIn OAuth record found for user {user_id}")
                return schemas.AdminDeleteLinkedinOauthResponse(
                    success=True,
                    deleted=False,
                    user_id=user_id,
                    message=f"No LinkedIn OAuth record found for user {user_id}"
                )
                
        except Exception as e:
            logger.error(f"ADMIN: Error deleting LinkedIn OAuth for user {user_id}: {e}", exc_info=True)
            return schemas.AdminDeleteLinkedinOauthResponse(
                success=False,
                deleted=False,
                user_id=user_id,
                message=f"Failed to delete LinkedIn OAuth record: {str(e)}"
            )
    
    async def admin_list_oauth_records(
        self,
        db: AsyncSession,
        limit: int = 100,
        offset: int = 0
    ) -> schemas.AdminLinkedinOauthListResponse:
        """
        Admin method to list LinkedIn OAuth records with pagination.
        
        This method provides administrative overview of all LinkedIn OAuth
        connections with user information for management purposes.
        
        Args:
            db: Database session
            limit: Maximum number of records to return
            offset: Number of records to skip
            
        Returns:
            AdminLinkedinOauthListResponse with paginated records
        """
        try:
            # Get records with user information
            records = await self.linkedin_oauth_dao.admin_get_all_oauth_records(
                db, limit=limit + 1, offset=offset, include_user_info=True
            )
            
            # Check if there are more records for pagination
            has_more = len(records) > limit
            if has_more:
                records = records[:limit]  # Remove the extra record
            
            # Transform to response format
            list_items = []
            for record in records:
                user_email = None
                user_full_name = None
                
                if record.user:
                    user_email = record.user.email
                    user_full_name = record.user.full_name
                
                list_items.append(schemas.AdminLinkedinOauthListItem(
                    id=record.id,
                    user_id=record.user_id,
                    user_email=user_email,
                    user_full_name=user_full_name,
                    oauth_state=str(getattr(record.oauth_state, "value", record.oauth_state)),
                    scopes=record.get_scopes_list(),
                    token_expires_at=record.token_expires_at,
                    is_expired=record.is_access_token_expired(),
                    created_at=record.created_at,
                    updated_at=record.updated_at
                ))
            
            # Get total count for pagination info
            # Note: In production, you might want to cache this or use a more efficient count query
            all_records = await self.linkedin_oauth_dao.admin_get_all_oauth_records(
                db, limit=None, offset=0, include_user_info=False
            )
            total_count = len(all_records)
            
            logger.info(f"ADMIN: Retrieved {len(list_items)} LinkedIn OAuth records (limit={limit}, offset={offset})")
            
            return schemas.AdminLinkedinOauthListResponse(
                records=list_items,
                total_count=total_count,
                limit=limit,
                offset=offset,
                has_more=has_more
            )
            
        except Exception as e:
            logger.error(f"ADMIN: Error listing LinkedIn OAuth records: {e}", exc_info=True)
            raise exceptions.LinkedInOauthException(
                "Failed to retrieve LinkedIn OAuth records",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LinkedinIntegrationService:
    """
    Service layer for LinkedIn Integration operations.
    
    This service handles LinkedIn integrations for managing multiple LinkedIn
    accounts/organizations, separate from the OAuth login functionality.
    """
    
    def __init__(
        self,
        linkedin_integration_dao: crud.LinkedinIntegrationDAO,
        linkedin_account_dao: crud.LinkedinAccountDAO,
        org_linkedin_account_dao: crud.OrgLinkedinAccountDAO,
        user_dao: auth_crud.UserDAO,
        auth_service: AuthService
    ):
        self.linkedin_integration_dao = linkedin_integration_dao
        self.linkedin_account_dao = linkedin_account_dao
        self.org_linkedin_account_dao = org_linkedin_account_dao
        self.user_dao = user_dao
        self.auth_service = auth_service
    
    # Helper methods for common operations
    
    def _get_auth_client(self) -> AuthClient:
        """
        Create and return a LinkedIn AuthClient instance.
        
        Returns:
            AuthClient: Configured LinkedIn auth client
        """
        return AuthClient(
            client_id=settings.LINKEDIN_CLIENT_ID,
            client_secret=settings.LINKEDIN_CLIENT_SECRET
        )
    
    def _get_linkedin_client(self, access_token: str) -> LinkedInClient:
        """
        Create a LinkedIn API client with a specific access token.
        
        Args:
            access_token: The user's access token
            
        Returns:
            LinkedInClient configured with the access token
        """
        return LinkedInClient(
            client_id=settings.LINKEDIN_CLIENT_ID,
            client_secret=settings.LINKEDIN_CLIENT_SECRET,
            access_token=access_token
        )
    
    async def _refresh_integration_tokens(
        self,
        db: AsyncSession,
        integration: models.LinkedinIntegration
    ) -> Optional[models.LinkedinIntegration]:
        """
        Refresh access tokens for an integration if expired.
        
        Args:
            db: Database session
            integration: LinkedIn integration to refresh
            
        Returns:
            Updated integration if successful, None if refresh failed
            
        Raises:
            Exception: If token refresh fails
        """
        if not integration.is_access_token_expired() or not integration.refresh_token:
            return integration
        
        auth_client = self._get_auth_client()
        
        token_response = await asyncio.to_thread(
            auth_client.exchange_refresh_token_for_access_token,
            integration.refresh_token
        )
        
        if token_response.status_code != 200:
            logger.error(f"Token refresh failed for integration {integration.id}: {token_response.status_code}")
            await self.linkedin_integration_dao.update_state(
                db, integration.id, models.LinkedinOauthState.EXPIRED
            )
            await self._update_org_account_statuses(
                db, integration.id, models.OrgLinkedinAccountStatus.EXPIRED
            )
            return None
        
        # Update tokens
        updated_integration = await self.linkedin_integration_dao.update_tokens(
            db,
            integration_id=integration.id,
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token or integration.refresh_token,
            expires_in=token_response.expires_in,
            refresh_token_expires_in=token_response.refresh_token_expires_in
        )
        
        return updated_integration
    
    def _extract_member_profile_data(self, member_profile: LinkedinMemberProfile) -> Dict[str, Any]:
        """
        Extract profile data from LinkedIn member profile response.
        
        Args:
            member_profile: LinkedIn API member profile response
            
        Returns:
            Dict containing extracted profile data
        """
        return {
            "localized_first_name": member_profile.localized_first_name,
            "localized_last_name": member_profile.localized_last_name,
            "localized_headline": member_profile.localized_headline,
            "vanity_name": member_profile.vanity_name,
            "id": member_profile.id
        }
    
    def _extract_organization_profile_data(self, org_details: LinkedinOrganization) -> Dict[str, Any]:
        """
        Extract profile data from LinkedIn organization details response.
        
        Args:
            org_details: LinkedIn API organization details response
            
        Returns:
            Dict containing extracted organization profile data
        """
        return {
            "vanity_name": org_details.vanity_name,
            "website": org_details.display_website,
            "description": org_details.display_description,
            "organization_type": org_details.organization_type,
            "staff_count_range": org_details.staff_count_range,
            "founded_year": org_details.founded_year
        }
    
    async def _parse_organization_roles(
        self,
        org_roles_response: OrganizationRolesResponse,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Parse organization roles from LinkedIn API response.
        
        Args:
            org_roles_response: LinkedIn API organization roles response
            
        Returns:
            Dict mapping org_id (URN) to org info including role, urn, and state
        """
        linkedin_orgs_roles = {}
        
        for role in org_roles_response.elements:
            # Use the full URN as the org_id, don't split it
            org_id = role.organization
            # User has only one role per organization
            linkedin_orgs_roles[org_id] = {
                "organization_urn": role.organization,
                "role": role.role,  # Single role, not array
                "state": role.state
            }
        
        return linkedin_orgs_roles
    
    async def _sync_organization_accounts(
        self,
        db: AsyncSession,
        linkedin_client: LinkedInClient,
        linkedin_orgs_roles: Dict[str, Dict[str, Any]]
    ) -> Tuple[int, int, int, List[str]]:
        """
        Sync organization accounts with LinkedIn.
        
        Args:
            db: Database session
            linkedin_client: LinkedIn client with user's access token
            linkedin_orgs_roles: Parsed organization roles data
            
        Returns:
            Tuple of (accounts_synced, new_accounts, updated_accounts, errors)
        """
        accounts_synced = 0
        new_accounts = 0
        updated_accounts = 0
        errors = []
        
        for org_id, org_info in linkedin_orgs_roles.items():
            try:
                success, org_details = await linkedin_client.get_organization_details(org_info["organization_urn"])
                if not success:
                    raise Exception(f"Failed to fetch organization details for {org_id}")
                
                # Update org_info with fetched details
                org_info["organization_name"] = org_details.display_name
                org_info["organization_vanity_name"] = org_details.vanity_name
                
                # Extract profile data (including numeric ID)
                profile_data = self._extract_organization_profile_data(org_details)
                profile_data["id"] = org_details.id  # Store numeric ID in profile data
                
                # Use the URN as the LinkedIn ID
                linkedin_id = org_id  # This is the full URN
                
                # Check if account exists
                existing_account = await self.linkedin_account_dao.get(db, linkedin_id)
                
                if existing_account:
                    await self.linkedin_account_dao.update(
                        db,
                        linkedin_id=linkedin_id,
                        name=org_details.display_name,
                        vanity_name=org_details.vanity_name,
                        profile_data=profile_data
                    )
                    updated_accounts += 1
                else:
                    await self.linkedin_account_dao.create_or_update(
                        db,
                        linkedin_id=linkedin_id,
                        account_type=models.LinkedinAccountType.ORGANIZATION,
                        name=org_details.display_name,
                        vanity_name=org_details.vanity_name,
                        profile_data=profile_data
                    )
                    new_accounts += 1
                
                accounts_synced += 1
                
            except Exception as e:
                logger.warning(f"Failed to sync organization {org_id}: {e}")
                errors.append(f"Organization {org_id} sync failed: {str(e)}")
        
        return accounts_synced, new_accounts, updated_accounts, errors
    
    async def _create_org_linkedin_account_response(
        self,
        db: AsyncSession,
        org_account: models.OrgLinkedinAccount
    ) -> schemas.OrgLinkedinAccountRead:
        """
        Create OrgLinkedinAccountRead response with nested data.
        
        Args:
            db: Database session
            org_account: OrgLinkedinAccount model instance
            
        Returns:
            OrgLinkedinAccountRead with populated nested relationships
        """
        # Load related data
        linkedin_account = await self.linkedin_account_dao.get(
            db, org_account.linkedin_account_id
        )
        integration = await self.linkedin_integration_dao.get(
            db, org_account.linkedin_integration_id
        )
        
        return schemas.OrgLinkedinAccountRead(
            id=org_account.id,
            linkedin_account_id=org_account.linkedin_account_id,
            linkedin_integration_id=org_account.linkedin_integration_id,
            managed_by_user_id=org_account.managed_by_user_id,
            organization_id=org_account.organization_id,
            role_in_linkedin_entity=org_account.role_in_linkedin_entity,
            is_shared=org_account.is_shared,
            is_active=org_account.is_active,
            status=org_account.status,
            created_at=org_account.created_at,
            updated_at=org_account.updated_at,
            linkedin_account=schemas.LinkedinAccountRead.model_validate(linkedin_account) if linkedin_account else None,
            linkedin_integration=schemas.LinkedinIntegrationRead.model_validate(integration) if integration else None
        )
    
    def _can_user_post_to_organization(self, role: Optional[str]) -> bool:
        """
        Determine if a user can post to an organization based on their role.
        
        Args:
            role: User's role in the organization
            
        Returns:
            True if user can post, False otherwise
        """
        return role in ["ADMINISTRATOR", "DIRECT_SPONSORED_CONTENT_POSTER"]

    async def initiate_integration_flow(
        self,
        user_id: uuid.UUID,
        redirect_uri: str,
        csrf_token: str,
    ) -> schemas.LinkedinIntegrationInitiateResponse:
        """
        Initiate LinkedIn integration OAuth flow for a logged-in user.
        
        Args:
            user_id: ID of the authenticated user
            redirect_uri: OAuth callback redirect URI
            csrf_token: CSRF token for protection
            
        Returns:
            LinkedinIntegrationInitiateResponse with authorization URL
        """
        # Create state token for integration flow
        state_token = LinkedInStateManager.create_state_token(
            user_id=str(user_id),
            additional_data={"csrf_token": csrf_token},  # "flow_type": "integration", 
        )
        logger.info(f" $$$ state: {state_token}")
        
        auth_client = AuthClient(
            client_id=settings.LINKEDIN_CLIENT_ID,
            client_secret=settings.LINKEDIN_CLIENT_SECRET,
            redirect_url=redirect_uri
        )
        
        authorization_url = await asyncio.to_thread(
            auth_client.generate_member_auth_url,
            scopes=LINKEDIN_SCOPES,
            state=state_token
        )
        
        logger.info(f"Generated LinkedIn integration auth URL for user: {user_id}")
        
        return schemas.LinkedinIntegrationInitiateResponse(
            authorization_url=authorization_url
        )
    
    async def process_integration_callback(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        code: str,
        redirect_uri: str,
        state: Optional[str] = None,
        csrf_cookie: Optional[str] = None,
    ) -> schemas.LinkedinIntegrationCallbackResponse:
        """
        Process LinkedIn integration OAuth callback.
        
        Handles the OAuth callback after user authorizes the integration:
        - Validates state token
        - Exchanges authorization code for access tokens
        - Fetches user profile and organization data
        - Creates or updates integration records
        - Syncs LinkedIn accounts (personal and organizational)
        
        Args:
            db: Database session
            user_id: Authenticated user ID
            code: Authorization code from LinkedIn
            redirect_uri: OAuth redirect URI
            state: State token for verification
            csrf_cookie: CSRF token for protection

        Returns:
            LinkedinIntegrationCallbackResponse with integration details
            
        Raises:
            LinkedInStateException: If state token validation fails
            LinkedInOauthException: If token exchange fails
            LinkedInAPIException: If API calls fail
        """
        try:
            # Verify state if provided
            if state:
                logger.info(f" $$$ 2 state: {state}")
                state_data = LinkedInStateManager.verify_state_token(state)
                jwt_csrf_token = state_data.get("csrf_token")
                if not validate_csrf_token(cookie_token=csrf_cookie, header_token=jwt_csrf_token):
                    raise exceptions.LinkedInStateException(f"CSRF token mismatch: {'state token null' if jwt_csrf_token is None else ('csrf token mismatch' if csrf_cookie else 'csrf token null')}")
                if state_data.get("user_id") != str(user_id):
                    raise exceptions.LinkedInStateException("State token user mismatch")
            
            # Exchange code for tokens
            auth_client = AuthClient(
                client_id=settings.LINKEDIN_CLIENT_ID,
                client_secret=settings.LINKEDIN_CLIENT_SECRET,
                redirect_url=redirect_uri
            )
            
            token_response = await asyncio.to_thread(
                auth_client.exchange_auth_code_for_access_token, code
            )
            
            if token_response.status_code != 200:
                raise exceptions.LinkedInOauthException(
                    "Failed to exchange authorization code",
                    status_code=status.HTTP_502_BAD_GATEWAY
                )
            
            # Create LinkedIn client with user's access token
            linkedin_client = self._get_linkedin_client(token_response.access_token)
            
            # Get LinkedIn user info
            success, user_info = await linkedin_client.get_member_info_including_email()
            
            if not success:
                raise exceptions.LinkedInAPIException(
                    "Failed to retrieve LinkedIn user info"
                )
            
            # Get member profile for detailed information
            member_profile = None
            profile_data = {"email": user_info.email}
            
            try:
                success, member_profile = await linkedin_client.get_member_profile()
                if not success:
                    raise Exception("Failed to fetch member profile")
                profile_data = self._extract_member_profile_data(member_profile)
                profile_data["email"] = user_info.email
            except Exception as e:
                logger.warning(f"Failed to fetch member profile: {e}")
            
            # Get LinkedIn organizations/roles
            linkedin_orgs_roles = {}
            try:
                success, org_roles_response = await linkedin_client.get_member_organization_roles()
                if not success:
                    raise Exception("Failed to fetch member organization roles")
                
                # Parse organization roles
                linkedin_orgs_roles = await self._parse_organization_roles(org_roles_response)
                
                # Sync organization accounts
                await self._sync_organization_accounts(db, linkedin_client, linkedin_orgs_roles)
                        
            except Exception as e:
                logger.warning(f"Failed to fetch organization roles: {e}")
            
            # Check if integration already exists
            existing = await self.linkedin_integration_dao.get_by_user_and_linkedin_id(
                db, user_id, user_info.sub
            )
            
            if existing:
                # Update existing integration
                integration = await self.linkedin_integration_dao.update_tokens(
                    db,
                    integration_id=existing.id,
                    access_token=token_response.access_token,
                    refresh_token=token_response.refresh_token,
                    expires_in=token_response.expires_in,
                    refresh_token_expires_in=token_response.refresh_token_expires_in
                )
                
                # Update orgs/roles if changed
                if linkedin_orgs_roles != existing.linkedin_orgs_roles:
                    await self.linkedin_integration_dao.update_linkedin_orgs_roles(
                        db, existing.id, linkedin_orgs_roles
                    )
                
                message = "LinkedIn integration updated successfully"
            else:
                # Create new integration
                integration = await self.linkedin_integration_dao.create_integration(
                    db,
                    user_id=user_id,
                    linkedin_id=user_info.sub,
                    access_token=token_response.access_token,
                    refresh_token=token_response.refresh_token,
                    scope=token_response.scope,
                    expires_in=token_response.expires_in,
                    refresh_token_expires_in=token_response.refresh_token_expires_in,
                    linkedin_orgs_roles=linkedin_orgs_roles
                )
                
                message = "LinkedIn integration created successfully"
            
            # Create/update LinkedIn account record for the person
            full_name = user_info.name
            vanity_name = None
            if member_profile:
                full_name = f"{member_profile.localized_first_name} {member_profile.localized_last_name}"
                vanity_name = member_profile.vanity_name if hasattr(member_profile, 'vanity_name') else None
                
            await self.linkedin_account_dao.create_or_update(
                db,
                linkedin_id=user_info.sub,
                account_type=models.LinkedinAccountType.PERSON,
                name=full_name,
                vanity_name=vanity_name,
                profile_data=profile_data
            )
            
            logger.info(f"LinkedIn integration processed for user {user_id}")
            
            return schemas.LinkedinIntegrationCallbackResponse(
                success=True,
                integration_id=integration.id,
                message=message,
                linkedin_orgs_roles=linkedin_orgs_roles
            )
            
        except exceptions.LinkedInOauthException:
            raise
        except Exception as e:
            logger.error(f"Error processing integration callback: {e}", exc_info=True)
            return schemas.LinkedinIntegrationCallbackResponse(
                success=False,
                message=f"Failed to process LinkedIn integration: {str(e)}",
                linkedin_orgs_roles=None
            )
    
    async def list_user_integrations(
        self,
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> schemas.LinkedinIntegrationListResponse:
        """
        List all LinkedIn integrations for a user.
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            LinkedinIntegrationListResponse with integrations
        """
        integrations = await self.linkedin_integration_dao.get_by_user_id(db, user_id)
        
        integration_reads = []
        for integration in integrations:
            integration_reads.append(schemas.LinkedinIntegrationRead(
                id=integration.id,
                user_id=integration.user_id,
                linkedin_id=integration.linkedin_id,
                scope=integration.scope,
                integration_state=integration.integration_state,
                linkedin_orgs_roles=integration.linkedin_orgs_roles,
                is_expired=integration.is_access_token_expired(),
                token_expires_at=integration.token_expires_at,
                last_sync_at=integration.last_sync_at,
                created_at=integration.created_at,
                updated_at=integration.updated_at
            ))
        
        return schemas.LinkedinIntegrationListResponse(
            integrations=integration_reads,
            total=len(integration_reads)
        )
    
    async def share_linkedin_account_with_org(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        create_data: schemas.OrgLinkedinAccountCreate
    ) -> schemas.OrgLinkedinAccountRead:
        """
        Share a LinkedIn account with an organization.
        
        Allows a user to share their LinkedIn account (personal or organizational)
        with their KiwiQ organization. The user must own the integration and have
        the appropriate permissions.
        
        Args:
            db: Database session
            user_id: User sharing the account
            organization_id: Target organization ID
            create_data: Account sharing configuration including:
                - linkedin_integration_id: Integration to use
                - linkedin_account_id: Account to share
                - is_shared: Whether to share with org members
                Role is automatically determined from the integration
            
        Returns:
            Created OrgLinkedinAccountRead with nested relationships
            
        Raises:
            HTTPException: If integration not found, unauthorized, or account doesn't exist
        """
        # Verify user owns the integration
        integration = await self.linkedin_integration_dao.get(
            db, create_data.linkedin_integration_id
        )
        
        if not integration or integration.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="LinkedIn integration not found or unauthorized"
            )
        
        # Verify LinkedIn account exists
        linkedin_account = await self.linkedin_account_dao.get(
            db, create_data.linkedin_account_id
        )
        
        if not linkedin_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="LinkedIn account not found"
            )
        
        # Determine the role based on account type
        role_in_linkedin_entity = None
        
        if linkedin_account.account_type == models.LinkedinAccountType.PERSON:
            # For personal accounts, user has full control
            role_in_linkedin_entity = "OWNER"
        elif linkedin_account.account_type == models.LinkedinAccountType.ORGANIZATION:
            # For organization accounts, get role from integration's linkedin_orgs_roles
            if integration.linkedin_orgs_roles:
                org_info = integration.linkedin_orgs_roles.get(create_data.linkedin_account_id)
                if org_info:
                    role_in_linkedin_entity = org_info.get("role")
                else:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You don't have access to this LinkedIn organization account"
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No organization roles found in integration"
                )
        
        # Create org LinkedIn account
        org_account = await self.org_linkedin_account_dao.create_org_linkedin_account(
            db,
            linkedin_account_id=create_data.linkedin_account_id,
            linkedin_integration_id=create_data.linkedin_integration_id,
            managed_by_user_id=user_id,
            organization_id=organization_id,
            role_in_linkedin_entity=role_in_linkedin_entity,
            is_shared=create_data.is_shared
        )
        
        # Return with nested data using helper method
        return await self._create_org_linkedin_account_response(db, org_account)
    
    async def list_org_linkedin_accounts(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        active_only: bool = True,
        shared_only: bool = True
    ) -> schemas.OrgLinkedinAccountListResponse:
        """
        List LinkedIn accounts shared with an organization.
        
        Retrieves all LinkedIn accounts that have been shared with the specified
        organization by its members. Includes nested account and integration details.
        
        Args:
            db: Database session
            organization_id: Organization ID to list accounts for
            active_only: If True, only return active accounts (default: True)
            shared_only: If True, only return accounts marked as shared (default: True)
            
        Returns:
            OrgLinkedinAccountListResponse containing:
            - accounts: List of OrgLinkedinAccountRead objects with nested data
            - total: Total number of accounts matching the criteria
        """
        org_accounts = await self.org_linkedin_account_dao.get_by_organization(
            db, organization_id, active_only, shared_only
        )
        
        # Build response list with nested data
        account_reads = []
        for org_account in org_accounts:
            try:
                account_read = await self._create_org_linkedin_account_response(db, org_account)
                account_reads.append(account_read)
            except Exception as e:
                # Log but continue - don't fail the entire list if one account has issues
                logger.warning(
                    f"Failed to load nested data for org account {org_account.id}: {e}"
                )
                # Create a minimal response without nested data
                account_reads.append(schemas.OrgLinkedinAccountRead(
                    id=org_account.id,
                    linkedin_account_id=org_account.linkedin_account_id,
                    linkedin_integration_id=org_account.linkedin_integration_id,
                    managed_by_user_id=org_account.managed_by_user_id,
                    organization_id=org_account.organization_id,
                    role_in_linkedin_entity=org_account.role_in_linkedin_entity,
                    is_shared=org_account.is_shared,
                    is_active=org_account.is_active,
                    status=org_account.status,
                    created_at=org_account.created_at,
                    updated_at=org_account.updated_at,
                    linkedin_account=None,
                    linkedin_integration=None
                ))
        
        return schemas.OrgLinkedinAccountListResponse(
            accounts=account_reads,
            total=len(account_reads)
        )
    
    async def update_org_linkedin_account(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        org_account_id: uuid.UUID,
        update_data: schemas.OrgLinkedinAccountUpdate
    ) -> schemas.OrgLinkedinAccountRead:
        """
        Update an organization's LinkedIn account settings.
        
        Only the user who shared the account can update its settings.
        This allows updating sharing status and active status.
        
        Args:
            db: Database session
            user_id: User making the update (must be the account manager)
            org_account_id: Org account ID to update
            update_data: Fields to update:
                - is_shared: Whether to share with org members
                - is_active: Whether the account is active
            
        Returns:
            Updated OrgLinkedinAccountRead with nested relationships
            
        Raises:
            HTTPException: If account not found or user is not the manager
        """
        # Get the org account and verify ownership
        org_account = await self.org_linkedin_account_dao.get(db, org_account_id)
        
        if not org_account or org_account.managed_by_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Org LinkedIn account not found or unauthorized"
            )
        
        # Update fields
        if update_data.is_shared is not None:
            await self.org_linkedin_account_dao.update_sharing_status(
                db, org_account_id, update_data.is_shared
            )
            # Refresh the object to get updated value
            org_account = await self.org_linkedin_account_dao.get(db, org_account_id)
        
        if update_data.is_active is not None:
            org_account.is_active = update_data.is_active
            db.add(org_account)
            await db.commit()
            await db.refresh(org_account)
        
        # Return updated account with nested data
        return await self._create_org_linkedin_account_response(db, org_account)
    
    async def delete_integration(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        integration_id: uuid.UUID
    ) -> bool:
        """
        Delete a LinkedIn integration and deactivate all associated org accounts.
        
        This method performs a cascading soft-delete:
        1. Verifies the user owns the integration
        2. Deactivates all organization accounts using this integration
        3. Deletes the integration record
        
        Note: This does not delete the LinkedIn account records themselves,
        as they may be referenced by other integrations.
        
        Args:
            db: Database session
            user_id: User ID requesting deletion (must own the integration)
            integration_id: Integration ID to delete
            
        Returns:
            True if successfully deleted, False if not found or unauthorized
        """
        # Verify ownership
        integration = await self.linkedin_integration_dao.get(db, integration_id)
        
        if not integration or integration.user_id != user_id:
            return False
        
        # Deactivate all org accounts using this integration
        await self.org_linkedin_account_dao.deactivate_by_integration(
            db, integration_id
        )
        
        # Delete the integration
        await self.linkedin_integration_dao.delete(db, integration_id)
        
        logger.info(f"Deleted LinkedIn integration {integration_id} for user {user_id}")
        return True
    
    async def delete_org_linkedin_account(
        self,
        db: AsyncSession,
        org_account_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        user_has_org_delete_linkedin_account_permission: bool = False,
    ) -> bool:
        """
        Delete an org LinkedIn account.
        
        This method is for organization admins to remove LinkedIn accounts
        shared with the organization.
        
        Args:
            db: Database session
            org_account_id: ID of the org LinkedIn account to delete
            organization_id: Organization ID (for verification)
            user_has_org_delete_linkedin_account_permission: Whether the user has the permission to delete LinkedIn accounts
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            HTTPException: If account not found or doesn't belong to org
        """
        # Get the org account
        org_account = await self.org_linkedin_account_dao.get(db, org_account_id)
        
        if not org_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Org LinkedIn account not found"
            )
        
        # Verify it belongs to the specified organization
        if org_account.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This LinkedIn account does not belong to your organization"
            )
        
        if (not user_has_org_delete_linkedin_account_permission) and (org_account.managed_by_user_id != user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to delete this Org LinkedIn Account"
            )
        
        # Delete the account
        success = await self.org_linkedin_account_dao.delete_org_linkedin_account(
            db, org_account_id
        )
        
        if success:
            logger.info(f"Deleted org LinkedIn account {org_account_id} from organization {organization_id}")
        
        return success
    
    async def sync_integration(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        integration_id: uuid.UUID
    ) -> schemas.SyncIntegrationResponse:
        """
        Sync a LinkedIn integration to update available organizations and accounts.
        
        This method performs a complete synchronization:
        1. Refreshes tokens if expired
        2. Fetches current organization roles from LinkedIn
        3. Updates LinkedIn accounts (personal and organizational)
        4. Updates integration state and status
        5. Updates status of org LinkedIn accounts
        
        Args:
            db: Database session
            user_id: User ID (for authorization check)
            integration_id: Integration ID to sync
            
        Returns:
            SyncIntegrationResponse with detailed sync results including:
            - Number of accounts synced, created, and updated
            - Any errors encountered during sync
            - Overall success status
        """
        try:
            # Get and verify integration ownership
            integration = await self.linkedin_integration_dao.get(db, integration_id)
            
            if not integration or integration.user_id != user_id:
                return schemas.SyncIntegrationResponse(
                    success=False,
                    integration_id=integration_id,
                    message="Integration not found or unauthorized"
                )
            
            # Refresh tokens if needed
            try:
                integration = await self._refresh_integration_tokens(db, integration)
                if not integration:
                    return schemas.SyncIntegrationResponse(
                        success=False,
                        integration_id=integration_id,
                        message="Token refresh failed - integration expired",
                        errors=["Failed to refresh access token"]
                    )
            except Exception as e:
                logger.error(f"Token refresh error for integration {integration_id}: {e}")
                await self.linkedin_integration_dao.update_state(
                    db, integration.id, models.LinkedinOauthState.EXPIRED
                )
                await self._update_org_account_statuses(
                    db, integration_id, models.OrgLinkedinAccountStatus.EXPIRED
                )
                
                return schemas.SyncIntegrationResponse(
                    success=False,
                    integration_id=integration_id,
                    message="Token refresh error",
                    errors=[str(e)]
                )
            
            # Create LinkedIn client with current access token
            linkedin_client = self._get_linkedin_client(integration.access_token)
            
            # Initialize counters
            accounts_synced = 0
            new_accounts = 0
            updated_accounts = 0
            errors = []
            
            # Sync personal account
            try:
                success, member_profile = await linkedin_client.get_member_profile()
                if not success:
                    raise Exception("Failed to fetch member profile")
                profile_data = self._extract_member_profile_data(member_profile)
                full_name = f"{member_profile.localized_first_name} {member_profile.localized_last_name}"
                vanity_name = member_profile.vanity_name if hasattr(member_profile, 'vanity_name') else None
                
                # Check if account exists
                existing_account = await self.linkedin_account_dao.get(db, integration.linkedin_id)
                
                if existing_account:
                    await self.linkedin_account_dao.update(
                        db,
                        linkedin_id=integration.linkedin_id,
                        name=full_name,
                        vanity_name=vanity_name,
                        profile_data=profile_data
                    )
                    updated_accounts += 1
                else:
                    await self.linkedin_account_dao.create_or_update(
                        db,
                        linkedin_id=integration.linkedin_id,
                        account_type=models.LinkedinAccountType.PERSON,
                        name=full_name,
                        vanity_name=vanity_name,
                        profile_data=profile_data
                    )
                    new_accounts += 1
                
                accounts_synced += 1
            except Exception as e:
                logger.warning(f"Failed to sync personal account: {e}")
                errors.append(f"Personal account sync failed: {str(e)}")
            
            # Sync organization accounts
            linkedin_orgs_roles = {}
            try:
                success, org_roles_response = await linkedin_client.get_member_organization_roles()
                if not success:
                    raise Exception("Failed to fetch member organization roles")
                
                # Parse organization roles
                linkedin_orgs_roles = await self._parse_organization_roles(org_roles_response)
                
                # Sync organization accounts and get stats
                org_synced, org_new, org_updated, org_errors = await self._sync_organization_accounts(
                    db, linkedin_client, linkedin_orgs_roles
                )
                
                # Update counters
                accounts_synced += org_synced
                new_accounts += org_new
                updated_accounts += org_updated
                errors.extend(org_errors)
                        
            except Exception as e:
                logger.warning(f"Failed to fetch organization roles: {e}")
                errors.append(f"Organization roles fetch failed: {str(e)}")
            
            # Update integration with new orgs/roles if changed
            if linkedin_orgs_roles != integration.linkedin_orgs_roles:
                await self.linkedin_integration_dao.update_linkedin_orgs_roles(
                    db, integration.id, linkedin_orgs_roles
                )
            
            # Update integration state to active and refresh last sync timestamp
            await self.linkedin_integration_dao.update_state(
                db, integration.id, models.LinkedinOauthState.ACTIVE
            )
            
            integration.last_sync_at = datetime_now_utc()
            db.add(integration)
            await db.commit()
            
            # Update all org account statuses to active
            await self._update_org_account_statuses(
                db, integration_id, models.OrgLinkedinAccountStatus.ACTIVE
            )
            
            logger.info(
                f"Synced integration {integration_id} for user {user_id}: "
                f"{accounts_synced} accounts, {new_accounts} new, {updated_accounts} updated"
            )
            
            return schemas.SyncIntegrationResponse(
                success=True,
                integration_id=integration_id,
                message="Integration synced successfully",
                accounts_synced=accounts_synced,
                new_accounts=new_accounts,
                updated_accounts=updated_accounts,
                errors=errors
            )
            
        except Exception as e:
            logger.error(f"Error syncing integration {integration_id}: {e}", exc_info=True)
            return schemas.SyncIntegrationResponse(
                success=False,
                integration_id=integration_id,
                message=f"Sync failed: {str(e)}",
                errors=[str(e)]
            )
    
    async def _update_org_account_statuses(
        self,
        db: AsyncSession,
        integration_id: uuid.UUID,
        status: models.OrgLinkedinAccountStatus
    ) -> None:
        """
        Update status for all organization accounts using a specific integration.
        
        This is typically called when an integration's status changes (e.g., tokens expire)
        to reflect that change across all associated organization accounts.
        
        Args:
            db: Database session
            integration_id: Integration ID whose accounts should be updated
            status: New status to set (ACTIVE, EXPIRED, or REVOKED)
        """
        try:
            org_accounts = await self.org_linkedin_account_dao.get_by_integration(db, integration_id)
            
            if org_accounts:
                for org_account in org_accounts:
                    org_account.status = status
                    db.add(org_account)
                
                await db.commit()
                logger.info(
                    f"Updated {len(org_accounts)} org accounts to status {status.value} "
                    f"for integration {integration_id}"
                )
            else:
                logger.debug(f"No org accounts found for integration {integration_id}")
                
        except Exception as e:
            logger.error(
                f"Error updating org account statuses for integration {integration_id}: {e}",
                exc_info=True
            )
            # Don't raise - this is a best-effort operation
            # The main operation should continue even if status update fails
    
    async def refresh_all_integrations(
        self,
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> schemas.RefreshAllIntegrationsResponse:
        """
        Refresh all LinkedIn integrations for a user.
        
        Performs a sync operation on each of the user's LinkedIn integrations,
        updating all associated accounts and organization data. This is useful
        for bulk updates or scheduled synchronization tasks.
        
        The method continues processing even if individual integrations fail,
        collecting all errors for reporting.
        
        Args:
            db: Database session
            user_id: User ID whose integrations should be refreshed
            
        Returns:
            RefreshAllIntegrationsResponse containing:
            - success: True if all integrations synced successfully
            - message: Summary message
            - integrations_processed: Total number of integrations attempted
            - accounts_synced: Total accounts successfully synced across all integrations
            - errors: Dict mapping integration_id to list of error messages
        """
        integrations = await self.linkedin_integration_dao.get_by_user_id(db, user_id)
        
        if not integrations:
            logger.info(f"No integrations found for user {user_id}")
            return schemas.RefreshAllIntegrationsResponse(
                success=True,
                message="No integrations to refresh",
                integrations_processed=0,
                accounts_synced=0,
                errors={}
            )
        
        logger.info(f"Starting refresh of {len(integrations)} integrations for user {user_id}")
        
        integrations_processed = 0
        total_accounts_synced = 0
        errors = {}
        
        for integration in integrations:
            try:
                sync_result = await self.sync_integration(db, user_id, integration.id)
                integrations_processed += 1
                
                if sync_result.success:
                    total_accounts_synced += sync_result.accounts_synced or 0
                else:
                    errors[str(integration.id)] = sync_result.errors
                    
            except Exception as e:
                # Catch any unexpected errors to continue processing other integrations
                logger.error(
                    f"Unexpected error refreshing integration {integration.id}: {e}",
                    exc_info=True
                )
                errors[str(integration.id)] = [f"Unexpected error: {str(e)}"]
                integrations_processed += 1
        
        success = len(errors) == 0
        
        if success:
            message = f"Successfully refreshed {integrations_processed} integrations"
        else:
            message = f"Refresh completed with errors in {len(errors)} of {integrations_processed} integrations"
        
        logger.info(
            f"Completed refresh for user {user_id}: {integrations_processed} processed, "
            f"{total_accounts_synced} accounts synced, {len(errors)} errors"
        )
        
        return schemas.RefreshAllIntegrationsResponse(
            success=success,
            message=message,
            integrations_processed=integrations_processed,
            accounts_synced=total_accounts_synced,
            errors=errors
        )
    
    async def list_user_accessible_accounts(
        self,
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> schemas.UserAccessibleLinkedinAccountsResponse:
        """
        List all LinkedIn accounts accessible to a user.
        
        Returns a comprehensive list of LinkedIn accounts the user can access:
        - Personal LinkedIn account (if connected)
        - Organization accounts the user has access to via integrations
        
        For each account, includes:
        - Account details (name, type, profile data)
        - User's role in the organization (if applicable)
        - Whether the user can post to the account
        - Integration status (active, expired, etc.)
        
        Args:
            db: Database session
            user_id: User ID to list accounts for
            
        Returns:
            UserAccessibleLinkedinAccountsResponse containing:
            - personal_account: User's personal LinkedIn account (if any)
            - organization_accounts: List of accessible organization accounts
            - total: Total number of accessible accounts
        """
        integrations = await self.linkedin_integration_dao.get_by_user_id(db, user_id)
        
        personal_account = None
        organization_accounts = []
        
        for integration in integrations:
            # Process personal account
            personal_linkedin_account = await self.linkedin_account_dao.get(db, integration.linkedin_id)
            
            if personal_linkedin_account and personal_linkedin_account.account_type == models.LinkedinAccountType.PERSON:
                personal_account = schemas.LinkedinAccountWithRole(
                    account=schemas.LinkedinAccountRead.model_validate(personal_linkedin_account),
                    role=None,  # Personal accounts don't have roles
                    integration_id=integration.id,
                    integration_state=integration.integration_state,
                    can_post=True  # Users can always post to their own account
                )
            
            # Process organization accounts
            if integration.linkedin_orgs_roles:
                for org_id, org_info in integration.linkedin_orgs_roles.items():
                    org_linkedin_account = await self.linkedin_account_dao.get(db, org_id)
                    
                    if org_linkedin_account:
                        # Get the user's role in this organization
                        role = org_info.get("role")
                        
                        # Check if user can post based on their role
                        can_post = self._can_user_post_to_organization(role)
                        
                        org_account_with_role = schemas.LinkedinAccountWithRole(
                            account=schemas.LinkedinAccountRead.model_validate(org_linkedin_account),
                            role=role,
                            integration_id=integration.id,
                            integration_state=integration.integration_state,
                            can_post=can_post
                        )
                        
                        organization_accounts.append(org_account_with_role)
        
        # Calculate total accessible accounts
        total = (1 if personal_account else 0) + len(organization_accounts)
        
        return schemas.UserAccessibleLinkedinAccountsResponse(
            personal_account=personal_account,
            organization_accounts=organization_accounts,
            total=total
        ) 