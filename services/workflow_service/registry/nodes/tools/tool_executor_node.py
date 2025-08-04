"""
Tool Executor Node for executing tool calls from the registry.

This module provides a node that can execute tool calls by looking up tools in the registry
and running them with the provided inputs. It handles success/failure tracking and timing.
"""
import asyncio
import json
import time
import traceback
from typing import Any, ClassVar, Dict, List, Optional, Type, Union
from uuid import uuid4

from pydantic import Field, BaseModel

from kiwi_app.workflow_app.constants import LaunchStatus
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY
)
from workflow_service.registry.nodes.core.base import BaseNode
from workflow_service.registry.schemas.base import BaseNodeConfig, BaseNodeConfig, BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode
from workflow_service.registry.nodes.llm.llm_node import ToolCall, ToolOutput

from langgraph.config import get_stream_writer


# Below commented objects for reference only

# class ToolOutput(BaseNodeConfig):
#     """Represents the output of a tool execution."""
#     tool_call_id: str = Field(description="ID of the tool call that generated this output")
#     content: str = Field(description="The output content from the tool execution")
#     type: str = Field(default="tool", description="Type of the output (always 'tool')")
#     name: str = Field(description="Name of the tool that was executed")
#     status: str = Field(description="Status of the execution ('success' or 'error')")
#     error_message: Optional[str] = Field(None, description="Error message if execution failed")

# class ToolCall(BaseNodeConfig):
#     """Represents a tool call made by the model."""
#     tool_name: str = Field(description="Name of the tool called")
#     tool_input: Dict[str, Any] = Field(description="Input provided to the tool")
#     tool_id: Optional[str] = Field(None, description="ID of the tool call (used by some providers)")



###########################
###### Input Schema ######
###########################


class ToolExecutorNodeInputSchema(DynamicSchema):
    """Input schema for the ToolExecutor node."""
    INTERNAL_FIELDS: ClassVar[List[str]] = [ "tool_calls", "execution_timeout", "prior_successful_calls", "prior_failed_calls" ]
    
    tool_calls: List[ToolCall] = Field(
        description="List of tool calls to execute"
    )
    execution_timeout: Optional[float] = Field(
        None,
        description="Timeout in seconds for each tool execution (overrides config)"
    )
    prior_successful_calls: int = Field(
        default=0,
        description="Number of successful tool calls from previous executions to count towards limit"
    )
    prior_failed_calls: int = Field(
        default=0,
        description="Number of failed tool calls from previous executions to count towards limit"
    )


###########################
###### Output Schema ######
###########################


class ToolCallMetadata(BaseNodeConfig):
    """Metadata about a tool call execution."""
    tool_call_id: str = Field(description="ID of the tool call")
    tool_name: str = Field(description="Name of the tool that was called")
    success: bool = Field(description="Whether the tool call was successful")
    execution_time: float = Field(description="Time taken to execute the tool in seconds")
    error_message: Optional[str] = Field(None, description="Error message if execution failed")
    error_type: Optional[str] = Field(None, description="Type of error that occurred")


class ToolExecutorNodeOutputSchema(BaseNodeConfig):
    """Output schema for the ToolExecutor node."""
    tool_outputs: List[ToolOutput] = Field(
        description="List of tool execution outputs"
    )
    internal_tool_user_prompt: Optional[str] = Field(
        "",
        description="Internal tool user prompt"
    )
    tool_call_metadata: List[ToolCallMetadata] = Field(
        description="Metadata about each tool call execution including success/failure and timing"
    )
    total_execution_time: float = Field(
        description="Total time taken to execute all tool calls in seconds"
    )
    successful_calls: int = Field(
        description="Number of successful tool calls"
    )
    failed_calls: int = Field(
        description="Number of failed tool calls"
    )
    state_changes: Optional[Dict[str, Any]] = Field(
        None,
        description="State changes made by the tool executions"
    )


###########################
###### Config Schema ######
###########################

class ToolNodeConfig(BaseNodeConfig):
    """Configuration for a tool node in the ToolExecutor."""
    tool_name: str = Field(description="Tool name")
    version: Optional[str] = Field(None, description="Tool version (uses latest if not specified)")
    tool_config: Optional[Dict[str, Any]] = Field(
        None, 
        description="Configuration to pass to the tool node during instantiation"
    )
    map_executor_input_fields_to_tool_input: Optional[bool] = Field(
        None,
        description="Whether to map executor input fields to tool inputs (overrides global setting if specified)"
    )
    mappings: Optional[Dict[str, str]] = Field(
        None,
        description="Mapping of executor input field names to tool input field names. If not provided, auto-maps fields with same names."
    )


