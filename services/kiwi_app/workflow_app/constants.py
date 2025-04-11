"""Constants for the Workflow Application."""
from enum import Enum

class LaunchStatus(str, Enum):
    """Enum for the launch status of Node Templates."""
    EXPERIMENTAL = "experimental"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

class WorkflowRunStatus(str, Enum):
    """Enum for the status of a Workflow Run."""
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_HITL = "waiting_hitl" # Waiting for Human-in-the-Loop input


class SchemaType(str, Enum):
    """Enum for the type of schema."""
    JSON_SCHEMA = "json_schema"
    CONSTRUCT_DYNAMIC_SCHEMA = "construct_dynamic_schema"
    CODE_REGISTERED_SCHEMA = "code_registered_schema"


class TemplateType(str, Enum):
    """Enum for the different types of templates."""
    NODE = "node"
    PROMPT = "prompt"
    SCHEMA = "schema"

class NotificationType(str, Enum):
    """Enum for the type of user notifications."""
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    HITL_REQUESTED = "hitl_requested"
    RUN_STARTED = "run_started" # Example: If needed
    SYSTEM_MESSAGE = "system_message"
    # Add more types as needed

class HITLJobStatus(str, Enum):
    """Enum for the status of Human-in-the-Loop (HITL) jobs."""
    PENDING = "pending"       # Waiting for user response
    RESPONDED = "responded"   # User provided a response
    EXPIRED = "expired"       # Job expired before response
    CANCELLED = "cancelled"   # Job was cancelled (e.g., workflow cancelled)

# Permissions specific to the Workflow service
# These should be added to the auth service's setup/seeding process
# alongside core auth permissions.
class WorkflowPermissions(str, Enum):
    """Permissions related to workflows and runs."""
    # Workflow Permissions
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_UPDATE = "workflow:update"
    WORKFLOW_DELETE = "workflow:delete"
    WORKFLOW_EXECUTE = "workflow:execute"

    # Workflow Run Permissions
    RUN_READ = "run:read"
    RUN_MANAGE = "run:manage" # For cancel/pause/resume, potentially separate

    # Template Permissions
    TEMPLATE_READ = "template:read"         # Read any accessible template
    TEMPLATE_CREATE = "template:create" # Create org-specific prompt/schema
    TEMPLATE_UPDATE = "template:update" # Update org-specific prompt/schema
    TEMPLATE_DELETE = "template:delete" # Delete org-specific prompt/schema

    # # Admin-only Template Permissions
    # TEMPLATE_MANAGE_SYSTEM = "template:manage_system" # CRUD for Node Templates and system prompt/schema 
