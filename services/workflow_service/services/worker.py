# PYTHONPATH=.:./services poetry run python /path/to/project/services/workflow_service/services/worker.py
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Tuple, AsyncGenerator, Optional, List, Union, cast
from pydantic import BaseModel

# Prefect imports
from prefect import flow, get_run_logger
from prefect.deployments import run_deployment
from prefect.server.schemas.schedules import CronSchedule
# from prefect.filesystems import S3, GitHub, LocalFileSystem
from prefect.cache_policies import NO_CACHE

# LangGraph and DB imports
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import AnyMessage, AIMessageChunk # Added AIMessageChunk
from langchain_core.load import dumps # Added dumps for logging complex objects

from db.session import get_async_pool, get_async_db_as_manager # Assuming this provides psycopg pool
from global_config.settings import global_settings
from global_config.logger import get_logger

# Local workflow service imports
from workflow_service.graph.graph import GraphSchema
from workflow_service.graph.builder import GraphBuilder
# from workflow_service.registry import default_registry
from workflow_service.graph.runtime.adapter import LangGraphRuntimeAdapter
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY,
    HITL_USER_PROMPT_KEY, # Added HITL keys
    HITL_USER_SCHEMA_KEY
)

from workflow_service.services.external_context_manager import (
    ExternalContextManager,
    get_external_context_manager_with_clients
)

# Import specific event types
from workflow_service.services.events import (
    WorkflowBaseEvent, # Added Base Event
    MessageStreamChunk,
    WorkflowRunNodeOutputEvent,
    WorkflowRunStatusUpdateEvent, # Renamed from Update to UpdateEvent
    HITLRequestEvent
)
from kiwi_app.workflow_app.schemas import WorkflowRunUpdate, NotificationType # Added NotificationType

from kiwi_app.workflow_app import schemas as wf_schemas # Assuming path
from kiwi_app.settings import settings # Assuming path for central settings
from workflow_service.utils.utils import get_node_output_state_key # Util for final output extraction
from workflow_service.config.constants import STATE_KEY_DELIMITER

# --- Core Workflow Execution Flow ---

external_context_global = None

# TODO: mount logs volume to persist logs!
configured_logger = get_logger(
    name="workflow-execution-worker",
    log_level=global_settings.LOG_LEVEL,
    log_filename=global_settings.LOG_PREFECT_FILE_NAME,
    # log_dir=,
    # log_to_console=,
    log_to_file=True,
)

@flow(
    name="workflow-execution",
    description="Orchestrates the execution of a LangGraph workflow",
    log_prints=global_settings.DEBUG,
    retries=1,
    retry_delay_seconds=30,
    # cache_result_in_memory=True, # by default, True
    # cache_policy=NO_CACHE,
)
async def workflow_execution_flow(
    run_job: wf_schemas.WorkflowRunJobCreate
) -> Dict[str, Any]:
    """
    Prefect flow to build and execute a single LangGraph workflow run.
    
    This flow handles the complete lifecycle of a workflow execution:
    1. Initializes the external context (DB, services, Mongo, etc.)
    2. Updates the run status to RUNNING
    3. Fetches the workflow graph schema if not provided
    4. Executes the LangGraph workflow (via run_graph)
    5. Processes the final status and results from run_graph
    6. Publishes completion/failure notifications
    7. Handles failures with proper error reporting
    
    Args:
        run_job: The workflow run job specification as a Pydantic model

    Returns:
        Dict[str, Any]: The workflow execution result or final status info.
    """
    # global external_context_global
    logger = get_run_logger()
    logger.info(f"Starting workflow execution for Run ID: {run_job.run_id}, Workflow ID: {run_job.workflow_id}")
    
    # Create application context for the LangGraph workflow
    # This is now less critical as run_job is passed directly, but kept for potential future use
    
    # --- Initialize ExternalContextManager ---
    # external_context = external_context_global
    # if external_context is None:
    external_context = await get_external_context_manager_with_clients()
    logger.info("External context manager initialized")
    
    try:
        # run_graph now handles internal status updates, event publishing, and returns final update info
        workflow_run_update_result = await run_graph(
            workflow_run_job=run_job,
            external_context=external_context
        )

        logger.info(f"Workflow execution processing completed for Run ID: {run_job.run_id} with status: {workflow_run_update_result.status}")

        # --- Process Final Result and Publish Notifications ---
        # final_outputs = workflow_run_update_result.outputs # Outputs are now part of the result from run_graph

        # logger.info(f"Workflow execution flow finished for Run ID {run_job.run_id}")
        # Return the final update info, which includes status and outputs
        return workflow_run_update_result  # .model_dump(mode='json', exclude_defaults=False)

    except Exception as e:
        logger.error(f"Workflow execution flow failed critically for Run ID {run_job.run_id}: {e}", exc_info=True)
        error_message = str(e)
        final_status = wf_schemas.WorkflowRunStatus.FAILED
        # Re-raise the original exception to ensure Prefect marks the flow as failed
        raise e # Re-raise the original error

    finally:
        # Clean up resources regardless of success or failure
        try:
            await external_context.close()
            logger.info("External context manager closed successfully")
        except Exception as close_err:
            logger.error(f"Error closing external context: {close_err}", exc_info=True)


