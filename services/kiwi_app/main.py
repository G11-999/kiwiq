# PYTHONPATH=$(pwd):$(pwd)/services  poetry run uvicorn services.kiwi_app.main:app --host 0.0.0.0 --port 8000
# PYTHONPATH=$(pwd):$(pwd)/services  poetry run python ./services/kiwi_app/main.py
# PYTHONPATH=$(pwd):$(pwd)/services  poetry run uvicorn main:app --app-dir services/kiwi_app --reload
import asyncio
import logging # Import logging
from contextlib import asynccontextmanager # Import asynccontextmanager
from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from kiwi_app.utils import get_kiwi_logger
from kiwi_app.settings import settings # Import settings
from kiwi_app import auth

from kiwi_app.workflow_app import routes as workflow_routes
from kiwi_app.workflow_app import customer_data_routes as customer_data_routes
from kiwi_app.workflow_app import event_consumer
from kiwi_app.workflow_app import dependencies as wf_deps
from scraper_service import scraping_routes
from kiwi_app.workflow_app import app_state as app_state_routes
from kiwi_app.workflow_app import app_artifacts as app_artifacts_routes
from kiwi_app.workflow_app import websockets as websocket_routes
from kiwi_app.billing import routers as billing_routers
from linkedin_integration import routers as linkedin_integration_routers

# Get a logger instance for the main application

tags_metadata = [
    {
        "name": "auth",
        "description": "Auth API endpoints including login, logout, register, verify email, verify password reset token, etc."
    },
    {
        "name": "organizations",
        "description": "Manage organizations. These endpoints allow you to read, update, and delete organizations, check or add/update membership, etc.",
        # "externalDocs": {
        #     "description": "Find more info",
        #     "url": "https://fastapi.tiangolo.com/"
        # }
    },
    {
        "name": "users",
        "description": "Manage users. These endpoints allow you to read your profile, update your profile etc.",
    },
    {
        "name": "admin",
        "description": "Admin API endpoints including creating roles, permissions, etc.",
    },
]

# --- Lifespan Context Manager --- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup and shutdown events."""
    # Startup logic
    kiwi_logger = get_kiwi_logger()
    kiwi_logger.info("Application starting up...")
    kiwi_logger.info(f"Log level set to: {settings.LOG_LEVEL.upper()}")
    await wf_deps.get_node_template_registry()
    # Add any other startup logic/logging here (e.g., initializing DB connections, loading models)
    # await init_db() # Ensure this is commented out if using Alembic

    try:
        # === Startup: Directly call start_event_consumer ===
        kiwi_logger.info("Attempting to start event consumer...")
        broker_instance = await event_consumer.start_event_consumer() # NO main() here
        app.state.event_broker = broker_instance # Optional: store instance
        kiwi_logger.info("Event consumer started successfully via lifespan.")

        yield # <-- FastAPI app runs

    except Exception as e:
        kiwi_logger.error(f"Error during application startup: {e}", exc_info=True)
        # Optionally re-raise or handle to prevent app from starting partially
        raise
    finally:
        # === Shutdown: Directly call stop_event_consumer ===
        kiwi_logger.info("Application shutting down...")
        kiwi_logger.info("Attempting to stop event consumer...")
        await event_consumer.stop_event_consumer(app.state.event_broker) # NO main() here
        if hasattr(app.state, "event_broker"):
             del app.state.event_broker # Optional: clean up state
        kiwi_logger.info("Event consumer stopped successfully via lifespan.")
        kiwi_logger.info("Cleanup finished.")

    # asyncio.create_task(event_consumer.main())
    # yield



    # Shutdown logic
    kiwi_logger.info("Application shutting down...")
    # Add any cleanup logic here

