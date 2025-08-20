"""
LLM Node using LangChain.

This module provides a LangChain-based LLM node implementation that supports multiple
model providers (OpenAI, Anthropic, Gemini) with structured output and tool calling.
"""
import asyncio
from copy import copy, deepcopy
import json
import os
from enum import Enum
import re
import time
from typing import Any, ClassVar, Dict, List, Optional, Type, Union, Literal, cast, get_origin, get_args, Tuple, TYPE_CHECKING
from functools import partial
from operator import itemgetter
from uuid import uuid4

# Add jsonschema imports
import jsonschema
from jsonschema import Draft202012Validator

# Add tokencost imports
from tokencost import calculate_prompt_cost, calculate_completion_cost, calculate_cost_by_tokens

from pydantic import Field, field_validator, model_validator, BaseModel, create_model
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from pydantic import ConfigDict
from pydantic.v1 import BaseModel as BaseModelV1
from sqlmodel.ext.asyncio.session import AsyncSession
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY,
)
from db.session import get_async_db_as_manager
# ######## ######## ######## ######## ######## ######## ########
# ######## ######## MONKEY PATCHING LANGCHAIN ######## ######## 
# ######## ######## ######## ######## ######## ######## ########
# from langchain_core.messages.ai import UsageMetadata
# from langchain_perplexity import chat_models

# def _custom_create_usage_metadata(token_usage: dict) -> UsageMetadata:
#     input_tokens = token_usage.get("prompt_tokens", 0)
#     output_tokens = token_usage.get("completion_tokens", 0)
#     total_tokens = token_usage.get("total_tokens", input_tokens + output_tokens)
#     print("####### ######## $$$$$ FUCKING MONKEY PATCHING $$$$$ ######## ########")
#     print("json.dumps(token_usage):", json.dumps(token_usage, indent=4))
#     return UsageMetadata(
#         input_tokens=input_tokens,
#         output_tokens=output_tokens,
#         total_tokens=total_tokens,
#     )

# chat_models._create_usage_metadata = _custom_create_usage_metadata

# ######## ######## ######## ######## ######## ######## ########
# ######## ######## ######## ######## ######## ######## ########

# from anthropic import Anthropic
from openai import OpenAI, AsyncOpenAI
import anthropic

from langchain_core.messages import (
    AIMessage, 
    HumanMessage, 
    SystemMessage, 
    ToolMessage,
    AnyMessage,
    # BaseMessage
)
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_perplexity import ChatPerplexity

from langchain_openai.chat_models.base import (
    _convert_to_openai_response_format, convert_to_openai_tool, 
    _is_pydantic_class, RunnableLambda, RunnablePassthrough, _oai_structured_outputs_parser, RunnableMap,
    PydanticToolsParser,
    JsonOutputKeyToolsParser,
)
from langchain_anthropic.chat_models import (
    convert_to_anthropic_tool, 
    LanguageModelInput, is_basemodel_subclass, OutputParserLike,
    OutputParserException, BaseMessage, AnthropicTool
)

from langchain_core.runnables import Runnable, RunnableBinding

from langchain_core.messages.utils import message_chunk_to_message

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.tools import BaseTool
from langchain.chat_models import init_chat_model
# from langchain_community.chat_models import ChatPerplexity

# Add db and service imports
# from kiwi_app.auth.models import User
# from db.session import get_async_db_as_manager
# Add context key imports

from global_utils.json_schema_to_pydantic import convert_json_schema_to_pydantic_in_memory
from kiwi_app.workflow_app.constants import LaunchStatus
from workflow_service.config.settings import settings
from workflow_service.registry.nodes.llm.internal_tools.internal_base import BaseProviderInternalTool
from workflow_service.registry.registry import DBRegistry
from workflow_service.registry.nodes.core.base import BaseNode
from workflow_service.registry.schemas.base import BaseSchema, BaseNodeConfig
from workflow_service.registry.nodes.core.dynamic_nodes import ConstructDynamicSchema, DynamicSchema
from workflow_service.registry.nodes.llm.config import LLMModelProvider, PROVIDER_MODEL_MAP, AnthropicModels, AWS_REGION, ModelMetadata, THINKING_MESSAGE_TYPES, REDACED_THINKING_MESSAGE_TYPES, GEMINI_PARAM_KEY_OVERRIDES, PARAM_KEY_OVERRIDES, AI_MESSAGE_TYPES
from workflow_service.registry.schemas.base import create_dynamic_schema_with_fields
# from workflow_service.services.external_context_manager import ExternalContextManager

if TYPE_CHECKING:
    from workflow_service.services.external_context_manager import ExternalContextManager

class MessageType(str, Enum):
    """Message types."""
    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"
    TOOL = "tool"


###########################
###### Input Schema ######
###########################


class ToolOutput(BaseSchema):
    """Represents the output of a tool execution."""
    tool_call_id: str = Field(description="ID of the tool call that generated this output")
    content: str = Field(description="The output content from the tool execution")
    type: str = Field(default="tool", description="Type of the output (always 'tool')")
    name: str = Field(description="Name of the tool that was executed")
    status: str = Field(description="Status of the execution ('success' or 'error')")
    error_message: Optional[str] = Field(None, description="Error message if execution failed")
    state_changes: Optional[Dict[str, Any]] = Field(None, description="State changes made by the tool execution")


