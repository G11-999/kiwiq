# poetry run python -m kiwi_client.test_run_client_v2

import asyncio
import json
import httpx
import logging
import uuid
import time
from typing import Dict, Any, Optional, List, Union

# Import pydantic for validation
from pydantic import ValidationError, TypeAdapter

# Import authenticated client and config
from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from kiwi_client.test_config import (
    RUNS_URL,
    RUN_DETAIL_URL,
    RUN_DETAILS_URL,
    RUN_STREAM_URL,
    EXAMPLE_BASIC_LLM_GRAPH_CONFIG,
    EXAMPLE_BASIC_LLM_RUN_INPUTS,
    CLIENT_LOG_LEVEL,
)
# Import workflow client to create a workflow to run
from kiwi_client.test_workflow_client_v2 import WorkflowTestClient

# Import schemas and constants from the workflow app

# from kiwi_app.workflow_app import schemas as wf_schemas
from kiwi_client.schemas import workflow_api_schemas as wf_schemas
# from kiwi_app.workflow_app.constants import WorkflowRunStatus, HITLJobStatus
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus, HITLJobStatus
# from workflow_service.services import events as event_schemas
from kiwi_client.schemas import events_schema as event_schemas

from kiwi_client.schemas.graph_schema import GraphSchema

# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)

# Create TypeAdapters for validating lists of schemas
WorkflowRunReadListAdapter = TypeAdapter(List[wf_schemas.WorkflowRunRead])
WorkflowRunEventDetailListAdapter = TypeAdapter(List[wf_schemas.WorkflowRunEventDetail])


