"""SQLModel definitions for the Workflow Application."""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal

import sqlalchemy as sa
from sqlalchemy import String as SQLAlchemyString, Text, JSON, Boolean, Index, ForeignKey, Enum as SQLAlchemyEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.schema import CheckConstraint
from sqlmodel import Field, Relationship, SQLModel, Column

# Assuming auth models are accessible, adjust import if needed
from kiwi_app.auth.models import User, Organization, table_prefix as auth_table_prefix
from global_utils import datetime_now_utc
from kiwi_app.settings import settings
from kiwi_app.workflow_app.constants import LaunchStatus, WorkflowRunStatus, NotificationType, HITLJobStatus, SchemaType # Import Enums

# Define table prefix using settings
table_prefix = settings.DB_TABLE_WORKFLOW_PREFIX

# --- NodeTemplate Model --- #
class NodeTemplate(SQLModel, table=True):
    """Represents a reusable node blueprint owned by KiwiQ."""
    __tablename__ = f"{table_prefix}node_template"
    # Define table arguments for constraints after the class definition
    __table_args__ = (
        UniqueConstraint('name', 'version', name=f'{table_prefix}node_template_name_version_uc'),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    name: str = Field(index=True, description="Unique name identifying the node type (e.g., 'llm_generator')")
    version: str = Field(index=True, description="Version string (e.g., '1.0.0', 'latest')")
    node_is_tool: Optional[bool] = Field(default=False, index=True, nullable=True, description="True if this is a tool node meant to be used with LLMs tool calling.")
    description: str = Field(sa_column=Column(Text))

    # Schemas stored as JSONB
    # Use Dict[str, Any] for flexibility, validation happens at service/registry level
    # NOTE: here None value ==> no schema; empty dict {} ==> dynamic schema!
    input_schema: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True), description="JSON Schema for inputs")
    output_schema: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True), description="JSON Schema for outputs")
    config_schema: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True), description="JSON Schema for node configuration")

    launch_status: LaunchStatus = Field(
        default=LaunchStatus.DEVELOPMENT,
        sa_column=Column(SQLAlchemyEnum(LaunchStatus, name=f"{table_prefix}node_launch_status_enum"), nullable=False, index=True),
        description="Deployment status of the node template"
    )

    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc))

# --- Workflow Model --- #
class Workflow(SQLModel, table=True):
    """Represents a user-defined workflow configuration owned by an organization."""
    __tablename__ = f"{table_prefix}workflow"
    __table_args__ = (
        # Ensure name/version is unique either for system templates OR within a specific org
        Index(f'{table_prefix}workflow_org_name_version_idx', 'owner_org_id', 'name', 'version_tag', unique=True),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    # Self-referential relationship to support workflow templates/inheritance
    parent_base_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{table_prefix}workflow.id",
        nullable=True,
        index=True,
        description="Reference to parent workflow this was derived from (for templates)"
    )
    name: str = Field(index=True, description="User-defined name for the workflow")
    description: Optional[str] = Field(default=None, sa_column=Column(Text))

    # NOTE: if this is None, implies it's a public workflow template, available to all users!
    # TODO: handle case when user deletes an org! provide option to transfer all workflows to another org!
    owner_org_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}org.id", ondelete="CASCADE"), index=True, nullable=True),
        description="Organization that owns this workflow"
    )
    graph_config: Dict[str, Any] = Field(
        sa_column=Column(JSON),
        description="The core definition of the workflow graph (nodes, edges, template refs)"
    )
    version_tag: Optional[str] = Field(default=None, nullable=True, index=True, description="User-defined tag for versioning (e.g., 'v1.2-stable')")
    is_template: bool = Field(default=False, index=True, description="Indicates if this workflow can be used as a template within the org")
    is_public: Optional[bool] = Field(default=False, index=True, nullable=True, description="Indicates if this workflow is publicly accessible")
    is_system_entity: Optional[bool] = Field(default=False, index=True, nullable=True, description="True if this is a KiwiQ system Workflow, only meant to be used by KiwiQ application.")

    launch_status: LaunchStatus = Field(
        default=LaunchStatus.DEVELOPMENT,
        sa_column=Column(SQLAlchemyEnum(LaunchStatus, name=f"{table_prefix}workflow_launch_status_enum"), nullable=False, index=True),
        description="Deployment status of the workflow"
    )

    created_by_user_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}user.id", ondelete="SET NULL"), nullable=True, index=True),
    )

    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc))

    # Relationships
    # Use full path string for cross-service relationships initially, SQLModel might need adjustment or explicit Session setup
    # NOTE: Define back_populates on the OTHER side (Organization, WorkflowRun)
    # Self-referential relationship for workflow templates/inheritance
    parent_base: Optional["Workflow"] = Relationship(
        sa_relationship_kwargs={
            "remote_side": "Workflow.id",  # Points to the primary key of the parent
            # "lazy": "joined",  # Eager load parent workflow for efficiency  # subquery  joined
            "backref": "derived_workflows"  # Creates a back-reference to access child workflows
        },
        # description="Reference to the parent workflow this was derived from (for templates)"
    )
    owner_org: "Organization" = Relationship(
        # sa_relationship_kwargs={"lazy": "joined"}
        ) # Eager load org
    runs: List["WorkflowRun"] = Relationship(back_populates="workflow")
    # Relationships for created_by/updated_by are optional, can be loaded on demand
    # created_by: Optional["User"] = Relationship(...)
    # updated_by: Optional["User"] = Relationship(...)


