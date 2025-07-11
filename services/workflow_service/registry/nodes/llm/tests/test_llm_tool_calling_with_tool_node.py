"""
Comprehensive integrated tests for LLMNode and ToolExecutorNode working together.

This module provides extensive testing for the complete tool calling workflow:
- LLMNode generates tool calls from user prompts
- ToolExecutorNode executes those tool calls
- Results are passed back to LLMNode for final processing
- Multi-turn conversations with tool usage
- Error handling and edge cases
- Different tool types and configurations
"""
import asyncio
from copy import copy
import json
import time
import unittest
import uuid
from typing import Any, ClassVar, Dict, List, Optional, Union
from unittest.mock import Mock, patch

from pydantic import BaseModel, Field, ConfigDict, create_model
from pydantic.fields import PydanticUndefined, FieldInfo

from kiwi_app.workflow_app.constants import LaunchStatus
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY,
    INPUT_NODE_NAME,
    OUTPUT_NODE_NAME,
    DB_SESSION_KEY,
)
from db.session import get_async_session
from workflow_service.graph.builder import GraphBuilder
from workflow_service.graph.graph import (
    EdgeMapping,
    EdgeSchema,
    GraphSchema,
    NodeConfig,
)
from workflow_service.graph.runtime.adapter import LangGraphRuntimeAdapter
from workflow_service.registry.nodes.core.base import BaseNode
from workflow_service.registry.schemas.base import BaseNodeConfig, BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import InputNode, OutputNode
from workflow_service.registry.nodes.core.flow_nodes import IfElseConditionNode
from workflow_service.registry.nodes.core.router_node import RouterNode
from workflow_service.registry.nodes.llm.llm_node import (
    LLMNode,
    LLMNodeConfigSchema, 
    LLMModelConfig,
    ModelSpec,
    ToolCallingConfig,
    ToolConfig,
    ToolCall,
    ToolOutput,
    LLMStructuredOutputSchema,
)
from workflow_service.registry.nodes.llm.config import (
    LLMModelProvider,
    AnthropicModels,
    OpenAIModels,
)
from workflow_service.registry.nodes.tools.tool_executor_node import (
    ToolExecutorNode,
    ToolExecutorNodeConfigSchema,
    ToolNodeConfig,
)
from workflow_service.registry.registry import DBRegistry
from workflow_service.services.external_context_manager import (
    ExternalContextManager,
    get_external_context_manager_with_clients,
)

# Import required schemas and models
from kiwi_app.workflow_app.schemas import WorkflowRunJobCreate


# --- Fake Tool Nodes for Integrated Testing ---

class MathCalculatorInputSchema(BaseSchema):
    """Input schema for the MathCalculator tool - enhanced for LLM integration."""
    operation: str = Field(..., description="The mathematical operation to perform: add, subtract, multiply, divide, power, sqrt")
    number_a: float = Field(..., description="First number for the operation")
    number_b: float = Field(description="Second number (not needed for sqrt)")
    precision: int = Field(description="Number of decimal places for the result")

# input_schema = MathCalculatorInputSchema
# field_definitions = {}

# for k, v in input_schema.model_fields.items():
#     if BaseSchema._is_field_for_llm_tool_call(v):
#         # Create a new FieldInfo with default removed to ensure all fields are required
#         # This is necessary for LLM tool calling where all parameters should be explicit
        
#         # Create a new FieldInfo instance without default values
#         # This forces the field to be required in the JSON schema
#         new_field_info = FieldInfo(
#             # Don't pass any default value - this makes the field required
#             annotation=v.annotation,
#             description=v.description,
#             title=v.title,
#             examples=v.examples,
#             json_schema_extra=v.json_schema_extra,
#             metadata=v.metadata,
#             # Explicitly exclude default and default_factory to make field required
#             # All other field properties are preserved
#         )
        
#         field_definitions[k] = (v.annotation, new_field_info)

# tool_for_binding = create_model(
#     input_schema.__name__,
#     __base__=(BaseNodeConfig),
#     __doc__=input_schema.__doc__,
#     __module__=input_schema.__module__,
#     # Only bind user editable fields, hide other fields!
#     **field_definitions
# )

# print(json.dumps(MathCalculatorInputSchema.model_json_schema(), indent=4))
# print(json.dumps(tool_for_binding.model_json_schema(), indent=4))
# raise Exception("Stop here")

class MathCalculatorOutputSchema(BaseNodeConfig):
    """Output schema for the MathCalculator tool."""
    result: float = Field(..., description="The calculation result")
    operation_performed: str = Field(..., description="Human-readable description of what was calculated")
    formula: str = Field(..., description="The mathematical formula used")


class MathCalculatorConfigSchema(BaseNodeConfig):
    """Configuration schema for the MathCalculator tool."""
    max_precision: int = Field(10, description="Maximum decimal places allowed")
    allow_division_by_zero: bool = Field(False, description="Whether to allow division by zero")


class MathCalculatorNode(BaseNode[MathCalculatorInputSchema, MathCalculatorOutputSchema, MathCalculatorConfigSchema]):
    """
    Enhanced Math Calculator Tool Node for LLM integration testing.
    Supports various mathematical operations with detailed output descriptions.
    """
    node_name: ClassVar[str] = "math_calculator"
    node_version: ClassVar[str] = "1.0.0"
    node_is_tool: ClassVar[bool] = True
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[type] = MathCalculatorInputSchema
    output_schema_cls: ClassVar[type] = MathCalculatorOutputSchema
    config_schema_cls: ClassVar[type] = MathCalculatorConfigSchema
    
    async def process(
        self, 
        input_data: MathCalculatorInputSchema, 
        config: Dict[str, Any], 
        *args: Any, 
        **kwargs: Any
    ) -> MathCalculatorOutputSchema:
        """
        Process mathematical operations with detailed output for LLM consumption.
        
        Args:
            input_data: The input data containing operation and numbers.
            config: Configuration parameters.
            
        Returns:
            MathCalculatorOutputSchema: The calculation result with description.
        """
        # Get config values
        max_precision = getattr(self.config, 'max_precision', 10) if hasattr(self, 'config') and self.config else 10
        allow_division_by_zero = getattr(self.config, 'allow_division_by_zero', False) if hasattr(self, 'config') and self.config else False
        
        operation = input_data.operation.lower()
        a = input_data.number_a
        b = input_data.number_b
        precision = min(input_data.precision or 2, max_precision)
        
        # Perform the operation
        if operation in ["add", "addition", "+"]:
            if b is None:
                raise ValueError("Addition requires two numbers")
            result = a + b
            formula = f"{a} + {b}"
            operation_desc = f"Added {a} and {b}"
        elif operation in ["subtract", "subtraction", "-"]:
            if b is None:
                raise ValueError("Subtraction requires two numbers")
            result = a - b
            formula = f"{a} - {b}"
            operation_desc = f"Subtracted {b} from {a}"
        elif operation in ["multiply", "multiplication", "*", "times"]:
            if b is None:
                raise ValueError("Multiplication requires two numbers")
            result = a * b
            formula = f"{a} × {b}"
            operation_desc = f"Multiplied {a} by {b}"
        elif operation in ["divide", "division", "/"]:
            if b is None:
                raise ValueError("Division requires two numbers")
            if b == 0 and not allow_division_by_zero:
                raise ValueError("Division by zero is not allowed")
            result = a / b if b != 0 else float('inf')
            formula = f"{a} ÷ {b}"
            operation_desc = f"Divided {a} by {b}"
        elif operation in ["power", "pow", "**", "^"]:
            if b is None:
                raise ValueError("Power operation requires two numbers")
            result = a ** b
            formula = f"{a}^{b}"
            operation_desc = f"Raised {a} to the power of {b}"
        elif operation in ["sqrt", "square_root"]:
            if a < 0:
                raise ValueError("Cannot take square root of negative number")
            result = a ** 0.5
            formula = f"√{a}"
            operation_desc = f"Calculated square root of {a}"
        else:
            raise ValueError(f"Unknown operation: {operation}. Supported operations: add, subtract, multiply, divide, power, sqrt")
        
        # Apply precision
        if precision is not None and result != float('inf'):
            result = round(result, precision)
        
        return MathCalculatorOutputSchema(
            result=result,
            operation_performed=operation_desc,
            formula=f"{formula} = {result}"
        )


