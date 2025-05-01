# test_flow_nodes_gemini.py

import unittest
import copy
import json

# Use real imports
from pydantic import ValidationError # Import for catching validation errors

# Assuming your refactored code is in 'workflow_nodes.py'
from workflow_service.registry.nodes.core.flow_nodes import (  # flow_nodes_gemini_CURRENT_GOOD  flow_nodes
    FilterNode,
    IfElseConditionNode,
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
class BaseNodeTest(unittest.IsolatedAsyncioTestCase):
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
    async def test_object_filter_simple_pass(self):
        config = {"targets": [{"filter_target": None, "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": True}]}]}]}
        node = FilterNode(config=config, node_id="filter1", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy()
        result = await node.process(input_data_dict)
        self.assertEqual(result.filtered_data, input_data_dict)
    
    async def test_object_filter_simple_allow_mode(self):
        """
        Test filtering with ALLOW mode on a simple object without lists.
        This test demonstrates how to:
        1. Use ALLOW mode to keep fields when conditions pass
        2. Test filtering on non-list data structures
        """
        # Create test data with a simple object structure
        test_data = {
            "person": {
                "name": "John Doe",
                "age": 30,
                "email": "john@example.com",
                "ssn": "123-45-6789",
                "address": {
                    "street": "123 Main St",
                    "city": "Anytown",
                    "zip": "12345"
                }
            },
            "account_info": {
                "account_number": "A12345",
                "balance": 1500.75,
                "type": "checking"
            }
        }
        
        # Config to:
        # 1. Keep person.name and person.age fields (ALLOW mode with conditions)
        # 2. Keep account_number and type by removing balance field
        config = {
            "targets": [
                # Target 1: Keep name field when it's not empty
                {"filter_target": "person.name", "condition_groups": [
                    {"conditions": [
                        {"field": "person.name", "operator": "is_not_empty", "value": None}
                    ]}
                ], "filter_mode": "allow"},
                
                # Target 2: Keep age field when it's greater than 18
                {"filter_target": "person.age", "condition_groups": [
                    {"conditions": [
                        {"field": "person.age", "operator": "greater_than", "value": 18}
                    ]}
                ], "filter_mode": "allow"},
                
                # Target 3: Remove email field
                {"filter_target": "person.email", "condition_groups": [
                    {"conditions": [
                        {"field": "person.email", "operator": "is_not_empty", "value": None}
                    ]}
                ], "filter_mode": "deny"},
                
                # Target 4: Remove ssn field
                {"filter_target": "person.ssn", "condition_groups": [
                    {"conditions": [
                        {"field": "person.ssn", "operator": "is_not_empty", "value": None}
                    ]}
                ], "filter_mode": "deny"},
                
                # Target 5: Remove address field
                {"filter_target": "person.address", "condition_groups": [
                    {"conditions": [
                        {"field": "person.address", "operator": "is_not_empty", "value": None}
                    ]}
                ], "filter_mode": "deny"},
                
                # Target 6: Remove balance field
                {"filter_target": "account_info.balance", "condition_groups": [
                    {"conditions": [
                        {"field": "account_info.balance", "operator": "is_not_empty", "value": None}
                    ]}
                ], "filter_mode": "deny"}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="allow_filter", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Filtered objects with only specified fields
        expected_data = {
            "person": {
                "name": "John Doe",
                "age": 30
            },
            "account_info": {
                "account_number": "A12345",
                "type": "checking"
            }
        }
        
        # Verify results
        self.assertEqual(result.filtered_data, expected_data)
        
        # Verify sensitive fields were removed
        self.assertNotIn("ssn", result.filtered_data["person"])
        self.assertNotIn("email", result.filtered_data["person"])
        self.assertNotIn("address", result.filtered_data["person"])
        self.assertNotIn("balance", result.filtered_data["account_info"])
    
    async def test_mixed_allow_deny_modes(self):
        """
        Test using both ALLOW and DENY modes in the same filter configuration.
        This demonstrates how to:
        1. Combine different filter modes in a single node
        2. Handle complex filtering scenarios with mixed approaches
        """
        # Create test data with mixed structure
        test_data = {
            "user_data": {
                "personal": {
                    "name": "Alex Johnson",
                    "dob": "1990-05-15",
                    "ssn": "987-65-4321"
                },
                "professional": {
                    "title": "Software Engineer",
                    "salary": 95000,
                    "department": "Engineering",
                    "manager": "Sarah Chen"
                }
            },
            "app_settings": {
                "notifications": {
                    "email": True,
                    "sms": False,
                    "push": True
                },
                "privacy": {
                    "share_data": False,
                    "analytics_opt_in": True
                },
                "display": {
                    "theme": "light",
                    "font_size": "medium"
                }
            }
        }
        
        # Config to:
        # 1. Keep name and dob fields from personal info
        # 2. Remove salary and manager from professional info
        # 3. Keep theme but remove font_size from display settings
        config = {
            "targets": [
                # Target 1: Keep name field when it exists
                {"filter_target": "user_data.personal.name", "condition_groups": [
                    {"conditions": [{"field": "user_data.personal.name", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "allow"},
                
                # Target 2: Keep dob field when it exists
                {"filter_target": "user_data.personal.dob", "condition_groups": [
                    {"conditions": [{"field": "user_data.personal.dob", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "allow"},
                
                # Target 3: Remove ssn field
                {"filter_target": "user_data.personal.ssn", "condition_groups": [
                    {"conditions": [{"field": "user_data.personal.ssn", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "deny"},
                
                # Target 4: Remove salary field
                {"filter_target": "user_data.professional.salary", "condition_groups": [
                    {"conditions": [{"field": "user_data.professional.salary", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "deny"},
                
                # Target 5: Remove manager field
                {"filter_target": "user_data.professional.manager", "condition_groups": [
                    {"conditions": [{"field": "user_data.professional.manager", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "deny"},
                
                # Target 6: Keep theme field
                {"filter_target": "app_settings.display.theme", "condition_groups": [
                    {"conditions": [{"field": "app_settings.display.theme", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "allow"},
                
                # Target 7: Remove font_size field
                {"filter_target": "app_settings.display.font_size", "condition_groups": [
                    {"conditions": [{"field": "app_settings.display.font_size", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "deny"}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="mixed_filter", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Complex filtered structure
        expected_data = {
            "user_data": {
                "personal": {
                    "name": "Alex Johnson",
                    "dob": "1990-05-15"
                },
                "professional": {
                    "title": "Software Engineer",
                    "department": "Engineering"
                }
            },
            "app_settings": {
                "notifications": {
                    "email": True,
                    "sms": False,
                    "push": True
                },
                "privacy": {
                    "share_data": False,
                    "analytics_opt_in": True
                },
                "display": {
                    "theme": "light"
                }
            }
        }
        
        # Verify results
        self.assertEqual(result.filtered_data, expected_data)
        
        # Verify specific fields were handled correctly
        self.assertNotIn("ssn", result.filtered_data["user_data"]["personal"])
        self.assertNotIn("salary", result.filtered_data["user_data"]["professional"])
        self.assertNotIn("manager", result.filtered_data["user_data"]["professional"])
        self.assertNotIn("font_size", result.filtered_data["app_settings"]["display"])
    
    async def test_object_filter_deny_mode_with_nested_objects(self):
        """
        Test filtering with DENY mode on nested objects without lists.
        This test demonstrates how to:
        1. Use DENY mode to remove specific nested fields
        2. Test complex path traversal in non-list structures
        """
        # Create test data with nested objects
        test_data = {
            "customer": {
                "profile": {
                    "basic_info": {
                        "name": "Jane Smith",
                        "age": 28
                    },
                    "contact": {
                        "email": "jane@example.com",
                        "phone": "555-123-4567"
                    },
                    "security": {
                        "password_hash": "abcdef123456",
                        "security_questions": {
                            "q1": "First pet's name",
                            "a1": "Fluffy"
                        }
                    }
                },
                "preferences": {
                    "notifications": True,
                    "theme": "dark"
                }
            },
            "system": {
                "version": "1.0.3",
                "debug_mode": True
            }
        }
        
        # Config to:
        # 1. Remove security information
        # 2. Remove debug_mode from system
        config = {
            "targets": [
                # Target 1: Remove entire security object
                {"filter_target": "customer.profile.security", "condition_groups": [
                    {"conditions": [{"field": "customer.profile.security", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "deny"},
                
                # Target 2: Remove phone from contact info
                {"filter_target": "customer.profile.contact.phone", "condition_groups": [
                    {"conditions": [{"field": "customer.profile.contact.phone", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "deny"},
                
                # Target 3: Remove debug_mode from system
                {"filter_target": "system.debug_mode", "condition_groups": [
                    {"conditions": [{"field": "system.debug_mode", "operator": "equals", "value": True}]}
                ], "filter_mode": "deny"}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="nested_deny_filter", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Objects with sensitive fields removed
        expected_data = {
            "customer": {
                "profile": {
                    "basic_info": {
                        "name": "Jane Smith",
                        "age": 28
                    },
                    "contact": {
                        "email": "jane@example.com"
                    }
                },
                "preferences": {
                    "notifications": True,
                    "theme": "dark"
                }
            },
            "system": {
                "version": "1.0.3"
            }
        }
        
        # Verify results
        self.assertEqual(result.filtered_data, expected_data)
        
        # Verify specific fields were removed
        self.assertNotIn("security", result.filtered_data["customer"]["profile"])
        self.assertNotIn("phone", result.filtered_data["customer"]["profile"]["contact"])
        self.assertNotIn("debug_mode", result.filtered_data["system"])
    
    
    
    async def test_edge_case_empty_objects_after_filtering(self):
        """
        Test edge case where filtering results in empty objects.
        This demonstrates how the filter node handles:
        1. Objects that become empty after filtering
        2. Proper handling of edge cases in complex structures
        """
        # Create test data with potentially empty objects after filtering
        test_data = {
            "main": {
                "section_a": {
                    "field1": "value1",
                    "sensitive": "secret"
                },
                "section_b": {
                    "sensitive_only": "top_secret"
                },
                "section_c": {
                    "field1": "keep_me",
                    "field2": "also_keep"
                }
            },
            "metadata": {
                "created_at": "2023-01-01",
                "sensitive_info": "metadata_secret"
            }
        }
        
        # Config to:
        # 1. Remove all sensitive fields
        # 2. This will make section_b empty
        config = {
            "targets": [
                {"filter_target": "main.section_a.sensitive", "condition_groups": [
                    {"conditions": [{"field": "main.section_a.sensitive", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "deny"},
                
                {"filter_target": "main.section_b.sensitive_only", "condition_groups": [
                    {"conditions": [{"field": "main.section_b.sensitive_only", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "deny"},
                
                {"filter_target": "metadata.sensitive_info", "condition_groups": [
                    {"conditions": [{"field": "metadata.sensitive_info", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "deny"}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="empty_objects_filter", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Structure with empty section_b object
        expected_data = {
            "main": {
                "section_a": {
                    "field1": "value1"
                },
                "section_b": {}, # Empty object after filtering
                "section_c": {
                    "field1": "keep_me",
                    "field2": "also_keep"
                }
            },
            "metadata": {
                "created_at": "2023-01-01"
            }
        }
        
        # Verify results
        self.assertEqual(result.filtered_data, expected_data)
        
        # Verify section_b exists but is empty
        self.assertIn("section_b", result.filtered_data["main"])
        self.assertEqual(result.filtered_data["main"]["section_b"], {})
    
    async def test_conditional_field_removal_based_on_other_fields(self):
        """
        Test removing fields conditionally based on values in other fields.
        This demonstrates how to:
        1. Use conditions on one field to determine filtering of another field
        2. Implement complex conditional logic in filtering
        """
        # Create test data with fields that should be conditionally removed
        test_data = {
            "records": [
                {
                    "id": 1,
                    "access_level": "public",
                    "content": "This is public information",
                    "details": "Additional public details"
                },
                {
                    "id": 2,
                    "access_level": "private",
                    "content": "This is private information",
                    "details": "Additional private details"
                },
                {
                    "id": 3,
                    "access_level": "restricted",
                    "content": "This is restricted information",
                    "details": "Additional restricted details"
                }
            ],
            "single_record": {
                "id": 4,
                "access_level": "private",
                "content": "This is a private single record",
                "details": "Additional private details for single record"
            }
        }
        
        # Config to:
        # 1. Remove content and details fields from any record with access_level != "public"
        config = {
            "targets": [
                # Target 1: Remove content from non-public records in the list
                {"filter_target": "records.content", "condition_groups": [
                    {"conditions": [{"field": "records.access_level", "operator": "not_equals", "value": "public"}]}
                ], "filter_mode": "deny"},
                
                # Target 2: Remove details from non-public records in the list
                {"filter_target": "records.details", "condition_groups": [
                    {"conditions": [{"field": "records.access_level", "operator": "not_equals", "value": "public"}]}
                ], "filter_mode": "deny"},
                
                # Target 3: Remove content from non-public single record
                {"filter_target": "single_record.content", "condition_groups": [
                    {"conditions": [{"field": "single_record.access_level", "operator": "not_equals", "value": "public"}]}
                ], "filter_mode": "deny"},
                
                # Target 4: Remove details from non-public single record
                {"filter_target": "single_record.details", "condition_groups": [
                    {"conditions": [{"field": "single_record.access_level", "operator": "not_equals", "value": "public"}]}
                ], "filter_mode": "deny"}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="conditional_filter", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Only public records have content and details
        expected_data = {
            "records": [
                {
                    "id": 1,
                    "access_level": "public",
                    "content": "This is public information",
                    "details": "Additional public details"
                },
                {
                    "id": 2,
                    "access_level": "private"
                },
                {
                    "id": 3,
                    "access_level": "restricted"
                }
            ],
            "single_record": {
                "id": 4,
                "access_level": "private"
            }
        }
        
        # Verify results
        self.assertEqual(result.filtered_data, expected_data)
        
        # Verify content and details were removed from non-public records
        self.assertIn("content", result.filtered_data["records"][0])  # Public record
        self.assertNotIn("content", result.filtered_data["records"][1])  # Private record
        self.assertNotIn("content", result.filtered_data["records"][2])  # Restricted record
        self.assertNotIn("content", result.filtered_data["single_record"])  # Private single record

    async def test_object_filter_with_deny_mode(self):
        """
        Test filtering with DENY mode to explicitly remove fields from objects.
        This test demonstrates how to:
        1. Filter out an entire object based on a name condition
        2. Use DENY mode to explicitly remove specific fields from objects
        """
        # Create test data with multiple user objects
        test_data = {
            "users": [
                {"name": "Alice", "age": 35, "email": "alice@example.com", "role": "admin"},
                {"name": "Bob", "age": 42, "email": "bob@example.com", "role": "user"},
                {"name": "Charlie", "age": 28, "email": "charlie@example.com", "role": "user"}
            ],
            "settings": {"mode": "production", "features": ["a", "b", "c"]}
        }
        
        # Config to:
        # 1. Filter out any user with name "Bob" (entire object)
        # 2. Remove "email" field from all remaining users (DENY specific field)
        config = {
            "targets": [
                # Target 1: Filter out users named "Bob"
                {"filter_target": "users", "condition_groups": [
                    {"conditions": [{"field": "users.name", "operator": "equals", "value": "Bob"}]}
                ], "filter_mode": "deny"},
                
                # Target 2: Remove email field from all remaining users
                {"filter_target": "users.email", "condition_groups": [
                    {"conditions": [{"field": "users.email", "operator": "is_not_empty", "value": None}]}
                ], "filter_mode": "deny"}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="deny_filter", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Two users (Bob removed), both missing email field
        expected_data = {
            "users": [
                {"name": "Alice", "age": 35, "role": "admin"},
                {"name": "Charlie", "age": 28, "role": "user"}
            ],
            "settings": {"mode": "production", "features": ["a", "b", "c"]}
        }
        
        # Verify results
        self.assertEqual(result.filtered_data, expected_data)
        
        # Verify Bob was removed
        user_names = [user["name"] for user in result.filtered_data["users"]]
        self.assertNotIn("Bob", user_names)
        
        # Verify no user has an email field
        for user in result.filtered_data["users"]:
            self.assertNotIn("email", user)
    
    async def test_complex_deny_filtering_with_multiple_conditions(self):
        """
        Test more complex DENY filtering with multiple condition groups.
        This demonstrates how to use multiple conditions to determine which fields
        or objects should be removed.
        """
        # Create test data with sensitive information
        test_data = {
            "records": [
                {"id": 1, "type": "personal", "data": {"ssn": "123-45-6789", "name": "Alice", "address": "123 Main St"}},
                {"id": 2, "type": "business", "data": {"tax_id": "87-1234567", "name": "ACME Corp", "address": "456 Business Ave"}},
                {"id": 3, "type": "personal", "data": {"ssn": "987-65-4321", "name": "Bob", "address": "789 Oak Dr"}}
            ],
            "metadata": {"classification": "confidential", "owner": "HR Department"}
        }
        
        # Config to:
        # 1. Remove SSN field from personal records
        # 2. Remove tax_id from business records
        # 3. Remove the entire metadata object if classification is confidential
        config = {
            "targets": [
                # Target 1: Remove SSN from personal records
                {"filter_target": "records.data.ssn", "condition_groups": [
                    {"conditions": [
                        {"field": "records.type", "operator": "equals", "value": "personal"},
                        {"field": "records.data.ssn", "operator": "is_not_empty", "value": None}
                    ], "logical_operator": "and"}
                ], "filter_mode": "deny"},
                
                # Target 2: Remove tax_id from business records
                {"filter_target": "records.data.tax_id", "condition_groups": [
                    {"conditions": [
                        {"field": "records.type", "operator": "equals", "value": "business"}
                    ]}
                ], "filter_mode": "deny"},
                
                # Target 3: Remove entire metadata object if classification is confidential
                {"filter_target": "metadata", "condition_groups": [
                    {"conditions": [
                        {"field": "metadata.classification", "operator": "equals", "value": "confidential"}
                    ]}
                ], "filter_mode": "deny"}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="complex_deny_filter", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Records with sensitive fields removed, metadata removed
        expected_data = {
            "records": [
                {"id": 1, "type": "personal", "data": {"name": "Alice", "address": "123 Main St"}},
                {"id": 2, "type": "business", "data": {"name": "ACME Corp", "address": "456 Business Ave"}},
                {"id": 3, "type": "personal", "data": {"name": "Bob", "address": "789 Oak Dr"}}
            ]
        }
        
        # Verify results
        self.assertEqual(result.filtered_data, expected_data)
        
        # Verify sensitive fields were removed
        for record in result.filtered_data["records"]:
            if record["type"] == "personal":
                self.assertNotIn("ssn", record["data"])
            elif record["type"] == "business":
                self.assertNotIn("tax_id", record["data"])
        
        # Verify metadata was removed
        self.assertNotIn("metadata", result.filtered_data)
    async def test_filter_with_nonexistent_target_field(self):
        """
        Test filtering when the target field doesn't exist in the data.
        The filter should be skipped gracefully without errors.
        """
        # Create test data without the target fields
        test_data = {
            "user": {"name": "Alice", "age": 30},
            "metadata": {"source": "test"}
        }
        
        # Config targeting a field that doesn't exist
        config = {
            "targets": [
                {"filter_target": "nonexistent_field", "condition_groups": [
                    {"conditions": [
                        {"field": "user.name", "operator": "equals", "value": "Alice"}
                    ]}
                ]}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="nonexistent_target", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Data should remain unchanged since the target doesn't exist
        self.assertEqual(result.filtered_data, test_data)
    
    async def test_filter_with_nonexistent_condition_field(self):
        """
        Test filtering when the condition field doesn't exist in the data.
        Conditions on non-existent fields should fail for most operators.
        """
        # Create test data
        test_data = {
            "user": {"name": "Alice"},
            "metadata": {"source": "test"}
        }
        
        # Config with condition on non-existent field
        config = {
            "targets": [
                {"filter_target": "metadata", "condition_groups": [
                    {"conditions": [
                        {"field": "user.nonexistent_field", "operator": "equals", "value": "some_value"}
                    ]}
                ]}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="nonexistent_condition", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: metadata should be removed since condition fails
        expected_data = {"user": {"name": "Alice"}}
        self.assertEqual(result.filtered_data, expected_data)
    
    async def test_filter_with_mixed_existent_nonexistent_conditions(self):
        """
        Test filtering with multiple condition groups where some reference 
        non-existent fields and others reference existing fields.
        """
        # Create test data
        test_data = {
            "user": {"name": "Alice", "age": 30},
            "metadata": {"source": "test"}
        }
        
        # Config with mixed conditions (one exists, one doesn't)
        config = {
            "targets": [
                {"filter_target": "metadata", "condition_groups": [
                    # This group should fail (non-existent field)
                    {"conditions": [
                        {"field": "user.nonexistent_field", "operator": "equals", "value": "some_value"}
                    ]},
                    # This group should pass
                    {"conditions": [
                        {"field": "user.name", "operator": "equals", "value": "Alice"}
                    ]}
                ], "group_logical_operator": "or"}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="mixed_conditions", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: metadata should be kept since one condition group passes
        self.assertEqual(result.filtered_data, test_data)
    
    async def test_filter_with_all_nonexistent_condition_fields(self):
        """
        Test filtering when all condition fields in all groups don't exist.
        All conditions should fail and the target should be filtered accordingly.
        """
        # Create test data
        test_data = {
            "user": {"name": "Alice"},
            "metadata": {"source": "test"}
        }
        
        # Config with multiple condition groups, all referencing non-existent fields
        config = {
            "targets": [
                {"filter_target": "metadata", "condition_groups": [
                    {"conditions": [
                        {"field": "nonexistent1", "operator": "equals", "value": "value1"}
                    ]},
                    {"conditions": [
                        {"field": "nonexistent2", "operator": "equals", "value": "value2"}
                    ]}
                ], "group_logical_operator": "or"}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="all_nonexistent", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: metadata should be removed since all condition groups fail
        expected_data = {"user": {"name": "Alice"}}
        self.assertEqual(result.filtered_data, expected_data)
    
    async def test_filter_with_is_empty_on_nonexistent_field(self):
        """
        Test filtering with is_empty operator on non-existent fields.
        The is_empty operator should return True for non-existent fields.
        """
        # Create test data
        test_data = {
            "user": {"name": "Alice"},
            "metadata": {"source": "test"}
        }
        
        # Config using is_empty on non-existent field
        config = {
            "targets": [
                {"filter_target": "metadata", "condition_groups": [
                    {"conditions": [
                        {"field": "user.nonexistent_field", "operator": "is_empty", "value": None}
                    ]}
                ]}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="is_empty_nonexistent", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: metadata should be kept since is_empty returns True for non-existent fields
        self.assertEqual(result.filtered_data, test_data)
    async def test_filter_with_is_not_empty_on_nonexistent_field(self):
        """
        Test filtering with is_not_empty operator on non-existent fields.
        The is_not_empty operator should return False for non-existent fields.
        """
        # Create test data
        test_data = {
            "user": {"name": "Alice"},
            "metadata": {"source": "test"}
        }
        
        # Config using is_not_empty on non-existent field
        config = {
            "targets": [
                {"filter_target": "metadata", "condition_groups": [
                    {"conditions": [
                        {"field": "user.nonexistent_field", "operator": "is_not_empty", "value": None}
                    ]}
                ]}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="is_not_empty_nonexistent", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: metadata should be removed since is_not_empty returns False for non-existent fields
        expected_data = {"user": {"name": "Alice"}}
        self.assertEqual(result.filtered_data, expected_data)
    
    async def test_filter_entire_object_with_complex_conditions(self):
        """
        Test filtering the entire object with complex conditions using filter_target=None.
        This test demonstrates how to:
        1. Use filter_target=None to apply conditions to the entire object
        2. Combine multiple conditions with AND logic
        3. Test with complex nested data structures
        """
        # Create test data with nested structure
        test_data = {
            "user": {
                "id": "U123",
                "profile": {
                    "name": "John Smith",
                    "email": "john@example.com",
                    "preferences": {
                        "notifications": True,
                        "theme": "dark"
                    }
                },
                "subscription": {
                    "plan": "premium",
                    "status": "active",
                    "renewal_date": "2023-12-31"
                }
            },
            "metrics": {
                "login_count": 42,
                "last_active": "2023-09-15T14:30:00Z"
            },
            "features_enabled": True
        }
        
        # Config targeting the entire object with multiple conditions
        config = {
            "targets": [
                {"filter_target": None, "condition_groups": [
                    {"conditions": [
                        {"field": "user.subscription.plan", "operator": "equals", "value": "premium"},
                        {"field": "user.subscription.status", "operator": "equals", "value": "active"},
                        {"field": "features_enabled", "operator": "equals", "value": True}
                    ], "logical_operator": "and"}
                ]}
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="entire_object_complex", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: All conditions pass, so the entire object should be kept
        self.assertEqual(result.filtered_data, test_data)
        
        # Test with modified data that should fail
        modified_data = copy.deepcopy(test_data)
        modified_data["user"]["subscription"]["status"] = "inactive"
        
        result2 = await node.process(modified_data)
        
        # Expected: Conditions fail, so filtered_data should be None
        self.assertIsNone(result2.filtered_data)
    
    async def test_filter_entire_object_with_nested_list_conditions(self):
        """
        Test filtering the entire object with conditions on nested lists using filter_target=None.
        This test demonstrates how to:
        1. Apply conditions to elements within nested lists
        2. Use filter_target=None to evaluate the entire object
        3. Test complex list traversal logic
        """
        # Create test data with nested lists
        test_data = {
            "organization": {
                "name": "Acme Corp",
                "departments": [
                    {
                        "name": "Engineering",
                        "employees": [
                            {"id": "E1", "name": "Alice", "role": "Developer", "level": "Senior"},
                            {"id": "E2", "name": "Bob", "role": "QA", "level": "Mid"}
                        ]
                    },
                    {
                        "name": "Marketing",
                        "employees": [
                            {"id": "E3", "name": "Charlie", "role": "Manager", "level": "Senior"},
                            {"id": "E4", "name": "Diana", "role": "Specialist", "level": "Junior"}
                        ]
                    }
                ]
            },
            "active": True
        }
        
        # Config targeting the entire object with conditions on nested list elements
        config = {
            "targets": [
                {"filter_target": None, "condition_groups": [
                    {"conditions": [
                        {"field": "organization.departments.employees.level", "operator": "equals", "value": "Senior"},
                        {"field": "active", "operator": "equals", "value": True}
                    ], "logical_operator": "and"}
                ], "nested_list_logical_operator": "or"}  # At least one employee must be Senior
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="entire_object_nested_lists", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Conditions pass (there are Senior employees), so the entire object should be kept
        self.assertEqual(result.filtered_data, test_data)
        
        # Test with modified data that should fail
        modified_data = copy.deepcopy(test_data)
        # Change all employee levels to non-Senior
        for dept in modified_data["organization"]["departments"]:
            for emp in dept["employees"]:
                emp["level"] = "Mid"
        
        result2 = await node.process(modified_data)
        
        # Expected: Conditions fail (no Senior employees), so filtered_data should be None
        self.assertIsNone(result2.filtered_data)
    async def test_object_filter_simple_fail(self):
        config = {"targets": [{"filter_target": None, "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": False}]}]}]}
        node = FilterNode(config=config, node_id="filter2", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        self.assertIsNone(result.filtered_data)

    async def test_object_filter_multi_cond_group_pass(self):
        config = {"targets": [{"filter_target": None, "condition_groups": [ {"conditions": [{"field": "user.name", "operator": "equals", "value": "NonExistent"}]}, {"conditions": [{"field": "metadata.source", "operator": "equals", "value": "prod"}]}], "group_logical_operator": "or"}]}
        node = FilterNode(config=config, node_id="filter3", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        self.assertIsNotNone(result.filtered_data)

    async def test_object_filter_multi_cond_group_fail(self):
        config = {"targets": [{"filter_target": None, "condition_groups": [ {"conditions": [{"field": "user.name", "operator": "equals", "value": "NonExistent"}]}, {"conditions": [{"field": "metadata.source", "operator": "equals", "value": "prod"}]}], "group_logical_operator": "and"}]}
        node = FilterNode(config=config, node_id="filter4", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        self.assertIsNone(result.filtered_data)

    async def test_object_filter_missing_field(self):
        config_pass = {"targets": [{"filter_target": None, "condition_groups": [{"conditions": [ {"field": "user.non_existent_field", "operator": "is_empty", "value": None}]}]}]}
        config_fail = {"targets": [{"filter_target": None, "condition_groups": [{"conditions": [ {"field": "user.non_existent_field", "operator": "equals", "value": "some_value"}]}]}]}
        node_pass = FilterNode(config=config_pass, node_id="filter5", prefect_mode=False)
        node_fail = FilterNode(config=config_fail, node_id="filter6", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy()
        result_pass = await node_pass.process(input_data_dict); self.assertIsNotNone(result_pass.filtered_data)
        result_fail = await node_fail.process(input_data_dict); self.assertIsNone(result_fail.filtered_data)

    # --- Field Filtering Tests ---
    async def test_field_filter_remove_simple(self):
        config = {"targets": [{"filter_target": "metadata", "condition_groups": [{"conditions": [{"field": "metadata.source", "operator": "equals", "value": "test"}]}]}]}
        node = FilterNode(config=config, node_id="filter7", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        expected_data = input_data_dict.copy(); del expected_data["metadata"]
        self.assertEqual(result.filtered_data, expected_data)

    async def test_field_filter_keep_simple(self):
        config = {"targets": [{"filter_target": "metadata", "condition_groups": [{"conditions": [{"field": "metadata.source", "operator": "equals", "value": "prod"}]}]}]}
        node = FilterNode(config=config, node_id="filter8", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        self.assertEqual(result.filtered_data, input_data_dict)

    async def test_field_filter_remove_nested(self):
        config = {"targets": [{"filter_target": "user.status", "condition_groups": [{"conditions": [{"field": "user.status", "operator": "equals", "value": "inactive"}]}]}]}
        node = FilterNode(config=config, node_id="filter9", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        expected_data = copy.deepcopy(input_data_dict); del expected_data["user"]["status"]
        self.assertEqual(result.filtered_data, expected_data)

    async def test_field_filter_multiple_targets(self):
        config = {"targets": [
                {"filter_target": "user.age", "condition_groups": [{"conditions": [{"field": "user.age", "operator": "greater_than", "value": 30}]}]},
                {"filter_target": "metadata", "condition_groups": [{"conditions": [{"field": "metadata.source", "operator": "equals", "value": "prod"}]}]},
                {"filter_target": "global_flag", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": False}]}]}
            ]}
        node = FilterNode(config=config, node_id="filter10", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        expected_data = input_data_dict.copy(); del expected_data["global_flag"]
        self.assertEqual(result.filtered_data, expected_data)

    # --- List Item Filtering Tests ---
    async def test_list_item_filter_relative_cond(self):
        # Config: Keep if status != 'pending'. Field path *must* be absolute now.
        config = {"targets": [{"filter_target": "orders", "condition_groups": [{"conditions": [
                    # Check status of the order being iterated
                    {"field": "orders.status", "operator": "not_equals", "value": "pending"}
                 ]}]}]}
        node = FilterNode(config=config, node_id="filter11", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        expected_data = copy.deepcopy(input_data_dict)
        expected_data["orders"] = [
            {"id": 1, "status": "completed", "value": 150.0, "items": ["apple", "banana"]},
            {"id": 3, "status": "shipped", "value": 210.0, "items": ["apple", "grape"]}
        ]
        self.assertEqual(result.filtered_data, expected_data)

    async def test_list_item_filter_absolute_cond(self):
         # Config: Keep if global_flag == True
        config = {"targets": [{"filter_target": "orders", "condition_groups": [{"conditions": [
                   {"field": "global_flag", "operator": "equals", "value": True}
                ]}]}]}
        node = FilterNode(config=config, node_id="filter12", prefect_mode=False)
        input_data_dict_true = self.sample_data_user_orders.copy(); result_true = await node.process(input_data_dict_true)
        self.assertEqual(result_true.filtered_data["orders"], input_data_dict_true["orders"])
        input_data_dict_false = self.sample_data_user_orders.copy(); input_data_dict_false["global_flag"] = False
        result_false = await node.process(input_data_dict_false); self.assertEqual(result_false.filtered_data["orders"], [])

    async def test_list_item_filter_mixed_cond(self):
        # Config: Keep if orders.status != 'pending' AND global_flag == True
        config = {"targets": [{"filter_target": "orders", "condition_groups": [{"conditions": [
                    {"field": "orders.status", "operator": "not_equals", "value": "pending"}, # Absolute path to item field
                    {"field": "global_flag", "operator": "equals", "value": True}
                ], "logical_operator": "and"}]}]}
        node = FilterNode(config=config, node_id="filter13", prefect_mode=False)
        # Data 1: flag=True
        input_data_dict_1 = self.sample_data_user_orders.copy(); result_1 = await node.process(input_data_dict_1)
        expected_orders_1 = [{"id": 1, "status": "completed", "value": 150.0, "items": ["apple", "banana"]}, {"id": 3, "status": "shipped", "value": 210.0, "items": ["apple", "grape"]}]
        self.assertEqual(result_1.filtered_data["orders"], expected_orders_1)
        # Data 2: flag=False
        input_data_dict_2 = self.sample_data_user_orders.copy(); input_data_dict_2["global_flag"] = False
        result_2 = await node.process(input_data_dict_2); self.assertEqual(result_2.filtered_data["orders"], [])

    async def test_list_item_filter_empty_list(self):
        config = {"targets": [{"filter_target": "orders", "condition_groups": [{"conditions": [
                    {"field": "orders.status", "operator": "equals", "value": "completed"}
                 ]}]}]}
        node = FilterNode(config=config, node_id="filter14", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); input_data_dict["orders"] = []
        result = await node.process(input_data_dict); self.assertEqual(result.filtered_data["orders"], [])

    # --- Nested List Condition Evaluation ---
    async def test_nested_list_cond_path_single_list_or(self):
         # Config: Keep item if item's 'tags' list CONTAINS 'urgent'
         # Field path must be absolute now for list item filtering logic
        data_dict = {"items": [{"id": "A", "tags": ["urgent", "internal"]}, {"id": "B", "tags": ["public", "low"]}]}
        config = {"targets": [{"filter_target": "items", "condition_groups": [{"conditions": [
                    {"field": "items.tags", "operator": "contains", "value": "urgent"}
                 ]}]}]}
        node = FilterNode(config=config, node_id="filter15", prefect_mode=False)
        result = await node.process(data_dict)
        self.assertEqual(len(result.filtered_data["items"]), 1)
        self.assertEqual(result.filtered_data["items"][0]["id"], "A")

    # TODO: FIXME
    # NOTE: you can't have both above behaviour and below at the same time where the list entire object is checked vs each object in list is checked one by one!
    # async def test_nested_list_cond_eval_path_single_list_or(self):
    #     # Config: Keep item if ANY value in item's 'values' list > 15 (nested_list_op=OR)
    #     # Path: items.values (absolute)
    #     data_dict = {"items": [{"id": "A", "values": [10, 20, 5]}, {"id": "B", "values": [1, 2, 3]}, {"id": "C", "values": [30, 40]}]}
    #     config = {"targets": [{"filter_target": "items", "condition_groups": [{"conditions": [
    #                 {"field": "items.values", "operator": "greater_than", "value": 15}
    #             ]}], "nested_list_logical_operator": "or"}]}
    #     node = FilterNode(config=config, node_id="filter16", prefect_mode=False)
    #     result = await node.process(data_dict)
    #     self.assertEqual(len(result.filtered_data["items"]), 2)
    #     self.assertEqual(result.filtered_data["items"][0]["id"], "A")
    #     self.assertEqual(result.filtered_data["items"][1]["id"], "C")

    # async def test_nested_list_cond_eval_path_single_list_and(self):
    #      # Config: Keep item if ALL values in item's 'values' list > 8 (nested_list_op=AND)
    #      # Path: items.values (absolute)
    #     data_dict = {"items": [{"id": "A", "values": [10, 20, 5]}, {"id": "B", "values": [1, 2, 3]}, {"id": "C", "values": [30, 40]}]}
    #     config = {"targets": [{"filter_target": "items", "condition_groups": [{"conditions": [
    #                 {"field": "items.values", "operator": "greater_than", "value": 8}
    #             ]}], "nested_list_logical_operator": "and"}]}
    #     node = FilterNode(config=config, node_id="filter17", prefect_mode=False)
    #     result = await node.process(data_dict)
    #     self.assertEqual(len(result.filtered_data["items"]), 1)
    #     self.assertEqual(result.filtered_data["items"][0]["id"], "C")

    # async def test_nested_list_cond_eval_path_multi_list_or_or(self):
    #      # Config: Keep group if OR(users(OR(scores))) > 15 (nested_list_op=OR)
    #      # Path: groups.users.scores (absolute)
    #     data_dict = {"groups": [{"id": "G1", "users": [{"name": "A", "scores": [1, 5]}, {"name": "B", "scores": [10, 12]}]},
    #                             {"id": "G2", "users": [{"name": "C", "scores": [2, 3]}, {"name": "D", "scores": [4, 6]}]},
    #                             {"id": "G3", "users": [{"name": "E", "scores": [20, 30]}]}]}
    #     config = {"targets": [{"filter_target": "groups", "condition_groups": [{"conditions": [
    #                 {"field": "groups.users.scores", "operator": "greater_than", "value": 15}
    #             ]}], "nested_list_logical_operator": "or"}]}
    #     node = FilterNode(config=config, node_id="filter18", prefect_mode=False)
    #     result = await node.process(data_dict)
    #     self.assertEqual(len(result.filtered_data["groups"]), 1)
    #     self.assertEqual(result.filtered_data["groups"][0]["id"], "G3")

    # async def test_nested_list_cond_eval_path_multi_list_and_applied_recursively(self):
    #      # Config: Keep group if AND(users(AND(scores))) > 15 (nested_list_op=AND)
    #      # Path: groups.users.scores (absolute)
    #     data_dict = {"groups": [{"id": "G1", "users": [{"name": "A", "scores": [20, 30]}, {"name": "B", "scores": [16, 18]}]},
    #                             {"id": "G2", "users": [{"name": "C", "scores": [20, 30]}, {"name": "D", "scores": [10, 40]}]},
    #                             {"id": "G3", "users": [{"name": "E", "scores": [5, 10]}]}]}
    #     config = {"targets": [{"filter_target": "groups", "condition_groups": [{"conditions": [
    #                 {"field": "groups.users.scores", "operator": "greater_than", "value": 15}
    #             ]}], "nested_list_logical_operator": "and"}]}
    #     node = FilterNode(config=config, node_id="filter19", prefect_mode=False)
    #     result = await node.process(data_dict)
    #     self.assertEqual(len(result.filtered_data["groups"]), 1)
    #     self.assertEqual(result.filtered_data["groups"][0]["id"], "G1")

    # --- Edge Cases & Complex Scenarios ---
    async def test_filter_mixed_targets(self):
        config = {"targets": [
                {"filter_target": None, "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": True}]}]},
                {"filter_target": "user.status", "condition_groups": [{"conditions": [{"field": "user.age", "operator": "greater_than_or_equals", "value": 40}]}]},
                {"filter_target": "orders", "condition_groups": [{"conditions": [{"field": "orders.value", "operator": "greater_than", "value": 100}]}]} # Absolute path
            ]}
        node = FilterNode(config=config, node_id="filter20", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        expected_data = copy.deepcopy(input_data_dict); del expected_data["user"]["status"]
        expected_data["orders"] = [{"id": 1, "status": "completed", "value": 150.0, "items": ["apple", "banana"]}, {"id": 3, "status": "shipped", "value": 210.0, "items": ["apple", "grape"]}]
        self.assertEqual(result.filtered_data, expected_data)

    async def test_filter_target_non_list_for_list_filter(self):
         # Config: Target user.name (non-list), condition fails -> remove field
         config = {"targets": [{"filter_target": "user.name", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "equals", "value": "Bob"}]}]}]}
         node = FilterNode(config=config, node_id="filter21", prefect_mode=False)
         input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
         expected_data = copy.deepcopy(input_data_dict); del expected_data["user"]["name"]
         self.assertEqual(result.filtered_data, expected_data)

    async def test_filter_target_removal_interplay(self):
        input_data_dict = self.sample_data_user_orders.copy()
        # Case 1: user kept, status removed
        config1 = {"targets": [ {"filter_target": "user", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "equals", "value": "Alice"}]}]}, {"filter_target": "user.status", "condition_groups": [{"conditions": [{"field": "user.age", "operator": "greater_than_or_equals", "value": 40}]}]}]}
        node1 = FilterNode(config=config1, node_id="filter22a", prefect_mode=False)
        result1 = await node1.process(input_data_dict)
        expected1 = copy.deepcopy(input_data_dict); del expected1["user"]["status"]
        self.assertEqual(result1.filtered_data, expected1)
        # Case 2: user removed
        config2 = {"targets": [ {"filter_target": "user", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "not_equals", "value": "Alice"}]}]}, {"filter_target": "user.status", "condition_groups": [{"conditions": [{"field": "user.age", "operator": "greater_than_or_equals", "value": 40}]}]}]}
        node2 = FilterNode(config=config2, node_id="filter22b", prefect_mode=False)
        result2 = await node2.process(self.sample_data_user_orders.copy()) # Fresh copy
        expected2 = copy.deepcopy(self.sample_data_user_orders); del expected2["user"]
        self.assertEqual(result2.filtered_data, expected2)

    async def test_config_validation_multiple_none_targets(self):
        cond_group = {"conditions": [{"field":"f","operator":"equals","value":1}]}
        config_dict = {"targets": [{"filter_target": None, "condition_groups": [cond_group]}, {"filter_target": None, "condition_groups": [cond_group]}]}
        with self.assertRaisesRegex(ValueError, "Only one FilterConfigSchema can have filter_target=None"):
            FilterTargets(**config_dict)

    async def test_config_validation_duplicate_path_targets(self):
        cond_group = {"conditions": [{"field":"f","operator":"equals","value":1}]}
        config_dict = {"targets": [{"filter_target": "user.name", "condition_groups": [cond_group]}, {"filter_target": "user.name", "condition_groups": [cond_group]}]}
        with self.assertRaisesRegex(ValueError, "Duplicate filter_target path found: 'user.name'"):
            FilterTargets(**config_dict)

    async def test_filter_with_dynamic_value_from_path(self):
        """
        Test filtering using values dynamically loaded from an input path.
        
        This test verifies that FilterNode can use another field's value as the comparison value
        by specifying value_path instead of a static value.
        """
        # Create test data with threshold values and data to filter
        test_data = {
            "thresholds": {
                "min_age": 25,
                "min_order_value": 100.0,
                "allowed_statuses": ["completed", "shipped"]
            },
            "users": [
                {"id": 1, "name": "Alice", "age": 30, "status": "active"},
                {"id": 2, "name": "Bob", "age": 22, "status": "inactive"},
                {"id": 3, "name": "Charlie", "age": 27, "status": "active"}
            ],
            "orders": [
                {"id": 101, "status": "pending", "value": 75.0},
                {"id": 102, "status": "completed", "value": 150.0},
                {"id": 103, "status": "shipped", "value": 95.0}
            ]
        }
        
        # Config to:
        # 1. Filter users whose age is less than the threshold in thresholds.min_age
        # 2. Filter orders whose value is less than the threshold in thresholds.min_order_value
        config = {
            "targets": [
                # Filter users based on dynamic age threshold
                {
                    "filter_target": "users",
                    "condition_groups": [{
                        "conditions": [{
                            "field": "users.age",
                            "operator": "greater_than_or_equals",
                            "value_path": "thresholds.min_age"
                        }]
                    }],
                    "filter_mode": "allow"
                },
                # Filter orders based on dynamic value threshold
                {
                    "filter_target": "orders",
                    "condition_groups": [{
                        "conditions": [{
                            "field": "orders.value",
                            "operator": "greater_than_or_equals",
                            "value_path": "thresholds.min_order_value"
                        }]
                    }],
                    "filter_mode": "allow"
                }
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="dynamic_filter", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected results after filtering
        expected_users = [
            {"id": 1, "name": "Alice", "age": 30, "status": "active"},
            {"id": 3, "name": "Charlie", "age": 27, "status": "active"}
        ]
        expected_orders = [
            {"id": 102, "status": "completed", "value": 150.0}
        ]
        
        # Verify results
        self.assertEqual(len(result.filtered_data["users"]), 2)
        self.assertEqual(result.filtered_data["users"], expected_users)
        self.assertEqual(len(result.filtered_data["orders"]), 1)
        self.assertEqual(result.filtered_data["orders"], expected_orders)
        
    async def test_filter_with_multiple_value_paths(self):
        """
        Test filtering using multiple conditions with different value paths.
        
        This test verifies that multiple conditions can use different value paths
        in a single filter configuration.
        """
        # Create test data with reference values and data to filter
        test_data = {
            "reference": {
                "criteria": {
                    "min_stock": 10,
                    "max_price": 50.0,
                    "featured_category": "electronics"
                }
            },
            "products": [
                {"id": "p1", "name": "Laptop", "category": "electronics", "price": 899.99, "stock": 15},
                {"id": "p2", "name": "T-shirt", "category": "clothing", "price": 19.99, "stock": 25},
                {"id": "p3", "name": "Headphones", "category": "electronics", "price": 49.99, "stock": 10},
                {"id": "p4", "name": "Smartphone", "category": "electronics", "price": 499.99, "stock": 12}
            ]
        }
        
        # Config to filter products based on multiple dynamic criteria:
        # - Category equals featured_category
        # - Stock >= min_stock
        # - Price <= max_price
        config = {
            "targets": [
                {
                    "filter_target": "products",
                    "condition_groups": [{
                        "conditions": [
                            {
                                "field": "products.category",
                                "operator": "equals",
                                "value_path": "reference.criteria.featured_category"
                            },
                            {
                                "field": "products.stock",
                                "operator": "greater_than_or_equals",
                                "value_path": "reference.criteria.min_stock"
                            },
                            {
                                "field": "products.price",
                                "operator": "less_than_or_equals",
                                "value_path": "reference.criteria.max_price"
                            }
                        ],
                        "logical_operator": "and"
                    }],
                    "filter_mode": "allow"
                }
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="multi_path_filter", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Only one product meets all criteria
        expected_products = [
            {"id": "p3", "name": "Headphones", "category": "electronics", "price": 49.99, "stock": 10}
        ]
        
        # Verify results - should have filtered to only products that match all criteria
        self.assertEqual(len(result.filtered_data["products"]), 1)
        
        # Verify the specific product that was kept
        self.assertEqual(result.filtered_data["products"][0]["id"], "p3")
        self.assertEqual(result.filtered_data["products"][0]["name"], "Headphones")
    
    async def test_filter_with_value_path_in_nested_structures(self):
        """
        Test filtering using value paths within complex nested structures.
        
        This test verifies that value paths can navigate complex nested data structures
        and correctly extract comparison values.
        """
        # Create test data with deeply nested reference values
        test_data = {
            "settings": {
                "filters": {
                    "user": {
                        "permissions": {
                            "minimum_level": 3,
                            "required_roles": ["admin", "editor"]
                        }
                    },
                    "content": {
                        "visibility": {
                            "public_only": True
                        }
                    }
                }
            },
            "users": [
                {
                    "id": "u1",
                    "name": "Admin User",
                    "access": {
                        "level": 5,
                        "roles": ["admin", "viewer"]
                    }
                },
                {
                    "id": "u2",
                    "name": "Basic User",
                    "access": {
                        "level": 1,
                        "roles": ["viewer"]
                    }
                },
                {
                    "id": "u3",
                    "name": "Editor",
                    "access": {
                        "level": 3,
                        "roles": ["editor", "viewer"]
                    }
                }
            ],
            "content_items": [
                {
                    "id": "c1",
                    "title": "Public Article",
                    "visibility": "public"
                },
                {
                    "id": "c2",
                    "title": "Internal Document",
                    "visibility": "private"
                },
                {
                    "id": "c3",
                    "title": "Draft Post",
                    "visibility": "draft"
                }
            ]
        }
        
        # Config to:
        # 1. Filter users based on access level from nested settings
        # 2. Filter content based on visibility setting
        config = {
            "targets": [
                # Filter users based on nested access level threshold
                {
                    "filter_target": "users",
                    "condition_groups": [{
                        "conditions": [{
                            "field": "users.access.level",
                            "operator": "greater_than_or_equals",
                            "value_path": "settings.filters.user.permissions.minimum_level"
                        }]
                    }],
                    "filter_mode": "allow"
                },
                # Filter content based on deep nested visibility setting
                {
                    "filter_target": "content_items",
                    "condition_groups": [{
                        "conditions": [{
                            "field": "content_items.visibility",
                            "operator": "equals",
                            "value": "public"
                        }]
                    }],
                    "filter_mode": "allow"
                }
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="nested_path_filter", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected results after filtering
        expected_users = [
            {
                "id": "u1",
                "name": "Admin User",
                "access": {
                    "level": 5,
                    "roles": ["admin", "viewer"]
                }
            },
            {
                "id": "u3",
                "name": "Editor",
                "access": {
                    "level": 3,
                    "roles": ["editor", "viewer"]
                }
            }
        ]
        
        expected_content = [
            {
                "id": "c1",
                "title": "Public Article",
                "visibility": "public"
            }
        ]
        
        # Verify results
        self.assertEqual(len(result.filtered_data["users"]), 2)
        self.assertEqual(result.filtered_data["users"], expected_users)
        self.assertEqual(len(result.filtered_data["content_items"]), 1)
        self.assertEqual(result.filtered_data["content_items"], expected_content)

    async def test_filter_with_nonexistent_value_path(self):
        """
        Test filtering when the specified value_path doesn't exist in the data.
        
        This test verifies the behavior when a value_path points to a non-existent location.
        """
        # Create simple test data
        test_data = {
            "items": [
                {"id": 1, "name": "Item 1", "price": 10.0},
                {"id": 2, "name": "Item 2", "price": 20.0},
                {"id": 3, "name": "Item 3", "price": 30.0}
            ],
            "config": {
                "visible": True
            }
        }
        
        # Config with a non-existent value path
        config = {
            "targets": [
                {
                    "filter_target": "items",
                    "condition_groups": [{
                        "conditions": [{
                            "field": "items.price",
                            "operator": "greater_than",
                            "value_path": "thresholds.min_price"  # This path doesn't exist
                        }]
                    }],
                    "filter_mode": "allow"
                }
            ]
        }
        
        # Create and process the node
        node = FilterNode(config=config, node_id="nonexistent_path_filter", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Since value_path doesn't exist, no items should pass the filter
        self.assertEqual(len(result.filtered_data["items"]), 0)
        self.assertEqual(result.filtered_data["items"], [])
        
        # The rest of the data should be preserved
        self.assertEqual(result.filtered_data["config"], {"visible": True})

# === IfElseNode Tests using unittest ===
class TestIfElseNodeUnittest(BaseNodeTest):

    # --- Basic Tests ---
    async def test_ifelse_single_tag_pass(self):
        config = {"tagged_conditions": [{"tag": "check1", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": True}]}]}]}
        node = IfElseConditionNode(config=config, node_id="ifelse1", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        self.assertEqual(result.tag_results, {"check1": True}); self.assertTrue(result.condition_result); self.assertEqual(result.branch, BranchPath.TRUE_BRANCH); self.assertEqual(result.data, input_data_dict)

    async def test_ifelse_single_tag_fail(self):
        config = {"tagged_conditions": [{"tag": "check1", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": False}]}]}]}
        node = IfElseConditionNode(config=config, node_id="ifelse2", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        self.assertEqual(result.tag_results, {"check1": False}); self.assertFalse(result.condition_result); self.assertEqual(result.branch, BranchPath.FALSE_BRANCH)

    # --- Multi-Tag Logic ---
    async def test_ifelse_multi_tag_and_pass(self):
        config = {"tagged_conditions": [ {"tag": "flag", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": True}]}]}, {"tag": "user", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "equals", "value": "Alice"}]}]}], "branch_logic_operator": "and"}
        node = IfElseConditionNode(config=config, node_id="ifelse3", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        self.assertEqual(result.tag_results, {"flag": True, "user": True}); self.assertTrue(result.condition_result); self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)

    async def test_ifelse_multi_tag_and_fail(self):
        config = {"tagged_conditions": [ {"tag": "flag", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": True}]}]}, {"tag": "user", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "equals", "value": "Bob"}]}]}], "branch_logic_operator": "and"}
        node = IfElseConditionNode(config=config, node_id="ifelse4", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        self.assertEqual(result.tag_results, {"flag": True, "user": False}); self.assertFalse(result.condition_result); self.assertEqual(result.branch, BranchPath.FALSE_BRANCH)

    async def test_ifelse_multi_tag_or_pass(self):
        config = {"tagged_conditions": [ {"tag": "flag", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": False}]}]}, {"tag": "user", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "equals", "value": "Alice"}]}]}], "branch_logic_operator": "or"}
        node = IfElseConditionNode(config=config, node_id="ifelse5", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        self.assertEqual(result.tag_results, {"flag": False, "user": True}); self.assertTrue(result.condition_result); self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)

    async def test_ifelse_multi_tag_or_fail(self):
        config = {"tagged_conditions": [ {"tag": "flag", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": False}]}]}, {"tag": "user", "condition_groups": [{"conditions": [{"field": "user.name", "operator": "equals", "value": "Bob"}]}]}], "branch_logic_operator": "or"}
        node = IfElseConditionNode(config=config, node_id="ifelse6", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        self.assertEqual(result.tag_results, {"flag": False, "user": False}); self.assertFalse(result.condition_result); self.assertEqual(result.branch, BranchPath.FALSE_BRANCH)

    # --- Nested List Evaluation ---
    async def test_ifelse_nested_list_cond_eval(self):
        # Config: Tag=True if OR(orders value) > 200
        config = {"tagged_conditions": [{"tag": "order_check", "condition_groups": [{"conditions": [{"field": "orders.value", "operator": "greater_than", "value": 200}]}], "nested_list_logical_operator": "or"}], "branch_logic_operator": "and"}
        node = IfElseConditionNode(config=config, node_id="ifelse7", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        # Should be True because order id=3 has value 210
        self.assertEqual(result.tag_results, {"order_check": True})
        self.assertTrue(result.condition_result)
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)

    # --- Validation and Passthrough ---
    async def test_config_validation_duplicate_tags(self):
        # Import Pydantic's specific validation error
        from pydantic import ValidationError

        cond_group = {"conditions": [{"field":"f","operator":"equals","value":1}]}
        config_dict = {"tagged_conditions": [ {"tag": "check1", "condition_groups": [cond_group]}, {"tag": "check1", "condition_groups": [cond_group]}]}
        # Catch the correct Pydantic error type
        with self.assertRaises(ValidationError) as cm:
            IfElseConfigSchema(**config_dict)
        # Check if the error message contains the expected text
        self.assertIn("Duplicate tag found: 'check1'", str(cm.exception))

    async def test_ifelse_data_passthrough(self):
        config = {"tagged_conditions": [{"tag": "t1", "condition_groups": [{"conditions": [{"field": "global_flag", "operator": "equals", "value": True}]}]}]}
        node = IfElseConditionNode(config=config, node_id="ifelse8", prefect_mode=False)
        input_data_dict = self.sample_data_user_orders.copy(); result = await node.process(input_data_dict)
        self.assertEqual(result.data, input_data_dict) # Compare dict directly
    

    # --- Complex Nested Structure Tests ---
    async def test_ifelse_complex_nested_dict(self):
        """
        Test IfElseNode with complex nested dictionary structures.
        This test demonstrates how to:
        1. Evaluate conditions on deeply nested fields
        2. Use multiple condition groups with different logical operators
        """
        # Create test data with complex nested structure
        test_data = {
            "customer": {
                "profile": {
                    "personal": {
                        "name": "Jane Smith",
                        "age": 28,
                        "contact": {
                            "email": "jane@example.com",
                            "phone": "555-1234"
                        }
                    },
                    "preferences": {
                        "notifications": {
                            "email": True,
                            "sms": False
                        },
                        "theme": "dark"
                    }
                },
                "subscription": {
                    "plan": "premium",
                    "status": "active",
                    "payment": {
                        "method": "credit_card",
                        "details": {
                            "last_four": "1234",
                            "expiry": "12/25"
                        }
                    }
                }
            },
            "analytics": {
                "visits": 42,
                "conversion": {
                    "rate": 0.15,
                    "source": "organic"
                }
            }
        }
        
        # Config with multiple condition groups checking deeply nested fields
        config = {
            "tagged_conditions": [
                {
                    "tag": "premium_user",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "customer.subscription.plan", "operator": "equals", "value": "premium"},
                                {"field": "customer.subscription.status", "operator": "equals", "value": "active"}
                            ],
                            "logical_operator": "and"
                        }
                    ]
                },
                {
                    "tag": "engaged_user",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "analytics.visits", "operator": "greater_than", "value": 30},
                                {"field": "customer.profile.preferences.notifications.email", "operator": "equals", "value": True}
                            ],
                            "logical_operator": "and"
                        }
                    ]
                },
                {
                    "tag": "payment_method",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "customer.subscription.payment.method", "operator": "equals", "value": "credit_card"}
                            ]
                        }
                    ]
                }
            ],
            "branch_logic_operator": "and"
        }
        
        # Create and process the node
        node = IfElseConditionNode(config=config, node_id="complex_nested", prefect_mode=False)
        result = await node.process(test_data)
        
        # All conditions should pass
        expected_tags = {
            "premium_user": True,
            "engaged_user": True,
            "payment_method": True
        }
        
        # Verify results
        self.assertEqual(result.tag_results, expected_tags)
        self.assertTrue(result.condition_result)
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)
        
        # Test with modified data that should fail
        modified_data = copy.deepcopy(test_data)
        modified_data["customer"]["subscription"]["status"] = "suspended"
        modified_data["analytics"]["visits"] = 25
        
        result2 = await node.process(modified_data)
        expected_tags2 = {
            "premium_user": False,  # Status is no longer active
            "engaged_user": False,  # Visits below threshold
            "payment_method": True  # Still using credit card
        }
        
        self.assertEqual(result2.tag_results, expected_tags2)
        self.assertFalse(result2.condition_result)
        self.assertEqual(result2.branch, BranchPath.FALSE_BRANCH)

    async def test_ifelse_nested_lists_complex(self):
        """
        Test IfElseNode with complex nested list structures.
        This test demonstrates how to:
        1. Evaluate conditions on fields within nested lists
        2. Use different nested list logical operators
        3. Combine multiple conditions across different levels of nesting
        """
        # Create test data with nested lists
        test_data = {
            "organization": {
                "name": "Acme Corp",
                "departments": [
                    {
                        "name": "Engineering",
                        "budget": 500000,
                        "teams": [
                            {
                                "name": "Frontend",
                                "members": [
                                    {"id": 101, "name": "Alice", "level": "senior", "skills": ["javascript", "react", "css"]},
                                    {"id": 102, "name": "Bob", "level": "mid", "skills": ["javascript", "angular"]}
                                ],
                                "projects": [
                                    {"name": "Website Redesign", "status": "in_progress", "priority": "high"},
                                    {"name": "Mobile App", "status": "planning", "priority": "medium"}
                                ]
                            },
                            {
                                "name": "Backend",
                                "members": [
                                    {"id": 201, "name": "Charlie", "level": "senior", "skills": ["python", "django", "sql"]},
                                    {"id": 202, "name": "Diana", "level": "senior", "skills": ["java", "spring", "kafka"]}
                                ],
                                "projects": [
                                    {"name": "API Refactor", "status": "in_progress", "priority": "critical"},
                                    {"name": "Database Migration", "status": "completed", "priority": "high"}
                                ]
                            }
                        ]
                    },
                    {
                        "name": "Marketing",
                        "budget": 300000,
                        "teams": [
                            {
                                "name": "Digital",
                                "members": [
                                    {"id": 301, "name": "Eve", "level": "mid", "skills": ["seo", "analytics"]},
                                    {"id": 302, "name": "Frank", "level": "junior", "skills": ["social media", "content"]}
                                ],
                                "projects": [
                                    {"name": "Q4 Campaign", "status": "in_progress", "priority": "high"}
                                ]
                            }
                        ]
                    }
                ]
            },
            "fiscal_year": 2023,
            "quarter": "Q3"
        }
        
        # Config to check for critical projects and senior engineers
        config = {
            "tagged_conditions": [
                {
                    "tag": "has_critical_projects",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "organization.departments.teams.projects.priority", "operator": "equals", "value": "critical"}
                            ]
                        }
                    ],
                    "nested_list_logical_operator": "or"
                },
                {
                    "tag": "senior_heavy",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "organization.departments.teams.members.level", "operator": "equals", "value": "senior"}
                            ]
                        }
                    ],
                    "nested_list_logical_operator": "or"
                },
                {
                    "tag": "high_budget_department",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "organization.departments.budget", "operator": "greater_than", "value": 400000}
                            ]
                        }
                    ],
                    "nested_list_logical_operator": "or"
                }
            ],
            "branch_logic_operator": "and"
        }
        
        # Create and process the node
        node = IfElseConditionNode(config=config, node_id="nested_lists_complex", prefect_mode=False)
        result = await node.process(test_data)
        
        # All conditions should pass
        expected_tags = {
            "has_critical_projects": True,  # Backend team has a critical project
            "senior_heavy": True,           # There are senior engineers
            "high_budget_department": True  # Engineering has budget > 400000
        }
        
        # Verify results
        self.assertEqual(result.tag_results, expected_tags)
        self.assertTrue(result.condition_result)
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)
        
        # Test with modified data that should fail one condition
        modified_data = copy.deepcopy(test_data)
        # Change all project priorities
        for dept in modified_data["organization"]["departments"]:
            for team in dept["teams"]:
                for project in team["projects"]:
                    project["priority"] = "medium"
        
        result2 = await node.process(modified_data)
        expected_tags2 = {
            "has_critical_projects": False,  # No more critical projects
            "senior_heavy": True,            # Still have senior engineers
            "high_budget_department": True   # Budget still high
        }
        
        self.assertEqual(result2.tag_results, expected_tags2)
        self.assertFalse(result2.condition_result)  # AND logic means one false makes all false
        self.assertEqual(result2.branch, BranchPath.FALSE_BRANCH)

    async def test_ifelse_mixed_nested_structures(self):
        """
        Test IfElseNode with a mix of nested dictionaries and lists with complex conditions.
        This test demonstrates how to:
        1. Combine conditions across different types of nested structures
        2. Use OR logic between condition groups
        3. Test complex real-world data scenarios
        """
        # Create test data with mixed nested structures
        test_data = {
            "user": {
                "id": "U123",
                "name": "John Doe",
                "account": {
                    "type": "business",
                    "tier": "enterprise",
                    "features": {
                        "api_access": True,
                        "white_labeling": True,
                        "support_level": "premium"
                    }
                }
            },
            "transactions": [
                {
                    "id": "T001",
                    "amount": 5000.00,
                    "currency": "USD",
                    "status": "completed",
                    "date": "2023-09-15",
                    "items": [
                        {"sku": "PRO-1", "quantity": 2, "price": 2000.00},
                        {"sku": "SRV-3", "quantity": 1, "price": 1000.00}
                    ]
                },
                {
                    "id": "T002",
                    "amount": 750.00,
                    "currency": "USD",
                    "status": "pending",
                    "date": "2023-09-20",
                    "items": [
                        {"sku": "SRV-2", "quantity": 3, "price": 250.00}
                    ]
                }
            ],
            "activity_log": [
                {"type": "login", "timestamp": "2023-09-21T08:30:00Z", "ip": "192.168.1.1"},
                {"type": "api_call", "timestamp": "2023-09-21T09:15:00Z", "endpoint": "/data/export"},
                {"type": "settings_change", "timestamp": "2023-09-21T10:45:00Z", "field": "notification_preferences"}
            ],
            "system": {
                "environment": "production",
                "version": "2.5.1",
                "flags": {
                    "beta_features": False,
                    "maintenance_mode": False
                }
            }
        }
        
        # Config with multiple condition groups using OR logic
        config = {
            "tagged_conditions": [
                {
                    "tag": "enterprise_customer",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "user.account.tier", "operator": "equals", "value": "enterprise"},
                                {"field": "user.account.features.support_level", "operator": "equals", "value": "premium"}
                            ],
                            "logical_operator": "and"
                        }
                    ]
                },
                {
                    "tag": "high_value_transactions",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "transactions.amount", "operator": "greater_than", "value": 1000.00}
                            ]
                        }
                    ],
                    "nested_list_logical_operator": "or"
                },
                {
                    "tag": "api_user",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "activity_log.type", "operator": "equals", "value": "api_call"}
                            ]
                        }
                    ],
                    "nested_list_logical_operator": "or"
                }
            ],
            "branch_logic_operator": "or"  # Using OR between tags
        }
        
        # Create and process the node
        node = IfElseConditionNode(config=config, node_id="mixed_nested", prefect_mode=False)
        result = await node.process(test_data)
        
        # All conditions should pass
        expected_tags = {
            "enterprise_customer": True,
            "high_value_transactions": True,
            "api_user": True
        }
        
        # Verify results
        self.assertEqual(result.tag_results, expected_tags)
        self.assertTrue(result.condition_result)
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)
        
        # Test with modified data where only one condition passes
        modified_data = copy.deepcopy(test_data)
        # Change account tier
        modified_data["user"]["account"]["tier"] = "standard"
        # Change transaction amounts
        for transaction in modified_data["transactions"]:
            transaction["amount"] = 500.00
        
        result2 = await node.process(modified_data)
        expected_tags2 = {
            "enterprise_customer": False,
            "high_value_transactions": False,
            "api_user": True  # This one still passes
        }
        
        self.assertEqual(result2.tag_results, expected_tags2)
        self.assertTrue(result2.condition_result)  # OR logic means one true makes all true
        self.assertEqual(result2.branch, BranchPath.TRUE_BRANCH)
        
        # Test with all conditions failing
        modified_data2 = copy.deepcopy(modified_data)
        # Remove api_call activity
        modified_data2["activity_log"] = [log for log in modified_data2["activity_log"] if log["type"] != "api_call"]
        
        result3 = await node.process(modified_data2)
        expected_tags3 = {
            "enterprise_customer": False,
            "high_value_transactions": False,
            "api_user": False
        }
        
        self.assertEqual(result3.tag_results, expected_tags3)
        self.assertFalse(result3.condition_result)
        self.assertEqual(result3.branch, BranchPath.FALSE_BRANCH)
    async def test_ifelse_with_all_nonexistent_and_some_existing_fields(self):
        """
        Test IfElseNode with conditions referencing fields that don't exist.
        This demonstrates how to:
        1. Handle gracefully when referenced fields don't exist
        2. Test behavior with missing fields in different operators
        """
        # Create test data with some fields but missing others
        test_data = {
            "user": {
                "name": "Alice Smith",
                "email": "alice@example.com"
                # Note: 'role' and 'permissions' fields are missing
            },
            "account": {
                "status": "active"
                # Note: 'subscription' field is missing
            }
        }
        
        # Config with conditions on both existing and non-existing fields
        config = {
            "tagged_conditions": [
                {
                    "tag": "admin_check",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "user.role", "operator": "equals", "value": "admin"},  # Non-existent field
                                {"field": "user.name", "operator": "is_not_empty", "value": None}  # Existing field
                            ],
                            "logical_operator": "and"
                        }
                    ]
                },
                {
                    "tag": "subscription_check",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "account.subscription.plan", "operator": "equals", "value": "premium"}  # Deeply nested non-existent field
                            ]
                        }
                    ]
                },
                {
                    "tag": "active_user",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "account.status", "operator": "equals", "value": "active"}  # Existing field
                            ]
                        }
                    ]
                }
            ],
            "branch_logic_operator": "or"  # Any true condition will make the overall result true
        }
        
        # Create and process the node
        node = IfElseConditionNode(config=config, node_id="nonexistent_fields", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected results:
        # - admin_check: False (non-existent field evaluates to false in AND with true)
        # - subscription_check: False (non-existent nested field)
        # - active_user: True (existing field with matching value)
        expected_tags = {
            "admin_check": False,
            "subscription_check": False,
            "active_user": True
        }
        
        # Verify results
        self.assertEqual(result.tag_results, expected_tags)
        self.assertTrue(result.condition_result)  # OR logic means one true makes all true
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)
        
        # Test with all conditions on non-existent fields
        config_all_nonexistent = {
            "tagged_conditions": [
                {
                    "tag": "missing_fields",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "user.role", "operator": "equals", "value": "admin"},
                                {"field": "user.permissions.admin", "operator": "equals", "value": True}
                            ],
                            "logical_operator": "or"  # Even with OR, both false = false
                        }
                    ]
                }
            ]
        }
        
        node2 = IfElseConditionNode(config=config_all_nonexistent, node_id="all_nonexistent", prefect_mode=False)
        result2 = await node2.process(test_data)
        
        self.assertEqual(result2.tag_results, {"missing_fields": False})
        self.assertFalse(result2.condition_result)
        self.assertEqual(result2.branch, BranchPath.FALSE_BRANCH)

        # Test with all conditions on non-existent fields
        config_some_nonexistent = {
            "tagged_conditions": [
                {
                    "tag": "some_missing_fields",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "account.status", "operator": "equals", "value": "active"},
                                {"field": "user.role", "operator": "equals", "value": "admin"},
                                {"field": "user.permissions.admin", "operator": "equals", "value": True}
                            ],
                            "logical_operator": "or"  # Even with OR, both false = false and true
                        }
                    ]
                }
            ]
        }
        
        node2 = IfElseConditionNode(config=config_some_nonexistent, node_id="some_nonexistent", prefect_mode=False)
        result2 = await node2.process(test_data)
        
        self.assertEqual(result2.tag_results, {"some_missing_fields": True})
        self.assertTrue(result2.condition_result)
        self.assertEqual(result2.branch, BranchPath.TRUE_BRANCH)

        # Test with all conditions on non-existent fields
        config_some_nonexistent = {
            "tagged_conditions": [
                {
                    "tag": "some_nonexistent",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "user.role", "operator": "equals", "value": "admin"},
                                {"field": "user.permissions.admin", "operator": "equals", "value": True}
                            ],
                            "logical_operator": "and"  # Even with AND, both false = false
                        }
                    ]
                }
            ]
        }
        
        node2 = IfElseConditionNode(config=config_some_nonexistent, node_id="some_nonexistent", prefect_mode=False)
        result2 = await node2.process(test_data)
        
        self.assertEqual(result2.tag_results, {"some_nonexistent": False})
        self.assertFalse(result2.condition_result)
        self.assertEqual(result2.branch, BranchPath.FALSE_BRANCH)
    
    async def test_ifelse_complex_operators_on_lists(self):
        """
        Test IfElseNode with complex operators on nested lists.
        This demonstrates how to:
        1. Use different operators on list items
        2. Combine AND/OR logic across nested list evaluations
        3. Test with various comparison operators
        """
        # Create test data with nested lists
        test_data = {
            "products": [
                {"id": "P1", "category": "electronics", "price": 1200.00, "stock": 5, "tags": ["premium", "new"]},
                {"id": "P2", "category": "electronics", "price": 800.00, "stock": 15, "tags": ["sale", "popular"]},
                {"id": "P3", "category": "books", "price": 25.00, "stock": 100, "tags": ["bestseller"]},
                {"id": "P4", "category": "clothing", "price": 49.99, "stock": 30, "tags": ["seasonal", "sale"]}
            ],
            "store": {
                "name": "SuperStore",
                "locations": [
                    {"id": "L1", "city": "New York", "employees": 50, "size": "large"},
                    {"id": "L2", "city": "Boston", "employees": 20, "size": "medium"},
                    {"id": "L3", "city": "Chicago", "employees": 35, "size": "large"}
                ]
            }
        }
        
        # Config with complex conditions on nested lists with different operators
        config = {
            "tagged_conditions": [
                {
                    "tag": "has_expensive_electronics",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "products.category", "operator": "equals", "value": "electronics"},
                                {"field": "products.price", "operator": "greater_than", "value": 1000.00}
                            ],
                            "logical_operator": "and"
                        }
                    ],
                    "nested_list_logical_operator": "or"  # ANY product matching both conditions
                },
                {
                    "tag": "all_products_in_stock",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "products.stock", "operator": "greater_than", "value": 0}
                            ]
                        }
                    ],
                    "nested_list_logical_operator": "and"  # ALL products must be in stock
                },
                {
                    "tag": "has_large_locations",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "store.locations.size", "operator": "equals", "value": "large"},
                                {"field": "store.locations.employees", "operator": "greater_than_or_equals", "value": 30}
                            ],
                            "logical_operator": "and"
                        }
                    ],
                    "nested_list_logical_operator": "or"  # ANY location matching both conditions
                },
                {
                    "tag": "has_sale_items",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "products.tags", "operator": "contains", "value": "sale"}
                            ]
                        }
                    ],
                    "nested_list_logical_operator": "or"  # ANY product with "sale" tag
                }
            ],
            "branch_logic_operator": "and"  # ALL tagged conditions must be true
        }
        
        # Create and process the node
        node = IfElseConditionNode(config=config, node_id="complex_list_operators", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected results:
        # - has_expensive_electronics: True (P1 matches)
        # - all_products_in_stock: True (all have stock > 0)
        # - has_large_locations: True (L1 and L3 match)
        # - has_sale_items: True (P2 and P4 have "sale" tag)
        expected_tags = {
            "has_expensive_electronics": True,
            "all_products_in_stock": True,
            "has_large_locations": True,
            "has_sale_items": True
        }
        
        # Verify results
        self.assertEqual(result.tag_results, expected_tags)
        self.assertTrue(result.condition_result)
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)
        
        # Test with modified data where some conditions fail
        modified_data = copy.deepcopy(test_data)
        # Make one product out of stock
        modified_data["products"][0]["stock"] = 0
        # Remove all large locations
        for location in modified_data["store"]["locations"]:
            if location["size"] == "large":
                location["size"] = "medium"
        
        result2 = await node.process(modified_data)
        expected_tags2 = {
            "has_expensive_electronics": True,  # Still true
            "all_products_in_stock": False,     # Now false (one product has 0 stock)
            "has_large_locations": False,       # Now false (no large locations)
            "has_sale_items": True              # Still true
        }
        
        self.assertEqual(result2.tag_results, expected_tags2)
        self.assertFalse(result2.condition_result)  # AND logic means one false makes all false
        self.assertEqual(result2.branch, BranchPath.FALSE_BRANCH)
    
    async def test_ifelse_mixed_logical_operators(self):
        """
        Test IfElseNode with mixed logical operators in different condition groups.
        This demonstrates how to:
        1. Use different logical operators in different condition groups
        2. Test complex combinations of AND/OR logic
        3. Handle conditions with various operators on the same data
        """
        # Create test data
        test_data = {
            "order": {
                "id": "ORD-12345",
                "customer_type": "business",
                "total": 1500.00,
                "items": 8,
                "status": "processing",
                "payment": {
                    "method": "credit_card",
                    "verified": True
                },
                "shipping": {
                    "method": "express",
                    "address": {
                        "country": "USA",
                        "state": "CA"
                    }
                }
            },
            "flags": {
                "priority": True,
                "international": False,
                "tax_exempt": True
            }
        }
        
        # Config with mixed logical operators in different condition groups
        config = {
            "tagged_conditions": [
                {
                    "tag": "high_value_business_order",
                    "condition_groups": [
                        # First group: Must be business AND high value
                        {
                            "conditions": [
                                {"field": "order.customer_type", "operator": "equals", "value": "business"},
                                {"field": "order.total", "operator": "greater_than", "value": 1000.00}
                            ],
                            "logical_operator": "and"
                        },
                        # Second group: OR must be priority with express shipping
                        {
                            "conditions": [
                                {"field": "flags.priority", "operator": "equals", "value": True},
                                {"field": "order.shipping.method", "operator": "equals", "value": "express"}
                            ],
                            "logical_operator": "or"
                        }
                    ],
                    "group_logical_operator": "or"  # Either group can make this tag true
                },
                {
                    "tag": "special_handling",
                    "condition_groups": [
                        # First group: International orders
                        {
                            "conditions": [
                                {"field": "flags.international", "operator": "equals", "value": True}
                            ]
                        },
                        # Second group: Large orders (many items)
                        {
                            "conditions": [
                                {"field": "order.items", "operator": "greater_than", "value": 5}
                            ]
                        },
                        # Third group: Very high value orders
                        {
                            "conditions": [
                                {"field": "order.total", "operator": "greater_than", "value": 2000.00}
                            ]
                        }
                    ],
                    "group_logical_operator": "or"  # Any group can make this tag true
                },
                {
                    "tag": "tax_compliance",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "flags.tax_exempt", "operator": "equals", "value": True},
                                {"field": "order.customer_type", "operator": "equals", "value": "business"}
                            ],
                            "logical_operator": "and"  # Both conditions must be true
                        }
                    ]
                }
            ],
            "branch_logic_operator": "and"  # All tagged conditions must be true
        }
        
        # Create and process the node
        node = IfElseConditionNode(config=config, node_id="mixed_operators", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected results:
        # - high_value_business_order: True (matches both condition groups)
        # - special_handling: True (matches second group - items > 5)
        # - tax_compliance: True (tax_exempt and business customer)
        expected_tags = {
            "high_value_business_order": True,
            "special_handling": True,
            "tax_compliance": True
        }
        
        # Verify results
        self.assertEqual(result.tag_results, expected_tags)
        self.assertTrue(result.condition_result)
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)
        
        # Test with modified data where some conditions fail
        modified_data = copy.deepcopy(test_data)
        modified_data["order"]["customer_type"] = "individual"
        modified_data["order"]["items"] = 3
        modified_data["flags"]["priority"] = False
        
        result2 = await node.process(modified_data)
        expected_tags2 = {
            "high_value_business_order": True,  # Still true because of express shipping
            "special_handling": False,          # Now false (not international, items <= 5, total <= 2000)
            "tax_compliance": False             # Now false (not a business customer)
        }
        
        self.assertEqual(result2.tag_results, expected_tags2)
        self.assertFalse(result2.condition_result)  # AND logic means one false makes all false
        self.assertEqual(result2.branch, BranchPath.FALSE_BRANCH)
    async def test_ifelse_with_contains_operator(self):
        """
        Test IfElseNode with the CONTAINS operator.
        This demonstrates how to:
        1. Use the contains operator with strings
        2. Use the contains operator with lists
        3. Test both positive and negative cases
        """
        # Create test data with strings and lists
        test_data = {
            "product": {
                "name": "Premium Smartphone XL",
                "description": "Latest model with advanced features",
                "categories": ["electronics", "mobile", "premium"],
                "tags": ["new", "featured", "sale"]
            },
            "customer": {
                "search_history": ["laptop", "smartphone", "headphones"],
                "preferences": "dark mode, notifications enabled, auto-updates"
            }
        }
        
        # Config with contains conditions on different field types
        config = {
            "tagged_conditions": [
                {
                    "tag": "premium_product",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "product.name", "operator": "contains", "value": "Premium"},
                                {"field": "product.categories", "operator": "contains", "value": "premium"}
                            ],
                            "logical_operator": "and"
                        }
                    ]
                },
                {
                    "tag": "customer_interested_in_smartphones",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "customer.search_history", "operator": "contains", "value": "smartphone"}
                            ]
                        }
                    ]
                },
                {
                    "tag": "notifications_enabled",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "customer.preferences", "operator": "contains", "value": "notifications enabled"}
                            ]
                        }
                    ]
                }
            ],
            "branch_logic_operator": "and"  # All tagged conditions must be true
        }
        
        # Create and process the node
        node = IfElseConditionNode(config=config, node_id="contains_operator", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected results - all conditions should pass
        expected_tags = {
            "premium_product": True,
            "customer_interested_in_smartphones": True,
            "notifications_enabled": True
        }
        
        # Verify results
        self.assertEqual(result.tag_results, expected_tags)
        self.assertTrue(result.condition_result)
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)
        
        # Test with modified data where some conditions fail
        modified_data = copy.deepcopy(test_data)
        modified_data["product"]["name"] = "Standard Smartphone"
        modified_data["customer"]["preferences"] = "light mode, notifications disabled"
        
        result2 = await node.process(modified_data)
        expected_tags2 = {
            "premium_product": False,  # Name no longer contains "Premium"
            "customer_interested_in_smartphones": True,  # This still passes
            "notifications_enabled": False  # Preferences changed
        }
        
        self.assertEqual(result2.tag_results, expected_tags2)
        self.assertFalse(result2.condition_result)  # AND logic means one false makes all false
        self.assertEqual(result2.branch, BranchPath.FALSE_BRANCH)

    async def test_ifelse_with_not_contains_operator(self):
        """
        Test IfElseNode with the NOT_CONTAINS operator.
        This demonstrates how to:
        1. Use the not_contains operator with strings and lists
        2. Combine not_contains with other operators
        """
        # Create test data
        test_data = {
            "document": {
                "title": "Confidential Report",
                "content": "This document contains sensitive information.",
                "metadata": {
                    "tags": ["internal", "confidential", "quarterly"],
                    "access_level": "restricted"
                }
            },
            "user": {
                "roles": ["viewer", "editor"],
                "departments": ["marketing", "research"]
            }
        }
        
        # Config with not_contains conditions
        config = {
            "tagged_conditions": [
                {
                    "tag": "public_document",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "document.content", "operator": "not_contains", "value": "sensitive"},
                                {"field": "document.metadata.tags", "operator": "not_contains", "value": "confidential"}
                            ],
                            "logical_operator": "and"
                        }
                    ]
                },
                {
                    "tag": "admin_user",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "user.roles", "operator": "not_contains", "value": "admin"}
                            ]
                        }
                    ]
                }
            ],
            "branch_logic_operator": "or"  # Any tagged condition can be true
        }
        
        # Create and process the node
        node = IfElseConditionNode(config=config, node_id="not_contains_operator", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected results
        expected_tags = {
            "public_document": False,  # Document contains "sensitive" and has "confidential" tag
            "admin_user": True         # User does not have "admin" role
        }
        
        # Verify results
        self.assertEqual(result.tag_results, expected_tags)
        self.assertTrue(result.condition_result)  # OR logic means one true makes all true
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)
        
        # Test with modified data where all conditions fail
        modified_data = copy.deepcopy(test_data)
        modified_data["user"]["roles"].append("admin")
        
        result2 = await node.process(modified_data)
        expected_tags2 = {
            "public_document": False,  # Still false
            "admin_user": False        # Now false because user has admin role
        }
        
        self.assertEqual(result2.tag_results, expected_tags2)
        self.assertFalse(result2.condition_result)
        self.assertEqual(result2.branch, BranchPath.FALSE_BRANCH)

    async def test_ifelse_with_starts_with_ends_with_operators(self):
        """
        Test IfElseNode with the STARTS_WITH and ENDS_WITH operators.
        This demonstrates how to:
        1. Use string prefix and suffix matching
        2. Combine these operators with other conditions
        """
        # Create test data
        test_data = {
            "files": [
                {"name": "report_2023Q4.pdf", "path": "/documents/reports/", "size": 1024},
                {"name": "invoice_12345.docx", "path": "/documents/finance/", "size": 512},
                {"name": "image.jpg", "path": "/media/images/", "size": 2048}
            ],
            "email": {
                "subject": "RE: Project Update",
                "sender": "manager@company.com",
                "recipients": ["team@company.com", "client@external.org"]
            }
        }
        
        # Config with starts_with and ends_with conditions
        config = {
            "tagged_conditions": [
                {
                    "tag": "has_report",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "files.name", "operator": "starts_with", "value": "report_"}
                            ]
                        }
                    ],
                    "nested_list_logical_operator": "or"  # Any file can match
                },
                {
                    "tag": "has_pdf",
                    "condition_groups": [
                        {
                            "conditions": [
                                {"field": "files.name", "operator": "ends_with", "value": ".pdf"}
                            ]
                        }
                    ],
                    "nested_list_logical_operator": "or"  # Any file can match
                },
                {
                    "tag": "company_email",
                    "condition_groups": [
                        {
                            "conditions": [
                                {
                                    "field": "email.recipients", "operator": "ends_with", "value": "company.com",
                                    "apply_to_each_value_in_list_field": True,
                                    "list_field_logical_operator": LogicalOperator.OR,
                                }
                            ],
                        }
                    ],
                    "nested_list_logical_operator": "or"  # Any recipient can match
                }
            ],
            "branch_logic_operator": "and"  # All tagged conditions must be true
        }
        
        # Create and process the node
        node = IfElseConditionNode(config=config, node_id="string_prefix_suffix", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected results
        expected_tags = {
            "has_report": True,   # There is a file starting with "report_"
            "has_pdf": True,      # There is a file ending with ".pdf"
            "company_email": True  # There is a recipient ending with "company.com"
        }
        
        # Verify results
        self.assertEqual(result.tag_results, expected_tags)
        self.assertTrue(result.condition_result)
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)
        
        # Test with modified data where some conditions fail
        modified_data = copy.deepcopy(test_data)
        modified_data["files"] = [
            {"name": "data_analysis.xlsx", "path": "/documents/reports/", "size": 1024},
            {"name": "invoice_12345.docx", "path": "/documents/finance/", "size": 512}
        ]
        
        result2 = await node.process(modified_data)
        expected_tags2 = {
            "has_report": False,  # No file starts with "report_"
            "has_pdf": False,     # No file ends with ".pdf"
            "company_email": True  # Still has a recipient ending with "company.com"
        }
        
        self.assertEqual(result2.tag_results, expected_tags2)
        self.assertFalse(result2.condition_result)  # AND logic means one false makes all false
        self.assertEqual(result2.branch, BranchPath.FALSE_BRANCH)

    async def test_ifelse_with_value_path(self):
        """
        Test IfElseConditionNode with value_path to dynamically load comparison values.
        
        This test verifies that IfElseConditionNode can use field values from other parts
        of the input data for condition evaluation.
        """
        # Create test data with threshold values and comparison data
        test_data = {
            "user": {
                "id": 123,
                "name": "Test User",
                "age": 35,
                "account": {
                    "balance": 1500,
                    "type": "premium",
                    "status": "active"
                }
            },
            "app_config": {
                "thresholds": {
                    "premium_min_balance": 1000,
                    "premium_min_age": 25,
                    "required_status": "active"
                }
            },
            "feature_flags": {
                "enable_premium": True
            }
        }
        
        # Config to check if user qualifies for premium features based on dynamic values
        config = {
            "tagged_conditions": [
                {
                    "tag": "premium_eligible",
                    "condition_groups": [{
                        "conditions": [
                            {
                                "field": "user.account.balance",
                                "operator": "greater_than_or_equals",
                                "value_path": "app_config.thresholds.premium_min_balance"
                            },
                            {
                                "field": "user.age",
                                "operator": "greater_than_or_equals",
                                "value_path": "app_config.thresholds.premium_min_age"
                            },
                            {
                                "field": "user.account.status",
                                "operator": "equals",
                                "value_path": "app_config.thresholds.required_status"
                            }
                        ],
                        "logical_operator": "and"
                    }]
                },
                {
                    "tag": "feature_enabled",
                    "condition_groups": [{
                        "conditions": [{
                            "field": "feature_flags.enable_premium",
                            "operator": "equals",
                            "value": True
                        }]
                    }]
                }
            ],
            "branch_logic_operator": "and"
        }
        
        # Create and process the node
        node = IfElseConditionNode(config=config, node_id="premium_check", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: User meets all premium criteria and feature is enabled
        expected_tag_results = {
            "premium_eligible": True,
            "feature_enabled": True
        }
        
        # Verify all conditions passed and true branch was selected
        self.assertEqual(result.tag_results, expected_tag_results)
        self.assertTrue(result.condition_result)
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)
        
        # Modify the test data so user doesn't meet balance threshold
        test_data["user"]["account"]["balance"] = 500
        
        # Re-process with updated data
        result_2 = await node.process(test_data)
        
        # Expected: User doesn't meet all criteria
        expected_tag_results_2 = {
            "premium_eligible": False,
            "feature_enabled": True
        }
        
        # Verify premium_eligible failed and false branch was selected
        self.assertEqual(result_2.tag_results, expected_tag_results_2)
        self.assertFalse(result_2.condition_result)
        self.assertEqual(result_2.branch, BranchPath.FALSE_BRANCH)
    
    async def test_ifelse_with_nested_value_paths(self):
        """
        Test IfElseConditionNode with deeply nested value paths.
        
        This test verifies that the node can correctly navigate complex data structures
        to extract comparison values from deeply nested locations.
        """
        # Create test data with deeply nested configuration
        test_data = {
            "transaction": {
                "id": "tx123",
                "amount": 750.0,
                "currency": "USD",
                "type": "purchase",
                "user_id": "u456",
                "risk_score": 25
            },
            "security": {
                "settings": {
                    "risk": {
                        "thresholds": {
                            "high_value_transaction": 500.0,
                            "suspicious_score": 75,
                            "verification_required": True
                        }
                    },
                    "transaction_types": {
                        "require_review": ["withdrawal", "refund"]
                    }
                }
            },
            "user": {
                "id": "u456",
                "verified": True,
                "history": {
                    "transaction_count": 12,
                    "flags": []
                }
            }
        }
        
        # Config to check various security conditions using nested paths
        config = {
            "tagged_conditions": [
                {
                    "tag": "high_value",
                    "condition_groups": [{
                        "conditions": [{
                            "field": "transaction.amount",
                            "operator": "greater_than",
                            "value_path": "security.settings.risk.thresholds.high_value_transaction"
                        }]
                    }]
                },
                {
                    "tag": "requires_review",
                    "condition_groups": [{
                        "conditions": [{
                            "field": "transaction.type",
                            "operator": "equals_any_of",
                            "value_path": "security.settings.transaction_types.require_review"
                        }]
                    }]
                },
                {
                    "tag": "user_verified",
                    "condition_groups": [{
                        "conditions": [{
                            "field": "user.verified",
                            "operator": "equals",
                            "value": True
                        }]
                    }]
                }
            ],
            "branch_logic_operator": "and"
        }
        
        # Create and process the node
        node = IfElseConditionNode(config=config, node_id="security_check", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Transaction is high-value but doesn't require review and user is verified
        expected_tag_results = {
            "high_value": True,
            "requires_review": False,
            "user_verified": True
        }
        
        # Verify that the OR operation produces the expected result
        # Since we're using AND logic and requires_review is False, the overall result should be False
        self.assertEqual(result.tag_results, expected_tag_results)
        self.assertFalse(result.condition_result)
        self.assertEqual(result.branch, BranchPath.FALSE_BRANCH)
        
        # Change transaction type to one that requires review
        test_data["transaction"]["type"] = "withdrawal"
        
        # Re-process with updated data
        result_2 = await node.process(test_data)
        
        # Expected: Now all conditions are true
        expected_tag_results_2 = {
            "high_value": True,
            "requires_review": True,
            "user_verified": True
        }
        
        # Verify all conditions are now true
        self.assertEqual(result_2.tag_results, expected_tag_results_2)
        self.assertTrue(result_2.condition_result)
        self.assertEqual(result_2.branch, BranchPath.TRUE_BRANCH)
    
    async def test_ifelse_with_mixed_value_and_value_path(self):
        """
        Test IfElseConditionNode with a mix of static values and dynamic value paths.
        
        This test verifies that conditions can mix static values and dynamically loaded values
        from paths within the same configuration.
        """
        # Create test data
        test_data = {
            "order": {
                "id": "ord789",
                "total": 125.50,
                "items": 3,
                "status": "processing",
                "shipping_method": "standard"
            },
            "customer": {
                "id": "cust123",
                "tier": "silver",
                "preferences": {
                    "shipping": "express"
                }
            },
            "config": {
                "shipping": {
                    "free_threshold": 100.0,
                    "express_min_total": 75.0
                },
                "status_flow": ["pending", "processing", "shipped", "delivered"]
            }
        }
        
        # Config to check eligibility for shipping upgrade with mixed conditions
        config = {
            "tagged_conditions": [
                {
                    "tag": "eligible_for_upgrade",
                    "condition_groups": [{
                        "conditions": [
                            # Static value comparison
                            {
                                "field": "customer.tier",
                                "operator": "equals",
                                "value": "silver"
                            },
                            # Dynamic path comparison
                            {
                                "field": "order.total",
                                "operator": "greater_than_or_equals",
                                "value_path": "config.shipping.express_min_total"
                            },
                            # Another static comparison
                            {
                                "field": "order.shipping_method",
                                "operator": "equals",
                                "value": "standard"
                            }
                        ],
                        "logical_operator": "and"
                    }]
                },
                {
                    "tag": "prefers_express",
                    "condition_groups": [{
                        "conditions": [{
                            "field": "customer.preferences.shipping",
                            "operator": "equals",
                            "value": "express"
                        }]
                    }]
                }
            ],
            "branch_logic_operator": "and"
        }
        
        # Create and process the node
        node = IfElseConditionNode(config=config, node_id="shipping_upgrade", prefect_mode=False)
        result = await node.process(test_data)
        
        # Expected: Customer is eligible for upgrade and prefers express
        expected_tag_results = {
            "eligible_for_upgrade": True,
            "prefers_express": True
        }
        
        # Verify all conditions passed
        self.assertEqual(result.tag_results, expected_tag_results)
        self.assertTrue(result.condition_result)
        self.assertEqual(result.branch, BranchPath.TRUE_BRANCH)
        
        # Change customer tier to one that's not eligible
        test_data["customer"]["tier"] = "bronze"
        
        # Re-process with updated data
        result_2 = await node.process(test_data)
        
        # Expected: Customer is no longer eligible for upgrade
        expected_tag_results_2 = {
            "eligible_for_upgrade": False,
            "prefers_express": True
        }
        
        # Verify eligible_for_upgrade condition failed
        self.assertEqual(result_2.tag_results, expected_tag_results_2)
        self.assertFalse(result_2.condition_result)
        self.assertEqual(result_2.branch, BranchPath.FALSE_BRANCH)

# === unittest execution ===
if __name__ == '__main__':
    unittest.main()
