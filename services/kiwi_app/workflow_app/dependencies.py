"""Dependencies for the Workflow Service."""

import uuid
from typing import Optional, List, AsyncGenerator

from fastapi import Depends, HTTPException, status, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.session import get_async_session, get_async_db_as_manager
from kiwi_app.auth.models import User # Assuming auth models are accessible
from kiwi_app.auth.dependencies import ( # Import relevant auth dependencies
    get_current_active_verified_user,
    get_active_org_id,
    PermissionChecker as AuthPermissionChecker,
    SpecificOrgPermissionChecker as AuthSpecificOrgPermissionChecker
)
from mongo_client import AsyncMongoDBClient # Import the client class

from kiwi_app.workflow_app import crud, models, schemas, services
from kiwi_app.workflow_app.constants import WorkflowPermissions
from kiwi_app.workflow_app.exceptions import (
    WorkflowNotFoundException,
    WorkflowRunNotFoundException,
    TemplateNotFoundException
)
from workflow_service.services.external_context_manager import get_workflow_mongo_client

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

# --- Service Dependency Factory --- #

def get_workflow_service_dependency(
    node_template_dao: crud.NodeTemplateDAO = Depends(get_node_template_dao),
    workflow_dao: crud.WorkflowDAO = Depends(get_workflow_dao),
    workflow_run_dao: crud.WorkflowRunDAO = Depends(get_workflow_run_dao),
    prompt_template_dao: crud.PromptTemplateDAO = Depends(get_prompt_template_dao),
    schema_template_dao: crud.SchemaTemplateDAO = Depends(get_schema_template_dao),
    user_notification_dao: crud.UserNotificationDAO = Depends(get_user_notification_dao),
    hitl_job_dao: crud.HITLJobDAO = Depends(get_hitl_job_dao),
    mongo_client: AsyncMongoDBClient = Depends(get_workflow_mongo_client)
) -> services.WorkflowService:
    """Dependency function to instantiate WorkflowService with its DAO dependencies."""
    return services.WorkflowService(
        node_template_dao=node_template_dao,
        workflow_dao=workflow_dao,
        workflow_run_dao=workflow_run_dao,
        prompt_template_dao=prompt_template_dao,
        schema_template_dao=schema_template_dao,
        user_notification_dao=user_notification_dao,
        hitl_job_dao=hitl_job_dao,
        mongo_client=mongo_client
        # Pass NoSQL client here
    )

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

# --- Resource Fetching Dependencies with Permission Checks --- #

async def get_workflow_for_org( # Renamed to be more specific
    workflow_id: uuid.UUID = Path(..., description="The ID of the workflow"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
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

    async with db_manager as db:
        workflow = await workflow_dao.get_by_id_and_org(db, workflow_id=workflow_id, org_id=active_org_id)
        if not workflow:
            raise WorkflowNotFoundException()
        return workflow

async def get_workflow_run_for_org(
    run_id: uuid.UUID = Path(..., description="The ID of the workflow run"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    run_dao: crud.WorkflowRunDAO = Depends(get_workflow_run_dao),
    # current_user: User = Depends(get_current_active_verified_user) # User fetched by perm checker
) -> models.WorkflowRun:
    """
    Dependency to fetch a workflow run by ID, ensuring it belongs to the active organization.
    Permissions should be checked by a separate dependency *before* this one.
    """
    if active_org_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Active-Org header is required.")

    async with db_manager as db:
        run = await run_dao.get_run_by_id_and_org(db, run_id=run_id, org_id=active_org_id)
        if not run:
            raise WorkflowRunNotFoundException()
        return run

async def get_notification_for_user(
    notification_id: uuid.UUID = Path(..., description="The ID of the notification"),
    current_user: User = Depends(get_current_active_verified_user),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    notification_dao: crud.UserNotificationDAO = Depends(get_user_notification_dao),
) -> models.UserNotification:
    """
    Dependency to fetch a notification by ID, ensuring it belongs to the current user.
    """
    async with db_manager as db:
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
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    hitl_job_dao: crud.HITLJobDAO = Depends(get_hitl_job_dao),
) -> models.HITLJob:
    """
    Dependency to fetch an HITL job by ID, ensuring it belongs to the active organization.
    Permissions should be checked by a separate dependency *before* this one.
    """
    if active_org_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Active-Org header is required.")

    async with db_manager as db:
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

# Add similar dependencies for getting PromptTemplate and SchemaTemplate by ID + Org if needed 