# --- ChatThread Model --- #
class ChatThread(SQLModel, table=True):
    """Represents a chat thread associated with a workflow.
    
    This model stores chat threads that are created for workflows, allowing
    conversations to be organized and tracked per workflow instance.
    """
    __tablename__ = f"{table_prefix}chat_thread"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, 
        primary_key=True, 
        index=True, 
        description="Unique ID for this chat thread"
    )
    
    workflow_name: str = Field(
        default=None,
        nullable=True,
        index=True,
        description="Name of the workflow this chat thread is associated with"
    )
    
    workflow_version: Optional[str] = Field(
        default=None,
        nullable=True,
        index=True,
        description="Version of the workflow this chat thread is associated with"
    )
    
    thread_name: Optional[str] = Field(
        default=None,
        nullable=True,
        description="Optional name/title for this chat thread"
    )

    tag: Optional[str] = Field(
        default=None,
        nullable=True,
        index=True,
        description="Optional tag to categorize or filter chat threads"
    )

    user_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}user.id", ondelete="CASCADE"), nullable=False, index=True),
        description="User ID of the thread owner"
    )

    created_at: datetime = Field(
        default_factory=datetime_now_utc, 
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
        description="Timestamp when this chat thread was created"
    )
    
    updated_at: datetime = Field(
        default_factory=datetime_now_utc, 
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc),
        description="Timestamp when this chat thread was last updated"
    )
    
    # TODO: add on-cascade_delete
    # Relationship to user model
    user: "User" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ChatThread.user_id]"
        }
    )


# --- WorkflowConfigOverride Model --- #
class WorkflowConfigOverride(SQLModel, table=True):
    """Represents configuration overrides for workflows at different scopes (system, org, user).
    
    This model allows for configuration overrides at various scopes:
    - System-wide overrides (is_system_entity=True)
    - Organization-specific overrides (org_id set)
    - User-specific overrides (user_id set)
    
    Workflow identification can be:
    - Specific workflow by ID (workflow_id)
    - Specific workflow by name (workflow_name)
    - Global settings when all workflow fields are None
    """
    __tablename__ = f"{table_prefix}workflow_config_override"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True, description="Unique ID for this override config")
    
    # Workflow identification - all fields can be None for global settings
    workflow_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{table_prefix}workflow.id", ondelete="CASCADE"), index=True, nullable=True),
        description="Reference to the workflow being overridden (None for global settings)"
    )
    workflow_name: Optional[str] = Field(
        default=None,
        nullable=True,
        index=True,
        description="Name of the workflow being overridden (None for global settings)"
    )
    workflow_version: Optional[str] = Field(
        default=None,
        nullable=True,
        index=True,
        description="Version of the workflow to override (None for global settings or all versions)"
    )
    tag: Optional[str] = Field(
        default=None,
        nullable=True,
        index=True,
        description="Optional tag to further categorize or identify this override configuration"
    )

    # Override configuration
    override_graph_schema: Dict[str, Any] = Field(
        sa_column=Column(JSON),
        description="The graph schema override configuration"
    )

    # Scope definition - at least one must be provided
    is_system_entity: Optional[bool] = Field(
        default=False,
        nullable=True,
        index=True,
        description="True if this is a system-wide override"
    )
    user_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}user.id", ondelete="CASCADE"), nullable=True, index=True),
        description="User-specific override"
    )
    org_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}org.id", ondelete="CASCADE"), nullable=True, index=True),
        description="Organization-specific override"
    )

    is_active: bool = Field(
        default=True,
        index=True,
        description="Whether this override configuration is currently active"
    )

    description: Optional[str] = Field(
        default=None,
        nullable=True,
        description="Description of what this override configuration does"
    )

    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc))

    # Add constraints to ensure proper configuration
    __table_args__ = (
        # Ensure at least one scope identifier is provided
        CheckConstraint(
            "(is_system_entity = true AND user_id IS NULL AND org_id IS NULL) OR "
            "(is_system_entity = false AND (user_id IS NOT NULL OR org_id IS NOT NULL))",
            name="check_scope_constraint"
        ),
        # Ensure either workflow_id or workflow_name is provided, but not both, or both can be None for global settings
        CheckConstraint(
            "(workflow_id IS NOT NULL AND workflow_name IS NULL) OR "
            "(workflow_id IS NULL AND workflow_name IS NOT NULL) OR "
            "(workflow_id IS NULL AND workflow_name IS NULL)",
            name="check_workflow_identifier"
        ),
        # Ensure workflow_version is NULL when workflow_id is provided
        CheckConstraint(
            "(workflow_id IS NULL) OR (workflow_version IS NULL)",
            name="check_workflow_version_constraint"
        ),
        # Ensure unique combination of workflow identification and scope
        UniqueConstraint(
            'workflow_id', 'workflow_name', 'workflow_version', 
            'is_system_entity', 'org_id', 'user_id', 'tag',
            name='uq_workflow_override_scope'
        ),
    )


