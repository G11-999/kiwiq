"""
Main module for the workflow service.

This module demonstrates how to use the workflow system to define and execute workflows.
"""
from typing import Any, Dict, List, Optional
import uuid
import json

from workflow_service.registry.registry import node_registry
from workflow_service.graph.graph import EdgeSchema, EdgeMapping, GraphSchema
from workflow_service.graph.builder import GraphBuilder
from workflow_service.graph.runtime.executor import WorkflowExecutor


def create_sample_workflow() -> Dict[str, Any]:
    """
    Create a sample workflow for demonstration purposes.
    
    This creates a simple workflow with the following structure:
    
    input_node → filter_node → openai_node → output_node
    
    Returns:
        Dict[str, Any]: The workflow schema as a dictionary.
    """
    # Create node configurations
    nodes = {
        "input": {
            "node_type": "input_node",
            "config": {}
        },
        "filter": {
            "node_type": "filter_node",
            "config": {
                "condition_groups": [
                    {
                        "conditions": [
                            {
                                "field": "text",
                                "operator": "is_not_empty",
                                "value": None
                            }
                        ],
                        "logical_operator": "and"
                    }
                ],
                "group_logical_operator": "and",
                "pass_through_if_empty": True
            }
        },
        "openai": {
            "node_type": "openai_node",
            "config": {
                "model_config": {
                    "provider": "openai",
                    "model_name": "gpt-4",
                    "temperature": 0.7,
                    "max_tokens": 500
                },
                "prompt_template": {
                    "template": "Generate a short reply to the following text: {text}",
                    "variables": {
                        "text": "The input text to respond to"
                    },
                    "system_message": "You are a helpful assistant."
                },
                "output_format": "text",
                "include_prompt_in_output": False
            }
        },
        "output": {
            "node_type": "output_node",
            "config": {}
        }
    }
    
    # Create edges
    edges = [
        {
            "source_node_id": "input",
            "target_node_id": "filter",
            "condition": None,
            "mappings": [
                {
                    "source_field": "text",
                    "target_field": "data.text",
                    "transform": None
                }
            ]
        },
        {
            "source_node_id": "filter",
            "target_node_id": "openai",
            "condition": None,
            "mappings": [
                {
                    "source_field": "filtered_data.text",
                    "target_field": "variables.text",
                    "transform": None
                }
            ]
        },
        {
            "source_node_id": "openai",
            "target_node_id": "output",
            "condition": None,
            "mappings": [
                {
                    "source_field": "output.content",
                    "target_field": "response",
                    "transform": None
                }
            ]
        }
    ]
    
    # Create graph schema
    graph_schema = {
        "nodes": nodes,
        "edges": edges,
        "input_node_id": "input",
        "output_node_id": "output",
        "metadata": {
            "name": "Sample Workflow",
            "description": "A simple workflow for demonstration purposes"
        }
    }
    
    return graph_schema


def run_sample_workflow(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run a sample workflow with the given input data.
    
    Args:
        input_data (Dict[str, Any]): Input data for the workflow.
        
    Returns:
        Dict[str, Any]: The output of the workflow.
    """
    # Create a graph builder with the node registry
    graph_builder = GraphBuilder(node_registry.get_registry_dict())
    
    # Create a workflow executor
    executor = WorkflowExecutor(graph_builder)
    
    # Create a sample workflow schema
    workflow_schema_dict = create_sample_workflow()
    
    # Parse the schema
    edge_list = []
    for edge_dict in workflow_schema_dict["edges"]:
        mappings = []
        for mapping in edge_dict["mappings"]:
            mappings.append(EdgeMapping(**mapping))
        
        edge = EdgeSchema(
            source_node_id=edge_dict["source_node_id"],
            target_node_id=edge_dict["target_node_id"],
            condition=edge_dict["condition"],
            mappings=mappings
        )
        edge_list.append(edge)
    
    graph_schema = GraphSchema(
        nodes=workflow_schema_dict["nodes"],
        edges=edge_list,
        input_node_id=workflow_schema_dict["input_node_id"],
        output_node_id=workflow_schema_dict["output_node_id"],
        metadata=workflow_schema_dict["metadata"]
    )
    
    # Execute the workflow
    result = executor.execute(
        graph_schema=graph_schema,
        input_data=input_data,
        workflow_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4())
    )
    
    return result


def main():
    """Main entry point for the workflow service demonstration."""
    print("Workflow Service Demonstration")
    print("=============================\n")
    
    # Sample input data
    input_data = {
        "text": "Hello, how are you today?"
    }
    
    print(f"Input data: {json.dumps(input_data, indent=2)}")
    print("\nExecuting workflow...\n")
    
    try:
        # Run the workflow
        result = run_sample_workflow(input_data)
        
        print("Workflow execution successful!")
        print(f"Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"Workflow execution failed: {str(e)}")


if __name__ == "__main__":
    main() 