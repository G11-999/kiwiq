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
    type: ClassVar[str] = "web_search_preview"
    name: ClassVar[str] = "web_search_preview"
    
    user_config: Optional[OpenAIWebSearchToolConfig] = None
