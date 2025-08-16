"""Service layer for the Workflow Application.

This module contains the business logic for managing workflows, runs,
templates, notifications, and HITL jobs. It uses the crud layer
for database interactions.
"""

import json
import uuid
import asyncio # Keep asyncio import
from datetime import datetime, timezone # Add timezone
from typing import List, Optional, Dict, Any, Union, Tuple
import copy

from db.session import get_async_pool
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from pydantic import ValidationError # For schema validation
from prefect.client.schemas import FlowRun

from jsonschema import validate
from jsonschema.validators import Draft202012Validator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from global_utils import datetime_now_utc
from global_config.logger import get_logger
from sqlmodel import or_, select
from kiwi_app.auth.dependencies import _check_permissions_for_org, get_user_dao
from kiwi_app.auth.exceptions import PermissionDeniedException
from kiwi_app.workflow_app.constants import WorkflowPermissions
from kiwi_app.workflow_app import models, schemas, crud
from kiwi_app.workflow_app.constants import WorkflowRunStatus, NotificationType, HITLJobStatus, LaunchStatus # Import LaunchStatus
from kiwi_app.auth.models import User, Organization # For type hinting and context
from kiwi_app.settings import settings # Import settings for Mongo paths etc.
from workflow_service.registry import registry
from kiwi_app.workflow_app.workflow_config_override import apply_graph_override # Added import
from kiwi_app.billing import services as billing_services
from kiwi_app.billing.models import CreditType

# MongoDB Client and Event Schemas
from mongo_client import AsyncMongoDBClient
from redis_client import AsyncRedisClient
from workflow_service.config.constants import GRAPH_STATE_SPECIAL_NODE_NAME, STATE_KEY_DELIMITER
from workflow_service.graph.graph import GraphSchema
from workflow_service.services import events as event_schemas # For Run Details

# Import the worker trigger function
# Ensure this path is correct based on your project structure
from workflow_service.services.worker import trigger_workflow_run

# Placeholder for JSON Schema validation library (e.g., jsonschema)
# import jsonschema # Add to requirements if used

logger = get_logger(__name__)

# No custom exception needed - using standard FastAPI HTTPException with appropriate status codes


