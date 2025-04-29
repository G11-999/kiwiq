"""Pydantic schemas for Workflow Service API interaction."""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Union, Sequence
from pydantic import BaseModel, Field, validator, ConfigDict, field_validator, model_validator
from enum import Enum

# from kiwi_app.workflow_app.constants import LaunchStatus, WorkflowRunStatus, NotificationType, HITLJobStatus, SchemaType
from kiwi_client.schemas.workflow_constants import LaunchStatus, WorkflowRunStatus, NotificationType, HITLJobStatus, SchemaType

# from workflow_service.graph.graph import GraphSchema
from kiwi_client.schemas.graph_schema import GraphSchema

# Import event schemas for detailing run results
# from workflow_service.services import events as event_schemas
from kiwi_client.schemas import events_schema as event_schemas


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
    is_system_entity: Optional[bool] = Field(default=False, description="Indicates if this workflow is a system entity. Only admins can create system workflows.")

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


# -- Graph Validation --
class WorkflowGraphValidationResult(BaseModel):
    """Schema for graph validation results."""
    is_valid: bool = Field(..., description="Whether the graph is valid overall")
    graph_schema_valid: bool = Field(..., description="Whether the graph schema structure is valid")
    node_configs_valid: bool = Field(..., description="Whether all node configurations are valid")
    errors: Dict[str, List[str]] = Field(default_factory=dict, description="Validation errors by category/node")


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
    force_resume_experimental_option: Optional[bool] = Field(default=False, description="Experimental option to force resume after HITL even if not in WAITING_HITL state or without pending HITL jobs! (Use with caution!)")
    on_behalf_of_user_id: Optional[uuid.UUID] = Field(None, description="User ID to act on behalf of (requires superuser privileges)")


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
    workflow_id: Optional[uuid.UUID] = None
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
    is_system_entity: Optional[bool] = Field(default=False, description="Indicates if this prompt template is a system entity. Only system admins can create system templates.")

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
    is_system_entity: bool
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
    is_public: Optional[bool] = Field(default=False, description="Whether the schema is public (system templates only)")

class SchemaTemplateCreate(SchemaTemplateBase):
    """Schema for creating an organization-specific SchemaTemplate."""
    is_system_entity: Optional[bool] = Field(default=False, description="Indicates if this schema template is a system entity. Only system admins can create system templates.")

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
    is_system_entity: bool
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
    get_notifications_for_all_user_orgs: Optional[bool] = Field(False, description="If true, get notifications for all user organizations")


class NodeTemplateListQuery(CommonListQuery):
    """Query parameters for listing node templates."""
    launch_status: Optional[List[LaunchStatus]] = Field(
        default=[LaunchStatus.DEVELOPMENT, LaunchStatus.STAGING, LaunchStatus.PRODUCTION], 
        description="Filter by one or more launch statuses"
    )


class PromptTemplateListQuery(CommonListQuery):
    """Query parameters for listing prompt templates."""
    owner_org_id: Optional[uuid.UUID] = Field(None, description="Filter by owning organization ID (Superuser only)")
    include_system: bool = Field(False, description="Include system templates.")


class SchemaTemplateListQuery(CommonListQuery):
    """Query parameters for listing schema templates."""
    owner_org_id: Optional[uuid.UUID] = Field(None, description="Filter by owning organization ID (Superuser only)")
    include_system: bool = Field(False, description="Include system templates.")


class WorkflowSearchQuery(BaseModel):
    """Query parameters for searching workflows by name and version."""
    name: str = Field(..., description="Name of the workflow to search for")
    version_tag: Optional[str] = Field(None, description="Optional version tag to filter by")
    include_public: bool = Field(True, description="Include public workflows in the results")
    include_system_entities: bool = Field(False, description="Include system entities (superuser only)")
    include_public_system_entities: bool = Field(False, description="Include public system entities")


class PromptTemplateSearchQuery(BaseModel):
    """Query parameters for searching prompt templates by name and version."""
    name: str = Field(..., description="Name of the prompt template to search for")
    version: Optional[str] = Field(None, description="Optional version to filter by")
    include_public: bool = Field(True, description="Include public templates in the results")
    include_system_entities: bool = Field(False, description="Include system entities (superuser only)")
    include_public_system_entities: bool = Field(False, description="Include public system entities")


