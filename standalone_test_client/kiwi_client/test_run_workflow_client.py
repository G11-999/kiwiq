import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone # Import timezone
from typing import Dict, Any, Optional, List, Tuple, Callable, TypedDict, Awaitable, Union

# Assume these exist based on the reference file\'s structure and project layout
try:
    from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
    from kiwi_client.customer_data_client import CustomerDataTestClient # Import CustomerDataTestClient
    from kiwi_client.test_config import CLIENT_LOG_LEVEL
    # Use the base clients provided by the library/framework
    from kiwi_client.run_client import WorkflowRunTestClient as BaseWorkflowRunTestClient
    from kiwi_client.notification_hitl_client import HITLTestClient
    # Add WorkflowTestClient for creating/deleting workflows
    from kiwi_client.workflow_client import WorkflowTestClient
    # Import schemas used
    from kiwi_client.schemas import workflow_api_schemas as wf_schemas
    from kiwi_client.schemas import events_schema as event_schemas # Import event schemas
    from kiwi_client.schemas.workflow_constants import WorkflowRunStatus
    # Import app artifact schemas for workflow key lookups
    from kiwi_client.schemas import app_artifact_schemas as aa_schemas
except ImportError as e:
    # Provide a helpful message if imports fail, common in complex project structures
    print(f"Import Error: {e}. Ensure kiwi_client package is correctly installed and accessible.")
    print("PYTHONPATH might need adjustment. Run scripts from the project root.")
    # Re-raise or exit if imports are critical for the module\'s basic function
    raise

# Setup logger
# Use __name__ so log messages clearly indicate their origin file
logger = logging.getLogger(__name__)
# Configure logging - basicConfig is simple, but consider more robust setup for larger apps
# Check if handlers are already configured to avoid duplicates if this module is imported elsewhere
if not logging.getLogger().handlers:
    logging.basicConfig(level=CLIENT_LOG_LEVEL)