class WorkflowService:
    """Service class containing business logic for workflows."""

    def __init__(
        self,
        node_template_dao: crud.NodeTemplateDAO,
        workflow_dao: crud.WorkflowDAO,
        workflow_run_dao: crud.WorkflowRunDAO,
        prompt_template_dao: crud.PromptTemplateDAO,
        schema_template_dao: crud.SchemaTemplateDAO,
        user_notification_dao: crud.UserNotificationDAO,
        hitl_job_dao: crud.HITLJobDAO,
        workflow_config_override_dao: crud.WorkflowConfigOverrideDAO = None,
        db_registry = None,
        mongo_client: Optional[AsyncMongoDBClient] = None, # Make Mongo optional for now
        billing_service: billing_services.BillingService = None,
    ) -> None:
        """Initialize the WorkflowService with its DAO and client dependencies."""
        self.node_template_dao = node_template_dao
        self.workflow_dao = workflow_dao
        self.workflow_run_dao = workflow_run_dao
        self.prompt_template_dao = prompt_template_dao
        self.schema_template_dao = schema_template_dao
        self.user_notification_dao = user_notification_dao
        self.hitl_job_dao = hitl_job_dao
        self.workflow_config_override_dao = workflow_config_override_dao
        self.mongo_client = mongo_client
        self.db_registry: registry.DBRegistry = db_registry
        self.billing_service = billing_service

    # --- NodeTemplate Operations --- #

    async def list_node_templates(
        self,
        db: AsyncSession,
        *,
        launch_statuses: Optional[List[LaunchStatus]] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[models.NodeTemplate]:
        """Lists node templates, optionally filtered by launch status."""
        # DAO handles default filtering if launch_statuses is None
        templates = await self.node_template_dao.get_multi(
            db, launch_statuses=launch_statuses, skip=skip, limit=limit
        )
        return list(templates) # Ensure list return type

    async def get_node_template(
        self,
        db: AsyncSession,
        *,
        name: str,
        version: str
    ) -> Optional[models.NodeTemplate]:
        """Gets a specific node template by name and version."""
        # Consider adding permission checks if needed (e.g., only specific roles can see experimental)
        return await self.node_template_dao.get_by_name_version(db, name=name, version=version)


    # --- Workflow Operations --- #

    async def create_workflow(
        self, 
        db: AsyncSession, 
        *, 
        workflow_in: schemas.WorkflowCreate, 
        owner_org_id: uuid.UUID, 
        user: User # Changed from user_id to User object
    ) -> models.Workflow:
        """Creates a new workflow."""
        # Check name uniqueness
        # TODO: some sanity check to prevent over duplication is required here or not?
        # existing = await self.workflow_dao.get_by_name(db, name=workflow_in.name, owner_org_id=owner_org_id)
        # if existing:
        #     raise HTTPException(
        #         status_code=status.HTTP_409_CONFLICT,
        #         detail=f"Workflow with name '{workflow_in.name}' already exists in this organization."
        #     )
        # TODO: Add validation logic for graph_config structure if needed
        return await self.workflow_dao.create(
            db, obj_in=workflow_in, owner_org_id=owner_org_id, user_id=user.id
        )

    async def get_workflow(
        self, 
        db: AsyncSession, 
        *, 
        user: User,
        workflow_id: uuid.UUID, 
        owner_org_id: uuid.UUID, # Used for permission check
        include_system_entities: bool = True,
    ) -> models.Workflow:
        """
        Retrieves a workflow by ID, ensuring it belongs to the specified organization.
        Raises 404 if not found or ownership mismatch.
        """
        # DAO now handles the org check
        workflow = await self.workflow_dao.get_by_id_and_org_or_public(db, workflow_id=workflow_id, user=user, org_id=owner_org_id, include_system_entities=include_system_entities)
        if not workflow:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found or access denied")
            # return workflow
        return workflow

    async def list_workflows(
        self, 
        db: AsyncSession, 
        *, 
        owner_org_id: uuid.UUID, 
        include_public: bool = True,
        include_system_entities: bool = False,
        # launch_status: Optional[LaunchStatus] = None, # LaunchStatus not on Workflow model
        skip: int = 0, 
        limit: int = 100
    ) -> List[models.Workflow]:
        """Lists workflows for a specific organization."""
        # Pass filters to DAO if they were available
        workflows = await self.workflow_dao.get_multi_by_org(
            db, owner_org_id=owner_org_id, include_public=include_public, include_system_entities=include_system_entities, skip=skip, limit=limit
        )
        return list(workflows) # Ensure list return type

    async def update_workflow(
        self, 
        db: AsyncSession, 
        *, 
        workflow: models.Workflow, # Use workflow object from dependency (assumes permission check done)
        workflow_update: schemas.WorkflowUpdate,
        user: User # Changed from user_id
    ) -> models.Workflow:
        """Updates an existing workflow."""
        # Check for name collision if name is being changed
        # if workflow_update.name and workflow_update.name != workflow.name:
        #     existing = await self.workflow_dao.get_by_name(db, name=workflow_update.name, owner_org_id=workflow.owner_org_id)
        #     if existing and existing.id != workflow.id:
        #         raise HTTPException(
        #             status_code=status.HTTP_409_CONFLICT,
        #             detail=f"Workflow with name '{workflow_update.name}' already exists in this organization."
        #         )
        # TODO: Add validation logic for graph_config if it's updated

        return await self.workflow_dao.update(db, db_obj=workflow, obj_in=workflow_update, user_id=user.id)

    async def delete_workflow(
        self, 
        db: AsyncSession, 
        *, 
        workflow: models.Workflow, # Use workflow object from dependency (assumes permission check done)
        user: User # Keep user for audit/permission logs if needed later
    ) -> bool:
        """Deletes a workflow."""
        # DAO handles the deletion and org check
        deleted_workflow = await self.workflow_dao.remove_obj(db, obj=workflow)
        # TODO: Consider implications - should deleting a workflow delete its runs?
        # Add logic here to handle cascading deletes or archiving if necessary
        return deleted_workflow is not None

    # --- Workflow Run Operations --- #

    async def submit_workflow_run(
        self, 
        db: AsyncSession, 
        *, 
        run_submit: schemas.WorkflowRunCreate, # New schema for submission
        owner_org_id: uuid.UUID, 
        user: User,
    ) -> models.WorkflowRun:
        """
        Submits a new workflow run, creating a workflow first if graph_schema is provided.
        Triggers the actual execution via the worker.
        
        Args:
            db: AsyncSession instance.
            run_submit: Schema containing workflow_id OR graph_schema, plus inputs/thread_id.
            owner_org_id: ID of the organization context for the run.
            user: The user initiating the run.

        Returns:
            The created WorkflowRun object (in SCHEDULED state).
            
        Raises:
            HTTPException: If workflow not found (when using workflow_id) or other errors occur.
        """
        workflow_id = run_submit.workflow_id
        graph_schema_dict = None

        if run_submit.resume_after_hitl:
            if workflow_id is not None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot provide both workflow_id and resume_after_hitl in the same request")
            if run_submit.graph_schema is not None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot provide both graph_schema and resume_after_hitl in the same request")
            if run_submit.run_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Must provide run_id when resuming after HITL")

            workflow_run = await self.workflow_run_dao.get_run_by_id_and_org(db, run_id=run_submit.run_id, org_id=owner_org_id)
            if not workflow_run:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
            if workflow_run.status != WorkflowRunStatus.WAITING_HITL and (not run_submit.force_resume_experimental_option):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot resume after HITL if run is not in WAITING_HITL state")

            # For HITL resume, get the latest pending HITL job and validate input
            # Get latest pending HITL job for this run
            pending_hitl_jobs = await self.hitl_job_dao.get_pending_by_run(db, requesting_run_id=workflow_run.id)
            if not pending_hitl_jobs and (not run_submit.force_resume_experimental_option):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="No pending HITL jobs found for this run"
                )
            if len(pending_hitl_jobs) > 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Multiple pending HITL jobs found for this run, this is unexpected and should not happen. Please contact support."
                )
            if pending_hitl_jobs:
                # Get the latest HITL job
                hitl_job = pending_hitl_jobs[0]  # Jobs are ordered by created_at desc
                
                # Validate input against response schema if one exists
                if hitl_job.response_schema:
                    try:
                        validate(instance=run_submit.inputs, schema=hitl_job.response_schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
                    except ValidationError as e:
                        error_path = "/".join(str(part) for part in e.path)
                        error_msg = f"{error_path}: {e.message}" if error_path else e.message
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"HITL input validation failed: {error_msg}"
                        )
                
                # Store HITL response and mark job as done
                hitl_job.response_data = run_submit.inputs
                hitl_job.status = HITLJobStatus.RESPONDED
                hitl_job.responded_at = datetime_now_utc()
                db.add(hitl_job)
                # await db.commit()
                
                # Update run status to SCHEDULED for resumption
                workflow_run.status = WorkflowRunStatus.SCHEDULED
                db.add(workflow_run)
                await db.commit()
                await db.refresh(hitl_job)
                await db.refresh(workflow_run)
            
            workflow = await self.get_workflow(db, workflow_id=workflow_run.workflow_id, user=user, owner_org_id=owner_org_id, include_system_entities=True)

            effective_graph_schema = workflow.graph_config

            if workflow_run.applied_workflow_config_overrides:
                override_ids = workflow_run.applied_workflow_config_overrides.split(",")
                if override_ids:
                    overrides = None
                    try:
                        overrides = await self.workflow_config_override_dao.get_overrides_by_ids(
                            db=db,
                            override_ids=override_ids
                        )
                    except Exception as e:
                        logger.error(f"ERROR: Failed to get overrides for run {workflow_run.id}: {e}")
                        # raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get overrides for run")
                    if overrides:
                        try:
                            effective_graph_schema = await self.apply_list_of_overrides(
                                overrides=overrides,
                                base_graph_schema=workflow.graph_config,
                                workflow_id=workflow.id
                            )
                        except Exception as e:
                            logger.error(f"ERROR: Failed to apply overrides for run {workflow_run.id}: {e}")
                            # raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to apply overrides for run")
            
        else:
            if run_submit.graph_schema:
                assert workflow_id is None, "Cannot provide both workflow_id and graph_schema in the same request"
                # Create a new workflow from the ad-hoc schema
                if isinstance(run_submit.graph_schema, dict):
                    graph_schema_dict = run_submit.graph_schema
                else:
                    # Assuming Pydantic model if not dict
                    graph_schema_dict = json.loads(run_submit.graph_schema.model_dump_json())


                # Generate a default name for the ad-hoc workflow
                timestamp = datetime_now_utc().strftime("%Y%m%d-%H%M%S")
                workflow_name = f"Adhoc Workflow - {user.email or user.id} - {timestamp}"

                workflow_create_data = schemas.WorkflowCreate(
                    name=workflow_name,
                    description="Workflow created from ad-hoc execution request.",
                    graph_config=graph_schema_dict,
                    is_template=False, # Ad-hoc workflows are typically not templates
                    launch_status=LaunchStatus.EXPERIMENTAL # Mark ad-hoc as experimental
                )
                # Use internal create method (avoids unique name check)
                workflow = await self._create_workflow_internal(
                    db, workflow_in=workflow_create_data, owner_org_id=owner_org_id, user_id=user.id
                )
                workflow_id = workflow.id
                # Keep graph_schema_dict for worker trigger
            elif workflow_id:
                # Validate the provided workflow_id belongs to the organization
                # NOTE: we want regular users to be able to execute system entity eg: workflows but which are marked public!
                workflow = await self.get_workflow(db, workflow_id=workflow_id, user=user, owner_org_id=owner_org_id, include_system_entities=True)
                workflow_name = workflow.name
                # If not found, get_workflow raises 404
                graph_schema_dict = workflow.graph_config # Get schema for worker trigger
            else:
                # Validation should happen in the schema, but double-check
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid submission: missing workflow_id or graph_schema.")
                
            # 2. Create the WorkflowRun record with SCHEDULED status
            if run_submit.run_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot provide run_id when submitting a new run")

            overrides, effective_graph_schema = await self.list_workflow_specific_overrides_and_optional_apply(
                db=db,
                include_active=run_submit.include_active_overrides,
                include_tags=run_submit.include_override_tags,
                active_org_id=owner_org_id,
                requesting_user=user,
                base_workflow_to_apply_overrides_to=workflow
            )
            
            workflow_run = await self.workflow_run_dao.create(
                db,
                workflow_id=workflow_id,
                workflow_name=workflow_name,
                owner_org_id=owner_org_id,
                triggered_by_user_id=user.id,
                inputs=run_submit.inputs,
                thread_id=run_submit.thread_id, # Pass thread_id if provided
                status=WorkflowRunStatus.SCHEDULED, # Explicitly set status
                tag=run_submit.tag,
                applied_workflow_config_overrides=",".join([str(override.id) for override in overrides]) if overrides else None,
                parent_run_id=run_submit.parent_run_id,
            )
            # TODO: FIXME: do the above and below in one step by checking thread_id is None!
            if not workflow_run.thread_id:
                workflow_run.thread_id = workflow_run.id
                db.add(workflow_run)
                await db.commit()
                await db.refresh(workflow_run)
            
            # await self.billing_service.allocate_credits_for_operation(
            #     db=db,
            #     org_id=owner_org_id,
            #     user_id=user.id,
            #     operation_id=workflow_run.id,
            #     credit_type=CreditType.WORKFLOWS,
            #     estimated_credits=1,
            # )

        # 3. Trigger the actual execution via Prefect worker/helper
        try:
            # Ensure we have the graph schema to pass to the worker
            graph_schema_dict = effective_graph_schema

            # Trigger the workflow run via the helper function
            flow_run: FlowRun = await trigger_workflow_run(
                workflow_id=workflow_run.workflow_id,
                owner_org_id=owner_org_id,
                triggered_by_user_id=user.id,
                inputs=run_submit.inputs,
                run_id=workflow_run.id, # Pass the created run_id
                thread_id=workflow_run.thread_id, # Pass thread_id
                graph_schema=GraphSchema.model_validate(graph_schema_dict), # Pass the graph schema
                resume_after_hitl=run_submit.resume_after_hitl, # This is a new submission
                prefect_run_ids=workflow_run.prefect_run_ids, # Pass the prefect run_id if provided
                streaming_mode=run_submit.streaming_mode,
            )
            workflow_run = await self.workflow_run_dao.update(
                db,
                db_obj=workflow_run,
                obj_in={
                    "prefect_run_ids": ",".join([workflow_run.prefect_run_ids, str(flow_run.id)]) if workflow_run.prefect_run_ids else str(flow_run.id)
                }
            )
        except Exception as e:
            # If triggering fails, mark the run as failed immediately
            await self.workflow_run_dao.update_status(
                db,
                run_id=workflow_run.id,
                status=WorkflowRunStatus.FAILED,
                error_message=f"Failed to trigger execution: {e}",
                ended_at=datetime_now_utc()
            )
            # Re-raise or log appropriately
            # Consider logging the full traceback: import traceback; traceback.print_exc()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to trigger workflow execution: {e}")

        return workflow_run

    # Internal helper to bypass unique name check for ad-hoc workflows
    async def _create_workflow_internal(
        self,
        db: AsyncSession,
        *,
        workflow_in: schemas.WorkflowCreate,
        owner_org_id: uuid.UUID,
        user_id: Optional[uuid.UUID]
    ) -> models.Workflow:
        """Internal workflow creation without unique name check."""
        return await self.workflow_dao.create(
            db, obj_in=workflow_in, owner_org_id=owner_org_id, user_id=user_id
        )

    async def get_run(
        self, 
        db: AsyncSession, 
        *, 
        run_id: uuid.UUID, 
        owner_org_id: uuid.UUID
    ) -> models.WorkflowRun:
        """Retrieves a run by ID, checking organization ownership."""
        # DAO handles the org check
        run = await self.workflow_run_dao.get_run_by_id_and_org(db, run_id=run_id, org_id=owner_org_id)
        if not run:
            # Use standard HTTPException
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found or access denied")
        return run
    
    async def get_run_state(
        self,
        db: AsyncSession,
        *,
        run: models.WorkflowRun,
    ) -> Dict[str, Any]:
        """Retrieves the state for a run."""
        # TODO: Implement this
        """
        Retrieves the state for a workflow run.
        
        This function fetches a workflow run by ID and organization, then retrieves
        the state from the checkpoint storage using the run's thread_id.
        
        Args:
            db: AsyncSession instance for database operations
            run: models.WorkflowRun instance
            owner_org_id: UUID of the organization that owns the run
            
        Returns:
            Dict containing the state of the workflow run
            
        Raises:
            HTTPException: If the run is not found or if there's an error retrieving the state
        """
        # First, retrieve the run to get the thread_id
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Workflow run not found or access denied"
            )
        
        # Check if thread_id exists
        if not run.thread_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Run does not have a thread_id associated with it"
            )
            
        try:
            # Use the thread_id to retrieve the central state from the checkpoint storage
            
            async with get_async_pool() as async_psycopg_pool:
                checkpointer = AsyncPostgresSaver(async_psycopg_pool)
                config = {"configurable": {"thread_id": str(run.thread_id)}}
                
                # Get the checkpoint snapshot
                snapshot = await checkpointer.aget_tuple(config)
                
                if not snapshot:
                    logger.warning(f"No checkpoint state found for run {run.id} with thread_id {run.thread_id}")
                    return {"state": None, "message": "No state found for this run"}
                
                # Return the central state
                return {
                    # Split channel values into central state and node outputs
                    # Central state keys have format "central_state:field_name"
                    # Node output keys have format "node_id:output"
                    "central_state": {
                        field_name.split(STATE_KEY_DELIMITER)[1]: value 
                        for field_name, value in snapshot.checkpoint["channel_values"].items() 
                        if field_name.startswith(GRAPH_STATE_SPECIAL_NODE_NAME)
                    },
                    "node_outputs": {
                        field_name.split(STATE_KEY_DELIMITER)[0]: value
                        for field_name, value in snapshot.checkpoint["channel_values"].items()
                        if STATE_KEY_DELIMITER in field_name 
                        and field_name.endswith("output") 
                        and not field_name.startswith(GRAPH_STATE_SPECIAL_NODE_NAME)
                    },
                    "run_id": str(run.id),
                    "thread_id": str(run.thread_id)
                }
                
        except Exception as e:
            logger.error(f"Error retrieving central state for run {run.id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve central state: {str(e)}"
            )
        

    async def list_runs(
        self, 
        db: AsyncSession, 
        *, 
        owner_org_id: uuid.UUID, 
        filters: schemas.WorkflowRunListQuery, # Use schema for filters
        skip: int = 0, # Keep individual pagination params for clarity at API level
        limit: int = 100
    ) -> List[models.WorkflowRun]:
        """
        Lists workflow runs for an organization, applying filters and pagination.
        """
        filter_dict = filters.model_dump(exclude_unset=True) if filters else {}

        # Always filter by the active owner_org_id unless superuser overrides
        # (Superuser check should ideally happen in dependency/permission checker)
        filter_dict["owner_org_id"] = owner_org_id

        # Remove pagination keys if they exist in the filter dict, use direct params
        filter_dict.pop("skip", None)
        filter_dict.pop("limit", None)

        # Use the filtered DAO method
        runs = await self.workflow_run_dao.get_multi_filtered(
            db, filters=filter_dict, skip=skip, limit=limit
            # Pass sorting info if available in filters schema and handled by DAO
            # order_by=filters.order_by, order_dir=filters.order_dir
        )
        return list(runs) # Ensure list return type

    async def get_run_details(
        self, 
        db: AsyncSession, # Keep db session for SQL part
        *,
        run: models.WorkflowRun, # Fetched run object from dependency
        user: User # Added user for permission check
    ) -> schemas.WorkflowRunDetailRead:
        """
        Retrieves detailed results for a workflow run, combining SQL summary
        and detailed event stream from MongoDB, respecting user permissions.
        """
        # Start with SQL data
        run_detail = schemas.WorkflowRunDetailRead.model_validate(run)

        # Fetch detailed events from MongoDB
        if not self.mongo_client:
            logger.warning(f"MongoDB client not configured. Cannot fetch detailed events for run {run.id}")
            run_detail.detailed_results = []
            return run_detail

        try:
            # Determine allowed prefixes based on user role
            allowed_prefixes: List[Union[str, List[str]]]
            if user.is_superuser:
                allowed_prefixes = [["*"]]
            else:
                # Regular user can access anything starting with their org_id
                allowed_prefixes = [[str(run.owner_org_id), "*"]]

            # Construct path prefix for run events
            # Targets the specific run within the org.
            # NOTE: TODO: FIXME: this is a compound index in mongo DB which is most efficient for hierarchical retrieval, so it may make sense for setting up the prefix keys too!
            mongo_runs_events_pattern = ["*", "*", str(run.id), "*"]

            allowed_event_schemas = [event_schemas.WorkflowRunNodeOutputEvent, event_schemas.WorkflowRunStatusUpdateEvent]
            allowed_event_keys = set()
            for event_schema in allowed_event_schemas:
                allowed_event_keys.update(list(event_schema.model_fields.keys()))
            
            if not user.is_superuser:
                if "payload" in allowed_event_keys:
                    allowed_event_keys.remove("payload")

            include_fields = [f"data.{k}" for k in allowed_event_keys]
            allowed_event_types = [event_schemas.WorkflowEvent.NODE_OUTPUT.value, event_schemas.WorkflowEvent.WORKFLOW_RUN_STATUS.value]

            # Find all events for this run, sorted by sequence number, respecting permissions
            event_dicts = await self.mongo_client.search_objects(
                key_pattern=mongo_runs_events_pattern,
                # filter_query={}, # Get all events for the run
                value_sort_by=[("timestamp", -1), ("sequence_i", -1)], # Sort by timestamp descending, then sequence descending
                allowed_prefixes=allowed_prefixes, # Apply permission check
                value_filter={"event_type": {"$in": allowed_event_types}},
                include_fields=include_fields,
            )

            # Validate and structure events
            detailed_events = []
            for raw_doc in event_dicts:
                 event_dict = raw_doc["data"]
                 try:
                    # Validate against the base event schema
                    base_event = event_schemas.WorkflowBaseEvent.model_validate(event_dict)
                    if base_event.event_type == event_schemas.WorkflowEvent.NODE_OUTPUT.value:
                        base_event = event_schemas.WorkflowRunNodeOutputEvent.model_validate(event_dict)
                        # detailed_events.append(node_output)
                    elif base_event.event_type == event_schemas.WorkflowEvent.WORKFLOW_RUN_STATUS.value:
                        base_event = event_schemas.WorkflowRunStatusUpdateEvent.model_validate(event_dict)
                        # detailed_events.append(status_update)
                    elif base_event.event_type == event_schemas.WorkflowEvent.HITL_REQUEST.value:
                        base_event = event_schemas.HITLRequestEvent.model_validate(event_dict)
                        # detailed_events.append(hitl_request)
                    elif base_event.event_type == event_schemas.WorkflowEvent.TOOL_CALL.value:
                        base_event = event_schemas.ToolCallEvent.model_validate(event_dict)
                        # detailed_events.append(tool_call)
                    # TODO: Could try validating against specific types based on 'event_type'
                    # for more detailed structure, but base is often sufficient for listing.
                    detailed_events.append(base_event)
                 except ValidationError as e:
                    # Log properly
                    logger.warning(f"Skipping invalid event data in MongoDB for run {run.id}: {e} - Data: {event_dict}")

            run_detail.detailed_results = detailed_events

        except Exception as e:
            # Log properly
            logger.error(f"Error fetching detailed results from MongoDB for run {run.id}: {e}")
            run_detail.detailed_results = [] # Return empty list on error
        
        return run_detail
        
    async def get_run_stream(
        self,
        db: AsyncSession, # Keep db session for SQL part
        *,
        run: models.WorkflowRun, # Fetched run object from dependency
        user: User, # Added user for permission check
        # skip: int = 0,
        # limit: int = 1000 # Default limit for stream events
    ) -> List[schemas.WorkflowRunEventDetail]:
        """
        Retrieves the event stream for a workflow run from MongoDB, respecting user permissions.
        
        Args:
            db: Database session (kept for consistency with other methods)
            run: The workflow run object to fetch events for
            user: User requesting the events (for permission checking)
            skip: Number of events to skip (for pagination)
            limit: Maximum number of events to return
            
        Returns:
            List of workflow events in chronological order
            
        Raises:
            HTTPException: If MongoDB client is not configured or if there's an error fetching events
        """
        if not self.mongo_client:
            logger.error("MongoDB client not configured. Cannot fetch event stream.")
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="MongoDB client not configured.")

        try:
            # Determine allowed prefixes based on user role
            allowed_prefixes: List[Union[str, List[str]]]
            if user.is_superuser:
                allowed_prefixes = [["*"]]
            else:
                # Regular user can access anything starting with their org_id
                allowed_prefixes = [[str(run.owner_org_id), "*"]]

            # Construct path prefix for run events
            # Targets the specific run within the org
            # NOTE: TODO: FIXME: this is a compound index in mongo DB which is most efficient for hierarchical retrieval, so it may make sense for setting up the prefix keys too!
            mongo_runs_events_pattern = ["*", "*", str(run.id), "*"]

            # Find all events for this run, sorted by sequence number, respecting permissions
            event_dicts = await self.mongo_client.search_objects(
                key_pattern=mongo_runs_events_pattern,
                # filter_query={}, # Get all events for the run
                value_sort_by=[("timestamp", -1), ("sequence_i", -1)], # Sort by sequence ascending for chronological order
                # skip=skip,
                # limit=limit,
                allowed_prefixes=allowed_prefixes # Apply permission check
            )

            # Validate and structure events
            stream_events = []
            for raw_doc in event_dicts:
                event_dict = raw_doc["data"]
                try:
                    # Validate against the base event schema
                    base_event = event_schemas.WorkflowBaseEvent.model_validate(event_dict)
                    typed_event = None
                    # Convert to specific event type based on event_type
                    if base_event.event_type == event_schemas.WorkflowEvent.NODE_OUTPUT.value:
                        typed_event = event_schemas.WorkflowRunNodeOutputEvent.model_validate(event_dict)
                        # stream_events.append(typed_event)
                    elif base_event.event_type == event_schemas.WorkflowEvent.WORKFLOW_RUN_STATUS.value:
                        typed_event = event_schemas.WorkflowRunStatusUpdateEvent.model_validate(event_dict)
                        # stream_events.append(typed_event)
                    elif base_event.event_type == event_schemas.WorkflowEvent.MESSAGE_CHUNK.value:
                        typed_event = event_schemas.MessageStreamChunk.model_validate(event_dict)
                        # stream_events.append(typed_event)
                    elif base_event.event_type == event_schemas.WorkflowEvent.HITL_REQUEST.value:
                        typed_event = event_schemas.HITLRequestEvent.model_validate(event_dict)
                        # stream_events.append(typed_event)
                    elif base_event.event_type == event_schemas.WorkflowEvent.TOOL_CALL.value:
                        typed_event = event_schemas.ToolCallEvent.model_validate(event_dict)
                        # stream_events.append(typed_event)
                    else:
                        # For unknown event types, use the base event
                        logger.info(f"Unknown event type {base_event.event_type} for run {run.id}, using base event model")
                    stream_events.append(typed_event or event_dict)
                except ValidationError as e:
                    # Log properly
                    logger.warning(f"Skipping invalid event data in MongoDB for run {run.id}: {e} - Data: {event_dict}")

            return stream_events

        except Exception as e:
            # Log properly
            logger.error(f"Error fetching event stream from MongoDB for run {run.id}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch run stream")

    async def get_run_logs(
        self,
        db: AsyncSession,
        *,
        run: models.WorkflowRun,
        skip: int = 0,
        limit: int = 10000,
    ) -> schemas.WorkflowRunLogs:
        """
        Retrieve Prefect logs for the provided workflow run, including direct child subworkflow runs.

        Notes:
        - Aggregates Prefect `flow_run_id`s from the given run and its direct children (non-recursive).
        - Does NOT recursively traverse grandchildren or deeper levels.
        - Returns a list of simplified LogEntry items (level, message, timestamp, flow_run_id).
        """
        try:
            # Lazy import to avoid optional dependency issues at import time
            from prefect import get_client as _get_client
            from prefect.client.schemas.filters import LogFilter as _LogFilter, LogFilterFlowRunId as _LogFilterFlowRunId
        except Exception:
            # Prefect client not available; return empty logs instead of failing
            return schemas.WorkflowRunLogs(logs=[])

        try:
            if not run:
                return schemas.WorkflowRunLogs(logs=[])

            # Collect Prefect flow run IDs for this run and its direct children (non-recursive)
            aggregated_prefect_run_ids: set[uuid.UUID] = set()

            # Helper to parse comma-separated UUID strings safely
            def _extend_with_prefect_ids(prefect_ids_str: Optional[str]) -> None:
                if not prefect_ids_str:
                    return
                for _id in prefect_ids_str.split(","):
                    _id = _id.strip()
                    if not _id:
                        continue
                    try:
                        aggregated_prefect_run_ids.add(uuid.UUID(_id))
                    except Exception:
                        # Skip invalid UUIDs silently
                        continue

            # Add current run IDs
            _extend_with_prefect_ids(run.prefect_run_ids)

            # Fetch direct child runs and add their IDs (do not recurse)
            try:
                child_runs = await self.workflow_run_dao.get_children_by_parent_run_id(
                    db,
                    parent_run_id=run.id,
                    owner_org_id=run.owner_org_id,
                    order_by="created_at",
                    order_dir="desc",
                )
            except Exception:
                child_runs = []

            for child in child_runs:
                _extend_with_prefect_ids(getattr(child, "prefect_run_ids", None))

            if not aggregated_prefect_run_ids:
                return schemas.WorkflowRunLogs(logs=[])

            flow_logs = []
            async with _get_client() as client:
                remaining = max(1, int(limit))
                current_offset = max(0, int(skip))
                while remaining > 0:
                    batch_limit = 200 if remaining > 200 else remaining
                    batch = await client.read_logs(
                        log_filter=_LogFilter(flow_run_id=_LogFilterFlowRunId(any_=list(aggregated_prefect_run_ids))),
                        limit=batch_limit,
                        offset=current_offset,
                    )
                    if not batch:
                        break
                    flow_logs.extend(batch)
                    fetched = len(batch)
                    remaining -= fetched
                    current_offset += fetched
                    if fetched < batch_limit:
                        break

            flow_logs.sort(key=lambda log: getattr(log, 'timestamp', datetime_now_utc()), reverse=True)

            level_map = {50: "CRITICAL", 40: "ERROR", 30: "WARNING", 20: "INFO", 10: "DEBUG"}
            formatted_logs = [
                schemas.LogEntry(
                    level=level_map.get(getattr(log, 'level', None), "UNKNOWN"),
                    message=getattr(log, 'message', ""),
                    timestamp=getattr(log, 'timestamp', datetime_now_utc()),
                    flow_run_id=getattr(log, 'flow_run_id', None),
                )
                for log in flow_logs
            ]

            return schemas.WorkflowRunLogs(logs=formatted_logs)
        except Exception as e:
            logger.error(f"Error fetching Prefect logs for workflow run {getattr(run, 'id', None)}: {e}", exc_info=True)
            return schemas.WorkflowRunLogs(logs=[])


    async def cancel_run(
        self,
        db: AsyncSession,
        *,
        run: models.WorkflowRun, # Fetched run object from dependency
        user: User # User performing the action
    ) -> models.WorkflowRun:
        """Cancels a workflow run."""
        # Check if the run is in a cancellable state
        if run.status not in [WorkflowRunStatus.SCHEDULED, WorkflowRunStatus.RUNNING, WorkflowRunStatus.WAITING_HITL, WorkflowRunStatus.PAUSED]:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Run in status {run.status} cannot be cancelled.")

        # TODO: Implement logic to signal the execution engine (Prefect/worker) to actually stop the run.
        # This is CRITICAL for actual cancellation.
        # Example Placeholder:
        # try:
        #     await signal_engine_to_cancel(run.id)
        # except Exception as engine_error:
        #     raise HTTPException(status_code=500, detail=f"Failed to signal engine cancellation: {engine_error}")
        logger.info(f"Signaling cancellation for run {run.id} (actual engine stop needs implementation)")

        # Update DB status optimistically
        updated = await self.workflow_run_dao.update_status(
            db,
            run_id=run.id,
            status=WorkflowRunStatus.CANCELLED,
            ended_at=datetime_now_utc(),
            error_message=f"Run cancelled by user {user.email or user.id}"
        )
        if not updated:
             # This might happen if the status changed between the check and the update
             # Fetch the latest status to return accurate info
             await db.refresh(run)
             raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Run status changed to {run.status}, could not cancel.")

        await db.refresh(run) # Refresh the object with the updated status
        return run

    # Add Pause/Resume similarly if needed, requiring engine interaction

    # --- Template Operations --- #

    async def create_prompt_template(
        self,
        db: AsyncSession,
        *,
        template_in: schemas.PromptTemplateCreate,
        owner_org_id: uuid.UUID,
        user: User # For audit/context
    ) -> models.PromptTemplate:
        """Creates an organization-specific prompt template."""
        # Check for name/version collision within the org
        existing = await self.prompt_template_dao.get_by_name_version(
            db, name=template_in.name, version=template_in.version, owner_org_id=owner_org_id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Prompt template '{template_in.name}' version '{template_in.version}' already exists in this organization."
            )
        return await self.prompt_template_dao.create(db, obj_in=template_in, owner_org_id=owner_org_id)

    async def get_prompt_template(
        self,
        db: AsyncSession,
        *,
        template_id: uuid.UUID,
        owner_org_id: Optional[uuid.UUID] = None # If checking specific org template
    ) -> models.PromptTemplate:
        """
        Retrieves a prompt template by ID.
        If owner_org_id is provided, ensures it belongs to that org (and is not system).
        If owner_org_id is None, retrieves system or org template based on ID (permission check needed).
        """
        # Fetch by ID first
        template = await self.prompt_template_dao.get(db, id=template_id)
        if not template:
            # Use standard HTTPException
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Prompt Template {template_id} not found.")

        # If org context is provided, check ownership AND ensure it's not a system template
        if owner_org_id:
             if template.owner_org_id != owner_org_id or template.is_system_entity:
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Prompt Template {template_id} not found in organization {owner_org_id}.")
        # Else (no org context), need permission check if template is system or belongs to another org

        return template

    async def list_prompt_templates(
        self,
        db: AsyncSession,
        *,
        owner_org_id: uuid.UUID, # The org context of the request
        include_system: bool = True,
        skip: int = 0,
        limit: int = 100
    ) -> List[models.PromptTemplate]:
        """Lists prompt templates accessible in an organization context."""
        # Get org-specific templates
        org_templates_seq = await self.prompt_template_dao.get_multi_by_org(db, owner_org_id=owner_org_id, skip=skip, limit=limit)
        org_templates = list(org_templates_seq)

        system_templates = []
        if include_system:
            # Adjust limit/skip if needed for combined results, or fetch separately and combine smartly
            # Fetching separately for now, potential pagination issues if combined limit is small
            system_templates_seq = await self.prompt_template_dao.get_multi_system(db, skip=skip, limit=limit)
            system_templates = list(system_templates_seq)

        # Combine results (consider more sophisticated merging/pagination later)
        # Simple combination might exceed limit if both have results
        all_templates = org_templates + system_templates
        # Apply limit again if necessary, though ideally DAO pagination handled this
        # return all_templates[:limit] # Be careful with slicing combined results

        return all_templates


    async def update_prompt_template(
        self,
        db: AsyncSession,
        *,
        template: models.PromptTemplate, # Fetched template object (permission checked)
        template_update: schemas.PromptTemplateUpdate,
        user: User # For audit/context
    ) -> models.PromptTemplate:
        """Updates an organization-specific prompt template."""
        # Ensure trying to update an org-specific template
        if template.is_system_entity:
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System prompt templates cannot be updated.")

        # Check for name/version collision if being changed
        new_name = template_update.name or template.name
        new_version = template_update.version or template.version
        if new_name != template.name or new_version != template.version:
            existing = await self.prompt_template_dao.get_by_name_version(
                db, name=new_name, version=new_version, owner_org_id=template.owner_org_id
            )
            if existing and existing.id != template.id:
                 raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Prompt template '{new_name}' version '{new_version}' already exists."
                )
        # DAO prevents changing owner/system status
        return await self.prompt_template_dao.update(db, db_obj=template, obj_in=template_update)

    async def delete_prompt_template(
        self,
        db: AsyncSession,
        *,
        template: models.PromptTemplate, # Fetched template object (permission checked)
        user: User # For audit/context
    ) -> bool:
        """Deletes an organization-specific prompt template."""
        if template.is_system_entity:
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System prompt templates cannot be deleted.")

        deleted = await self.prompt_template_dao.remove_by_id_and_org(db, id=template.id, owner_org_id=template.owner_org_id)
        return deleted is not None

    # --- SchemaTemplate Operations (Mirror PromptTemplate) --- #

    async def create_schema_template(
        self,
        db: AsyncSession,
        *,
        template_in: schemas.SchemaTemplateCreate,
        owner_org_id: uuid.UUID,
        user: User
    ) -> models.SchemaTemplate:
        """Creates an organization-specific schema template."""
        existing = await self.schema_template_dao.get_by_name_version(
            db, name=template_in.name, version=template_in.version, owner_org_id=owner_org_id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Schema template '{template_in.name}' version '{template_in.version}' already exists."
            )
        # TODO: Validate schema_definition if provided
        return await self.schema_template_dao.create(db, obj_in=template_in, owner_org_id=owner_org_id)

    async def get_schema_template(
        self,
        db: AsyncSession,
        *,
        template_id: uuid.UUID,
        owner_org_id: Optional[uuid.UUID] = None
    ) -> models.SchemaTemplate:
        """Retrieves a schema template by ID."""
        template = await self.schema_template_dao.get(db, id=template_id)
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Schema Template {template_id} not found.")
        if owner_org_id and (template.owner_org_id != owner_org_id or template.is_system_entity):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Schema Template {template_id} not found in organization {owner_org_id}.")
        return template

    async def list_schema_templates(
        self,
        db: AsyncSession,
        *,
        owner_org_id: uuid.UUID,
        include_system: bool = True,
        skip: int = 0,
        limit: int = 100
    ) -> List[models.SchemaTemplate]:
        """Lists schema templates accessible in an organization context."""
        org_templates_seq = await self.schema_template_dao.get_multi_by_org(db, owner_org_id=owner_org_id, skip=skip, limit=limit)
        org_templates = list(org_templates_seq)
        system_templates = []
        if include_system:
            system_templates_seq = await self.schema_template_dao.get_multi_system(db, skip=skip, limit=limit)
            system_templates = list(system_templates_seq)
        return org_templates + system_templates


    async def update_schema_template(
        self,
        db: AsyncSession,
        *,
        template: models.SchemaTemplate, # Fetched object
        template_update: schemas.SchemaTemplateUpdate,
        user: User
    ) -> models.SchemaTemplate:
        """Updates an organization-specific schema template."""
        if template.is_system_entity:
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System schema templates cannot be updated.")

        new_name = template_update.name or template.name
        new_version = template_update.version or template.version
        if new_name != template.name or new_version != template.version:
            existing = await self.schema_template_dao.get_by_name_version(
                db, name=new_name, version=new_version, owner_org_id=template.owner_org_id
            )
            if existing and existing.id != template.id:
                 raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Schema template '{new_name}' version '{new_version}' already exists."
                )
        # TODO: Validate schema_definition if updated
        return await self.schema_template_dao.update(db, db_obj=template, obj_in=template_update)

    async def delete_schema_template(
        self,
        db: AsyncSession,
        *,
        template: models.SchemaTemplate, # Fetched object
        user: User  # TODO: maintain delete logs for auditing later!
    ) -> bool:
        """Deletes an organization-specific schema template."""
        if template.is_system_entity:
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System schema templates cannot be deleted.")
        deleted = await self.schema_template_dao.remove_by_id_and_org(db, id=template.id, owner_org_id=template.owner_org_id)
        return deleted is not None

    async def search_workflows(
        self,
        db: AsyncSession,
        *,
        name: str,
        version_tag: Optional[str] = None,
        owner_org_id: uuid.UUID,
        include_public: bool = True,
        include_system_entities: bool = False,
        include_public_system_entities: bool = False,
        user: User,
        sort_by: schemas.SearchSortBy = schemas.SearchSortBy.CREATED_AT,
        sort_order: schemas.SortOrder = schemas.SortOrder.DESC
    ) -> List[models.Workflow]:
        """
        Search for workflows by name and optional version_tag.
        
        Returns workflows from:
        - The active organization matching name/version_tag
        - Public workflows matching name/version_tag (if include_public=True)
        - System workflows matching name/version_tag (if include_system_entities=True and user is superuser)
        
        Args:
            db: Database session
            name: Name of the workflow to search for
            version_tag: Optional version tag to filter by
            owner_org_id: Organization ID context for the search
            include_public: Whether to include public workflows
            include_system_entities: Whether to include system entities (superuser only)
            user: User performing the search
            sort_by: Field to sort by
            sort_order: Sort order ('asc' or 'desc')
            
        Returns:
            List of matching workflow objects
        """
        # Check superuser permission for system entities
        if include_system_entities and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Only superusers can access non-public system workflows"
            )
        
        # Use the generic search method from the DAO
        results = await self.workflow_dao.search_by_name_version(
            db=db,
            name=name,
            version=version_tag,
            version_field="version_tag",
            owner_org_id=owner_org_id,
            include_public=include_public,
            include_system_entities=include_system_entities,
            include_public_system_entities=include_public_system_entities,
            is_superuser=user.is_superuser,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        return list(results)

    async def search_prompt_templates(
        self,
        db: AsyncSession,
        *,
        name: str,
        version: Optional[str] = None,
        owner_org_id: uuid.UUID,
        include_public: bool = True,
        include_system_entities: bool = False,
        include_public_system_entities: bool = False,
        user: User,
        sort_by: schemas.SearchSortBy = schemas.SearchSortBy.CREATED_AT,
        sort_order: schemas.SortOrder = schemas.SortOrder.DESC
    ) -> List[models.PromptTemplate]:
        """
        Search for prompt templates by name and optional version.
        
        Returns prompt templates from:
        - The active organization matching name/version
        - Public prompt templates matching name/version (if include_public=True)
        - System prompt templates matching name/version (if include_system_entities=True and user is superuser)
        
        Args:
            db: Database session
            name: Name of the prompt template to search for
            version: Optional version to filter by
            owner_org_id: Organization ID context for the search
            include_public: Whether to include public templates
            include_system_entities: Whether to include system entities (superuser only)
            include_public_system_entities: Whether to include public system entities (superuser only)
            user: User performing the search
            sort_by: Field to sort by
            sort_order: Sort order ('asc' or 'desc')
            
        Returns:
            List of matching prompt template objects
        """
        # Check superuser permission for system entities
        if include_system_entities and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Only superusers can access non-public system prompt templates"
            )
        
        # Use the generic search method from the DAO
        results = await self.prompt_template_dao.search_by_name_version(
            db=db,
            name=name,
            version=version,
            version_field="version",
            owner_org_id=owner_org_id,
            include_public=include_public,
            include_system_entities=include_system_entities,
            include_public_system_entities=include_public_system_entities,
            is_superuser=user.is_superuser,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        return list(results)

    async def search_schema_templates(
        self,
        db: AsyncSession,
        *,
        name: str,
        version: Optional[str] = None,
        owner_org_id: uuid.UUID,
        include_public: bool = True,
        include_system_entities: bool = False,
        include_public_system_entities: bool = False,
        user: User,
        sort_by: schemas.SearchSortBy = schemas.SearchSortBy.CREATED_AT,
        sort_order: schemas.SortOrder = schemas.SortOrder.DESC
    ) -> List[models.SchemaTemplate]:
        """
        Search for schema templates by name and optional version.
        
        Returns schema templates from:
        - The active organization matching name/version
        - Public schema templates matching name/version (if include_public=True)
        - System schema templates matching name/version (if include_system_entities=True and user is superuser)
        
        Args:
            db: Database session
            name: Name of the schema template to search for
            version: Optional version to filter by
            owner_org_id: Organization ID context for the search
            include_public: Whether to include public templates
            include_system_entities: Whether to include system entities (superuser only)
            include_public_system_entities: Whether to include public system entities (superuser only)
            user: User performing the search
            sort_by: Field to sort by
            sort_order: Sort order ('asc' or 'desc')
            
        Returns:
            List of matching schema template objects
        """
        # Check superuser permission for system entities
        if include_system_entities and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Only superusers can access non-public system schema templates directly."
            )
        
        # Use the generic search method from the DAO
        results = await self.schema_template_dao.search_by_name_version(
            db=db,
            name=name,
            version=version,
            version_field="version",
            owner_org_id=owner_org_id,
            include_public=include_public,
            include_system_entities=include_system_entities,
            include_public_system_entities=include_public_system_entities,
            is_superuser=user.is_superuser,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        return list(results)

    # --- User Notification Operations --- #

    async def create_user_notification(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        notification_type: NotificationType,
        message: Dict[str, Any],
        related_run_id: Optional[uuid.UUID] = None
    ) -> models.UserNotification:
        """Creates a user notification."""
        # DAO handles creation
        notification = await self.user_notification_dao.create(
            db,
            user_id=user_id,
            org_id=org_id,
            notification_type=notification_type,
            message=message,
            related_run_id=related_run_id
        )
        # TODO: Trigger WebSocket push notification here or in a separate consumer
        logger.info(f"INFO: Created notification {notification.id} for user {user_id}")
        # Example: await self.websocket_manager.send_notification(user_id, notification)
        return notification

    async def list_user_notifications(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        filters: schemas.NotificationListQuery, # Use schema for filters/sort
        skip: int = 0,
        limit: int = 20 # Keep specific default for notifications
    ) -> List[models.UserNotification]:
        """Lists notifications for a user within an organization."""
        # DAO handles filtering/sorting based on parameters
        notifications = await self.user_notification_dao.get_multi_by_user(
            db,
            user_id=user_id,
            org_id=org_id,
            is_read=filters.is_read,
            skip=skip,
            limit=limit,
            sort_by=filters.sort_by,
            sort_order=filters.sort_order
        )
        return list(notifications) # Ensure list return type

    async def mark_notification_read(
        self,
        db: AsyncSession,
        *,
        notification_id: uuid.UUID,
        user_id: uuid.UUID # User performing the action
    ) -> models.UserNotification:
        """Marks a specific notification as read."""
        # DAO's mark_as_read checks ownership and returns updated object or None
        notification = await self.user_notification_dao.mark_as_read(db, id=notification_id, user_id=user_id)
        if not notification:
             # If DAO returned None, it means it wasn't found, didn't belong to user, or was already read.
             # We need to fetch it again to check existence/ownership or return 404.
             existing = await self.user_notification_dao.get(db, id=notification_id)
             if not existing or existing.user_id != user_id:
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found or access denied")
             # If it exists but wasn't updated, it was likely already read. Return current state.
             return existing
        # If DAO returned the updated object, return it.
        return notification

    async def mark_all_notifications_read(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID
    ) -> int:
        """Marks all notifications as read for a user in an organization."""
        # DAO returns the count of updated notifications
        return await self.user_notification_dao.mark_all_as_read(db, user_id=user_id, org_id=org_id)

    async def count_unread_notifications(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID
    ) -> int:
        """Counts unread notifications for a user in an organization."""
        # DAO returns the count
        return await self.user_notification_dao.count_unread_by_user(db, user_id=user_id, org_id=org_id)

    async def get_notifications_for_run( # Keep this specific method
        self,
        db: AsyncSession,
        *,
        run_id: uuid.UUID,
        user_id: uuid.UUID # User context for permission is implicit
    ) -> List[models.UserNotification]:
        """Gets all notifications associated with a specific workflow run for a user."""
        # DAO fetches notifications linked to the run and user
        notifications = await self.user_notification_dao.get_by_run_and_user(
            db, related_run_id=run_id, user_id=user_id
        )
        return list(notifications) # Ensure list return type

    # --- HITL Job Operations --- #

    async def create_hitl_job( # This is likely called internally by worker, not exposed via API
        self,
        db: AsyncSession,
        *,
        requesting_run_id: uuid.UUID,
        org_id: uuid.UUID,
        request_details: Dict[str, Any],
        assigned_user_id: Optional[uuid.UUID] = None,
        response_schema: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None
    ) -> models.HITLJob:
        """
        Creates a new HITL job, typically called by the execution engine/workflow node.
        Also creates a corresponding user notification.
        Assumes the calling context (worker) has validated the run state.
        """
        # Minimal validation here, main checks assumed done by worker
        run = await self.workflow_run_dao.get(db, id=requesting_run_id)
        if not run:
             # Log error, but might proceed if called by trusted internal process
             logger.error(f"ERROR: Cannot create HITL job, requesting run {requesting_run_id} not found.")
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requesting run not found.")
        if run.owner_org_id != org_id:
             logger.error(f"ERROR: Org mismatch for HITL job. Run Org: {run.owner_org_id}, Request Org: {org_id}")
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization mismatch for HITL job")
        if run.status != WorkflowRunStatus.WAITING_HITL:
             logger.warning(f"Creating HITL job for run {requesting_run_id} not in WAITING_HITL state (current: {run.status}).")
             # Decide whether to enforce WAITING_HITL state strictly

        # Create the HITL job using DAO
        hitl_job = await self.hitl_job_dao.create(
            db,
            requesting_run_id=requesting_run_id,
            org_id=org_id,
            request_details=request_details,
            assigned_user_id=assigned_user_id,
            response_schema=response_schema,
            expires_at=expires_at,
            status=HITLJobStatus.PENDING # Ensure it starts as pending
        )

        # Create a notification for the assigned user
        if assigned_user_id:
            await self.create_user_notification(
                db,
                user_id=assigned_user_id,
                org_id=org_id,
                notification_type=NotificationType.HITL_REQUESTED,
                message={ # Construct meaningful message
                    "summary": f"Action required for workflow run {requesting_run_id}",
                    "hitl_job_id": str(hitl_job.id),
                    "request_details": request_details # Include details for notification display
                },
                related_run_id=requesting_run_id
            )
        # else: Handle notification for unassigned jobs? E.g., notify org admins?

        return hitl_job

    async def respond_to_hitl_job(
        self,
        db: AsyncSession,
        *,
        job: models.HITLJob, # Fetched job object from dependency (checks org, accessibility)
        active_org_id: uuid.UUID,
        response_data: Dict[str, Any],
        user: User # User performing the action
    ) -> models.HITLJob:
        """
        Submits a response to a pending HITL job, validates response,
        and triggers workflow resumption.
        """
        # Dependency get_hitl_job_for_user has already checked org and accessibility

        if job.status != HITLJobStatus.PENDING:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="HITL job is not pending response.")

        # 1. Validate response_data against job.response_schema if it exists
        if job.response_schema:
             try:
                # Placeholder for actual schema validation (e.g., using jsonschema)
                # jsonschema.validate(instance=response_data, schema=job.response_schema)
                logger.info(f"INFO: Skipping HITL response schema validation for job {job.id}")
             except Exception as schema_error: # Catch specific validation error type
                 # Log properly
                 logger.error(f"ERROR: HITL response schema validation failed for job {job.id}: {schema_error}")
                 raise HTTPException(
                     status_code=status.HTTP_400_BAD_REQUEST,
                     detail=f"Response data validation failed: {schema_error}"
                 )

        # 2. Update the job response in the database using DAO
        # DAO handles setting status to RESPONDED and responded_at
        updated_job = await self.hitl_job_dao.update_response(
            db, 
            id=job.id,
            response_data=response_data, 
            user_id=user.id # Record who responded
        )
        
        if not updated_job:
            # Should not happen if checks above pass, but handle defensively
            # Log error
            logger.error(f"ERROR: Failed to update HITL job response in DAO for job {job.id}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update HITL job response")

        # 3. Trigger workflow resumption via the worker
        try:
            # Fetch the run to get necessary details
            run = await self.workflow_run_dao.get(db, id=job.requesting_run_id)
            if not run:
                 # Log error
                 logger.error(f"ERROR: Associated workflow run {job.requesting_run_id} not found for HITL job {job.id}")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated workflow run not found.")
            # Fetch the workflow to get the schema
            workflow = await self.workflow_dao.get(db, id=run.workflow_id)
            if not workflow:
                # Log error
                logger.error(f"ERROR: Associated workflow {run.workflow_id} not found for run {run.id}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated workflow definition not found.")

            
            effective_graph_schema = workflow.graph_config

            if run.applied_workflow_config_overrides:
                override_ids = run.applied_workflow_config_overrides.split(",")
                if override_ids:
                    overrides = None
                    try:
                        overrides = await self.workflow_config_override_dao.get_overrides_by_ids(
                            db=db,
                            override_ids=override_ids
                        )
                    except Exception as e:
                        logger.error(f"ERROR: Failed to get overrides for run {run.id}: {e}")
                        # raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get overrides for run")
                    if overrides:
                        try:
                            effective_graph_schema = await self.apply_list_of_overrides(
                                overrides=overrides,
                                base_graph_schema=workflow.graph_config,
                                workflow_id=workflow.id
                            )
                        except Exception as e:
                            logger.error(f"ERROR: Failed to apply overrides for run {run.id}: {e}")
                            # raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to apply overrides for run")
            
            # Call the worker trigger function
            flow_run: FlowRun = await trigger_workflow_run(
                workflow_id=run.workflow_id,
                owner_org_id=run.owner_org_id,
                triggered_by_user_id=run.triggered_by_user_id, # Original triggerer
                inputs=response_data, # Pass HITL response as input for resumption node
                run_id=run.id,
                thread_id=run.thread_id, # Use existing thread_id for checkpointing
                graph_schema=effective_graph_schema, # Pass the workflow schema
                resume_after_hitl=True, # Indicate this is a resumption
                prefect_run_ids=run.prefect_run_ids # Pass the prefect run_id if provided
            )
            run = await self.workflow_run_dao.update(
                db,
                db_obj=run,
                obj_in={
                    "prefect_run_ids": ",".join([run.prefect_run_ids, str(flow_run.id)]) if run.prefect_run_ids else str(flow_run.id)
                }
            )
            logger.info(f"INFO: Triggered workflow resumption for run {run.id} after HITL response for job {job.id}.")
        except Exception as e:
            # Log error, but don't necessarily fail the HITL response itself
            # Log properly with traceback
            logger.error(f"ERROR: Failed to trigger workflow resumption for run {job.requesting_run_id} after HITL job {job.id} response: {e}")
            # Consider creating a system notification/alert about the resumption failure

        return updated_job # Return the updated job object

    async def list_hitl_jobs(
        self,
        db: AsyncSession,
        *,
        owner_org_id: uuid.UUID, # For authorization context
        user: User, # For filtering by 'me'
        filters: schemas.HITLJobListQuery, # Use schema for filters
        skip: int = 0,
        limit: int = 100
    ) -> List[models.HITLJob]:
        """Lists HITL jobs based on provided filters, applying permission logic."""
        filter_dict = filters.model_dump(exclude_unset=True) if filters else {}

        # Translate 'me' to current user ID if used in filter
        if filter_dict.get("assigned_user_id") == "me":
            filter_dict["assigned_user_id"] = user.id

        # Apply permission-based filtering
        if not user.is_superuser:
             # Non-superusers see jobs in their org that are assigned to them OR unassigned
             filter_dict["user_accessible_id"] = user.id
             filter_dict["org_id"] = owner_org_id # Enforce org boundary
             # Remove potentially conflicting owner_org_id from filters if set
             filter_dict.pop("owner_org_id", None)
        elif filters.owner_org_id: # Superuser can filter by a specific org ID if provided
             filter_dict["org_id"] = filters.owner_org_id
             # Remove user_accessible_id if superuser is filtering by org
             filter_dict.pop("user_accessible_id", None)
        # If superuser and no org_id filter, list across all orgs (no org_id in filter_dict)

        # Remove pagination/custom filter keys before passing to DAO
        filter_dict.pop("skip", None)
        filter_dict.pop("limit", None)
        filter_dict.pop("owner_org_id", None) # Already handled above

        # Handle boolean flags like pending_only, exclude_cancelled within the service or DAO
        # Using DAO's _build_hitl_filters which handles these flags
        if filters.pending_only:
            filter_dict["pending_only"] = True
        if filters.exclude_cancelled:
             filter_dict["exclude_cancelled"] = True

        # Fetch using the DAO's filtered method
        jobs = await self.hitl_job_dao.get_multi_filtered(
            db, filters=filter_dict, skip=skip, limit=limit
            # Pass sorting if implemented in DAO/query schema
        )
        return list(jobs) # Ensure list return type

    async def get_hitl_job(
        self,
        db: AsyncSession,
        *,
        job: models.HITLJob, # Fetched from dependency (permission checked)
        user: User # For context
    ) -> models.HITLJob:
        """Retrieves a specific HITL job (permissions checked by dependency)."""
        # Dependency get_hitl_job_for_user handles fetching and access checks
        return job

    async def cancel_hitl_job(
        self,
        db: AsyncSession,
        *,
        job: models.HITLJob, # Fetched job object from dependency (checks org, accessibility)
        user: User # User performing the action
    ) -> models.HITLJob:
        """Cancels a pending HITL job."""
        # Dependency get_hitl_job_for_user has already checked org and accessibility

        if job.status != HITLJobStatus.PENDING:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending HITL jobs can be cancelled.")

        # Update status to CANCELLED using DAO
        updated_job = await self.hitl_job_dao.update_status(
            db,
            id=job.id,
            status=HITLJobStatus.CANCELLED
        )

        if not updated_job:
             # Log error
             logger.error(f"ERROR: Failed to update HITL job status to cancelled for job {job.id}")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update HITL job status to cancelled.")

        # TODO: Optionally, notify the workflow run?
        # If the workflow is WAITING_HITL, cancelling the job might imply failing the run?
        # Or maybe the workflow has logic to handle a cancelled HITL request.
        # This depends on the desired workflow behavior.
        logger.info(f"INFO: Cancelled HITL job {job.id}. Workflow run {job.requesting_run_id} may need manual handling or has logic to proceed.")

        return updated_job

    # --- WorkflowConfigOverride Operations --- #

    async def create_workflow_config_override(
        self,
        db: AsyncSession,
        *,
        override_in: schemas.WorkflowConfigOverrideCreate,
        user: User,
        active_org_id: Optional[uuid.UUID] = None
    ) -> models.WorkflowConfigOverride:
        """
        Creates a new workflow configuration override.
        
        If is_system_entity is True, ensures the user is a superuser.
        If user_id is provided, ensures it matches the requesting user or the user is a superuser.
        Validates the override_graph_schema against a target workflow if specified.
        
        Args:
            db: Database session
            override_in: The override configuration data
            user: The user creating the override
            active_org_id: Optional organization context for permission checks.
            
        Returns:
            The created WorkflowConfigOverride
            
        Raises:
            HTTPException: If the user lacks permissions or data validation fails
        """
        # Perform permission checks
        if override_in.is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can create system-wide overrides"
            )
            
        if override_in.user_id and override_in.user_id != user.id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot create overrides for other users"
            )
        if override_in.org_id and override_in.org_id != active_org_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot create overrides for other organizations"
            )

        if not override_in.override_graph_schema:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Override graph schema is required"
            )
            
        # If no user_id specified, use the current user's ID for user-specific overrides
        user_id = override_in.user_id
        if (not override_in.is_system_entity) and (not override_in.org_id) and (not override_in.user_id):
            user_id = user.id
            
        base_workflow_to_validate_against: Optional[models.Workflow] = None
        
        # If workflow_id is provided, verify it exists
        if override_in.workflow_id:
            workflow = await self.workflow_dao.get(db, id=override_in.workflow_id)
            if not workflow:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Workflow with ID {override_in.workflow_id} not found"
                )
            base_workflow_to_validate_against = workflow
        elif override_in.workflow_name:
            # TODO: potentially sort by OWNED WORKFLOWS!
            workflows = await self.workflow_dao.search_by_name_version(db, 
                name=override_in.workflow_name, version=override_in.workflow_version, version_field="version_tag",
                owner_org_id=active_org_id,
                include_public=True,
                include_system_entities=user.is_superuser,
                include_public_system_entities=True,
                is_superuser=user.is_superuser,
            )
            if not workflows:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Target workflow with name '{override_in.workflow_name}' (version: {override_in.workflow_version or 'any'}) not found for validation."
                )
            base_workflow_to_validate_against = workflows[0] # Validate against the first match
            logger.info(f"Found {len(workflows)} matching workflows for '{override_in.workflow_name}'. Validating override against the first: {base_workflow_to_validate_against.id}")

        # Perform validation if a base workflow is identified and has a graph_config
        if base_workflow_to_validate_against and base_workflow_to_validate_against.graph_config:
            if not self.db_registry:
                logger.warning("DBRegistry not available in WorkflowService. Skipping override schema validation.")
            else:
                try:
                    base_graph_schema_model = GraphSchema.model_validate(base_workflow_to_validate_against.graph_config)
                    
                    logger.info(f"Attempting to validate override schema against workflow '{base_workflow_to_validate_against.name}' (ID: {base_workflow_to_validate_against.id})")
                    # The override_in.override_graph_schema is a Dict[str, Any] which should conform to GraphOverridePayload
                    await apply_graph_override(
                        base_graph_schema=base_graph_schema_model,
                        override_payload_dict=override_in.override_graph_schema, # This is the new override's schema payload
                        validate_schema=True, # This will trigger full validation including node configs
                        db_registry=self.db_registry
                    )
                    logger.info(f"Validation successful for override against workflow '{base_workflow_to_validate_against.name}'.")
                except ValueError as e:
                    logger.error(f"Validation of override schema failed: {e}", exc_info=True)
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Override graph schema validation failed: {e}"
                    )
                except Exception as e: 
                    logger.error(f"Unexpected error during override schema validation: {e}", exc_info=True)
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Unexpected error during override schema validation: {str(e)}"
                    )
        elif (override_in.workflow_id or override_in.workflow_name):
             logger.warning(f"Target workflow for override validation not found or has no graph_config. Override will be created without pre-validation against a base schema.")
            
        # Convert Pydantic model to dict for DAO
        try:
            override_data = override_in.model_dump(exclude_unset=True)
        except AttributeError:
            override_data = override_in.dict(exclude_unset=True)
            
        # Remove keys that are passed separately to DAO
        workflow_id = override_data.pop("workflow_id", None)
        workflow_name = override_data.pop("workflow_name", None) 
        workflow_version = override_data.pop("workflow_version", None)
        override_graph_schema = override_data.pop("override_graph_schema", {})
        is_system_entity = override_data.pop("is_system_entity", False)
        org_id_from_data = override_data.pop("org_id", None)
        # user_id_from_data = override_data.pop("user_id", None)
        is_active = override_data.pop("is_active", True)
        description = override_data.pop("description", None)
        tag = override_data.pop("tag", None)
        
        # Create override with DAO
        return await self.workflow_config_override_dao.create(
            db=db,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            workflow_version=workflow_version,
            override_graph_schema=override_graph_schema,
            is_system_entity=is_system_entity,
            user_id=user_id,
            org_id=org_id_from_data,
            is_active=is_active,
            description=description,
            tag=tag
        )

    async def update_workflow_config_override(
        self,
        db: AsyncSession,
        *,
        override_id: uuid.UUID,
        override_update: schemas.WorkflowConfigOverrideUpdate,
        user: User,
        active_org_id: Optional[uuid.UUID] = None
    ) -> models.WorkflowConfigOverride:
        """
        Updates an existing workflow configuration override.
        
        Only the override_graph_schema, is_active, description, and tag can be updated.
        If override_graph_schema is updated, it will be validated against the target workflow if applicable.
        
        Args:
            db: Database session
            override_id: The ID of the override to update
            override_update: The update data
            user: The user performing the update
            active_org_id: The active organization context for permission checks.
            
        Returns:
            The updated WorkflowConfigOverride
            
        Raises:
            HTTPException: If the override doesn't exist or user lacks permissions or validation fails.
        """
        # Get the existing override
        existing_override = await self.workflow_config_override_dao.get(db, id=override_id)
        if not existing_override:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow config override with ID {override_id} not found"
            )
            
        # Check permissions
        if existing_override.is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can update system-wide overrides"
            )
            
        if existing_override.user_id and existing_override.user_id != user.id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update overrides belonging to other users"
            )

        if existing_override.org_id and existing_override.org_id != active_org_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update overrides belonging to other organizations"
            )

        # Validate new override_graph_schema if provided
        if override_update.override_graph_schema:
            base_workflow_to_validate_against: Optional[models.Workflow] = None
            if existing_override.workflow_id:
                workflow = await self.workflow_dao.get(db, id=existing_override.workflow_id)
                if not workflow:
                    logger.warning(f"Target workflow ID {existing_override.workflow_id} for override {override_id} not found. Skipping schema validation for update.")
                else:
                    base_workflow_to_validate_against = workflow
            elif existing_override.workflow_name:
                context_org_for_search = active_org_id # Similar to create
                if not context_org_for_search and not user.is_superuser:
                     logger.warning(f"Org context required to search for workflow by name for override {override_id}. Skipping schema validation for update.")
                else:
                    workflows = await self.workflow_dao.search_by_name_version(
                        db,
                        name=existing_override.workflow_name,
                        version=existing_override.workflow_version,
                        version_field="version_tag",
                        owner_org_id=context_org_for_search,
                        include_public=True,
                        include_system_entities=user.is_superuser,
                        include_public_system_entities=True,
                        is_superuser=user.is_superuser,
                    )
                    if not workflows:
                        logger.warning(f"Target workflow name '{existing_override.workflow_name}' for override {override_id} not found. Skipping schema validation for update.")
                    else:
                        base_workflow_to_validate_against = workflows[0]
                        logger.info(f"Found {len(workflows)} matching workflows for '{existing_override.workflow_name}' for override {override_id}. Validating updated override schema against the first: {base_workflow_to_validate_against.id}")
            
            if base_workflow_to_validate_against and base_workflow_to_validate_against.graph_config:
                if not self.db_registry:
                    logger.warning(f"DBRegistry not available in WorkflowService. Skipping override schema validation for update of override {override_id}.")
                else:
                    try:
                        base_graph_schema_model = GraphSchema.model_validate(base_workflow_to_validate_against.graph_config)
                        logger.info(f"Attempting to validate updated override schema for override {override_id} against workflow '{base_workflow_to_validate_against.name}' (ID: {base_workflow_to_validate_against.id})")
                        
                        # The override_update.override_graph_schema is a Dict[str, Any]
                        await apply_graph_override(
                            base_graph_schema=base_graph_schema_model,
                            override_payload_dict=override_update.override_graph_schema, # This is the new override's schema payload from the update
                            validate_schema=True,
                            db_registry=self.db_registry
                        )
                        logger.info(f"Validation successful for updated override schema for override {override_id} against workflow '{base_workflow_to_validate_against.name}'.")
                    except ValueError as e:
                        logger.error(f"Validation of updated override schema for override {override_id} failed: {e}", exc_info=True)
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Updated override graph schema validation failed: {e}"
                        )
                    except Exception as e:
                        logger.error(f"Unexpected error during updated override schema validation for override {override_id}: {e}", exc_info=True)
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Unexpected error during updated override schema validation: {str(e)}"
                        )
            elif override_update.override_graph_schema and (existing_override.workflow_id or existing_override.workflow_name):
                 logger.warning(f"Target workflow for override {override_id} validation not found or has no graph_config. Override will be updated without pre-validation against a base schema.")

            
        # Convert Pydantic model to dict for DAO
        update_data = override_update.model_dump(exclude_unset=True)
            
        # Extract fields for DAO
        override_graph_schema = update_data.get("override_graph_schema")
        is_active = update_data.get("is_active")
        description = update_data.get("description")
        tag = update_data.get("tag")
        
        # Update the override
        return await self.workflow_config_override_dao.update(
            db=db,
            override_id=override_id,
            override_graph_schema=override_graph_schema,
            is_active=is_active,
            description=description,
            tag=tag
        )

    async def get_workflow_config_override(
        self,
        db: AsyncSession,
        *,
        override_id: uuid.UUID,
        user: User
    ) -> models.WorkflowConfigOverride:
        """
        Retrieves a workflow configuration override by ID with permission checks.
        
        Args:
            db: Database session
            override_id: The ID of the override to retrieve
            user: The requesting user
            
        Returns:
            The WorkflowConfigOverride
            
        Raises:
            HTTPException: If the override doesn't exist or user lacks permissions
        """
        override = await self.workflow_config_override_dao.get(db, id=override_id)
        if not override:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow config override with ID {override_id} not found"
            )
            
        # Check permissions
        if override.is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can access system-wide overrides"
            )
            
        if override.user_id and override.user_id != user.id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access overrides belonging to other users"
            )
            
        return override

    async def delete_workflow_config_override(
        self,
        db: AsyncSession,
        *,
        override_id: uuid.UUID,
        user: User,
        active_org_id: Optional[uuid.UUID] = None
    ) -> bool:
        """
        Deletes a workflow configuration override.
        
        Args:
            db: Database session
            override_id: The ID of the override to delete
            user: The requesting user
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            HTTPException: If the override doesn't exist or user lacks permissions
        """
        override = await self.workflow_config_override_dao.get(db, id=override_id)
        if not override:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow config override with ID {override_id} not found"
            )
            
        # Check permissions
        if override.is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can delete system-wide overrides"
            )
            
        if override.user_id and override.user_id != user.id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete overrides belonging to other users"
            )
        
        if override.org_id and override.org_id != active_org_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete overrides belonging to other organizations"
            )
            
        # Delete the override
        deleted = await self.workflow_config_override_dao.remove(db, id=override_id)
        return deleted is not None

    async def list_user_overrides(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        active_org_id: Optional[uuid.UUID] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
        requesting_user: User
    ) -> List[models.WorkflowConfigOverride]:
        """
        Lists workflow configuration overrides for a specific user.
        
        Args:
            db: Database session
            user_id: The ID of the user whose overrides to list
            active_org_id: Optional organization context
            is_active: If provided, filter by active status
            skip: Number of items to skip
            limit: Maximum number of items to return
            requesting_user: The user making the request
            
        Returns:
            List of WorkflowConfigOverride objects for the specified user
            
        Raises:
            HTTPException: If the requesting user doesn't have permission
        """
        # Permission check - users can only see their own overrides unless superuser
        if user_id != requesting_user.id and not requesting_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot list overrides belonging to other users"
            )
            
        # Get the overrides
        overrides = await self.workflow_config_override_dao.get_user_overrides(
            db=db,
            user_id=user_id,
            org_id=active_org_id,
            is_active=is_active
        )
        
        # Apply pagination manually
        paginated_overrides = list(overrides)[skip:skip+limit]
        return paginated_overrides
        
    async def list_org_overrides(
        self,
        db: AsyncSession,
        *,
        active_org_id: uuid.UUID,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
        requesting_user: User
    ) -> List[models.WorkflowConfigOverride]:
        """
        Lists workflow configuration overrides for a specific organization.
        
        Args:
            db: Database session
            org_id: The ID of the organization whose overrides to list
            is_active: If provided, filter by active status
            skip: Number of items to skip
            limit: Maximum number of items to return
            requesting_user: The user making the request
            
        Returns:
            List of WorkflowConfigOverride objects for the specified organization
            
        Raises:
            HTTPException: If the requesting user doesn't have permission
        """
        
        # Get the overrides
        overrides = await self.workflow_config_override_dao.get_org_overrides(
            db=db,
            org_id=active_org_id,
            is_active=is_active
        )
        
        # Apply pagination manually
        paginated_overrides = list(overrides)[skip:skip+limit]
        return paginated_overrides
        
    async def list_system_overrides(
        self,
        db: AsyncSession,
        *,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
        requesting_user: User
    ) -> List[models.WorkflowConfigOverride]:
        """
        Lists system-wide workflow configuration overrides.
        
        Args:
            db: Database session
            is_active: If provided, filter by active status
            skip: Number of items to skip
            limit: Maximum number of items to return
            requesting_user: The user making the request
            
        Returns:
            List of system-wide WorkflowConfigOverride objects
            
        Raises:
            HTTPException: If the requesting user is not a superuser
        """
        # Only superusers can list system overrides
        if not requesting_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can list system-wide overrides"
            )
            
        # Get the overrides
        overrides = await self.workflow_config_override_dao.get_system_overrides(
            db=db,
            is_active=is_active
        )
        
        # Apply pagination manually
        paginated_overrides = list(overrides)[skip:skip+limit]
        return paginated_overrides

    async def apply_list_of_overrides(
        self,
        overrides: List[models.WorkflowConfigOverride],
        base_graph_schema: GraphSchema,
        workflow_id: Optional[uuid.UUID] = None,
    ) -> GraphSchema:
        """
        Applies a list of workflow configuration overrides to a base workflow.
        
        Args:
            overrides: List of WorkflowConfigOverride objects to apply
            base_graph_schema: The base graph schema to apply overrides to
            
        Returns:
            The final effective GraphSchema after applying all overrides

        Raises:
            HTTPException: If the base workflow is not found or has an invalid graph_config
        """
        if not base_graph_schema:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Base workflow not found"
            )
        
        current_graph_schema = base_graph_schema
        for override_idx, override_config in enumerate(overrides):
            if not override_config.override_graph_schema:
                logger.warning(f"Skipping override ID {override_config.id} (Tag: {override_config.tag or 'N/A'}) as its override_graph_schema is empty/None.")
                continue
            
            override_payload = override_config.override_graph_schema
            if not isinstance(override_payload, dict):
                logger.error(f"Override ID {override_config.id} has non-dict override_graph_schema (type: {type(override_payload)}). Skipping application.")
                continue

            logger.info(f"Applying override {override_idx + 1}/{len(overrides)}: ID {override_config.id}, Tag: {override_config.tag or 'N/A'}, User: {override_config.user_id}, Org: {override_config.org_id}, System: {override_config.is_system_entity}")
            try:
                current_graph_schema = await apply_graph_override(
                    base_graph_schema=current_graph_schema,
                    override_payload_dict=override_payload,
                    validate_schema=True, 
                    db_registry=self.db_registry
                )
                # logger.debug(f"Successfully applied override ID {override_config.id}. Intermediate schema: {current_graph_schema.model_dump_json(indent=2)}")
            except ValueError as e:
                logger.error(f"Failed to apply override ID {override_config.id} to workflow {workflow_id}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Error applying configuration override ID {override_config.id} (Tag: {override_config.tag or 'N/A'}): {e}"
                )
            except Exception as e:
                logger.error(f"Unexpected error applying override ID {override_config.id} to workflow {workflow_id}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Unexpected error applying configuration override ID {override_config.id} (Tag: {override_config.tag or 'N/A'}): {str(e)}"
                )
        return current_graph_schema
    

    async def get_workflow_config_with_overrides(
        self,
        db: AsyncSession,
        *,
        workflow_id: uuid.UUID,
        active_org_id: uuid.UUID,
        requesting_user: User,
        include_active: bool = True,
        include_tags: Optional[List[str]] = None,
    ) -> Tuple[List[models.WorkflowConfigOverride], GraphSchema]:
        """
        Retrieves a workflow configuration with all applicable overrides.
        
        Args:
            db: Database session
            workflow_id: The ID of the workflow to retrieve
            requesting_user: The user making the request
            
        Returns:
            The final effective GraphSchema after applying all overrides
            
        Raises:
            HTTPException: If the base workflow is not found or has an invalid graph_config
        """
        workflow = await self.get_workflow(
            db=db,
            user=requesting_user,
            workflow_id=workflow_id,
            owner_org_id=active_org_id,
            include_system_entities=True
        )

        overrides, effective_graph_schema = await self.list_workflow_specific_overrides_and_optional_apply(
            db=db,
            active_org_id=active_org_id,
            base_workflow_to_apply_overrides_to=workflow,
            include_active=include_active,
            include_tags=include_tags,
            requesting_user=requesting_user,
        )

        return overrides, effective_graph_schema
    
    async def list_workflow_specific_overrides_and_optional_apply(
        self,
        db: AsyncSession,
        *,
        workflow_id: Optional[uuid.UUID] = None,
        workflow_name: Optional[str] = None,
        workflow_version: Optional[str] = None,
        include_active: bool = True,
        include_tags: Optional[List[str]] = None,
        active_org_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 100,
        requesting_user: User,
        base_workflow_to_apply_overrides_to: Optional[models.Workflow] = None
    ) -> Tuple[List[models.WorkflowConfigOverride], Optional[GraphSchema]]:
        """
        Lists workflow configuration overrides for a specific workflow.
        
        Args:
            db: Database session
            workflow_id: Optional workflow ID to filter by
            workflow_name: Optional workflow name to filter by
            workflow_version: Optional workflow version to filter by
            include_active: Whether to include active overrides
            include_tags: Optional list of tags to filter by
            active_org_id: The current organization context
            skip: Number of items to skip
            limit: Maximum number of items to return
            requesting_user: The user making the request
            base_workflow_to_apply_overrides_to: Optional base workflow to apply overrides to

        Returns: 
            Tuple[List[WorkflowConfigOverride], Optional[GraphSchema]] containing:
            - List of WorkflowConfigOverride objects for the specified workflow
            - Optional GraphSchema representing the final effective schema after applying overrides
            
        Raises:
            HTTPException: If neither workflow_id nor workflow_name is provided
        """
        if base_workflow_to_apply_overrides_to:
            if workflow_id or workflow_name or workflow_version:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot provide both base_workflow_to_apply_overrides_to and workflow_id, workflow_name, or workflow_version"
                )
            workflow_id = base_workflow_to_apply_overrides_to.id
            workflow_name = base_workflow_to_apply_overrides_to.name
            workflow_version = base_workflow_to_apply_overrides_to.version_tag

        if not workflow_id and not workflow_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either workflow_id or workflow_name must be provided"
            )
            
        # Get all relevant overrides for this workflow
        overrides = await self.workflow_config_override_dao.get_overrides_for_workflow(
            db=db,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            workflow_version=workflow_version,
            user_id=requesting_user.id,
            user_is_superuser=requesting_user.is_superuser,
            org_id=active_org_id,
            include_tags=include_tags,
            include_active=include_active,
            include_system_overrides=True,
            include_global_overrides=True,
            include_org_overrides=True,
            include_user_overrides=True  # Always include user's own overrides
        )


        if base_workflow_to_apply_overrides_to:
            try:
                current_graph_schema = GraphSchema.model_validate(base_workflow_to_apply_overrides_to.graph_config)
            except ValidationError as e:
                logger.error(f"Base workflow {base_workflow_to_apply_overrides_to.id} ('{base_workflow_to_apply_overrides_to.name}') has invalid graph_config: {e}", exc_info=True)
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Base workflow's graph configuration is invalid: {e}")

            if not self.db_registry:
                logger.error("DBRegistry not available in WorkflowService. Cannot apply or validate overrides requiring node template information.")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Service configuration error: DBRegistry not available.")


            if not overrides:
                logger.info(f"No applicable config overrides found for workflow {base_workflow_to_apply_overrides_to.id} ('{base_workflow_to_apply_overrides_to.name}'). Returning base schema.")
                return [], current_graph_schema

            logger.info(f"Applying {len(overrides)} config overrides to workflow {base_workflow_to_apply_overrides_to.id} ('{base_workflow_to_apply_overrides_to.name}').")

            effective_graph_schema = await self.apply_list_of_overrides(
                overrides=overrides,
                base_graph_schema=current_graph_schema,
                workflow_id=base_workflow_to_apply_overrides_to.id
            )
                    
            logger.info(f"Successfully applied all applicable ({len(overrides)}) overrides to workflow {base_workflow_to_apply_overrides_to.id}. Returning final effective schema.")
            return overrides, effective_graph_schema

        # Apply pagination manually
        paginated_overrides = list(overrides)[skip:skip+limit]
        return paginated_overrides, None
        
    async def list_tag_overrides(
        self,
        db: AsyncSession,
        *,
        tag: str,
        is_active: Optional[bool] = None,
        active_org_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 100,
        requesting_user: User
    ) -> List[models.WorkflowConfigOverride]:
        """
        Lists workflow configuration overrides with a specific tag.
        
        Args:
            db: Database session
            tag: The tag to filter by
            is_active: If provided, filter by active status
            active_org_id: The current organization context
            skip: Number of items to skip
            limit: Maximum number of items to return
            requesting_user: The user making the request
            
        Returns:
            List of WorkflowConfigOverride objects with the specified tag
        """
        # Get overrides by tag
        overrides = await self.workflow_config_override_dao.get_overrides_by_tag(
            db=db,
            tag=tag,
            is_active=is_active,
            user_id=requesting_user.id,
            org_id=active_org_id,
            user_is_superuser=requesting_user.is_superuser
        )
        
        # Apply pagination manually
        paginated_overrides = list(overrides)[skip:skip+limit]
        return paginated_overrides

    async def get_all_workflow_config_overrides(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        requesting_user: User
    ) -> List[models.WorkflowConfigOverride]:
        """
        Gets all workflow configuration overrides using the generic get_multi method.
        Only accessible to superusers.
        
        Args:
            db: Database session
            skip: Number of items to skip for pagination
            limit: Maximum number of items to return
            requesting_user: The user making the request
            
        Returns:
            List of all WorkflowConfigOverride objects
            
        Raises:
            HTTPException: If the requesting user is not a superuser
        """
        # Only superusers can access all overrides
        if not requesting_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can list all overrides"
            )
            
        # Use the generic get_multi method from the DAO
        overrides = await self.workflow_config_override_dao.get_multi(
            db=db,
            skip=skip,
            limit=limit
        )
        
        return list(overrides)

    # --- ChatThread methods --- #
    
    async def create_chat_thread(
        self,
        db: AsyncSession,
        *,
        thread_data: schemas.ChatThreadCreate,
        user: User
    ) -> models.ChatThread:
        """
        Create a new chat thread.
        
        Args:
            db: Database session
            thread_data: Data for creating the thread
            user: User creating the thread
            
        Returns:
            The created chat thread
        """
        chat_thread_dao = crud.ChatThreadDAO()
        
        # For non-superusers, always use the current user's ID
        # Superusers can specify a different user_id
        if not user.is_superuser:
            # If user_id is specified and doesn't match current user, raise error
            if thread_data.user_id is not None and thread_data.user_id != user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only superusers can create threads for other users")
            
            # Force use of current user's ID
            user_id = user.id
        else:
            # Superusers can specify user_id or use their own
            user_id = thread_data.user_id if thread_data.user_id else user.id
            
        return await chat_thread_dao.create_thread(db, thread_in=thread_data, user_id=user_id)
    
    async def get_chat_thread(
        self,
        db: AsyncSession,
        *,
        thread_id: uuid.UUID,
        user: User
    ) -> Optional[models.ChatThread]:
        """
        Get a chat thread by ID.
        
        Args:
            db: Database session
            thread_id: ID of the thread to retrieve
            user: User requesting the thread
            
        Returns:
            The chat thread or None if not found
            
        Raises:
            PermissionDeniedError: If user is not the owner and not a superuser
        """
        chat_thread_dao = crud.ChatThreadDAO()
        thread = await chat_thread_dao.get_by_id(db, thread_id=thread_id)
        
        if not thread:
            return None
            
        # Check ownership - allow access if superuser or owner
        if user.is_superuser or thread.user_id == user.id:
            return thread
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to access this chat thread")
    
    async def update_chat_thread(
        self,
        db: AsyncSession,
        *,
        thread_id: uuid.UUID,
        thread_data: schemas.ChatThreadUpdate,
        user: User
    ) -> Optional[models.ChatThread]:
        """
        Update an existing chat thread.
        
        Args:
            db: Database session
            thread_id: ID of the thread to update
            thread_data: New data for the thread
            user: User updating the thread
            
        Returns:
            The updated chat thread or None if not found
            
        Raises:
            PermissionDeniedError: If user is not the owner and not a superuser
        """
        chat_thread_dao = crud.ChatThreadDAO()
        
        # For superusers, allow update without ownership check
        if user.is_superuser:
            return await chat_thread_dao.update_thread(db, thread_id=thread_id, thread_update=thread_data)
        else:
            # For regular users, verify ownership
            return await chat_thread_dao.update_thread(
                db, 
                thread_id=thread_id, 
                thread_update=thread_data,
                user_id=user.id
            )
    
    async def delete_chat_thread(
        self,
        db: AsyncSession,
        *,
        thread_id: uuid.UUID,
        user: User
    ) -> bool:
        """
        Delete a chat thread.
        
        Args:
            db: Database session
            thread_id: ID of the thread to delete
            user: User deleting the thread
            
        Returns:
            True if the thread was deleted, False otherwise
            
        Raises:
            PermissionDeniedError: If user is not the owner and not a superuser
        """
        chat_thread_dao = crud.ChatThreadDAO()
        
        # For superusers, allow deletion without ownership check
        if user.is_superuser:
            deleted_thread = await chat_thread_dao.remove_thread(db, thread_id=thread_id)
        else:
            # For regular users, verify ownership
            deleted_thread = await chat_thread_dao.remove_thread(
                db, 
                thread_id=thread_id,
                user_id=user.id
            )
            
        return deleted_thread is not None
    
    async def list_chat_threads(
        self,
        db: AsyncSession,
        *,
        user: User,
        workflow_name: Optional[str] = None,
        workflow_version: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
        tag: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[models.ChatThread]:
        """
        List chat threads, optionally filtered by workflow, owner, and tag.
        
        Args:
            db: Database session
            user: User requesting the thread list
            workflow_name: Optional name of the workflow to filter by
            workflow_version: Optional version of the workflow to filter by
            user_id: Optional user ID to filter by owner
            tag: Optional tag to filter by
            skip: Number of items to skip for pagination
            limit: Maximum number of items to return
            
        Returns:
            List of chat threads matching the criteria
            
        Raises:
            PermissionDeniedError: If non-superuser tries to view other users' threads
        """
        chat_thread_dao = crud.ChatThreadDAO()
        
        # Non-superusers can only see their own threads
        if not user.is_superuser:
            if user_id is not None and user_id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to access this chat thread"
                )
            
            # Force filter by current user
            user_id = user.id
        
        # Use the comprehensive filtering method which supports all filters including tag
        return await chat_thread_dao.get_multi_filtered(
            db,
            workflow_name=workflow_name,
            workflow_version=workflow_version,
            user_id=user_id,
            tag=tag,
            skip=skip,
            limit=limit
        )


