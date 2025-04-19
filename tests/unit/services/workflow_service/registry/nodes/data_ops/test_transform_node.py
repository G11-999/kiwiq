import unittest
import copy
from typing import Dict, Any

# Use real imports
from pydantic import ValidationError # Import for catching validation errors

# Import nodes and schemas to test
from workflow_service.registry.nodes.data_ops.transform_node import (
    TransformerNode,
    DataJoinNode,
    TransformerConfigSchema,
    TransformMappingSchema,
    MapperConfigSchema,
    MapperJoinConfigSchema,
    JoinType,
    TransformerOutputSchema,
    MapperOutputSchema
)
# Import base classes or helpers if needed (e.g., DynamicSchema if inputs require it)
# from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema

# === Base Test Class ===
class BaseTransformNodeTest(unittest.TestCase):
    """Base class for setting up common test data."""
    def setUp(self):
        """Set up sample data structures for testing."""
        self.sample_data_simple = {
            "user": {"id": 101, "name": "Alice", "email": "alice@example.com"},
            "product": {"sku": "XYZ123", "price": 99.99},
            "metadata": {"source": "web", "timestamp": 1678886400}
        }

        self.sample_data_nested = {
            "customer": {
                "details": {
                    "id": "CUST-001",
                    "profile": {
                        "first_name": "Bob",
                        "last_name": "Smith",
                        "contact": {"email": "bob.s@example.net"}
                    },
                    "status": "active"
                },
                "preferences": {
                    "newsletter": True,
                    "theme": "dark"
                }
            },
            "order_summary": {
                "last_order_id": "ORD-555",
                "total_spent": 450.75
            }
        }

        self.sample_data_for_mapping = {
            "users": [
                {"user_id": "u1", "name": "Alice", "department_id": "d1"},
                {"user_id": "u2", "name": "Bob", "department_id": "d2"},
                {"user_id": "u3", "name": "Charlie", "department_id": "d1"}
            ],
            "departments": [
                {"dept_id": "d1", "name": "Engineering", "location": "Building A"},
                {"dept_id": "d2", "name": "Marketing", "location": "Building B"}
            ],
            "posts": [
                {"post_id": "p1", "author_id": "u1", "content": "Content by Alice"},
                {"post_id": "p2", "author_id": "u2", "content": "Content by Bob"},
                {"post_id": "p3", "author_id": "u1", "content": "More content by Alice"}
            ],
            "single_user": {"user_id": "u4", "name": "David", "department_id": "d2"},
            "single_dept": {"dept_id": "d3", "name": "Sales", "location": "Remote"},
            "empty_users": [],
            "empty_departments": []
        }

