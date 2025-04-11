"""
LLM Node using LangChain.

This module provides a LangChain-based LLM node implementation that supports multiple
model providers (OpenAI, Anthropic, Gemini) with structured output and tool calling.
"""
from copy import copy
import json
import os
from enum import Enum
import re
import time
from typing import Any, ClassVar, Dict, List, Optional, Type, Union, Literal

from pydantic import Field, field_validator
from pydantic import ConfigDict

from anthropic import Anthropic
from openai import OpenAI

from langchain_core.messages import (
    AIMessage, 
    HumanMessage, 
    SystemMessage, 
    ToolMessage,
    AnyMessage,
    # BaseMessage
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.tools import BaseTool
from langchain_core.runnables import Runnable
from langchain.chat_models import init_chat_model
from langchain_community.chat_models import ChatPerplexity


from kiwi_app.workflow_app.constants import LaunchStatus
from workflow_service.config.settings import settings
from workflow_service.registry.registry import DBRegistry
from workflow_service.registry.nodes.core.base import BaseNode, BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import ConstructDynamicSchema, DynamicSchema
from workflow_service.registry.nodes.llm.config import LLMModelProvider, PROVIDER_MODEL_MAP, AnthropicModels, AWS_REGION, ModelMetadata, THINKING_MESSAGE_TYPES, REDACED_THINKING_MESSAGE_TYPES, GEMINI_PARAM_KEY_OVERRIDES, PARAM_KEY_OVERRIDES
from workflow_service.registry.schemas.base import create_dynamic_schema_with_fields





# print(BaseMessage("test", type="test"))
# print(BaseMessage({"content": "test", "type": "test"}))
# raise Exception("stop")


class MessageType(str, Enum):
    """Message types."""
    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"
    TOOL = "tool"


###########################
###### Input Schema ######
###########################

class LLMNodeInputSchema(BaseSchema):
    """Input schema for the LLM node."""
    # Messages input
    messages_history: List[AnyMessage] = Field(
        default_factory=list, 
        description="List of messages history in the conversation. Each message must have 'type' and 'content' keys."
    )
    user_prompt: Optional[str] = Field(
        None, 
        description="Simple text user prompt (alternative to messages). Will be converted to a HumanMessage."
    )
    system_prompt: Optional[str] = Field(
        None, 
        description="System message to prepend to the conversation if using prompt."
    )
    tool_outputs: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Dict of tool outputs to append to the conversation. Each tool output must have 'tool_name' and 'output' keys."
    )
###########################


###########################
###### Output Schema ######
###########################

class LLMMetadata(BaseSchema):
    """Metadata about the LLM response including token usage."""
    model_name: str = Field(description="Model name used for generation")
    response_metadata: Optional[Dict[str, Any]] = Field(None, description="Response metadata")
    token_usage: Optional[Dict[str, Union[int, Dict[str, Any]]]] = Field(None, description="Token usage statistics. Input, Output, Thinking, Cached tokens.")
    # thinking_tokens: Optional[int] = Field(None, description="Number of thinking tokens (for models that support it)")
    finish_reason: Optional[str] = Field(None, description="Reason for finish (e.g., 'stop', 'length', 'tool_calls')")
    latency: Optional[float] = Field(None, description="Latency in seconds")
    cached: Optional[bool] = Field(default=False, description="Whether the response was cached")


class ToolCall(BaseSchema):
    """Represents a tool call made by the model."""
    tool_name: str = Field(description="Name of the tool called")
    tool_input: Dict[str, Any] = Field(description="Input provided to the tool")
    tool_id: Optional[str] = Field(None, description="ID of the tool call (used by some providers)")


class Citation(BaseSchema):
    """Represents a citation from web search results."""
    url: Optional[str] = Field(None, description="URL of the source")
    title: Optional[str] = Field(None, description="Title of the source")
    snippet: Optional[str] = Field(None, description="Relevant snippet from the source")
    timestamp: Optional[str] = Field(None, description="Timestamp of the source")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata about the source")


class WebSearchResult(BaseSchema):
    """Represents a web search result."""
    # query: str = Field(description="The search query used")
    # answer: str = Field(description="The answer generated from search results")
    citations: Optional[List[Citation]] = Field(default_factory=list, description="Citations used in the answer")
    # related_questions: Optional[List[str]] = Field(None, description="Related questions generated")
    search_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional search metadata")


class LLMNodeOutputSchema(BaseSchema):
    """Output schema for the LLM node."""
    # content: str = Field(description="Text content of the response")
    # https://python.langchain.com/docs/how_to/response_metadata/
    metadata: LLMMetadata = Field(description="Metadata about the response")
    
    current_messages: List[AnyMessage] = Field(description="Current messages including any user prompts / tool outputs and the new response")
    # Content type copied from langgraph message content annotation!
    content: Optional[Union[str, List[Union[str, Dict[str, Any]]]]] = Field(None, description="Raw response content from the provider")
    # For structured output
    structured_output: Optional[Dict[str, Any]] = Field(
        None, 
        description="Structured output parsed from the response (if output_format was structured)"
    )
    # For tool calling
    tool_calls: Optional[List[ToolCall]] = Field(
        None,
        description="Tool calls made by the model (if any)"
    )
    web_search_result: Optional[WebSearchResult] = Field(
        None,
        description="Web search result (if web search was enabled)"
    )
###########################


###########################
###### Config Schema ######
###########################


class ModelSpec(BaseSchema):
    """Combined model specification with provider and model name."""
    provider: LLMModelProvider = Field(
        default=LLMModelProvider.ANTHROPIC,
        description="The model provider to use"
    )
    model: str = Field(  # str  OR   OpenAIModels | AnthropicModels
        default=AnthropicModels.CLAUDE_3_7_SONNET.value,
        description="The model name to use"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            # "examples": [
            #     {"provider": "openai", "model": "gpt-4-turbo"},
            #     {"provider": "anthropic", "model": "claude-3-5-sonnet-20240620"},
            #     {"provider": "google_genai", "model": "gemini-2.0-flash"}
            # ],
            "allOf": [
                {
                    "if": {
                        "properties": {"provider": {"const": provider.value}}
                    },
                    "then": {
                        "properties": {
                            "model": {
                                "enum": [e.value for e in model_enum]
                            }
                        }
                    }
                }
                for provider, model_enum in PROVIDER_MODEL_MAP.items()
            ]
        }
    )
    
    @field_validator('model')
    def validate_model_for_provider(cls, v, info):
        """Validate that the model is appropriate for the selected provider."""
        provider = info.data.get('provider')
        
        # If no provider specified, we can't validate
        if not provider:
            return v
        
        # Get the model enum class for the specified provider
        if provider in PROVIDER_MODEL_MAP:
            model_enum = PROVIDER_MODEL_MAP[provider]
            valid_models = [e.value for e in model_enum]
            
            # Define prefix checks for each provider to allow custom models
            # prefix_checks = {
            #     ModelProvider.OPENAI: "gpt-",
            #     ModelProvider.ANTHROPIC: "claude-",
            #     ModelProvider.GEMINI: "gemini-",
            #     ModelProvider.FIREWORKS: "accounts/fireworks/models/"
            # }
            
            # Check if model is in the enum values or starts with the appropriate prefix
            # prefix = prefix_checks.get(provider, "")
            if v not in valid_models:  #  and not (prefix and v.startswith(prefix)):
                raise ValueError(f"Model '{v}' is not a valid {provider.value} model")
                
        return v