class LLMNodeInputSchema(BaseSchema):
    """Input schema for the LLM node. NOTE: always use prompt constructor when using loops since this node will always read the same inputs over and over!"""
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
    tool_outputs: Optional[List[ToolOutput]] = Field(
        None,
        description="Dict of tool outputs to append to the conversation. Each tool output must have 'tool_name' and 'output' keys."
    )
    image_input_url_or_base64: Optional[Union[str, List[str]]] = Field(
        None,
        description="URL or base64 encoded image(s) to send to the model. If provided, the model will generate a response based on the image(s)."
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
    search_query_usage: int = Field(default=0, description="Number of search queries used")
    # thinking_tokens: Optional[int] = Field(None, description="Number of thinking tokens (for models that support it)")
    finish_reason: Optional[str] = Field(None, description="Reason for finish (e.g., 'stop', 'length', 'tool_calls')")
    latency: Optional[float] = Field(None, description="Latency in seconds")
    cached: Optional[bool] = Field(default=False, description="Whether the response was cached")
    iteration_count: Optional[int] = Field(default=0, description="Number of LLM Generation iterations")
    tool_call_count: Optional[int] = Field(default=0, description="Number of tool calls made")


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


class AgentAction(BaseSchema):
    """Represents an agent action performed during model execution."""
    id: str = Field(description="Unique identifier for the action")
    index: int = Field(description="Index/order of the action")
    action: Dict[str, Any] = Field(description="The action details (e.g., query, type, url)")
    type: str = Field(description="Type of the action (e.g., 'web_search_call')")
    status: str = Field(description="Status of the action (e.g., 'completed', 'failed')")


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
    text_content: Optional[Any] = Field(None, description="Text content of the response")
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
    agent_actions: Optional[List[AgentAction]] = Field(
        None,
        description="List of agent actions performed during model execution (e.g., web searches, tool calls)"
    )
###########################


###########################
###### Config Schema ######
###########################


class ModelSpec(BaseNodeConfig):
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


class SchemaFromRegistryConfig(BaseNodeConfig):
    """Schema configuration."""
    schema_name: str = Field(description="Schema Unique name")
    schema_version: Optional[str] = Field(None, description="Schema version")


class LLMStructuredOutputSchema(BaseNodeConfig):
    """Output format types. Defines how the structured output schema is specified.

    Exactly one of the following must be provided:
    - dynamic_schema_spec: Define the schema directly using Pydantic fields.
    - schema_template_name: Load the schema from a named template in the registry.
    - schema_definition: Provide the raw JSON schema definition directly.

    NOTE: Some providers do not support strict structured output or JSON mode and use / force tool calling to fill the schema instead.
    You may want to add additional instructions to the prompt to ensure the tool is called, including reinforcing the output schema format expected.

    For eg, Anthropic structured output relies on forced tool calling, which is not supported when `thinking` is enabled. Sometimes, the tool calls are not generated leading to parser errors.
    Consider disabling `thinking` or adjust your prompt to ensure the tool is called.

    NOTE: For Anthropic, structured output is not properly supported when using tools with non-reasoning models, be careful of errors caused by this.
    """
    # Option 1: Dynamic Pydantic Schema
    dynamic_schema_spec: Optional[ConstructDynamicSchema] = Field(
        None,
        description="Dynamic Pydantic Schema specification for the output."
    )
    # Option 2: Schema from Registry Template
    schema_template_name: Optional[str] = Field(
        None,
        description="Name of the schema template to load from the registry."
    )
    schema_template_version: Optional[str] = Field(
        None,
        description="Version of the schema template (optional, defaults to latest)."
    )
    # Option 3: Direct JSON Schema Definition
    schema_definition: Optional[Dict[str, Any]] = Field(
        None,
        description="Raw JSON schema definition for the output."
    )

    convert_loaded_schema_to_pydantic: Optional[bool] = Field(
        True,
        description="Whether to convert the loaded schema to a Pydantic model before using in structured output. JSON Schemas have a lot of restrictions and format nuances across providers and sometimes passing pydantic models is better for structured generation."
    )

    @model_validator(mode='before')
    def check_exclusive_options(cls, values):
        if not values:
            return values
        """Ensure exactly one schema option is provided."""
        provided_options = [
            values.get('dynamic_schema_spec') is not None,
            values.get('schema_template_name') is not None,
            values.get('schema_definition') is not None
        ]
        if sum(provided_options) > 1:
            raise ValueError("Only one of 'dynamic_schema_spec', 'schema_template_name', or 'schema_definition' can be provided.")
        return values

    @model_validator(mode='after')
    def check_template_version(self):
        """Ensure version is provided only if name is provided."""
        if self.schema_template_version is not None and self.schema_template_name is None:
            raise ValueError("'schema_template_version' can only be provided if 'schema_template_name' is also provided.")
        return self

    def is_output_str(self) -> bool:
        """Check if no structured output schema is defined."""
        return not (self.dynamic_schema_spec or self.schema_template_name or self.schema_definition)


    @staticmethod
    def _recursive_set_json_schema_to_openai_format(
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        if isinstance(schema, dict):
            # Check if 'required' is a key at the current level or if the schema is empty,
            # in which case additionalProperties still needs to be specified.
            
            
            ### DEBUG HACKS for any Of ###
            if "additionalProperties" in schema:
                schema["additionalProperties"] = False
            if "anyOf" in schema:
                if isinstance(schema["anyOf"], list):
                    schema["anyOf"] = [
                        LLMStructuredOutputSchema._recursive_set_json_schema_to_openai_format(a) for a in schema["anyOf"]
                    ]
                else:
                    schema["anyOf"] = LLMStructuredOutputSchema._recursive_set_json_schema_to_openai_format(schema["anyOf"])
            ### DEBUG HACKS for any Of ###

            # Recursively check 'properties' and 'items' if they exist
            if "properties" in schema:
                if "required" not in schema:
                    schema["required"] = []
                for value in schema["properties"].values():
                    if "$ref" in value:
                        # continue
                        if "description" in value:
                            del value["description"]
                    LLMStructuredOutputSchema._recursive_set_json_schema_to_openai_format(value)
                for key in schema["properties"].keys(): # NOTE: this is a hack to set additionalProperties to False for all properties
                    if key not in schema["required"]:
                        schema["required"].append(key)
            if "$defs" in schema:
                for value in schema["$defs"].values():
                    LLMStructuredOutputSchema._recursive_set_json_schema_to_openai_format(value)
            if "items" in schema:
                LLMStructuredOutputSchema._recursive_set_json_schema_to_openai_format(schema["items"])
            
            if "required" in schema or (
                "properties" in schema and not schema["properties"]
            ):
                schema["additionalProperties"] = False

        return schema

    async def get_schema(
        self,
        model_metadata: ModelMetadata,
        org_id: str,
        user,  # : User
        customer_data_service,  # : CustomerDataService
        built_schema_name: Optional[str] = None
    ) -> Union[Type[BaseSchema], Dict[str, Any], None]:
        """
        Get the output schema based on the configuration.

        Retrieves the schema either by building a dynamic Pydantic model,
        loading a JSON schema from a template in the registry, or using
        a directly provided JSON schema definition.

        Args:
            model_metadata: Model metadata.
            org_id: The organization ID.
            user: The user object.
            customer_data_service: Service to interact with customer data and schemas.
            built_schema_name: Optional name for the dynamically built Pydantic schema.

        Returns:
            The Pydantic model class, a JSON schema dictionary, or None if is_output_str() is True.
            Output JSON Schema is converted to a Pydantic model if convert_loaded_schema_to_pydantic is True.

        Raises:
            ValueError: If the schema template is not found or configuration is invalid.
        """
        if self.is_output_str():
            response = None

        if self.dynamic_schema_spec:
            # Build Pydantic schema from dynamic spec
            schema_name = built_schema_name or f"{self.__class__.__name__}DynamicOutputSchema"
            response = self.dynamic_schema_spec.build_schema(schema_name=schema_name)
        elif self.schema_template_name:
            # Load JSON schema from registry template
            async with get_async_db_as_manager() as db_session:
                loaded_schema = await customer_data_service._get_schema_from_template(  # : Optional[SchemaTemplate]
                    db=db_session,
                    template_name=self.schema_template_name,
                    template_version=self.schema_template_version,
                    org_id=org_id,
                    user=user
                )
            if not loaded_schema:
                raise ValueError(f"Schema template '{self.schema_template_name}' (version: {self.schema_template_version or 'latest'}) not found or has no definition.")
            response = loaded_schema  # .schema_definition
        elif self.schema_definition:
            # Use directly provided JSON schema
            response = self.schema_definition
        else:
            # Should not happen due to validator, but included for completeness
            raise ValueError("Invalid LLMStructuredOutputSchema configuration: No schema source specified.")

        if self.convert_loaded_schema_to_pydantic and isinstance(response, dict):
            response = convert_json_schema_to_pydantic_in_memory(response)
        elif isinstance(response, dict):
            if model_metadata.provider == LLMModelProvider.OPENAI:
                response = LLMStructuredOutputSchema._recursive_set_json_schema_to_openai_format(response)

        return response


class ToolConfig(BaseNodeConfig):
    """Configuration for a tool. (Pulled from ToolRegistry)
    NOTE: this tool is configured in the tool caller node and it has the config default / set by user. 
    This config in LLM node only receives input_overwrites so that it can determine which parts of the input schema go into the tool call.
    IMPORTANT NOTE: A tool node should have a verbose, descriptive input schema btw!

    NOTE: many inbuilt tools such as web search are provider specific, and not all models from the same provider support all inbuilt tools. EG: O3_MINI / O4_MINI don't support the web search preview tool.
    """
    tool_name: str = Field(description="Tool name")
    version: Optional[str] = Field(None, description="Tool version")
    is_provider_inbuilt_tool: Optional[bool] = Field(None, description="if this a provider specific inbuilt tool or a KiwiQ defined tool.")
    provider_inbuilt_user_config: Optional[Dict[str, Any]] = Field(None, description="User config for provider inbuilt tools.")
    # input_overwrites: Optional[Dict[str, Any]] = Field(None, description="Input overwrites for the tool. These fields are not passed to the LLM and are not filled!")
    # additional_tool_config_fields: Optional[ConstructDynamicSchema] = Field(None, description="Additional fields for the tool. They could contain additional config fields for the tool not part of standard input schema.")


class LLMModelConfig(BaseNodeConfig):
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
    verbosity: Optional[Literal["low", "medium", "high"]] = Field(
        default=None,
        description="Verbosity level for models that support it (GPT-5 series only)."
    )
    max_tool_calls: Optional[int] = Field(
        None,
        description="Maximum number of tool calls to make"
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


class ToolCallingConfig(BaseNodeConfig):
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

class WebSearchConfig(BaseNodeConfig):
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

class LLMNodeConfigSchema(BaseNodeConfig):
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
    output_schema: Optional[LLMStructuredOutputSchema] = Field(
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

    # @model_validator(mode='after')
    # def validate_anthropic_tools_and_structured_output(self) -> 'LLMNodeConfigSchema':
    #     """
    #     Validate that when using Anthropic with built-in tools, structured output is not provided.
        
    #     This is because Anthropic's tool calling implementation is incompatible with structured output
    #     when using built-in tools.
    #     """
    #     if (self.llm_config and 
    #         self.llm_config.model_spec.provider == LLMModelProvider.ANTHROPIC and 
    #         self.tools and 
    #         any(tool.is_provider_inbuilt_tool for tool in self.tools) and
    #         self.output_schema):
    #         raise ValueError(
    #             "Structured output (output_schema) is not supported when using Anthropic with "
    #             "built-in tools. Please either remove the output_schema or use custom tools instead."
    #         )
    #     return self

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

    async def process(self, input_data: LLMNodeInputSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> LLMNodeOutputSchema:
        """
        Process LLM request using node config (self.config) and runtime parameters.
        
        Key changes:
        - All node configuration comes from self.config
        - Runtime config (passed parameter) used for execution context
        - Registry accessed through kwargs
        """
        if isinstance(input_data, dict):
            input_data = self.input_schema_cls(**input_data)
        # Extract context from runtime config
        if not config:
            self.error("Missing runtime config (config argument).")
            # TODO: Consider returning a default error output or raising an exception
            return LLMNodeOutputSchema(
                current_messages=[],
                metadata=LLMMetadata(model_name=self.config.llm_config.model_spec.model),
            )
        config = config.get("configurable")

        app_context: Optional[Dict[str, Any]] = config.get(APPLICATION_CONTEXT_KEY)
        
        ext_context: "ExternalContextManager" = config.get(EXTERNAL_CONTEXT_MANAGER_KEY)  # : Optional[ExternalContextManager]
        registry = ext_context.db_registry  # : Optional[DBRegistry]

        if not app_context or not ext_context:
            self.error(f"Missing required keys in runtime_config: {APPLICATION_CONTEXT_KEY}, {EXTERNAL_CONTEXT_MANAGER_KEY} in external config.")
            return LLMNodeOutputSchema(
                current_messages=[],
                metadata=LLMMetadata(model_name=self.config.llm_config.model_spec.model),
            )

        user = app_context.get("user")  # : Optional[User]
        run_job = app_context.get("workflow_run_job")  # : Optional[WorkflowRunJobCreate]
        customer_data_service = ext_context.customer_data_service  # : Optional[CustomerDataService]

        if not user or not run_job or not customer_data_service:
            self.error("Missing 'user', 'workflow_run_job', or 'customer_data_service' in context.")
            return LLMNodeOutputSchema(
                current_messages=[],
                metadata=LLMMetadata(model_name=self.config.llm_config.model_spec.model),
            )

        org_id = run_job.owner_org_id

        # Initialize model using node config
        try:
            model_metadata: ModelMetadata
            chat_model, model_metadata = self._init_model()
        except Exception as e:
            self.critical("Model initialization failed")
            raise ValueError(f"Model initialization failed: {str(e)}, \n{e.__traceback__}") from e

        # Prepare messages using node config
        messages_for_model, current_messages = self._prepare_messages(input_data, model_metadata)

        is_structured_output = self.config.output_schema and not self.config.output_schema.is_output_str()
        is_tool_use = self.config.tool_calling_config.enable_tool_calling and self.config.tools

        # Bind tools if configured in node config
        tool_kwargs = {}
        tools = []
        is_all_inbuild_tools = True
        has_code_execution_tool = False
        if is_tool_use:
            assert model_metadata.tool_use, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support tool use!"
            has_code_execution_tool, is_all_inbuild_tools, tool_use_chat_model, tools, tool_kwargs = self._bind_tools(chat_model, model_metadata, registry)
            if not is_structured_output:
                chat_model = tool_use_chat_model
            # import ipdb; ipdb.set_trace()
            # bind_tool_kwargs = chat_model.kwargs
        
        # Determine and fetch the structured output schema if configured
        
        determined_output_schema: Union[Type[BaseSchema], Dict[str, Any], None] = None
        structured_output_kwargs = {}
        if is_structured_output:
            assert model_metadata.structured_output, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support structured output!"
            try:
                determined_output_schema = await self.config.output_schema.get_schema(
                    model_metadata=model_metadata,
                    org_id=org_id,
                    user=user,
                    customer_data_service=customer_data_service,
                    built_schema_name=f"{self.__class__.node_name}StructuredOutputSchema"
                )
                if not is_tool_use:
                    chat_model = self._apply_structured_output(chat_model, determined_output_schema, model_metadata)
                    # structured_output_kwargs = chat_model.kwargs
            except Exception as e:
                self.critical("Failed to get or apply structured output schema")
                raise ValueError(f"Structured output configuration failed: {str(e)}") from e


        if is_tool_use and is_structured_output:
            chat_model = self._apply_both_structured_output_and_tool_kwargs(chat_model, model_metadata, output_schema=determined_output_schema, tools=tools, is_all_inbuild_tools=is_all_inbuild_tools, **tool_kwargs)
        
        
        # chat_model = chat_model.bind(**structured_output_kwargs, **tool_kwargs)
        
        # elif self.config.tool_calling_config.enable_tool_calling and self.config.tools:
        #     assert model_metadata.tool_use, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support tool use!"
        #     chat_model = self._bind_tools(chat_model, model_metadata, registry)

        

        # Execute model with provider-specific handling
        allocated_credits = 0.0
        try:
            start_time = time.time()
            response, allocated_credits = await self._execute_model(
                chat_model, messages_for_model, model_metadata, ext_context=ext_context, app_context=app_context,  # **tool_kwargs
                has_code_execution_tool=has_code_execution_tool,
            )
            # NOTE: 
            # if (not self.config.output_schema.is_output_str()): 
            #     # response is dict with keys {"raw": Any, "parsed": Any, "parsing_error": Optional[str]}
            # if (not self.config.output_schema.is_output_str()):
            #     pass
            # import ipdb; ipdb.set_trace()
            latency = time.time() - start_time
        except Exception as e:
            self.critical("Model execution failed")
            raise RuntimeError(f"Model execution failed: {str(e)}") from e

        # Parse and validate response using node config
        return await self._parse_response(response, input_data.messages_history, current_messages, latency, determined_output_schema, model_metadata, ext_context=ext_context, app_context=app_context, allocated_credits=allocated_credits)
    
    def _apply_both_structured_output_and_tool_kwargs(self, chat_model, model_metadata: ModelMetadata, output_schema: BaseSchema, tools: Optional[list] = None, is_all_inbuild_tools: bool = True, **kwargs: Dict[str, Any]):
        if model_metadata.provider == LLMModelProvider.OPENAI:
            # NOTE: if using inbuilt tools only, we allow strict json schema (for structured output) param to maintain consistency; if using internal tools, using strict yields to incorrect tool call results so turn it off then.
            #     This behaviour may have to change if strict impacts internal tool calls too, just like external tool calls!
            return self._apply_structured_and_tools_openai(chat_model, schema=output_schema, method="json_schema", include_raw=True, strict=True if is_all_inbuild_tools else False, tools=tools, **kwargs)  # DEBUG: STRICT
        elif model_metadata.provider == LLMModelProvider.ANTHROPIC:
            return self._apply_structured_and_tools_anthropic(chat_model, schema=output_schema, include_raw=True, tools=tools, **kwargs)
        else:
            raise ValueError(f"Unsupported provider: {model_metadata.provider}")
    
    ############## ############## ############## ############## ############## ##############
    ############## ##############  LANGCHAIN OVERRIDES   ##############  ##############
    ############## ############## ############## ############## ############## ##############

    def _get_llm_for_structured_output_when_thinking_is_enabled_anthropic(
        self,
        chat_model: ChatAnthropic,
        schema: Union[dict, type],
        formatted_tool: AnthropicTool,
        tools: Optional[list] = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, BaseMessage]:
        thinking_admonition = (
            "Anthropic structured output relies on forced tool calling, "
            "which is not supported when `thinking` is enabled. This method will raise "
            "langchain_core.exceptions.OutputParserException if tool calls are not "
            "generated. Consider disabling `thinking` or adjust your prompt to ensure "
            "the tool is called."
        )
        self.warning(thinking_admonition)
        llm = chat_model.bind_tools(
            [schema] + tools,
            ls_structured_output_format={
                "kwargs": {"method": "function_calling"},
                "schema": formatted_tool,
            },
            **kwargs,
        )

        # def _raise_if_no_tool_calls(message: AIMessage) -> AIMessage:
        #     if not message.tool_calls:
        #         raise OutputParserException(thinking_admonition)
        #     return message

        return llm  #  | _raise_if_no_tool_calls

    def _apply_structured_and_tools_anthropic(
        self,
        chat_model: ChatAnthropic,
        schema: Union[dict, type],
        *,
        include_raw: bool = False,
        tools: Optional[list] = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, Union[dict, BaseModel]]:
        formatted_tool = convert_to_anthropic_tool(schema)
        tool_name = formatted_tool["name"]
        if chat_model.thinking is not None and chat_model.thinking.get("type") == "enabled":
            llm = self._get_llm_for_structured_output_when_thinking_is_enabled_anthropic(
                chat_model, schema, formatted_tool, tools, **kwargs
            )
        else:
            llm = chat_model.bind_tools(
                [schema] + tools,
                # tool_choice=tool_name,
                ls_structured_output_format={
                    "kwargs": {"method": "function_calling"},
                    "schema": formatted_tool,
                },
                **kwargs,
            )

        return llm
        # if isinstance(schema, type) and is_basemodel_subclass(schema):
        #     output_parser: OutputParserLike = PydanticToolsParser(
        #         tools=[schema], first_tool_only=True
        #     )
        # else:
        #     output_parser = JsonOutputKeyToolsParser(
        #         key_name=tool_name, first_tool_only=True
        #     )

        # if include_raw:
        #     parser_assign = RunnablePassthrough.assign(
        #         parsed=itemgetter("raw") | output_parser, parsing_error=lambda _: None
        #     )
        #     parser_none = RunnablePassthrough.assign(parsed=lambda _: None)
        #     parser_with_fallback = parser_assign.with_fallbacks(
        #         [parser_none], exception_key="parsing_error"
        #     )
        #     return RunnableMap(raw=llm) | parser_with_fallback
        # else:
        #     return llm | output_parser

    def _apply_structured_and_tools_openai(
            self,
            chat_model: ChatOpenAI, 
            schema = None,
            method: Literal[
                "json_schema", "function_calling"
            ] = "json_schema",
            include_raw: bool = False,
            strict: Optional[bool] = None,
            tools: Optional[list] = None, **kwargs
        ) -> Runnable:

        is_pydantic_schema = _is_pydantic_class(schema)

        if method == "json_schema":
            # Check for Pydantic BaseModel V1
            if (
                is_pydantic_schema and issubclass(schema, BaseModelV1)  # type: ignore[arg-type]
            ):
                self.warning(
                    "Received a Pydantic BaseModel V1 schema. This is not supported by "
                    'method="json_schema". Please use method="function_calling" '
                    "or specify schema via JSON Schema or Pydantic V2 BaseModel. "
                    'Overriding to method="function_calling".'
                )
                method = "function_calling"
            # Check for incompatible model
            if chat_model.model_name and (
                chat_model.model_name.startswith("gpt-3")
                or chat_model.model_name.startswith("gpt-4-")
                or chat_model.model_name == "gpt-4"
            ):
                self.warning(
                    f"Cannot use method='json_schema' with model {chat_model.model_name} "
                    f"since it doesn't support OpenAI's Structured Output API. You can "
                    f"see supported models here: "
                    f"https://platform.openai.com/docs/guides/structured-outputs#supported-models. "  # noqa: E501
                    "To fix this warning, set `method='function_calling'. "
                    "Overriding to method='function_calling'."
                )
                method = "function_calling"

        if method == "function_calling":
            if schema is None:
                raise ValueError(
                    "schema must be specified when method is not 'json_mode'. "
                    "Received None."
                )
            tool_name = convert_to_openai_tool(schema)["function"]["name"]
            bind_kwargs = chat_model._filter_disabled_params(
                tool_choice=tool_name,
                parallel_tool_calls=False,
                strict=strict,
                ls_structured_output_format={
                    "kwargs": {"method": method, "strict": strict},
                    "schema": schema,
                },
            )

            llm = chat_model.bind_tools([schema], **bind_kwargs)
            if is_pydantic_schema:
                output_parser: Runnable = PydanticToolsParser(
                    tools=[schema],  # type: ignore[list-item]
                    first_tool_only=True,  # type: ignore[list-item]
                )
            else:
                output_parser = JsonOutputKeyToolsParser(
                    key_name=tool_name, first_tool_only=True
                )
        elif method == "json_schema":
            if schema is None:
                raise ValueError(
                    "schema must be specified when method is not 'json_mode'. "
                    "Received None."
                )
            response_format = _convert_to_openai_response_format(schema, strict=strict)
            bind_kwargs = dict(
                response_format=response_format,
                ls_structured_output_format={
                    "kwargs": {"method": method, "strict": strict},
                    "schema": convert_to_openai_tool(schema),
                },
            )
            if tools:
                bind_kwargs["tools"] = [
                    convert_to_openai_tool(t, strict=strict) for t in tools
                ]
                bind_kwargs["parallel_tool_calls"] = True
            bind_kwargs.update(kwargs)
            llm = chat_model.bind(**bind_kwargs)
            if is_pydantic_schema:
                output_parser = RunnableLambda(
                    partial(_oai_structured_outputs_parser, schema=cast(type, schema))
                ).with_types(output_type=cast(type, schema))
            else:
                output_parser = JsonOutputParser()
        else:
            raise ValueError(
                f"Unrecognized method argument. Expected one of 'function_calling' or "
                f"'json_mode'. Received: '{method}'"
            )

        if include_raw:
            parser_assign = RunnablePassthrough.assign(
                parsed=itemgetter("raw") | output_parser, parsing_error=lambda _: None
            )
            parser_none = RunnablePassthrough.assign(parsed=lambda _: None)
            parser_with_fallback = parser_assign.with_fallbacks(
                [parser_none], exception_key="parsing_error"
            )
            return RunnableMap(raw=llm) | parser_with_fallback
        else:
            return llm | output_parser
    
    ############## ############## ############## ############## ############## ##############
    ############## ############## ############## ############## ############## ##############
    ############## ############## ############## ############## ############## ##############
    
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

        if hasattr(model_metadata, "web_search") and model_metadata.web_search:
            if self.config.web_search_options is not None:
                # Validate web search capabilities against model metadata
                web_search_options = self.config.web_search_options.model_dump(exclude_none=True)
                
                # Check if model supports specific web search features
                if self.config.web_search_options.search_recency_filter and (not model_metadata.search_recency_filter):
                    raise ValueError(f"Model {model_metadata.model_name} does not support recency filtering for web search, but it was configured")
                    # self.warning(f"Model {model_metadata.model_name} does not support recency filtering, but it was configured")
                
                if self.config.web_search_options.search_domain_filter and (not model_metadata.search_domain_filter):
                    raise ValueError(f"Model {model_metadata.model_name} does not support domain filtering for web search, but it was configured")
                
                if self.config.web_search_options.search_context_size and (not model_metadata.search_context_size):
                    raise ValueError(f"Model {model_metadata.model_name} does not support search context size configuration for web search, but it was configured")
                
                if self.config.web_search_options.user_location and (not model_metadata.user_location):
                    raise ValueError(f"Model {model_metadata.model_name} does not support user location for web search, but it was configured")
                
                # Add validated options to the request
                key = "extra_body" if provider == LLMModelProvider.OPENAI else "model_kwargs"
                if key not in model_kwargs:
                    model_kwargs[key] = {}
                model_kwargs[key]["web_search_options"] = web_search_options
                self.info(f"Web search options in extra body: {json.dumps(web_search_options, indent=4)}")

        if model_metadata.max_tool_calls_param_key and self.config.llm_config.max_tool_calls is not None:
            model_kwargs[model_metadata.max_tool_calls_param_key] = self.config.llm_config.max_tool_calls
        
        if provider == LLMModelProvider.OPENAI:
           model_kwargs["stream_usage"] = True
           model_kwargs["use_responses_api"] = True
           model_kwargs["output_version"] = "responses/v1"
           # model_kwargs["stream_options"] = {"include_usage": True}
           # GPT-5 series: optional verbosity control
           if self.config.llm_config.verbosity and model_metadata.verbosity_supported:
                # model_kwargs["extra_body"]["verbosity"] = self.config.llm_config.verbosity
                model_kwargs["verbosity"] = self.config.llm_config.verbosity
                self.info(f"Verbosity in extra body: {self.config.llm_config.verbosity}")

        assert model_kwargs.get("max_tokens") <= model_metadata.output_token_limit, f"Max tokens ({model_kwargs['max_tokens']}) exceeds the model's {provider.value} -> `{model_name}` output token limit ({model_metadata.output_token_limit})"

        # reasoning kwargs
        reasoning_kwargs = self._get_reasoning_params(provider, model_name, model_metadata)
        model_kwargs.update(reasoning_kwargs)

        if "deep-research" in model_name:
            model_kwargs["request_timeout"] = 60 * 30  # 30 minutes

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
        if provider == LLMModelProvider.ANTHROPIC and self.config.tools and any(tool.tool_name.startswith("code_execution") for tool in self.config.tools):
            model_kwargs["betas"] = ["code-execution-2025-05-22"]

        if provider == LLMModelProvider.PERPLEXITY:
            model = ChatPerplexity(model=model_name, **model_kwargs)
        else:
            model = init_chat_model(
                model=model_name,
                model_provider=provider.value,
                **model_kwargs,
            )
        
        # import ipdb; ipdb.set_trace()
        return model, model_metadata

    def _prepare_messages(self, input_data: LLMNodeInputSchema, model_metadata: ModelMetadata) -> List[AnyMessage]:
        """Prepare messages using node config's thinking token settings."""
        messages = []
        current_messages = []

        ####
        def _extract_tool_call_ids(message: Any) -> List[str]:
            """Extract all unique tool call IDs from a message, handling both objects and dicts."""
            tool_ids = {}
            
            # Try accessing tool_calls directly (object attribute or dict key)
            for attr_name in ['tool_calls', 'additional_kwargs']:
                attr_val = getattr(message, attr_name, None) or (message.get(attr_name) if isinstance(message, dict) else None)
                tool_calls = attr_val
                if attr_val and attr_name == 'additional_kwargs':
                    tool_calls = attr_val.get('tool_calls', [])
                if tool_calls:
                    for call in tool_calls:
                        name = call.get('name', None)
                        if not name:
                            name = call.get('function', {}).get('name', None)
                        if name:
                            tool_ids[call.get('id')] = name
            
            return tool_ids
        ####

        last_tool_call_ids = {}
        
        added_images = set()
        if input_data.messages_history:
            # messages.extend(self._convert_messages(input_data.messages_history))
            # TODO: FIXME: probably don't need to convert past message histories to langchain types??
            messages.extend(input_data.messages_history)
            for message in input_data.messages_history:
                if isinstance(message, HumanMessage) and message.content and isinstance(message.content, list):
                    for content in message.content:
                        if content.get("type") == "image_url":
                            added_images.add(content.get("image_url", {}).get("url"))
        
            # Extract tool call IDs from the last message for potential tool response handling
            
            if messages:
                last_tool_call_ids = _extract_tool_call_ids(messages[-1])
                if last_tool_call_ids:
                    self.debug(f"Extracted tool call IDs from last message: {last_tool_call_ids}")

        elif input_data.system_prompt or self.config.default_system_prompt:
            # Don't add system prompt if messages_history is available
            messages.append(SystemMessage(content=input_data.system_prompt or self.config.default_system_prompt, id=str(uuid4())))
            current_messages.append(messages[-1])
        
        # print(added_images)
        # import ipdb; ipdb.set_trace()

        ###### # TOOL USE # ######

        last_tool_response_ids = set()
        missing_tool_responses = set()

        tool_outputs_to_add = []

        # Find out all valid tool response ids following a tool call in last message and handle any missing tool responses by assuming user skipped the tool call
        
        if input_data.tool_outputs:
            for i, tool_output in enumerate(input_data.tool_outputs):
                if isinstance(tool_output, BaseModel):
                    tool_output = tool_output.model_dump()
                tool_call_id = tool_output.get("tool_call_id", f"tool_output_{i}")
                if tool_call_id not in last_tool_call_ids:
                    self.debug(f"Skipping tool output {i} since it's not in last tool call ids: {tool_call_id} not in {last_tool_call_ids}")
                    continue
                last_tool_response_ids.add(tool_call_id)
                tool_outputs_to_add.append(tool_output)
        
        missing_tool_responses = {k:v for k, v in last_tool_call_ids.items() if k not in last_tool_response_ids}
        for tool_call_id, tool_call_name in missing_tool_responses.items():
            self.warning(f"Missing tool response ids: {missing_tool_responses}, assuming user skipped tool use")
            tool_outputs_to_add.append(
                ToolOutput(
                    tool_call_id=tool_call_id,
                    content="User skipped this tool use, please proceed accordingly.",
                    name=tool_call_name,
                    status="error",
                )
            )
        
        assert tool_outputs_to_add or (input_data.system_prompt or self.config.default_system_prompt) or input_data.user_prompt, "At least one of tool_outputs, system_prompt, or user_prompt must be provided to call the LLM!"
        
        if tool_outputs_to_add:
            assert model_metadata.tool_use, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support tool use!"
            tool_messages = []
            for i, tool_output in enumerate(tool_outputs_to_add):
                if isinstance(tool_output, BaseModel):
                    tool_output = tool_output.model_dump()
                if "content" not in tool_output:
                    raise ValueError(f"Tool output {i} must have a 'content' key! {tool_output}")
                tool_call_id = tool_output.get("tool_call_id", f"tool_output_{i}")
                if tool_call_id not in last_tool_call_ids:
                    self.debug(f"Skipping tool output {i} since it's not in last tool call ids: {tool_call_id} not in {last_tool_call_ids}")
                    continue
                last_tool_response_ids.add(tool_call_id)

                content = tool_output.get("content")
                error_message = tool_output.get("error_message")
                status = tool_output.get("status")
                if error_message:
                    # Clean tool output content
                    content = content if content else ""
                    if not isinstance(content, str):
                        content = str(content)

                    if content:
                        content += "\n\n"
                    if status:
                        content += f"Tool status: {status}\n"
                    content += f"Error: {error_message}"
                
                status = status if status else "success"

                tool_msg_content = {}
                if model_metadata.provider == LLMModelProvider.ANTHROPIC:
                    tool_msg_content["type"] = "tool_result"
                    tool_msg_content["tool_use_id"] = tool_call_id
                    tool_msg_content["content"] = content
                    

                    
                    # tool_msg_content = [tool_msg_content]

                    # tool_output_msg = {
                    #     "role": "user",
                    #     "content": tool_msg_content,
                    # }

                    tool_output_msg = tool_msg_content
                    
                    # tool_output_msg = HumanMessage(
                    #     content=tool_msg_content,  # NOTE: this can be a str or a list of str / dicts as per langchain!
                    #     # TODO: has to be in this similar format for eg:
                    #     # content=[
                    #     #     {'type': 'text', 'text': '\n\nHello, world! 👋 How can I assist you today?'}, 
                    #     #     {'type': 'reasoning_content', 'reasoning_content': {
                    #     #         'text': 'Okay, the user wrote "Hello, world!" That\'s a classic first program in many programming languages. Maybe they\'re just testing the chat or starting out with coding.\n\nI should respond warmly. Let me say hello back and ask how I can assist them today. Keep it friendly and open-ended to encourage them to ask questions or share what they need help with.\n', 
                    #     #         'signature': ''
                    #     #     }}
                    #     # ]
                    #     tool_call_id=tool_call_id,
                    #     id=tool_call_id,
                    #     name=tool_output.get("name", ""),
                    #     status=tool_output.get("status", "success"),
                    #     # **tool_msg_kwargs
                    # )
                elif model_metadata.provider == LLMModelProvider.OPENAI:
                    # tool_msg_content["type"] = "function_call_output"
                    # tool_msg_content["call_id"] = tool_call_id
                    # tool_msg_content["output"] = tool_output.get("content")
                    tool_output_msg = ToolMessage(
                        content=content,
                        tool_call_id=tool_call_id,
                        # NOTE: DEBUG: may end up replace tool call!
                        id=tool_call_id,
                        name=tool_output.get("name", ""),
                        status=status,
                    )

                tool_messages.append(
                    tool_output_msg
                )
            if model_metadata.provider == LLMModelProvider.ANTHROPIC:
                tool_messages = [{
                    "role": "user",
                    "type": "human",
                    "id": str(uuid4()),
                    "content": tool_messages
                }] if tool_messages else []
            # import ipdb; ipdb.set_trace()
            messages.extend(tool_messages)
            current_messages.extend(tool_messages)
        
        # Add user prompt if available after tool responses are added
        if input_data.user_prompt:  #  or input_data.image_input_url_or_base64  ?? Can images be added without a user prompt??  NOTE: this behaviour was removed since this value is not being set NULL by tool calls!
            # Prepare content for HumanMessage - handle both text and images
            content_parts = []
            
            # Add text content
            if input_data.user_prompt:
                content_parts.append({
                    "type": "text",
                    "text": input_data.user_prompt,
                })
            images = input_data.image_input_url_or_base64
            if images:
                if not isinstance(images, list):
                    images = [images]
                # Add images if available and not already added
                if images:
                    for image_url in images:
                        if image_url not in added_images:
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {"url": image_url},
                            })
                            added_images.add(image_url)
            
            # Create HumanMessage with appropriate content format
            if len(content_parts) == 1 and content_parts[0]["type"] == "text":
                # If only text, use string content for simplicity
                messages.append(HumanMessage(content=input_data.user_prompt, id=str(uuid4())))
            else:
                # If multiple parts or images, use list format
                messages.append(HumanMessage(content=content_parts, id=str(uuid4())))
            current_messages.append(messages[-1])
        # TODO: log warning if neither of user prompt or tool output provided!
        
        # import ipdb; ipdb.set_trace()
        # Use node config for thinking message handling
        messages = self._filter_thinking_messages(messages, keep=self.config.thinking_tokens_in_prompt)

      # import ipdb; ipdb.set_trace()

        return messages, current_messages
    
    def _apply_structured_output(self, model: Any, output_schema: Union[Type[BaseSchema], Dict[str, Any]], model_metadata: ModelMetadata) -> Any:
        """Apply structured output configuration to the model.

        Args:
            model: The LangChain chat model instance.
            output_schema: The Pydantic model or JSON schema dictionary to enforce.
            model_metadata: Metadata about the model's capabilities.

        Returns:
            The model instance with structured output configured.

        Raises:
            ValueError: If structured output configuration fails.
        """
        try:
            kwargs = {}
            # Langchain's with_structured_output determines method based on schema type (Pydantic or dict)
            # For OpenAI, we might still want to enforce strict mode if possible and schema is dict
            # TODO: Check if Langchain handles strict mode automatically for dict schemas with OpenAI
            if model_metadata.provider == LLMModelProvider.OPENAI:  #  and isinstance(output_schema, dict):
                #  kwargs["mode"] = "json"
                kwargs["strict"] = True # Strict is often implicit with JSON mode

            return model.with_structured_output(
                schema=output_schema,
                method="json_schema", # Let langchain infer method based on schema type
                include_raw=True,
                **kwargs
            )
        except Exception as e:
            self.critical("Failed to apply structured output to model")
            raise ValueError(f"Structured output configuration failed: {str(e)}") from e

    def _bind_tools(self, model: Any, model_metadata: ModelMetadata, registry: DBRegistry) -> Tuple[bool, RunnableBinding, List[Any], Dict[str, Any]]:
        """Bind tools from node config."""
        assert model_metadata.tool_use, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support tool use!"
        tools = []
        is_all_inbuild_tools = True
        has_code_execution_tool = False
        for tool_config in self.config.tools:
            tool_for_binding: Any
            if tool_config.is_provider_inbuilt_tool:
                if not model_metadata.inbuilt_tools or tool_config.tool_name not in model_metadata.inbuilt_tools:
                    raise ValueError(
                        f"Inbuilt tool '{tool_config.tool_name}' not supported by model "
                        f"{model_metadata.provider.value} -> `{model_metadata.model_name}` or not found in model metadata."
                    )
                
                tool = model_metadata.inbuilt_tools[tool_config.tool_name]
                if tool_config.tool_name.startswith("code_"):
                    has_code_execution_tool = True
                tool_class: Type[BaseProviderInternalTool] = tool["tool_class"]
                
                # Instantiate the tool with user_config if provided
                # The user_config from ToolConfig should be a dictionary that matches the tool's specific user_config Pydantic model
                # For example, if tool_class is OpenAIWebSearchTool, provider_inbuilt_user_config should match OpenAIWebSearchToolConfig
                tool_instance_kwargs = {}
                if tool_config.provider_inbuilt_user_config:
                    tool_instance_kwargs["user_config"] = tool_config.provider_inbuilt_user_config
                
                tool_object = tool_class(**tool_instance_kwargs)
                tool_for_binding = tool_object.get_tool()

            else:
                is_all_inbuild_tools = False
                # NOTE: will raise error if node not found or found node is not a tool node!
                tool_node: Type[BaseNode] = registry.get_node(tool_config.tool_name, tool_config.version, return_if_tool=True)
                if not tool_node:
                    raise ValueError(f"Tool {tool_config.tool_name} not found in registry")
                
                input_schema = tool_node.input_schema_cls
                if not input_schema:
                    raise ValueError(f"Tool {tool_config.tool_name} has no input schema!")
                
                # Change schema name to be equal to tool name!
                field_definitions = {}
                for k,v in input_schema.model_fields.items():
                    if BaseSchema._is_field_for_llm_tool_call(v):
                        # Create a new FieldInfo with default removed and is_required set to True
                        # This ensures LLM tools see all fields as required for proper tool calling
                        modified_field = v
                        # NOTE: hack for openai schemas since they don't support default, etc
                        if model_metadata.provider == LLMModelProvider.OPENAI:
                            # modified_field = copy(v)
                            # modified_field.default = PydanticUndefined  # Remove any default value
                            # modified_field.default_factory = PydanticUndefined  # Mark as required for LLM tool calls

                            annotation = v.annotation
                            # origin = get_origin(v.annotation)
                            # if origin is Union and any(arg is None for arg in get_args(v.annotation)):
                            #     annotation = [arg for arg in get_args(v.annotation) if arg is not None][0]
                            
                            # modified_field = FieldInfo(
                            #     # Don't pass any default value - this makes the field required
                            #     annotation=annotation,
                            #     description=v.description,
                            #     title=v.title,
                            #     examples=v.examples,
                            #     json_schema_extra=v.json_schema_extra,
                            #     metadata=v.metadata,
                            #     # Explicitly exclude default and default_factory to make field required
                            #     # All other field properties are preserved
                            # )
                        

                        field_definitions[k] = (v.annotation, modified_field)
                
                tool_for_binding = create_model(
                    tool_config.tool_name,
                    __base__=(BaseNodeConfig if model_metadata.provider == LLMModelProvider.OPENAI else BaseSchema),
                    __doc__=input_schema.__doc__,
                    __module__=input_schema.__module__,  # module_name or 
                    # Only bind user editable fields, hide other fields!
                    **field_definitions
                )
                if model_metadata.provider == LLMModelProvider.OPENAI:
                    def convert_to_openai_tool_internal(schema: Dict[str, Any]) -> Dict[str, Any]:
                        if "name" not in schema:
                            name = schema.get("title", None)
                        else:
                            name = schema.get("name", None)
                        
                        schema["additionalProperties"] = False
                        {
                            "name": name,
                            "parameters": schema,
                            "strict": False,  # DEBUG: STRICT
                            "type": "function",
                            "description": schema.get("description", None),
                        }
                        return schema
                        
                        # openai_tool = {"type": "function"}
                        # function = {}
                        # if "name" not in schema:
                        #     name = schema.pop("title", None)
                        # else:
                        #     name = schema.pop("name", None)
                        # function["description"] = schema.pop("description", None)
                        # function["strict"] = True

                        # schema["additionalProperties"] = False
                        # # openai_tool["additionalProperties"] = False
                        # function["parameters"] = schema

                        # function_format = {"type": "function", "function": function}

                        # tool_format = {**openai_tool, **function}

                        # # tool_format["function"] = {"strict": True, "name": function["name"], 
                        # #                         #    "description": function["description"], "parameters": function["parameters"]
                        # #                            }

                        # # tool_format_with_function = deepcopy(tool_format)
                        # # tool_format_with_function["function"] = function
                        # # function = deepcopy(function)
                        # return tool_format

                        # # return tool_format
                    
                    json_schema = LLMStructuredOutputSchema._recursive_set_json_schema_to_openai_format(tool_for_binding.model_json_schema())
                    if "title" in json_schema:
                        json_schema["title"] = tool_config.tool_name
                    if "name" in json_schema:
                        json_schema["name"] = tool_config.tool_name
                    tool_for_binding = convert_to_openai_tool_internal(json_schema)
                    
                ##### tool_for_binding = input_schema
            
            tools.append(tool_for_binding)
        
        kwargs = {}
        if self.config.tool_calling_config.tool_choice:
            assert self.config.tool_calling_config.tool_choice in model_metadata.tool_choice, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support tool choice!"
            kwargs["tool_choice"] = self.config.tool_calling_config.tool_choice
        if self.config.tool_calling_config.parallel_tool_calls:
            assert model_metadata.parallel_tool_calling_configurable, f"Model {model_metadata.provider.value} -> `{model_metadata.model_name}` does not support parallel tool calling!"
            kwargs["parallel_tool_calls"] = self.config.tool_calling_config.parallel_tool_calls

        return has_code_execution_tool, is_all_inbuild_tools, model.bind_tools(tools=tools, **kwargs), tools, kwargs

    async def _execute_model(self, model: Any, messages: List[AnyMessage], model_metadata: ModelMetadata, ext_context: "ExternalContextManager", app_context, has_code_execution_tool: bool, **kwargs) -> Any:
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
        # print(json.dumps([m.model_dump(mode="json") if isinstance(m, BaseModel) else m for m in messages], indent=4))
        # import ipdb; ipdb.set_trace()

        # web_search_options = None
        invoke_kwargs = kwargs
        
        # NOTE: this arg is not supported by some langchain integrations with providers, eg: perplexity
        # invoke_kwargs["max_concurrency"] = 50
        # import ipdb; ipdb.set_trace()
        # from asyncio import shield
        
        # Extract necessary info for billing
        user = app_context.get("user")  # : Optional[User]
        run_job = app_context.get("workflow_run_job")  # : Optional[WorkflowRunJobCreate]
        org_id = run_job.owner_org_id
        
        # Calculate estimated cost and allocate credits before model execution
        estimated_cost = 0.0
        allocated_credits = 0.0
        
        if self.billing_mode:
            # Calculate estimated cost
            estimated_cost = self._calculate_estimated_cost(
                messages=messages,
                provider=self.config.llm_config.model_spec.provider,
                model_name=self.config.llm_config.model_spec.model,
                max_output_tokens=self.config.llm_config.max_tokens
            )

            extra_tool_costs = 0.0
            if has_code_execution_tool:
                extra_tool_costs = model_metadata.code_execution_tool_cost
            
            # Allocate credits based on estimated cost
            from kiwi_app.billing.models import CreditType
            async with get_async_db_as_manager() as db_session:
                metadata = {
                    "model_name": self.config.llm_config.model_spec.model,
                    "provider": self.config.llm_config.model_spec.provider.value,
                }
                if extra_tool_costs > 0:
                    metadata["extra_tool_costs"] = extra_tool_costs
                await ext_context.billing_service.allocate_credits_for_operation(
                    db=db_session,
                    org_id=org_id,
                    user_id=user.id,
                    operation_id=run_job.run_id,
                    credit_type=CreditType.DOLLAR_CREDITS,
                    estimated_credits=estimated_cost + extra_tool_costs,
                    event_type="llm_token_usage__allocation",
                    metadata=metadata
                )
            allocated_credits = estimated_cost
            self.info(f"Allocated ${allocated_credits:.6f} credits for LLM call")
        
        if "extra_body" in invoke_kwargs:
            # TODO: migrate this to using model_kwargs or directly providing this to model init!
            response = await asyncio.to_thread(model.invoke, messages, **invoke_kwargs)
        else:
            message = None
            async for chunk in model.astream(messages, **invoke_kwargs):
                if not message:
                    message = chunk
                else:
                    message += chunk
            message = message_chunk_to_message(message)
            if "raw" in message:
                message["raw"] = message_chunk_to_message(message["raw"])
            # import ipdb; ipdb.set_trace()
            response = message
        
        return (response, allocated_credits)
        # return await asyncio.to_thread(model.invoke, messages, **invoke_kwargs)
        # return await shield(model.ainvoke)(messages, **invoke_kwargs)
    
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
    
    async def _parse_response(
        self,
        original_response: Any,
        message_history: List[AnyMessage],
        current_messages: List[AnyMessage],
        latency: float,
        output_schema: Union[Type[BaseSchema], Dict[str, Any], None],
        model_metadata: ModelMetadata,
        app_context: Optional[Dict[str, Any]] = None,
        ext_context: "ExternalContextManager" = None,
        allocated_credits: float = 0.0,
    ) -> LLMNodeOutputSchema:
        """Parse response, handle structured output validation/parsing, and format the final output.

        Handles both Pydantic model parsing and JSON schema validation.
        https://python.langchain.com/docs/how_to/response_metadata/

        NOTE: reasoning mode with JSON mode in Fireworks:
        https://docs.fireworks.ai/structured-responses/structured-response-formatting#reasoning-model-json-mode
        """

        
        # Determine if the model actually made tool calls (excluding potential internal structured output calls)
        # import ipdb; ipdb.set_trace()
        
        
        # Get actual response object
        if self.config.output_schema.is_output_str():
            response = original_response
        else:
            response = original_response["raw"] if isinstance(original_response, dict) and "raw" in original_response else original_response
        
        
        # Tool Calls
        filtered_tool_calls = []
        schema_tool_call = None
        schema_name_to_filter = None
        if output_schema:
            if isinstance(output_schema, dict):
                schema_name_to_filter = output_schema.get("title", output_schema.get("$id", None))
            else:
                schema_name_to_filter = output_schema.__name__
        
        if hasattr(response, 'tool_calls') and response.tool_calls:
            # TODO: change this behaviour for only Anthropic which uses tool calls for structured responses!
            # We filter here ONLY if a structured output schema was provided.
            # If output_schema is None, we assume any tool call is a legitimate external tool call.
            
            if schema_name_to_filter:
                 filtered_tool_calls = [t for t in response.tool_calls if t["name"] != schema_name_to_filter]
                 schema_tool_call = [t for t in response.tool_calls if t["name"] == schema_name_to_filter]
                 schema_tool_call = schema_tool_call[0] if schema_tool_call else None
            else:
                 filtered_tool_calls = response.tool_calls # Keep all if no structured output or JSON schema
                
            # Filter out tool calls that don't have a name
            filtered_tool_calls = [t for t in filtered_tool_calls if "name" in t and t["name"]]

        # import ipdb; ipdb.set_trace()

        # print(response.model_dump_json(indent=4) if isinstance(response, BaseModel) else response)
        # import ipdb; ipdb.set_trace()
        

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
        usage_metadata = getattr(response, "usage_metadata", {})
        if not response_metadata:
            response_metadata = usage_metadata
        else:
            response_metadata = {**response_metadata, **usage_metadata} if (usage_metadata and isinstance(usage_metadata, dict)) else response_metadata
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
            # {'input_tokens': 10, 'output_tokens': 269, 'total_tokens': 279, 'reasoning_tokens': 0, 'cached_tokens': 0}
            token_usage=normalized_metadata["token_usage"] if normalized_metadata else None,
            finish_reason=normalized_metadata["finish_reason"] if normalized_metadata else None,
            # cached=self.config.cache_responses)
        )

        # After model execution, calculate actual cost and adjust if billing is enabled
        if self.billing_mode and response:
            try:
                user = app_context.get("user")
                run_job = app_context.get("workflow_run_job")
                org_id = run_job.owner_org_id
                if metadata.token_usage:
                    # Calculate actual cost
                    actual_cost = self._calculate_actual_cost(
                        token_usage=metadata.token_usage,
                        provider=self.config.llm_config.model_spec.provider,
                        model_name=self.config.llm_config.model_spec.model,
                        model_metadata=model_metadata,
                    )

                    # Add a markup factor for LLM token costs
                    actual_cost = actual_cost * settings.LLM_TOKEN_COST_MARKUP_FACTOR
                    
                    # Adjust allocated credits with actual cost
                    from kiwi_app.billing.models import CreditType
                    async with get_async_db_as_manager() as db_session:
                        await ext_context.billing_service.adjust_allocated_credits(
                            db=db_session,
                            org_id=org_id,
                            user_id=user.id,
                            operation_id=run_job.run_id,
                            credit_type=CreditType.DOLLAR_CREDITS,
                            allocated_credits=allocated_credits,
                            actual_credits=actual_cost,
                            event_type="llm_token_usage__adjustment",
                            metadata={
                                "model_name": self.config.llm_config.model_spec.model,
                                "provider": self.config.llm_config.model_spec.provider.value,
                                "token_usage": metadata.token_usage,
                            }
                        )
                    self.info(f"Adjusted credits: allocated=${allocated_credits:.6f}, actual=${actual_cost:.6f}, difference=${actual_cost - allocated_credits:.6f}")
                else:
                    self.warning("No token usage found in response metadata for credit adjustment!")
            except Exception as e:
                self.warning(f"Error adjusting allocated credits: {str(e)}")
                # Continue processing even if billing adjustment fails

        # Handle tool calls
        tool_calls = []
        if filtered_tool_calls:
            tool_calls = [
                ToolCall(
                    tool_name=call['name'],
                    tool_input=call['args'],
                    tool_id=call.get('id')  #  or call.get('tool_id')
                ) for call in filtered_tool_calls
            ]
            """
            Gemini sample tool calls: [{'name': 'llmStructuredOutputSchema', 'args': {'content': 'Four', 'metadata': ['The user asked for the sum of 2+2.', 'The result is 4.', 'The user requested the answer in one word.', "The word for 4 is 'Four'."]}, 'id': 'd9cbb3a1-f1e5-4566-a8c3-734b30366eae', 'type': 'tool_call'}]

            """
        # import ipdb; ipdb.set_trace()
        # Handle structured output
        # TODO: FIXME: Assumes that tool response and structured outputs can't both happen at once!
        
        # Populate RAW TEXT
        raw_text = response.content
        # import ipdb; ipdb.set_trace()
        try:
            content = response.content
            if not isinstance(content, list):
                content = [content]
            last_text = None
            concatenated_text = ""
            for item in content:
                if not isinstance(item, dict):
                    if isinstance(item, str) and item:
                        last_text = item
                        concatenated_text = concatenated_text + last_text
                elif "text" in item:
                    last_text = item["text"]
                    if item.get("type", None) == "text":
                        concatenated_text = concatenated_text + last_text
            raw_text = concatenated_text or last_text or raw_text
        except Exception as e:
            pass

        structured_output = None
        if not filtered_tool_calls:
            if not self.config.output_schema.is_output_str():
                try:
                    # NOTE: parsing non-list content probably woudn't be neccessary and should be the same attempt as the result in `parsed` key below!
                    if schema_tool_call:
                        parsed_json_data = schema_tool_call.get("args", {})
                    else:
                        parsed_json_data = json.loads(raw_text)
                    
                    structured_output = parsed_json_data
                    if issubclass(output_schema, BaseModel):
                        structured_output = output_schema.model_validate(parsed_json_data)
                    else:
                        jsonschema.validate(instance=parsed_json_data, schema=output_schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
                except Exception as e:
                    pass
                    # logger.warning(f"Error parsing structured output: {e}")
                structured_output = structured_output or (original_response["parsed"] if isinstance(original_response, dict) and ((not original_response.get("parsing_error", None)) and "parsed" in original_response) else None)
                structured_output = structured_output.model_dump() if isinstance(structured_output, BaseModel) else structured_output
                if not structured_output:
                    raise ValueError("No structured output found in LLM response!")
                
        
        # Filter Response object, mainly for Anthropic to filter out unneccessary tool calls
        # TODO: change this behaviour for only Anthropic which uses tool calls for structured responses!
        try:
            if hasattr(response, "content"):  #  and model_metadata.provider == LLMModelProvider.ANTHROPIC
                
                filtered_tool_calls = []
                for t in response.tool_calls:
                    if "name" in t and t["name"] and t["name"] != schema_name_to_filter:
                        filtered_tool_calls.append(t)
                response.tool_calls = filtered_tool_calls
                
                if isinstance(response.content, list):
                    filtered_content = []
                    for t in response.content:
                        if (not isinstance(t, dict)) or "name" not in t or t["name"] != schema_name_to_filter:
                            if isinstance(t, dict):
                                # Filter out tool use messages that don't have a name
                                if ("type" in t and t["type"] == "tool_use") and ("name" not in t or (not t["name"])):
                                    continue
                            filtered_content.append(t)
                        else:
                            temp_text_content = t
                            if isinstance(t, dict):
                                temp_text_content = t.get('input')
                                temp_text_content = temp_text_content or t.get('partial_json')
                                temp_text_content = temp_text_content or t.get('json')
                            temp_text_content = str(temp_text_content)
                            # NOTE: this is a hack to include structured output tool call for Anthropic primarily
                            # This could create issues since below content doesn't have any role, etc but should be fine since response should be of type AIMessage!
                            # Try to remove this hack and see if just keepint this with partial_json key etc as original doesn't create a new tool call msg!
                            filtered_content.append({'type': 'text', 'text': temp_text_content})
                    response.content = filtered_content
                
        except Exception as e:
            pass
        # import ipdb; ipdb.set_trace()
        
        current_messages=current_messages + (response if isinstance(response, list) else [response])
        metadata.iteration_count = self._get_iteration_count(message_history + current_messages)
        # import ipdb; ipdb.set_trace()
        web_search_result = LLMNode._parse_search_results(model_metadata, response) or LLMNode._parse_citations_from_response(model_metadata, response)
        
        # Parse agent actions from additional_kwargs
        agent_actions = LLMNode._parse_agent_actions(response)
        
        # Web Searches billing
        # TODO: potentially estimate web searches in pre allocation credits??
        citation_count = len(web_search_result.citations) if web_search_result else 0
        if self.billing_mode and response and citation_count > 0:
            try:
                user = app_context.get("user")
                run_job = app_context.get("workflow_run_job")
                org_id = run_job.owner_org_id
                estimated_credits = citation_count // settings.WEB_SEARCH_NUM_CITATIONS_PER_CREDIT
                # Adjust allocated credits with actual cost
                from kiwi_app.billing.models import CreditType
                from kiwi_app.billing.schemas import CreditConsumptionRequest
                async with get_async_db_as_manager() as db_session:
                    await ext_context.billing_service.consume_credits(
                        db=db_session,
                        org_id=org_id,
                        user_id=user.id,
                        consumption_request=CreditConsumptionRequest(
                            credit_type=CreditType.WEB_SEARCHES,
                            credits_consumed=estimated_credits,
                            event_type="web_search",
                            metadata={
                                "model_name": self.config.llm_config.model_spec.model,
                                "provider": self.config.llm_config.model_spec.provider.value,
                                "citation_count": citation_count,
                            },
                        ),
                    )
                self.info(f"Consumed estimated web search credits: allocated (type web search) ={estimated_credits:.6f}")
            except Exception as e:
                self.warning(f"Error adjusting allocated web search credits: {str(e)}")

        tool_call_count = len(tool_calls) if tool_calls else 0
        metadata.tool_call_count = tool_call_count

        if self.config.output_schema.is_output_str() and not tool_calls:
            if not raw_text:
                raise ValueError("No raw text response found in LLM response!")



        return LLMNodeOutputSchema(
            current_messages=current_messages,
            content=response.content,
            text_content=raw_text,
            metadata=metadata,
            structured_output=structured_output,
            tool_calls=tool_calls or None,
            web_search_result=web_search_result,
            agent_actions=agent_actions,
        )

    @staticmethod
    def _parse_citations_from_response(model_metadata: ModelMetadata, response: Any) -> Optional[WebSearchResult]:
        """
        Parse citations from the model response.
        
        Args:
            model_metadata: Model metadata
            response: The model response object
            
        Returns:
            WebSearchResult object with parsed citations or None if no citations found
        """
        # if not model_metadata.web_search:
        #     return None
            
        citations = []
        
        # Handle response content with citations
        response = response["raw"] if isinstance(response, dict) and "raw" in response else response
        if hasattr(response, 'content'):
            content = response.content
            if not isinstance(content, list):
                content = [content]
            for content_item in content:
                 if not isinstance(content_item, dict):
                     continue
                 if 'citations' in content_item:
                    for citation in content_item['citations']:
                        if citation.get('type') == 'web_search_result_location':
                            citations.append(
                                Citation(
                                    url=citation.get('url'),
                                    title=citation.get('title'),
                                    snippet=citation.get('cited_text'),
                                    timestamp=None,
                                    metadata=None,
                                )
                            )
                 if 'annotations' in content_item:
                    for annotation in content_item['annotations']:
                        if annotation.get('type') == 'url_citation':
                            snippet = None
                            if 'start_index' in annotation and 'end_index' in annotation:
                                snippet = f"index-{annotation.get('start_index')}-{annotation.get('end_index')}"
                            citations.append(
                                Citation(
                                    url=annotation.get('url'),
                                    title=annotation.get('title'),
                                    snippet=snippet,  # Annotations don't provide snippets
                                    timestamp=None,
                                    metadata=annotation  # Store full annotation as metadata
                                )
                            )
        return WebSearchResult(citations=citations) if citations else None
    
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
        web_search_result = WebSearchResult(
            citations=citations,
            search_metadata=additional_kwargs.get('search_metadata')
        )
        if not (web_search_result.citations or web_search_result.search_metadata):
            return None
        return web_search_result

    @staticmethod
    def _parse_agent_actions(response: Any) -> Optional[List[AgentAction]]:
        """
        Parse agent actions from the model response.
        
        Args:
            response: The model response object
            
        Returns:
            List of AgentAction objects or None if no agent actions found
        """
        # Get additional_kwargs from response, handling different response structures
        additional_kwargs = None
        if hasattr(response, 'additional_kwargs'):
            additional_kwargs = response.additional_kwargs
        elif isinstance(response, dict) and 'raw' in response and hasattr(response['raw'], 'additional_kwargs'):
            additional_kwargs = response['raw'].additional_kwargs
        
        if not additional_kwargs:
            return None
            
        # Check for tool_outputs in additional_kwargs
        tool_outputs = additional_kwargs.get('tool_outputs', [])
        if not tool_outputs:
            return None
            
        agent_actions = []
        for tool_output in tool_outputs:
            try:
                agent_action = AgentAction(
                    id=tool_output.get('id', ''),
                    index=tool_output.get('index', 0),
                    action=tool_output.get('action', {}),
                    type=tool_output.get('type', ''),
                    status=tool_output.get('status', '')
                )
                agent_actions.append(agent_action)
            except Exception as e:
                # Skip malformed agent actions
                continue
        
        return agent_actions if agent_actions else None

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
    
    @staticmethod
    def get_attr_or_key(obj: Any, key: str) -> Any:
        """Get the attribute or key from the object."""
        dict_val = obj.get(key, None) if isinstance(obj, dict) else None
        return getattr(obj, key, dict_val)
    
    @staticmethod
    def msg_is_types(msg: AnyMessage, types: List[str] = THINKING_MESSAGE_TYPES) -> bool:  # REDACED_THINKING_MESSAGE_TYPES
        """Check if the message type is in the list of types."""
        msg_type = LLMNode.get_attr_or_key(msg, "type")
        return msg_type in types

    def _filter_thinking_messages(self, messages: List[AnyMessage], keep: Literal[ThinkingTokensInPrompt.ALL, ThinkingTokensInPrompt.LATEST, ThinkingTokensInPrompt.NONE] = ThinkingTokensInPrompt.ALL) -> List[AnyMessage]:
        """Filter out thinking messages from the message list."""
        def filter_out_messages_of_type(messages: List[AnyMessage], types: List[str] = THINKING_MESSAGE_TYPES, perform_filter: bool = True) -> List[AnyMessage]:
            filtered_messages = []
            last_filtered_message_idx = None
            for i, message in enumerate(messages):
                content = LLMNode.get_attr_or_key(message, "content")
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
                    if not LLMNode.msg_is_types(sub_message, types):
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

    def _get_iteration_count(self, messages: List[AnyMessage]) -> int:
        """Get the iteration count from the messages."""
        return len([m for m in messages if LLMNode.msg_is_types(m, AI_MESSAGE_TYPES)])

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
                    "output_tokens": int,
                    "input_tokens": int,
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
            # For OpenAI, token usage is directly in raw_metadata with the new format
            token_usage = {
                "input_tokens": raw_metadata.get("input_tokens", 0),
                "output_tokens": raw_metadata.get("output_tokens", 0),
                "total_tokens": raw_metadata.get("total_tokens", 0),
                "reasoning_tokens": raw_metadata.get("output_token_details", {}).get("reasoning", 0),
                "cached_tokens": raw_metadata.get("input_token_details", {}).get("cache_read", 0),
                "audio_input_tokens": raw_metadata.get("input_token_details", {}).get("audio", 0),
                "audio_output_tokens": raw_metadata.get("output_token_details", {}).get("audio", 0)
            }
        elif provider == LLMModelProvider.ANTHROPIC:
            # For Anthropic, the token usage data is directly in raw_metadata, not nested under 'usage'
            token_usage = {
                "input_tokens": raw_metadata.get("input_tokens", 0),
                "output_tokens": raw_metadata.get("output_tokens", 0),
                "total_tokens": raw_metadata.get("total_tokens", 0),
                "reasoning_tokens": 0,  # Anthropic doesn't report reasoning tokens in this format
                "cache_creation_input_tokens": raw_metadata.get("input_token_details", {}).get("cache_creation", 0),
                "cached_tokens": raw_metadata.get("input_token_details", {}).get("cache_read", 0)
            }
        elif provider == LLMModelProvider.GEMINI:
            usage = raw_metadata.get("usage_metadata", {}) or {}
            token_usage = {
                "input_tokens": usage.get("prompt_token_count", 0),
                "output_tokens": usage.get("candidates_token_count", 0),
                "total_tokens": usage.get("total_token_count", 0),
                "cached_tokens": usage.get("cached_content_token_count", 0),
                "reasoning_tokens": 0  # Gemini doesn't report reasoning tokens
            }
        elif provider == LLMModelProvider.AWS_BEDROCK:
            usage = raw_metadata.get("usage", {}) or {}
            token_usage = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                "reasoning_tokens": 0,  # Bedrock doesn't report reasoning tokens
                "cached_tokens": 0
            }
        elif provider in [LLMModelProvider.FIREWORKS]:  # LLMModelProvider.MISTRALAI, 
            token_usage = raw_metadata.get("token_usage", {}) or {}
            if "total_tokens" not in token_usage:
                token_usage["total_tokens"] = token_usage.get("input_tokens", 0) + token_usage.get("output_tokens", 0)
            token_usage.update({
                "reasoning_tokens": 0,  # These providers don't report reasoning tokens
                "cached_tokens": 0
            })
        elif provider == LLMModelProvider.PERPLEXITY:
            usage = raw_metadata
            token_usage = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
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

    @staticmethod
    def map_model_to_tokencost_format(provider: LLMModelProvider, model_name: str) -> str:
        """
        Map our internal model names to tokencost library format.
        
        The tokencost library expects model names in the format:
        - OpenAI: model names as-is (e.g., "gpt-4o", "o1-mini")
        - Anthropic: with "anthropic/" prefix (e.g., "anthropic/claude-3-5-sonnet-20241022")
        - Google: with "google/" or "gemini/" prefix (e.g., "google/gemini-2.0-flash-thinking-exp-01-21")
        - AWS Bedrock: with "bedrock/" prefix (e.g., "bedrock/us.deepseek.r1-v1:0")
        - Perplexity: with "perplexity/" prefix (e.g., "perplexity/sonar-deep-research")
        - Fireworks: not directly supported, but we can try with the model name as-is
        
        Args:
            provider: The model provider
            model_name: Our internal model name
            
        Returns:
            str: Model name in tokencost format
        """
        # Map provider to tokencost prefix
        provider_prefixes = {
            # LLMModelProvider.OPENAI: "",  # OpenAI models don't need prefix
            # LLMModelProvider.ANTHROPIC: "anthropic/",
            # LLMModelProvider.GEMINI: "google/",  # or "gemini/" - we'll try both
            LLMModelProvider.AWS_BEDROCK: "bedrock/",
            LLMModelProvider.PERPLEXITY: "perplexity/",
            LLMModelProvider.FIREWORKS: "",  # Fireworks models might not be supported
        }
        
        prefix = provider_prefixes.get(provider, "")
        
        # # Special handling for certain providers
        # if provider == LLMModelProvider.GEMINI:
        #     # Try to match Gemini model names to tokencost format
        #     # Some models use "gemini/" prefix, others use "google/"
        #     if "gemini" in model_name.lower():
        #         # For models like "gemini-2.0-flash-thinking-exp-01-21"
        #         return f"gemini/{model_name}"
        #     else:
        #         # For other Google models
        #         return f"google/{model_name}"
        if provider == LLMModelProvider.AWS_BEDROCK:
            # AWS Bedrock models might need region prefix
            # For now, just use the model name with bedrock/ prefix
            return f"{prefix}{model_name}"
        else:
            # Standard case - just add the prefix
            return f"{prefix}{model_name}"

    def _calculate_estimated_cost(
        self, 
        messages: List[AnyMessage], 
        provider: LLMModelProvider,
        model_name: str,
        max_output_tokens: Optional[int] = None
    ) -> float:
        """
        Calculate estimated cost for the LLM call.
        
        Args:
            messages: List of messages to send to the model
            provider: Model provider
            model_name: Model name
            max_output_tokens: Maximum number of output tokens (for estimation)
            
        Returns:
            float: Estimated cost in USD
        """
        try:

            # Deep research models have a higher cost for single research report!
            deep_research_fallback_costs = {
                LLMModelProvider.OPENAI: 1.,
                LLMModelProvider.ANTHROPIC: 1.,
                LLMModelProvider.GEMINI: 1.,
                # LLMModelProvider.AWS_BEDROCK: 0.5,
                LLMModelProvider.PERPLEXITY: 0.5,
                # LLMModelProvider.FIREWORKS: 0.5,
            }
            if "deep-research" in model_name:
                return deep_research_fallback_costs.get(provider, 0.5)
            
            # Map model to tokencost format
            tokencost_model = self.map_model_to_tokencost_format(provider, model_name)
            
            # Calculate prompt cost
            # Convert messages to format expected by tokencost
            prompt_messages = []
            system_message = None
            for i, msg in enumerate(messages):
                if isinstance(msg, dict):
                    prompt_messages.append(msg)
                else:
                    # Convert LangChain message to dict format
                    msg_dict = {
                        "role": msg.type,
                        "content": msg.content if hasattr(msg, 'content') else str(msg)
                    }
                    # Map role names
                    role_mapping = {
                        "human": "user",
                        "chat": "user",
                        "ai": "assistant",
                        "system": "system",
                        "tool": "tool",
                        "function": "function"
                    }
                    msg_dict["role"] = role_mapping.get(msg_dict["role"], msg_dict["role"])
                    if msg_dict["role"] == "system":
                        system_message = (i, msg_dict["content"])
                    prompt_messages.append(msg_dict)
            
            # Calculate prompt cost
            if provider == LLMModelProvider.ANTHROPIC:
                kwargs = {}
                if system_message:
                    prompt_messages.pop(system_message[0])
                    if system_message[1]:
                        kwargs = {
                            "system": system_message[1]
                        }
                # self.info(f"messages: {json.dumps(prompt_messages, indent=2)}, kwargs_system: {kwargs.get('system', None)}")
                input_tokens = anthropic.Anthropic().beta.messages.count_tokens(
                        model=model_name,
                        messages=prompt_messages,
                        **kwargs,
                    ).input_tokens
                prompt_cost =  calculate_cost_by_tokens(input_tokens, tokencost_model, "input")
            else:
                try:
                    prompt_cost = calculate_prompt_cost(prompt_messages, tokencost_model)
                except Exception as e:
                    self.info(f"Error calculating prompt cost via direct messages: {str(e)} \n\n; converting to string and trying again...")
                    prompt_cost = calculate_prompt_cost(str(prompt_messages), tokencost_model)
            
            # Estimate completion cost based on max_output_tokens or a default
            if max_output_tokens is None:
                max_output_tokens = 1000  # Default estimate
            
            approx_output_tokens = max_output_tokens // 2
            completion_cost =  calculate_cost_by_tokens(approx_output_tokens, tokencost_model, "output")
            
            # Total estimated cost
            estimated_cost = prompt_cost + completion_cost

            estimated_cost = float(estimated_cost)
            
            self.info(f"Estimated token cost for {provider.value}/{model_name}: ${estimated_cost:.6f}")
            return estimated_cost
            
        except Exception as e:
            self.warning(f"Error calculating token cost: {str(e)}")
            # Fallback to a conservative estimate based on provider
            fallback_costs = {
                LLMModelProvider.OPENAI: 0.002,
                LLMModelProvider.ANTHROPIC: 0.003,
                LLMModelProvider.GEMINI: 0.001,
                LLMModelProvider.AWS_BEDROCK: 0.002,
                LLMModelProvider.PERPLEXITY: 0.001,
                LLMModelProvider.FIREWORKS: 0.001,
            }
            
            return fallback_costs.get(provider, 0.001)

    def _calculate_actual_cost(
        self,
        token_usage: Dict[str, Any],
        provider: LLMModelProvider,
        model_name: str,
        model_metadata: ModelMetadata,
    ) -> float:
        """
        Calculate actual cost based on token usage from the response.
        
        Args:
            token_usage: Token usage dict with input_tokens, output_tokens, etc.
            provider: Model provider
            model_name: Model name
            model_metadata: Model metadata
        Returns:
            float: Actual cost in USD
        """
        try:
            # Map model to tokencost format
            tokencost_model = self.map_model_to_tokencost_format(provider, model_name)
            
            # Get token counts
            input_tokens = token_usage.get("input_tokens", 0)
            output_tokens = token_usage.get("output_tokens", 0)
            cached_tokens = token_usage.get("cached_tokens", 0)

            if provider == LLMModelProvider.PERPLEXITY:
                cached_tokens = 0

            if provider == LLMModelProvider.PERPLEXITY and "deep-research" in model_name:
                # https://docs.perplexity.ai/guides/pricing
                # Perplexity doesn't report reasoning tokens, so we need to add them manually
                reasoning_tokens = token_usage.get("reasoning_tokens", 0)
                citation_tokens = token_usage.get("citation_tokens", 0)
                if not citation_tokens:
                    # rough estimation!
                    citation_tokens = 5 * output_tokens
                if not reasoning_tokens:
                    # rough estimation!
                    reasoning_tokens = 10 * output_tokens
                input_tokens = input_tokens + reasoning_tokens * 1.5 + citation_tokens
                # TODO: add citation tokens!
                # TODO: add web search tool calls!

            input_tokens = input_tokens - cached_tokens
            # TODO: adjust input tokens cost based on cached tokens!
            #     also add anthropic cache creation costs!
            cached_input_tokens_cost = 0.
            if provider != LLMModelProvider.PERPLEXITY:
                try:
                    cached_input_tokens_cost = calculate_cost_by_tokens(cached_tokens, tokencost_model, "cached")
                    cached_input_tokens_cost = float(cached_input_tokens_cost)
                except Exception as e:
                    if model_metadata.cached_token_price_per_M > 0.:
                        cached_input_tokens_cost = model_metadata.cached_token_price_per_M * cached_tokens / 1000000.
                    else:
                        raise e
            # adjusted_input_tokens = input_tokens - cached_tokens
            # adjusted_input_tokens_cost = calculate_cost_by_tokens(adjusted_input_tokens, tokencost_model, "input")
            # adjusted_actual_cost = actual_cost + adjusted_input_tokens_cost + output_tokens_cost
            
            # TODO: add cached tokens costs!
            try:
                input_tokens_cost = calculate_cost_by_tokens(input_tokens, tokencost_model, "input")
                input_tokens_cost = float(input_tokens_cost)
            except Exception as e:
                if model_metadata.input_token_price_per_M > 0.:
                    input_tokens_cost = model_metadata.input_token_price_per_M * input_tokens / 1000000.
                else:
                    raise e

            try:
                output_tokens_cost = calculate_cost_by_tokens(output_tokens, tokencost_model, "output")
                output_tokens_cost = float(output_tokens_cost)
            except Exception as e:
                if model_metadata.output_token_price_per_M > 0.:
                    output_tokens_cost = model_metadata.output_token_price_per_M * output_tokens / 1000000.
                else:
                    raise e
            
            actual_cost = input_tokens_cost + output_tokens_cost + cached_input_tokens_cost

            actual_cost = float(actual_cost)
            
            self.info(f"Actual token cost for {provider.value}/{model_name}: ${actual_cost:.6f}")
            return actual_cost
            
        except Exception as e:
            self.error(f"Error calculating actual token cost: {str(e)}", exc_info=True)
            return 0.0