class WeatherLookupInputSchema(BaseNodeConfig):
    """Input schema for the WeatherLookup tool."""
    location: str = Field(..., description="City and country/state (e.g., 'San Francisco, CA' or 'London, UK')")
    units: Optional[str] = Field("celsius", description="Temperature units: 'celsius', 'fahrenheit', or 'kelvin'")
    include_forecast: bool = Field(False, description="Whether to include 3-day forecast")


class WeatherInfo(BaseNodeConfig):
    """Weather information model."""
    temperature: float = Field(..., description="Current temperature")
    condition: str = Field(..., description="Weather condition description")
    humidity: int = Field(..., description="Humidity percentage")
    wind_speed: float = Field(..., description="Wind speed")
    pressure: float = Field(..., description="Atmospheric pressure")


class ForecastDay(BaseNodeConfig):
    """Single day forecast model."""
    day: str = Field(..., description="Day of the week")
    high_temp: float = Field(..., description="High temperature")
    low_temp: float = Field(..., description="Low temperature")
    condition: str = Field(..., description="Expected weather condition")


class WeatherLookupOutputSchema(BaseNodeConfig):
    """Output schema for the WeatherLookup tool."""
    location: str = Field(..., description="Location that was queried")
    current_weather: WeatherInfo = Field(..., description="Current weather information")
    forecast: Optional[List[ForecastDay]] = Field(None, description="3-day forecast if requested")
    units: str = Field(..., description="Temperature units used")
    timestamp: str = Field(..., description="When this weather data was retrieved")


class WeatherLookupConfigSchema(BaseNodeConfig):
    """Configuration schema for the WeatherLookup tool."""
    default_units: str = Field("celsius", description="Default temperature units")
    enable_forecast: bool = Field(True, description="Whether forecast functionality is enabled")


class WeatherLookupNode(BaseNode[WeatherLookupInputSchema, WeatherLookupOutputSchema, WeatherLookupConfigSchema]):
    """
    Fake Weather Lookup Tool Node for testing LLM integration.
    Returns realistic but fake weather data for any location.
    """
    node_name: ClassVar[str] = "weather_lookup"
    node_version: ClassVar[str] = "1.0.0"
    node_is_tool: ClassVar[bool] = True
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[type] = WeatherLookupInputSchema
    output_schema_cls: ClassVar[type] = WeatherLookupOutputSchema
    config_schema_cls: ClassVar[type] = WeatherLookupConfigSchema
    
    async def process(
        self, 
        input_data: WeatherLookupInputSchema, 
        config: Dict[str, Any], 
        *args: Any, 
        **kwargs: Any
    ) -> WeatherLookupOutputSchema:
        """
        Generate fake weather data for the requested location.
        
        Args:
            input_data: The input data containing location and preferences.
            config: Configuration parameters.
            
        Returns:
            WeatherLookupOutputSchema: Fake weather information.
        """
        location = input_data.location
        units = input_data.units or "celsius"
        include_forecast = input_data.include_forecast
        
        # Generate realistic fake weather based on location hints
        location_lower = location.lower()
        
        # Base temperature in Celsius
        if "alaska" in location_lower or "iceland" in location_lower or "antarctica" in location_lower:
            base_temp = -10
            condition = "Snow"
        elif "sahara" in location_lower or "phoenix" in location_lower or "dubai" in location_lower:
            base_temp = 40
            condition = "Hot and sunny"
        elif "london" in location_lower or "seattle" in location_lower:
            base_temp = 12
            condition = "Cloudy with light rain"
        elif "california" in location_lower or "florida" in location_lower or "hawaii" in location_lower:
            base_temp = 24
            condition = "Sunny"
        else:
            base_temp = 20  # Default pleasant temperature
            condition = "Partly cloudy"
        
        # Convert temperature if needed
        if units == "fahrenheit":
            current_temp = (base_temp * 9/5) + 32
        elif units == "kelvin":
            current_temp = base_temp + 273.15
        else:
            current_temp = base_temp
        
        # Generate current weather
        current_weather = WeatherInfo(
            temperature=round(current_temp, 1),
            condition=condition,
            humidity=65,  # Reasonable default
            wind_speed=8.5,
            pressure=1013.25
        )
        
        # Generate forecast if requested
        forecast = None
        if include_forecast:
            days = ["Tomorrow", "Day after tomorrow", "In 3 days"]
            forecast = []
            for i, day in enumerate(days):
                # Vary temperature slightly for each day
                high_variation = base_temp + (i * 2) - 1
                low_variation = base_temp - 5 + (i * 1)
                
                if units == "fahrenheit":
                    high_temp = (high_variation * 9/5) + 32
                    low_temp = (low_variation * 9/5) + 32
                elif units == "kelvin":
                    high_temp = high_variation + 273.15
                    low_temp = low_variation + 273.15
                else:
                    high_temp = high_variation
                    low_temp = low_variation
                
                forecast_conditions = ["Sunny", "Partly cloudy", "Cloudy"]
                forecast.append(ForecastDay(
                    day=day,
                    high_temp=round(high_temp, 1),
                    low_temp=round(low_temp, 1),
                    condition=forecast_conditions[i % 3]
                ))
        
        return WeatherLookupOutputSchema(
            location=location,
            current_weather=current_weather,
            forecast=forecast,
            units=units,
            timestamp="2025-01-12 10:30:00 UTC"  # Fixed timestamp for testing
        )


class TextAnalyzerInputSchema(BaseNodeConfig):
    """Input schema for the TextAnalyzer tool."""
    text: str = Field(..., description="Text to analyze")
    analysis_type: str = Field(..., description="Type of analysis: 'sentiment', 'readability', 'keywords', 'summary', 'full'")
    max_keywords: int = Field(10, description="Maximum number of keywords to extract")


class SentimentAnalysis(BaseNodeConfig):
    """Sentiment analysis result."""
    sentiment: str = Field(..., description="Overall sentiment: positive, negative, or neutral")
    confidence: float = Field(..., description="Confidence score (0.0 to 1.0)")
    emotional_tone: str = Field(..., description="Detected emotional tone")


class ReadabilityAnalysis(BaseNodeConfig):
    """Readability analysis result."""
    reading_level: str = Field(..., description="Estimated reading level")
    avg_sentence_length: float = Field(..., description="Average sentence length")
    complexity_score: float = Field(..., description="Text complexity score (0.0 to 1.0)")


