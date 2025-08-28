"""
Workflow Runner Node - Execute workflows as subflows or independent runs.

This node enables workflows to trigger other workflows, supporting both
subprocess execution (for true nested flows) and independent execution
(for decoupled workflow orchestration).
"""

import asyncio
import json
import uuid
from typing import Any, ClassVar, Dict, List, Optional, Type, Union, TYPE_CHECKING
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator
from prefect.flow_engine import run_flow_in_subprocess
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_async_db_as_manager

from workflow_service.registry.nodes.core.dynamic_nodes import BaseNode, DynamicSchema, BaseDynamicNode
from workflow_service.registry.schemas.base import BaseNodeConfig, BaseSchema
from kiwi_app.workflow_app.constants import LaunchStatus, WorkflowRunStatus
from workflow_service.config.constants import APPLICATION_CONTEXT_KEY, EXTERNAL_CONTEXT_MANAGER_KEY

from kiwi_app.workflow_app import models, schemas

if TYPE_CHECKING:
    from kiwi_app.workflow_app.services import WorkflowService

from kiwi_app.workflow_app.app_artifacts import DEFAULT_ALL_WORKFLOWS, DEFAULT_USER_DOCUMENTS_CONFIG
from kiwi_app.workflow_app.schemas import GraphSchema


class ExecutionMode(str, Enum):
    """Execution mode for the workflow runner."""
    SUBPROCESS = "subprocess"  # Run as true subprocess with parent-child relationship
    INDEPENDENT = "independent"  # Submit as independent workflow run


class WorkflowRunnerConfig(BaseNodeConfig):
    """
    Configuration for the workflow runner node.
    
    Controls how the target workflow is executed and monitored.
    """
    
    # Workflow identification
    workflow_name: Optional[str] = Field(
        default=None,
        description="Name of the workflow to run. Takes precedence over workflow_id if both provided."
    )
    workflow_id: Optional[str] = Field(
        default=None,
        description="UUID of the workflow to run. Used if workflow_name is not provided."
    )
    workflow_version: Optional[str] = Field(
        default=None,
        description="Version of the workflow to run (used with workflow_name). "
                   "If not specified, uses the latest version."
    )
    
    # Execution settings
    execution_mode: ExecutionMode = Field(
        default=ExecutionMode.SUBPROCESS,
        description="How to execute the workflow. "
                   "'subprocess': Run as true subprocess with parent-child relationship. "
                   "'independent': Submit as independent workflow run."
    )
    
    # Monitoring settings
    poll_interval_seconds: int = Field(
        default=3,
        ge=1,
        le=60,
        description="Interval in seconds between status checks when monitoring workflow execution."
    )
    timeout_seconds: int = Field(
        default=1200,
        ge=10,
        le=3600,
        description="Maximum time in seconds to wait for workflow completion before timing out."
    )
    
    # Caching settings
    enable_workflow_cache: bool = Field(
        default=True,
        description="If True, attempts to reuse outputs from recent successful runs with identical inputs."
    )
    cache_lookback_period: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Number of days to look back for matching successful runs."
    )
    check_error_free_logs: bool = Field(
        default=False,
        description="When True, only reuse cached runs that have no error logs. When False, pick the recent run with the fewest error logs."
    )
    
    # Error handling
    fail_on_workflow_error: bool = Field(
        default=True,
        description="Whether to fail this node if the triggered workflow fails. "
                   "If False, node succeeds but includes error details in output."
    )
    
    # Input/Output mapping
    input_mapping: Optional[Dict[str, str]] = Field(
        default=None,
        description="Map workflow input fields to paths in node inputs. "
                   "Format: {'workflow_input_field': 'path.to.value'} where path uses dot notation. "
                   "If not specified, uses direct field name matching."
    )
    output_fields: Optional[List[str]] = Field(
        default=None,
        description="List of specific output fields to extract from workflow results. "
                   "If not specified, returns all workflow outputs."
    )
    
    @model_validator(mode='after')
    def validate_workflow_identification(self) -> 'WorkflowRunnerConfig':
        """Ensure at least one workflow identification method is provided."""
        if not self.workflow_name and not self.workflow_id:
            raise ValueError("Either workflow_name or workflow_id must be provided")
        return self


# Input schema will be dynamically created, but we define a base structure
class WorkflowRunnerInput(DynamicSchema):
    """
    Dynamic input schema for the workflow runner node.
    
    This schema accepts arbitrary inputs that can be mapped to workflow inputs.
    Fields are dynamically accepted and processed based on configuration.
    """
    pass