# --- Asset Services --- #

# Asset type registry - mapping asset types to their Pydantic schemas for app_data validation
ASSET_TYPE_REGISTRY: Dict[str, Dict[str, Any]] = {
    # LinkedIn Profile asset type
    schemas.AssetType.LINKEDIN_PROFILE.value: {
        "display_name": "LinkedIn Profile",
        "description": "LinkedIn profile for data extraction and monitoring",
        "app_data_schema": schemas.LinkedInProfileAppData
    },
    schemas.AssetType.BLOG_URL.value: {
        "display_name": "Blog URL",
        "description": "Blog URL for content extraction and monitoring",
        "app_data_schema": schemas.BlogUrlAppData
    }
}


class AssetService:
    """Service layer for managing assets."""
    
    def __init__(
        self,
        asset_dao: crud.AssetDAO,
        user_app_resume_metadata_dao: crud.UserAppResumeMetadataDAO,
        redis_client: Optional['AsyncRedisClient'] = None,
    ):
        """
        Initialize AssetService with required DAOs and optional Redis client.
        
        Args:
            asset_dao: DAO for asset operations
            user_app_resume_metadata_dao: DAO for user app resume metadata operations
            redis_client: Optional Redis client for distributed locking
        """
        self.asset_dao = asset_dao
        self.user_app_resume_metadata_dao = user_app_resume_metadata_dao
        self.redis_client = redis_client
        self.logger = get_logger(__name__)
    
    # --- Asset Type Registry Methods --- #
    
    def get_asset_type_info(self, asset_type: str) -> schemas.AssetTypeInfo:
        """Get information about an asset type including its schema."""
        if asset_type not in ASSET_TYPE_REGISTRY:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset type '{asset_type}' not found"
            )
        
        type_info = ASSET_TYPE_REGISTRY[asset_type]
        schema_class = type_info["app_data_schema"]
        
        # Convert Pydantic schema to JSON schema if it's a Pydantic model
        json_schema = None
        if schema_class and hasattr(schema_class, 'model_json_schema'):
            json_schema = schema_class.model_json_schema()
        
        return schemas.AssetTypeInfo(
            asset_type=asset_type,
            display_name=type_info["display_name"],
            description=type_info["description"],
            app_data_schema=json_schema
        )
    
    def list_asset_types(self) -> List[schemas.AssetTypeInfo]:
        """List all available asset types."""
        result = []
        for asset_type, info in ASSET_TYPE_REGISTRY.items():
            schema_class = info["app_data_schema"]
            
            # Convert Pydantic schema to JSON schema if it's a Pydantic model
            json_schema = None
            if schema_class and hasattr(schema_class, 'model_json_schema'):
                json_schema = schema_class.model_json_schema()
            
            result.append(schemas.AssetTypeInfo(
                asset_type=asset_type,
                display_name=info["display_name"],
                description=info["description"],
                app_data_schema=json_schema
            ))
        
        return result
    
    def validate_asset_app_data(self, asset_type: str, app_data: Optional[Dict[str, Any]]) -> None:
        """Validate app_data against the asset type's schema."""
        if asset_type not in ASSET_TYPE_REGISTRY:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid asset type: {asset_type}"
            )
        
        schema_class = ASSET_TYPE_REGISTRY[asset_type]["app_data_schema"]
        
        # Skip validation if no schema is defined (e.g., for custom assets)
        if schema_class is None:
            return
        
        # Skip validation if app_data is None
        if app_data is None:
            return
        
        try:
            # Use Pydantic model for validation
            if hasattr(schema_class, 'model_validate'):
                schema_class.model_validate(app_data)
            else:
                # Fallback to jsonschema if not a Pydantic model
                validate(instance=app_data, schema=schema_class)
        except ValidationError as e:
            # Pydantic validation error
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid app_data: {str(e)}"
            )
        except Exception as e:
            # Other validation errors
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid app_data for asset type '{asset_type}': {str(e)}"
            )
    
    # --- Asset Data Filtering Methods --- #
    
    def filter_app_data_fields(self, asset: models.Asset, fields: Optional[List[str]] = None) -> models.Asset:
        """
        Filter app_data to include only specified fields.
        
        If fields is None or empty, returns the asset unchanged.
        If fields are specified, creates a new dict with only those fields.
        
        Args:
            asset: The asset model instance
            fields: List of field names to include (supports nested paths with dots)
            
        Returns:
            The asset with filtered app_data
        """
        if not fields or not asset.app_data:
            return asset
        
        # Extract requested fields from app_data
        filtered_data = {}
        
        for field in fields:
            # Support nested field access with dot notation
            parts = field.split('.')
            source = asset.app_data
            target = filtered_data
            
            # Navigate through nested structure
            for i, part in enumerate(parts[:-1]):
                if isinstance(source, dict) and part in source:
                    source = source[part]
                    if part not in target:
                        target[part] = {}
                    target = target[part]
                else:
                    # Field doesn't exist, skip it
                    break
            else:
                # Add the final field if it exists
                if isinstance(source, dict) and parts[-1] in source:
                    target[parts[-1]] = source[parts[-1]]
        
        # Create a new Asset object with filtered app_data
        # This avoids modifying the original SQLAlchemy object
        filtered_asset = models.Asset(
            id=asset.id,
            asset_type=asset.asset_type,
            asset_name=asset.asset_name,
            is_shared=asset.is_shared,
            org_id=asset.org_id,
            managing_user_id=asset.managing_user_id,
            is_active=asset.is_active,
            app_data=filtered_data if filtered_data else None,
            created_at=asset.created_at,
            updated_at=asset.updated_at
        )
        return filtered_asset
    
    def filter_assets_app_data(self, assets: List[models.Asset], fields: Optional[List[str]] = None) -> List[models.Asset]:
        """Filter app_data fields for a list of assets."""
        if not fields:
            return assets
        
        return [self.filter_app_data_fields(asset, fields) for asset in assets]
    
    # --- Asset CRUD Methods --- #
    
    async def create_asset(
        self,
        db: AsyncSession,
        *,
        user: User,
        asset_in: schemas.AssetCreate,
        org_id: Optional[uuid.UUID] = None,
        is_superuser: bool = False
    ) -> models.Asset:
        """Create a new asset."""
        # Determine effective org_id
        effective_org_id = org_id
        if asset_in.org_id and is_superuser:
            effective_org_id = asset_in.org_id
        elif not effective_org_id:
            # Use user's current org if not specified
            effective_org_id = org_id
        
        if not effective_org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization ID must be specified"
            )
        
        # Validate app_data against asset type schema
        self.validate_asset_app_data(asset_in.asset_type, asset_in.app_data)
        
        # Check if asset with same type and name exists in the org
        existing = await self.asset_dao.get_by_type_and_name(
            db,
            org_id=effective_org_id,
            asset_type=asset_in.asset_type,
            asset_name=asset_in.asset_name
        )
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Asset with type '{asset_in.asset_type}' and name '{asset_in.asset_name}' already exists in this organization"
            )
        
        # Determine managing user
        managing_user_id = user.id
        if asset_in.managing_user_id and is_superuser:
            managing_user_id = asset_in.managing_user_id
        elif asset_in.on_behalf_of_user_id and is_superuser:
            managing_user_id = asset_in.on_behalf_of_user_id
        
        # Create the asset
        db_asset = models.Asset(
            asset_type=asset_in.asset_type,
            asset_name=asset_in.asset_name,
            is_shared=asset_in.is_shared,
            is_active=asset_in.is_active,
            app_data=asset_in.app_data,
            org_id=effective_org_id,
            managing_user_id=managing_user_id
        )
        
        db.add(db_asset)
        await db.commit()
        await db.refresh(db_asset)
        
        self.logger.info(f"Created asset {db_asset.id} of type {db_asset.asset_type} for org {effective_org_id}")
        
        return db_asset
    
    async def get_asset(
        self,
        db: AsyncSession,
        *,
        user: User,
        asset_id: uuid.UUID,
        org_id: uuid.UUID,
        is_superuser: bool = False,
        app_data_fields: Optional[List[str]] = None
    ) -> models.Asset:
        """Get an asset by ID, checking permissions."""
        asset = await self.asset_dao.get(db, id=asset_id)
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found"
            )
        
        # Check permissions
        if not is_superuser:
            # Must be in the same org
            if asset.org_id != org_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Asset belongs to a different organization"
                )
            
            # Must be accessible (shared or user is managing user)
            if not asset.is_shared and asset.managing_user_id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to access this asset"
                )
        
        # Filter app_data fields if requested
        if app_data_fields:
            asset = self.filter_app_data_fields(asset, app_data_fields)
        
        return asset
    
    async def update_asset(
        self,
        db: AsyncSession,
        *,
        user: User,
        asset_id: uuid.UUID,
        asset_update: schemas.AssetUpdate,
        org_id: uuid.UUID,
        is_superuser: bool = False,
        is_asset_manage_update: bool = False
    ) -> models.Asset:
        """Update an asset."""
        # Get existing asset
        asset = await self.get_asset(db, user=user, asset_id=asset_id, org_id=org_id, is_superuser=is_superuser)
        
        # Check update permissions
        if (not is_superuser) and (asset.managing_user_id != user.id):
            # Only managing user can update (org-level permission already checked by route)
            if is_asset_manage_update:
                await _check_permissions_for_org(
                    db=db,
                    user_dao=get_user_dao(),
                    user=user,
                    org_id=org_id,
                    required_permissions=[WorkflowPermissions.ORG_MANAGE_ASSETS]
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the managing user can update this asset"
                )
        
        # Validate app_data if being updated
        if asset_update.app_data is not None:
            self.validate_asset_app_data(asset.asset_type, asset_update.app_data)
        
        # Check if name is being changed and would conflict
        if asset_update.asset_name and asset_update.asset_name != asset.asset_name:
            existing = await self.asset_dao.get_by_type_and_name(
                db,
                org_id=asset.org_id,
                asset_type=asset.asset_type,
                asset_name=asset_update.asset_name
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Asset with type '{asset.asset_type}' and name '{asset_update.asset_name}' already exists"
                )
        
        # Update the asset
        updated_asset = await self.asset_dao.update(db, db_obj=asset, obj_in=asset_update)
        
        self.logger.info(f"Updated asset {asset_id}")
        
        return updated_asset
    
    async def update_asset_app_data(
        self,
        db: AsyncSession,
        *,
        user: User,
        asset_id: uuid.UUID,
        app_data_update: schemas.AssetAppDataUpdate,
        org_id: uuid.UUID,
        is_superuser: bool = False
    ) -> models.Asset:
        """Update asset app_data using JSONB operations with distributed locking."""
        # First check permissions without lock
        asset = await self.get_asset(db, user=user, asset_id=asset_id, org_id=org_id, is_superuser=is_superuser)
        
        # Check update permissions
        if not is_superuser:
            # Only managing user can update (org-level permission already checked by route)
            if asset.managing_user_id != user.id and (not asset.is_shared):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the managing user can update this asset"
                )
        
        # For replace operation, validate the new app_data
        if app_data_update.operation == schemas.AssetAppDataOperation.REPLACE:
            self.validate_asset_app_data(asset.asset_type, app_data_update.value)
        
        # Use Redis lock if available to prevent race conditions during concurrent updates
        if self.redis_client:
            lock_key = f"asset:{asset_id}:app_data"
            async with self.redis_client.with_lock(lock_key, timeout=30, ttl=60):
                # Perform the JSONB update within the lock
                success = await self.asset_dao.update_app_data_jsonb(
                    db,
                    asset_id=asset_id,
                    operation=app_data_update.operation,
                    path=app_data_update.path,
                    value=app_data_update.value
                )
        else:
            # No Redis client available, perform update without lock
            self.logger.warning(f"Redis client not available for asset {asset_id}, updating without distributed lock")
            success = await self.asset_dao.update_app_data_jsonb(
                db,
                asset_id=asset_id,
                operation=app_data_update.operation,
                path=app_data_update.path,
                value=app_data_update.value
            )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update asset app_data"
            )
        
        # Fetch and return updated asset
        updated_asset = await self.asset_dao.get(db, id=asset_id)
        
        self.logger.info(f"Updated app_data for asset {asset_id} using operation {app_data_update.operation}")
        
        return updated_asset
    
    async def increment_asset_app_data_field(
        self,
        db: AsyncSession,
        *,
        user: User,
        asset_id: uuid.UUID,
        path: List[str],
        increment: Union[int, float] = 1,
        org_id: uuid.UUID
    ) -> models.Asset:
        """
        Atomically increment a numeric field in asset app_data.
        
        Args:
            db: Database session
            user: User performing the operation
            asset_id: ID of the asset to update
            path: JSON path to the numeric field
            increment: Amount to increment by (default 1), can be int or float
            org_id: Optional organization ID for permission check
            
        Returns:
            Updated asset
            
        Raises:
            HTTPException: If asset not found, user lacks permission, or field is not numeric
        """
        # Get and validate asset (this also checks basic permissions)
        asset = await self.get_asset(db, user=user, asset_id=asset_id, org_id=org_id)
        
        # Check update permissions (only managing user can update)
        if asset.managing_user_id != user.id and (not asset.is_shared) and (not user.is_superuser):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the managing user can update this asset"
            )
        
        # Use Redis lock if available
        lock_key = f"asset:{asset_id}:app_data"
        async with self.redis_client.with_lock(lock_key, timeout=30, ttl=60):
            success = await self.asset_dao.increment_app_data_field(
                db,
                asset_id=asset_id,
                path=path,
                increment=increment
            )
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to increment field at path {path} for asset {asset_id}"
            )
        
        # Return updated asset
        updated_asset = await self.asset_dao.get(db, id=asset_id)
        return updated_asset
    
    async def deactivate_asset(
        self,
        db: AsyncSession,
        *,
        user: User,
        asset_id: uuid.UUID,
        org_id: uuid.UUID,
        is_superuser: bool = False
    ) -> models.Asset:
        """Deactivate an asset (soft delete)."""
        # Use update_asset with is_active=False
        asset_update = schemas.AssetUpdate(is_active=False)
        
        updated_asset = await self.update_asset(
            db,
            user=user,
            asset_id=asset_id,
            asset_update=asset_update,
            org_id=org_id,
            is_superuser=is_superuser,
            is_asset_manage_update=True,
        )
        
        self.logger.info(f"Deactivated asset {asset_id}")
        
        return updated_asset
    
    async def list_accessible_assets(
        self,
        db: AsyncSession,
        *,
        user: User,
        org_id: uuid.UUID,
        asset_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_shared: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
        is_superuser: bool = False,
        app_data_fields: Optional[List[str]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc"
    ) -> List[models.Asset]:
        """List assets accessible to a user within an organization."""
        # For superusers listing a specific org, show all assets
        if is_superuser:
            assets = await self.asset_dao.get_all_org_assets(
                db,
                org_id=org_id,
                asset_type=asset_type,
                is_active=is_active,
                is_shared=is_shared,
                skip=skip,
                limit=limit,
                sort_by=sort_by,
                sort_order=sort_order
            )
        else:
            # For regular users, show only accessible assets
            assets = await self.asset_dao.get_accessible_assets(
                db,
                org_id=org_id,
                user_id=user.id,
                asset_type=asset_type,
                is_active=is_active,
                is_shared=is_shared,
                skip=skip,
                limit=limit,
                sort_by=sort_by,
                sort_order=sort_order
            )
        
        # Filter app_data fields if requested
        if app_data_fields:
            assets = self.filter_assets_app_data(assets, app_data_fields)
        
        return assets
    
    async def list_managed_assets(
        self,
        db: AsyncSession,
        *,
        user: User,
        org_id: Optional[uuid.UUID] = None,
        asset_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        include_all_orgs: bool = False,
        skip: int = 0,
        limit: int = 100,
        is_superuser: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        app_data_fields: Optional[List[str]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc"
    ) -> List[models.Asset]:
        """List all assets managed by a user."""
        # Determine target user
        target_user_id = user.id
        if on_behalf_of_user_id and is_superuser:
            target_user_id = on_behalf_of_user_id
        
        # If include_all_orgs is False and org_id is provided, filter by org
        effective_org_id = None if include_all_orgs else org_id
        
        assets = await self.asset_dao.get_managed_assets(
            db,
            user_id=target_user_id,
            org_id=effective_org_id,
            asset_type=asset_type,
            is_active=is_active,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # Filter app_data fields if requested
        if app_data_fields:
            assets = self.filter_assets_app_data(assets, app_data_fields)
        
        return assets
    
    async def list_all_org_assets(
        self,
        db: AsyncSession,
        *,
        user: User,
        org_id: uuid.UUID,
        asset_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_shared: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
        is_superuser: bool = False,
        app_data_fields: Optional[List[str]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc"
    ) -> List[models.Asset]:
        """List all assets in an organization (requires ORG_DATA_WRITE permission)."""
        # Permission checking is handled by the route dependency
        
        assets = await self.asset_dao.get_all_org_assets(
            db,
            org_id=org_id,
            asset_type=asset_type,
            is_active=is_active,
            is_shared=is_shared,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # Filter app_data fields if requested
        if app_data_fields:
            assets = self.filter_assets_app_data(assets, app_data_fields)
        
        return assets
    
    # --- UserAppResumeMetadata Methods --- #
    
    async def create_user_app_resume_metadata(
        self,
        db: AsyncSession,
        *,
        user: User,
        metadata_in: schemas.UserAppResumeMetadataCreate,
        org_id: Optional[uuid.UUID] = None,
        is_superuser: bool = False
    ) -> models.UserAppResumeMetadata:
        """Create a new user app resume metadata record."""
        # Determine effective org_id and user_id
        effective_org_id = org_id
        if metadata_in.org_id and is_superuser:
            effective_org_id = metadata_in.org_id
        elif not effective_org_id:
            effective_org_id = org_id
        
        if not effective_org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization ID must be specified"
            )
        
        effective_user_id = user.id
        if metadata_in.on_behalf_of_user_id and is_superuser:
            effective_user_id = metadata_in.on_behalf_of_user_id
        
        # Create the metadata record
        db_metadata = await self.user_app_resume_metadata_dao.create(
            db,
            obj_in=metadata_in,
            org_id=effective_org_id,
            user_id=effective_user_id
        )
        
        self.logger.info(f"Created user app resume metadata {db_metadata.id} for user {effective_user_id}")
        
        return db_metadata
    
    async def get_user_app_resume_metadata(
        self,
        db: AsyncSession,
        *,
        user: User,
        metadata_id: uuid.UUID,
        is_superuser: bool = False
    ) -> models.UserAppResumeMetadata:
        """Get a user app resume metadata record by ID."""
        if is_superuser:
            metadata = await self.user_app_resume_metadata_dao.get(db, id=metadata_id)
        else:
            metadata = await self.user_app_resume_metadata_dao.get_by_id_and_user(db, id=metadata_id, user_id=user.id)
        
        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User app resume metadata not found"
            )
        
        return metadata
    
    async def update_user_app_resume_metadata(
        self,
        db: AsyncSession,
        *,
        user: User,
        metadata_id: uuid.UUID,
        metadata_update: schemas.UserAppResumeMetadataUpdate,
        is_superuser: bool = False
    ) -> models.UserAppResumeMetadata:
        """Update a user app resume metadata record with distributed locking."""
        # First check permissions without lock
        metadata = await self.get_user_app_resume_metadata(db, user=user, metadata_id=metadata_id, is_superuser=is_superuser)
        
        # Use Redis lock if available to prevent race conditions during concurrent updates
        async def _perform_update() -> models.UserAppResumeMetadata:
            # Re-fetch metadata inside lock to ensure we have the latest version
            metadata = await self.get_user_app_resume_metadata(db, user=user, metadata_id=metadata_id, is_superuser=is_superuser)
            
            # Validate that update maintains constraints
            # Create a copy of the current object and apply updates to check constraints
            test_obj = {
                "workflow_name": metadata.workflow_name,
                "asset_id": metadata.asset_id,
                "entity_tag": metadata.entity_tag,
                "frontend_stage": metadata.frontend_stage,
                "run_id": metadata.run_id,
                "app_metadata": metadata.app_metadata
            }
            
            # Apply updates
            update_data = metadata_update.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                test_obj[field] = value
            
            # Check constraints
            identifiers = [test_obj["workflow_name"], test_obj["asset_id"], test_obj["entity_tag"], test_obj["frontend_stage"]]
            data_fields = [test_obj["run_id"], test_obj["app_metadata"]]
            
            if not any(field is not None for field in identifiers):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="At least one of workflow_name, asset_id, entity_tag, or frontend_stage must remain after update"
                )
            
            if not any(field is not None for field in data_fields):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="At least one of run_id or app_metadata must remain after update"
                )
            
            # Update the metadata
            return await self.user_app_resume_metadata_dao.update(db, db_obj=metadata, obj_in=metadata_update)
        
        if self.redis_client:
            lock_key = f"user_app_resume_metadata:{metadata_id}"
            async with self.redis_client.with_lock(lock_key, timeout=30, ttl=60):
                updated_metadata = await _perform_update()
        else:
            # No Redis client available, perform update without lock
            self.logger.warning(f"Redis client not available for metadata {metadata_id}, updating without distributed lock")
            updated_metadata = await _perform_update()
        
        self.logger.info(f"Updated user app resume metadata {metadata_id}")
        
        return updated_metadata
    
    async def delete_user_app_resume_metadata(
        self,
        db: AsyncSession,
        *,
        user: User,
        metadata_id: uuid.UUID,
        is_superuser: bool = False
    ) -> bool:
        """Delete a user app resume metadata record."""
        # Get existing metadata to check permissions
        metadata = await self.get_user_app_resume_metadata(db, user=user, metadata_id=metadata_id, is_superuser=is_superuser)
        
        # Delete the metadata
        deleted = await self.user_app_resume_metadata_dao.remove(db, id=metadata_id)
        
        if deleted:
            self.logger.info(f"Deleted user app resume metadata {metadata_id}")
            return True
        
        return False
    
    async def list_user_app_resume_metadata(
        self,
        db: AsyncSession,
        *,
        user: User,
        org_id: Optional[uuid.UUID] = None,
        workflow_name: Optional[str] = None,
        asset_id: Optional[uuid.UUID] = None,
        entity_tag: Optional[str] = None,
        frontend_stage: Optional[str] = None,
        run_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 100,
        is_superuser: bool = False
    ) -> List[models.UserAppResumeMetadata]:
        """List user app resume metadata records with filters."""
        # Determine effective org_id and user_id
        effective_org_id = org_id
        if not effective_org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization ID must be specified"
            )
        
        effective_user_id = user.id
        if user_id and is_superuser:
            effective_user_id = user_id
        
        return await self.user_app_resume_metadata_dao.get_by_filters(
            db,
            org_id=effective_org_id,
            user_id=effective_user_id,
            workflow_name=workflow_name,
            asset_id=asset_id,
            entity_tag=entity_tag,
            frontend_stage=frontend_stage,
            run_id=run_id,
            skip=skip,
            limit=limit
        )

