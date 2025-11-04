from datetime import datetime

from typing import Any, Dict, Optional, Literal
import uuid
from pydantic import BaseModel

from langchain_core.messages import AnyMessage
from enum import Enum

from kiwi_app.workflow_app.constants import WorkflowRunStatus


class WorkflowEvent(str, Enum):
    NODE_OUTPUT = "node_output"
    MESSAGE_CHUNK = "message_chunk"
    WORKFLOW_RUN_STATUS = "workflow_run_status"
    HITL_REQUEST = "hitl_request"
    TOOL_CALL = "tool_call"
    NODE_STATUS = "node_status"


class WorkflowBaseEvent(BaseModel):
    run_id: uuid.UUID
    parent_run_id: Optional[uuid.UUID] = None
    event_id: uuid.UUID
    user_id: uuid.UUID
    org_id: uuid.UUID
    sequence_i: int
    event_type: WorkflowEvent
    node_id: Optional[str] = None
    node_name: Optional[str] = None
    timestamp: Optional[datetime] = None
    payload: Optional[Dict[str, Any]] = None


class HITLRequestEvent(WorkflowBaseEvent):
    """Event emitted when a node outputs data."""
    event_type: WorkflowEvent = WorkflowEvent.HITL_REQUEST
    request_data_schema: Dict[str, Any]
    user_prompt: Dict[str, Any]


class WorkflowRunNodeOutputEvent(WorkflowBaseEvent):
    """Event emitted when a node outputs data."""
    event_type: WorkflowEvent = WorkflowEvent.NODE_OUTPUT


class ToolCallEvent(WorkflowBaseEvent):
    """Event emitted when a tool call is made."""
    event_type: WorkflowEvent = WorkflowEvent.TOOL_CALL
    tool_call_id: str
    tool_name: str
    status: str

class NodeStatusEvent(WorkflowBaseEvent):
    """Event emitted when a node status changes."""
    event_type: WorkflowEvent = WorkflowEvent.NODE_STATUS
    status: str


class MessageStreamChunk(WorkflowBaseEvent):
    """Event emitted when a node outputs a message chunk."""
    event_type: WorkflowEvent = WorkflowEvent.MESSAGE_CHUNK
    message: AnyMessage


class WorkflowRunStatusUpdateEvent(WorkflowBaseEvent):
    """Event emitted when a workflow run status changes."""
    event_type: WorkflowEvent = WorkflowEvent.WORKFLOW_RUN_STATUS
    status: WorkflowRunStatus
    error_message: Optional[str] = None