# --- Custom Swagger UI HTML with CSRF Support --- #
def get_swagger_ui_html(
    *,
    openapi_url: str,
    title: str,
    swagger_js_url: str = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
    swagger_css_url: str = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    swagger_favicon_url: str = "https://fastapi.tiangolo.com/img/favicon.png",
    oauth2_redirect_url: str = None,
) -> HTMLResponse:
    """
    Generate custom Swagger UI HTML with proper CSRF request interceptor.
    
    This custom implementation ensures the requestInterceptor is treated as a 
    JavaScript function rather than a string, which was the issue with the 
    built-in FastAPI swagger_ui_parameters approach.
    """
    
    if oauth2_redirect_url is None:
        oauth2_redirect_url = "/docs/oauth2-redirect"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <link type="text/css" rel="stylesheet" href="{swagger_css_url}">
        <link rel="shortcut icon" href="{swagger_favicon_url}">
        <title>{title} - Swagger UI</title>
        <style>
            /* Custom styles for the Org ID form */
            .org-id-form {{
                background: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                padding: 20px;
                margin: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }}
            .org-id-form h3 {{
                margin: 0 0 15px 0;
                color: #495057;
                font-size: 18px;
                font-weight: 600;
            }}
            .org-id-form-row {{
                display: flex;
                align-items: center;
                gap: 10px;
                flex-wrap: wrap;
            }}
            .org-id-input {{
                flex: 1;
                min-width: 200px;
                padding: 8px 12px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                font-size: 14px;
                font-family: monospace;
            }}
            .org-id-button {{
                background: #007bff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                transition: background-color 0.2s;
            }}
            .org-id-button:hover {{
                background: #0056b3;
            }}
            .org-id-clear {{
                background: #6c757d;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                transition: background-color 0.2s;
            }}
            .org-id-clear:hover {{
                background: #545b62;
            }}
            .org-id-status {{
                margin-top: 10px;
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: 500;
            }}
            .org-id-status.active {{
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }}
            .org-id-status.inactive {{
                background: #fff3cd;
                color: #856404;
                border: 1px solid #ffeaa7;
            }}
        </style>
    </head>
    <body>
        <!-- Custom Organization ID Form -->
        <div class="org-id-form">
            <h3>🏢 Organization Context</h3>
            <div class="org-id-form-row">
                <input 
                    type="text" 
                    id="org-id-input" 
                    class="org-id-input"
                    placeholder="Enter Organization ID (UUID)"
                    pattern="[0-9a-f-]{{36}}"
                    title="Organization ID should be a valid UUID"
                />
                <button id="set-org-button" class="org-id-button" onclick="setOrgId()">
                    Set Active Org
                </button>
                <button id="clear-org-button" class="org-id-clear" onclick="clearOrgId()">
                    Clear
                </button>
            </div>
            <div id="org-status" class="org-id-status inactive">
                No active organization set. Requests will not include X-Active-Org header.
            </div>
        </div>
        
        <div id="swagger-ui">
        </div>
        <script src="{swagger_js_url}"></script>
        <script>
        console.log('🚀 Loading custom Swagger UI with CSRF support...');
        
        // Global variable to store the active organization ID
        var activeOrgId = localStorage.getItem('activeOrgId') || null;
        
        // Organization ID Management Functions
        function setOrgId() {{
            var input = document.getElementById('org-id-input');
            var orgId = input.value.trim();
            
            if (!orgId) {{
                alert('Please enter an Organization ID');
                return;
            }}
            
            // Basic UUID validation
            var uuidRegex = /^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$/i;
            if (!uuidRegex.test(orgId)) {{
                alert('Please enter a valid UUID format for Organization ID');
                return;
            }}
            
            activeOrgId = orgId;
            localStorage.setItem('activeOrgId', orgId);
            updateOrgStatus();
            console.log('🏢 Active Organization ID set to:', orgId);
        }}
        
        function clearOrgId() {{
            activeOrgId = null;
            localStorage.removeItem('activeOrgId');
            document.getElementById('org-id-input').value = '';
            updateOrgStatus();
            console.log('🏢 Active Organization ID cleared');
        }}
        
        function updateOrgStatus() {{
            var statusElement = document.getElementById('org-status');
            var inputElement = document.getElementById('org-id-input');
            
            if (activeOrgId) {{
                statusElement.className = 'org-id-status active';
                statusElement.textContent = `✅ Active Organization: ${{activeOrgId}}`;
                inputElement.value = activeOrgId;
            }} else {{
                statusElement.className = 'org-id-status inactive';
                statusElement.textContent = 'No active organization set. Requests will not include X-Active-Org header.';
            }}
        }}
        
        // Initialize the form with saved org ID
        document.addEventListener('DOMContentLoaded', function() {{
            updateOrgStatus();
            
            // Allow Enter key to set org ID
            document.getElementById('org-id-input').addEventListener('keypress', function(e) {{
                if (e.key === 'Enter') {{
                    setOrgId();
                }}
            }});
        }});
        
        // Enhanced Request Interceptor Function (CSRF + Organization)
        function enhancedRequestInterceptor(req) {{
            console.log('🔧 Enhanced Request interceptor called for:', req.url);
            
            // Skip OpenAPI spec requests
            if (req.loadSpec) {{
                console.log('⏭️ Skipping OpenAPI spec request');
                return req;
            }}
            
            console.log('📝 Processing API request (not OpenAPI spec)');
            
            // 1. Handle CSRF Protection
            var cookies = document.cookie.split(';');
            var csrfToken = null;
            var cookieName = '{settings.CSRF_TOKEN_COOKIE_NAME}';
            
            for (var i = 0; i < cookies.length; i++) {{
                var cookie = cookies[i].trim();
                if (cookie.indexOf(cookieName + '=') === 0) {{
                    csrfToken = cookie.substring((cookieName + '=').length);
                    break;
                }}
            }}
            
            if (csrfToken) {{
                req.headers['{settings.CSRF_TOKEN_HEADER_NAME}'] = csrfToken;
                console.log('🔒 CSRF token added to request:', csrfToken.substring(0, 8) + '...');
            }} else {{
                console.warn('⚠️ No CSRF token found in cookies');
                console.log('🍪 Available cookies:', document.cookie);
                console.log('🔍 Looking for cookie:', cookieName);
            }}
            
            // 2. Handle Organization Context
            // Only add X-Active-Org if:
            // - activeOrgId is set from the form
            // - X-Active-Org header is not already present in the request
            if (activeOrgId && !req.headers['X-Active-Org']) {{
                req.headers['X-Active-Org'] = activeOrgId;
                console.log('🏢 Organization ID added to request:', activeOrgId);
            }} else if (req.headers['X-Active-Org']) {{
                console.log('🏢 X-Active-Org header already present in request:', req.headers['X-Active-Org']);
            }} else if (!activeOrgId) {{
                console.log('🏢 No active organization ID set - skipping X-Active-Org header');
            }}
            
            return req;
        }}
        
        // Initialize Swagger UI
        const ui = SwaggerUIBundle({{
            url: '{openapi_url}',
            dom_id: '#swagger-ui',
            layout: 'BaseLayout',
            deepLinking: true,
            showExtensions: true,
            showCommonExtensions: true,
            withCredentials: true,
            requestInterceptor: enhancedRequestInterceptor,  // Enhanced interceptor with CSRF + Org support!
            oauth2RedirectUrl: window.location.origin + '{oauth2_redirect_url}',
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset
            ],
        }});
        
        console.log('✅ Swagger UI initialized with CSRF protection and Organization ID support');
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

