"""Dependencies for the Workflow Service.

# TODO: CRITICAL: handle lifecycle of connections dependencies!
"""

import uuid
from typing import Optional, List, AsyncGenerator

from fastapi import Depends, HTTPException, status, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.session import get_async_session, get_async_db_dependency
from functools import partial
from kiwi_app.auth.models import User # Assuming auth models are accessible
from kiwi_app.auth.dependencies import ( # Import relevant auth dependencies
    get_current_active_verified_user,
    get_active_org_id,
    PermissionChecker as AuthPermissionChecker,
    SpecificOrgPermissionChecker as AuthSpecificOrgPermissionChecker
)
from mongo_client import AsyncMongoDBClient, AsyncMongoVersionedClient # Import the client classes
from kiwi_app.settings import settings

from kiwi_app.workflow_app import crud, models, schemas, services
from kiwi_app.workflow_app.constants import WorkflowPermissions
from kiwi_app.workflow_app.exceptions import (
    WorkflowNotFoundException,
    WorkflowRunNotFoundException,
    TemplateNotFoundException
)
from kiwi_app.workflow_app.service_customer_data import CustomerDataService
from workflow_service.registry import registry
from workflow_service.services.db_node_register import register_node_templates
from workflow_service.services.external_context_manager import get_workflow_mongo_client, get_customer_mongo_client, get_customer_versioned_mongo_client
from kiwi_app.billing import services as billing_services, dependencies as billing_dependencies

# --- DAO Dependency Factories --- #

def get_node_template_dao() -> crud.NodeTemplateDAO:
    return crud.NodeTemplateDAO()

def get_workflow_dao() -> crud.WorkflowDAO:
    return crud.WorkflowDAO()

def get_workflow_run_dao() -> crud.WorkflowRunDAO:
    return crud.WorkflowRunDAO()

def get_prompt_template_dao() -> crud.PromptTemplateDAO:
    return crud.PromptTemplateDAO()

def get_schema_template_dao() -> crud.SchemaTemplateDAO:
    return crud.SchemaTemplateDAO()

def get_user_notification_dao() -> crud.UserNotificationDAO:
    return crud.UserNotificationDAO()

def get_hitl_job_dao() -> crud.HITLJobDAO:
    return crud.HITLJobDAO()

def get_workflow_config_override_dao() -> crud.WorkflowConfigOverrideDAO:
    return crud.WorkflowConfigOverrideDAO()

db_registry = None

async def get_node_template_registry() -> registry.DBRegistry:
    global db_registry
    if db_registry is None:
        node_template_dao =  crud.NodeTemplateDAO()
        workflow_dao = crud.WorkflowDAO()
        prompt_template_dao = crud.PromptTemplateDAO()
        schema_template_dao = crud.SchemaTemplateDAO()

        db_registry = registry.DBRegistry(
            node_template_dao = node_template_dao,
            schema_template_dao = schema_template_dao,
            prompt_template_dao = prompt_template_dao,
            workflow_dao = workflow_dao,
        )

        await register_node_templates(db_registry)
    return db_registry

# --- Service Dependency Factory --- #

# TODO: FIXME: for fastapi dependencies, lifecycle is managed by yield, so do graceful shutdown!
async def get_workflow_service_dependency(
    node_template_dao: crud.NodeTemplateDAO = Depends(get_node_template_dao),
    workflow_dao: crud.WorkflowDAO = Depends(get_workflow_dao),
    workflow_run_dao: crud.WorkflowRunDAO = Depends(get_workflow_run_dao),
    prompt_template_dao: crud.PromptTemplateDAO = Depends(get_prompt_template_dao),
    schema_template_dao: crud.SchemaTemplateDAO = Depends(get_schema_template_dao),
    user_notification_dao: crud.UserNotificationDAO = Depends(get_user_notification_dao),
    hitl_job_dao: crud.HITLJobDAO = Depends(get_hitl_job_dao),
    workflow_config_override_dao: crud.WorkflowConfigOverrideDAO = Depends(get_workflow_config_override_dao),
    mongo_client: AsyncMongoDBClient = Depends(get_workflow_mongo_client),
    db_registry: registry.DBRegistry = Depends(get_node_template_registry),
    billing_service: billing_services.BillingService = Depends(billing_dependencies.get_billing_service_no_dependencies),
) -> AsyncGenerator[services.WorkflowService, None]:
    """Dependency function to instantiate WorkflowService with its DAO dependencies."""
    workflow_service = services.WorkflowService(
        node_template_dao=node_template_dao,
        workflow_dao=workflow_dao,
        workflow_run_dao=workflow_run_dao,
        prompt_template_dao=prompt_template_dao,
        schema_template_dao=schema_template_dao,
        user_notification_dao=user_notification_dao,
        hitl_job_dao=hitl_job_dao,
        workflow_config_override_dao=workflow_config_override_dao,
        mongo_client=mongo_client,
        db_registry=db_registry,
        billing_service=billing_service,
        # Pass NoSQL client here
    )
    yield workflow_service
    await workflow_service.mongo_client.close()

