import unittest
import asyncio
import copy
from typing import Dict, Any, List, Optional

from pydantic import ValidationError as PydanticValidationError

from workflow_service.graph.graph import GraphSchema, NodeConfig, EdgeSchema, EdgeMapping
from workflow_service.registry.registry import DBRegistry
from workflow_service.config.constants import INPUT_NODE_NAME, OUTPUT_NODE_NAME

from kiwi_app.workflow_app.workflow_config_override import (
    GraphOverridePayload,
    NodeOverrideCriteria,
    apply_graph_override
)
from kiwi_app.workflow_app.dependencies import get_node_template_registry

# Import example graph schemas (dictionaries)
from kiwi_client.workflows.wf_content_strategy import workflow_graph_schema as content_strategy_schema_dict
from kiwi_client.workflows.wf_content_generation import workflow_graph_schema as content_generation_schema_dict
from kiwi_client.workflows.wf_linkedin_content_analysis import workflow_graph_schema as linkedin_analysis_schema_dict


class TestGraphConfigOverrides(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for the graph configuration override functionality.
    """
    # db_registry: Optional[DBRegistry] = None # Will be instance variable
    # base_content_strategy_schema: Optional[GraphSchema] = None
    # base_content_generation_schema: Optional[GraphSchema] = None
    # base_linkedin_analysis_schema: Optional[GraphSchema] = None

    # @classmethod
    # async def asyncSetUpClass(cls):
    #     """
    #     Set up the DBRegistry and load base graph schemas once for all tests.
    #     This is an Pydantic V2 adaptation of a class-level async setup.
    #     Actual test methods in unittest.IsolatedAsyncioTestCase run in separate event loops.
    #     For shared async resources like db_registry initialized once, this is a common pattern.
    #     """
    #     # This logic will be moved to asyncSetUp for IsolatedAsyncioTestCase
    #     pass

    async def asyncSetUp(self):
        """
        Set up DBRegistry and parse base graph schemas before each test method.
        This ensures fresh resources for each test's event loop.
        """
        self.db_registry = await get_node_template_registry()
        
        # Load and parse schemas here to ensure they are fresh for each test if needed,
        # or load them once if they are not modified by tests (which deepcopy helps with).
        # For safety and to match IsolatedAsyncioTestCase's intent, load them here.
        self.base_content_strategy_schema = GraphSchema.model_validate(copy.deepcopy(content_strategy_schema_dict))
        self.base_content_generation_schema = GraphSchema.model_validate(copy.deepcopy(content_generation_schema_dict))
        self.base_linkedin_analysis_schema = GraphSchema.model_validate(copy.deepcopy(linkedin_analysis_schema_dict))


    async def test_basic_node_config_override_by_id(self):
        """Test overriding a node's config by its specific node_id."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        target_node_id = "generate_content" # LLM node in content strategy
        original_temp = base_schema.nodes[target_node_id].node_config["llm_config"]["temperature"]

        override_payload = {
            "node_configs": [
                {
                    "node_id": target_node_id,
                    "node_name": "llm", # Verification
                    "node_config": {
                        "llm_config": {
                            "temperature": 0.5 # New temperature
                        }
                    }
                }
            ]
        }

        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry)
        
        self.assertNotEqual(
            updated_schema.nodes[target_node_id].node_config["llm_config"]["temperature"],
            original_temp
        )
        self.assertEqual(
            updated_schema.nodes[target_node_id].node_config["llm_config"]["temperature"],
            0.5
        )
        # Ensure original schema is unchanged
        self.assertEqual(base_schema.nodes[target_node_id].node_config["llm_config"]["temperature"], original_temp)


    async def test_node_config_override_by_name_single_match(self):
        """Test overriding a node's config by node_name when it's unique."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        target_node_name = "store_customer_data" # This node name is unique in content strategy
        target_node_id = "store_customer_data" # The ID for this unique node name

        original_operation = base_schema.nodes[target_node_id].node_config["global_versioning"]["operation"]

        override_payload = {
            "node_configs": [
                {
                    "node_name": target_node_name,
                    "node_config": {
                        "global_versioning": {
                            "operation": "new_operation"
                        }
                    }
                }
            ]
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry)
        self.assertEqual(
            updated_schema.nodes[target_node_id].node_config["global_versioning"]["operation"],
            "new_operation"
        )
        self.assertNotEqual(original_operation, "new_operation")

    async def test_node_config_override_by_name_and_version(self):
        """Test overriding node config by node_name and a specific node_version."""
        # For this, we'd ideally need a graph with multiple versions of the same node_name
        # Let's use content_generation, assuming 'llm' node has a version.
        # If not, this test might be trivial or need adjustment.
        # The current NodeConfig in graph.py has node_version: Optional[str] = None
        # And node templates are registered with versions.
        
        base_schema = copy.deepcopy(self.base_content_generation_schema)
        target_node_name = "llm"
        
        # Find an LLM node and its version. If it's None, this test might not be as effective.
        # Let's assume 'generate_content' is an LLM node and has a version after registry load.
        # For robust testing, we might need to setup a node with a specific version in the schema.
        # However, the override logic relies on the version in the GraphSchema's NodeConfig.
        
        # Let's simulate a node with a version in the schema
        test_node_id_with_version = "generate_content"
        base_schema.nodes[test_node_id_with_version].node_version = "1.0.0" # Assign a version for test
        original_temp = base_schema.nodes[test_node_id_with_version].node_config["llm_config"]["temperature"]

        override_payload = {
            "node_configs": [
                {
                    "node_name": target_node_name,
                    "node_version": "1.0.0", # Specific version
                    "node_config": {
                        "llm_config": { "temperature": 0.1 }
                    }
                },
                { # This should not apply if we add another LLM node with a different version
                    "node_name": target_node_name,
                    "node_version": "2.0.0",
                    "node_config": {
                        "llm_config": { "temperature": 0.99 }
                    }
                }
            ]
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry)
        self.assertEqual(
            updated_schema.nodes[test_node_id_with_version].node_config["llm_config"]["temperature"],
            0.1
        )
        self.assertNotEqual(original_temp, 0.1)

    async def test_node_config_override_by_name_no_version_applies_to_all(self):
        """Test override by node_name (no version) applies to all matching nodes."""
        base_schema = copy.deepcopy(self.base_content_generation_schema)
        # Add a second 'llm' node for testing this.
        interpret_feedback_copy_id = "interpret_feedback_copy"
        base_schema.nodes[interpret_feedback_copy_id] = NodeConfig(
            node_id=interpret_feedback_copy_id,
            node_name="llm", # Same name as 'interpret_feedback'
            node_version="1.1.0", # Different version or could be same
            node_config={
                "llm_config": {
                    "model_spec": {"provider": "openai", "model": "gpt-3.5-turbo"},
                    "temperature": 0.8
                }
            }
        )
        # Add a dummy source and an edge to satisfy GraphSchema validator for the new node
        # This is needed because GraphSchema.model_validate runs its own validators
        # even if validate_schema=False for apply_graph_override.
        dummy_source_id = "dummy_source_for_ifc"
        base_schema.nodes[dummy_source_id] = NodeConfig(
            node_id=dummy_source_id,
            node_name="dummy_node_type", # A generic name, won't be validated by registry if validate_schema=False
            node_config={}
        )
        base_schema.edges.append(EdgeSchema(
            src_node_id=dummy_source_id,
            dst_node_id=interpret_feedback_copy_id,
            mappings=[]
        ))
        # dummy_source_id itself needs an incoming edge if it's not the graph's input_node
        if dummy_source_id != base_schema.input_node_id:
            base_schema.edges.append(EdgeSchema(
                src_node_id=base_schema.input_node_id, # Typically "input_node"
                dst_node_id=dummy_source_id,
                mappings=[]
            ))

        # If GraphSchema validation were to check for outgoing edges for non-output nodes (currently commented out in graph.py):
        # if interpret_feedback_copy_id != base_schema.output_node_id:
        #     dummy_sink_id = "dummy_sink_for_ifc"
        #     base_schema.nodes[dummy_sink_id] = NodeConfig(node_id=dummy_sink_id, node_name="dummy_node_type", node_config={})
        #     base_schema.edges.append(EdgeSchema(src_node_id=interpret_feedback_copy_id, dst_node_id=dummy_sink_id, mappings=[]))

        target_node_name = "llm"
        override_temp = 0.05
        override_payload = {
            "node_configs": [
                {
                    "node_name": target_node_name, # No version specified
                    "node_config": {
                        "llm_config": { "temperature": override_temp }
                    }
                }
            ]
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False) # Validate=False to avoid issues with ad-hoc node

        for node_id, node_data in updated_schema.nodes.items():
            if node_data.node_name == target_node_name:
                self.assertEqual(node_data.node_config["llm_config"]["temperature"], override_temp)
    
    async def test_node_config_override_id_name_mismatch(self):
        """Test that override by node_id does not apply if node_name in rule mismatches."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        target_node_id = "generate_content"
        original_temp = base_schema.nodes[target_node_id].node_config["llm_config"]["temperature"]

        override_payload = {
            "node_configs": [
                {
                    "node_id": target_node_id,
                    "node_name": "not_the_correct_name", # Mismatch
                    "node_config": { "llm_config": { "temperature": 0.01 } }
                }
            ]
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry)
        self.assertEqual(
            updated_schema.nodes[target_node_id].node_config["llm_config"]["temperature"],
            original_temp # Should be unchanged
        )

    async def test_node_config_override_add_new_key(self):
        """Test adding a new key to a node's config."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        target_node_id = "generate_content"
        
        override_payload = {
            "node_configs": [
                {
                    "node_id": target_node_id,
                    "node_name": "llm",
                    "node_config": { "llm_config": { "new_param": "test_value" } }
                }
            ]
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False) # May fail validation if schema is strict
        self.assertEqual(
            updated_schema.nodes[target_node_id].node_config["llm_config"]["new_param"],
            "test_value"
        )

    async def test_node_config_override_nested_dicts_and_lists(self):
        """Test overriding nested dictionaries and lists within node_config."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        target_node_id = "construct_prompt" # prompt_constructor node
        original_vars = copy.deepcopy(base_schema.nodes[target_node_id].node_config["prompt_templates"]["user_prompt"]["variables"])

        override_payload = {
            "node_configs": [
                {
                    "node_id": target_node_id,
                    "node_name": "prompt_constructor",
                    "node_config": {
                        "prompt_templates": {
                            "user_prompt": {
                                "variables": { # Override entire dict
                                    "new_var": "new_val",
                                    "user_preferences": "overridden"
                                },
                                "template": "new template text" # Replace scalar
                            },
                            "new_prompt_type": { # Add new key
                                "id": "new_id", "template": "...", "variables": {}
                            }
                        },
                        "some_list_config": [1, {"key": "new_val"}, 30] # New list
                    }
                }
            ]
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False) # Schema for prompt_constructor may be strict
        
        updated_node_config = updated_schema.nodes[target_node_id].node_config
        self.assertEqual(updated_node_config["prompt_templates"]["user_prompt"]["variables"]["new_var"], "new_val")
        self.assertEqual(updated_node_config["prompt_templates"]["user_prompt"]["variables"]["user_preferences"], "overridden")
        self.assertIn("methodology_implementation", updated_node_config["prompt_templates"]["user_prompt"]["variables"]) # Preserved by deep merge
        self.assertEqual(updated_node_config["prompt_templates"]["user_prompt"]["variables"]["methodology_implementation"], original_vars["methodology_implementation"]) # Check original value (None) is preserved

        self.assertEqual(updated_node_config["prompt_templates"]["user_prompt"]["template"], "new template text")
        self.assertIn("new_prompt_type", updated_node_config["prompt_templates"])
        self.assertEqual(updated_node_config["some_list_config"], [1, {"key": "new_val"}, 30])


    async def test_general_metadata_override(self):
        """Test overriding the top-level metadata."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        original_metadata = copy.deepcopy(base_schema.metadata)

        override_payload = {
            "metadata": {
                "new_meta_key": "new_meta_value",
                "$graph_state": { # Merge into existing
                    "reducer": {
                        "current_generated_concepts": "new_reducer_type" # Change existing
                    },
                    "new_sub_key": "sub_value" # Add new sub-key
                }
            }
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry)
        
        self.assertEqual(updated_schema.metadata["new_meta_key"], "new_meta_value")
        self.assertEqual(updated_schema.metadata["$graph_state"]["reducer"]["current_generated_concepts"], "new_reducer_type")
        self.assertEqual(updated_schema.metadata["$graph_state"]["new_sub_key"], "sub_value")
        # Ensure original specific sub-key is still there if not overridden
        if original_metadata and "$graph_state" in original_metadata and "reducer" in original_metadata["$graph_state"]:
             pass # original_metadata["$graph_state"]["reducer"] should be different if it existed


    async def test_edges_override_replace_and_add(self):
        """Test overriding edges by replacing an existing one and adding a new one."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        # Store a reference to the original first edge's mappings for later comparison
        original_first_edge_mappings = copy.deepcopy(base_schema.edges[0].mappings)

        # Define node IDs that will be used in the override but might not exist in base_schema
        new_dest_node_id = "new_destination_for_first_edge"
        new_src_node_id_for_append = "some_new_src_node"
        new_dst_node_id_for_append = "some_new_dst_node"

        # Add these nodes to base_schema so GraphSchema.model_validate doesn't fail
        # when validate_schema=False for apply_graph_override.
        # Their node_name is generic as their specific type/config isn't the focus here.
        base_schema.nodes[new_dest_node_id] = NodeConfig(node_id=new_dest_node_id, node_name="dummy_node_type", node_config={})
        base_schema.nodes[new_src_node_id_for_append] = NodeConfig(node_id=new_src_node_id_for_append, node_name="dummy_node_type", node_config={})
        base_schema.nodes[new_dst_node_id_for_append] = NodeConfig(node_id=new_dst_node_id_for_append, node_name="dummy_node_type", node_config={})
        
        # Ensure these new nodes are structurally valid for GraphSchema (incoming/outgoing edges)
        # new_dest_node_id gets an incoming edge from 'input_node' via override. It needs an outgoing if not output_node.
        if new_dest_node_id != base_schema.output_node_id:
            base_schema.edges.append(EdgeSchema(src_node_id=new_dest_node_id, dst_node_id=base_schema.output_node_id, mappings=[]))
        
        # new_src_node_id_for_append is a source in an appended edge. It needs an incoming if not input_node.
        if new_src_node_id_for_append != base_schema.input_node_id:
             base_schema.edges.append(EdgeSchema(src_node_id=base_schema.input_node_id, dst_node_id=new_src_node_id_for_append, mappings=[]))

        # new_dst_node_id_for_append is a dest in an appended edge. It needs an outgoing if not output_node.
        if new_dst_node_id_for_append != base_schema.output_node_id:
            base_schema.edges.append(EdgeSchema(src_node_id=new_dst_node_id_for_append, dst_node_id=base_schema.output_node_id, mappings=[]))

        original_edges_count = len(base_schema.edges)
        new_edges_count = len(base_schema.edges)
        new_edge_mapping = [{"src_field": "new_src", "dst_field": "new_dst"}]
        override_payload = {
            "edges": [
                { # Replace first edge entirely
                    "src_node_id": "input_node",
                    "dst_node_id": new_dest_node_id,
                    "mappings": new_edge_mapping
                },
                None, # Keep second edge as is
                # Third edge will be taken from original if override list is shorter
                # Add a new edge (if override list is longer)
                { 
                    "src_node_id": new_src_node_id_for_append,
                    "dst_node_id": new_dst_node_id_for_append,
                    "mappings": [{"src_field": "a", "dst_field": "b"}]
                } 
            ]
        }
        # validate_schema=False skips _validate_updated_graph_schema, but GraphSchema.model_validate still runs.
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False)
        self.assertEqual(updated_schema.edges[0].dst_node_id, new_dest_node_id)
        
        # Check the mappings of the first edge after deep merge
        # The override provided 1 mapping. The original first edge had 2 mappings.
        # Deep merge should update the first mapping and keep the second original mapping.
        self.assertEqual(len(updated_schema.edges[0].mappings), 2) 
        self.assertEqual(updated_schema.edges[0].mappings[0].src_field, "new_src")
        self.assertEqual(updated_schema.edges[0].mappings[0].dst_field, "new_dst")
        
        # Check that the second mapping is the original second mapping
        self.assertEqual(updated_schema.edges[0].mappings[1].src_field, original_first_edge_mappings[1].src_field)
        self.assertEqual(updated_schema.edges[0].mappings[1].dst_field, original_first_edge_mappings[1].dst_field)


        if original_edges_count > 1: # If there was a second edge originally
            # The 'None' in override_payload.edges means the second edge should be unchanged
            self.assertEqual(updated_schema.edges[1].dst_node_id, base_schema.edges[1].dst_node_id) 
            self.assertEqual(updated_schema.edges[1].mappings, base_schema.edges[1].mappings)


        # The number of edges depends on the original count and override list length
        # If override is shorter and has non-None items, it replaces.
        # If override is longer, it appends.
        # Here, override list has 3 items. If original_edges_count was >=2, edges[0] replaced, edges[1] same.
        # If original_edges_count was 3, then edges[2] would be replaced by the 3rd item in override.
        # If original_edges_count was 2, then 3rd item from override is appended.
        # This specific override has 3 elements.
        if new_edges_count <= 2:
             self.assertEqual(len(updated_schema.edges), 3) # Appended
             self.assertEqual(updated_schema.edges[2].src_node_id, new_src_node_id_for_append)
        elif new_edges_count >=3 :
            self.assertEqual(len(updated_schema.edges), new_edges_count)
            self.assertEqual(updated_schema.edges[2].src_node_id, new_src_node_id_for_append)


    async def test_list_merge_logic_with_none_and_append(self):
        """Test list merging: None in override skips update, longer override appends."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        # Target the mappings list of the first edge
        original_mappings = copy.deepcopy(base_schema.edges[0].mappings)
        
        override_payload = {
            "edges": [
                { # Modify first edge's mappings
                    "src_node_id": base_schema.edges[0].src_node_id, # Keep same
                    "dst_node_id": base_schema.edges[0].dst_node_id, # Keep same
                    "mappings": [
                        None, # First mapping in original list should remain unchanged
                        {"src_field": "override_src2", "dst_field": "override_dst2"}, # Override second mapping
                        {"src_field": "appended_src", "dst_field": "appended_dst"} # Append new mapping
                    ]
                }
                # Other edges will be implicitly kept if not mentioned or if override list is shorter
            ]
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False)
        
        updated_mappings = updated_schema.edges[0].mappings
        
        self.assertEqual(updated_mappings[0].src_field, original_mappings[0].src_field) # First is None in override
        
        if len(original_mappings) > 1:
            self.assertEqual(updated_mappings[1].src_field, "override_src2")
            self.assertEqual(len(updated_mappings), max(len(original_mappings), 3) ) # original was 2, override provides 3
            if len(updated_mappings) == 3 : # Check appended
                 self.assertEqual(updated_mappings[2].src_field, "appended_src")
        elif len(original_mappings) == 1: # Original had 1 mapping
            self.assertEqual(len(updated_mappings), 3) # Override had 3 items
            self.assertEqual(updated_mappings[1].src_field, "override_src2")
            self.assertEqual(updated_mappings[2].src_field, "appended_src")


    async def test_error_list_override_for_non_list_base(self):
        """Test TypeError when override value is list and base is not."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        # input_node_id is a string
        override_payload = {
            "input_node_id": ["this", "should", "fail"] # Trying to set a list to a string field
        }
        # Expect ValueError from Pydantic validation of GraphOverridePayload
        # The error comes from Pydantic trying to validate the type of input_node_id
        with self.assertRaisesRegex(ValueError, r"(?s)Invalid override payload structure.*input_node_id\s*Input should be a valid string"):
            await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry)

    async def test_error_list_override_for_non_list_base_pydantic_validation(self):
        """Test Pydantic error when override value is list and base GraphSchema field expects string."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        # input_node_id is a string
        override_payload_dict = { # Pass as dict to test GraphOverridePayload parsing
            "input_node_id": ["this", "should", "fail"]
        }
        # Expect ValueError from Pydantic validation of GraphOverridePayload itself,
        # as input_node_id in GraphOverridePayload expects a string.
        with self.assertRaisesRegex(ValueError, r"(?s)Invalid override payload structure.*input_node_id\s*Input should be a valid string"):
            await apply_graph_override(base_schema, override_payload_dict, db_registry=self.db_registry)


    async def test_error_empty_node_config_override(self):
        """Test ValueError for empty node_config in NodeOverrideCriteria."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        override_payload_dict = {
            "node_configs": [{
                "node_name": "llm",
                "node_config": {} # Empty, should fail NodeOverrideCriteria validation
            }]
        }
        # This validation happens during GraphOverridePayload.model_validate
        with self.assertRaisesRegex(ValueError, r"(?s)Invalid override payload structure.*Value error, 'node_config' in an override rule cannot be an empty dictionary"):
            await apply_graph_override(base_schema, override_payload_dict, db_registry=self.db_registry)


    async def test_error_validate_schema_true_no_registry(self):
        """Test ValueError if validate_schema is True but db_registry is None."""
        base_schema = self.base_content_strategy_schema
        override_payload = {"metadata": {"comment": "simple override"}}
        with self.assertRaisesRegex(ValueError, "DBRegistry must be provided if validate_schema is True"):
            await apply_graph_override(base_schema, override_payload, validate_schema=True, db_registry=None)

    async def test_validation_successful_after_valid_override(self):
        """Test successful validation after a valid override."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        target_node_id = "generate_content"
        
        override_payload = {
            "node_configs": [{
                "node_id": target_node_id, "node_name": "llm",
                "node_config": {"llm_config": {"temperature": 0.6}}
            }],
            "metadata": {"validated_override": True}
        }
        
        # This should pass without raising an error
        updated_schema = await apply_graph_override(
            base_schema, override_payload, validate_schema=True, db_registry=self.db_registry
        )
        self.assertTrue(updated_schema.metadata.get("validated_override"))
        self.assertEqual(updated_schema.nodes[target_node_id].node_config["llm_config"]["temperature"], 0.6)


    async def test_validation_failure_invalid_node_config_after_override(self):
        """Test validation failure due to an invalid node config after override."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        target_node_id = "generate_content" # LLM node
        
        # 'llm_config' expects 'model_spec' which is a dict. Setting it to int is invalid.
        override_payload = {
            "node_configs": [{
                "node_id": target_node_id, "node_name": "llm",
                "node_config": {"llm_config": {"model_spec": 123}} # Invalid type for model_spec
            }]
        }
        
        with self.assertRaisesRegex(ValueError, "Validation failed for the merged graph schema"):
            await apply_graph_override(
                base_schema, override_payload, validate_schema=True, db_registry=self.db_registry
            )

    async def test_validation_failure_graph_builder_error(self):
        """Test validation failure if GraphBuilder detects issues (e.g., broken edge)."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        
        # Override an edge to point to a non-existent node
        # THIS_NODE_DOES_NOT_EXIST is not added to base_schema.nodes, so GraphSchema validation should catch it.
        override_payload = {
            "edges": [
                { # Override first edge
                    "src_node_id": "input_node",
                    "dst_node_id": "THIS_NODE_DOES_NOT_EXIST", # Invalid destination
                    "mappings": [{"src_field": "value", "dst_field": "value"}]
                }
                # Keep other edges by not specifying them / using shorter list
            ]
        }
        # Expect error from GraphSchema's own validation due to non-existent node in edges.
        # The error scope should be 'graph_schema'.
        with self.assertRaisesRegex(ValueError, r"(?s)Validation failed for the merged graph schema.*Scope 'graph_schema'.*Target node THIS_NODE_DOES_NOT_EXIST in edge not found in nodes"):
            await apply_graph_override(
                base_schema, override_payload, validate_schema=True, db_registry=self.db_registry
            )


    async def test_complex_override_multiple_rules_and_types(self):
        """Test a complex override with multiple node rules and general property changes."""
        base_schema = copy.deepcopy(self.base_linkedin_analysis_schema)
        
        override_payload = {
            "node_configs": [
                { # Rule 1: by ID
                    "node_id": "extract_themes", "node_name": "llm",
                    "node_config": {"llm_config": {"max_tokens": 3500}}
                },
                { # Rule 2: by Name (applies to 'llm' nodes: classify_batch, analyze_theme_group)
                    "node_name": "llm", 
                    "node_config": {"llm_config": {"temperature": 0.15}}
                },
                { # Rule 3: specific node 'load_posts'
                    "node_name": "load_customer_data", "node_id": "load_posts",
                    "node_config": {"new_loader_param": True}
                }
            ],
            "metadata": {
                "analysis_version": "v2",
                "$graph_state": {"reducer": {"all_classifications_batches": "custom_append"}}
            },
            "edges": [ # Modify first edge, keep others (implicit via shorter list)
                {
                    "src_node_id": "input_node", "dst_node_id": "$graph_state",
                    "mappings": [{"src_field": "entity_username", "dst_field": "global_entity_username"}]
                }
            ]
        }

        # Validation might be tricky if 'new_loader_param' isn't in load_customer_data's schema
        updated_schema = await apply_graph_override(base_schema, override_payload, validate_schema=False, db_registry=self.db_registry)

        # Check Rule 1
        self.assertEqual(updated_schema.nodes["extract_themes"].node_config["llm_config"]["max_tokens"], 3500)
        self.assertEqual(updated_schema.nodes["extract_themes"].node_config["llm_config"]["temperature"], 0.15) # Also hit by Rule 2

        # Check Rule 2 (applied to classify_batch and analyze_theme_group, and extract_themes)
        self.assertEqual(updated_schema.nodes["classify_batch"].node_config["llm_config"]["temperature"], 0.15)
        self.assertEqual(updated_schema.nodes["analyze_theme_group"].node_config["llm_config"]["temperature"], 0.15)
        # Max tokens for these should be original, unless they were also 2000/4000
        self.assertEqual(updated_schema.nodes["classify_batch"].node_config["llm_config"]["max_tokens"], 
                         base_schema.nodes["classify_batch"].node_config["llm_config"]["max_tokens"])


        # Check Rule 3
        self.assertTrue(updated_schema.nodes["load_posts"].node_config.get("new_loader_param"))

        # Check metadata
        self.assertEqual(updated_schema.metadata["analysis_version"], "v2")
        self.assertEqual(updated_schema.metadata["$graph_state"]["reducer"]["all_classifications_batches"], "custom_append")

        # Check edges
        self.assertEqual(updated_schema.edges[0].mappings[0].dst_field, "global_entity_username")
        # Ensure other edges are still there
        self.assertGreaterEqual(len(updated_schema.edges), len(base_schema.edges) if len(override_payload["edges"]) >= len(base_schema.edges) else len(override_payload["edges"]))


    async def test_original_schema_not_mutated(self):
        """Ensure the original base_graph_schema object is not mutated."""
        base_schema_original_copy = copy.deepcopy(self.base_content_strategy_schema)
        base_schema_for_test = copy.deepcopy(self.base_content_strategy_schema)
        
        target_node_id = "generate_content"
        override_payload = {
            "node_configs": [{"node_id": target_node_id, "node_name":"llm", "node_config": {"llm_config": {"temperature": 0.1}}}]
        }
        
        await apply_graph_override(base_schema_for_test, override_payload, db_registry=self.db_registry)
        
        # Compare the original copy with the one passed to the function (which should also be unchanged)
        self.assertEqual(base_schema_original_copy.model_dump(), base_schema_for_test.model_dump())

    # --- Tests for replace_mode and list_replace_mode ---

    async def test_global_replace_mode_true_general_override(self):
        """Test global replace_mode=True replaces a general dict (metadata)."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        original_metadata = copy.deepcopy(base_schema.metadata)
        
        override_payload = {
            "metadata": {"new_key": "new_value", "completely_different": True},
            "replace_mode": True
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry)
        
        self.assertEqual(updated_schema.metadata, {"new_key": "new_value", "completely_different": True})
        self.assertNotEqual(updated_schema.metadata, original_metadata)

    async def test_global_replace_mode_true_node_config(self):
        """Test global replace_mode=True replaces node_config for a matched node."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        target_node_id = "generate_content"
        original_node_config = copy.deepcopy(base_schema.nodes[target_node_id].node_config)

        override_payload = {
            "node_configs": [{
                "node_id": target_node_id, "node_name": "llm",
                "node_config": {"new_config_key": "totally_new_config"} 
            }],
            "replace_mode": True # Global replace mode, will be inherited by the node rule
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False)
        
        expected_node_config = {"new_config_key": "totally_new_config"}
        self.assertEqual(updated_schema.nodes[target_node_id].node_config, expected_node_config)
        self.assertNotEqual(updated_schema.nodes[target_node_id].node_config, original_node_config)

    async def test_node_specific_replace_mode_true_overrides_global_false(self):
        """Test node's replace_mode=True overrides global replace_mode=False."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        target_node_id = "generate_content"
        other_node_id = "construct_prompt" # This node should merge, not replace
        
        original_target_node_config = copy.deepcopy(base_schema.nodes[target_node_id].node_config)
        original_other_node_config_template_vars = copy.deepcopy(base_schema.nodes[other_node_id].node_config["prompt_templates"]["user_prompt"]["variables"])


        override_payload = {
            "node_configs": [
                { # This node will replace its config
                    "node_id": target_node_id, "node_name": "llm",
                    "node_config": {"completely_new_llm_config": True},
                    "replace_mode": True 
                },
                { # This node will merge its config (global replace_mode is False, node rule replace_mode is None)
                    "node_id": other_node_id, "node_name": "prompt_constructor",
                    "node_config": {"prompt_templates": {"user_prompt": {"variables": {"new_var": "merged_value"}}}}
                    # replace_mode is None, inherits global False
                    # list_replace_mode is None, inherits global False
                }
            ],
            "replace_mode": False, # Global replace mode is False
            "list_replace_mode": False # Global list_replace_mode is False
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False)

        # Check target node (replaced)
        self.assertEqual(updated_schema.nodes[target_node_id].node_config, {"completely_new_llm_config": True})
        
        # Check other node (merged)
        self.assertIn("new_var", updated_schema.nodes[other_node_id].node_config["prompt_templates"]["user_prompt"]["variables"])
        self.assertEqual(updated_schema.nodes[other_node_id].node_config["prompt_templates"]["user_prompt"]["variables"]["new_var"], "merged_value")
        # Ensure original keys in the merged sub-dictionary are still there
        self.assertIn("user_preferences", updated_schema.nodes[other_node_id].node_config["prompt_templates"]["user_prompt"]["variables"])
        self.assertEqual(updated_schema.nodes[other_node_id].node_config["prompt_templates"]["user_prompt"]["variables"]["user_preferences"], original_other_node_config_template_vars["user_preferences"])


    async def test_global_list_replace_mode_true_general_edges(self):
        """Test global list_replace_mode=True replaces 'edges' list."""
        # Create a minimal base schema for this test to avoid connectivity issues
        # with GraphSchema validation after edges are replaced.
        # Only include nodes that will be connected by the new edge list.
        minimal_nodes = {
            "input_node": NodeConfig(node_id="input_node", node_name="input_node", node_config={}),
            # "generate_content": NodeConfig(node_id="generate_content", node_name="llm", node_config={"llm_config": {"temperature":0.9}}), # Removed
            "output_node": NodeConfig(node_id="output_node", node_name="output_node", node_config={})
        }
        # Original edges are irrelevant here as the 'edges' list will be fully replaced.
        # We still need a valid base GraphSchema to start with, so define some initial valid edges
        # for the initial set of nodes if they were more complex.
        # For this simplified set, an empty initial edge list or a direct connection is fine.
        minimal_edges = [
             EdgeSchema(src_node_id="input_node", dst_node_id="output_node", mappings=[]) # Initial valid connection
        ]
        base_schema = GraphSchema(
            nodes=minimal_nodes, 
            edges=minimal_edges, 
            input_node_id="input_node", 
            output_node_id="output_node",
            metadata={"original_meta": "value"}
        )
        original_edges_dump = [e.model_dump() for e in base_schema.edges]
        
        # The new edge connects input_node directly to output_node.
        # Ensure these nodes are in minimal_nodes.
        new_edge_for_replace = {"src_node_id": "input_node", "dst_node_id": "output_node", "mappings": [{"src_field": "direct_x", "dst_field": "direct_y"}]}
        
        override_payload = {
            "edges": [new_edge_for_replace], 
            "replace_mode": False, 
            "list_replace_mode": True 
        }
        
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False)
        
        self.assertEqual(len(updated_schema.edges), 1)
        self.assertEqual(updated_schema.edges[0].model_dump(exclude_unset=True), new_edge_for_replace)
        self.assertNotEqual([e.model_dump(exclude_unset=True) for e in updated_schema.edges], original_edges_dump)
        # Ensure other parts of the graph (like metadata) were not affected by list_replace_mode on edges
        self.assertEqual(updated_schema.metadata, base_schema.metadata)


    async def test_node_specific_list_replace_mode_true_node_config_list(self):
        """Test node's list_replace_mode=True replaces a list within node_config."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        # Use 'construct_prompt' node, which has 'variables' which is a dict,
        # let's add a list to its config for testing.
        target_node_id = "construct_prompt"
        base_schema.nodes[target_node_id].node_config["test_list_key"] = [{"a":1}, {"b":2}]
        original_list = base_schema.nodes[target_node_id].node_config["test_list_key"]

        override_payload = {
            "node_configs": [{
                "node_id": target_node_id, "node_name": "prompt_constructor",
                "node_config": {"test_list_key": [{"new_c": 3}]}, # This list will replace
                "replace_mode": False, # Node-level merge for dict structure
                "list_replace_mode": True # Node-level list replace
            }],
            "replace_mode": False, # Global merge
            "list_replace_mode": False # Global element-wise list merge
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False)
        
        self.assertEqual(updated_schema.nodes[target_node_id].node_config["test_list_key"], [{"new_c": 3}])
        self.assertNotEqual(updated_schema.nodes[target_node_id].node_config["test_list_key"], original_list)
        # Ensure other parts of node_config are merged (e.g. prompt_templates)
        self.assertIn("prompt_templates", updated_schema.nodes[target_node_id].node_config)


    async def test_replace_mode_true_replaces_non_list_with_list(self):
        """Test replace_mode=True allows replacing a non-list with a list."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        base_schema.metadata["scalar_key"] = "original_value"
        
        override_payload = {
            "metadata": {"scalar_key": ["new", "list", "value"]},
            "replace_mode": True
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry)
        self.assertEqual(updated_schema.metadata["scalar_key"], ["new", "list", "value"])

    async def test_replace_mode_true_replaces_list_with_non_list(self):
        """Test replace_mode=True allows replacing a list with a non-list."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        
        override_payload_dict = { # Pass as dict to test GraphOverridePayload parsing
            "edges": "this_is_now_a_string", # Replacing list with string
            "replace_mode": True 
        }
        
        # The error should come from GraphOverridePayload.model_validate because 'edges' in GraphOverridePayload expects a list.
        # `replace_mode` doesn't affect Pydantic's own type validation of the override payload itself.
        with self.assertRaisesRegex(ValueError, r"(?s)Invalid override payload structure.*edges\s*Input should be a valid list"):
            await apply_graph_override(base_schema, override_payload_dict, db_registry=self.db_registry, validate_schema=False)
        

    async def test_node_replace_mode_true_makes_list_replace_mode_irrelevant(self):
        """Node replace_mode=True, its list_replace_mode (False) should not cause element-wise merge."""
        base_schema = copy.deepcopy(self.base_content_strategy_schema)
        target_node_id = "construct_prompt"
        base_schema.nodes[target_node_id].node_config["test_list_key"] = [{"a":1}, {"b":2}]
        
        override_payload = {
            "node_configs": [{
                "node_id": target_node_id, "node_name": "prompt_constructor",
                "node_config": { # This entire dict replaces the node's original node_config
                    "test_list_key": [{"new_c": 3}], 
                    "another_key": "value"
                },
                "replace_mode": True, # Node-level replace for its node_config
                "list_replace_mode": False # This should be ignored due to replace_mode=True
            }],
        }
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False)
        
        expected_config = {
            "test_list_key": [{"new_c": 3}],
            "another_key": "value"
        }
        self.assertEqual(updated_schema.nodes[target_node_id].node_config, expected_config)

    async def test_complex_nested_override_with_content_generation_schema(self):
        """
        Test a complex, multi-level nested dictionary override using the content_generation_schema.
        This test aims to modify parts of the 'construct_initial_prompt' node's configuration,
        which includes nested dictionaries for prompt templates, variables, and construct options.
        It will demonstrate adding new keys, changing existing values at various depths,
        and ensuring that unspecified parts remain untouched (due to default merge behavior).
        """
        base_schema = copy.deepcopy(self.base_content_generation_schema)
        target_node_id = "construct_initial_prompt" # Node with complex nested config

        # Original values for assertion later (ensure only specified parts change)
        original_system_prompt_template = base_schema.nodes[target_node_id].node_config["prompt_templates"]["system_prompt"]["template"]
        original_initial_gen_prompt_vars_brief = base_schema.nodes[target_node_id].node_config["prompt_templates"]["initial_generation_prompt"]["variables"]["brief"]

        override_payload = {
            "node_configs": [
                {
                    "node_id": target_node_id,
                    "node_name": "prompt_constructor", # Verification
                    "node_config": {
                        "prompt_templates": {
                            "initial_generation_prompt": {
                                "template": "Overridden initial generation template text. {brief}", # Change template
                                "variables": {
                                    "user_dna": "overridden_user_dna_value", # Change existing variable
                                    "new_custom_variable": "new_value_here" # Add new variable
                                },
                                "construct_options": {
                                    "brief": "new_brief_source_path" # Change existing construct option
                                }
                            },
                            "system_prompt": {
                                # Keep template the same by not specifying it, but add a new key
                                "new_system_prompt_config": {"detail": "value"}
                            },
                            "added_prompt_type": { # Add a completely new prompt type
                                "id": "added_prompt",
                                "template": "Template for added prompt. {foo}",
                                "variables": {"foo": "bar"}
                            }
                        },
                        "new_top_level_config_key_in_node": "new_top_level_value" # Add new key at node_config level
                    }
                }
            ]
        }

        # Using validate_schema=False as new keys might not be in the original Pydantic model for node_config
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False)
        
        updated_node_config = updated_schema.nodes[target_node_id].node_config

        # Assertions for 'initial_generation_prompt'
        self.assertEqual(updated_node_config["prompt_templates"]["initial_generation_prompt"]["template"], "Overridden initial generation template text. {brief}")
        self.assertEqual(updated_node_config["prompt_templates"]["initial_generation_prompt"]["variables"]["user_dna"], "overridden_user_dna_value")
        self.assertEqual(updated_node_config["prompt_templates"]["initial_generation_prompt"]["variables"]["new_custom_variable"], "new_value_here")
        self.assertEqual(updated_node_config["prompt_templates"]["initial_generation_prompt"]["construct_options"]["brief"], "new_brief_source_path")
        
        # Check that an original variable in 'initial_generation_prompt.variables' that was not overridden is preserved
        self.assertEqual(updated_node_config["prompt_templates"]["initial_generation_prompt"]["variables"]["brief"], original_initial_gen_prompt_vars_brief)

        # Assertions for 'system_prompt'
        self.assertEqual(updated_node_config["prompt_templates"]["system_prompt"]["template"], original_system_prompt_template) # Unchanged
        self.assertEqual(updated_node_config["prompt_templates"]["system_prompt"]["new_system_prompt_config"], {"detail": "value"})

        # Assertion for 'added_prompt_type'
        self.assertIn("added_prompt_type", updated_node_config["prompt_templates"])
        self.assertEqual(updated_node_config["prompt_templates"]["added_prompt_type"]["template"], "Template for added prompt. {foo}")

        # Assertion for new top-level key in node_config
        self.assertEqual(updated_node_config["new_top_level_config_key_in_node"], "new_top_level_value")

        # Ensure original schema is not mutated
        self.assertNotEqual(base_schema.nodes[target_node_id].node_config, updated_node_config)


    async def test_global_node_name_override_with_linkedin_analysis_schema(self):
        """
        Test overriding configuration for all nodes of a specific type (node_name)
        using the wf_linkedin_content_analysis schema, which has multiple 'llm' nodes.
        This will apply a common change to 'llm_config.temperature' and add a new
        parameter to 'llm_config' for all 'llm' nodes.
        """
        base_schema = copy.deepcopy(self.base_linkedin_analysis_schema)
        target_node_name = "llm" # Applies to extract_themes, classify_batch, analyze_theme_group
        
        # Store original temperatures and check for absence of the new key
        original_temps: Dict[str, Optional[float]] = {}
        llm_node_ids_in_schema: List[str] = []

        for node_id, node_data in base_schema.nodes.items():
            if node_data.node_name == target_node_name:
                llm_node_ids_in_schema.append(node_id)
                original_temps[node_id] = node_data.node_config.get("llm_config", {}).get("temperature")
                self.assertNotIn("new_shared_llm_param", node_data.node_config.get("llm_config", {}))

        self.assertGreater(len(llm_node_ids_in_schema), 1, "Test precondition failed: Need multiple LLM nodes in schema.")

        new_temperature = 0.25
        new_shared_param_value = "applied_globally_to_llms"

        override_payload = {
            "node_configs": [
                {
                    "node_name": target_node_name, # No node_id, applies to all 'llm' nodes
                    # No node_version, applies to all versions of this node_name
                    "node_config": {
                        "llm_config": {
                            "temperature": new_temperature,
                            "new_shared_llm_param": new_shared_param_value,
                            "model_spec": { # Test nested override within the shared llm_config
                                "provider": "test_provider_override"
                            }
                        }
                    }
                }
            ]
        }

        # Using validate_schema=False because 'new_shared_llm_param' and 'test_provider_override' 
        # might not be in the strict Pydantic model for LLMNodeConfig's llm_config
        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False)

        for node_id in llm_node_ids_in_schema:
            updated_node_llm_config = updated_schema.nodes[node_id].node_config["llm_config"]
            self.assertEqual(updated_node_llm_config["temperature"], new_temperature)
            self.assertEqual(updated_node_llm_config["new_shared_llm_param"], new_shared_param_value)
            self.assertEqual(updated_node_llm_config["model_spec"]["provider"], "test_provider_override")
            
            # Ensure other llm_config keys (like 'model' within 'model_spec', or 'max_tokens') are preserved if they existed
            if "model" in base_schema.nodes[node_id].node_config.get("llm_config", {}).get("model_spec", {}):
                self.assertEqual(updated_node_llm_config["model_spec"]["model"], base_schema.nodes[node_id].node_config["llm_config"]["model_spec"]["model"])
            if "max_tokens" in base_schema.nodes[node_id].node_config.get("llm_config", {}):
                 self.assertEqual(updated_node_llm_config["max_tokens"], base_schema.nodes[node_id].node_config["llm_config"]["max_tokens"])


        # Check a non-LLM node to ensure it wasn't affected
        non_llm_node_id = "load_posts" # This is a 'load_customer_data' node
        self.assertEqual(
            updated_schema.nodes[non_llm_node_id].node_config,
            base_schema.nodes[non_llm_node_id].node_config
        )


    async def test_full_schema_override_with_various_replace_modes(self):
        """
        Test various replace_mode and list_replace_mode interactions on a full schema.
        This test will use the content_generation schema and apply:
        1. Global replace_mode=True for 'metadata'.
        2. Node-specific replace_mode=True for 'generate_content' node's config.
        3. Node-specific list_replace_mode=True for a list within 'store_draft' node's config,
           while its node-level replace_mode is False (inheriting global False).
        4. Default merge behavior for 'construct_initial_prompt' node.
        """
        base_schema = copy.deepcopy(self.base_content_generation_schema)

        # For 'store_draft', add a list to its config for testing list_replace_mode
        # Its store_configs is a list of dicts. Let's target that.
        original_store_configs = copy.deepcopy(base_schema.nodes["store_draft"].node_config["store_configs"])
        self.assertGreater(len(original_store_configs), 0, "Test precondition: store_draft needs store_configs")
        
        original_metadata = copy.deepcopy(base_schema.metadata) if base_schema.metadata else {}
        original_generate_content_config = copy.deepcopy(base_schema.nodes["generate_content"].node_config)
        original_construct_prompt_template = base_schema.nodes["construct_initial_prompt"].node_config["prompt_templates"]["initial_generation_prompt"]["template"]


        override_payload = {
            "metadata": {"completely_new_metadata": "yes", "version": 2.0}, # To be replaced
            "node_configs": [
                { # Rule for generate_content: Full config replacement
                    "node_id": "generate_content",
                    "node_name": "llm",
                    "node_config": {"new_llm_setup": True, "details": "fully_replaced"},
                    "replace_mode": True # This node's config will be entirely replaced
                },
                { # Rule for store_draft: Merge dicts, but replace 'store_configs' list
                    "node_id": "store_draft",
                    "node_name": "store_customer_data",
                    "node_config": {
                        "store_configs": [ # This new list will replace the original
                            {"input_field_path": "new_path", "target_path": {"docname": "new_doc"}},
                        ],
                        "another_store_param": "merged_value" # This should be merged
                    },
                    "replace_mode": False, # Merge the overall node_config dict
                    "list_replace_mode": True # But replace lists found within (like store_configs)
                },
                { # Rule for construct_initial_prompt: Default merge behavior
                    "node_id": "construct_initial_prompt",
                    "node_name": "prompt_constructor",
                    "node_config": {
                        "prompt_templates": {
                            "initial_generation_prompt": {
                                "variables": {"brief": "merged_brief_value"} # Merge this
                            }
                        }
                        # replace_mode = None (inherits global False)
                        # list_replace_mode = None (inherits global False)
                    },
                    "replace_mode": False,
                }
            ],
            "replace_mode": True, # Global: True for top-level (metadata)
                                  # but node rules can override for their node_config
            "list_replace_mode": False # Global: False (element-wise merge for lists)
                                       # but node rules can override for lists in their node_config
        }

        updated_schema = await apply_graph_override(base_schema, override_payload, db_registry=self.db_registry, validate_schema=False)

        # 1. Check metadata (global replace_mode=True applies)
        self.assertEqual(updated_schema.metadata, {"completely_new_metadata": "yes", "version": 2.0})
        self.assertNotEqual(updated_schema.metadata, original_metadata)

        # 2. Check generate_content node (node-specific replace_mode=True)
        self.assertEqual(updated_schema.nodes["generate_content"].node_config, {"new_llm_setup": True, "details": "fully_replaced"})
        self.assertNotEqual(updated_schema.nodes["generate_content"].node_config, original_generate_content_config)

        # 3. Check store_draft node (node replace_mode=False, list_replace_mode=True)
        updated_store_draft_config = updated_schema.nodes["store_draft"].node_config
        self.assertEqual(updated_store_draft_config["store_configs"], [{"input_field_path": "new_path", "target_path": {"docname": "new_doc"}}])
        self.assertNotEqual(updated_store_draft_config["store_configs"], original_store_configs)
        self.assertEqual(updated_store_draft_config["another_store_param"], "merged_value") # Merged part
        # Check that other original keys in store_draft.node_config are preserved (e.g., global_versioning)
        self.assertIn("global_versioning", updated_store_draft_config)
        self.assertEqual(updated_store_draft_config["global_versioning"], base_schema.nodes["store_draft"].node_config["global_versioning"])


        # 4. Check construct_initial_prompt node (default merge behavior)
        updated_construct_prompt_config = updated_schema.nodes["construct_initial_prompt"].node_config
        self.assertEqual(updated_construct_prompt_config["prompt_templates"]["initial_generation_prompt"]["variables"]["brief"], "merged_brief_value")
        # Check that other parts of construct_initial_prompt are preserved
        # import ipdb; ipdb.set_trace()
        self.assertEqual(updated_construct_prompt_config["prompt_templates"]["initial_generation_prompt"]["template"], original_construct_prompt_template)
        self.assertIn("system_prompt", updated_construct_prompt_config["prompt_templates"])


if __name__ == '__main__':
    unittest.main()