class WorkflowRunTestClient:
    """
    Provides methods to test the /runs/ endpoints defined in routes.py.
    Uses schemas from schemas.py for requests and response validation.
    """
    def __init__(self, auth_client: AuthenticatedClient):
        """
        Initializes the WorkflowRunTestClient.

        Args:
            auth_client (AuthenticatedClient): An instance of AuthenticatedClient, assumed to be logged in.
        """
        self._auth_client: AuthenticatedClient = auth_client
        self._client: httpx.AsyncClient = auth_client.client
        # Store the ID as UUID for type consistency if retrieved successfully
        self._last_submitted_run_id: Optional[uuid.UUID] = None
        logger.info("WorkflowRunTestClient initialized.")

    @property
    def last_submitted_run_id(self) -> Optional[uuid.UUID]:
        """Returns the UUID of the last successfully submitted run in this session."""
        return self._last_submitted_run_id

    async def submit_run(self,
                         workflow_id: Optional[Union[str, uuid.UUID]] = None,
                         graph_schema: Optional[GraphSchema] = None,
                         inputs: Dict[str, Any] = EXAMPLE_BASIC_LLM_RUN_INPUTS,
                         resume_run_id: Optional[Union[str, uuid.UUID]] = None) -> Optional[wf_schemas.WorkflowRunRead]:
        """
        Tests submitting a new workflow run via POST /runs/.

        Corresponds to the `submit_workflow_run` route which expects `schemas.WorkflowRunCreate`.

        Exactly one of `workflow_id` or `graph_schema` must be provided (unless resuming).
        If `resume_run_id` is provided, it attempts to resume that run with the given inputs.

        Args:
            workflow_id (Optional[Union[str, uuid.UUID]]): The ID of an existing workflow to run.
            graph_schema (Optional[GraphSchema]): A graph schema for an ad-hoc run.
            inputs (Dict[str, Any]): The input data for the workflow run.
            resume_run_id (Optional[Union[str, uuid.UUID]]): The ID of a previous run to resume.

        Returns:
            Optional[wf_schemas.WorkflowRunRead]: The parsed and validated response body of the submitted run
                                                 (usually in SCHEDULED state), or None on failure.
        """
        # Prepare payload according to schemas.WorkflowRunCreate
        payload: Dict[str, Any] = {}
        if resume_run_id:
            logger.info(f"Attempting to resume workflow run ID: {resume_run_id}")
            payload["run_id"] = str(resume_run_id) # Ensure string for JSON
            payload["inputs"] = inputs
            payload["resume_after_hitl"] = True
        elif workflow_id and not graph_schema:
            logger.info(f"Attempting to submit run for workflow ID: {workflow_id}")
            payload["workflow_id"] = str(workflow_id) # Ensure string for JSON
            payload["inputs"] = inputs
        elif graph_schema and not workflow_id:
            logger.info("Attempting to submit ad-hoc workflow run...")
            # Convert GraphSchema to dict for JSON serialization
            payload["graph_schema"] = graph_schema.model_dump() if hasattr(graph_schema, 'model_dump') else graph_schema
            payload["inputs"] = inputs
        else:
            logger.error("Submission error: Provide exactly one of workflow_id or graph_schema, or provide resume_run_id.")
            return None

        try:
            # Endpoint returns 202 Accepted, body contains WorkflowRunRead schema
            response = await self._client.post(RUNS_URL, json=payload)

            # Check for non-success status codes explicitly
            if response.status_code != 202:
                logger.error(f"Error submitting run: Status {response.status_code} - {response.text}")
                response.raise_for_status() # Raise exception for non-202 codes

            response_json = response.json()
            # Validate the response against the WorkflowRunRead schema
            validated_run = wf_schemas.WorkflowRunRead.model_validate(response_json)
            self._last_submitted_run_id = validated_run.id # Store the UUID
            logger.info(f"Successfully submitted run. Assigned Run ID: {validated_run.id} (Status: {validated_run.status})")
            logger.debug(f"Submit response validated: {validated_run.model_dump_json(indent=2)}")
            return validated_run
        except httpx.HTTPStatusError as e:
            # Logged above if status code wasn't 202
            logger.debug(f"HTTP Status Error Detail: {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error submitting run: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error submitting run: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error during run submission.")
        return None

    async def list_runs(self,
                        skip: int = 0,
                        limit: int = 10,
                        workflow_id: Optional[Union[str, uuid.UUID]] = None,
                        status: Optional[WorkflowRunStatus] = None,
                        triggered_by_user_id: Optional[Union[str, uuid.UUID]] = None,
                        owner_org_id: Optional[Union[str, uuid.UUID]] = None # For superuser testing
                        ) -> Optional[List[wf_schemas.WorkflowRunRead]]:
        """
        Tests listing workflow runs via GET /runs/.

        Corresponds to the `list_runs` route which uses `schemas.WorkflowRunListQuery`.

        Args:
            skip (int): Number of runs to skip.
            limit (int): Maximum number of runs to return.
            workflow_id (Optional[Union[str, uuid.UUID]]): Filter by workflow ID.
            status (Optional[WorkflowRunStatus]): Filter by run status.
            triggered_by_user_id (Optional[Union[str, uuid.UUID]]): Filter by user ID (requires superuser for others).
            owner_org_id (Optional[Union[str, uuid.UUID]]): Filter by org ID (requires superuser).

        Returns:
            Optional[List[wf_schemas.WorkflowRunRead]]: A list of parsed and validated workflow runs,
                                                       or None on failure.
        """
        logger.info(f"Attempting to list runs (skip={skip}, limit={limit})...")
        # Prepare query parameters matching schemas.WorkflowRunListQuery
        params: Dict[str, Any] = {"skip": skip, "limit": limit}
        if workflow_id: params["workflow_id"] = str(workflow_id)
        if status: params["status"] = status.value
        if triggered_by_user_id: params["triggered_by_user_id"] = str(triggered_by_user_id)
        if owner_org_id: params["owner_org_id"] = str(owner_org_id)

        try:
            # Endpoint returns 200 OK, body is List[WorkflowRunRead]
            response = await self._client.get(RUNS_URL, params=params)
            response.raise_for_status() # Raise exception for non-2xx codes
            response_json = response.json()

            # Validate the response list against List[WorkflowRunRead]
            validated_runs = WorkflowRunReadListAdapter.validate_python(response_json)
            logger.info(f"Successfully listed and validated {len(validated_runs)} runs.")
            logger.debug(f"List runs response (first item): {validated_runs[0].model_dump() if validated_runs else 'None'}")
            return validated_runs
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing runs: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error listing runs: {e}")
        except ValidationError as e:
             logger.error(f"Response validation error listing runs: {e}")
             logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error during run listing.")
        return None

    async def get_run_status(self, run_id: Union[str, uuid.UUID]) -> Optional[wf_schemas.WorkflowRunRead]:
        """
        Tests getting the status summary of a specific run via GET /runs/{run_id}.

        Corresponds to the `get_run_status` route which returns `schemas.WorkflowRunRead`.

        Args:
            run_id (Union[str, uuid.UUID]): The ID of the run to retrieve status for.

        Returns:
            Optional[wf_schemas.WorkflowRunRead]: The parsed and validated run status summary,
                                                 or None on failure.
        """
        run_id_str = str(run_id)
        logger.info(f"Attempting to get status for run ID: {run_id_str}")
        url = RUN_DETAIL_URL(run_id_str) # Uses the /runs/{run_id} endpoint
        try:
            # Endpoint returns 200 OK, body is WorkflowRunRead schema
            response = await self._client.get(url)
            response.raise_for_status()
            response_json = response.json()

            # Validate the response against the WorkflowRunRead schema
            validated_run_status = wf_schemas.WorkflowRunRead.model_validate(response_json)
            logger.info(f"Successfully retrieved and validated status for run ID: {validated_run_status.id} (Status: {validated_run_status.status})")
            logger.debug(f"Get status response validated: {validated_run_status.model_dump_json(indent=2)}")
            return validated_run_status
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting status for run {run_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting status for run {run_id_str}: {e}")
        except ValidationError as e:
             logger.error(f"Response validation error getting status for run {run_id_str}: {e}")
             logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception(f"Unexpected error getting status for run {run_id_str}.")
        return None

    async def get_run_details(self, run_id: Union[str, uuid.UUID]) -> Optional[wf_schemas.WorkflowRunDetailRead]:
        """
        Tests getting the detailed results (including event stream embedded) of a specific run
        via GET /runs/{run_id}/details.

        Corresponds to the `get_run_details` route which returns `schemas.WorkflowRunDetailRead`.

        Args:
            run_id (Union[str, uuid.UUID]): The ID of the run to retrieve details for.

        Returns:
            Optional[wf_schemas.WorkflowRunDetailRead]: The parsed and validated run details,
                                                       or None on failure.
        """
        run_id_str = str(run_id)
        logger.info(f"Attempting to get details for run ID: {run_id_str}")
        url = RUN_DETAILS_URL(run_id_str) # Uses the /runs/{run_id}/details endpoint
        try:
            # Endpoint returns 200 OK, body is WorkflowRunDetailRead schema
            response = await self._client.get(url)
            response.raise_for_status()
            response_json = response.json()

            # print("\n\n\n\n RUN DETAILS RESPONSE:: ", json.dumps(response_json, indent=4), "\n\n\n\n")

            # Validate the response against the WorkflowRunDetailRead schema
            validated_run_details = wf_schemas.WorkflowRunDetailRead.model_validate(response_json)
            event_count = len(validated_run_details.detailed_results) if validated_run_details.detailed_results else 0
            logger.info(f"Successfully retrieved and validated details for run ID: {validated_run_details.id} ({event_count} events found)")
            # Limit debug log size
            log_details = validated_run_details.model_dump()
            if log_details.get("detailed_results"):
                 log_details["detailed_results"] = f"{len(log_details['detailed_results'])} events..." # Summarize events
            logger.debug(f"Get details response validated: {log_details}")
            return validated_run_details
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting details for run {run_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting details for run {run_id_str}: {e}")
        except ValidationError as e:
             logger.error(f"Response validation error getting details for run {run_id_str}: {e}")
             logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception(f"Unexpected error getting details for run {run_id_str}.")
        return None

    async def get_run_stream(self, run_id: Union[str, uuid.UUID]) -> Optional[List[wf_schemas.WorkflowRunEventDetail]]:
        """
        Tests getting the raw event stream for a specific run via GET /runs/{run_id}/stream.

        Corresponds to the `get_run_stream` route which returns `List[schemas.WorkflowRunEventDetail]`.

        Args:
            run_id (Union[str, uuid.UUID]): The ID of the run to retrieve the stream for.

        Returns:
            Optional[List[wf_schemas.WorkflowRunEventDetail]]: A list of parsed and validated events
                                                              from the run stream, or None on failure.
                                                              Note: `WorkflowRunEventDetail` is a Union type.
        """
        run_id_str = str(run_id)
        logger.info(f"Attempting to get event stream for run ID: {run_id_str}")
        url = RUN_STREAM_URL(run_id_str) # Uses the /runs/{run_id}/stream endpoint
        try:
             # Endpoint returns 200 OK, body is List[WorkflowRunEventDetail]
            response = await self._client.get(url)
            response.raise_for_status()
            response_json = response.json()

            # print("\n\n\n\n RUN STREAM RESPONSE:: ", json.dumps(response_json, indent=4), "\n\n\n\n")

            # Validate and parse the response events based on their event_type
            validated_stream = []
            for event_data in response_json:
                # First validate as base event to get the event_type
                try:
                    base_event = event_schemas.WorkflowBaseEvent.model_validate(event_data)
                    # Then validate against the specific event type schema
                    if base_event.event_type == event_schemas.WorkflowEvent.NODE_OUTPUT:
                        validated_event = event_schemas.WorkflowRunNodeOutputEvent.model_validate(event_data)
                    elif base_event.event_type == event_schemas.WorkflowEvent.MESSAGE_CHUNK:
                        validated_event = event_schemas.MessageStreamChunk.model_validate(event_data)
                    elif base_event.event_type == event_schemas.WorkflowEvent.WORKFLOW_RUN_STATUS:
                        validated_event = event_schemas.WorkflowRunStatusUpdateEvent.model_validate(event_data)
                    elif base_event.event_type == event_schemas.WorkflowEvent.HITL_REQUEST:
                        validated_event = event_schemas.HITLRequestEvent.model_validate(event_data)
                    else:
                        # Fallback to base event if type is unknown
                        validated_event = base_event
                        logger.warning(f"Unknown event type: {base_event.event_type}")
                    
                    validated_stream.append(validated_event)
                except ValidationError as e:
                    logger.warning(f"Skipping invalid event: {e}")
            
            logger.info(f"Successfully retrieved stream for run ID: {run_id_str} ({len(validated_stream)} events validated)")
            
            # Log first event type if available
            if validated_stream:
                first_event = validated_stream[0]
                event_type = type(first_event).__name__
                    
                logger.debug(f"Get stream response (first event type): {event_type}")
            return validated_stream

        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting stream for run {run_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting stream for run {run_id_str}: {e}")
        except ValidationError as e:
             logger.error(f"Response validation error getting stream for run {run_id_str}: {e}")
             logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception(f"Unexpected error getting stream for run {run_id_str}.")
        return None

    async def wait_for_run_completion(self, run_id: Union[str, uuid.UUID], timeout_sec: int = 60, poll_interval_sec: int = 3) -> Optional[wf_schemas.WorkflowRunRead]:
        """
        Polls the run status (using `get_run_status`) until it reaches a terminal state
        (COMPLETED, FAILED, CANCELLED) or the timeout is reached.

        Args:
            run_id (Union[str, uuid.UUID]): The ID of the run to monitor.
            timeout_sec (int): Maximum time to wait in seconds.
            poll_interval_sec (int): Time between status checks in seconds.

        Returns:
            Optional[wf_schemas.WorkflowRunRead]: The final validated run status summary if completed
                                                 within timeout, None otherwise.
        """
        run_id_str = str(run_id) # Use string internally for consistency
        logger.info(f"Waiting for run {run_id_str} to complete (timeout: {timeout_sec}s)...")
        start_time = time.time()
        
        # Terminal states for workflow runs
        terminal_states = {
            WorkflowRunStatus.COMPLETED,
            WorkflowRunStatus.FAILED,
            WorkflowRunStatus.CANCELLED
        }

        while time.time() - start_time < timeout_sec:
            # Use the updated get_run_status which returns a validated schema object
            run_status: Optional[wf_schemas.WorkflowRunRead] = await self.get_run_status(run_id_str)
            if run_status:
                current_state = run_status.status # Access status via attribute
                logger.info(f"  Run {run_id_str} status: {current_state}")
                if current_state in terminal_states:
                    logger.info(f"Run {run_id_str} reached terminal state: {current_state}")
                    return run_status # Return the validated object
            else:
                # get_run_status already logs errors
                logger.warning(f"Could not fetch status for run {run_id_str} during polling loop.")
                # Optional: Decide whether to retry or fail immediately if status fetch fails
                # return None # Or continue polling

            await asyncio.sleep(poll_interval_sec)

        logger.warning(f"Run {run_id_str} did not complete within the {timeout_sec}s timeout.")
        # Optionally, try one last time to get the status
        final_status = await self.get_run_status(run_id_str)
        return final_status

# --- Example Usage --- (for testing this module directly)
async def main():
    """Demonstrates using the updated WorkflowRunTestClient with schema validation."""
    print("--- Starting Workflow Run API Test --- ")
    workflow_id_to_run: Optional[uuid.UUID] = None
    created_run_id: Optional[uuid.UUID] = None
    adhoc_run_id: Optional[uuid.UUID] = None

    # Need an authenticated client first
    try:
        async with AuthenticatedClient() as auth_client:
            print("Authenticated.")
            # Initialize test clients
            workflow_tester = WorkflowTestClient(auth_client)
            run_tester = WorkflowRunTestClient(auth_client)

            # --- Setup: Create a workflow to run ---
            print("\n--- Setup: Creating a workflow --- ")

            print("\n1. Comprehensive workflow validation using API...")
            # Use the API-based validation method instead of the local validation
            validation_result = await workflow_tester.validate_graph_api(EXAMPLE_BASIC_LLM_GRAPH_CONFIG)
            if validation_result:
                if validation_result.is_valid:
                    print("   ✓ Workflow validation completed successfully!")
                    print(f"   - Graph schema valid: {validation_result.graph_schema_valid}")
                    print(f"   - Node configs valid: {validation_result.node_configs_valid}")
                else:
                    print("   ✗ Workflow validation failed:")
                    for category, errors in validation_result.errors.items():
                        print(f"     {category}:")
                        for error in errors:
                            print(f"       - {error}")
            else:
                print("   ✗ Failed to perform API-based validation - falling back to local validation")
                # Fallback to local validation if API validation fails
                valid_workflow, all_errors = await workflow_tester.validate_workflow(EXAMPLE_BASIC_LLM_GRAPH_CONFIG)
                if valid_workflow:
                    print("   ✓ Workflow validation completed successfully!")
                else:
                    print("   ✗ Workflow validation failed:")
                    for category, errors in all_errors.items():
                        print(f"     {category}:")
                        for error in errors:
                            print(f"       - {error}")

            created_workflow = await workflow_tester.create_workflow(
                name="Workflow For Run Test",
                graph_config=EXAMPLE_BASIC_LLM_GRAPH_CONFIG # from test_config
            )
            if created_workflow:
                workflow_id_to_run = created_workflow.id # Access UUID directly from schema
                print(f"Setup complete: Created workflow ID: {workflow_id_to_run}")
                print(f"Workflow name: {created_workflow.name}")
            else:
                print("Setup failed: Could not create workflow.")
                return
            # --- ----------------------------- ---

            # 1. Submit Run using Workflow ID
            print(f"\n1. Submitting run for workflow ID: {workflow_id_to_run}...")
            # submit_run returns Optional[wf_schemas.WorkflowRunRead]
            submitted_run: Optional[wf_schemas.WorkflowRunRead] = await run_tester.submit_run(
                workflow_id=workflow_id_to_run,
                inputs=EXAMPLE_BASIC_LLM_RUN_INPUTS # from test_config
            )
            if submitted_run:
                created_run_id = submitted_run.id # Access ID via attribute
                print(f"   Run submitted successfully: ID = {created_run_id} (Status: {submitted_run.status})")
            else:
                print("   Run submission failed.")
                # Consider stopping if the first run fails, depending on test goals

            # 2. Submit Ad-hoc Run using Graph Schema
            print("\n2. Submitting ad-hoc run...")
            adhoc_input = {"user_prompt": "Tell me a short joke about APIs."}
            adhoc_submitted_run: Optional[wf_schemas.WorkflowRunRead] = await run_tester.submit_run(
                graph_schema=EXAMPLE_BASIC_LLM_GRAPH_CONFIG, # from test_config
                inputs=adhoc_input
            )
            if adhoc_submitted_run:
                adhoc_run_id = adhoc_submitted_run.id
                print(f"   Ad-hoc run submitted successfully: ID = {adhoc_run_id} (Status: {adhoc_submitted_run.status})")
            else:
                print("   Ad-hoc run submission failed.")

            # 3. List Runs (Check if new runs appear)
            print("\n3. Listing runs...")
            # list_runs returns Optional[List[wf_schemas.WorkflowRunRead]]
            recent_runs: Optional[List[wf_schemas.WorkflowRunRead]] = await run_tester.list_runs(limit=5)
            if recent_runs is not None: # Check for None explicitly
                print(f"   Found {len(recent_runs)} recent runs.")
                run_ids = [run.id for run in recent_runs] # Get list of UUIDs
                if created_run_id and created_run_id in run_ids:
                    found_run = next((run for run in recent_runs if run.id == created_run_id), None)
                    print(f"   Run {created_run_id} found in list (Status: {found_run.status if found_run else 'unknown'})")
                if adhoc_run_id and adhoc_run_id in run_ids:
                    found_adhoc = next((run for run in recent_runs if run.id == adhoc_run_id), None)
                    print(f"   Ad-hoc run {adhoc_run_id} found in list (Status: {found_adhoc.status if found_adhoc else 'unknown'})")
            else:
                print("   Run listing failed.")

            # --- Wait for the first run (created_run_id) to complete ---
            if created_run_id:
                print(f"\n--- Waiting for run {created_run_id} to finish ---")
                # wait_for_run_completion returns Optional[wf_schemas.WorkflowRunRead]
                final_status_obj: Optional[wf_schemas.WorkflowRunRead] = await run_tester.wait_for_run_completion(created_run_id)

                if final_status_obj and final_status_obj.status == WorkflowRunStatus.COMPLETED:
                    print(f"   Run {created_run_id} completed successfully.")

                    # 4. Get Run Status (Final) - Re-fetch for demo
                    print(f"\n4. Getting final status for run {created_run_id}...")
                    # get_run_status returns Optional[wf_schemas.WorkflowRunRead]
                    status_summary_obj = await run_tester.get_run_status(created_run_id)
                    if status_summary_obj:
                        print(f"   Final Status from API: {status_summary_obj.status}")
                        print(f"   Run completed at: {status_summary_obj.ended_at}")
                        assert status_summary_obj.status == WorkflowRunStatus.COMPLETED
                        assert status_summary_obj.id == created_run_id
                    else:
                        print("   Failed to get final status summary.")

                    # 5. Get Run Details
                    print(f"\n5. Getting details for run {created_run_id}...")
                    # get_run_details returns Optional[wf_schemas.WorkflowRunDetailRead]
                    details_obj: Optional[wf_schemas.WorkflowRunDetailRead] = await run_tester.get_run_details(created_run_id)
                    if details_obj:
                        output_sample = str(details_obj.outputs)[:100] if details_obj.outputs else "N/A"
                        event_count = len(details_obj.detailed_results) if details_obj.detailed_results else 0
                        print(f"   Successfully fetched details (Status: {details_obj.status}, Events: {event_count})")
                        print(f"   Output sample: {output_sample}...")
                        # Add assertions based on expected output structure using schema attributes
                        assert details_obj.id == created_run_id
                        assert details_obj.outputs is not None 
                        assert details_obj.detailed_results is not None
                        assert event_count > 0 # Expect some events for a successful run
                    else:
                        print("   Failed to get run details.")

                    # 6. Get Run Stream
                    print(f"\n6. Getting event stream for run {created_run_id}...")
                    # get_run_stream returns Optional[List[wf_schemas.WorkflowRunEventDetail]]
                    stream_events: Optional[List[wf_schemas.WorkflowRunEventDetail]] = await run_tester.get_run_stream(created_run_id)
                    if stream_events is not None: # Check for None
                        print(f"   Successfully fetched stream with {len(stream_events)} events.")
                        # Check the type of the first event if present
                        if stream_events:
                            first_event = stream_events[0]
                            if isinstance(first_event, event_schemas.WorkflowRunNodeOutputEvent):
                                event_type = "WorkflowRunNodeOutputEvent"
                            elif isinstance(first_event, event_schemas.MessageStreamChunk):
                                event_type = "MessageStreamChunk"
                            elif isinstance(first_event, event_schemas.WorkflowRunStatusUpdateEvent):
                                event_type = "WorkflowRunStatusUpdateEvent"
                            elif isinstance(first_event, event_schemas.HITLRequestEvent):
                                event_type = "HITLRequestEvent"
                            else:
                                event_type = type(first_event).__name__
                            print(f"     First event type: {event_type}")
                    else:
                        print("   Failed to get run stream.")

                elif final_status_obj:
                    print(f"   Run {created_run_id} finished with non-success status: {final_status_obj.status}")
                    print(f"   Error message: {final_status_obj.error_message}")
                else:
                    print(f"   Run {created_run_id} timed out or final status could not be retrieved.")
            # --- ---------------------------------- ---

    except AuthenticationError as e:
        print(f"Authentication Error: {e}")
    except ImportError as e:
         print(f"Import Error: {e}. Check PYTHONPATH and schema locations.")
    except Exception as e:
        print(f"An unexpected error occurred in the main test execution: {e}")
        logger.exception("Main test execution error:")
    finally:
        # --- Cleanup: Delete the workflow ---
        if workflow_id_to_run:
            print(f"\n--- Cleanup: Deleting workflow {workflow_id_to_run} --- ")
            try:
                # Re-authenticate for cleanup if the main block failed early
                async with AuthenticatedClient() as cleanup_auth_client:
                    cleanup_workflow_tester = WorkflowTestClient(cleanup_auth_client)
                    deleted = await cleanup_workflow_tester.delete_workflow(workflow_id_to_run)
                    if deleted:
                        if isinstance(deleted, bool):
                            print(f"   Cleanup successful: Deleted workflow {workflow_id_to_run}.")
                        else:
                            print(f"   Cleanup successful: Deleted workflow {workflow_id_to_run} (Name: {deleted.name}).")
                    else:
                        print(f"   Cleanup failed: Could not delete workflow {workflow_id_to_run}.")
            except AuthenticationError as auth_e:
                 print(f"   Cleanup failed: Authentication error during cleanup - {auth_e}")
            except httpx.HTTPStatusError as http_e:
                 print(f"   Cleanup failed: HTTP error deleting workflow - {http_e.response.status_code} {http_e.response.text}")
            except Exception as cleanup_e:
                print(f"   Cleanup failed: Unexpected error during cleanup - {cleanup_e}")
                logger.exception("Cleanup error:")
        # NOTE: Runs are usually not deleted automatically when workflow is deleted.
        #       No explicit run deletion endpoint tested here.
        # --- ---------------------------- ---
        print("\n--- Workflow Run API Test Finished --- ")

if __name__ == "__main__":
    # Ensure API server is running and config is correct
    # Run with: PYTHONPATH=. python test_clients/test_run_client_v2.py
    print("Attempting to run test client main function...")
    asyncio.run(main()) # Run the main test function
    print("\nRun this script with `PYTHONPATH=[path_to_project_root] python test_clients/test_run_client_v2.py`")