# --- FastAPI App Setup --- #
# Pass the lifespan context manager to the FastAPI app
# IMPORTANT: Set docs_url=None to disable the built-in Swagger UI
app = FastAPI(
    title="KiwiQ Backend - Refactored Auth",
    lifespan=lifespan,
    docs_url=None,  # Disable built-in docs, we'll create our own
    redoc_url="/kiwiq-secret-redoc",
    openapi_url="/openapi.json",
    openapi_tags=tags_metadata,
)

# app = FastAPI(
#     title="KiwiQ Backend - Refactored Auth",
#     lifespan=lifespan,
#     docs_url="/docs",
#     redoc_url="/redoc",
#     openapi_url="/openapi.json",
#     openapi_tags=tags_metadata,
#     swagger_ui_parameters={
#         "withCredentials": True,
#     }
# )

# --- Custom Swagger UI Route --- #
@app.get("/kiwiq-secret-docs", include_in_schema=False)
async def custom_swagger_ui_html(req: Request):
    """
    Custom Swagger UI route with proper CSRF support.
    
    This replaces the built-in FastAPI Swagger UI to ensure the 
    requestInterceptor works correctly as a JavaScript function.
    """
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=app.title,
        oauth2_redirect_url="/kiwiq-secret-docs/oauth2-redirect",
    )