class InteractiveWorkflowRunClient:
    """
    A test client designed to submit a workflow run, monitor its progress,
    and interactively handle Human-in-the-Loop (HITL) steps.

    Can optionally create the workflow from a provided schema before running,
    and cleans it up afterwards if it created it.

    Can optionally stream intermediate run events (node outputs, status changes,
    message chunks) to standard output in near real-time.

    Attributes:
        _auth_client (AuthenticatedClient): Client for authenticated API calls.
        _run_client (BaseWorkflowRunTestClient): Client for workflow run operations.
        _hitl_client (HITLTestClient): Client for HITL job operations.
        _workflow_client (WorkflowTestClient): Client for workflow definition operations.
    """
    EVENT_TYPES_TO_PRINT = [
        event_schemas.MessageStreamChunk,
        # event_schemas.WorkflowRunNodeOutputEvent,
        # event_schemas.WorkflowRunStatusUpdateEvent,
        # event_schemas.HITLRequestEvent,
    ]

    def __init__(self, auth_client: AuthenticatedClient):
        """
        Initializes the InteractiveWorkflowRunClient.

        Args:
            auth_client: An authenticated client instance for making API calls.

        Raises:
            ValueError: If auth_client is not provided.
        """
        if not auth_client:
            # Ensure necessary dependencies are provided.
            raise ValueError("AuthenticatedClient is required.")
        self._auth_client: AuthenticatedClient = auth_client
        # Instantiate the specific clients needed for operations.
        # Prefixing with underscore indicates intended internal use.
        self._run_client: BaseWorkflowRunTestClient = BaseWorkflowRunTestClient(auth_client)
        self._hitl_client: HITLTestClient = HITLTestClient(auth_client)
        # Add workflow client instance
        self._workflow_client: WorkflowTestClient = WorkflowTestClient(auth_client)
        logger.info("InteractiveWorkflowRunClient initialized.")

    async def _get_hitl_input(
        self,
        run_id: uuid.UUID,
        hitl_job: wf_schemas.HITLJobRead,
        hitl_input_iterator: int,
        provided_hitl_inputs: Optional[List[Dict[str, Any]]]
    ) -> Optional[Dict[str, Any]]:
        """Internal helper to get HITL input (pre-provided or user prompt)."""
        # Check if a pre-provided input exists at the current index
        if provided_hitl_inputs and 0 <= hitl_input_iterator < len(provided_hitl_inputs):
            hitl_inputs = provided_hitl_inputs[hitl_input_iterator]
            logger.info(f"Using pre-provided HITL input #{hitl_input_iterator + 1} for run {run_id}.")
            print(f"\n--- Using pre-provided HITL input #{hitl_input_iterator + 1} ---")
            try:
                print(json.dumps(hitl_inputs, indent=2))
            except TypeError as e:
                logger.error(f"Failed to serialize pre-provided HITL input for display: {e}")
                print(f"(Could not display input due to serialization error: {e})")
            if not isinstance(hitl_inputs, dict):
                 logger.error(f"Pre-provided HITL input #{hitl_input_iterator + 1} is not a dictionary: {type(hitl_inputs)}")
                 print(f"   ✗ Error: Pre-provided input #{hitl_input_iterator + 1} is not a valid JSON object (dictionary).")
                 return None
            return hitl_inputs
        else:
            # Handle exhausted or no pre-provided inputs
            if provided_hitl_inputs and hitl_input_iterator >= len(provided_hitl_inputs):
                logger.warning(f"Pre-provided HITL inputs exhausted for run {run_id} (Step {hitl_input_iterator + 1}).")
                print("\n--- Pre-provided HITL inputs exhausted --- --- Waiting for Human Input --- --- --- --- --- --- ---")
            logger.info(f"Prompting user for HITL input for run {run_id}, job {hitl_job.id} (Step {hitl_input_iterator + 1}).")

            # --- User Prompting Logic ---
            print("\n" + "="*30)
            print("--- Waiting for Human Input ---")
            print(f"Workflow Run ID: {run_id}")
            print(f"HITL Step Index: {hitl_input_iterator + 1}")
            print(f"HITL Job ID: {hitl_job.id}")
            print(f"Run ID requiring input: {run_id}")
            print("--- Request Details (Data passed to HITL node) ---")
            try:
                print(json.dumps(hitl_job.request_details, indent=2, default=str))
            except TypeError as e:
                logger.error(f"Failed to serialize HITL request_details: {e}")
                print(f"(Could not display request details: {e}) Raw: {hitl_job.request_details}")
            print("--- Expected Response Schema ---")
            try:
                print(json.dumps(hitl_job.response_schema, indent=2))
            except TypeError as e:
                logger.error(f"Failed to serialize HITL response_schema: {e}")
                print(f"(Could not display response schema: {e}) Raw: {hitl_job.response_schema}")
            print("="*30)
            print("\nPlease provide the response as a valid JSON string and press Enter:")

            while True:
                try:
                    user_input_str = input("> ")
                    user_inputs = json.loads(user_input_str)
                    if not isinstance(user_inputs, dict):
                        print("Invalid input: Please provide a valid JSON object (e.g., {\"key\": \"value\"}). Try again.")
                        logger.warning("User provided non-dictionary JSON for HITL input.")
                        continue
                    logger.info(f"Received HITL input from user for run {run_id}.")
                    return user_inputs
                except json.JSONDecodeError as e:
                    print(f"Invalid JSON format: {e}. Please try again.")
                    logger.warning(f"User provided invalid JSON for HITL input: {e}")
                except EOFError:
                    print("\nInput stream closed. Cannot get user input.")
                    logger.error("EOFError received while waiting for user HITL input.")
                    return None
                except KeyboardInterrupt:
                     print("\nKeyboard interrupt received. Aborting HITL input.")
                     logger.warning("KeyboardInterrupt received while waiting for user HITL input.")
                     return None
                except Exception as e:
                    print(f"An unexpected error occurred while reading input: {e}")
                    logger.exception("Error reading user HITL input.")
                    return None

    async def _handle_hitl_step(
        self,
        run_id: uuid.UUID,
        hitl_input_iterator: int,
        provided_hitl_inputs: Optional[List[Dict[str, Any]]],
        on_behalf_of_user_id: Optional[uuid.UUID] = None
    ) -> Tuple[bool, int]:
        """Internal helper to fetch HITL job details and submit response."""
        logger.info(f"Run {run_id} is WAITING_HITL. Fetching job details for step {hitl_input_iterator + 1}...")
        print(f"\n--- Run {run_id} paused for HITL (Step {hitl_input_iterator + 1}) ---")

        next_iterator_index = hitl_input_iterator

        try:
            pending_job = await self._hitl_client.get_latest_pending_hitl_job(run_id=run_id)
            if not pending_job:
                logger.error(f"Could not find pending HITL job for run {run_id}. Cannot resume.")
                print(f"   ✗ Error: Could not find pending HITL job for run {run_id}.")
                return False, hitl_input_iterator

            logger.info(f"Found pending HITL job {pending_job.id} for run {run_id}.")
            print(f"   ✓ Found pending HITL job: {pending_job.id} (Run: {run_id})")

            hitl_response_inputs = await self._get_hitl_input(
                run_id, pending_job, hitl_input_iterator, provided_hitl_inputs
            )

            if hitl_response_inputs is None:
                logger.error(f"Failed to obtain HITL input for run {run_id}, job {pending_job.id}.")
                print("   ✗ Error: Failed to obtain HITL input. Run cannot be resumed automatically.")
                return False, hitl_input_iterator

            next_iterator_index = hitl_input_iterator + 1

            logger.info(f"Submitting HITL response for run {run_id}, job {pending_job.id}...")
            print(f"\n   Submitting response to resume run {run_id}...")
            try:
                print(f"   Inputs being sent: {json.dumps(hitl_response_inputs, indent=2)}")
            except TypeError as e:
                 logger.error(f"Failed to serialize HITL response inputs for display: {e}")
                 print(f"(Could not display inputs being sent due to serialization error: {e})")

            resumed_run_status = await self._run_client.submit_run(
                resume_run_id=run_id,
                inputs=hitl_response_inputs,
                on_behalf_of_user_id=on_behalf_of_user_id
            )

            if resumed_run_status:
                logger.info(f"Resume request submitted for run {run_id}. Current status: {resumed_run_status.status}")
                print(f"   ✓ Resume request submitted. Run status is now: {resumed_run_status.status}")
                await asyncio.sleep(1)
                return True, next_iterator_index
            else:
                logger.error(f"Failed to submit resume request via API for run {run_id}.")
                print(f"   ✗ Error: Failed to submit resume request for run {run_id}.")
                return False, next_iterator_index

        except AuthenticationError as e:
             logger.exception(f"Authentication error during HITL handling for run {run_id}: {e}")
             print(f"   ✗ Authentication Error during HITL step: {e}")
             return False, hitl_input_iterator
        except Exception as e:
            logger.exception(f"An error occurred while handling HITL step for run {run_id}: {e}")
            print(f"   ✗ Unexpected Error handling HITL step: {e}")
            return False, next_iterator_index

    def _print_event(self, event: event_schemas.WorkflowBaseEvent, last_event: event_schemas.WorkflowBaseEvent, event_types_to_print: List[event_schemas.WorkflowBaseEvent] = EVENT_TYPES_TO_PRINT):
        """Formats and prints a single workflow event to stdout."""
        try:
            event_type_str = event.event_type.value if hasattr(event, 'event_type') and event.event_type else type(event).__name__
            node_id_str = f" (Node: {event.node_id})" if hasattr(event, 'node_id') and event.node_id else ""
            ts_str = event.timestamp.isoformat() if hasattr(event, 'timestamp') and event.timestamp else 'No Timestamp'
            if (not isinstance(event, event_schemas.MessageStreamChunk)) or (last_event.event_type != event.event_type):
                print(f"\n\n\n\n[{ts_str}] Event: {event_type_str}{node_id_str}\n\n\n\n")
            
            is_printable_event = any(isinstance(event, event_type) for event_type in event_types_to_print)
            if not is_printable_event:
                return
            
            if isinstance(event, event_schemas.WorkflowRunNodeOutputEvent):
                try:
                    print(f"  Payload: {json.dumps(event.payload, indent=2, default=str)}")
                except Exception as json_err:
                    print(f"  Payload: (Could not serialize: {json_err}) {event.payload}")
            elif isinstance(event, event_schemas.MessageStreamChunk):
                # Special handling for message chunks for continuous output
                if hasattr(event, 'message') and hasattr(event.message, 'content'):
                    # Print content directly without newline, flushing to ensure immediate visibility
                    print(event.message.content, end='', flush=True)
                else:
                    # Fallback if structure is different
                    msg_content = str(event.message) if hasattr(event, 'message') else '(no message content)'
                    print(f"\n  Chunk: {msg_content}") # Print with newline if not content chunk
            elif isinstance(event, event_schemas.WorkflowRunStatusUpdateEvent):
                print(f"  Status: {event.status.value}" + (f", Error: {event.error_message}" if event.error_message else ""))
            elif isinstance(event, event_schemas.HITLRequestEvent):
                prompt_str = str(event.user_prompt) if hasattr(event, 'user_prompt') else '(no prompt)'
                schema_str = str(event.request_data_schema) if hasattr(event, 'request_data_schema') else '(no schema)'
                print(f"  HITL Request: User Prompt: {prompt_str}, Schema: {schema_str}")
            elif isinstance(event, event_schemas.ToolCallEvent):
                print(f"  Tool Call: {event.tool_name} (ID: {event.tool_call_id}) -- status: {event.status}")
            # Add more specific event type printing if needed
            # else: # Optional: print generic payload if not handled above
            #     if hasattr(event, 'payload') and event.payload:
            #         try:
            #             print(f"  Payload: {json.dumps(event.payload, indent=2, default=str)}")
            #         except Exception:
            #             print(f"  Payload: {event.payload}")
        except Exception as print_err:
            logger.error(f"Error formatting event for printing: {print_err}")
            print(f"\n  (Error printing event details: {event})")

    async def _fetch_and_print_new_events(
        self,
        run_id: uuid.UUID,
        last_event_timestamp: Optional[datetime],
        last_event: Optional[event_schemas.WorkflowBaseEvent] = None
    ) -> Tuple[Optional[datetime], Optional[event_schemas.WorkflowBaseEvent]]:
        """Fetches new events from the stream, prints them, and returns the latest timestamp."""
        latest_timestamp_in_batch = last_event_timestamp
        try:
            event_stream = await self._run_client.get_run_stream(run_id)
            if event_stream:
                new_events = []
                for event in event_stream:
                    # Ensure timestamp exists and is timezone-aware for comparison
                    event_ts = getattr(event, 'timestamp', None)
                    if event_ts:
                        # Make naive timestamps timezone-aware (assume UTC)
                        if event_ts.tzinfo is None:
                            event_ts = event_ts.replace(tzinfo=timezone.utc)

                        # Compare with last timestamp (also ensure it's tz-aware)
                        if last_event_timestamp is None or event_ts > last_event_timestamp:
                            new_events.append(event)
                            # Update latest timestamp seen in this batch
                            if latest_timestamp_in_batch is None or event_ts > latest_timestamp_in_batch:
                                latest_timestamp_in_batch = event_ts
                    else:
                         logger.warning(f"Event missing timestamp: {event}")

                # Sort new events by timestamp before printing for chronological order
                new_events.sort(key=lambda e: getattr(e, 'timestamp', datetime.min.replace(tzinfo=timezone.utc)))

                if new_events:
                    # print(f"\n--- Processing {len(new_events)} new event(s) for run {run_id} --- ") # Debug print
                    for event in new_events:
                        self._print_event(event, last_event=last_event)
                        last_event = event
                    # Print a newline after a batch of message chunks to separate from subsequent non-chunk events
                    if any(isinstance(e, event_schemas.MessageStreamChunk) for e in new_events):
                        print()

        except Exception as e:
            logger.error(f"Error fetching or processing event stream for run {run_id}: {e}")
            # Don't print error to stdout during streaming, rely on logs

        return latest_timestamp_in_batch, last_event # Return the timestamp of the latest processed event

    async def _stream_events_task(
        self,
        run_id: uuid.UUID,
        stop_event: asyncio.Event,
        poll_interval_sec: int
    ):
        """Background task to periodically fetch and print new events."""
        last_event_timestamp: Optional[datetime] = None
        logger.info(f"Starting event streaming task for run {run_id}.")
        last_event = None
        while not stop_event.is_set():
            try:
                last_event_timestamp, last_event = await self._fetch_and_print_new_events(
                    run_id,
                    last_event_timestamp,
                    last_event
                )
                # Wait for the specified interval or until stop_event is set
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval_sec)
            except asyncio.TimeoutError:
                # Timeout occurred, continue polling
                continue
            except Exception as e:
                logger.exception(f"Error in event streaming task for run {run_id}: {e}")
                # Avoid task crashing, wait before retrying
                await asyncio.sleep(poll_interval_sec)
        logger.info(f"Stopping event streaming task for run {run_id}.")
        # Print a final newline if the last streamed output was a message chunk without one
        print() # Ensures the next stdout starts on a new line

    async def submit_and_monitor_run(
        self,
        workflow_id: Optional[uuid.UUID] = None,
        graph_schema: Optional[Dict[str, Any]] = None,
        inputs: Dict[str, Any] = {},
        hitl_inputs: Optional[List[Dict[str, Any]]] = None,
        poll_interval_sec: int = 3,
        timeout_sec: int = 300,
        stream_intermediate_results: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        thread_id: Optional[uuid.UUID] = None
    ) -> Tuple[Optional[wf_schemas.WorkflowRunRead], Optional[Dict[str, Any]]]:
        """
        Submits a workflow run and monitors its execution until completion,
        failure, cancellation, or timeout, handling HITL steps interactively.

        Can either run an existing workflow specified by `workflow_id` or
        create a new one from `graph_schema` before running.

        Optionally streams intermediate results (node outputs, status changes) to stdout.

        Args:
            workflow_id: The UUID of an *existing* workflow definition to run.
                         Mutually exclusive with `graph_schema`.
            graph_schema: A dictionary representing the workflow graph schema.
                          If provided, a new workflow will be created using this
                          schema before the run. The created workflow will be
                          automatically deleted afterwards. Mutually exclusive
                          with `workflow_id`.
            inputs: The initial inputs required by the workflow's input node.
            hitl_inputs: An optional list of dictionaries. Each dictionary represents
                         the inputs for a sequential HITL step encountered during the run.
                         If this list is provided, the client uses these inputs in order.
                         If the list is exhausted or not provided, the user is prompted
                         via the console for subsequent HITL steps.
            poll_interval_sec: The interval (in seconds) between status checks and stream polls.
            timeout_sec: The maximum time (in seconds) to wait for the run to reach a
                         terminal state (COMPLETED, FAILED, CANCELLED).
            stream_intermediate_results: If True, polls the event stream in the background
                                         and prints new events to stdout.
            on_behalf_of_user_id: Optional user ID to act on behalf of. This is typically
                                 used by superusers/admins to perform operations as if they
                                 were another user.
            thread_id: Optional thread ID to resume from existing thread to retain message history.

        Returns:
            A tuple containing:
            - Optional[wf_schemas.WorkflowRunRead]: The final status summary object of the run.
            - Optional[Dict[str, Any]]: The final outputs of the workflow if it completed successfully.
            Returns (None, None) if the initial submission fails, workflow creation fails,
            or monitoring times out before a definitive state is reached.

        Raises:
            ValueError: If both or neither of `workflow_id` and `graph_schema` are provided.
        """
        if (workflow_id is None and graph_schema is None) or \
           (workflow_id is not None and graph_schema is not None):
            raise ValueError("Exactly one of 'workflow_id' or 'graph_schema' must be provided.")

        created_run_id: Optional[uuid.UUID] = None
        workflow_id_to_run: Optional[uuid.UUID] = workflow_id
        workflow_created_by_client: bool = False
        workflow_to_cleanup_id: Optional[uuid.UUID] = None
        final_status_obj: Optional[wf_schemas.WorkflowRunRead] = None
        final_outputs: Optional[Dict[str, Any]] = None
        streaming_task: Optional[asyncio.Task] = None
        stop_streaming_event = asyncio.Event()

        start_time = time.monotonic()
        hitl_input_iterator = 0

        try:
            # 1. Create Workflow if graph_schema is provided
            if graph_schema:
                logger.info("Graph schema provided. Attempting to create workflow...")
                print("\n--- Creating temporary workflow from provided schema ---")
                
                # <-- ADD VALIDATION STEP HERE -->
                logger.info("Validating provided graph schema before creation...")
                print("   Validating schema via API...")
                validation_result = await self._workflow_client.validate_graph_api(graph_config=graph_schema)
                if not validation_result or not validation_result.is_valid:
                    logger.error(f"Provided graph schema failed validation: {validation_result.errors if validation_result else 'Validation request failed'}")
                    print(f"   ✗ Error: Graph schema validation failed. Errors: {json.dumps(validation_result.errors if validation_result else {}, indent=2)}")
                    return None, None
                logger.info("Graph schema validation passed.")
                print("   ✓ Schema validation passed.")
                # <-- END VALIDATION STEP -->

                try:
                    workflow_name = f"InteractiveClientWorkflow-{uuid.uuid4().hex[:8]}"
                    created_workflow = await self._workflow_client.create_workflow(
                        name=workflow_name, graph_config=graph_schema
                    )
                    if created_workflow and created_workflow.id:
                        workflow_id_to_run = created_workflow.id
                        workflow_created_by_client = True
                        workflow_to_cleanup_id = workflow_id_to_run
                        logger.info(f"Successfully created temporary workflow {workflow_name} with ID: {workflow_id_to_run}")
                        print(f"   ✓ Created workflow: {workflow_name} (ID: {workflow_id_to_run})")
                    else:
                        logger.error("Failed to create workflow from the provided schema.")
                        print("   ✗ Error: Workflow creation failed.")
                        return None, None
                except Exception as create_err:
                    logger.exception(f"Error during workflow creation: {create_err}")
                    print(f"   ✗ Error during workflow creation: {create_err}")
                    return None, None

            if not workflow_id_to_run:
                 logger.error("Workflow ID is missing before run submission.")
                 print("   ✗ Internal Error: Workflow ID not available.")
                 return None, None

            # 2. Submit the initial workflow run request
            logger.info(f"Attempting to submit run for workflow ID: {workflow_id_to_run}...")
            submitted_run = await self._run_client.submit_run(
                workflow_id=workflow_id_to_run, 
                inputs=inputs,
                on_behalf_of_user_id=on_behalf_of_user_id,
                thread_id=thread_id
            )
            if not submitted_run:
                logger.error(f"Failed to submit initial workflow run for workflow {workflow_id_to_run}.")
                print("   ✗ Initial run submission failed.")
                return None, None

            created_run_id = submitted_run.id
            current_status = submitted_run.status
            print(f"--- Run submitted successfully: ID = {created_run_id} (Initial Status: {current_status}) ---")
            logger.info(f"Run {created_run_id} submitted for workflow {workflow_id_to_run}. Initial status: {current_status}")

            # 3. Start background event streaming if requested
            if stream_intermediate_results:
                print("--- Starting background event streaming --- ")
                streaming_task = asyncio.create_task(
                    self._stream_events_task(created_run_id, stop_streaming_event, poll_interval_sec)
                )

            # 4. Enter the main status monitoring loop
            while True:
                # --- Timeout Check ---
                elapsed_time = time.monotonic() - start_time
                if elapsed_time > timeout_sec:
                    logger.warning(f"Run {created_run_id} timed out after {elapsed_time:.1f} seconds.")
                    print(f"\n--- Run {created_run_id} timed out ---")
                    try:
                        final_status_obj = await self._run_client.get_run_status(created_run_id)
                        final_outputs = final_status_obj.outputs if final_status_obj else None
                    except Exception as final_status_err:
                         logger.error(f"Failed to get final status for timed-out run {created_run_id}: {final_status_err}")
                    break # Exit the loop on timeout

                # --- Status Check --- #
                try:
                    current_run_status_obj = await self._run_client.get_run_status(created_run_id)
                    if not current_run_status_obj:
                        logger.warning(f"Failed to retrieve status for run {created_run_id} via API. Waiting before retry.")
                        print(f"\n--- Warning: Could not retrieve status for run {created_run_id}. Retrying... ---")
                        await asyncio.sleep(poll_interval_sec)
                        continue

                    latest_status = current_run_status_obj.status
                    latest_error_message = current_run_status_obj.error_message
                    fetched_outputs = current_run_status_obj.outputs

                except Exception as status_err:
                    logger.error(f"Error retrieving status for run {created_run_id}: {status_err}. Waiting before retry.")
                    print(f"\n--- Error retrieving status ({status_err}). Retrying... ---")
                    await asyncio.sleep(poll_interval_sec)
                    continue

                # --- State Handling Logic --- #
                logger.debug(f"Run {created_run_id} main poll status: {latest_status}")

                # Check for Terminal States
                if latest_status in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED):
                    final_status_obj = current_run_status_obj
                    final_outputs = fetched_outputs
                    end_message = f"Run {created_run_id} finished with status: {latest_status}"
                    if latest_status == WorkflowRunStatus.COMPLETED:
                         logger.info(end_message)
                         print(f"\n--- {end_message} ---")
                    elif latest_status == WorkflowRunStatus.FAILED:
                         error_msg = latest_error_message or "No error message provided."
                         logger.error(f"{end_message}. Error: {error_msg}")
                         print(f"\n--- {end_message} ---")
                         print(f"   Error: {error_msg}")
                    else: # Cancelled
                         logger.warning(end_message)
                         print(f"\n--- {end_message} ---")
                    break # Exit loop on terminal state

                # Handle HITL State
                elif latest_status == WorkflowRunStatus.WAITING_HITL:
                    # Signal streaming task to pause/stop printing potentially confusing intermediate states during HITL prompt
                    # (Optional enhancement: could pause the task instead of just letting it run) 
                    handled, next_iterator_index = await self._handle_hitl_step(
                        created_run_id, hitl_input_iterator, hitl_inputs, on_behalf_of_user_id
                    )
                    hitl_input_iterator = next_iterator_index

                    if not handled:
                        final_status_obj = current_run_status_obj # Store the WAITING_HITL state
                        final_outputs = fetched_outputs
                        logger.error(f"Failed to handle HITL step for run {created_run_id}. Aborting monitoring.")
                        print(f"\n--- Failed to handle HITL for run {created_run_id}. Stopping monitoring. ---")
                        break # Exit loop if HITL handling fails
                    # If handled=True, loop continues to poll status after resume.

                # Handle Non-Terminal, Non-HITL States
                else:
                    # Log progress (only if not streaming, avoids duplicate status messages)
                    if not stream_intermediate_results:
                         print(f"   Run {created_run_id} status: {latest_status}. Waiting {poll_interval_sec}s...")
                    await asyncio.sleep(poll_interval_sec)

        except AuthenticationError as e:
             logger.exception(f"Authentication error: {e}")
             print(f"Authentication Error: {e}")
             return None, None
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            print(f"An unexpected error occurred: {e}")
            if created_run_id:
                try:
                    final_status_obj = await asyncio.wait_for(self._run_client.get_run_status(created_run_id), timeout=5)
                    final_outputs = final_status_obj.outputs if final_status_obj else None
                except Exception:
                    pass # Ignore errors getting final status after another error
            return final_status_obj, final_outputs
        finally:
            # --- Stop and Cleanup Streaming Task --- #
            stop_streaming_event.set() # Signal the streaming task to stop
            if streaming_task:
                logger.info("Attempting to cancel event streaming task...")
                try:
                    streaming_task.cancel()
                    await asyncio.gather(streaming_task, return_exceptions=True)
                    logger.info("Event streaming task cancelled.")
                except asyncio.CancelledError:
                     logger.info("Event streaming task already cancelled.")
                except Exception as task_cancel_err:
                    logger.exception(f"Error cancelling streaming task: {task_cancel_err}")

            # --- Cleanup Workflow (if created) --- #
            if workflow_created_by_client and workflow_to_cleanup_id:
                logger.info(f"Cleaning up workflow {workflow_to_cleanup_id} created by client...")
                print(f"\n--- Cleaning up temporary workflow {workflow_to_cleanup_id} ---")
                try:
                    deleted = await self._workflow_client.delete_workflow(workflow_to_cleanup_id)
                    print(f"   {'✓' if deleted else '✗'} Deleted workflow.")
                except Exception as cleanup_err:
                    logger.exception(f"Error during workflow cleanup: {cleanup_err}")
                    print(f"   ✗ Workflow cleanup failed: {cleanup_err}")

        return final_status_obj, final_outputs