# --- Customer Data Service Dependency --- #

# async def partial_get_customer_mongo_client_with_extra_segments():
#     return await get_customer_mongo_client_with_extra_segments(extra_segments=AsyncMongoVersionedClient.VERSION_SEGMENT_NAMES)

# async def get_customer_versioned_mongo_client_dependency(
#     customer_mongo_client: AsyncMongoDBClient = Depends(partial_get_customer_mongo_client_with_extra_segments),
# ) -> AsyncMongoVersionedClient:
#     """Create and return a versioned MongoDB client for customer data."""
#     # Create versioned client based on the base MongoDB client
#     # Use base segment names without version/sequence segments that will be added internally
#     versioned_client = AsyncMongoVersionedClient(
#         client=customer_mongo_client,
#         segment_names=settings.MONGO_CUSTOMER_SEGMENTS, # Base segments defined in settings
#     )
#     return versioned_client

# TODO: FIXME: REFACTOR TO MOVE this to external dependencies and refactor customer data service to use an underlying DAO so as not to raise HTTP exceptions and potentially use it in prefect worker too!
async def get_customer_data_service_dependency(
    customer_mongo_client: AsyncMongoDBClient = Depends(get_customer_mongo_client),
    versioned_mongo_client: AsyncMongoVersionedClient = Depends(get_customer_versioned_mongo_client),
    schema_template_dao: crud.SchemaTemplateDAO = Depends(get_schema_template_dao),
    # workflow_service: services.WorkflowService = Depends(get_workflow_service_dependency),
) -> AsyncGenerator[CustomerDataService, None]:
    """Dependency function to instantiate CustomerDataService."""
    customer_data_service = CustomerDataService(
        mongo_client=customer_mongo_client,
        versioned_mongo_client=versioned_mongo_client,
        schema_template_dao=schema_template_dao,
    )
    yield customer_data_service
    await customer_data_service.mongo_client.close()
    await customer_data_service.versioned_mongo_client.client.close()
    await customer_data_service.versioned_mongo_client._redis_client.close()


# --- Permission Checkers (using Auth checkers) --- #
# We can reuse the permission checker logic from the auth service.
# Create instances with specific workflow permissions.

# Example: Check permission against the Active Org (X-Active-Org header)
RequireWorkflowReadActiveOrg = AuthPermissionChecker([WorkflowPermissions.WORKFLOW_READ])
RequireWorkflowCreateActiveOrg = AuthPermissionChecker([WorkflowPermissions.WORKFLOW_CREATE])
RequireWorkflowExecuteActiveOrg = AuthPermissionChecker([WorkflowPermissions.WORKFLOW_EXECUTE])
RequireWorkflowUpdateActiveOrg = AuthPermissionChecker([WorkflowPermissions.WORKFLOW_UPDATE])
RequireWorkflowDeleteActiveOrg = AuthPermissionChecker([WorkflowPermissions.WORKFLOW_DELETE])

RequireRunReadActiveOrg = AuthPermissionChecker([WorkflowPermissions.RUN_READ])
RequireRunManageActiveOrg = AuthPermissionChecker([WorkflowPermissions.RUN_MANAGE])

