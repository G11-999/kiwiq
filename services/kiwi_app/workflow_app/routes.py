import asyncio
import uuid
from typing import List, Optional, Dict, Any, Annotated, Union, AsyncGenerator

from fastapi import (
    APIRouter, Depends, HTTPException, status, Query, WebSocket,
    WebSocketDisconnect, Body, Path, Response # Added Path, Response
)
from sqlalchemy.ext.asyncio import AsyncSession
import jwt # For encoding/decoding tokens (requires python-jose)
from datetime import datetime, timedelta

# --- Core Dependencies ---
from db.session import get_async_session, get_async_db_as_manager
from global_utils import datetime_now_utc
from kiwi_app.auth import crud as auth_crud, dependencies as auth_deps
from kiwi_app.settings import settings

# --- Auth Dependencies ---
from kiwi_app.auth.models import User
from kiwi_app.auth.dependencies import (
    get_current_active_verified_user,
    get_active_org_id
)
from kiwi_app.workflow_app import crud as wf_crud
# Import function to fetch user from auth crud (used in websocket auth)
# from kiwi_app.auth.crud import user as user_crud

# --- Workflow App Dependencies ---
# Import local schemas, services, models, constants, exceptions
from kiwi_app.workflow_app import schemas, services, models, dependencies as wf_deps, exceptions, constants

# --- Event Schemas ---
# Import event schemas for stream response type
from workflow_service.services import events as event_schemas

from kiwi_app.workflow_app.websockets import websocket_router

# --- Permission Checker Dependencies (Imported from wf_deps correctly now) ---
# Example: wf_deps.RequireWorkflowRead, wf_deps.RequireWorkflowCreate, etc.

# --- Setup Routers ---
# Group routes logically using tags
workflow_router = APIRouter(prefix="/workflows", tags=["Workflows"])
run_router = APIRouter(prefix="/runs", tags=["Workflow Runs"])
template_router = APIRouter(prefix="/templates", tags=["Templates"])
notification_router = APIRouter(prefix="/notifications", tags=["User Notifications"])
hitl_router = APIRouter(prefix="/hitl", tags=["HITL Jobs"])
notification_router.include_router(websocket_router, prefix="/ws", tags=["WebSocket Stream & Notifications"])

# === Template Endpoints ===