class ToolExecutorNodeConfigSchema(BaseNodeConfig):
    """Configuration schema for the ToolExecutor node."""
    default_timeout: Optional[float] = Field(
        30.0,
        description="Default timeout in seconds for tool execution"
    )
    max_concurrent_executions: int = Field(
        5,
        description="Maximum number of tools to execute concurrently"
    )
    continue_on_error: bool = Field(
        True,
        description="Whether to continue executing other tools if one fails"
    )
    include_error_details: bool = Field(
        True,
        description="Whether to include detailed error information in outputs"
    )
    tool_configs: Optional[List[ToolNodeConfig]] = Field(
        None,
        description="List of tool configurations with specific versions and configs to use"
    )
    restrict_tools_to_configured_tools_only: bool = Field(
        False,
        description="Whether to restrict tool execution to only tools specified in tool_configs"
    )
    tool_call_limit: Optional[int] = Field(
        None,
        description="Maximum number of tool calls allowed per execution (None for no limit)"
    )
    consider_failed_calls_in_limit: bool = Field(
        True,
        description="Whether to count failed tool calls towards the tool_call_limit"
    )
    map_executor_input_fields_to_tool_input: bool = Field(
        True,
        description="Global setting: whether to map executor input fields to tool inputs (can be overridden per tool)"
    )


###########################


