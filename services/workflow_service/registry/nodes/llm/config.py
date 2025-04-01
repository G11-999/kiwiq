from enum import Enum
from typing import Dict, Type, Any, Optional, List, Tuple
from pydantic import BaseModel
import json
from openai import OpenAI
from anthropic import Anthropic

from workflow_service.config.settings import settings

from fireworks.client import Fireworks

from langchain.chat_models import init_chat_model


class EnumWithAttr(Enum):
    """Enum with attributes."""
     
    def __new__(cls, value: Any, metadata: Any):
        member = cls.__new__(cls)
        member._value_ = value
        metadata.model_name = value
        member.metadata = metadata
        return member


class LLMModelProvider(str, Enum):
    """Supported model providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "google_genai"
    FIREWORKS = "fireworks"
    AWS_BEDROCK = "bedrock_converse"
    PERPLEXITY = "perplexity"



class ModelMetadata(BaseModel):
    """Model metadata.

    TODO: best source integrate!
    https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json

    TODO: NOTE: there are a lot of thinking related nuances in diff feature compatibilities, etc:
    https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking
    """
    provider: LLMModelProvider
    model_name: str = ""
    verbose_name: Optional[str] = None
    context_limit: int
    output_token_limit: int
    output_token_limit_thinking: Optional[int] = None
    rate_limits: Optional[Dict[str, Any]] = None
    
    # reasoning
    reasoning: bool = False
    reasoning_effort_class: Optional[List[str]] = None
    reasoning_effort_number_range: Optional[Tuple[int, int]] = None
    reasoning_tokens_budget: bool = False
    reasoning_tokens_budget_min: Optional[int] = None
    # reasoning_tokens_budget_max: Optional[int] = None
    
    streaming: bool = True
    structured_output: bool = True
    # model supports regular non-reasoning mode. True for all non-reasoning models.
    non_reasoning_mode: Optional[bool] = True

    # Tool use config
    tool_use: bool = True
    tool_choice: List[str] = []
    parallel_tool_calling_configurable: bool = False

    multimodal: bool = False
    # price computed by tokencost library
    # price: Optional[Dict[str, float]] = None

    # Web Search Configs
    web_search: bool = True
    # real_time_search: bool = True
    citation_support: bool = True
    search_recency_filter: bool = True
    search_domain_filter: bool = True 
    # return_images: bool = False
    # return_related_questions: bool = True
    search_context_size: bool = False
    user_location: bool = False


# class ModelMetadata(ModelMetadata):
#     """Extends base model metadata with web search capabilities."""
#     web_search: bool = True
#     # real_time_search: bool = True
#     citation_support: bool = True
#     search_recency_filter: bool = True
#     search_domain_filter: bool = True 
#     # return_images: bool = False
#     # return_related_questions: bool = True
#     search_context_size: bool = False
#     user_location: bool = False
    

REDACED_THINKING_MESSAGE_TYPES = ["redacted_thinking"]
THINKING_MESSAGE_TYPES = ["thinking", "reasoning_content"] + REDACED_THINKING_MESSAGE_TYPES

# Default metadata templates


DEFAULT_OPENAI_METADATA = ModelMetadata(
    provider=LLMModelProvider.OPENAI,
    context_limit=128000,
    output_token_limit=16384,
    # reasoning = True
    # reasoning_effort_class = ["low", "medium", "high"],
    rate_limits={"requests_per_minute": 10000, "tokens_per_minute": 30000000},  # TODO: RECHECK!
    tool_choice=["auto", "any", "none"],
    parallel_tool_calling_configurable=True,
    multimodal=True
)

# Default metadata templates
DEFAULT_OPENAI_SEARCH_METADATA = ModelMetadata(
    provider=LLMModelProvider.OPENAI,
    context_limit=128000,
    output_token_limit=16384,
    rate_limits={"requests_per_minute": 10000, "tokens_per_minute": 30000000},
    # real_time_search=True,
    web_search=True,
    citation_support=True,
    # structured_output=True,
    search_recency_filter=False,
    search_domain_filter=False,
    # return_images=False,
    # return_related_questions=True,
    search_context_size=True,  # OpenAI supports search context size
    user_location=True  # OpenAI supports user location
)

class OpenAIModels(str, EnumWithAttr):
    """OpenAI model options."""
    O3_MINI = "o3-mini", ModelMetadata(**(DEFAULT_OPENAI_METADATA.model_dump() | {
        "rate_limits": {"requests_per_minute": 30000, "tokens_per_minute": 150000000},
        "reasoning": True,
        "non_reasoning_mode": False,
        "reasoning_effort_class": ["low", "medium", "high"],
        "multimodal": False,
        "context_limit": 200000,
        "output_token_limit": 100000,
    }))
    GPT_4_5 = "gpt-4.5-preview", ModelMetadata(**(DEFAULT_OPENAI_METADATA.model_dump() | {"rate_limits": {"requests_per_minute": 10000, "tokens_per_minute": 2000000}}))
    GPT_4o = "gpt-4o", DEFAULT_OPENAI_METADATA
    GPT_4o_mini = "gpt-4o-mini", ModelMetadata(**(DEFAULT_OPENAI_METADATA.model_dump() | {"rate_limits": {"requests_per_minute": 30000, "tokens_per_minute": 150000000}}))
    O1_MINI = "o1-mini", ModelMetadata(**(DEFAULT_OPENAI_METADATA.model_dump() | {
        "rate_limits": {"requests_per_minute": 30000, "tokens_per_minute": 150000000},
        "reasoning": True,
        "non_reasoning_mode": False,
        "reasoning_effort_class": ["low", "medium", "high"],
        "multimodal": False,
        "tool_use": False,
        "structured_output": False,
        "output_token_limit": 65536,
    }))
    O1 = "o1", ModelMetadata(**(DEFAULT_OPENAI_METADATA.model_dump() | {
        "rate_limits": {"requests_per_minute": 10000, "tokens_per_minute": 30000000},
        "reasoning": True,
        "non_reasoning_mode": False,
        "reasoning_effort_class": ["low", "medium", "high"],
        "multimodal": True,
        "context_limit": 200000,
        "output_token_limit": 100000,
    }))
    # NOTE: O1-pro available via Requests API!

    """OpenAI web search model options."""
    GPT_4O_SEARCH_PREVIEW = "gpt-4o-search-preview", ModelMetadata(**(DEFAULT_OPENAI_SEARCH_METADATA.model_dump() | {
        "rate_limits": {"requests_per_minute": 1000, "tokens_per_minute": 3000000}
    }))
    GPT_4O_MINI_SEARCH_PREVIEW = "gpt-4o-mini-search-preview", ModelMetadata(**(DEFAULT_OPENAI_SEARCH_METADATA.model_dump() | {
        "rate_limits": {"requests_per_minute": 30000, "tokens_per_minute": 150000000}
    }))


ANTHROPIC_METADATA = ModelMetadata(
    provider=LLMModelProvider.ANTHROPIC,
    context_limit=200000,
    output_token_limit=8192,
    rate_limits={"requests_per_minute": 4000, "input_tokens_per_minute": 400000, "output_tokens_per_minute": 80000},
    # reasoning=True,
    # reasoning_effort_class=["low", "medium", "high"],
    # reasoning_tokens_budget=True,
    tool_use=True,
    multimodal=True,
    non_reasoning_mode=True,
    tool_choice=["auto", "any", "none"],
    parallel_tool_calling_configurable=True,
)


class AnthropicModels(str, EnumWithAttr):
    """Anthropic model options."""
    CLAUDE_3_7_SONNET = "claude-3-7-sonnet-20250219", ModelMetadata(**(ANTHROPIC_METADATA.model_dump() | {
        "output_token_limit_thinking": 64000,
        "rate_limits": {"requests_per_minute": None, "input_tokens_per_minute": 1000000, "output_tokens_per_minute": 400000},
        "reasoning": True,
        # it also has non-reasoning mode!
        "reasoning_tokens_budget": True,
        "reasoning_tokens_budget_min": 1024,
    }))
    CLAUDE_3_5_SONNET = "claude-3-5-sonnet-20241022", ModelMetadata(**(ANTHROPIC_METADATA.model_dump() | {
        "rate_limits": {"requests_per_minute": 4000, "input_tokens_per_minute": 2000000, "output_tokens_per_minute": 400000},
    }))
    CLAUDE_3_5_HAIKU = "claude-3-5-haiku-20241022", ModelMetadata(**(ANTHROPIC_METADATA.model_dump() | {
        "output_token_limit": 4096,
    }))
    CLAUDE_3_OPUS = "claude-3-opus-20240229", ModelMetadata(**(ANTHROPIC_METADATA.model_dump() | {
        "output_token_limit": 4096,
    }))



GEMINI_METADATA = ModelMetadata(
    provider=LLMModelProvider.GEMINI,
    context_limit=1048576,
    output_token_limit=8192,
    # https://ai.google.dev/gemini-api/docs/models#token-size
    # https://ai.google.dev/gemini-api/docs/rate-limits#tier-1
    # TODO: dynamically get Gemini's model configs / params: https://ai.google.dev/gemini-api/docs/tokens?lang=python
    # Diff finish reasons for Gemini: https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference#gen-ai-sdk-for-python
    rate_limits={"requests_per_minute": 20, "tokens_per_minute": 2000000, "requests_per_day": 100},
    # reasoning=True,
    # reasoning_effort_class=["low", "medium", "high"],
    # reasoning_tokens_budget=True,
    tool_use=True,
    multimodal=True,
    tool_choice=["auto", "any", "none"],
    # parallel_tool_calling_configurable=True,
)


GEMINI_PARAM_KEY_OVERRIDES = {
    "max_tokens": "maxOutputTokens"
}


# Gemini max tokens arg in langchain is bugged out!
# Gemini's correct max tokens input param is mentioned here: https://js.langchain.com/docs/integrations/platforms/google/
# and here: https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference#gen-ai-sdk-for-python
# and here: https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference#request
class GeminiModels(str, EnumWithAttr):
    """Google Gemini model options.
    """
    GEMINI_2_5_PRO_EXP = "gemini-2.5-pro-exp-03-25", ModelMetadata(**(GEMINI_METADATA.model_dump() | {
        "reasoning": True,
        "output_token_limit": 65536,
        "non_reasoning_mode": False,
        # "output_token_limit": 4096,
    }))  # Enhanced thinking and reasoning, multimodal understanding, advanced coding
    GEMINI_2_0_FLASH = "gemini-2.0-flash", ModelMetadata(**(GEMINI_METADATA.model_dump() | {
        "rate_limits": {"requests_per_minute": 2000, "tokens_per_minute": 4000000},
        # "output_token_limit": 4096,
    }))  # Next generation features, speed, thinking, realtime streaming, and multimodal generation
    GEMINI_2_0_FLASH_THINKING_EXP = "gemini-2.0-flash-thinking-exp-01-21", ModelMetadata(**(GEMINI_METADATA.model_dump() | {
        "rate_limits": {"requests_per_minute": 10, "tokens_per_minute": 4000000},
         "reasoning": True,
         "non_reasoning_mode": False,
        # "output_token_limit": 4096,
    }))  # Experiment Thinking!
    GEMINI_2_0_FLASH_LITE = "gemini-2.0-flash-lite", ModelMetadata(**(GEMINI_METADATA.model_dump() | {
        "rate_limits": {"requests_per_minute": 4000, "tokens_per_minute": 4000000},
        "tool_use": False,
        # "output_token_limit": 4096,
    }))  # Cost efficiency and low latency
    # GEMINI_1_5_PRO = "gemini-1.5-pro", GLOBAL_DEFAULT_METADATA  # Long context window model with strong multimodal capabilities


FIREWORKS_METADATA = ModelMetadata(
    provider=LLMModelProvider.FIREWORKS,
    context_limit=128000,
    output_token_limit=100000, # TODO: FIXME: it is context_limit - input tokens!
    # https://docs.fireworks.ai/guides/quotas_usage/rate-limits#rate-limits-spend-limits-and-quotas
    # Complex and autoscales! Can upgrade tier by increase historical spend
    rate_limits={"requests_per_minute": 100, "tokens_per_minute": 100000},
    tool_use=False,
    reasoning=True,
    non_reasoning_mode=False,
    reasoning_effort_class=["low", "medium", "high"],
    reasoning_effort_number_range=(0, 20000),
    # TODO: verify structured outputs in AWS Deepseek!
)


class FireworksModels(str, EnumWithAttr):
    """Fireworks model options.
    Eg Output:
    content='<think>\nOkay, the user wrote "Hello, world!" That\'s a classic first program in many programming languages. Maybe they\'re just testing the response or starting to learn coding. I should acknowledge their message and offer help. Let me think of a friendly reply that invites them to ask questions or seek assistance.\n\nI should keep it simple and welcoming. Perhaps mention common uses of "Hello, world!" and ask if they need help with something specific. Make sure to encourage them to reach out if they have any questions. Avoid technical jargon unless they ask for it. Yeah, that sounds good.\n</think>\n\nHello, world! 👋 It looks like you\'re testing things out or maybe starting your journey into programming! If you have a question, need help with code, or want to explore a topic, feel free to ask. How can I assist you today? 😊' additional_kwargs={} response_metadata={'token_usage': {'prompt_tokens': 7, 'total_tokens': 184, 'completion_tokens': 177}, 'model_name': 'accounts/fireworks/models/deepseek-r1-basic', 'system_fingerprint': '', 'finish_reason': 'stop', 'logprobs': None} id='run-8c46e535-4545-4c9b-87c6-fec1c2ee9b39-0' usage_metadata={'input_tokens': 7, 'output_tokens': 177, 'total_tokens': 184}
    """
    DEEPSEEK_R1_FAST = "accounts/fireworks/models/deepseek-r1", FIREWORKS_METADATA
    DEEPSEEK_R1_BASIC = "accounts/fireworks/models/deepseek-r1-basic", FIREWORKS_METADATA  # NOTE: this faces a lot of server errors!!


AWS_BEDROCK_METADATA = ModelMetadata(
    # https://us-east-1.console.aws.amazon.com/servicequotas/home/services/bedrock/quotas
    provider=LLMModelProvider.AWS_BEDROCK,
    context_limit=128000,
    output_token_limit=4096,
    rate_limits={"requests_per_minute": 20, "tokens_per_minute": 20000},
    tool_use=False,
    reasoning=True,
    non_reasoning_mode=False,
    structured_output=False,
    # TODO: verify structured outputs in AWS Deepseek!
)

class AWSBedrockModels(str, EnumWithAttr):
    """Bedrock Converse model options."""
    DEEPSEEK_R1 = "us.deepseek.r1-v1:0", AWS_BEDROCK_METADATA
    # init_chat_model(model="us.deepseek.r1-v1:0", model_provider="bedrock_converse", aws_secret_access_key=settings.AWS_BEDROCK_SECRET_ACCESS_KEY, aws_access_key_id=settings.AWS_BEDROCK_ACCESS_KEY_ID, region_name="us-east-1")


AWS_REGION = "us-east-1"

DEFAULT_PERPLEXITY_SEARCH_METADATA = ModelMetadata(
    provider=LLMModelProvider.PERPLEXITY,
    context_limit=200000,
    output_token_limit=8096,
    rate_limits={"requests_per_minute": 50},
    web_search=True,
    # real_time_search=True,
    citation_support=True,
    # structured_output=True,
    # # TEST! NOT SUPPORTED?? NO!!!
    # reasoning_effort_class=["low", "medium", "high"],
    # reasoning_effort_number_range=(0, 20000),
    search_recency_filter=True,
    search_domain_filter=True,
    # return_images=True,
    # return_related_questions=True,
    search_context_size=True,  # Perplexity supports search context size
    user_location=False  # Perplexity supports user location
)


class PerplexityModels(str, EnumWithAttr):
    """Perplexity model options."""
    SONAR_DEEP_RESEARCH = "sonar-deep-research", ModelMetadata(**(DEFAULT_PERPLEXITY_SEARCH_METADATA.model_dump() | {
        "context_limit": 128000,
        "output_token_limit": 16384,
        "reasoning": True,
        "rate_limits": {"requests_per_minute": 5, }
    }))
    SONAR_REASONING_PRO = "sonar-reasoning-pro", ModelMetadata(**(DEFAULT_PERPLEXITY_SEARCH_METADATA.model_dump() | {
        "context_limit": 128000,
        "reasoning": True,
        "output_token_limit": 8096,  # Updated per Perplexity model card: max output token limit is 8k

    }))
    SONAR_REASONING = "sonar-reasoning", ModelMetadata(**(DEFAULT_PERPLEXITY_SEARCH_METADATA.model_dump() | {
        "context_limit": 128000,
        "reasoning": True,
        "output_token_limit": 8000,  # Updated per Perplexity model card: max output token limit is 8k
    }))
    SONAR_PRO = "sonar-pro", ModelMetadata(**(DEFAULT_PERPLEXITY_SEARCH_METADATA.model_dump() | {
        "context_limit": 128000,
        "output_token_limit": 8000,  # Updated per Perplexity model card: max output token limit is 8k
    }))
    
    SONAR = "sonar", ModelMetadata(**(DEFAULT_PERPLEXITY_SEARCH_METADATA.model_dump() | {
        "context_limit": 127072,
        "output_token_limit": 127072,
    }))

    # Offline model
    R1 = "r1-1776", ModelMetadata(**(DEFAULT_PERPLEXITY_SEARCH_METADATA.model_dump() | {
        "context_limit": 128000,
        "output_token_limit": 16384,
        "reasoning": True,
        "web_search": False,
    }))



PROVIDER_MODEL_MAP: Dict[LLMModelProvider, Type[Enum]] = {
    LLMModelProvider.OPENAI: OpenAIModels,
    LLMModelProvider.ANTHROPIC: AnthropicModels,
    LLMModelProvider.GEMINI: GeminiModels,
    LLMModelProvider.FIREWORKS: FireworksModels,
    LLMModelProvider.AWS_BEDROCK: AWSBedrockModels,
    LLMModelProvider.PERPLEXITY: PerplexityModels
}
PARAM_KEY_OVERRIDES = {
    LLMModelProvider.GEMINI: GEMINI_PARAM_KEY_OVERRIDES
}


def list_models(provider: LLMModelProvider):
    if provider == LLMModelProvider.ANTHROPIC:
        client = Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
        )
        models = client.models.list()
        print(json.dumps([model.id for model in models], indent=4))
    elif provider == LLMModelProvider.OPENAI:
        client = OpenAI(
            api_key = settings.OPENAI_API_KEY
        )
        models = client.models.list()
        print(json.dumps([model.id for model in models], indent=4))
    else:
        raise NotImplementedError("Gemini models are not supported in this context")
    return models