async def run_graph(
    workflow_run_job: wf_schemas.WorkflowRunJobCreate,
    external_context: ExternalContextManager
) -> wf_schemas.WorkflowRunUpdate:
    """
    Build and execute a LangGraph graph, processing the stream for events,
    status updates, and HITL requests.

    Args:
        workflow_run_job: The workflow run job specification.
        external_context: The initialized ExternalContextManager instance.

    Returns:
        WorkflowRunUpdate: An object containing the final status, outputs, and error message (if any).
    """
    logger = get_run_logger()
    run_id = workflow_run_job.run_id
    org_id = workflow_run_job.owner_org_id
    user_id = workflow_run_job.triggered_by_user_id
    final_output_node_id = None # Initialize
    final_outputs = None
    sequence_id_counter = 0 # Start event sequence counter
    
    # Check if this is a resume after HITL
    if workflow_run_job.resume_after_hitl:
        logger.info(f"Resuming workflow after HITL for Run ID: {run_id}")
        # # Fetch any pending HITL jobs for this run to process their responses
        # async with get_async_db_as_manager() as db:
        #     # NOTE: this is sorted by descending created at, latest first!
        #     pending_hitl_jobs = await external_context.daos.hitl_job.get_pending_by_run(
        #         db=db, 
        #         requesting_run_id=run_id
        #     ) 
        #     if pending_hitl_jobs:
        #         logger.info(f"Found {len(pending_hitl_jobs)} pending HITL jobs to process")
        #         for job in pending_hitl_jobs:
        #             logger.info(f"Processing HITL job: {job.id}")
        #             logger.info(f"Request details: {job.request_details}")
        #             logger.info(f"Response schema: {job.response_schema}")
        #     else:
        #         logger.info("No pending HITL jobs found for this run")
    else:
        # Create a new workflow run instance if this is not a resume
        # This is needed when run_id is None and we need to create a new run
        if not run_id:
            raise ValueError("Non NULL, existing Run ID is required to create a new workflow run")
            # logger.info("Creating new workflow run instance")
            # async with get_async_db_as_manager() as db:
            #     new_workflow_run = await external_context.daos.workflow_run.create(
            #         db=db,
            #         workflow_id=workflow_run_job.workflow_id,
            #         owner_org_id=org_id,
            #         triggered_by_user_id=user_id,
            #         inputs=workflow_run_job.inputs,
            #         thread_id=workflow_run_job.thread_id
            #     )
            #     # Update the run_id in the job
            #     run_id = new_workflow_run.id
            #     workflow_run_job.run_id = run_id
            #     logger.info(f"Created new workflow run with ID: {run_id}")
    
    # If thread_id is not provided, use run_id as the thread_id
    thread_id = workflow_run_job.thread_id or run_id

    logger.info(f"Building graph for Run ID: {run_id}")
    error_message = None

    try:
        # --- Graph Building ---
        builder = GraphBuilder(external_context.db_registry)
        # Pass run job directly for context if builder needs it
        graph_entities = builder.build_graph_entities(workflow_run_job.graph_schema, prefect_mode=True, allow_non_user_editable_fields=True)
        logger.info("Graph entities built successfully")
        final_output_node_id = graph_entities.get("output_node_id")

        # --- Runtime Configuration ---
        runtime_config = graph_entities.get("runtime_config", {})
        # Pass necessary context items into the config for LangGraph nodes
        runtime_config[APPLICATION_CONTEXT_KEY] = workflow_run_job # Pass the whole job object
        runtime_config[EXTERNAL_CONTEXT_MANAGER_KEY] = external_context

        # Configure thread_id for checkpointing
        thread_id = workflow_run_job.thread_id or run_id
        runtime_config["thread_id"] = str(thread_id)
        runtime_config["use_checkpointing"] = True # Assume checkpointing is always desired

        # Setup Checkpointer using Postgres pool from external_context
        # Assuming external_context provides the necessary pool or connection
        # This requires external_context to have been initialized with DB access
        async with get_async_pool() as async_psycopg_pool:
            checkpointer = AsyncPostgresSaver(async_psycopg_pool)
            runtime_config["checkpointer"] = checkpointer

            # --- Adapter and Execution ---
            adapter = LangGraphRuntimeAdapter()
            compiled_graph = adapter.build_graph(graph_entities)
            logger.info("Graph compiled successfully")

            # Get initial input data
            initial_input = workflow_run_job.inputs or {}
            logger.info(f"Executing graph stream with input data: {initial_input}")

            # --- Process Graph Stream ---
            current_status = wf_schemas.WorkflowRunStatus.RUNNING # Track status locally
            error_message = None
            exception_raised = False

            # 1. Update DB status to PENDING_HITL
            async with get_async_db_as_manager() as db:
                await external_context.daos.workflow_run.update_status(
                    db=db, run_id=run_id, status=current_status
                )
                logger.info(f"Updated Run {run_id} status to RUNNING in DB.")

            async for chunk in adapter.aexecute_graph_stream(
                graph=compiled_graph,
                input_data=initial_input,
                config=runtime_config, # Pass the full runtime config
                output_node_id=final_output_node_id,
                interrupt_handler=None, # Adapter handles internal interrupt loop
                resume_with_hitl=workflow_run_job.resume_after_hitl,
            ):
                try:
                    # Ensure chunk is a tuple (stream_mode, data)
                    if not isinstance(chunk, tuple) or len(chunk) != 2:
                        logger.warning(f"Received unexpected chunk format: {chunk}")
                        continue

                    stream_mode, data = chunk
                    timestamp = datetime.now(tz=timezone.utc)

                    base_event_data = {
                        "run_id": run_id,
                        "org_id": org_id,
                        "user_id": user_id,
                        "event_id": str(uuid.uuid4()),
                        "sequence_i": sequence_id_counter,
                        "timestamp": timestamp,
                    }

                    # Build the final path list in the order defined by settings
                    mongo_path = [str(base_event_data.get(seg_name, "*")) for seg_name in settings.MONGO_WORKFLOW_STREAM_SEGMENTS]
                    # Ensure no wildcards remain unintentionally
                    if "*" in mongo_path:
                        logger.warning(f"Failed to construct MongoDB path. Some segments missing for event: {stream_mode}::{sequence_id_counter}::{run_id}")
                        mongo_path = None
                    # logger.info(f"MongoDB path constructed successfully: {mongo_path}")

                    # --- Handle Different Stream Modes ---
                    if stream_mode == "messages":
                        # Process message chunks (e.g., from LLMs)
                        # Data is often AIMessageChunk or similar
                        if isinstance(data, (tuple, list)) and len(data) == 2:  #  and isinstance(data[0], AIMessageChunk):
                            message_chunk, runtime_config = data
                            message_event = MessageStreamChunk(
                                **base_event_data,
                                node_id=runtime_config.get("langgraph_node", ""),
                                message=message_chunk,
                                # node_id might be available in data.response_metadata or config if adapter provides it
                            )
                            message_event_dump = message_event.model_dump(mode='json', exclude_defaults=False)

                            # NOTE: this will help reconstruct the stream and resume output potentially!
                            # Otherwise this is very high bandwidth potentially!
                            if mongo_path:
                                # Persist to Mongo DB
                                await external_context.mongo.workflow.create_object(
                                    path=mongo_path,
                                    data=message_event_dump
                                    # No need for allowed_prefixes here, internal system operation
                                )
                                logger.info(f"Persisted event {message_event.event_type} (RunID: {message_event.run_id}, SeqID: {message_event.sequence_i}) to MongoDB.")

                            # Publish to RabbitMQ Stream
                            await external_context.rabbit.publish_workflow_event(message_event_dump)
                            sequence_id_counter += 1
                        else:
                            logger.debug(f"Received non-AnyMessage in 'messages' stream: {type(data)} \n{data}\n")

                    elif stream_mode == "updates":
                        # Process state updates, node outputs, and interrupts
                        if not isinstance(data, dict):
                            logger.warning(f"Received non-dict data in 'updates' stream: {data}")
                            continue

                        for node_id, node_output in data.items():
                            if node_id == "__interrupt__":
                                # --- Handle HITL Interrupt ---
                                current_status = wf_schemas.WorkflowRunStatus.WAITING_HITL
                                logger.info(f"Run {run_id} interrupted for HITL.")

                                # Extract interrupt payload
                                interrupt_list = cast(List[Any], node_output)
                                if not interrupt_list: continue
                                interrupt_payload = interrupt_list[0].value # Get value from the langgraph Interrupt object

                                hitl_prompt = interrupt_payload.get(HITL_USER_PROMPT_KEY, {})
                                if isinstance(hitl_prompt, BaseModel):
                                    hitl_prompt = json.loads(hitl_prompt.model_dump_json())
                                hitl_schema = interrupt_payload.get(HITL_USER_SCHEMA_KEY, {})

                                # 1. Update DB status to PENDING_HITL
                                async with get_async_db_as_manager() as db:
                                    await external_context.daos.workflow_run.update_status(
                                        db=db, run_id=run_id, status=current_status
                                    )
                                    assigned_user = user_id # Default to triggering user for now
                                    # 2. Create HITL Job in DB
                                    hitl_job = await external_context.daos.hitl_job.create(
                                        db=db,
                                        requesting_run_id=run_id,
                                        org_id=org_id,
                                        request_details=hitl_prompt,
                                        response_schema=hitl_schema,
                                        assigned_user_id=assigned_user
                                    )
                                    # 2.b. Create User Notification in DB
                                    user_notification = await external_context.daos.user_notification.create(
                                        db=db,
                                        user_id=assigned_user,
                                        org_id=org_id,
                                        notification_type=NotificationType.HITL_REQUESTED,
                                        message=hitl_prompt,
                                        related_run_id=run_id
                                    )
                                    
                                    logger.info(f"Created HITL Job DB entry {hitl_job.id} and notification entry {user_notification.id} for Run {run_id}.")
                                logger.info(f"Updated Run {run_id} status to PENDING_HITL in DB.")

                                # 3. Publish Status Update Event
                                status_event = WorkflowRunStatusUpdateEvent(
                                    **base_event_data, status=current_status
                                )
                                status_event_dump = status_event.model_dump(mode='json', exclude_defaults=False)
                                if mongo_path:
                                    # Persist to Mongo DB
                                    await external_context.mongo.workflow.create_object(
                                        path=mongo_path,
                                        data=status_event_dump
                                        # No need for allowed_prefixes here, internal system operation
                                    )
                                    logger.info(f"Persisted event {status_event.event_type} (RunID: {status_event.run_id}, SeqID: {status_event.sequence_i}) to MongoDB.")

                                # Publish to RabbitMQ Stream
                                await external_context.rabbit.publish_workflow_event(status_event_dump)
                                sequence_id_counter += 1


                                # 4. Publish HITL Request Event
                                hitl_event = HITLRequestEvent(
                                    **base_event_data,
                                    # node_id: Needs context from adapter/interrupt payload if available
                                    request_data_schema=hitl_schema,
                                    user_prompt=hitl_prompt,
                                    payload={"message": "User input required"} # Simple payload
                                )
                                hitl_event_dump = hitl_event.model_dump(mode='json', exclude_defaults=False)
                                if mongo_path:
                                    mongo_path[-1] = mongo_path[-1] + "_hitl_requests"
                                    # Persist to Mongo DB
                                    await external_context.mongo.workflow.create_object(
                                        path=mongo_path,
                                        data=hitl_event_dump
                                        # No need for allowed_prefixes here, internal system operation
                                    )
                                    logger.info(f"Persisted event {hitl_event.event_type} (RunID: {hitl_event.run_id}, SeqID: {hitl_event.sequence_i}) to MongoDB.")

                                # Publish to RabbitMQ Stream
                                await external_context.rabbit.publish_workflow_event(hitl_event_dump)
                                
                                
                                sequence_id_counter += 1

                                # 5. Send User Notification for HITL
                                if assigned_user:
                                     await external_context.rabbit.publish_notification(
                                         hitl_event,
                                    #      {
                                    #      "user_id": str(assigned_user),
                                    #      "org_id": str(org_id),
                                    #      "notification_type": NotificationType.HITL_REQUEST.value,
                                    #      "message": {
                                    #          "summary": "Action required: Input needed for workflow",
                                    #          "run_id": str(run_id),
                                    #          "prompt": hitl_prompt # Include prompt in notification
                                    #      },
                                    #      "related_run_id": str(run_id)
                                    #  }
                                     )
                                     logger.info(f"Sent HITL notification for Run {run_id} to user {assigned_user}.")

                            else:
                                # --- Handle Node Output ---
                                # Extract actual node_id from the state key
                                # actual_node_id = node_id.replace(get_node_output_state_key(node_id), "")
                                
                                node_state_update = node_output  # .get(node_id, {})
                                # print(node_output)
                                node_output = node_state_update.get(get_node_output_state_key(node_id), {})
                                if isinstance(node_output, BaseModel):
                                    node_output = json.loads(node_output.model_dump_json())
                                
                                # print(node_state_update)
                                # print(node_output)
                                # import ipdb; ipdb.set_trace()
                                
                                central_state_update = {k.split(STATE_KEY_DELIMITER)[-1]:v for k,v in node_state_update.items() if k != get_node_output_state_key(node_id)}
                                for k,v in central_state_update.items():
                                    if isinstance(v, BaseModel):
                                        central_state_update[k] = json.loads(v.model_dump_json())

                                payload={
                                    "node_output": node_output,
                                }
                                if central_state_update:
                                    payload["central_state_update"] = central_state_update
                                output_event = WorkflowRunNodeOutputEvent(
                                    **base_event_data,
                                    node_id=node_id,
                                    payload=payload,
                                )
                                output_event_dump = output_event.model_dump(mode='json', exclude_defaults=False)
                                if mongo_path:
                                    # Persist to Mongo DB
                                    await external_context.mongo.workflow.create_object(
                                        path=mongo_path,
                                        data=output_event_dump
                                        # No need for allowed_prefixes here, internal system operation
                                    )
                                    logger.info(f"Persisted event {output_event.event_type} (RunID: {output_event.run_id}, SeqID: {output_event.sequence_i}) to MongoDB.")

                                # Publish to RabbitMQ Stream
                                await external_context.rabbit.publish_workflow_event(output_event_dump)
                                sequence_id_counter += 1

                                # Capture final output if this is the designated output node
                                if final_output_node_id and node_id == final_output_node_id:
                                    final_outputs = node_output
                                    logger.info(f"Captured final output from node {final_output_node_id}")

                            # else: Handle other update keys if necessary (e.g., central state updates)
                            #    logger.debug(f"Ignoring general state update key: {node_id}")

                    elif stream_mode == "debug":
                         # Log debug information if needed
                         logger.debug(f"Graph Debug Chunk: {dumps(data, pretty=True)}")

                    else:
                         logger.warning(f"Received unhandled stream mode: {stream_mode}")

                except Exception as stream_err:
                     logger.error(f"Error processing stream chunk for Run ID {run_id}: {stream_err}", exc_info=True)
                     # Decide if this error should fail the whole run
                     # current_status = wf_schemas.WorkflowRunStatus.FAILED
                     # error_message = f"Error processing stream chunk: {stream_err}"
                     # break # Exit stream loop on processing error? Or continue?

            # --- After Stream Loop ---
            if current_status == wf_schemas.WorkflowRunStatus.RUNNING: # If it finished without error or HITL
                 current_status = wf_schemas.WorkflowRunStatus.COMPLETED
                 logger.info(f"Graph stream execution completed successfully for Run ID: {run_id}")
            # If status is PENDING_HITL, it remains so. If FAILED, it remains so.


    except Exception as graph_exec_err:
        logger.error(f"Graph execution failed for Run ID {run_id}: {graph_exec_err}", exc_info=True)
        current_status = wf_schemas.WorkflowRunStatus.FAILED
        error_message = str(graph_exec_err)
        # exception_raised = graph_exec_err
        # global external_context_global
        # external_context_global = None
        # external_context = None
        raise graph_exec_err
    
    finally:
        if current_status not in [wf_schemas.WorkflowRunStatus.COMPLETED, wf_schemas.WorkflowRunStatus.WAITING_HITL]:
            current_status = wf_schemas.WorkflowRunStatus.FAILED
        # --- Final Status Update and Event Publishing ---
        ended_at = datetime.now(tz=timezone.utc) if current_status in [wf_schemas.WorkflowRunStatus.COMPLETED, wf_schemas.WorkflowRunStatus.FAILED] else None

        # Create the final update object to return
        workflow_run_update = WorkflowRunUpdate(
            run_id=run_id,
            status=current_status,
            ended_at=ended_at,
            error_message=error_message,
            outputs=final_outputs # Include captured outputs
        )

        # Update DB with the final status (unless it's PENDING_HITL, which was already updated)
        if current_status != wf_schemas.WorkflowRunStatus.WAITING_HITL:
            try:
                async with get_async_db_as_manager() as db:
                    await external_context.daos.workflow_run.update_status(
                        db=db,
                        run_id=run_id,
                        status=workflow_run_update.status,
                        ended_at=workflow_run_update.ended_at,
                        error_message=workflow_run_update.error_message,
                        outputs=workflow_run_update.outputs
                    )
                logger.info(f"Updated final status ({current_status.value}) and outputs in DB for Run ID: {run_id}")
            except Exception as db_update_err:
                logger.error(f"Failed to update final DB status/outputs for Run ID {run_id}: {db_update_err}", exc_info=True)
                # Potentially override status to FAILED if DB update fails critically?
                # workflow_run_update.status = wf_schemas.WorkflowRunStatus.FAILED
                # workflow_run_update.error_message = f"DB update failed: {db_update_err}"

            # Publish final status update event to stream (unless PENDING_HITL)
            final_status_event = WorkflowRunStatusUpdateEvent(
                event_id=str(uuid.uuid4()),
                run_id=run_id,
                org_id=org_id,
                user_id=user_id,
                sequence_i=sequence_id_counter, # Final sequence ID
                status=workflow_run_update.status,
                error_message=workflow_run_update.error_message,
                timestamp=ended_at or datetime.now(tz=timezone.utc),
                payload=final_outputs if current_status == wf_schemas.WorkflowRunStatus.COMPLETED else None # Include output in final event
            )
            try:
                # default: field: event_type!
                final_status_event_dump = final_status_event.model_dump(mode='json', exclude_defaults=False)
                mongo_path = [str(final_status_event_dump[key]) for key in settings.MONGO_WORKFLOW_STREAM_SEGMENTS]
                await external_context.mongo.workflow.create_object(
                    path=mongo_path,
                    data=final_status_event_dump
                    # No need for allowed_prefixes here, internal system operation
                )
                logger.info(f"Persisted event {final_status_event.event_type} (RunID: {final_status_event.run_id}, SeqID: {final_status_event.sequence_i}) to MongoDB.")

                await external_context.rabbit.publish_workflow_event(final_status_event_dump)
                logger.info(f"Published final status update event ({current_status.value}) for Run ID: {run_id}")

                # Create User Notification in DB
                await external_context.daos.user_notification.create(
                    db=db,
                    user_id=user_id,
                    org_id=org_id,
                    notification_type=NotificationType.RUN_COMPLETED if current_status == wf_schemas.WorkflowRunStatus.COMPLETED else NotificationType.RUN_FAILED,
                    message=final_status_event_dump,
                    related_run_id=run_id
                )
                logger.info(f"Published final status update event ({current_status.value}) for Run ID: {run_id}")
                await external_context.rabbit.publish_notification(
                    final_status_event,
                )
            except Exception as publish_err:
                logger.error(f"Failed to publish final status event for Run ID {run_id}: {publish_err}", exc_info=True)

    # if exception_raised is not None:
    #     raise exception_raised

    logger.info(f"run_graph finished processing for Run ID: {run_id}. Final status: {current_status.value}")
    return workflow_run_update