class SchemaTemplateSearchQuery(BaseModel):
    """Query parameters for searching schema templates by name and version."""
    name: str = Field(..., description="Name of the schema template to search for")
    version: Optional[str] = Field(None, description="Optional version to filter by")
    include_public: bool = Field(True, description="Include public templates in the results")
    include_system_entities: bool = Field(False, description="Include system entities (superuser only)")
    include_public_system_entities: bool = Field(False, description="Include public system entities")


# --- Customer Data Schemas ---

class CustomerDataVersionedInitialize(BaseModel):
    """
    Schema for initializing a customer data document.
    
    When is_system_entity=True, document is stored in system paths instead of 
    organization-specific paths. The is_shared parameter still applies normally 
    to determine if it's shared with the organization or user-specific.
    
    The on_behalf_of_user_id parameter only works with user-specific documents 
    and is ignored for system entities or shared documents.
    """
    is_shared: bool = Field(False, description="Set to true to create a document shared within the organization, false for a user-specific document.")
    initial_version: Optional[str] = Field(default="default", description="The initial version name for the document. Defaults to 'default'.")
    schema_template_name: Optional[str] = Field(None, description="Optional name of a SchemaTemplate to enforce.")
    schema_template_version: Optional[str] = Field(None, description="Optional version of the SchemaTemplate. Defaults to latest if name is provided but version is not.")
    initial_data: Optional[Any] = Field({}, description="Optional initial data for the document. Defaults to an empty object.")
    is_complete: Optional[bool] = Field(False, description="Mark the initial data as complete for validation.")
    is_system_entity: bool = Field(False, description="Whether this is a system entity (superusers only). When True, data is stored in system paths instead of organization-specific paths. The is_shared parameter still applies normally to determine if it's shared with the org or user-specific.")
    on_behalf_of_user_id: Optional[uuid.UUID] = Field(None, description="Optional user ID to act on behalf of (superusers only). Note: This parameter only works with user-specific documents and is ignored for system entities or shared documents.")


class CustomerDataVersionedUpdate(BaseModel):
    """
    Schema for updating customer data.
    
    When is_system_entity=True, document is updated in system paths instead of 
    organization-specific paths. The is_shared parameter still applies normally 
    to determine if it's shared with the organization or user-specific.
    
    The on_behalf_of_user_id parameter only works with user-specific documents 
    and is ignored for system entities or shared documents.
    """
    is_shared: bool = Field(False, description="Set to true to update a shared document, false for a user-specific document.")
    data: Any = Field(..., description="The data to update the document with. Can be a partial update for JSON objects or a full replacement for primitive types.")
    version: Optional[str] = Field(None, description="Specific version to update. If None, updates the active version.")
    is_complete: Optional[bool] = Field(None, description="Mark the document as complete after this update (for validation). Leave as None to keep current status.")
    schema_template_name: Optional[str] = Field(None, description="Optional: Name of a SchemaTemplate to update the document's schema with before applying the data update.")
    schema_template_version: Optional[str] = Field(None, description="Optional: Version of the SchemaTemplate. Defaults to latest if name is provided.")
    is_system_entity: bool = Field(False, description="Whether this is a system entity (superusers only). When True, data is accessed from system paths instead of organization-specific paths. The is_shared parameter still applies normally to determine if it's shared with the org or user-specific.")
    on_behalf_of_user_id: Optional[uuid.UUID] = Field(None, description="Optional user ID to act on behalf of (superusers only). Note: This parameter only works with user-specific documents and is ignored for system entities or shared documents.")


class CustomerDataRead(BaseModel):
    """Schema for reading customer data. Returns the data itself."""
    data: Any = Field(..., description="The customer data.")

    model_config = ConfigDict(from_attributes=True) # Allow creation from ORM/dict


class CustomerDataVersionInfo(BaseModel):
    """Schema representing metadata about a specific version."""
    version: str
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_complete: bool
    edit_count: int

    model_config = ConfigDict(from_attributes=True)


class CustomerDataVersionHistoryItem(BaseModel):
    """Schema representing an item in the version history."""
    timestamp: datetime
    sequence: int
    patch: str = Field(..., description="JSON Patch string representing the change.")
    is_primitive: bool = Field(..., description="Indicates if the change was a replacement of a primitive type.")

    model_config = ConfigDict(from_attributes=True)