# -- Node Templates --
@template_router.get(
    "/nodes/",
    response_model=List[schemas.NodeTemplateRead],
    summary="List Node Templates",
    # dependencies=[Depends(wf_deps.RequireTemplateRead)] # Requires TEMPLATE_READ on active org
)
async def list_node_templates(
    query_params: Annotated[schemas.NodeTemplateListQuery, Query()],
    user: User = Depends(get_current_active_verified_user),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Retrieves a list of available Node Templates.

    - By default, returns **STAGING** and **PRODUCTION** templates.
    - Use the `launch_status` query parameter (e.g., `?launch_status=production&launch_status=staging`)
      to filter by specific statuses.
    - Supports pagination via `skip` and `limit`.
    - Requires `template:read` permission on the active organization.
    """
    if constants.LaunchStatus.EXPERIMENTAL in query_params.launch_status and not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Experimental templates are not accessible to regular users.")

    async with db_manager as db:
        return await workflow_service.list_node_templates(
            db=db,
            launch_statuses=query_params.launch_status,
            skip=query_params.skip,
            limit=query_params.limit
        )

@template_router.get(
    "/nodes/{name}/{version}",
    response_model=schemas.NodeTemplateRead,
    summary="Get Node Template by Name and Version",
    # dependencies=[Depends(wf_deps.RequireTemplateRead)]
)
async def get_node_template(
    user: User = Depends(get_current_active_verified_user),
    name: str = Path(..., description="Name of the node template"),
    version: str = Path(..., description="Version of the node template"),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Retrieves a specific Node Template by its unique name and version.

    - Requires `template:read` permission.
    """
    async with db_manager as db:
        template = await workflow_service.get_node_template(db=db, name=name, version=version)
        if not template:
            raise exceptions.TemplateNotFoundException(f"Node template '{name}' version '{version}' not found.")
        if template.launch_status == constants.LaunchStatus.EXPERIMENTAL and not user.is_superuser:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Experimental templates are not accessible to regular users.")
        return template


# -- Prompt Templates --
@template_router.post(
    "/prompts/",
    response_model=schemas.PromptTemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Prompt Template",
    # dependencies=[Depends(wf_deps.RequireTemplateCreateActiveOrg)] # Requires TEMPLATE_CREATE on active org
)
async def create_prompt_template(
    template_in: schemas.PromptTemplateCreate,
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(wf_deps.RequireTemplateCreateActiveOrg),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Creates a new organization-specific prompt template.

    - Requires `template:create_org` permission on the active organization.
    """
    # Service layer handles potential name/version conflicts within the org
    async with db_manager as db:
        return await workflow_service.create_prompt_template(
            db=db, template_in=template_in, owner_org_id=active_org_id, user=current_user
        )

@template_router.get(
    "/prompts/",
    response_model=List[schemas.PromptTemplateRead],
    summary="List Prompt Templates. System templates are accessible to all users and can configure if requested or not. Pagination applies separately to org and system templates.",
    dependencies=[Depends(wf_deps.RequireTemplateReadActiveOrg)] # Requires TEMPLATE_READ on active org
)
async def list_prompt_templates(
    query_params: Annotated[schemas.PromptTemplateListQuery, Query()],
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    # current_user: User = Depends(wf_deps.RequireTemplateReadActiveOrg), # Needed only if superuser bypasses active_org_id
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Lists accessible prompt templates.

    - Returns templates owned by the active organization.
    - Optionally includes system-wide templates if `include_system=true` (default).
    - Supports pagination via `skip` and `limit`.
    - Superusers can potentially filter by a different `owner_org_id` (requires service/checker support).
    - Requires `template:read` permission on the active organization.
    """
    # Superuser filtering by owner_org_id needs to be handled in the service layer
    # based on the current_user's is_superuser flag if needed.
    async with db_manager as db:
        return await workflow_service.list_prompt_templates(
            db=db,
            owner_org_id=active_org_id, # Pass active org as context
            include_system=query_params.include_system,
            skip=query_params.skip,
            limit=query_params.limit
        )

@template_router.get(
    "/prompts/{template_id}",
    response_model=schemas.PromptTemplateRead,
    summary="Get Prompt Template by ID. System templates are accessible to all users.",
    dependencies=[Depends(wf_deps.RequireTemplateReadActiveOrg)] # Check basic read permission first
)
async def get_prompt_template(
    template_id: uuid.UUID = Path(..., description="The ID of the prompt template"),
    active_org_id: uuid.UUID = Depends(get_active_org_id), # For context if accessing org template
    # current_user: User = Depends(get_current_active_verified_user), # Needed if checking access to system templates differently
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Retrieves a specific prompt template by its ID.

    - Can fetch both organization-specific templates (checking ownership against active org)
      and system-wide templates.
    - Requires `template:read` permission.
    """
    async with db_manager as db:
        try:
            template = await workflow_service.get_prompt_template(
                db=db, template_id=template_id, owner_org_id=active_org_id # Pass org context for check
            )
        except exceptions.TemplateNotFoundException as e:
            raise e # Re-raise the specific 404 exception from the service layer
        return template


@template_router.put(
    "/prompts/{template_id}",
    response_model=schemas.PromptTemplateRead,
    summary="Update Prompt Template",
    # dependencies=[Depends(wf_deps.RequireTemplateUpdateActiveOrg)] # Requires TEMPLATE_UPDATE on active org
)
async def update_prompt_template(
    template_update: schemas.PromptTemplateUpdate,
    template_id: uuid.UUID = Path(..., description="The ID of the prompt template"),
    active_org_id: uuid.UUID = Depends(get_active_org_id), # For context if accessing org template
    # Fetch the template ensuring it belongs to the active org using the specific dependency
    # template: models.PromptTemplate = Depends(wf_deps.get_prompt_template_for_active_org),
    current_user: User = Depends(wf_deps.RequireTemplateUpdateActiveOrg),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Updates an organization-specific prompt template.

    - Only templates owned by the active organization can be updated.
    - Requires `template:update_org` permission on the active organization.
    """
    async with db_manager as db:
        try:
            template = await workflow_service.get_prompt_template(
                db=db, template_id=template_id, owner_org_id=active_org_id
            )
        except exceptions.TemplateNotFoundException as e:
            raise e
        # Dependency ensures template belongs to active org before calling service
        return await workflow_service.update_prompt_template(
            db=db, template=template, template_update=template_update, user=current_user
        )

@template_router.delete(
    "/prompts/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Prompt Template",
    # dependencies=[Depends(wf_deps.RequireTemplateDeleteActiveOrg)] # Requires TEMPLATE_DELETE on active org
)
async def delete_prompt_template(
    # template: models.PromptTemplate = Depends(wf_deps.get_prompt_template_for_active_org),
    template_id: uuid.UUID = Path(..., description="The ID of the prompt template"),
    active_org_id: uuid.UUID = Depends(get_active_org_id), # For context if accessing org template
    current_user: User = Depends(wf_deps.RequireTemplateDeleteActiveOrg), # Pass user for audit/logging
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Deletes an organization-specific prompt template.

    - Only templates owned by the active organization can be deleted.
    - Requires `template:delete_org` permission on the active organization.
    """
    async with db_manager as db:
        try:
            template = await workflow_service.get_prompt_template(
                db=db, template_id=template_id, owner_org_id=active_org_id
            )
        except exceptions.TemplateNotFoundException as e:
            raise e
        await workflow_service.delete_prompt_template(db=db, template=template, user=current_user)
        return Response(status_code=status.HTTP_204_NO_CONTENT) # Explicitly return 204

# TODO: FIXME: add custom validators to ensure every prompt variable exists in the prompt template
#   and every placeholder variable `{...}` in template exists as variable
#   maybe use a templating system like Jinja etc??

# -- Schema Templates (Mirrors Prompt Templates) --
@template_router.post(
    "/schemas/",
    response_model=schemas.SchemaTemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Schema Template",
    # dependencies=[Depends(wf_deps.RequireTemplateCreate)]
)
async def create_schema_template(
    template_in: schemas.SchemaTemplateCreate,
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(wf_deps.RequireTemplateCreateActiveOrg),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Creates a new organization-specific schema template.

    - Requires `template:create_org` permission on the active organization.
    """
    async with db_manager as db:
        return await workflow_service.create_schema_template(
            db=db, template_in=template_in, owner_org_id=active_org_id, user=current_user
        )

@template_router.get(
    "/schemas/",
    response_model=List[schemas.SchemaTemplateRead],
    summary="List Schema Templates",
    # dependencies=[Depends(wf_deps.RequireTemplateReadActiveOrg)]
)
async def list_schema_templates(
    query_params: Annotated[schemas.SchemaTemplateListQuery, Query()],
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Lists accessible schema templates (organization-specific and optionally system).

     - Requires `template:read` permission on the active organization.
    """
    async with db_manager as db:
        return await workflow_service.list_schema_templates(
            db=db,
            owner_org_id=(query_params.owner_org_id if current_user.is_superuser else None) or active_org_id,
            include_system=query_params.include_system,
            skip=query_params.skip,
            limit=query_params.limit
        )

@template_router.get(
    "/schemas/{template_id}",
    response_model=schemas.SchemaTemplateRead,
    summary="Get Schema Template by ID. System templates are accessible to all users, otherwise only org-specific templates are accessible, org indicated via org header.",
    dependencies=[Depends(wf_deps.RequireTemplateReadActiveOrg)]
)
async def get_schema_template(
    template_id: uuid.UUID = Path(..., description="The ID of the schema template"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    # current_user: User = Depends(get_current_active_verified_user),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Retrieves a specific schema template by its ID.

    - Can fetch both organization-specific and system templates.
    - Requires `template:read` permission.
    """
    async with db_manager as db:
        try:
            template = await workflow_service.get_schema_template(
                db=db, template_id=template_id, owner_org_id=active_org_id
            )
        except exceptions.TemplateNotFoundException as e:
            raise e
        return template

@template_router.put(
    "/schemas/{template_id}",
    response_model=schemas.SchemaTemplateRead,
    summary="Update Schema Template",
    # dependencies=[Depends(wf_deps.RequireTemplateUpdateActiveOrg)]
)
async def update_schema_template(
    template_update: schemas.SchemaTemplateUpdate,
    template_id: uuid.UUID = Path(..., description="The ID of the schema template"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    # template: models.SchemaTemplate = Depends(wf_deps.get_schema_template_for_active_org),
    current_user: User = Depends(wf_deps.RequireTemplateUpdateActiveOrg),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Updates an organization-specific schema template.

     - Requires `template:update_org` permission on the active organization.
    """
    async with db_manager as db:
        try:
            template = await workflow_service.get_schema_template(
                db=db, template_id=template_id, owner_org_id=active_org_id
            )
        except exceptions.TemplateNotFoundException as e:
            raise e
        return await workflow_service.update_schema_template(
            db=db, template=template, template_update=template_update, user=current_user
        )

@template_router.delete(
    "/schemas/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Schema Template",
    # dependencies=[Depends(wf_deps.RequireTemplateDeleteActiveOrg)]
)
async def delete_schema_template(
    # template: models.SchemaTemplate = Depends(wf_deps.get_schema_template_for_active_org),
    template_id: uuid.UUID = Path(..., description="The ID of the schema template"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(wf_deps.RequireTemplateDeleteActiveOrg),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Deletes an organization-specific schema template.

     - Requires `template:delete_org` permission on the active organization.
    """
    async with db_manager as db:
        try:
            template = await workflow_service.get_schema_template(
                db=db, template_id=template_id, owner_org_id=active_org_id
            )
        except exceptions.TemplateNotFoundException as e:
            raise e
        await workflow_service.delete_schema_template(db=db, template=template, user=current_user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


# === Workflow Endpoints ===

@workflow_router.post(
    "/",
    response_model=schemas.WorkflowRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Workflow. active_org_id is optional for superuser to create workflows without org context (potentially for testing purposes or global workflows which can be used across all orgs).",
    # dependencies=[Depends(wf_deps.RequireWorkflowCreateActiveOrg)] # Check permission first
)
async def create_workflow(
    workflow_in: schemas.WorkflowCreate,
    active_org_id: Optional[uuid.UUID] = Depends(get_active_org_id),
    current_user: User = Depends(wf_deps.RequireWorkflowCreateActiveOrg),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Creates a new workflow configuration within the active organization.

    - The `graph_config` defines the structure and nodes of the workflow.
    - Requires `workflow:create` permission on the active organization.
    """
    # Service layer handles potential name conflicts within the org
    async with db_manager as db:
        return await workflow_service.create_workflow(
            db=db, workflow_in=workflow_in, owner_org_id=active_org_id, user=current_user
        )

@workflow_router.get(
    "/",
    response_model=List[schemas.WorkflowRead],
    summary="List Workflows for the active org. Superusers can list workflows for any org by providing the `owner_org_id` query parameter or using the active org context from header (the former overrides the latter).",
    # dependencies=[Depends(wf_deps.RequireWorkflowRead)] # Requires workflow:read on active org
)
async def list_workflows(
    query_params: Annotated[schemas.WorkflowListQuery, Query()],
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(wf_deps.RequireWorkflowReadActiveOrg),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Lists workflows accessible to the current user.

    - By default, lists workflows belonging to the active organization.
    - **Superusers** can list workflows for any organization by providing the `owner_org_id` query parameter.
    - Supports pagination via `skip` and `limit`.
    - Requires `workflow:read` permission on the active organization (or superuser status for cross-org listing).
    """
    list_org_id = active_org_id
    # Allow superuser to list workflows for other orgs
    if current_user.is_superuser and query_params.owner_org_id:
        list_org_id = query_params.owner_org_id
    elif not current_user.is_superuser and query_params.owner_org_id and query_params.owner_org_id != active_org_id:
         # If not superuser, cannot list for other orgs
         raise HTTPException(
             status_code=status.HTTP_403_FORBIDDEN,
             detail="Insufficient permissions to list workflows for other organizations."
         )

    # Pass relevant filters (excluding pagination) to the service layer
    # launch_status filter is removed as it's not on the workflow model according to models.py
    async with db_manager as db:
        return await workflow_service.list_workflows(
            db=db,
            owner_org_id=list_org_id, # Use the determined org_id
            # launch_status=query_params.launch_status,
            include_public=query_params.include_public,
            skip=query_params.skip,
            limit=query_params.limit
        )

@workflow_router.get(
    "/{workflow_id}",
    response_model=schemas.WorkflowRead,
    summary="Get Workflow by ID",
    # dependencies=[Depends(wf_deps.RequireWorkflowReadActiveOrg)] # Basic check on active org context
)
async def get_workflow(
    workflow_id: uuid.UUID = Path(..., description="The ID of the workflow"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    # Use dependency to fetch workflow and ensure it belongs to active org
    # Dependency raises 404 if not found in active org
    current_user: User = Depends(wf_deps.RequireWorkflowReadActiveOrg),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Retrieves the details of a specific workflow configuration.

    - Ensures the workflow belongs to the user's active organization.
    - Requires `workflow:read` permission on the active organization.
    """
    async with db_manager as db:
        return await workflow_service.get_workflow(
            db=db,
            user=current_user,
            workflow_id=workflow_id,
            owner_org_id=active_org_id
        )

@workflow_router.put(
    "/{workflow_id}",
    response_model=schemas.WorkflowRead,
    summary="Update Workflow",
    # dependencies=[Depends(wf_deps.RequireWorkflowUpdateActiveOrg)] # Check update perm on active org
)
async def update_workflow(
    workflow_update: schemas.WorkflowUpdate,
    workflow_id: uuid.UUID = Path(..., description="The ID of the workflow"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    # Fetch workflow, ensuring it belongs to active org for modification
    # workflow: models.Workflow = Depends(wf_deps.get_workflow_for_active_org),
    workflow_dao: wf_crud.WorkflowDAO = Depends(wf_deps.get_workflow_dao),
    current_user: User = Depends(wf_deps.RequireWorkflowUpdateActiveOrg),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Updates an existing workflow configuration.

    - Only workflows belonging to the active organization can be updated.
    - Requires `workflow:update` permission on the active organization.
    """
    async with db_manager as db:
        workflow = await workflow_dao.get_by_id_and_org(db, workflow_id=workflow_id, org_id=active_org_id)
        # Dependency handles fetch and ensures it's in the active org
        return await workflow_service.update_workflow(
            db=db, workflow=workflow, workflow_update=workflow_update, user=current_user
        )
@workflow_router.delete(
    "/{workflow_id}",
    response_model=schemas.WorkflowRead,
    summary="Delete Workflow",
    # dependencies=[Depends(wf_deps.RequireWorkflowDeleteActiveOrg)] # Check delete perm on active org
)
async def delete_workflow(
    workflow_id: uuid.UUID = Path(..., description="The ID of the workflow"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    workflow_dao: wf_crud.WorkflowDAO = Depends(wf_deps.get_workflow_dao),
    current_user: User = Depends(wf_deps.RequireWorkflowDeleteActiveOrg),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Deletes a workflow configuration.

    - Only workflows belonging to the active organization can be deleted.
    - Note: Associated workflow runs are typically *not* deleted by default (check FK constraints).
    - Requires `workflow:delete` permission on the active organization.
    """
    async with db_manager as db:
        workflow = await workflow_dao.get_by_id_and_org(db, workflow_id=workflow_id, org_id=active_org_id)
        # Dependency handles fetch and ensures it's in the active org
        await workflow_service.delete_workflow(db=db, workflow=workflow, user=current_user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


# === Workflow Run Endpoints ===

@run_router.post(
    "/",
    response_model=schemas.WorkflowRunRead,
    status_code=status.HTTP_202_ACCEPTED, # Indicate async processing started
    summary="Submit Workflow Run. If resuming after HITL, provide the `run_id` of the run to resume and the `inputs` to resume with. If not resuming, provide `workflow_id` to run an existing saved workflow or `graph_schema` to define and run an ad-hoc workflow.",
    dependencies=[Depends(wf_deps.RequireWorkflowExecuteActiveOrg)] # Check execute perm on active org
)
async def submit_workflow_run(
    run_submit: schemas.WorkflowRunCreate,
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(wf_deps.RequireWorkflowExecuteActiveOrg),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Submits a new workflow run for execution.

    - Provide `workflow_id` to run an existing saved workflow.
    - **OR** provide `graph_schema` to define and run an ad-hoc workflow
      (an associated workflow record will be created automatically).
    - Provide `inputs` required by the workflow.
    - Returns the initial `WorkflowRun` record (usually in `SCHEDULED` state).
    - Requires `workflow:execute` permission on the active organization.
    """
    if not active_org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active organization not found")
    # Service layer handles creating ad-hoc workflow if needed and triggering execution
    async with db_manager as db:
        return await workflow_service.submit_workflow_run(
            db=db, run_submit=run_submit, owner_org_id=active_org_id, user=current_user
        )


@run_router.get(
    "/",
    response_model=List[schemas.WorkflowRunRead],
    summary="List Workflow Runs",
    # dependencies=[Depends(wf_deps.RequireRunReadActiveOrg)] # Check read perm on active org
)
async def list_runs(
    query_params: Annotated[schemas.WorkflowRunListQuery, Query()],
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(wf_deps.RequireRunReadActiveOrg), # Needed for superuser check
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Lists workflow runs accessible to the current user.

    - By default, lists runs belonging to the active organization.
    - **Superusers** can list runs for any organization by providing `owner_org_id`.
    - Supports filtering by:
        - `workflow_id`
        - `status`
        - `triggered_by_user_id` (only own runs for non-superusers)
    - Supports pagination via `skip` and `limit`.
    - Requires `run:read` permission on the active organization (or superuser status).
    """
    list_org_id = active_org_id
    list_user_id = query_params.triggered_by_user_id

    # Apply superuser logic for cross-org and cross-user filtering
    if current_user.is_superuser:
        if query_params.owner_org_id:
            list_org_id = query_params.owner_org_id or active_org_id
        # Superuser can filter by any user ID or None
        list_user_id = query_params.triggered_by_user_id or current_user.id
    else:
        # Non-superuser checks
        if query_params.owner_org_id and query_params.owner_org_id != active_org_id:
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot list runs for other organizations.")
        if query_params.triggered_by_user_id and query_params.triggered_by_user_id != current_user.id:
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot filter runs triggered by other users.")
        # If filter is None or current_user.id, it's allowed
        list_user_id = query_params.triggered_by_user_id

    # Prepare filters for service layer, converting schema to dict/kwargs if needed
    service_filters = schemas.WorkflowRunListQuery(
        workflow_id=query_params.workflow_id,
        status=query_params.status,
        triggered_by_user_id=list_user_id,
        owner_org_id=list_org_id # Pass the determined org_id to the service
        # Pagination handled separately
    )

    async with db_manager as db:
        return await workflow_service.list_runs(
            db=db,
            owner_org_id=list_org_id, # Pass final org id for main query scope
            filters=service_filters, # Pass filters object
            skip=query_params.skip,
            limit=query_params.limit
        )

@run_router.get(
    "/{run_id}",
    response_model=schemas.WorkflowRunRead,
    summary="Get Workflow Run Status Summary",
    dependencies=[Depends(wf_deps.RequireRunReadActiveOrg)] # Basic check on active org context
)
async def get_run_status(
    # Use dependency to fetch run and ensure it belongs to active org
    run: models.WorkflowRun = Depends(wf_deps.get_workflow_run_for_org),
    # Re-inject active_org_id for service call if needed, though run object has it
    # current_user: User = Depends(wf_deps.RequireRunReadActiveOrg),
    # db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    # workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Gets the status summary of a specific workflow run.

    - Fetches data primarily from the SQL database.
    - May attempt to augment the status with the latest update from the event stream (MongoDB) if available.
    - Requires `run:read` permission on the active organization.
    """
    # Dependency handles fetch and access check against active org
    # Call service method that might augment with Mongo status
    # async with db_manager as db:
    #     return await workflow_service.get_run_summary_with_mongo_status(
    #         db=db, run_id=run.id, owner_org_id=run.owner_org_id, user=current_user # Use org_id from fetched run
    #     )
    return run

@run_router.get(
    "/{run_id}/details",
    response_model=schemas.WorkflowRunDetailRead,
    summary="Get Workflow Run Details",
    # dependencies=[Depends(wf_deps.RequireRunReadActiveOrg)] # Basic check on active org context
)
async def get_run_details(
    run: models.WorkflowRun = Depends(wf_deps.get_workflow_run_for_org),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    current_user: User = Depends(wf_deps.RequireRunReadActiveOrg),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Gets detailed results for a specific workflow run.

    - Combines the summary data from the SQL database with the detailed event stream
      fetched from the configured NoSQL store (e.g., MongoDB).
    - Includes node outputs, status changes, message chunks, etc.
    - Requires `run:read` permission on the active organization.
    """
    # Dependency handles fetch and access check
    async with db_manager as db:
        return await workflow_service.get_run_details(db=db, run=run, user=current_user)

@run_router.get(
    "/{run_id}/stream",
    response_model=List[schemas.WorkflowRunEventDetail],
    summary="Get Workflow Run Event Stream",
    # dependencies=[Depends(wf_deps.RequireRunReadActiveOrg)] # Basic check on active org context
)
async def get_run_stream(
    run: models.WorkflowRun = Depends(wf_deps.get_workflow_run_for_org),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    current_user: User = Depends(wf_deps.RequireRunReadActiveOrg),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
    # skip: int = Query(0, ge=0, description="Number of events to skip"),
    # limit: int = Query(1000, ge=1, le=5000, description="Maximum number of events to return"),
):
    """
    Retrieves the sequence of events for a specific workflow run from the event store (e.g., MongoDB).

    - Useful for displaying progress or debugging.
    - Supports pagination using `skip` and `limit`.
    - Requires `run:read` permission on the active organization.
    """
    # Dependency handles fetch and access check
    async with db_manager as db:
        return await workflow_service.get_run_stream(db=db, run=run,
                                                    # skip=skip, limit=limit,
                                                    user=current_user)


# @run_router.post(
#     "/{run_id}/cancel",
#     response_model=schemas.WorkflowRunRead,
#     summary="Cancel Workflow Run",
#     dependencies=[Depends(wf_deps.RequireRunManage)] # Requires RUN_MANAGE permission
# )
# async def cancel_run(
#     run: models.WorkflowRun = Depends(wf_deps.get_workflow_run_for_active_org), # Ensures run is in active org
#     current_user: User = Depends(get_current_active_verified_user),
#     db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
#     workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
# ):
#     """
#     Attempts to cancel a workflow run that is currently `SCHEDULED` or `RUNNING`.

#     - Sends a cancellation signal to the execution engine (best-effort).
#     - Updates the run status to `CANCELLED` in the database.
#     - Requires `run:manage` permission on the active organization.
#     """
#     async with db_manager as db:
#         return await workflow_service.cancel_run(db=db, run=run, user=current_user)

# TODO: Add endpoints for Pause / Resume Run if needed


# === User Notification Endpoints ===

@notification_router.get(
    "/",
    response_model=List[schemas.UserNotificationRead],
    summary="List User Notifications"
    # Permissions: Requires authenticated user. Active org context is used implicitly.
)
async def list_user_notifications(
    query_params: schemas.NotificationListQuery = Depends(),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Lists notifications for the current authenticated user within their active organization.

    - Supports filtering by read status (`is_read=true` or `is_read=false`).
    - Supports sorting by `created_at` (default: descending).
    - Supports pagination via `skip` and `limit`.
    """
    async with db_manager as db:
        return await workflow_service.list_user_notifications(
            db=db,
            user_id=current_user.id,
            org_id=active_org_id,
            filters=query_params,
            skip=query_params.skip,
            limit=query_params.limit
        )

@notification_router.post(
    "/{notification_id}/read",
    response_model=schemas.UserNotificationRead,
    status_code=status.HTTP_200_OK,
    summary="Mark Notification as Read"
    # Permissions: User must be authenticated. Dependency checks ownership.
)
async def mark_notification_read(
    # Fetch notification ensuring it belongs to the current user using the dependency
    notification: models.UserNotification = Depends(wf_deps.get_notification_for_user),
    current_user: User = Depends(get_current_active_verified_user), # For service call context consistency
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Marks a specific notification as read for the current user.

    - Raises 404 if the notification does not exist or does not belong to the user.
    """
    # Dependency fetched and verified ownership
    async with db_manager as db:
        return await workflow_service.mark_notification_read(
            db=db,
            notification_id=notification.id,
            user_id=current_user.id
        )

@notification_router.post(
    "/read-all",
    status_code=status.HTTP_200_OK,
    summary="Mark All Notifications as Read"
    # Permissions: User must be authenticated.
)
async def mark_all_notifications_read(
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Marks all currently unread notifications as read for the current user
    within their active organization.
    """
    async with db_manager as db:
        count = await workflow_service.mark_all_notifications_read(
            db=db,
            user_id=current_user.id,
            org_id=active_org_id
        )
    return {"message": f"{count} notifications marked as read"}

@notification_router.get(
    "/unread-count",
    response_model=int,
    summary="Get Unread Notification Count"
    # Permissions: User must be authenticated.
)
async def get_unread_notification_count(
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Gets the count of unread notifications for the current user
    in their active organization.
    """
    async with db_manager as db:
        return await workflow_service.count_unread_notifications(
            db=db, user_id=current_user.id, org_id=active_org_id
        )


# === HITL Job Endpoints ===

@hitl_router.get(
    "/",
    response_model=List[schemas.HITLJobRead],
    summary="List HITL Jobs"
    # Permissions: Requires authenticated user. Service layer filters based on access rules.
)
async def list_hitl_jobs(
    query_params: schemas.HITLJobListQuery = Depends(),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Lists Human-in-the-Loop (HITL) jobs accessible by the current user.

    - By default, lists jobs within the active organization that are either
      assigned to the current user or are unassigned.
    - **Superusers** can list jobs for any organization by providing `owner_org_id`.
    - Supports filtering by:
        - `run_id`: Show jobs for a specific workflow run.
        - `assigned_user_id`: Filter by assignee ('me' for current user, or a specific user UUID).
        - `status`: Filter by job status (e.g., 'pending', 'responded').
        - `pending_only=true`: Shortcut to only show 'pending' jobs.
        - `exclude_cancelled=false`: Set to false to include 'cancelled' jobs (default is true).
    - Supports pagination via `skip` and `limit`.
    """
    # Service layer handles complex filtering logic, including 'me' translation and superuser checks
    async with db_manager as db:
        return await workflow_service.list_hitl_jobs(
            db=db,
            owner_org_id=active_org_id, # Pass active org as context
            user=current_user,
            filters=query_params,
            skip=query_params.skip,
            limit=query_params.limit
        )

@hitl_router.get(
    "/{job_id}",
    response_model=schemas.HITLJobRead,
    summary="Get HITL Job Details"
    # Permissions: User must be authenticated. Dependency checks access.
)
async def get_hitl_job(
    # Fetch job ensuring it belongs to active org and user can access it
    job: models.HITLJob = Depends(wf_deps.get_hitl_job_for_org),
    # Re-inject dependencies needed by the service method (if any beyond db)
    # current_user: User = Depends(get_current_active_verified_user), # Already injected by get_hitl_job_for_user
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Gets the details of a specific HITL job.

    - Requires the job to be in the active organization and accessible by the user
      (assigned to them or unassigned).
    """
    # Dependency handles fetch and access checks
    # Service method might add extra processing if needed, but here just return job
    # async with db_manager as db:
    #     return await workflow_service.get_hitl_job(db=db, job=job, user=current_user) # Service method just returns job
    return job

# @hitl_router.post(
#     "/{job_id}/respond",
#     response_model=schemas.HITLJobRead,
#     summary="Respond to HITL Job"
#     # Permissions: User must be authenticated. Dependency checks access.
# )
# async def respond_to_hitl_job(
#     response_in: schemas.HITLJobRespond,
#     job: models.HITLJob = Depends(wf_deps.get_hitl_job_for_user), # Fetch job ensuring access
#     current_user: User = Depends(get_current_active_verified_user),
#     db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
#     workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
# ):
#     """
#     Submits a response to a pending HITL job.

#     - Requires the job to be in `PENDING` status and accessible by the user.
#     - Validates the `response_data` against the job's `response_schema` (if defined).
#     - Updates the job status to `RESPONDED`.
#     - Triggers the resumption of the associated workflow run.
#     """
#     # Dependency handles fetch and access checks
#     # Service handles validation, DB update, and triggering resumption
#     async with db_manager as db:
#         return await workflow_service.respond_to_hitl_job(
#             db=db,
#             job=job,
#             response_data=response_in.response_data,
#             user=current_user
#         )

@hitl_router.post(
    "/{job_id}/cancel",
    response_model=schemas.HITLJobRead,
    summary="Cancel HITL Job"
    # Permissions: Requires access to the job (checked by dependency)
    # TODO: Define specific permission? run:manage? hitl:manage? Assume job access is sufficient for now.
)
async def cancel_hitl_job(
    job: models.HITLJob = Depends(wf_deps.get_hitl_job_for_org), # Fetch job ensuring access
    current_user: User = Depends(get_current_active_verified_user),
    db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
    workflow_service: services.WorkflowService = Depends(wf_deps.get_workflow_service_dependency),
):
    """
    Cancels a pending HITL job.

    - Requires the job to be in `PENDING` status and accessible by the user.
    - Updates the job status to `CANCELLED`.
    - Note: This may or may not automatically fail the associated workflow run,
      depending on the workflow's design.
    """
    async with db_manager as db:
        return await workflow_service.cancel_hitl_job(db=db, job=job, user=current_user)

