# poetry run python -m kiwi_client.run_client

import asyncio
import json
import httpx
import logging
import uuid
import time
import os
from typing import Dict, Any, Optional, List, Union, Tuple

# Import pydantic for validation
from pydantic import ValidationError, TypeAdapter

# Import authenticated client and config
from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from kiwi_client.test_config import (
    RUNS_URL,
    RUN_DETAIL_URL,
    RUN_DETAILS_URL,
    RUN_STREAM_URL,
    RUN_LOGS_URL,
    RUN_STATE_URL,
    DATA_DIR,
    EXAMPLE_BASIC_LLM_GRAPH_CONFIG,
    EXAMPLE_BASIC_LLM_RUN_INPUTS,
    CLIENT_LOG_LEVEL,
)
# Import workflow client to create a workflow to run
from kiwi_client.workflow_client import WorkflowTestClient

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
                         resume_run_id: Optional[Union[str, uuid.UUID]] = None,
                         force_resume_experimental_option: Optional[bool] = False,
                         on_behalf_of_user_id: Optional[Union[str, uuid.UUID]] = None,
                         thread_id: Optional[Union[str, uuid.UUID]] = None,
                         streaming_mode: Optional[bool] = True,
                         ) -> Optional[wf_schemas.WorkflowRunRead]:
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
            force_resume_experimental_option (Optional[bool]): Whether to force resume a run even if not in WAITING_HITL state.
            on_behalf_of_user_id (Optional[Union[str, uuid.UUID]]): User ID to act on behalf of (requires superuser privileges).
            thread_id (Optional[Union[str, uuid.UUID]]): Thread ID to resume from existing thread to retain message history.
            streaming_mode (Optional[bool]): Whether to stream the LLM tokens.

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
            if force_resume_experimental_option:
                payload["force_resume_experimental_option"] = force_resume_experimental_option
        elif workflow_id and not graph_schema:
            logger.info(f"Attempting to submit run for workflow ID: {workflow_id}")
            payload["workflow_id"] = str(workflow_id) # Ensure string for JSON
            payload["inputs"] = inputs
        elif graph_schema and not workflow_id:
            logger.info("Attempting to submit ad-hoc workflow run...")
            # Convert GraphSchema to dict for JSON serialization
            payload["graph_schema"] = graph_schema.model_dump() if hasattr(graph_schema, 'model_dump') else graph_schema
            payload["inputs"] = inputs
            payload["streaming_mode"] = streaming_mode
        else:
            logger.error("Submission error: Provide exactly one of workflow_id or graph_schema, or provide resume_run_id.")
            return None

        # Add on_behalf_of_user_id to payload if provided
        if on_behalf_of_user_id:
            payload["on_behalf_of_user_id"] = str(on_behalf_of_user_id)  # Ensure string for JSON
            logger.info(f"Run will be submitted on behalf of user ID: {on_behalf_of_user_id}")

        # Add thread_id to payload if provided
        if thread_id:
            payload["thread_id"] = str(thread_id)  # Ensure string for JSON
            logger.info(f"Run will be submitted with thread ID: {thread_id}")

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
                    elif base_event.event_type == event_schemas.WorkflowEvent.TOOL_CALL:
                        validated_event = event_schemas.ToolCallEvent.model_validate(event_data)
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

    async def get_run_logs(self, 
                         run_id: Union[str, uuid.UUID], 
                         save_to_file: bool = True,
                         output_filename: Optional[str] = None,
                         test_name: Optional[str] = None,
                         output_format: str = "markdown") -> Optional[Tuple[Dict[str, Any], str]]:
        """
        Gets the logs of a specific workflow run via GET /runs/{run_id}/logs.

        Corresponds to the `get_run_logs` route which returns `schemas.WorkflowRunLogs`.
        
        Args:
            run_id (Union[str, uuid.UUID]): The ID of the run to retrieve logs for.
            save_to_file (bool): Whether to save logs to a file.
            output_filename (Optional[str]): Filename to save logs to. If None, a default name is used.
            test_name (Optional[str]): Test name to include in the default filename if output_filename is None.
            output_format (str): Format to save logs in - "markdown" or "json".
            
        Returns:
            Optional[Tuple[Dict[str, Any], str]]: The logs response and output path, or None on failure.
        """
        run_id_str = str(run_id)
        logger.info(f"Attempting to get logs for run ID: {run_id_str}")
        url = RUN_LOGS_URL(run_id_str)
        
        try:
            # Endpoint returns 200 OK with logs
            response = await self._client.get(url)
            response.raise_for_status()
            logs_data = response.json()
            
            logger.info(f"Successfully retrieved logs for run ID: {run_id_str} ({len(logs_data.get('logs', []))} log entries)")
            
            # Save to file if requested
            if save_to_file:
                if output_filename is None:
                    # Include test_name in filename if provided
                    if test_name:
                        test_name_safe = test_name.replace(" ", "_").replace("/", "_").lower()
                        output_filename = f"{test_name_safe}_run_{run_id_str}_logs"
                    else:
                        output_filename = f"run_{run_id_str}_logs"
                
                # Determine file extension based on output format
                if output_format.lower() == "markdown":
                    output_filename = f"{output_filename}.md"
                else:  # default to json
                    output_filename = f"{output_filename}.json"
                
                output_path = os.path.join(DATA_DIR, output_filename)
                
                if output_format.lower() == "markdown":
                    logs = logs_data.get('logs', [])
                    
                    # Prepare log level counts and extract error/critical logs
                    level_counts = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0, "OTHER": 0}
                    error_logs = []
                    critical_logs = []
                    warning_logs = []
                    
                    # Process all logs first to collect stats and important messages
                    for idx, log in enumerate(logs):
                        level = log.get('level', 'INFO').upper()
                        
                        # Count by level
                        if level in level_counts:
                            level_counts[level] += 1
                        else:
                            level_counts["OTHER"] += 1
                            
                        # Collect important logs
                        if level == "ERROR":
                            error_logs.append((idx, log))
                        elif level == "CRITICAL":
                            critical_logs.append((idx, log))
                        elif level == "WARNING":
                            warning_logs.append((idx, log))
                    
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(f"# Workflow Run Logs - Run ID: {run_id_str}\n\n")
                        
                        if not logs:
                            f.write("*No logs found for this run.*\n")
                        else:
                            # Write summary section
                            f.write("## Log Summary\n\n")
                            
                            # Write log level counts as a table
                            f.write("| Log Level | Count |\n")
                            f.write("|-----------|-------|\n")
                            for level, count in level_counts.items():
                                if count > 0 or level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                                    f.write(f"| {level} | {count} |\n")
                            f.write("\n")
                            
                            # Write important logs sections if they exist
                            if critical_logs or error_logs:
                                f.write("## ⚠️ Critical Messages and Errors\n\n")
                                
                                if critical_logs:
                                    f.write("### Critical Messages\n\n")
                                    for idx, log in critical_logs:
                                        message = log.get('message', 'No message')
                                        timestamp = log.get('timestamp', 'N/A')
                                        
                                        # Format critical messages with more emphasis
                                        f.write(f"**[{timestamp}]** <span style='color:red; font-weight:bold'>CRITICAL</span>\n\n")
                                        
                                        # Create a markdown code block for the message
                                        if "\n" in message:
                                            f.write("```\n")
                                            f.write(message)
                                            f.write("\n```\n\n")
                                        else:
                                            f.write(f"`{message}`\n\n")
                                
                                if error_logs:
                                    f.write("### Error Messages\n\n")
                                    for idx, log in error_logs:
                                        message = log.get('message', 'No message')
                                        timestamp = log.get('timestamp', 'N/A')
                                        
                                        # Format error messages
                                        f.write(f"**[{timestamp}]** <span style='color:red'>ERROR</span>\n\n")
                                        
                                        # Create a markdown code block for the message
                                        if "\n" in message:
                                            f.write("```\n")
                                            f.write(message)
                                            f.write("\n```\n\n")
                                        else:
                                            f.write(f"`{message}`\n\n")
                                
                                f.write("---\n\n")
                            
                            # Write warning logs section if they exist
                            if warning_logs:
                                f.write("## ⚠️ Warning Messages\n\n")
                                for idx, log in warning_logs:
                                    message = log.get('message', 'No message')
                                    timestamp = log.get('timestamp', 'N/A')
                                    
                                    # Format warning messages
                                    f.write(f"**[{timestamp}]** <span style='color:orange'>WARNING</span>\n\n")
                                    
                                    # Create a markdown code block for the message
                                    if "\n" in message:
                                        f.write("```\n")
                                        f.write(message)
                                        f.write("\n```\n\n")
                                    else:
                                        f.write(f"`{message}`\n\n")
                                
                                f.write("---\n\n")
                            
                            # Write chronological log entries
                            f.write("## Complete Log (Chronological Order)\n\n")
                            
                            # Write each log entry as a formatted markdown section
                            for idx, log in enumerate(logs):
                                # Format timestamp
                                timestamp = log.get('timestamp', 'N/A')
                                
                                # Format level with color using HTML span tags
                                level = log.get('level', 'INFO').upper()
                                level_format = level
                                
                                weight = None
                                message_color = None
                                
                                if level == "ERROR":
                                    message_color = "red"
                                    level_format = f"<span style='color:red'>{level}</span>"
                                elif level == "WARNING":
                                    message_color = "orange"
                                    level_format = f"<span style='color:orange'>{level}</span>"
                                # elif level == "INFO":
                                #     message_color = "blue"
                                #     level_format = f"<span style='color:blue'>{level}</span>"
                                elif level == "CRITICAL":
                                    message_color = "red"
                                    weight = "bold"
                                    level_format = f"<span style='color:red; font-weight:bold'>{level}</span>"
                                
                                # Handle message with proper newline preservation
                                message = log.get('message', 'No message')
                                
                                # Create a markdown code block for multi-line messages
                                if "\n" in message:
                                    formatted_message = f"```\n{message}\n```"
                                else:
                                    formatted_message = f"`{message}`"
                                
                                # Prepare style for heading and timestamp based on log level
                                style = ""
                                if message_color:
                                    style = f"color:{message_color}"
                                    if weight == "bold":
                                        style += "; font-weight:bold"
                                
                                # Write the formatted log entry with colored heading
                                if style:
                                    f.write(f"### <span style='{style}'>Log Entry {idx+1}</span>\n\n")
                                    f.write(f"**<span style='{style}'>Timestamp:</span>** {timestamp}\n\n")
                                else:
                                    f.write(f"### Log Entry {idx+1}\n\n")
                                    f.write(f"**Timestamp:** {timestamp}\n\n")
                                
                                f.write(f"**Level:** {level_format}\n\n")
                                f.write(f"**Message:**\n\n{formatted_message}\n\n")
                                
                                # Add flow_run_id if present
                                flow_run_id = log.get('flow_run_id')
                                if flow_run_id:
                                    f.write(f"**Flow Run ID:** {flow_run_id}\n\n")
                                
                                # Add separator between log entries
                                if idx < len(logs) - 1:
                                    f.write("---\n\n")
                else:
                    with open(output_path, 'w', encoding='utf-8') as f:
                        # Use ensure_ascii=False to preserve unicode characters
                        # Use indent=2 for readability
                        json.dump(logs_data, f, indent=2, ensure_ascii=False)
                
                logger.info(f"Saved logs to {output_path}")
            
            return logs_data, output_path
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting logs for run {run_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting logs for run {run_id_str}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error getting logs for run {run_id_str}.")
        return None

    async def get_run_state(self, 
                           run_id: Union[str, uuid.UUID],
                           save_to_file: bool = True,
                           output_filename: Optional[str] = None,
                           test_name: Optional[str] = None,
                           output_format: str = "markdown") -> Optional[Tuple[Dict[str, Any], str]]:
        """
        Gets the state of a specific workflow run via GET /runs/{run_id}/state.
        
        This endpoint is primarily for debugging and is typically only accessible to superusers.
        Corresponds to the `get_run_state` route which returns `schemas.WorkflowRunState`.
        
        Args:
            run_id (Union[str, uuid.UUID]): The ID of the run to retrieve state for.
            save_to_file (bool): Whether to save state to a file.
            output_filename (Optional[str]): Filename to save state to. If None, a default name is used.
            test_name (Optional[str]): Test name to include in the default filename if output_filename is None.
            output_format (str): Format to save state in - "markdown" or "json".
            
        Returns:
            Optional[Tuple[Dict[str, Any], str]]: The state response and output path, or None on failure.
        """
        run_id_str = str(run_id)
        logger.info(f"Attempting to get state for run ID: {run_id_str}")
        url = RUN_STATE_URL(run_id_str)
        
        try:
            # Endpoint returns 200 OK with state (only accessible to superusers)
            response = await self._client.get(url)
            response.raise_for_status()
            state_data = response.json()
            
            logger.info(f"Successfully retrieved state for run ID: {run_id_str}")
            
            # Save to file if requested
            if save_to_file:
                if output_filename is None:
                    # Include test_name in filename if provided
                    if test_name:
                        test_name_safe = test_name.replace(" ", "_").replace("/", "_").lower()
                        output_filename = f"{test_name_safe}_run_{run_id_str}_state"
                    else:
                        output_filename = f"run_{run_id_str}_state"
                
                # Determine file extension based on output format
                if output_format.lower() == "markdown":
                    output_filename = f"{output_filename}.md"
                else:  # default to json
                    output_filename = f"{output_filename}.json"
                    
                output_path = os.path.join(DATA_DIR, output_filename)
                
                if output_format.lower() == "markdown":
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(f"# Workflow Run State - Run ID: {run_id_str}\n\n")
                        
                        # Write run_id and thread_id
                        f.write("## Run Information\n\n")
                        f.write(f"**Run ID:** `{state_data.get('run_id', 'N/A')}`\n\n")
                        f.write(f"**Thread ID:** `{state_data.get('thread_id', 'N/A')}`\n\n")
                        
                        # Write central state section
                        f.write("## Central State\n\n")
                        central_state = state_data.get('central_state', {})
                        
                        if not central_state:
                            f.write("*No central state data found.*\n\n")
                        else:
                            central_state_json = json.dumps(central_state, indent=2, ensure_ascii=False)
                            f.write("```json\n")
                            f.write(central_state_json)
                            f.write("\n```\n\n")
                        
                        # Write node outputs section
                        f.write("## Node Outputs\n\n")
                        node_outputs = state_data.get('node_outputs', {})
                        
                        if not node_outputs:
                            f.write("*No node outputs data found.*\n\n")
                        else:
                            # Process each node output
                            for node_name, output in node_outputs.items():
                                f.write(f"### Node: {node_name}\n\n")
                                
                                # Format node output as JSON
                                output_json = json.dumps(output, indent=2, ensure_ascii=False)
                                f.write("```json\n")
                                f.write(output_json)
                                f.write("\n```\n\n")
                else:
                    # Save as JSON
                    with open(output_path, 'w', encoding='utf-8') as f:
                        # Use ensure_ascii=False to preserve unicode characters and newlines
                        # Use indent=2 for readability
                        json.dump(state_data, f, indent=2, ensure_ascii=False)
                
                logger.info(f"Saved state to {output_path}")
            
            return state_data, output_path
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting state for run {run_id_str}: {e.response.status_code} - {e.response.text}")
            if e.response.status_code == 403:
                logger.error("This endpoint is typically only accessible to superusers.")
        except httpx.RequestError as e:
            logger.error(f"Request error getting state for run {run_id_str}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error getting state for run {run_id_str}.")
        return None

    async def wait_for_run_completion(self, run_id: Union[str, uuid.UUID], timeout_sec: int = 60, poll_interval_sec: int = 3) -> Optional[wf_schemas.WorkflowRunRead]:
        """
        Polls the run status (using `get_run_status`) until it reaches a terminal state
        (COMPLETED, FAILED, CANCELLED, WAITING_HITL) or the timeout is reached.

        Args:
            run_id (Union[str, uuid.UUID]): The ID of the run to monitor.
            timeout_sec (int): Maximum time to wait in seconds.
            poll_interval_sec (int): Time between status checks in seconds.

        Returns:
            Optional[wf_schemas.WorkflowRunRead]: The final validated run status summary if completed
                                                 or waiting for HITL within timeout, None otherwise.
        """
        run_id_str = str(run_id) # Use string internally for consistency
        logger.info(f"Waiting for run {run_id_str} to complete or pause (timeout: {timeout_sec}s)...")
        start_time = time.time()

        # Terminal states for workflow runs (including WAITING_HITL as an intermediate stop)
        terminal_states = {
            WorkflowRunStatus.COMPLETED,
            WorkflowRunStatus.FAILED,
            WorkflowRunStatus.CANCELLED,
            WorkflowRunStatus.WAITING_HITL # Add WAITING_HITL as a state to stop polling for
        }

        while time.time() - start_time < timeout_sec:
            # Use the updated get_run_status which returns a validated schema object
            run_status: Optional[wf_schemas.WorkflowRunRead] = await self.get_run_status(run_id_str)
            if run_status:
                current_state = run_status.status # Access status via attribute
                logger.info(f"  Run {run_id_str} status: {current_state}")
                if current_state in terminal_states:
                    if current_state == WorkflowRunStatus.WAITING_HITL:
                        logger.info(f"Run {run_id_str} is now WAITING_HITL.")
                    else:
                        logger.info(f"Run {run_id_str} reached terminal state: {current_state}")
                    return run_status # Return the validated object
            else:
                # get_run_status already logs errors
                logger.warning(f"Could not fetch status for run {run_id_str} during polling loop.")
                # Optional: Decide whether to retry or fail immediately if status fetch fails
                # return None # Or continue polling

            await asyncio.sleep(poll_interval_sec)

        logger.warning(f"Run {run_id_str} did not complete or pause within the {timeout_sec}s timeout.")
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

    # Import HITL client only if needed
    from kiwi_client.notification_hitl_client import HITLTestClient

    # Need an authenticated client first
    try:
        async with AuthenticatedClient() as auth_client:
            print("Authenticated.")
            # Initialize test clients
            workflow_tester = WorkflowTestClient(auth_client)
            run_tester = WorkflowRunTestClient(auth_client)
            # Initialize HITL tester here for potential use later
            hitl_tester = HITLTestClient(auth_client)

            # --- Setup: Create a workflow to run ---
            # NOTE: We need a workflow that includes a HITL node for this test.
            #       Using EXAMPLE_BASIC_LLM_GRAPH_CONFIG will likely result in COMPLETION, not WAITING_HITL.
            #       Replace EXAMPLE_BASIC_LLM_GRAPH_CONFIG with a graph containing a HITL node.
            #       For now, we proceed assuming it might hit WAITING_HITL for demonstration.
            # TODO: Define EXAMPLE_HITL_GRAPH_CONFIG in test_config.py
            example_graph_config = EXAMPLE_BASIC_LLM_GRAPH_CONFIG # Replace with actual HITL graph
            example_inputs = EXAMPLE_BASIC_LLM_RUN_INPUTS        # Replace with inputs for HITL graph


            print("\n--- Setup: Creating a workflow (ensure it has a HITL node for full test) --- ")
            # ... (workflow validation remains the same) ...
            validation_result = await workflow_tester.validate_graph_api(example_graph_config)
            # ... (error handling for validation) ...

            created_workflow = await workflow_tester.create_workflow(
                name="Workflow For Run Test (HITL)", # Updated name
                graph_config=example_graph_config
            )
            if created_workflow:
                workflow_id_to_run = created_workflow.id
                print(f"Setup complete: Created workflow ID: {workflow_id_to_run}")
            else:
                print("Setup failed: Could not create workflow.")
                return
            # --- ----------------------------- ---

            # 1. Submit Run using Workflow ID
            print(f"\n1. Submitting run for workflow ID: {workflow_id_to_run}...")
            submitted_run: Optional[wf_schemas.WorkflowRunRead] = await run_tester.submit_run(
                workflow_id=workflow_id_to_run,
                inputs=example_inputs
                # Uncomment to test submitting on behalf of another user (requires superuser privileges)
                # on_behalf_of_user_id=uuid.UUID("00000000-0000-0000-0000-000000000000")  # Replace with actual user ID
            )
            if submitted_run:
                created_run_id = submitted_run.id
                print(f"   Run submitted successfully: ID = {created_run_id} (Status: {submitted_run.status})")
            else:
                print("   Run submission failed.")
                return # Stop if initial submission fails

            # ... (Adhoc run submission and listing remain similar, but less relevant for HITL flow) ...
            # 2. Submit Ad-hoc Run using Graph Schema (Skipping for HITL focus)
            # 3. List Runs (Check if new runs appear) (Skipping for HITL focus)

            # --- Wait for the first run (created_run_id) to complete OR pause for HITL ---
            if created_run_id:
                print(f"\n--- Waiting for run {created_run_id} to finish or pause ---")
                # wait_for_run_completion now also stops for WAITING_HITL
                intermediate_status_obj: Optional[wf_schemas.WorkflowRunRead] = await run_tester.wait_for_run_completion(created_run_id)

                if intermediate_status_obj and intermediate_status_obj.status == WorkflowRunStatus.WAITING_HITL:
                    print(f"   Run {created_run_id} paused, waiting for HITL.")

                    # --- Handle WAITING_HITL State ---
                    print(f"\n--- Handling WAITING_HITL for run {created_run_id} ---")

                    # 4. Get Latest Pending HITL Job for this run
                    print("4. Fetching pending HITL job details...")
                    pending_job = await hitl_tester.get_latest_pending_hitl_job(run_id=created_run_id)

                    if pending_job:
                        print(f"   Found pending HITL job: {pending_job.id}")
                        print(f"     Request Details: {json.dumps(pending_job.request_details, indent=2)}")
                        print(f"     Response Schema: {json.dumps(pending_job.response_schema, indent=2)}")

                        # 5. Prepare and Submit HITL Response to Resume Run
                        print("\n5. Preparing and submitting HITL response to resume run...")
                        # !!! Define the response based on the actual request_details and response_schema !!!
                        # This is a placeholder - adjust according to your HITL node's needs.
                        hitl_response_inputs = {
                            "approval_status": "approved",
                            "comments": "Looks good to proceed.",
                            "confidence_score": 0.95
                        }
                        print(f"   Submitting response: {json.dumps(hitl_response_inputs, indent=2)}")

                        # Use submit_run with resume_run_id
                        resumed_run_status = await run_tester.submit_run(
                            resume_run_id=created_run_id,
                            inputs=hitl_response_inputs # Provide the HITL response data here
                            # resume_after_hitl=True is handled internally by submit_run when resume_run_id is set
                        )

                        if resumed_run_status:
                            print(f"   Resume request submitted. Run {created_run_id} status potentially updated (check logs/polling). Current status from response: {resumed_run_status.status}")
                            # Note: The status in the response might still be SCHEDULED or RUNNING immediately after resuming.

                            # 6. Wait for Final Completion after resuming
                            print(f"\n6. Waiting for run {created_run_id} to reach *final* completion after resume...")
                            final_status_obj: Optional[wf_schemas.WorkflowRunRead] = await run_tester.wait_for_run_completion(created_run_id, timeout_sec=120) # Increase timeout potentially

                            if final_status_obj and final_status_obj.status == WorkflowRunStatus.COMPLETED:
                                print(f"   Run {created_run_id} completed successfully after HITL response.")
                                # You can now fetch final details/stream as before
                                print(f"\n7. Getting final details for run {created_run_id}...")
                                details_obj = await run_tester.get_run_details(created_run_id)
                                if details_obj:
                                     output_sample = str(details_obj.outputs)[:100] if details_obj.outputs else "N/A"
                                     event_count = len(details_obj.detailed_results) if details_obj.detailed_results else 0
                                     print(f"   Final Details: Status={details_obj.status}, Events={event_count}, Output={output_sample}...")
                                else:
                                     print("   Failed to get final run details after resume.")

                            elif final_status_obj:
                                print(f"   Run {created_run_id} finished with non-success status after resume: {final_status_obj.status}")
                                print(f"   Error message: {final_status_obj.error_message}")
                            else:
                                print(f"   Run {created_run_id} timed out or final status could not be retrieved after resume.")

                        else:
                            print("   Failed to submit resume request.")
                    else:
                        print("   Could not find pending HITL job for this run. Cannot resume.")
                    # --- End Handle WAITING_HITL ---

                elif intermediate_status_obj and intermediate_status_obj.status == WorkflowRunStatus.COMPLETED:
                    # --- Handle Direct Completion (No HITL) ---
                    print(f"   Run {created_run_id} completed successfully (without HITL step).")
                    # Fetch details/stream as before if needed
                    print(f"\n4. Getting details for completed run {created_run_id}...")
                    details_obj = await run_tester.get_run_details(created_run_id)
                    if details_obj:
                         output_sample = str(details_obj.outputs)[:100] if details_obj.outputs else "N/A"
                         event_count = len(details_obj.detailed_results) if details_obj.detailed_results else 0
                         print(f"   Details: Status={details_obj.status}, Events={event_count}, Output={output_sample}...")
                    else:
                         print("   Failed to get run details.")
                    
                    # Get logs and state data and save to files
                    print(f"\n5. Getting logs for run {created_run_id}...")
                    logs_data, logs_path = await run_tester.get_run_logs(
                        run_id=created_run_id, 
                        save_to_file=True,
                        test_name="Example_Basic_LLM_Test"
                    )
                    if logs_data:
                        log_count = len(logs_data.get("logs", []))
                        print(f"   Successfully retrieved {log_count} log entries for run {created_run_id}")
                        print(f"   Saved logs to file: Example_Basic_LLM_Test_run_{created_run_id}_logs.json \nPATH: {logs_path}\n")
                    else:
                        print(f"   Failed to retrieve logs for run {created_run_id}")
                    
                    print(f"\n6. Getting state for run {created_run_id} (requires superuser)...")
                    state_data, state_path = await run_tester.get_run_state(
                        run_id=created_run_id, 
                        save_to_file=True,
                        test_name="Example_Basic_LLM_Test"
                    )
                    if state_data:
                        print(f"   Successfully retrieved state for run {created_run_id}")
                        print(f"   Saved state to file: Example_Basic_LLM_Test_run_{created_run_id}_state.json \nPATH: {state_path}\n")
                    else:
                        print(f"   Failed to retrieve state for run {created_run_id} (likely not a superuser)")
                    # --- End Handle Direct Completion ---

                elif intermediate_status_obj:
                    print(f"   Run {created_run_id} finished with non-success status: {intermediate_status_obj.status}")
                    print(f"   Error message: {intermediate_status_obj.error_message}")
                else:
                    print(f"   Run {created_run_id} timed out or status could not be retrieved.")
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
