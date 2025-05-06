"""
Pydantic models for App Artifacts API requests and responses.
These are based on the models defined in services/kiwi_app/workflow_app/app_artifacts.py.
"""
import uuid
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field

# --- Request/Response Models for API Endpoints ---


# # --- Core Pydantic Models ---

# --- Request/Response Models for API Endpoints (Modified) ---

class GetWorkflowRequest(BaseModel):
    workflow_key: str = Field(..., description="The key of the workflow to process from default configurations.")
    override_variables: Optional[Union[Dict[str, Any], Dict[str, Dict[str, Any]]]] = Field(
        None,
        description="Optional override for user_documents_config_variables of the selected workflow."
    )
    override_template_specific: Optional[bool] = Field(
        None,
        description="Optional override for template_specific flag of the selected workflow."
    )

class GetWorkflowResponse(BaseModel):
    original_workflow_name: str
    original_workflow_version: Optional[str]
    processed_inputs: Dict[str, Any]
    messages: List[str] = Field(default_factory=list)

class GetBuiltDocConfigsRequest(BaseModel):
    doc_keys: List[str] = Field(..., description="List of document keys to build from default UserDocumentsConfig.")
    variables: Union[Dict[str, Any], Dict[str, Dict[str, Any]]] = Field(
        ..., 
        description="Variables for building templates. Structure depends on 'template_specific_variables' flag."
    )
    template_specific_variables: bool = Field(
        False, 
        description="If True, 'variables' is a Dict[doc_key, Dict[var_name, value]]. Else, flat Dict applied to all."
    )
    partial_build: bool = Field(False, description="If true, performs a partial build allowing missing variables.")
    # documents_config removed, will use DEFAULT_USER_DOCUMENTS_CONFIG

class BuiltDocConfigItem(BaseModel):
    doc_key: str
    built_config: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class BuiltDocConfigsResponse(BaseModel):
    results: List[BuiltDocConfigItem]
    messages: List[str] = Field(default_factory=list)

class DocConfigsInfoRequest(BaseModel):
    doc_keys: Optional[List[str]] = Field(None, description="List of document keys from default UserDocumentsConfig to get info for. If None, all.")
    # documents_config removed

class DocConfigInfoItem(BaseModel):
    doc_key: str
    info: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class DocConfigsInfoResponse(BaseModel):
    results: List[DocConfigInfoItem]

class WorkflowInfoRequest(BaseModel):
    workflow_key: str = Field(..., description="The key of the workflow to get info for from default configurations.")
    # workflow_definition removed
    # documents_config removed

class WorkflowInfoResponse(BaseModel):
    workflow_name: str
    workflow_version: Optional[str]
    unresolved_inputs_analysis: Dict[str, Any]
