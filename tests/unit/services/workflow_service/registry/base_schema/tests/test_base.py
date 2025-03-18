"""
Tests for core functionality of BaseSchema class.

This module contains tests for:
1. Basic schema validation and instantiation
2. Field type validation
3. Schema configuration
4. Field validation rules
5. Special field keys
6. Caching mechanism
"""

# import pytest
# pytestmark = pytest.mark.unit



import unittest
from enum import Enum, IntEnum
from typing import Dict, List, Optional

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

# from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.registry.schemas.base import BaseSchema

# Test Enums
class TestStrEnum(str, Enum):
    """String enum for testing."""
    A = "a"
    B = "b"
    C = "c"

class TestIntEnum(IntEnum):
    """Integer enum for testing."""
    ONE = 1
    TWO = 2
    THREE = 3

# Test Schema Classes
class SimpleTestSchema(BaseSchema):
    """Simple schema with primitive types for basic testing."""
    str_field: str
    int_field: int
    float_field: float
    bool_field: bool
    bytes_field: bytes

class EnumTestSchema(BaseSchema):
    """Schema for testing enum field handling."""
    str_enum: TestStrEnum
    int_enum: TestIntEnum
    optional_enum: Optional[TestStrEnum] = None

class NestedTestSchema(BaseSchema):
    """Schema for testing nested schema handling."""
    name: str
    simple: SimpleTestSchema
    enums: EnumTestSchema

class CollectionTestSchema(BaseSchema):
    """Schema for testing collection type handling."""
    str_list: List[str]
    enum_list: List[TestStrEnum]
    schema_list: List[SimpleTestSchema]
    str_dict: Dict[str, str]
    enum_dict: Dict[str, TestStrEnum]
    schema_dict: Dict[str, SimpleTestSchema]
    nested_list_dict: Dict[str, List[SimpleTestSchema]]

class UserEditableTestSchema(BaseSchema):
    """Schema for testing user editable field handling."""
    public_field: str
    internal_field: SkipJsonSchema[str]
    optional_public: Optional[str] = None
    optional_internal: SkipJsonSchema[Optional[str]] = None

