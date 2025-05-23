"""
Integration tests for basic LLM node workflows.

This module tests the LLM node in a simple 3-node graph (input -> LLM -> output)
with different model configurations and output types.
"""
import json
from typing import Dict, Any, List, ClassVar, Awaitable, Optional
import unittest
import asyncio
import uuid
from pydantic import BaseModel, Field
from langchain_core.messages import AnyMessage

from kiwi_app.workflow_app.constants import SchemaType
from kiwi_app.workflow_app.schemas import SchemaTemplateCreate
from db.session import get_async_db_as_manager
from workflow_service.registry.nodes.core.base import BaseSchema
from workflow_service.config.constants import (
    INPUT_NODE_NAME,
    OUTPUT_NODE_NAME,
)
from workflow_service.graph.graph import (
    EdgeMapping, 
    EdgeSchema, 
    GraphSchema, 
    NodeConfig,
    ConstructDynamicSchema
)
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchemaFieldConfig
from workflow_service.registry.nodes.llm.llm_node import (
    LLMNode,
    LLMNodeInputSchema,
    LLMNodeOutputSchema,
    LLMNodeConfigSchema,
    LLMStructuredOutputSchema,
    LLMModelConfig,
    ModelSpec,
    ToolCallingConfig,
    ToolConfig,
)
from workflow_service.registry.nodes.llm.config import (
    LLMModelProvider,
    AnthropicModels,
    OpenAIModels,
    GeminiModels,
    FireworksModels,
    AWSBedrockModels,
    PerplexityModels,
)
from workflow_service.config.settings import settings
from workflow_service.graph.builder import GraphBuilder
from workflow_service.graph.runtime.adapter import LangGraphRuntimeAdapter
from workflow_service.registry.registry import DBRegistry
from workflow_service.registry.nodes.core.dynamic_nodes import InputNode, OutputNode

# Context and Service imports
from workflow_service.services.external_context_manager import (
    ExternalContextManager,
    get_external_context_manager_with_clients
)
from kiwi_app.workflow_app.service_customer_data import CustomerDataService # Assuming path
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY,
)

# Schema/Model imports
from kiwi_app.workflow_app.schemas import WorkflowRunJobCreate # Assuming path
# from kiwi_app.auth.models import User # Import real User if available and simple

# x = ConstructDynamicSchema(
#         schema_name="OpenAIDynamicSchema",
#         fields={
#             "answer": DynamicSchemaFieldConfig(type="str", required=True, description="The answer."),
#             "confidence": DynamicSchemaFieldConfig(type="float", required=False, description="Confidence score (0.0-1.0).")
#         }
# )
# print(json.dumps(x.build_schema().model_json_schema(), indent=2))
# raise Exception("Stop here")


