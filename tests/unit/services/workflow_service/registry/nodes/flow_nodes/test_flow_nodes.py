# test_flow_nodes_gemini.py

import unittest
import copy
import json

# Use real imports
from pydantic import ValidationError # Import for catching validation errors

# Assuming your refactored code is in 'workflow_nodes.py'
from workflow_service.registry.nodes.core.flow_nodes_v1 import (  # flow_nodes_gemini_CURRENT_GOOD  flow_nodes
    FilterNode,
    IfElseNode,
    FilterTargets,
    FilterConfigSchema,
    IfElseConfigSchema,
    IfElseConditionConfig,
    FilterConditionGroup,
    FilterCondition,
    LogicalOperator,
    FilterOperator,
    BranchPath,
    FilterOutputSchema,
    IfElseOutputSchema
)


# === Base Test Class ===
class BaseNodeTest(unittest.TestCase):
    def setUp(self):
        self.sample_data_user_orders = {
            "user": {"name": "Alice", "age": 35, "status": "active"},
            "orders": [
                {"id": 1, "status": "completed", "value": 150.0, "items": ["apple", "banana"]},
                {"id": 2, "status": "pending", "value": 75.5, "items": ["orange"]},
                {"id": 3, "status": "shipped", "value": 210.0, "items": ["apple", "grape"]}
            ],
            "metadata": {"source": "prod", "timestamp": 1234567890},
            "global_flag": True,
            "tags": ["new", "priority"]
        }

