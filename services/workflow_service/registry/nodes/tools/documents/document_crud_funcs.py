"""
Document CRUD Functions - Simple schemas and functions for document identification and retrieval.

This module provides schemas and utility functions for:
1. Identifying specific documents by doc key, filters, or view context
2. Listing and filtering documents for search queries
3. Resolving document parameters from doc keys using app_artifacts.py configurations
"""

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Tuple
from pydantic import BaseModel, Field, field_validator, model_validator

# Import from app_artifacts to use the actual configurations and classes
from kiwi_app.workflow_app.app_artifacts import (
    DEFAULT_USER_DOCUMENTS_CONFIG,
    UserDocumentConfig,
    UserDocumentsConfig
)
from workflow_service.registry.schemas.base import BaseSchema
from kiwi_app.workflow_app.schemas import CustomerDocumentSearchResultMetadata

# --- Helper Functions to work with app_artifacts.py ---

def get_doc_config(doc_key: str) -> Optional[UserDocumentConfig]:
    """
    Get the document configuration for a given doc key.
    
    Args:
        doc_key: The document key (e.g., 'user_dna_doc', 'brief', etc.)
        
    Returns:
        UserDocumentConfig instance or None if not found
    """
    return DEFAULT_USER_DOCUMENTS_CONFIG.get_document_config(doc_key)


