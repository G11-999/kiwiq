"""
Integration tests for basic LLM node workflows.

This module tests the LLM node in a simple 3-node graph (input -> LLM -> output)
with different model configurations and output types.
"""
import json
from typing import Dict, Any, List, ClassVar
import unittest
from pydantic import BaseModel, Field
from langchain_core.messages import AnyMessage

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
from workflow_service.registry.registry import MockRegistry
from workflow_service.registry.nodes.core.dynamic_nodes import InputNode, OutputNode


class TestOutputSchema(BaseModel):
    """Schema for test output."""
    content: str = Field(description="Generated content")
    metadata: Dict[str, Any] = Field(description="Response metadata")


def create_basic_llm_graph(
    model_provider: LLMModelProvider,
    model_name: str,
    output_type: str = "text",
    reasoning_config: Dict[str, Any] = None,
    max_tokens: int = 100,
    **kwargs
) -> GraphSchema:
    """
    Create a basic 3-node graph with LLM node.
    
    Args:
        model_provider: The LLM provider to use
        model_name: The model name to use
        output_type: Type of output ("text" or "structured")
        reasoning_config: Optional reasoning configuration
        
    Returns:
        GraphSchema: The configured graph schema
    """
    # Input node
    input_node = NodeConfig(
        node_id=INPUT_NODE_NAME,
        node_name=INPUT_NODE_NAME,
        node_config={}
    )

    dynamic_schema_spec_fields = {
            # try Any or Dict field!
            "content": DynamicSchemaFieldConfig(type="str", required=True, description="Content of the response"),
            # Below works with Anthropic!
            # "metadata": DynamicSchemaFieldConfig(type="dict",  required=True, description="Metadata of the response"),
            # "metadata": DynamicSchemaFieldConfig(type="dict",  required=True, description="Metadata of the response in dictionary key-value format", keys_type="str", values_type="str"),
            "metadata": DynamicSchemaFieldConfig(type="list", items_type="str", required=True, description="Reasoning metadata of the response"),
            # "metadata": DynamicSchemaFieldConfig(type="str", required=True, description="Reasoning metadata of the response"),
    } if "fields" not in kwargs else kwargs["fields"]

    dynamic_schema_spec = None
    if dynamic_schema_spec_fields:
        dynamic_schema_spec = ConstructDynamicSchema(
            schema_name="TestSchema",
            schema_description="Test schema",
            fields=dynamic_schema_spec_fields
        )
    
    # LLM node configuration
    llm_config = LLMNodeConfigSchema(
        default_system_prompt=kwargs.get("default_system_prompt", None),
        llm_config=LLMModelConfig(
            model_spec=ModelSpec(
                provider=model_provider,
                model=model_name
            ),
            temperature=0.0,  # For deterministic outputs
            max_tokens=max_tokens + (reasoning_config.get("reasoning_tokens_budget", 0) if reasoning_config else 0),  # Keep responses short for testing
            **reasoning_config if reasoning_config else {}
            # reasoning config
            # reasoning_effort_class="high",
            # reasoning_effort_number=100,
            # reasoning_tokens_budget=1000
        ),
        # default_system_prompt
        thinking_tokens_in_prompt="all",
        output_schema=LLMStructuredOutputSchema(
            schema_from_registry=kwargs.get("schema_from_registry", None),
            # schema_from_registry
            dynamic_schema_spec=dynamic_schema_spec if (output_type == "structured" and dynamic_schema_spec) else None
        ),
        web_search_options=kwargs.get("web_search_options", None),
    )
    
    # LLM node
    llm_node = NodeConfig(
        node_id="llm_node",
        node_name="llm",
        node_config=llm_config.model_dump()
    )
    
    # Output node
    output_node = NodeConfig(
        node_id=OUTPUT_NODE_NAME,
        node_name=OUTPUT_NODE_NAME,
        node_config={}
    )
    
    # Define edges
    edges = [
        # Input to LLM
        EdgeSchema(
            src_node_id=INPUT_NODE_NAME,
            dst_node_id="llm_node",
            mappings=[
                EdgeMapping(src_field="user_prompt", dst_field="user_prompt")
                # messages_history
                # system_prompt --> check if this will override default!
            ]
        ),
        
        # LLM to Output
        EdgeSchema(
            src_node_id="llm_node",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="structured_output", dst_field="structured_output"),
                EdgeMapping(src_field="metadata", dst_field="metadata"),
                EdgeMapping(src_field="current_messages", dst_field="current_messages"),
                EdgeMapping(src_field="content", dst_field="content"),
                EdgeMapping(src_field="web_search_result", dst_field="web_search_result"),
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
    """Setup the registry for the LLM node."""
    registry = MockRegistry()
    registry.register_node(LLMNode)
    registry.register_node(InputNode)
    registry.register_node(OutputNode)

    class TTestSchema(BaseSchema):
        schema_name: ClassVar[str] = "TTestSchema"
        int_value: int = Field(description="Integer value of answer")

    registry.register_schema(TTestSchema)
    # TODO: register schemas for consumption in llm node!
    return registry


def run_llm_test(
    model_provider: LLMModelProvider,
    model_name: str,
    max_tokens: int = 100,
    output_type: str = "text",
    reasoning_config: Dict[str, Any] = None,
    user_prompt: str = "What is 2+2? Answer in one word.",
    **kwargs
) -> Dict[str, Any]:
    """
    Run a test with the specified LLM configuration.
    
    Args:
        model_provider: The LLM provider to use
        model_name: The model name to use
        output_type: Type of output ("text" or "structured")
        reasoning_config: Optional reasoning configuration
        user_prompt: The prompt to send to the LLM
        
    Returns:
        Dict[str, Any]: The test results
    """
    # import ipdb; ipdb.set_trace()
    # Setup registry
    registry = setup_registry()
    
    # Create graph schema
    graph_schema = create_basic_llm_graph(
        model_provider=model_provider,
        model_name=model_name,
        output_type=output_type,
        max_tokens=max_tokens,
        reasoning_config=reasoning_config,
        **kwargs
    )
    
    # Create graph builder
    builder = GraphBuilder(registry)
    
    # Build graph entities
    graph_entities = builder.build_graph_entities(graph_schema)
    
    # Configure runtime
    runtime_config = graph_entities["runtime_config"]
    runtime_config["thread_id"] = f"llm_test_{model_provider}_{model_name}"
    runtime_config["use_checkpointing"] = True
    
    # Create runtime adapter
    adapter = LangGraphRuntimeAdapter()
    
    # Build graph
    graph = adapter.build_graph(graph_entities)
    
    # Execute graph
    result = adapter.execute_graph(
        graph=graph,
        input_data={"user_prompt": user_prompt},
        config=runtime_config,
        output_node_id=graph_entities["output_node_id"]
    )
    
    return result


class TestBasicLLMWorkflow(unittest.TestCase):
    """Test basic LLM node functionality with different configurations."""
    
    def test_anthropic_text_output(self):
        """Test Anthropic Claude 3.7 Sonnet with text output."""
        result = run_llm_test(
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
            output_type="text"
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], str)
        self.assertGreater(len(result["content"]), 0)
    
    def test_anthropic_text_output_non_reasoning_model(self):
        """Test Anthropic Claude 3.5 Sonnet with text output."""
        result = run_llm_test(
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_5_SONNET.value,
            output_type="text"
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], str)
        self.assertGreater(len(result["content"]), 0)

    def test_anthropic_structured_output_non_reasoning_model(self):
        """Test Anthropic Claude 3.5 Sonnet with structured output."""
        result = run_llm_test(
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_5_SONNET.value,
            output_type="structured",
            # reasoning_config={
            #     "reasoning_tokens_budget": 1024  # Claude 3.7 supports reasoning tokens budget
            # }
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("content", result["structured_output"])
    
    def test_anthropic_structured_output_with_schema_from_registry_and_defined_dynamic_fields_non_reasoning_model(self):
        """Test Anthropic Claude 3.5 Sonnet with structured output."""
        result = run_llm_test(
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_5_SONNET.value,
            output_type="structured",
            schema_from_registry={
                "schema_name": "TTestSchema",
            },
            # reasoning_config={
            #     "reasoning_tokens_budget": 1024  # Claude 3.7 supports reasoning tokens budget
            # }
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("content", result["structured_output"])
    
    def test_anthropic_structured_output_with_schema_from_registry_non_reasoning_model(self):
        """Test Anthropic Claude 3.5 Sonnet with structured output."""
        result = run_llm_test(
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_5_SONNET.value,
            output_type="structured",
            schema_from_registry={
                "schema_name": "TTestSchema",
            },
            fields=None,
            # reasoning_config={
            #     "reasoning_tokens_budget": 1024  # Claude 3.7 supports reasoning tokens budget
            # }
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("int_value", result["structured_output"])
        
    def test_anthropic_structured_output(self):
        """Test Anthropic Claude 3.7 Sonnet with structured output and reasoning."""
        result = run_llm_test(
            model_provider=LLMModelProvider.ANTHROPIC,
            model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
            output_type="structured",
            reasoning_config={
                "reasoning_tokens_budget": 1024  # Claude 3.7 supports reasoning tokens budget
            }
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("content", result["structured_output"])
        
    def test_openai_text_output_reasoning_model(self):
        """Test OpenAI O3 Mini with text output and reasoning (thinking model)."""
        result = run_llm_test(
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.O3_MINI.value,
            output_type="text",
            reasoning_config={
                "reasoning_effort_class": "low"  # O3 Mini supports reasoning effort class
            }
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], str)
        self.assertGreater(len(result["content"]), 0)
        
    def test_openai_structured_output_reasoning_model(self):
        """Test OpenAI O1 with structured output and reasoning (thinking model)."""
        result = run_llm_test(
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.O1.value,
            output_type="structured",
            reasoning_config={
                "reasoning_effort_class": "low"  # O1 supports reasoning effort class
            },
            max_tokens=1000
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("content", result["structured_output"])
        
    def test_openai_text_output_non_reasoning_model(self):
        """Test OpenAI GPT-4o-mini with text output (non-thinking model)."""
        result = run_llm_test(
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.GPT_4_5.value,
            output_type="text"
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], str)
        self.assertGreater(len(result["content"]), 0)
        
    def test_openai_structured_output_non_reasoning_model(self):
        """Test OpenAI GPT-4o with structured output (non-thinking model)."""
        result = run_llm_test(
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.GPT_4o.value,
            output_type="structured"
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("content", result["structured_output"])
        
    def test_gemini_pro_exp_text_reasoning(self):
        """Test Gemini 2.5 Pro Exp with text output and reasoning (thinking model).
        
        This test verifies that Gemini 2.5 Pro Exp can generate text responses with
        reasoning capabilities enabled. The model supports advanced thinking and
        reasoning features.
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.GEMINI,
            model_name=GeminiModels.GEMINI_2_5_PRO_EXP.value,
            output_type="text",
            # reasoning_config={
            #     "reasoning_effort_class": "low"  # Pro Exp supports reasoning with effort class
            # }
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], str)
        self.assertGreater(len(result["content"]), 0)
    
    def test_gemini_pro_exp_structured_reasoning(self):
        """Test Gemini 2.5 Pro Exp with structured output and reasoning (thinking model).
        
        This test verifies that Gemini 2.5 Pro Exp can generate structured outputs
        with reasoning capabilities enabled. The model supports advanced thinking and
        multimodal understanding with structured response formats.
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.GEMINI,
            model_name=GeminiModels.GEMINI_2_5_PRO_EXP.value,
            output_type="structured",
            # reasoning_config={
            #     "reasoning_effort_class": "low"  # Pro Exp supports reasoning with effort class
            # }
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("content", result["structured_output"])
    
    def test_gemini_flash_text(self):
        """Test Gemini 2.0 Flash with text output (non-thinking model).
        
        This test verifies that Gemini 2.0 Flash can generate text responses without
        explicit reasoning capabilities. The model is optimized for speed and
        real-time streaming.
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.GEMINI,
            model_name=GeminiModels.GEMINI_2_0_FLASH.value,
            output_type="text"
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], str)
        self.assertGreater(len(result["content"]), 0)
    
    def test_gemini_flash_structured(self):
        """Test Gemini 2.0 Flash with structured output (non-thinking model).
        
        This test verifies that Gemini 2.0 Flash can generate structured outputs
        without explicit reasoning capabilities. The model supports tool use and
        structured response formats.
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.GEMINI,
            model_name=GeminiModels.GEMINI_2_0_FLASH.value,
            output_type="structured"
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("content", result["structured_output"])
    
    def test_fireworks_text_with_reasoning(self):
        """Test Fireworks DeepSeek R1 Fast with text output and reasoning.
        
        This test verifies that Fireworks DeepSeek R1 Fast can generate text responses
        with reasoning capabilities. The model only supports reasoning mode and
        configurable reasoning effort.
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.FIREWORKS,
            model_name=FireworksModels.DEEPSEEK_R1_FAST.value,
            output_type="text",
            reasoning_config={
                "reasoning_effort_class": "low"  # Supports reasoning effort class
            },
            max_tokens=300,
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], list)
        self.assertGreater(len(result["content"]), 0)
    
    def test_fireworks_basic_text_with_reasoning_number(self):
        """Test Fireworks DeepSeek R1 Basic with text output and reasoning number.
        
        This test verifies that Fireworks DeepSeek R1 Basic can generate text responses
        with reasoning capabilities using a numeric reasoning effort value instead of
        a class. The model supports a reasoning effort range of (0, 20000).
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.FIREWORKS,
            model_name=FireworksModels.DEEPSEEK_R1_FAST.value,
            output_type="text",
            reasoning_config={
                "reasoning_effort_number": 50  # Within the allowed range (0, 20000)
            }
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], list)
        self.assertGreater(len(result["content"]), 0)
    
    def test_fireworks_basic_structured_with_reasoning_number(self):
        """Test Fireworks DeepSeek R1 Basic with structured output and reasoning number.
        
        This test verifies that Fireworks DeepSeek R1 Basic can generate text responses
        with reasoning capabilities using a numeric reasoning effort value instead of
        a class. The model supports a reasoning effort range of (0, 20000).
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.FIREWORKS,
            model_name=FireworksModels.DEEPSEEK_R1_FAST.value,
            output_type="structured",
            reasoning_config={
                "reasoning_effort_class": "low",  # Within the allowed range (0, 20000)
            },
            max_tokens=1000,
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], list)
        self.assertGreater(len(result["content"]), 0)
    
    def test_aws_bedrock_text_with_reasoning(self):
        """Test AWS Bedrock DeepSeek R1 with text output and reasoning.
        
        This test verifies that AWS Bedrock DeepSeek R1 can generate text responses
        with reasoning capabilities. The model only supports reasoning mode and
        does not support structured output.
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.AWS_BEDROCK,
            model_name=AWSBedrockModels.DEEPSEEK_R1.value,
            output_type="text",
            # reasoning_config={
            #     "reasoning_effort_class": "low"  # Supports reasoning effort class
            # }
            max_tokens=1000,
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], list)
        self.assertGreater(len(result["content"]), 0)
    
    def test_perplexity_text_output_reasoning_model(self):
        """Test Perplexity Sonar Reasoning with text output and web search.
        
        This test verifies that Perplexity Sonar Reasoning can generate text responses
        with reasoning capabilities and web search integration. The model supports
        real-time search with citation support.
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.PERPLEXITY,
            model_name=PerplexityModels.SONAR_REASONING.value,
            output_type="text",
            web_search_options={
                "search_recency_filter": "year",
                "search_context_size": "low",
                # search_domain_filter: ["site.com"]
                # user_location: {...}  # OPENAI!
            },
            # # TEST! NOT SUPPORTED??
            # reasoning_config={
            #     # "reasoning_effort_class": "low",  # '<think>\nAlright, let\'s tackle this query. The user is asking, "What is the capital of France?" I need to find the correct answer from the provided search results. Let\'s go through each result to gather the necessary information.\n\nFirst, looking at search result [1], it clearly states, "Paris is the capital of France." That\'s a direct answer. Then, in [2], the Wikipedia page lists Paris as the current capital since 1944. The detailed chronology there might be useful for understanding historical capitals, but the key point is that Paris is the current one. \n\nSearch result [3] is the Wikipedia page for Paris itself, which in its opening lines states, "Paris is the capital and largest city of France." That\'s another confirmation. The population figures here are from 2025, which shows the city\'s current status.\n\nBritannica in [4] also confirms Paris as the capital and provides more context about its location along the Seine River. Result [5] from the Council of Europe again mentions Paris as the capital and most populous city. \n\nResult [6] lists France\'s capital as Paris, aligning with all others. The travel guide in [7] emphatically answers the question with Paris and discusses its history briefly. Finally, [8] in the video transcript also states Paris as the capital, adding cultural context.\n\nThere\'s consistent agreement across all sources that Paris is the capital. Some results mention historical changes, like brief periods in Versailles, Bordeaux, or Vichy during wars, but the primary and enduring capital is Paris. The only exception noted is during WWII when Vichy was a temporary capital, but Paris resumed its status post-liberation in 1944.\n\nI need to present this information concisely, highlighting that Paris is the capital, note its prominence, and mention any temporary exceptions without complicating the answer. Citations should be checked to ensure accuracy. All sources [1], [2], [3], [4], [5], [6], [7], [8] confirm Paris, so they should be cited appropriately.\n</think>\n\n**Paris** is the capital of France, as confirmed by multiple authoritative sources[1][2][3][4][5][6][7][8]. It has held this status since 1944, when it was liberated after a brief period of German occupation during WWII (1940-1944), when Vichy briefly served as'
            #     "reasoning_effort_number": 50,
            # },
            user_prompt="What is the capital of France? Answer briefly.",
            max_tokens=500,
        )
        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["content"], (list, str))
        self.assertGreater(len(result["content"]), 0)
        
    def test_perplexity_structured_output_reasoning_model(self):
        """Test Perplexity Sonar Reasoning Pro with structured output and web search.
        
        This test verifies that Perplexity Sonar Reasoning Pro can generate structured responses
        with reasoning capabilities and web search integration. The model supports
        real-time search with citation support and domain filtering.
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.PERPLEXITY,
            model_name=PerplexityModels.SONAR_REASONING_PRO.value,
            output_type="structured",
            web_search_options={
                "search_recency_filter": "month",
                "search_context_size": "medium",
                "search_domain_filter": ["arxiv.org", "openai.com"]
            },
            user_prompt="What are the latest developments in AI safety research? Answer briefly top highlights.",
            fields={
                "summary": DynamicSchemaFieldConfig(type="str", required=True, description="Content of the response"),
                "key_findings": DynamicSchemaFieldConfig(type="str", required=True, description="List of key findings from the search"),
                "citations": DynamicSchemaFieldConfig(type="str", required=True, description="List of citations from the search results")
            },
            max_tokens=1000
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("summary", result["structured_output"])
        self.assertIn("key_findings", result["structured_output"])
        self.assertIn("citations", result["structured_output"])
        
    def test_perplexity_text_output_non_reasoning_model(self):
        """Test Perplexity Sonar Pro with text output and web search.
        
        This test verifies that Perplexity Sonar Pro can generate text responses
        with web search integration. The model supports real-time search with
        citation support but does not have reasoning capabilities.
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.PERPLEXITY,
            model_name=PerplexityModels.SONAR_PRO.value,
            output_type="text",
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
        
    def test_perplexity_structured_output_non_reasoning_model(self):
        """Test Perplexity Sonar with structured output and web search.
        
        This test verifies that Perplexity Sonar can generate structured responses
        with web search integration. The model supports real-time search with
        citation support but does not have reasoning capabilities.
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.PERPLEXITY,
            model_name=PerplexityModels.SONAR.value,
            output_type="structured",
            web_search_options={
                "search_recency_filter": "year",
                "search_context_size": "low"
            },
            user_prompt="What are the emerging trends in renewable energy? Answer briefly top highlights.",
            fields={
                "summary": DynamicSchemaFieldConfig(type="str", required=True, description="Content of the response"),
                "trends": DynamicSchemaFieldConfig(type="str", required=True, description="List of emerging trends in renewable energy"),
                "sources": DynamicSchemaFieldConfig(type="str", required=True, description="List of sources from the search results")
            },
            max_tokens=500
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("summary", result["structured_output"])
        self.assertIn("trends", result["structured_output"])
        self.assertIn("sources", result["structured_output"])
    
    def test_openai_text_output_with_web_search(self):
        """Test OpenAI GPT-4o Search Preview with text output and web search.
        
        This test verifies that OpenAI GPT-4o Search Preview can generate text responses
        with web search integration. The model supports real-time search with
        citation support and user location awareness.
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.GPT_4O_SEARCH_PREVIEW.value,
            output_type="text",
            web_search_options={
                "search_context_size": "medium",
                "user_location": {
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
        
    def test_openai_structured_output_with_web_search(self):
        """Test OpenAI GPT-4o Mini Search Preview with structured output and web search.
        
        This test verifies that OpenAI GPT-4o Mini Search Preview can generate structured responses
        with web search integration. The model supports real-time search with
        citation support and user location awareness.
        """
        result = run_llm_test(
            model_provider=LLMModelProvider.OPENAI,
            model_name=OpenAIModels.GPT_4O_MINI_SEARCH_PREVIEW.value,
            output_type="structured",
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
            user_prompt="What is the current state of electric vehicle adoption?",
            fields={
                "summary": DynamicSchemaFieldConfig(type="str", required=True, description="Content of the response"),
                "key_statistics": DynamicSchemaFieldConfig(type="str", required=True, description="Important statistics about EV adoption"),
                "regional_differences": DynamicSchemaFieldConfig(type="str", required=True, description="How adoption varies by region"),
                "citations": DynamicSchemaFieldConfig(type="str", required=True, description="Sources of information")
            },
            max_tokens=1000
        )
        self.assertIsInstance(result, dict)
        self.assertIn("structured_output", result)
        self.assertIn("metadata", result)
        self.assertIsInstance(result["structured_output"], dict)
        self.assertIn("summary", result["structured_output"])
        self.assertIn("key_statistics", result["structured_output"])
        self.assertIn("regional_differences", result["structured_output"])
        self.assertIn("citations", result["structured_output"])


if __name__ == "__main__":
    unittest.main() 

    # from langchain.chat_models import init_chat_model
    # model = init_chat_model("gemini-2.5-pro-exp-03-25", model_provider="google_genai")
    # response = model.invoke("Hello, world!")
    # """
    # AIMessage(content='Hello there! "Hello, world!" - the classic greeting. 😊\n\nHow can I help you today?', additional_kwargs={}, response_metadata={'prompt_feedback': {'block_reason': 0, 'safety_ratings': []}, 'finish_reason': 'STOP', 'model_name': 'gemini-2.5-pro-exp-03-25', 'safety_ratings': []}, id='run-c91059d9-3e46-4dda-9d7c-8a3efea60315-0', usage_metadata={'input_tokens': 5, 'output_tokens': 22, 'total_tokens': 27, 'input_token_details': {'cache_read': 0}})
    # """
    # print(response.content)
    # import ipdb; ipdb.set_trace()


    # from google import genai

    # client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    # prompt = "Explain the concept of Occam's Razor and provide a simple, everyday example."
    # response = client.models.generate_content(
    #     model="gemini-2.5-pro-exp-03-25",  # or gemini-2.0-flash-thinking-exp
    #     contents=prompt
    # )

    # print(response.text)
    # import ipdb; ipdb.set_trace()
    # x = ConstructDynamicSchema(
    #     schema_name="TestSchema",
    #     schema_description="Test schema",
    #     fields={
    #         # try Any or Dict field!
    #         "content": DynamicSchemaFieldConfig(type="str", required=True, description="Content of the response"),
    #         # "metadata": DynamicSchemaFieldConfig(type="dict", required=True, description="Metadata of the response"),
    #         "metadata": DynamicSchemaFieldConfig(type="dict",  required=True, description="Metadata of the response", keys_type="str", values_type="str"),
    #     }
    # )
    # y = x.build_schema()
    # print(json.dumps(y.model_json_schema(), indent=2))
