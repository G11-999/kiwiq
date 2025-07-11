"""
Integration tests for basic LLM node workflows.

This module tests the LLM node in a simple 3-node graph (input -> LLM -> output)
with different model configurations and output types.
"""
import json
from typing import Dict, Any, List, ClassVar, Awaitable, Optional, Union
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
from services.workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY,
    OBJECT_PATH_REFERENCE_DELIMITER,
    DB_SESSION_KEY,
)
from db.session import get_async_session

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
                EdgeMapping(src_field="image_input_url_or_base64", dst_field="image_input_url_or_base64"),
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
                EdgeMapping(src_field="tool_calls", dst_field="tool_calls"), # Added for tool testing
                EdgeMapping(src_field="text_content", dst_field="text_content"), # Added for image testing
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
    image_input_url_or_base64: Optional[Union[str, List[str]]] = None,
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
        image_input_url_or_base64: Optional image URL or base64 encoded image(s) to send to the model.
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
    if image_input_url_or_base64:
        input_data["image_input_url_or_base64"] = image_input_url_or_base64

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

    for node in graph_entities["node_instances"].values():
        node.billing_mode = False

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
        
        self.db_session = await get_async_session()

        # Runtime Configs
        self.runtime_config_regular = {
            APPLICATION_CONTEXT_KEY: {
                "user": self.user_regular,
                "workflow_run_job": self.run_job_regular
            },
            EXTERNAL_CONTEXT_MANAGER_KEY: self.external_context,
            DB_SESSION_KEY: self.db_session
        }
        

        self.customer_data_service = self.external_context.customer_data_service
        if not self.customer_data_service:
             self.logger.warning("CustomerDataService could not be initialized in external context.")
             # Decide if this is a skip condition or just a warning
             # raise unittest.SkipTest("CustomerDataService could not be initialized.")
    
    async def asyncTearDown(self):
        """Tear down test-specific resources after each test."""
        if self.db_session:
            await self.db_session.close()
        try:
            if self.external_context:
                await self.external_context.close()
        except Exception as e:
            print(f"Error in asyncTearDown: {e}")


    async def test_anthropic_text_output(self):
        """Test Anthropic Claude 3.7 Sonnet with default text output."""
        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular, # Pass config
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
            # output_schema_config is None by default -> text output
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertTrue(("structured_output" not in result) or (result["structured_output"] is None)) # Should not be present for text
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], str)
        self.assertGreater(len(result["content"]), 0)
        self.assertIn("iteration_count", result["metadata"])
        self.assertGreaterEqual(result["metadata"]["iteration_count"], 1) # At least one AI message

    async def test_anthropic_structured_output_dynamic_spec(self):
        """Test Anthropic Claude 3.5 Sonnet with structured output via dynamic_schema_spec."""
        dynamic_schema_spec = ConstructDynamicSchema(
            schema_name="TestDynamicSchema",
            schema_description="Schema for simple content and metadata list",
            fields={
                "content": DynamicSchemaFieldConfig(type="str", default="placeholder", required=False, description="The main textual answer."),
                "metadata": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="List of reasoning steps or metadata."),
            }
        )
        schema_config = LLMStructuredOutputSchema(dynamic_schema_spec=dynamic_schema_spec)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular, # Pass config
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_5_SONNET.value,
            output_schema_config=schema_config,
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("content", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["content"], str)
        self.assertIn("metadata", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["metadata"], list)

    async def test_anthropic_structured_output_json_definition(self):
        """Test Anthropic Claude 3.5 Sonnet with structured output via schema_definition."""
        json_schema_def = {
            "title": "TestJsonSchema",
            "description": "Raw JSON schema definition for content and an integer value.",
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The primary textual response."
                },
                "value_integer": {
                    "type": "integer",
                    "description": "An integer representation of the answer."
                }
            },
            "required": ["content", "value_integer"]
        }
        schema_config = LLMStructuredOutputSchema(schema_definition=json_schema_def)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular, # Pass config
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_5_SONNET.value,
            output_schema_config=schema_config,
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("content", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["content"], str)
        self.assertIn("value_integer", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["value_integer"], int)


    async def test_anthropic_structured_output_reasoning(self):
        """Test Anthropic Claude 3.7 Sonnet with structured output and reasoning."""
        dynamic_schema_spec = ConstructDynamicSchema(
            schema_name="ReasoningSchema",
            fields={
                "answer": DynamicSchemaFieldConfig(type="str", required=True, description="Final answer."),
                "steps": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="Reasoning steps."),
            }
        )
        schema_config = LLMStructuredOutputSchema(dynamic_schema_spec=dynamic_schema_spec)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
            output_schema_config=schema_config,
            reasoning_config={
                "reasoning_tokens_budget": 1024
            },
            input_system_prompt="Think step by step before answering.", # Encourage reasoning
            user_prompt="What is the capital of France? Explain your reasoning."
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("answer", result["structured_output"])
        self.assertIn("steps", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["steps"], list)
        # Check if reasoning tokens were used (if provider exposes this in metadata)
        # self.assertGreater(result["metadata"].get("token_usage", {}).get("reasoning_tokens", 0), 0)

    # # # --- OpenAI Tests (similar structure) ---

    async def test_openai_text_output_non_reasoning_model(self):
        """Test OpenAI GPT-4o-mini with text output."""
        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.GPT_4o.value, # Using GPT-4.5 enum value
            # No output_schema_config -> text output
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertTrue(("structured_output" not in result) or (result["structured_output"] is None))
        self.assertIsInstance(result["content"], str)
        self.assertGreater(len(result["content"]), 0)

    async def test_openai_structured_output_dynamic_spec_non_reasoning_model(self):
        """Test OpenAI GPT-4o with structured output via dynamic_schema_spec."""
        dynamic_schema_spec = ConstructDynamicSchema(
             schema_name="OpenAIDynamicSchema",
             fields={
                 "answer": DynamicSchemaFieldConfig(type="str", required=True, description="The answer."),
                 "confidence": DynamicSchemaFieldConfig(type="float", required=False, description="Confidence score (0.0-1.0).")
             }
        )
        schema_config = LLMStructuredOutputSchema(
            # dynamic_schema_spec=dynamic_schema_spec
            schema_definition={'properties': {'answer': {'description': 'The answer.', 'title': 'Answer', 'type': 'string'}, 'confidence': {'anyOf': [{'type': 'number'}, {'type': 'null'}], 'default': None, 'description': 'Confidence score (0.0-1.0).', 'title': 'Confidence'}}, 'required': ['answer'], 'title': 'OpenAIDynamicSchema', 'type': 'object'}
        )

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.GPT_4o.value,
            output_schema_config=schema_config,
            user_prompt="What is 2+2? Provide the answer and optionally a confidence score."
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("answer", result["structured_output"])
        # Confidence is optional, so check its type if present
        if "confidence" in result["structured_output"]:
            self.assertIsInstance(result["structured_output"]["confidence"], float)
        # import ipdb; ipdb.set_trace()

    async def test_llm_structured_output_from_db_schema(self):
        """Test LLM node structured output using a schema fetched from the DB registry."""
        # 1. Define Schema Details
        schema_name = f"test_db_schema_{uuid.uuid4()}"
        schema_version = "1.0"
        schema_definition = {
            "title": schema_name,
            "description": "Schema fetched from DB for testing.",
            "type": "object",
            "properties": {
                "person_name": {"type": "string", "description": "Name of the person"},
                "person_age": {"type": "integer", "description": "Age of the person"}
            },
            "required": ["person_name", "person_age"]
        }
        schema_template_in = SchemaTemplateCreate(
            name=schema_name,
            version=schema_version,
            schema_type=SchemaType.JSON_SCHEMA,
            schema_definition=schema_definition,
            description="Test schema template",
            is_public=True, # Keep test schemas private to the org
            is_system_entity=True,
        )

        created_schema_template = None
        try:
            # 2. Create Schema Template in DB
            # Ensure the DAO and DB session are available via external_context
            async with get_async_db_as_manager() as db:
                try:
                    # First, try to delete any existing schema template with the same name/version
                    # This ensures we don't have conflicts if the test was interrupted previously
                    existing_template = await self.external_context.daos.schema_template.get_by_name_version(
                        db=db,
                        name=schema_name,
                        version=schema_version
                    )
                    
                    if existing_template:
                        # Delete the existing template to avoid conflicts
                        await self.external_context.daos.schema_template.remove(
                            db=db,
                            id=existing_template.id
                        )
                except Exception as e:
                    pass
                created_schema_template = await self.external_context.daos.schema_template.create(
                    db=db,
                    obj_in=schema_template_in,
                    owner_org_id=None
                    # owner_org_id=self.test_org_id
                )
            async with get_async_db_as_manager() as db:
                loaded_schema_template = await self.external_context.daos.schema_template.get(db, id=created_schema_template.id)
                schema_template = await self.runtime_config_regular[EXTERNAL_CONTEXT_MANAGER_KEY].customer_data_service._get_schema_from_template(  # : Optional[SchemaTemplate]
                    db=db,
                    template_name=schema_name,
                    template_version=schema_version,
                    org_id=self.test_org_id,
                    user=self.runtime_config_regular[APPLICATION_CONTEXT_KEY]["user"]
                )
                # import ipdb; ipdb.set_trace()
            self.assertIsNotNone(created_schema_template)
            self.assertEqual(created_schema_template.name, schema_name)

            # 3. Configure LLM Node to use the DB Schema
            # Use the schema_template_name and optionally version
            schema_config = LLMStructuredOutputSchema(
                schema_template_name=schema_name,
                schema_template_version=schema_version
                # schema_definition=None, # Ensure only one method is used
                # dynamic_schema_spec=None
            )

            # 4. Run the graph
            result = await arun_llm_test(
                runtime_config=self.runtime_config_regular,
                model_provider=LLMModelProvider.OPENAI, # Use a model known to support structured output
                model_name=OpenAIModels.GPT_4o.value,
                output_schema_config=schema_config,
                user_prompt="Extract the name (Alice) and age (30) from the text."
            )

            # 5. Assertions
            self.assertIsInstance(result, dict)
            self.assertIn("structured_output", result)
            self.assertIsInstance(result["structured_output"], dict)
            # Validate against the specific schema defined
            self.assertIn("person_name", result["structured_output"])
            self.assertIsInstance(result["structured_output"]["person_name"], str)
            self.assertIn("person_age", result["structured_output"])
            self.assertIsInstance(result["structured_output"]["person_age"], int)
            # Optional: Check values if the model is consistent enough
            # self.assertEqual(result["structured_output"]["person_name"], "Alice")
            # self.assertEqual(result["structured_output"]["person_age"], 30)

        finally:
            # 6. Teardown: Delete the schema template
            if created_schema_template:
                async with get_async_db_as_manager() as db:
                    await self.external_context.daos.schema_template.remove_obj(
                        db=db,
                        obj=created_schema_template
                    )
                    # Verify deletion (optional)
                    # deleted = await self.external_context.daos.schema_template.get(db, id=created_schema_template.id)
                    # self.assertIsNone(deleted)
    # --- OpenAI Reasoning Tests ---

    async def test_openai_text_output_reasoning_model(self):
        """Test OpenAI O3 Mini with text output and reasoning (thinking model)."""
        # Note: O3 Mini is not a standard OpenAI model name in the enum.
        # Assuming the user meant a reasoning-capable model like O1 or similar.
        # Using O1 for the test. Adjust if O3_MINI exists in your enum.
        # If OpenAIModels.O3_MINI does not exist, this test will fail at enum lookup.
        # Check if O3_MINI is defined before running
        if not hasattr(OpenAIModels, "O3_MINI"):
             self.skipTest("OpenAIModels.O3_MINI not defined in enum.")

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.O3_MINI.value, # Adjust if needed
            output_schema_config=None, # Explicitly text output
            reasoning_config={
                "reasoning_effort_class": "low"
            }
        )
        print(result)
        print(result["content"])
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], str) # Reasoning model might return list, check response format
        self.assertGreater(len(result["content"]), 0)

    async def test_openai_structured_output_reasoning_model(self):
        """Test OpenAI O1 with structured output and reasoning (thinking model)."""
        # Check if O1 is defined before running
        if not hasattr(OpenAIModels, "O1"):
             self.skipTest("OpenAIModels.O1 not defined in enum.")

        # Define a simple dynamic schema for the structured output
        dynamic_schema_spec = ConstructDynamicSchema(
             schema_name="OpenAIReasoningStructSchema",
             fields={
                 "result": DynamicSchemaFieldConfig(type="str", required=True, description="The final result."),
                 "explanation": DynamicSchemaFieldConfig(type="str", required=False, description="Explanation or reasoning steps.")
             }
        )
        schema_config = LLMStructuredOutputSchema(dynamic_schema_spec=dynamic_schema_spec)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.O1.value, # Use O1 model
            output_schema_config=schema_config, # Structured output
            reasoning_config={
                "reasoning_effort_class": "low"
            },
            max_tokens=1000,
            user_prompt="Calculate 5 * 12 and explain the steps briefly."
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("result", result["structured_output"])
        # Explanation is optional

    async def test_openai_structured_output_json_definition(self):
        """Test OpenAI GPT-4o with structured output via schema_definition."""
        json_schema_def = {
            "title": "TestJsonSchemaOpenAI",
            "description": "Raw JSON schema definition for OpenAI.",
            "type": "object",
            "properties": {
                "item_name": {"type": "string", "description": "Name of the item"},
                "item_count": {"type": "integer", "description": "Quantity of the item"}
            },
            "required": ["item_name", "item_count"]
        }
        schema_config = LLMStructuredOutputSchema(schema_definition=json_schema_def)

        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.GPT_4o.value,
            output_schema_config=schema_config,
            user_prompt="Generate details for 5 apples."
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("item_name", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["item_name"], str)
        self.assertIn("item_count", result["structured_output"])
        self.assertIsInstance(result["structured_output"]["item_count"], int)
    
    # --- OpenAI Web Search Tests ---

    # async def test_openai_text_output_with_web_search(self):
    #     """Test OpenAI GPT-4o Search Preview with text output and web search."""
    #     if not hasattr(OpenAIModels, "GPT_4O_SEARCH_PREVIEW"):
    #          self.skipTest("OpenAIModels.GPT_4O_SEARCH_PREVIEW not defined in enum.")

    #     result = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.OPENAI,
    #         model_name=OpenAIModels.GPT_4O_SEARCH_PREVIEW.value,
    #         output_schema_config=None, # Text output
    #         web_search_options={
    #             "search_context_size": "medium",
    #             "user_location": { # OpenAI specific location format
    #                 "type": "approximate",
    #                 "approximate": {
    #                     "country": "US",
    #                     "city": "San Francisco",
    #                     "region": "California",
    #                 },
    #             }
    #         },
    #         user_prompt="What are the latest climate change policies? Answer briefly top highlights.",
    #         max_tokens=500
    #     )
    #     self.assertIsInstance(result, dict)
    #     self.assertIn("content", result)
        
    #     self.assertIn("metadata", result)
    #     self.assertIsInstance(result["content"], str)
    #     self.assertGreater(len(result["content"]), 0)
    #     self.assertIn("web_search_result", result)
    #     self.assertIsNotNone(result["web_search_result"])
    #     # OpenAI search results might have citations in metadata
    #     self.assertIsInstance(result["web_search_result"].get("citations", []), list)

    # async def test_openai_structured_output_with_web_search(self):
    #     """Test OpenAI GPT-4o Mini Search Preview with structured output and web search."""
    #     if not hasattr(OpenAIModels, "GPT_4O_MINI_SEARCH_PREVIEW"):
    #          self.skipTest("OpenAIModels.GPT_4O_MINI_SEARCH_PREVIEW not defined in enum.")

    #     dynamic_schema_spec = ConstructDynamicSchema(
    #          schema_name="OpenAISearchStructSchema",
    #          fields={
    #              "summary": DynamicSchemaFieldConfig(type="str", required=True, description="Content of the response"),
    #              "key_statistics": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="Important stats"), # Changed to list
    #              "regional_differences": DynamicSchemaFieldConfig(type="str", required=True, description="How adoption varies"),
    #              "citations": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="Sources") # Changed to list
    #          }
    #     )
    #     schema_config = LLMStructuredOutputSchema(dynamic_schema_spec=dynamic_schema_spec)

    #     result = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.OPENAI,
    #         model_name=OpenAIModels.GPT_4O_MINI_SEARCH_PREVIEW.value,
    #         output_schema_config=schema_config, # Structured output
    #         web_search_options={
    #             "search_context_size": "medium",
    #             "user_location": {
    #                 "type": "approximate",
    #                 "approximate": {
    #                     "country": "US",
    #                     "city": "Austin",
    #                     "region": "Texas",
    #                 },
    #             }
    #         },
    #         user_prompt="What is the current state of electric vehicle adoption? Provide summary, key stats list, regional differences, and citations list.",
    #         max_tokens=1000
    #     )
    #     self.assertIsInstance(result, dict)
    #     self.assertIn("structured_output", result)
    #     self.assertIn("metadata", result)
    #     self.assertIsInstance(result["structured_output"], dict)
    #     self.assertIn("summary", result["structured_output"])
    #     self.assertIn("key_statistics", result["structured_output"])
    #     self.assertIsInstance(result["structured_output"]["key_statistics"], list)
    #     self.assertIn("regional_differences", result["structured_output"])
    #     self.assertIn("citations", result["structured_output"])
    #     self.assertIsInstance(result["structured_output"]["citations"], list)
    #     self.assertIn("web_search_result", result)
    #     self.assertIsNotNone(result["web_search_result"])

    # --- Vision Tests ---

    async def test_openai_vision_text_output(self):
        """Test OpenAI GPT-4o with image input and text output."""
        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.GPT_4o.value,
            user_prompt="What text do you see in this image? Please describe what you observe.",
            image_input_url_or_base64="https://upload.wikimedia.org/wikipedia/en/a/a9/Example.jpg",
            max_tokens=200
        )
        self.assertIsInstance(result, dict)
        self.assertIn("text_content", result)
        self.assertIsInstance(result["text_content"], str)
        self.assertGreater(len(result["text_content"]), 0)
        # Assert that the response contains the word "example" (case-insensitive)
        self.assertIn("example", result["text_content"].lower())
        print(result["text_content"])

    async def test_anthropic_vision_text_output(self):
        """Test Anthropic Claude 3.5 Sonnet with image input and text output."""
        result = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_5_SONNET.value,
            user_prompt="What text do you see in this image? Please describe what you observe.",
            image_input_url_or_base64="https://upload.wikimedia.org/wikipedia/en/a/a9/Example.jpg",
            max_tokens=200
        )
        self.assertIsInstance(result, dict)
        self.assertIn("text_content", result)
        self.assertIsInstance(result["text_content"], str)
        self.assertGreater(len(result["text_content"]), 0)
        # Assert that the response contains the word "example" (case-insensitive)
        self.assertIn("example", result["text_content"].lower())
        print(result["text_content"])


if __name__ == "__main__":
    # Consider adding logic to skip tests if required API keys are not set in settings
    # if not settings.ANTHROPIC_API_KEY or not settings.OPENAI_API_KEY:
    #     print("Skipping LLM tests: Missing API keys in settings.")
    # else:
    # It's generally better to run tests via a test runner (like pytest or python -m unittest)
    # rather than executing the file directly.
    unittest.main()

