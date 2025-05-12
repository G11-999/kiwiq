# PYTHONPATH=$(pwd):$(pwd)/services  poetry run uvicorn services.kiwi_app.main:app --host 0.0.0.0 --port 8000
# PYTHONPATH=$(pwd):$(pwd)/services  poetry run python ./services/kiwi_app/main.py
# PYTHONPATH=$(pwd):$(pwd)/services  poetry run uvicorn main:app --app-dir services/kiwi_app --reload
import asyncio
import logging # Import logging
from contextlib import asynccontextmanager # Import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from kiwi_app.utils import get_kiwi_logger
from kiwi_app import auth
from kiwi_app.settings import settings # Import settings

from kiwi_app.workflow_app import routes as workflow_routes
from kiwi_app.workflow_app import customer_data_routes as customer_data_routes
from kiwi_app.workflow_app import event_consumer
from kiwi_app.workflow_app import dependencies as wf_deps
from scraper_service import scraping_routes
from kiwi_app.workflow_app import app_state as app_state_routes
from kiwi_app.workflow_app import app_artifacts as app_artifacts_routes
from kiwi_app.workflow_app import websockets as websocket_routes

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

# --- FastAPI App Setup --- #
# Pass the lifespan context manager to the FastAPI app
# TODO: replace with in production links for production!
app = FastAPI(
    title="KiwiQ Backend - Refactored Auth",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=tags_metadata,
    )

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
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)

# Include the workflow routes using the exposed router
app.include_router(workflow_routes.workflow_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_routes.run_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_routes.template_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_routes.notification_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflow_routes.hitl_router, prefix=settings.API_V1_PREFIX)
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

