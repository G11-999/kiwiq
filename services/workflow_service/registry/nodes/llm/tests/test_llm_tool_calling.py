import json
from typing import Dict, Any, List, ClassVar, Awaitable, Optional
import unittest
import asyncio
import uuid
from pydantic import BaseModel, Field
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage

from kiwi_app.workflow_app.constants import SchemaType
from kiwi_app.workflow_app.schemas import SchemaTemplateCreate
from db.session import get_async_db_as_manager, get_async_session
from workflow_service.registry.nodes.core.base import BaseSchema, BaseNode
from workflow_service.config.constants import (
    INPUT_NODE_NAME,
    OUTPUT_NODE_NAME,
    DB_SESSION_KEY,
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
    ToolOutput,
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
# Import internal tool config schemas
from workflow_service.registry.nodes.llm.internal_tools.openai_tools import OpenAIWebSearchToolConfig
from workflow_service.registry.nodes.llm.internal_tools.anthropic_tools import AnthropicSearchToolConfig


# --- Fake Web Search Node for Testing ---
class FakeWebSearchInputSchema(BaseSchema):
    """Input schema for the FakeWebSearch node."""
    query: str = Field(..., description="The search query to execute")
    max_results: int = Field(description="Maximum number of results to return")

class FakeWebSearchConfigSchema(BaseSchema):
    """Configuration schema for the FakeWebSearch node."""
    pass

class FakeWebSearchOutputSchema(BaseSchema):
    """Output schema for the FakeWebSearch node."""
    search_results: List[Dict[str, str]] = Field(..., description="List of search results")
    query_used: str = Field(..., description="The query that was used")

class FakeWebSearchNode(BaseNode[FakeWebSearchInputSchema, FakeWebSearchOutputSchema, FakeWebSearchConfigSchema]):
    """
    Fake Web Search Node for testing purposes.
    Simulates a web search by returning predefined results based on the query.
    """
    node_name: ClassVar[str] = "web_search_tool"
    node_version: ClassVar[str] = "1.0.0"
    node_is_tool: ClassVar[bool] = True
    
    input_schema_cls: ClassVar[type] = FakeWebSearchInputSchema
    output_schema_cls: ClassVar[type] = FakeWebSearchOutputSchema
    config_schema_cls: ClassVar[type] = FakeWebSearchConfigSchema
    
    async def process(self, input_data: FakeWebSearchInputSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> FakeWebSearchOutputSchema:
        """
        Process the input data and return fake search results.
        
        Args:
            input_data: The input data containing the search query.
            config: Configuration parameters.
            
        Returns:
            FakeWebSearchOutputSchema: The fake search results.
        """
        query = input_data.query
        max_results = input_data.max_results or 3
        
        # Generate fake search results based on the query
        fake_results = []
        
        # Common topics to generate relevant results
        if "mindfulness" in query.lower() or "meditation" in query.lower():
            fake_results = [
                {
                    "title": "The Science of Mindfulness Meditation",
                    "snippet": "Recent studies show that mindfulness meditation can reduce stress by up to 40% by lowering cortisol levels...",
                    "url": "https://example.com/mindfulness-science"
                },
                {
                    "title": "5 Simple Mindfulness Techniques for Stress Reduction",
                    "snippet": "These evidence-based mindfulness practices can be done in just 5-10 minutes per day and have been shown to significantly reduce anxiety...",
                    "url": "https://example.com/mindfulness-techniques"
                },
                {
                    "title": "How Mindfulness Changes the Brain",
                    "snippet": "Neuroimaging research reveals that regular meditation practice can increase gray matter density in brain regions associated with emotional regulation...",
                    "url": "https://example.com/mindfulness-brain-changes"
                },
                {
                    "title": "Workplace Mindfulness Programs Show Promising Results",
                    "snippet": "Companies implementing mindfulness programs report 28% reduction in stress-related sick days and improved employee satisfaction...",
                    "url": "https://example.com/workplace-mindfulness"
                }
            ]
        else:
            # Generic results for any query
            fake_results = [
                {
                    "title": f"Research on {query}",
                    "snippet": f"Recent studies about {query} have shown significant developments in this field...",
                    "url": f"https://example.com/{query.replace(' ', '-')}-research"
                },
                {
                    "title": f"Top 10 Facts about {query}",
                    "snippet": f"Interesting and well-researched information about {query} that experts agree on...",
                    "url": f"https://example.com/{query.replace(' ', '-')}-facts"
                },
                {
                    "title": f"The Future of {query}",
                    "snippet": f"Experts predict that {query} will continue to evolve in the coming years with new innovations...",
                    "url": f"https://example.com/{query.replace(' ', '-')}-future"
                }
            ]
        
        # Limit the number of results
        limited_results = fake_results[:max_results]
        
        return FakeWebSearchOutputSchema(
            search_results=limited_results,
            query_used=query
        )

# --- Test-specific Schemas and Prompts ---

class SimplePostSchema(BaseModel):
    """Schema for simple post generation output."""
    post_text: str = Field(..., description="The content of the post.")
    tags: List[str] = Field(description="Relevant tags for the post.")
    citations: List[str] = Field(description="Citations used in the post.")

SIMPLE_POST_SYSTEM_PROMPT = "You are an expert writer. Create content based on user requests. If given feedback, revise the previous content based on the feedback. Please search for the latest information from 2025 using web search tool before writing the post."
INITIAL_POST_USER_PROMPT_TEMPLATE = "Write a short post about {topic}. Use citations and links / quotes from web pages to support your points in the post -- don't hallucinate the citations / links / quotes or make them up, only use them if provided in context via search results."
FEEDBACK_POST_USER_PROMPT_TEMPLATE = """I have some feedback on the previous post about {topic}.\
Previous post: \"{previous_post_text}\"\
Feedback: \"{feedback}\"\
Please rewrite the post incorporating the feedback."""

# --- Tool Definition for Web Search Tool Use Tests ---
class WebSearchResultSummarySchema(BaseModel):
    '''Schema for summarizing web search results.'''
    summary: str = Field(..., description="A concise summary of the web search findings.")
    key_points: List[str] = Field(description="Key points or facts extracted.")
    urls_processed_count: int = Field(..., description="Number of (mock) URLs processed from the search results.")
    citations: List[str] = Field(description="Citations used in the post.")

WEB_SEARCH_SYSTEM_PROMPT = "You are a helpful research assistant. When asked a question that requires up-to-date information or general knowledge beyond your training cut-off, you must use the web search tool to find relevant information. Then, answer the user's question or summarize the findings based on the search results."
WEB_SEARCH_USER_PROMPT_TURN1_TEMPLATE = "Please find out the latest information on '{topic}' and then tell me about it."
WEB_SEARCH_USER_PROMPT_TURN2_TEXT_TEMPLATE = """Based on the search results you found for '{topic}', please provide a text summary."""
WEB_SEARCH_USER_PROMPT_TURN2_STRUCTURED_TEMPLATE = """Based on the search results you found for '{topic}', please provide a structured summary including key points and the number of URLs you processed."""


# --- Helper function for message conversion ---
# This function might still be used by other tests not modified in this pass.
# If it's confirmed to be unused after all modifications, it can be removed later.
def convert_lc_messages_to_dicts(messages: List[AnyMessage]) -> List[Dict[str, Any]]:
    """Converts a list of Langchain BaseMessage objects to a list of dictionaries."""
    # ... existing code ...

# --- Tool Definition for Tool Use Tests ---
class GetWeatherParams(BaseModel):
    """Parameters for the get_weather tool."""
    location: str = Field(..., description="The city and state, e.g., San Francisco, CA")
    unit: Optional[str] = Field(default="celsius", description="Temperature unit: 'celsius' or 'fahrenheit'")

GET_WEATHER_TOOL_NAME = "get_weather"
GET_WEATHER_TOOL_DESCRIPTION = "Get the current weather in a given location."
# Generate the JSON schema for the tool parameters
GET_WEATHER_TOOL_SCHEMA_DEFINITION = GetWeatherParams.model_json_schema()


class ActivitySuggestionSchema(BaseModel):
    """Schema for activity suggestion output after using a tool."""
    activity: str = Field(..., description="The suggested activity based on weather or other tool output.")
    reasoning: str = Field(..., description="Why this activity is suitable.")

class DetailedActivitySuggestionSchema(BaseModel):
    """More detailed schema for activity suggestion, possibly involving more reasoning."""
    activity: str = Field(..., description="The suggested activity.")
    detailed_reasoning: str = Field(..., description="A detailed explanation for the suggestion, potentially citing tool outputs.")
    alternatives: List[str] = Field(description="Alternative activities, if any.")

TOOL_USE_SYSTEM_PROMPT = "You are a helpful assistant. When asked a question that requires external information like weather, you must use the available tools to get that information first, and then answer the user's question using the tool's output. Call only one tool at a time if multiple are available and relevant."
TOOL_USE_USER_PROMPT_TURN1_TEMPLATE = "What's the weather like in {location}? After you find out, please suggest a suitable outdoor activity there."
TOOL_USE_USER_PROMPT_TURN2_TEMPLATE = "Okay, I have the weather. Now, based on the weather being {weather_details}, what's a good outdoor activity in {location}?"



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
    tools: Optional[List[ToolConfig]] = None,
    **kwargs,
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
        web_search_options: Optional web search config for model's native search.
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
    if output_schema_config:
        output_schema_config.convert_loaded_schema_to_pydantic = False
    llm_config_data = LLMNodeConfigSchema(
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
        thinking_tokens_in_prompt="all", # type: ignore
        output_schema=output_schema_config or LLMStructuredOutputSchema(), # Use provided or default
        web_search_options=web_search_options, # type: ignore
        tool_calling_config=tool_calling_config or ToolCallingConfig(),
        tools=tools
    )

    # LLM node
    llm_node = NodeConfig(
        node_id="llm_node",
        node_name="llm",
        node_config=llm_config_data.model_dump(exclude_none=True) # Exclude Nones for cleaner config
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
                EdgeMapping(src_field="tool_outputs", dst_field="tool_outputs"), # For providing tool execution results back to LLM
            ]
        ),
        EdgeSchema(
            src_node_id="llm_node",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="structured_output", dst_field="structured_output"),
                EdgeMapping(src_field="metadata", dst_field="metadata"),
                EdgeMapping(src_field="text_content", dst_field="text_content"),
                EdgeMapping(src_field="current_messages", dst_field="current_messages"),
                EdgeMapping(src_field="content", dst_field="content"),
                EdgeMapping(src_field="web_search_result", dst_field="web_search_result"),
                EdgeMapping(src_field="tool_calls", dst_field="tool_calls"), # Crucial for testing tool call generation
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
    registry.register_node(FakeWebSearchNode)  # Register our fake search node

    # No need to register TTestSchema here as we are providing schemas directly

    return registry


async def arun_llm_test(
    runtime_config: Dict[str, Any], # Pass runtime config
    model_provider: LLMModelProvider,
    model_name: str,
    max_tokens: int = 100,
    output_schema_config: Optional[LLMStructuredOutputSchema] = None,
    reasoning_config: Optional[Dict[str, Any]] = None,
    user_prompt: str = None,
    messages_history: Optional[List[Dict]] = None,
    input_system_prompt: Optional[str] = None,
    tool_calling_config: Optional[ToolCallingConfig] = None, # Added for tool testing
    tools: Optional[List[ToolConfig]] = None, # Added for tool testing
    tool_outputs: Optional[List[ToolOutput]] = None, # Added for tool output handling
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
        messages_history: Optional message history.
        input_system_prompt: Optional system prompt to override default.
        tool_calling_config: Optional tool calling config.
        tools: Optional list of tools.
        tool_outputs: Optional list of tool outputs to be passed to the LLM.
        **kwargs: Additional arguments passed to create_basic_llm_graph.

    Returns:
        Dict[str, Any]: The test results from the graph execution.
    """
    registry = setup_registry()

    # Prepare input data based on provided args
    input_data = {"user_prompt": user_prompt}
    if messages_history:
        input_data["messages_history"] = messages_history # type: ignore
    if input_system_prompt:
        input_data["system_prompt"] = input_system_prompt
    if tool_outputs:
        input_data["tool_outputs"] = tool_outputs # Add tool outputs to input data

    # Create graph schema using the passed arguments
    graph_schema = create_basic_llm_graph(
        model_provider=model_provider,
        model_name=model_name,
        output_schema_config=output_schema_config,
        max_tokens=max_tokens,
        reasoning_config=reasoning_config,
        default_system_prompt=kwargs.pop("default_system_prompt", None), # Handle explicitly
        tool_calling_config=tool_calling_config, # Pass through
        tools=tools, # Pass through
        **kwargs # Pass remaining kwargs
    )

    builder = GraphBuilder(registry)
    graph_entities = builder.build_graph_entities(graph_schema)

    for node in graph_entities["node_instances"].values():
        node.billing_mode = False

    # Use provided runtime config, but ensure a unique thread_id for isolation
    graph_runtime_config = graph_entities["runtime_config"]
    graph_runtime_config.update(runtime_config) # type: ignore
    test_runtime_config = graph_runtime_config
    test_runtime_config["thread_id"] = f"llm_test_{model_provider.value}_{model_name}_{uuid.uuid4()}" # type: ignore
    test_runtime_config["use_checkpointing"] = True # Usually good for testing state # type: ignore

    adapter = LangGraphRuntimeAdapter()
    graph = adapter.build_graph(graph_entities)

    result = await adapter.aexecute_graph(
        graph=graph, # type: ignore
        input_data=input_data, # type: ignore
        config=test_runtime_config, # Use the test-specific config
        output_node_id=graph_entities["output_node_id"] # type: ignore
    )

    return result # type: ignore


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
        self.run_job_regular = WorkflowRunJobCreate(**base_run_job_info) # type: ignore

        # Initialize context for each test
        try:
             self.external_context = await get_external_context_manager_with_clients()
             registry = setup_registry()
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

        self.customer_data_service = self.external_context.customer_data_service
        # if not self.customer_data_service:
        #      self.logger.warning("CustomerDataService could not be initialized in external context.")
             # Decide if this is a skip condition or just a warning
             # raise unittest.SkipTest("CustomerDataService could not be initialized.")
    
    async def asyncTearDown(self) -> None:
        try:
            if self.external_context:
                await self.external_context.close()
        except Exception as e:
            print(f"Error in asyncTearDown: {e}")

    # async def test_anthropic_claude3_7_tool_use_text_output_reasoning(self):
    #     """Test Anthropic Claude 3.7 Sonnet with tool use (web_search), text output, and reasoning."""
    #     if not hasattr(AnthropicModels, 'CLAUDE_3_7_SONNET'):
    #         self.skipTest("AnthropicModels.CLAUDE_3_7_SONNET not defined in enum.")

    #     topic = "ethical implications of gene editing"
    #     reasoning_config = {"reasoning_tokens_budget": 1024}
    #     system_prompt_turn1 = "Think step by step before answering. " + WEB_SEARCH_SYSTEM_PROMPT

    #     # Configure the web_search_tool
    #     tool_config = ToolConfig(
    #         tool_name="web_search_tool",
    #         is_provider_inbuilt_tool=False,
    #         provider_inbuilt_user_config={}
    #     )

    #     # Enhanced prompt to strongly encourage using the search tool first
    #     user_prompt_turn2 = f"Based on your search results about {topic}, please provide a comprehensive summary, including key points and citations from your findings."
    #     enhanced_user_prompt = f"Please first search for the latest information about {topic} using the web search tool, then I'll ask you to provide a detailed summary of your findings. Please only use the tool once and then follow with the summary."

    #     # --- Turn 1: LLM makes a tool call ---
    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value, 
    #         max_tokens=1000,
    #         reasoning_config=reasoning_config,
    #         user_prompt=enhanced_user_prompt,
    #         input_system_prompt=system_prompt_turn1,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("metadata", result_turn1)
    #     self.assertIn("tool_calls", result_turn1, "Tool calls should be in Turn 1 result")
        
    #     # Get the tool call ID from the first result
    #     tool_calls = result_turn1.get("tool_calls", [])
    #     for i, tool_call in enumerate(tool_calls):
    #         if isinstance(tool_call, BaseModel):
    #             tool_calls[i] = tool_call.model_dump()

    #     tool_calls = [t for t in tool_calls if t.get("tool_name") == "web_search_tool"]
    #     tool_call_id = "fake_tool_call_id_1"
    #     if tool_calls:
    #         tool_call_id = tool_calls[0].get("tool_id")
    #     tool_args = tool_calls[0].get("tool_input")

    #     # Simulate running the fake web search node
    #     fake_search_node = FakeWebSearchNode(node_id="fake_web_search_node", prefect_mode=False)
    #     fake_search_input = FakeWebSearchInputSchema(query=tool_args.get("query", ""), max_results=tool_args.get("max_results", 3))
    #     fake_search_result = await fake_search_node.process(fake_search_input, {})
        
    #     # Convert the fake search result to the format expected by the LLM
    #     mock_tool_output_content = {
    #         "searchResults": fake_search_result.search_results,
    #         "queryUsed": fake_search_result.query_used
    #     }
    #     mock_tool_output_str = json.dumps(mock_tool_output_content)

    #     messages_history_turn1 = result_turn1.get("current_messages", [])

    #     # --- Turn 2: Provide tool output and get text summary with reasoning ---
        
    #     # Create tool_outputs for the second call
    #     tool_outputs_for_turn2 = [
    #         ToolOutput(
    #             tool_call_id=tool_call_id,
    #             content=mock_tool_output_str,
    #             type="tool",
    #             name="web_search_tool",
    #             status="success"
    #         )
    #     ]
    #     messages_history_turn2 = messages_history_turn1

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
    #         max_tokens=1000,
    #         reasoning_config=reasoning_config,
    #         messages_history=messages_history_turn2,
    #         tool_outputs=tool_outputs_for_turn2,  # Pass the fake tool outputs
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=False),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("text_content", result_turn2)
    #     text_content = result_turn2["text_content"]
    #     self.assertIsInstance(text_content, str)
    #     self.assertGreater(len(text_content), 0, "Summary should not be empty")

    #     self.assertIn("current_messages", result_turn2)
    #     print(f"Anthropic Claude 3.7 Sonnet Text Reasoning - Turn 1 metadata: {result_turn1.get('metadata')}")
    #     print(f"Anthropic Claude 3.7 Sonnet Text Reasoning - Turn 2 metadata: {result_turn2.get('metadata')}")


    # async def test_anthropic_claude3_7_tool_use_text_output(self):
    #     """Test Anthropic Claude 3.7 Sonnet with tool use (web_search), text output."""
    #     if not hasattr(AnthropicModels, 'CLAUDE_3_7_SONNET'):
    #         self.skipTest("AnthropicModels.CLAUDE_3_7_SONNET not defined in enum.")

    #     topic = "ethical implications of gene editing"
    #     system_prompt_turn1 = "Think step by step before answering. " + WEB_SEARCH_SYSTEM_PROMPT

    #     # Configure the web_search_tool
    #     tool_config = ToolConfig(
    #         tool_name="web_search_tool",
    #         is_provider_inbuilt_tool=False,
    #         provider_inbuilt_user_config={}
    #     )

    #     # Enhanced prompt to strongly encourage using the search tool first
    #     enhanced_user_prompt = f"Please first search for the latest information about {topic} using the web search tool, then I'll ask you to provide a detailed summary of your findings. Please only use the tool once and then follow with the summary."

    #     # --- Turn 1: LLM makes a tool call ---
    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value, 
    #         max_tokens=1000,
    #         user_prompt=enhanced_user_prompt,
    #         input_system_prompt=system_prompt_turn1,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("metadata", result_turn1)
    #     self.assertIn("tool_calls", result_turn1, "Tool calls should be in Turn 1 result")
        
    #     # Get the tool call ID from the first result
    #     tool_calls = result_turn1.get("tool_calls", [])
    #     for i, tool_call in enumerate(tool_calls):
    #         if isinstance(tool_call, BaseModel):
    #             tool_calls[i] = tool_call.model_dump()

    #     tool_calls = [t for t in tool_calls if t.get("tool_name") == "web_search_tool"]
    #     tool_call_id = "fake_tool_call_id_1"
    #     if tool_calls:
    #         tool_call_id = tool_calls[0].get("tool_id")
    #     tool_args = tool_calls[0].get("tool_input")
        
    #     print(tool_calls)

    #     # Simulate running the fake web search node
    #     fake_search_node = FakeWebSearchNode(node_id="fake_web_search_node", prefect_mode=False)
    #     fake_search_input = FakeWebSearchInputSchema(query=tool_args.get("query", ""), max_results=tool_args.get("max_results", 3))
    #     fake_search_result = await fake_search_node.process(fake_search_input, {})
        
    #     # Convert the fake search result to the format expected by the LLM
    #     mock_tool_output_content = {
    #         "searchResults": fake_search_result.search_results,
    #         "queryUsed": fake_search_result.query_used
    #     }
    #     mock_tool_output_str = json.dumps(mock_tool_output_content)

    #     messages_history_turn1 = result_turn1.get("current_messages", [])

    #     # --- Turn 2: Provide tool output and get text post ---
        
    #     # Create tool_outputs for the second call
    #     tool_outputs_for_turn2 = [
    #         ToolOutput(
    #             tool_call_id=tool_call_id,
    #             content=mock_tool_output_str,
    #             type="tool",
    #             name="web_search_tool",
    #             status="success"
    #         )
    #     ]
    #     messages_history_turn2 = messages_history_turn1

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
    #         max_tokens=1000,
    #         # user_prompt=user_prompt_turn2,
    #         messages_history=messages_history_turn2,
    #         tool_outputs=tool_outputs_for_turn2,  # Pass the fake tool outputs
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=False),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("text_content", result_turn2)
    #     text_content = result_turn2["text_content"]
    #     self.assertIsInstance(text_content, str)
    #     self.assertGreater(len(text_content), 0, "Post text should not be empty")

    #     self.assertIn("current_messages", result_turn2)
    #     print(f"Anthropic Claude 3.7 Sonnet Text - Turn 1 metadata: {result_turn1.get('metadata')}")
    #     print(f"Anthropic Claude 3.7 Sonnet Text - Turn 2 metadata: {result_turn2.get('metadata')}")

##########    ##########    ##########    ##########    ##########    ##########    ##########
##########    ##########    ##########    ##########    ##########    ##########    ##########
    async def test_anthropic_claude3_7_tool_use_text_output_reasoning(self):
        """Test Anthropic Claude 3.7 Sonnet with tool use (web_search), text output, and reasoning."""
        if not hasattr(AnthropicModels, 'CLAUDE_3_7_SONNET'):
            self.skipTest("AnthropicModels.CLAUDE_3_7_SONNET not defined in enum.")

        topic = "ethical implications of gene editing"
        reasoning_config = {"reasoning_tokens_budget": 1024}
        system_prompt_turn1 = "Think step by step before answering. " + WEB_SEARCH_SYSTEM_PROMPT

        anthropic_search_config = AnthropicSearchToolConfig().model_dump(exclude_none=True)
        tool_config = ToolConfig(
            tool_name="web_search",
            is_provider_inbuilt_tool=True,
            provider_inbuilt_user_config=anthropic_search_config
        )

        # --- Turn 1: LLM makes a tool call ---
        result_turn1 = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_7_SONNET.value, 
            max_tokens=1000,
            reasoning_config=reasoning_config,
            user_prompt=WEB_SEARCH_USER_PROMPT_TURN1_TEMPLATE.format(topic=topic),
            input_system_prompt=system_prompt_turn1,
            tool_calling_config=ToolCallingConfig(enable_tool_calling=True),
            tools=[tool_config]
        )

        self.assertIn("metadata", result_turn1)

        messages_history_turn1 = result_turn1.get("current_messages", [])

        # import ipdb; ipdb.set_trace()

        # --- Turn 2: Provide tool output and get text summary with reasoning ---
        user_prompt_turn2 = WEB_SEARCH_USER_PROMPT_TURN2_TEXT_TEMPLATE.format(
            topic=topic, 
        )
        messages_history_turn2 = messages_history_turn1

        result_turn2 = await arun_llm_test(
            runtime_config=self.runtime_config_regular,
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
            max_tokens=1000,
            reasoning_config=reasoning_config,
            user_prompt=user_prompt_turn2,
            messages_history=messages_history_turn2,
            # tool_outputs=tool_outputs_for_turn2,
            tool_calling_config=ToolCallingConfig(enable_tool_calling=False),
            tools=[tool_config]
        )

        self.assertIn("text_content", result_turn2)
        text_output = result_turn2["text_content"]
        self.assertIsInstance(text_output, str)
        self.assertGreater(len(text_output), 0, "Text output should not be empty")

        self.assertIn("current_messages", result_turn2)
        print(f"Anthropic Claude 3.7 Sonnet Text Reasoning - Turn 1 metadata: {result_turn1.get('metadata')}")
        print(f"Anthropic Claude 3.7 Sonnet Text Reasoning - Turn 2 metadata: {result_turn2.get('metadata')}")
##########    ##########    ##########    ##########    ##########    ##########    ##########
##########    ##########    ##########    ##########    ##########    ##########    ##########

    # async def test_anthropic_claude3_7_tool_use_text_output(self):
    #     """Test Anthropic Claude 3.7 Sonnet with tool use (web_search), text output."""
    #     if not hasattr(AnthropicModels, 'CLAUDE_3_7_SONNET'):
    #         self.skipTest("AnthropicModels.CLAUDE_3_7_SONNET not defined in enum.")

    #     topic = "ethical implications of gene editing"
    #     system_prompt_turn1 = "Think step by step before answering. " + WEB_SEARCH_SYSTEM_PROMPT

    #     anthropic_search_config = AnthropicSearchToolConfig().model_dump(exclude_none=True)
    #     tool_config = ToolConfig(
    #         tool_name="web_search",
    #         is_provider_inbuilt_tool=True,
    #         provider_inbuilt_user_config=anthropic_search_config
    #     )

    #     # --- Turn 1: LLM makes a tool call ---
    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value, 
    #         max_tokens=1000,
    #         user_prompt=WEB_SEARCH_USER_PROMPT_TURN1_TEMPLATE.format(topic=topic),
    #         input_system_prompt=system_prompt_turn1,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("metadata", result_turn1)

    #     messages_history_turn1 = result_turn1.get("current_messages", [])

    #     # --- Turn 2: Provide tool output and get text summary ---
    #     user_prompt_turn2 = WEB_SEARCH_USER_PROMPT_TURN2_TEXT_TEMPLATE.format(
    #         topic=topic, 
    #     )
    #     messages_history_turn2 = messages_history_turn1

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
    #         max_tokens=1000,
    #         user_prompt=user_prompt_turn2,
    #         messages_history=messages_history_turn2,
    #         # tool_outputs=tool_outputs_for_turn2,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=False),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("text_content", result_turn2)
    #     text_output = result_turn2["text_content"]
    #     self.assertIsInstance(text_output, str)
    #     self.assertGreater(len(text_output), 0, "Text output should not be empty")

    #     self.assertIn("current_messages", result_turn2)
    #     print(f"Anthropic Claude 3.7 Sonnet Text - Turn 1 metadata: {result_turn1.get('metadata')}")
    #     print(f"Anthropic Claude 3.7 Sonnet Text - Turn 2 metadata: {result_turn2.get('metadata')}")
    


    # async def test_anthropic_claude3_7_tool_use_structured_output_reasoning(self):
    #     """Test Anthropic Claude 3.7 Sonnet with tool use (web_search), structured output, and reasoning."""
    #     if not hasattr(AnthropicModels, 'CLAUDE_3_7_SONNET'):
    #         self.skipTest("AnthropicModels.CLAUDE_3_7_SONNET not defined in enum.")

    #     topic = "ethical implications of gene editing"
    #     reasoning_config = {"reasoning_tokens_budget": 1024}
    #     system_prompt_turn1 = "Think step by step before answering. " + WEB_SEARCH_SYSTEM_PROMPT

    #     # Setup structured output schema for turn 2
    #     summary_schema_dict = WebSearchResultSummarySchema.model_json_schema()
    #     structured_output_config = LLMStructuredOutputSchema(
    #         schema_definition=summary_schema_dict,
    #     )

    #     anthropic_search_config = AnthropicSearchToolConfig().model_dump(exclude_none=True)
    #     tool_config = ToolConfig(
    #         tool_name="web_search",
    #         is_provider_inbuilt_tool=True,
    #         provider_inbuilt_user_config=anthropic_search_config
    #     )

    #     # Enhanced prompt to strongly encourage using the search tool first
    #     enhanced_user_prompt = f"Please first search for the latest information about {topic} using the web search tool, then I'll ask you to provide a structured summary of your findings."

    #     # --- Turn 1: LLM makes a tool call ---
    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value, 
    #         max_tokens=1000,
    #         reasoning_config=reasoning_config,
    #         user_prompt=enhanced_user_prompt,
    #         output_schema_config=structured_output_config,
    #         input_system_prompt=system_prompt_turn1,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("metadata", result_turn1)

    #     messages_history_turn1 = result_turn1.get("current_messages", [])

    #     # --- Turn 2: Provide tool output and get structured summary with reasoning ---
    #     user_prompt_turn2 = f"Based on your search results about {topic}, please provide a structured summary following the schema, including key points and citations from your findings."
    #     messages_history_turn2 = messages_history_turn1

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
    #         max_tokens=1000,
    #         reasoning_config=reasoning_config,
    #         user_prompt=user_prompt_turn2,
    #         messages_history=messages_history_turn2,
    #         output_schema_config=structured_output_config,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=False),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("structured_output", result_turn2)
    #     structured_data = result_turn2["structured_output"]
    #     self.assertIsInstance(structured_data, dict)
        
    #     summary = structured_data.get("summary", "")
    #     key_points = structured_data.get("key_points", [])
    #     urls_processed_count = structured_data.get("urls_processed_count", 0)
    #     citations = structured_data.get("citations", [])

    #     try:
    #         validated_output = WebSearchResultSummarySchema(**structured_data)
    #         summary = validated_output.summary
    #         key_points = validated_output.key_points
    #         urls_processed_count = validated_output.urls_processed_count
    #         citations = validated_output.citations
    #     except Exception as e:
    #         # self.fail(f"Structured output validation failed: {e}\nOutput: {json.dumps(structured_data, indent=2)}")
    #         pass
        
    #     self.assertIsInstance(summary, str)
    #     self.assertGreater(len(summary), 0, "Summary should not be empty")
    #     self.assertGreaterEqual(urls_processed_count, 1, "Should process at least one URL")

    #     self.assertIn("current_messages", result_turn2)
    #     print(f"Anthropic Claude 3.7 Sonnet Text Reasoning - Turn 1 metadata: {result_turn1.get('metadata')}")
    #     print(f"Anthropic Claude 3.7 Sonnet Text Reasoning - Turn 2 metadata: {result_turn2.get('metadata')}")
    

    # async def test_anthropic_claude3_7_tool_use_structured_output(self):
    #     """Test Anthropic Claude 3.7 Sonnet with tool use (web_search), structured output."""
    #     if not hasattr(AnthropicModels, 'CLAUDE_3_7_SONNET'):
    #         self.skipTest("AnthropicModels.CLAUDE_3_7_SONNET not defined in enum.")

    #     topic = "ethical implications of gene editing"
    #     system_prompt_turn1 = "Think step by step before answering. " + WEB_SEARCH_SYSTEM_PROMPT

    #     # Setup structured output schema for SimplePostSchema
    #     post_schema_dict = SimplePostSchema.model_json_schema()
    #     structured_output_config = LLMStructuredOutputSchema(
    #         schema_definition=post_schema_dict,
    #     )

    #     anthropic_search_config = AnthropicSearchToolConfig().model_dump(exclude_none=True)
    #     tool_config = ToolConfig(
    #         tool_name="web_search",
    #         is_provider_inbuilt_tool=True,
    #         provider_inbuilt_user_config=anthropic_search_config
    #     )

    #     # Enhanced prompt to strongly encourage using the search tool first
    #     enhanced_user_prompt = f"Please first search for the latest information about {topic} using the web search tool. After that, please create a post about it."  # After that, I'll ask you to create a post about it."

    #     # --- Turn 1: LLM makes a tool call ---
    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value, 
    #         max_tokens=1000,
    #         user_prompt=enhanced_user_prompt,
    #         # output_schema_config=structured_output_config,
    #         input_system_prompt=system_prompt_turn1,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("metadata", result_turn1)

    #     messages_history_turn1 = result_turn1.get("current_messages", [])
    #     web_search_result = result_turn1.get("web_search_result", [])

    #     # --- Turn 2: Provide tool output and get structured post ---
    #     user_prompt_turn2 = f"Based on your search results about {topic} \n\nSearch Results: {json.dumps(web_search_result, indent=2)}\n\n, please create a structured post that includes the main text, relevant tags, and citations from your search."
    #     messages_history_turn2 = messages_history_turn1

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
    #         max_tokens=1000,
    #         user_prompt=user_prompt_turn2,
    #         messages_history=messages_history_turn2,
    #         output_schema_config=structured_output_config,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("structured_output", result_turn2)
    #     structured_data = result_turn2["structured_output"]
    #     self.assertIsInstance(structured_data, dict)

    #     post_text = structured_data.get("post_text", "")
        
    #     try:
    #         validated_output = SimplePostSchema(**structured_data)
    #         post_text = validated_output.post_text
    #     except Exception as e:
    #         print(f"Structured output validation failed: {e}\nOutput: {json.dumps(structured_data, indent=2)}")
    #         # self.fail(f"Structured output validation failed: {e}\nOutput: {json.dumps(structured_data, indent=2)}")
        
    #     self.assertIsInstance(post_text, str)
    #     self.assertGreater(len(post_text), 0, "Post text should not be empty")

    #     self.assertIn("current_messages", result_turn2)
    #     print(f"Anthropic Claude 3.7 Sonnet Text - Turn 1 metadata: {result_turn1.get('metadata')}")
    #     print(f"Anthropic Claude 3.7 Sonnet Text - Turn 2 metadata: {result_turn2.get('metadata')}")

    # async def test_anthropic_claude3_7_tool_use_structured_output_reasoning(self):
    #     """Test Anthropic Claude 3.7 Sonnet with tool use (web_search), structured output, and reasoning."""
    #     if not hasattr(AnthropicModels, 'CLAUDE_3_7_SONNET'):
    #         self.skipTest("AnthropicModels.CLAUDE_3_7_SONNET not defined in enum.")

    #     topic = "ethical implications of gene editing"
    #     reasoning_config = {"reasoning_tokens_budget": 1024}
    #     system_prompt_turn1 = "Think step by step before answering. " + WEB_SEARCH_SYSTEM_PROMPT

    #     # Setup structured output schema for turn 2
    #     summary_schema_dict = WebSearchResultSummarySchema.model_json_schema()
    #     structured_output_config = LLMStructuredOutputSchema(
    #         schema_definition=summary_schema_dict,
    #     )

    #     # Configure the web_search_tool
    #     tool_config = ToolConfig(
    #         tool_name="web_search_tool",
    #         is_provider_inbuilt_tool=False,
    #         provider_inbuilt_user_config={}
    #     )

    #     # Enhanced prompt to strongly encourage using the search tool first
    #     user_prompt_turn2 = f"Based on your search results about {topic}, please provide a structured summary following the schema, including key points and citations from your findings."
    #     enhanced_user_prompt = f"Please first search for the latest information about {topic} using the web search tool, then I'll ask you to provide a structured summary of your findings. Please only use the tool once and then following then {user_prompt_turn2}"

    #     # --- Turn 1: LLM makes a tool call ---
    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value, 
    #         max_tokens=1000,
    #         reasoning_config=reasoning_config,
    #         user_prompt=enhanced_user_prompt,
    #         output_schema_config=structured_output_config,
    #         input_system_prompt=system_prompt_turn1,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("metadata", result_turn1)
    #     self.assertIn("tool_calls", result_turn1, "Tool calls should be in Turn 1 result")
        
    #     # Get the tool call ID from the first result
    #     tool_calls = result_turn1.get("tool_calls", [])
    #     for i, tool_call in enumerate(tool_calls):
    #         if isinstance(tool_call, BaseModel):
    #             tool_calls[i] = tool_call.model_dump()

    #     tool_calls = [t for t in tool_calls if t.get("tool_name") == "web_search_tool"]
    #     tool_call_id = "fake_tool_call_id_1"
    #     if tool_calls:
    #         tool_call_id = tool_calls[0].get("tool_id")
    #     tool_args = tool_calls[0].get("tool_input")
        
    #     print(tool_calls)

    #     # Simulate running the fake web search node
    #     fake_search_node = FakeWebSearchNode(node_id="fake_web_search_node", prefect_mode=False)
    #     fake_search_input = FakeWebSearchInputSchema(query=tool_args.get("query", ""), max_results=tool_args.get("max_results", 3))
    #     fake_search_result = await fake_search_node.process(fake_search_input, {})
        
    #     # Convert the fake search result to the format expected by the LLM
    #     mock_tool_output_content = {
    #         "searchResults": fake_search_result.search_results,
    #         "queryUsed": fake_search_result.query_used
    #     }
    #     mock_tool_output_str = json.dumps(mock_tool_output_content)

    #     messages_history_turn1 = result_turn1.get("current_messages", [])

    #     # --- Turn 2: Provide tool output and get structured summary with reasoning ---
        
        
    #     # Create tool_outputs for the second call
    #     tool_outputs_for_turn2 = [
    #         ToolOutput(
    #             tool_call_id=tool_call_id,
    #             content=mock_tool_output_str,
    #             type="tool",
    #             name="web_search_tool",
    #             status="success"
    #         )
    #     ]
    #     messages_history_turn2 = messages_history_turn1

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
    #         max_tokens=1000,
    #         reasoning_config=reasoning_config,
    #         # user_prompt=user_prompt_turn2,
    #         messages_history=messages_history_turn2,
    #         tool_outputs=tool_outputs_for_turn2,  # Pass the fake tool outputs
    #         output_schema_config=structured_output_config,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("structured_output", result_turn2)
    #     structured_data = result_turn2["structured_output"]
    #     self.assertIsInstance(structured_data, dict)
        
    #     summary = structured_data.get("summary", "")
    #     key_points = structured_data.get("key_points", [])
    #     urls_processed_count = structured_data.get("urls_processed_count", 0)
    #     citations = structured_data.get("citations", [])

    #     try:
    #         validated_output = WebSearchResultSummarySchema(**structured_data)
    #         summary = validated_output.summary
    #         key_points = validated_output.key_points
    #         urls_processed_count = validated_output.urls_processed_count
    #         citations = validated_output.citations
    #     except Exception as e:
    #         # self.fail(f"Structured output validation failed: {e}\nOutput: {json.dumps(structured_data, indent=2)}")
    #         pass
        
    #     self.assertIsInstance(summary, str)
    #     self.assertGreater(len(summary), 0, "Summary should not be empty")
    #     self.assertGreaterEqual(urls_processed_count, 1, "Should process at least one URL")

    #     self.assertIn("current_messages", result_turn2)
    #     print(f"Anthropic Claude 3.7 Sonnet Text Reasoning - Turn 1 metadata: {result_turn1.get('metadata')}")
    #     print(f"Anthropic Claude 3.7 Sonnet Text Reasoning - Turn 2 metadata: {result_turn2.get('metadata')}")
    

    # async def test_anthropic_claude3_7_tool_use_structured_output(self):
    #     """Test Anthropic Claude 3.7 Sonnet with tool use (web_search), structured output."""
    #     if not hasattr(AnthropicModels, 'CLAUDE_3_7_SONNET'):
    #         self.skipTest("AnthropicModels.CLAUDE_3_7_SONNET not defined in enum.")

    #     topic = "ethical implications of gene editing"
    #     system_prompt_turn1 = "Think step by step before answering. " + WEB_SEARCH_SYSTEM_PROMPT

    #     # Setup structured output schema for SimplePostSchema
    #     post_schema_dict = SimplePostSchema.model_json_schema()
    #     structured_output_config = LLMStructuredOutputSchema(
    #         schema_definition=post_schema_dict,
    #     )

    #     # Configure the web_search_tool
    #     tool_config = ToolConfig(
    #         tool_name="web_search_tool",
    #         is_provider_inbuilt_tool=False,
    #         provider_inbuilt_user_config={}
    #     )

    #     # Enhanced prompt to strongly encourage using the search tool first
    #     user_prompt_turn2 = f"Based on your search results about {topic}, please provide a structured summary following the schema, including key points and citations from your findings."
    #     enhanced_user_prompt = f"Please first search for the latest information about {topic} using the web search tool, then I'll ask you to provide a structured summary of your findings. Please only use the tool once and then following then {user_prompt_turn2}"
    #     # enhanced_user_prompt = f"Please first search for the latest information about {topic} using the web search tool. After that, please create a post about it."

    #     # --- Turn 1: LLM makes a tool call ---
    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value, 
    #         max_tokens=1000,
    #         user_prompt=enhanced_user_prompt,
    #         input_system_prompt=system_prompt_turn1,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("metadata", result_turn1)
    #     self.assertIn("tool_calls", result_turn1, "Tool calls should be in Turn 1 result")
        
    #     # Get the tool call ID from the first result
    #     tool_calls = result_turn1.get("tool_calls", [])
    #     for i, tool_call in enumerate(tool_calls):
    #         if isinstance(tool_call, BaseModel):
    #             tool_calls[i] = tool_call.model_dump()

    #     tool_calls = [t for t in tool_calls if t.get("tool_name") == "web_search_tool"]
    #     tool_call_id = "fake_tool_call_id_1"
    #     if tool_calls:
    #         tool_call_id = tool_calls[0].get("tool_id")
    #     tool_args = tool_calls[0].get("tool_input")
        
    #     print(tool_calls)

    #     # Simulate running the fake web search node
    #     fake_search_node = FakeWebSearchNode(node_id="fake_web_search_node", prefect_mode=False)
    #     fake_search_input = FakeWebSearchInputSchema(query=tool_args.get("query", ""), max_results=tool_args.get("max_results", 3))
    #     fake_search_result = await fake_search_node.process(fake_search_input, {})
        
    #     # Convert the fake search result to the format expected by the LLM
    #     mock_tool_output_content = {
    #         "searchResults": fake_search_result.search_results,
    #         "queryUsed": fake_search_result.query_used
    #     }
    #     mock_tool_output_str = json.dumps(mock_tool_output_content)

    #     messages_history_turn1 = result_turn1.get("current_messages", [])

    #     # --- Turn 2: Provide tool output and get structured post ---
    #     user_prompt_turn2 = f"Based on your search results about {topic}, please create a structured post that includes the main text, relevant tags, and citations from your search."
        
    #     # Create tool_outputs for the second call
    #     tool_outputs_for_turn2 = [
    #         ToolOutput(
    #             tool_call_id=tool_call_id,
    #             content=mock_tool_output_str,
    #             type="tool",
    #             name="web_search_tool",
    #             status="success"
    #         )
    #     ]
    #     messages_history_turn2 = messages_history_turn1

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.ANTHROPIC,
    #         model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
    #         max_tokens=1000,
    #         # user_prompt=user_prompt_turn2,
    #         messages_history=messages_history_turn2,
    #         tool_outputs=tool_outputs_for_turn2,  # Pass the fake tool outputs
    #         output_schema_config=structured_output_config,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("structured_output", result_turn2)
    #     structured_data = result_turn2["structured_output"]
    #     self.assertIsInstance(structured_data, dict)

    #     post_text = structured_data.get("post_text", "")
        
    #     try:
    #         validated_output = SimplePostSchema(**structured_data)
    #         post_text = validated_output.post_text
    #     except Exception as e:
    #         print(f"Structured output validation failed: {e}\nOutput: {json.dumps(structured_data, indent=2)}")
    #         # self.fail(f"Structured output validation failed: {e}\nOutput: {json.dumps(structured_data, indent=2)}")
        
    #     self.assertIsInstance(post_text, str)
    #     self.assertGreater(len(post_text), 0, "Post text should not be empty")

    #     self.assertIn("current_messages", result_turn2)
    #     print(f"Anthropic Claude 3.7 Sonnet Text - Turn 1 metadata: {result_turn1.get('metadata')}")
    #     print(f"Anthropic Claude 3.7 Sonnet Text - Turn 2 metadata: {result_turn2.get('metadata')}")





    ################### ################### ################### ################### ################### 
    ######################################     OPEN AI TESTS    ################### ###################
    ################### ################### ################### ################### ################### 

##########    ##########    ##########    ##########    ##########    ##########    ##########
##########    ##########    ##########    ##########    ##########    ##########    ##########
    # async def test_openai_gpt4o_text_output_with_web_search(self):
    #     """
    #     Test OpenAI GPT-4o for a multi-turn conversation involving feedback for content generation.
    #     Uses independent schemas and prompts and web search tool.
    #     """

    #     # Set up web search tool
    #     openai_search_config = OpenAIWebSearchToolConfig().model_dump(exclude_none=True)
    #     tool_config = ToolConfig(
    #         tool_name="web_search_preview",
    #         is_provider_inbuilt_tool=True,
    #         provider_inbuilt_user_config=openai_search_config
    #     )
    #     tool_calling_config = ToolCallingConfig(
    #         enable_tool_calling=True
    #     )

    #     topic = "AI in creative writing"
    #     user_dna_example = "The user is a novelist, prefers an inspiring tone, and likes to explore philosophical aspects of technology."

    #     # First turn: Initial post creation
    #     initial_user_prompt = "Please search for the latest information from 2025 about " + topic + " and then " + INITIAL_POST_USER_PROMPT_TEMPLATE.format(topic=topic)

    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.OPENAI,
    #         model_name=OpenAIModels.GPT_4o.value,
    #         user_prompt=initial_user_prompt,
    #         input_system_prompt=SIMPLE_POST_SYSTEM_PROMPT,
    #         max_tokens=500,
    #         tools=[tool_config],
    #         tool_calling_config=tool_calling_config
    #     )

    #     self.assertIsInstance(result_turn1, dict, "Turn 1 result should be a dictionary.")
        
    #     self.assertIn("current_messages", result_turn1, "current_messages missing in turn 1 result.")
    #     self.assertIsInstance(result_turn1["current_messages"], list, "current_messages should be a list.")
    #     self.assertTrue(len(result_turn1["current_messages"]) >= 2, "Should have at least system, user, assistant messages in history.")

    #     # Second turn: Provide feedback and ask for revision
    #     feedback_text = "Could you make the tone more philosophical and add a specific example?"
        
    #     feedback_user_prompt = FEEDBACK_POST_USER_PROMPT_TEMPLATE.format(
    #         topic=topic,
    #         previous_post_text=result_turn1.get("text_content", ""),
    #         feedback=feedback_text
    #     )
        
    #     messages_history_turn2 = result_turn1.get("current_messages", [])
    #     self.assertTrue(len(messages_history_turn2) > 0, "Message history for turn 2 is empty.")

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.OPENAI,
    #         model_name=OpenAIModels.GPT_4o.value,
    #         user_prompt=feedback_user_prompt,
    #         messages_history=messages_history_turn2,
    #         input_system_prompt=SIMPLE_POST_SYSTEM_PROMPT,
    #         max_tokens=500,
    #         tools=[tool_config],
    #         tool_calling_config=tool_calling_config
    #     )

    #     self.assertIsInstance(result_turn2, dict, "Turn 2 result should be a dictionary.")

    #     self.assertNotEqual(result_turn1.get("text_content", ""), result_turn2.get("text_content", ""), "Revised post should differ from the original.")

    #     self.assertIn("current_messages", result_turn2, "current_messages missing in turn 2 result.")
    #     self.assertIsInstance(result_turn2["current_messages"], list, "current_messages should be a list in turn 2.")
##########    ##########    ##########    ##########    ##########    ##########    ##########
##########    ##########    ##########    ##########    ##########    ##########    ##########

    # async def test_openai_gpt4o_conversation_with_feedback_content_generation(self):
    #     """
    #     Test OpenAI GPT-4o for a multi-turn conversation involving feedback for content generation.
    #     Uses independent schemas and prompts and web search tool.

    #     # NOTE: somehow inbuilt tools not being called when structured outputs are used!
    #     """
    #     post_draft_schema_dict = SimplePostSchema.model_json_schema()
    #     structured_output_config = LLMStructuredOutputSchema(
    #         schema_definition=post_draft_schema_dict,
    #     )

    #     # Set up web search tool
    #     openai_search_config = OpenAIWebSearchToolConfig().model_dump(exclude_none=True)
    #     tool_config = ToolConfig(
    #         tool_name="web_search_preview",
    #         is_provider_inbuilt_tool=True,
    #         provider_inbuilt_user_config=openai_search_config
    #     )
    #     tool_calling_config = ToolCallingConfig(
    #         enable_tool_calling=True
    #     )

    #     topic = "AI in creative writing"
    #     user_dna_example = "The user is a novelist, prefers an inspiring tone, and likes to explore philosophical aspects of technology."

    #     # First turn: Initial post creation
    #     initial_user_prompt = "Please search for the latest information from 2025 about " + topic + " and then " + INITIAL_POST_USER_PROMPT_TEMPLATE.format(topic=topic)

    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.OPENAI,
    #         model_name=OpenAIModels.GPT_4o.value,
    #         user_prompt=initial_user_prompt,
    #         input_system_prompt=SIMPLE_POST_SYSTEM_PROMPT,
    #         output_schema_config=structured_output_config,
    #         max_tokens=1000,
    #         tools=[tool_config],
    #         tool_calling_config=tool_calling_config
    #     )

    #     self.assertIsInstance(result_turn1, dict, "Turn 1 result should be a dictionary.")
        
    #     self.assertIn("structured_output", result_turn1, "Turn 1 structured_output is missing.")
    #     self.assertIsNotNone(result_turn1["structured_output"], "Turn 1 structured_output should not be None.")
    #     self.assertIsInstance(result_turn1["structured_output"], dict, "Turn 1 structured_output should be a dict.")
        
    #     try:
    #         initial_post = SimplePostSchema(**result_turn1["structured_output"])
    #     except Exception as e:
    #         self.fail(f"Turn 1 structured_output does not match SimplePostSchema: {e}\\\\nOutput: {json.dumps(result_turn1['structured_output'], indent=2)}")

    #     self.assertTrue(len(initial_post.post_text) > 10, "Generated post_text in turn 1 seems too short.")

    #     self.assertIn("current_messages", result_turn1, "current_messages missing in turn 1 result.")
    #     self.assertIsInstance(result_turn1["current_messages"], list, "current_messages should be a list.")
    #     self.assertTrue(len(result_turn1["current_messages"]) >= 2, "Should have at least system, user, assistant messages in history.")

    #     # Second turn: Provide feedback and ask for revision
    #     feedback_text = "Could you make the tone more philosophical and add a specific example?"
        
    #     feedback_user_prompt = FEEDBACK_POST_USER_PROMPT_TEMPLATE.format(
    #         topic=topic,
    #         previous_post_text=initial_post.post_text,
    #         feedback=feedback_text
    #     )
        
    #     messages_history_turn2 = result_turn1.get("current_messages", [])
    #     self.assertTrue(len(messages_history_turn2) > 0, "Message history for turn 2 is empty.")

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.OPENAI,
    #         model_name=OpenAIModels.GPT_4o.value,
    #         user_prompt=feedback_user_prompt,
    #         messages_history=messages_history_turn2,
    #         input_system_prompt=SIMPLE_POST_SYSTEM_PROMPT,
    #         output_schema_config=structured_output_config,
    #         max_tokens=1000,
    #         tools=[tool_config],
    #         tool_calling_config=tool_calling_config
    #     )

    #     self.assertIsInstance(result_turn2, dict, "Turn 2 result should be a dictionary.")
    #     self.assertIn("structured_output", result_turn2, "Turn 2 structured_output is missing.")
    #     self.assertIsNotNone(result_turn2["structured_output"], "Turn 2 structured_output should not be None.")
    #     self.assertIsInstance(result_turn2["structured_output"], dict, "Turn 2 structured_output should be a dict.")

    #     try:
    #         revised_post = SimplePostSchema(**result_turn2["structured_output"])
    #     except Exception as e:
    #         self.fail(f"Turn 2 structured_output does not match SimplePostSchema: {e}\\\\nOutput: {json.dumps(result_turn2['structured_output'], indent=2)}")
        
    #     self.assertTrue(len(revised_post.post_text) > 10, "Revised post_text in turn 2 seems too short.")
    #     self.assertNotEqual(initial_post.post_text, revised_post.post_text, "Revised post should differ from the original.")

    #     self.assertIn("current_messages", result_turn2, "current_messages missing in turn 2 result.")
    #     self.assertIsInstance(result_turn2["current_messages"], list, "current_messages should be a list in turn 2.")

    




    # async def test_openai_gpt_4_1_tool_use_structured_output_reasoning(self):
    #     """Test OpenAI GPT_4_1 with tool use (web_search_preview), structured output, and reasoning."""
    #     # Ensure the model enum is available

    #     topic = "benefits of mindfulness meditation for stress reduction"
    #     system_prompt_turn1 = WEB_SEARCH_SYSTEM_PROMPT # Standard system prompt for web search

    #     model_provider = LLMModelProvider.OPENAI

    #     # Configure the OpenAI web_search_preview tool
    #     openai_search_config = OpenAIWebSearchToolConfig().model_dump(exclude_none=True)
    #     tool_config = ToolConfig(
    #         tool_name="web_search_tool",
    #         is_provider_inbuilt_tool=False,
    #         provider_inbuilt_user_config=openai_search_config
    #     )

    #     # --- Turn 1: LLM makes a tool call ---
    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=model_provider,
    #         model_name=OpenAIModels.GPT_4_1.value, # Using GPT_4_1 as per user guidance for reasoning
    #         max_tokens=1000, # Max tokens for the initial response part
    #         user_prompt=WEB_SEARCH_USER_PROMPT_TURN1_TEMPLATE.format(topic=topic),
    #         input_system_prompt=system_prompt_turn1,
    #         output_schema_config=LLMStructuredOutputSchema(
    #             schema_definition=WebSearchResultSummarySchema.model_json_schema()
    #         ),
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True, parallel_tool_calls=False),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("metadata", result_turn1, "Metadata should be in Turn 1 result")
    #     self.assertIn("tool_calls", result_turn1, "Tool calls should be in Turn 1 result")
        
    #     # Get the tool call ID from the first result
    #     tool_calls = result_turn1.get("tool_calls", [])
    #     for i, tool_call in enumerate(tool_calls):
    #         if isinstance(tool_call, BaseModel):
    #             tool_calls[i] = tool_call.model_dump()

    #     tool_calls = [t for t in tool_calls if t.get("tool_name") == "web_search_tool"]
    #     tool_call_id = "fake_tool_call_id_1"
    #     if tool_calls:
    #         tool_call_id = tool_calls[0].get("tool_id")
    #     tool_args = tool_calls[0].get("tool_input")
        
    #     print(tool_calls)

    #     # Simulate running the fake web search node
    #     fake_search_node = FakeWebSearchNode(node_id="fake_web_search_node", prefect_mode=False)
    #     fake_search_input = FakeWebSearchInputSchema(query=tool_args.get("query", ""), max_results=tool_args.get("max_results", 3))
    #     fake_search_result = await fake_search_node.process(fake_search_input, {})
        
    #     # Convert the fake search result to the format expected by the LLM
    #     mock_tool_output_content = {
    #         "searchResults": fake_search_result.search_results,
    #         "queryUsed": fake_search_result.query_used
    #     }
    #     mock_tool_output_str = json.dumps(mock_tool_output_content)

    #     messages_history_turn1 = result_turn1.get("current_messages", [])

    #     # --- Turn 2: Provide tool output and get structured summary ---
    #     user_prompt_turn2 = WEB_SEARCH_USER_PROMPT_TURN2_STRUCTURED_TEMPLATE.format(
    #         topic=topic,
    #     )

    #     # Create tool_outputs for the second call
    #     tool_outputs_for_turn2 = [
    #         ToolOutput(
    #             tool_call_id=tool_call_id,
    #             content=mock_tool_output_str,
    #             type="tool",
    #             name="web_search_tool",
    #             status="success"
    #             # "name": "web_search_preview"
    #         ) 
    #         # if model_provider == LLMModelProvider.ANTHROPIC else
    #         # {                               # append result message
    #         #     "type": "function_call_output",
    #         #     "call_id": tool_call_id,
    #         #     "output": mock_tool_output_str
    #         # }
    #     ]
    #     messages_history_turn2 = messages_history_turn1

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.OPENAI,
    #         model_name=OpenAIModels.GPT_4_1.value,
    #         max_tokens=1000,
    #         messages_history=messages_history_turn2,
    #         tool_outputs=tool_outputs_for_turn2,  # Pass the fake tool outputs
    #         output_schema_config=LLMStructuredOutputSchema(
    #             schema_definition=WebSearchResultSummarySchema.model_json_schema()
    #         ),
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=False, parallel_tool_calls=False),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("structured_output", result_turn2)
    #     structured_data = result_turn2["structured_output"]
    #     self.assertIsInstance(structured_data, dict)

    #     try:
    #         validated_output = WebSearchResultSummarySchema(**structured_data)
    #     except Exception as e:
    #         self.fail(f"Pydantic validation failed for OpenAI GPT_4_1 structured_output: {e}\\nData: {json.dumps(structured_data)}")

    #     self.assertIsInstance(validated_output.summary, str)
    #     self.assertGreater(len(validated_output.summary), 0)
    #     self.assertGreaterEqual(validated_output.urls_processed_count, 1)

    #     print(f"OpenAI GPT_4_1 SR Reasoning - Turn 1 metadata: {result_turn1.get('metadata')}")
    #     print(f"OpenAI GPT_4_1 SR Reasoning - Turn 2 metadata: {result_turn2.get('metadata')}")
    
    # async def test_openai_GPT_4_1_tool_use_text_reasoning(self):
    #     """Test OpenAI GPT_4_1 with tool use (web_search_preview), structured output, and reasoning."""
    #     # Ensure the model enum is available

    #     # Ensure the model enum is available

    #     topic = "benefits of mindfulness meditation for stress reduction"
    #     system_prompt_turn1 = WEB_SEARCH_SYSTEM_PROMPT # Standard system prompt for web search

    #     model_provider = LLMModelProvider.OPENAI

    #     # Configure the OpenAI web_search_preview tool
    #     openai_search_config = OpenAIWebSearchToolConfig().model_dump(exclude_none=True)
    #     tool_config = ToolConfig(
    #         tool_name="web_search_tool",
    #         is_provider_inbuilt_tool=False,
    #         provider_inbuilt_user_config=openai_search_config
    #     )

    #     # --- Turn 1: LLM makes a tool call ---
    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=model_provider,
    #         model_name=OpenAIModels.GPT_4_1.value, # Using GPT_4_1 as per user guidance for reasoning
    #         max_tokens=1000, # Max tokens for the initial response part
    #         user_prompt=WEB_SEARCH_USER_PROMPT_TURN1_TEMPLATE.format(topic=topic),
    #         input_system_prompt=system_prompt_turn1,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True, parallel_tool_calls=False),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("metadata", result_turn1, "Metadata should be in Turn 1 result")
    #     self.assertIn("tool_calls", result_turn1, "Tool calls should be in Turn 1 result")
        
    #     # Get the tool call ID from the first result
    #     tool_calls = result_turn1.get("tool_calls", [])
    #     for i, tool_call in enumerate(tool_calls):
    #         if isinstance(tool_call, BaseModel):
    #             tool_calls[i] = tool_call.model_dump()

    #     tool_calls = [t for t in tool_calls if t.get("tool_name") == "web_search_tool"]
    #     tool_call_id = "fake_tool_call_id_1"
    #     if tool_calls:
    #         tool_call_id = tool_calls[0].get("tool_id")
    #     tool_args = tool_calls[0].get("tool_input")
        
    #     print(tool_calls)

    #     # Simulate running the fake web search node
    #     fake_search_node = FakeWebSearchNode(node_id="fake_web_search_node", prefect_mode=False)
    #     fake_search_input = FakeWebSearchInputSchema(query=tool_args.get("query", ""), max_results=tool_args.get("max_results", 3))
    #     fake_search_result = await fake_search_node.process(fake_search_input, {})
        
    #     # Convert the fake search result to the format expected by the LLM
    #     mock_tool_output_content = {
    #         "searchResults": fake_search_result.search_results,
    #         "queryUsed": fake_search_result.query_used
    #     }
    #     mock_tool_output_str = json.dumps(mock_tool_output_content)

    #     messages_history_turn1 = result_turn1.get("current_messages", [])

    #     # --- Turn 2: Provide tool output and get structured summary ---
    #     user_prompt_turn2 = WEB_SEARCH_USER_PROMPT_TURN2_STRUCTURED_TEMPLATE.format(
    #         topic=topic,
    #     )

    #     # Create tool_outputs for the second call
    #     tool_outputs_for_turn2 = [
    #         ToolOutput(
    #             tool_call_id=tool_call_id,
    #             content=mock_tool_output_str,
    #             type="tool",
    #             name="web_search_tool",
    #             status="success"
    #             # "name": "web_search_preview"
    #         ) 
    #         # if model_provider == LLMModelProvider.ANTHROPIC else
    #         # {                               # append result message
    #         #     "type": "function_call_output",
    #         #     "call_id": tool_call_id,
    #         #     "output": mock_tool_output_str
    #         # }
    #     ]
    #     messages_history_turn2 = messages_history_turn1

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.OPENAI,
    #         model_name=OpenAIModels.GPT_4_1.value,
    #         max_tokens=1000,
    #         messages_history=messages_history_turn2,
    #         tool_outputs=tool_outputs_for_turn2,  # Pass the fake tool outputs
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=False, parallel_tool_calls=False),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("text_content", result_turn2)
    #     text_content = result_turn2["text_content"]
    #     self.assertIsInstance(text_content, str)

    #     self.assertGreater(len(text_content), 0)




    # async def test_openai_o4_mini_tool_use_structured_output_reasoning(self):
    #     """Test OpenAI O4_MINI with tool use (web_search_preview), structured output, and reasoning."""
    #     # Ensure the model enum is available

    #     topic = "benefits of mindfulness meditation for stress reduction"
    #     reasoning_config = {"reasoning_effort_class": "low"} # OpenAI specific reasoning config
    #     system_prompt_turn1 = WEB_SEARCH_SYSTEM_PROMPT # Standard system prompt for web search

    #     model_provider = LLMModelProvider.OPENAI

    #     # Configure the OpenAI web_search_preview tool
    #     openai_search_config = OpenAIWebSearchToolConfig().model_dump(exclude_none=True)
    #     tool_config = ToolConfig(
    #         tool_name="web_search_tool",
    #         is_provider_inbuilt_tool=False,
    #         provider_inbuilt_user_config=openai_search_config
    #     )

    #     # --- Turn 1: LLM makes a tool call ---
    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=model_provider,
    #         model_name=OpenAIModels.O4_MINI.value, # Using O4_MINI as per user guidance for reasoning
    #         max_tokens=1000, # Max tokens for the initial response part
    #         reasoning_config=reasoning_config,
    #         user_prompt=WEB_SEARCH_USER_PROMPT_TURN1_TEMPLATE.format(topic=topic),
    #         input_system_prompt=system_prompt_turn1,
    #         output_schema_config=LLMStructuredOutputSchema(
    #             schema_definition=WebSearchResultSummarySchema.model_json_schema()
    #         ),
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True, parallel_tool_calls=False),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("metadata", result_turn1, "Metadata should be in Turn 1 result")
    #     self.assertIn("tool_calls", result_turn1, "Tool calls should be in Turn 1 result")
        
    #     # Get the tool call ID from the first result
    #     tool_calls = result_turn1.get("tool_calls", [])
    #     for i, tool_call in enumerate(tool_calls):
    #         if isinstance(tool_call, BaseModel):
    #             tool_calls[i] = tool_call.model_dump()

    #     tool_calls = [t for t in tool_calls if t.get("tool_name") == "web_search_tool"]
    #     tool_call_id = "fake_tool_call_id_1"
    #     if tool_calls:
    #         tool_call_id = tool_calls[0].get("tool_id")
    #     tool_args = tool_calls[0].get("tool_input")
        
    #     print(tool_calls)

    #     # Simulate running the fake web search node
    #     fake_search_node = FakeWebSearchNode(node_id="fake_web_search_node", prefect_mode=False)
    #     fake_search_input = FakeWebSearchInputSchema(query=tool_args.get("query", ""), max_results=tool_args.get("max_results", 3))
    #     fake_search_result = await fake_search_node.process(fake_search_input, {})
        
    #     # Convert the fake search result to the format expected by the LLM
    #     mock_tool_output_content = {
    #         "searchResults": fake_search_result.search_results,
    #         "queryUsed": fake_search_result.query_used
    #     }
    #     mock_tool_output_str = json.dumps(mock_tool_output_content)

    #     messages_history_turn1 = result_turn1.get("current_messages", [])

    #     # --- Turn 2: Provide tool output and get structured summary ---
    #     user_prompt_turn2 = WEB_SEARCH_USER_PROMPT_TURN2_STRUCTURED_TEMPLATE.format(
    #         topic=topic,
    #     )

    #     # Create tool_outputs for the second call
    #     tool_outputs_for_turn2 = [
    #         ToolOutput(
    #             tool_call_id=tool_call_id,
    #             content=mock_tool_output_str,
    #             type="tool",
    #             name="web_search_tool",
    #             status="success"
    #             # "name": "web_search_preview"
    #         ) 
    #         # if model_provider == LLMModelProvider.ANTHROPIC else
    #         # {                               # append result message
    #         #     "type": "function_call_output",
    #         #     "call_id": tool_call_id,
    #         #     "output": mock_tool_output_str
    #         # }
    #     ]
    #     messages_history_turn2 = messages_history_turn1

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.OPENAI,
    #         model_name=OpenAIModels.O4_MINI.value,
    #         max_tokens=1000,
    #         reasoning_config=reasoning_config,
    #         messages_history=messages_history_turn2,
    #         tool_outputs=tool_outputs_for_turn2,  # Pass the fake tool outputs
    #         output_schema_config=LLMStructuredOutputSchema(
    #             schema_definition=WebSearchResultSummarySchema.model_json_schema()
    #         ),
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=False, parallel_tool_calls=False),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("structured_output", result_turn2)
    #     structured_data = result_turn2["structured_output"]
    #     self.assertIsInstance(structured_data, dict)

    #     try:
    #         validated_output = WebSearchResultSummarySchema(**structured_data)
    #     except Exception as e:
    #         self.fail(f"Pydantic validation failed for OpenAI O4_MINI structured_output: {e}\\nData: {json.dumps(structured_data)}")

    #     self.assertIsInstance(validated_output.summary, str)
    #     self.assertGreater(len(validated_output.summary), 0)
    #     self.assertGreaterEqual(validated_output.urls_processed_count, 1)

    #     print(f"OpenAI O4_MINI SR Reasoning - Turn 1 metadata: {result_turn1.get('metadata')}")
    #     print(f"OpenAI O4_MINI SR Reasoning - Turn 2 metadata: {result_turn2.get('metadata')}")
    
    # async def test_openai_o4_mini_tool_use_text_reasoning(self):
    #     """Test OpenAI O4_MINI with tool use (web_search_preview), structured output, and reasoning."""
    #     # Ensure the model enum is available

    #     # Ensure the model enum is available

    #     topic = "benefits of mindfulness meditation for stress reduction"
    #     reasoning_config = {"reasoning_effort_class": "low"} # OpenAI specific reasoning config
    #     system_prompt_turn1 = WEB_SEARCH_SYSTEM_PROMPT # Standard system prompt for web search

    #     model_provider = LLMModelProvider.OPENAI

    #     # Configure the OpenAI web_search_preview tool
    #     openai_search_config = OpenAIWebSearchToolConfig().model_dump(exclude_none=True)
    #     tool_config = ToolConfig(
    #         tool_name="web_search_tool",
    #         is_provider_inbuilt_tool=False,
    #         provider_inbuilt_user_config=openai_search_config
    #     )

    #     # --- Turn 1: LLM makes a tool call ---
    #     result_turn1 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=model_provider,
    #         model_name=OpenAIModels.O4_MINI.value, # Using O4_MINI as per user guidance for reasoning
    #         max_tokens=1000, # Max tokens for the initial response part
    #         reasoning_config=reasoning_config,
    #         user_prompt=WEB_SEARCH_USER_PROMPT_TURN1_TEMPLATE.format(topic=topic),
    #         input_system_prompt=system_prompt_turn1,
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=True, parallel_tool_calls=False),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("metadata", result_turn1, "Metadata should be in Turn 1 result")
    #     self.assertIn("tool_calls", result_turn1, "Tool calls should be in Turn 1 result")
        
    #     # Get the tool call ID from the first result
    #     tool_calls = result_turn1.get("tool_calls", [])
    #     for i, tool_call in enumerate(tool_calls):
    #         if isinstance(tool_call, BaseModel):
    #             tool_calls[i] = tool_call.model_dump()

    #     tool_calls = [t for t in tool_calls if t.get("tool_name") == "web_search_tool"]
    #     tool_call_id = "fake_tool_call_id_1"
    #     if tool_calls:
    #         tool_call_id = tool_calls[0].get("tool_id")
    #     tool_args = tool_calls[0].get("tool_input")
        
    #     print(tool_calls)

    #     # Simulate running the fake web search node
    #     fake_search_node = FakeWebSearchNode(node_id="fake_web_search_node", prefect_mode=False)
    #     fake_search_input = FakeWebSearchInputSchema(query=tool_args.get("query", ""), max_results=tool_args.get("max_results", 3))
    #     fake_search_result = await fake_search_node.process(fake_search_input, {})
        
    #     # Convert the fake search result to the format expected by the LLM
    #     mock_tool_output_content = {
    #         "searchResults": fake_search_result.search_results,
    #         "queryUsed": fake_search_result.query_used
    #     }
    #     mock_tool_output_str = json.dumps(mock_tool_output_content)

    #     messages_history_turn1 = result_turn1.get("current_messages", [])

    #     # --- Turn 2: Provide tool output and get structured summary ---
    #     user_prompt_turn2 = WEB_SEARCH_USER_PROMPT_TURN2_STRUCTURED_TEMPLATE.format(
    #         topic=topic,
    #     )

    #     # Create tool_outputs for the second call
    #     tool_outputs_for_turn2 = [
    #         ToolOutput(
    #             tool_call_id=tool_call_id,
    #             content=mock_tool_output_str,
    #             type="tool",
    #             name="web_search_tool",
    #             status="success"
    #             # "name": "web_search_preview"
    #         ) 
    #         # if model_provider == LLMModelProvider.ANTHROPIC else
    #         # {                               # append result message
    #         #     "type": "function_call_output",
    #         #     "call_id": tool_call_id,
    #         #     "output": mock_tool_output_str
    #         # }
    #     ]
    #     messages_history_turn2 = messages_history_turn1

    #     result_turn2 = await arun_llm_test(
    #         runtime_config=self.runtime_config_regular,
    #         model_provider=LLMModelProvider.OPENAI,
    #         model_name=OpenAIModels.O4_MINI.value,
    #         max_tokens=1000,
    #         reasoning_config=reasoning_config,
    #         messages_history=messages_history_turn2,
    #         tool_outputs=tool_outputs_for_turn2,  # Pass the fake tool outputs
    #         tool_calling_config=ToolCallingConfig(enable_tool_calling=False, parallel_tool_calls=False),
    #         tools=[tool_config]
    #     )

    #     self.assertIn("text_content", result_turn2)
    #     text_content = result_turn2["text_content"]
    #     self.assertIsInstance(text_content, str)

    #     self.assertGreater(len(text_content), 0)


if __name__ == "__main__":
    unittest.main()
