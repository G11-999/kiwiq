from pydantic_settings import BaseSettings
from typing import Optional, List, Dict
from pydantic import Field

from global_config.settings import ENV_FILE_PATH, Settings as GlobalSettings, global_settings as global_settings

class Settings(GlobalSettings):
    # --- Auth Settings --- #
    SECRET_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 10
    MAGIC_LINK_TOKEN_EXPIRE_MINUTES: int = 10
    
    EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = 1440

    DEFAULT_SUPERUSER_EMAIL: Optional[str] = None
    DEFAULT_SUPERUSER_PASSWORD: Optional[str] = None

    DB_TABLE_AUTH_PREFIX: str = "auth_"
    DB_TABLE_BILLING_PREFIX: str = "billing_"  # Added prefix for billing tables

    DB_TABLE_WORKFLOW_PREFIX: str = "kw_wf_" # Added prefix for workflow tables
    DB_TABLE_LINKEDIN_PREFIX: str = "linkedin_"

    # LinkedIn integration settings
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""
    LINKEDIN_API_VERSION: str = "202505"
    LINKEDIN_API_MEMBER_ANALYTICS_VERSION: str = "202506"
    LINKEDIN_REDIRECT_URL: str = ""
    LINKEDIN_ACCESS_TOKEN: str = ""  # NOTE: only for testing!

    # --- Gmail SMTP Settings --- #
    """
    Gmail SMTP Configuration Guide:
    
    Gmail supports two main SMTP configurations:
    
    1. Port 587 with STARTTLS (RECOMMENDED):
       - GMAIL_SMTP_PORT: 587
       - MAIL_SSL_TLS: False (no implicit TLS)
       - MAIL_STARTTLS: True (upgrade plain connection to TLS)
       - Works with both smtp.gmail.com and smtp-relay.gmail.com
    
    2. Port 465 with implicit SSL/TLS:
       - GMAIL_SMTP_PORT: 465  
       - MAIL_SSL_TLS: True (implicit TLS from connection start)
       - MAIL_STARTTLS: False (no STARTTLS needed)
       - Works with smtp.gmail.com (smtp-relay.gmail.com doesn't support port 465)
    
    Common Issues:
    - Port 587 + MAIL_SSL_TLS=True → SSL: WRONG_VERSION_NUMBER error
    - Port 465 + MAIL_STARTTLS=True → Connection timeout or SSL errors
    - Both MAIL_SSL_TLS and MAIL_STARTTLS True → Configuration conflict
    
    For production, always use encrypted connections (either configuration above).
    Never use plain SMTP without encryption for sensitive data.
    """
    GMAIL_SMTP_USERNAME: Optional[str] = None # Your Gmail address (e.g., your_email@gmail.com)
    GMAIL_SMTP_PASSWORD: Optional[str] = None # Your Gmail App Password (NOT your regular password)
    GMAIL_SMTP_FROM: Optional[str] = None     # The email address emails should be sent from
    GMAIL_SMTP_PORT: int = 587                # Gmail STARTTLS port (587) or SSL/TLS port (465)
    GMAIL_SMTP_SERVER: str = "smtp-relay.gmail.com"  # smtp-relay.gmail.com or smtp.gmail.com
    # TLS Configuration - Choose ONE of these two configurations:
    # Configuration 1: Port 587 with STARTTLS (recommended for Gmail)
    MAIL_STARTTLS: bool = True                # Start plain, upgrade to TLS
    MAIL_SSL_TLS: bool = False                # No implicit TLS from start
    # Configuration 2: Port 465 with implicit SSL/TLS (alternative)
    # MAIL_STARTTLS: bool = False             # No STARTTLS needed
    # MAIL_SSL_TLS: bool = True               # Implicit TLS from connection start
    # GMAIL_SMTP_PORT: int = 465              # Change port to 465
    USE_CREDENTIALS: bool = True
    VALIDATE_CERTS: bool = True
    MAIL_FROM_NAME: Optional[str] = "KiwiQ Verification" # Optional: Sender name

    # --- Logging Settings --- #
    LOG_LEVEL: str = "INFO"

    # --- Cookie Settings --- #
    # Add settings for cookie security (optional but recommended)
    """
    cookie_secure (True):

    When set to True, the cookie is only sent over HTTPS connections. This prevents the cookie from being transmitted over unencrypted HTTP, helping protect sensitive data from eavesdropping.

    cookie_httponly (True):

    When enabled, this setting prevents client-side JavaScript from accessing the cookie. This adds a layer of protection against cross-site scripting (XSS) attacks by ensuring that the cookie can't be read or manipulated by scripts running in the browser.

    cookie_samesite (lax):

    This setting controls when cookies are sent along with cross-site requests.

    Lax (default): Cookies are sent on top-level navigations (e.g., clicking a link) but are withheld on less safe cross-site requests (like iframes or AJAX calls), helping mitigate CSRF (Cross-Site Request Forgery) attacks.

    Strict: Cookies are only sent in a first-party context (i.e., when the site for the cookie's domain is currently being visited).

    None: Cookies are sent with all requests, including cross-origin requests—but this requires cookie_secure to be True.
    """
    # --- Cookie Settings --- #
    ACCESS_TOKEN_COOKIE_NAME: str = "access_token"
    REFRESH_COOKIE_NAME: str = "refresh_token"
    CSRF_TOKEN_COOKIE_NAME: str = "XSRF-TOKEN"  # Standard name for CSRF cookie, readable by JavaScript
    CSRF_TOKEN_HEADER_NAME: str = "X-XSRF-TOKEN"
    CSRF_TOKEN_LENGTH: int = 32  # Length in bytes for token generation
    COOKIE_SECURE: bool = global_settings.APP_ENV in ["PROD", "STAGE"] # Set to False for local HTTP development ONLY
    COOKIE_DOMAIN: Optional[str] = ".kiwiq.ai" if global_settings.APP_ENV in ["PROD", "STAGE"] else None
    COOKIE_HTTPONLY: bool = True
    COOKIE_SAMESITE: str = "lax" # Or "strict"

    # NOTE: set this URL to the route to get auth token from without global prefix!
    AUTH_TOKEN_URL: str = "/auth/login/token"
    AUTH_REFRESH_URL: str = "/auth/refresh"
    AUTH_VERIFY_EMAIL_URL: str = "/auth/verify-email"
    AUTH_VERIFY_EMAIL_CHANGE_URL: str = "/auth/verify-email-change"
    AUTH_VERIFY_PASSWORD_RESET_TOKEN_URL: str = "/auth/verify-password-reset-token"
    MAGIC_LOGIN_URL: str = "/auth/magic-login"
    LINKEDIN_AUTH_CALLBACK_URL: str = "/linkedin/auth/callback"
    LINKEDIN_AUTH_VERIFY_LINKING_URL: str = "/linkedin/auth/verify-linking"
    REDIRECT_BASE_URL: str = "https://beta.kiwiq.ai"  # "http://localhost:3000"
    # Frontend URLs for first steps guide email
    # These URLs are used in the first steps guide email sent after email verification
    # They should point to the frontend application pages where users can take their next steps
    URL_CREATE_NEW_POST: str = f"{REDIRECT_BASE_URL}/studio/post/new"
    URL_EXPLORE_CONTENT_IDEAS: str = f"{REDIRECT_BASE_URL}/studio/idea/new"
    URL_CONTENT_CALENDAR: str = f"{REDIRECT_BASE_URL}/calendar"
    
    # TODO: FIXME: fill these up in production to redirect correctly to the SPA to handle verification / password reset!
    VERIFY_EMAIL_SPA_URL: Optional[str] = f"{REDIRECT_BASE_URL}/auth/verify-email"
    VERIFY_EMAIL_CHANGE_SPA_URL: Optional[str] = f"{REDIRECT_BASE_URL}/auth/verify-email-change"
    VERIFY_PASSWORD_RESET_TOKEN_SPA_URL: Optional[str] = f"{REDIRECT_BASE_URL}/auth/verify-password-reset-token"
    MAGIC_LOGIN_SPA_URL: Optional[str] = f"{REDIRECT_BASE_URL}/auth/email-login"
    LINKEDIN_OAUTH_CALLBACK_SPA_URL: Optional[str] = f"{REDIRECT_BASE_URL}/auth/linkedin-callback"
    LINKEDIN_VERIFY_LINKING_SPA_URL: Optional[str] = f"{REDIRECT_BASE_URL}/auth/linkedin-verify"  # URL to handle email verification links for linkedin account creation / linking / verification
    
    # LinkedIn OAuth Frontend URLs
    LINKEDIN_LOGIN_SPA_URL: Optional[str] = f"{REDIRECT_BASE_URL}/login"  # Show user errors during login with query params that linkedin linking failed
    LINKEDIN_DASHBOARD_SPA_URL: Optional[str] = f"{REDIRECT_BASE_URL}/dashboard"  # redirect to dashboard after login via linkedin
    LINKEDIN_SETTINGS_SPA_URL: Optional[str] = f"{REDIRECT_BASE_URL}/settings"  # redirect to settings to show newly linkedin linkedin account
    LINKEDIN_REGISTER_SPA_URL: Optional[str] = f"{REDIRECT_BASE_URL}/register"  # Ask user to complete new account registration to finish linkedin linking
    LINKEDIN_VERIFY_ACCOUNT_SPA_URL: Optional[str] = f"{REDIRECT_BASE_URL}/verify-account"  # For unverified linkedin emails i.e. user email is not verified by Linkedin
    # LINKEDIN_CONFLICT_SPA_URL: Optional[str] = f"{REDIRECT_BASE_URL}/linkedin-conflict"  # Conflict: show user that linkedin account linked to another KIWIQ user account
    # NOTE: if API prefix var name changes, change it here: `security.py` to set `OAuth2PasswordBearer``
    # NOTE: also used in verify email url!
    API_V1_PREFIX: str = "/api/v1"

    # --- Billing & Stripe Settings --- #
    # Stripe API configuration
    STRIPE_SECRET_KEY: Optional[str] = Field(None, env="STRIPE_SECRET_KEY")
    STRIPE_PUBLISHABLE_KEY: Optional[str] = Field(None, env="STRIPE_PUBLISHABLE_KEY")
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(None, env="STRIPE_WEBHOOK_SECRET")
    STRIPE_API_VERSION: str = Field("2025-05-28.basil", env="STRIPE_API_VERSION")
    
    # Billing configuration
    # BILLING_TRIAL_DAYS_DEFAULT: int = Field(14, description="Default trial period in days")
    # BILLING_GRACE_PERIOD_DAYS: int = Field(3, description="Grace period for failed payments")
    
    # Credit pricing (in dollars to support fractional pricing)
    # CREDIT_PRICE_WORKFLOWS_DOLLARS: float = Field(0.10, description="Price per workflow credit in dollars")
    # CREDIT_PRICE_WEB_SEARCHES_DOLLARS: float = Field(0.02, description="Price per web search credit in dollars")
    # CREDIT_PRICE_DOLLAR_CREDITS_RATIO: float = Field(1.2, description="Markup ratio for dollar credits (1.2 = 20% markup)")
    CREDIT_PRICE_IN_DOLLARS: Dict[str, float] = Field(
        {
            "workflows": 0.05,
            "web_searches": 0.05,
            "default": 0.02
        }, description="Price per credit in dollars"
    )
    SCRAPING_CREDIT_PRICE: float = Field(0.01, description="Price per scraping credit in dollars (1 cent)")
    
    # Minimum purchase amounts
    MINIMUM_DOLLAR_CREDITS_PURCHASE: float = Field(5.0, description="Minimum dollar credits purchase amount in dollars")
    
    # Overage policies
    OVERAGE_GRACE_PERCENTAGE: int = Field(10, ge=0, le=100, description="Percentage of monthly allocation allowed as grace")
    MAX_OVERAGE_ABSOLUTE: Dict[str, float] = Field(
        {
            "workflows": 20.0,
            "web_searches": 10.0,
            "default": 5.0,
        }, description="Maximum credits overage per month allowed (absolute value)"
    )
    # OVERAGE_HARD_LIMIT_MULTIPLIER: float = Field(1.5, description="Hard limit as multiplier of monthly allocation")
    
    # Credit expiration policies (in days)
    SUBSCRIPTION_CREDITS_EXPIRE_DAYS: int = Field(31, description="Days until subscription credits expire")
    SUBSCRIPTION_CREDITS_EXPIRE_DAYS_ANNUAL: int = Field(366, description="Days until subscription credits expire for annual plans")
    PURCHASED_CREDITS_EXPIRE_DAYS: int = Field(365, description="Days until purchased credits expire")
    TRIAL_CREDITS_EXPIRE_DAYS: int = Field(7, description="Days until trial credits expire")
    TRIAL_CREDITS_PRORATION_FACTOR: float = Field(0.25, description="Factor for proration of trial credits")
    MAX_TRIAL_CREDITS: Dict[str, float] = Field(
        {
            "workflows": 20,
            "web_searches": 20,
            "default": 10
        }, description="Maximum number of credits for trial"
    )
    MIN_SEATS_ALLOWED_WITHOUT_SUBSCRIPTION: int = Field(1, description="Minimum number of seats allowed without a subscription")
    
    # # Webhook processing
    # WEBHOOK_RETRY_MAX_ATTEMPTS: int = Field(3, description="Maximum webhook retry attempts")
    # WEBHOOK_RETRY_DELAY_SECONDS: int = Field(5, description="Initial delay between webhook retries")
    # WEBHOOK_IDEMPOTENCY_TTL_SECONDS: int = Field(86400, description="TTL for webhook idempotency keys (24 hours)")
    
    # # Usage tracking and caching
    # CREDIT_BALANCE_CACHE_TTL_SECONDS: int = Field(300, description="TTL for credit balance cache (5 minutes)")
    # USAGE_EVENT_BATCH_SIZE: int = Field(100, description="Batch size for processing usage events")
    
    # # Rate limiting for billing operations
    # BILLING_API_RATE_LIMIT_PER_MINUTE: int = Field(60, description="Rate limit for billing API calls per minute")
    # CREDIT_CONSUMPTION_RATE_LIMIT_PER_SECOND: int = Field(10, description="Rate limit for credit consumption per second")

    # --- Workflow Service Settings (Merged from config.py) --- #

    # --- RabbitMQ Settings --- #
    # Name for the persistent workflow event stream
    WORKFLOW_EVENTS_STREAM: str = Field(default="kiwiq_workflow_events_stream")
    # Consumer group name for the FastAPI backend consumer
    WORKFLOW_EVENTS_CONSUMER_GROUP: str = Field(default="kiwiq_backend_consumer_group")
    # --- Workflow Stream Queue Settings --- #
    WORKFLOW_STREAM_EVENTS_EXPIRATION: int = Field(default=60 * 60 * 24 * 30) # 30 days default
    WORKFLOW_STREAM_EVENTS_MAX_LENGTH_BYTES: int = Field(default=1024 * 1024 * 1024 * 10) # 10 GB default
    WORKFLOW_STREAM_EVENTS_MAX_AGE: str = Field(default="30D") # 30 days default; after which stream messages will be deleted!
    # --- Workflow Notifications Queue Settings (Standard Queue) --- #
    WORKFLOW_NOTIFICATIONS_QUEUE: str = Field(default="kiwiq_workflow_notifications_queue")
    WORKFLOW_NOTIFICATIONS_TTL_MS: int = Field(default=60 * 60 * 24 * 7 * 1000) # 7 days in milliseconds
    WORKFLOW_NOTIFICATIONS_MAX_LENGTH_BYTES: int = Field(default=1024 * 1024 * 512) # 512 MB default

    # --- MongoDB Settings --- #
    # URL coming from global settings
    # MONGO_URL: str = Field(..., env="MONGO_URI") # Make URI required
    # --- Workflow Database Settings --- #
    MONGO_WORKFLOW_DATABASE: str = Field(default="kiwiq_workflow_db", env="MONGO_WORKFLOW_DATABASE")
    MONGO_WORKFLOW_STREAM_COLLECTION: str = Field(default="workflow_stream_data", env="MONGO_WORKFLOW_STREAM_COLLECTION")
    MONGO_WORKFLOW_STREAM_SEGMENTS: List[str] = Field(default=["org_id", "user_id", "run_id", "event_id"])
    MONGO_WORKFLOW_STREAM_SEGMENTS_VALUE_FILTER_FIELDS: Optional[List[str]] = Field(default=["event_type"])
    # --- Customer Database Settings --- #
    MONGO_CUSTOMER_DATABASE: str = Field(default="kiwiq_customer_db", env="MONGO_CUSTOMER_DATABASE")
    MONGO_CUSTOMER_COLLECTION: str = Field(default="customer_data", env="MONGO_CUSTOMER_COLLECTION")
    MONGO_CUSTOMER_SEGMENTS: List[str] = Field(default=["org_id", "user_id", "namespace", "docname"])
    MONGO_CUSTOMER_SEGMENTS_VALUE_FILTER_FIELDS: Optional[List[str]] = Field(
        default=["created_at", "updated_at", "scheduled_date"],  # Allow filtering by namespace/docname
        env="MONGO_CUSTOMER_SEGMENTS_VALUE_FILTER_FIELDS"
    )
    
    # --- WebSocket Settings --- #
    # Secret for potentially encoding/decoding WebSocket auth tokens
    WEBSOCKET_AUTH_SECRET: str = Field(default="super-secret-websocket-key", env="WEBSOCKET_AUTH_SECRET")
    WEBSOCKET_TOKEN_EXPIRE_MINUTES: int = Field(default=60 * 24 * 7) # 1 week default

    # --- User App State --- #
    USER_STATE_NAMESPACE: str = Field(default="user_state", env="USER_STATE_NAMESPACE")
    USER_STATE_DOCNAME: str = Field(default="user_state_{entity_username}", env="USER_STATE_DOCNAME")

    

settings = Settings()
print(settings.MONGO_WORKFLOW_STREAM_SEGMENTS)
