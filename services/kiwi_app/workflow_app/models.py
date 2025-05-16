"""SQLModel definitions for the Workflow Application."""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal

from sqlalchemy import String as SQLAlchemyString, Text, JSON, Boolean, Index, ForeignKey, Enum as SQLAlchemyEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
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

    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=datetime_now_utc, nullable=False, sa_column_kwargs={"onupdate": datetime_now_utc})

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
        foreign_key=f"{auth_table_prefix}org.id", # Use full path to auth org table
        index=True,
        nullable=True,
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
        foreign_key=f"{auth_table_prefix}user.id", # Full path to auth user table
        nullable=True
    )

    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=datetime_now_utc, nullable=False, sa_column_kwargs={"onupdate": datetime_now_utc})

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

# --- WorkflowRun Model --- #
class WorkflowRun(SQLModel, table=True):
    """Represents an execution instance of a Workflow."""
    __tablename__ = f"{table_prefix}workflow_run"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True, description="Unique ID for this specific run")
    thread_id: Optional[uuid.UUID] = Field(default=None, nullable=True, index=True, description="Associated thread ID (e.g., from LangGraph) for shared memory across runs")
    workflow_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{table_prefix}workflow.id", 
        index=True,
        nullable=True,
        description="Reference to the parent workflow"
    )
    workflow_name: Optional[str] = Field(
        default=None,
        nullable=True,
        index=True,
        description="Key name of the workflow"
    )
    owner_org_id: uuid.UUID = Field(
        foreign_key=f"{auth_table_prefix}org.id", # Full path to auth org table
        index=True,
        description="Denormalized Org ID for easier run querying"
    )
    triggered_by_user_id: Optional[uuid.UUID] = Field(
        # default=None,
        foreign_key=f"{auth_table_prefix}user.id", # Full path to auth user table
        nullable=True,  # Explicitly nullable
        index=True
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

    started_at: Optional[datetime] = Field(default=None, nullable=True)
    ended_at: Optional[datetime] = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=datetime_now_utc, nullable=False, sa_column_kwargs={"onupdate": datetime_now_utc})

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
        foreign_key=f"{auth_table_prefix}org.id", # Full path to auth org table
        nullable=True,
        index=True,
        description="Org owner if not a system template"
    )
    is_system_entity: Optional[bool] = Field(default=False, index=True, nullable=True, description="True if this is a KiwiQ system template, only meant to be used by KiwiQ application.")
    is_public: Optional[bool] = Field(default=False, index=True, nullable=True, description="True if this is a public template, available to all users.")

    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=datetime_now_utc, nullable=False, sa_column_kwargs={"onupdate": datetime_now_utc})

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
        foreign_key=f"{auth_table_prefix}org.id", # Full path to auth org table
        nullable=True,
        index=True,
        description="Org owner if not a system template"
    )
    is_system_entity: Optional[bool] = Field(default=False, index=True, nullable=True, description="True if this is a KiwiQ system template, only meant to be used by KiwiQ application.")
    is_public: Optional[bool] = Field(default=False, index=True, nullable=True, description="True if this is a public template, available to all users.")

    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=datetime_now_utc, nullable=False, sa_column_kwargs={"onupdate": datetime_now_utc})

    # Relationship (Optional loading)
    # owner_org: Optional["Organization"] = Relationship()


# --- UserNotification Model --- #
class UserNotification(SQLModel, table=True):
    """Stores notifications generated for specific users related to workflow events or system messages."""
    __tablename__ = f"{table_prefix}user_notification"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: uuid.UUID = Field(
        foreign_key=f"{auth_table_prefix}user.id", 
        index=True,
        description="The user receiving the notification"
    )
    org_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{auth_table_prefix}org.id",
        nullable=True,
        index=True,
        description="The organization context for the notification"
    )
    related_run_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{table_prefix}workflow_run.id",
        nullable=True,
        index=True,
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
    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)
    read_at: Optional[datetime] = Field(default=None, nullable=True, description="Timestamp when the notification was marked as read")

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
        foreign_key=f"{table_prefix}workflow_run.id",
        index=True,
        nullable=True,
        description="The workflow run that requested human input"
    )
    assigned_user_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{auth_table_prefix}user.id",
        nullable=True,
        index=True,
        description="The specific user assigned to this job (if any)"
    )
    # TODO: Consider adding assigned_group_id or role if assignment is not always to a specific user
    org_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key=f"{auth_table_prefix}org.id",
        index=True,
        nullable=True,
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
    created_at: datetime = Field(default_factory=datetime_now_utc, nullable=False)
    responded_at: Optional[datetime] = Field(default=None, nullable=True, description="Timestamp when the user responded")
    expires_at: Optional[datetime] = Field(default=None, nullable=True, description="Optional deadline for the response")

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

# --- Update Forward Refs --- #
# Needed for relationships defined using string type hints if classes are defined out of order
# Make sure all models referencing others are included.
# Note: Relationships TO auth models don't require rebuild here, but relationships FROM auth models TO workflow models
# would require rebuilding the auth models after workflow models are defined (if not using strings).
NodeTemplate.model_rebuild()
Workflow.model_rebuild()
WorkflowRun.model_rebuild()
PromptTemplate.model_rebuild()
SchemaTemplate.model_rebuild()
UserNotification.model_rebuild()
HITLJob.model_rebuild()

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
