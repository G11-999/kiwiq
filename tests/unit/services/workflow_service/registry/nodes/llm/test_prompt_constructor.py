import json
from typing import Dict, Any, Optional, Awaitable
import unittest
import re
from datetime import datetime
from pydantic import BaseModel # Import BaseModel for type hinting result

from global_utils.utils import datetime_now_utc

from workflow_service.config.constants import (
        INPUT_NODE_NAME,
        OUTPUT_NODE_NAME,
        OBJECT_PATH_REFERENCE_DELIMITER,
    )

from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchemaFieldConfig
from workflow_service.registry.nodes.llm.prompt import PromptConstructorNode, OBJECT_PATH_REFERENCE_DELIMITER

from workflow_service.registry.registry import DBRegistry
from workflow_service.registry.nodes.core.dynamic_nodes import InputNode, OutputNode

from workflow_service.graph.graph import (
    EdgeMapping, 
    EdgeSchema, 
    GraphSchema, 
    NodeConfig,
    ConstructDynamicSchema
)
from workflow_service.graph.builder import GraphBuilder
from workflow_service.graph.runtime.adapter import LangGraphRuntimeAdapter
from pydantic_core import ValidationError # Import for catching expected error

async def create_prompt_constructor_graph():
    """
    Create a *default* workflow graph configuration for testing PromptConstructorNode.
    Includes necessary input fields for various test scenarios (direct keys, construct options).

    Returns:
        GraphSchema: The configured graph schema with all nodes and edges
    """
    # Define potential input keys used across tests
    specific_t1_var1_key = f"template1{OBJECT_PATH_REFERENCE_DELIMITER}variable1"

    # Input node - Output schema declares all potential fields needed by the constructor
    input_node = NodeConfig(
        node_id=INPUT_NODE_NAME,
        node_name=INPUT_NODE_NAME,
        node_config={},
        dynamic_output_schema=ConstructDynamicSchema(fields={
            # For construct_options paths starting with 'data.'
            "data": DynamicSchemaFieldConfig(type="any", required=False, description="Nested data container for data.* paths"),
            # For construct_options paths starting with 'specific.'
            "specific": DynamicSchemaFieldConfig(type="any", required=False, description="Nested data container for specific.* paths"),
            # For global variable override test
            "variable1": DynamicSchemaFieldConfig(type="str", required=False, description="Direct global variable input"),
            # For template-specific variable override test
            specific_t1_var1_key: DynamicSchemaFieldConfig(type="str", required=False, description="Direct template-specific variable input"),
        })
    )

    # Prompt Constructor node
    prompt_constructor_node = NodeConfig(
        node_id="prompt_constructor",
        node_name="prompt_constructor",
        node_config={
            # Default templates and global options for basic tests.
            # Specific tests might override parts of this config via custom_graph_schema.
            "prompt_templates": {
                "template1": {
                    "id": "template1",
                    "template": "This is a template with {variable1} and {variable2} and {variable3}",
                    "variables": { "variable2": "USER_OVERRIDE_VALUE_2", "variable1": "DEFAULT_VALUE_1", "variable3": "DEFAULT_VALUE_3" }
                },
                "template2": {
                    "id": "template2", "template": "Another template with {variable1}",
                    "variables": { "variable1": "DEFAULT_VALUE_1_T2" }
                }
            },
            "global_construct_options": {
                "variable1": "data.var1_source",
                "variable3": "data.inner.var3_source"
            }
        },
        # Input schema declares all fields it *might* receive and use for lookups.
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "data": DynamicSchemaFieldConfig(type="any", required=False, description="Input for data.* construct paths"),
            "specific": DynamicSchemaFieldConfig(type="any", required=False, description="Input for specific.* construct paths"),
            "variable1": DynamicSchemaFieldConfig(type="str", required=False, description="Direct global variable input"),
            specific_t1_var1_key: DynamicSchemaFieldConfig(type="str", required=False, description="Direct template-specific variable input"),
        }),
        # Output schema defines the expected successful outputs and error field.
        dynamic_output_schema=ConstructDynamicSchema(fields={
            "template1": DynamicSchemaFieldConfig(type="str", required=True, description="Constructed template 1"), # Mark as required
            "template2": DynamicSchemaFieldConfig(type="str", required=True, description="Constructed template 2"), # Mark as required
            "prompt_template_errors": DynamicSchemaFieldConfig(type="list", required=False, description="Errors during template processing")
        })
    )

    # Output node config remains the same
    output_node = NodeConfig(
        node_id=OUTPUT_NODE_NAME,
        node_name=OUTPUT_NODE_NAME,
        node_config={},
        dynamic_input_schema=ConstructDynamicSchema(fields={
            "system_prompt": DynamicSchemaFieldConfig(type="str", required=True, description="Mapped from template 1"),
            "user_prompt": DynamicSchemaFieldConfig(type="str", required=True, description="Mapped from template 2"),
            "prompt_template_errors": DynamicSchemaFieldConfig(type="list", required=False, description="Errors during template processing")
        })
    )

    # Define edges: Map ALL potential input fields from InputNode to PromptConstructorNode
    edges = [
        EdgeSchema(
            src_node_id=INPUT_NODE_NAME,
            dst_node_id="prompt_constructor",
            mappings=[
                EdgeMapping(src_field="data", dst_field="data"),
                EdgeMapping(src_field="specific", dst_field="specific"),
                EdgeMapping(src_field="variable1", dst_field="variable1"),
                EdgeMapping(src_field=specific_t1_var1_key, dst_field=specific_t1_var1_key),
            ]
        ),
        # Edge from Prompt Constructor to Output remains the same
        EdgeSchema(
            src_node_id="prompt_constructor",
            dst_node_id=OUTPUT_NODE_NAME,
            mappings=[
                EdgeMapping(src_field="template1", dst_field="system_prompt"),
                EdgeMapping(src_field="template2", dst_field="user_prompt"),
                EdgeMapping(src_field="prompt_template_errors", dst_field="prompt_template_errors")
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


async def build_and_run_prompt_constructor_graph(
    input_data: Dict[str, Any],
    # Allow passing a custom node config to modify the default graph
    custom_node_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]: # Keep returning Dict for easier testing access
    """
    Build and run the prompt constructor graph asynchronously.

    Args:
        input_data: Dictionary containing prompt variables, potentially nested.
        custom_node_config: Optional dict to update the default prompt_constructor config.

    Returns:
        Dict[str, Any]: The output of the graph execution containing constructed prompts.
                        This is the model_dump() of the final node's output.
    """

    registry = DBRegistry()
    registry.register_node(PromptConstructorNode)
    registry.register_node(InputNode)
    registry.register_node(OutputNode)

    # Get the default graph schema
    graph_schema = await create_prompt_constructor_graph()

    # Apply custom config if provided
    if custom_node_config:
        # Ensure node_config exists before updating
        if graph_schema.nodes["prompt_constructor"].node_config is None:
             graph_schema.nodes["prompt_constructor"].node_config = {}
        graph_schema.nodes["prompt_constructor"].node_config.update(custom_node_config)


    builder = GraphBuilder(registry)
    graph_entities = builder.build_graph_entities(graph_schema)
    runtime_config = graph_entities["runtime_config"]
    runtime_config["thread_id"] = f"prompt_constructor_test_{unittest.TestCase.id(unittest.TestCase())}" # Unique thread per test
    runtime_config["use_checkpointing"] = True
    adapter = LangGraphRuntimeAdapter()
    graph = adapter.build_graph(graph_entities)

    # Execute graph asynchronously
    # The final result from aexecute_graph is typically the output of the specified output_node_id
    final_output_node_result = await adapter.aexecute_graph(
        graph=graph,
        input_data=input_data,
        config=runtime_config,
        output_node_id=graph_entities["output_node_id"]
    )

    # If the result is a Pydantic model (likely from OutputNode), dump it to dict for assertion
    if isinstance(final_output_node_result, BaseModel):
        return final_output_node_result.model_dump()
    elif isinstance(final_output_node_result, dict):
         return final_output_node_result
    else:
         # Handle unexpected result types if necessary
         return {}


class TestPromptConstructorNode(unittest.IsolatedAsyncioTestCase):

    # Helper to get the specific input key name
    def _get_specific_key(self, template_id: str, var_name: str) -> str:
         return f"{template_id}{OBJECT_PATH_REFERENCE_DELIMITER}{var_name}"

    async def test_prompt_constructor_node_with_global_construct_options(self):
        """
        Tests P2 (Global construct_options) sourcing over P5 (Defaults).
        """
        input_data = { "data": { "var1_source": "`global_construct_var1`", "inner": { "var3_source": "`global_construct_var3`" } } }
        # Uses default graph config where global options exist and override defaults
        result = await build_and_run_prompt_constructor_graph(input_data)
        expected_output = {
            'system_prompt': 'This is a template with `global_construct_var1` and USER_OVERRIDE_VALUE_2 and `global_construct_var3`', # var1, var3 from P2
            'user_prompt': 'Another template with `global_construct_var1`', # var1 from P2
            'prompt_template_errors': []
        }
        self.assertDictEqual(result, expected_output)

    async def test_template_specific_construct_options_override_global(self):
        """
        Tests P1 (Template-specific construct_options) overrides P2 (Global construct_options).
        """
        custom_config = {
            "prompt_templates": {
                "template1": {
                    "id": "template1", "template": "This is a template with {variable1} and {variable2} and {variable3}",
                    "variables": { "variable2": "USER_OVERRIDE_VALUE_2", "variable1": "DEFAULT_VALUE_1", "variable3": "DEFAULT_VALUE_3" },
                    "construct_options": { "variable1": "specific.path.var1" } # P1 for var1
                },
                "template2": {
                     "id": "template2", "template": "Another template with {variable1}",
                     "variables": { "variable1": "DEFAULT_VALUE_1_T2" }
                }
            },
             # P2 global options still defined in default graph for var1 and var3
        }
        input_data = {
            "data": { "var1_source": "`global_construct_var1_IGNORED`", "inner": { "var3_source": "`global_construct_var3`" } }, # Source for P2
            "specific": { "path": { "var1": "`template_specific_construct_var1`" } } # Source for P1
        }
        result = await build_and_run_prompt_constructor_graph(input_data, custom_node_config=custom_config)
        expected_output = {
            # template1: P1 for var1, P5 for var2, P2 for var3
            'system_prompt': 'This is a template with `template_specific_construct_var1` and USER_OVERRIDE_VALUE_2 and `global_construct_var3`',
            # template2: P2 for var1 (no P1 defined for it)
            'user_prompt': 'Another template with `global_construct_var1_IGNORED`',
            'prompt_template_errors': []
        }
        self.assertDictEqual(result, expected_output)

    async def test_construct_options_precedence_over_specific_input_key(self):
        """
        Tests P1/P2 (Construct Options) take precedence over P3 (Template-specific input key).
        Uses P2 (Global construct option) as P1 is not defined for var1 in default config.
        """
        specific_key = self._get_specific_key("template1", "variable1")
        input_data = {
            specific_key: "`specific_input_key_var1_IGNORED`", # Source for P3 (lower precedence)
            "data": { "var1_source": "`global_construct_var1`", "inner": { "var3_source": "`global_construct_var3`" } } # Source for P2 (higher precedence)
        }
        # Uses default graph config where P2 global construct option exists for var1
        result = await build_and_run_prompt_constructor_graph(input_data)
        expected_output = {
            # template1: P2 for var1, P5 for var2, P2 for var3
            'system_prompt': 'This is a template with `global_construct_var1` and USER_OVERRIDE_VALUE_2 and `global_construct_var3`',
            # template2: P2 for var1
            'user_prompt': 'Another template with `global_construct_var1`',
            'prompt_template_errors': []
        }
        self.assertDictEqual(result, expected_output)

    async def test_construct_options_precedence_over_global_input_key(self):
        """
        Tests P1/P2 (Construct Options) take precedence over P4 (Global input key).
        Uses P2 (Global construct option) as P1 is not defined for var1 in default config.
        """
        input_data = {
            "variable1": "`global_input_key_var1_IGNORED`", # Source for P4 (lower precedence)
            "data": { "var1_source": "`global_construct_var1`", "inner": { "var3_source": "`global_construct_var3`" } } # Source for P2 (higher precedence)
        }
        # Uses default graph config where P2 global construct option exists for var1
        result = await build_and_run_prompt_constructor_graph(input_data)
        expected_output = {
             # template1: P2 for var1, P5 for var2, P2 for var3
            'system_prompt': 'This is a template with `global_construct_var1` and USER_OVERRIDE_VALUE_2 and `global_construct_var3`',
             # template2: P2 for var1
            'user_prompt': 'Another template with `global_construct_var1`',
            'prompt_template_errors': []
        }
        self.assertDictEqual(result, expected_output)

    async def test_specific_input_key_precedence_over_global_input_key(self):
        """
        Tests P3 (Template-specific input key) takes precedence over P4 (Global input key).
        Requires removing construct_options for the tested variable.
        """
        specific_key = self._get_specific_key("template1", "variable1")
        # Remove construct options for variable1
        custom_config = { "global_construct_options": { "variable3": "data.inner.var3_source" } } # Only keep var3 global option

        input_data = {
            specific_key: "`specific_input_key_var1`", # Source for P3 (higher precedence)
            "variable1": "`global_input_key_var1_IGNORED`", # Source for P4 (lower precedence)
            "data": { "inner": { "var3_source": "`global_construct_var3`" } } # Source for var3 (P2)
        }
        result = await build_and_run_prompt_constructor_graph(input_data, custom_node_config=custom_config)
        expected_output = {
            # template1: P3 for var1, P5 for var2, P2 for var3
            'system_prompt': 'This is a template with `specific_input_key_var1` and USER_OVERRIDE_VALUE_2 and `global_construct_var3`',
            # template2: P4 for var1 (no P3 defined for it)
            'user_prompt': 'Another template with `global_input_key_var1_IGNORED`',
            'prompt_template_errors': []
        }
        self.assertDictEqual(result, expected_output)

    async def test_global_input_key_precedence_over_default(self):
        """
        Tests P4 (Global input key) takes precedence over P5 (Default value).
        Requires removing construct_options and specific keys for the tested variable.
        """
         # Remove construct options for variable1
        custom_config = { "global_construct_options": { "variable3": "data.inner.var3_source" } } # Only keep var3 global option

        input_data = {
            "variable1": "`global_input_key_var1`", # Source for P4 (higher precedence than P5 default)
            "data": { "inner": { "var3_source": "`global_construct_var3`" } } # Source for var3 (P2)
        }
        result = await build_and_run_prompt_constructor_graph(input_data, custom_node_config=custom_config)
        expected_output = {
            # template1: P4 for var1, P5 for var2, P2 for var3
            'system_prompt': 'This is a template with `global_input_key_var1` and USER_OVERRIDE_VALUE_2 and `global_construct_var3`',
             # template2: P4 for var1
            'user_prompt': 'Another template with `global_input_key_var1`',
            'prompt_template_errors': []
        }
        self.assertDictEqual(result, expected_output)

    async def test_missing_variable_error(self):
        """
        Tests that a ValidationError occurs if a *required* output field fails construction (P5 fails).
        """
        # Customize node config to remove default and construct option for required var3
        custom_config = {
            "prompt_templates": {
                "template1": {
                    "id": "template1", "template": "Template requires {variable3}",
                    "variables": {} # No P5 default for variable3
                },
                 "template2": { # Keep template2 simple
                     "id": "template2", "template": "Second template", "variables": {}
                 }
            },
            "global_construct_options": {} # No P1/P2 construct option for variable3
        }

        input_data = { "data": {} } # No P3/P4 source for variable3

        with self.assertRaises(ValidationError) as cm:
             await build_and_run_prompt_constructor_graph(input_data, custom_node_config=custom_config)

        self.assertIn("1 validation error for DynamicPromptConstructorNodeOutputSchema", str(cm.exception))
        self.assertIn("template1", str(cm.exception))
        self.assertIn("Field required", str(cm.exception))

    async def test_special_variables_replacement(self):
        """
        Tests the replacement of special variables like $current_date and $current_datetime.
        
        Special variables are predefined strings that get replaced with dynamic values
        when the prompt is constructed, regardless of how they were sourced
        (construct_options, direct input, or defaults).
        """
        custom_config = {
            "prompt_templates": {
                "template1": {
                    "id": "template1",
                    "template": "Today's date is {date_var} and current time is {datetime_var}",
                    "variables": {
                        "date_var": "$current_date",        # From default (P5)
                        "datetime_var": "$current_datetime"       # Will be overridden
                    }
                },
                "template2": {
                    "id": "template2", 
                    "template": "Date from path: {date_var}, direct input: {datetime_var}",
                    "variables": {
                        "date_var": "$current_date",        # From default (P5)
                        "datetime_var": "$current_datetime"       # Will be overridden
                    }  # No defaults
                }
            },
            "global_construct_options": {
                "date_var": "data.special_date"  # Will be sourced through construct_options (P2)
            }
        }
        
        # Set up input with special variables through different paths
        input_data = {
            "datetime_var": "$current_datetime",  # Direct input (P4)
            "data": {
                "special_date": "$current_date"   # Via construct_options path
            }
        }
        
        result = await build_and_run_prompt_constructor_graph(input_data, custom_node_config=custom_config)
        
        # Verify date format in the first template (YYYY-MM-DD)
        date_pattern = r'\d{4}-\d{2}-\d{2}'
        datetime_pattern = r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'
        
        # First template should have date from default and datetime from direct input
        self.assertRegex(result['system_prompt'], f"Today's date is {date_pattern} and current time is {datetime_pattern}")
        
        # Second template should have date from construct_options and datetime from direct input
        self.assertRegex(result['user_prompt'], f"Date from path: {date_pattern}, direct input: {datetime_pattern}")
        
        # Verify that the dates are actually today's date
        today = datetime_now_utc().strftime("%Y-%m-%d")
        self.assertIn(today, result['system_prompt'])
        self.assertIn(today, result['user_prompt'])

    async def test_user_custom_instructions(self):
        """
        Tests that user_custom_instructions are properly appended to the template content.
        """
        # Define custom config with user_custom_instructions
        custom_instructions = "Please provide a detailed explanation with examples."
        custom_config = {
            "prompt_templates": {
                "template1": {
                    "id": "template1",
                    "template": "This is a template with {variable1}",
                    "variables": {"variable1": "DEFAULT_VALUE_1"},
                    "user_custom_instructions": custom_instructions
                },
                "template2": {
                    "id": "template2", 
                    "template": "Another template with {variable1}",
                    "variables": {"variable1": "DEFAULT_VALUE_1_T2"}
                    # No custom instructions for template2
                }
            }
        }
        
        input_data = {}  # Empty input is fine for this test
        
        result = await build_and_run_prompt_constructor_graph(input_data, custom_node_config=custom_config)
        
        # Verify template1 has the custom instructions appended
        expected_template1 = f"This is a template with DEFAULT_VALUE_1\n\n# Additional User Instructions\n{custom_instructions}"
        expected_template2 = "Another template with DEFAULT_VALUE_1_T2"  # No custom instructions
        
        self.assertEqual(result['system_prompt'], expected_template1)
        self.assertEqual(result['user_prompt'], expected_template2)
        self.assertEqual(result['prompt_template_errors'], [])


# Keep the main execution block
if __name__ == "__main__":
    unittest.main()