# === TransformerNode Tests ===
class TestTransformerNode(BaseTransformNodeTest):
    """Test suite for the TransformerNode."""

    def test_transform_basic_mapping(self):
        """Test simple field-to-field mapping."""
        config = {
            "mappings": [
                {"source_path": "user.name", "destination_path": "customer_name"},
                {"source_path": "product.price", "destination_path": "item_cost"}
            ]
        }
        node = TransformerNode(config=config, node_id="transform1")
        result = node.process(self.sample_data_simple)
        expected = {"customer_name": "Alice", "item_cost": 99.99}
        self.assertEqual(result.transformed_data, expected)

    def test_transform_nested_source(self):
        """Test mapping from a nested source path."""
        config = {
            "mappings": [
                {"source_path": "customer.details.profile.contact.email", "destination_path": "email_address"}
            ]
        }
        node = TransformerNode(config=config, node_id="transform2")
        result = node.process(self.sample_data_nested)
        expected = {"email_address": "bob.s@example.net"}
        self.assertEqual(result.transformed_data, expected)

    def test_transform_nested_destination(self):
        """Test mapping to a nested destination path, creating intermediate dicts."""
        config = {
            "mappings": [
                {"source_path": "user.id", "destination_path": "output.user_data.id"},
                {"source_path": "metadata.timestamp", "destination_path": "output.meta.creation_time"}
            ]
        }
        node = TransformerNode(config=config, node_id="transform3")
        result = node.process(self.sample_data_simple)
        expected = {
            "output": {
                "user_data": {"id": 101},
                "meta": {"creation_time": 1678886400}
            }
        }
        self.assertEqual(result.transformed_data, expected)

    def test_transform_map_list_and_dict(self):
        """Test mapping entire lists and dictionaries."""
        config = {
            "mappings": [
                {"source_path": "users", "destination_path": "all_users"},
                {"source_path": "departments.0", "destination_path": "first_department"} # Map first dept object
            ]
        }
        node = TransformerNode(config=config, node_id="transform4")
        result = node.process(self.sample_data_for_mapping)
        expected_users = copy.deepcopy(self.sample_data_for_mapping["users"])
        expected_dept = copy.deepcopy(self.sample_data_for_mapping["departments"][0])
        expected = {"all_users": expected_users, "first_department": expected_dept}
        self.assertEqual(result.transformed_data, expected)

    def test_transform_overwrite_value(self):
        """Test that later mappings overwrite earlier ones at the same destination."""
        config = {
            "mappings": [
                {"source_path": "user.name", "destination_path": "target.value"},
                {"source_path": "product.sku", "destination_path": "target.value"} # Overwrites
            ]
        }
        node = TransformerNode(config=config, node_id="transform5")
        result = node.process(self.sample_data_simple)
        expected = {"target": {"value": "XYZ123"}}
        self.assertEqual(result.transformed_data, expected)

    def test_transform_source_path_not_found(self):
        """Test mapping when the source path does not exist (should be skipped)."""
        config = {
            "mappings": [
                {"source_path": "user.non_existent_field", "destination_path": "should_not_exist"},
                {"source_path": "user.name", "destination_path": "name"} # This one should still work
            ]
        }
        node = TransformerNode(config=config, node_id="transform6")
        result = node.process(self.sample_data_simple)
        expected = {"name": "Alice"} # Only the valid mapping is applied
        self.assertEqual(result.transformed_data, expected)

    def test_transform_source_value_is_none(self):
        """Test mapping when the source value exists but is None."""
        data_with_none = copy.deepcopy(self.sample_data_simple)
        data_with_none["user"]["email"] = None
        config = {
            "mappings": [
                {"source_path": "user.email", "destination_path": "contact_email"}
            ]
        }
        node = TransformerNode(config=config, node_id="transform7")
        result = node.process(data_with_none)
        expected = {"contact_email": None}
        self.assertEqual(result.transformed_data, expected)

    def test_transform_complex_nested_structure(self):
        """Test complex mapping involving multiple nested levels."""
        config = {
            "mappings": [
                {"source_path": "customer.details.profile.first_name", "destination_path": "output.customer.first"},
                {"source_path": "customer.details.profile.last_name", "destination_path": "output.customer.last"},
                {"source_path": "customer.preferences.theme", "destination_path": "output.settings.ui_theme"},
                {"source_path": "order_summary", "destination_path": "output.summary"}
            ]
        }
        node = TransformerNode(config=config, node_id="transform8")
        result = node.process(self.sample_data_nested)
        expected = {
            "output": {
                "customer": {"first": "Bob", "last": "Smith"},
                "settings": {"ui_theme": "dark"},
                "summary": copy.deepcopy(self.sample_data_nested["order_summary"])
            }
        }
        self.assertEqual(result.transformed_data, expected)

    def test_transform_validation_empty_path(self):
        """Test configuration validation fails for empty paths."""
        with self.assertRaises(ValidationError):
            TransformerConfigSchema(mappings=[
                {"source_path": "", "destination_path": "valid.path"}
            ])
        with self.assertRaises(ValidationError):
            TransformerConfigSchema(mappings=[
                {"source_path": "valid.path", "destination_path": "  "}
            ])

    def test_transform_empty_input(self):
        """Test transforming an empty input dictionary."""
        config = {
            "mappings": [
                {"source_path": "user.name", "destination_path": "customer_name"}
            ]
        }
        node = TransformerNode(config=config, node_id="transform9")
        result = node.process({})
        expected = {} # No source paths found
        self.assertEqual(result.transformed_data, expected)

    def test_transform_empty_mappings(self):
        """Test node with an empty mappings list (should raise validation error)."""
        with self.assertRaises(ValidationError):
             TransformerConfigSchema(mappings=[])