class CustomerDataCreateVersion(BaseModel):
    """
    Schema for creating a new version (branching).
    
    When is_system_entity=True, document versions are created in system paths instead of 
    organization-specific paths. The is_shared parameter still applies normally 
    to determine if it's shared with the organization or user-specific.
    
    The on_behalf_of_user_id parameter only works with user-specific documents 
    and is ignored for system entities or shared documents.
    """
    is_shared: bool = Field(False, description="Set to true to create a new version for a shared document, false for a user-specific document.")
    new_version: str = Field(..., description="The name for the new version.")
    from_version: Optional[str] = Field(None, description="The version to branch from. If None, branches from the active version.")
    is_system_entity: bool = Field(False, description="Whether this is a system entity (superusers only). When True, data is accessed from system paths instead of organization-specific paths. The is_shared parameter still applies normally to determine if it's shared with the org or user-specific.")
    on_behalf_of_user_id: Optional[uuid.UUID] = Field(None, description="Optional user ID to act on behalf of (superusers only). Note: This parameter only works with user-specific documents and is ignored for system entities or shared documents.")


class CustomerDataSetActiveVersion(BaseModel):
    """
    Schema for setting the active version.
    
    When is_system_entity=True, document versions are accessed in system paths instead of 
    organization-specific paths. The is_shared parameter still applies normally 
    to determine if it's shared with the organization or user-specific.
    
    The on_behalf_of_user_id parameter only works with user-specific documents 
    and is ignored for system entities or shared documents.
    """
    is_shared: bool = Field(False, description="Set to true to set the active version for a shared document, false for a user-specific document.")
    version: str = Field(..., description="The version name to set as active.")
    is_system_entity: bool = Field(False, description="Whether this is a system entity (superusers only). When True, data is accessed from system paths instead of organization-specific paths. The is_shared parameter still applies normally to determine if it's shared with the org or user-specific.")
    on_behalf_of_user_id: Optional[uuid.UUID] = Field(None, description="Optional user ID to act on behalf of (superusers only). Note: This parameter only works with user-specific documents and is ignored for system entities or shared documents.")


class CustomerDataVersionedRestore(BaseModel):
    """
    Schema for restoring a document to a previous state.
    
    When is_system_entity=True, document is restored in system paths instead of 
    organization-specific paths. The is_shared parameter still applies normally 
    to determine if it's shared with the organization or user-specific.
    
    The on_behalf_of_user_id parameter only works with user-specific documents 
    and is ignored for system entities or shared documents.
    """
    is_shared: bool = Field(False, description="Set to true to restore a shared document, false for a user-specific document.")
    sequence: int = Field(..., ge=0, description="The sequence number to restore to.")
    version: Optional[str] = Field(None, description="The version to restore within. If None, uses the active version.")
    is_system_entity: bool = Field(False, description="Whether this is a system entity (superusers only). When True, data is accessed from system paths instead of organization-specific paths. The is_shared parameter still applies normally to determine if it's shared with the org or user-specific.")
    on_behalf_of_user_id: Optional[uuid.UUID] = Field(None, description="Optional user ID to act on behalf of (superusers only). Note: This parameter only works with user-specific documents and is ignored for system entities or shared documents.")


class CustomerDataSchemaUpdate(BaseModel):
    """
    Schema for explicitly updating the schema of a document.
    
    When is_system_entity=True, document schema is updated in system paths instead of 
    organization-specific paths. The is_shared parameter still applies normally 
    to determine if it's shared with the organization or user-specific.
    
    The on_behalf_of_user_id parameter only works with user-specific documents 
    and is ignored for system entities or shared documents.
    """
    is_shared: bool = Field(False, description="Set to true to update a shared document, false for a user-specific document.")
    schema_template_name: str = Field(..., description="Name of the SchemaTemplate to apply.")
    schema_template_version: Optional[str] = Field(None, description="Optional version of the SchemaTemplate. Defaults to latest if name is provided but version is not.")
    is_system_entity: bool = Field(False, description="Whether this is a system entity (superusers only). When True, data is accessed from system paths instead of organization-specific paths. The is_shared parameter still applies normally to determine if it's shared with the org or user-specific.")
    on_behalf_of_user_id: Optional[uuid.UUID] = Field(None, description="Optional user ID to act on behalf of (superusers only). Note: This parameter only works with user-specific documents and is ignored for system entities or shared documents.")


# --- Unversioned Customer Data Schemas ---

