"""
Comprehensive tests for ToolExecutorNode functionality.

This module provides extensive testing for the tool executor node including:
- Basic tool execution scenarios
- Concurrent vs sequential execution
- Tool call limits and restrictions
- Error handling and timeouts
- Field mapping between executor input and tool input
- Tool configurations and versions
- Success/failure tracking and metadata
"""
import asyncio
import json
import time
import unittest
import uuid
from typing import Any, ClassVar, Dict, List, Optional, Union
from unittest.mock import Mock, patch

from pydantic import BaseModel, Field

from kiwi_app.workflow_app.constants import LaunchStatus
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY,
    INPUT_NODE_NAME,
    OUTPUT_NODE_NAME,
)
from workflow_service.graph.builder import GraphBuilder
from workflow_service.graph.graph import (
    EdgeMapping,
    EdgeSchema,
    GraphSchema,
    NodeConfig,
)
from workflow_service.graph.runtime.adapter import LangGraphRuntimeAdapter
from workflow_service.registry.nodes.core.base import BaseNode, BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import InputNode, OutputNode
from workflow_service.registry.nodes.llm.llm_node import ToolCall, ToolOutput
from workflow_service.registry.nodes.tools.tool_executor_node import (
    ToolExecutorNode,
    ToolExecutorNodeConfigSchema,
    ToolExecutorNodeInputSchema,
    ToolExecutorNodeOutputSchema,
    ToolNodeConfig,
)
from workflow_service.registry.registry import DBRegistry
from workflow_service.services.external_context_manager import (
    ExternalContextManager,
    get_external_context_manager_with_clients,
)

# Import required schemas and models
from kiwi_app.workflow_app.schemas import WorkflowRunJobCreate


# --- Fake Tool Nodes for Testing ---

class SimpleCalculatorInputSchema(BaseSchema):
    """Input schema for the SimpleCalculator tool."""
    operation: str = Field(..., description="The operation to perform: add, subtract, multiply, divide")
    number_a: float = Field(..., description="First number")
    number_b: float = Field(..., description="Second number")


class SimpleCalculatorOutputSchema(BaseSchema):
    """Output schema for the SimpleCalculator tool."""
    result: float = Field(..., description="The calculation result")
    operation_performed: str = Field(..., description="Description of the operation performed")


class SimpleCalculatorConfigSchema(BaseSchema):
    """Configuration schema for the SimpleCalculator tool."""
    precision: Optional[int] = Field(2, description="Number of decimal places for results")
    allow_division_by_zero: bool = Field(False, description="Whether to allow division by zero")


class SimpleCalculatorNode(BaseNode[SimpleCalculatorInputSchema, SimpleCalculatorOutputSchema, SimpleCalculatorConfigSchema]):
    """
    Simple Calculator Tool Node for testing basic tool execution.
    Performs basic arithmetic operations with configurable precision.
    """
    node_name: ClassVar[str] = "simple_calculator"
    node_version: ClassVar[str] = "1.0.0"
    node_is_tool: ClassVar[bool] = True
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[type] = SimpleCalculatorInputSchema
    output_schema_cls: ClassVar[type] = SimpleCalculatorOutputSchema
    config_schema_cls: ClassVar[type] = SimpleCalculatorConfigSchema
    
    async def process(
        self, 
        input_data: SimpleCalculatorInputSchema, 
        config: Dict[str, Any], 
        *args: Any, 
        **kwargs: Any
    ) -> SimpleCalculatorOutputSchema:
        """
        Process the calculation based on the input operation.
        
        Args:
            input_data: The input data containing operation and numbers.
            config: Configuration parameters.
            
        Returns:
            SimpleCalculatorOutputSchema: The calculation result.
        """
        # Get precision from node config (set during initialization)
        precision = getattr(self.config, 'precision', 2) if hasattr(self, 'config') and self.config else 2
        allow_division_by_zero = getattr(self.config, 'allow_division_by_zero', False) if hasattr(self, 'config') and self.config else False
        
        operation = input_data.operation.lower()
        a = input_data.number_a
        b = input_data.number_b
        
        if operation == "add":
            result = a + b
            operation_desc = f"{a} + {b}"
        elif operation == "subtract":
            result = a - b
            operation_desc = f"{a} - {b}"
        elif operation == "multiply":
            result = a * b
            operation_desc = f"{a} * {b}"
        elif operation == "divide":
            if b == 0 and not allow_division_by_zero:
                raise ValueError("Division by zero is not allowed")
            result = a / b if b != 0 else float('inf')
            operation_desc = f"{a} / {b}"
        else:
            raise ValueError(f"Unknown operation: {operation}")
        
        # Apply precision
        if precision is not None and result != float('inf'):
            result = round(result, precision)
        
        return SimpleCalculatorOutputSchema(
            result=result,
            operation_performed=f"{operation_desc} = {result}"
        )


class TextProcessorInputSchema(BaseSchema):
    """Input schema for the TextProcessor tool."""
    text: str = Field(..., description="The text to process")
    operation: str = Field(..., description="Operation: uppercase, lowercase, reverse, count_words, count_chars")
    custom_prefix: Optional[str] = Field(None, description="Custom prefix to add to result")


class TextProcessorOutputSchema(BaseSchema):
    """Output schema for the TextProcessor tool."""
    processed_text: str = Field(..., description="The processed text")
    original_text: str = Field(..., description="The original input text")
    operation_used: str = Field(..., description="The operation that was performed")
    statistics: Dict[str, Any] = Field(..., description="Text statistics")


class TextProcessorConfigSchema(BaseSchema):
    """Configuration schema for the TextProcessor tool."""
    include_statistics: bool = Field(True, description="Whether to include text statistics")
    max_text_length: Optional[int] = Field(None, description="Maximum allowed text length")