# === MapperNode Tests ===
class TestMapperNode(BaseTransformNodeTest):
    """Test suite for the MapperNode."""

    def test_map_basic_one_to_many(self):
        """Test basic one-to-many join (departments -> users)."""
        config = {
            "joins": [
                {
                    "primary_list_path": "departments",
                    "secondary_list_path": "users",
                    "primary_join_key": "dept_id",
                    "secondary_join_key": "department_id",
                    "output_nesting_field": "members",
                    "join_type": "one_to_many" # Explicitly setting default
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map1")
        result = node.process(self.sample_data_for_mapping)
        expected_data = copy.deepcopy(self.sample_data_for_mapping)
        # Expected nested structure
        expected_data["departments"][0]["members"] = [
            {"user_id": "u1", "name": "Alice", "department_id": "d1"},
            {"user_id": "u3", "name": "Charlie", "department_id": "d1"}
        ]
        expected_data["departments"][1]["members"] = [
            {"user_id": "u2", "name": "Bob", "department_id": "d2"}
        ]
        self.assertEqual(result.mapped_data, expected_data)

    def test_map_basic_one_to_one(self):
        """Test basic one-to-one join (users -> departments)."""
        config = {
            "joins": [
                {
                    "primary_list_path": "users",
                    "secondary_list_path": "departments",
                    "primary_join_key": "department_id",
                    "secondary_join_key": "dept_id",
                    "output_nesting_field": "department_info",
                    "join_type": "one_to_one"
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map2")
        result = node.process(self.sample_data_for_mapping)
        expected_data = copy.deepcopy(self.sample_data_for_mapping)
        # Expected nested structure
        dept1_info = copy.deepcopy(self.sample_data_for_mapping["departments"][0])
        dept2_info = copy.deepcopy(self.sample_data_for_mapping["departments"][1])
        expected_data["users"][0]["department_info"] = dept1_info
        expected_data["users"][1]["department_info"] = dept2_info
        expected_data["users"][2]["department_info"] = dept1_info
        self.assertEqual(result.mapped_data, expected_data)

    def test_map_nested_paths_all(self):
        """Test join with nested paths for lists, keys, and output."""
        nested_data = {
            "data": {
                "all_users": self.sample_data_for_mapping["users"],
                "all_departments": self.sample_data_for_mapping["departments"]
            },
            "config": {"active": True}
        }
        config = {
            "joins": [
                {
                    "primary_list_path": "data.all_users",
                    "secondary_list_path": "data.all_departments",
                    "primary_join_key": "department_id", # Simple key in primary item
                    "secondary_join_key": "dept_id", # Simple key in secondary item
                    "output_nesting_field": "dept.details", # Nested output field
                    "join_type": "one_to_one"
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map3")
        result = node.process(nested_data)
        # Check if nesting happened correctly
        user1_dept = result.mapped_data["data"]["all_users"][0]["dept"]["details"]
        self.assertEqual(user1_dept["name"], "Engineering")
        user2_dept = result.mapped_data["data"]["all_users"][1]["dept"]["details"]
        self.assertEqual(user2_dept["name"], "Marketing")

    def test_map_nested_join_keys(self):
        """Test join using nested keys within list items."""
        data = {
            "students": [
                {"id": "s1", "info": {"advisor_id": "a1"}},
                {"id": "s2", "info": {"advisor_id": "a2"}},
            ],
            "advisors": [
                {"id": "prof1", "details": {"internal_id": "a1", "name": "Dr. Foo"}},
                {"id": "prof2", "details": {"internal_id": "a2", "name": "Dr. Bar"}},
            ]
        }
        config = {
            "joins": [
                {
                    "primary_list_path": "students",
                    "secondary_list_path": "advisors",
                    "primary_join_key": "info.advisor_id", # Nested primary key
                    "secondary_join_key": "details.internal_id", # Nested secondary key
                    "output_nesting_field": "advisor_details",
                    "join_type": "one_to_one"
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map4")
        result = node.process(data)
        student1_advisor = result.mapped_data["students"][0]["advisor_details"]
        student2_advisor = result.mapped_data["students"][1]["advisor_details"]
        self.assertEqual(student1_advisor["details"]["name"], "Dr. Foo")
        self.assertEqual(student2_advisor["details"]["name"], "Dr. Bar")

    def test_map_single_object_primary(self):
        """Test joining when the primary path points to a single object."""
        config = {
            "joins": [
                {
                    "primary_list_path": "single_user", # Path to single dict
                    "secondary_list_path": "departments",
                    "primary_join_key": "department_id",
                    "secondary_join_key": "dept_id",
                    "output_nesting_field": "department_info",
                    "join_type": "one_to_one"
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map5")
        result = node.process(self.sample_data_for_mapping)
        expected_data = copy.deepcopy(self.sample_data_for_mapping)
        expected_data["single_user"]["department_info"] = copy.deepcopy(self.sample_data_for_mapping["departments"][1])
        self.assertEqual(result.mapped_data, expected_data)
        # Verify the primary object itself was modified, not wrapped in a list
        self.assertIsInstance(result.mapped_data["single_user"], dict)

    def test_map_single_object_secondary(self):
        """Test joining when the secondary path points to a single object."""
        config = {
            "joins": [
                {
                    "primary_list_path": "users",
                    "secondary_list_path": "single_dept", # Path to single dict
                    "primary_join_key": "department_id",
                    "secondary_join_key": "dept_id",
                    "output_nesting_field": "department_info",
                    "join_type": "one_to_one"
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map6")
        result = node.process(self.sample_data_for_mapping)
        expected_data = copy.deepcopy(self.sample_data_for_mapping)
        # Only users matching the single dept ID ("d3") would get it, others get None
        expected_data["users"][0]["department_info"] = None
        expected_data["users"][1]["department_info"] = None
        expected_data["users"][2]["department_info"] = None
        # Modify data to test a match
        data_with_match = copy.deepcopy(self.sample_data_for_mapping)
        data_with_match["users"][0]["department_id"] = "d3"
        result_match = node.process(data_with_match)
        expected_match_dept = copy.deepcopy(data_with_match["single_dept"])
        self.assertEqual(result_match.mapped_data["users"][0]["department_info"], expected_match_dept)
        self.assertIsNone(result_match.mapped_data["users"][1]["department_info"])

    def test_map_missing_join_key_primary(self):
        """Test when primary join key is missing in some items."""
        data_with_missing = copy.deepcopy(self.sample_data_for_mapping)
        del data_with_missing["users"][1]["department_id"] # Bob has no dept ID
        config = {
            "joins": [
                {
                    "primary_list_path": "users",
                    "secondary_list_path": "departments",
                    "primary_join_key": "department_id",
                    "secondary_join_key": "dept_id",
                    "output_nesting_field": "department_info",
                    "join_type": "one_to_one"
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map7")
        result = node.process(data_with_missing)
        dept1_info = copy.deepcopy(self.sample_data_for_mapping["departments"][0])
        # Alice and Charlie should get dept info
        self.assertEqual(result.mapped_data["users"][0]["department_info"], dept1_info)
        self.assertEqual(result.mapped_data["users"][2]["department_info"], dept1_info)
        # Bob should get None (default for missing key in one-to-one)
        self.assertIsNone(result.mapped_data["users"][1]["department_info"])

    def test_map_missing_join_key_secondary(self):
        """Test when secondary join key is missing in some items (lookup ignores them)."""
        data_with_missing = copy.deepcopy(self.sample_data_for_mapping)
        del data_with_missing["departments"][1]["dept_id"] # Marketing has no ID
        config = {
            "joins": [
                {
                    "primary_list_path": "users",
                    "secondary_list_path": "departments",
                    "primary_join_key": "department_id",
                    "secondary_join_key": "dept_id",
                    "output_nesting_field": "department_info",
                    "join_type": "one_to_one"
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map8")
        result = node.process(data_with_missing)
        dept1_info = copy.deepcopy(self.sample_data_for_mapping["departments"][0])
        # Alice and Charlie match Engineering (d1)
        self.assertEqual(result.mapped_data["users"][0]["department_info"], dept1_info)
        self.assertEqual(result.mapped_data["users"][2]["department_info"], dept1_info)
        # Bob tries to match Marketing (d2), but Marketing is missing its key, so no match found
        self.assertIsNone(result.mapped_data["users"][1]["department_info"])

    def test_map_no_match_found(self):
        """Test when a primary key value has no corresponding secondary key value."""
        data_no_match = copy.deepcopy(self.sample_data_for_mapping)
        data_no_match["users"][1]["department_id"] = "d_non_existent" # Bob's dept doesn't exist
        config = {
            "joins": [
                {
                    "primary_list_path": "users",
                    "secondary_list_path": "departments",
                    "primary_join_key": "department_id",
                    "secondary_join_key": "dept_id",
                    "output_nesting_field": "department_info",
                    "join_type": "one_to_many" # Use one-to-many to check for empty list
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map9")
        result = node.process(data_no_match)
        dept1_info = copy.deepcopy(self.sample_data_for_mapping["departments"][0])
        # Alice and Charlie match Engineering
        self.assertEqual(result.mapped_data["users"][0]["department_info"], [dept1_info])
        self.assertEqual(result.mapped_data["users"][2]["department_info"], [dept1_info])
        # Bob finds no match, gets empty list for one-to-many
        self.assertEqual(result.mapped_data["users"][1]["department_info"], [])

    def test_map_empty_primary_list(self):
        """Test joining when the primary list is empty."""
        config = {
            "joins": [
                {
                    "primary_list_path": "empty_users", # Empty list
                    "secondary_list_path": "departments",
                    "primary_join_key": "department_id",
                    "secondary_join_key": "dept_id",
                    "output_nesting_field": "department_info",
                    "join_type": "one_to_one"
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map10")
        result = node.process(self.sample_data_for_mapping)
        # The empty list should remain empty, no errors
        self.assertEqual(result.mapped_data["empty_users"], [])
        # Other data remains unchanged
        self.assertEqual(result.mapped_data["departments"], self.sample_data_for_mapping["departments"])

    def test_map_empty_secondary_list(self):
        """Test joining when the secondary list is empty."""
        config = {
            "joins": [
                {
                    "primary_list_path": "users",
                    "secondary_list_path": "empty_departments", # Empty list
                    "primary_join_key": "department_id",
                    "secondary_join_key": "dept_id",
                    "output_nesting_field": "department_info",
                    "join_type": "one_to_many"
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map11")
        result = node.process(self.sample_data_for_mapping)
        # All users should get an empty list nested, as no matches are found
        for user in result.mapped_data["users"]:
            self.assertEqual(user["department_info"], [])

    def test_map_multiple_sequential_joins(self):
        """Test performing multiple joins sequentially within one node."""
        config = {
            "joins": [
                # 1. Join departments into users (one-to-one)
                {
                    "primary_list_path": "users",
                    "secondary_list_path": "departments",
                    "primary_join_key": "department_id",
                    "secondary_join_key": "dept_id",
                    "output_nesting_field": "department_info",
                    "join_type": "one_to_one"
                },
                # 2. Join posts into users (one-to-many), using result of previous join
                {
                    "primary_list_path": "users", # Operate on the modified users list
                    "secondary_list_path": "posts",
                    "primary_join_key": "user_id",
                    "secondary_join_key": "author_id",
                    "output_nesting_field": "user_posts",
                    "join_type": "one_to_many"
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map12")
        result = node.process(self.sample_data_for_mapping)

        # Verify first join results (department_info)
        user1 = result.mapped_data["users"][0]
        user2 = result.mapped_data["users"][1]
        self.assertEqual(user1["department_info"]["name"], "Engineering")
        self.assertEqual(user2["department_info"]["name"], "Marketing")

        # Verify second join results (user_posts)
        user1_posts = user1["user_posts"]
        user2_posts = user2["user_posts"]
        user3_posts = result.mapped_data["users"][2]["user_posts"]
        self.assertEqual(len(user1_posts), 2)
        self.assertEqual(user1_posts[0]["post_id"], "p1")
        self.assertEqual(user1_posts[1]["post_id"], "p3")
        self.assertEqual(len(user2_posts), 1)
        self.assertEqual(user2_posts[0]["post_id"], "p2")
        self.assertEqual(len(user3_posts), 0) # Charlie has no posts

    def test_map_list_contains_non_dict(self):
        """Test join robustness when lists contain non-dictionary items."""
        data_mixed = copy.deepcopy(self.sample_data_for_mapping)
        data_mixed["users"].append("not_a_dict") # Add invalid item to primary
        data_mixed["departments"].insert(0, 123) # Add invalid item to secondary
        config = {
            "joins": [
                {
                    "primary_list_path": "users",
                    "secondary_list_path": "departments",
                    "primary_join_key": "department_id",
                    "secondary_join_key": "dept_id",
                    "output_nesting_field": "department_info",
                    "join_type": "one_to_one"
                }
            ]
        }
        node = DataJoinNode(config=config, node_id="map13")
        # Expect processing to succeed, skipping invalid items
        result = node.process(data_mixed)
        # Check valid users were processed
        self.assertIn("department_info", result.mapped_data["users"][0])
        self.assertIn("department_info", result.mapped_data["users"][1])
        # Check invalid primary item remains unchanged (and wasn't processed for join)
        self.assertEqual(result.mapped_data["users"][3], "not_a_dict")
        # Check that the invalid secondary item didn't break the lookup for valid items
        self.assertIsNotNone(result.mapped_data["users"][0]["department_info"]) # Should still find Engineering

    def test_map_critical_error_path_not_found(self):
        """Test that a critical error (primary/secondary list path not found) returns None."""
        config_primary = {
            "joins": [{"primary_list_path": "non_existent_users", "secondary_list_path": "departments", "primary_join_key": "a", "secondary_join_key": "b", "output_nesting_field": "c"}]
        }
        config_secondary = {
            "joins": [{"primary_list_path": "users", "secondary_list_path": "non_existent_depts", "primary_join_key": "a", "secondary_join_key": "b", "output_nesting_field": "c"}]
        }
        node1 = DataJoinNode(config=config_primary, node_id="map_err1")
        node2 = DataJoinNode(config=config_secondary, node_id="map_err2")
        result1 = node1.process(self.sample_data_for_mapping)
        result2 = node2.process(self.sample_data_for_mapping)
        self.assertIsNone(result1.mapped_data)
        self.assertIsNone(result2.mapped_data)

    def test_map_critical_error_path_not_list_or_dict(self):
        """Test critical error if path points to neither list nor dict."""
        data_invalid_type = {"users": "this_is_a_string", "departments": [1,2,3]}
        config = {
            "joins": [{"primary_list_path": "users", "secondary_list_path": "departments", "primary_join_key": "a", "secondary_join_key": "b", "output_nesting_field": "c"}]
        }
        node = DataJoinNode(config=config, node_id="map_err3")
        result = node.process(data_invalid_type)
        self.assertIsNone(result.mapped_data)

    def test_map_validation_empty_path(self):
        """Test configuration validation fails for empty paths."""
        with self.assertRaises(ValidationError):
            MapperJoinConfigSchema(primary_list_path="", secondary_list_path="b", primary_join_key="c", secondary_join_key="d", output_nesting_field="e")
        with self.assertRaises(ValidationError):
            MapperJoinConfigSchema(primary_list_path="a", secondary_list_path="  ", primary_join_key="c", secondary_join_key="d", output_nesting_field="e")
        with self.assertRaises(ValidationError):
             MapperJoinConfigSchema(primary_list_path="a", secondary_list_path="b", primary_join_key="", secondary_join_key="d", output_nesting_field="e")
        with self.assertRaises(ValidationError):
             MapperJoinConfigSchema(primary_list_path="a", secondary_list_path="b", primary_join_key="c", secondary_join_key="  ", output_nesting_field="e")
        with self.assertRaises(ValidationError):
            MapperJoinConfigSchema(primary_list_path="a", secondary_list_path="b", primary_join_key="c", secondary_join_key="d", output_nesting_field="")

    def test_map_validation_empty_joins(self):
        """Test configuration validation fails for empty joins list."""
        with self.assertRaises(ValidationError):
            MapperConfigSchema(joins=[])

# === unittest execution ===
if __name__ == '__main__':
    unittest.main()
