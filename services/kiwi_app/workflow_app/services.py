"""Service layer for the Workflow Application.

This module contains the business logic for managing workflows, runs,
templates, notifications, and HITL jobs. It uses the crud layer
for database interactions.
"""

import json
import uuid
import asyncio # Keep asyncio import
from datetime import datetime, timezone # Add timezone
from typing import List, Optional, Dict, Any, Union

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from pydantic import ValidationError # For schema validation

from jsonschema import validate
from jsonschema.validators import Draft202012Validator

from global_utils import datetime_now_utc
from global_config.logger import get_logger
from sqlmodel import or_, select
from kiwi_app.workflow_app import models, schemas, crud
from kiwi_app.workflow_app.constants import WorkflowRunStatus, NotificationType, HITLJobStatus, LaunchStatus # Import LaunchStatus
from kiwi_app.auth.models import User, Organization # For type hinting and context
from kiwi_app.settings import settings # Import settings for Mongo paths etc.

# MongoDB Client and Event Schemas
from mongo_client import AsyncMongoDBClient
from workflow_service.graph.graph import GraphSchema
from workflow_service.services import events as event_schemas # For Run Details

# Import the worker trigger function
# Ensure this path is correct based on your project structure
from workflow_service.services.worker import trigger_workflow_run

# Placeholder for JSON Schema validation library (e.g., jsonschema)
# import jsonschema # Add to requirements if used

logger = get_logger(__name__)


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
        mongo_client: Optional[AsyncMongoDBClient] = None, # Make Mongo optional for now
        customer_mongo_client: Optional[AsyncMongoDBClient] = None, # Make Mongo optional for now
    ) -> None:
        """Initialize the WorkflowService with its DAO and client dependencies."""
        self.node_template_dao = node_template_dao
        self.workflow_dao = workflow_dao
        self.workflow_run_dao = workflow_run_dao
        self.prompt_template_dao = prompt_template_dao
        self.schema_template_dao = schema_template_dao
        self.user_notification_dao = user_notification_dao
        self.hitl_job_dao = hitl_job_dao
        self.mongo_client = mongo_client
        self.customer_mongo_client = customer_mongo_client

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
        user: User
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
                new_workflow = await self._create_workflow_internal(
                    db, workflow_in=workflow_create_data, owner_org_id=owner_org_id, user_id=user.id
                )
                workflow_id = new_workflow.id
                # Keep graph_schema_dict for worker trigger
            elif workflow_id:
                # Validate the provided workflow_id belongs to the organization
                # NOTE: we want regular users to be able to execute system entity eg: workflows but which are marked public!
                workflow = await self.get_workflow(db, workflow_id=workflow_id, user=user, owner_org_id=owner_org_id, include_system_entities=True)
                # If not found, get_workflow raises 404
                graph_schema_dict = workflow.graph_config # Get schema for worker trigger
            else:
                # Validation should happen in the schema, but double-check
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid submission: missing workflow_id or graph_schema.")
                
            # 2. Create the WorkflowRun record with SCHEDULED status
            if run_submit.run_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot provide run_id when submitting a new run")

            workflow_run = await self.workflow_run_dao.create(
                db,
                workflow_id=workflow_id,
                owner_org_id=owner_org_id,
                triggered_by_user_id=user.id,
                inputs=run_submit.inputs,
                thread_id=run_submit.thread_id, # Pass thread_id if provided
                status=WorkflowRunStatus.SCHEDULED # Explicitly set status
            )
            if not workflow_run.thread_id:
                workflow_run.thread_id = workflow_run.id
                db.add(workflow_run)
                await db.commit()
                await db.refresh(workflow_run)

        # 3. Trigger the actual execution via Prefect worker/helper
        try:
            # Ensure we have the graph schema to pass to the worker
            if not graph_schema_dict:
                 # This should only happen if workflow_id was provided but we failed to get the schema earlier
                 # NOTE: we want regular users to be able to execute system entity eg: workflows but which are marked public!
                 workflow = await self.get_workflow(db, workflow_id=workflow_run.workflow_id, user=user, owner_org_id=owner_org_id, include_system_entities=True)
                 graph_schema_dict = workflow.graph_config

            # Trigger the workflow run via the helper function
            await trigger_workflow_run(
                workflow_id=workflow_run.workflow_id,
                owner_org_id=owner_org_id,
                triggered_by_user_id=user.id,
                inputs=run_submit.inputs,
                run_id=workflow_run.id, # Pass the created run_id
                thread_id=workflow_run.thread_id, # Pass thread_id
                graph_schema=GraphSchema.model_validate(graph_schema_dict), # Pass the graph schema
                resume_after_hitl=run_submit.resume_after_hitl # This is a new submission
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

            # Find all events for this run, sorted by sequence number, respecting permissions
            event_dicts = await self.mongo_client.search_objects(
                key_pattern=mongo_runs_events_pattern,
                # filter_query={}, # Get all events for the run
                value_sort_by=[("timestamp", -1), ("sequence_i", -1)], # Sort by timestamp descending, then sequence descending
                allowed_prefixes=allowed_prefixes, # Apply permission check
                value_filter={"event_type": {"$in": [event_schemas.WorkflowEvent.NODE_OUTPUT.value, event_schemas.WorkflowEvent.WORKFLOW_RUN_STATUS.value]}}
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
        user: User
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
            is_superuser=user.is_superuser
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
        user: User
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
            is_superuser=user.is_superuser
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
        user: User
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
            is_superuser=user.is_superuser
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

            # Call the worker trigger function
            await trigger_workflow_run(
                workflow_id=run.workflow_id,
                owner_org_id=run.owner_org_id,
                triggered_by_user_id=run.triggered_by_user_id, # Original triggerer
                inputs=response_data, # Pass HITL response as input for resumption node
                run_id=run.id,
                thread_id=run.thread_id, # Use existing thread_id for checkpointing
                graph_schema=workflow.graph_config, # Pass the workflow schema
                resume_after_hitl=True # Indicate this is a resumption
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

# --- Helper Functions/Classes (Optional) --- #

# Example Custom Exception (replace with HTTPException)
# class TemplateNotFoundException(HTTPException):
#     def __init__(self, detail: str = "Template not found"):
#         super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

# class WorkflowRunNotFoundException(HTTPException):
#     def __init__(self, detail: str = "Workflow run not found or access denied"):
#         super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

# TODO: Add service methods for fetching/managing workflow templates (workflows where is_template=True)
# TODO: Add methods for managing system templates (Node, Prompt, Schema) if needed (requires Admin role checks)
# TODO: Implement robust logging throughout the service layer.
# TODO: Add detailed validation for input schemas, response schemas, graph configs.