class TextProcessorNode(BaseNode[TextProcessorInputSchema, TextProcessorOutputSchema, TextProcessorConfigSchema]):
    """
    Text Processor Tool Node for testing field mapping and text operations.
    Processes text with various operations and provides statistics.
    """
    node_name: ClassVar[str] = "text_processor"
    node_version: ClassVar[str] = "1.0.0"
    node_is_tool: ClassVar[bool] = True
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[type] = TextProcessorInputSchema
    output_schema_cls: ClassVar[type] = TextProcessorOutputSchema
    config_schema_cls: ClassVar[type] = TextProcessorConfigSchema
    
    async def process(
        self, 
        input_data: TextProcessorInputSchema, 
        config: Dict[str, Any], 
        *args: Any, 
        **kwargs: Any
    ) -> TextProcessorOutputSchema:
        """
        Process the text based on the specified operation.
        
        Args:
            input_data: The input data containing text and operation.
            config: Configuration parameters.
            
        Returns:
            TextProcessorOutputSchema: The processed text with statistics.
        """
        # Get config values
        include_statistics = getattr(self.config, 'include_statistics', True) if hasattr(self, 'config') and self.config else True
        max_text_length = getattr(self.config, 'max_text_length', None) if hasattr(self, 'config') and self.config else None
        
        text = input_data.text
        operation = input_data.operation.lower()
        custom_prefix = input_data.custom_prefix or ""
        
        # Check text length limit
        if max_text_length and len(text) > max_text_length:
            raise ValueError(f"Text length ({len(text)}) exceeds maximum allowed ({max_text_length})")
        
        # Perform operation
        if operation == "uppercase":
            processed = text.upper()
        elif operation == "lowercase":
            processed = text.lower()
        elif operation == "reverse":
            processed = text[::-1]
        elif operation == "count_words":
            word_count = len(text.split())
            processed = f"Word count: {word_count}"
        elif operation == "count_chars":
            char_count = len(text)
            processed = f"Character count: {char_count}"
        else:
            raise ValueError(f"Unknown text operation: {operation}")
        
        # Add custom prefix if provided
        if custom_prefix:
            processed = f"{custom_prefix}{processed}"
        
        # Generate statistics
        statistics = {}
        if include_statistics:
            statistics = {
                "original_length": len(text),
                "processed_length": len(processed),
                "word_count": len(text.split()),
                "unique_chars": len(set(text)),
                "operation_applied": operation
            }
        
        return TextProcessorOutputSchema(
            processed_text=processed,
            original_text=text,
            operation_used=operation,
            statistics=statistics
        )


class SlowToolInputSchema(BaseSchema):
    """Input schema for the SlowTool."""
    delay_seconds: float = Field(..., description="Number of seconds to delay")
    message: str = Field("Slow operation completed", description="Message to return after delay")


class SlowToolOutputSchema(BaseSchema):
    """Output schema for the SlowTool."""
    message: str = Field(..., description="The message after delay")
    actual_delay: float = Field(..., description="Actual delay experienced")


class SlowToolConfigSchema(BaseSchema):
    """Configuration schema for the SlowTool."""
    max_allowed_delay: Optional[float] = Field(None, description="Maximum allowed delay in seconds")


class SlowToolNode(BaseNode[SlowToolInputSchema, SlowToolOutputSchema, SlowToolConfigSchema]):
    """
    Slow Tool Node for testing timeout scenarios and concurrent execution.
    Simulates slow operations by introducing delays.
    """
    node_name: ClassVar[str] = "slow_tool"
    node_version: ClassVar[str] = "1.0.0"
    node_is_tool: ClassVar[bool] = True
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[type] = SlowToolInputSchema
    output_schema_cls: ClassVar[type] = SlowToolOutputSchema
    config_schema_cls: ClassVar[type] = SlowToolConfigSchema
    
    async def process(
        self, 
        input_data: SlowToolInputSchema, 
        config: Dict[str, Any], 
        *args: Any, 
        **kwargs: Any
    ) -> SlowToolOutputSchema:
        """
        Process with a configurable delay to simulate slow operations.
        
        Args:
            input_data: The input data containing delay and message.
            config: Configuration parameters.
            
        Returns:
            SlowToolOutputSchema: The result after delay.
        """
        max_allowed_delay = getattr(self.config, 'max_allowed_delay', None) if hasattr(self, 'config') and self.config else None
        
        delay = input_data.delay_seconds
        
        # Check if delay exceeds maximum allowed
        if max_allowed_delay and delay > max_allowed_delay:
            raise ValueError(f"Requested delay ({delay}s) exceeds maximum allowed ({max_allowed_delay}s)")
        
        start_time = time.time()
        await asyncio.sleep(delay)
        actual_delay = time.time() - start_time
        
        return SlowToolOutputSchema(
            message=input_data.message,
            actual_delay=actual_delay
        )


class FailingToolInputSchema(BaseSchema):
    """Input schema for the FailingTool."""
    should_fail: bool = Field(False, description="Whether the tool should fail")
    failure_message: str = Field("Tool execution failed", description="Message to use when failing")
    success_message: str = Field("Tool execution succeeded", description="Message to use when succeeding")


class FailingToolOutputSchema(BaseSchema):
    """Output schema for the FailingTool."""
    message: str = Field(..., description="Success message")
    execution_count: int = Field(..., description="Number of times this tool has been called")


class FailingToolConfigSchema(BaseSchema):
    """Configuration schema for the FailingTool."""
    pass


