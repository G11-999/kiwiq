"""Pydantic schemas for Workflow Service API interaction."""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Union, Sequence
from pydantic import BaseModel, Field, validator, ConfigDict, field_validator, model_validator

from kiwi_app.workflow_app.constants import LaunchStatus, WorkflowRunStatus, NotificationType, HITLJobStatus, SchemaType
# Import base User/Org schemas if needed for nesting, or use full models if simpler
from kiwi_app.auth.schemas import UserRead, OrganizationRead
# Import GraphSchema for type hinting if needed, but graph_config will be stored as Dict
from workflow_service.graph.graph import GraphSchema
# Import event schemas for detailing run results
from workflow_service.services import events as event_schemas

# --- NodeTemplate Schemas --- #

class NodeTemplateBase(BaseModel):
    """Base schema for NodeTemplate."""
    name: str = Field(..., description="Unique name identifying the node type (e.g., 'llm_generator')")
    version: str = Field(..., description="Version string (e.g., '1.0.0', 'latest')")
    description: Optional[str] = Field(None, description="Description of the node template")
    input_schema: Optional[Dict[str, Any]] = Field(None, description="JSON Schema for inputs")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="JSON Schema for outputs")
    config_schema: Optional[Dict[str, Any]] = Field(None, description="JSON Schema for node configuration")
    launch_status: LaunchStatus = Field(..., description="Deployment status of the node template")

class NodeTemplateCreate(NodeTemplateBase):
    """Schema for creating a NodeTemplate (Admin only)."""
    pass # Inherits all fields from base

class NodeTemplateUpdate(BaseModel):
    """Schema for updating a NodeTemplate (Admin only). Allows partial updates."""
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    config_schema: Optional[Dict[str, Any]] = None
    launch_status: Optional[LaunchStatus] = None

class NodeTemplateRead(NodeTemplateBase):
    """Schema for reading a NodeTemplate."""
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Workflow Schemas --- #

class WorkflowBase(BaseModel):
    """Base schema for Workflow."""
    name: str = Field(..., min_length=1, description="User-defined name for the workflow")
    description: Optional[str] = Field(None, description="Description of the workflow")
    graph_config: Dict[str, Any] = Field(..., description="The core definition of the workflow graph (nodes, edges, etc.)")
    version_tag: Optional[str] = Field(None, description="User-defined tag for versioning (e.g., 'v1.2-stable')")
    is_template: Optional[bool] = Field(default=False, description="Indicates if this workflow can be used as a template within the org")
    launch_status: Optional[LaunchStatus] = Field(default=LaunchStatus.DEVELOPMENT, description="Deployment status of the workflow")
    is_public: Optional[bool] = Field(default=False, description="Indicates if this workflow is publicly accessible")

class WorkflowCreate(WorkflowBase):
    """Schema for creating a new Workflow."""
    parent_base_id: Optional[uuid.UUID] = None

class WorkflowUpdate(WorkflowBase):
    """Schema for updating an existing Workflow. Allows partial updates."""
    # set both the below fields as Optional!
    name: Optional[str] = Field(None, min_length=1, description="User-defined name for the workflow")
    graph_config: Optional[Dict[str, Any]] = Field(None, description="The core definition of the workflow graph (nodes, edges, etc.)")

class WorkflowRead(WorkflowBase):
    """Schema for reading a Workflow, including owner info."""
    id: uuid.UUID
    owner_org_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime
    created_by_user_id: Optional[uuid.UUID] = None
    parent_base_id: Optional[uuid.UUID] = None

    model_config = ConfigDict(from_attributes=True)


# --- WorkflowRun Schemas --- #

class WorkflowRunBase(BaseModel):
    """Base schema for WorkflowRun."""
    status: WorkflowRunStatus
    inputs: Optional[Dict[str, Any]] = Field(None, description="Inputs provided when the run was triggered")
    outputs: Optional[Dict[str, Any]] = Field(None, description="High-level final outputs or summary")
    error_message: Optional[str] = None
    detailed_results_ref: Optional[str] = Field(None, description="Reference to detailed logs/results (e.g., NoSQL collection/path)")
    thread_id: Optional[uuid.UUID] = Field(None, description="Associated thread ID (e.g., from LangGraph)")
    # resume_from_checkpoint: Optional[bool] = Field(default=False, description="Whether to resume from a checkpoint")


class WorkflowRunCreate(BaseModel):
    """Schema used internally or by other services to create a run record."""
    run_id: Optional[uuid.UUID] = None
    workflow_id: Optional[uuid.UUID] = None
    inputs: Optional[Dict[str, Any]] = Field(None, description="Inputs to provide to the workflow run")
    # TODO: add checkpoint ID as well for resume!
    thread_id: Optional[uuid.UUID] = Field(None, description="Optional existing thread ID to reuse")
    graph_schema: Optional[GraphSchema] = None
    resume_after_hitl: Optional[bool] = False
    force_resume_experimental_option: Optional[bool] = Field(default=False, description="Experimental option to force resume after HITL even if not in WAITING_HITL state or without pending HITL jobs!")

