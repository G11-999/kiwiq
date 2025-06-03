"""
KiwiQ Billing Module

This module provides comprehensive billing functionality for the KiwiQ system,
including subscription management, credit tracking, usage analytics, and Stripe integration.

Key Components:
- Models: Database models for billing entities
- Schemas: Pydantic schemas for API validation
- CRUD: Data access objects for database operations
- Services: Business logic layer for billing operations
- Routers: FastAPI routers for billing endpoints
- Dependencies: Dependency injection for services and permissions
- Exceptions: Custom exceptions for billing operations

Integration Points:
- Auth System: Uses existing organization and user models
- Workflow Engine: Provides credit consumption for workflow execution
- Stripe API: Handles payments and subscription management
- Redis: Caches credit balances for performance
- PostgreSQL: Stores all billing data with proper relationships

Usage:
    from kiwi_app.billing import models, schemas, services
    from kiwi_app.billing.routers import router as billing_router
"""

# Import key components for easy access
from . import models
from . import schemas
from . import crud
from . import services
from . import dependencies
from . import exceptions
from . import routers

# Version information
__version__ = "1.0.0"
__author__ = "KiwiQ Team"

# Export commonly used components
__all__ = [
    "models",
    "schemas", 
    "crud",
    "services",
    "dependencies",
    "exceptions",
    "routers"
] 