class TextAnalyzerOutputSchema(BaseNodeConfig):
    """Output schema for the TextAnalyzer tool."""
    original_text: str = Field(..., description="The original text that was analyzed")
    word_count: int = Field(..., description="Total number of words")
    sentence_count: int = Field(..., description="Total number of sentences")
    character_count: int = Field(..., description="Total number of characters")
    sentiment_analysis: Optional[SentimentAnalysis] = Field(None, description="Sentiment analysis results")
    readability_analysis: Optional[ReadabilityAnalysis] = Field(None, description="Readability analysis results")
    keywords: Optional[List[str]] = Field(None, description="Extracted keywords")
    summary: Optional[str] = Field(None, description="Text summary")


class TextAnalyzerConfigSchema(BaseNodeConfig):
    """Configuration schema for the TextAnalyzer tool."""
    max_text_length: int = Field(10000, description="Maximum text length to analyze")
    enable_advanced_analysis: bool = Field(True, description="Whether to enable advanced analysis features")


class TextAnalyzerNode(BaseNode[TextAnalyzerInputSchema, TextAnalyzerOutputSchema, TextAnalyzerConfigSchema]):
    """
    Text Analyzer Tool Node for testing complex LLM-tool interactions.
    Provides various types of text analysis with detailed results.
    """
    node_name: ClassVar[str] = "text_analyzer"
    node_version: ClassVar[str] = "1.0.0"
    node_is_tool: ClassVar[bool] = True
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[type] = TextAnalyzerInputSchema
    output_schema_cls: ClassVar[type] = TextAnalyzerOutputSchema
    config_schema_cls: ClassVar[type] = TextAnalyzerConfigSchema
    
    async def process(
        self, 
        input_data: TextAnalyzerInputSchema, 
        config: Dict[str, Any], 
        *args: Any, 
        **kwargs: Any
    ) -> TextAnalyzerOutputSchema:
        """
        Analyze text based on the requested analysis type.
        
        Args:
            input_data: The input data containing text and analysis preferences.
            config: Configuration parameters.
            
        Returns:
            TextAnalyzerOutputSchema: Comprehensive text analysis results.
        """
        text = input_data.text
        analysis_type = input_data.analysis_type.lower()
        max_keywords = input_data.max_keywords
        
        # Basic text statistics
        word_count = len(text.split())
        sentence_count = len([s for s in text.split('.') if s.strip()])
        character_count = len(text)
        
        # Initialize analysis results
        sentiment_analysis = None
        readability_analysis = None
        keywords = None
        summary = None
        
        # Perform requested analysis
        if analysis_type in ["sentiment", "full"]:
            # Simple fake sentiment analysis based on keywords
            positive_words = ["good", "great", "excellent", "amazing", "wonderful", "love", "happy", "joy"]
            negative_words = ["bad", "terrible", "awful", "hate", "sad", "angry", "horrible", "disappointed"]
            
            text_lower = text.lower()
            positive_count = sum(1 for word in positive_words if word in text_lower)
            negative_count = sum(1 for word in negative_words if word in text_lower)
            
            if positive_count > negative_count:
                sentiment = "positive"
                confidence = min(0.6 + (positive_count * 0.1), 0.95)
                emotional_tone = "optimistic"
            elif negative_count > positive_count:
                sentiment = "negative"
                confidence = min(0.6 + (negative_count * 0.1), 0.95)
                emotional_tone = "critical"
            else:
                sentiment = "neutral"
                confidence = 0.5
                emotional_tone = "balanced"
            
            sentiment_analysis = SentimentAnalysis(
                sentiment=sentiment,
                confidence=round(confidence, 2),
                emotional_tone=emotional_tone
            )
        
        if analysis_type in ["readability", "full"]:
            avg_sentence_length = word_count / max(sentence_count, 1)
            
            # Simple readability estimation based on sentence length and word length
            avg_word_length = sum(len(word) for word in text.split()) / max(word_count, 1)
            complexity_score = min((avg_sentence_length / 20) + (avg_word_length / 10), 1.0)
            
            if complexity_score < 0.3:
                reading_level = "Elementary"
            elif complexity_score < 0.6:
                reading_level = "Middle School"
            elif complexity_score < 0.8:
                reading_level = "High School"
            else:
                reading_level = "College"
            
            readability_analysis = ReadabilityAnalysis(
                reading_level=reading_level,
                avg_sentence_length=round(avg_sentence_length, 1),
                complexity_score=round(complexity_score, 2)
            )
        
        if analysis_type in ["keywords", "full"]:
            # Simple keyword extraction based on word frequency and length
            words = [word.lower().strip('.,!?":;()[]') for word in text.split()]
            # Filter out common words and short words
            stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}
            meaningful_words = [word for word in words if len(word) > 3 and word not in stop_words]
            
            # Count word frequency
            word_freq = {}
            for word in meaningful_words:
                word_freq[word] = word_freq.get(word, 0) + 1
            
            # Get top keywords
            sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            keywords = [word for word, freq in sorted_words[:max_keywords]]
        
        if analysis_type in ["summary", "full"]:
            # Simple summary: first sentence + last sentence if text is long enough
            sentences = [s.strip() for s in text.split('.') if s.strip()]
            if len(sentences) > 2:
                summary = f"{sentences[0]}. ... {sentences[-1]}."
            elif len(sentences) == 2:
                summary = f"{sentences[0]}. {sentences[1]}."
            else:
                summary = text[:200] + "..." if len(text) > 200 else text
        
        return TextAnalyzerOutputSchema(
            original_text=text,
            word_count=word_count,
            sentence_count=sentence_count,
            character_count=character_count,
            sentiment_analysis=sentiment_analysis,
            readability_analysis=readability_analysis,
            keywords=keywords,
            summary=summary
        )


# --- Test Response Schemas for Structured LLM Output ---

class MathProblemSolutionSchema(BaseModel):
    """Schema for LLM response to math problems."""
    problem_understanding: str = Field(..., description="LLM's understanding of the math problem")
    solution_steps: List[str] = Field(..., description="Step-by-step solution process")
    final_answer: str = Field(..., description="The final numerical answer with units if applicable")
    confidence: float = Field(..., description="Confidence in the solution (0.0 to 1.0)")


class WeatherRecommendationSchema(BaseModel):
    """Schema for LLM response to weather-based recommendations."""
    weather_summary: str = Field(..., description="Summary of the current weather conditions")
    recommendations: List[str] = Field(..., description="Activity recommendations based on weather")
    clothing_suggestions: List[str] = Field(..., description="Clothing suggestions for the weather")
    travel_advice: str = Field(..., description="Travel advice based on weather conditions")


class TextAnalysisReportSchema(BaseModel):
    """Schema for LLM response to text analysis requests."""
    analysis_summary: str = Field(..., description="Overall summary of the text analysis")
    key_insights: List[str] = Field(..., description="Key insights from the analysis")
    recommendations: List[str] = Field(..., description="Recommendations based on the analysis")
    overall_assessment: str = Field(..., description="Overall assessment of the analyzed text")


# --- Helper Functions ---