# --- WorkflowRun Model --- #
class WorkflowRun(SQLModel, table=True):
    """Represents an execution instance of a Workflow."""
    __tablename__ = f"{table_prefix}workflow_run"
    __table_args__ = (
        # Composite index to accelerate cache lookups by workflow id + input_hash + time
        Index(f"{table_prefix}workflow_run_input_hash_created_idx", 'workflow_id', 'input_hash', 'created_at'),
        # Name-based composite index for frequent lookups when runs are executed by workflow name
        Index(f"{table_prefix}workflow_run_name_input_hash_created_idx", 'workflow_name', 'owner_org_id', 'input_hash', 'created_at'),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True, description="Unique ID for this specific run")
    parent_run_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{table_prefix}workflow_run.id", ondelete="SET NULL"), nullable=True, index=True),
        description="Reference to the parent run ID"
    )
    thread_id: Optional[uuid.UUID] = Field(default=None, nullable=True, index=True, description="Associated thread ID (e.g., from LangGraph) for shared memory across runs")
    workflow_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{table_prefix}workflow.id", ondelete="SET NULL"), nullable=True, index=True),
        description="Reference to the parent workflow"
    )
    workflow_name: Optional[str] = Field(
        default=None,
        nullable=True,
        index=True,
        description="Key name of the workflow"
    )
    owner_org_id: Optional[uuid.UUID] = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}org.id", ondelete="CASCADE"), nullable=True, index=True),
        description="Denormalized Org ID for easier run querying"
    )
    triggered_by_user_id: Optional[uuid.UUID] = Field(
        # default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}user.id", ondelete="SET NULL"), nullable=True, index=True),
    )

    status: WorkflowRunStatus = Field(
        default=WorkflowRunStatus.SCHEDULED,
        sa_column=Column(SQLAlchemyEnum(WorkflowRunStatus, name=f"{table_prefix}workflow_run_status_enum"), nullable=False, index=True),
        description="Current status of the workflow run"
    )

    inputs: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True), description="Inputs provided when the run was triggered")
    outputs: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True), description="High-level final outputs or summary")
    graph_schema: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True), description="Schema of the workflow graph")
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True), description="Error message if the run failed")
    # A deterministic hash derived from the normalized JSON of `inputs` (sorted keys) to support caching
    input_hash: Optional[str] = Field(
        default=None,
        sa_column=Column(SQLAlchemyString, index=True, nullable=True),
        description="Deterministic hash of normalized inputs used for cache lookups"
    )
    detailed_results_ref: Optional[str] = Field(
        default=None,
        nullable=True,
        description="Reference (e.g., ID or path) to detailed logs/results in NoSQL/S3"
    )
    prefect_run_ids: Optional[str] = Field(
        default=None,
        nullable=True,
        description="Comma-separated list of IDs of the Prefect runs"
    )
    tag: Optional[str] = Field(
        default=None,
        nullable=True,
        index=True,
        description="Optional tag to mark the run (e.g., for experiments, A/B testing)"
    )
    applied_workflow_config_overrides: Optional[str] = Field(
        default=None,
        nullable=True,
        description="Comma-separated list of workflow config override IDs that were applied to this run, in order of application (later ones override previous ones)"
    )
    retry_count: Optional[int] = Field(
        default=0,
        nullable=True,
        ge=0,
        description="Number of times this workflow run has been retried. Defaults to 0."
    )

    started_at: Optional[datetime] = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True))
    ended_at: Optional[datetime] = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc))

    # Relationships
    workflow: Workflow = Relationship(
        back_populates="runs", 
        # sa_relationship_kwargs={
        #     "lazy": "joined"
        # }
    ) # Eager load parent workflow  # subquery  joined
    # owner_org: "Organization" = Relationship() # Can be loaded via owner_org_id if needed
    # triggered_by: Optional["User"] = Relationship() # Can be loaded via triggered_by_user_id


