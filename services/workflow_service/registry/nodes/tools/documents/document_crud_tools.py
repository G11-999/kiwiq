"""
Document CRUD Tools for LLM Integration

This module provides four essential tools for document operations within workflows:
1. EditDocumentTool - For editing a single document with various operation types
2. DocumentViewerTool - For viewing either a single document or listing documents
3. DocumentSearchTool - For searching documents with text queries
4. ListDocumentsTool - For listing documents with filters

All tools use DocumentIdentifier and DocumentListFilter schemas from document_crud_funcs.py
and automatically use the organization ID and user ID from the runtime context.
"""

import json
import uuid
import random
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional, Type, Union
from pydantic import BaseModel, Field, field_validator, model_validator, create_model
from pydantic.fields import FieldInfo


from kiwi_app.workflow_app.constants import LaunchStatus
from kiwi_app.workflow_app.schemas import (
    CustomerDocumentSearchResult,
    CustomerDocumentSearchResultMetadata,
    CustomerDocumentMetadata
)
from kiwi_app.workflow_app.service_customer_data import CustomerDataService
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY,
)
from workflow_service.registry.nodes.core.base import BaseNode
from workflow_service.registry.schemas.base import BaseNodeConfig, BaseSchema

# Import database session manager
from db.session import get_async_db_as_manager

# Import schemas from document_crud_funcs
from services.workflow_service.registry.nodes.tools.documents.document_crud_funcs import (
    DocumentIdentifier,
    DocumentListFilter,
    identify_document,
    build_list_query
)

# --- Common Helper Functions --- #

async def fetch_document_content(
    document_info: CustomerDocumentSearchResultMetadata,
    customer_data_service: CustomerDataService,
    user: Any,
    org_id: uuid.UUID
) -> Optional[Any]:
    """
    Fetch full document content from customer data service.
    
    Args:
        document_info: Document metadata
        customer_data_service: Customer data service instance
        user: User object
        org_id: Organization ID
        
    Returns:
        Document content or None if not found
    """
    try:
        if document_info.is_versioned:
            # Fetch versioned document
            content = await customer_data_service.get_versioned_document(
                org_id=org_id or document_info.org_id,
                namespace=document_info.namespace,
                docname=document_info.docname,
                is_shared=document_info.is_shared,
                user=user,
                version=document_info.version,
                is_system_entity=document_info.is_system_entity,
                is_called_from_workflow=True
            )
        else:
            # Fetch unversioned document
            content = await customer_data_service.get_unversioned_document(
                org_id=org_id or document_info.org_id,
                namespace=document_info.namespace,
                docname=document_info.docname,
                is_shared=document_info.is_shared,
                user=user,
                is_system_entity=document_info.is_system_entity,
                is_called_from_workflow=True
            )
        return content
    except Exception:
        return None


def generate_doc_serial_number(doc_key: Optional[str], docname: str, index: int) -> str:
    """
    Generate a document serial number for display.
    
    Args:
        doc_key: Document key/type (optional)
        docname: Document name
        index: Index in the list (1-based)
        
    Returns:
        Serial number in format {doc_key}_{index}
    """
    rand_int_seed = random.randint(10, 99)
    suffix = f"_{rand_int_seed}_{index}"
    if doc_key:
        return f"{doc_key}{suffix}"
    else:
        # Try to extract doc_key from docname by removing last component
        parts = docname.split('_')
        if len(parts) > 1:
            approx_doc_key = '_'.join(parts[:-1])
            return f"{approx_doc_key}{suffix}"
        else:
            return f"{docname}{suffix}"


# --- Enums for Operation Types ---

class EditOperationType(str, Enum):
    """Types of edit operations supported by the EditDocumentTool."""
    # JSON operations
    JSON_UPSERT_KEYS = "json_upsert_keys"
    JSON_EDIT_KEY = "json_edit_key"
    
    # Text operations
    TEXT_REPLACE_SUBSTRING = "text_replace_substring"
    TEXT_ADD_AT_POSITION = "text_add_at_position"
    
    # Common operations
    REPLACE_DOCUMENT = "replace_document"  # Works for both JSON and text documents
    DELETE_DOCUMENT = "delete_document"


# --- Common Base Schemas ---

class BaseDocumentInputSchema(BaseSchema):
    """
    Base schema for document operations with hidden fields.
    
    entity_username and view_context are marked as hidden from LLM tool calls
    using BaseSchema.FOR_LLM_TOOL_CALL_FIELD_KEY.
    """
    entity_username: str = Field(
        ..., 
        description="Entity username for namespace resolution", 
        json_schema_extra={BaseSchema.FOR_LLM_TOOL_CALL_FIELD_KEY: False}
    )
    view_context: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="View context mapping serial number to document info: {'brief_23_1': {'docname': 'doc1', 'version': 'draft'}, ...}",
        json_schema_extra={BaseSchema.FOR_LLM_TOOL_CALL_FIELD_KEY: False}
    )


# --- Edit Document Tool ---

class TextEditDetails(BaseSchema):
    """
    Details for text editing operations.
    
    Supports two types of text operations:
    1. Substring replacement: requires text_to_find and replacement_text
    2. Position-based insertion: requires position and text_to_add
    """
    # For substring replacement
    text_to_find: Optional[str] = Field(
        None,
        description="Exact text to find and replace in the content"
    )
    replacement_text: Optional[str] = Field(
        None,
        description="The text to replace the found text with"
    )
    
    # For position-based insertion
    position: Optional[int] = Field(
        None,
        description="Position to insert text (0 = start, -1 or >= length = end)"
    )
    text_to_add: Optional[str] = Field(
        None,
        description="Text to insert at the specified position"
    )
    
    @model_validator(mode='after')
    def validate_operation_fields(self) -> 'TextEditDetails':
        """Ensure exactly one type of text operation is specified with all required fields."""
        has_substring = (self.text_to_find is not None) or (self.replacement_text is not None)
        has_position = (self.position is not None) or (self.text_to_add is not None)
        
        if has_substring and has_position:
            raise ValueError("Cannot specify both substring replacement and position insertion fields")
        
        if has_substring:
            if not self.text_to_find:
                raise ValueError("text_to_find must be provided for substring replacement")
            if self.replacement_text is None:
                raise ValueError("replacement_text must be provided for substring replacement")
        elif has_position:
            if self.position is None:
                raise ValueError("position must be provided for position insertion")
            if not self.text_to_add:
                raise ValueError("text_to_add must be provided for position insertion")
        else:
            raise ValueError("Must specify either substring replacement (text_to_find, replacement_text) or position insertion (position, text_to_add) fields")
            
        return self


class JsonOperationDetails(BaseSchema):
    """
    Details for JSON-specific operations.
    
    Supports:
    1. Upserting keys: requires json_keys
    2. Editing a specific key: requires json_key_path and either replacement_value or text_edit_on_value
       - json_key_path supports array indices for lists (e.g., 'users.0.email', 'data.items.2.name')
       - For dicts with numeric string keys, the path treats them as keys, not indices
         (e.g., path 'data.4' accesses {"data": {"4": "value"}}, not data[4])
    """
    # For JSON_UPSERT_KEYS
    json_keys: Optional[Dict[str, Any]] = Field(
        None,
        description="Key-value pairs to upsert into the JSON document"
    )
    
    # For JSON_EDIT_KEY
    json_key_path: Optional[str] = Field(
        None,
        description=(
            "Dot-notation path to the key to edit. Supports array indices for lists "
            "(e.g., 'users.0.email', 'items.2.price'). "
            "Note: For dicts with numeric string keys (e.g., {'4': 'value'}), "
            "the key '4' is treated as a string key, not an array index."
            "NOTE: if document contents are contained in `document_contents` in viewer response, that shouldn't be prefixed to the path"
        )
    )
    replacement_value: Optional[Union[str, int, float, bool, Dict[str, Any], List[Union[str, Dict[str, Any], int, float, bool]]]] = Field(  # [Union[str, Dict[str, Any]]]
        None,
        description="The replacement value for the specified key"
    )
    
    # For text operations on JSON string values
    text_edit_on_value: Optional[TextEditDetails] = Field(
        None,
        description="Text edit operations to perform on a string value at json_key_path"
    )
    
    @model_validator(mode='after')
    def validate_json_fields(self) -> 'JsonOperationDetails':
        """Validate JSON operation fields are consistent."""
        if self.json_keys and (self.json_key_path or self.replacement_value is not None or self.text_edit_on_value):
            raise ValueError("json_keys cannot be used with json_key_path, replacement_value, or text_edit_on_value")
            
        if self.json_key_path:
            if (self.replacement_value is None) and (not self.text_edit_on_value):
                raise ValueError("json_key_path requires either replacement_value or text_edit_on_value")
            if (self.replacement_value is not None) and self.text_edit_on_value:
                raise ValueError("Cannot specify both replacement_value and text_edit_on_value for json_key_path")
                
        if not self.json_keys and not self.json_key_path:
            raise ValueError("Must specify either json_keys (for upsert) or json_key_path (for edit)")
                
        return self