class SchemaFromRegistryConfig(BaseSchema):
    """Schema configuration."""
    schema_name: str = Field(description="Schema Unique name")
    schema_version: Optional[str] = Field(None, description="Schema version")


class LLMStructuredOutputSchema(BaseSchema):
    """Output format types.
    
    NOTE: Some providers do not support strict structured output or JSON mode and use / force tool calling to fill the schema instead.
    You may want to add additional instructions to the prompt to ensure the tool is called, including reinforcing the output schema format expected.

    For eg, Anthropic structured output relies on forced tool calling, which is not supported when `thinking` is enabled. Sometimes, the tool calls are not generated leading to parser errors. 
    Consider disabling `thinking` or adjust your prompt to ensure the tool is called.
    """
    schema_from_registry: Optional[SchemaFromRegistryConfig] = Field(None, description="Output schema from registry")
    # NOTE: if both are specified, fields from dynamic schema spec will overwrite fields from the schema from registry if same field name, 
    #     otherwise all schema from registry fields will be added to the dynamic schema, aside from new fields from the spec!
    dynamic_schema_spec: Optional[ConstructDynamicSchema] = Field(None, description="Dynamic Schema specification for the output")

    def is_output_str(self):
        return self.schema_from_registry is None and self.dynamic_schema_spec is None

    def get_schema(self, registry: DBRegistry = None, built_schema_name = None):
        """
        Get schema config from registry

        NOTE: dynamic schema spec ovewrite fields from registry schema
        """
        schema = None
        if self.schema_from_registry:
            assert registry is not None, "Registry must be provided if schema_from_registry is used"
            schema = registry.get_schema(self.schema_from_registry.schema_name, self.schema_from_registry.schema_version)
        if self.dynamic_schema_spec:
            dynamic_schema = self.dynamic_schema_spec.build_schema(schema_name=built_schema_name)
            if schema is not None:
                original_schema_fields = {k:None for k in schema.model_fields.keys()}
                for field_name, field_def in dynamic_schema.model_fields.items():
                    original_schema_fields[field_name] = (field_def.annotation, field_def)
                schema = create_dynamic_schema_with_fields(schema, fields=original_schema_fields)
            else:
                schema = dynamic_schema
        # else:
        #     raise ValueError("No schema config provided")
        return schema


class ToolConfig(BaseSchema):
    """Configuration for a tool. (Pulled from ToolRegistry)
    NOTE: this tool is configured in the tool caller node and it has the config default / set by user. 
    This config in LLM node only receives input_overwrites so that it can determine which parts of the input schema go into the tool call.
    IMPORTANT NOTE: A tool node should have a verbose, descriptive input schema btw!
    """
    tool_name: str = Field(description="Tool name")
    version: Optional[str] = Field(None, description="Tool version")
    input_overwrites: Optional[Dict[str, Any]] = Field(None, description="Input overwrites for the tool. These fields are not passed to the LLM and are not filled!")
    additional_tool_config_fields: Optional[ConstructDynamicSchema] = Field(None, description="Additional fields for the tool. They could contain additional config fields for the tool not part of standard input schema.")


class LLMModelConfig(BaseSchema):
    """Configuration schema for the LLM model."""
    model_spec: ModelSpec = Field(
        default=ModelSpec(),
        description="Model specification to use"
    )
    max_tokens: Optional[int] = Field(
        None,
        description="Maximum number of tokens to generate"
    )
    temperature: float = Field(
        default=0.0,
        description="""Temperature for sampling (0.0 = deterministic, 1.0 = creative). 
        NOTE: For thinking, its recommended to use a higher temperature, for eg, Anthropic only accepts 1.0 temperature when thinking is enabled!
        NOTE: OpenAI Web Search models don't seem to support temperature!
        """
    )
    force_temperature_setting_when_thinking: Optional[bool] = Field(
        False,
        description="Use the exact temperature value specified in the `temperature` field, even when thinking mode is enabled. Note: Most models work better with higher temperatures (like 1.0) when thinking is enabled. For example, Anthropic models require a temperature of 1.0 when thinking mode is on."
    )
    
    # reasoning config
    reasoning_effort_class: Optional[str] = Field(
        None,
        description="Class of reasoning effort to use"
    )
    reasoning_effort_number: Optional[int] = Field(
        None,
        description="Number level of reasoning effort to use"
    )
    reasoning_tokens_budget: Optional[int] = Field(
        None,
        description="Maximum number of tokens available for reasoning"
    )

    
    kwargs: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional keyword arguments to pass to the model"
    )
    # top_p: Optional[float] = Field(
    #     None,
    #     description="Top-p sampling parameter"
    # )


class ThinkingTokensInPrompt(Enum):
    """Enum for thinking tokens in prompt."""
    ALL = "all"
    LATEST = "latest_message"
    NONE = "none"


class ToolCallingConfig(BaseSchema):
    """Configuration for tool calling."""
    enable_tool_calling: bool = Field(
        default=False,
        description="Whether to enable tool calling"
    )
    tool_choice: Optional[str] = Field(
        None,
        description="Mode of tool calling"
    )
    parallel_tool_calls: bool = Field(
        default=True,
        description="Whether to enable parallel tool calls"
    )

class WebSearchConfig(BaseSchema):
    """Extends base LLM config with web search parameters."""
    search_recency_filter: Optional[Literal["day", "week", "month", "year"]] = Field(None, description="""Recency filter for search.
    Options: 'day', 'week', 'month', 'year'
    """)
    search_domain_filter: Optional[List[str]] = Field(None, description="""List of site domains to filter search results.
    """)
    # return_images: bool = Field(False)
    # return_related_questions: bool = Field(True)
    # max_results: Optional[int] = Field(None)
    search_context_size: Optional[Literal["low", "medium", "high"]] = Field(
        default="medium", 
        description="Controls the amount of search context provided to the model. Options: 'low', 'medium', 'high'"
    )
    user_location: Optional[Dict[str, Any]] = Field(None, description="""User location for search context.
    NOTE: This is not used for Perplexity, but is used for other providers like OpenAI.
    
    Example:
    user_location: {
            type: "approximate",
        approximate: {
            country: "GB",
            city: "London",
            region: "London",
        },
    }                                                
    """)