class FailingToolNode(BaseNode[FailingToolInputSchema, FailingToolOutputSchema, FailingToolConfigSchema]):
    """
    Failing Tool Node for testing error handling and failure scenarios.
    Can be configured to succeed or fail based on input parameters.
    """
    node_name: ClassVar[str] = "failing_tool"
    node_version: ClassVar[str] = "1.0.0"
    node_is_tool: ClassVar[bool] = True
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[type] = FailingToolInputSchema
    output_schema_cls: ClassVar[type] = FailingToolOutputSchema
    config_schema_cls: ClassVar[type] = FailingToolConfigSchema
    
    # Class variable to track execution count across instances
    cls_execution_count: ClassVar[int] = 0
    
    async def process(
        self, 
        input_data: FailingToolInputSchema, 
        config: Dict[str, Any], 
        *args: Any, 
        **kwargs: Any
    ) -> FailingToolOutputSchema:
        """
        Process with configurable success/failure behavior.
        
        Args:
            input_data: The input data containing failure configuration.
            config: Configuration parameters.
            
        Returns:
            FailingToolOutputSchema: The result (if successful).
            
        Raises:
            RuntimeError: If configured to fail.
        """
        FailingToolNode.cls_execution_count += 1
        
        if input_data.should_fail:
            raise RuntimeError(input_data.failure_message)
        
        return FailingToolOutputSchema(
            message=input_data.success_message,
            execution_count=FailingToolNode.cls_execution_count
        )


class FieldMappingToolInputSchema(BaseSchema):
    """Input schema for the FieldMappingTool with specific field names."""
    primary_text: str = Field(..., description="Primary text input")
    secondary_text: Optional[str] = Field(None, description="Secondary text input")
    operation_type: str = Field(..., description="Type of operation to perform")
    metadata_info: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class FieldMappingToolOutputSchema(BaseSchema):
    """Output schema for the FieldMappingTool."""
    combined_result: str = Field(..., description="Combined processing result")
    field_mapping_info: Dict[str, Any] = Field(..., description="Information about field mappings used")


class FieldMappingToolConfigSchema(BaseSchema):
    """Configuration schema for the FieldMappingTool."""
    pass


class FieldMappingToolNode(BaseNode[FieldMappingToolInputSchema, FieldMappingToolOutputSchema, FieldMappingToolConfigSchema]):
    """
    Field Mapping Tool Node for testing field mapping functionality.
    Uses specific field names to test mapping between executor input and tool input.
    """
    node_name: ClassVar[str] = "field_mapping_tool"
    node_version: ClassVar[str] = "1.0.0"
    node_is_tool: ClassVar[bool] = True
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[type] = FieldMappingToolInputSchema
    output_schema_cls: ClassVar[type] = FieldMappingToolOutputSchema
    config_schema_cls: ClassVar[type] = FieldMappingToolConfigSchema
    
    async def process(
        self, 
        input_data: FieldMappingToolInputSchema, 
        config: Dict[str, Any], 
        *args: Any, 
        **kwargs: Any
    ) -> FieldMappingToolOutputSchema:
        """
        Process input fields and return information about what was mapped.
        
        Args:
            input_data: The input data with mapped fields.
            config: Configuration parameters.
            
        Returns:
            FieldMappingToolOutputSchema: The processing result with mapping info.
        """
        # Combine the text inputs
        combined_text = input_data.primary_text
        if input_data.secondary_text:
            combined_text += f" | {input_data.secondary_text}"
        
        # Process based on operation type
        if input_data.operation_type == "uppercase":
            combined_result = combined_text.upper()
        elif input_data.operation_type == "lowercase":
            combined_result = combined_text.lower()
        elif input_data.operation_type == "reverse":
            combined_result = combined_text[::-1]
        else:
            combined_result = combined_text
        
        # Create field mapping information
        field_mapping_info = {
            "received_primary_text": input_data.primary_text is not None,
            "received_secondary_text": input_data.secondary_text is not None,
            "received_metadata": input_data.metadata_info is not None,
            "operation_applied": input_data.operation_type,
            "result_length": len(combined_result)
        }
        
        if input_data.metadata_info:
            field_mapping_info["metadata_keys"] = list(input_data.metadata_info.keys())
        
        return FieldMappingToolOutputSchema(
            combined_result=combined_result,
            field_mapping_info=field_mapping_info
        )


# --- Test Helper Functions ---

def setup_test_registry() -> DBRegistry:
    """
    Set up a test registry with all fake tool nodes registered.
    
    Returns:
        DBRegistry: Configured registry with test tool nodes.
    """
    registry = DBRegistry()
    
    # Register core nodes
    registry.register_node(InputNode)
    registry.register_node(OutputNode)
    registry.register_node(ToolExecutorNode)
    
    # Register test tool nodes
    registry.register_node(SimpleCalculatorNode)
    registry.register_node(TextProcessorNode)
    registry.register_node(SlowToolNode)
    registry.register_node(FailingToolNode)
    registry.register_node(FieldMappingToolNode)
    
    return registry


def create_basic_tool_executor_graph(
    executor_config: Optional[ToolExecutorNodeConfigSchema] = None,
    **input_fields
) -> GraphSchema:
    """
    Create a basic 3-node graph with ToolExecutor node.

    Args:
        executor_config: Configuration for the ToolExecutor node.
        **input_fields: Additional input fields to include in the input schema.

    Returns:
        GraphSchema: The configured graph schema.
    """
    # Input node
    input_node = NodeConfig(
        node_id=INPUT_NODE_NAME,
        node_name=INPUT_NODE_NAME,
        node_config={}
    )

    # ToolExecutor node configuration
    tool_executor_config_data = executor_config or ToolExecutorNodeConfigSchema()

    # ToolExecutor node
    tool_executor_node = NodeConfig(
        node_id="tool_executor_node",
        node_name="tool_executor",
        node_config=tool_executor_config_data.model_dump(exclude_none=True)
    )

    # Output node
    output_node = NodeConfig(
        node_id=OUTPUT_NODE_NAME,
        node_name=OUTPUT_NODE_NAME,
        node_config={}
    )

    # Define edges
    edges = [
        EdgeSchema(
            src_node_id=INPUT_NODE_NAME,
            dst_node_id="tool_executor_node",
            mappings=[
                EdgeMapping(src_field="tool_calls", dst_field="tool_calls"),
                EdgeMapping(src_field="execution_timeout", dst_field="execution_timeout"),
                EdgeMapping(src_field="prior_successful_calls", dst_field="prior_successful_calls"),
                EdgeMapping(src_field="prior_failed_calls", dst_field="prior_failed_calls"),
                # Add additional field mappings for input_fields
                *[EdgeMapping(src_field=field, dst_field=field) for field in input_fields.keys()]
            ]
        ),
        EdgeSchema(
            src_node_id="tool_executor_node",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="tool_outputs", dst_field="tool_outputs"),
                EdgeMapping(src_field="tool_call_metadata", dst_field="tool_call_metadata"),
                EdgeMapping(src_field="total_execution_time", dst_field="total_execution_time"),
                EdgeMapping(src_field="successful_calls", dst_field="successful_calls"),
                EdgeMapping(src_field="failed_calls", dst_field="failed_calls"),
            ]
        )
    ]

    return GraphSchema(
        nodes={
            INPUT_NODE_NAME: input_node,
            "tool_executor_node": tool_executor_node,
            OUTPUT_NODE_NAME: output_node
        },
        edges=edges,
        input_node_id=INPUT_NODE_NAME,
        output_node_id=OUTPUT_NODE_NAME
    )


