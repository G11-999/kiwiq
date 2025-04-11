from typing import Dict, Any
import unittest

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
from workflow_service.registry.nodes.llm.prompt import PromptConstructorNode, PROMPT_CONSTRUCTOR_DELIMITER

from workflow_service.graph.builder import GraphBuilder
from workflow_service.graph.runtime.adapter import LangGraphRuntimeAdapter
from workflow_service.registry.registry import DBRegistry
from workflow_service.registry.nodes.core.dynamic_nodes import InputNode, OutputNode


def create_prompt_constructor_graph():
    """
    Create a workflow graph with a prompt constructor node.
    
    This function configures a graph with nodes for input, prompt construction,
    and output of all constructed templates.
    
    Returns:
        GraphSchema: The configured graph schema with all nodes and edges
    """

    
    

    
    # Input node with dynamic schema to accept all prompt variables
    input_node = NodeConfig(
        node_id=INPUT_NODE_NAME,
        node_name=INPUT_NODE_NAME,
        node_config={},
        # dynamic_output_schema=ConstructDynamicSchema(fields={
        #     # This will be populated dynamically based on the prompt templates
        #     # Each field will be a prompt variable
        # })
    )
    
    # Prompt Constructor node
    prompt_constructor_node = NodeConfig(
        node_id="prompt_constructor",
        node_name="prompt_constructor",  # This should match the registered node name
        node_config={
            # Configuration for the prompt constructor node
            # This would include the prompt templates
            "prompt_templates": {
                "template1": {
                    "id": "template1",
                    "template": "This is a template with {variable1} and {variable2} and {variable3}",
                    "variables": {
                        "variable1": "DEFAULT_VALUE_1",
                        "variable2": "USER_OVERRIDE_VALUE_2",
                        "variable3": None
                    }
                },
                "template2": {
                    "id": "template2",
                    "template": "Another template with {variable1}",
                    "variables": {
                        "variable1": None
                    }
                }
            }
        },
        # Dynamic input schema to accept all prompt variables
        dynamic_input_schema=ConstructDynamicSchema(fields={
            f"template1{PROMPT_CONSTRUCTOR_DELIMITER}variable3": DynamicSchemaFieldConfig(type="str", required=True, description="Constructed template 1"),
            f"variable1": DynamicSchemaFieldConfig(type="str", required=True, description="Constructed template 2")
        }),
        # Dynamic output schema to output all constructed templates
        dynamic_output_schema=ConstructDynamicSchema(fields={
            # Will be populated with template IDs as field names
            f"template1": DynamicSchemaFieldConfig(type="str", required=True, description="Constructed template 1"),
            f"template2": DynamicSchemaFieldConfig(type="str", required=True, description="Constructed template 2")
        })
    )
    
    # Output node to output all constructed templates
    output_node = NodeConfig(
        node_id=OUTPUT_NODE_NAME,
        node_name=OUTPUT_NODE_NAME,
        node_config={},
        # dynamic_input_schema=ConstructDynamicSchema(fields={
        #     # Will match the output schema of the prompt constructor
        #     "template1": DynamicSchemaFieldConfig(type="str", required=True, description="Constructed template 1"),
        #     "template2": DynamicSchemaFieldConfig(type="str", required=True, description="Constructed template 2")
        # })
    )
    
    # Define edges between nodes
    edges = [
        EdgeSchema(
            src_node_id=INPUT_NODE_NAME,
            dst_node_id="prompt_constructor",
            mappings=[
                EdgeMapping(src_field="t1_variable3", dst_field=f"template1{PROMPT_CONSTRUCTOR_DELIMITER}variable3"),
                EdgeMapping(src_field="write_variable1", dst_field="variable1")
            ]
        ),
        EdgeSchema(
            src_node_id="prompt_constructor",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="template1", dst_field="system_prompt"),
                EdgeMapping(src_field="template2", dst_field="user_prompt")
            ]
        )
    ]
    
    # Create and return the graph schema
    return GraphSchema(
        nodes={
            INPUT_NODE_NAME: input_node,
            "prompt_constructor": prompt_constructor_node,
            OUTPUT_NODE_NAME: output_node
        },
        edges=edges,
        input_node_id=INPUT_NODE_NAME,
        output_node_id=OUTPUT_NODE_NAME,
    )


def build_and_run_prompt_constructor_graph(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build and run the prompt constructor graph.
    
    Args:
        input_data: Dictionary containing prompt variables
        
    Returns:
        Dict[str, Any]: The output of the graph execution containing constructed prompts
    """

    registry = DBRegistry()
    registry.register_node(PromptConstructorNode)
    registry.register_node(InputNode)
    registry.register_node(OutputNode)
    
    
    # Create graph schema
    graph_schema = create_prompt_constructor_graph()
    
    # Setup registry with prompt constructor node
    
    # Assuming the prompt constructor node is already registered
    
    # Create graph builder
    builder = GraphBuilder(registry)
    
    # Build graph entities
    graph_entities = builder.build_graph_entities(graph_schema)
    
    # Configure runtime
    runtime_config = graph_entities["runtime_config"]
    runtime_config["thread_id"] = "prompt_constructor_test"
    runtime_config["use_checkpointing"] = True
    
    # Create runtime adapter
    adapter = LangGraphRuntimeAdapter()
    
    # Build graph
    graph = adapter.build_graph(graph_entities)
    
    # Execute graph
    result = adapter.execute_graph(
        graph=graph,
        input_data=input_data,
        config=runtime_config,
        output_node_id=graph_entities["output_node_id"]
    )
    
    return result


class TestPromptConstructorNode(unittest.TestCase):
    def test_prompt_constructor_node(self):
        input_data = {
            "t1_variable3": "`3x Hello, world!`",
            "write_variable1": "`1x Hello, world!`"
        }
        result = build_and_run_prompt_constructor_graph(input_data)
        assert result == {
        'system_prompt': 'This is a template with `1x Hello, world!` and USER_OVERRIDE_VALUE_2 and `3x Hello, world!`', 
        'user_prompt': 'Another template with `1x Hello, world!`'
    }

if __name__ == "__main__":
    unittest.main()