class WorkflowRunJobCreate(WorkflowRunCreate):
    """Schema used specifically to trigger a new run."""
    owner_org_id: uuid.UUID
    triggered_by_user_id: Optional[uuid.UUID] = None
    status: Optional[WorkflowRunStatus] = Field(default=WorkflowRunStatus.SCHEDULED)

    # @model_validator(mode='before')
    # @classmethod
    # def check_workflow_or_graph(cls, values):
    #     workflow_id, graph_schema = values.get('workflow_id'), values.get('graph_schema')
    #     if workflow_id is None and graph_schema is None:
    #         raise ValueError('Either workflow_id or graph_schema must be provided.')
    #     if workflow_id is not None and graph_schema is not None:
    #         raise ValueError('Provide either workflow_id or graph_schema, not both.')
    #     return values

class WorkflowRunUpdate(BaseModel):
    """Schema for internal updates to a WorkflowRun (e.g., status, outputs)."""
    run_id: uuid.UUID
    status: Optional[WorkflowRunStatus] = None
    outputs: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    detailed_results_ref: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    thread_id: Optional[uuid.UUID] = None

class WorkflowRunRead(WorkflowRunBase):
    """Schema for reading a WorkflowRun summary (SQL data mainly)."""
    id: uuid.UUID
    workflow_id: uuid.UUID
    owner_org_id: uuid.UUID
    triggered_by_user_id: Optional[uuid.UUID] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Define a type for the detailed_results (list of events from MongoDB)
WorkflowRunEventDetail = Union[event_schemas.WorkflowRunNodeOutputEvent, event_schemas.WorkflowRunStatusUpdateEvent, event_schemas.MessageStreamChunk, event_schemas.HITLRequestEvent, Dict[str, Any]]

class WorkflowRunDetailRead(WorkflowRunRead):
    """Schema for reading detailed WorkflowRun results (combines SQL + NoSQL data)."""
    detailed_results: Optional[List[WorkflowRunEventDetail]] = Field(None, description="Detailed run events fetched from external store (MongoDB)")


# --- PromptTemplate Schemas --- #

class PromptTemplateBase(BaseModel):
    """Base schema for PromptTemplate."""
    name: str = Field(..., description="Name of the prompt template (unique within org/system context)")
    version: Optional[str] = Field(None, description="Version string (e.g., '1.0', 'latest')")
    description: Optional[str] = Field(None, description="Description of the prompt template")
    template_content: str = Field(..., description="The prompt template string (e.g., Jinja2 format)")
    input_variables: Optional[Dict[str, Any]] = Field(None, description="Dictionary of expected input variables and optional defaults")

class PromptTemplateCreate(PromptTemplateBase):
    """Schema for creating an organization-specific PromptTemplate."""
    pass

class PromptTemplateUpdate(BaseModel):
    """Schema for updating an organization-specific PromptTemplate."""
    name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    template_content: Optional[str] = None
    input_variables: Optional[Dict[str, Any]] = None
    # parent_base_id: Optional[uuid.UUID] = None

class PromptTemplateRead(PromptTemplateBase):
    """Schema for reading a PromptTemplate."""
    id: uuid.UUID
    owner_org_id: Optional[uuid.UUID] = None
    is_system_template: bool
    # parent_base_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- SchemaTemplate Schemas --- #

class SchemaTemplateBase(BaseModel):
    """Base schema for SchemaTemplate."""
    name: str = Field(..., description="Name of the schema template (unique within org/system context)")
    version: str = Field(..., description="Version string")
    description: Optional[str] = Field(None, description="Description of the schema template")
    schema_definition: Optional[Dict[str, Any]] = Field(None, description="The JSON schema definition")
    schema_type: SchemaType = Field(default=SchemaType.JSON_SCHEMA, description="Type of schema")

class SchemaTemplateCreate(SchemaTemplateBase):
    """Schema for creating an organization-specific SchemaTemplate."""
    pass

class SchemaTemplateUpdate(BaseModel):
    """Schema for updating an organization-specific SchemaTemplate."""
    name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    schema_definition: Optional[Dict[str, Any]] = None
    schema_type: Optional[SchemaType] = None

class SchemaTemplateRead(SchemaTemplateBase):
    """Schema for reading a SchemaTemplate."""
    id: uuid.UUID
    owner_org_id: Optional[uuid.UUID] = None
    is_system_template: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- UserNotification Schemas --- #

class UserNotificationBase(BaseModel):
    """Base schema for user notifications."""
    notification_type: NotificationType
    message: Dict[str, Any] = Field(..., description="Content of the notification")
    related_run_id: Optional[uuid.UUID] = None