class MockUser(BaseModel):
    """Mock User model for testing."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    is_superuser: bool = False


def setup_test_registry() -> DBRegistry:
    """
    Set up a test registry with all necessary nodes for LLM-Tool integration.
    
    Returns:
        DBRegistry: Configured registry with LLM, Tool Executor, flow control, and test tool nodes.
    """
    registry = DBRegistry()
    
    # Register core nodes
    registry.register_node(InputNode)
    registry.register_node(OutputNode)
    registry.register_node(LLMNode)
    registry.register_node(ToolExecutorNode)
    
    # Register flow control nodes for looping
    registry.register_node(IfElseConditionNode)
    registry.register_node(RouterNode)
    
    # Register test tool nodes
    registry.register_node(MathCalculatorNode)
    registry.register_node(WeatherLookupNode)
    registry.register_node(TextAnalyzerNode)
    
    return registry


def create_llm_tool_integration_graph(
    llm_provider: LLMModelProvider,
    llm_model: str,
    available_tools: List[str],
    llm_config: Optional[LLMNodeConfigSchema] = None,
    tool_executor_config: Optional[ToolExecutorNodeConfigSchema] = None,
    structured_output_schema: Optional[Dict[str, Any]] = None,
    include_final_llm: bool = True,
    parallel_tool_calls: bool = False,
    max_iterations: int = 5  # Add parameter for maximum iterations
) -> GraphSchema:
    """
    Create a graph for LLM-Tool integration testing with looping support.
    
    The graph flow with looping is:
    Input → LLM → check_loop_conditions → route_loop → tool_executor → [back to LLM or Output]
    
    The loop continues until:
    1. Tool calls are empty (LLM didn't generate any tool calls), OR
    2. Iterations exceed max_iterations (default 5)
    
    Args:
        llm_provider: The LLM provider to use.
        llm_model: The LLM model name.
        available_tools: List of tool names to make available.
        llm_config: Optional LLM configuration.
        tool_executor_config: Optional tool executor configuration.
        structured_output_schema: Optional structured output schema for final LLM.
        include_final_llm: Whether to include final LLM processing (deprecated - always uses single LLM).
        parallel_tool_calls: Whether to allow parallel tool calls.
        max_iterations: Maximum number of iterations before forcing exit.
        
    Returns:
        GraphSchema: The configured graph schema with looping logic.
    """
    # Input node
    input_node = NodeConfig(
        node_id=INPUT_NODE_NAME,
        node_name=INPUT_NODE_NAME,
        node_config={}
    )
    
    # Configure tools for LLM
    tool_configs = [
        ToolConfig(
            tool_name=tool_name,
            is_provider_inbuilt_tool=False,
            provider_inbuilt_user_config={}
        )
        for tool_name in available_tools
    ]
    
    # LLM configuration (single LLM for both tool generation and final processing)
    llm_config_data = llm_config or LLMNodeConfigSchema(
        llm_config=LLMModelConfig(
            model_spec=ModelSpec(
                provider=llm_provider,
                model=llm_model
            ),
            temperature=0.1,
            max_tokens=800
        ),
        tool_calling_config=ToolCallingConfig(
            enable_tool_calling=True,
            parallel_tool_calls=parallel_tool_calls
        ),
        tools=tool_configs,
        default_system_prompt="You are a helpful assistant. Use the available tools to help answer questions accurately. When you need to perform calculations, look up weather information, or analyze text, use the appropriate tools. Continue using tools as needed until you have all the information required to provide a complete answer."
    )
    
    # Add structured output if provided
    if structured_output_schema:
        llm_config_data.output_schema = LLMStructuredOutputSchema(
            schema_definition=structured_output_schema
        )
    
    # Single LLM node (handles both tool generation and final processing)
    llm_node = NodeConfig(
        node_id="llm_generator",
        node_name="llm",
        node_config=llm_config_data.model_dump(exclude_none=True)
    )
    
    # Check loop conditions node - checks if tool calls are empty and iteration count
    check_loop_conditions_node = NodeConfig(
        node_id="check_loop_conditions",
        node_name="if_else_condition",
        node_config={
            "tagged_conditions": [
                {
                    "tag": "tool_calls_empty_check",
                    "condition_groups": [{
                        "logical_operator": "or",
                        "conditions": [
                            {
                                "field": "tool_calls",
                                "operator": "is_empty"
                            }
                        ]
                    }]
                },
                {
                    "tag": "iteration_limit_check",
                    "condition_groups": [{
                        "conditions": [{
                            "field": "generation_metadata.iteration_count",
                            "operator": "greater_than_or_equals",
                            "value": max_iterations
                        }]
                    }]
                }
            ],
            "branch_logic_operator": "or"  # Exit loop if EITHER condition is true
        }
    )
    
    # Route based on loop conditions
    route_loop_node = NodeConfig(
        node_id="route_loop",
        node_name="router_node",
        node_config={
            "choices": ["tool_executor", OUTPUT_NODE_NAME],  # Route to tool executor or output
            "allow_multiple": False,
            "choices_with_conditions": [
                {
                    "choice_id": "tool_executor",  # Continue to tool executor
                    "input_path": "condition_result",
                    "target_value": False  # Continue if conditions are NOT met
                },
                {
                    "choice_id": OUTPUT_NODE_NAME,  # Exit loop - go to output
                    "input_path": "condition_result", 
                    "target_value": True  # Exit if conditions ARE met
                }
            ]
        }
    )
    
    # Tool Executor configuration
    executor_config = tool_executor_config or ToolExecutorNodeConfigSchema(
        default_timeout=30.0,
        max_concurrent_executions=3,
        continue_on_error=True,
        include_error_details=True
    )
    
    # Tool Executor node
    executor_node = NodeConfig(
        node_id="tool_executor",
        node_name="tool_executor",
        node_config=executor_config.model_dump(exclude_none=True)
    )

    nodes = {
        INPUT_NODE_NAME: input_node,
        "llm_generator": llm_node,
        "check_loop_conditions": check_loop_conditions_node,
        "route_loop": route_loop_node,
        "tool_executor": executor_node,
    }
    
    edges = [
        # Input to LLM
        EdgeSchema(
            src_node_id=INPUT_NODE_NAME,
            dst_node_id="llm_generator",
            mappings=[
                EdgeMapping(src_field="user_prompt", dst_field="user_prompt"),
                EdgeMapping(src_field="system_prompt", dst_field="system_prompt"),
                # EdgeMapping(src_field="messages_history", dst_field="messages_history"),
            ]
        ),
        # LLM to Central State: Store message history and metadata
        EdgeSchema(
            src_node_id="llm_generator",
            dst_node_id="$graph_state",
            mappings=[
                EdgeMapping(src_field="current_messages", dst_field="messages_history"),
                EdgeMapping(src_field="metadata", dst_field="generation_metadata"),
                EdgeMapping(src_field="tool_calls", dst_field="latest_tool_calls"),
                EdgeMapping(src_field="text_content", dst_field="latest_response"),
                EdgeMapping(src_field="structured_output", dst_field="latest_structured_output"),
            ]
        ),
        # LLM to Check Loop Conditions
        EdgeSchema(
            src_node_id="llm_generator",
            dst_node_id="check_loop_conditions",
            mappings=[
                EdgeMapping(src_field="tool_calls", dst_field="tool_calls"),
            ]
        ),
        # State to Check Loop Conditions: Provide iteration count and metadata
        EdgeSchema(
            src_node_id="$graph_state",
            dst_node_id="check_loop_conditions",
            mappings=[
                EdgeMapping(src_field="generation_metadata", dst_field="generation_metadata"),
            ]
        ),
        # Check Loop Conditions to Route Loop
        EdgeSchema(
            src_node_id="check_loop_conditions",
            dst_node_id="route_loop",
            mappings=[
                EdgeMapping(src_field="condition_result", dst_field="condition_result"),
                EdgeMapping(src_field="tag_results", dst_field="tag_results"),
            ]
        ),
        # Route Loop to Tool Executor (continue with tool execution)
        EdgeSchema(
            src_node_id="route_loop",
            dst_node_id="tool_executor",
            mappings=[]  # No explicit mappings - relies on state
        ),
        # State to Tool Executor: Provide tool calls for execution
        EdgeSchema(
            src_node_id="$graph_state",
            dst_node_id="tool_executor",
            mappings=[
                EdgeMapping(src_field="latest_tool_calls", dst_field="tool_calls"),
            ]
        ),
        # Tool Executor to Central State: Store tool execution results
        EdgeSchema(
            src_node_id="tool_executor",
            dst_node_id="$graph_state",
            mappings=[
                EdgeMapping(src_field="tool_outputs", dst_field="tool_outputs"),
                EdgeMapping(src_field="tool_call_metadata", dst_field="tool_call_metadata"),
                EdgeMapping(src_field="successful_calls", dst_field="successful_calls"),
                EdgeMapping(src_field="failed_calls", dst_field="failed_calls"),
                EdgeMapping(src_field="internal_tool_user_prompt", dst_field="internal_tool_user_prompt"),
            ]
        ),
        # Tool Executor back to LLM Generator (continue loop)
        EdgeSchema(
            src_node_id="tool_executor",
            dst_node_id="llm_generator",
            mappings=[EdgeMapping(src_field="tool_outputs", dst_field="tool_outputs"), EdgeMapping(src_field="internal_tool_user_prompt", dst_field="user_prompt"),]  # No explicit mappings - relies on state
        ),
        # State to LLM Generator (for loop continuation): Provide updated context
        EdgeSchema(
            src_node_id="$graph_state",
            dst_node_id="llm_generator",
            mappings=[
                EdgeMapping(src_field="messages_history", dst_field="messages_history"),
                # EdgeMapping(src_field="tool_outputs", dst_field="tool_outputs"),
                # EdgeMapping(src_field="internal_tool_user_prompt", dst_field="user_prompt"),
            ]
        ),
    ]
    
    # Output node
    output_node = NodeConfig(
        node_id=OUTPUT_NODE_NAME,
        node_name=OUTPUT_NODE_NAME,
        node_config={}
    )
    
    nodes[OUTPUT_NODE_NAME] = output_node

    # State to Output: Provide final results
    edges.append(
        EdgeSchema(
            src_node_id="$graph_state",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="messages_history", dst_field="messages_history"),
                EdgeMapping(src_field="generation_metadata", dst_field="generation_metadata"),
                EdgeMapping(src_field="tool_outputs", dst_field="tool_outputs"),
                EdgeMapping(src_field="tool_call_metadata", dst_field="tool_call_metadata"),
                EdgeMapping(src_field="successful_calls", dst_field="successful_calls"),
                EdgeMapping(src_field="failed_calls", dst_field="failed_calls"),
                EdgeMapping(src_field="latest_response", dst_field="text_content"),
                EdgeMapping(src_field="latest_structured_output", dst_field="structured_output"),
            ]
        )
    )
    
    # Route Loop to Output (direct exit from loop conditions)
    edges.append(
        EdgeSchema(
            src_node_id="route_loop",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[]
        )
    )
    
    # Create the graph schema
    graph_schema = GraphSchema(
        nodes=nodes,
        edges=edges,
        input_node_id=INPUT_NODE_NAME,
        output_node_id=OUTPUT_NODE_NAME,
        metadata={
            "$graph_state": {  # 
                "reducer": {  # reducer
                    # central state key : reducer name
                    "messages_history": "add_messages",  # Use collect_values reducer for collecting states not initialized as lists!
                    "successful_calls": "add",
                    "failed_calls": "add",
                }
            },
        },
    )
    

    
    return graph_schema


async def run_llm_tool_integration_test(
    runtime_config: Dict[str, Any],
    llm_provider: LLMModelProvider,
    llm_model: str,
    user_prompt: str,
    available_tools: List[str],
    system_prompt: Optional[str] = None,
    structured_output_schema: Optional[Dict[str, Any]] = None,
    include_final_llm: bool = True,
    messages_history: Optional[List[Dict]] = None,
    parallel_tool_calls: bool = False,
    max_iterations: int = 5,  # Add max_iterations parameter
    **kwargs
) -> Dict[str, Any]:
    """
    Run an integrated test with LLM and Tool Executor nodes.
    
    Args:
        runtime_config: The runtime configuration dictionary.
        llm_provider: The LLM provider to use.
        llm_model: The LLM model name.
        user_prompt: The user's prompt/question.
        available_tools: List of tool names to make available.
        system_prompt: Optional system prompt override.
        structured_output_schema: Optional structured output schema.
        include_final_llm: Whether to include final LLM processing.
        messages_history: Optional message history for multi-turn conversations.
        parallel_tool_calls: Whether to allow parallel tool calls.
        max_iterations: Maximum number of iterations before forcing loop exit.
        **kwargs: Additional arguments for graph creation.
        
    Returns:
        Dict[str, Any]: The test results from the graph execution.
    """
    registry = setup_test_registry()
    
    # Prepare input data
    input_data = {
        "user_prompt": user_prompt
    }
    
    if system_prompt:
        input_data["system_prompt"] = system_prompt
    
    if messages_history:
        input_data["messages_history"] = messages_history
    
    # Create graph schema with looping support
    graph_schema = create_llm_tool_integration_graph(
        llm_provider=llm_provider,
        llm_model=llm_model,
        available_tools=available_tools,
        structured_output_schema=structured_output_schema,
        include_final_llm=include_final_llm,
        parallel_tool_calls=parallel_tool_calls,
        max_iterations=max_iterations,  # Pass max_iterations to graph creation
        **kwargs
    )
    
    builder = GraphBuilder(registry)
    graph_entities = builder.build_graph_entities(graph_schema)

    for node in graph_entities["node_instances"].values():
        node.billing_mode = False
    
    # Use provided runtime config with unique thread_id for isolation
    graph_runtime_config = graph_entities["runtime_config"]
    graph_runtime_config.update(runtime_config)
    test_runtime_config = graph_runtime_config
    test_runtime_config["thread_id"] = f"llm_tool_test_{uuid.uuid4()}"
    test_runtime_config["use_checkpointing"] = True
    
    adapter = LangGraphRuntimeAdapter()
    graph = adapter.build_graph(graph_entities)
    
    result = await adapter.aexecute_graph(
        graph=graph,
        input_data=input_data,
        config=test_runtime_config,
        output_node_id=graph_entities["output_node_id"],
        recursion_limit=200,
    )
    
    return result


# --- Test Classes ---

class TestLLMToolIntegration(unittest.IsolatedAsyncioTestCase):
    """Test comprehensive LLM and Tool Executor integration scenarios."""
    
    # Test setup attributes
    test_org_id: uuid.UUID
    test_user_id: uuid.UUID
    user_regular: MockUser
    run_job_regular: WorkflowRunJobCreate
    external_context: ExternalContextManager
    runtime_config_regular: Dict[str, Any]
    
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
        self.db_session = await get_async_session()
        
        # Initialize context for each test
        try:
            self.external_context = await get_external_context_manager_with_clients()
            registry = setup_test_registry()
            self.external_context.db_registry = registry
        except Exception as e:
            raise unittest.SkipTest(f"Failed to initialize external context: {e}")
        
        # Runtime Configs
        self.runtime_config_regular = {
            APPLICATION_CONTEXT_KEY: {
                "user": self.user_regular,
                "workflow_run_job": self.run_job_regular
            },
            EXTERNAL_CONTEXT_MANAGER_KEY: self.external_context,
            DB_SESSION_KEY: self.db_session
        }

    async def asyncTearDown(self):
        """Tear down test-specific resources after each test."""
        if self.db_session:
            await self.db_session.close()
        try:
            if self.external_context:
                await self.external_context.close()
        except Exception as e:
            print(f"Error in asyncTearDown: {e}")
    
    async def test_math_problem_solving_with_calculator(self):
        """Test LLM solving math problems using the calculator tool."""
        user_prompt = """
        I need help solving this math problem: What is the result of 15.7 * 8.3, and then what's the square root of that result?
        Please show me the step-by-step calculation.
        """
        
        structured_output_schema = MathProblemSolutionSchema.model_json_schema()
        
        result = await run_llm_tool_integration_test(
            runtime_config=self.runtime_config_regular,
            llm_provider=LLMModelProvider.ANTHROPIC,
            llm_model=AnthropicModels.CLAUDE_3_7_SONNET.value,
            user_prompt=user_prompt,
            available_tools=["math_calculator"],
            structured_output_schema=structured_output_schema
        )
        
        # Verify the response structure
        self.assertIn("structured_output", result)
        self.assertIsInstance(result["structured_output"], dict)
        
        # Validate the structured output
        try:
            solution = MathProblemSolutionSchema(**result["structured_output"])
            
            # Check that the solution includes expected elements
            self.assertIsInstance(solution.problem_understanding, str)
            self.assertGreater(len(solution.problem_understanding), 10)
            
            self.assertIsInstance(solution.solution_steps, list)
            self.assertGreater(len(solution.solution_steps), 0)
            
            self.assertIsInstance(solution.final_answer, str)
            self.assertGreater(len(solution.final_answer), 0)
            
            self.assertIsInstance(solution.confidence, float)
            self.assertGreaterEqual(solution.confidence, 0.0)
            self.assertLessEqual(solution.confidence, 1.0)
            
            print(f"Math Problem Solution: {solution.final_answer}")
            print(f"Confidence: {solution.confidence}")
            
        except Exception as e:
            self.fail(f"Structured output validation failed: {e}\nOutput: {json.dumps(result['structured_output'], indent=2)}")
    
    async def test_weather_based_recommendations(self):
        """Test LLM providing weather-based recommendations using weather lookup tool."""
        user_prompt = """
        I'm planning to visit San Francisco, CA tomorrow. Can you check the weather and give me recommendations 
        for outdoor activities, what to wear, and any travel advice?
        """
        
        structured_output_schema = WeatherRecommendationSchema.model_json_schema()
        
        result = await run_llm_tool_integration_test(
            runtime_config=self.runtime_config_regular,
            llm_provider=LLMModelProvider.ANTHROPIC,
            llm_model=AnthropicModels.CLAUDE_3_7_SONNET.value,
            user_prompt=user_prompt,
            available_tools=["weather_lookup"],
            structured_output_schema=structured_output_schema
        )
        
        # Verify the response structure
        self.assertIn("structured_output", result)
        self.assertIsInstance(result["structured_output"], dict)
        
        # Validate the structured output
        try:
            recommendations = WeatherRecommendationSchema(**result["structured_output"])
            
            # Check that the recommendations include expected elements
            self.assertIsInstance(recommendations.weather_summary, str)
            self.assertGreater(len(recommendations.weather_summary), 10)
            
            self.assertIsInstance(recommendations.recommendations, list)
            self.assertGreater(len(recommendations.recommendations), 0)
            
            self.assertIsInstance(recommendations.clothing_suggestions, list)
            self.assertGreater(len(recommendations.clothing_suggestions), 0)
            
            self.assertIsInstance(recommendations.travel_advice, str)
            self.assertGreater(len(recommendations.travel_advice), 10)
            
            print(f"Weather Summary: {recommendations.weather_summary}")
            print(f"Number of recommendations: {len(recommendations.recommendations)}")
            
        except Exception as e:
            self.fail(f"Structured output validation failed: {e}\nOutput: {json.dumps(result['structured_output'], indent=2)}")
    
    async def test_text_analysis_workflow(self):
        """Test LLM analyzing text using the text analyzer tool."""
        user_prompt = """
        Please analyze this text for me: "The new product launch was absolutely amazing! Customers are thrilled with the innovative features and exceptional quality. However, some users found the interface slightly confusing at first, though they quickly adapted. Overall, the feedback has been overwhelmingly positive, and sales are exceeding our expectations."
        
        I'd like a full analysis including sentiment, readability, keywords, and a summary, plus your insights and recommendations.
        """
        
        structured_output_schema = TextAnalysisReportSchema.model_json_schema()
        
        result = await run_llm_tool_integration_test(
            runtime_config=self.runtime_config_regular,
            llm_provider=LLMModelProvider.ANTHROPIC,
            llm_model=AnthropicModels.CLAUDE_3_7_SONNET.value,
            user_prompt=user_prompt,
            available_tools=["text_analyzer"],
            structured_output_schema=structured_output_schema
        )
        
        # Verify the response structure
        self.assertIn("structured_output", result)
        self.assertIsInstance(result["structured_output"], dict)
        
        # Validate the structured output
        try:
            analysis_report = TextAnalysisReportSchema(**result["structured_output"])
            
            # Check that the analysis includes expected elements
            self.assertIsInstance(analysis_report.analysis_summary, str)
            self.assertGreater(len(analysis_report.analysis_summary), 20)
            
            self.assertIsInstance(analysis_report.key_insights, list)
            self.assertGreater(len(analysis_report.key_insights), 0)
            
            self.assertIsInstance(analysis_report.recommendations, list)
            self.assertGreater(len(analysis_report.recommendations), 0)
            
            self.assertIsInstance(analysis_report.overall_assessment, str)
            self.assertGreater(len(analysis_report.overall_assessment), 10)
            
            print(f"Analysis Summary: {analysis_report.analysis_summary}")
            print(f"Key Insights: {len(analysis_report.key_insights)}")
            
        except Exception as e:
            self.fail(f"Structured output validation failed: {e}\nOutput: {json.dumps(result['structured_output'], indent=2)}")
    
    async def test_multi_tool_complex_workflow(self):
        """Test LLM using multiple tools in a complex workflow."""
        user_prompt = """
        I'm writing a blog post about productivity and need your help with calculations and analysis. 
        
        First, help me calculate: If someone works 8.5 hours per day, 5 days per week, for 48 weeks per year, 
        how many total hours do they work annually? Then calculate their hourly productivity if they complete 
        120 tasks per week.
        
        Next, analyze this sample text from my blog draft: "Productivity isn't just about working harder; 
        it's about working smarter. Successful people understand that efficiency comes from focus, not from 
        multitasking. They prioritize ruthlessly and eliminate distractions."
        
        Please provide a comprehensive analysis combining the calculations and text insights.
        """
        
        system_prompt = """
        You are a helpful assistant. You must ONLY use the tools that have been assigned to you. 
        Do not attempt to perform calculations or analysis manually - always use the appropriate 
        assigned tools for mathematical calculations and text analysis tasks. Only use the tools 
        provided to you and do not make assumptions about having access to other capabilities.
        """
        
        result = await run_llm_tool_integration_test(
            runtime_config=self.runtime_config_regular,
            llm_provider=LLMModelProvider.ANTHROPIC,
            llm_model=AnthropicModels.CLAUDE_SONNET_4.value,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            available_tools=["math_calculator", "text_analyzer"],
            include_final_llm=True,
            parallel_tool_calls=True,
        )
        
        # Verify the response structure
        self.assertIn("text_content", result)
        self.assertIsInstance(result["text_content"], str)
        # self.assertGreater(len(result["text_content"]), 100)
        
        # The response should mention both calculation and text analysis results
        text_content = result["text_content"].lower()
        # self.assertTrue(
        #     any(keyword in text_content for keyword in ["hours", "calculate", "annual"]),
        #     "Response should mention calculation results"
        # )
        # self.assertTrue(
        #     any(keyword in text_content for keyword in ["text", "analysis", "sentiment", "productivity"]),
        #     "Response should mention text analysis results"
        # )
        
        print(f"Multi-tool response length: {len(result['text_content'])}")
        print(f"Response preview: {result['text_content'][:200]}...")
    
    async def test_error_handling_with_invalid_tool_input(self):
        """Test error handling when tools receive invalid input."""
        user_prompt = """
        Please calculate the square root of -25 for me.
        """
        
        result = await run_llm_tool_integration_test(
            runtime_config=self.runtime_config_regular,
            llm_provider=LLMModelProvider.ANTHROPIC,
            llm_model=AnthropicModels.CLAUDE_3_7_SONNET.value,
            user_prompt=user_prompt,
            available_tools=["math_calculator"],
            include_final_llm=True
        )
        
        # Should still get a response even if tool fails
        self.assertIn("text_content", result)
        self.assertIsInstance(result["text_content"], str)
        self.assertGreater(len(result["text_content"]), 10)
        
        # Response should handle the error gracefully
        text_content = result["text_content"].lower()
        self.assertTrue(
            any(keyword in text_content for keyword in ["error", "cannot", "negative", "complex"]),
            "Response should acknowledge the mathematical limitation"
        )
        
        print(f"Error handling response: {result['text_content']}")
    
    async def test_looping_workflow_until_tool_calls_empty_or_max_iterations(self):
        """Test the looping workflow that continues until tool calls are empty or max iterations reached."""
        user_prompt = """
        I need help with a multi-step analysis. Please help me:
        1. First, calculate what 15 * 23 equals
        2. Then, take that result and calculate its square root
        3. Next, analyze this text for sentiment: "I absolutely love this new product! It's amazing and has exceeded all my expectations."
        4. Finally, check the weather in San Francisco, CA
        
        Please work through these steps one by one using the available tools. Use each tool as needed to gather all the information before providing your final comprehensive answer.
        """
        
        system_prompt = """
        You are a helpful assistant with access to calculation, text analysis, and weather tools. 
        
        IMPORTANT: Work through the user's request step by step. Use the tools in sequence to:
        1. Perform the calculation (15 * 23)
        2. Calculate the square root of that result
        3. Analyze the given text for sentiment
        4. Look up weather information for San Francisco
        
        After using each tool, you should consider if you need to use another tool to complete the user's request. 
        Only stop making tool calls when you have all the information needed to provide a complete answer.
        """
        
        result = await run_llm_tool_integration_test(
            runtime_config=self.runtime_config_regular,
            llm_provider=LLMModelProvider.ANTHROPIC,
            llm_model=AnthropicModels.CLAUDE_SONNET_4.value,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            available_tools=["math_calculator", "text_analyzer", "weather_lookup"],
            include_final_llm=True,
            max_iterations=5,  # Test with explicit max iterations
            parallel_tool_calls=False,  # Force sequential tool calls for predictable behavior
        )
        
        # Verify we got a result
        self.assertIn("text_content", result)
        self.assertIsInstance(result["text_content"], str)
        self.assertGreater(len(result["text_content"]), 200)
        
        # Verify the response contains information from multiple tool calls
        text_content = result["text_content"].lower()
        
        # Should mention calculation results
        self.assertTrue(
            any(keyword in text_content for keyword in ["345", "calculate", "multiply", "square root"]),
            "Response should mention calculation results (15 * 23 = 345)"
        )
        
        # Should mention text analysis
        self.assertTrue(
            any(keyword in text_content for keyword in ["sentiment", "positive", "analysis", "love"]),
            "Response should mention text sentiment analysis"
        )
        
        # Should mention weather information
        self.assertTrue(
            any(keyword in text_content for keyword in ["weather", "san francisco", "temperature"]),
            "Response should mention weather information"
        )
        
        # Check metadata for iteration information
        if "generation_metadata" in result:
            metadata = result["generation_metadata"]
            print(f"Total iterations performed: {metadata.get('iteration_count', 'N/A')}")
        
        # Verify we have tool outputs from multiple iterations
        # self.assertIn("tool_outputs", result)
        # self.assertIsInstance(result["tool_outputs"], list)
        # self.assertGreater(len(result["tool_outputs"]), 2)  # Should have multiple tool calls
        
        print(f"Multi-step looping response length: {len(result['text_content'])}")
        print(f"Number of tool outputs: {len(result['tool_outputs'])}")
        print(f"Tool types used: {[output.get('name') for output in result['tool_outputs']]}")
        print(f"Response preview: {result['text_content'][:300]}...")
    
    async def test_looping_workflow_reaches_max_iterations(self):
        """Test that the looping workflow properly exits when max iterations is reached."""
        user_prompt = """
        Please help me with calculations. Start by calculating 2 + 2, then keep doing more calculations 
        based on the results. For example, take the result and multiply by 3, then add 10, then divide by 2, etc. 
        Keep making calculations until you've done many steps.
        """
        
        system_prompt = """
        You are a helpful assistant. For this task, you should:
        1. Start with the initial calculation (2 + 2)
        2. Then continue making additional calculations using the previous results
        3. Always generate new tool calls to perform more calculations
        4. Keep going until the system stops you
        
        Always use the math_calculator tool for each calculation, even simple ones.
        """
        
        result = await run_llm_tool_integration_test(
            runtime_config=self.runtime_config_regular,
            llm_provider=LLMModelProvider.ANTHROPIC,
            llm_model=AnthropicModels.CLAUDE_3_7_SONNET.value,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            available_tools=["math_calculator"],
            include_final_llm=True,
            max_iterations=3,  # Set low limit to test max iterations behavior
            parallel_tool_calls=False,
        )
        
        # Verify we got a result
        self.assertIn("text_content", result)
        self.assertIsInstance(result["text_content"], str)
        # self.assertGreater(len(result["text_content"]), 50)
        
        # Check that we have multiple tool outputs (should hit the iteration limit)
        self.assertIn("tool_outputs", result)
        self.assertIsInstance(result["tool_outputs"], list)
        
        # Should have tool calls from multiple iterations but stopped at max
        tool_count = result["successful_calls"]
        self.assertGreaterEqual(tool_count, 3)  # At least 3 iterations worth
        self.assertLessEqual(tool_count, 6)  # But not too many (respecting the limit)
        
        # Check that all tool calls were math calculations
        tool_names = [output.get('name') for output in result['tool_outputs']]
        self.assertTrue(all(name == 'math_calculator' for name in tool_names))
        
        print(f"Max iterations test - Tool calls made: {tool_count}")
        print(f"Tool results: {[json.loads(output['content'])['result'] for output in result['tool_outputs'] if output.get('status') == 'success']}")
        print(f"Response length: {len(result['text_content'])}")
    ##
    async def test_looping_workflow_stops_when_no_tool_calls(self):
        """Test that the looping workflow properly exits when LLM stops generating tool calls."""
        user_prompt = """
        Please help me with this simple question: What is the capital of France?
        
        This is just a basic geography question that doesn't require any tools.
        """
        
        system_prompt = """
        You are a helpful assistant. Answer questions directly when you can. 
        Only use tools when they are necessary for the specific question asked.
        For basic knowledge questions, provide direct answers without using tools.
        """
        
        result = await run_llm_tool_integration_test(
            runtime_config=self.runtime_config_regular,
            llm_provider=LLMModelProvider.ANTHROPIC,
            llm_model=AnthropicModels.CLAUDE_3_7_SONNET.value,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            available_tools=["math_calculator", "text_analyzer", "weather_lookup"],
            include_final_llm=True,
            max_iterations=5,  # Allow up to 5 iterations
            parallel_tool_calls=False,
        )
        
        # Verify we got a result
        self.assertIn("text_content", result)
        self.assertIsInstance(result["text_content"], str)
        self.assertGreater(len(result["text_content"]), 10)
        
        # Should mention Paris in the response
        text_content = result["text_content"].lower()
        self.assertTrue(
            any(keyword in text_content for keyword in ["paris", "france", "capital"]),
            "Response should mention Paris as the capital of France"
        )
        
        # Should have minimal or no tool calls since this doesn't require tools
        tool_outputs = result.get("tool_outputs", [])
        self.assertLessEqual(len(tool_outputs), 1)  # Should be 0 or very few tool calls
        
        print(f"No-tools test - Tool calls made: {len(tool_outputs)}")
        print(f"Response: {result['text_content']}")
        print("✓ Loop properly exited when no tool calls were needed")
    
    async def test_openai_gpt4o_math_workflow(self):
        """Test OpenAI GPT-4o with math calculation workflow."""
        user_prompt = """
        I'm planning a budget and need help with some calculations:
        1. What's 2,500 * 12 (monthly savings for a year)?
        2. Then add 5,000 (bonus) to that result.
        3. Finally, if I invest that total amount and it grows by 7% annually, what would it be worth?
        
        Please show me each step clearly.
        """
        
        structured_output_schema = MathProblemSolutionSchema.model_json_schema()
        
        result = await run_llm_tool_integration_test(
            runtime_config=self.runtime_config_regular,
            llm_provider=LLMModelProvider.OPENAI,
            llm_model=OpenAIModels.GPT_4o.value,
            user_prompt=user_prompt,
            available_tools=["math_calculator"],
            structured_output_schema=structured_output_schema
        )
        
        # Verify the response structure
        self.assertIn("structured_output", result)
        self.assertIsInstance(result["structured_output"], dict)
        
        # Validate the structured output
        try:
            solution = MathProblemSolutionSchema(**result["structured_output"])
            
            # Check that the solution includes expected elements
            self.assertIsInstance(solution.problem_understanding, str)
            self.assertIsInstance(solution.solution_steps, list)
            self.assertGreater(len(solution.solution_steps), 1)  # Should have multiple steps
            self.assertIsInstance(solution.final_answer, str)
            
            # The final answer should contain numbers related to the calculation
            self.assertTrue(
                any(char.isdigit() for char in solution.final_answer),
                "Final answer should contain numerical results"
            )
            
            print(f"OpenAI Math Solution Steps: {len(solution.solution_steps)}")
            print(f"Final Answer: {solution.final_answer}")
            
        except Exception as e:
            self.fail(f"Structured output validation failed: {e}\nOutput: {json.dumps(result['structured_output'], indent=2)}")
    
    async def test_weather_and_text_combination_workflow(self):
        """Test combining weather lookup with text analysis in a single workflow."""
        user_prompt = """
        I'm writing a travel blog post about London, UK. Can you:
        1. Check the current weather in London
        2. Analyze this draft paragraph for me: "London's weather is notoriously unpredictable, but that's part of its charm. Whether it's a crisp autumn morning or a drizzly afternoon, the city always has something magical to offer visitors."
        
        Then help me improve the writing based on both the actual weather data and the text analysis.
        """
        
        result = await run_llm_tool_integration_test(
            runtime_config=self.runtime_config_regular,
            llm_provider=LLMModelProvider.ANTHROPIC,
            llm_model=AnthropicModels.CLAUDE_3_7_SONNET.value,
            user_prompt=user_prompt,
            available_tools=["weather_lookup", "text_analyzer"],
            include_final_llm=True
        )
        
        # Verify the response
        self.assertIn("text_content", result)
        self.assertIsInstance(result["text_content"], str)
        self.assertGreater(len(result["text_content"]), 150)
        
        # Response should mention both weather and text analysis
        text_content = result["text_content"].lower()
        self.assertTrue(
            any(keyword in text_content for keyword in ["weather", "temperature", "london"]),
            "Response should mention weather information"
        )
        self.assertTrue(
            any(keyword in text_content for keyword in ["text", "writing", "analysis", "paragraph"]),
            "Response should mention text analysis"
        )
        
        print(f"Combined workflow response length: {len(result['text_content'])}")
        print(f"Response contains weather info: {'weather' in text_content}")
        print(f"Response contains text analysis: {'analysis' in text_content}")
    
    async def test_tool_execution_with_direct_calculation_request(self):
        """Test workflow with a direct calculation request that should generate tool calls."""
        user_prompt = """
        Calculate 45 * 67 for me. I need the exact result using mathematical tools.
        """
        
        system_prompt = """
        You are a helpful assistant. Always use the available mathematical tools for calculations, 
        even simple ones, to ensure accuracy. Do not perform manual calculations.
        """
        
        result = await run_llm_tool_integration_test(
            runtime_config=self.runtime_config_regular,
            llm_provider=LLMModelProvider.ANTHROPIC,
            llm_model=AnthropicModels.CLAUDE_3_7_SONNET.value,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            available_tools=["math_calculator"],
            include_final_llm=True
        )
        
        # Should get both tool outputs and final text response
        self.assertIn("tool_outputs", result)
        self.assertIn("text_content", result)
        self.assertIn("successful_calls", result)
        self.assertIn("failed_calls", result)
        
        self.assertIsInstance(result["tool_outputs"], list)
        self.assertGreater(len(result["tool_outputs"]), 0)
        self.assertEqual(result["successful_calls"], 1)
        self.assertEqual(result["failed_calls"], 0)
        
        # Check the tool output content
        tool_output = result["tool_outputs"][0]
        self.assertEqual(tool_output["name"], "math_calculator")
        self.assertEqual(tool_output["status"], "success")
        
        # Parse and verify the calculation result
        output_content = json.loads(tool_output["content"])
        self.assertIn("result", output_content)
        self.assertEqual(output_content["result"], 3015)  # 45 * 67 = 3015
        
        # Verify final text response mentions the result
        text_content = result["text_content"].lower()
        self.assertTrue(
            any(keyword in text_content for keyword in ["3015", "calculation", "result"]),
            "Final response should mention the calculation result"
        )
        
        print(f"Direct tool output: {output_content}")
        print(f"Final response includes result: {'3015' in result['text_content']}")


if __name__ == "__main__":
    unittest.main()