# --- Helper Functions ---

async def trigger_workflow_run(
    workflow_id: uuid.UUID,
    inputs: Optional[Dict[str, Any]] = None,
    owner_org_id: Optional[uuid.UUID] = None,
    triggered_by_user_id: Optional[uuid.UUID] = None,
    run_id: Optional[uuid.UUID] = None,
    thread_id: Optional[uuid.UUID] = None, # Added thread_id
    graph_schema: Optional[GraphSchema] = None,
    resume_after_hitl: Optional[bool] = False,
) -> uuid.UUID:
    """
    Helper function to trigger a workflow run via the Prefect deployment.
    
    Args:
        workflow_id: ID of the workflow to run
        inputs: Optional inputs for the workflow
        owner_org_id: Organization ID that owns this workflow run
        triggered_by_user_id: User ID that triggered this workflow run
        run_id: Optional custom run_id, generated if not provided
        thread_id: Optional thread_id for resuming runs
        
    Returns:
        uuid.UUID: The run ID of the triggered flow
    """
    # if run_id is None:
    #     run_id = uuid.uuid4()
        
    if owner_org_id is None:
        # Default to system org ID if available
        # Use a specific system org ID if configured, otherwise generate one (might not be ideal)
        system_org_id_str = getattr(settings, "SYSTEM_ORG_ID", None)
        owner_org_id = uuid.UUID(system_org_id_str) if system_org_id_str else uuid.uuid4() # Handle potential None

    # Create the run job payload
    run_job = wf_schemas.WorkflowRunJobCreate(
        run_id=run_id,
        workflow_id=workflow_id,
        owner_org_id=owner_org_id,
        triggered_by_user_id=triggered_by_user_id,
        inputs=inputs or {},
        thread_id=thread_id, # Pass thread_id
        graph_schema=graph_schema,
        resume_after_hitl=resume_after_hitl,
    )
    
    # Trigger the workflow as a deployment
    # This returns a PrefectFuture we could wait on if needed
    flow_run = await run_deployment(
        name="workflow-execution/prod",  # References the deployment name below
        parameters={"run_job": run_job},   # .model_dump(mode='json')}, # Ensure proper serialization
        timeout=0  # Don't wait for completion
    )
    from global_config.logger import get_logger
    get_logger(__name__).info(f"Triggered deployment 'workflow-execution/prod' for Run ID: {run_id} (Prefect Flow Run ID: {flow_run.id})")

    return run_id