# === FilterNode Tests using unittest ===
class TestFilterNodeUnittest(BaseNodeTest):

    # --- Object Filtering Tests ---
    def test_object_filter_simple_pass(self):
        config = {"targets": [{"filter_target": None, "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": True}]}]}]}
        node = FilterNode(config=config, node_id="filter1", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        self.assertEqual(result.filtered_data, input_data_dict)

    def test_object_filter_simple_fail(self):
        config = {"targets": [{"filter_target": None, "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": False}]}]}]}
        node = FilterNode(config=config, node_id="filter2", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        self.assertIsNone(result.filtered_data)

    def test_object_filter_multi_cond_group_pass(self):
        config = {"targets": [{"filter_target": None, "condition_groups": [ {"conditions": [{"field": "user.name", "operator": "equals", "value": "NonExistent"}]}, {"conditions": [{"field": "metadata.source", "operator": "equals", "value": "prod"}]}], "group_logical_operator": "or"}]}
        node = FilterNode(config=config, node_id="filter3", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        self.assertIsNotNone(result.filtered_data)

    def test_object_filter_multi_cond_group_fail(self):
        config = {"targets": [{"filter_target": None, "condition_groups": [ {"conditions": [{"field": "user.name", "operator": "equals", "value": "NonExistent"}]}, {"conditions": [{"field": "metadata.source", "operator": "equals", "value": "prod"}]}], "group_logical_operator": "and"}]}
        node = FilterNode(config=config, node_id="filter4", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        self.assertIsNone(result.filtered_data)

    def test_object_filter_missing_field(self):
        config_pass = {"targets": [{"filter_target": None, "condition_groups": [{"conditions": [ {"field": "user.non_existent_field", "operator": "is_empty", "value": None}]}]}]}
        config_fail = {"targets": [{"filter_target": None, "condition_groups": [{"conditions": [ {"field": "user.non_existent_field", "operator": "equals", "value": "some_value"}]}]}]}
        node_pass = FilterNode(config=config_pass, node_id="filter5", prefect_mode=False)
        node_fail = FilterNode(config=config_fail, node_id="filter6", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy()
        result_pass = node_pass.process(input_data_dict); self.assertIsNotNone(result_pass.filtered_data)
        result_fail = node_fail.process(input_data_dict); self.assertIsNone(result_fail.filtered_data)

    # --- Field Filtering Tests ---
    def test_field_filter_remove_simple(self):
        config = {"targets": [{"filter_target": "metadata", "condition_groups": [{"conditions": [{"field": "metadata.source", "operator": "equals", "value": "test"}]}]}]}
        node = FilterNode(config=config, node_id="filter7", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        expected_data = input_data_dict.copy(); del expected_data["metadata"]
        self.assertEqual(result.filtered_data, expected_data)

    def test_field_filter_keep_simple(self):
        config = {"targets": [{"filter_target": "metadata", "condition_groups": [{"conditions": [{"field": "metadata.source", "operator": "equals", "value": "prod"}]}]}]}
        node = FilterNode(config=config, node_id="filter8", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        self.assertEqual(result.filtered_data, input_data_dict)

    def test_field_filter_remove_nested(self):
        config = {"targets": [{"filter_target": "user.status", "condition_groups": [{"conditions": [{"field": "user.status", "operator": "equals", "value": "inactive"}]}]}]}
        node = FilterNode(config=config, node_id="filter9", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        expected_data = copy.deepcopy(input_data_dict); del expected_data["user"]["status"]
        self.assertEqual(result.filtered_data, expected_data)

    def test_field_filter_multiple_targets(self):
        config = {"targets": [
                {"filter_target": "user.age", "condition_groups": [{"conditions": [{"field": "user.age", "operator": "greater_than", "value": 30}]}]},
                {"filter_target": "metadata", "condition_groups": [{"conditions": [{"field": "metadata.source", "operator": "equals", "value": "prod"}]}]},
                {"filter_target": "global_flag", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": False}]}]}
            ]}
        node = FilterNode(config=config, node_id="filter10", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        expected_data = input_data_dict.copy(); del expected_data["global_flag"]
        self.assertEqual(result.filtered_data, expected_data)

    # --- List Item Filtering Tests ---
    def test_list_item_filter_relative_cond(self):
        # Config: Keep if status != 'pending'. Field path *must* be absolute now.
        config = {"targets": [{"filter_target": "orders", "condition_groups": [{"conditions": [
                    # Check status of the order being iterated
                    {"field": "orders.status", "operator": "not_equals", "value": "pending"}
                 ]}]}]}
        node = FilterNode(config=config, node_id="filter11", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        expected_data = copy.deepcopy(input_data_dict)
        expected_data["orders"] = [
            {"id": 1, "status": "completed", "value": 150.0, "items": ["apple", "banana"]},
            {"id": 3, "status": "shipped", "value": 210.0, "items": ["apple", "grape"]}
        ]
        self.assertEqual(result.filtered_data, expected_data)

    def test_list_item_filter_absolute_cond(self):
         # Config: Keep if global_flag == True
        config = {"targets": [{"filter_target": "orders", "condition_groups": [{"conditions": [
                   {"field": "global_flag", "operator": "equals", "value": True}
                ]}]}]}
        node = FilterNode(config=config, node_id="filter12", prefect_mode=False)
        input_data_dict_true = self.sample_data_user_orders.copy(); result_true = node.process(input_data_dict_true)
        self.assertEqual(result_true.filtered_data["orders"], input_data_dict_true["orders"])
        input_data_dict_false = self.sample_data_user_orders.copy(); input_data_dict_false["global_flag"] = False
        result_false = node.process(input_data_dict_false); self.assertEqual(result_false.filtered_data["orders"], [])

    def test_list_item_filter_mixed_cond(self):
        # Config: Keep if orders.status != 'pending' AND global_flag == True
        config = {"targets": [{"filter_target": "orders", "condition_groups": [{"conditions": [
                    {"field": "orders.status", "operator": "not_equals", "value": "pending"}, # Absolute path to item field
                    {"field": "global_flag", "operator": "equals", "value": True}
                ], "logical_operator": "and"}]}]}
        node = FilterNode(config=config, node_id="filter13", prefect_mode=False)
        # Data 1: flag=True
        input_data_dict_1 = self.sample_data_user_orders.copy(); result_1 = node.process(input_data_dict_1)
        expected_orders_1 = [{"id": 1, "status": "completed", "value": 150.0, "items": ["apple", "banana"]}, {"id": 3, "status": "shipped", "value": 210.0, "items": ["apple", "grape"]}]
        self.assertEqual(result_1.filtered_data["orders"], expected_orders_1)
        # Data 2: flag=False
        input_data_dict_2 = self.sample_data_user_orders.copy(); input_data_dict_2["global_flag"] = False
        result_2 = node.process(input_data_dict_2); self.assertEqual(result_2.filtered_data["orders"], [])

    def test_list_item_filter_empty_list(self):
        config = {"targets": [{"filter_target": "orders", "condition_groups": [{"conditions": [
                    {"field": "orders.status", "operator": "equals", "value": "completed"}
                 ]}]}]}
        node = FilterNode(config=config, node_id="filter14", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); input_data_dict["orders"] = []
        result = node.process(input_data_dict); self.assertEqual(result.filtered_data["orders"], [])

    # --- Nested List Condition Evaluation ---
    def test_nested_list_cond_path_single_list_or(self):
         # Config: Keep item if item's 'tags' list CONTAINS 'urgent'
         # Field path must be absolute now for list item filtering logic
        data_dict = {"items": [{"id": "A", "tags": ["urgent", "internal"]}, {"id": "B", "tags": ["public", "low"]}]}
        config = {"targets": [{"filter_target": "items", "condition_groups": [{"conditions": [
                    {"field": "items.tags", "operator": "contains", "value": "urgent"}
                 ]}]}]}
        node = FilterNode(config=config, node_id="filter15", prefect_mode=False)
        result = node.process(data_dict)
        self.assertEqual(len(result.filtered_data["items"]), 1)
        self.assertEqual(result.filtered_data["items"][0]["id"], "A")

    # TODO: FIXME
    # NOTE: you can't have both above behaviour and below at the same time where the list entire object is checked vs each object in list is checked one by one!
    # def test_nested_list_cond_eval_path_single_list_or(self):
    #     # Config: Keep item if ANY value in item's 'values' list > 15 (nested_list_op=OR)
    #     # Path: items.values (absolute)
    #     data_dict = {"items": [{"id": "A", "values": [10, 20, 5]}, {"id": "B", "values": [1, 2, 3]}, {"id": "C", "values": [30, 40]}]}
    #     config = {"targets": [{"filter_target": "items", "condition_groups": [{"conditions": [
    #                 {"field": "items.values", "operator": "greater_than", "value": 15}
    #             ]}], "nested_list_logical_operator": "or"}]}
    #     node = FilterNode(config=config, node_id="filter16", prefect_mode=False)
    #     result = node.process(data_dict)
    #     self.assertEqual(len(result.filtered_data["items"]), 2)
    #     self.assertEqual(result.filtered_data["items"][0]["id"], "A")
    #     self.assertEqual(result.filtered_data["items"][1]["id"], "C")

    # def test_nested_list_cond_eval_path_single_list_and(self):
    #      # Config: Keep item if ALL values in item's 'values' list > 8 (nested_list_op=AND)
    #      # Path: items.values (absolute)
    #     data_dict = {"items": [{"id": "A", "values": [10, 20, 5]}, {"id": "B", "values": [1, 2, 3]}, {"id": "C", "values": [30, 40]}]}
    #     config = {"targets": [{"filter_target": "items", "condition_groups": [{"conditions": [
    #                 {"field": "items.values", "operator": "greater_than", "value": 8}
    #             ]}], "nested_list_logical_operator": "and"}]}
    #     node = FilterNode(config=config, node_id="filter17", prefect_mode=False)
    #     result = node.process(data_dict)
    #     self.assertEqual(len(result.filtered_data["items"]), 1)
    #     self.assertEqual(result.filtered_data["items"][0]["id"], "C")

    # def test_nested_list_cond_eval_path_multi_list_or_or(self):
    #      # Config: Keep group if OR(users(OR(scores))) > 15 (nested_list_op=OR)
    #      # Path: groups.users.scores (absolute)
    #     data_dict = {"groups": [{"id": "G1", "users": [{"name": "A", "scores": [1, 5]}, {"name": "B", "scores": [10, 12]}]},
    #                             {"id": "G2", "users": [{"name": "C", "scores": [2, 3]}, {"name": "D", "scores": [4, 6]}]},
    #                             {"id": "G3", "users": [{"name": "E", "scores": [20, 30]}]}]}
    #     config = {"targets": [{"filter_target": "groups", "condition_groups": [{"conditions": [
    #                 {"field": "groups.users.scores", "operator": "greater_than", "value": 15}
    #             ]}], "nested_list_logical_operator": "or"}]}
    #     node = FilterNode(config=config, node_id="filter18", prefect_mode=False)
    #     result = node.process(data_dict)
    #     self.assertEqual(len(result.filtered_data["groups"]), 1)
    #     self.assertEqual(result.filtered_data["groups"][0]["id"], "G3")

    # def test_nested_list_cond_eval_path_multi_list_and_applied_recursively(self):
    #      # Config: Keep group if AND(users(AND(scores))) > 15 (nested_list_op=AND)
    #      # Path: groups.users.scores (absolute)
    #     data_dict = {"groups": [{"id": "G1", "users": [{"name": "A", "scores": [20, 30]}, {"name": "B", "scores": [16, 18]}]},
    #                             {"id": "G2", "users": [{"name": "C", "scores": [20, 30]}, {"name": "D", "scores": [10, 40]}]},
    #                             {"id": "G3", "users": [{"name": "E", "scores": [5, 10]}]}]}
    #     config = {"targets": [{"filter_target": "groups", "condition_groups": [{"conditions": [
    #                 {"field": "groups.users.scores", "operator": "greater_than", "value": 15}
    #             ]}], "nested_list_logical_operator": "and"}]}
    #     node = FilterNode(config=config, node_id="filter19", prefect_mode=False)
    #     result = node.process(data_dict)
    #     self.assertEqual(len(result.filtered_data["groups"]), 1)
    #     self.assertEqual(result.filtered_data["groups"][0]["id"], "G1")

    # --- Edge Cases & Complex Scenarios ---
    def test_filter_mixed_targets(self):
        config = {"targets": [
                {"filter_target": None, "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": True}]}]},
                {"filter_target": "user.status", "condition_groups": [{"conditions": [{"field": "user.age", "operator": "greater_than_or_equals", "value": 40}]}]},
                {"filter_target": "orders", "condition_groups": [{"conditions": [{"field": "orders.value", "operator": "greater_than", "value": 100}]}]} # Absolute path
            ]}
        node = FilterNode(config=config, node_id="filter20", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        expected_data = copy.deepcopy(input_data_dict); del expected_data["user"]["status"]
        expected_data["orders"] = [{"id": 1, "status": "completed", "value": 150.0, "items": ["apple", "banana"]}, {"id": 3, "status": "shipped", "value": 210.0, "items": ["apple", "grape"]}]
        self.assertEqual(result.filtered_data, expected_data)

    def test_filter_target_non_list_for_list_filter(self):
         # Config: Target user.name (non-list), condition fails -> remove field
         config = {"targets": [{"filter_target": "user.name", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "equals", "value": "Bob"}]}]}]}
         node = FilterNode(config=config, node_id="filter21", prefect_mode=False)
         input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
         expected_data = copy.deepcopy(input_data_dict); del expected_data["user"]["name"]
         self.assertEqual(result.filtered_data, expected_data)

    def test_filter_target_removal_interplay(self):
        input_data_dict = self.sample_data_user_orders.copy()
        # Case 1: user kept, status removed
        config1 = {"targets": [ {"filter_target": "user", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "equals", "value": "Alice"}]}]}, {"filter_target": "user.status", "condition_groups": [{"conditions": [{"field": "user.age", "operator": "greater_than_or_equals", "value": 40}]}]}]}
        node1 = FilterNode(config=config1, node_id="filter22a", prefect_mode=False)
        result1 = node1.process(input_data_dict)
        expected1 = copy.deepcopy(input_data_dict); del expected1["user"]["status"]
        self.assertEqual(result1.filtered_data, expected1)
        # Case 2: user removed
        config2 = {"targets": [ {"filter_target": "user", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "not_equals", "value": "Alice"}]}]}, {"filter_target": "user.status", "condition_groups": [{"conditions": [{"field": "user.age", "operator": "greater_than_or_equals", "value": 40}]}]}]}
        node2 = FilterNode(config=config2, node_id="filter22b", prefect_mode=False)
        result2 = node2.process(self.sample_data_user_orders.copy()) # Fresh copy
        expected2 = copy.deepcopy(self.sample_data_user_orders); del expected2["user"]
        self.assertEqual(result2.filtered_data, expected2)

    def test_config_validation_multiple_none_targets(self):
        cond_group = {"conditions": [{"field":"f","operator":"equals","value":1}]}
        config_dict = {"targets": [{"filter_target": None, "condition_groups": [cond_group]}, {"filter_target": None, "condition_groups": [cond_group]}]}
        with self.assertRaisesRegex(ValueError, "Only one FilterConfigSchema can have filter_target=None"):
            FilterTargets(**config_dict)

    def test_config_validation_duplicate_path_targets(self):
        cond_group = {"conditions": [{"field":"f","operator":"equals","value":1}]}
        config_dict = {"targets": [{"filter_target": "user.name", "condition_groups": [cond_group]}, {"filter_target": "user.name", "condition_groups": [cond_group]}]}
        with self.assertRaisesRegex(ValueError, "Duplicate filter_target path found: 'user.name'"):
            FilterTargets(**config_dict)