class WorkflowRunnerOutput(BaseSchema):
    """
    Output schema for the workflow runner node.
    
    Contains the results and metadata from the executed workflow.
    """
    
    # Execution identification
    workflow_id: str = Field(
        ...,
        description="UUID of the workflow that was executed."
    )
    workflow_name: str = Field(
        ...,
        description="Name of the workflow that was executed."
    )
    workflow_version: Optional[str] = Field(
        default=None,
        description="Version of the workflow that was executed."
    )
    run_id: str = Field(
        ...,
        description="UUID of the workflow run that was created."
    )
    
    # Execution results
    status: str = Field(
        ...,
        description="Final status of the workflow execution. "
                   "Values: 'completed', 'failed', 'cancelled', 'timeout'"
    )
    workflow_outputs: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Outputs from the executed workflow. "
                   "Contains either all outputs or filtered based on output_fields configuration."
    )
    
    # Execution metadata
    execution_mode: str = Field(
        ...,
        description="The execution mode that was used ('subprocess' or 'independent')."
    )
    started_at: str = Field(
        ...,
        description="ISO 8601 timestamp when the workflow execution started."
    )
    completed_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp when the workflow execution completed."
    )
    duration_seconds: Optional[float] = Field(
        default=None,
        description="Total execution time in seconds."
    )
    
    # Error information
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if the workflow execution failed."
    )
    error_details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Detailed error information including stack trace if available."
    )
    
    # Parent-child relationship (for subprocess mode)
    parent_run_id: Optional[str] = Field(
        default=None,
        description="Parent workflow run ID (only set in subprocess mode)."
    )


