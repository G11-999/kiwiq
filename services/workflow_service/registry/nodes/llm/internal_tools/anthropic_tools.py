from abc import ABC
from pydantic import BaseModel, HttpUrl, field_validator, Field
from typing import Optional, Union, ClassVar, Literal
import re

from workflow_service.registry.nodes.llm.internal_tools.internal_base import BaseProviderInternalTool, UserLocation


class BaseAnthropicTool(BaseProviderInternalTool, ABC):
    """Base class for Anthropic tools."""
    # provider_name: ClassVar[LLMModelProvider] = LLMModelProvider.ANTHROPIC

    def get_tool(self):
        tool = {
            "type": self.type,
            "name": self.name,
        }
        if self.user_config:
            tool.update(self.user_config.model_dump(mode="json", exclude_none=True))
        return tool


class AnthropicSearchToolConfig(BaseModel):
    """Configuration schema for search tool parameters.
    
    Attributes:
        max_uses: Maximum number of searches allowed per request
        allowed_domains: List of domains to restrict search results to
        blocked_domains: List of domains to exclude from search results 
        user_location: Location settings for localizing search results
    
    Eg:
        // Optional: Limit the number of searches per request
        "max_uses": 5,

        // Optional: Only include results from these domains
        "allowed_domains": ["example.com", "trusteddomain.org"],

        // Optional: Never include results from these domains
        "blocked_domains": ["untrustedsource.com"],

        // Optional: Localize search results
        "user_location": {
            "type": "approximate",
            "city": "San Francisco",
            "region": "California",
            "country": "US",
            "timezone": "America/Los_Angeles"
        }
    """
    max_uses: Optional[int] = None
    # Allow either full URLs (https://domain.com) or domain patterns (domain.com, sub.domain.com)
    allowed_domains: Optional[list[Union[HttpUrl, str]]] = None
    blocked_domains: Optional[list[Union[HttpUrl, str]]] = None
    user_location: Optional[UserLocation] = None

    @field_validator('allowed_domains', 'blocked_domains')
    @classmethod
    def validate_domain_patterns(cls, domains: Optional[list[Union[HttpUrl, str]]]) -> Optional[list[Union[HttpUrl, str]]]:
        """Validate that domain patterns are either valid URLs or valid domain patterns.
        
        Valid formats:
        - Full URLs: https://domain.com
        - Domain patterns: domain.com, sub.domain.com
        
        Args:
            domains: List of domains to validate
            
        Returns:
            The validated list of domains
            
        Raises:
            ValueError: If any domain pattern is invalid
        """
        if not domains:
            return domains
            
        domain_pattern = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9-]*(\.[a-zA-Z0-9][a-zA-Z0-9-]*)*\.[a-zA-Z]{2,}$')
        
        for domain in domains:
            if isinstance(domain, str) and not domain_pattern.match(domain):
                try:
                    HttpUrl(url=domain)
                except ValueError as e:
                    raise ValueError(f"Invalid domain pattern: {domain} - {e}")
        return domains



class AnthropicWebSearchTool(BaseAnthropicTool):
    """Anthropic web search tool.
    
    This tool allows Claude to search the web for information.
    """
    type: ClassVar[str] = "web_search_20250305"
    name: ClassVar[str] = "web_search"
    
    user_config: Optional[AnthropicSearchToolConfig] = None