# --- Prefect Deployment Definition ---

# def create_workflow_deployment(
#     work_pool_name: str = "default-process-pool",
#     cron_schedule: Optional[str] = None,
#     version: str = "1.0.0",
#     storage_block: Optional[str] = None,
#     description: str = "Executes LangGraph workflows from configuration"
# ) -> Deployment:
#     """
#     Create a Prefect deployment for the workflow execution flow.
    
#     Args:
#         work_pool_name: The Prefect work pool to use
#         cron_schedule: Optional cron expression for scheduled runs
#         version: Version string for this deployment
#         storage_block: Optional storage block for flow code (e.g., "github/my-repo")
#         description: Description of this deployment
        
#     Returns:
#         Deployment: The configured deployment definition
#     """
#     # Configure schedule if provided
#     schedule = None
#     if cron_schedule:
#         schedule = CronSchedule(cron=cron_schedule, timezone="UTC")
    
#     # Configure storage if provided
#     # Define infrastructure overrides, like environment variables
#     infra_overrides = {
#         "env": {
#             "PREFECT_LOGGING_LEVEL": settings.LOG_LEVEL, # Use settings
#             "PYTHONUNBUFFERED": "1", # Often useful for logging in containers
#             # Add other environment variables needed by the flow from settings
#             # e.g., "DATABASE_URL": settings.DATABASE_URL,
#             # Ensure sensitive variables are handled securely (e.g., Prefect secrets)
#         }
#     }

