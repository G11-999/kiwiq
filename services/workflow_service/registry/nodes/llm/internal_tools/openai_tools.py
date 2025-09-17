from abc import ABC
import json
from pydantic import BaseModel, HttpUrl, field_validator, Field
from typing import Optional, Union, ClassVar, Literal
import re

from workflow_service.registry.nodes.llm.internal_tools.internal_base import BaseProviderInternalTool, UserLocation

class BaseOpenAITool(BaseProviderInternalTool, ABC):
    """Base class for OpenAI tools."""
    # provider_name: ClassVar[LLMModelProvider] = LLMModelProvider.OPENAI
    
    def get_tool(self):
        tool = {
            "type": self.type,
        }
        if self.user_config:
            tool.update(self.user_config.model_dump(mode="json", exclude_none=True))
        return tool
    

class OpenAIWebSearchToolConfig(BaseModel):
    """Configuration schema for OpenAI web search tool.
    
    Attributes:
        max_results: Maximum number of search results to return
        allowed_domains: List of domains to restrict search results to
        blocked_domains: List of domains to exclude from search results
        recency_days: Only include results from the past N days
        region: Geographic region to use for search results
    """
    user_location: Optional[UserLocation] = None
    search_context_size: Optional[Literal["high", "medium", "low"]] = Field(
        default=None,
        description="Controls the amount of context used for search results. "
                   "high: Most comprehensive context, highest cost, slower response. "
                   "medium: Balanced context, cost, and latency. "
                   "low: Least context, lowest cost, fastest response, but potentially lower answer quality."
    )


class OpenAIWebSearchTool(BaseOpenAITool):
    """OpenAI web search tool.
    
    This tool allows GPT models to search the web for information.
    """
    type: ClassVar[str] = "web_search"
    name: ClassVar[str] = "web_search"
    
    user_config: Optional[OpenAIWebSearchToolConfig] = None


class ContainerAutoConfig(BaseModel):
    """Configuration for automatic container selection."""
    type: Literal["auto"] = "auto"


class OpenAICodeInterpreterToolConfig(BaseModel):
    """Configuration schema for OpenAI code interpreter tool.
    
    The code interpreter tool enables GPT models to write and run Python code
    in a sandboxed execution environment. It can be used for:
    - Data analysis and visualization
    - Mathematical calculations
    - File processing and manipulation
    - Code execution and debugging
    
    Attributes:
        container: Container configuration for code execution. Can be:
            - A string representing a specific container ID (e.g., "cntr_abc123")
            - An object with type "auto" for automatic container selection
    """
    container: Optional[Union[str, ContainerAutoConfig]] = Field(
        default_factory=lambda: { "type": "auto" },
        description="Container configuration for code execution. "
                   "Can be a container ID string (e.g., 'cntr_abc123') or "
                   "an object with type 'auto' for automatic container selection."
    )


class OpenAICodeInterpreterTool(BaseOpenAITool):
    """OpenAI code interpreter tool.
    
    This tool allows GPT models to write and run Python code in a sandboxed
    execution environment. The assistant can:
    
    - Write and execute Python code iteratively
    - Analyze data and generate visualizations
    - Perform mathematical calculations
    - Process and manipulate files
    - Debug and modify code based on execution results
    
    Key capabilities:
    - Sandboxed Python execution environment
    - Access to common Python libraries (pandas, numpy, matplotlib, etc.)
    - Ability to read and write files
    - Iterative code development and debugging
    - Generation of charts, graphs, and data visualizations
    
    Usage considerations:
    - Code interpreter sessions are stateful during a conversation
    - Each session has resource limits and timeout constraints
    - Generated files can be downloaded and shared
    - Ideal for data analysis, mathematical problem-solving, and prototyping
    
    Container configuration:
    - Can use automatic container selection: {"type": "auto"}
    - Can specify a specific container ID: "cntr_abc123"
    """
    type: ClassVar[str] = "code_interpreter"
    name: ClassVar[str] = "code_interpreter"
    
    user_config: Optional[OpenAICodeInterpreterToolConfig] = Field(
        default_factory=lambda: OpenAICodeInterpreterToolConfig(),
    )