# --- PromptTemplate Model --- #
class PromptTemplate(SQLModel, table=True):
    """Stores reusable prompt templates, system or org-owned."""
    __tablename__ = f"{table_prefix}prompt_template"
    __table_args__ = (
        # Ensure name/version is unique either for system templates OR within a specific org
        Index(f'{table_prefix}prompt_template_org_name_version_idx', 'owner_org_id', 'name', 'version', unique=True),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    parent_base_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{table_prefix}prompt_template.id",
        nullable=True,
        index=True,
        description="Reference to parent prompt template this was derived from (for templates)"
    )
    name: str = Field(index=True, description="Name of the prompt template")
    version: Optional[str] = Field(default=None, nullable=True, index=True, description="Version string")
    description: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    template_content: str = Field(sa_column=Column(Text), description="The prompt template string (e.g., Jinja2 format)")
    input_variables: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True), description="List of expected input variable names with default values")

    owner_org_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}org.id", ondelete="CASCADE"), nullable=True, index=True),
        description="Org owner if not a system template"
    )
    is_system_entity: Optional[bool] = Field(default=False, index=True, nullable=True, description="True if this is a KiwiQ system template, only meant to be used by KiwiQ application.")
    is_public: Optional[bool] = Field(default=False, index=True, nullable=True, description="True if this is a public template, available to all users.")

    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc))

    parent_base: Optional["PromptTemplate"] = Relationship(
        sa_relationship_kwargs={
            "remote_side": "PromptTemplate.id",  # Points to the primary key of the parent
            "backref": "derived_templates"  # Creates a back-reference to access child templates
        },
        # description="Reference to the parent prompt template this was derived from (for templates)"
    )

    # Relationship (Optional loading)
    # owner_org: Optional["Organization"] = Relationship()

# --- SchemaTemplate Model --- #
class SchemaTemplate(SQLModel, table=True):
    """Stores reusable schema templates (e.g., for structured output), system or org-owned."""
    __tablename__ = f"{table_prefix}schema_template"
    __table_args__ = (
        # Similar unique constraints as PromptTemplate
        Index(f'{table_prefix}schema_template_org_name_version_idx', 'owner_org_id', 'name', 'version', unique=True),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    name: str = Field(index=True, description="Name of the schema template")
    version: Optional[str] = Field(default=None, nullable=True, index=True, description="Version string")
    description: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    schema_definition: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True), description="The JSON schema definition")
    # TODO: implement support for JSON Schema which can be converted to Pydantic models using: https://github.com/koxudaxi/datamodel-code-generator
    #     https://koxudaxi.github.io/datamodel-code-generator/using_as_module/
    schema_type: SchemaType = Field(index=True, default=SchemaType.JSON_SCHEMA, description="Type of schema (e.g., 'json_schema')") # Could be enum later

    owner_org_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}org.id", ondelete="CASCADE"), nullable=True, index=True),
        description="Org owner if not a system template"
    )
    is_system_entity: Optional[bool] = Field(default=False, index=True, nullable=True, description="True if this is a KiwiQ system template, only meant to be used by KiwiQ application.")
    is_public: Optional[bool] = Field(default=False, index=True, nullable=True, description="True if this is a public template, available to all users.")

    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc))

    # Relationship (Optional loading)
    # owner_org: Optional["Organization"] = Relationship()