class EditOperation(BaseSchema):
    """
    A single edit operation to apply to a document.
    
    Operation types and their requirements:
    - JSON_UPSERT_KEYS: requires json_operation.json_keys
    - JSON_EDIT_KEY: requires json_operation.json_key_path and either replacement_value or text_edit_on_value
    - TEXT_REPLACE_SUBSTRING: requires text_operation with substring fields (text_to_find, replacement_text)
    - TEXT_ADD_AT_POSITION: requires text_operation with position fields (position, text_to_add)
    - REPLACE_DOCUMENT: requires new_content
    - DELETE_DOCUMENT: no additional fields required
    """
    operation_type: EditOperationType = Field(
        ..., 
        description="The type of edit operation to perform"
    )
    
    # For document replacement (both JSON and text)
    new_content: Optional[Union[str, int, float, bool, Dict[str, Any], List[Union[str, Dict[str, Any], int, float, bool]]]] = Field(  # [Union[str, Dict[str, Any]]]
        None,
        description="For REPLACE_DOCUMENT: the new document content (string or dict/JSON)"
    )
    
    # Operation-specific details
    json_operation: Optional[JsonOperationDetails] = Field(
        None,
        description="Details for JSON-specific operations"
    )
    text_operation: Optional[TextEditDetails] = Field(
        None,
        description="Details for text document operations"
    )
    
    @model_validator(mode='after')
    def validate_operation_parameters(self) -> 'EditOperation':
        """Validate that required parameters are provided for each operation type."""
        op_type = self.operation_type
        
        # JSON operations
        if op_type in [EditOperationType.JSON_UPSERT_KEYS, EditOperationType.JSON_EDIT_KEY]:
            if not self.json_operation:
                raise ValueError(f"json_operation must be provided for {op_type.value}")
            if self.text_operation:
                raise ValueError(f"text_operation cannot be provided for {op_type.value}")
            if self.new_content is not None:
                raise ValueError(f"new_content cannot be provided for {op_type.value}")
                
        # Text operations
        elif op_type in [EditOperationType.TEXT_REPLACE_SUBSTRING, EditOperationType.TEXT_ADD_AT_POSITION]:
            if not self.text_operation:
                raise ValueError(f"text_operation must be provided for {op_type.value}")
            if self.json_operation:
                raise ValueError(f"json_operation cannot be provided for {op_type.value}")
            if self.new_content is not None:
                raise ValueError(f"new_content cannot be provided for {op_type.value}")
                
        # Replace document operation
        elif op_type == EditOperationType.REPLACE_DOCUMENT:
            if self.new_content is None:
                raise ValueError("new_content must be provided for REPLACE_DOCUMENT operation")
            if self.json_operation or self.text_operation:
                raise ValueError("json_operation and text_operation cannot be provided for REPLACE_DOCUMENT")
                
        # Delete operation
        elif op_type == EditOperationType.DELETE_DOCUMENT:
            if self.new_content is not None or self.json_operation or self.text_operation:
                raise ValueError("No additional fields should be provided for DELETE_DOCUMENT operation")
                
        return self


class EditDocumentInputSchema(BaseDocumentInputSchema):
    """
    Input schema for the EditDocumentTool.
    
    This tool identifies a single document and applies one or more edit operations to it.
    Documents can be identified either by their exact name or by a serial number from a view context.
    
    Document Identification:
    The 'document_identifier' field specifies which document to edit. You must provide:
    - 'doc_key': The type of document (e.g., 'brief', 'concept', 'user_preferences_doc', 'idea')
    - EITHER 'docname' OR 'document_serial_number' (not both):
      * Use 'docname' when you know the exact document name (e.g., 'brief_123e4567-e89b-12d3-a456-426614174000')
      * Use 'document_serial_number' when selecting from a generated serial number from view context
        (e.g., 'brief_78_1', 'concept_23_2' - these are strings, not numbers)
    
    Operations:
    The 'operations' field contains a list of edit operations to apply in sequence. Each operation
    specifies its type and the required parameters for that type. If any operation fails, subsequent
    operations will not be applied.
    
    Available Operation Types:
    - JSON_UPSERT_KEYS: Add/update keys in JSON documents
    - JSON_EDIT_KEY: Edit specific nested keys with dot notation (supports array indices)
    - TEXT_REPLACE_SUBSTRING: Replace text in string documents
    - TEXT_ADD_AT_POSITION: Insert text at specific positions
    - REPLACE_DOCUMENT: Replace entire document content
    - DELETE_DOCUMENT: Delete the document completely (stops further operations)
    
    Example Usage:
    1. JSON upsert by exact name:
       document_identifier: {doc_key: "brief", docname: "brief_123..."}
       operations: [{
         operation_type: "json_upsert_keys",
         json_operation: {json_keys: {"status": "published", "priority": "high"}}
       }]
    
    2. JSON edit with text operation on string value using serial number:
       document_identifier: {doc_key: "concept", document_serial_number: "concept_23_2"}
       operations: [{
         operation_type: "json_edit_key",
         json_operation: {
           json_key_path: "description",
           text_edit_on_value: {
             text_to_find: "original description",
             replacement_text: "updated description"
           }
         }
       }]
    
    3. JSON edit with array index:
       document_identifier: {doc_key: "brief", docname: "brief_123..."}
       operations: [{
         operation_type: "json_edit_key",
         json_operation: {
           json_key_path: "users.0.email",
           replacement_value: "newemail@example.com"
         }
       }]
    
    4. JSON edit nested array element:
       operations: [{
         operation_type: "json_edit_key",
         json_operation: {
           json_key_path: "items.2.price",
           replacement_value: 19.99
         }
       }]
    
    5. JSON edit with numeric string key (not array index):
       # For document: {"data": {"4": "old_value", "items": [...]}}
       operations: [{
         operation_type: "json_edit_key",
         json_operation: {
           json_key_path: "data.4",  # Accesses key "4", not array index
           replacement_value: "new_value"
         }
       }]
    
    6. Text replace in document:
       document_identifier: {doc_key: "content_analysis_doc", docname: "content_analysis_doc"}
       operations: [{
         operation_type: "text_replace_substring",
         text_operation: {
           text_to_find: "TODO",
           replacement_text: "COMPLETED"
         }
       }]
    
    7. Multiple operations in sequence:
       operations: [
         {operation_type: "json_edit_key", json_operation: {json_key_path: "status", replacement_value: "published"}},
         {operation_type: "json_upsert_keys", json_operation: {json_keys: {"published_at": "2024-01-01T12:00:00Z"}}}
       ]
    
    8. Delete document:
       document_identifier: {doc_key: "concept", document_serial_number: "concept_42_1"}
       operations: [{operation_type: "delete_document"}]
    
    Notes:
    - For versioned documents (like 'brief'), specify version in document_identifier if needed
    - DELETE_DOCUMENT operation requires no additional fields and stops further operations
    - Operations are applied sequentially and stop on first failure
    - Handling timezones:
        - All dates / times during edit operations should be in UTC timezone during storage in format `YYYY-MM-DDTHH:MM:SSZ`
        - If user's timezone is provided and is not UTC, convert any edits on date / time to UTC before storage
    """
    # Document identification - single field for both use cases
    document_identifier: DocumentIdentifier = Field(
        ...,
        description=(
            "Identifies the document to edit. Must include 'doc_key' and either:\n"
            "- 'docname': The exact document name (e.g., 'brief_123e4567...')\n"
            "- 'document_serial_number': A generated serial number from a presented list (e.g., 'brief_78_1', 'concept_23_2')\n"
            "Use docname when you know the exact name, use document_serial_number when selecting from a view context."
        )
    )
    
    # List of operations to apply
    operations: List[EditOperation] = Field(
        ...,
        min_length=1,
        description=(
            "List of edit operations to apply to the document in sequence. "
            "Each operation must specify its type and provide the required fields for that type. "
            "Operations are applied in order and stop on first failure."
        )
    )


class EditDocumentOutputSchema(BaseNodeConfig):
    """Output schema for the EditDocumentTool."""
    success: bool = Field(..., description="Whether all edit operations were successful")
    message: str = Field(..., description="Status message describing the overall result")
    
    # Document info
    document_info: Optional[CustomerDocumentSearchResultMetadata] = Field(
        None,
        description="Metadata about the edited document"
    )
    
    # Per-operation results
    operation_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Results for each operation attempted"
    )
    
    # Final content
    final_content: Optional[Union[str, Dict[str, Any]]] = Field(
        None,
        description="The final document content after all operations"
    )


class EditDocumentConfigSchema(BaseNodeConfig):
    """Configuration schema for the EditDocumentTool."""
    max_document_size_mb: float = Field(
        10.0,
        description="Maximum document size allowed in megabytes"
    )
    allow_system_document_edits: bool = Field(
        False,
        description="Whether to allow editing of system-level documents"
    )