class LLMNodeConfigSchema(BaseSchema):
    """Configuration schema for the LLM node."""
    # Model Config
    llm_config: Optional[LLMModelConfig] = Field(
        default=LLMModelConfig(),
        description="LLM configuration"
    )
    default_system_prompt: Optional[str] = Field(
        None,
        description="Default system prompt to use if no system prompt is provided in the input"
    )
    thinking_tokens_in_prompt: Optional[ThinkingTokensInPrompt] = Field(
        default=ThinkingTokensInPrompt.ALL,
        description="Whether to include thinking tokens in the prompt"
    )
    api_key_override: Optional[Dict[str, str]] = Field(
        None,
        description="Override API keys for specific providers"
    )
    cache_responses: bool = Field(
        default=True,
        description="Whether to cache responses"
    )

    # Output configuration
    output_schema: LLMStructuredOutputSchema = Field(
        default_factory=LLMStructuredOutputSchema,
        description="JSON schema for structured output (required if output_format is 'structured')"
    )
    stream: bool = Field(
        default=True,
        description="Whether to stream the response"
    )
    
    # Tool calling configuration
    tool_calling_config: ToolCallingConfig = Field(
        default_factory=ToolCallingConfig,
        description="Configuration for tool calling"
    )
    tools: Optional[List[ToolConfig]] = Field(
        None,
        description="List of tools to make available to the model"
    )

    # Web Search Options
    web_search_options: Optional[WebSearchConfig] = Field(
        None,
        description="Configuration for web search"
    )
    
    @field_validator('tools')
    def validate_tools(cls, v, info):
        """Validate that tools are provided if tool calling is enabled."""
        if info.data.get('enable_tool_calling', False) and not v:
            raise ValueError("Tools must be provided when tool calling is enabled")
        return v

###########################