# --- UserNotification Model --- #
class UserNotification(SQLModel, table=True):
    """Stores notifications generated for specific users related to workflow events or system messages."""
    __tablename__ = f"{table_prefix}user_notification"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: Optional[uuid.UUID] = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}user.id", ondelete="CASCADE"), nullable=True, index=True),
        description="The user receiving the notification"
    )
    org_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}org.id", ondelete="SET NULL"), nullable=True, index=True),
        description="The organization context for the notification"
    )
    related_run_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{table_prefix}workflow_run.id", ondelete="CASCADE"), nullable=True, index=True),
        description="Optional link to the relevant workflow run"
    )
    notification_type: NotificationType = Field(
        sa_column=Column(SQLAlchemyEnum(NotificationType, name=f"{table_prefix}notification_type_enum"), nullable=False, index=True),
        description="The type of notification (e.g., run completion, HITL request)"
    )
    message: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="The content of the notification (e.g., summary, link, details)"
    )
    is_read: bool = Field(default=False, index=True, description="Whether the notification has been read by the user")
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    read_at: Optional[datetime] = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True), description="Timestamp when the notification was marked as read")

    # Relationships (Loaded on demand)
    user: "User" = Relationship(
        sa_relationship_kwargs={
            # "lazy": "select"
        }
    )
    organization: "Organization" = Relationship(
        sa_relationship_kwargs={
            # "lazy": "select"
        }
    )
    workflow_run: Optional["WorkflowRun"] = Relationship(
        sa_relationship_kwargs={
            # "lazy": "select"
        }
    )


# --- HITLJob Model --- #
class HITLJob(SQLModel, table=True):
    """Represents a Human-in-the-Loop (HITL) task waiting for user input within a workflow run."""
    __tablename__ = f"{table_prefix}hitl_job"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    requesting_run_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{table_prefix}workflow_run.id", ondelete="CASCADE"), nullable=True, index=True),
        description="The workflow run that requested human input"
    )
    assigned_user_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}user.id", ondelete="SET NULL"), nullable=True, index=True),
        description="The specific user assigned to this job (if any)"
    )
    # TODO: Consider adding assigned_group_id or role if assignment is not always to a specific user
    org_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}org.id", ondelete="CASCADE"), nullable=True, index=True),
        description="The organization context for this job"
    )
    status: HITLJobStatus = Field(
        sa_column=Column(SQLAlchemyEnum(HITLJobStatus, name=f"{table_prefix}hitl_job_status_enum"), nullable=False, index=True),
        default=HITLJobStatus.PENDING,
        description="The current status of the HITL job"
    )
    request_details: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="Information presented to the user (e.g., question, context, previous data)"
    )
    response_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Optional JSON schema defining the expected response format"
    )
    response_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="The data provided by the user in response to the job"
    )
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    responded_at: Optional[datetime] = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True), description="Timestamp when the user responded")
    expires_at: Optional[datetime] = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True), description="Optional deadline for the response")

    # Relationships
    # Add back_populates if needed on WorkflowRun, User, Organization
    workflow_run: "WorkflowRun" = Relationship(
        sa_relationship_kwargs={
            # "lazy": "select"
        }
    )
    assigned_user: Optional["User"] = Relationship(
        sa_relationship_kwargs={
            # "lazy": "select"
        }
    )
    organization: "Organization" = Relationship(
        sa_relationship_kwargs={
            # "lazy": "select"
        }
    )


class Asset(SQLModel, table=True):
    """Represents a reusable asset owned by an organization and managed by a user."""
    __tablename__ = f"{table_prefix}asset"
    __table_args__ = (
        # Ensure unique asset names within an org for a given type
        UniqueConstraint('org_id', 'asset_type', 'asset_name', name=f'{table_prefix}asset_org_type_name_uc'),
        # Index for common queries
        Index(f'{table_prefix}asset_org_managing_user_idx', 'org_id', 'managing_user_id'),
        Index(f'{table_prefix}asset_type_active_idx', 'asset_type', 'is_active'),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    asset_type: str = Field(index=True, description="Type of the asset (e.g., 'document_template', 'data_source')")
    asset_name: str = Field(index=True, description="Name of the asset, unique within org+type")
    is_shared: bool = Field(default=True, index=True, description="Whether the asset is shared within the organization")
    org_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}org.id", ondelete="CASCADE"), nullable=False, index=True),
        description="Organization that owns this asset"
    )
    managing_user_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}user.id", ondelete="RESTRICT"), nullable=False, index=True),
        description="User who manages this asset"
    )
    is_active: bool = Field(default=True, index=True, description="Whether the asset is currently active")
    app_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Application-specific data for the asset, validated by asset type schemas"
    )
    
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True))
    updated_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc, index=True))

    # Relationships
    organization: "Organization" = Relationship()
    managing_user: "User" = Relationship()