class ToolExecutorNode(BaseDynamicNode):  # BaseNode[ToolExecutorNodeInputSchema, ToolExecutorNodeOutputSchema, ToolExecutorNodeConfigSchema]
    """
    Tool Executor Node that executes tool calls from the registry.
    
    This node takes a list of tool calls and executes them by looking up the corresponding
    nodes in the registry. It provides detailed execution metadata including timing,
    success/failure status, and error handling.
    
    Features:
    - Concurrent execution of multiple tool calls
    - Comprehensive error handling and reporting
    - Execution timing and metadata tracking
    - Configurable timeouts and execution limits
    - Support for continuing execution when individual tools fail
    """
    node_name: ClassVar[str] = "tool_executor"
    node_version: ClassVar[str] = "1.0.0"
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[Type[ToolExecutorNodeInputSchema]] = ToolExecutorNodeInputSchema
    output_schema_cls: ClassVar[Type[ToolExecutorNodeOutputSchema]] = ToolExecutorNodeOutputSchema
    config_schema_cls: ClassVar[Type[ToolExecutorNodeConfigSchema]] = ToolExecutorNodeConfigSchema
    
    # instance config
    config: ToolExecutorNodeConfigSchema

    async def process(
        self, 
        input_data: ToolExecutorNodeInputSchema, 
        runtime_config: Dict[str, Any], 
        *args: Any, 
        **kwargs: Any
    ) -> ToolExecutorNodeOutputSchema:
        """
        Process tool calls by executing them through the registry.
        
        Args:
            input_data: The input data containing tool calls to execute
            config: Runtime configuration containing context and registry access
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments
            
        Returns:
            ToolExecutorNodeOutputSchema: Results of all tool executions with metadata
        """
        if isinstance(input_data, dict):
            input_data = self.input_schema_cls(**input_data)
            
        # Validate that we have tool calls to execute
        if not input_data.tool_calls:
            self.warning("No tool calls provided for execution")
            return ToolExecutorNodeOutputSchema(
                tool_outputs=[],
                tool_call_metadata=[],
                total_execution_time=0.0,
                successful_calls=0,
                failed_calls=0
            )
        
        if not runtime_config:
            self.error("Missing runtime config (config argument).")
            return self._create_error_response(
                input_data.tool_calls,
                "Missing runtime configuration"
            )


        # The 'config' argument (runtime_config_arg) itself should contain these keys as per test setup
        # and how LangGraph passes RunnableConfig.
        app_context: Optional[Dict[str, Any]] = runtime_config.get("configurable", {}).get(APPLICATION_CONTEXT_KEY)
        ext_context = runtime_config.get("configurable", {}).get(EXTERNAL_CONTEXT_MANAGER_KEY)
        
        if not app_context or not ext_context:
            self.error(f"Missing required keys in runtime_config: {APPLICATION_CONTEXT_KEY}, {EXTERNAL_CONTEXT_MANAGER_KEY}")
            return self._create_error_response(
                input_data.tool_calls,
                "Missing required context in runtime configuration"
            )
        
        registry = ext_context.db_registry
        if not registry:
            self.error("Registry not available in external context")
            return self._create_error_response(
                input_data.tool_calls,
                "Registry not available"
            )
        
        # Log tool configuration information
        self.info(f"Starting execution of {len(input_data.tool_calls)} tool calls")
        self.debug(self._get_tool_config_info())
        
        # Check tool call limits before execution
        if self.config.tool_call_limit is not None:
            # Calculate current call count including priors
            if self.config.consider_failed_calls_in_limit:
                prior_total_calls = input_data.prior_successful_calls + input_data.prior_failed_calls
            else:
                prior_total_calls = input_data.prior_successful_calls
            
            self.debug(f"Tool call limit: {self.config.tool_call_limit}, Prior calls: {prior_total_calls} "
                      f"(successful: {input_data.prior_successful_calls}, failed: {input_data.prior_failed_calls})")
            
            if prior_total_calls >= self.config.tool_call_limit:
                # Limit already reached, mark all as failed
                self.warning(f"Tool call limit ({self.config.tool_call_limit}) already reached. "
                            f"Marking all {len(input_data.tool_calls)} tool calls as failed.")
                return self._create_limit_reached_response(input_data.tool_calls)
        
        # Record start time for total execution tracking
        total_start_time = time.time()
        
        # Extract non-internal fields from executor input for mapping to tools
        executor_extra_fields = {}
        if hasattr(input_data, 'model_dump'):
            all_input_fields = input_data.model_dump()
            internal_fields = getattr(input_data.__class__, 'INTERNAL_FIELDS', [])
            executor_extra_fields = {
                field: value for field, value in all_input_fields.items() 
                if field not in internal_fields
            }
            
            if executor_extra_fields:
                self.debug(f"Extracted {len(executor_extra_fields)} additional fields for tool mapping: {list(executor_extra_fields.keys())}")
        
        # Execute tool calls (potentially concurrently) with limit checking
        if self.config.max_concurrent_executions > 1:
            tool_outputs, tool_metadata = await self._execute_tools_concurrently(
                input_data.tool_calls,
                registry,
                runtime_config,
                input_data.execution_timeout,
                input_data.prior_successful_calls,
                input_data.prior_failed_calls,
                executor_extra_fields
            )
        else:
            tool_outputs, tool_metadata = await self._execute_tools_sequentially(
                input_data.tool_calls,
                registry,
                runtime_config,
                input_data.execution_timeout,
                input_data.prior_successful_calls,
                input_data.prior_failed_calls,
                executor_extra_fields
            )
        
        total_execution_time = time.time() - total_start_time
        
        # Calculate summary statistics
        successful_calls = sum(1 for metadata in tool_metadata if metadata.success)
        failed_calls = len(tool_metadata) - successful_calls
        
        self.info(f"Executed {len(input_data.tool_calls)} tool calls: {successful_calls} successful, {failed_calls} failed")

        state_changes = {}
        for tool_output in tool_outputs:
            if tool_output.state_changes:
                state_changes.update(tool_output.state_changes)
        
        return ToolExecutorNodeOutputSchema(
            tool_outputs=tool_outputs,
            tool_call_metadata=tool_metadata,
            total_execution_time=total_execution_time,
            successful_calls=successful_calls,
            failed_calls=failed_calls,
            state_changes=state_changes,
        )
    
    async def _execute_tools_sequentially(
        self,
        tool_calls: List[ToolCall],
        registry,
        runtime_config: Dict[str, Any],
        timeout_override: Optional[float],
        prior_successful_calls: int,
        prior_failed_calls: int,
        executor_extra_fields: Dict[str, Any]
    ) -> tuple[List[ToolOutput], List[ToolCallMetadata]]:
        """
        Execute tool calls one by one sequentially.
        
        Args:
            tool_calls: List of tool calls to execute
            registry: The registry to look up tools from
            config: Runtime configuration
            timeout_override: Optional timeout override from input
            prior_successful_calls: Number of successful calls from previous executions
            prior_failed_calls: Number of failed calls from previous executions
            executor_extra_fields: Additional input data from the executor
            
        Returns:
            Tuple of (tool_outputs, tool_metadata)
        """
        tool_outputs = []
        tool_metadata = []
        
        # Calculate initial call counts
        current_successful = prior_successful_calls
        current_failed = prior_failed_calls
        
        for i, tool_call in enumerate(tool_calls):
            # Check if we should continue based on previous failures
            if not self.config.continue_on_error and tool_metadata and not tool_metadata[-1].success:
                # Previous call failed and we're not continuing on error
                self.warning(f"Skipping tool call {tool_call.tool_name} due to previous failure")
                continue
            
            # Check tool call limit before executing this tool
            if self.config.tool_call_limit is not None:
                if self.config.consider_failed_calls_in_limit:
                    current_total_calls = current_successful + current_failed
                else:
                    current_total_calls = current_successful
                
                if current_total_calls >= self.config.tool_call_limit:
                    # Limit reached, mark remaining tools as failed
                    self.warning(f"Tool call limit ({self.config.tool_call_limit}) reached. "
                               f"Marking remaining {len(tool_calls) - i} tool calls as failed.")
                    
                    # Create limit reached outputs for remaining tools
                    for remaining_tool_call in tool_calls[i:]:
                        limit_output, limit_metadata = self._create_limit_reached_output_and_metadata(
                            remaining_tool_call
                        )
                        tool_outputs.append(limit_output)
                        tool_metadata.append(limit_metadata)
                    
                    break
            
            # Execute the tool
            output, metadata = await self._execute_single_tool(
                tool_call,
                registry,
                runtime_config,
                timeout_override,
                prior_successful_calls,
                prior_failed_calls,
                executor_extra_fields
            )
            
            tool_outputs.append(output)
            tool_metadata.append(metadata)
            
            # Update call counts
            if metadata.success:
                current_successful += 1
            else:
                current_failed += 1
        
        return tool_outputs, tool_metadata
    
    async def _execute_tools_concurrently(
        self,
        tool_calls: List[ToolCall],
        registry,
        runtime_config: Dict[str, Any],
        timeout_override: Optional[float],
        prior_successful_calls: int,
        prior_failed_calls: int,
        executor_extra_fields: Dict[str, Any]
    ) -> tuple[List[ToolOutput], List[ToolCallMetadata]]:
        """
        Execute tool calls concurrently with limited concurrency.
        
        Note: When tool_call_limit is set, this method falls back to sequential execution
        to ensure proper limit checking and ordering.
        
        Args:
            tool_calls: List of tool calls to execute
            registry: The registry to look up tools from
            config: Runtime configuration
            timeout_override: Optional timeout override from input
            prior_successful_calls: Number of successful calls from previous executions
            prior_failed_calls: Number of failed calls from previous executions
            executor_extra_fields: Additional input data from the executor
            
        Returns:
            Tuple of (tool_outputs, tool_metadata)
        """
        # If tool call limit is set, fall back to sequential execution for proper limit checking
        if self.config.tool_call_limit is not None:
            self.debug("Tool call limit is set, falling back to sequential execution for proper limit checking")
            return await self._execute_tools_sequentially(
                tool_calls,
                registry,
                runtime_config,
                timeout_override,
                prior_successful_calls,
                prior_failed_calls,
                executor_extra_fields
            )
        
        # Proceed with concurrent execution (no limits to check)
        semaphore = asyncio.Semaphore(self.config.max_concurrent_executions)
        
        async def execute_with_semaphore(tool_call: ToolCall):
            async with semaphore:
                return await self._execute_single_tool(
                    tool_call,
                    registry,
                    runtime_config,
                    timeout_override,
                    prior_successful_calls,
                    prior_failed_calls,
                    executor_extra_fields
                )
        
        # Execute all tool calls concurrently
        results = await asyncio.gather(
            *[execute_with_semaphore(tool_call) for tool_call in tool_calls],
            return_exceptions=True
        )
        
        tool_outputs = []
        tool_metadata = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Handle case where gather itself failed
                tool_call = tool_calls[i]
                tool_call_id = tool_call.tool_id or f"tool_call_{i}"
                
                error_output = ToolOutput(
                    tool_call_id=tool_call_id,
                    content=f"Execution failed: {str(result)}",
                    name=tool_call.tool_name,
                    status="error",
                    error_message=str(result)
                )
                
                error_metadata = ToolCallMetadata(
                    tool_call_id=tool_call_id,
                    tool_name=tool_call.tool_name,
                    success=False,
                    execution_time=0.0,
                    error_message=str(result),
                    error_type=type(result).__name__
                )
                
                tool_outputs.append(error_output)
                tool_metadata.append(error_metadata)
            else:
                output, metadata = result
                tool_outputs.append(output)
                tool_metadata.append(metadata)
        
        return tool_outputs, tool_metadata
    
    async def _execute_single_tool(
        self,
        tool_call: ToolCall,
        registry,
        runtime_config: Dict[str, Any],
        timeout_override: Optional[float],
        prior_successful_calls: int,
        prior_failed_calls: int,
        executor_extra_fields: Dict[str, Any]
    ) -> tuple[ToolOutput, ToolCallMetadata]:
        """
        Execute a single tool call.
        
        Args:
            tool_call: The tool call to execute
            registry: The registry to look up the tool from
            config: Runtime configuration
            timeout_override: Optional timeout override from input
            prior_successful_calls: Number of successful calls from previous executions
            prior_failed_calls: Number of failed calls from previous executions
            executor_extra_fields: Additional input data from the executor
            
        Returns:
            Tuple of (ToolOutput, ToolCallMetadata)
        """
        tool_call_id = tool_call.tool_id or str(uuid4())
        start_time = time.time()

        # print(f"\n\nTOOL CALL: {tool_call.tool_name}\n\n")
        # import ipdb; ipdb.set_trace()

        try:
            stream_writer = get_stream_writer()
        except Exception as e:
            self.warning(f"Failed to get stream writer: {str(e)}")
            stream_writer = None
        
        try:
            # Check if tool execution is restricted and validate against configured tools
            if self.config.restrict_tools_to_configured_tools_only:
                if not self.config.tool_configs:
                    raise ValueError(
                        f"Tool execution is restricted but no tool_configs provided. "
                        f"Cannot execute tool '{tool_call.tool_name}'"
                    )
                
                configured_tool_names = [tc.tool_name for tc in self.config.tool_configs]
                if tool_call.tool_name not in configured_tool_names:
                    raise ValueError(
                        f"Tool '{tool_call.tool_name}' is not in the configured tools list. "
                        f"Available tools: {configured_tool_names}"
                    )
            
            # Determine tool version, config, and mapping settings to use
            tool_version = None
            tool_node_config = {}
            tool_mapping_config = None
            
            # Check if this tool has specific configuration
            if self.config.tool_configs:
                for tool_config in self.config.tool_configs:
                    if tool_config.tool_name == tool_call.tool_name:
                        tool_version = tool_config.version
                        if tool_config.tool_config:
                            tool_node_config = tool_config.tool_config
                        tool_mapping_config = tool_config
                        break
            
            # Look up the tool node in the registry with specific version if configured
            tool_node_class: Type[BaseNode] = registry.get_node(
                tool_call.tool_name, 
                version=tool_version,  # Use configured version or None for latest
                return_if_tool=True,
            )
            
            if not tool_node_class:
                if tool_version:
                    raise ValueError(
                        f"Tool '{tool_call.tool_name}' version '{tool_version}' not found in registry"
                    )
                else:
                    raise ValueError(f"Tool '{tool_call.tool_name}' not found in registry")
            
            # Validate that it's actually a tool node
            if not getattr(tool_node_class, 'node_is_tool', False):
                raise ValueError(f"Node '{tool_call.tool_name}' is not marked as a tool")
            
            # Configure the tool node with provided config and enable prefect_mode for logging
            # Always create a new instance of the tool node with the specified configuration
            # to avoid issues with shared instances from the registry.
            tool_node_kwargs = {
                'node_id': f"TOOL_CALL:{tool_call.tool_name}_{tool_call_id}",
                'prefect_mode': self.prefect_mode, # Enable prefect mode for logging
                'config': tool_node_config,  #  if tool_node_config else None # Pass None if no specific config
            }

            # tool_node here is the class retrieved from the registry.
            configured_tool_node = tool_node_class(**tool_node_kwargs)
            
            # Get the tool's input schema and validate the input
            input_schema_cls = configured_tool_node.input_schema_cls
            if not input_schema_cls:
                raise ValueError(f"Tool '{tool_call.tool_name}' has no input schema")
            
            # Prepare tool input by merging tool call input with mapped executor inputs
            final_tool_input = self._prepare_tool_input(
                tool_call=tool_call,
                tool_schema=input_schema_cls,
                tool_mapping_config=tool_mapping_config,
                executor_input_data=executor_extra_fields
            )
            
            # Create and validate the input data
            try:
                validated_input = input_schema_cls(**final_tool_input)
            except Exception as e:
                raise ValueError(f"Invalid input for tool '{tool_call.tool_name}': {str(e)}")
            
            # Determine timeout
            timeout = timeout_override or self.config.default_timeout

            if stream_writer:
                stream_writer({"event_type": "tool_call", "tool_call_id": tool_call_id, "tool_name": tool_call.tool_name, "input": validated_input, "status": "processing", "node_id": self.node_id})
            
            # Execute the tool with timeout
            if timeout and timeout > 0:
                result = await asyncio.wait_for(
                    configured_tool_node.process(validated_input, runtime_config),
                    timeout=timeout
                )
            else:
                result = await configured_tool_node.process(validated_input, runtime_config)
            
            execution_time = time.time() - start_time
            
            # Convert result to string format for tool output
            state_changes = None
            if isinstance(result, BaseModel):
                exclude_keys = None
                if hasattr(result, "state_changes"):
                    state_changes = result.state_changes
                    exclude_keys = {"state_changes"}
                content = result.model_dump_json(indent=2, exclude=exclude_keys)
            elif isinstance(result, dict):
                content = json.dumps(result, indent=2, default=str)
            else:
                content = str(result)

            ######  Handle Tool Runtime Errors ######
            success = getattr(result, "success", True)
            if not success:
                error_msg = getattr(result, "message", "Tool execution failed")
                self.warning(f"Tool '{tool_call.tool_name}' failed: {error_msg}")

                if stream_writer:
                    stream_writer({"event_type": "tool_call", "tool_call_id": tool_call_id, "tool_name": tool_call.tool_name, "status": "error", "error_message": error_msg, "node_id": self.node_id})
                
                tool_output, tool_metadata = self._create_error_output_and_metadata(
                    tool_call_id,
                    tool_call.tool_name,
                    error_msg,
                    execution_time,
                    "ToolExecutionError"
                )

                tool_output.state_changes = state_changes

                return tool_output, tool_metadata

            ###### ###### ###### ###### ###### ######

            # Create successful output and metadata
            tool_output = ToolOutput(
                tool_call_id=tool_call_id,
                content=content,
                name=tool_call.tool_name,
                status="success",
                state_changes=state_changes,
            )

            if stream_writer:
                stream_writer({"event_type": "tool_call", "tool_call_id": tool_call_id, "tool_name": tool_call.tool_name, "output": content, "status": "success", "node_id": self.node_id})
            
            tool_metadata = ToolCallMetadata(
                tool_call_id=tool_call_id,
                tool_name=tool_call.tool_name,
                success=True,
                execution_time=execution_time
            )
            
            version_info = f" (v{tool_version})" if tool_version else ""
            self.debug(f"Successfully executed tool '{tool_call.tool_name}{version_info}' in {execution_time:.2f}s")
            
            return tool_output, tool_metadata
            
        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            error_msg = f"Tool execution timed out after {timeout}s"
            
            self.warning(f"Tool '{tool_call.tool_name}' timed out after {timeout}s")

            if stream_writer:
                stream_writer({"event_type": "tool_call", "tool_call_id": tool_call_id, "tool_name": tool_call.tool_name, "status": "error", "error_message": error_msg, "node_id": self.node_id})
            
            return self._create_error_output_and_metadata(
                tool_call_id,
                tool_call.tool_name,
                error_msg,
                execution_time,
                "TimeoutError"
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = str(e)
            error_type = type(e).__name__

            if stream_writer:
                stream_writer({"event_type": "tool_call", "tool_call_id": tool_call_id, "tool_name": tool_call.tool_name, "status": "error", "error_message": error_msg, "error_type": error_type, "node_id": self.node_id})
            
            # Include full traceback in logs but not in output unless configured
            if self.config.include_error_details:
                full_error = f"{error_msg}\n\nTraceback:\n{traceback.format_exc()}"
                self.error(f"Tool '{tool_call.tool_name}' failed: {full_error}")
            else:
                self.error(f"Tool '{tool_call.tool_name}' failed: {error_msg}")
            
            return self._create_error_output_and_metadata(
                tool_call_id,
                tool_call.tool_name,
                error_msg,
                execution_time,
                error_type
            )
    
    def _create_error_output_and_metadata(
        self,
        tool_call_id: str,
        tool_name: str,
        error_message: str,
        execution_time: float,
        error_type: str
    ) -> tuple[ToolOutput, ToolCallMetadata]:
        """
        Create error output and metadata for a failed tool call.
        
        Args:
            tool_call_id: ID of the tool call
            tool_name: Name of the tool
            error_message: Error message
            execution_time: Time taken before failure
            error_type: Type of error
            
        Returns:
            Tuple of (ToolOutput, ToolCallMetadata)
        """
        tool_output = ToolOutput(
            tool_call_id=tool_call_id,
            content=f"Error executing tool: {error_message}",
            name=tool_name,
            status="error",
            error_message=error_message if self.config.include_error_details else "Tool execution failed"
        )
        
        tool_metadata = ToolCallMetadata(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            success=False,
            execution_time=execution_time,
            error_message=error_message,
            error_type=error_type
        )
        
        return tool_output, tool_metadata
    
    def _create_limit_reached_output_and_metadata(
        self,
        tool_call: ToolCall
    ) -> tuple[ToolOutput, ToolCallMetadata]:
        """
        Create output and metadata for a tool call that was not executed due to limit being reached.
        
        Args:
            tool_call: The tool call that wasn't executed
            
        Returns:
            Tuple of (ToolOutput, ToolCallMetadata)
        """
        tool_call_id = tool_call.tool_id or str(uuid4())
        error_message = "limit reached"
        
        tool_output = ToolOutput(
            tool_call_id=tool_call_id,
            content=f"Tool call not executed: {error_message}",
            name=tool_call.tool_name,
            status="error",
            error_message=error_message
        )
        
        tool_metadata = ToolCallMetadata(
            tool_call_id=tool_call_id,
            tool_name=tool_call.tool_name,
            success=False,
            execution_time=0.0,
            error_message=error_message,
            error_type="LimitReachedError"
        )
        
        return tool_output, tool_metadata
    
    def _create_limit_reached_response(
        self,
        tool_calls: List[ToolCall]
    ) -> ToolExecutorNodeOutputSchema:
        """
        Create a response when the tool call limit has already been reached before execution.
        
        Args:
            tool_calls: The tool calls that were supposed to be executed
            
        Returns:
            ToolExecutorNodeOutputSchema with limit reached information
        """
        tool_outputs = []
        tool_metadata = []
        
        for tool_call in tool_calls:
            output, metadata = self._create_limit_reached_output_and_metadata(tool_call)
            tool_outputs.append(output)
            tool_metadata.append(metadata)
        
        return ToolExecutorNodeOutputSchema(
            tool_outputs=tool_outputs,
            tool_call_metadata=tool_metadata,
            total_execution_time=0.0,
            successful_calls=0,
            failed_calls=len(tool_calls)
        )
    
    def _create_error_response(
        self,
        tool_calls: List[ToolCall],
        error_message: str
    ) -> ToolExecutorNodeOutputSchema:
        """
        Create an error response when the entire execution fails.
        
        Args:
            tool_calls: The tool calls that were supposed to be executed
            error_message: The error message
            
        Returns:
            ToolExecutorNodeOutputSchema with error information
        """
        tool_outputs = []
        tool_metadata = []
        
        for i, tool_call in enumerate(tool_calls):
            tool_call_id = tool_call.tool_id or f"tool_call_{i}"
            
            output, metadata = self._create_error_output_and_metadata(
                tool_call_id,
                tool_call.tool_name,
                error_message,
                0.0,
                "ConfigurationError"
            )
            
            tool_outputs.append(output)
            tool_metadata.append(metadata)
        
        return ToolExecutorNodeOutputSchema(
            tool_outputs=tool_outputs,
            tool_call_metadata=tool_metadata,
            total_execution_time=0.0,
            successful_calls=0,
            failed_calls=len(tool_calls)
        )
    
    def _get_tool_config_info(self) -> str:
        """
        Get a formatted string with information about configured tools.
        
        Returns:
            str: Formatted information about tool configurations
        """
        info_lines = []
        
        # Tool configurations
        if not self.config.tool_configs:
            info_lines.append("No tool configurations specified")
        else:
            config_info = []
            for tool_config in self.config.tool_configs:
                version_str = f"v{tool_config.version}" if tool_config.version else "latest"
                config_str = " (with config)" if tool_config.tool_config else ""
                
                # Add mapping information
                mapping_info = ""
                if tool_config.map_executor_input_fields_to_tool_input is not None:
                    mapping_enabled = tool_config.map_executor_input_fields_to_tool_input
                else:
                    mapping_enabled = self.config.map_executor_input_fields_to_tool_input
                
                if mapping_enabled:
                    if tool_config.mappings:
                        mapping_count = len(tool_config.mappings)
                        mapping_info = f" (explicit mappings: {mapping_count})"
                    else:
                        mapping_info = " (auto-mapping)"
                else:
                    mapping_info = " (no mapping)"
                
                config_info.append(f"  - {tool_config.tool_name} ({version_str}){config_str}{mapping_info}")
            
            restriction_info = " (restricted mode)" if self.config.restrict_tools_to_configured_tools_only else ""
            info_lines.append(f"Configured tools{restriction_info}:")
            info_lines.extend(config_info)
        
        # Global field mapping setting
        global_mapping_info = "enabled" if self.config.map_executor_input_fields_to_tool_input else "disabled"
        info_lines.append(f"Global field mapping: {global_mapping_info}")
        
        # Tool call limits
        if self.config.tool_call_limit is not None:
            failed_count_info = " (including failed calls)" if self.config.consider_failed_calls_in_limit else " (successful calls only)"
            info_lines.append(f"Tool call limit: {self.config.tool_call_limit}{failed_count_info}")
        else:
            info_lines.append("No tool call limit set")
        
        return "\n".join(info_lines)

    def _prepare_tool_input(
        self,
        tool_call: ToolCall,
        tool_schema: Type[BaseNodeConfig],
        tool_mapping_config: Optional[ToolNodeConfig],
        executor_input_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Prepare the final tool input by merging tool call inputs with mapped executor inputs.
        
        This method handles the mapping of executor input fields to tool input fields based on configuration:
        1. If mappings are provided in tool config, uses explicit field mappings
        2. If no mappings provided, auto-maps fields with same names between executor input and tool schema
        3. Tool call inputs take precedence over executor inputs when fields overlap (if tool call value is not None)
        
        Args:
            tool_call: The tool call containing input data
            tool_schema: The tool's input schema class
            tool_mapping_config: Tool-specific mapping configuration (if any)
            executor_input_data: Additional input data from the executor
            
        Returns:
            Dict[str, Any]: Final merged input data for the tool
        """
        # Start with tool call input as base
        final_input = dict(tool_call.tool_input)
        
        # Check if field mapping is enabled
        should_map_fields = self.config.map_executor_input_fields_to_tool_input
        if tool_mapping_config and tool_mapping_config.map_executor_input_fields_to_tool_input is not None:
            should_map_fields = tool_mapping_config.map_executor_input_fields_to_tool_input
        
        if not should_map_fields or not executor_input_data:
            return final_input
        
        # Get tool schema field names
        tool_field_names = set(tool_schema.model_fields.keys())
        
        # Determine which executor fields to map
        if tool_mapping_config and tool_mapping_config.mappings:
            # Use explicit mappings
            for executor_field, tool_field in tool_mapping_config.mappings.items():
                if executor_field in executor_input_data and tool_field in tool_field_names:
                    executor_value = executor_input_data[executor_field]
                    
                    # Tool call input takes precedence if not None
                    if tool_field not in final_input or final_input[tool_field] is None:
                        final_input[tool_field] = executor_value
                        self.debug(f"Mapped executor field '{executor_field}' -> tool field '{tool_field}' for tool '{tool_call.tool_name}'")
        else:
            # Auto-map fields with same names
            for executor_field, executor_value in executor_input_data.items():
                if executor_field in tool_field_names:
                    # Tool call input takes precedence if not None
                    if executor_field not in final_input or final_input[executor_field] is None:
                        final_input[executor_field] = executor_value
                        self.debug(f"Auto-mapped field '{executor_field}' for tool '{tool_call.tool_name}'")
        
        return final_input