class WorkflowRunnerNode(BaseDynamicNode):  # [WorkflowRunnerInput, WorkflowRunnerOutput, WorkflowRunnerConfig]
    """
    Workflow Runner Node - Execute workflows within workflows with dynamic input handling.
    
    This node enables complex workflow orchestration by allowing workflows to trigger
    other workflows. It accepts dynamic inputs and intelligently maps them to the target
    workflow's expected inputs.
    
    ## Execution Modes
    
    1. **Subprocess Mode**: Executes the workflow as a true subprocess with parent-child
       relationship tracking. The child workflow inherits context from the parent and
       creates a proper workflow run record in the database.
    
    2. **Independent Mode**: Submits the workflow as an independent run through the
       workflow service. The workflow runs separately but is monitored by this node.
    
    ## Dynamic Input Handling
    
    This node accepts arbitrary input fields dynamically. Input mapping works in two ways:
    
    1. **Direct Matching** (default): If an input field name exactly matches a workflow 
       input field name, it's passed directly to the workflow.
    
    2. **Path-Based Mapping**: Use the `input_mapping` config to map workflow input fields
       to paths in the received inputs using dot notation for nested values.
    
    ## Special Control Fields
    
    Reserved input fields (prefixed with underscore) control node behavior:
    - `_override_workflow_name`: Override the configured workflow name
    - `_override_workflow_id`: Override the configured workflow ID
    - `_override_workflow_version`: Override the configured workflow version
    - `_thread_id`: Thread ID for conversational workflows
    
    ## Features
    
    - **Dynamic inputs**: Accept any input structure and map to workflow inputs
    - **App artifacts integration**: Fetch workflow requirements and defaults from app_artifacts
    - **Flexible identification**: Target workflows by name, ID, or key
    - **Smart input mapping**: Direct matching or path-based resolution
    - **Output filtering**: Extract specific fields from workflow results
    - **Error handling**: Configurable behavior on workflow failure
    - **Thread support**: Maintain conversation context across executions
    - **Database integration**: Proper workflow run tracking for subprocess mode
    
    ## Usage Examples
    
    ### Example 1: Direct field matching
    ```json
    {
        "entity_username": "john_doe",
        "user_input": "Write about AI trends",
        "past_context_posts_limit": 10,
        "_thread_id": "conversation-123"
    }
    ```
    
    ### Example 2: Path-based mapping
    ```json
    {
        "user_data": {
            "profile": {
                "username": "john_doe"
            },
            "preferences": {
                "post_limit": 10
            }
        },
        "content": {
            "prompt": "Write about AI"
        }
    }
    ```
    With config:
    ```json
    {
        "input_mapping": {
            "entity_username": "user_data.profile.username",
            "past_context_posts_limit": "user_data.preferences.post_limit",
            "user_input": "content.prompt"
        }
    }
    ```
    
    ## Configuration Example
    ```json
    {
        "workflow_name": "linkedin_content_creation_workflow",
        "execution_mode": "subprocess",
        "input_mapping": {
            "entity_username": "user.username",
            "brief_docname": "documents.brief"
        },
        "output_fields": ["generated_content", "metadata"]
    }
    ```
    """
    
    node_name: ClassVar[str] = "workflow_runner"
    node_version: ClassVar[str] = "1.0.0"
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    
    input_schema_cls: ClassVar[Type[WorkflowRunnerInput]] = WorkflowRunnerInput
    output_schema_cls: ClassVar[Type[WorkflowRunnerOutput]] = WorkflowRunnerOutput
    config_schema_cls: ClassVar[Type[WorkflowRunnerConfig]] = WorkflowRunnerConfig
    
    config: WorkflowRunnerConfig
    
    async def _fetch_workflow(
        self,
        workflow_service: 'WorkflowService',
        user,
        org_id: uuid.UUID,
        workflow_name: Optional[str] = None,
        workflow_id: Optional[str] = None,
        workflow_version: Optional[str] = None
    ) -> models.Workflow:
        """
        Fetch workflow by name or ID.
        
        Args:
            db: Database session
            workflow_service: Workflow service instance
            user: User executing the workflow
            org_id: Organization ID
            workflow_name: Name of the workflow
            workflow_id: UUID of the workflow
            workflow_version: Version of the workflow (used with name)
            
        Returns:
            Workflow model instance
            
                    Raises:
            ValueError: If workflow not found or access denied
        """
        try:
            # Prefer name-based lookup
            async with get_async_db_as_manager() as db:
                if workflow_name:
                    # Search for workflow by name and version
                    workflows = await workflow_service.search_workflows(
                        db=db,
                        name=workflow_name,
                        version_tag=workflow_version,
                        owner_org_id=org_id,
                        include_public=True,
                        include_system_entities=False,
                        include_public_system_entities=True,
                        user=user,
                    )
                    
                    if not workflows:
                        raise ValueError(
                            f"Workflow '{workflow_name}' "
                            f"{'version ' + workflow_version if workflow_version else ''} not found"
                        )
                    
                    # Use the first match (should be unique by name+version)
                    return workflows[0]
                
                elif workflow_id:
                    # Fetch by ID
                    workflow_uuid = uuid.UUID(workflow_id)
                    workflow = await workflow_service.get_workflow(
                        db=db,
                        user=user,
                        workflow_id=workflow_uuid,
                        owner_org_id=org_id,
                        include_system_entities=True,
                    )
                    
                    if not workflow:
                        raise ValueError(f"Workflow with ID '{workflow_id}' not found")
                    
                    return workflow
            
                else:
                    raise ValueError("Either workflow_name or workflow_id must be provided")
                
        except ValueError as e:
            raise ValueError(f"Invalid workflow_id format: {e}")
        except Exception as e:
            raise ValueError(f"Failed to fetch workflow: {e}")
    
    def _resolve_path(self, data: Dict[str, Any], path: str) -> Any:
        """
        Resolve a dot-notation path in nested data structure.
        
        Args:
            data: The data structure to traverse
            path: Dot-notation path (e.g., 'field.subfield.value')
            
        Returns:
            The value at the path, or None if path doesn't exist
        """
        parts = path.split('.')
        current = data
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                # Handle array indexing like field.0.subfield
                try:
                    index = int(part)
                    if 0 <= index < len(current):
                        current = current[index]
                    else:
                        return None
                except (ValueError, IndexError):
                    return None
            else:
                return None
        
        return current
    
    async def _map_inputs(
        self,
        node_inputs: Dict[str, Any],
        workflow_inputs_spec: Dict[str, Any],
        input_mapping: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Map node inputs to workflow inputs based on configuration.
        
        This function implements two mapping strategies:
        1. Direct matching: If a field in node_inputs exactly matches a workflow input field name
        2. Path-based mapping: Use configured mapping to resolve paths in node_inputs
        
        Args:
            node_inputs: Raw inputs from the node
            workflow_inputs_spec: Expected workflow inputs with defaults from app_artifacts
            input_mapping: Mapping configuration (workflow_field -> path in node_inputs)
            
        Returns:
            Mapped inputs for the workflow
        """
        mapped_inputs = {}
        
        # Start with defaults from workflow spec
        for field, default_value in workflow_inputs_spec.items():
            if default_value is not None:
                mapped_inputs[field] = default_value
        
        if input_mapping:
            # Apply explicit path-based mapping
            for workflow_field, input_path in input_mapping.items():
                value = self._resolve_path(node_inputs, input_path)
                if value is not None:
                    mapped_inputs[workflow_field] = value
        else:
            # Use direct field name matching
            for workflow_field in workflow_inputs_spec.keys():
                if workflow_field in node_inputs:
                    mapped_inputs[workflow_field] = node_inputs[workflow_field]
        
        return mapped_inputs
    
    async def _filter_outputs(
        self,
        workflow_outputs: Dict[str, Any],
        output_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Filter workflow outputs based on configuration.
        
        Args:
            workflow_outputs: Raw outputs from the workflow
            output_fields: List of fields to extract
            
        Returns:
            Filtered outputs
        """
        if not output_fields or not workflow_outputs:
            # Return all outputs
            return workflow_outputs
        
        # Extract specified fields
        filtered_outputs = {}
        for field in output_fields:
            if field in workflow_outputs:
                filtered_outputs[field] = workflow_outputs[field]
        
        return filtered_outputs

    def _compute_input_hash(self, inputs: Dict[str, Any]) -> Optional[str]:
        """
        Compute a deterministic hash of the mapped workflow inputs.
        Uses compact JSON with sorted keys to ensure stable hashing.
        Returns None if serialization fails.
        """
        try:
            import hashlib
            normalized = json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        except Exception:
            return None

    async def _has_error_logs_for_run(self, *, workflow_service: 'WorkflowService', run: models.WorkflowRun, user) -> bool:
        """
        Use service method to retrieve Prefect logs and detect any error-level entries.
        Returns True if error logs are present.
        """
        try:
            async with get_async_db_as_manager() as db:
                logs_schema = await workflow_service.get_run_logs(db=db, run=run, skip=0, limit=10000)
        except Exception as e:
            # If logs cannot be retrieved, be conservative and treat as errors
            self.warning(f"Failed to get run logs for run {run.id}: {e}")
            return True

        if not logs_schema or not getattr(logs_schema, 'logs', None):
            return False

        for entry in logs_schema.logs:
            level = (entry.level if hasattr(entry, 'level') else str(entry.get('level', '') if isinstance(entry, dict) else '')).upper()
            if level in {"ERROR", "CRITICAL"}:
                return True
            # Fallback on message scanning to catch stacktraces logged at WARNING
            message = entry.message if hasattr(entry, 'message') else (entry.get('message', '') if isinstance(entry, dict) else '')
            if isinstance(message, str):
                low = message.lower()
                if 'traceback' in low or 'exception' in low:
                    return True
        return False
    
    async def _poll_for_completion(
        self,
        run_id: uuid.UUID,
        workflow_service: 'WorkflowService',
        user,
        org_id: uuid.UUID,
        poll_interval: int = 3,
        timeout: int = 600
    ) -> Dict[str, Any]:
        """
        Poll for workflow completion and return results.
        
        Used by both subprocess and independent execution modes.
        
        Args:
            run_id: The workflow run ID to monitor
            workflow_service: Workflow service instance
            user: User executing the workflow
            org_id: Organization ID
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait for completion
            
        Returns:
            Dict with run_id, status, outputs, and error (if any)
        """
        self.info(f"Starting to poll for workflow run {run_id}")
        start_time = datetime.now(timezone.utc)
        last_status = None
        
        while True:
            # Check timeout
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed > timeout:
                self.warning(f"Workflow run {run_id} timed out after {elapsed:.1f} seconds")
                
                # Try to get final status even on timeout
                try:
                    async with get_async_db_as_manager() as db:
                        workflow_run = await workflow_service.get_run(
                            db=db,
                            run_id=run_id,
                            owner_org_id=org_id
                        )
                        last_status = workflow_run.status.value if hasattr(workflow_run.status, 'value') else str(workflow_run.status)
                except Exception as e:
                    self.error(f"Failed to get final status for timed-out run {run_id}: {e}")
                
                return {
                    "run_id": str(run_id),
                    "status": "timeout",
                    "outputs": None,
                    "error": f"Workflow execution timed out after {timeout} seconds. Last status: {last_status or 'unknown'}"
                }
            
            # Get current run status - WorkflowRun already has all the fields we need
            try:
                async with get_async_db_as_manager() as db:
                    workflow_run = await workflow_service.get_run(
                        db=db,
                        run_id=run_id,
                        owner_org_id=org_id
                    )
                
                current_status = workflow_run.status
                
                # Log status changes
                if current_status != last_status:
                    self.info(f"Workflow run {run_id} status changed: {last_status} -> {current_status}")
                    last_status = current_status
                
                # Check for terminal states
                if current_status in [
                    WorkflowRunStatus.COMPLETED,
                    WorkflowRunStatus.FAILED,
                    WorkflowRunStatus.CANCELLED,
                ]:
                    self.info(f"Workflow run {run_id} reached terminal state: {current_status}")
                    
                    # Return results directly from workflow_run - no need for get_run_details
                    return {
                        "run_id": str(run_id),
                        "status": current_status.value.lower() if hasattr(current_status, 'value') else str(current_status).lower(),
                        "outputs": workflow_run.outputs,  # Direct field access
                        "error": workflow_run.error_message  # Direct field access
                    }
                
                # Handle HITL state (if needed in future)
                elif current_status == WorkflowRunStatus.WAITING_HITL:
                    self.info(f"Workflow run {run_id} is waiting for HITL input")
                    # For now, we don't handle HITL in the runner node
                    # This could be extended in the future
                    pass
                
            except Exception as e:
                self.error(f"Error retrieving status for run {run_id}: {e}. Retrying...")
                # Continue polling even on error
            
            # Wait before next check
            await asyncio.sleep(poll_interval)
    
    async def _run_as_subprocess(
        self,
        workflow: models.Workflow,
        inputs: Dict[str, Any],
        external_context,
        workflow_service: 'WorkflowService',
        user,
        org_id: uuid.UUID,
        workflow_run_job,  # The parent workflow_run_job from app_context
        parent_run_id: Optional[uuid.UUID] = None,
        thread_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """
        Run workflow as a subprocess, creating the run in DB first.
        
        This follows the same pattern as submit_workflow_run in services.py,
        creating a proper workflow run record before execution.
        
        Args:
            workflow: Workflow to execute
            inputs: Workflow inputs
            external_context: External context manager
            workflow_service: Workflow service instance
            user: User executing the workflow
            org_id: Organization ID
            workflow_run_job: The parent workflow run job from app_context
            parent_run_id: Parent workflow run ID
            thread_id: Thread ID for conversational workflows
            
        Returns:
            Workflow execution results
        """
        # Get workflow configuration overrides if applicable
        async with get_async_db_as_manager() as db:
            overrides, effective_graph_schema = await workflow_service.list_workflow_specific_overrides_and_optional_apply(
                db=db,
                include_active=True,
                include_tags=None,
                active_org_id=org_id,
                requesting_user=user,
                base_workflow_to_apply_overrides_to=workflow
            )
            
            # Create the workflow run record in database (similar to submit_workflow_run)
            workflow_run = await workflow_service.workflow_run_dao.create(
                db,
                workflow_id=workflow.id,
                workflow_name=workflow.name,
                owner_org_id=org_id,
                triggered_by_user_id=user.id if user and hasattr(user, 'id') else workflow_run_job.triggered_by_user_id,
                inputs=inputs,
                thread_id=thread_id,
                status=WorkflowRunStatus.SCHEDULED,
                tag=f"subprocess_of_{parent_run_id}" if parent_run_id else None,
                applied_workflow_config_overrides=",".join([str(override.id) for override in overrides]) if overrides else None,
                parent_run_id=parent_run_id,  # Set parent relationship
            )
        
            # Set thread_id to run_id if not provided (same as in submit_workflow_run)
            if not workflow_run.thread_id:
                workflow_run.thread_id = workflow_run.id
                db.add(workflow_run)
                await db.commit()
                await db.refresh(workflow_run)
        
        try:
            # Prepare the workflow run job
            run_job = schemas.WorkflowRunJobCreate(
                run_id=workflow_run.id,
                workflow_id=workflow.id,
                workflow_name=workflow.name,
                graph_schema=effective_graph_schema if effective_graph_schema else workflow.graph_config,
                inputs=inputs,
                owner_org_id=org_id,
                triggered_by_user_id=user.id if user and hasattr(user, 'id') else workflow_run_job.triggered_by_user_id,
                parent_run_id=parent_run_id,
                thread_id=thread_id,
                streaming_mode=True,
            )
            
            # Run the workflow as a subprocess
            # Note: run_flow_in_subprocess is NOT async - it just submits the flow
            # The subprocess will handle its own status updates internally
            from workflow_service.services.worker import workflow_execution_flow
            from prefect.context import serialize_context, get_run_context
            from prefect import get_run_logger
            context = serialize_context()
            if "task_run_context" in context:
                if "parameters" in context["task_run_context"]:
                    context["task_run_context"]["parameters"] = {}
            # context = {k: v for k, v in context.items() if k not in ["task_run_context"]}  # "flow_run_context", 
            # self.warning(f"Context json {json.dumps(context, indent=4, default=str)}")
            # context = {"logger_name": get_run_logger().name}
            p = await asyncio.to_thread(run_flow_in_subprocess, flow=workflow_execution_flow,
                parameters={"run_job": run_job.model_dump()},
                context=context,)
            # p = run_flow_in_subprocess(
            #     flow=workflow_execution_flow,
            #     parameters={"run_job": run_job.model_dump()},
            #     context=context,
            # )
            await asyncio.to_thread(p.join)
            # p.join()
            
            self.info(f"Subprocess submitted for workflow run {workflow_run.id}")
            
            # Poll for completion - subprocess doesn't return results directly
            # We need to poll just like with independent runs
            result = await self._poll_for_completion(
                run_id=workflow_run.id,
                workflow_service=workflow_service,
                user=user,
                org_id=org_id,
                poll_interval=self.config.poll_interval_seconds,
                timeout=self.config.timeout_seconds
            )
            
            return result
            
        except Exception as e:
            self.error(f"Subprocess submission or polling failed: {e}", exc_info=True)
            # raise e
            
            # Even on exception, try to poll for the actual status
            # The workflow may have been submitted and is running
            try:
                result = await self._poll_for_completion(
                    run_id=workflow_run.id,
                    workflow_service=workflow_service,
                    user=user,
                    org_id=org_id,
                    poll_interval=self.config.poll_interval_seconds,
                    timeout=self.config.timeout_seconds
                )
                # If polling succeeded, return the result even if initial submission had issues
                if result.get("status") != "timeout":
                    return result
            except Exception as poll_error:
                self.error(f"Failed to poll for status after error: {poll_error}")
            
            # If everything failed, return error status
            return {
                "run_id": str(workflow_run.id),
                "error": str(e),
                "status": "failed",
                "outputs": None
            }
    
    async def _run_as_independent(
        self,
        workflow: models.Workflow,
        inputs: Dict[str, Any],
        workflow_service: 'WorkflowService',
        user,
        org_id: uuid.UUID,
        thread_id: Optional[uuid.UUID] = None,
        poll_interval: int = 3,
        timeout: int = 600
    ) -> Dict[str, Any]:
        """
        Submit workflow as an independent run and monitor its execution.
        
        This follows the pattern from test_run_workflow_client.py - submitting
        a workflow run and polling for status without manually updating it.
        
        Args:
            workflow: Workflow to execute
            inputs: Workflow inputs
            workflow_service: Workflow service instance
            user: User executing the workflow
            org_id: Organization ID
            thread_id: Thread ID for conversational workflows
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait for completion
            
        Returns:
            Workflow execution results
        """
        # Submit the workflow run
        run_submit = schemas.WorkflowRunCreate(
            workflow_id=workflow.id,
            inputs=inputs,
            thread_id=thread_id,
        )
        async with get_async_db_as_manager() as db:
            workflow_run = await workflow_service.submit_workflow_run(
                db=db,
                run_submit=run_submit,
                owner_org_id=org_id,
                user=user,
            )
        
        run_id = workflow_run.id
        self.info(f"Submitted workflow run {run_id} for workflow {workflow.id}")
        
        # Poll for completion using the shared polling method
        result = await self._poll_for_completion(
            run_id=run_id,
            workflow_service=workflow_service,
            user=user,
            org_id=org_id,
            poll_interval=poll_interval,
            timeout=timeout
        )
        
        return result
    
    async def process(
        self,
        input_data: Union[WorkflowRunnerInput, Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any
    ) -> WorkflowRunnerOutput:
        """
        Execute the target workflow and return results.
        
        This method:
        1. Fetches the target workflow by name or ID
        2. Maps inputs according to configuration
        3. Executes the workflow (subprocess or independent)
        4. Monitors execution and collects results
        5. Filters outputs and prepares response
        
        Args:
            input_data: Node input data
            runtime_config: Optional runtime configuration
            *args: Additional arguments
            **kwargs: Additional keyword arguments including context
            
        Returns:
            WorkflowRunnerOutput with execution results
            
        Raises:
            ValueError: If workflow execution fails and fail_on_workflow_error is True
        """
        # Since we're using DynamicSchema, input_data is already a dict of arbitrary fields
        if not isinstance(input_data, dict):
            input_data = input_data.model_dump() if hasattr(input_data, 'model_dump') else dict(input_data)
        
        # Get context from kwargs (following crawler_scraper_node pattern)
        from workflow_service.services.external_context_manager import ExternalContextManager
        runtime_config = runtime_config.get("configurable")
        app_context: Optional[Dict[str, Any]] = runtime_config.get(APPLICATION_CONTEXT_KEY)
        external_context= runtime_config.get(EXTERNAL_CONTEXT_MANAGER_KEY)  # : ExternalContextManager 
        
        if not external_context:
            raise ValueError("External context is required for workflow execution")
        
        # Extract required context from app_context which contains workflow_run_job and user
        # This follows the pattern from worker.py lines 311-314
        workflow_run_job = app_context.get("workflow_run_job")
        user = app_context.get("user")
        
        if not workflow_run_job:
            raise ValueError("workflow_run_job is required in app_context for workflow execution")
        
        # Extract from workflow_run_job
        org_id = workflow_run_job.owner_org_id
        parent_run_id = workflow_run_job.run_id  # Current run becomes parent
        
        if not user:
            raise ValueError("User is required in app_context for workflow execution")
        if not org_id:
            raise ValueError("Organization ID is required for workflow execution")
        
        # Get workflow service using dependency injection like in worker.py
        from kiwi_app.workflow_app.dependencies import get_workflow_service
        workflow_service = await get_workflow_service()
        
        # Extract special control fields if present (prefixed with underscore)
        override_workflow_name = input_data.pop('_override_workflow_name', None)
        override_workflow_id = input_data.pop('_override_workflow_id', None) 
        override_workflow_version = input_data.pop('_override_workflow_version', None)
        thread_id_str = input_data.pop('_thread_id', None)
        
        # Determine workflow identification (runtime overrides take precedence)
        workflow_name = override_workflow_name or self.config.workflow_name
        workflow_id = override_workflow_id or self.config.workflow_id
        workflow_version = override_workflow_version or self.config.workflow_version
        
        # Track execution start time
        start_time = datetime.now(timezone.utc)
        
        try:
            # Fetch the target workflow
            self.info(f"Fetching workflow: name={workflow_name}, id={workflow_id}, version={workflow_version}")
            workflow = await self._fetch_workflow(
                workflow_service=workflow_service,
                user=user,
                org_id=org_id,
                workflow_name=workflow_name,
                workflow_id=workflow_id,
                workflow_version=workflow_version
            )

            workflow_name  = workflow.name
            workflow_id = workflow.id
            workflow_version = workflow.version_tag

            # When workflow_name is provided, check app_artifacts for input specifications
            workflow_inputs_spec = {}
            if workflow_name:
                # Try to find matching workflow in app_artifacts by name
                app_workflow = DEFAULT_ALL_WORKFLOWS.get(workflow_name)
                if app_workflow:
                    self.info(f"Found workflow '{workflow_name}' in app_artifacts'")
                    workflow_inputs_spec = app_workflow.get_processed_inputs(DEFAULT_USER_DOCUMENTS_CONFIG)
                    # Use version from app_artifacts if not specified
                    if not workflow_version and app_workflow.version:
                        workflow_version = app_workflow.version
                else:
                    self.info(f"Workflow '{workflow_name}' not found in app_artifacts, proceeding without default inputs")
            
            # Map inputs - input_data now contains all the dynamic fields
            mapped_inputs = await self._map_inputs(
                node_inputs=input_data,  # All remaining fields after popping control fields
                workflow_inputs_spec=workflow_inputs_spec,
                input_mapping=self.config.input_mapping
            )

            # Attempt cache lookup if enabled
            cached_result = None
            if self.config.enable_workflow_cache:
                # Compute input hash (same scheme used by DAO when creating runs)
                input_hash = self._compute_input_hash(mapped_inputs)
                if input_hash:
                    # Determine lookback window
                    lookback_days = max(1, int(self.config.cache_lookback_period))
                    from datetime import timedelta
                    since_ts = datetime.now(timezone.utc) - timedelta(days=lookback_days)
                    # Query recent successful runs by input hash, preferring name-based search
                    # TODO: NOTE: this workflow run caching (Org level, not user level) may be buggy due to not being user specific!
                    #     inputs may still make it work, but what happens when 2 org users run the same workflow with same inputs?? the files for 1 user won't exist if not is_shared!
                    try:
                        async with get_async_db_as_manager() as db:
                            recent_runs = []
                            if workflow.name:
                                recent_runs = await workflow_service.workflow_run_dao.find_recent_completed_runs_by_name_and_input_hash(
                                    db=db,
                                    workflow_name=workflow.name,
                                    owner_org_id=org_id,
                                    input_hash=input_hash,
                                    since_ts=since_ts,
                                    limit=5,
                                )
                            if not recent_runs:
                                # Fallback to workflow_id-based search
                                recent_runs = await workflow_service.workflow_run_dao.find_recent_completed_runs_by_input_hash(
                                    db=db,
                                    workflow_id=workflow.id,
                                    owner_org_id=org_id,
                                    input_hash=input_hash,
                                    since_ts=since_ts,
                                    limit=5,
                                )
                        # Evaluate candidates
                        if self.config.check_error_free_logs:
                            # Strict: pick the first candidate with zero error logs
                            for past_run in recent_runs:
                                has_errors = await self._has_error_logs_for_run(
                                    workflow_service=workflow_service,
                                    run=past_run,
                                    user=user,
                                )
                                if not has_errors and past_run.outputs:
                                    cached_result = {
                                        "run_id": str(past_run.id),
                                        "status": "completed",
                                        "outputs": past_run.outputs,
                                        "error": None,
                                        "started_at": past_run.started_at.isoformat() if past_run.started_at else None,
                                        "completed_at": past_run.ended_at.isoformat() if past_run.ended_at else None,
                                    }
                                    break
                        else:
                            # Lenient: pick the recent run with the fewest error logs (prefer 0 if any)
                            best_tuple = None  # (error_count, ended_at, run)
                            for past_run in recent_runs:
                                try:
                                    async with get_async_db_as_manager() as db:
                                        logs = await workflow_service.get_run_logs(db=db, run=past_run, skip=0, limit=5000)
                                except Exception:
                                    # If logs retrieval fails, penalize with high error count
                                    error_count = 10**9
                                else:
                                    error_count = 0
                                    for entry in getattr(logs, 'logs', []) or []:
                                        level = (entry.level if hasattr(entry, 'level') else str(entry.get('level', '') if isinstance(entry, dict) else '')).upper()
                                        if level in {"ERROR", "CRITICAL"}:
                                            error_count += 1
                                ended_at = getattr(past_run, 'ended_at', None) or datetime.now(timezone.utc)
                                candidate = (error_count, ended_at, past_run)
                                if best_tuple is None or candidate < best_tuple:
                                    best_tuple = candidate
                            if best_tuple and best_tuple[0] < 10**9:
                                chosen = best_tuple[2]
                                if chosen and chosen.outputs:
                                    cached_result = {
                                        "run_id": str(chosen.id),
                                        "status": "completed",
                                        "outputs": chosen.outputs,
                                        "error": None,
                                        "started_at": chosen.started_at.isoformat() if chosen.started_at else None,
                                        "completed_at": ended_at.isoformat() if ended_at else None,
                                    }
                    except Exception as cache_err:
                        self.warning(f"Cache lookup skipped due to error: {cache_err}")

            if cached_result is not None:
                # Use cached outputs without running the workflow
                end_time = datetime.now(timezone.utc)
                duration = (end_time - start_time).total_seconds()
                workflow_outputs = await self._filter_outputs(
                    workflow_outputs=cached_result.get("outputs"),
                    output_fields=self.config.output_fields,
                ) if cached_result.get("outputs") else None

                self.info(f"Using cached result for workflow <{workflow.name}> from workflow run: {cached_result.get('run_id')} executed at {cached_result.get('started_at')}")

                return WorkflowRunnerOutput(
                    workflow_id=str(workflow.id),
                    workflow_name=workflow.name,
                    workflow_version=workflow.version_tag,
                    run_id=cached_result.get("run_id", "unknown"),
                    status=cached_result.get("status", "completed"),
                    workflow_outputs=workflow_outputs,
                    execution_mode=self.config.execution_mode.value,
                    started_at=start_time.isoformat(),
                    completed_at=end_time.isoformat(),
                    duration_seconds=duration,
                    error_message=None,
                    error_details=None,
                    parent_run_id=str(parent_run_id) if self.config.execution_mode == ExecutionMode.SUBPROCESS else None,
                )
            
            # Parse thread_id if provided
            thread_id_str = uuid.UUID(thread_id_str) if thread_id_str else None
            
            # Execute workflow based on mode
            self.info(f"Executing workflow '{workflow.name}' in {self.config.execution_mode} mode")
            
            if self.config.execution_mode == ExecutionMode.SUBPROCESS:
                # Run as subprocess with parent-child relationship
                result = await self._run_as_subprocess(
                    workflow=workflow,
                    inputs=mapped_inputs,
                    external_context=external_context,
                    workflow_service=workflow_service,
                    user=user,
                    org_id=org_id,
                    workflow_run_job=workflow_run_job,
                    parent_run_id=parent_run_id,
                    thread_id=thread_id_str
                )
            else:
                # Run as independent workflow
                result = await self._run_as_independent(
                    workflow=workflow,
                    inputs=mapped_inputs,
                    workflow_service=workflow_service,
                    user=user,
                    org_id=org_id,
                    thread_id=thread_id_str,
                    poll_interval=self.config.poll_interval_seconds,
                    timeout=self.config.timeout_seconds
                )
            
            # Calculate execution duration
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            # Extract and filter outputs
            # Both subprocess and independent modes now return 'outputs' field
            workflow_outputs = result.get("outputs")
            if workflow_outputs:
                workflow_outputs = await self._filter_outputs(
                    workflow_outputs=workflow_outputs,
                    output_fields=self.config.output_fields
                )
            
            # Determine final status
            status = result.get("status", "unknown")
            error_message = result.get("error")
            
            # Check if we should fail on workflow error
            if self.config.fail_on_workflow_error and status in ["failed", "timeout"]:
                raise ValueError(
                    f"Workflow execution failed: {error_message or 'Unknown error'}"
                )
            
            # Prepare output
            return WorkflowRunnerOutput(
                workflow_id=str(workflow.id),
                workflow_name=workflow.name,
                workflow_version=workflow.version_tag,
                run_id=result.get("run_id", "unknown"),
                status=status,
                workflow_outputs=workflow_outputs,
                execution_mode=self.config.execution_mode.value,
                started_at=start_time.isoformat(),
                completed_at=end_time.isoformat(),
                duration_seconds=duration,
                error_message=error_message,
                error_details={"error": error_message} if error_message else None,
                parent_run_id=str(parent_run_id) if self.config.execution_mode == ExecutionMode.SUBPROCESS else None
            )
            
        except ValueError:
            # Re-raise node errors
            raise
        except Exception as e:
            # Log and wrap unexpected errors
            self.error(f"Unexpected error in workflow runner: {e}", exc_info=True)
            
            # Calculate duration even on error
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            if self.config.fail_on_workflow_error:
                raise ValueError(f"Workflow execution failed unexpectedly: {e}")
            
            # Return error details if not failing
            return WorkflowRunnerOutput(
                workflow_id=workflow_id or "unknown",
                workflow_name=workflow_name or "unknown",
                workflow_version=workflow_version,
                run_id="error",
                status="failed",
                workflow_outputs=None,
                execution_mode=self.config.execution_mode.value,
                started_at=start_time.isoformat(),
                completed_at=end_time.isoformat(),
                duration_seconds=duration,
                error_message=str(e),
                error_details={"exception": str(e), "type": type(e).__name__}
            )