# Simple Mock User if real one is complex to import/instantiate
class MockUser(BaseModel):
    """Mock User model for testing."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    is_superuser: bool = False
    # Add other fields if CustomerDataService or other parts check them


class TestOutputSchema(BaseModel):
    """Schema for test output."""
    content: str = Field(description="Generated content")
    metadata: Dict[str, Any] = Field(description="Response metadata")


def create_basic_llm_graph(
    model_provider: LLMModelProvider,
    model_name: str,
    output_schema_config: Optional[LLMStructuredOutputSchema] = None, # Pass the whole config object
    reasoning_config: Optional[Dict[str, Any]] = None,
    max_tokens: int = 100,
    default_system_prompt: Optional[str] = None,
    web_search_options: Optional[Dict[str, Any]] = None,
    tool_calling_config: Optional[ToolCallingConfig] = None,
    tools: Optional[List[ToolConfig]] = None
) -> GraphSchema:
    """
    Create a basic 3-node graph with LLM node.

    Args:
        model_provider: The LLM provider to use.
        model_name: The model name to use.
        output_schema_config: Configuration for structured output.
        reasoning_config: Optional reasoning configuration.
        max_tokens: Maximum tokens for the response.
        default_system_prompt: Optional default system prompt.
        web_search_options: Optional web search config.
        tool_calling_config: Optional tool calling config.
        tools: Optional list of tools.

    Returns:
        GraphSchema: The configured graph schema.
    """
    # Input node
    input_node = NodeConfig(
        node_id=INPUT_NODE_NAME,
        node_name=INPUT_NODE_NAME,
        node_config={}
    )

    # LLM node configuration
    llm_config = LLMNodeConfigSchema(
        default_system_prompt=default_system_prompt,
        llm_config=LLMModelConfig(
            model_spec=ModelSpec(
                provider=model_provider,
                model=model_name
            ),
            temperature=0.0,  # For deterministic outputs
            max_tokens=max_tokens + (reasoning_config.get("reasoning_tokens_budget", 0) if reasoning_config else 0),
            **(reasoning_config if reasoning_config else {})
        ),
        thinking_tokens_in_prompt="all",
        output_schema=output_schema_config or LLMStructuredOutputSchema(), # Use provided or default
        web_search_options=web_search_options,
        tool_calling_config=tool_calling_config or ToolCallingConfig(),
        tools=tools
    )

    # LLM node
    llm_node = NodeConfig(
        node_id="llm_node",
        node_name="llm",
        node_config=llm_config.model_dump(exclude_none=True) # Exclude Nones for cleaner config
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
            dst_node_id="llm_node",
            mappings=[
                EdgeMapping(src_field="user_prompt", dst_field="user_prompt"),
                EdgeMapping(src_field="messages_history", dst_field="messages_history"),
                EdgeMapping(src_field="system_prompt", dst_field="system_prompt"),
                # EdgeMapping(src_field="tool_outputs", dst_field="tool_outputs"), # Added for tool testing
            ]
        ),
        EdgeSchema(
            src_node_id="llm_node",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="structured_output", dst_field="structured_output"),
                EdgeMapping(src_field="metadata", dst_field="metadata"),
                EdgeMapping(src_field="current_messages", dst_field="current_messages"),
                EdgeMapping(src_field="content", dst_field="content"),
                EdgeMapping(src_field="web_search_result", dst_field="web_search_result"),
                # EdgeMapping(src_field="tool_calls", dst_field="tool_calls"), # Added for tool testing
            ]
        )
    ]

    return GraphSchema(
        nodes={
            INPUT_NODE_NAME: input_node,
            "llm_node": llm_node,
            OUTPUT_NODE_NAME: output_node
        },
        edges=edges,
        input_node_id=INPUT_NODE_NAME,
        output_node_id=OUTPUT_NODE_NAME
    )


def setup_registry():
    """Setup the registry with necessary nodes and schemas."""
    registry = DBRegistry()
    registry.register_node(LLMNode)
    registry.register_node(InputNode)
    registry.register_node(OutputNode)

    # No need to register TTestSchema here as we are providing schemas directly

    return registry


async def arun_llm_test(
    runtime_config: Dict[str, Any], # Pass runtime config
    model_provider: LLMModelProvider,
    model_name: str,
    max_tokens: int = 100,
    output_schema_config: Optional[LLMStructuredOutputSchema] = None,
    reasoning_config: Optional[Dict[str, Any]] = None,
    user_prompt: str = "What is 2+2? Answer in one word.",
    message_history: Optional[List[Dict]] = None,
    input_system_prompt: Optional[str] = None,
    **kwargs # Pass other graph creation args like web_search_options etc.
) -> Dict[str, Any]:
    """
    Run a test with the specified LLM configuration asynchronously.

    Args:
        runtime_config: The runtime configuration dictionary.
        model_provider: The LLM provider to use.
        model_name: The model name to use.
        max_tokens: Max tokens for generation.
        output_schema_config: Structured output configuration.
        reasoning_config: Optional reasoning configuration.
        user_prompt: The prompt to send to the LLM.
        message_history: Optional message history.
        input_system_prompt: Optional system prompt to override default.
        **kwargs: Additional arguments passed to create_basic_llm_graph.

    Returns:
        Dict[str, Any]: The test results from the graph execution.
    """
    registry = setup_registry()

    # Prepare input data based on provided args
    input_data = {"user_prompt": user_prompt}
    if message_history:
        input_data["messages_history"] = message_history
    if input_system_prompt:
        input_data["system_prompt"] = input_system_prompt

    # Create graph schema using the passed arguments
    graph_schema = create_basic_llm_graph(
        model_provider=model_provider,
        model_name=model_name,
        output_schema_config=output_schema_config,
        max_tokens=max_tokens,
        reasoning_config=reasoning_config,
        default_system_prompt=kwargs.pop("default_system_prompt", None), # Handle explicitly
        **kwargs # Pass remaining kwargs
    )

    builder = GraphBuilder(registry)
    graph_entities = builder.build_graph_entities(graph_schema)

    # Use provided runtime config, but ensure a unique thread_id for isolation
    graph_runtime_config = graph_entities["runtime_config"]
    graph_runtime_config.update(runtime_config)
    test_runtime_config = graph_runtime_config
    test_runtime_config["thread_id"] = f"llm_test_{model_provider}_{model_name}_{uuid.uuid4()}"
    test_runtime_config["use_checkpointing"] = True # Usually good for testing state

    adapter = LangGraphRuntimeAdapter()
    graph = adapter.build_graph(graph_entities)

    result = await adapter.aexecute_graph(
        graph=graph,
        input_data=input_data,
        config=test_runtime_config, # Use the test-specific config
        output_node_id=graph_entities["output_node_id"]
    )

    return result


class TestBasicLLMWorkflow(unittest.IsolatedAsyncioTestCase):
    """Test basic LLM node functionality with different configurations asynchronously."""

    # Test setup attributes
    test_org_id: uuid.UUID
    test_user_id: uuid.UUID
    user_regular: MockUser
    run_job_regular: WorkflowRunJobCreate
    external_context: ExternalContextManager
    runtime_config_regular: Dict[str, Any]
    customer_data_service: Optional[CustomerDataService]

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

        self.customer_data_service = self.external_context.customer_data_service
        if not self.customer_data_service:
             self.logger.warning("CustomerDataService could not be initialized in external context.")
             # Decide if this is a skip condition or just a warning
             # raise unittest.SkipTest("CustomerDataService could not be initialized.")


    # --- Gemini Tests ---

    async def test_gemini_pro_exp_text_reasoning(self):
        """Test Gemini 2.5 Pro Exp with text output and reasoning (thinking model)."""
        if not hasattr(GeminiModels, "GEMINI_2_5_PRO"):
             self.skipTest("GeminiModels.GEMINI_2_5_PRO not defined in enum.")

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.GEMINI,
            model_name=GeminiModels.GEMINI_2_5_PRO.value,
            output_schema_config=None, # Text output
            # Gemini reasoning config might differ, test without specific reasoning flags first
            # reasoning_config={ # Example, adjust if Gemini uses different keys
            #     "reasoning_effort_class": "low"
            # }
            user_prompt="Explain the concept of quantum entanglement simply."
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], str)
        self.assertGreater(len(result["content"]), 0)

    async def test_gemini_pro_exp_structured_reasoning(self):
        """Test Gemini 2.5 Pro Exp with structured output and reasoning (thinking model)."""
        if not hasattr(GeminiModels, "GEMINI_2_5_PRO"):
             self.skipTest("GeminiModels.GEMINI_2_5_PRO not defined in enum.")

        dynamic_schema_spec = ConstructDynamicSchema(
             schema_name="GeminiReasoningStructSchema",
             fields={
                 "explanation": DynamicSchemaFieldConfig(type="str", required=True, description="The explanation."),
                 "key_points": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="Key takeaways.")
             }
        )
        schema_config = LLMStructuredOutputSchema(dynamic_schema_spec=dynamic_schema_spec)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.GEMINI,
            model_name=GeminiModels.GEMINI_2_5_PRO.value,
            output_schema_config=schema_config, # Structured output
            # reasoning_config={ # Example, adjust if Gemini uses different keys
            #     "reasoning_effort_class": "low"
            # },
            user_prompt="Explain the theory of relativity simply and list key points."
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("explanation", result["structured_output"])
        self.assertIn("key_points", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["key_points"], list)

    async def test_gemini_flash_text(self):
        """Test Gemini 2.5 Flash with text output (non-thinking model)."""
        if not hasattr(GeminiModels, "GEMINI_2_0_FLASH"):
             self.skipTest("GeminiModels.GEMINI_2_0_FLASH not defined in enum.")

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.GEMINI,
            model_name=GeminiModels.GEMINI_2_5_FLASH.value,
            output_schema_config=None # Text output
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], str)
        self.assertGreater(len(result["content"]), 0)

    async def test_gemini_flash_structured(self):
        """Test Gemini 2.5 Flash with structured output (non-thinking model)."""
        if not hasattr(GeminiModels, "GEMINI_2_0_FLASH"):
             self.skipTest("GeminiModels.GEMINI_2_0_FLASH not defined in enum.")

        dynamic_schema_spec = ConstructDynamicSchema(
             schema_name="GeminiFlashStructSchema",
             fields={
                 "answer": DynamicSchemaFieldConfig(type="str", required=True, description="The answer."),
                 "certainty": DynamicSchemaFieldConfig(type="str", required=False, description="Certainty level (e.g., High, Medium, Low).")
             }
        )
        schema_config = LLMStructuredOutputSchema(dynamic_schema_spec=dynamic_schema_spec)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.GEMINI,
            model_name=GeminiModels.GEMINI_2_5_FLASH.value,
            output_schema_config=schema_config # Structured output
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("answer", result["structured_output"])
        # certainty is optional

    async def test_gemini_structured_output_json_definition(self):
        """Test Gemini 2.5 Flash with structured output via schema_definition."""
        if not hasattr(GeminiModels, "GEMINI_2_0_FLASH"):
             self.skipTest("GeminiModels.GEMINI_2_0_FLASH not defined in enum.")

        json_schema_def = {
            "title": "TestJsonSchemaGemini",
            "description": "Raw JSON schema definition for Gemini.",
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
                "population": {"type": "integer", "description": "Approximate population"}
            },
            "required": ["city", "population"]
        }
        schema_config = LLMStructuredOutputSchema(schema_definition=json_schema_def)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.GEMINI,
            model_name=GeminiModels.GEMINI_2_5_FLASH.value,
            output_schema_config=schema_config,
            user_prompt="Provide info for London: city name and population integer."
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("city", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["city"], str)
        self.assertIn("population", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["population"], (int, float))

    # --- Fireworks Tests ---

    async def test_fireworks_text_with_reasoning(self):
        """Test Fireworks DeepSeek R1 Fast with text output and reasoning."""
        if not hasattr(FireworksModels, "DEEPSEEK_R1_FAST"):
             self.skipTest("FireworksModels.DEEPSEEK_R1_FAST not defined in enum.")

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.FIREWORKS,
            model_name=FireworksModels.DEEPSEEK_R1_FAST.value,
            output_schema_config=None, # Text output
            reasoning_config={
                "reasoning_effort_class": "low"
            },
            max_tokens=1000,
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        
        self.assertIn("metadata", result)
        # Fireworks reasoning models often return a list with thinking/text pairs
        self.assertIsInstance(result["content"], list)
        self.assertGreater(len(result["content"]), 0)
        # Check for thinking and text parts
        self.assertTrue(any(isinstance(item, dict) and item.get('type') == 'thinking' for item in result["content"]))
        self.assertTrue(any(isinstance(item, dict) and item.get('type') == 'text' for item in result["content"]))


    async def test_fireworks_basic_text_with_reasoning_number(self):
        """Test Fireworks DeepSeek R1 Basic with text output and reasoning number."""
        # Assuming DEEPSEEK_R1_FAST supports reasoning_effort_number, adjust if needed
        if not hasattr(FireworksModels, "DEEPSEEK_R1_FAST"):
             self.skipTest("FireworksModels.DEEPSEEK_R1_FAST not defined in enum.")

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.FIREWORKS,
            model_name=FireworksModels.DEEPSEEK_R1_FAST.value, # Using FAST, adjust if BASIC exists
            output_schema_config=None, # Text output
            reasoning_config={
                "reasoning_effort_number": 50
            }
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], list)
        self.assertGreater(len(result["content"]), 0)
        self.assertTrue(any(isinstance(item, dict) and item.get('type') == 'thinking' for item in result["content"]))
        self.assertTrue(any(isinstance(item, dict) and item.get('type') == 'text' for item in result["content"]))

    async def test_fireworks_basic_structured_with_reasoning_number(self):
        """Test Fireworks DeepSeek R1 Basic with structured output and reasoning number."""
        if not hasattr(FireworksModels, "DEEPSEEK_R1_FAST"):
            self.skipTest("FireworksModels.DEEPSEEK_R1_FAST not defined in enum.")

        dynamic_schema_spec = ConstructDynamicSchema(
             schema_name="FireworksReasoningStructSchema",
             fields={
                 "answer": DynamicSchemaFieldConfig(type="str", required=True, description="The computed answer."),
                 "process": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="Steps taken.")
             }
        )
        schema_config = LLMStructuredOutputSchema(dynamic_schema_spec=dynamic_schema_spec)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.FIREWORKS,
            model_name=FireworksModels.DEEPSEEK_R1_FAST.value, # Using FAST, adjust if BASIC exists
            output_schema_config=schema_config, # Structured output
            reasoning_config={
                # Fireworks might require effort class for structured output, testing with class
                "reasoning_effort_class": "low",
            },
            max_tokens=3000,
            user_prompt="What is 3 factorial? Show the main steps."
        )
        # import ipdb; ipdb.set_trace()
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result) # Fireworks might put structured in 'content' or 'structured_output'
        self.assertIn("metadata", result)
        # Depending on Fireworks structured output implementation with reasoning:
        # if "structured_output" in result and result["structured_output"]:
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("answer", result["structured_output"])
        self.assertIn("process", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["process"], list)
        # elif "content" in result and isinstance(result["content"], list):
        #      # Check if the structured output is embedded in the content list (less ideal)
        #      self.assertTrue(any(isinstance(item, dict) and 'answer' in item for item in result["content"]), "Structured output not found in content list")

    async def test_fireworks_structured_output_json_definition(self):
        """Test Fireworks DeepSeek R1 Fast with structured output via schema_definition."""
        # Note: Fireworks structured output often relies on tool calling under the hood.
        if not hasattr(FireworksModels, "DEEPSEEK_R1_FAST"):
             self.skipTest("FireworksModels.DEEPSEEK_R1_FAST not defined in enum.")

        json_schema_def = {
            "title": "TestJsonSchemaFireworks",
            "description": "Raw JSON schema for Fireworks.",
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product identifier"},
                "in_stock": {"type": "boolean", "description": "Stock availability"}
            },
            "required": ["product_id", "in_stock"]
        }
        schema_config = LLMStructuredOutputSchema(schema_definition=json_schema_def)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.FIREWORKS,
            model_name=FireworksModels.DEEPSEEK_R1_FAST.value,
            output_schema_config=schema_config,
            reasoning_config={ # May require reasoning for structured output
                "reasoning_effort_class": "low",
            },
            max_tokens=3000,
            user_prompt="Give product ID 'XYZ789' and stock status true."
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("product_id", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["product_id"], str)
        self.assertIn("in_stock", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["in_stock"], bool)


    # --- AWS Bedrock Tests ---

    async def test_aws_bedrock_text_with_reasoning(self):
        """Test AWS Bedrock DeepSeek R1 with text output and reasoning."""
        # Bedrock models might require specific setup (credentials) not handled here.
        if not hasattr(AWSBedrockModels, "DEEPSEEK_R1"):
            self.skipTest("AWSBedrockModels.DEEPSEEK_R1 not defined in enum.")
        if not settings.AWS_BEDROCK_ACCESS_KEY_ID or not settings.AWS_BEDROCK_SECRET_ACCESS_KEY:
             self.skipTest("AWS Bedrock credentials not configured in settings.")

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.AWS_BEDROCK,
            model_name=AWSBedrockModels.DEEPSEEK_R1.value,
            output_schema_config=None, # Text output expected
            # Assuming Bedrock DeepSeek uses reasoning by default or specific config
            # reasoning_config={ # Adjust based on actual Bedrock config needs
            #     "reasoning_effort_class": "low"
            # },
            max_tokens=1000,
            user_prompt="Describe the process of photosynthesis."
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
         # Bedrock DeepSeek might not support structured output
        self.assertIn("metadata", result)
        # Bedrock response format might vary (string or list with reasoning)
        self.assertTrue(isinstance(result["content"], (str, list)))
        self.assertGreater(len(result["content"]), 0)

    # --- Perplexity Tests ---

    async def test_perplexity_text_output_reasoning_model(self):
        """Test Perplexity Sonar Reasoning with text output and web search."""
        if not hasattr(PerplexityModels, "SONAR_REASONING"):
            self.skipTest("PerplexityModels.SONAR_REASONING not defined in enum.")

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.PERPLEXITY,
            model_name=PerplexityModels.SONAR_REASONING.value,
            output_schema_config=None, # Text output
            web_search_options={
                "search_recency_filter": "year",
                "search_context_size": "low",
                # "search_domain_filter": ["example.com"] # Optional domain filter
            },
            # Perplexity reasoning is often implicit in the model, may not need config
            user_prompt="What is the capital of France? Answer briefly.",
            max_tokens=500,
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        
        self.assertIn("metadata", result)
        # Perplexity reasoning models might return list with thinking/text or just text
        self.assertTrue(isinstance(result["content"], (list, str)))
        self.assertGreater(len(result["content"]), 0)
        self.assertIn("web_search_result", result) # Expect search results
        self.assertIsNotNone(result["web_search_result"])
        self.assertIsInstance(result["web_search_result"].get("citations"), list)

    async def test_perplexity_structured_output_reasoning_model(self):
        """Test Perplexity Sonar Reasoning Pro with structured output and web search."""
        if not hasattr(PerplexityModels, "SONAR_REASONING_PRO"):
             self.skipTest("PerplexityModels.SONAR_REASONING_PRO not defined in enum.")

        # Define the structured output schema based on the user's example fields
        dynamic_schema_spec = ConstructDynamicSchema(
             schema_name="PerplexitySearchStructSchema",
             fields={
                 "summary": DynamicSchemaFieldConfig(type="str", required=True, description="Content of the response"),
                 "key_findings": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="List of key findings from the search"), # Changed to list
                 "citations": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="List of citations from the search results") # Changed to list
             }
        )
        schema_config = LLMStructuredOutputSchema(dynamic_schema_spec=dynamic_schema_spec)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.PERPLEXITY,
            model_name=PerplexityModels.SONAR_REASONING_PRO.value,
            output_schema_config=schema_config, # Structured output
            web_search_options={
                "search_recency_filter": "month",
                "search_context_size": "medium",
                "search_domain_filter": ["arxiv.org", "openai.com"]
            },
            user_prompt="What are the latest developments in AI safety research? Provide a summary, key findings, and citations.",
            max_tokens=1000
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("summary", result["structured_output"])
        self.assertIn("key_findings", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["key_findings"], list)
        self.assertIn("citations", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["citations"], list)
        self.assertIn("web_search_result", result) # Expect search results metadata as well
        self.assertIsNotNone(result["web_search_result"])

    async def test_perplexity_text_output_non_reasoning_model(self):
        """Test Perplexity Sonar Pro with text output and web search."""
        if not hasattr(PerplexityModels, "SONAR_PRO"):
            self.skipTest("PerplexityModels.SONAR_PRO not defined in enum.")

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.PERPLEXITY,
            model_name=PerplexityModels.SONAR_PRO.value,
            output_schema_config=None, # Text output
            web_search_options={
                "search_recency_filter": "month",
                "search_context_size": "low"
            },
            user_prompt="What are the recent breakthroughs in fusion energy? Answer briefly top highlights.",
            max_tokens=500
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], str)
        self.assertGreater(len(result["content"]), 0)
        self.assertIn("web_search_result", result)
        self.assertIsNotNone(result["web_search_result"])

    async def test_perplexity_structured_output_non_reasoning_model(self):
        """Test Perplexity Sonar with structured output and web search."""
        if not hasattr(PerplexityModels, "SONAR"):
            self.skipTest("PerplexityModels.SONAR not defined in enum.")

        dynamic_schema_spec = ConstructDynamicSchema(
             schema_name="PerplexityNonReasoningStructSchema",
             fields={
                 "summary": DynamicSchemaFieldConfig(type="str", required=True, description="Content of the response"),
                 "trends": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="List of emerging trends"), # Changed to list
                 "sources": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="List of sources") # Changed to list
             }
        )
        schema_config = LLMStructuredOutputSchema(dynamic_schema_spec=dynamic_schema_spec)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.PERPLEXITY,
            model_name=PerplexityModels.SONAR.value,
            output_schema_config=schema_config, # Structured output
            web_search_options={
                "search_recency_filter": "year",
                "search_context_size": "low"
            },
            user_prompt="What are the emerging trends in renewable energy? Provide summary, trends list, and sources list.",
            max_tokens=500
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("summary", result["structured_output"])
        self.assertIn("trends", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["trends"], list)
        self.assertIn("sources", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["sources"], list)
        self.assertIn("web_search_result", result)
        self.assertIsNotNone(result["web_search_result"])

    # --- OpenAI Web Search Tests ---

    async def test_openai_text_output_with_web_search(self):
        """Test OpenAI GPT-4o Search Preview with text output and web search."""
        if not hasattr(OpenAIModels, "GPT_4O_SEARCH_PREVIEW"):
             self.skipTest("OpenAIModels.GPT_4O_SEARCH_PREVIEW not defined in enum.")

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.GPT_4O_SEARCH_PREVIEW.value,
            output_schema_config=None, # Text output
            web_search_options={
                "search_context_size": "medium",
                "user_location": { # OpenAI specific location format
                    "type": "approximate",
                    "approximate": {
                        "country": "US",
                        "city": "San Francisco",
                        "region": "California",
                    },
                }
            },
            user_prompt="What are the latest climate change policies? Answer briefly top highlights.",
            max_tokens=500
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], str)
        self.assertGreater(len(result["content"]), 0)
        self.assertIn("web_search_result", result)
        self.assertIsNotNone(result["web_search_result"])
        # OpenAI search results might have citations in metadata
        self.assertIsInstance(result["web_search_result"].get("citations", []), list)

    async def test_openai_structured_output_with_web_search(self):
        """Test OpenAI GPT-4o Mini Search Preview with structured output and web search."""
        if not hasattr(OpenAIModels, "GPT_4O_MINI_SEARCH_PREVIEW"):
             self.skipTest("OpenAIModels.GPT_4O_MINI_SEARCH_PREVIEW not defined in enum.")

        dynamic_schema_spec = ConstructDynamicSchema(
             schema_name="OpenAISearchStructSchema",
             fields={
                 "summary": DynamicSchemaFieldConfig(type="str", required=True, description="Content of the response"),
                 "key_statistics": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="Important stats"), # Changed to list
                 "regional_differences": DynamicSchemaFieldConfig(type="str", required=True, description="How adoption varies"),
                 "citations": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="Sources") # Changed to list
             }
        )
        schema_config = LLMStructuredOutputSchema(dynamic_schema_spec=dynamic_schema_spec)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.GPT_4O_MINI_SEARCH_PREVIEW.value,
            output_schema_config=schema_config, # Structured output
            web_search_options={
                "search_context_size": "medium",
                "user_location": {
                    "type": "approximate",
                    "approximate": {
                        "country": "US",
                        "city": "Austin",
                        "region": "Texas",
                    },
                }
            },
            user_prompt="What is the current state of electric vehicle adoption? Provide summary, key stats list, regional differences, and citations list.",
            max_tokens=1000
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("summary", result["structured_output"])
        self.assertIn("key_statistics", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["key_statistics"], list)
        self.assertIn("regional_differences", result["structured_output"])
        self.assertIn("citations", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["citations"], list)
        self.assertIn("web_search_result", result)
        self.assertIsNotNone(result["web_search_result"])

    async def test_perplexity_structured_output_json_definition(self):
        """Test Perplexity Sonar with structured output via schema_definition."""
        if not hasattr(PerplexityModels, "SONAR"):
            self.skipTest("PerplexityModels.SONAR not defined in enum.")

        json_schema_def = {
            "title": "TestJsonSchemaPerplexity",
            "description": "Raw JSON schema for Perplexity search results.",
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Main topic of the search"},
                "result_count": {"type": "integer", "description": "Number of key results found"}
            },
            "required": ["topic", "result_count"]
        }
        schema_config = LLMStructuredOutputSchema(schema_definition=json_schema_def)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.PERPLEXITY,
            model_name=PerplexityModels.SONAR.value, # Using non-reasoning model for simplicity
            output_schema_config=schema_config,
            web_search_options={ # Perplexity models often require web search
                "search_context_size": "low"
            },
            user_prompt="Search for 'latest Mars rover findings'. Return topic and count of main findings."
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("topic", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["topic"], str)
        self.assertIn("result_count", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["result_count"], int)


if __name__ == "__main__":
    unittest.main()
