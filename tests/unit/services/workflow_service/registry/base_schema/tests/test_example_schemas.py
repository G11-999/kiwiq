"""
Tests for real-world usage patterns of BaseSchema class.

This module contains example schemas and tests that demonstrate:
1. Complex nested structures
2. Field validation rules
3. Schema inheritance
4. Type validation in real-world scenarios
"""

import unittest
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime, date

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from workflow_service.registry.schemas.base import BaseSchema

# Example Enums
class UserRole(str, Enum):
    """User role enumeration."""
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"

class TaskStatus(str, Enum):
    """Task status enumeration."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"

# Example Schemas
class UserSchema(BaseSchema):
    """User information schema."""
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    role: UserRole
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True
    internal_id: SkipJsonSchema[str]

class TaskSchema(BaseSchema):
    """Task information schema."""
    title: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    status: TaskStatus = TaskStatus.TODO
    due_date: Optional[date] = None
    assigned_to: Optional[UserSchema] = None
    tags: List[str] = []
    metadata: Dict[str, str] = {}

class ProjectSchema(BaseSchema):
    """Project information schema."""
    name: str = Field(..., min_length=3, max_length=50)
    description: str = Field(..., max_length=1000)
    owner: UserSchema
    members: List[UserSchema] = []
    tasks: List[TaskSchema] = []
    created_at: datetime
    updated_at: datetime
    is_archived: bool = False
    internal_data: SkipJsonSchema[Dict[str, str]] = {}

class TestExampleSchemas(unittest.TestCase):
    """Test cases for example schemas."""

    def setUp(self):
        """Set up test fixtures."""
        self.user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "role": "admin",
            "created_at": "2024-03-16T12:00:00",
            "internal_id": "user123"
        }
        
        self.task_data = {
            "title": "Test Task",
            "description": "A test task",
            "status": "todo",
            "due_date": "2024-04-01",
            "tags": ["test", "example"],
            "metadata": {"priority": "high"}
        }
        
        self.project_data = {
            "name": "Test Project",
            "description": "A test project",
            "created_at": "2024-03-16T12:00:00",
            "updated_at": "2024-03-16T12:00:00",
            "internal_data": {"key": "value"}
        }

    def test_user_schema_validation(self):
        """Test user schema validation rules."""
        # Test valid user data
        user = UserSchema(**self.user_data)
        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.role, UserRole.ADMIN)
        self.assertTrue(user.is_active)
        self.assertEqual(user.internal_id, "user123")

        # Test invalid username
        with self.assertRaises(ValueError):
            UserSchema(**{
                **self.user_data,
                "username": "ab"  # Too short
            })

        # Test invalid email
        with self.assertRaises(ValueError):
            UserSchema(**{
                **self.user_data,
                "email": "invalid-email"  # Invalid format
            })

        # Test invalid role
        with self.assertRaises(ValueError):
            UserSchema(**{
                **self.user_data,
                "role": "invalid"  # Invalid enum value
            })

    def test_task_schema_validation(self):
        """Test task schema validation rules."""
        # Test valid task data
        task = TaskSchema(**self.task_data)
        self.assertEqual(task.title, "Test Task")
        self.assertEqual(task.description, "A test task")
        self.assertEqual(task.status, TaskStatus.TODO)
        self.assertEqual(task.due_date, date(2024, 4, 1))
        self.assertEqual(task.tags, ["test", "example"])
        self.assertEqual(task.metadata, {"priority": "high"})

        # Test invalid title
        with self.assertRaises(ValueError):
            TaskSchema(**{
                **self.task_data,
                "title": ""  # Empty title
            })

        # Test invalid description
        with self.assertRaises(ValueError):
            TaskSchema(**{
                **self.task_data,
                "description": "x" * 1001  # Too long
            })

        # Test invalid status
        with self.assertRaises(ValueError):
            TaskSchema(**{
                **self.task_data,
                "status": "invalid"  # Invalid enum value
            })

        # Test with assigned user
        task_with_user = TaskSchema(**{
            **self.task_data,
            "assigned_to": self.user_data
        })
        self.assertIsInstance(task_with_user.assigned_to, UserSchema)
        self.assertEqual(task_with_user.assigned_to.username, "testuser")

    def test_project_schema_validation(self):
        """Test project schema validation rules."""
        # Create a complete project with nested structures
        project_data = {
            **self.project_data,
            "owner": self.user_data,
            "members": [self.user_data],
            "tasks": [self.task_data]
        }

        project = ProjectSchema(**project_data)
        self.assertEqual(project.name, "Test Project")
        self.assertEqual(project.description, "A test project")
        self.assertIsInstance(project.owner, UserSchema)
        self.assertEqual(len(project.members), 1)
        self.assertEqual(len(project.tasks), 1)
        self.assertFalse(project.is_archived)
        self.assertEqual(project.internal_data, {"key": "value"})

        # Test invalid name
        with self.assertRaises(ValueError):
            ProjectSchema(**{
                **project_data,
                "name": "ab"  # Too short
            })

        # Test invalid description
        with self.assertRaises(ValueError):
            ProjectSchema(**{
                **project_data,
                "description": "x" * 1001  # Too long
            })

    def test_schema_inheritance(self):
        """Test schema inheritance and type validation."""
        class ExtendedUserSchema(UserSchema):
            """Extended user schema with additional fields."""
            phone: Optional[str] = None
            address: Optional[str] = None

        # Test that extended schema inherits validation rules
        extended_user = ExtendedUserSchema(**{
            **self.user_data,
            "phone": "+1234567890",
            "address": "123 Test St"
        })

        self.assertEqual(extended_user.username, "testuser")
        self.assertEqual(extended_user.phone, "+1234567890")
        self.assertEqual(extended_user.address, "123 Test St")

        # Test that validation rules are inherited
        with self.assertRaises(ValueError):
            ExtendedUserSchema(**{
                **self.user_data,
                "username": "ab",  # Too short (inherited validation)
                "phone": "+1234567890"
            })

    # def test_user_editable_fields(self):
    #     """Test user editable fields in example schemas."""
    #     # Check UserSchema editable fields
    #     user_editable = UserSchema.get_user_editable_fields()
    #     self.assertIn("username", user_editable)
    #     self.assertIn("email", user_editable)
    #     self.assertIn("role", user_editable)
    #     self.assertNotIn("internal_id", user_editable)

    #     # Check TaskSchema editable fields
    #     task_editable = TaskSchema.get_user_editable_fields()
    #     self.assertIn("title", task_editable)
    #     self.assertIn("description", task_editable)
    #     self.assertIn("status", task_editable)
    #     self.assertIn("assigned_to", task_editable)
    #     self.assertIsInstance(task_editable["assigned_to"], dict)

    #     # Check ProjectSchema editable fields
    #     project_editable = ProjectSchema.get_user_editable_fields()
    #     self.assertIn("name", project_editable)
    #     self.assertIn("description", project_editable)
    #     self.assertIn("owner", project_editable)
    #     self.assertIn("members", project_editable)
    #     self.assertIn("tasks", project_editable)
    #     self.assertNotIn("internal_data", project_editable)

    def test_json_schema_generation(self):
        """Test JSON schema generation for example schemas."""
        # Get schema for UserSchema
        user_schema = UserSchema.get_schema_for_db()
        self.assertIn("username", user_schema)
        self.assertIn("email", user_schema)
        self.assertIn("role", user_schema)
        self.assertIn("internal_id", user_schema)

        # Check field types
        self.assertEqual(user_schema["username"]["_type"], "str")
        self.assertEqual(user_schema["role"]["_type"], "<enum 'UserRole'>")
        self.assertEqual(user_schema["is_active"]["_type"], "bool")

        # Get schema for TaskSchema
        task_schema = TaskSchema.get_schema_for_db()
        self.assertIn("title", task_schema)
        self.assertIn("status", task_schema)
        self.assertIn("assigned_to", task_schema)

        # Check nested schema
        self.assertIsInstance(task_schema["assigned_to"]["_nested_schema"], dict)

        # Get schema for ProjectSchema
        project_schema = ProjectSchema.get_schema_for_db()
        self.assertIn("name", project_schema)
        self.assertIn("owner", project_schema)
        self.assertIn("members", project_schema)
        self.assertIn("tasks", project_schema)

        # Check list fields
        self.assertEqual(project_schema["members"]["_type"], "typing.List[test_example_schemas.UserSchema]")
        self.assertEqual(project_schema["tasks"]["_type"], "typing.List[test_example_schemas.TaskSchema]")

if __name__ == '__main__':
    unittest.main() 