# --- Reusable Test Execution Helper --- #

class SetupDocInfo(TypedDict):
    """Information required to set up a prerequisite document for a test."""
    namespace: str
    docname: str
    initial_data: Any
    is_shared: bool
    is_versioned: bool
    initial_version: Optional[str] # Required if is_versioned is True
    is_system_entity: Optional[bool]

class CleanupDocInfo(TypedDict):
    """Information required to identify a document for cleanup after a test."""
    namespace: str
    docname: str
    is_shared: bool
    is_versioned: bool
    is_system_entity: Optional[bool]


class SetupSchemaInfo(TypedDict):
    """Information required to set up a prerequisite schema template for a test."""
    name: str
    json_schema: Dict[str, Any]
    description: Optional[str]
    version: str # Version is required for creation
    is_public: Optional[bool]
    is_system_entity: Optional[bool]

class CleanupSchemaInfo(TypedDict):
    """Information required to identify a schema template for cleanup after a test."""
    # We'll store the ID after creation for reliable cleanup
    id: uuid.UUID
    name: str # Store name for logging clarity


async def run_workflow_test(
    test_name: str,
    workflow_graph_schema: Optional[Dict[str, Any]] = None,
    workflow_id: Optional[Union[str, uuid.UUID]] = None,
    workflow_name: Optional[str] = None,
    workflow_version: Optional[str] = None,
    workflow_key: Optional[str] = None,
    initial_inputs: Dict[str, Any] = {},
    expected_final_status: WorkflowRunStatus = WorkflowRunStatus.COMPLETED,
    hitl_inputs: Optional[List[Dict[str, Any]]] = None,
    setup_docs: Optional[List[SetupDocInfo]] = None,
    cleanup_docs: Optional[List[CleanupDocInfo]] = None,
    setup_schemas: Optional[List[SetupSchemaInfo]] = None,
    cleanup_docs_created_by_setup: bool = True,
    cleanup_created_schemas: bool = True,
    validate_output_func: Optional[Callable[[Optional[Dict[str, Any]]], Awaitable[bool]]] = None,
    stream_intermediate_results: bool = True,
    dump_artifacts: bool = True,
    poll_interval_sec: int = 3,
    timeout_sec: int = 600,
    on_behalf_of_user_id: Optional[uuid.UUID] = None,
    thread_id: Optional[uuid.UUID] = None
) -> Tuple[Optional[wf_schemas.WorkflowRunRead], Optional[Dict[str, Any]]]:
    """
    Runs a complete workflow test, including setup, execution, validation, and cleanup.

    This helper function encapsulates the common pattern of setting up prerequisite
    customer data, running a workflow, validating its outcome, and cleaning up
    any created or specified data.

    Args:
        test_name: A descriptive name for the test, used in logging and print statements.
        workflow_graph_schema: The workflow graph schema definition to execute. Mutually exclusive with workflow_id, workflow_name, and workflow_key.
        workflow_id: The ID of an existing workflow to execute. Mutually exclusive with workflow_graph_schema, workflow_name, and workflow_key.
        workflow_name: The name of an existing workflow to search for and execute. If provided, will search for the workflow and use its ID.
                      If workflow_version is also provided, will search for that specific version. Mutually exclusive with 
                      workflow_graph_schema, workflow_id, and workflow_key.
        workflow_version: Optional version tag to filter workflows when searching by name. Only used when workflow_name is provided.
        workflow_key: The key of a workflow in app artifacts to fetch and execute. Will retrieve the workflow ID from the app artifacts.
                     Mutually exclusive with workflow_graph_schema, workflow_id, and workflow_name.
        initial_inputs: A dictionary containing the initial inputs for the workflow run.
        expected_final_status: The WorkflowRunStatus enum value expected at the end
                               of the run. Defaults to COMPLETED.
        hitl_inputs: An optional list of dictionaries, where each dictionary represents
                     the inputs for a Human-in-the-Loop (HITL) step. The list order
                     determines the sequence in which inputs are provided.
        setup_docs: An optional list of SetupDocInfo dictionaries. Each dictionary
                    specifies a customer data document to be created or ensured
                    exists before the workflow execution. The function attempts to
                    initialize/create these documents idempotently.
        cleanup_docs: An optional list of CleanupDocInfo dictionaries. Each dictionary
                      specifies a customer data document to be deleted after the
                      workflow execution, regardless of whether it was created by
                      the setup phase. Documents successfully created by the setup
                      phase are automatically added to the cleanup list.
        setup_schemas: An optional list of SetupSchemaInfo dictionaries. Each dictionary
                       specifies a schema template to be created or ensured
                       exists before the workflow execution. The function attempts
                       to create these schemas idempotently (logs warning if exists).
        cleanup_created_schemas: If True (default), schema templates successfully created
                               during the `setup_schemas` phase will be deleted
                               automatically during the cleanup phase.
        validate_output_func: An optional asynchronous function that accepts the final
                              workflow outputs dictionary (or None if the workflow didn't
                              complete successfully) and returns True if the outputs are
                              valid according to custom logic, False otherwise. If this
                              function raises an exception, it's treated as a validation failure.
        stream_intermediate_results: If True, events and intermediate results from the
                                   workflow run will be printed to standard output.
        dump_artifacts: If True, saves logs and state data to files in the data directory
                        with filenames that include the test name and run ID.
        poll_interval_sec: The interval in seconds at which the client polls the API
                           for workflow status updates.
        timeout_sec: The maximum time in seconds to wait for the workflow run to reach
                     a terminal state.
        on_behalf_of_user_id: Optional user ID to act on behalf of. This is typically
                             used by superusers/admins to perform operations as if they
                             were another user.
        thread_id: Optional thread ID to resume from existing thread to retain message history.

    Returns:
        A tuple containing:
        - The final WorkflowRunRead Pydantic object representing the run's state (or None
          if the run couldn't be started or monitored properly).
        - A dictionary containing the final outputs of the workflow run (or None if the
          run did not complete successfully or produced no outputs).

    Raises:
        AuthenticationError: If authentication with the backend fails.
        RuntimeError: If critical setup steps fail (e.g., cannot create a required document).
        ValueError: If more than one way of specifying the workflow is provided, or if 
                   none of the workflow specification methods are provided.
        AssertionError: If the final workflow status does not match `expected_final_status`,
                        or if `validate_output_func` is provided and returns False or raises
                        an exception.
        Exception: For any other unexpected errors during the process.

    Key Design Decisions & Caveats:
    - **Idempotent Setup:** The setup phase tries to create documents but logs if they already
      exist. It uses `initialize_versioned_document` which might fail if the doc exists
      with a different initial state (this is desired behavior). For unversioned docs,
      `create_or_update_unversioned_document` is used. Schema setup logs a warning
      if the schema already exists.
    - **Automatic Cleanup:** Documents successfully created during the `setup_docs` phase are
      automatically added to the cleanup list to ensure test isolation. Schema templates
      created during `setup_schemas` are cleaned up if `cleanup_created_schemas` is True.
    - **Cleanup Best Effort:** Cleanup attempts to delete specified documents but logs warnings
      if deletion fails, rather than failing the entire test. This prevents transient cleanup
      issues from masking actual workflow execution failures. Critical cleanup failures
      (like auth errors) might still raise exceptions.
    - **Error Handling:** Errors during setup or execution/validation are raised immediately
      to fail the test. Cleanup errors are logged as warnings.
    - **TypedDicts:** `SetupDocInfo` and `CleanupDocInfo` are used for clarity and type safety
      when defining documents for setup and cleanup.
    - **Workflow Resolution:** Workflows can be specified by providing a graph schema directly, 
      by ID, by name (with optional version), or by a workflow key from app artifacts. The function
      will resolve the appropriate workflow ID before execution.
    """
    # Validate that exactly one workflow specification method is provided
    workflow_spec_count = sum(1 for spec in [workflow_graph_schema, workflow_id, workflow_name, workflow_key] if spec is not None)
    if workflow_spec_count == 0:
        raise ValueError("At least one of 'workflow_graph_schema', 'workflow_id', 'workflow_name', or 'workflow_key' must be provided.")
    if workflow_spec_count > 1:
        raise ValueError("Only one of 'workflow_graph_schema', 'workflow_id', 'workflow_name', or 'workflow_key' can be provided.")
    
    print(f"\n{'='*20} Starting Test: {test_name} {'='*20}")
    logger.info(f"Starting workflow test: {test_name}")

    # Store info about documents created by the setup phase for automatic cleanup
    docs_created_by_setup: List[CleanupDocInfo] = []
    # Store info about schemas created by the setup phase for automatic cleanup
    schemas_created_by_setup: List[CleanupSchemaInfo] = []
    # Variables to hold the final results
    final_run_status_obj: Optional[wf_schemas.WorkflowRunRead] = None
    final_run_outputs: Optional[Dict[str, Any]] = None

    try:
        # Use a single authenticated session for setup and execution if possible
        async with AuthenticatedClient() as auth_client:
            logger.info(f"[{test_name}] Authentication successful for main test phases.")
            interactive_client = InteractiveWorkflowRunClient(auth_client)
            data_tester = CustomerDataTestClient(auth_client)
            # Instantiate template client needed for schema setup/cleanup
            from kiwi_client.template_client import TemplateTestClient
            template_tester = TemplateTestClient(auth_client)
            # Instantiate workflow client for validation
            workflow_tester = WorkflowTestClient(auth_client) # Added for validation
            # Instantiate app artifact client for workflow key lookup
            from kiwi_client.app_artifact_client import AppArtifactTestClient
            artifact_tester = AppArtifactTestClient(auth_client)

            # --- 1. Setup Phase --- #

            # --- 1.1 Resolve workflow_id if using workflow_name or workflow_key --- #
            resolved_workflow_id = workflow_id

            # Helper function to search for workflow by name and version
            async def search_workflow_by_name(name: str, version: Optional[str] = None) -> Optional[wf_schemas.WorkflowRead]:
                """Search for a workflow by name and optional version tag."""
                search_results = await workflow_tester.search_workflows(
                    name=name,
                    version_tag=version,
                    include_public=True,
                    include_system_entities=True
                )
                
                if not search_results or len(search_results) == 0:
                    return None
                
                if len(search_results) > 1:
                    # If multiple workflows found, use the most recently updated one but log a warning
                    logger.warning(f"[{test_name}] Multiple workflows ({len(search_results)}) found with name '{name}'. Using the most recently updated one.")
                    print(f"   ⚠ Multiple workflows ({len(search_results)}) found with name '{name}'. Using the most recently updated one.")
                
                # Return the first (most recently updated) workflow
                return search_results[0]

            # Resolve workflow by name or key
            if workflow_name or workflow_key:
                if workflow_name:
                    # Search for workflow by name
                    print(f"\n--- [{test_name}] Setup: Searching for workflow by name: {workflow_name} {f'(version: {workflow_version})' if workflow_version else ''} ---")
                    found_workflow = await search_workflow_by_name(workflow_name, workflow_version)
                    
                    if not found_workflow:
                        error_msg = f"No workflow found with name '{workflow_name}'{f' and version {workflow_version}' if workflow_version else ''}"
                        logger.error(f"[{test_name}] {error_msg}")
                        print(f"   ✗ {error_msg}")
                        raise RuntimeError(error_msg)
                    
                    resolved_workflow_id = found_workflow.id
                    logger.info(f"[{test_name}] Found workflow: ID={resolved_workflow_id}, Name={found_workflow.name}")
                    print(f"   ✓ Found workflow: {found_workflow.name} (ID: {resolved_workflow_id})")
                
                elif workflow_key:
                    # Fetch workflow by key from app artifacts
                    print(f"\n--- [{test_name}] Setup: Fetching workflow by key: {workflow_key} ---")
                    
                    # First get workflow processing info to get the name and version
                    workflow_info_req = aa_schemas.GetWorkflowRequest(workflow_key=workflow_key)
                    workflow_info = await artifact_tester.get_workflow(workflow_info_req)
                    
                    if not workflow_info:
                        error_msg = f"Failed to get workflow info for key '{workflow_key}'"
                        logger.error(f"[{test_name}] {error_msg}")
                        print(f"   ✗ {error_msg}")
                        raise RuntimeError(error_msg)
                    
                    workflow_name_from_key = workflow_info.original_workflow_name
                    workflow_version_from_key = workflow_info.original_workflow_version
                    
                    # Now search for the workflow by name and version
                    logger.info(f"[{test_name}] Searching for workflow named '{workflow_name_from_key}' with version '{workflow_version_from_key}'")
                    print(f"   Searching for workflow: {workflow_name_from_key} (version: {workflow_version_from_key if workflow_version_from_key else 'any'})")
                    
                    found_workflow = await search_workflow_by_name(workflow_name_from_key, workflow_version_from_key)
                    
                    if not found_workflow:
                        error_msg = f"No workflow found with name '{workflow_name_from_key}'{f' and version {workflow_version_from_key}' if workflow_version_from_key else ''} for key '{workflow_key}'"
                        logger.error(f"[{test_name}] {error_msg}")
                        print(f"   ✗ {error_msg}")
                        raise RuntimeError(error_msg)
                    
                    resolved_workflow_id = found_workflow.id
                    logger.info(f"[{test_name}] Found workflow for key '{workflow_key}': ID={resolved_workflow_id}, Name={found_workflow.name}")
                    print(f"   ✓ Found workflow: {found_workflow.name} (ID: {resolved_workflow_id})")

            # --- 1a. Setup Documents --- #
            if setup_docs:
                print(f"\n--- [{test_name}] Setup: Ensuring prerequisite documents exist ---")
                for doc_info in setup_docs:
                    # Extract document details for clarity
                    ns: str = doc_info['namespace']
                    dn: str = doc_info['docname']
                    is_shared: bool = doc_info['is_shared']
                    is_versioned: bool = doc_info['is_versioned']
                    is_system: bool = doc_info.get('is_system_entity', False)
                    initial_data: Any = doc_info['initial_data']
                    initial_version: Optional[str] = doc_info.get('initial_version') # Will be None if not provided

                    # Construct a user-friendly ID string for logging
                    doc_id_str = f"{'System/' if is_system else ''}{'Shared/' if is_shared else 'User/'}{ns}/{dn}"
                    logger.info(f"[{test_name}] Ensuring document: {doc_id_str}")
                    print(f"   Ensuring {('Versioned' if is_versioned else 'Unversioned')} doc: {doc_id_str}...")

                    created_this_run = False # Flag to track if we performed a creation/initialization action
                    try:
                        # First check if the document already exists
                        metadata = await data_tester.get_document_metadata(
                            ns, dn, 
                            is_shared=is_shared, 
                            is_system_entity=is_system,
                            on_behalf_of_user_id=on_behalf_of_user_id
                        )
                        
                        if metadata:
                            # Document already exists
                            logger.info(f"[{test_name}] Document {doc_id_str} already exists, skipping creation.")
                            print(f"     ✓ Already exists.")
                            # continue
                            
                        # Document doesn't exist, proceed with creation
                        if is_versioned:
                            # --- Setup for Versioned Document --- # 
                            if initial_version is None:
                                # Enforce that initial_version is provided for versioned docs
                                raise ValueError(f"'initial_version' is required in SetupDocInfo for versioned document: {doc_id_str}")
                            
                            init_payload = wf_schemas.CustomerDataVersionedInitialize(
                                is_shared=is_shared,
                                initial_data=initial_data,
                                initial_version=initial_version,
                                is_system_entity=is_system,
                                on_behalf_of_user_id=on_behalf_of_user_id
                            )
                            # Attempt to initialize the versioned document
                            # This might return False if the document already exists 
                            init_result = await data_tester.initialize_versioned_document(ns, dn, init_payload)
                            if init_result:
                                logger.info(f"   ✓ [{test_name}] Initialized versioned document: {doc_id_str} (Version: {initial_version})")
                                print(f"     ✓ Initialized (Version: {initial_version})")
                                created_this_run = True
                            else:
                                # If initialization failed, check if it's because it already exists
                                # This helps distinguish between 'already exists' and other setup failures.
                                logger.warning(f"[{test_name}] Initialization returned False for {doc_id_str}. Checking existence...")
                                metadata = await data_tester.get_document_metadata(
                                    ns, dn, 
                                    is_shared=is_shared, 
                                    is_system_entity=is_system,
                                    on_behalf_of_user_id=on_behalf_of_user_id
                                )
                                if metadata and metadata.is_versioned:
                                    logger.info(f"   ✓ [{test_name}] Versioned document {doc_id_str} already exists.")
                                    print(f"     ✓ Already exists.")
                                    # Potentially check if existing version matches `initial_version` if needed? For now, just log existence.
                                else:
                                    # If it doesn't exist after failed init, something else is wrong.
                                    error_msg = f"Failed to initialize versioned doc {doc_id_str} and it does not appear to exist."
                                    logger.error(f"[{test_name}] {error_msg}")
                                    raise RuntimeError(error_msg)
                        else:
                            # --- Setup for Unversioned Document --- #
                            create_payload = wf_schemas.CustomerDataUnversionedCreateUpdate(
                                is_shared=is_shared,
                                data=initial_data,
                                is_system_entity=is_system,
                                on_behalf_of_user_id=on_behalf_of_user_id
                            )
                            # Attempt to create or update the unversioned document
                            # This returns True on success (create or update)
                            create_result = await data_tester.create_or_update_unversioned_document(ns, dn, create_payload)
                            if create_result:
                                # We don't know for sure if we *created* vs *updated*, but the state is now as desired.
                                logger.info(f"   ✓ [{test_name}] Created/Updated unversioned document: {doc_id_str}")
                                print(f"     ✓ Created/Updated.")
                                # We mark it as 'created_this_run' to ensure it's considered for cleanup,
                                # as an update might overwrite state from a previous failed run.
                                created_this_run = True
                            else:
                                # If create/update fails, this indicates a potential issue.
                                # Double-check existence just in case.
                                logger.warning(f"[{test_name}] Create/Update returned False for {doc_id_str}. Checking existence...")
                                metadata = await data_tester.get_document_metadata(
                                    ns, dn, 
                                    is_shared=is_shared, 
                                    is_system_entity=is_system,
                                    on_behalf_of_user_id=on_behalf_of_user_id
                                )
                                if metadata and not metadata.is_versioned:
                                    logger.info(f"   ✓ [{test_name}] Unversioned document {doc_id_str} exists despite create/update failure (unexpected). ")
                                    print(f"     ✓ Exists (despite reported C/U failure).")
                                else:
                                    error_msg = f"Failed to create/update unversioned doc {doc_id_str} and it does not appear to exist."
                                    logger.error(f"[{test_name}] {error_msg}")
                                    raise RuntimeError(error_msg)

                        # If we successfully initialized or created/updated, add to the auto-cleanup list.
                        if created_this_run:
                            docs_created_by_setup.append({
                                'namespace': ns,
                                'docname': dn,
                                'is_shared': is_shared,
                                'is_versioned': is_versioned,
                                'is_system_entity': is_system
                                # No data needed for cleanup info
                            })
                    except Exception as setup_err:
                        # Catch errors specific to setting up this document
                        logger.exception(f"[{test_name}] Error during setup for document {doc_id_str}: {setup_err}")
                        print(f"   ✗ [{test_name}] Critical Setup Error for {doc_id_str}: {setup_err}")
                        # Raising the error here halts the entire test because setup is prerequisite.
                        raise
            else:
                print(f"\n--- [{test_name}] Setup: No prerequisite documents specified ---")

            # --- 1b. Setup Schemas --- #
            if setup_schemas:
                print(f"\n--- [{test_name}] Setup: Ensuring prerequisite schema templates exist ---")
                for schema_info in setup_schemas:
                    # Extract schema details
                    name: str = schema_info['name']
                    version: str = schema_info['version']
                    json_schema: Dict[str, Any] = schema_info['json_schema']
                    description: Optional[str] = schema_info.get('description')
                    is_public: Optional[bool] = schema_info.get('is_public', False)
                    is_system: Optional[bool] = schema_info.get('is_system_entity', False)

                    # Construct a user-friendly ID string for logging
                    schema_id_str = f"{'System/' if is_system else 'Org/'}{name} (v{version})"
                    logger.info(f"[{test_name}] Ensuring schema template: {schema_id_str}")
                    print(f"   Ensuring Schema Template: {schema_id_str}...")

                    created_this_run = False
                    created_schema_id = None
                    try:
                        create_payload = wf_schemas.SchemaTemplateCreate(
                            name=name,
                            version=version,
                            description=description,
                            schema_definition=json_schema, # Adjusted field name based on schema
                            is_public=is_public,
                            is_system_entity=is_system,
                            schema_type=wf_schemas.SchemaType.JSON_SCHEMA # Assuming JSON schema
                        )
                        # Attempt to create the schema template
                        created_schema = await template_tester.create_schema_template(create_payload)

                        if created_schema and created_schema.id:
                            created_schema_id = created_schema.id
                            logger.info(f"   ✓ [{test_name}] Created schema template: {schema_id_str} (ID: {created_schema_id})")
                            print(f"     ✓ Created (ID: {created_schema_id})")
                            created_this_run = True
                        else:
                            # If creation failed, check if it already exists
                            logger.warning(f"[{test_name}] Schema template creation returned no result for {schema_id_str}. Checking existence...")
                            # Note: Search is often better than Get for checking existence to avoid 404 noise
                            search_query = wf_schemas.SchemaTemplateSearchQuery(
                                name=name, version=version, include_system_entities=True, include_public=True
                            )
                            existing_schemas = await template_tester.search_schema_templates(search_query)
                            if existing_schemas and any(s.name == name and s.version == version for s in existing_schemas):
                                logger.info(f"   ✓ [{test_name}] Schema template {schema_id_str} already exists.")
                                print(f"     ✓ Already exists.")
                                # Find the ID if possible for potential cleanup consistency, though not strictly needed
                                existing_schema = next((s for s in existing_schemas if s.name == name and s.version == version), None)
                                if existing_schema:
                                    created_schema_id = existing_schema.id
                            else:
                                # If it doesn't exist after failed creation, something else is wrong.
                                error_msg = f"Failed to create schema template {schema_id_str} and it does not appear to exist."
                                logger.error(f"[{test_name}] {error_msg}")
                                raise RuntimeError(error_msg)

                        # If we successfully created it, add to the auto-cleanup list.
                        if created_this_run and created_schema_id:
                            schemas_created_by_setup.append({
                                'id': created_schema_id,
                                'name': name
                            })

                    except Exception as setup_err:
                        # Catch errors specific to setting up this schema
                        logger.exception(f"[{test_name}] Error during setup for schema template {schema_id_str}: {setup_err}")
                        print(f"   ✗ [{test_name}] Critical Setup Error for {schema_id_str}: {setup_err}")
                        # Raising the error here halts the entire test because setup is prerequisite.
                        raise
            else:
                 print(f"\n--- [{test_name}] Setup: No prerequisite schema templates specified ---")

            # --- 1.c Validate Workflow Graph Schema (if provided) or verify workflow ID exists --- #
            if workflow_graph_schema:
                print(f"\n--- [{test_name}] Setup: Validating workflow graph schema ---")
                validation_result = await workflow_tester.validate_graph_api(workflow_graph_schema)
                if not validation_result or not validation_result.is_valid:
                    error_details = validation_result.errors if validation_result else {"error": "Validation request failed"}
                    error_msg = f"Workflow graph schema validation failed for test '{test_name}'. Errors: {json.dumps(error_details, indent=2)}"
                    logger.error(f"[{test_name}] {error_msg}")
                    print(f"   ✗ Validation Failed: {json.dumps(error_details, indent=2)}")
                    raise RuntimeError(error_msg) # Fail the test if schema is invalid
                else:
                    logger.info(f"[{test_name}] Workflow graph schema validation passed.")
                    print("   ✓ Schema validation passed.")
            else:
                # If using workflow_id, verify the workflow exists
                print(f"\n--- [{test_name}] Setup: Verifying workflow ID exists ---")
                workflow_exists = False
                try:
                    workflow_info = await workflow_tester.get_workflow(resolved_workflow_id)
                    if workflow_info and workflow_info.id:
                        workflow_exists = True
                        logger.info(f"[{test_name}] Verified workflow exists: ID {resolved_workflow_id}, Name: {workflow_info.name}")
                        print(f"   ✓ Workflow exists: {workflow_info.name} (ID: {resolved_workflow_id})")
                    else:
                        logger.error(f"[{test_name}] Workflow ID {resolved_workflow_id} does not exist or is not accessible.")
                        print(f"   ✗ Workflow ID {resolved_workflow_id} does not exist or is not accessible.")
                except Exception as workflow_err:
                    logger.error(f"[{test_name}] Error verifying workflow: {workflow_err}")
                    print(f"   ✗ Error verifying workflow: {workflow_err}")
                
                if not workflow_exists:
                    error_msg = f"Workflow ID {resolved_workflow_id} does not exist or is not accessible."
                    raise RuntimeError(error_msg)

            # --- 2. Execute Workflow Phase --- #
            print(f"\n--- [{test_name}] Executing Workflow --- ")
            if workflow_graph_schema:
                print(f"   Workflow Schema: Provided (details omitted for brevity)") # Avoid printing large schemas
            else:
                print(f"   Workflow ID: {resolved_workflow_id}")
                
            try:
                # Log initial inputs cleanly using JSON serialization
                print(f"   Initial Inputs: {json.dumps(initial_inputs, indent=2, default=str)}")
            except Exception:
                 print(f"   Initial Inputs: (Could not serialize, raw: {initial_inputs}) ")
            if hitl_inputs:
                 print(f"   Predefined HITL Inputs ({len(hitl_inputs)} steps): Provided")
            else:
                 print(f"   Predefined HITL Inputs: None")
            print(f"   Streaming Intermediate Results: {'ENABLED' if stream_intermediate_results else 'DISABLED'}")
            print(f"   Polling Interval: {poll_interval_sec}s, Timeout: {timeout_sec}s")

            # import ipdb; ipdb.set_trace()

            # Execute the workflow and wait for completion
            final_run_status_obj, final_run_outputs = await interactive_client.submit_and_monitor_run(
                workflow_id=resolved_workflow_id if resolved_workflow_id else None,
                graph_schema=workflow_graph_schema if workflow_graph_schema else None,
                inputs=initial_inputs,
                hitl_inputs=hitl_inputs,
                poll_interval_sec=poll_interval_sec,
                timeout_sec=timeout_sec,
                stream_intermediate_results=stream_intermediate_results,
                on_behalf_of_user_id=on_behalf_of_user_id,
                thread_id=thread_id
            )

            # --- 3. Validation Phase --- #
            print(f"\n--- [{test_name}] Validation --- ")
            # Basic check: Did we get a status object back?
            assert final_run_status_obj is not None, f"[{test_name}] Test Failed: Workflow run monitoring did not return a status object."

            run_id = final_run_status_obj.id
            final_status = final_run_status_obj.status
            error_message = final_run_status_obj.error_message
            print(f"   Run ID: {run_id}")
            print(f"   Actual Final Status: {final_status}")
            if error_message:
                print(f"   Error Message: {error_message}")

            # --- 3a. Dump Logs and State --- #
            if dump_artifacts:
                print(f"\n--- [{test_name}] Dumping Run Artifacts ---")
                try:
                    # Create a run client for fetching logs and state
                    run_client = BaseWorkflowRunTestClient(auth_client)
                    
                    # Get and save logs
                    print(f"   Fetching and saving run logs...")
                    logs_data, logs_path = await run_client.get_run_logs(
                        run_id=run_id,
                        save_to_file=True,
                        test_name=test_name
                    )
                    
                    if logs_data:
                        log_count = len(logs_data.get("logs", []))
                        print(f"   ✓ Saved {log_count} log entries to data directory \n\n\n\n *****Path:***** {logs_path}\n\n\n\n")
                    else:
                        print(f"   ✗ Failed to retrieve logs")
                        
                    # Try getting state data (might fail for non-superusers)
                    print(f"   Fetching and saving run state...")
                    state_data, state_path = await run_client.get_run_state(
                        run_id=run_id,
                        save_to_file=True,
                        test_name=test_name
                    )
                    
                    if state_data:
                        print(f"   ✓ Saved state data to data directory \n\n\n\n *****Path:***** {state_path}\n\n\n\n")
                    else:
                        print(f"   ✗ Failed to retrieve state data (possibly not a superuser)")
                        
                except Exception as artifact_err:
                    logger.exception(f"[{test_name}] Error dumping artifacts: {artifact_err}")
                    print(f"   ✗ Error dumping artifacts: {artifact_err}")
                    # Continue with validation - don't fail the test just because of artifact dumps

            # Core validation: Does the actual status match the expected status?
            assert final_status == expected_final_status, \
                   f"[{test_name}] Test Failed: Expected final status '{expected_final_status.name}', but got '{final_status.name}'. Error: {error_message}"
            logger.info(f"[{test_name}] Final status check passed (Expected: {expected_final_status}, Got: {final_status}).")
            print(f"   ✓ Final status matches expected: {expected_final_status.name}")

            # If the workflow completed successfully, proceed with output validation (if any)
            if final_status == WorkflowRunStatus.COMPLETED:
                print(f"   Final Outputs:")
                try:
                    # Attempt to pretty-print the outputs
                    print(json.dumps(final_run_outputs, indent=2, default=str))
                except Exception as json_e:
                    print(f"     (Could not JSON serialize final outputs: {json_e}) Raw: {final_run_outputs}")

                # Perform custom output validation if a function was provided
                if validate_output_func:
                    print(f"   Running custom output validation function...")
                    try:
                        # Await the custom validation function
                        is_valid = await validate_output_func(final_run_outputs)
                        # Assert that the custom validation returned True
                        assert is_valid, f"[{test_name}] Test Failed: Custom output validation function returned False."
                        print(f"   ✓ Custom output validation passed.")
                        logger.info(f"[{test_name}] Custom output validation passed.")
                    except Exception as val_err:
                        # Catch errors *during* the validation function execution
                        logger.exception(f"[{test_name}] Error during custom output validation: {val_err}")
                        print(f"   ✗ Error during custom output validation: {val_err}")
                        # Re-raise as an AssertionError to clearly mark a test failure
                        raise AssertionError(f"[{test_name}] Test Failed: Custom output validation function raised an error: {val_err}") from val_err
                else:
                     print(f"   (No custom output validation function provided)")
            elif final_status == WorkflowRunStatus.FAILED:
                 print(f"   (Run FAILED, skipping output validation. Error: {error_message}) ")
            else:
                 # Handle other terminal states like TIMEOUT, CANCELLED
                 print(f"   (Run did not complete successfully with status {final_status.name}, skipping output validation)")

    except AuthenticationError as e:
        # Authentication errors are critical and should stop the test
        print(f"\nAuthentication Error during test {test_name}: {e}")
        logger.error(f"[{test_name}] Authentication failed: {e}")
        # No specific cleanup needed here as the client context manager handles it.
        raise # Re-raise to indicate test failure
    except AssertionError as e:
         # Assertion errors indicate validation failures
         print(f"\nAssertion Error during test {test_name}: {e}")
         logger.error(f"[{test_name}] Assertion failed: {e}")
         # Cleanup will still run in the finally block.
         raise # Re-raise to indicate test failure
    except Exception as e:
        # Catch any other unexpected exceptions during setup, execution, or validation
        print(f"\nAn unexpected error occurred during test {test_name}: {e}")
        logger.exception(f"[{test_name}] Unexpected error during main execution phases:")
        # Cleanup will still run in the finally block.
        raise # Re-raise to indicate test failure

    # --- 4. Cleanup Phase --- #
    finally:
        # This block executes regardless of whether errors occurred in the try block.
        print(f"\n--- [{test_name}] Cleanup --- ")
        # Workflow run cleanup (like associated pods/resources) is typically handled
        # by the workflow engine itself or potentially background tasks, not explicitly here.
        # This focuses on cleaning up *customer data* documents.

        # --- 4a. Cleanup Documents --- #
        # Combine documents created during setup with explicitly requested cleanup docs.
        all_docs_to_cleanup = list(docs_created_by_setup) if cleanup_docs_created_by_setup else []
        if cleanup_docs:
            # Create a set of identifiers for docs already in the setup list to avoid duplicates.
            # Identifier includes namespace, docname, is_shared, is_versioned, is_system.
            setup_doc_ids = {
                (d['namespace'], d['docname'], d['is_shared'], d['is_versioned'], d.get('is_system_entity', False))
                for d in docs_created_by_setup
            }
            # Add docs from the explicit cleanup list if they weren't already added from setup.
            for doc_info in cleanup_docs:
                cleanup_id = (
                    doc_info['namespace'],
                    doc_info['docname'],
                    doc_info['is_shared'],
                    doc_info['is_versioned'],
                    doc_info.get('is_system_entity', False)
                )
                if cleanup_id not in setup_doc_ids:
                    all_docs_to_cleanup.append(doc_info)

        if not all_docs_to_cleanup:
            print("   No customer data documents marked for cleanup.")
            logger.info(f"[{test_name}] No customer data documents marked for cleanup.")
        else:
            print(f"   Attempting cleanup for {len(all_docs_to_cleanup)} document(s)...")
            # Use a new authenticated client session specifically for cleanup.
            # This is important in case the original session in the try block failed.
            try:
                 async with AuthenticatedClient() as cleanup_auth_client:
                    cleanup_data_tester = CustomerDataTestClient(cleanup_auth_client)
                    logger.info(f"[{test_name}] Cleanup authentication successful.")

                    for doc_info in all_docs_to_cleanup:
                        # Extract details for cleanup action
                        ns = doc_info['namespace']
                        dn = doc_info['docname']
                        is_shared = doc_info['is_shared']
                        is_versioned = doc_info['is_versioned']
                        is_system = doc_info.get('is_system_entity', False)
                        doc_type = "Versioned" if is_versioned else "Unversioned"
                        # Check if this doc was one created by setup for logging clarity
                        # Note: Direct dict comparison works here because they are simple structures.
                        was_created_by_setup = any(d == doc_info for d in docs_created_by_setup)
                        created_by_setup_flag = " (created by setup)" if was_created_by_setup else ""
                        doc_id_str = f"{'System/' if is_system else ''}{'Shared/' if is_shared else 'User/'}{ns}/{dn}"

                        logger.info(f"[{test_name}] Cleaning up {doc_type} document: {doc_id_str}{created_by_setup_flag}")
                        print(f"   Deleting {doc_type} doc: {doc_id_str}{created_by_setup_flag}...")
                        deleted = False
                        try:
                            # Call the appropriate deletion method based on whether it's versioned
                            if is_versioned:
                                deleted = await cleanup_data_tester.delete_versioned_document(
                                    namespace=ns, 
                                    docname=dn, 
                                    is_shared=is_shared, 
                                    is_system_entity=is_system,
                                    on_behalf_of_user_id=on_behalf_of_user_id
                                )
                            else:
                                deleted = await cleanup_data_tester.delete_unversioned_document(
                                    namespace=ns, 
                                    docname=dn, 
                                    is_shared=is_shared, 
                                    is_system_entity=is_system,
                                    on_behalf_of_user_id=on_behalf_of_user_id
                                )
                            # Log success or failure of the individual deletion attempt
                            if deleted:
                                print(f"     ✓ Deleted.")
                                logger.info(f"   ✓ [{test_name}] Successfully deleted document {doc_id_str}.")
                            else:
                                # Deletion returning False usually means the document didn't exist.
                                print(f"     ✗ Deletion returned False (likely didn't exist or already deleted)." )
                                logger.warning(f"[{test_name}] Deletion returned False for document {doc_id_str}. Assuming it didn't exist or was already deleted.")

                        except Exception as del_e:
                            # Catch errors during the specific deletion call
                            print(f"     ✗ Deletion API call failed: {del_e}")
                            # Log as a warning, as cleanup failure shouldn't obscure the main test result.
                            logger.warning(f"[{test_name}] Failed to delete document {doc_id_str} due to API error: {del_e}")

            except AuthenticationError as cleanup_auth_err:
                # Handle authentication errors during cleanup separately
                 print(f"   ✗ CRITICAL CLEANUP ERROR: Authentication failed during cleanup: {cleanup_auth_err}")
                 logger.error(f"[{test_name}] Authentication failed during cleanup phase: {cleanup_auth_err}")
                 # This might leave resources behind, but we don't raise here to preserve the original test result.
            except Exception as cleanup_e:
                # Catch other errors during the cleanup setup (e.g., client instantiation)
                print(f"   ✗ CRITICAL CLEANUP ERROR: Unexpected error during cleanup setup: {cleanup_e}")
                logger.exception(f"[{test_name}] Unexpected error setting up cleanup client:")
                 # This might leave resources behind.

        # --- 4b. Cleanup Schemas --- #
        if cleanup_created_schemas and schemas_created_by_setup:
            print(f"   Attempting cleanup for {len(schemas_created_by_setup)} schema template(s) created by setup...")
            # Use a new authenticated client session specifically for cleanup.
            try:
                 async with AuthenticatedClient() as cleanup_auth_client:
                    # Avoid shadowing outer scope `template_tester` if it might be used after finally
                    from kiwi_client.template_client import TemplateTestClient
                    cleanup_template_tester = TemplateTestClient(cleanup_auth_client)
                    logger.info(f"[{test_name}] Schema cleanup authentication successful.")

                    for schema_info in schemas_created_by_setup:
                        schema_id = schema_info['id']
                        schema_name = schema_info['name'] # For logging
                        logger.info(f"[{test_name}] Cleaning up schema template: {schema_name} (ID: {schema_id}) (created by setup)")
                        print(f"   Deleting Schema Template: {schema_name} (ID: {schema_id}) (created by setup)...")
                        deleted = False
                        try:
                            deleted = await cleanup_template_tester.delete_schema_template(schema_id)
                            if deleted:
                                print(f"     ✓ Deleted.")
                                logger.info(f"   ✓ [{test_name}] Successfully deleted schema template {schema_name} (ID: {schema_id}).")
                            else:
                                # Deletion returning False could mean it was already deleted or another issue.
                                print(f"     ✗ Deletion returned False (likely already deleted or error during deletion)." )
                                logger.warning(f"[{test_name}] Deletion returned False for schema template {schema_name} (ID: {schema_id}).")

                        except Exception as del_e:
                            # Catch errors during the specific deletion call
                            print(f"     ✗ Deletion API call failed: {del_e}")
                            logger.warning(f"[{test_name}] Failed to delete schema template {schema_name} (ID: {schema_id}) due to API error: {del_e}")

            except AuthenticationError as cleanup_auth_err:
                 print(f"   ✗ CRITICAL SCHEMA CLEANUP ERROR: Authentication failed: {cleanup_auth_err}")
                 logger.error(f"[{test_name}] Authentication failed during schema cleanup phase: {cleanup_auth_err}")
            except Exception as cleanup_e:
                print(f"   ✗ CRITICAL SCHEMA CLEANUP ERROR: Unexpected error during setup: {cleanup_e}")
                logger.exception(f"[{test_name}] Unexpected error setting up schema cleanup client:")
        elif cleanup_created_schemas and not schemas_created_by_setup:
             print("   No schema templates were created by setup, nothing to cleanup.")
             logger.info(f"[{test_name}] No schema templates created by setup to cleanup.")
        else:
            print("   Schema template cleanup skipped (cleanup_created_schemas=False)." )
            logger.info(f"[{test_name}] Schema template cleanup skipped (cleanup_created_schemas=False)." )

    # Final message indicating the test completion.
    print(f"\n{'='*20} Finished Test: {test_name} {'='*20}")
    # Return the results captured during the execution phase.
    return final_run_status_obj, final_run_outputs