class CustomerDataUnversionedCreateUpdate(BaseModel):
    """
    Schema for creating or updating unversioned customer data.
    
    When is_system_entity=True, document is stored in system paths instead of 
    organization-specific paths. The is_shared parameter still applies normally 
    to determine if it's shared with the organization or user-specific.
    
    The on_behalf_of_user_id parameter only works with user-specific documents 
    and is ignored for system entities or shared documents.
    """
    is_shared: bool = Field(False, description="Set to true to create/update a shared document, false for user-specific.")
    data: Any = Field(..., description="The data for the document.")
    schema_template_name: Optional[str] = Field(None, description="Optional name of a SchemaTemplate to validate against.")
    schema_template_version: Optional[str] = Field(None, description="Optional version of the SchemaTemplate. Defaults to latest if name is provided.")
    is_system_entity: bool = Field(False, description="Whether this is a system entity (superusers only). When True, data is stored in system paths instead of organization-specific paths. The is_shared parameter still applies normally to determine if it's shared with the org or user-specific.")
    on_behalf_of_user_id: Optional[uuid.UUID] = Field(None, description="Optional user ID to act on behalf of (superusers only). Note: This parameter only works with user-specific documents and is ignored for system entities or shared documents.")


class CustomerDataUnversionedRead(BaseModel):
    """Schema for reading unversioned customer data."""
    data: Any = Field(..., description="The unversioned customer data.")
    # Include metadata if needed, e.g., last updated timestamp
    # updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# --- Document Listing Schema ---

class CustomerDocumentMetadata(BaseModel):
    """
    Schema representing metadata about a customer document (versioned or unversioned).
    
    For system entities (is_system_entity=True), the document is stored in system paths
    instead of organization-specific paths. The is_shared flag indicates whether the document
    is shared within the organization or specific to a user.
    """
    org_id: Optional[uuid.UUID] = None
    # scope: str # e.g., 'shared', 'user' - Replaced by user_id + is_shared logic
    user_id_or_shared_placeholder: str = Field(..., description="The user ID or '_shared_' placeholder.")
    namespace: str
    docname: str
    is_versioned: bool = Field(..., description="Indicates if this corresponds to a versioned document entry")
    is_shared: bool = Field(..., description="Indicates if this is a shared document path accessible by all users in the organization.")
    is_system_entity: bool = Field(False, description="Whether this is a system entity. When True, document is stored in system paths instead of organization-specific paths. The is_shared flag still determines if it's shared within the organization or user-specific.")
    # Add other relevant metadata like updated_at if available from the base client document
    # updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)



class CustomerDataVersionedUpsert(BaseModel):
    """
    Schema for upserting a versioned customer data document.
    Updates the document if it exists, otherwise initializes it.
    Can target a specific version or the active version.
    If updating a specific version that doesn't exist, it attempts to create it first.
    """
    is_shared: bool = Field(False, description="Target a shared document (true) or user-specific document (false).")
    data: Any = Field(..., description="The data to upsert into the document.")
    version: Optional[str] = Field(None, description="Specific version to target. If None, targets the active version for updates, or uses 'default' for initialization.")
    from_version: Optional[str] = Field(None, description="If 'version' is specified and doesn't exist, use this version to branch from when creating it. Defaults to active version if None.")
    is_complete: Optional[bool] = Field(None, description="Mark the document state as complete/incomplete after the operation. Applies to both updates and initializations. If None during update, keeps current status; if None during init, defaults to False.")
    schema_template_name: Optional[str] = Field(None, description="Optional name of a SchemaTemplate to enforce/apply.")
    schema_template_version: Optional[str] = Field(None, description="Optional version of the SchemaTemplate. Defaults to latest.")
    # schema_definition: Optional[Dict[str, Any]] = Field(None, description="Optional explicit schema definition (takes precedence over template). NOTE: Not typically exposed directly in API for security/simplicity, prefer templates.")
    is_system_entity: bool = Field(False, description="Target a system entity (superusers only).")
    on_behalf_of_user_id: Optional[uuid.UUID] = Field(None, description="Act on behalf of another user (superusers only, requires is_shared=False).")


class CustomerDocumentIdentifier(BaseModel):
    """
    Identifies a specific customer document, potentially including version info.
    Used to reconstruct the path or retrieve the document after an operation.
    """
    doc_path_segments: Dict[str, str] = Field(..., description="Core path segments (org/system, user/shared, namespace, docname).")
    operation_params: Dict[str, Any] = Field(..., description="Parameters used in the operation affecting the document (org_id, is_shared, etc.).")
    version: Optional[str] = Field(None, description="The specific version affected or created (can be 'active' or None).")


class CustomerDataVersionedUpsertResponse(BaseModel):
    """
    Response schema for the versioned document upsert operation.
    """
    operation_performed: str = Field(..., description="String indicating the action taken (e.g., 'updated_active', 'initialized_version_default').")
    document_identifier: CustomerDocumentIdentifier = Field(..., description="Identifier for the document that was upserted.")

    model_config = ConfigDict(from_attributes=True)