RequireTemplateReadActiveOrg = AuthPermissionChecker([WorkflowPermissions.TEMPLATE_READ])
RequireTemplateCreateActiveOrg = AuthPermissionChecker([WorkflowPermissions.TEMPLATE_CREATE])
RequireTemplateUpdateActiveOrg = AuthPermissionChecker([WorkflowPermissions.TEMPLATE_UPDATE])
RequireTemplateDeleteActiveOrg = AuthPermissionChecker([WorkflowPermissions.TEMPLATE_DELETE])
# Example: Check permission against a Specific Org (from path parameter)
# Note: The path parameter name in the route must match the one expected by the checker (default 'org_id')
# or be specified in the checker's __init__ if it needs customization.

# You might need a slightly different checker if the workflow/run ID is in the path
# and you need to fetch the object first to find its owning org ID.

# Add checkers for Organization Data
RequireOrgDataReadActiveOrg = AuthPermissionChecker([WorkflowPermissions.ORG_DATA_READ])
RequireOrgDataWriteActiveOrg = AuthPermissionChecker([WorkflowPermissions.ORG_DATA_WRITE])

# --- Resource Fetching Dependencies with Permission Checks --- #

async def get_workflow_for_org( # Renamed to be more specific
    workflow_id: uuid.UUID = Path(..., description="The ID of the workflow"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    db: AsyncSession = Depends(get_async_db_dependency),
    workflow_dao: crud.WorkflowDAO = Depends(get_workflow_dao),
    # current_user: User = Depends(get_current_active_verified_user) # User fetched by perm checker
) -> models.Workflow:
    """
    Dependency to fetch a workflow by ID, ensuring it belongs to the active organization.
    Permissions should be checked by a separate dependency *before* this one.
    """
    if active_org_id is None:
        # This should ideally be caught by permission checker if required
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Active-Org header is required.")

    workflow = await workflow_dao.get_by_id_and_org(db, workflow_id=workflow_id, org_id=active_org_id)
    if not workflow:
        raise WorkflowNotFoundException()
    return workflow

async def get_workflow_run_for_org(
    run_id: uuid.UUID = Path(..., description="The ID of the workflow run"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    db: AsyncSession = Depends(get_async_db_dependency),
    run_dao: crud.WorkflowRunDAO = Depends(get_workflow_run_dao),
    # current_user: User = Depends(get_current_active_verified_user) # User fetched by perm checker
) -> models.WorkflowRun:
    """
    Dependency to fetch a workflow run by ID, ensuring it belongs to the active organization.
    Permissions should be checked by a separate dependency *before* this one.
    """
    if active_org_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Active-Org header is required.")

    run = await run_dao.get_run_by_id_and_org(db, run_id=run_id, org_id=active_org_id)
    if not run:
        raise WorkflowRunNotFoundException()
    return run

async def get_notification_for_user(
    notification_id: uuid.UUID = Path(..., description="The ID of the notification"),
    current_user: User = Depends(get_current_active_verified_user),
    db: AsyncSession = Depends(get_async_db_dependency),
    notification_dao: crud.UserNotificationDAO = Depends(get_user_notification_dao),
) -> models.UserNotification:
    """
    Dependency to fetch a notification by ID, ensuring it belongs to the current user.
    """
    result = await db.execute(
        select(models.UserNotification).where(
            models.UserNotification.id == notification_id,
            models.UserNotification.user_id == current_user.id
        )
    )
    notification = result.scalars().first()
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Notification not found or does not belong to the current user"
        )
    return notification

async def get_hitl_job_for_org(
    job_id: uuid.UUID = Path(..., description="The ID of the HITL job"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    db: AsyncSession = Depends(get_async_db_dependency),
    hitl_job_dao: crud.HITLJobDAO = Depends(get_hitl_job_dao),
) -> models.HITLJob:
    """
    Dependency to fetch an HITL job by ID, ensuring it belongs to the active organization.
    Permissions should be checked by a separate dependency *before* this one.
    """
    if active_org_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Active-Org header is required.")

    result = await db.execute(
        select(models.HITLJob).where(
            models.HITLJob.id == job_id,
            models.HITLJob.org_id == active_org_id
        )
    )
    job = result.scalars().first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="HITL job not found or does not belong to the active organization"
        )
    return job