# Simple Mock User for testing
class MockUser(BaseModel):
    """Mock User model for testing."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    is_superuser: bool = False


async def run_tool_executor_test(
    runtime_config: Dict[str, Any],
    tool_calls: List[ToolCall],
    executor_config: Optional[ToolExecutorNodeConfigSchema] = None,
    execution_timeout: Optional[float] = None,
    prior_successful_calls: int = 0,
    prior_failed_calls: int = 0,
    **additional_input_fields
) -> Dict[str, Any]:
    """
    Run a test with the specified ToolExecutor configuration.

    Args:
        runtime_config: The runtime configuration dictionary.
        tool_calls: List of tool calls to execute.
        executor_config: Configuration for the ToolExecutor node.
        execution_timeout: Optional timeout override for tool execution.
        prior_successful_calls: Number of successful calls from previous executions.
        prior_failed_calls: Number of failed calls from previous executions.
        **additional_input_fields: Additional input fields to pass to the executor.

    Returns:
        Dict[str, Any]: The test results from the graph execution.
    """
    registry = setup_test_registry()

    # Prepare input data
    input_data = {
        "tool_calls": tool_calls,
        "prior_successful_calls": prior_successful_calls,
        "prior_failed_calls": prior_failed_calls
    }
    
    if execution_timeout is not None:
        input_data["execution_timeout"] = execution_timeout
    
    # Add additional input fields
    input_data.update(additional_input_fields)

    # Create graph schema
    graph_schema = create_basic_tool_executor_graph(
        executor_config=executor_config,
        **additional_input_fields
    )

    builder = GraphBuilder(registry)
    graph_entities = builder.build_graph_entities(graph_schema)

    # Use provided runtime config with unique thread_id for isolation
    graph_runtime_config = graph_entities["runtime_config"]
    graph_runtime_config.update(runtime_config)
    test_runtime_config = graph_runtime_config
    test_runtime_config["thread_id"] = f"tool_executor_test_{uuid.uuid4()}"
    test_runtime_config["use_checkpointing"] = True

    adapter = LangGraphRuntimeAdapter()
    graph = adapter.build_graph(graph_entities)

    result = await adapter.aexecute_graph(
        graph=graph,
        input_data=input_data,
        config=test_runtime_config,
        output_node_id=graph_entities["output_node_id"]
    )

    return result


# --- Test Classes ---

class TestToolExecutorNode(unittest.IsolatedAsyncioTestCase):
    """Test comprehensive ToolExecutor node functionality."""

    # Test setup attributes
    test_org_id: uuid.UUID
    test_user_id: uuid.UUID
    user_regular: MockUser
    run_job_regular: WorkflowRunJobCreate
    external_context: ExternalContextManager
    runtime_config_regular: Dict[str, Any]

    async def asyncSetUp(self):
        """Set up test-specific users, orgs, and contexts before each test."""
        self.test_org_id = uuid.uuid4()
        self.test_user_id = uuid.uuid4()

        self.user_regular = MockUser(id=self.test_user_id, is_superuser=False)

        # Base Run Job
        base_run_job_info = {
            "run_id": uuid.uuid4(),
            "workflow_id": uuid.uuid4(),
            "owner_org_id": self.test_org_id,
            "triggered_by_user_id": self.user_regular.id
        }
        self.run_job_regular = WorkflowRunJobCreate(**base_run_job_info)

        # Initialize context for each test
        try:
            self.external_context = await get_external_context_manager_with_clients()
            registry = setup_test_registry()
            self.external_context.db_registry = registry
        except Exception as e:
            raise unittest.SkipTest(f"Failed to initialize external context: {e}")

        # Runtime Configs
        self.runtime_config_regular = {
            APPLICATION_CONTEXT_KEY: {
                "user": self.user_regular,
                "workflow_run_job": self.run_job_regular
            },
            EXTERNAL_CONTEXT_MANAGER_KEY: self.external_context
        }

    async def test_basic_single_tool_execution(self):
        """Test basic execution of a single calculator tool."""
        tool_calls = [
            ToolCall(
                tool_name="simple_calculator",
                tool_input={
                    "operation": "add",
                    "number_a": 10.5,
                    "number_b": 5.2
                },
                tool_id="calc_1"
            )
        ]

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls
        )

        # Verify basic structure
        self.assertIn("tool_outputs", result)
        self.assertIn("tool_call_metadata", result)
        self.assertIn("successful_calls", result)
        self.assertIn("failed_calls", result)

        # Verify successful execution
        self.assertEqual(result["successful_calls"], 1)
        self.assertEqual(result["failed_calls"], 0)
        self.assertEqual(len(result["tool_outputs"]), 1)

        # Verify tool output
        tool_output = result["tool_outputs"][0]
        self.assertEqual(tool_output["tool_call_id"], "calc_1")
        self.assertEqual(tool_output["name"], "simple_calculator")
        self.assertEqual(tool_output["status"], "success")

        # Parse and verify the calculation result
        output_content = json.loads(tool_output["content"])
        self.assertAlmostEqual(output_content["result"], 15.7, places=1)
        self.assertIn("10.5 + 5.2", output_content["operation_performed"])

        # Verify metadata
        metadata = result["tool_call_metadata"][0]
        self.assertEqual(metadata["tool_call_id"], "calc_1")
        self.assertEqual(metadata["tool_name"], "simple_calculator")
        self.assertTrue(metadata["success"])
        self.assertGreater(metadata["execution_time"], 0)

    async def test_multiple_tools_sequential_execution(self):
        """Test sequential execution of multiple different tools."""
        tool_calls = [
            ToolCall(
                tool_name="simple_calculator",
                tool_input={
                    "operation": "multiply",
                    "number_a": 6,
                    "number_b": 7
                },
                tool_id="calc_1"
            ),
            ToolCall(
                tool_name="text_processor",
                tool_input={
                    "text": "Hello World",
                    "operation": "uppercase"
                },
                tool_id="text_1"
            ),
            ToolCall(
                tool_name="simple_calculator",
                tool_input={
                    "operation": "divide",
                    "number_a": 100,
                    "number_b": 4
                },
                tool_id="calc_2"
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            max_concurrent_executions=1  # Force sequential execution
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config
        )

        # Verify all tools executed successfully
        self.assertEqual(result["successful_calls"], 3)
        self.assertEqual(result["failed_calls"], 0)
        self.assertEqual(len(result["tool_outputs"]), 3)

        # Verify each tool output
        outputs = {output["tool_call_id"]: output for output in result["tool_outputs"]}
        
        # Calculator 1: 6 * 7 = 42
        calc1_content = json.loads(outputs["calc_1"]["content"])
        self.assertEqual(calc1_content["result"], 42)
        
        # Text processor: "Hello World" -> "HELLO WORLD"
        text1_content = json.loads(outputs["text_1"]["content"])
        self.assertEqual(text1_content["processed_text"], "HELLO WORLD")
        
        # Calculator 2: 100 / 4 = 25
        calc2_content = json.loads(outputs["calc_2"]["content"])
        self.assertEqual(calc2_content["result"], 25)

    async def test_concurrent_tool_execution(self):
        """Test concurrent execution of multiple tools."""
        tool_calls = [
            ToolCall(
                tool_name="slow_tool",
                tool_input={
                    "delay_seconds": 0.1,
                    "message": "First slow operation"
                },
                tool_id="slow_1"
            ),
            ToolCall(
                tool_name="slow_tool",
                tool_input={
                    "delay_seconds": 0.1,
                    "message": "Second slow operation"
                },
                tool_id="slow_2"
            ),
            ToolCall(
                tool_name="slow_tool",
                tool_input={
                    "delay_seconds": 0.1,
                    "message": "Third slow operation"
                },
                tool_id="slow_3"
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            max_concurrent_executions=3  # Allow concurrent execution
        )

        start_time = time.time()
        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config
        )
        total_time = time.time() - start_time

        # Verify all tools executed successfully
        self.assertEqual(result["successful_calls"], 3)
        self.assertEqual(result["failed_calls"], 0)

        # Concurrent execution should be faster than sequential (3 * 0.1 = 0.3s)
        # Allow some overhead but it should be significantly less than 0.3s
        self.assertLess(total_time, 0.25, "Concurrent execution should be faster than sequential")

        # Verify all outputs are present
        self.assertEqual(len(result["tool_outputs"]), 3)
        for output in result["tool_outputs"]:
            self.assertEqual(output["status"], "success")

    async def test_tool_call_limit_enforcement(self):
        """Test that tool call limits are properly enforced."""
        tool_calls = [
            ToolCall(
                tool_name="simple_calculator",
                tool_input={"operation": "add", "number_a": 1, "number_b": 1},
                tool_id="calc_1"
            ),
            ToolCall(
                tool_name="simple_calculator",
                tool_input={"operation": "add", "number_a": 2, "number_b": 2},
                tool_id="calc_2"
            ),
            ToolCall(
                tool_name="simple_calculator",
                tool_input={"operation": "add", "number_a": 3, "number_b": 3},
                tool_id="calc_3"
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            tool_call_limit=2,  # Only allow 2 tool calls
            consider_failed_calls_in_limit=True
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config
        )

        # Should execute 2 tools successfully, fail the third due to limit
        self.assertEqual(result["successful_calls"], 2)
        self.assertEqual(result["failed_calls"], 1)
        self.assertEqual(len(result["tool_outputs"]), 3)

        # First two should succeed
        self.assertEqual(result["tool_outputs"][0]["status"], "success")
        self.assertEqual(result["tool_outputs"][1]["status"], "success")
        
        # Third should fail due to limit
        self.assertEqual(result["tool_outputs"][2]["status"], "error")
        self.assertIn("limit reached", result["tool_outputs"][2]["error_message"])

    async def test_tool_call_limit_with_prior_calls(self):
        """Test tool call limits with prior successful/failed calls."""
        tool_calls = [
            ToolCall(
                tool_name="simple_calculator",
                tool_input={"operation": "add", "number_a": 1, "number_b": 1},
                tool_id="calc_1"
            ),
            ToolCall(
                tool_name="simple_calculator",
                tool_input={"operation": "add", "number_a": 2, "number_b": 2},
                tool_id="calc_2"
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            tool_call_limit=3,
            consider_failed_calls_in_limit=True
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config,
            prior_successful_calls=1,  # 1 prior successful call
            prior_failed_calls=1       # 1 prior failed call (total: 2)
        )

        # Should execute 1 tool successfully (limit reached at 3), fail the second
        self.assertEqual(result["successful_calls"], 1)
        self.assertEqual(result["failed_calls"], 1)
        
        # First should succeed (total calls: 2 + 1 = 3, at limit)
        self.assertEqual(result["tool_outputs"][0]["status"], "success")
        
        # Second should fail (would exceed limit)
        self.assertEqual(result["tool_outputs"][1]["status"], "error")
        self.assertIn("limit reached", result["tool_outputs"][1]["error_message"])

    async def test_tool_timeout_handling(self):
        """Test timeout handling for slow tools."""
        tool_calls = [
            ToolCall(
                tool_name="slow_tool",
                tool_input={
                    "delay_seconds": 2.0,  # 2 second delay
                    "message": "This should timeout"
                },
                tool_id="slow_timeout"
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            default_timeout=0.5  # 0.5 second timeout
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config
        )

        # Should fail due to timeout
        self.assertEqual(result["successful_calls"], 0)
        self.assertEqual(result["failed_calls"], 1)
        
        tool_output = result["tool_outputs"][0]
        self.assertEqual(tool_output["status"], "error")
        self.assertIn("timed out", tool_output["error_message"])
        
        # Verify metadata shows timeout
        metadata = result["tool_call_metadata"][0]
        self.assertFalse(metadata["success"])
        self.assertEqual(metadata["error_type"], "TimeoutError")

    async def test_timeout_override_from_input(self):
        """Test timeout override from input parameter."""
        tool_calls = [
            ToolCall(
                tool_name="slow_tool",
                tool_input={
                    "delay_seconds": 0.3,
                    "message": "Should complete"
                },
                tool_id="slow_success"
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            default_timeout=0.1  # Very short default timeout
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config,
            execution_timeout=1.0  # Override with longer timeout
        )

        # Should succeed due to timeout override
        self.assertEqual(result["successful_calls"], 1)
        self.assertEqual(result["failed_calls"], 0)
        
        tool_output = result["tool_outputs"][0]
        self.assertEqual(tool_output["status"], "success")

    async def test_error_handling_and_continue_on_error(self):
        """Test error handling and continue_on_error behavior."""
        tool_calls = [
            ToolCall(
                tool_name="failing_tool",
                tool_input={
                    "should_fail": True,
                    "failure_message": "Intentional failure"
                },
                tool_id="fail_1"
            ),
            ToolCall(
                tool_name="simple_calculator",
                tool_input={
                    "operation": "add",
                    "number_a": 5,
                    "number_b": 3
                },
                tool_id="calc_1"
            ),
            ToolCall(
                tool_name="failing_tool",
                tool_input={
                    "should_fail": False,
                    "success_message": "This should succeed"
                },
                tool_id="success_1"
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            continue_on_error=True,
            include_error_details=True,
            max_concurrent_executions=1  # Sequential to test order
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config
        )

        # Should have 1 failure and 2 successes
        self.assertEqual(result["successful_calls"], 2)
        self.assertEqual(result["failed_calls"], 1)
        
        # Verify first tool failed
        self.assertEqual(result["tool_outputs"][0]["status"], "error")
        self.assertIn("Intentional failure", result["tool_outputs"][0]["error_message"])
        
        # Verify second tool succeeded despite first failure
        self.assertEqual(result["tool_outputs"][1]["status"], "success")
        
        # Verify third tool succeeded
        self.assertEqual(result["tool_outputs"][2]["status"], "success")

    async def test_stop_on_error_behavior(self):
        """Test that execution stops on error when continue_on_error=False."""
        tool_calls = [
            ToolCall(
                tool_name="simple_calculator",
                tool_input={
                    "operation": "add",
                    "number_a": 1,
                    "number_b": 1
                },
                tool_id="calc_success"
            ),
            ToolCall(
                tool_name="failing_tool",
                tool_input={
                    "should_fail": True,
                    "failure_message": "Stop here"
                },
                tool_id="fail_stop"
            ),
            ToolCall(
                tool_name="simple_calculator",
                tool_input={
                    "operation": "add",
                    "number_a": 2,
                    "number_b": 2
                },
                tool_id="calc_skip"
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            continue_on_error=False,  # Stop on error
            max_concurrent_executions=1  # Sequential execution
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config
        )

        # Should execute first 2 tools, skip the third after failure
        self.assertEqual(len(result["tool_outputs"]), 2)
        self.assertEqual(result["successful_calls"], 1)
        self.assertEqual(result["failed_calls"], 1)
        
        # First should succeed
        self.assertEqual(result["tool_outputs"][0]["status"], "success")
        
        # Second should fail
        self.assertEqual(result["tool_outputs"][1]["status"], "error")

    async def test_tool_with_configuration(self):
        """Test tool execution with specific tool configuration."""
        tool_calls = [
            ToolCall(
                tool_name="simple_calculator",
                tool_input={
                    "operation": "divide",
                    "number_a": 10,
                    "number_b": 3
                },
                tool_id="calc_precision"
            ),
            ToolCall(
                tool_name="text_processor",
                tool_input={
                    "text": "Short",
                    "operation": "uppercase"
                },
                tool_id="text_limited"
            )
        ]

        # Configure tools with specific settings
        tool_configs = [
            ToolNodeConfig(
                tool_name="simple_calculator",
                tool_config={
                    "precision": 4,  # 4 decimal places
                    "allow_division_by_zero": False
                }
            ),
            ToolNodeConfig(
                tool_name="text_processor",
                tool_config={
                    "max_text_length": 10,  # Max 10 characters
                    "include_statistics": True
                }
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            tool_configs=tool_configs
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config
        )

        # Both should succeed
        self.assertEqual(result["successful_calls"], 2)
        self.assertEqual(result["failed_calls"], 0)

        # Verify calculator uses 4 decimal precision
        calc_output = json.loads(result["tool_outputs"][0]["content"])
        self.assertAlmostEqual(calc_output["result"], 3.3333, places=4)

        # Verify text processor includes statistics
        text_output = json.loads(result["tool_outputs"][1]["content"])
        self.assertIn("statistics", text_output)
        self.assertTrue(text_output["statistics"])

    async def test_tool_configuration_with_length_limit_violation(self):
        """Test tool with configuration that causes validation error."""
        tool_calls = [
            ToolCall(
                tool_name="text_processor",
                tool_input={
                    "text": "This text is way too long for the configured limit",
                    "operation": "uppercase"
                },
                tool_id="text_too_long"
            )
        ]

        tool_configs = [
            ToolNodeConfig(
                tool_name="text_processor",
                tool_config={
                    "max_text_length": 10  # Much shorter than input text
                }
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            tool_configs=tool_configs
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config
        )

        # Should fail due to length limit
        self.assertEqual(result["successful_calls"], 0)
        self.assertEqual(result["failed_calls"], 1)
        
        tool_output = result["tool_outputs"][0]
        self.assertEqual(tool_output["status"], "error")
        self.assertIn("exceeds maximum allowed", tool_output["error_message"])

    async def test_field_mapping_auto_mapping(self):
        """Test automatic field mapping between executor input and tool input."""
        tool_calls = [
            ToolCall(
                tool_name="field_mapping_tool",
                tool_input={
                    "operation_type": "uppercase"
                    # primary_text will come from executor input via auto-mapping
                },
                tool_id="mapping_test"
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            map_executor_input_fields_to_tool_input=True  # Enable auto-mapping
        )

        # Provide additional fields that should be auto-mapped
        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config,
            primary_text="hello world",  # This should auto-map to tool input
            secondary_text="additional text",
            metadata_info={"source": "test", "version": 1}
        )

        # Should succeed
        self.assertEqual(result["successful_calls"], 1)
        self.assertEqual(result["failed_calls"], 0)

        # Verify field mapping worked
        tool_output = json.loads(result["tool_outputs"][0]["content"])
        self.assertEqual(tool_output["combined_result"], "HELLO WORLD | ADDITIONAL TEXT")
        
        mapping_info = tool_output["field_mapping_info"]
        self.assertTrue(mapping_info["received_primary_text"])
        self.assertTrue(mapping_info["received_secondary_text"])
        self.assertTrue(mapping_info["received_metadata"])

    async def test_field_mapping_explicit_mappings(self):
        """Test explicit field mappings between executor input and tool input."""
        tool_calls = [
            ToolCall(
                tool_name="field_mapping_tool",
                tool_input={
                    "operation_type": "lowercase"
                },
                tool_id="explicit_mapping_test"
            )
        ]

        # Configure explicit field mappings
        tool_configs = [
            ToolNodeConfig(
                tool_name="field_mapping_tool",
                mappings={
                    "user_text": "primary_text",       # executor field -> tool field
                    "extra_text": "secondary_text",     # executor field -> tool field
                    "user_metadata": "metadata_info"    # executor field -> tool field
                }
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            tool_configs=tool_configs,
            map_executor_input_fields_to_tool_input=True
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config,
            user_text="MAPPED TEXT",  # Will map to primary_text
            extra_text="MORE TEXT",   # Will map to secondary_text
            user_metadata={"mapped": True}  # Will map to metadata_info
        )

        # Should succeed
        self.assertEqual(result["successful_calls"], 1)
        self.assertEqual(result["failed_calls"], 0)

        # Verify explicit mapping worked
        tool_output = json.loads(result["tool_outputs"][0]["content"])
        self.assertEqual(tool_output["combined_result"], "mapped text | more text")
        
        mapping_info = tool_output["field_mapping_info"]
        self.assertTrue(mapping_info["received_primary_text"])
        self.assertTrue(mapping_info["received_secondary_text"])
        self.assertTrue(mapping_info["received_metadata"])
        self.assertIn("mapped", mapping_info["metadata_keys"])

    async def test_field_mapping_tool_precedence(self):
        """Test that tool call input takes precedence over executor input in mapping."""
        tool_calls = [
            ToolCall(
                tool_name="field_mapping_tool",
                tool_input={
                    "primary_text": "TOOL CALL TEXT",  # This should take precedence
                    "operation_type": "uppercase"
                },
                tool_id="precedence_test"
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            map_executor_input_fields_to_tool_input=True
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config,
            primary_text="EXECUTOR TEXT",  # This should be overridden by tool call
            secondary_text="EXECUTOR SECONDARY"  # This should be mapped
        )

        # Should succeed
        self.assertEqual(result["successful_calls"], 1)
        self.assertEqual(result["failed_calls"], 0)

        # Verify tool call input took precedence
        tool_output = json.loads(result["tool_outputs"][0]["content"])
        self.assertEqual(tool_output["combined_result"], "TOOL CALL TEXT | EXECUTOR SECONDARY")

    async def test_tool_restriction_mode(self):
        """Test restricted mode where only configured tools can be executed."""
        tool_calls = [
            ToolCall(
                tool_name="simple_calculator",  # This is configured, should work
                tool_input={
                    "operation": "add",
                    "number_a": 1,
                    "number_b": 2
                },
                tool_id="calc_allowed"
            ),
            ToolCall(
                tool_name="text_processor",  # This is NOT configured, should fail
                tool_input={
                    "text": "test",
                    "operation": "uppercase"
                },
                tool_id="text_restricted"
            )
        ]

        tool_configs = [
            ToolNodeConfig(
                tool_name="simple_calculator"  # Only calculator is allowed
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            tool_configs=tool_configs,
            restrict_tools_to_configured_tools_only=True  # Enable restriction
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config
        )

        # Should have 1 success and 1 failure
        self.assertEqual(result["successful_calls"], 1)
        self.assertEqual(result["failed_calls"], 1)

        # Calculator should succeed
        self.assertEqual(result["tool_outputs"][0]["status"], "success")
        
        # Text processor should fail due to restriction
        self.assertEqual(result["tool_outputs"][1]["status"], "error")
        self.assertIn("not in the configured tools list", result["tool_outputs"][1]["error_message"])

    async def test_nonexistent_tool_error(self):
        """Test error handling when trying to execute a non-existent tool."""
        tool_calls = [
            ToolCall(
                tool_name="nonexistent_tool",
                tool_input={"param": "value"},
                tool_id="bad_tool"
            )
        ]

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls
        )

        # Should fail
        self.assertEqual(result["successful_calls"], 0)
        self.assertEqual(result["failed_calls"], 1)
        
        tool_output = result["tool_outputs"][0]
        self.assertEqual(tool_output["status"], "error")
        self.assertIn("not found in registry", tool_output["error_message"])

    async def test_invalid_tool_input_error(self):
        """Test error handling for invalid tool input."""
        tool_calls = [
            ToolCall(
                tool_name="simple_calculator",
                tool_input={
                    "operation": "add",
                    "number_a": "not_a_number",  # Invalid type
                    "number_b": 5
                },
                tool_id="bad_input"
            )
        ]

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls
        )

        # Should fail due to invalid input
        self.assertEqual(result["successful_calls"], 0)
        self.assertEqual(result["failed_calls"], 1)
        
        tool_output = result["tool_outputs"][0]
        self.assertEqual(tool_output["status"], "error")
        self.assertIn("Invalid input", tool_output["error_message"])

    async def test_empty_tool_calls_list(self):
        """Test handling of empty tool calls list."""
        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=[]  # Empty list
        )

        # Should complete successfully with no operations
        self.assertEqual(result["successful_calls"], 0)
        self.assertEqual(result["failed_calls"], 0)
        self.assertEqual(len(result["tool_outputs"]), 0)
        self.assertEqual(len(result["tool_call_metadata"]), 0)
        self.assertEqual(result["total_execution_time"], 0.0)

    async def test_execution_time_tracking(self):
        """Test that execution times are properly tracked."""
        tool_calls = [
            ToolCall(
                tool_name="slow_tool",
                tool_input={
                    "delay_seconds": 0.1,
                    "message": "Timing test"
                },
                tool_id="timing_test"
            )
        ]

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls
        )

        # Should succeed
        self.assertEqual(result["successful_calls"], 1)
        self.assertEqual(result["failed_calls"], 0)

        # Verify timing information
        metadata = result["tool_call_metadata"][0]
        self.assertGreaterEqual(metadata["execution_time"], 0.1)  # At least the delay time
        self.assertGreater(result["total_execution_time"], 0)

        # Individual time should be less than or equal to total time (for single tool)
        self.assertLessEqual(metadata["execution_time"], result["total_execution_time"])

    async def test_field_mapping_disabled(self):
        """Test that field mapping can be disabled globally and per-tool."""
        tool_calls = [
            ToolCall(
                tool_name="field_mapping_tool",
                tool_input={
                    "primary_text": "ONLY THIS TEXT",
                    "operation_type": "uppercase"
                },
                tool_id="no_mapping_test"
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            map_executor_input_fields_to_tool_input=False  # Disable mapping
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config,
            secondary_text="THIS SHOULD NOT BE MAPPED",  # Should be ignored
            metadata_info={"ignored": True}  # Should be ignored
        )

        # Should succeed
        self.assertEqual(result["successful_calls"], 1)
        self.assertEqual(result["failed_calls"], 0)

        # Verify only tool call input was used (no mapping)
        tool_output = json.loads(result["tool_outputs"][0]["content"])
        self.assertEqual(tool_output["combined_result"], "ONLY THIS TEXT")
        
        mapping_info = tool_output["field_mapping_info"]
        self.assertTrue(mapping_info["received_primary_text"])
        self.assertFalse(mapping_info["received_secondary_text"])  # Not mapped
        self.assertFalse(mapping_info["received_metadata"])  # Not mapped

    async def test_consider_failed_calls_in_limit_false(self):
        """Test tool call limit counting only successful calls when consider_failed_calls_in_limit=False."""
        tool_calls = [
            ToolCall(
                tool_name="failing_tool",
                tool_input={"should_fail": True, "failure_message": "First failure"},
                tool_id="fail_1"
            ),
            ToolCall(
                tool_name="simple_calculator",
                tool_input={"operation": "add", "number_a": 1, "number_b": 1},
                tool_id="calc_1"
            ),
            ToolCall(
                tool_name="simple_calculator",
                tool_input={"operation": "add", "number_a": 2, "number_b": 2},
                tool_id="calc_2"
            ),
            ToolCall(
                tool_name="simple_calculator",
                tool_input={"operation": "add", "number_a": 3, "number_b": 3},
                tool_id="calc_3"
            )
        ]

        executor_config = ToolExecutorNodeConfigSchema(
            tool_call_limit=2,  # Only count 2 successful calls
            consider_failed_calls_in_limit=False,  # Don't count failed calls
            max_concurrent_executions=1  # Sequential to ensure order
        )

        result = await run_tool_executor_test(
            runtime_config=self.runtime_config_regular,
            tool_calls=tool_calls,
            executor_config=executor_config
        )

        # Should have 1 failure and 2 successes (3rd calc should fail due to limit)
        self.assertEqual(result["successful_calls"], 2)
        self.assertEqual(result["failed_calls"], 2)  # 1 intentional failure + 1 limit failure

        # First call fails intentionally
        self.assertEqual(result["tool_outputs"][0]["status"], "error")
        self.assertIn("First failure", result["tool_outputs"][0]["error_message"])

        # Second and third calls succeed (successful count: 1, 2)
        self.assertEqual(result["tool_outputs"][1]["status"], "success")
        self.assertEqual(result["tool_outputs"][2]["status"], "success")

        # Fourth call fails due to limit (successful count would be 3)
        self.assertEqual(result["tool_outputs"][3]["status"], "error")
        self.assertIn("limit reached", result["tool_outputs"][3]["error_message"])


if __name__ == "__main__":
    unittest.main()
