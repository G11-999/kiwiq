"""
LinkedIn OAuth Service Layer

This module implements the business logic for LinkedIn OAuth operations,
following KiwiQ's established service patterns with dependency injection.
"""

import uuid
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status, BackgroundTasks, Request

from kiwi_app.auth.models import User, Organization, UserOrganizationRole
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

from linkedin_integration.client.linkedin_auth_client import LinkedInAccessTokenSchema, AuthClient, LINKEDIN_SCOPES
from linkedin_integration.client.linkedin_client import LinkedInClient, UserInfo

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
        
        # LinkedIn API client for user data
        self._linkedin_client = LinkedInClient(
            client_id=settings.LINKEDIN_CLIENT_ID,
            client_secret=settings.LINKEDIN_CLIENT_SECRET
        )
    
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
        authorization_url = auth_client.generate_member_auth_url(
            scopes=LINKEDIN_SCOPES,
            state=state_token
        )
        
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
            token_response = auth_client.exchange_auth_code_for_access_token(code)
            
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
            
            # Set access token for API calls
            await self._linkedin_client._set_access_token(token_data.access_token)
            
            # Get LinkedIn user info
            success, user_info = await self._linkedin_client.get_member_info_including_email()
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
        logger.info(f"JWT CSRF token: {jwt_csrf_token} -- token_data: {token_data}")
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
    ) -> Tuple[User, models.LinkedinUserOauth]:
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
            Tuple of (User, LinkedinUserOauth)
            
        Raises:
            LinkedInOauthException: For registration errors
            LinkedInStateException: For invalid state tokens
        """
        # State data is already verified by the dependency
        linkedin_id = state_data['linkedin_id']
        oauth_record_pending = await self.linkedin_oauth_dao.get(db, linkedin_id)
        if not oauth_record_pending:
            raise exceptions.LinkedInOauthException("Pending LinkedIn OAuth record not found.")
        
        # Create user registration data
        user_create = auth_schemas.UserCreate(
            email=registration_data.email,
            full_name=registration_data.full_name,
            password=None,  # No password for OAuth users
            agree_to_terms=registration_data.agree_to_terms
        )
        
        # Register new user (skip email verification if LinkedIn verified)
        skip_email = state_data.get("email_verified", False)
        user = await self.auth_service.register_new_user(
            db=db,
            user_in=user_create,
            background_tasks=background_tasks,
            base_url=base_url if not skip_email else None,
            registered_by_admin=False,
            is_verified=True,
        )
        
        if skip_email and not user.is_verified:
            await self.user_dao.update(db, db_obj=user, obj_in=auth_schemas.UserUpdate(is_verified=True))
        
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
        
        return user, oauth_record
    
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
            response = auth_client.exchange_refresh_token_for_access_token(
                oauth_record.refresh_token
            )
            
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