@app.get("/kiwiq-secret-docs/oauth2-redirect", include_in_schema=False)
async def swagger_ui_oauth2_redirect():
    """
    OAuth2 redirect handler for Swagger UI authentication flows.
    
    PURPOSE:
    --------
    This endpoint serves as the redirect URI for OAuth2 authentication flows
    initiated from Swagger UI. When users click "Authorize" in Swagger UI to
    test protected endpoints, this handler processes the OAuth2 provider's
    response and completes the authentication.
    
    OAUTH2 FLOW PROCESS:
    -------------------
    1. User clicks "Authorize" in Swagger UI for a protected endpoint
    2. Swagger UI redirects user to OAuth2 provider (e.g., Google, GitHub, etc.)
    3. User authenticates with OAuth2 provider
    4. OAuth2 provider redirects back to THIS endpoint with:
       - Authorization code (for authorization_code flow)
       - Access token (for implicit flow)  
       - Error information (if authentication failed)
    5. This endpoint processes the response and passes results back to Swagger UI
    6. Swagger UI uses the tokens to make authenticated API requests
    
    SUPPORTED OAUTH2 FLOWS:
    ----------------------
    - Authorization Code Flow (most secure, recommended)
    - Implicit Flow (legacy, less secure)
    - Client Credentials Flow (for service-to-service)
    
    QUERY PARAMETERS HANDLED:
    ------------------------
    - code: Authorization code from OAuth2 provider
    - state: CSRF protection parameter (validated against sent state)
    - error: Error code if authentication failed
    - error_description: Human-readable error description
    - error_uri: URI with additional error information
    - token_type: Type of token received (Bearer, etc.)
    - access_token: Access token (for implicit flow)
    - expires_in: Token expiration time
    
    SECURITY FEATURES:
    -----------------
    - State parameter validation to prevent CSRF attacks
    - Proper error handling and user feedback
    - Automatic window closure after processing
    - Integration with Swagger UI's security model
    
    TECHNICAL DETAILS:
    -----------------
    - Returns HTML page with JavaScript that processes OAuth2 response
    - Communicates with parent Swagger UI window via window.opener
    - Handles both URL fragment (#) and query string (?) parameters
    - Automatically closes popup window after processing
    - Supports multiple OAuth2 flow types dynamically
    
    INTEGRATION:
    -----------
    This endpoint must be configured in:
    1. OAuth2 provider settings as allowed redirect URI
    2. Swagger UI configuration (oauth2RedirectUrl parameter)
    3. OpenAPI spec security definitions
    
    DEBUGGING:
    ---------
    Common issues:
    - Redirect URI mismatch in OAuth2 provider settings
    - Missing CORS headers preventing cross-origin communication
    - State parameter mismatch indicating potential CSRF attack
    - Invalid authorization code or expired tokens
    
    Returns:
    -------
    HTMLResponse: Interactive HTML page with JavaScript to handle OAuth2 flow
    """
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Swagger UI OAuth2 Redirect Handler</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: #fafafa;
                padding: 20px;
                text-align: center;
            }
            .processing {
                background: white;
                border-radius: 8px;
                padding: 30px;
                margin: 50px auto;
                max-width: 400px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
        </style>
    </head>
    <body>
        <div class="processing">
            <h2>🔐 Processing OAuth2 Authentication...</h2>
            <p>Please wait while we complete your authentication.</p>
            <p><small>This window will close automatically.</small></p>
        </div>
        
        <script>
        'use strict';
        
        console.log('🔐 OAuth2 Redirect Handler - Processing authentication response...');
        
        function run() {
            // Get reference to the parent Swagger UI window
            var oauth2 = window.opener.swaggerUIRedirectOauth2;
            
            if (!oauth2) {
                console.error('❌ No OAuth2 context found in parent window');
                alert('OAuth2 authentication failed: No parent context found');
                window.close();
                return;
            }
            
            var sentState = oauth2.state;
            var redirectUrl = oauth2.redirectUrl;
            var isValid, qp, arr;

            console.log('📋 Sent state:', sentState);
            console.log('🔗 Redirect URL:', redirectUrl);

            // Parse OAuth2 response from URL (supports both hash and query string)
            if (/code|token|error/.test(window.location.hash)) {
                qp = window.location.hash.substring(1);
                console.log('🔍 Found OAuth2 params in URL fragment');
            } else {
                qp = location.search.substring(1);
                console.log('🔍 Found OAuth2 params in query string');
            }

            console.log('📝 Raw OAuth2 response:', qp);

            // Convert query parameters to JSON object
            arr = qp.split("&");
            arr.forEach(function (v,i,_arr) { 
                _arr[i] = '"' + v.replace('=', '":"') + '"';
            });
            
            qp = qp ? JSON.parse('{' + arr.join(',') + '}',
                function (key, value) {
                    return key === "" ? value : decodeURIComponent(value);
                }
            ) : {};

            console.log('📊 Parsed OAuth2 response:', qp);

            // Validate state parameter for CSRF protection
            isValid = qp.state === sentState;
            console.log('🔒 State validation:', isValid ? '✅ Valid' : '❌ Invalid');

            // Handle Authorization Code Flow
            if ((
              oauth2.auth.schema.get("flow") === "accessCode" ||
              oauth2.auth.schema.get("flow") === "authorizationCode" ||
              oauth2.auth.schema.get("flow") === "authorization_code"
            ) && !oauth2.auth.code) {
                
                console.log('🔄 Processing Authorization Code Flow...');
                
                if (!isValid) {
                    console.warn('⚠️ State parameter mismatch - potential CSRF attack');
                    oauth2.errCb({
                        authId: oauth2.auth.name,
                        source: "auth",
                        level: "warning",
                        message: "Authorization may be unsafe, passed state was changed in server. Passed state wasn't returned from auth server"
                    });
                }

                if (qp.code) {
                    console.log('✅ Authorization code received successfully');
                    delete oauth2.state;
                    oauth2.auth.code = qp.code;
                    oauth2.callback({auth: oauth2.auth, redirectUrl: redirectUrl});
                } else {
                    console.error('❌ No authorization code received');
                    let oauthErrorMsg;
                    if (qp.error) {
                        oauthErrorMsg = "[" + qp.error + "]: " +
                            (qp.error_description ? qp.error_description + ". " : "no accessCode received from the server. ") +
                            (qp.error_uri ? "More info: " + qp.error_uri : "");
                        console.error('❌ OAuth2 Error:', oauthErrorMsg);
                    }

                    oauth2.errCb({
                        authId: oauth2.auth.name,
                        source: "auth",
                        level: "error",
                        message: oauthErrorMsg || "[Authorization failed]: no accessCode received from the server"
                    });
                }
            } else {
                // Handle Implicit Flow or other token-based flows
                console.log('🔄 Processing token-based OAuth2 flow...');
                oauth2.callback({
                    auth: oauth2.auth, 
                    token: qp, 
                    isValid: isValid, 
                    redirectUrl: redirectUrl
                });
            }
            
            console.log('✅ OAuth2 processing complete - closing window');
            window.close();
        }

        // Execute when DOM is ready
        if (document.readyState !== 'loading') {
            run();
        } else {
            document.addEventListener('DOMContentLoaded', function () {
                run();
            });
        }
        </script>
    </body>
    </html>
    """)

if settings.APP_ENV not in ("PROD", "STAGE"):
    # Only in dev/stage—skip in real PROD where NGINX handles it
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",   # your frontend URL(s)
            "http://localhost:8000",   # if you also hit the openapi from another port
        ],
        allow_credentials=True,       # must be True to allow cookies
        allow_methods=["*"],          # GET, POST, PUT, etc.
        allow_headers=["*"],          # Authorization, Content-Type, etc.
    )  # :contentReference[oaicite:2]{index=2}

# origins = [
#     "http://localhost:3000",  # Your frontend URL
#     "https://beta.kiwiq.ai",
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
#     # expose_headers=["Access-Control-Allow-Origin", "Access-Control-Allow-Headers", "Access-Control-Allow-Methods", ],
# )

# Include the authentication routes using the exposed router
app.include_router(linkedin_integration_routers.linkedin_oauth_router, prefix=settings.API_V1_PREFIX)
app.include_router(linkedin_integration_routers.linkedin_integration_router, prefix=settings.API_V1_PREFIX)
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
# Include the billing routes using the exposed router
app.include_router(billing_routers.billing_router, prefix=f"{settings.API_V1_PREFIX}")
app.include_router(billing_routers.billing_admin_router, prefix=f"{settings.API_V1_PREFIX}")
app.include_router(billing_routers.billing_webhook_router, prefix=f"{settings.API_V1_PREFIX}")
app.include_router(billing_routers.billing_dashboard_router, prefix=f"{settings.API_V1_PREFIX}")

# Include the workflow routes using the exposed router
app.include_router(workflow_routes.workflow_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_routes.run_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_routes.template_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_routes.notification_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_routes.hitl_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_routes.workflow_config_override_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_routes.chat_thread_router, prefix=settings.API_V1_PREFIX)
app.include_router(customer_data_routes.customer_data_router, prefix=settings.API_V1_PREFIX)
app.include_router(scraping_routes.scraping_router, prefix=settings.API_V1_PREFIX)
app.include_router(app_state_routes.app_state_router, prefix=settings.API_V1_PREFIX)
app.include_router(app_artifacts_routes.artifact_router, prefix=settings.API_V1_PREFIX)
app.include_router(websocket_routes.websocket_router, prefix=settings.API_V1_PREFIX)

# ... rest of your app setup ...

# @app.get("/")
# async def root():
#     kiwi_logger.debug("Root endpoint requested.") # Example debug log
#     return {"message": "Welcome to KiwiQ API"} 