# === IfElseNode Tests using unittest ===
class TestIfElseNodeUnittest(BaseNodeTest):

    # --- Basic Tests ---
    def test_ifelse_single_tag_pass(self):
        config = {"tagged_conditions": [{"tag": "check1", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": True}]}]}]}
        node = IfElseNode(config=config, node_id="ifelse1", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        self.assertEqual(result.tag_results, {"check1": True}); self.assertTrue(result.condition_result); self.assertEqual(result.branch, BranchPath.TRUE_BRANCH); self.assertEqual(result.data, input_data_dict)

    def test_ifelse_single_tag_fail(self):
        config = {"tagged_conditions": [{"tag": "check1", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": False}]}]}]}
        node = IfElseNode(config=config, node_id="ifelse2", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        self.assertEqual(result.tag_results, {"check1": False}); self.assertFalse(result.condition_result); self.assertEqual(result.branch, BranchPath.FALSE_BRANCH)

    # --- Multi-Tag Logic ---
    def test_ifelse_multi_tag_and_pass(self):
        config = {"tagged_conditions": [ {"tag": "flag", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": True}]}]}, {"tag": "user", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "equals", "value": "Alice"}]}]}], "branch_logic_operator": "and"}
        node = IfElseNode(config=config, node_id="ifelse3", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        self.assertEqual(result.tag_results, {"flag": True, "user": True}); self.assertTrue(result.condition_result); self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)

    def test_ifelse_multi_tag_and_fail(self):
        config = {"tagged_conditions": [ {"tag": "flag", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": True}]}]}, {"tag": "user", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "equals", "value": "Bob"}]}]}], "branch_logic_operator": "and"}
        node = IfElseNode(config=config, node_id="ifelse4", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        self.assertEqual(result.tag_results, {"flag": True, "user": False}); self.assertFalse(result.condition_result); self.assertEqual(result.branch, BranchPath.FALSE_BRANCH)

    def test_ifelse_multi_tag_or_pass(self):
        config = {"tagged_conditions": [ {"tag": "flag", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": False}]}]}, {"tag": "user", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "equals", "value": "Alice"}]}]}], "branch_logic_operator": "or"}
        node = IfElseNode(config=config, node_id="ifelse5", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        self.assertEqual(result.tag_results, {"flag": False, "user": True}); self.assertTrue(result.condition_result); self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)

    def test_ifelse_multi_tag_or_fail(self):
        config = {"tagged_conditions": [ {"tag": "flag", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": False}]}]}, {"tag": "user", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "equals", "value": "Bob"}]}]}], "branch_logic_operator": "or"}
        node = IfElseNode(config=config, node_id="ifelse6", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        self.assertEqual(result.tag_results, {"flag": False, "user": False}); self.assertFalse(result.condition_result); self.assertEqual(result.branch, BranchPath.FALSE_BRANCH)

    # --- Nested List Evaluation ---
    def test_ifelse_nested_list_cond_eval(self):
        # Config: Tag=True if OR(orders value) > 200
        config = {"tagged_conditions": [{"tag": "order_check", "condition_groups": [{"conditions": [{"field": "orders.value", "operator": "greater_than", "value": 200}]}], "nested_list_logical_operator": "or"}], "branch_logic_operator": "and"}
        node = IfElseNode(config=config, node_id="ifelse7", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        # Should be True because order id=3 has value 210
        self.assertEqual(result.tag_results, {"order_check": True})
        self.assertTrue(result.condition_result)
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)

    # --- Validation and Passthrough ---
    def test_config_validation_duplicate_tags(self):
        # Import Pydantic's specific validation error
        from pydantic import ValidationError

        cond_group = {"conditions": [{"field":"f","operator":"equals","value":1}]}
        config_dict = {"tagged_conditions": [ {"tag": "check1", "condition_groups": [cond_group]}, {"tag": "check1", "condition_groups": [cond_group]}]}
        # Catch the correct Pydantic error type
        with self.assertRaises(ValidationError) as cm:
            IfElseConfigSchema(**config_dict)
        # Check if the error message contains the expected text
        self.assertIn("Duplicate tag found: 'check1'", str(cm.exception))

    def test_ifelse_data_passthrough(self):
        config = {"tagged_conditions": [{"tag": "t1", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": True}]}]}]}
        node = IfElseNode(config=config, node_id="ifelse8", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = node.process(input_data_dict)
        self.assertEqual(result.data, input_data_dict) # Compare dict directly

# === unittest execution ===
if __name__ == '__main__':
    unittest.main()
