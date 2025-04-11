"""
Tests for GraphBuilder functionality.

This module tests the GraphBuilder class which is responsible for constructing executable 
workflow graphs from graph schemas. It tests both individual builder functions and the 
end-to-end graph building process.
"""

from copy import deepcopy
import unittest
from typing import Dict, Type, List, Any, Optional, ClassVar
from typing import Annotated, get_origin, get_args
from pydantic import Field
from pydantic import TypeAdapter
    

from workflow_service.graph import graph
from workflow_service.graph.builder import GraphBuilder
from workflow_service.graph.graph import GraphSchema, EdgeSchema, NodeConfig, EdgeMapping
from workflow_service.graph.runtime.adapter import LangGraphRuntimeAdapter
from workflow_service.registry.nodes.core.base import BaseNode
from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import (
    DynamicSchema, BaseDynamicNode, InputNode, OutputNode, ConstructDynamicSchema, DynamicSchemaFieldConfig
)
from workflow_service.config.constants import INPUT_NODE_NAME, OUTPUT_NODE_NAME, GRAPH_STATE_SPECIAL_NODE_NAME
from workflow_service.registry.registry import DBRegistry
from workflow_service.utils.utils import get_central_state_field_key, get_node_output_state_key


# Test schemas for graph builder tests
class SimpleInputSchema(DynamicSchema):
    """Simple input schema for test nodes."""
    value: str = Field(description="Input value")


class SimpleOutputSchema(DynamicSchema):
    """Simple output schema for test nodes."""
    result: str = Field(description="Output result")


class SimpleConfigSchema(DynamicSchema):
    """Simple configuration schema for test nodes."""
    multiplier: int = Field(default=1, description="Value multiplier")