class EditDocumentTool(BaseNode[EditDocumentInputSchema, EditDocumentOutputSchema, EditDocumentConfigSchema]):
    """
    Edit Document Tool for LLM workflows.
    
    This tool identifies a single document and applies one or more edit operations to it.
    Documents can be identified either by their exact name or by a serial number from a view context.
    
    Key Features:
    - Supports both JSON and text document operations
    - Applies multiple operations in sequence
    - Provides detailed per-operation results
    - Handles versioned and unversioned documents
    - Supports document deletion
    
    Available Operations:
    - JSON_UPSERT_KEYS: Add/update keys in JSON documents
    - JSON_EDIT_KEY: Edit specific nested keys with dot notation (supports array indices)
    - TEXT_REPLACE_SUBSTRING: Replace text in string documents
    - TEXT_ADD_AT_POSITION: Insert text at specific positions
    - REPLACE_DOCUMENT: Replace entire document content
    - DELETE_DOCUMENT: Delete the document completely (stops further operations)
    
    Document Identification:
    - By name: Use 'document_identifier' with doc_key and docname
    - By serial number: Use 'document_identifier' with doc_key and document_serial_number
    
    The entity_username is required but hidden from LLM tool calls.
    The view_context is optional and also hidden from LLM tool calls.
    Operations are applied sequentially and stop on first failure.
    """
    
    node_name: ClassVar[str] = "edit_document"
    node_version: ClassVar[str] = "2.0.0"
    node_is_tool: ClassVar[bool] = True
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[Type[EditDocumentInputSchema]] = EditDocumentInputSchema
    output_schema_cls: ClassVar[Type[EditDocumentOutputSchema]] = EditDocumentOutputSchema
    config_schema_cls: ClassVar[Type[EditDocumentConfigSchema]] = EditDocumentConfigSchema
    
    async def process(
        self,
        input_data: EditDocumentInputSchema,
        config: Dict[str, Any],
        *args: Any,
        **kwargs: Any
    ) -> EditDocumentOutputSchema:
        """Process the document edit operations."""
        self.info(f"Starting document edit operations with {len(input_data.operations)} operations")
        
        # Extract context from runtime config
        if not config:
            self.error("Missing runtime config (config argument)")
            return EditDocumentOutputSchema(
                success=False,
                message="Missing runtime config (config argument)"
            )
        
        config = config.get("configurable")
        
        app_context: Optional[Dict[str, Any]] = config.get(APPLICATION_CONTEXT_KEY)
        ext_context = config.get(EXTERNAL_CONTEXT_MANAGER_KEY)
        
        if not app_context or not ext_context:
            self.error(f"Missing required keys in runtime_config: {APPLICATION_CONTEXT_KEY}, {EXTERNAL_CONTEXT_MANAGER_KEY}")
            return EditDocumentOutputSchema(
                success=False,
                message="Missing required context in runtime configuration"
            )
        
        user = app_context.get("user")
        run_job = app_context.get("workflow_run_job")
        customer_data_service: CustomerDataService = ext_context.customer_data_service
        
        if not user or not run_job or not customer_data_service:
            self.error("Missing user, workflow run job, or customer data service in context")
            return EditDocumentOutputSchema(
                success=False,
                message="Missing user, workflow run job, or customer data service in application context"
            )
        
        org_id = run_job.owner_org_id
        
        # Identify the document
        document_info = identify_document(
            identifier=input_data.document_identifier,
            entity_username=input_data.entity_username,
            view_context=input_data.view_context
        )
        
        if not document_info:
            self.error("Failed to identify document for editing")
            return EditDocumentOutputSchema(
                success=False,
                message="Failed to identify document"
            )
    
        if not document_info.user_id_or_shared_placeholder:
            document_info.user_id_or_shared_placeholder = user.id
        
        # Check if editing system documents is allowed
        if document_info.is_system_entity and not self.config.allow_system_document_edits:
            self.warning(f"Attempted to edit system document {document_info.namespace}/{document_info.docname} but system document editing is disabled")
            return EditDocumentOutputSchema(
                success=False,
                message="Editing system documents is not allowed by configuration",
                document_info=document_info
            )
        
        # Process operations
        operation_results = []
        current_content = None
        all_success = True
        
        try:

            base_path = customer_data_service._build_base_path(
                org_id=org_id, 
                namespace=document_info.namespace, 
                docname=document_info.docname, 
                is_shared=document_info.is_shared, 
                user=user,
                # on_behalf_of_user_id=on_behalf_of_user_id,
                is_system_entity=document_info.is_system_entity,
            )

            async with customer_data_service.versioned_mongo_client._with_document_lock(base_path, "update_document"):
                # Fetch initial document content
                current_content = await self._fetch_document(
                    document_info, org_id, user, customer_data_service
                )
                
                ops_errors = None
                # Apply each operation
                for i, operation in enumerate(input_data.operations):
                    try:
                        if operation.operation_type == EditOperationType.DELETE_DOCUMENT:
                            # Handle delete specially
                            result = await self._handle_delete_operation(
                                document_info, org_id, user, customer_data_service
                            )
                            operation_results.append({
                                "operation_index": i,
                                "operation_type": operation.operation_type.value,
                                "success": result["success"],
                                "message": result.get("message", "")
                            })
                            if result["success"]:
                                current_content = None
                            else:
                                all_success = False
                            break  # No operations after delete
                        else:
                            # Apply edit operation
                            updated_content = await self._apply_edit_operation(
                                operation, current_content
                            )
                            current_content = updated_content
                            operation_results.append({
                                "operation_index": i,
                                "operation_type": operation.operation_type.value,
                                "success": True,
                                "message": "Operation applied successfully"
                            })
                    except Exception as e:
                        operation_results.append({
                            "operation_index": i,
                            "operation_type": operation.operation_type.value,
                            "success": False,
                            "message": f"Error: {str(e)}"
                        })
                        all_success = False
                        self.error(f"Error in edit document operation: {e}", exc_info=True)
                        ops_errors = str(e)
                        break  # Stop on first error
                
                # Save the final content if not deleted
                if all_success and current_content is not None:
                    save_success = await self._save_document(
                        document_info, current_content, org_id, user, customer_data_service
                    )
                    if not save_success:
                        all_success = False
                        operation_results.append({
                            "operation_index": -1,
                            "operation_type": "save",
                            "success": False,
                            "message": "Failed to save document after edits"
                        })
            
            if all_success:
                self.info(f"Successfully completed {len(operation_results)} edit operations on document {document_info.namespace}/{document_info.docname}")
            else:
                self.warning(f"Edit operations failed for document {document_info.namespace}/{document_info.docname} -- ops errors: {ops_errors}")
            
            return EditDocumentOutputSchema(
                success=all_success,
                message=f"Processed {len(operation_results)} operations" if all_success else (ops_errors or "Some operations failed"),
                document_info=document_info,
                operation_results=operation_results,
                final_content=current_content if all_success else None
            )
            
        except Exception as e:
            self.error(f"Error in edit document operation: {e}", exc_info=True)
            return EditDocumentOutputSchema(
                success=False,
                message=f"Error: {str(e)}",
                document_info=document_info,
                operation_results=operation_results
            )
    
    async def _fetch_document(
        self,
        document_info: CustomerDocumentSearchResultMetadata,
        org_id: uuid.UUID,
        user: Any,
        customer_data_service: CustomerDataService
    ) -> Union[str, Dict[str, Any]]:
        """Fetch the existing document content."""
        content = await fetch_document_content(
            document_info=document_info,
            customer_data_service=customer_data_service,
            user=user,
            org_id=org_id
        )
        
        if content is None:
            self.error(f"Document not found: {document_info.namespace}/{document_info.docname}")
            return {}
        
        return content
    
    async def _apply_edit_operation(
        self,
        operation: EditOperation,
        current_content: Union[str, Dict[str, Any]]
    ) -> Union[str, Dict[str, Any]]:
        """Apply a single edit operation to the content."""
        if operation.operation_type in [EditOperationType.JSON_UPSERT_KEYS, EditOperationType.JSON_EDIT_KEY]:
            return self._handle_json_operation(operation, current_content)
        elif operation.operation_type in [EditOperationType.TEXT_REPLACE_SUBSTRING, EditOperationType.TEXT_ADD_AT_POSITION]:
            return self._handle_text_operation(operation, current_content)
        elif operation.operation_type == EditOperationType.REPLACE_DOCUMENT:
            return self._handle_replace_document(operation, current_content)
        else:
            raise ValueError(f"Unsupported operation type: {operation.operation_type}")
    
    def _handle_json_operation(
        self,
        operation: EditOperation,
        existing_content: Union[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Handle JSON document operations."""
        # Ensure we have a dict to work with
        if isinstance(existing_content, str):
            try:
                existing_dict = json.loads(existing_content)
            except json.JSONDecodeError:
                # If content is not valid JSON, raise an error
                raise ValueError("Cannot perform JSON operations on non-JSON content")
        else:
            existing_dict = existing_content or {}
        
        if not isinstance(existing_dict, dict):
            raise ValueError("JSON operations can only be performed on dictionary/object content")
        
        if operation.operation_type == EditOperationType.JSON_UPSERT_KEYS:
            # Merge new keys into existing document
            existing_dict.update(operation.json_operation.json_keys or {})
            return existing_dict
            
        elif operation.operation_type == EditOperationType.JSON_EDIT_KEY:
            # Handle text operations on string values if specified
            if operation.json_operation.text_edit_on_value:
                # Get current value at the path
                current_value = self._get_nested_value(existing_dict, operation.json_operation.json_key_path)
                if not isinstance(current_value, str):
                    raise ValueError(f"Cannot perform text operations on non-string value at path '{operation.json_operation.json_key_path}'. Current value type: {type(current_value)}")
                
                # Apply text operation
                new_value = self._apply_text_edit(current_value, operation.json_operation.text_edit_on_value)
                self._set_nested_value(existing_dict, operation.json_operation.json_key_path, new_value)
            else:
                # Direct replacement
                self._set_nested_value(
                    existing_dict,
                    operation.json_operation.json_key_path,
                    operation.json_operation.replacement_value
                )
            return existing_dict
        
        return existing_dict
    
    def _handle_text_operation(
        self,
        operation: EditOperation,
        existing_content: Union[str, Dict[str, Any]]
    ) -> str:
        """Handle text document operations."""
        # Convert to string if needed
        if isinstance(existing_content, dict):
            # Cannot perform text operations on JSON content directly
            raise ValueError("Cannot perform text operations on JSON/dictionary content. Use JSON operations or REPLACE_DOCUMENT instead.")
        else:
            existing_text = str(existing_content or "")
        
        return self._apply_text_edit(existing_text, operation.text_operation)
    
    def _apply_text_edit(self, text: str, text_edit: TextEditDetails) -> str:
        """Apply text edit details to a string."""
        if text_edit.text_to_find is not None and text_edit.replacement_text is not None:
            # Replace exact substring
            if text_edit.text_to_find not in text:
                raise ValueError(f"Text '{text_edit.text_to_find}' not found in content")
            return text.replace(text_edit.text_to_find, text_edit.replacement_text)
            
        elif text_edit.position is not None and text_edit.text_to_add is not None:
            # Add text at position
            position = text_edit.position
            text_length = len(text)
            
            if position < 0 or position >= text_length:
                # Append to end
                return text + text_edit.text_to_add
            else:
                # Insert at position
                return text[:position] + text_edit.text_to_add + text[position:]
        
        raise ValueError("Invalid text edit configuration")
    
    def _handle_replace_document(
        self,
        operation: EditOperation,
        existing_content: Union[str, Dict[str, Any]]
    ) -> Union[str, Dict[str, Any]]:
        """Handle document replacement for both JSON and text documents."""
        if operation.new_content is None:
            raise ValueError("new_content must be provided for REPLACE_DOCUMENT operation")
        
        # Try to determine if new_content is JSON
        if isinstance(operation.new_content, (dict, list)):
            # Already a dict, return as is
            return operation.new_content
        elif isinstance(operation.new_content, str):
            # Try to parse as JSON
            try:
                parsed_content = json.loads(operation.new_content)
                # Successfully parsed as JSON, return the dict
                return parsed_content
            except json.JSONDecodeError:
                # Not JSON, return as plain text
                return operation.new_content
        else:
            raise ValueError(f"new_content must be a string or dict, got {type(operation.new_content)}")
    
    async def _save_document(
        self,
        document_info: CustomerDocumentSearchResultMetadata,
        content: Union[str, Dict[str, Any]],
        org_id: uuid.UUID,
        user: Any,
        customer_data_service: CustomerDataService
    ) -> bool:
        """Save the updated document."""
        try:
            # Convert any datetime objects to strings if content is JSON
            if isinstance(content, dict) and ("created_at" in content or "updated_at" in content):
                if "created_at" in content:
                    del content["created_at"]
                if "updated_at" in content:
                    del content["updated_at"]

            # if isinstance(content, dict):
            #     content = self._convert_datetimes_to_str(content)

            
            async with get_async_db_as_manager() as db_session:
                if document_info.is_versioned:
                    success = await customer_data_service.update_versioned_document(
                        db=db_session,
                        org_id=org_id,
                        namespace=document_info.namespace,
                        docname=document_info.docname,
                        is_shared=document_info.is_shared,
                        user=user,
                        data=content,
                        version=document_info.version,
                        is_system_entity=document_info.is_system_entity,
                        is_called_from_workflow=True,
                        lock=False,
                    )
                else:
                    _, created = await customer_data_service._create_or_update_unversioned_document_no_lock(
                        db=db_session,
                        org_id=org_id,
                        namespace=document_info.namespace,
                        docname=document_info.docname,
                        is_shared=document_info.is_shared,
                        user=user,
                        data=content,
                        is_system_entity=document_info.is_system_entity,
                        is_called_from_workflow=True
                    )
                    success = True
            
            return success
        except Exception as e:
            self.error(f"Error saving document {document_info.namespace}/{document_info.docname}: {e}")
            return False
    
    async def _handle_delete_operation(
        self,
        document_info: CustomerDocumentSearchResultMetadata,
        org_id: uuid.UUID,
        user: Any,
        customer_data_service: CustomerDataService
    ) -> Dict[str, Any]:
        """
        Handle document deletion.
        
        Args:
            document_info: Metadata about the document to delete
            org_id: Organization ID
            user: User object
            customer_data_service: Customer data service instance
            
        Returns:
            Dictionary with success status and message
        """
        try:
            if document_info.is_versioned:
                # Delete versioned document
                success = await customer_data_service.delete_versioned_document(
                    org_id=org_id or document_info.org_id,
                    namespace=document_info.namespace,
                    docname=document_info.docname,
                    is_shared=document_info.is_shared,
                    user=user,
                    is_system_entity=document_info.is_system_entity,
                    is_called_from_workflow=True,
                    lock=False,
                )
            else:
                # Delete unversioned document
                success = await customer_data_service.delete_unversioned_document(
                    org_id=org_id or document_info.org_id,
                    namespace=document_info.namespace,
                    docname=document_info.docname,
                    is_shared=document_info.is_shared,
                    user=user,
                    is_system_entity=document_info.is_system_entity,
                    is_called_from_workflow=True,
                )
            
            if success:
                return {
                    "success": True,
                    "message": f"Document '{document_info.namespace}/{document_info.docname}' deleted successfully"
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to delete document '{document_info.namespace}/{document_info.docname}'"
                }
                
        except Exception as e:
            self.error(f"Error deleting document {document_info.namespace}/{document_info.docname}: {e}")
            return {
                "success": False,
                "message": f"Error deleting document: {str(e)}"
            }
    
    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """
        Get a value from a nested dictionary/list using dot notation with array index support.
        
        Handles paths like:
        - "user.name" - Access dict keys
        - "users.0.email" - Access array elements by index
        - "data.4.value" - Prefers dict key "4" over array index 4
        
        Important behavior:
        - For dictionaries: Always tries the key as-is first (including numeric strings)
        - For lists: Only accepts numeric indices (0, 1, 2, etc.)
        - Negative indices are NOT supported (e.g., -1 for last element)
        - Out of bounds indices raise IndexError
        - Non-numeric keys on lists raise TypeError
        
        Examples:
        - Path "data.4" on {"data": {"4": "value"}} -> Returns "value" (dict key)
        - Path "data.4" on {"data": ["a", "b", "c", "d", "e"]} -> Returns "e" (index 4)
        - Path "items.-1" -> Raises error (negative indices not supported)
        - Path "items.foo" on {"items": [...]} -> Raises error (non-numeric on list)
        """
        if not path:
            raise KeyError("Empty path provided")
            
        keys = path.split('.')
        current = data
        traversed = []
        
        for key in keys:
            traversed.append(key)
            current_path = '.'.join(traversed)
            
            try:
                if isinstance(current, dict):
                    # For dictionaries, always try the key as-is first
                    if key in current:
                        current = current[key]
                    else:
                        raise KeyError(f"Key '{key}' not found in dictionary")
                        
                elif isinstance(current, list):
                    # For lists, require numeric indices
                    if not key.isdigit():
                        raise TypeError(f"Cannot use non-numeric key '{key}' for list access")
                    
                    index = int(key)
                    if 0 <= index < len(current):
                        current = current[index]
                    else:
                        raise IndexError(f"Index {index} out of range for list of length {len(current)}")
                        
                else:
                    raise TypeError(f"Cannot traverse into {type(current).__name__} with key '{key}'")
                    
            except (KeyError, IndexError, TypeError) as e:
                raise KeyError(f"Error accessing path '{path}' at '{current_path}': {str(e)}")
        
        return current
    
    def _set_nested_value(self, data: Dict[str, Any], path: str, value: Any) -> None:
        """
        Set a value in a nested dictionary/list using dot notation with array index support.
        
        Handles paths like:
        - "user.name" - Set dict keys
        - "users.0.email" - Set array elements by index
        - "data.4.value" - Prefers dict key "4" over array index 4
        
        Auto-creates intermediate structures:
        - Creates dicts for string keys
        - Does NOT auto-create lists (must already exist for array access)
        
        Important behavior:
        - For dictionaries: Always sets the key as-is (including numeric strings)
        - For lists: Only accepts numeric indices (0, 1, 2, etc.)
        - Cannot extend lists - index must be within current bounds
        - Negative indices are NOT supported
        - Type conversion: String values that are valid JSON are automatically parsed
        
        Examples:
        - Path "data.4" on {"data": {}} -> Creates {"data": {"4": value}}
        - Path "items.3" on {"items": ["a", "b", "c"]} -> Error (index 3 out of bounds)
        - Path "config.ports.0" -> Error if config.ports doesn't exist (won't create list)
        """
        if not path:
            raise ValueError("Empty path provided")
            
        keys = path.split('.')
        current = data
        traversed = []
        
        # Navigate to the parent of the final key
        for i, key in enumerate(keys[:-1]):
            traversed.append(key)
            current_path = '.'.join(traversed)
            next_key = keys[i + 1]
            
            try:
                if isinstance(current, dict):
                    # For dictionaries, check if key exists
                    if key not in current:
                        # Auto-create only dicts, not lists
                        current[key] = {}
                    current = current[key]
                    
                elif isinstance(current, list):
                    # For lists, require numeric indices
                    if not key.isdigit():
                        raise TypeError(f"Cannot use non-numeric key '{key}' for list access")
                    
                    index = int(key)
                    if 0 <= index < len(current):
                        current = current[index]
                    else:
                        raise IndexError(f"Index {index} out of range for list of length {len(current)}")
                        
                else:
                    raise TypeError(f"Cannot traverse into {type(current).__name__} with key '{key}'")
                    
                # Validate that we can continue traversing
                if not isinstance(current, (dict, list)):
                    raise ValueError(f"Cannot continue traversing at '{current_path}': found {type(current).__name__}")
                    
            except (KeyError, IndexError, TypeError, ValueError) as e:
                raise ValueError(f"Error setting value at path '{path}': {str(e)}")
        
        # Handle the final key
        final_key = keys[-1]
        traversed.append(final_key)
        final_path = '.'.join(traversed)
        
        # Parse string values as JSON if possible
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass  # Keep as string
        
        try:
            if isinstance(current, dict):
                # For dictionaries, always set the key as-is
                current[final_key] = value
                
            elif isinstance(current, list):
                # For lists, require numeric index
                if not final_key.isdigit():
                    raise TypeError(f"Cannot use non-numeric key '{final_key}' for list assignment")
                
                index = int(final_key)
                if 0 <= index < len(current):
                    current[index] = value
                else:
                    raise IndexError(f"Index {index} out of range for list of length {len(current)}")
                    
            else:
                raise TypeError(f"Cannot set value on {type(current).__name__}")
                
        except (IndexError, TypeError) as e:
            raise ValueError(f"Error setting value at path '{path}': {str(e)}")

    def _convert_datetimes_to_str(self, obj: Any) -> Any:
        """Recursively convert datetime objects to ISO format strings."""
        from datetime import datetime, date
        
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._convert_datetimes_to_str(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_datetimes_to_str(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self._convert_datetimes_to_str(item) for item in obj)
        else:
            return obj


# --- Document Viewer Tool ---

class DocumentViewerInputSchema(BaseDocumentInputSchema):
    """
    Input schema for the DocumentViewerTool.
    
    This tool can operate in two modes:
    1. Single Document View: View the content of one specific document
    2. List Documents: View multiple documents based on filter criteria
    
    Mode Selection:
    You must provide EITHER 'document_identifier' (for single document) OR 'list_filter' (for listing), not both.
    
    Single Document View:
    Use 'document_identifier' to view one document. Provide:
    - 'doc_key': The type of document (e.g., 'brief', 'concept', 'user_preferences_doc', 'idea')
    - EITHER 'docname' OR 'document_serial_number':
      * 'docname': When you know the exact name (e.g., 'brief_123e4567...')
      * 'document_serial_number': When selecting from a view context (e.g., 'brief_78_1', 'concept_45_2')
    
    List Documents View:
    Use 'list_filter' to view multiple documents. Provide:
    - 'doc_key' OR 'namespace_of_doc_key': Filter by document type or namespace
    - Optional date filters: scheduled_date_range_start/end, created_at_range_start/end
    - Results are limited to 5 documents by default (max 10) for viewing purposes
    
    Example Usage:
    1. View single document by name:
       document_identifier: {doc_key: "user_preferences_doc", docname: "user_preferences_doc"}
    
    2. View single document by serial number from view context:
       document_identifier: {doc_key: "concept", document_serial_number: "concept_45_2"}
    
    3. List all briefs (limited to 5):
       list_filter: {doc_key: "brief", limit: 5}
    
    4. List recent concepts with date filter:
       list_filter: {doc_key: "concept", created_at_range_start: "2024-01-01T00:00:00Z", limit: 10}
    
    5. List scheduled briefs for a date range:
       list_filter: {
         doc_key: "brief",
         scheduled_date_range_start: "2024-01-15T00:00:00Z",
         scheduled_date_range_end: "2024-01-22T00:00:00Z"
       }
    
    Notes:
    - View context format: {"concept_45_2": {"docname": "actual_name", "version": "default"}}
    - Pagination may not be 100% accurate due to versioning metadata documents being filtered out
    - Results include both user-specific and shared documents
    """
    # Single document identification
    document_identifier: Optional[DocumentIdentifier] = Field(
        None,
        description=(
            "Identifies a single document to view. Must include 'doc_key' and either:\n"
            "- 'docname': The exact document name\n"
            "- 'document_serial_number': A generated serial number from view context\n"
            "Use this for viewing one specific document."
        )
    )
    
    # List documents filter
    list_filter: Optional[DocumentListFilter] = Field(
        None,
        description=(
            "Filter criteria for listing multiple documents. Must include either:\n"
            "- 'doc_key': To list all documents of a specific type\n"
            "- 'namespace_of_doc_key': To list all documents in a namespace\n"
            "Can also include date filters and pagination options.\n"
            "Use this for viewing multiple documents at once."
        )
    )
    
    # Pagination for list view (limit is capped)
    limit: int = Field(
        5,
        ge=1,
        le=10,
        description="Maximum number of documents to return when listing (1-10, default 5). Only applies to list mode."
    )
    offset: int = Field(
        0,
        ge=0,
        description="Number of documents to skip for pagination. Only applies to list mode."
    )
    
    @model_validator(mode='after')
    def validate_operation_mode(self) -> 'DocumentViewerInputSchema':
        """Ensure exactly one operation mode is specified."""
        has_document = self.document_identifier is not None
        has_list = self.list_filter is not None
        
        if not has_document and not has_list:
            raise ValueError("Must provide either 'document_identifier' (for single document) or 'list_filter' (for listing)")
        
        if has_document and has_list:
            raise ValueError("Provide either 'document_identifier' or 'list_filter', not both")
            
        return self


class DocumentViewerOutputSchema(BaseNodeConfig):
    """Output schema for the DocumentViewerTool."""
    success: bool = Field(..., description="Whether the view operation was successful")
    message: str = Field(..., description="Status message")
    
    documents: Dict[str, CustomerDocumentSearchResult] = Field(
        default_factory=dict,
        description="Dictionary of documents with metadata and content indexed by document serial number"
    )
    
    state_changes: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Dictionary of document metadata indexed by document serial number"
    )
    
    total_count: int = Field(0, description="Total number of documents found (for pagination)")
    view_mode: str = Field(..., description="Whether viewing 'single' document or 'list' of documents")


class DocumentViewerConfigSchema(BaseNodeConfig):
    """Configuration schema for the DocumentViewerTool."""
    max_view_limit: int = Field(
        10,
        description="Maximum number of documents that can be viewed at once"
    )


class DocumentViewerTool(BaseNode[DocumentViewerInputSchema, DocumentViewerOutputSchema, DocumentViewerConfigSchema]):
    """
    Document Viewer Tool for LLM workflows.
    
    This versatile tool can:
    1. View a single document by name or serial number
    2. List multiple documents based on filters
    
    Key Features:
    - Dual mode: single document or list view
    - Automatic limit of 5 documents for list view (max 10)
    - Supports doc_key and namespace-based filtering
    - Includes document content and metadata
    
    Usage Modes:
    - Single document by name: Set 'document' with doc_key and docname
    - Single document by serial number: Set 'document_identifier' with doc_key and document_serial_number
    - List documents: Set 'list_filter' with filter criteria
    
    The entity_username is required but hidden from LLM tool calls.
    The view_context is optional and also hidden from LLM tool calls.
    """
    
    node_name: ClassVar[str] = "view_documents"
    node_version: ClassVar[str] = "2.0.0"
    node_is_tool: ClassVar[bool] = True
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[Type[DocumentViewerInputSchema]] = DocumentViewerInputSchema
    output_schema_cls: ClassVar[Type[DocumentViewerOutputSchema]] = DocumentViewerOutputSchema
    config_schema_cls: ClassVar[Type[DocumentViewerConfigSchema]] = DocumentViewerConfigSchema
    
    async def process(
        self,
        input_data: DocumentViewerInputSchema,
        config: Dict[str, Any],
        *args: Any,
        **kwargs: Any
    ) -> DocumentViewerOutputSchema:
        """Process the document view operation."""
        # Determine operation mode for logging
        view_mode = "single" if input_data.document_identifier else "list"
        self.info(f"Starting document viewer in {view_mode} mode")
        
        # Extract context from runtime config
        if not config:
            self.error("Missing runtime config (config argument)")
            return DocumentViewerOutputSchema(
                success=False,
                message="Missing runtime config (config argument)",
                view_mode="unknown"
            )
        
        config = config.get("configurable")
        
        app_context: Optional[Dict[str, Any]] = config.get(APPLICATION_CONTEXT_KEY)
        ext_context = config.get(EXTERNAL_CONTEXT_MANAGER_KEY)
        
        if not app_context or not ext_context:
            self.error(f"Missing required keys in runtime_config: {APPLICATION_CONTEXT_KEY}, {EXTERNAL_CONTEXT_MANAGER_KEY}")
            return DocumentViewerOutputSchema(
                success=False,
                message="Missing required context in runtime configuration",
                view_mode="unknown"
            )
        
        user = app_context.get("user")
        run_job = app_context.get("workflow_run_job")
        customer_data_service = ext_context.customer_data_service
        
        if not user or not run_job or not customer_data_service:
            self.error("Missing user, workflow run job, or customer data service in context")
            return DocumentViewerOutputSchema(
                success=False,
                message="Missing user, workflow run job, or customer data service in application context",
                view_mode="unknown"
            )
        
        org_id = run_job.owner_org_id
        
        try:
            # Determine operation mode
            if input_data.document_identifier:
                # Single document view
                return await self._view_single_document(
                    input_data, org_id, user, customer_data_service
                )
            else:
                # List documents view
                return await self._list_documents(
                    input_data, org_id, user, customer_data_service
                )
                
        except Exception as e:
            self.error(f"Error in document viewer: {e}", exc_info=True)
            return DocumentViewerOutputSchema(
                success=False,
                message=f"Error: {str(e)}",
                view_mode="error"
            )
    
    async def _view_single_document(
        self,
        input_data: DocumentViewerInputSchema,
        org_id: uuid.UUID,
        user: Any,
        customer_data_service: CustomerDataService
    ) -> DocumentViewerOutputSchema:
        """View a single document."""
        # Identify the document
        document_info = identify_document(
            identifier=input_data.document_identifier,
            entity_username=input_data.entity_username,
            view_context=input_data.view_context
        )
        
        if not document_info:
            self.error("Failed to identify document for viewing")
            return DocumentViewerOutputSchema(
                success=False,
                message="Failed to identify document",
                view_mode="single"
            )
        
        if not document_info.user_id_or_shared_placeholder:
            document_info.user_id_or_shared_placeholder = user.id
        
        # Fetch document content
        try:
            content = await fetch_document_content(
                document_info=document_info,
                customer_data_service=customer_data_service,
                user=user,
                org_id=org_id
            )
            
            if content is None:
                self.warning(f"Document not found: {document_info.namespace}/{document_info.docname}")
                return DocumentViewerOutputSchema(
                    success=False,
                    message=f"Document not found: {document_info.namespace}/{document_info.docname}",
                    view_mode="single"
                )
            
            # Create result
            document_result = CustomerDocumentSearchResult(
                metadata=document_info,
                document_contents=content
            )
            
            # Generate serial number
            doc_key = input_data.document_identifier.doc_key if input_data.document_identifier else None
            serial_number = generate_doc_serial_number(doc_key, document_info.docname, 1)
            
            # Build state changes entry
            state_entry = {
                "docname": document_info.docname
            }
            if document_info.version:
                state_entry["version"] = document_info.version
            
            self.info(f"Successfully retrieved document {document_info.namespace}/{document_info.docname}")
            
            return DocumentViewerOutputSchema(
                success=True,
                message="Document retrieved successfully",
                documents={serial_number: document_result},
                state_changes={serial_number: state_entry},
                total_count=1,
                view_mode="single"
            )
            
        except Exception as e:
            self.error(f"Error fetching document {document_info.namespace}/{document_info.docname}: {e}")
            return DocumentViewerOutputSchema(
                success=False,
                message=f"Error fetching document: {str(e)}",
                view_mode="single"
            )
    
    async def _list_documents(
        self,
        input_data: DocumentViewerInputSchema,
        org_id: uuid.UUID,
        user: Any,
        customer_data_service: CustomerDataService
    ) -> DocumentViewerOutputSchema:
        """List documents based on filter criteria."""
        # Build query parameters
        query_params = build_list_query(
            filter_obj=input_data.list_filter,
            entity_username=input_data.entity_username
        )
        
        try:
            # Extract filter parameters
            namespace_filter = query_params.get("namespace")
            doc_key = query_params.get("doc_key")
            
            # Extract date filters from query_params
            scheduled_date_range_start = query_params.get("scheduled_after")
            scheduled_date_range_end = query_params.get("scheduled_before")
            created_at_range_start = query_params.get("created_after")
            created_at_range_end = query_params.get("created_before")
            
            # Build value filter for date ranges
            value_filter = {}
            if scheduled_date_range_start or scheduled_date_range_end:
                value_filter["scheduled_date"] = {}
                if scheduled_date_range_start:
                    value_filter["scheduled_date"]["$gte"] = scheduled_date_range_start
                if scheduled_date_range_end:
                    value_filter["scheduled_date"]["$lte"] = scheduled_date_range_end
                    
            if created_at_range_start or created_at_range_end:
                value_filter["created_at"] = {}
                if created_at_range_start:
                    value_filter["created_at"]["$gte"] = created_at_range_start
                if created_at_range_end:
                    value_filter["created_at"]["$lte"] = created_at_range_end
            
            # Use search_documents from customer data service
            search_results = await customer_data_service.search_documents(
                org_id=org_id,
                user=user,
                namespace_filter=namespace_filter,
                text_search_query=None,  # No text search for listing
                value_filter=value_filter if value_filter else None,
                include_shared=True,
                include_user_specific=True,
                skip=input_data.offset,
                limit=input_data.limit,
                include_system_entities=False,
                is_called_from_workflow=True
            )
            
            # Convert search results to document viewer format
            documents = {}
            state_changes = {}
            index = 1
            
            for search_result in search_results:
                # Skip versioning metadata entries
                if search_result.metadata.is_versioning_metadata:
                    continue
                
                # Generate serial number
                serial_number = generate_doc_serial_number(doc_key, search_result.metadata.docname, index)
                
                # Add to results
                documents[serial_number] = search_result
                
                # Build state changes entry
                state_entry = {
                    "docname": search_result.metadata.docname
                }
                if search_result.metadata.version:
                    state_entry["version"] = search_result.metadata.version
                
                state_changes[serial_number] = state_entry
                index += 1
            
            self.info(f"Successfully listed {len(documents)} documents")
            
            return DocumentViewerOutputSchema(
                success=True,
                message=f"Listed {len(documents)} documents",
                documents=documents,
                state_changes=state_changes,
                total_count=len(documents),
                view_mode="list"
            )
            
        except Exception as e:
            self.error(f"Error listing documents: {e}", exc_info=True)
            return DocumentViewerOutputSchema(
                success=False,
                message=f"Error listing documents: {str(e)}",
                documents={},
                state_changes={},
                total_count=0,
                view_mode="list"
            )


# --- Document Search Tool ---

class DocumentSearchInputSchema(BaseDocumentInputSchema):
    """
    Input schema for the DocumentSearchTool.
    
    This tool searches for text within documents using the RAG (Retrieval Augmented Generation) service.
    You can search in two scopes:
    1. Single Document Search: Search within one specific document
    2. Multiple Document Search: Search across documents matching filter criteria
    
    Required Fields:
    - 'search_query': The text you want to find in documents
    - EITHER 'document_identifier' OR 'list_filter' (not both) to specify search scope
    
    Single Document Search:
    Use 'document_identifier' to search within one document. Provide:
    - 'doc_key': The type of document (e.g., 'brief', 'concept', 'user_preferences_doc')
    - EITHER 'docname' OR 'document_serial_number':
      * 'docname': When you know the exact name
      * 'document_serial_number': When selecting from a view context (e.g., 'brief_78_1', 'concept_23_2')
    
    Multiple Document Search:
    Use 'list_filter' to search across multiple documents. Provide:
    - 'doc_key' OR 'namespace_of_doc_key': To define the search scope
    - Optional date filters to narrow the search
    
    Search Options:
    - 'limit': Maximum results to return (1-10, default 10)
    - 'offset': Skip results for pagination
    
    Example Usage:
    1. Search in specific document by name:
       search_query: "revenue projections"
       document_identifier: {doc_key: "brief", docname: "brief_123..."}
    
    2. Search in document by serial number from view context:
       search_query: "marketing strategy"
       document_identifier: {doc_key: "brief", document_serial_number: "brief_78_1"}
    
    3. Search across all briefs:
       search_query: "Q4 goals"
       list_filter: {doc_key: "brief"}
    
    4. Search across concepts with date filter:
       search_query: "artificial intelligence"
       list_filter: {doc_key: "concept", created_at_range_start: "2024-01-01T00:00:00Z"}
    
    Notes:
    - Search uses hybrid search (vector + keyword) for best results. Since vector search is used, relatively longer search queries may also be used for hybrid semantic search optionally.
    - Results include the entire document, content previews and relevance scores
    """
    # Search query
    search_query: str = Field(
        ...,
        description="The text to search for in documents. This is the search term or phrase you want to find."
    )
    
    # Target: single document or list filter
    document_identifier: Optional[DocumentIdentifier] = Field(
        None,
        description=(
            "Search within a single document. Must include 'doc_key' and either:\n"
            "- 'docname': The exact document name\n"
            "- 'document_serial_number': A generated serial number from view context\n"
            "Use this to search within one specific document."
        )
    )
    list_filter: Optional[DocumentListFilter] = Field(
        None,
        description=(
            "Search across multiple documents. Must include either:\n"
            "- 'doc_key': To search all documents of a specific type\n"
            "- 'namespace_of_doc_key': To search all documents in a namespace\n"
            "Use this to search across many documents at once."
        )
    )
    
    # Search options
    limit: int = Field(
        10,
        ge=1,
        le=10,
        description="Maximum number of search results to return (1-10, default 10)"
    )
    offset: int = Field(
        0,
        ge=0,
        description="Number of results to skip for pagination"
    )
    
    @model_validator(mode='after')
    def validate_search_target(self) -> 'DocumentSearchInputSchema':
        """Ensure exactly one search target is specified."""
        has_document = self.document_identifier is not None
        has_list = self.list_filter is not None
        
        if not has_document and not has_list:
            raise ValueError("Must provide either 'document_identifier' (to search one document) or 'list_filter' (to search multiple)")
        
        if has_document and has_list:
            raise ValueError("Provide either 'document_identifier' or 'list_filter', not both")
            
        return self


class SearchResult(BaseSchema):
    """A single search result."""
    document_info: CustomerDocumentSearchResultMetadata = Field(
        ...,
        description="Metadata about the document containing the match"
    )
    content_preview: str = Field(
        ...,
        description="Preview of the matching content"
    )
    match_score: Optional[float] = Field(
        None,
        description="Relevance score of the match"
    )
    document_contents: Optional[Any] = Field(
        None,
        description="Full document contents fetched from customer data service"
    )


class DocumentSearchOutputSchema(BaseNodeConfig):
    """Output schema for the DocumentSearchTool."""
    success: bool = Field(..., description="Whether the search was successful")
    message: str = Field(..., description="Status message")
    
    results: Dict[str, SearchResult] = Field(
        default_factory=dict,
        description="Dictionary of search results indexed by document serial number"
    )
    
    state_changes: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Dictionary of document metadata indexed by document serial number"
    )
    
    total_results: int = Field(0, description="Total number of results found")
    search_scope: str = Field(..., description="Whether searched in 'single' document or 'multiple' documents")


class DocumentSearchConfigSchema(BaseNodeConfig):
    """Configuration schema for the DocumentSearchTool."""
    max_results_limit: int = Field(
        10,
        description="Maximum number of search results that can be returned"
    )


class DocumentSearchTool(BaseNode[DocumentSearchInputSchema, DocumentSearchOutputSchema, DocumentSearchConfigSchema]):
    """
    Document Search Tool for LLM workflows.
    
    Performs text search within documents using the RAG (Retrieval Augmented Generation) service.
    Can search:
    1. Within a single specific document
    2. Across multiple documents based on filter criteria
    
    Key Features:
    - REQUIRES RAG service to be available (fails if not available)
    - Text-based search with hybrid search (vector + keyword)
    - Flexible targeting (single doc or filtered set)
    - Returns content previews with relevance scores
    - Returns full document contents along with previews
    - Limited to 10 results for performance
    
    Search Targets:
    - Single document by name: Set 'document_identifier' with doc_key and docname
    - Single document by serial number: Set 'document_identifier' with doc_key and document_serial_number
    - Multiple documents: Set 'list_filter' with filter criteria
    
    The entity_username is required but hidden from LLM tool calls.
    The view_context is optional and also hidden from LLM tool calls.
    Documents must be ingested into RAG service to be searchable.
    """
    
    node_name: ClassVar[str] = "search_documents"
    node_version: ClassVar[str] = "2.0.0"
    node_is_tool: ClassVar[bool] = True
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[Type[DocumentSearchInputSchema]] = DocumentSearchInputSchema
    output_schema_cls: ClassVar[Type[DocumentSearchOutputSchema]] = DocumentSearchOutputSchema
    config_schema_cls: ClassVar[Type[DocumentSearchConfigSchema]] = DocumentSearchConfigSchema
    
    async def process(
        self,
        input_data: DocumentSearchInputSchema,
        config: Dict[str, Any],
        *args: Any,
        **kwargs: Any
    ) -> DocumentSearchOutputSchema:
        """Process the document search operation."""
        search_scope = "single" if input_data.document_identifier else "multiple"
        self.info(f"Starting document search in {search_scope} mode for query: '{input_data.search_query}'")
        
        # Extract context from runtime config
        if not config:
            self.error("Missing runtime config (config argument)")
            return DocumentSearchOutputSchema(
                success=False,
                message="Missing runtime config (config argument)",
                search_scope="unknown"
            )
        
        config = config.get("configurable")
        
        app_context: Optional[Dict[str, Any]] = config.get(APPLICATION_CONTEXT_KEY)
        ext_context = config.get(EXTERNAL_CONTEXT_MANAGER_KEY)
        
        if not app_context or not ext_context:
            self.error(f"Missing required keys in runtime_config: {APPLICATION_CONTEXT_KEY}, {EXTERNAL_CONTEXT_MANAGER_KEY}")
            return DocumentSearchOutputSchema(
                success=False,
                message="Missing required context in runtime configuration",
                search_scope="unknown"
            )
        
        user = app_context.get("user")
        run_job = app_context.get("workflow_run_job")
        
        # Get RAG service from external context - it's always available now
        rag_service = ext_context.rag_service
        customer_data_service = ext_context.customer_data_service
        
        if not user or not run_job:
            self.error("Missing user or workflow run job in context")
            return DocumentSearchOutputSchema(
                success=False,
                message="Missing user or workflow run job in application context",
                search_scope="unknown"
            )
        
        if not rag_service:
            self.error("RAG service not available - search functionality requires RAG service")
            return DocumentSearchOutputSchema(
                success=False,
                message="RAG service is required for search functionality",
                search_scope="unknown"
            )
        
        org_id = run_job.owner_org_id
        
        try:
            search_scope = "single" if input_data.document_identifier else "multiple"
            results = {}
            state_changes = {}
            
            # Always use RAG service for search
            # Import RAG schemas
            from kiwi_app.rag_service.schemas import RAGSearchRequest, SearchType
            
            # Build RAG search request
            namespace_filter = None
            doc_name_filter = None
            version_filter = None
            created_after = None
            created_before = None
            scheduled_after = None
            scheduled_before = None
            doc_key = None
            
            if input_data.document_identifier:
                # Single document search - first identify the document
                document_info = identify_document(
                    identifier=input_data.document_identifier,
                    entity_username=input_data.entity_username,
                    view_context=input_data.view_context
                )
                
                if not document_info:
                    self.error("Failed to identify document for search")
                    return DocumentSearchOutputSchema(
                        success=False,
                        message="Failed to identify document for search",
                        results={},
                        state_changes={},
                        total_results=0,
                        search_scope=search_scope
                    )
                if not document_info.user_id_or_shared_placeholder:
                    document_info.user_id_or_shared_placeholder = user.id
                
                # Set filters for specific document
                namespace_filter = document_info.namespace
                doc_name_filter = document_info.docname
                version_filter = document_info.version
                doc_key = input_data.document_identifier.doc_key
                
            else:
                # Multiple document search using list filter
                if input_data.list_filter:
                    # Build query parameters
                    query_params = build_list_query(
                        filter_obj=input_data.list_filter,
                        entity_username=input_data.entity_username
                    )
                    
                    # Extract filter parameters
                    namespace_filter = query_params.get("namespace")
                    doc_key = query_params.get("doc_key")
                    
                    # Extract date filters
                    scheduled_date_range_start = query_params.get("scheduled_after")
                    scheduled_date_range_end = query_params.get("scheduled_before")
                    created_at_range_start = query_params.get("created_after")
                    created_at_range_end = query_params.get("created_before")
                    
                    if scheduled_date_range_start:
                        scheduled_after = scheduled_date_range_start
                    if scheduled_date_range_end:
                        scheduled_before = scheduled_date_range_end
                    if created_at_range_start:
                        created_after = created_at_range_start
                    if created_at_range_end:
                        created_before = created_at_range_end
            
            # Create RAG search request
            rag_request = RAGSearchRequest(
                query=input_data.search_query,
                search_type=SearchType.HYBRID,  # Use hybrid search for best results
                limit=input_data.limit,
                offset=input_data.offset,
                org_id=org_id,
                user_id=user.id,
                namespace_filter=namespace_filter,
                doc_name_filter=doc_name_filter,
                version_filter=version_filter,
                created_after=created_after,
                created_before=created_before,
                scheduled_after=scheduled_after,
                scheduled_before=scheduled_before,
                include_vector=False,
                include_chunk_keys=True,
                alpha=0.5  # Balance between vector and keyword search
            )
            
            # Call RAG service
            rag_response = await rag_service.search_documents(
                search_request=rag_request,
                user=user
            )
            
            # Convert RAG results to DocumentSearchTool format
            # Group results by document for better presentation
            docs_chunks = {}
            for rag_result in rag_response.results:
                doc_id = rag_result.doc_id
                if doc_id not in docs_chunks:
                    docs_chunks[doc_id] = []
                docs_chunks[doc_id].append(rag_result)
            
            # Process each document's chunks
            index = 1
            doc_results = []
            
            for doc_id, chunks in docs_chunks.items():
                # Get the best scoring chunk for preview
                best_chunk = max(chunks, key=lambda c: c.score or 0.0)
                
                # Extract document metadata from the first chunk
                first_chunk = chunks[0]
                
                # Convert to CustomerDocumentSearchResultMetadata
                doc_metadata = CustomerDocumentSearchResultMetadata(
                    id=doc_id,
                    org_id=uuid.UUID(first_chunk.org_segment) if first_chunk.org_segment != CustomerDataService.SYSTEM_DOC_PLACEHOLDER else None,
                    user_id_or_shared_placeholder=first_chunk.user_segment,
                    namespace=first_chunk.namespace,
                    docname=first_chunk.doc_name,
                    version=first_chunk.version,
                    is_versioned=first_chunk.version is not None,
                    is_shared=first_chunk.user_segment == CustomerDataService.SHARED_DOC_PLACEHOLDER,
                    is_system_entity=first_chunk.org_segment == CustomerDataService.SYSTEM_DOC_PLACEHOLDER,
                    is_versioning_metadata=False  # RAG results are actual documents, not versioning metadata
                )
                
                # Use the best chunk's content as preview (full content, no processing)
                content_preview = best_chunk.chunk_content
                
                # Calculate average score across all chunks
                avg_score = sum(c.score or 0.0 for c in chunks) / len(chunks) if chunks else 0.0
                
                # Fetch full document content
                document_contents = await fetch_document_content(
                    document_info=doc_metadata,
                    customer_data_service=customer_data_service,
                    user=user,
                    org_id=org_id
                )
                
                doc_results.append((avg_score, doc_metadata, content_preview, document_contents))
            
            # Sort results by score
            doc_results.sort(key=lambda x: x[0], reverse=True)
            
            # Build final results dictionary
            for score, doc_metadata, content_preview, document_contents in doc_results:
                # Generate serial number
                serial_number = generate_doc_serial_number(doc_key, doc_metadata.docname, index)
                
                # Add to results
                results[serial_number] = SearchResult(
                    document_info=doc_metadata,
                    content_preview=content_preview,
                    match_score=score,
                    document_contents=document_contents
                )
                
                # Build state changes entry
                state_entry = {
                    "docname": doc_metadata.docname
                }
                if doc_metadata.version:
                    state_entry["version"] = doc_metadata.version
                
                state_changes[serial_number] = state_entry
                index += 1
            
            self.info(f"Search completed successfully: found {len(results)} matches for query '{input_data.search_query}'")
            
            return DocumentSearchOutputSchema(
                success=True,
                message=f"Found {len(results)} matches for '{input_data.search_query}' using RAG search",
                results=results,
                state_changes=state_changes,
                total_results=len(results),
                search_scope=search_scope
            )
            
        except Exception as e:
            self.error(f"Error in document search: {e}", exc_info=True)
            return DocumentSearchOutputSchema(
                success=False,
                message=f"Error: {str(e)}",
                results={},
                state_changes={},
                total_results=0,
                search_scope="error"
            )


# --- List Documents Tool ---

class ListDocumentsInputSchema(BaseDocumentInputSchema):
    """
    Input schema for the ListDocumentsTool.
    
    This tool lists documents based on filter criteria, returning metadata only (not full content).
    It's designed for browsing and discovering documents when you don't know exact names.
    
    Required Field:
    - 'list_filter': Defines what documents to list
    
    Filter Options:
    The 'list_filter' must include one of these:
    - 'doc_key': List all documents of a specific type (e.g., 'brief', 'concept', 'idea')
    - 'namespace_of_doc_key': List all documents in a namespace (e.g., all docs in the 'concept' namespace)
    
    Optional Filters:
    - Date ranges: Filter by scheduled dates or creation dates
      * scheduled_date_range_start/end: For time-sensitive docs like briefs
      * created_at_range_start/end: Filter by when documents were created
    
    Pagination:
    - 'limit': Number of documents to return (1-10, default 10)
    - 'offset': Skip documents for pagination
    
    Common Use Cases:
    1. List all briefs:
       list_filter: {doc_key: "brief"}
    
    2. List recent concepts:
       list_filter: {doc_key: "concept", created_at_range_start: "2024-01-01T00:00:00Z"}
    
    3. List concepts with pagination:
       list_filter: {doc_key: "concept"}
       limit: 5
       offset: 10
    
    4. List all documents in concept namespace (includes shared docs):
       list_filter: {namespace_of_doc_key: "concept"}
    
    5. List scheduled briefs for next week:
       list_filter: {
         doc_key: "brief",
         scheduled_date_range_start: "2024-01-15T00:00:00Z",
         scheduled_date_range_end: "2024-01-22T00:00:00Z"
       }
    
    Notes:
    - Returns document metadata only, not full content (use view_documents for full content)
    - Results include both user-specific and shared documents
    - Pagination may not be 100% accurate due to versioning metadata documents being filtered out
    - Dates should be in ISO format: YYYY-MM-DDTHH:MM:SSZ
    """
    # Required list filter
    list_filter: DocumentListFilter = Field(
        ...,
        description=(
            "Filter criteria for listing documents. Must specify either:\n"
            "- 'doc_key': To list all documents of a specific type (e.g., 'brief', 'concept')\n"
            "- 'namespace_of_doc_key': To list all documents in a namespace\n"
            "Can also include optional date filters:\n"
            "- scheduled_date_range_start/end: Filter by scheduled dates (for briefs/posts)\n"
            "- created_at_range_start/end: Filter by creation dates\n"
            "Dates should be in ISO format: YYYY-MM-DDTHH:MM:SSZ"
        )
    )
    
    # Pagination
    limit: int = Field(
        10,
        ge=1,
        le=10,
        description=(
            "Maximum number of documents to list (1-10, default 10). "
            "Use smaller values for quick browsing, larger for comprehensive lists."
        )
    )
    offset: int = Field(
        0,
        ge=0,
        description=(
            "Number of documents to skip for pagination. "
            "Use 0 for first page, then increment by 'limit' for subsequent pages."
        )
    )


class DocumentListItem(BaseSchema):
    """A single document in the list."""
    document_info: CustomerDocumentSearchResultMetadata = Field(
        ...,
        description="Metadata about the document"
    )


class ListDocumentsOutputSchema(BaseNodeConfig):
    """Output schema for the ListDocumentsTool."""
    success: bool = Field(..., description="Whether the list operation was successful")
    message: str = Field(..., description="Status message")
    
    documents: Dict[str, DocumentListItem] = Field(
        default_factory=dict,
        description="Dictionary of documents with metadata indexed by document serial number"
    )
    
    state_changes: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Dictionary of document metadata indexed by document serial number"
    )
    
    total_count: int = Field(0, description="Total number of documents matching the filter")
    filter_applied: Dict[str, Any] = Field(
        default_factory=dict,
        description="The filter criteria that were applied"
    )


class ListDocumentsConfigSchema(BaseNodeConfig):
    """Configuration schema for the ListDocumentsTool."""
    max_list_limit: int = Field(
        10,
        description="Maximum number of documents that can be listed at once"
    )


class ListDocumentsTool(BaseNode[ListDocumentsInputSchema, ListDocumentsOutputSchema, ListDocumentsConfigSchema]):
    """
    List Documents Tool for LLM workflows.
    
    Lists documents based on filter criteria such as doc_key or namespace.
    Designed for browsing and discovering documents.
    
    Key Features:
    - Filter by doc_key or namespace_of_doc_key
    - Optional date range filtering
    - Pagination support (max 10 documents per page)
    - Returns document metadata and previews
    
    Filter Options:
    - By doc_key: Lists all documents of a specific type
    - By namespace: Lists all documents in a namespace
    - Date ranges: Filter by scheduled or created dates
    
    The entity_username is required but hidden from LLM tool calls.
    Always returns up to 10 documents per request for performance.
    """
    
    node_name: ClassVar[str] = "list_documents"
    node_version: ClassVar[str] = "2.0.0"
    node_is_tool: ClassVar[bool] = True
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[Type[ListDocumentsInputSchema]] = ListDocumentsInputSchema
    output_schema_cls: ClassVar[Type[ListDocumentsOutputSchema]] = ListDocumentsOutputSchema
    config_schema_cls: ClassVar[Type[ListDocumentsConfigSchema]] = ListDocumentsConfigSchema
    
    async def process(
        self,
        input_data: ListDocumentsInputSchema,
        config: Dict[str, Any],
        *args: Any,
        **kwargs: Any
    ) -> ListDocumentsOutputSchema:
        """Process the list documents operation."""
        doc_key = input_data.list_filter.doc_key if input_data.list_filter.doc_key else "documents"
        self.info(f"Starting document listing for {doc_key} with limit {input_data.limit}")
        
        # Extract context from runtime config
        if not config:
            self.error("Missing runtime config (config argument)")
            return ListDocumentsOutputSchema(
                success=False,
                message="Missing runtime config (config argument)"
            )
        
        config = config.get("configurable")
        
        app_context: Optional[Dict[str, Any]] = config.get(APPLICATION_CONTEXT_KEY)
        ext_context = config.get(EXTERNAL_CONTEXT_MANAGER_KEY)
        
        if not app_context or not ext_context:
            self.error(f"Missing required keys in runtime_config: {APPLICATION_CONTEXT_KEY}, {EXTERNAL_CONTEXT_MANAGER_KEY}")
            return ListDocumentsOutputSchema(
                success=False,
                message="Missing required context in runtime configuration"
            )
        
        user = app_context.get("user")
        run_job = app_context.get("workflow_run_job")
        customer_data_service: CustomerDataService = ext_context.customer_data_service
        
        if not user or not run_job or not customer_data_service:
            self.error("Missing user, workflow run job, or customer data service in context")
            return ListDocumentsOutputSchema(
                success=False,
                message="Missing user, workflow run job, or customer data service in application context"
            )
        
        org_id = run_job.owner_org_id
        
        try:
            # Build query parameters
            query_params = build_list_query(
                filter_obj=input_data.list_filter,
                entity_username=input_data.entity_username
            )
            
            # Extract filter parameters
            namespace_filter = query_params.get("namespace")
            doc_key = query_params.get("doc_key")
            
            # Extract date filters from query_params
            scheduled_date_range_start = query_params.get("scheduled_after")
            scheduled_date_range_end = query_params.get("scheduled_before")
            created_at_range_start = query_params.get("created_after")
            created_at_range_end = query_params.get("created_before")
            
            # Build value filter for date ranges
            value_filter = {}
            if scheduled_date_range_start or scheduled_date_range_end:
                value_filter["scheduled_date"] = {}
                if scheduled_date_range_start:
                    value_filter["scheduled_date"]["$gte"] = scheduled_date_range_start
                if scheduled_date_range_end:
                    value_filter["scheduled_date"]["$lte"] = scheduled_date_range_end
                    
            if created_at_range_start or created_at_range_end:
                value_filter["created_at"] = {}
                if created_at_range_start:
                    value_filter["created_at"]["$gte"] = created_at_range_start
                if created_at_range_end:
                    value_filter["created_at"]["$lte"] = created_at_range_end
            
            # Use search_documents from customer data service
            search_results = await customer_data_service.search_documents(
                org_id=org_id,
                user=user,
                namespace_filter=namespace_filter,
                text_search_query=None,  # No text search for listing
                value_filter=value_filter if value_filter else None,
                include_shared=True,
                include_user_specific=True,
                skip=input_data.offset,
                limit=input_data.limit,
                include_system_entities=False,
                is_called_from_workflow=True
            )
            
            # Convert search results to DocumentListItem format
            documents = {}
            state_changes = {}
            index = 1
            
            for search_result in search_results:
                # Skip versioning metadata entries
                if search_result.metadata.is_versioning_metadata:
                    continue
                
                # Generate serial number
                serial_number = generate_doc_serial_number(doc_key, search_result.metadata.docname, index)
                
                # Add to results
                documents[serial_number] = DocumentListItem(
                    document_info=search_result.metadata
                )
                
                # Build state changes entry
                state_entry = {
                    "docname": search_result.metadata.docname
                }
                if search_result.metadata.version:
                    state_entry["version"] = search_result.metadata.version
                
                state_changes[serial_number] = state_entry
                index += 1
            
            self.info(f"Successfully listed {len(documents)} documents")
            
            return ListDocumentsOutputSchema(
                success=True,
                message=f"Listed {len(documents)} documents",
                documents=documents,
                state_changes=state_changes,
                total_count=len(documents),
                filter_applied=query_params
            )
            
        except Exception as e:
            self.error(f"Error listing documents: {e}", exc_info=True)
            return ListDocumentsOutputSchema(
                success=False,
                message=f"Error: {str(e)}",
                documents={},
                state_changes={},
                total_count=0,
                filter_applied={}
            ) 

if __name__ == "__main__":
    from workflow_service.registry.nodes.llm.llm_node import LLMStructuredOutputSchema
    json_schema = EditDocumentInputSchema.model_json_schema()  # EditDocumentInputSchema  DocumentSearchInputSchema  ListDocumentsInputSchema
    json_schema = LLMStructuredOutputSchema._recursive_set_json_schema_to_openai_format(json_schema)

    print(json.dumps(json_schema, indent=4))
    import ipdb; ipdb.set_trace()



    field_definitions = {}
    for k,v in ListDocumentsInputSchema.model_fields.items():
        if BaseSchema._is_field_for_llm_tool_call(v):
            # Create a new FieldInfo with default removed and is_required set to True
            # This ensures LLM tools see all fields as required for proper tool calling
            modified_field = v
            # NOTE: hack for openai schemas since they don't support default, etc

            modified_field = FieldInfo(
                # Don't pass any default value - this makes the field required
                annotation=v.annotation,
                description=v.description,
                title=v.title,
                examples=v.examples,
                json_schema_extra=v.json_schema_extra,
                metadata=v.metadata,
                # Explicitly exclude default and default_factory to make field required
                # All other field properties are preserved
            )
            

            field_definitions[k] = (v.annotation, modified_field)
            if k in ["limit", "offset"]:
                import ipdb; ipdb.set_trace()



    print(json.dumps(json_schema, indent=4))
    import ipdb; ipdb.set_trace()
    """
    "limit": {
            "default": 10,
            "description": "Maximum number of search results to return (1-10, default 10)",
            "maximum": 10,
            "minimum": 1,
            "title": "Limit",
            "type": "integer"
        },
    """
    field_definitions = {}
    for k,v in DocumentSearchInputSchema.model_fields.items():
        if BaseSchema._is_field_for_llm_tool_call(v):
            # Create a new FieldInfo with default removed and is_required set to True
            # This ensures LLM tools see all fields as required for proper tool calling
            modified_field = v
            modified_field = FieldInfo(
                # Don't pass any default value - this makes the field required
                annotation=v.annotation,
                description=v.description,
                title=v.title,
                examples=v.examples,
                json_schema_extra=v.json_schema_extra,
                metadata=v.metadata,
                # Explicitly exclude default and default_factory to make field required
                # All other field properties are preserved
            )
            

            field_definitions[k] = (v.annotation, modified_field)

    tool_for_binding = create_model(
        DocumentSearchInputSchema.__name__,
        __base__=(BaseNodeConfig),
        __doc__=DocumentSearchInputSchema.__doc__,
        __module__=DocumentSearchInputSchema.__module__,  # module_name or 
        # Only bind user editable fields, hide other fields!
        **field_definitions
    )
    print(json.dumps(tool_for_binding.model_json_schema(), indent=4))