#     # storage = None
#     # if storage_block:
#     #     # Example assumes storage block names match Prefect Cloud/Server config
#     #     if storage_block.startswith("s3/"):
#     #          storage = S3.load(storage_block.replace("s3/", ""))
#     #     elif storage_block.startswith("github/"):
#     #          storage = GitHub.load(storage_block.replace("github/", ""))
#     #     elif storage_block.startswith("local/"): # Example for local
#     #          storage = LocalFileSystem.load(storage_block.replace("local/", ""))
#     #     # Add more storage types as needed

#     # Build the deployment
#     deployment = Deployment.build_from_flow(
#         flow=workflow_execution_flow,
#         name="prod",  # Will be "<flow_name>/prod" when deployed
#         version=version,
#         work_pool_name=work_pool_name,
#         schedule=schedule,
#         parameters={},  # Parameters are provided at runtime via run_deployment
#         tags=["workflow-service", "langgraph", settings.ENV], # Add environment tag
#         description=description,
#         infra_overrides=infra_overrides,
#         # storage=storage # Use the loaded storage block object
#     )

#     return deployment

# Entry point for deployment registration
if __name__ == "__main__":
    """
    Script entry point for registering the workflow deployment with Prefect.
    
    Usage:
        python -m services.workflow_service.services.worker apply

    This will register/update the workflow deployment with the Prefect server
    configured in your environment or Prefect profile.
    """
    workflow_execution_flow.serve(
        name="prod",
        tags=["workflow-service"],
        # parameters={"goodbye": True},
        pause_on_shutdown=global_settings.APP_ENV != "PROD",
        # interval=60,
        # cron="* * * * *",
        description=f"Production deployment for KiwiQ LangGraph workflows ({global_settings.APP_ENV})",
        version="workflow-service/deployments",
    )
    # import sys
    # if len(sys.argv) > 1 and sys.argv[1] == 'apply':
    #     print("Registering Prefect deployment...")
    #     # Create the deployment with customized settings from environment/config
    #     deployment = create_workflow_deployment(
    #         work_pool_name=settings.PREFECT_WORK_POOL_NAME, # Use your actual work pool name from settings
    #         cron_schedule=None,  # Set dynamically if needed
    #         version=settings.VERSION,
    #         # Example: storage_block="github/your-org/your-repo" # Configure via settings
    #         storage_block=settings.PREFECT_STORAGE_BLOCK,
    #         description=f"Production deployment for KiwiQ LangGraph workflows ({settings.ENV})"
    #     )

    #     # Apply the deployment to the Prefect server
    #     deployment.apply() # Use apply() which creates or updates
    #     print(f"Workflow deployment '{deployment.flow_name}/{deployment.name}' (version {deployment.version}) applied successfully to work pool '{deployment.work_pool_name}'.")

    #     # Note about work pool existence
    #     print(f"\nNote: Ensure the work pool '{settings.PREFECT_WORK_POOL_NAME}' exists in your Prefect Cloud/Server.")
    #     print("If not, create it (e.g., via Prefect UI or CLI).")
    #     # Example CLI command:
    #     # prefect work-pool create your-pool-name --type process # Or 'kubernetes', 'docker', etc.
    # else:
    #      print("Run with 'apply' argument to register the Prefect deployment:")
    #      print("  python -m services.workflow_service.services.worker apply")
