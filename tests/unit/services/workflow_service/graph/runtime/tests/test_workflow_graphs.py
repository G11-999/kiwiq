"""
Workflow graph tests.

This module contains test implementations for workflow graphs,
demonstrating various node types and workflow patterns.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional, ClassVar, Type, cast, Tuple, Callable
from pydantic import Field
from enum import Enum
import json

from workflow_service.config.constants import (
    INPUT_NODE_NAME, OUTPUT_NODE_NAME, HITL_NODE_NAME_PREFIX,
    GRAPH_STATE_SPECIAL_NODE_NAME, TEMP_STATE_UPDATE_KEY, ROUTER_CHOICE_KEY
)
from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.registry.nodes.core.base import BaseNode
from workflow_service.graph.graph import EdgeSchema, GraphSchema, NodeConfig, EdgeMapping
from workflow_service.registry.registry import DBRegistry
from workflow_service.graph.builder import GraphBuilder
from workflow_service.registry.nodes.core.dynamic_nodes import (
    BaseDynamicNode, InputNode, OutputNode, HITLNode, 
    DynamicRouterNode, RouterSchema, DynamicSchema, 
    ConstructDynamicSchema, DynamicSchemaFieldConfig, 
)


from workflow_service.config.constants import (
    INPUT_NODE_NAME, OUTPUT_NODE_NAME, HITL_NODE_NAME_PREFIX,
    GRAPH_STATE_SPECIAL_NODE_NAME, TEMP_STATE_UPDATE_KEY, ROUTER_CHOICE_KEY, HITL_USER_PROMPT_KEY, HITL_USER_SCHEMA_KEY
)

# Import graph-related classes
from workflow_service.graph.runtime.adapter import LangGraphRuntimeAdapter

# ===============================
# Test Node Implementations
# ===============================

# Basic Schema Definitions
class NumberSchema(BaseSchema):
    """Schema for a number."""
    value: float = Field(description="Numeric value")
    description: Optional[str] = Field(None, description="Optional description")

class TextSchema(BaseSchema):
    """Schema for text content."""
    text: str = Field(description="Text content")
    metadata: Optional[Dict[str, str]] = Field(default_factory=dict, description="Optional metadata")

class RouteChoiceSchema(BaseSchema):
    """Schema for route selection."""
    route_name: str = Field(description="Name of the selected route")
    reason: Optional[str] = Field(None, description="Reason for selection")

# Basic Node Implementations
class NumberGeneratorNode(BaseNode[None, NumberSchema, NumberSchema]):
    """
    A node that generates a number based on configuration.
    
    This node doesn't require input and outputs a number with an optional description.
    """
    node_name: ClassVar[str] = "number_generator"
    node_version: ClassVar[str] = "1.0.0"
    
    input_schema_cls = None
    output_schema_cls = NumberSchema
    config_schema_cls = NumberSchema
    
    def process(self, input_data, config: Dict[str, Any], *args: Any, **kwargs: Any) -> NumberSchema:
        """
        Generate a number based on configuration.
        
        Args:
            input_data: None (this node doesn't require input)
            config: Configuration containing the number value and description
            
        Returns:
            NumberSchema: The generated number with description
        """
        # Use value from config or default to 42
        value = config.get("value", 42.0)
        description = config.get("description", "Generated number")
        
        return NumberSchema(value=value, description=description)

class NumberMultiplierNode(BaseNode[NumberSchema, NumberSchema, NumberSchema]):
    """
    A node that multiplies an input number by a configured factor.
    
    Takes a number as input and multiplies it by the factor specified in the config.
    """
    node_name: ClassVar[str] = "number_multiplier"
    node_version: ClassVar[str] = "1.0.0"
    
    input_schema_cls = NumberSchema
    output_schema_cls = NumberSchema
    config_schema_cls = NumberSchema
    
    def process(self, input_data: NumberSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> NumberSchema:
        """
        Multiply the input number by the configured factor.
        
        Args:
            input_data: Input number to multiply
            config: Configuration containing the multiplication factor
            
        Returns:
            NumberSchema: The result of the multiplication with description
        """
        # Use value from config or default to 2.0
        factor = config.get("value", 2.0)
        
        # Multiply the input value by the factor
        result_value = input_data.value * factor
        
        # Create a description for the result
        description = f"{input_data.description} multiplied by {factor}"
        
        return NumberSchema(value=result_value, description=description)

class TextGeneratorNode(BaseNode[None, TextSchema, TextSchema]):
    """
    A node that generates text based on configuration.
    
    This node doesn't require input and outputs text with optional metadata.
    """
    node_name: ClassVar[str] = "text_generator"
    node_version: ClassVar[str] = "1.0.0"
    
    input_schema_cls = None
    output_schema_cls = TextSchema
    config_schema_cls = TextSchema
    
    def process(self, input_data, config: Dict[str, Any], *args: Any, **kwargs: Any) -> TextSchema:
        """
        Generate text based on configuration.
        
        Args:
            input_data: None (this node doesn't require input)
            config: Configuration containing the text and metadata
            
        Returns:
            TextSchema: The generated text with metadata
        """
        # Use text from config or default
        text = "Default generated text"
        metadata = {"test_metadata_key": "test_metadata_value"}
        
        return TextSchema(text=text, metadata=metadata)

class TextProcessorNode(BaseNode[TextSchema, TextSchema, None]):
    """
    A node that processes text (converts to uppercase).
    
    Takes text as input and returns it in uppercase.
    """
    node_name: ClassVar[str] = "text_processor"
    node_version: ClassVar[str] = "1.0.0"
    
    input_schema_cls = TextSchema
    output_schema_cls = TextSchema
    config_schema_cls = None
    
    def process(self, input_data: TextSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> TextSchema:
        """
        Process text (convert to uppercase).
        
        Args:
            input_data: Input text to process
            config: Not used
            
        Returns:
            TextSchema: The processed text with metadata
        """
        # Convert text to uppercase
        processed_text = input_data.text.upper()
        
        # Add processing info to metadata
        metadata = dict(input_data.metadata)
        metadata["processed"] = "true"
        metadata["processor"] = self.node_name
        
        return TextSchema(text=processed_text, metadata=metadata)

class SimpleRouterConfig(BaseSchema):
    threshold: float = Field(default=50.0, description="Threshold for routing decisions")
    choices: List[str] = Field(default_factory=list, description="List of choices for routing decisions", min_length=1)
    allow_multiple: bool = Field(default=False, description="Allow multiple choices to be selected")

# Router Node Implementation
class SimpleRouterNode(DynamicRouterNode):
    """
    A simple router node that selects between two paths.
    
    This node makes routing decisions based on a numeric threshold:
    - If the input number is greater than the threshold, route to "high_path"
    - Otherwise, route to "low_path"
    """
    node_name: ClassVar[str] = "simple_router"
    node_version: ClassVar[str] = "1.0.0"

    # input_schema_cls = None
    # output_schema_cls = SimpleRouterConfig
    config_schema_cls: ClassVar[Type[SimpleRouterConfig]] = SimpleRouterConfig
    # config_schema_cls = ClassVar[SimpleRouterConfig]

    # instance config
    config: SimpleRouterConfig
    
    def process(self, input_data: DynamicSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """
        Decide routing based on a numeric value compared to a threshold.
        
        Args:
            input_data: Input data containing a 'value' field
            config: Router configuration
            
        Returns:
            Dict: Contains the routing decision and state update
        """
        # Default threshold is 50
        threshold = 50.0
        if hasattr(self, "config") and hasattr(self.config, "threshold"):
            threshold = getattr(self.config, "threshold", 50.0)
        
        # Extract value from input
        value = getattr(input_data, "value", 0.0)
        
        # Make routing decision
        if value > threshold:
            route = "high_path"
            reason = f"Value {value} is greater than threshold {threshold}"
        else:
            route = "low_path"
            reason = f"Value {value} is less than or equal to threshold {threshold}"
        
        # Get destination node ID from choices
        destination = None
        for choice in self.config.choices:
            if choice.endswith(route):
                destination = choice
                break
        
        if not destination:
            raise ValueError(f"No destination found for route {route}")
        
        # Return routing decision and pass through input data
        if input_data is not None:
            output_data = self.__class__.output_schema_cls(**input_data.model_dump()) if self.__class__.output_schema_cls is not None else input_data
        else:
            output_data =  self.__class__.output_schema_cls() if self.__class__.output_schema_cls is not None else input_data

        return {
            TEMP_STATE_UPDATE_KEY: output_data,
            ROUTER_CHOICE_KEY: destination
        }

# HITL Node Implementation
class ReviewHITLNode(HITLNode):
    """
    A human-in-the-loop node for content review.
    
    This node presents data to a human reviewer and collects their feedback.
    """
    node_name: ClassVar[str] = f"{HITL_NODE_NAME_PREFIX}review"
    node_version: ClassVar[str] = "1.0.0"
    
    def process(self, input_data: DynamicSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> DynamicSchema:
        """
        Process input data through human review.
        
        In a real implementation, this would present data to a human and wait for feedback.
        For testing purposes, we simulate approval without modification.
        
        Args:
            input_data: Data to review
            config: Configuration for the review
            
        Returns:
            DynamicSchema: Reviewed/approved data
        """
        # For testing purposes, we have a simplified implementation
        # that just approves the input without modification
        
        # In a real application, this would:
        # 1. Send data for human review
        # 2. Pend the workflow execution
        # 3. Resume when human input is received
        # 4. Return the human-modified data
        
        # For now, we'll just pass through the data

        # print("input_data", json.dumps(input_data.model_dump(), indent=4))
        return self.output_schema_cls(**input_data)

# Transform Node (Number to Text)
class DataTransformNode(BaseNode[NumberSchema, TextSchema, None]):
    """
    A node that transforms a number into text with analysis.
    
    This node demonstrates converting between different schema types.
    """
    node_name: ClassVar[str] = "data_transformer"
    node_version: ClassVar[str] = "1.0.0"
    
    input_schema_cls = NumberSchema
    output_schema_cls = TextSchema
    config_schema_cls = None
    
    def process(self, input_data: NumberSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> TextSchema:
        """
        Transform a number into text with analysis.
        
        Args:
            input_data: Number data to transform
            config: Not used
            
        Returns:
            TextSchema: Text representation with analysis
        """
        # Create a text analysis of the number
        value = input_data.value
        categories = ["very low", "low", "medium", "high", "very high"]
        category_index = min(int(value / 20), 4)  # 0-19: very low, 20-39: low, etc.
        
        analysis = f"The value {value} is categorized as '{categories[category_index]}'."
        if input_data.description:
            analysis += f" Original description: {input_data.description}"
        
        # Add metadata about the source
        metadata = {
            "source_value": str(value),
            "category": categories[category_index],
            "transformer": self.node_name
        }
        
        return TextSchema(text=analysis, metadata=metadata)

# Join Node (combines data from multiple paths)
class JoinDataNode(BaseNode[TextSchema, TextSchema, None]):
    """
    A node that joins data from multiple paths.
    
    This node demonstrates merging data from different paths in a workflow.
    """
    node_name: ClassVar[str] = "join_data"
    node_version: ClassVar[str] = "1.0.0"
    # dynamic_schemas: ClassVar[bool] = True

    input_schema_cls = TextSchema
    output_schema_cls = TextSchema
    config_schema_cls = None
    
    def process(self, input_data: DynamicSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> DynamicSchema:
        """
        Join data from multiple inputs.
        
        Args:
            input_data: Input data to join
            config: Not used
            
        Returns:
            DynamicSchema: Combined data
        """
        # Get the text content
        text = getattr(input_data, "text", "")
        
        # Get metadata (if any)
        metadata = getattr(input_data, "metadata", {})
        
        # Add joining information
        joined_metadata = dict(metadata)
        joined_metadata["joined_by"] = self.node_name
        joined_metadata["join_time"] = "simulated_timestamp"
        
        return self.__class__.output_schema_cls(
            text=text,
            metadata=joined_metadata
        )




# ===============================
# Graph Creation Functions
# ===============================

def create_simple_number_graph() -> GraphSchema:
    """
    Create a simple workflow graph with number generator and multiplier nodes.
    
    Returns:
        GraphSchema: The constructed graph schema
    """
    # Create node configurations
    input_node = NodeConfig(
            node_id=INPUT_NODE_NAME,
            node_name=INPUT_NODE_NAME,
            node_version="0.1.0",
            node_config={}
        )
    
    output_node = NodeConfig(
        node_id=OUTPUT_NODE_NAME,
        node_name=OUTPUT_NODE_NAME,
        node_version="0.1.0",
        node_config={}
    )
    
    generator_node = NodeConfig(
        node_id="generator1",
        node_name="number_generator",
        node_version="1.0.0",
        node_config={
            "value": 42.0,
            "description": "Initial number"
        }
    )
    
    multiplier_node = NodeConfig(
        node_id="multiplier1",
        node_name="number_multiplier",
        node_version="1.0.0",
        node_config={
            "value": 2.5,
            "description": "Multiplication factor"
        }
    )
    
    # Create edges
    edges = [
        # Input to Generator
        EdgeSchema(
            src_node_id=INPUT_NODE_NAME,
            dst_node_id="generator1",
            mappings=[]  # No mappings needed as generator doesn't require input
        ),
        # Generator to Multiplier
        EdgeSchema(
            src_node_id="generator1",
            dst_node_id="multiplier1",
            mappings=[
                EdgeMapping(src_field="value", dst_field="value"),
                EdgeMapping(src_field="description", dst_field="description")
            ]
        ),
        # Multiplier to Output
        EdgeSchema(
            src_node_id="multiplier1",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="value", dst_field="result_value"),
                EdgeMapping(src_field="description", dst_field="result_description")
            ]
        )
    ]
    
    # Create graph schema
    graph_schema = GraphSchema(
        nodes={
            INPUT_NODE_NAME: input_node,
            OUTPUT_NODE_NAME: output_node,
            "generator1": generator_node,
            "multiplier1": multiplier_node
        },
        edges=edges,
        input_node_id=INPUT_NODE_NAME,
        output_node_id=OUTPUT_NODE_NAME
    )
    
    return graph_schema

def create_router_graph() -> GraphSchema:
    """
    Create a workflow graph with a router node to demonstrate conditional routing.
    
    Returns:
        GraphSchema: The constructed graph schema
    """
    # Create node configurations
    input_node = NodeConfig(
        node_id=INPUT_NODE_NAME,
        node_name=INPUT_NODE_NAME,
        node_version="0.1.0",
        node_config={},
        # Now specify dynamic schema directly in the graph config
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "value": DynamicSchemaFieldConfig(type="float", required=True, description="Input value to route"),
            "description": DynamicSchemaFieldConfig(type="str", required=False, description="Optional description")
        })
    )
    
    output_node = NodeConfig(
        node_id=OUTPUT_NODE_NAME,
        node_name=OUTPUT_NODE_NAME,
        node_version="0.1.0",
        node_config={},
        # Specify output schema for output node
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "result_value": DynamicSchemaFieldConfig(type="dict", required=True, description="Result value", keys_type="str", values_type="str"),
            "result_text": DynamicSchemaFieldConfig(type="str", required=True, description="Result text")
        })
    )
    
    # Create nodes for the high and low paths
    multiplier_node = NodeConfig(
        node_id="high_path",
        node_name="number_multiplier",
        node_version="1.0.0",
        node_config={
            "value": 3.0,
            "description": "High path multiplication"
        }
    )
    
    text_gen_node = NodeConfig(
        node_id="low_path",
        node_name="text_generator",
        node_version="1.0.0",
        node_config={
            "text": "Low value detected",
            "metadata": {"path": "low"}
        }
    )
    
    # Create transformer nodes to ensure consistent output types
    high_transform_node = NodeConfig(
        node_id="high_transform",
        node_name="data_transformer",
        node_version="1.0.0",
        node_config={}
    )
    
    text_processor_node = NodeConfig(
        node_id="low_transform",
        node_name="text_processor",
        node_version="1.0.0",
        node_config={}
    )
    
    # Create router node
    router_node = NodeConfig(
        node_id="router",
        node_name="simple_router",
        node_version="1.0.0",
        node_config={
            # "threshold": 50.0,
            "choices": ["high_path", "low_path"],
            "allow_multiple": False
        },
        # Define dynamic input schema for router
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "value": DynamicSchemaFieldConfig(type="float", required=True, description="Value to evaluate"),
            "description": DynamicSchemaFieldConfig(type="str", required=False, description="Description")
        })
    )
    
    # Create edges
    edges = [
        # Input to Router
        EdgeSchema(
            src_node_id=INPUT_NODE_NAME,
            dst_node_id="router",
            mappings=[
                EdgeMapping(src_field="value", dst_field="value"),
                EdgeMapping(src_field="description", dst_field="description")
            ]
        ),
        # Router to High Path (multiplier)
        EdgeSchema(
            src_node_id="router",
            dst_node_id="high_path",
            mappings=[
                EdgeMapping(src_field="value", dst_field="value"),
                EdgeMapping(src_field="description", dst_field="description")
            ]
        ),
        # Router to Low Path (text generator)
        EdgeSchema(
            src_node_id="router",
            dst_node_id="low_path",
            mappings=[]  # Text generator doesn't require input
        ),
        # High Path to Transform
        EdgeSchema(
            src_node_id="high_path",
            dst_node_id="high_transform",
            mappings=[
                EdgeMapping(src_field="value", dst_field="value"),
                EdgeMapping(src_field="description", dst_field="description")
            ]
        ),
        # Low Path to Text Processor
        EdgeSchema(
            src_node_id="low_path",
            dst_node_id="low_transform",
            mappings=[
                EdgeMapping(src_field="text", dst_field="text"),
                EdgeMapping(src_field="metadata", dst_field="metadata")
            ]
        ),
        # High Transform to Output
        EdgeSchema(
            src_node_id="high_transform",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="text", dst_field="result_text"),
                # Also pass the original value from router to output
                EdgeMapping(src_field="metadata", dst_field="result_value", override_type_validation=True)
            ]
        ),
        # Low Transform to Output
        EdgeSchema(
            src_node_id="low_transform",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="text", dst_field="result_text"),
                # Use a default value for result_value since low path doesn't produce a number
                EdgeMapping(src_field="metadata", dst_field="result_value", override_type_validation=True)
            ]
        )
    ]
    
    # Create graph schema
    graph_schema = GraphSchema(
        nodes={
            INPUT_NODE_NAME: input_node,
            OUTPUT_NODE_NAME: output_node,
            "router": router_node,
            "high_path": multiplier_node,
            "low_path": text_gen_node,
            "high_transform": high_transform_node,
            "low_transform": text_processor_node
        },
        edges=edges,
        input_node_id=INPUT_NODE_NAME,
        output_node_id=OUTPUT_NODE_NAME
    )
    
    return graph_schema

def create_hitl_graph() -> GraphSchema:
    """
    Create a workflow graph with a human-in-the-loop node.
    
    Returns:
        GraphSchema: The constructed graph schema
    """
    # Create node configurations
    input_node = NodeConfig(
        node_id=INPUT_NODE_NAME,
        node_name=INPUT_NODE_NAME,
        node_version="0.1.0",
        node_config={},
        # Define input schema explicitly
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "value": DynamicSchemaFieldConfig(type="float", required=True, description="Input value for processing"),
            "description": DynamicSchemaFieldConfig(type="str", required=False, description="Optional description")
        })
    )
    
    output_node = NodeConfig(
        node_id=OUTPUT_NODE_NAME,
        node_name=OUTPUT_NODE_NAME,
        node_version="0.1.0",
        node_config={},
        # Define output schema explicitly
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "text": DynamicSchemaFieldConfig(type="str", required=True, description="Reviewed text content"),
            "metadata": DynamicSchemaFieldConfig(
                type="dict",
                keys_type="str",
                values_type="str",
                required=False,
                description="Additional metadata including review information"
            )
        })
    )
    
    transform_node = NodeConfig(
        node_id="transform",
        node_name="data_transformer",
        node_version="1.0.0",
        node_config={}
    )
    
    # Human-in-the-loop node for review
    hitl_node = NodeConfig(
        node_id="review",
        node_name=f"{HITL_NODE_NAME_PREFIX}review",
        node_version="1.0.0",
        node_config={},
        # Define both input and output schemas for HITL node
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "text": DynamicSchemaFieldConfig(type="str", required=True, description="Text to review"),
            "metadata": DynamicSchemaFieldConfig(
                type="dict",
                keys_type="str",
                values_type="str",
                required=False,
                description="Additional metadata"
            )
        }),
        dynamic_output_schema=ConstructDynamicSchema(fields={
            "text": DynamicSchemaFieldConfig(type="str", required=True, description="Reviewed text"),
            "metadata": DynamicSchemaFieldConfig(
                type="dict",
                keys_type="str",
                values_type="str",
                required=False,
                description="Metadata with review information"
            ),
            "review_notes": DynamicSchemaFieldConfig(type="str", required=False, description="Notes from reviewer")
        })
    )
    
    # Create edges
    edges = [
        # Input to Transform
        EdgeSchema(
            src_node_id=INPUT_NODE_NAME,
            dst_node_id="transform",
            mappings=[
                EdgeMapping(src_field="value", dst_field="value"),
                EdgeMapping(src_field="description", dst_field="description")
            ]
        ),
        # Transform to HITL Review
        EdgeSchema(
            src_node_id="transform",
            dst_node_id="review",
            mappings=[
                EdgeMapping(src_field="text", dst_field="text"),
                EdgeMapping(src_field="metadata", dst_field="metadata")
            ]
        ),
        # HITL Review to Output
        EdgeSchema(
            src_node_id="review",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="text", dst_field="text"),
                EdgeMapping(src_field="metadata", dst_field="metadata")
            ]
        )
    ]
    
    # Create graph schema
    graph_schema = GraphSchema(
        nodes={
            INPUT_NODE_NAME: input_node,
            OUTPUT_NODE_NAME: output_node,
            "transform": transform_node,
            "review": hitl_node
        },
        edges=edges,
        input_node_id=INPUT_NODE_NAME,
        output_node_id=OUTPUT_NODE_NAME
    )
    
    return graph_schema

def create_dynamic_nodes_connected_graph() -> GraphSchema:
    """
    Create a workflow graph where dynamic nodes connect to each other.
    
    Returns:
        GraphSchema: The constructed graph schema
    """
    # Create node configurations
    input_node = NodeConfig(
        node_id=INPUT_NODE_NAME,
        node_name=INPUT_NODE_NAME,
        node_version="0.1.0",
        node_config={},
        # Define output schema explicitly
        dynamic_output_schema=ConstructDynamicSchema(fields={
            "value": DynamicSchemaFieldConfig(type="float", required=True, description="Input value"),
            "message": DynamicSchemaFieldConfig(type="str", required=True, description="Input message")
        })
    )
    
    output_node = NodeConfig(
        node_id=OUTPUT_NODE_NAME,
        node_name=OUTPUT_NODE_NAME,
        node_version="0.1.0",
        node_config={},
        # Define input schema explicitly
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "final_value": DynamicSchemaFieldConfig(type="float", required=True, description="Final value"),
            "final_message": DynamicSchemaFieldConfig(type="str", required=True, description="Final message"),
            "review_notes": DynamicSchemaFieldConfig(type="str", required=False, description="Review notes")
        })
    )
    
    # Human-in-the-loop node 1
    hitl_node1 = NodeConfig(
        node_id="review1",
        node_name=f"{HITL_NODE_NAME_PREFIX}review",
        node_version="1.0.0",
        node_config={},
        # Define only input schema - output schema will be inferred from connection to hitl_node2
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "value": DynamicSchemaFieldConfig(type="float", required=True, description="Value to review"),
            "message": DynamicSchemaFieldConfig(type="str", required=True, description="Message to review")
        })
    )
    
    # Human-in-the-loop node 2
    hitl_node2 = NodeConfig(
        node_id="review2",
        node_name=f"{HITL_NODE_NAME_PREFIX}review",
        node_version="1.0.0",
        node_config={},
        # Define only output schema - input schema will be inferred from connection to hitl_node1
        dynamic_output_schema=ConstructDynamicSchema(fields={
            "final_value": DynamicSchemaFieldConfig(type="float", required=True, description="Reviewed value"),
            "final_message": DynamicSchemaFieldConfig(type="str", required=True, description="Reviewed message"),
            "review_notes": DynamicSchemaFieldConfig(type="str", required=False, description="Notes from reviewer")
        })
    )
    
    # Create edges
    edges = [
        # Input to HITL1
        EdgeSchema(
            src_node_id=INPUT_NODE_NAME,
            dst_node_id="review1",
            mappings=[
                EdgeMapping(src_field="value", dst_field="value"),
                EdgeMapping(src_field="message", dst_field="message")
            ]
        ),
        # HITL1 to HITL2 (dynamic nodes connecting to each other)
        EdgeSchema(
            src_node_id="review1",
            dst_node_id="review2",
            mappings=[
                EdgeMapping(src_field="value", dst_field="value"),
                EdgeMapping(src_field="message", dst_field="message")
            ]
        ),
        # HITL2 to Output
        EdgeSchema(
            src_node_id="review2",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="final_value", dst_field="final_value"),
                EdgeMapping(src_field="final_message", dst_field="final_message"),
                EdgeMapping(src_field="review_notes", dst_field="review_notes")
            ]
        )
    ]
    
    # Create graph schema
    graph_schema = GraphSchema(
        nodes={
            INPUT_NODE_NAME: input_node,
            OUTPUT_NODE_NAME: output_node,
            "review1": hitl_node1,
            "review2": hitl_node2
        },
        edges=edges,
        input_node_id=INPUT_NODE_NAME,
        output_node_id=OUTPUT_NODE_NAME
    )
    
    return graph_schema

def create_central_state_graph() -> GraphSchema:
    """
    Create a workflow graph where dynamic nodes connect to central state.
    
    This demonstrates how a dynamic node can define a central state field.
    
    Returns:
        GraphSchema: The constructed graph schema
    """
    # Create node configurations
    input_node = NodeConfig(
        node_id=INPUT_NODE_NAME,
        node_name=INPUT_NODE_NAME,
        node_version="0.1.0",
        node_config={},
        # Define output schema explicitly
        dynamic_output_schema=ConstructDynamicSchema(fields={
            "user_id": DynamicSchemaFieldConfig(type="str", required=True, description="User ID"),
            "query": DynamicSchemaFieldConfig(type="str", required=True, description="User query")
        })
    )
    
    output_node = NodeConfig(
        node_id=OUTPUT_NODE_NAME,
        node_name=OUTPUT_NODE_NAME,
        node_version="0.1.0",
        node_config={},
        # Define input schema explicitly
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "response": DynamicSchemaFieldConfig(type="str", required=True, description="Final response"),
            "user_id": DynamicSchemaFieldConfig(type="str", required=True, description="User ID")
        })
    )
    
    # Text generator node
    text_gen_node = NodeConfig(
        node_id="generator",
        node_name="text_generator",
        node_version="1.0.0",
        node_config={
            "text": "Generated response",
            "metadata": {"type": "response"}
        }
    )
    
    # HITL node with a custom field that will define a central state field
    hitl_node = NodeConfig(
        node_id="review",
        node_name=f"{HITL_NODE_NAME_PREFIX}review",
        node_version="1.0.0",
        node_config={},
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "text": DynamicSchemaFieldConfig(type="str", required=True, description="Text to review"),
            "metadata": DynamicSchemaFieldConfig(
                type="dict",
                keys_type="str",
                values_type="str",
                required=False,
                description="Metadata"
            )
        }),
        dynamic_output_schema=ConstructDynamicSchema(fields={
            "response": DynamicSchemaFieldConfig(type="str", required=True, description="Reviewed response"),
            "audit_log": DynamicSchemaFieldConfig(
                type="str", 
                required=True, 
                description="Audit log entry - will define a central state field"
            )
        })
    )
    
    # Create edges
    edges = [
        # Input to Central State for user_id
        EdgeSchema(
            src_node_id=INPUT_NODE_NAME,
            dst_node_id=GRAPH_STATE_SPECIAL_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="user_id", dst_field="user_id")
            ]
        ),
        # Input to Text Generator
        EdgeSchema(
            src_node_id=INPUT_NODE_NAME,
            dst_node_id="generator",
            mappings=[
                EdgeMapping(src_field="query", dst_field="text")
            ]
        ),
        # Text Generator to HITL
        EdgeSchema(
            src_node_id="generator",
            dst_node_id="review",
            mappings=[
                EdgeMapping(src_field="text", dst_field="text"),
                EdgeMapping(src_field="metadata", dst_field="metadata")
            ]
        ),
        # HITL to Output
        EdgeSchema(
            src_node_id="review",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="response", dst_field="response")
            ]
        ),
        # HITL to Central State for audit_log (dynamic field defining central state)
        EdgeSchema(
            src_node_id="review",
            dst_node_id=GRAPH_STATE_SPECIAL_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="audit_log", dst_field="audit_log")
            ]
        ),
        # Central State to Output for user_id
        EdgeSchema(
            src_node_id=GRAPH_STATE_SPECIAL_NODE_NAME,
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="user_id", dst_field="user_id")
            ]
        )
    ]
    
    # Create graph schema
    graph_schema = GraphSchema(
        nodes={
            INPUT_NODE_NAME: input_node,
            OUTPUT_NODE_NAME: output_node,
            "generator": text_gen_node,
            "review": hitl_node
        },
        edges=edges,
        input_node_id=INPUT_NODE_NAME,
        output_node_id=OUTPUT_NODE_NAME
    )
    
    return graph_schema

def create_complex_graph() -> GraphSchema:
    """
    Create a complex workflow graph with multiple paths, routers, and transforms.
    
    Returns:
        GraphSchema: The constructed graph schema
    """
    # Create node configurations
    input_node = NodeConfig(
        node_id=INPUT_NODE_NAME,
        node_name=INPUT_NODE_NAME,
        node_version="0.1.0",
        node_config={},
        # Define input schema explicitly
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "value": DynamicSchemaFieldConfig(type="float", required=True, description="Input value"),
            "description": DynamicSchemaFieldConfig(type="str", required=False, description="Optional description")
        })
    )
    
    output_node = NodeConfig(
        node_id=OUTPUT_NODE_NAME,
        node_name=OUTPUT_NODE_NAME,
        node_version="0.1.0",
        node_config={},
        # Define output schema explicitly
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "result_text": DynamicSchemaFieldConfig(type="str", required=True, description="Result text"),
            "result_metadata": DynamicSchemaFieldConfig(
                type="dict",
                keys_type="str",
                values_type="str",
                required=False,
                description="Result metadata"
            )
        })
    )
    
    # Nodes for the complex graph
    nodes = {
        INPUT_NODE_NAME: input_node,
        OUTPUT_NODE_NAME: output_node,
        
        # Router and path nodes
        "router": NodeConfig(
            node_id="router",
            node_name="simple_router",
            node_version="1.0.0",
            node_config={
                "threshold": 50.0,
                "choices": ["high_path", "low_path"],
                "allow_multiple": False
            },
            # Define dynamic input schema for router explicitly
            dynamic_input_schema=ConstructDynamicSchema(fields={
                "value": DynamicSchemaFieldConfig(type="float", required=True, description="Value to evaluate"),
                "description": DynamicSchemaFieldConfig(type="str", required=False, description="Description")
            })
        ),
        
        # High path nodes
        "high_path": NodeConfig(
            node_id="high_path",
            node_name="number_multiplier",
            node_version="1.0.0",
            node_config={
                "value": 3.0,
                "description": "High path multiplication"
            }
        ),
        
        "high_transform": NodeConfig(
            node_id="high_transform",
            node_name="data_transformer",
            node_version="1.0.0",
            node_config={}
        ),
        
        # Low path nodes
        "low_path": NodeConfig(
            node_id="low_path",
            node_name="text_generator",
            node_version="1.0.0",
            node_config={
                "text": "Low value detected",
                "metadata": {"path": "low"}
            }
        ),
        
        "low_transform": NodeConfig(
            node_id="low_transform",
            node_name="text_processor",
            node_version="1.0.0",
            node_config={}
        ),
        
        # Join node to combine paths
        "join": NodeConfig(
            node_id="join",
            node_name="join_data",
            node_version="1.0.0",
            node_config={},
            # Define dynamic input/output schemas for join node
            # dynamic_input_schema=ConstructDynamicSchema(fields={
            #     "text": DynamicSchemaFieldConfig(type="str", required=True, description="Text to join"),
            #     "metadata": DynamicSchemaFieldConfig(
            #         type="dict",
            #         keys_type="str",
            #         values_type="str",
            #         required=False,
            #         description="Metadata to join"
            #     )
            # }),
            # dynamic_output_schema=ConstructDynamicSchema(fields={
            #     "text": DynamicSchemaFieldConfig(type="str", required=True, description="Joined text"),
            #     "metadata": DynamicSchemaFieldConfig(
            #         type="dict",
            #         keys_type="str",
            #         values_type="str",
            #         required=False,
            #         description="Joined metadata"
            #     )
            # })
        ),
        
        # HITL review node
        "review": NodeConfig(
            node_id="review",
            node_name=f"{HITL_NODE_NAME_PREFIX}review",
            node_version="1.0.0",
            node_config={},
            # Define dynamic schemas for HITL node
            dynamic_input_schema=ConstructDynamicSchema(fields={
                "text": DynamicSchemaFieldConfig(type="str", required=True, description="Text to review"),
                "metadata": DynamicSchemaFieldConfig(
                    type="dict",
                    keys_type="str",
                    values_type="str",
                    required=False,
                    description="Metadata"
                )
            }),
            dynamic_output_schema=ConstructDynamicSchema(fields={
                "text": DynamicSchemaFieldConfig(type="str", required=True, description="Reviewed text"),
                "metadata": DynamicSchemaFieldConfig(
                    type="dict",
                    keys_type="str",
                    values_type="str",
                    required=False,
                    description="Updated metadata"
                )
            })
        )
    }
    
    # Create edges
    edges = [
        # Input to Router
        EdgeSchema(
            src_node_id=INPUT_NODE_NAME,
            dst_node_id="router",
            mappings=[
                EdgeMapping(src_field="value", dst_field="value"),
                EdgeMapping(src_field="description", dst_field="description")
            ]
        ),
        
        # Router to paths
        EdgeSchema(
            src_node_id="router",
            dst_node_id="high_path",
            mappings=[
                EdgeMapping(src_field="value", dst_field="value"),
                EdgeMapping(src_field="description", dst_field="description")
            ]
        ),
        EdgeSchema(
            src_node_id="router",
            dst_node_id="low_path",
            mappings=[]  # No mappings needed as text generator doesn't require input
        ),
        
        # Path processing
        EdgeSchema(
            src_node_id="high_path",
            dst_node_id="high_transform",
            mappings=[
                EdgeMapping(src_field="value", dst_field="value"),
                EdgeMapping(src_field="description", dst_field="description")
            ]
        ),
        EdgeSchema(
            src_node_id="low_path",
            dst_node_id="low_transform",
            mappings=[
                EdgeMapping(src_field="text", dst_field="text"),
                EdgeMapping(src_field="metadata", dst_field="metadata")
            ]
        ),
        
        # Transforms to Join
        EdgeSchema(
            src_node_id="high_transform",
            dst_node_id="join",
            mappings=[
                EdgeMapping(src_field="text", dst_field="text"),
                EdgeMapping(src_field="metadata", dst_field="metadata")
            ]
        ),
        EdgeSchema(
            src_node_id="low_transform",
            dst_node_id="join",
            mappings=[
                EdgeMapping(src_field="text", dst_field="text"),
                EdgeMapping(src_field="metadata", dst_field="metadata")
            ]
        ),
        
        # Join to Review
        EdgeSchema(
            src_node_id="join",
            dst_node_id="review",
            mappings=[
                EdgeMapping(src_field="text", dst_field="text"),
                EdgeMapping(src_field="metadata", dst_field="metadata")
            ]
        ),
        
        # Review to Output
        EdgeSchema(
            src_node_id="review",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="text", dst_field="result_text"),
                EdgeMapping(src_field="metadata", dst_field="result_metadata")
            ]
        )
    ]
    
    # Create and return graph schema
    return GraphSchema(
        nodes=nodes,
        edges=edges,
        input_node_id=INPUT_NODE_NAME,
        output_node_id=OUTPUT_NODE_NAME
    )

# ===============================
# Test Execution Functions
# ===============================

def setup_registry() -> DBRegistry:
    """
    Set up a MockRegistry with all test nodes registered.
    
    Returns:
        MockRegistry: The configured registry
    """
    registry = DBRegistry()
    
    # Register built-in dynamic nodes
    registry.register_node(InputNode)
    registry.register_node(OutputNode)
    registry.register_node(ReviewHITLNode)
    
    # Register test nodes
    registry.register_node(NumberGeneratorNode)
    registry.register_node(NumberMultiplierNode)
    registry.register_node(TextGeneratorNode)

    registry.register_node(TextProcessorNode)
    registry.register_node(SimpleRouterNode)

    registry.register_node(DataTransformNode)
    registry.register_node(JoinDataNode)
    
    return registry

def run_simple_number_graph() -> Dict[str, Any]:
    """
    Build and run the simple number graph.
    
    Returns:
        Dict[str, Any]: The output of the graph execution
    """
    # Setup registry and create graph schema
    registry = setup_registry()
    graph_schema = create_simple_number_graph()
    
    # Create graph builder
    builder = GraphBuilder(registry)
    
    # Build graph entities
    graph_entities = builder.build_graph_entities(graph_schema)
    
    # Create runtime adapter
    adapter = LangGraphRuntimeAdapter()

    runtime_config = graph_entities["runtime_config"]
    runtime_config["thread_id"] = 1
    runtime_config["use_checkpointing"] = True

    print("\n\n\n\n#### graph_entities", graph_entities["runtime_config"], "\n\n\n\n")

    # Build graph
    graph = adapter.build_graph(graph_entities)
    
    # Execute graph
    result = adapter.execute_graph(graph, input_data={}, config=runtime_config, output_node_id=graph_entities["output_node_id"])
    
    return result

def run_router_graph(input_value: float = 75.0) -> Dict[str, Any]:
    """
    Build and run the router graph.
    
    Args:
        input_value (float): The value to use for routing decision
        
    Returns:
        Dict[str, Any]: The output of the graph execution
    """
    # Setup registry and create graph schema
    registry = setup_registry()
    graph_schema = create_router_graph()
    
    # Modify the generator value based on input
    # graph_schema.nodes["generator"].node_config["value"] = input_value
    
    # Create graph builder
    builder = GraphBuilder(registry)
    
    # Build graph entities
    graph_entities = builder.build_graph_entities(graph_schema)
    
    # Create runtime adapter
    adapter = LangGraphRuntimeAdapter()
    
    runtime_config = graph_entities["runtime_config"]
    runtime_config["thread_id"] = 1
    runtime_config["use_checkpointing"] = True

    print("\n\n\n\n#### graph_entities", graph_entities["runtime_config"], "\n\n\n\n")

    # Build graph
    graph = adapter.build_graph(graph_entities)
    
    # Execute graph
    result = adapter.execute_graph(graph, input_data={"value": input_value}, config=runtime_config, output_node_id=graph_entities["output_node_id"])
    
    return result

def run_hitl_graph() -> Dict[str, Any]:
    """
    Build and run the HITL graph.
    
    Returns:
        Dict[str, Any]: The output of the graph execution
    """
    # Setup registry and create graph schema
    registry = setup_registry()
    graph_schema = create_hitl_graph()
    
    # Create graph builder
    builder = GraphBuilder(registry)
    
    # Build graph entities
    graph_entities = builder.build_graph_entities(graph_schema)
    
    # Create runtime adapter
    adapter = LangGraphRuntimeAdapter()

    runtime_config = graph_entities["runtime_config"]
    runtime_config["thread_id"] = 1
    runtime_config["use_checkpointing"] = True
    print("\n\n\n\n#### graph_entities", graph_entities["runtime_config"], "\n\n\n\n")
    # Build graph
    graph = adapter.build_graph(graph_entities)

    ################################################################################################################
    def get_value_from_human(
        interrupt_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get a value from a human.
        
        In a test environment, this function mocks human input by returning
        a predefined response based on the interrupt data schema.
        
        Args:
            interrupt_data: Dictionary containing the user prompt and schema
            
        Returns:
            Dict[str, Any]: Mocked human response that matches the expected schema
        """
        user_prompt = interrupt_data[HITL_USER_PROMPT_KEY]
        user_schema = interrupt_data[HITL_USER_SCHEMA_KEY]

        from langchain_core.load import dumpd, dumps, load, loads

        print("\n\n\n\n#### HANDLE INTERRUPT HITL: ##############################################################")
        print("\n\n#### HANDLE INTERRUPT HITL: user prompt for interrupt", dumps(user_prompt, pretty=True), "\n\n")
        print("\n\n#### HANDLE INTERRUPT HITL: user input required schema", dumps(user_schema, pretty=True), "\n\n")
        print("\n\n#### HANDLE INTERRUPT HITL: ##############################################################\n\n\n\n")
        if not isinstance(user_prompt, dict):
            user_prompt = user_prompt.model_dump()
        # Create a mock response based on the schema
        # This simulates what a human would input during the HITL process
        mock_response = {
            "metadata": {
                "approved": "True",
                "review_status": "approved",
                "review_notes": "Automatically approved in test environment",
            },
            "text": user_prompt.get("text", "") + " [REVIEWED BY TEST]"
        }
        
        # In a real environment, we would use:
        # response = input()
        # But for testing, we use the mock response
        return mock_response
    ################################################################################################################

    # Execute graph
    result = adapter.execute_graph(graph, input_data={"value": 100}, config=runtime_config, output_node_id=graph_entities["output_node_id"], interrupt_handler=get_value_from_human)
    
    return result

def run_complex_graph(input_value: float = 60.0) -> Dict[str, Any]:
    """
    Build and run the complex graph.
    
    Args:
        input_value (float): The initial value for the workflow
        
    Returns:
        Dict[str, Any]: The output of the graph execution
    """
    # Setup registry and create graph schema
    registry = setup_registry()
    
    # Register additional nodes needed for complex graph
    
    
    graph_schema = create_complex_graph()
    
    # Modify the generator value based on input
    # graph_schema.nodes["generator"].node_config["value"] = input_value
    
    # Create graph builder
    builder = GraphBuilder(registry)
    
    # Build graph entities
    graph_entities = builder.build_graph_entities(graph_schema)
    
    # Create runtime adapter
    adapter = LangGraphRuntimeAdapter()

    runtime_config = graph_entities["runtime_config"]
    runtime_config["thread_id"] = 1
    runtime_config["use_checkpointing"] = True
    
    # Build graph
    graph = adapter.build_graph(graph_entities)

    ################################################################################################################
    def get_value_from_human(
        interrupt_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get a value from a human.
        
        In a test environment, this function mocks human input by returning
        a predefined response based on the interrupt data schema.
        
        Args:
            interrupt_data: Dictionary containing the user prompt and schema
            
        Returns:
            Dict[str, Any]: Mocked human response that matches the expected schema
        """
        user_prompt = interrupt_data[HITL_USER_PROMPT_KEY]
        user_schema = interrupt_data[HITL_USER_SCHEMA_KEY]

        from langchain_core.load import dumpd, dumps, load, loads
        # Print debug information
        print("\n\n\n\n#### HANDLE INTERRUPT HITL: ##############################################################")
        print("\n\n#### HANDLE INTERRUPT HITL: user prompt for interrupt", dumps(user_prompt, pretty=True), "\n\n")
        print("\n\n#### HANDLE INTERRUPT HITL: user input required schema", dumps(user_schema, pretty=True), "\n\n")
        print("\n\n#### HANDLE INTERRUPT HITL: ##############################################################\n\n\n\n")
        if not isinstance(user_prompt, dict):
            user_prompt = user_prompt.model_dump()
        # if not isinstance(user_schema, dict):
        #     user_schema = user_schema.model_dump()
        # Create a mock response based on the schema
        # This simulates what a human would input during the HITL process
        mock_response = {
            "metadata": {
                "approved": "True",
                "review_status": "approved",
                "review_notes": "Automatically approved in test environment",
            },
            "text": user_prompt.get("text", "") + " [REVIEWED BY TEST]"
        }
        
        # In a real environment, we would use:
        # response = input()
        # But for testing, we use the mock response
        return mock_response
    ################################################################################################################
    
    # Execute graph
    result = adapter.execute_graph(graph, input_data={"value": input_value, "description": "test"}, config=runtime_config, output_node_id=graph_entities["output_node_id"], interrupt_handler=get_value_from_human)
    
    return result

# ===============================
# Main Test Function
# ===============================

def run_all_tests():
    # """Run all test graphs and print results."""
    print("Running Simple Number Graph...")
    simple_result = run_simple_number_graph()
    print(f"Result: {simple_result}\n")
    
    print("Running Router Graph with High Path (value=75)...")
    high_result = run_router_graph(75.0)
    print(f"Result: {high_result}\n")
    
    print("Running Router Graph with Low Path (value=25)...")
    low_result = run_router_graph(25.0)
    print(f"Result: {low_result}\n")
    
    print("Running HITL Review Graph...")
    hitl_result = run_hitl_graph()
    print(f"Result: {hitl_result}\n")
    
    print("Running Complex Graph with High Path (value=75)...")
    complex_high_result = run_complex_graph(75.0)
    print(f"Result: {complex_high_result}\n")
    
    print("Running Complex Graph with Low Path (value=25)...")
    complex_low_result = run_complex_graph(25.0)
    print(f"Result: {complex_low_result}\n")

if __name__ == "__main__":
    run_all_tests() 