class TestBaseSchema(unittest.TestCase):
    """Test cases for BaseSchema class."""

    def setUp(self):
        """Set up test fixtures."""
        self.simple_data = {
            "str_field": "test",
            "int_field": 42,
            "float_field": 3.14,
            "bool_field": True,
            "bytes_field": b"test"
        }
        self.enum_data = {
            "str_enum": "a",
            "int_enum": 1
        }
        self.nested_data = {
            "name": "test",
            "simple": self.simple_data,
            "enums": self.enum_data
        }

    def test_primitive_type_validation(self):
        """Test validation of primitive field types."""
        # Test valid primitive types
        schema = SimpleTestSchema(**self.simple_data)
        self.assertEqual(schema.str_field, "test")
        self.assertEqual(schema.int_field, 42)
        self.assertEqual(schema.float_field, 3.14)
        self.assertTrue(schema.bool_field)
        self.assertEqual(schema.bytes_field, b"test")

        # Test invalid primitive types
        with self.assertRaises(ValueError):
            SimpleTestSchema(
                str_field=42,  # Type error: int instead of str
                int_field="42",  # Type error: str instead of int
                float_field="3.14",  # Type error: str instead of float
                bool_field="True",  # Type error: str instead of bool
                bytes_field="test"  # Type error: str instead of bytes
            )

    def test_enum_type_validation(self):
        """Test validation of enum field types."""
        # Test valid enum values
        schema = EnumTestSchema(**self.enum_data)
        self.assertEqual(schema.str_enum, TestStrEnum.A)
        self.assertEqual(schema.int_enum, TestIntEnum.ONE)
        self.assertIsNone(schema.optional_enum)

        # Test invalid enum values
        with self.assertRaises(ValueError):
            EnumTestSchema(
                str_enum="invalid",  # Invalid enum value
                int_enum=4  # Invalid enum value
            )

    def test_nested_schema_validation(self):
        """Test validation of nested schema fields."""
        # Test valid nested schema
        schema = NestedTestSchema(**self.nested_data)
        self.assertEqual(schema.name, "test")
        self.assertIsInstance(schema.simple, SimpleTestSchema)
        self.assertIsInstance(schema.enums, EnumTestSchema)

        # Test invalid nested schema
        with self.assertRaises(ValueError):
            NestedTestSchema(
                name="test",
                simple={"invalid": "data"},  # Missing required fields
                enums=self.enum_data
            )

    def test_collection_type_validation(self):
        """Test validation of collection field types (List and Dict)."""
        data = {
            "str_list": ["a", "b", "c"],
            "enum_list": ["a", "b"],
            "schema_list": [self.simple_data],
            "str_dict": {"key": "value"},
            "enum_dict": {"key": "a"},
            "schema_dict": {"key": self.simple_data},
            "nested_list_dict": {"key": [self.simple_data]}
        }

        # Test valid collections
        schema = CollectionTestSchema(**data)
        self.assertEqual(len(schema.str_list), 3)
        self.assertEqual(len(schema.enum_list), 2)
        self.assertEqual(len(schema.schema_list), 1)
        self.assertEqual(len(schema.str_dict), 1)
        self.assertEqual(len(schema.enum_dict), 1)
        self.assertEqual(len(schema.schema_dict), 1)
        self.assertEqual(len(schema.nested_list_dict), 1)

        # Test invalid collections
        with self.assertRaises(ValueError):
            CollectionTestSchema(
                str_list=[1, 2, 3],  # Type error: int instead of str
                enum_list=["invalid"],  # Invalid enum value
                schema_list=[{"invalid": "data"}],  # Invalid schema data
                str_dict={"key": 1},  # Type error: int instead of str
                enum_dict={"key": "invalid"},  # Invalid enum value
                schema_dict={"key": {"invalid": "data"}},  # Invalid schema data
                nested_list_dict={"key": [{"invalid": "data"}]}  # Invalid schema data
            )

    def test_user_editable_fields(self):
        """Test handling of user editable fields."""
        schema = UserEditableTestSchema(
            public_field="public",
            internal_field="internal"
        )

        # # Test get_user_editable_fields
        # editable_fields = UserEditableTestSchema.get_user_editable_fields()
        # self.assertIn("public_field", editable_fields)
        # self.assertIn("optional_public", editable_fields)
        # self.assertNotIn("internal_field", editable_fields)
        # self.assertNotIn("optional_internal", editable_fields)

        # Test model_dump_json_only_user_editable
        user_visible = schema.model_dump_only_user_editable()
        self.assertIn("public_field", user_visible)
        self.assertIn("optional_public", user_visible)
        self.assertNotIn("internal_field", user_visible)
        self.assertNotIn("optional_internal", user_visible)

    def test_validate_only_user_editable_fields_provided_in_input(self):
        """Test validation of input data containing only user editable fields."""
        # Test valid input with only user editable fields
        is_valid, _ = UserEditableTestSchema.validate_only_user_editable_fields_provided_in_input({
            "public_field": "public",
            "optional_public": "optional"
        })
        self.assertTrue(is_valid)

        # Test invalid input with non-user editable fields
        is_valid, field_name = UserEditableTestSchema.validate_only_user_editable_fields_provided_in_input({
            "public_field": "public",
            "internal_field": "internal"  # Not user editable
        })
        self.assertFalse(is_valid)
        self.assertEqual(field_name, "internal_field")

    # def test_cache_classmethod_decorator(self):
    #     """Test the cache_classmethod decorator functionality."""
    #     # First call should compute and cache
    #     result1 = UserEditableTestSchema.get_user_editable_fields()
        
    #     # Second call should use cache
    #     result2 = UserEditableTestSchema.get_user_editable_fields()
        
    #     # Results should be identical
    #     self.assertEqual(result1, result2)
        
    #     # Cache should exist
    #     self.assertIn("_cache_get_user_editable_fields", UserEditableTestSchema._CACHE)

if __name__ == '__main__':
    unittest.main() 