class UserNotificationCreate(UserNotificationBase):
    """Schema used internally to create a notification."""
    user_id: uuid.UUID
    org_id: Optional[uuid.UUID]

class UserNotificationRead(UserNotificationBase):
    """Schema for reading a user notification."""
    id: uuid.UUID
    user_id: uuid.UUID
    org_id: Optional[uuid.UUID]
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# --- HITLJob Schemas --- #

class HITLJobBase(BaseModel):
    """Base schema for HITL jobs."""
    assigned_user_id: Optional[uuid.UUID] = None
    request_details: Dict[str, Any] = Field(..., description="Information presented to the user")
    response_schema: Optional[Dict[str, Any]] = Field(None, description="Optional expected response schema")
    expires_at: Optional[datetime] = None

class HITLJobCreate(HITLJobBase):
    """Schema used internally to create an HITL job (triggered by a workflow)."""
    requesting_run_id: Optional[uuid.UUID]
    org_id: Optional[uuid.UUID]
    status: HITLJobStatus = Field(default=HITLJobStatus.PENDING)

class HITLJobRespond(BaseModel):
    """Schema for a user responding to an HITL job."""
    response_data: Dict[str, Any] = Field(..., description="The user's response data")

class HITLJobRead(HITLJobBase):
    """Schema for reading an HITL job."""
    id: uuid.UUID
    requesting_run_id: Optional[uuid.UUID]
    org_id: Optional[uuid.UUID]
    status: HITLJobStatus
    response_data: Optional[Dict[str, Any]] = None
    created_at: datetime
    responded_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class HITLJobCancel(BaseModel):
    """Schema for cancelling an HITL job (no body needed, ID from path)."""
    pass


# --- List Query Parameter Schemas --- #


class CommonListQuery(BaseModel):
    """Base query parameters for list endpoints."""
    skip: int = Field(0, ge=0, description="Number of items to skip")
    limit: int = Field(100, ge=1, le=200, description="Maximum number of items to return")


class WorkflowListQuery(CommonListQuery):
    """Query parameters for listing workflows."""
    owner_org_id: Optional[uuid.UUID] = Field(None, description="Filter by owning organization ID (Superuser only)")
    include_public: Optional[bool] = Field(True, description="Include public workflows in the results")


class WorkflowRunListQuery(CommonListQuery):
    """Query parameters for listing workflow runs."""
    workflow_id: Optional[uuid.UUID] = Field(None, description="Filter runs by workflow ID")
    status: Optional[WorkflowRunStatus] = Field(None, description="Filter runs by status")
    triggered_by_user_id: Optional[uuid.UUID] = Field(None, description="Filter runs by triggering user ID (Superuser only)")
    owner_org_id: Optional[uuid.UUID] = Field(None, description="Filter by owning organization ID (Superuser only)")


class HITLJobListQuery(CommonListQuery):
    """Query parameters for listing HITL jobs."""
    run_id: Optional[uuid.UUID] = Field(None, description="Filter by requesting run ID")
    assigned_user_id: Optional[uuid.UUID] = Field(None, description="Filter by assigned user ID ('me' for current user, uuid.UUID for specific user)")
    status: Optional[HITLJobStatus] = Field(None, description="Filter by job status")
    pending_only: Optional[bool] = Field(None, description="If true, only returns PENDING jobs")
    exclude_cancelled: Optional[bool] = Field(True, description="If true (default), excludes CANCELLED jobs")
    owner_org_id: Optional[uuid.UUID] = Field(None, description="Filter by owning organization ID (Superuser only)")


class NotificationListQuery(CommonListQuery):
    """Query parameters for listing notifications."""
    is_read: Optional[bool] = Field(None, description="Filter by read status (true=read, false=unread, null=all)")
    sort_by: str = Field("created_at", description="Field to sort by")
    sort_order: str = Field("desc", description="Sort order ('asc' or 'desc')")


class NodeTemplateListQuery(CommonListQuery):
    """Query parameters for listing node templates."""
    launch_status: Optional[List[LaunchStatus]] = Field(
        default=[LaunchStatus.DEVELOPMENT, LaunchStatus.STAGING, LaunchStatus.PRODUCTION], 
        description="Filter by one or more launch statuses"
    )


class PromptTemplateListQuery(CommonListQuery):
    """Query parameters for listing prompt templates."""
    owner_org_id: Optional[uuid.UUID] = Field(None, description="Filter by owning organization ID (Superuser only)")
    include_system: bool = Field(True, description="Include system templates")


class SchemaTemplateListQuery(CommonListQuery):
    """Query parameters for listing schema templates."""
    owner_org_id: Optional[uuid.UUID] = Field(None, description="Filter by owning organization ID (Superuser only)")
    include_system: bool = Field(True, description="Include system templates")
