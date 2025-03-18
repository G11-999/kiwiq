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
        
        # Check changes
        self.assertIn("new_field", diff["added"])
        self.assertIn("enum_list", diff["removed"])
        self.assertIn("str_dict._type", diff["modified_type"])
        self.assertIn("int_dict._default", diff["modified_default"])

    def test_model_dump_only_user_editable_nested(self):
        """Test model_dump_only_user_editable with complex nested BaseSchema scenarios.
        
        Tests all dump modes and serialization options:
        1. model_dump_only_user_editable() in Python mode - retains Python objects
        2. model_dump_only_user_editable() in JSON mode - serializes to JSON-compatible values 
        3. model_dump_only_user_editable() with include_deprecated=True/False
        4. model_dump_only_user_editable() with serialize_values=True/False
        5. Regular model_dump() - includes all fields including SkipJsonSchema ones
        """
        # Define nested schemas with mix of user editable and non-editable fields
        deprecated_field_key = BaseSchema.DEPRECATED_FIELD_KEY
        class InnerSchema(BaseSchema):
            """Inner schema with mix of editable and non-editable fields."""
            editable_str: str = Field(default="test")
            editable_int: int = Field(default=42)
            editable_date: datetime = Field(default_factory=datetime.now)
            deprecated_field: str = Field(default="old", **{deprecated_field_key: True})
            internal_id: SkipJsonSchema[str] = Field(default="id123") 
            internal_metadata: SkipJsonSchema[Dict[str, str]] = Field(default_factory=dict)
            # Added list and dict fields
            str_list: List[str] = Field(default_factory=list)
            int_dict: Dict[str, int] = Field(default_factory=dict)

        class MiddleSchema(BaseSchema):
            """Middle schema with nested inner schema."""
            name: str = Field(default="middle")
            inner: InnerSchema = Field(default_factory=InnerSchema)
            deprecated_count: int = Field(default=0, **{deprecated_field_key: True})
            internal_status: SkipJsonSchema[str] = Field(default="active")
            inner_list: List[InnerSchema] = Field(default_factory=list)
            # Added list and dict fields with BaseSchema values
            schema_dict: Dict[str, InnerSchema] = Field(default_factory=dict)
            nested_list_dict: Dict[str, List[InnerSchema]] = Field(default_factory=dict)

        class OuterSchema(BaseSchema):
            """Outer schema with multiple levels of nesting."""
            title: str = Field(default="outer")
            middle: MiddleSchema = Field(default_factory=MiddleSchema)
            middle_list: List[MiddleSchema] = Field(default_factory=list)
            deprecated_flag: bool = Field(default=False, **{deprecated_field_key: True})
            internal_created_at: SkipJsonSchema[datetime] = Field(default_factory=datetime.now)
            # Added list and dict fields
            str_int_dict: Dict[str, int] = Field(default_factory=dict)
            middle_dict: Dict[str, MiddleSchema] = Field(default_factory=dict)

        test_date = datetime(2024, 1, 1, 12, 30, 45)

        # Create test instances with nested data
        inner1 = InnerSchema(
            editable_str="inner1",
            editable_int=100,
            editable_date=test_date,
            deprecated_field="legacy1",
            internal_id="id1",
            internal_metadata={"key": "value"},
            str_list=["a", "b", "c"],
            int_dict={"x": 1, "y": 2}
        )

        inner2 = InnerSchema(
            editable_str="inner2", 
            editable_int=200,
            editable_date=test_date,
            deprecated_field="legacy2",
            internal_id="id2",
            str_list=["d", "e"],
            int_dict={"z": 3}
        )

        middle1 = MiddleSchema(
            name="middle1",
            inner=inner1,
            deprecated_count=5,
            internal_status="pending",
            inner_list=[inner1, inner2],
            schema_dict={"first": inner1, "second": inner2},
            nested_list_dict={"group1": [inner1, inner2]}
        )

        middle2 = MiddleSchema(
            name="middle2",
            inner=inner2,
            deprecated_count=3,
            inner_list=[inner2],
            schema_dict={"third": inner2},
            nested_list_dict={"group2": [inner2]}
        )

        outer = OuterSchema(
            title="test_outer",
            middle=middle1,
            middle_list=[middle1, middle2],
            deprecated_flag=True,
            internal_created_at=test_date,
            str_int_dict={"a": 1, "b": 2},
            middle_dict={"m1": middle1, "m2": middle2}
        )

        # Test 1: Python mode with include_deprecated=True (default)
        python_dump = outer.model_dump_only_user_editable()

        # Verify Python objects and deprecated fields are preserved
        self.assertIsInstance(python_dump["middle"]["inner"]["editable_date"], datetime)
        self.assertEqual(python_dump["middle"]["inner"]["editable_date"], test_date)
        self.assertEqual(python_dump["middle"]["inner"]["deprecated_field"], "legacy1")
        self.assertEqual(python_dump["middle"]["deprecated_count"], 5)
        self.assertEqual(python_dump["deprecated_flag"], True)

        # Verify new list and dict fields
        self.assertEqual(python_dump["middle"]["inner"]["str_list"], ["a", "b", "c"])
        self.assertEqual(python_dump["middle"]["inner"]["int_dict"], {"x": 1, "y": 2})
        self.assertEqual(len(python_dump["middle"]["schema_dict"]), 2)
        self.assertEqual(python_dump["str_int_dict"], {"a": 1, "b": 2})
        self.assertEqual(len(python_dump["middle_dict"]), 2)

        # Test 2: Python mode with include_deprecated=False
        python_dump_no_deprecated = outer.model_dump_only_user_editable(include_deprecated=False)

        # Verify deprecated fields are excluded
        self.assertNotIn("deprecated_field", python_dump_no_deprecated["middle"]["inner"])
        self.assertNotIn("deprecated_count", python_dump_no_deprecated["middle"])
        self.assertNotIn("deprecated_flag", python_dump_no_deprecated)

        # Test 3: JSON mode with serialize_values=True
        json_dump = outer.model_dump_only_user_editable(serialize_values=True)

        # Verify values are JSON serialized
        self.assertIsInstance(json_dump["middle"]["inner"]["editable_date"], str)
        self.assertEqual(json_dump["middle"]["inner"]["editable_date"], test_date.isoformat())

        # Verify complex collections are properly serialized
        self.assertEqual(json_dump["middle"]["schema_dict"]["first"]["str_list"], ["a", "b", "c"])
        self.assertEqual(json_dump["middle_dict"]["m1"]["inner"]["int_dict"], {"x": 1, "y": 2})

        # Test 4: JSON mode with serialize_values=True and include_deprecated=False
        json_dump_no_deprecated = outer.model_dump_only_user_editable(
            serialize_values=True,
            include_deprecated=False
        )

        # Verify JSON serialization and deprecated field exclusion
        self.assertIsInstance(json_dump_no_deprecated["middle"]["inner"]["editable_date"], str)
        self.assertNotIn("deprecated_field", json_dump_no_deprecated["middle"]["inner"])

        # Common verification for all user editable dumps
        for dump in [python_dump, python_dump_no_deprecated, json_dump, json_dump_no_deprecated]:
            # Verify outer level
            self.assertEqual(dump["title"], "test_outer")
            self.assertNotIn("internal_created_at", dump)
            self.assertEqual(dump["str_int_dict"], {"a": 1, "b": 2})

            # Verify middle level
            middle_dump = dump["middle"]
            self.assertEqual(middle_dump["name"], "middle1")
            self.assertNotIn("internal_status", middle_dump)
            self.assertEqual(len(middle_dump["schema_dict"]), 2)
            self.assertEqual(len(middle_dump["nested_list_dict"]["group1"]), 2)

            # Verify inner level
            inner_dump = middle_dump["inner"]
            self.assertEqual(inner_dump["editable_str"], "inner1")
            self.assertEqual(inner_dump["editable_int"], 100)
            self.assertEqual(inner_dump["str_list"], ["a", "b", "c"])
            self.assertEqual(inner_dump["int_dict"], {"x": 1, "y": 2})
            self.assertNotIn("internal_id", inner_dump)
            self.assertNotIn("internal_metadata", inner_dump)

            # Verify lists
            self.assertEqual(len(dump["middle_list"]), 2)
            self.assertEqual(dump["middle_list"][0]["name"], "middle1")
            self.assertEqual(dump["middle_list"][1]["name"], "middle2")

            # Verify dicts
            self.assertEqual(len(dump["middle_dict"]), 2)
            self.assertEqual(dump["middle_dict"]["m1"]["name"], "middle1")
            self.assertEqual(dump["middle_dict"]["m2"]["name"], "middle2")

        # Test 5: Regular model_dump should include all fields
        full_dump = outer.model_dump()
        
        # Verify all fields are present including SkipJsonSchema and deprecated
        self.assertIn("internal_created_at", full_dump)
        self.assertEqual(full_dump["internal_created_at"], test_date)
        self.assertIn("deprecated_flag", full_dump)
        self.assertTrue(full_dump["deprecated_flag"])
        
        self.assertIn("internal_status", full_dump["middle"])
        self.assertEqual(full_dump["middle"]["internal_status"], "pending")
        self.assertIn("deprecated_count", full_dump["middle"])
        self.assertEqual(full_dump["middle"]["deprecated_count"], 5)
        
        self.assertIn("internal_id", full_dump["middle"]["inner"])
        self.assertEqual(full_dump["middle"]["inner"]["internal_id"], "id1")
        self.assertIn("internal_metadata", full_dump["middle"]["inner"])
        self.assertEqual(full_dump["middle"]["inner"]["internal_metadata"], {"key": "value"})
        self.assertIn("deprecated_field", full_dump["middle"]["inner"])
        self.assertEqual(full_dump["middle"]["inner"]["deprecated_field"], "legacy1")

        # Verify new fields in full dump
        self.assertEqual(full_dump["str_int_dict"], {"a": 1, "b": 2})
        self.assertEqual(len(full_dump["middle_dict"]), 2)
        self.assertEqual(full_dump["middle"]["inner"]["str_list"], ["a", "b", "c"])
        self.assertEqual(full_dump["middle"]["inner"]["int_dict"], {"x": 1, "y": 2})
        self.assertEqual(len(full_dump["middle"]["schema_dict"]), 2)
        self.assertEqual(len(full_dump["middle"]["nested_list_dict"]["group1"]), 2)

        # Verify JSON serializability
        try:
            json.dumps(json_dump)
            json.dumps(json_dump_no_deprecated)
        except Exception as e:
            self.fail(f"Failed to JSON serialize dumps: {e}")

        # Verify Python dumps are NOT JSON serializable due to datetime objects
        with self.assertRaises(TypeError):
            json.dumps(python_dump)
        with self.assertRaises(TypeError):
            json.dumps(python_dump_no_deprecated)


if __name__ == '__main__':
    unittest.main() 