def resolve_doc_params(
    doc_key: str, 
    entity_username: str,
    additional_vars: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Resolve document parameters (namespace, docname, etc.) from a doc key.
    
    Args:
        doc_key: The document key
        entity_username: The entity username for namespace resolution
        additional_vars: Additional template variables (e.g., _uuid_, post_uuid)
        
    Returns:
        Dict with resolved namespace, docname, and other params, or None if doc_key not found
    """
    doc_config = get_doc_config(doc_key)
    if not doc_config:
        return None
    
    # Prepare template variables
    template_vars = {"entity_username": entity_username}
    if additional_vars:
        template_vars.update(additional_vars)
    
    built_config = doc_config.build_document_templates(
        input_variables=template_vars,
        partial=True
    )
    return built_config


def is_high_cardinality_doc(doc_key: str) -> bool:
    """
    Check if a document type is high cardinality.
    
    High cardinality documents are those that have template variables other than entity_username
    in either their docname_template or namespace_template.
    
    Args:
        doc_key: The document key
        
    Returns:
        True if the document has template variables other than entity_username
    """
    doc_config = get_doc_config(doc_key)
    if not doc_config:
        return False
    
    # Get template info to check required variables
    template_info = doc_config.get_template_info()
    
    # Get all placeholders from both templates
    all_placeholders = set(template_info.get("all_placeholders", []))
    
    # Remove entity_username from the set
    placeholders_without_entity_username = all_placeholders - {"entity_username"}
    
    # If there are any other placeholders, it's high cardinality
    return len(placeholders_without_entity_username) > 0


def supports_scheduled_date(doc_key: str) -> bool:
    """
    Check if a document type supports scheduled_date field.
    
    Args:
        doc_key: The document key
        
    Returns:
        True if the document type supports scheduled dates
    """
    # Documents that typically have scheduled dates
    scheduled_date_docs = {"brief", "draft"}
    return doc_key in scheduled_date_docs


def get_required_template_vars(doc_key: str) -> Dict[str, List[str]]:
    """
    Get the required template variables for a document key.
    
    Args:
        doc_key: The document key
        
    Returns:
        Dict with 'docname_vars' and 'namespace_vars' lists
    """
    doc_config = get_doc_config(doc_key)
    if not doc_config:
        return {"docname_vars": [], "namespace_vars": []}
    
    template_info = doc_config.get_template_info()
    
    # Get placeholders that don't have defaults
    required_vars = template_info.get("required_variables_without_defaults", [])
    
    # Separate by template type
    docname_placeholders = set(template_info.get("docname_placeholders", []))
    namespace_placeholders = set(template_info.get("namespace_placeholders", []))
    
    docname_required = [var for var in required_vars if var in docname_placeholders]
    namespace_required = [var for var in required_vars if var in namespace_placeholders]
    
    return {
        "docname_vars": docname_required,
        "namespace_vars": namespace_required
    }


# --- Schemas for Document Identification ---

class DocumentIdentifier(BaseModel):
    """
    Combined schema for identifying a document.
    
    Requirements:
    - Always provide doc_key
    - For high cardinality documents: must provide either docname OR document_serial_number (not both)
    - For unitary documents: doc_key alone is sufficient (docname/serial_number not required)
    """
    doc_key: str = Field(..., description="The exact document key from provided documents config")
    
    # Identification method - only one should be provided
    docname: Optional[str] = Field(None, description="Direct document name (for high cardinality docs)")
    document_serial_number: Optional[str] = Field(None, description="Serial number from tool outputs view context (generated string identifier)")
    
    # Optional fields
    version: Optional[str] = Field(None, description="Document version (for versioned docs)", json_schema_extra={BaseSchema.FOR_LLM_TOOL_CALL_FIELD_KEY: False})
    # view_context: Optional[Dict[int, Dict[str, str]]] = Field(
    #     None, 
    #     description="View context mapping S.No. to document info: {1: {'docname': 'doc1', 'version': 'draft'}, ...}"
    # )
    
    @field_validator('doc_key')
    def validate_doc_key(cls, v: str) -> str:
        """Validate that the doc_key exists in configuration."""
        if not get_doc_config(v):
            raise ValueError(f"Unknown doc_key: {v}")
        return v
    
    @model_validator(mode='after')
    def validate_identification_method(self) -> 'DocumentIdentifier':
        """
        Validate identification method based on document cardinality.
        - For high cardinality docs: require either docname or document_serial_number
        - For unitary docs: doc_key alone is sufficient
        """
        has_docname = self.docname is not None
        has_serial = self.document_serial_number is not None
        
        # Check if this is a high cardinality document
        is_high_card = is_high_cardinality_doc(self.doc_key)
        
        if is_high_card:
            # High cardinality docs need additional identification
            if not has_docname and not has_serial:
                raise ValueError(
                    f"High cardinality document '{self.doc_key}' requires either 'docname' or 'document_serial_number'"
                )
            
        # Unitary docs: doc_key is sufficient, but docname/serial can still be provided if needed
        if has_docname and has_serial:
            raise ValueError("Provide either 'docname' or 'document_serial_number', not both")
        
        return self
    
    def resolve(self, entity_username: str, view_context: Optional[Dict[str, Dict[str, str]]] = None) -> Dict[str, Any]:
        """Resolve to full document parameters."""
        # For unitary docs (no additional vars needed)
        # if not is_high_cardinality_doc(self.doc_key):
        resolved_doc_params = resolve_doc_params(self.doc_key, entity_username)
        
        # For high cardinality docs
        additional_vars = {}
        actual_docname = self.docname

        if self.document_serial_number and not view_context:
            raise ValueError("When using document_serial_number, view_context should be provided")
        if self.document_serial_number and view_context and self.document_serial_number not in view_context:
            raise ValueError(f"Serial number {self.document_serial_number} not found in view_context")
        
        # If using serial number, get docname from view context
        actual_version = self.version
        if self.document_serial_number and view_context:
            doc_info = view_context.get(self.document_serial_number, {})
            actual_docname = doc_info.get("docname")
            actual_version = doc_info.get("version") or actual_version
        
        if actual_docname:
            resolved_doc_params["docname"] = actual_docname

        if actual_version:
            resolved_doc_params["version"] = actual_version
        
        return resolved_doc_params
    

# --- Schemas for Listing and Filtering ---

class DocumentListFilter(BaseModel):
    """
    Combined schema for listing and filtering documents.
    Must provide either doc_key OR namespace_of_doc_key (not both).
    """
    
    # Filter method - only one should be provided
    doc_key: Optional[str] = Field(None, description="Filter by specific doc key")
    namespace_of_doc_key: Optional[str] = Field(
        None, 
        description="Mention the doc key whose namespace will be used for filtering. This will automatically resolve the correct namespace including template vars, given the correct doc key."
    )
    
    # Date range filters
    scheduled_date_range_start: Optional[datetime] = Field(
        None,
        description="Filter docs scheduled after this date (YYYY-MM-DDTHH:MM:SSZ UTC format)"
    )
    scheduled_date_range_end: Optional[datetime] = Field(
        None,
        description="Filter docs scheduled before this date (YYYY-MM-DDTHH:MM:SSZ UTC format)"
    )
    created_at_range_start: Optional[datetime] = Field(
        None,
        description="Filter docs created after this date (YYYY-MM-DDTHH:MM:SSZ UTC format)"
    )
    created_at_range_end: Optional[datetime] = Field(
        None,
        description="Filter docs created before this date (YYYY-MM-DDTHH:MM:SSZ UTC format)"
    )
    
    # # Pagination
    # limit: int = Field(10, ge=1, le=100, description="Maximum number of results")
    # offset: int = Field(0, ge=0, description="Offset for pagination")
    
    @model_validator(mode='after')
    def validate_filter_method(self) -> 'DocumentListFilter':
        """Ensure exactly one filter method is provided."""
        has_doc_key = self.doc_key is not None
        has_namespace_key = self.namespace_of_doc_key is not None
        
        if not has_doc_key and not has_namespace_key:
            raise ValueError("Must provide either 'doc_key' or 'namespace_of_doc_key'")
        
        if has_doc_key and has_namespace_key:
            raise ValueError("Provide either 'doc_key' or 'namespace_of_doc_key', not both")
        
        # Validate doc keys exist
        if has_doc_key and not get_doc_config(self.doc_key):
            raise ValueError(f"Unknown doc_key: {self.doc_key}")
        
        if has_namespace_key and not get_doc_config(self.namespace_of_doc_key):
            raise ValueError(f"Unknown namespace_of_doc_key: {self.namespace_of_doc_key}")
        
        return self
    
    @model_validator(mode='after')
    def validate_date_ranges(self) -> 'DocumentListFilter':
        """Validate date range formats and logic."""
        # Validate scheduled_date_range
        if self.scheduled_date_range_start and self.scheduled_date_range_end:
            if self.scheduled_date_range_start >= self.scheduled_date_range_end:
                raise ValueError("scheduled_date_range: start must be before end")
        
        # Check if doc_key supports scheduled dates when scheduled date filters are used
        if (self.scheduled_date_range_start or self.scheduled_date_range_end):
            check_key = self.doc_key or self.namespace_of_doc_key
            if check_key and not supports_scheduled_date(check_key):
                raise ValueError(f"Doc key '{check_key}' does not support scheduled dates")
        
        # Validate created_at_range
        if self.created_at_range_start and self.created_at_range_end:
            if self.created_at_range_start >= self.created_at_range_end:
                raise ValueError("created_at_range: start must be before end")
        
        return self
    
    def get_namespace(self, entity_username: str) -> str:
        """Get the namespace for filtering."""
        key_to_use = self.doc_key or self.namespace_of_doc_key
        if key_to_use:
            params = resolve_doc_params(key_to_use, entity_username)
            return params["namespace"] if params else ""
        return ""
    
    def to_query_params(self, entity_username: str) -> Dict[str, Any]:
        """Convert to query parameters for document listing."""
        params = {
            "namespace": self.get_namespace(entity_username),
            # "limit": self.limit,
            # "offset": self.offset
        }
        
        # Add the actual doc_key if filtering by doc_key
        if self.doc_key:
            params["doc_key"] = self.doc_key
            params["filter_type"] = "doc_key"
        else:
            params["filter_type"] = "namespace"
        
        # Add date filters
        if self.scheduled_date_range_start:
            params["scheduled_after"] = self.scheduled_date_range_start
        if self.scheduled_date_range_end:
            params["scheduled_before"] = self.scheduled_date_range_end
        
        if self.created_at_range_start:
            params["created_after"] = self.created_at_range_start
        if self.created_at_range_end:
            params["created_before"] = self.created_at_range_end
        
        return params


# --- Response Schemas ---

class DocumentInfo(BaseModel):
    """Information about a resolved document."""
    doc_key: str
    namespace: str
    docname: str
    is_shared: bool
    is_versioned: bool
    is_system_entity: bool
    supports_scheduled_date: bool
    is_high_cardinality: bool
    required_template_vars: Dict[str, List[str]]


# --- Utility Functions ---

def identify_document(
    identifier: DocumentIdentifier,
    entity_username: str,
    view_context: Optional[Dict[str, Dict[str, str]]] = None
) -> Optional[CustomerDocumentSearchResultMetadata]:
    """
    Identify a document using the DocumentIdentifier schema.
    
    Args:
        identifier: DocumentIdentifier instance with doc_key and either docname or document_serial_number
        entity_username: Entity username for namespace resolution
        view_context: Optional view context mapping for serial number resolution
        
    Returns:
        CustomerDocumentSearchResultMetadata if successful, None otherwise
    """
    
    try:
        params = identifier.resolve(entity_username=entity_username, view_context=view_context)
        if not params:
            return None
        
        return CustomerDocumentSearchResultMetadata(
            versionless_path=None,  # Will be populated by actual service
            id=None,  # Will be populated by actual service
            org_id=None,  # Will be populated by actual service
            user_id_or_shared_placeholder="_shared_" if params.get("is_shared", False) else None,
            namespace=params["namespace"],
            docname=params["docname"],
            is_versioned=params.get("is_versioned", True),
            is_shared=params.get("is_shared", False),
            is_system_entity=params.get("is_system_entity", False),
            version=params.get("version"),
            is_active_version=True if params.get("version") else None,
            is_versioning_metadata=False
        )
        
    except Exception as e:
        print(f"Error identifying document: {e}")
        return None


def build_list_query(
    filter_obj: DocumentListFilter,
    entity_username: str
) -> Dict[str, Any]:
    """
    Build a query for listing documents using the DocumentListFilter schema.
    
    Args:
        filter_obj: DocumentListFilter instance with filter criteria
        entity_username: Entity username for namespace resolution
        
    Returns:
        Query parameters dict
    """
    try:
        return filter_obj.to_query_params(entity_username=entity_username)
    except Exception as e:
        print(f"Error building list query: {e}")
        return {}


# --- Example Usage Functions ---

def example_identify_unitary_doc():
    """Example: Identify a unitary document like user_dna_doc."""
    identifier = DocumentIdentifier(
        doc_key="user_dna_doc"
        # For unitary docs, doc_key alone is sufficient - no docname needed
    )
    doc_info = identify_document(
        identifier=identifier,
        entity_username="john_doe"
    )
    print(f"Identified unitary doc: {doc_info}")
    return doc_info


def example_identify_high_cardinality_doc_by_name():
    """Example: Identify a high cardinality document by direct name."""
    identifier = DocumentIdentifier(
        doc_key="brief",
        docname="brief_123e4567-e89b-12d3-a456-426614174000"
    )
    doc_info = identify_document(
        identifier=identifier,
        entity_username="john_doe"
    )
    print(f"Identified by docname: {doc_info}")
    return doc_info


def example_identify_doc_by_serial_number():
    """Example: Identify a document by serial number from view context."""
    view_context = {
        "brief_23_1": {"docname": "brief_123e4567-e89b-12d3-a456-426614174000"},
        "brief_23_2": {"docname": "brief_234e5678-f90c-23e4-b567-537725285111"},
        "brief_23_3": {"docname": "brief_345e6789-g01d-34f5-c678-648836396222"}
    }
    
    identifier = DocumentIdentifier(
        doc_key="brief",
        document_serial_number="brief_23_2"
    )
    doc_info = identify_document(
        identifier=identifier,
        entity_username="john_doe",
        view_context=view_context
    )
    print(f"Identified by serial number: {doc_info}")
    return doc_info


def example_list_by_doc_key():
    """Example: List documents by doc key."""
    filter_obj = DocumentListFilter(
        doc_key="brief",
        limit=20
    )
    query = build_list_query(
        filter_obj=filter_obj,
        entity_username="john_doe"
    )
    print(f"List by doc_key query: {query}")
    return query


def example_list_by_namespace():
    """Example: List documents using namespace of a doc key."""
    filter_obj = DocumentListFilter(
        namespace_of_doc_key="brief",  # Will use content_briefs_john_doe namespace
        limit=50
    )
    query = build_list_query(
        filter_obj=filter_obj,
        entity_username="john_doe"
    )
    print(f"List by namespace query: {query}")
    return query


def example_list_scheduled_briefs():
    """Example: List briefs scheduled in a date range."""
    from datetime import timezone
    
    filter_obj = DocumentListFilter(
        doc_key="brief",
        scheduled_date_range_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        scheduled_date_range_end=datetime(2024, 1, 31, 23, 59, 59, tzinfo=timezone.utc),
        limit=50
    )
    query = build_list_query(
        filter_obj=filter_obj,
        entity_username="john_doe"
    )
    print(f"List scheduled briefs query: {query}")
    return query


def example_list_recently_created():
    """Example: List recently created documents."""
    from datetime import timezone, timedelta
    
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    
    filter_obj = DocumentListFilter(
        namespace_of_doc_key="concept",  # List from concept namespace
        created_at_range_start=seven_days_ago,
        created_at_range_end=now,
        limit=100
    )
    query = build_list_query(
        filter_obj=filter_obj,
        entity_username="john_doe"
    )
    print(f"List recently created query: {query}")
    return query


def example_check_high_cardinality():
    """Example: Check which documents are high cardinality."""
    doc_keys = ["user_dna_doc", "brief", "concept", "draft", "content_strategy_doc"]
    
    print("\nDocument Type Analysis:")
    print("-" * 60)
    for doc_key in doc_keys:
        is_high_card = is_high_cardinality_doc(doc_key)
        template_vars = get_required_template_vars(doc_key)
        print(f"{doc_key}:")
        print(f"  High cardinality: {is_high_card}")
        print(f"  Required vars: {template_vars}")
    
    return None


def example_validate_inputs():
    """Example: Show validation errors for invalid inputs."""
    print("\nValidation Examples:")
    print("-" * 60)
    
    # Valid: Unitary document with just doc_key
    try:
        identifier = DocumentIdentifier(
            doc_key="user_dna_doc"
            # No docname or document_serial_number needed for unitary docs
        )
        print(f"Success (unitary doc): {identifier.doc_key} - valid with just doc_key")
    except ValueError as e:
        print(f"Error (unitary doc): {e}")
    
    # Invalid: High cardinality document without identification method
    try:
        identifier = DocumentIdentifier(
            doc_key="brief"
            # Missing both docname and document_serial_number for high cardinality doc
        )
    except ValueError as e:
        print(f"Error (high cardinality missing identification): {e}")
    
    # Invalid: Both identification methods provided
    try:
        identifier = DocumentIdentifier(
            doc_key="brief",
            docname="brief_123",
            document_serial_number="brief_23_1"  # Can't have both
        )
    except ValueError as e:
        print(f"Error (both methods): {e}")
    
    # Invalid: Missing filter method
    try:
        filter_obj = DocumentListFilter(
            # Missing both doc_key and namespace_of_doc_key
        )
    except ValueError as e:
        print(f"Error (missing filter): {e}")
    
    # Invalid: Invalid date range
    try:
        filter_obj = DocumentListFilter(
            doc_key="brief",
            scheduled_date_range_start=datetime(2024, 1, 31),
            scheduled_date_range_end=datetime(2024, 1, 1)  # End before start
        )
    except ValueError as e:
        print(f"Error (invalid date range): {e}")
    
    return None


if __name__ == "__main__":
    # Run examples
    print("=" * 60)
    print("Document Identification and Listing Examples")
    print("=" * 60)
    
    example_identify_unitary_doc()
    print()
    
    example_identify_high_cardinality_doc_by_name()
    print()
    
    example_identify_doc_by_serial_number()
    print()
    
    example_list_by_doc_key()
    print()
    
    example_list_by_namespace()
    print()
    
    example_list_scheduled_briefs()
    print()
    
    example_list_recently_created()
    print()
    
    example_check_high_cardinality()
    print()
    
    example_validate_inputs()