# --- File Upload Schemas ---

class FileUploadModeEnum(str, Enum):
    """Enum defining the modes for handling file uploads."""
    create = "create"
    upsert = "upsert"


class FileUploadVersionedConfig(BaseModel):
    """
    Configuration specific to versioned file uploads.
    These fields are only relevant if `is_versioned` is True in the main config.
    """
    version: Optional[str] = Field(None, description="Specific version to target for upsert/create. If None during upsert, targets active version. If None during create, uses 'default'.")
    from_version: Optional[str] = Field(None, description="Version to branch from if creating a new version during an 'upsert' operation when the target 'version' doesn't exist. Defaults to active version if None.")
    is_complete: Optional[bool] = Field(None, description="Mark the document state as complete/incomplete after the operation. Applies to both upserts and creations. If None during update, keeps current status; if None during create, defaults to False.")

    model_config = ConfigDict(extra='forbid') # Forbid extra fields


class FileUploadConfig(BaseModel):
    """
    Configuration for processing a single uploaded file and storing it as customer data.
    """
    namespace: str = Field("uploaded_files", description="Namespace where the document should be stored. Default is 'uploaded_files'.")
    docname: Optional[str] = Field(None, description="Document name. If None, it will be inferred from the uploaded filename.")
    is_shared: bool = Field(False, description="Set to true to store as a document shared within the organization, false for a user-specific document.")
    is_system_entity: bool = Field(False, description="Whether this is a system entity (superusers only).")
    on_behalf_of_user_id: Optional[uuid.UUID] = Field(None, description="Act on behalf of another user (superusers only, requires is_shared=False).")

    mode: FileUploadModeEnum = Field(FileUploadModeEnum.create, description="Upload mode: 'create' (fail if exists) or 'upsert' (create or update).")
    is_versioned: bool = Field(False, description="Whether to store the file content as a versioned document.")

    versioned_config: Optional[FileUploadVersionedConfig] = Field(None, description="Configuration for versioned uploads. Required if is_versioned is True.")

    @model_validator(mode='after')
    def check_versioned_config(self) -> 'FileUploadConfig':
        """Validate that versioned_config is provided if is_versioned is True."""
        if self.is_versioned and self.versioned_config is None:
            raise ValueError("`versioned_config` must be provided when `is_versioned` is True.")
        if not self.is_versioned and self.versioned_config is not None:
            # Optionally, you could clear it or raise an error. Clearing seems more robust.
            # raise ValueError("`versioned_config` should not be provided when `is_versioned` is False.")
            self.versioned_config = None # Clear it if provided unnecessarily
        return self

    model_config = ConfigDict(extra='forbid') # Forbid extra fields


# Optional: If you want to allow passing global defaults and per-file overrides in one request
class FileUploadRequestPayload(BaseModel):
    """
    Optional schema to allow specifying global defaults and per-file overrides
    in a single API request payload, potentially alongside the file uploads
    using multipart/form-data encoding (requires careful handling in the endpoint).
    """
    global_defaults: Optional[FileUploadConfig] = Field(default_factory=FileUploadConfig, description="Global default configuration to apply to all files unless overridden.")
    file_configs: Optional[Dict[str, FileUploadConfig]] = Field(None, description="Dictionary mapping original filenames to their specific configurations, overriding global defaults.")

    model_config = ConfigDict(extra='forbid')


class FileUploadValidationRequest(BaseModel):
    """
    Schema for the request of the file upload configuration validation endpoint.
    """
    payload: FileUploadRequestPayload = Field(default_factory=FileUploadRequestPayload, description="The payload containing global defaults and per-file configurations.")
    files: List[str] = Field(..., description="The files to upload.")


class FileUploadValidationResult(BaseModel):
    """
    Schema for the response of the file upload configuration validation endpoint.
    Indicates overall validity and lists any global or per-file errors found.
    """
    is_valid: bool = Field(..., description="True if all configurations and checks passed, False otherwise.")
    global_errors: List[str] = Field(default_factory=list, description="List of validation errors not specific to a single file (e.g., payload parsing). Empty if none.")
    file_errors: Dict[str, List[str]] = Field(default_factory=dict, description="Dictionary mapping filenames to a list of their specific validation errors. Empty if none.")

    model_config = ConfigDict(extra='forbid')