class UserAppResumeMetadata(SQLModel, table=True):
    """Stores metadata for resuming user application state."""
    __tablename__ = f"{table_prefix}user_app_resume_metadata"
    __table_args__ = (
        # Composite index for common query patterns
        Index(f'{table_prefix}user_app_resume_org_user_idx', 'org_id', 'user_id'),
        Index(f'{table_prefix}user_app_resume_workflow_idx', 'workflow_name', 'user_id'),
        Index(f'{table_prefix}user_app_resume_asset_idx', 'asset_id', 'user_id'),
        Index(f'{table_prefix}user_app_resume_tag_idx', 'entity_tag', 'user_id'),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    org_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}org.id", ondelete="CASCADE"), nullable=False, index=True),
        description="Organization context for this metadata"
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{auth_table_prefix}user.id", ondelete="CASCADE"), nullable=False, index=True),
        description="User who owns this metadata"
    )
    
    # At least one of these identifiers must be present
    workflow_name: Optional[str] = Field(default=None, nullable=True, index=True, description="Associated workflow name")
    asset_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{table_prefix}asset.id", ondelete="CASCADE"), nullable=True, index=True),
        description="Associated asset ID"
    )
    entity_tag: Optional[str] = Field(default=None, nullable=True, index=True, description="Entity tag for grouping/filtering")
    frontend_stage: Optional[str] = Field(default=None, nullable=True, index=True, description="Frontend application stage/state")
    
    # At least one of these data fields must be present
    run_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey(f"{table_prefix}workflow_run.id", ondelete="SET NULL"), nullable=True, index=True),
        description="Associated workflow run ID"
    )
    app_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Additional metadata for resuming application state"
    )
    
    created_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=datetime_now_utc, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, onupdate=datetime_now_utc))

    # Relationships
    organization: "Organization" = Relationship()
    user: "User" = Relationship()
    asset: Optional["Asset"] = Relationship()
    workflow_run: Optional["WorkflowRun"] = Relationship()


# --- Update Forward Refs --- #
# Needed for relationships defined using string type hints if classes are defined out of order
# Make sure all models referencing others are included.
# Note: Relationships TO auth models don't require rebuild here, but relationships FROM auth models TO workflow models
# would require rebuilding the auth models after workflow models are defined (if not using strings).
NodeTemplate.model_rebuild()
Workflow.model_rebuild()
WorkflowConfigOverride.model_rebuild()
WorkflowRun.model_rebuild()
PromptTemplate.model_rebuild()
SchemaTemplate.model_rebuild()
UserNotification.model_rebuild()
HITLJob.model_rebuild()
ChatThread.model_rebuild()
Asset.model_rebuild()
UserAppResumeMetadata.model_rebuild()

# TODO: FIXME
# --- Add back_populates to Auth Models (Requires modifying auth/models.py) --- #
# In kiwi_app/auth/models.py:
#
# class Organization(SQLModel, table=True):
#    ... existing fields ...
#    # Add relationship to workflows owned by this org
#    workflows: List["Workflow"] = Relationship(back_populates="owner_org", sa_relationship_kwargs={"cascade": "all, delete-orphan"}) # Cascade delete workflows if org deleted
#    # Add relationships for notifications and HITL jobs
#    user_notifications: List["UserNotification"] = Relationship(back_populates="organization")
#    hitl_jobs: List["HITLJob"] = Relationship(back_populates="organization")
#
# class User(SQLModel, table=True):
#    ... existing fields ...
#    # Add relationships for notifications and HITL jobs
#    user_notifications: List["UserNotification"] = Relationship(back_populates="user")
#    assigned_hitl_jobs: List["HITLJob"] = Relationship(back_populates="assigned_user")
#
# Need to add `Workflow`, `UserNotification`, `HITLJob` to the forward ref imports 
# in auth/models.py and call Organization.model_rebuild() and User.model_rebuild() there.
# Similarly for User if `created_by`/`updated_by` relationships are added with back_populates.
#
# In kiwi_app/workflow_app/models.py (WorkflowRun):
#    # Optional: Add back-population from HITLJob and UserNotification
#    hitl_jobs: List["HITLJob"] = Relationship(back_populates="workflow_run")
#    notifications: List["UserNotification"] = Relationship(back_populates="workflow_run")
