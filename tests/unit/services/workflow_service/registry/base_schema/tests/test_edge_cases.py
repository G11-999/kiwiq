"""
Tests for edge cases and complex scenarios in BaseSchema.

This module tests:
1. Complex type validations
2. Circular dependencies
3. Empty schemas
4. Optional fields
5. Field validators
6. Cache invalidation
7. Schema diffing edge cases
"""

import json
import unittest
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime
from copy import deepcopy

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from workflow_service.registry.schemas.base import BaseSchema

# Test Enums
class ComplexEnum(str, Enum):
    """Complex enum with special characters."""
    SPECIAL_CHARS = "!@#$%^&*()"
    SPACES = "with spaces"
    UNICODE = "üñîçødé"
    EMPTY = ""

# Test Schemas
class EmptySchema(BaseSchema):
    """Schema with no fields."""
    pass

class AllOptionalSchema(BaseSchema):
    """Schema with all optional fields."""
    str_field: Optional[str] = None
    int_field: Optional[int] = None
    bool_field: Optional[bool] = None
    enum_field: Optional[ComplexEnum] = None
    internal_field: SkipJsonSchema[Optional[str]] = None

class ValidatorSchema(BaseSchema):
    """Schema with field validators."""
    username: str = Field(..., min_length=3, max_length=50)
    age: int = Field(..., gt=0, lt=150)
    password: str
    confirm_password: str
    email: str = Field(..., pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

    @field_validator("age")
    def validate_age(cls, v: int) -> int:
        """Validate age is reasonable."""
        if v < 0:
            raise ValueError("Age cannot be negative")
        if v > 150:
            raise ValueError("Age cannot be greater than 150")
        return v

    @field_validator("confirm_password")
    def passwords_match(cls, v: str, info: Any) -> str:
        """Validate password confirmation matches."""
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v

    @field_validator("email")
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        if "@" not in v:
            raise ValueError("Invalid email format")
        return v

class CircularSchema(BaseSchema):
    """Schema with circular reference to itself."""
    name: str
    created_at: datetime
    parent: Optional["CircularSchema"] = None
    children: List["CircularSchema"] = []
    metadata: Dict[str, str] = {}

class ComplexTypesSchema(BaseSchema):
    """Schema with complex type combinations."""
    enum_list: List[ComplexEnum] = []
    str_dict: Dict[str, str] = {}
    int_dict: Dict[str, int] = {}
    enum_dict: Dict[str, ComplexEnum] = {}
    nested_list_dict: Dict[str, List[str]] = {}
    optional_enum_list: Optional[List[ComplexEnum]] = None
    optional_dict: Optional[Dict[str, str]] = None
    internal_dict: SkipJsonSchema[Dict[str, str]] = {}

class TestEdgeCases(unittest.TestCase):
    """Test cases for edge cases and complex scenarios."""

    def test_empty_schema(self):
        """Test schema with no fields."""
        # Test instantiation
        schema = EmptySchema()
        self.assertIsInstance(schema, EmptySchema)

        # Test schema generation
        db_schema = EmptySchema.get_schema_for_db()
        self.assertEqual(len(db_schema), 0)

        # Test user editable fields
        # editable = EmptySchema.get_user_editable_fields()
        # self.assertEqual(len(editable), 0)

    def test_all_optional_schema(self):
        """Test schema with all optional fields."""
        # Test with no fields provided
        schema = AllOptionalSchema()
        self.assertIsNone(schema.str_field)
        self.assertIsNone(schema.int_field)
        self.assertIsNone(schema.bool_field)
        self.assertIsNone(schema.enum_field)
        self.assertIsNone(schema.internal_field)

        # Test with all fields provided
        schema = AllOptionalSchema(
            str_field="test",
            int_field=42,
            bool_field=True,
            enum_field=ComplexEnum.UNICODE,
            internal_field="internal"
        )
        self.assertEqual(schema.str_field, "test")
        self.assertEqual(schema.int_field, 42)
        self.assertTrue(schema.bool_field)
        self.assertEqual(schema.enum_field, ComplexEnum.UNICODE)
        self.assertEqual(schema.internal_field, "internal")

        # # Test user editable fields
        # editable = AllOptionalSchema.get_user_editable_fields()
        # self.assertIn("str_field", editable)
        # self.assertIn("int_field", editable)
        # self.assertIn("bool_field", editable)
        # self.assertIn("enum_field", editable)
        # self.assertNotIn("internal_field", editable)

    def test_validator_schema(self):
        """Test schema with field validators."""
        # Test valid data
        schema = ValidatorSchema(
            username="testuser",
            age=25,
            password="password123",
            confirm_password="password123",
            email="test@example.com"
        )
        self.assertEqual(schema.username, "testuser")
        self.assertEqual(schema.age, 25)
        self.assertEqual(schema.password, "password123")
        self.assertEqual(schema.confirm_password, "password123")
        self.assertEqual(schema.email, "test@example.com")

        # Test invalid username
        with self.assertRaises(ValueError):
            ValidatorSchema(
                username="ab",  # Too short
                age=25,
                password="password123",
                confirm_password="password123",
                email="test@example.com"
            )

        # Test invalid age
        with self.assertRaises(ValueError):
            ValidatorSchema(
                username="testuser",
                age=-1,  # Negative age
                password="password123",
                confirm_password="password123",
                email="test@example.com"
            )

        # Test mismatched passwords
        with self.assertRaises(ValueError):
            ValidatorSchema(
                username="testuser",
                age=25,
                password="password123",
                confirm_password="different",  # Doesn't match
                email="test@example.com"
            )

        # Test invalid email
        with self.assertRaises(ValueError):
            ValidatorSchema(
                username="testuser",
                age=25,
                password="password123",
                confirm_password="password123",
                email="invalid-email"  # Invalid format
            )

    def test_circular_schema(self):
        """Test schema with circular references."""
        # Test simple instantiation
        schema = CircularSchema(
            name="root",
            created_at="2024-03-16T12:00:00"
        )
        self.assertEqual(schema.name, "root")
        self.assertIsNone(schema.parent)
        self.assertEqual(len(schema.children), 0)

        # Test nested structure
        child = CircularSchema(
            name="child",
            created_at="2024-03-16T12:00:00",
            parent=schema,
            metadata={"type": "child"}
        )
        schema.children.append(child)

        self.assertEqual(len(schema.children), 1)
        self.assertEqual(schema.children[0].name, "child")
        self.assertEqual(schema.children[0].parent, schema)
        self.assertEqual(schema.children[0].metadata, {"type": "child"})

        # Test deep nesting
        grandchild = CircularSchema(
            name="grandchild",
            created_at="2024-03-16T12:00:00",
            parent=child,
            metadata={"type": "grandchild"}
        )
        child.children.append(grandchild)

        self.assertEqual(len(child.children), 1)
        self.assertEqual(child.children[0].name, "grandchild")
        self.assertEqual(child.children[0].parent, child)
        self.assertEqual(child.children[0].metadata, {"type": "grandchild"})

    def test_complex_types(self):
        """Test schema with complex type combinations."""
        # Test with empty collections
        schema = ComplexTypesSchema()
        self.assertEqual(schema.enum_list, [])
        self.assertEqual(schema.str_dict, {})
        self.assertEqual(schema.int_dict, {})
        self.assertEqual(schema.enum_dict, {})
        self.assertEqual(schema.nested_list_dict, {})
        self.assertIsNone(schema.optional_enum_list)
        self.assertIsNone(schema.optional_dict)
        self.assertEqual(schema.internal_dict, {})

        # Test with populated collections
        schema = ComplexTypesSchema(
            enum_list=[ComplexEnum.SPECIAL_CHARS, ComplexEnum.UNICODE],
            str_dict={"key": "value"},
            int_dict={"key": 42},
            enum_dict={"key": ComplexEnum.SPACES},
            nested_list_dict={"key": ["value1", "value2"]},
            optional_enum_list=[ComplexEnum.EMPTY],
            optional_dict={"key": "value"},
            internal_dict={"key": "value"}
        )

        self.assertEqual(len(schema.enum_list), 2)
        self.assertEqual(schema.enum_list[0], ComplexEnum.SPECIAL_CHARS)
        self.assertEqual(schema.str_dict["key"], "value")
        self.assertEqual(schema.int_dict["key"], 42)
        self.assertEqual(schema.enum_dict["key"], ComplexEnum.SPACES)
        self.assertEqual(schema.nested_list_dict["key"], ["value1", "value2"])
        self.assertEqual(schema.optional_enum_list, [ComplexEnum.EMPTY])
        self.assertEqual(schema.optional_dict, {"key": "value"})
        self.assertEqual(schema.internal_dict, {"key": "value"})

        # Test invalid enum values
        with self.assertRaises(ValueError):
            ComplexTypesSchema(
                enum_list=["invalid_enum"]  # Invalid enum value
            )

        # Test invalid dict values
        with self.assertRaises(ValueError):
            ComplexTypesSchema(
                int_dict={"key": "not_an_int"}  # Invalid int value
            )

    # def test_cache_invalidation(self):
    #     """Test cache invalidation for class methods."""
    #     # Get user editable fields (should cache)
    #     fields1 = ValidatorSchema.get_user_editable_fields()
        
    #     # Get again (should use cache)
    #     fields2 = ValidatorSchema.get_user_editable_fields()
        
    #     # Results should be identical
    #     self.assertEqual(fields1, fields2)
        
    #     # Cache should exist
    #     self.assertIn("_cache_get_user_editable_fields", ValidatorSchema._CACHE)

    #     # Clear cache
    #     ValidatorSchema._CACHE.clear()
        
    #     # Get fields again (should recompute)
    #     fields3 = ValidatorSchema.get_user_editable_fields()
        
    #     # Results should still be the same
    #     self.assertEqual(fields1, fields3)

    def test_schema_diffing(self):
        """Test schema diffing with complex scenarios."""
        # Get current schema
        current = ComplexTypesSchema.get_schema_for_db()

        # Test no changes
        diff = ComplexTypesSchema.diff_from_provided_schema(current)
        self.assertEqual(len(diff["added"]), 0)
        self.assertEqual(len(diff["removed"]), 0)
        self.assertEqual(len(diff["modified_type"]), 0)
        self.assertEqual(len(diff["modified_default"]), 0)
        self.assertEqual(len(diff["modified_deprecated"]), 0)
        self.assertEqual(len(diff["modified_editable"]), 0)

        # Modify schema
        modified = deepcopy(current)
        
        # Add new field
        modified["new_field"] = {
            "_type": "str",
            "_default": None,
            "_deprecated": False,
            "_user_editable": True
        }
        
        # Remove field
        del modified["enum_list"]
        
        # Modify type
        modified["str_dict"]["_type"] = "dict[str,int]"
        
        # Modify default
        modified["int_dict"]["_default"] = {"key": 0}
        
        # Get diff
        diff = ComplexTypesSchema.diff_from_provided_schema(modified, self_is_base_for_diff=True)
        print(json.dumps(diff, indent=4))
        
        # Check changes
        self.assertIn("new_field", diff["added"])
        self.assertIn("enum_list", diff["removed"])
        self.assertIn("str_dict._type", diff["modified_type"])
        self.assertIn("int_dict._default", diff["modified_default"])

if __name__ == '__main__':
    unittest.main() 