class TestNode(BaseDynamicNode):  # [SimpleInputSchema, SimpleOutputSchema, SimpleConfigSchema]):
    """Test node for graph builder tests."""
    # Class variables for node metadata
    node_name: ClassVar[str] = "test_node"
    node_version: ClassVar[str] = "1.0.0"
    
    # Schema class references as class variables
    input_schema_cls: ClassVar[Type[SimpleInputSchema]] = SimpleInputSchema
    output_schema_cls: ClassVar[Type[SimpleOutputSchema]] = SimpleOutputSchema
    config_schema_cls: ClassVar[Type[SimpleConfigSchema]] = SimpleConfigSchema

    # instance
    config: SimpleConfigSchema
    
    def process(self, input_data: SimpleInputSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> SimpleOutputSchema:
        """Process input data and return output."""
        multiplier = self.config.multiplier if self.config else config.get("multiplier", 1)
        input_fields = input_data.model_dump()
        return self.output_schema_cls(result=input_fields["value"] * multiplier, **input_fields)


class AnotherTestNode(BaseDynamicNode):  # [SimpleOutputSchema, SimpleOutputSchema, None]):
    """Another test node for graph builder tests."""
    # Class variables for node metadata
    node_name: ClassVar[str] = "another_test_node"
    node_version: ClassVar[str] = "1.0.0"
    
    # Schema class references as class variables
    input_schema_cls: ClassVar[Type[SimpleOutputSchema]] = SimpleOutputSchema
    output_schema_cls: ClassVar[Type[SimpleOutputSchema]] = SimpleOutputSchema
    config_schema_cls: ClassVar[Type[None]] = None
    
    def process(self, input_data: SimpleOutputSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> SimpleOutputSchema:
        """Process input data and return output."""
        return self.output_schema_cls(result=input_data.result + "_processed")


def setup_registry() -> DBRegistry:
    """Set up a mock registry with test nodes for testing."""
    registry = DBRegistry()
    
    # Register test nodes
    registry.register_node(TestNode)
    registry.register_node(AnotherTestNode)
    registry.register_node(InputNode)
    registry.register_node(OutputNode)
    
    return registry


class TestGraphBuilder(unittest.TestCase):
    """Tests for the GraphBuilder class."""
    
    def setUp(self):
        """Set up test environment."""
        # Set up mock registry with test nodes
        self.registry = setup_registry()
        
        # Create GraphBuilder instance with the registry
        self.builder = GraphBuilder(self.registry)
        
        # Create simple test graph schema
        self.simple_graph_schema = GraphSchema(
            nodes={
                INPUT_NODE_NAME: NodeConfig(
                    node_id=INPUT_NODE_NAME,
                    node_name=INPUT_NODE_NAME,
                    node_version="0.1.0"
                ),
                "test1": NodeConfig(
                    node_id="test1",
                    node_name="test_node",
                    node_version="1.0.0",
                    node_config={"multiplier": 2},
                    enable_dynamic_fields_from_edges=False
                ),
                "test2": NodeConfig(
                    node_id="test2",
                    node_name="another_test_node",
                    node_version="1.0.0",
                    enable_dynamic_fields_from_edges=False
                ),
                OUTPUT_NODE_NAME: NodeConfig(
                    node_id=OUTPUT_NODE_NAME,
                    node_name=OUTPUT_NODE_NAME,
                    node_version="0.1.0"
                )
            },
            edges=[
                EdgeSchema(
                    src_node_id=INPUT_NODE_NAME,
                    dst_node_id="test1",
                    mappings=[
                        EdgeMapping(src_field="value", dst_field="value")
                    ]
                ),
                EdgeSchema(
                    src_node_id="test1",
                    dst_node_id="test2",
                    mappings=[
                        EdgeMapping(src_field="result", dst_field="result")
                    ]
                ),
                EdgeSchema(
                    src_node_id="test2",
                    dst_node_id=OUTPUT_NODE_NAME,
                    mappings=[
                        EdgeMapping(src_field="result", dst_field="result")
                    ]
                )
            ],
            input_node_id=INPUT_NODE_NAME,
            output_node_id=OUTPUT_NODE_NAME
        )

    def test_build_nodes_from_schema_mappings(self):
        """Test building node instances from schema mappings."""
        # Test the actual implementation without mocking
        print("\n\n\n\n ### simple_graph_schema \n\n", self.simple_graph_schema.model_dump_json(indent=4), "\n\n\n\n")
        node_instances = self.builder.build_nodes_from_schema_mappings(self.simple_graph_schema)
        print("\n\n\n\n", node_instances, "\n\n\n\n")
        central_state_fields = self.builder.build_central_state_schema(self.simple_graph_schema, node_instances)
        dynamic_nodes = self.builder.build_dynamic_nodes_from_schema_mappings(self.simple_graph_schema, central_state_fields)

        node_instances = {k:v for k,v in dynamic_nodes.items() if k not in [INPUT_NODE_NAME, OUTPUT_NODE_NAME]}
        dynamic_nodes = {k:v for k,v in dynamic_nodes.items() if k in [INPUT_NODE_NAME, OUTPUT_NODE_NAME]}
        
        # Verify correct number of nodes were created
        self.assertEqual(len(node_instances), 2)  # input and output nodes are created from dynamic nodes creation!
        self.assertEqual(len(dynamic_nodes), 2)  # dynamic nodes -> input / output nodes are created from dynamic nodes creation!
        
        # Verify all expected node IDs are present
        self.assertIn(INPUT_NODE_NAME, dynamic_nodes)
        self.assertIn("test1", node_instances)
        self.assertIn("test2", node_instances)
        self.assertIn(OUTPUT_NODE_NAME, dynamic_nodes)
        
        # Verify node types are correct
        self.assertIsInstance(dynamic_nodes[INPUT_NODE_NAME], InputNode)
        self.assertIsInstance(node_instances["test1"], TestNode)
        self.assertIsInstance(node_instances["test2"], AnotherTestNode)
        self.assertIsInstance(dynamic_nodes[OUTPUT_NODE_NAME], OutputNode)
        
        # Verify node configuration was properly applied
        self.assertEqual(node_instances["test1"].config.multiplier, 2)
        
        # Verify node IDs were properly assigned
        self.assertEqual(dynamic_nodes[INPUT_NODE_NAME].node_id, INPUT_NODE_NAME)
        self.assertEqual(node_instances["test1"].node_id, "test1")
        self.assertEqual(node_instances["test2"].node_id, "test2")
        self.assertEqual(dynamic_nodes[OUTPUT_NODE_NAME].node_id, OUTPUT_NODE_NAME)

    def test_build_central_state_schema(self):
        """Test building the central state schema."""
        # Create nodes for testing
        nodes = self.builder.build_nodes_from_schema_mappings(self.simple_graph_schema)

        # dynamic_nodes = self.build_dynamic_nodes_from_schema_mappings(graph_schema, central_state_fields)
        
        # Test with a simple graph (no central state connections)
        central_state_fields = self.builder.build_central_state_schema(self.simple_graph_schema, nodes)
        
        # Check central state central_state_fields
        self.assertIsInstance(central_state_fields, dict)
        
        # This is a simple graph with no central state connections, so it should be empty
        self.assertEqual(len(central_state_fields), 0)
        
        # Create a graph with central state connections
        graph_with_central_state = GraphSchema(
            nodes=self.simple_graph_schema.nodes,
            edges=[
                # Add an edge to the central state
                EdgeSchema(
                    src_node_id="test1",
                    dst_node_id=GRAPH_STATE_SPECIAL_NODE_NAME,
                    mappings=[
                        EdgeMapping(src_field="result", dst_field="stored_result")
                    ]
                ),
                # Add other edges
                *self.simple_graph_schema.edges
            ],
            input_node_id=INPUT_NODE_NAME,
            output_node_id=OUTPUT_NODE_NAME
        )
        
        # central_state_with_fields = self.builder.build_central_state_schema(
        #     graph_with_central_state, nodes
        # )

        # Build dynamic nodes and updates central state with state from edges from dynamic nodes!
        print("\n\n\n\n ### central_state_fields \n\n", central_state_fields, "\n\n\n\n")
        dynamic_nodes = self.builder.build_dynamic_nodes_from_schema_mappings(graph_with_central_state, central_state_fields)
        print("\n\n\n\n ### central_state_fields \n\n", central_state_fields, "\n\n\n\n")
        
        # Check that the central state now contains the mapped field
        stored_result_key = get_central_state_field_key("stored_result")
        self.assertIn(stored_result_key, central_state_fields)
        
        # Verify the field type is correct (should match the source field type)
        # Verify the field type is correct (should match the source field type)
        

        # type_adapter = TypeAdapter(central_state_with_fields[stored_result_key][0])
        
        # Check that the type stored in central_state_with_fields matches str
        # core_type_class = BaseSchema._validate_type(central_state_with_fields[stored_result_key][0])
        # print(central_state_with_fields[stored_result_key][0])
        # print(get_origin(central_state_with_fields[stored_result_key][0]))
        # print(get_args(central_state_with_fields[stored_result_key][0])[0])
        # print(core_type_class.core_type_annotation, core_type_class.core_type_class)
        self.assertEqual(get_args(central_state_fields[stored_result_key][0])[0], str)
        
        # Additionally verify using TypeAdapter that the field can be properly validated as a string
        
        # self.assertEqual(type_adapter.validate_python("test_string"), "test_string")
        # with self.assertRaises(ValueError):
        #     type_adapter.validate_python(123)  # Should fail for non-string values

    def test_build_runtime_config(self):
        """Test building runtime configuration."""
        # Create nodes for testing
        nodes = self.builder.build_nodes_from_schema_mappings(self.simple_graph_schema)
        
        # Call the method
        runtime_config = self.builder.build_runtime_config(self.simple_graph_schema, nodes)
        
        # Check runtime config structure
        self.assertIsInstance(runtime_config, dict)
        self.assertIn("inputs", runtime_config)
        self.assertIn("outputs", runtime_config)
        
        # Verify the input mappings for nodes
        inputs = runtime_config["inputs"]
        self.assertIn("test1", inputs)
        self.assertIn("test2", inputs)
        self.assertIn(OUTPUT_NODE_NAME, inputs)
        
        # Verify specific mappings
        self.assertEqual(inputs["test1"]["value"], [[INPUT_NODE_NAME, "value"]])
        self.assertEqual(inputs["test2"]["result"], [["test1", "result"]])
        self.assertEqual(inputs[OUTPUT_NODE_NAME]["result"], [["test2", "result"]])

    def test_build_graph_state(self):
        """Test building the graph state TypedDict."""
        # Create nodes for testing
        simple_graph_schema_copy = GraphSchema(**deepcopy(self.simple_graph_schema.model_dump()))
        
        edge_to_central_state = EdgeSchema(
            src_node_id="test2",
            dst_node_id=GRAPH_STATE_SPECIAL_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="result", dst_field="stored_result")
            ]
        )
        
        simple_graph_schema_copy.edges.append(edge_to_central_state)
        
        nodes = self.builder.build_nodes_from_schema_mappings(simple_graph_schema_copy)
        # Add dynamic nodes
        central_state_fields = self.builder.build_central_state_schema(simple_graph_schema_copy, nodes)
        dynamic_nodes = self.builder.build_dynamic_nodes_from_schema_mappings(
            simple_graph_schema_copy, central_state_fields
        )
        input_schema = dynamic_nodes[simple_graph_schema_copy.input_node_id].input_schema_cls
        central_state = GraphBuilder.build_central_state_typeddict(input_schema, central_state_fields)
        
        # Combine all nodes
        all_nodes = {**nodes, **dynamic_nodes}
        
        # Call the method
        graph_state_type = self.builder.build_graph_state(all_nodes, central_state)
        
        # Check graph state type
        self.assertTrue(hasattr(graph_state_type, "__annotations__"))
        
        # The graph state should contain all nodes plus the central state
        print("\n\n\n\n ### graph_state_type.__annotations__ \n\n", graph_state_type.__annotations__, "\n\n\n\n")
        # NOTE: 
        self.assertEqual(len(graph_state_type.__annotations__), 7)  # 4 nodes + 1 central state + 1 input field (dynamically inferred!) + 1 node order field central state
        
        # Verify expected keys in annotations
        for node_id in [INPUT_NODE_NAME, "test1", "test2", OUTPUT_NODE_NAME,]:
            self.assertIn(get_node_output_state_key(node_id), graph_state_type.__annotations__)
        self.assertIn(get_central_state_field_key("stored_result"), graph_state_type.__annotations__)

        # Check inputs added to central state!
        for field in dynamic_nodes[simple_graph_schema_copy.input_node_id].input_schema_cls.__annotations__.keys():
            self.assertIn(get_central_state_field_key(field), graph_state_type.__annotations__)

    def test_build_graph_entities(self):
        """Test building all graph entities in one go."""
        # Call the method
        graph_entities = self.builder.build_graph_entities(self.simple_graph_schema)
        
        # Check that all expected entities are present
        self.assertIn("node_instances", graph_entities)
        self.assertIn("central_state", graph_entities)
        self.assertIn("graph_state", graph_entities)
        self.assertIn("runtime_config", graph_entities)
        self.assertIn("edges", graph_entities)
        self.assertIn("input_node_id", graph_entities)
        self.assertIn("output_node_id", graph_entities)
        
        # Check node instances
        node_instances = graph_entities["node_instances"]
        self.assertEqual(len(node_instances), 4)  # 2 regular + 2 dynamic nodes
        
        # Verify all expected node IDs are present
        self.assertIn(INPUT_NODE_NAME, node_instances)
        self.assertIn("test1", node_instances)
        self.assertIn("test2", node_instances)
        self.assertIn(OUTPUT_NODE_NAME, node_instances)
        
        # Verify node types
        self.assertIsInstance(node_instances[INPUT_NODE_NAME], InputNode)
        self.assertIsInstance(node_instances["test1"], TestNode)
        self.assertIsInstance(node_instances["test2"], AnotherTestNode)
        self.assertIsInstance(node_instances[OUTPUT_NODE_NAME], OutputNode)
        
        # Check edges
        edges = graph_entities["edges"]
        self.assertEqual(len(edges), 3)
        
        # Check runtime config
        runtime_config = graph_entities["runtime_config"]
        self.assertIn("inputs", runtime_config)
        self.assertIn("outputs", runtime_config)
        
        # Check input and output node IDs
        self.assertEqual(graph_entities["input_node_id"], INPUT_NODE_NAME)
        self.assertEqual(graph_entities["output_node_id"], OUTPUT_NODE_NAME)

    # def test_build_graph(self):
    #     """Test the full graph building process."""
    #     # Call build_graph
    #     graph_entities = self.builder.build_graph_entities(self.simple_graph_schema)
    #     #     self.simple_graph_schema, 
    #     #     workflow_id="test_workflow",
    #     #     run_id="test_run"
    #     # )
        
    #     # Verify the graph was created
    #     self.assertIsNotNone(graph_entities)
    #     self.assertIsNotNone(state_manager)
        
        # # Test the graph by running a simple workflow
        # input_data = {"value": "test"}
        
        # # Execute the graph
        # result = graph.invoke(input_data)
        
        # # Verify the result matches the expected output
        # # Input "test" * multiplier 2 = "testtest", then processed = "testtest_processed"
        # self.assertEqual(result["result"], "testtest_processed")

    def test_dynamic_schema_handling(self):
        """Test handling of dynamic schemas in graph building."""
        # Create a graph schema with dynamic node configurations
        dynamic_graph_schema = GraphSchema(
            nodes={
                INPUT_NODE_NAME: NodeConfig(
                    node_id=INPUT_NODE_NAME,
                    node_name=INPUT_NODE_NAME,
                    node_version="0.1.0",
                    dynamic_output_schema=ConstructDynamicSchema(fields={
                        "dynamic_value": DynamicSchemaFieldConfig(type="str", required=True)
                    })
                ),
                "test1": NodeConfig(
                    node_id="test1",
                    node_name="test_node",
                    node_version="1.0.0",
                    node_config={"multiplier": 2},
                    dynamic_input_schema=ConstructDynamicSchema(fields={
                        "dynamic_value": DynamicSchemaFieldConfig(type="str", required=True)
                    }),
                    dynamic_output_schema=ConstructDynamicSchema(fields={
                        "dynamic_value": DynamicSchemaFieldConfig(type="str", required=True)
                    }),
                    # enable_dynamic_fields_from_edges=False
                ),
                OUTPUT_NODE_NAME: NodeConfig(
                    node_id=OUTPUT_NODE_NAME,
                    node_name=OUTPUT_NODE_NAME,
                    node_version="0.1.0",
                    dynamic_input_schema=ConstructDynamicSchema(fields={
                        "dynamic_value": DynamicSchemaFieldConfig(type="str", required=True)
                    })
                )
            },
            edges=[
                EdgeSchema(
                    src_node_id=INPUT_NODE_NAME,
                    dst_node_id="test1",
                    mappings=[
                        EdgeMapping(src_field="dynamic_value", dst_field="dynamic_value")
                    ]
                ),
                EdgeSchema(
                    src_node_id="test1",
                    dst_node_id=OUTPUT_NODE_NAME,
                    mappings=[
                        EdgeMapping(src_field="dynamic_value", dst_field="dynamic_value"),
                        EdgeMapping(src_field="result", dst_field="result"),
                    ]
                )
            ],
            input_node_id=INPUT_NODE_NAME,
            output_node_id=OUTPUT_NODE_NAME
        )
        
        # Build the graph entities
        with self.assertRaises(ValueError) as context:
            # The above config doesn't provide mapping to required input `value` in test1 node!
            graph_entities = self.builder.build_graph_entities(dynamic_graph_schema)
        
        # add mapping to required field to make graph schema valid!
        dynamic_graph_schema.edges.append(
            EdgeSchema(
                    src_node_id=INPUT_NODE_NAME,
                    dst_node_id="test1",
                    mappings=[
                        EdgeMapping(src_field="value", dst_field="value")
                    ]
                )
        )

        graph_entities = self.builder.build_graph_entities(dynamic_graph_schema)
        
        # Check that dynamic nodes were created
        node_instances = graph_entities["node_instances"]
        self.assertIn(INPUT_NODE_NAME, node_instances)
        self.assertIn("test1", node_instances)
        self.assertIn(OUTPUT_NODE_NAME, node_instances)
        
        # Verify the dynamic schemas were properly configured
        input_node = node_instances[INPUT_NODE_NAME]
        self.assertIsInstance(input_node, InputNode)
        self.assertIsInstance(input_node.output_schema_cls(**{"dynamic_value": "test", "value": "test"}), DynamicSchema)
        self.assertIn("dynamic_value", input_node.output_schema_cls.model_fields)
        
        test_node = node_instances["test1"]
        self.assertIsInstance(test_node, TestNode)
        self.assertIsInstance(test_node.input_schema_cls(**{"dynamic_value": "test", "value": "test"}), DynamicSchema)
        self.assertIn("dynamic_value", test_node.input_schema_cls.model_fields)
        
        output_node = node_instances[OUTPUT_NODE_NAME]
        self.assertIsInstance(output_node, OutputNode)
        self.assertIsInstance(output_node.input_schema_cls(**{"dynamic_value": "test", "result": "test"}), DynamicSchema)
        self.assertIn("dynamic_value", output_node.input_schema_cls.model_fields)
        
        # Build and test the graph
        graph_entities = self.builder.build_graph_entities(
            dynamic_graph_schema,
        )
        
        # Test the graph with dynamic schemas
        input_data = {"dynamic_value": "dynamic_test", "value": "dynamic_test"}

        runtime_config = graph_entities["runtime_config"]
        runtime_config["thread_id"] = 1
        runtime_config["use_checkpointing"] = True

        adapter = LangGraphRuntimeAdapter()
        graph = adapter.build_graph(graph_entities)

        result = adapter.execute_graph(graph, input_data=input_data, config=runtime_config, output_node_id=graph_entities["output_node_id"])
        
        # Verify the result matches the expected output
        self.assertIn("dynamic_value", result)
        # Input "dynamic_test" * multiplier 2 = "dynamic_testdynamic_test"
        # The TestNode's process method is called with the dynamic input
        self.assertEqual(result["result"], "dynamic_testdynamic_test")

    def test_error_handling(self):
        """Test error handling in graph building."""
        # Create an invalid graph schema with a missing node reference
        with self.assertRaises(Exception) as context:
            invalid_graph_schema = GraphSchema(
                nodes={
                    INPUT_NODE_NAME: NodeConfig(
                        node_id=INPUT_NODE_NAME,
                        node_name=INPUT_NODE_NAME,
                        node_version="0.1.0"
                    ),
                    "test2": NodeConfig(
                        node_id="test2",
                        node_name="another_test_node",
                        node_version="1.0.0"
                    ),
                    OUTPUT_NODE_NAME: NodeConfig(
                        node_id=OUTPUT_NODE_NAME,
                        node_name=OUTPUT_NODE_NAME,
                        node_version="0.1.0"
                    )
                },
                edges=[
                    EdgeSchema(
                        src_node_id=INPUT_NODE_NAME,
                        dst_node_id="missing_node",  # This node doesn't exist
                        mappings=[
                            EdgeMapping(src_field="value", dst_field="value")
                        ]
                    ),
                    EdgeSchema(
                        src_node_id="test2",
                        dst_node_id=OUTPUT_NODE_NAME,
                        mappings=[
                            EdgeMapping(src_field="result", dst_field="result")
                        ]
                    )
                ],
                input_node_id=INPUT_NODE_NAME,
                output_node_id=OUTPUT_NODE_NAME
            )
        
        # Attempt to build nodes should raise error
        # with self.assertRaises(Exception) as context:
        #     self.builder.build_nodes_from_schema_mappings(invalid_graph_schema)
        
        # # Verify the error message mentions the missing node
        # self.assertIn("missing_node", str(context.exception))
        
        # Test with unknown node type
        unknown_node_graph = GraphSchema(
            nodes={
                INPUT_NODE_NAME: NodeConfig(
                    node_id=INPUT_NODE_NAME,
                    node_name=INPUT_NODE_NAME,
                    node_version="0.1.0"
                ),
                "unknown": NodeConfig(
                    node_id="unknown",
                    node_name="unknown_node_type",  # This node type doesn't exist
                    node_version="1.0.0"
                ),
                OUTPUT_NODE_NAME: NodeConfig(
                    node_id=OUTPUT_NODE_NAME,
                    node_name=OUTPUT_NODE_NAME,
                    node_version="0.1.0"
                )
            },
            edges=[
                EdgeSchema(
                    src_node_id=INPUT_NODE_NAME,
                    dst_node_id="unknown",
                    mappings=[]
                ),
                EdgeSchema(
                    src_node_id="unknown",
                    dst_node_id=OUTPUT_NODE_NAME,
                    mappings=[]
                )
            ],
            input_node_id=INPUT_NODE_NAME,
            output_node_id=OUTPUT_NODE_NAME
        )
        
        # Attempt to build nodes should raise error
        with self.assertRaises(Exception) as context:
            self.builder.build_nodes_from_schema_mappings(unknown_node_graph)
        
        # Verify the error message mentions the unknown node type
        self.assertIn("unknown_node_type", str(context.exception))


if __name__ == "__main__":
    unittest.main()