class LLMNode(BaseNode[LLMNodeInputSchema, LLMNodeOutputSchema, LLMNodeConfigSchema]):
    """
    LLM Node that processes requests using LangChain.
    
    This node provides a flexible interface to various LLM providers through LangChain,
    supporting different input formats, structured outputs, and tool calling capabilities.
    
    Additional options that could be implemented:
    - Request timeouts and retry logic
    - Dynamic model selection based on input complexity
    - Batched requests for processing multiple prompts
    - Custom prompt templates
    - Fallback models if primary model fails
    - Prompt optimization/compression
    - Response filtering/moderation
    - Caching with TTL settings
    - Cost tracking and budget limits
    - Response validators
    - Chained LLM calls (use output of one as input to another)
    - Parallel model calls with voting/ensemble
    - Context window management
    - Semantic caching for similar queries
    """
    node_name: ClassVar[str] = "llm"
    node_version: ClassVar[str] = "1.0.0"
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[Type[LLMNodeInputSchema]] = LLMNodeInputSchema
    output_schema_cls: ClassVar[Type[LLMNodeOutputSchema]] = LLMNodeOutputSchema
    config_schema_cls: ClassVar[Type[LLMNodeConfigSchema]] = LLMNodeConfigSchema
    
    # instance config
    config: LLMNodeConfigSchema

    def process(self, input_data: LLMNodeInputSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> LLMNodeOutputSchema:
        """
        Process LLM request using node config (self.config) and runtime parameters.
        
        Key changes:
        - All node configuration comes from self.config
        - Runtime config (passed parameter) used for execution context
        - Registry accessed through kwargs
        """
        external_config = config.get("configurable", {}).get("external", {})
        # Initialize model using node config
        try:
            model_metadata: ModelMetadata
            chat_model, model_metadata = self._init_model()
        except Exception as e:
            raise ValueError(f"Model initialization failed: {str(e)}, \n{e.__traceback__}") from e

        # Prepare messages using node config
        messages_for_model, current_messages = self._prepare_messages(input_data, model_metadata)

        registry: DBRegistry = external_config.get('registry')
        
        # Configure structured output if specified in node config
        if self.config.output_schema and (not self.config.output_schema.is_output_str()):
            assert model_metadata.structured_output, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support structured output!"
            chat_model = self._apply_structured_output(chat_model, registry, model_metadata)

        # Bind tools if configured in node config
        if self.config.tool_calling_config.enable_tool_calling and self.config.tools:
            assert model_metadata.tool_use, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support tool use!"
            chat_model = self._bind_tools(chat_model, model_metadata, registry)

        # Execute model with provider-specific handling
        try:
            start_time = time.time()
            response = self._execute_model(chat_model, messages_for_model, model_metadata)
            # NOTE: 
            # if (not self.config.output_schema.is_output_str()): 
            #     # response is dict with keys {"raw": Any, "parsed": Any, "parsing_error": Optional[str]}
            # if (not self.config.output_schema.is_output_str()):
            #     pass
            # import ipdb; ipdb.set_trace()
            latency = time.time() - start_time
        except Exception as e:
            raise RuntimeError(f"Model execution failed: {str(e)}") from e

        # Parse and validate response using node config
        structured_output_schema = self._get_structured_output_schema(registry)
        return self._parse_response(response, input_data.messages_history, current_messages, latency, structured_output_schema, model_metadata)
    
    
    
    def _get_reasoning_params(self, provider: LLMModelProvider, model_name: str, model_metadata: ModelMetadata) -> Dict[str, Any]:
        """Get reasoning parameters for the model."""
        # Handle Reasoning config
        reasoning_kwargs = {}
        any_reasoning_config_provided = self.config.llm_config.reasoning_effort_class or self.config.llm_config.reasoning_effort_number or self.config.llm_config.reasoning_tokens_budget
        if any_reasoning_config_provided:
            assert model_metadata.reasoning, f"Model {provider.value} -> `{model_name}` does not support reasoning but reasoning config was provided!"
        # Check that only one reasoning configuration is provided
        reasoning_configs_provided = [
            self.config.llm_config.reasoning_effort_class is not None,
            self.config.llm_config.reasoning_effort_number is not None,
            self.config.llm_config.reasoning_tokens_budget is not None
        ]
        
        if sum(reasoning_configs_provided) > 1:
            raise ValueError(
                "Only one reasoning configuration should be provided. "
                "Please specify only one of: reasoning_effort_class, reasoning_effort_int, or reasoning_effort_tokens."
            )

        if self.config.llm_config.reasoning_tokens_budget:
            # TODO: AWS Bedrock may also later server Anthropic models, fix this then!
            assert self.config.llm_config.reasoning_tokens_budget is not None and model_metadata.reasoning_tokens_budget, f"Either reasoning tokens budget were not provided for Anthropic model or model {model_name} does not support reasoning!"
            assert self.config.llm_config.reasoning_tokens_budget < model_metadata.output_token_limit, f"Reasoning tokens budget {self.config.llm_config.reasoning_tokens_budget} is greater than the model's {provider.value} -> `{model_name}` output token limit ({model_metadata.output_token_limit})!"
            if model_metadata.reasoning_tokens_budget_min is not None:
                assert self.config.llm_config.reasoning_tokens_budget >= model_metadata.reasoning_tokens_budget_min, f"Reasoning tokens budget {self.config.llm_config.reasoning_tokens_budget} is less than the model's {provider.value} -> `{model_name}` reasoning tokens budget min ({model_metadata.reasoning_tokens_budget_min})!"
            reasoning_kwargs["thinking"] = {"type": "enabled", "budget_tokens": self.config.llm_config.reasoning_tokens_budget}
        elif self.config.llm_config.reasoning_tokens_budget:
            raise ValueError(f"Model {provider.value} -> `{model_name}` does not support reasoning token budget but reasoning config was provided!")
        if self.config.llm_config.reasoning_effort_class:
            assert model_metadata.reasoning_effort_class, f"Model {provider.value} -> `{model_name}` does not support reasoning but reasoning config was provided!"
            reasoning_kwargs["reasoning_effort"] = self.config.llm_config.reasoning_effort_class
            assert self.config.llm_config.reasoning_effort_class in model_metadata.reasoning_effort_class, f"Reasoning effort class {self.config.llm_config.reasoning_effort_class} is not supported for {provider.value} -> `{model_name}`"
        if self.config.llm_config.reasoning_effort_number:
            reasoning_kwargs["reasoning_effort"] = self.config.llm_config.reasoning_effort_number
            assert model_metadata.reasoning_effort_number_range and (model_metadata.reasoning_effort_number_range[0] <= self.config.llm_config.reasoning_effort_number <= model_metadata.reasoning_effort_number_range[1]), f"Reasoning effort number {self.config.llm_config.reasoning_effort_number} is not supported for {provider.value} -> `{model_name}` or its out of supported range {model_metadata.reasoning_effort_number_range}!"
        return reasoning_kwargs
    
    def _init_model(self) -> Any:
        """Initialize model using self.config values."""
        kwargs = self.config.llm_config.kwargs or {}
        
        model_kwargs = {
            "temperature": self.config.llm_config.temperature,
            "max_tokens": self.config.llm_config.max_tokens,
            # "stream": self.config.stream,
            **kwargs
        }

        provider = self.config.llm_config.model_spec.provider
        provider_param_key_overrides = PARAM_KEY_OVERRIDES[provider] if provider in PARAM_KEY_OVERRIDES else {}
        model_name = self.config.llm_config.model_spec.model
        model_metadata: ModelMetadata = PROVIDER_MODEL_MAP[provider](model_name).metadata
        

        assert model_kwargs.get("max_tokens") <= model_metadata.output_token_limit, f"Max tokens ({model_kwargs['max_tokens']}) exceeds the model's {provider.value} -> `{model_name}` output token limit ({model_metadata.output_token_limit})"

        # reasoning kwargs
        reasoning_kwargs = self._get_reasoning_params(provider, model_name, model_metadata)
        model_kwargs.update(reasoning_kwargs)

        model_called_in_reasoning_mode = (not model_metadata.non_reasoning_mode) or (reasoning_kwargs)
        if model_called_in_reasoning_mode:
            model_kwargs["temperature"] = 1.0
            if self.config.llm_config.force_temperature_setting_when_thinking:
                if not provider == LLMModelProvider.ANTHROPIC:
                    model_kwargs["temperature"] = self.config.llm_config.temperature
                # TODO: warn temperature config is overwritten even when forcing since Anthropic doesn't accept temperature less than 1.0 in thinking mode!
        
        if model_metadata.web_search and provider == LLMModelProvider.OPENAI:
            # OPENAI Web Search doesn't seem to suppor temperature!
            del model_kwargs["temperature"]

        if provider == LLMModelProvider.AWS_BEDROCK:
            model_kwargs["aws_secret_access_key"] = settings.AWS_BEDROCK_SECRET_ACCESS_KEY
            model_kwargs["aws_access_key_id"] = settings.AWS_BEDROCK_ACCESS_KEY_ID
            model_kwargs["region_name"] = AWS_REGION 
        
        
        # This was introduced since Gemini's max token param key was different than provided by langchain!
        model_kwargs = {provider_param_key_overrides.get(k, k): v for k, v in model_kwargs.items()}
        # import ipdb; ipdb.set_trace()
        if provider == LLMModelProvider.PERPLEXITY:
            model = ChatPerplexity(model=model_name, **model_kwargs)
        else:
            model = init_chat_model(
                model=model_name,
                model_provider=provider.value,
                **model_kwargs
            )
        
        # import ipdb; ipdb.set_trace()
        return model, model_metadata

    def _prepare_messages(self, input_data: LLMNodeInputSchema, model_metadata: ModelMetadata) -> List[AnyMessage]:
        """Prepare messages using node config's thinking token settings."""
        messages = []
        current_messages = []

        assert input_data.tool_outputs or (input_data.system_prompt or self.config.default_system_prompt) or input_data.user_prompt, "At least one of tool_outputs, system_prompt, or user_prompt must be provided to call the LLM!"
        
        if input_data.messages_history:
            # messages.extend(self._convert_messages(input_data.messages_history))
            # TODO: FIXME: probably don't need to convert past message histories to langchain types??
            messages.extend(input_data.messages_history)
        elif input_data.system_prompt or self.config.default_system_prompt:
            # Don't add system prompt if messages_history is available
            messages.append(SystemMessage(content=input_data.system_prompt or self.config.default_system_prompt))
            current_messages.append(messages[-1])
        
        if input_data.user_prompt:
            messages.append(HumanMessage(content=input_data.user_prompt))
            current_messages.append(messages[-1])
        # TODO: log warning if neither of user prompt or tool output provided!
        
        if input_data.tool_outputs:
            assert model_metadata.tool_use, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support tool use!"
            tool_messages = []
            for i, tool_output in enumerate(input_data.tool_outputs):
                if "content" not in tool_output:
                    raise ValueError(f"Tool output {i} must have a 'content' key! {tool_output}")
                tool_messages.append(
                    ToolMessage(
                        content=tool_output.get("content"),  # NOTE: this can be a str or a list of str / dicts as per langchain!
                        # TODO: has to be in this similar format for eg:
                        # content=[
                        #     {'type': 'text', 'text': '\n\nHello, world! 👋 How can I assist you today?'}, 
                        #     {'type': 'reasoning_content', 'reasoning_content': {
                        #         'text': 'Okay, the user wrote "Hello, world!" That\'s a classic first program in many programming languages. Maybe they\'re just testing the chat or starting out with coding.\n\nI should respond warmly. Let me say hello back and ask how I can assist them today. Keep it friendly and open-ended to encourage them to ask questions or share what they need help with.\n', 
                        #         'signature': ''
                        #     }}
                        # ]
                        tool_call_id=tool_output.get("tool_id", f"tool_output_{i}"), 
                        name=tool_output.get("tool_name", ""),
                        status=tool_output.get("status", "success")
                    )
                )
            messages.extend(tool_messages)
            current_messages.extend(tool_messages)
        # Use node config for thinking message handling
        messages = self._filter_thinking_messages(messages, keep=self.config.thinking_tokens_in_prompt)

      # import ipdb; ipdb.set_trace()

        return messages, current_messages
    
    def _get_structured_output_schema(self, registry: DBRegistry) -> Any:
        """Get structured output schema from node config."""
        if self.config.output_schema:
            return self.config.output_schema.get_schema(registry, built_schema_name=f"{self.__class__.node_name}StructuredOutputSchema")
        return None
    
    def _apply_structured_output(self, model: Any, registry: DBRegistry, model_metadata: ModelMetadata) -> Any:
        """Apply structured output from node config."""
        try:
            output_schema = self._get_structured_output_schema(registry)
            kwargs = {}
            if model_metadata.provider == LLMModelProvider.OPENAI:
                kwargs["strict"] = True
            return model.with_structured_output(
                schema=output_schema,
                method="json_schema",  # json_schema
                include_raw=True,
                **kwargs
            )
        except Exception as e:
            raise ValueError(f"Structured output configuration failed: {str(e)}") from e

    def _bind_tools(self, model: Any, model_metadata: ModelMetadata, registry: DBRegistry) -> Any:
        """Bind tools from node config."""
        assert model_metadata.tool_use, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support tool use!"
        tools = []
        for tool_config in self.config.tools:
            # NOTE: will raise error if node not found or found node is not a tool node!
            tool_node: BaseNode = registry.get_node(tool_config.tool_name, tool_config.version, return_if_tool=True)
            # if not tool_node:
            #     raise ValueError(f"Tool {tool_config.tool_name} not found in registry")

            default_tool_no_params = create_dynamic_schema_with_fields(DynamicSchema,
                fields={}, schema_name=tool_config.tool_name
            )
            default_tool_no_params.__doc__ = tool_node.__doc__
            
            
            additional_fields = tool_config.additional_tool_config_fields
            if additional_fields:
                additional_fields = additional_fields.build_schema(schema_name=tool_config.tool_name)
            
            input_schema = tool_node.input_schema_cls
            if input_schema:
                input_overwrites = tool_config.input_overwrites or {}
                included_fields = {k:None for k,v in input_schema.model_fields.items() if k not in input_overwrites}
                input_schema = create_dynamic_schema_with_fields(input_schema,
                    fields=included_fields, schema_name=tool_config.tool_name
                )
                if additional_fields is not None:
                    additional_fields = {field_name: (field_info.annotation, field_info) for field_name, field_info in additional_fields.model_fields.items()}
                    input_schema = create_dynamic_schema_with_fields(
                        input_schema, fields=included_fields | additional_fields, schema_name=tool_config.tool_name
                    )
            tool_for_binding = input_schema or additional_fields or default_tool_no_params
            tools.append(tool_for_binding)
        
        kwargs = {}
        if self.config.tool_calling_config.tool_choice:
            assert self.config.tool_calling_config.tool_choice in model_metadata.tool_choice, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support tool choice!"
            kwargs["tool_choice"] = self.config.tool_calling_config.tool_choice
        if self.config.tool_calling_config.enable_parallel_tool_calling:
            assert model_metadata.parallel_tool_calling_configurable, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support parallel tool calling!"
            kwargs["parallel_tool_calls"] = self.config.tool_calling_config.enable_parallel_tool_calling

        return model.bind_tools(tools=tools, **kwargs)

    def _execute_model(self, model: Any, messages: List[AnyMessage], model_metadata: ModelMetadata) -> Any:
        """Execute model with provider-specific streaming handling."""
        # if self.config.stream:
        #     return self._handle_streaming(model, messages)
        # NOTE: Langgraph doesn't need the langchain model to explicitly call stream and will stream through the graph even if calling invoke if graph is run in streaming mode
        # https://python.langchain.com/docs/concepts/streaming/#auto-streaming-chat-models
        
        #################################
        # temp_model = init_chat_model("gemini-2.5-pro-exp-03-25", model_provider="google_genai")

        # model_kwargs = {
        #     "temperature": self.config.llm_config.temperature,
        #     "maxOutputTokens": self.config.llm_config.max_tokens,
        # }

        # provider = self.config.llm_config.model_spec.provider
        # model_name = self.config.llm_config.model_spec.model

        # temp_chat_model = init_chat_model(
        #     model=model_name,
        #     model_provider=provider.value,
        #     **model_kwargs
        # )

        # resp = temp_chat_model.invoke(messages)
        #################################


        # response = temp_model.invoke("Hello, world!")
        # # import ipdb; ipdb.set_trace()

        invoke_kwargs = {}
        if hasattr(model_metadata, "web_search") and model_metadata.web_search:
            if self.config.web_search_options is not None:
                # Validate web search capabilities against model metadata
                web_search_options = self.config.web_search_options.model_dump(exclude_none=True)
                
                # Check if model supports specific web search features
                if self.config.web_search_options.search_recency_filter and (not model_metadata.search_recency_filter):
                    raise ValueError(f"Model {model_metadata.model_name} does not support recency filtering for web search, but it was configured")
                    # self.logger.warning(f"Model {model_metadata.model_name} does not support recency filtering, but it was configured")
                
                if self.config.web_search_options.search_domain_filter and (not model_metadata.search_domain_filter):
                    raise ValueError(f"Model {model_metadata.model_name} does not support domain filtering for web search, but it was configured")
                
                if self.config.web_search_options.search_context_size and (not model_metadata.search_context_size):
                    raise ValueError(f"Model {model_metadata.model_name} does not support search context size configuration for web search, but it was configured")
                
                if self.config.web_search_options.user_location and (not model_metadata.user_location):
                    raise ValueError(f"Model {model_metadata.model_name} does not support user location for web search, but it was configured")
                
                # Add validated options to the request
                invoke_kwargs["extra_body"] = {
                    "web_search_options": web_search_options
                }
      # import ipdb; ipdb.set_trace()
        return model.invoke(messages, **invoke_kwargs)
    
    def filter_tool_calls(self, tool_calls: Any, output_schema: Any) -> LLMNodeOutputSchema:
        """Filter tool calls from the response.
        
        Anthropic response example with tool call!
        AIMessage(
        content=[
            {
                'signature': 'ErUBCkYIAhgCIkBgH45kw0udMhB5F6420HYPASaleby/BjavNWaBWxJhMMzT6T7D9GNTcX37vIFYR7S/ZI5Rn8Wn8ff5uK58Cwk1Egwbup9wvTm79CcEXM8aDN62YBormKaT6ZdDHSIwhh7e0aD6/RDW+KfP/dYORB+x3UoEnFub+ups7RcnHteY2wiQDdRhXgNWFW/2JGc7Kh0JoZDPrdF8CVrOkgTLYtn0LesMTBBdy6WfRUIucQ==', 
                'thinking': 'The user wants me to calculate 2+2 and provide a one-word answer. This is a simple arithmetic calculation.\n\n2+2 = 4\n\nThe answer is "four" which is one word as requested. I\'ll use the llmStructuredOutputSchema function to format my response.', 'type': 'thinking'
            }, 
            {
                'id': 'toolu_01SBoc7VfjiaTnqJMX3RJPcg', 
                'input': {
                        'content': 'Four', 'metadata': {'calculation': '2+2=4'}
                        }, 
                'name': 'llmStructuredOutputSchema', 'type': 'tool_use'
            }
        ], 
        additional_kwargs={}, 
        response_metadata={'id': 'msg_01AZaUbf2yX425VGp2s7awx9', 'model': 'claude-3-7-sonnet-20250219', 'stop_reason': 'tool_use', 'stop_sequence': None, 'usage': {'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0, 'input_tokens': 446, 'output_tokens': 155}, 'model_name': 'claude-3-7-sonnet-20250219'}, 
        id='run-9678153b-39c8-4742-b13b-7bc7e9d88308-0', 
        tool_calls=[{'name': 'llmStructuredOutputSchema', 'args': {'content': 'Four', 'metadata': {'calculation': '2+2=4'}}, 'id': 'toolu_01SBoc7VfjiaTnqJMX3RJPcg', 'type': 'tool_call'}], 
        usage_metadata={'input_tokens': 446, 'output_tokens': 155, 'total_tokens': 601, 'input_token_details': {'cache_read': 0, 'cache_creation': 0}})
        """
        if not tool_calls:
            return
        if not self.config.output_schema.is_output_str():
            tool_calls = [t for t in tool_calls if t["name"] != output_schema.__name__]
        return tool_calls
    
    def _parse_response(self, original_response: Any, message_history: List[AnyMessage], current_messages: List[AnyMessage], latency: float, output_schema: Any, model_metadata: ModelMetadata) -> LLMNodeOutputSchema:
        """Parse response using node config values.
        
        https://python.langchain.com/docs/how_to/response_metadata/

        NOTE: reasoning mode with JSON mode in Fireworks:
        https://docs.fireworks.ai/structured-responses/structured-response-formatting#reasoning-model-json-mode
        """
        has_tool_calls = hasattr(original_response, 'tool_calls') and original_response.tool_calls
        if has_tool_calls:
            filtered_tool_calls = self.filter_tool_calls(original_response.tool_calls, output_schema)
            has_tool_calls = bool(filtered_tool_calls)

        # import ipdb; ipdb.set_trace()
        if self.config.output_schema.is_output_str() or has_tool_calls:
            response = original_response
        else:
            response = original_response["raw"]
        

        # Extract reasoning from Fireworks models that support it
        if model_metadata.provider in [LLMModelProvider.FIREWORKS, LLMModelProvider.PERPLEXITY] and model_metadata.reasoning:
            # Check if we have a response with content attribute (typical for LangChain responses)
            if hasattr(response, 'content'):
                response_content = response.content
                
                # Extract the reasoning part enclosed in <think>...</think> tags
                reasoning_match = re.search(r"<think>(.*?)</think>", response_content, re.DOTALL)
                if reasoning_match:
                    # Extract reasoning content
                    reasoning = reasoning_match.group(1).strip()
                    
                    # Create a new thinking message to add to the conversation history
                    # Create a list with thinking and clean text content
                    separated_content = [
                        {'type': 'thinking', 'text': reasoning},
                        {'type': 'text', 'text': re.sub(r"<think>.*?</think>\s*", "", response_content, flags=re.DOTALL)}
                    ]
                    
                    response.content = separated_content


        response_metadata = getattr(response, 'response_metadata', {})
        
        # Normalize metadata to OpenAI format
        normalized_metadata = None
        if not response_metadata:
            response_metadata = getattr(response, "usage_metadata", {})
        if response_metadata:
            normalized_metadata = self.normalize_metadata_to_openai_format(
                # response,
                response_metadata,
                self.config.llm_config.model_spec.provider
            )
        # import ipdb; ipdb.set_trace()
        metadata = LLMMetadata(
            response_metadata=response_metadata,  # Use normalized metadata
            model_name=self.config.llm_config.model_spec.model,
            latency=latency,
            token_usage=normalized_metadata["token_usage"] if normalized_metadata else None,
            finish_reason=normalized_metadata["finish_reason"] if normalized_metadata else None
        )

        # Handle tool calls
        tool_calls = []
        if has_tool_calls:
            tool_calls = [
                ToolCall(
                    tool_name=call['name'],
                    tool_input=call['args'],
                    tool_id=call.get('id')
                ) for call in filtered_tool_calls
            ]
            """
            Gemini sample tool calls: [{'name': 'llmStructuredOutputSchema', 'args': {'content': 'Four', 'metadata': ['The user asked for the sum of 2+2.', 'The result is 4.', 'The user requested the answer in one word.', "The word for 4 is 'Four'."]}, 'id': 'd9cbb3a1-f1e5-4566-a8c3-734b30366eae', 'type': 'tool_call'}]

            """
        # import ipdb; ipdb.set_trace()
        # Handle structured output
        # TODO: FIXME: Assumes that tool response and structured outputs can't both happen at once!
        structured_output = None
        if not has_tool_calls:
            if not self.config.output_schema.is_output_str():
                try:
                    if isinstance(response.content, list):
                        structured_output = output_schema.parse_raw(response.content[-1]["text"])
                    else:
                        # NOTE: this probably woudn't be neccessary and should be the same attempt as the result in `parsed` key below!
                        structured_output = output_schema.parse_raw(response.content)
                except Exception as e:
                    pass
                    # logger.warning(f"Error parsing structured output: {e}")
                structured_output = structured_output or (original_response["parsed"] if not original_response["parsing_error"] else None)
                structured_output = structured_output.model_dump() if structured_output else None
                
        # import ipdb; ipdb.set_trace()
        return LLMNodeOutputSchema(
            current_messages=current_messages + [response],
            content=response.content,
            metadata=metadata,
            structured_output=structured_output,
            tool_calls=tool_calls or None,
            web_search_result=LLMNode._parse_search_results(model_metadata, response)
        )

    @staticmethod
    def _parse_search_results(model_metadata: ModelMetadata, response: Any) -> Optional[WebSearchResult]:
        """
        Parse web search results from the model response.
        
        Handles two different formats:
        1. OpenAI format with annotations containing url_citation objects
        2. Perplexity format with a simple list of citation URLs
        
        Args:
            model_metadata: Model metadata
            response: The model response object
            
        Returns:
            WebSearchResult object with parsed citations or None if no search results found
        """
        if not model_metadata.web_search:
            return None
        # Initialize empty citations list
        citations = []
        
        # Get additional_kwargs from response, handling different response structures
        additional_kwargs = None
        if hasattr(response, 'additional_kwargs'):
            additional_kwargs = response.additional_kwargs
        elif isinstance(response, dict) and 'raw' in response and hasattr(response['raw'], 'additional_kwargs'):
            additional_kwargs = response['raw'].additional_kwargs
        
        if not additional_kwargs:
            return None
            
        # Handle OpenAI format with annotations
        if 'annotations' in additional_kwargs:
            annotations = additional_kwargs.get('annotations', [])
            for annotation in annotations:
                citations.append(
                        Citation(
                            url=None,
                            title=None,
                            snippet=None,  # OpenAI doesn't provide snippets directly
                            timestamp=None,
                            metadata=annotation
                        )
                    )
                if annotation.get('type', None) == 'url_citation' and 'url_citation' in annotation:
                    url_citation = annotation['url_citation']
                    citations[-1].url = url_citation.get('url', None)
                    citations[-1].title = url_citation.get('title', None)
                    
        
        # Handle Perplexity format with simple citations list
        elif 'citations' in additional_kwargs:
            citation_urls = additional_kwargs.get('citations', [])
            for url in citation_urls:
                citations.append(
                    Citation(
                        url=url,
                        title=None,  # Perplexity doesn't provide titles directly
                        snippet=None,
                        timestamp=None,
                        metadata=None
                    )
                )
        else:
            # Handle markdown-style URL citations in content (common in some providers)
            # Use regex to find all markdown-style links [title](url)
            content = response.content
            if not isinstance(content, str):
                content = json.dumps(content)
            markdown_links = re.findall(r'\[(.*?)\]\((\S+)\)', content)
            for title, url in markdown_links:
                citations.append(
                    Citation(
                        url=url,
                        title=title.strip() if title else None,
                        snippet=None,
                        timestamp=None,
                        metadata={'detected_format': 'markdown_link'}
                    )
                )
            
        # Create and return the WebSearchResult object
        return WebSearchResult(
            citations=citations,
            search_metadata=additional_kwargs.get('search_metadata')
        )

    def _convert_messages(self, message_dicts: List[Dict[str, Any]]) -> List[AnyMessage]:
        """
        Convert message dictionaries to LangChain message objects.
        
        Args:
            message_dicts: List of message dictionaries
            
        Returns:
            List[AnyMessage]: List of LangChain message objects
        """
        messages = []
        for msg in message_dicts:
            msg_type = msg.get("type", "human").lower()
            content = msg.get("content", "")
            
            if msg_type == "human" or msg_type == "user":
                messages.append(HumanMessage(content=content))
            elif msg_type == "ai" or msg_type == "assistant":
                messages.append(AIMessage(content=content))
            elif msg_type == "system":
                messages.append(SystemMessage(content=content))
            elif msg_type == "tool" or msg_type == "function":
                tool_name = msg.get("tool_name", "") or msg.get("function_name", "")
                messages.append(ToolMessage(content=content, tool_call_id=msg.get("id"), name=tool_name))
        
        return messages
    
    def _filter_thinking_messages(self, messages: List[AnyMessage], keep: Literal[ThinkingTokensInPrompt.ALL, ThinkingTokensInPrompt.LATEST, ThinkingTokensInPrompt.NONE] = ThinkingTokensInPrompt.ALL) -> List[AnyMessage]:
        """Filter out thinking messages from the message list."""
        def get_attr_or_key(obj: Any, key: str) -> Any:
            dict_val = obj.get(key, None) if isinstance(obj, dict) else None
            return getattr(obj, key, dict_val)
        def msg_is_types(msg: AnyMessage, types: List[str] = THINKING_MESSAGE_TYPES) -> bool:  # REDACED_THINKING_MESSAGE_TYPES
            msg_type = get_attr_or_key(msg, "type")
            return msg_type in types
        def filter_out_messages_of_type(messages: List[AnyMessage], types: List[str] = THINKING_MESSAGE_TYPES, perform_filter: bool = True) -> List[AnyMessage]:
            filtered_messages = []
            last_filtered_message_idx = None
            for i, message in enumerate(messages):
                content = get_attr_or_key(message, "content")
                content_is_dict = False
                if not content:
                    filtered_messages.append(message)
                    continue
                elif isinstance(content, str):
                    filtered_messages.append(message)
                    continue
                elif isinstance(content, dict):
                    # TODO: FIXME: this shouldn't happen! dict type content is now allowed in langchain BaseMessage class!
                    content = list[content]
                    content_is_dict = True
                if not isinstance(content, list):
                    # TODO: FIXME: this shouldn't happen!
                    # content is unknown type!
                    filtered_messages.append(message)
                    continue
                
                filtered_content = []   
                for sub_message in content:
                    if not msg_is_types(sub_message, types):
                        filtered_content.append(sub_message)
                    else:
                        last_filtered_message_idx = i
                
                if not filtered_content:
                    continue
                if content_is_dict:
                    filtered_content = filtered_content[0]
                
                kwargs = copy(message) if isinstance(message, dict) else message.model_dump()
                kwargs["content"] = filtered_content
                filtered_message_copy = message.__class__(**kwargs)
                filtered_messages.append(filtered_message_copy)
            return (filtered_messages if perform_filter else messages), last_filtered_message_idx
        
        keep_redacted = self.config.llm_config.model_spec.provider == LLMModelProvider.ANTHROPIC

        _, last_filtered_message_idx = filter_out_messages_of_type(messages, THINKING_MESSAGE_TYPES, perform_filter=False)
        _, last_filtered_message_idx_unredacted = filter_out_messages_of_type(messages, list(set(THINKING_MESSAGE_TYPES) - set(REDACED_THINKING_MESSAGE_TYPES)), perform_filter=False)
        if (keep_redacted and keep == ThinkingTokensInPrompt.ALL) or (last_filtered_message_idx is None):
            # If we're keeping all thinking messages including redacted or there's not thinking (including redacted) messages, keep all messages
            return messages
        if keep == ThinkingTokensInPrompt.ALL or (last_filtered_message_idx_unredacted is None and (not keep_redacted)):
            # If we're keeping all thinking messages (and not keeping redacted messages -- condition implicitly addressed previously) 
            #     or there's no unredacted messages and we're not keeping redacted messages; 
            #     we will filter out all redacted
            filter_type = REDACED_THINKING_MESSAGE_TYPES
        elif keep == ThinkingTokensInPrompt.NONE:
            filter_type = THINKING_MESSAGE_TYPES
        else:
            idx = last_filtered_message_idx if keep_redacted else last_filtered_message_idx_unredacted
            latest_message_filter =  [] if keep_redacted else REDACED_THINKING_MESSAGE_TYPES

            filtered_messages_left, _ = filter_out_messages_of_type(messages[:idx], THINKING_MESSAGE_TYPES, perform_filter=True)
            # Only keep latest thinking messages!
            filtered_messages_latest, _ = filter_out_messages_of_type(messages[idx:idx+1], latest_message_filter, perform_filter=True)
            filtered_messages_right, _ = filter_out_messages_of_type(messages[idx+1:], THINKING_MESSAGE_TYPES, perform_filter=True)
            return filtered_messages_left + filtered_messages_latest + filtered_messages_right
        filtered_messages, _ = filter_out_messages_of_type(messages, filter_type, perform_filter=True)
        return filtered_messages

    def _handle_streaming(self, model: Any, messages: List[AnyMessage]) -> Any:
        """Handle streaming response from the model."""
        # This method needs to be implemented based on the specific streaming logic for each provider
        # It's a placeholder and should be replaced with the actual implementation
        raise NotImplementedError("Streaming handling not implemented for this provider")

    def _get_current_time_ms(self) -> float:
        """Get the current time in milliseconds."""
        import time
        return time.time() * 1000

    @staticmethod
    def normalize_metadata_to_openai_format(raw_metadata: Dict[str, Any], provider: LLMModelProvider) -> Dict[str, Any]:
        """
        Normalize provider-specific response metadata to OpenAI-like format.
        
        Args:
            raw_metadata: Raw metadata from provider response
            provider: Model provider enum
            
        Returns:
            Dict with OpenAI-style metadata format:
            {
                "token_usage": {
                    "completion_tokens": int,
                    "prompt_tokens": int,
                    "total_tokens": int
                },
                "model_name": str,
                "system_fingerprint": Optional[str],
                "id": Optional[str],
                "finish_reason": Optional[str],
                "logprobs": Optional[Any]
            }
        """
        if not raw_metadata:
            # raw_metadata = getattr(response, "usage_metadata", {})
            # if not raw_metadata:
            return

        def get_key(response_metadata, keys):
            for key in keys:
                if key in response_metadata:
                    return response_metadata[key]
            return ""
        
        # usage_keys = [
        #     'usage_metadata',
        #     'usage',
        #     'token_usage'
        # ]
        # token_usage = get_key(raw_metadata, usage_keys)
        finish_reason_keys = [
            'stopReason',
            'stop_reason',
            'finish_reason'
        ]
        # finish_reason = 
        normalized = {
            "token_usage": {},
            # "model_name": raw_metadata.get("model_name") or raw_metadata.get("model", ""),
            # "system_fingerprint": raw_metadata.get("system_fingerprint"),
            # "id": raw_metadata.get("id"),
            "finish_reason": get_key(raw_metadata, finish_reason_keys),  # raw_metadata.get("finish_reason"),
            # "logprobs": raw_metadata.get("logprobs")
        }

        # Handle token usage normalization
        token_usage = {}
        if provider == LLMModelProvider.OPENAI:
            token_usage = raw_metadata.get("token_usage", {})
            # Add OpenAI-specific token details if available
            token_usage.update({
                "reasoning_tokens": raw_metadata.get("token_usage", {}).get("completion_tokens_details", {}).get("reasoning_tokens", 0),
                "accepted_prediction_tokens": raw_metadata.get("token_usage", {}).get("completion_tokens_details", {}).get("accepted_prediction_tokens", 0),
                "rejected_prediction_tokens": raw_metadata.get("token_usage", {}).get("completion_tokens_details", {}).get("rejected_prediction_tokens", 0),
                "cached_tokens": raw_metadata.get("token_usage", {}).get("prompt_tokens_details", {}).get("cached_tokens", 0)
            })
        elif provider == LLMModelProvider.ANTHROPIC:
            usage = raw_metadata.get("usage", {})
            token_usage = {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                "reasoning_tokens": usage.get("reasoning_tokens", 0),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
                "cached_tokens": usage.get("cache_read_input_tokens", 0)
            }
        elif provider == LLMModelProvider.GEMINI:
            usage = raw_metadata.get("usage_metadata", {})
            token_usage = {
                "prompt_tokens": usage.get("prompt_token_count", 0),
                "completion_tokens": usage.get("candidates_token_count", 0),
                "total_tokens": usage.get("total_token_count", 0),
                "cached_tokens": usage.get("cached_content_token_count", 0),
                "reasoning_tokens": 0  # Gemini doesn't report reasoning tokens
            }
        elif provider == LLMModelProvider.AWS_BEDROCK:
            usage = raw_metadata.get("usage", {})
            token_usage = {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                "reasoning_tokens": 0,  # Bedrock doesn't report reasoning tokens
                "cached_tokens": 0
            }
        elif provider in [LLMModelProvider.FIREWORKS]:  # LLMModelProvider.MISTRALAI, 
            token_usage = raw_metadata.get("token_usage", {})
            if "total_tokens" not in token_usage:
                token_usage["total_tokens"] = token_usage.get("prompt_tokens", 0) + token_usage.get("completion_tokens", 0)
            token_usage.update({
                "reasoning_tokens": 0,  # These providers don't report reasoning tokens
                "cached_tokens": 0
            })
        elif provider == LLMModelProvider.PERPLEXITY:
            usage = raw_metadata
            token_usage = {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "reasoning_tokens": usage.get("reasoning_tokens", 0),  # Perplexity doesn't report reasoning tokens
                # "cached_tokens": 0
            }

        # Ensure all token types are present
        token_usage.setdefault("reasoning_tokens", 0)
        token_usage.setdefault("cached_tokens", 0)
        normalized["token_usage"] = token_usage

        # Handle finish reason aliases
        finish_reason_mapping = {
            "function_call": "tool_call",
            "end_turn": "stop",
            "stop_sequence": "stop",
            "stop": "stop",
            "length": "max_tokens",
            "max_tokens": "max_tokens"
        }
        if normalized.get("finish_reason", "").lower() in finish_reason_mapping:
            normalized["finish_reason"] = finish_reason_mapping[normalized.get("finish_reason", "").lower()]

        return normalized
