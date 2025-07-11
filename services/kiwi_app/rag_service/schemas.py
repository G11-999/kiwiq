"""
RAG Service schemas for KiwiQ system.

This module defines Pydantic schemas for RAG (Retrieval Augmented Generation) operations including
document search, ingestion, and deletion. These schemas provide proper typing and validation
for the RAG service endpoints.
"""

import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from enum import Enum

from pydantic import BaseModel, Field, field_validator

# --- Enums --- #

class SearchType(str, Enum):
    """Types of search supported by RAG service."""
    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"

class SortOrder(str, Enum):
    """Sort order options."""
    ASC = "asc"
    DESC = "desc"

# --- Base Schemas --- #

class RAGBaseRequest(BaseModel):
    """Base schema for RAG requests with common fields."""
    org_id: Optional[uuid.UUID] = Field(None, description="Organization ID filter (superuser only - regular users automatically use their active org)")
    user_id: Optional[uuid.UUID] = Field(None, description="User ID filter (optional - regular users can only filter by their own user ID)")

# --- Search Schemas --- #

class RAGSearchRequest(RAGBaseRequest):
    """Schema for RAG search requests."""
    query: str = Field(..., description="Search query text", min_length=1, max_length=1000)
    search_type: SearchType = Field(SearchType.HYBRID, description="Type of search to perform")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results to return")
    offset: int = Field(0, ge=0, description="Number of results to skip for pagination")
    
    # Vector search specific
    alpha: Optional[float] = Field(None, ge=0.0, le=1.0, description="Hybrid search balance (1.0=vector, 0.0=keyword)")
    
    # Filtering options
    namespace_filter: Optional[str] = Field(None, description="Filter by document namespace")
    doc_name_filter: Optional[str] = Field(None, description="Filter by document name")
    version_filter: Optional[str] = Field(None, description="Filter by document version")
    
    # Date range filtering
    created_after: Optional[datetime] = Field(None, description="Filter documents created after this date")
    created_before: Optional[datetime] = Field(None, description="Filter documents created before this date")
    updated_after: Optional[datetime] = Field(None, description="Filter documents updated after this date")
    updated_before: Optional[datetime] = Field(None, description="Filter documents updated before this date")
    scheduled_after: Optional[datetime] = Field(None, description="Filter documents scheduled after this date")
    scheduled_before: Optional[datetime] = Field(None, description="Filter documents scheduled before this date")
    
    # Chunk content filtering
    chunk_keys_contain: Optional[List[str]] = Field(None, description="Filter by chunk keys containing these values")
    
    # Return options
    include_vector: bool = Field(False, description="Whether to include vector embeddings in results")
    include_chunk_keys: bool = Field(True, description="Whether to include chunk keys in results")

class RAGSearchResult(BaseModel):
    """Schema for individual search results."""
    uuid: str = Field(..., description="Weaviate chunk UUID")
    doc_id: str = Field(..., description="Original document ID")
    org_segment: str = Field(..., description="Organization segment")
    user_segment: str = Field(..., description="User segment")
    namespace: str = Field(..., description="Document namespace")
    doc_name: str = Field(..., description="Document name")
    version: Optional[str] = Field(None, description="Document version")
    chunk_no: int = Field(..., description="Chunk number within document")
    chunk_content: str = Field(..., description="Chunk content text")
    chunk_keys: Optional[List[str]] = Field(None, description="Extracted JSON keys from chunk")
    
    # Temporal fields
    created_at: Optional[datetime] = Field(None, description="Document creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Document update timestamp")
    scheduled_date: Optional[datetime] = Field(None, description="Document scheduled date")
    
    # Search relevance
    score: Optional[float] = Field(None, description="Search relevance score")
    distance: Optional[float] = Field(None, description="Vector distance (lower is better)")
    certainty: Optional[float] = Field(None, description="Vector certainty (higher is better)")
    
    # Optional fields
    vector: Optional[List[float]] = Field(None, description="Vector embeddings if requested")

class RAGSearchResponse(BaseModel):
    """Schema for RAG search response."""
    results: List[RAGSearchResult] = Field(..., description="Search results")
    total_results: int = Field(..., description="Total number of results found")
    search_params: Dict[str, Any] = Field(..., description="Search parameters used")
    execution_time_ms: Optional[float] = Field(None, description="Query execution time in milliseconds")

# --- Document Management Schemas --- #

class RAGDocumentDeleteRequest(RAGBaseRequest):
    """Schema for deleting documents from RAG vector database."""
    doc_ids: List[str] = Field(..., description="List of document IDs to delete", min_length=1, max_length=100)
    
    @field_validator('doc_ids')
    def validate_doc_ids(cls, v):
        if not v:
            raise ValueError("At least one document ID must be provided")
        return v

class RAGDocumentDeleteResponse(BaseModel):
    """Schema for document deletion response."""
    success: bool = Field(..., description="Whether the operation was successful")
    deleted_doc_ids: List[str] = Field(..., description="List of successfully deleted document IDs")
    failed_doc_ids: List[str] = Field(default_factory=list, description="List of document IDs that failed to delete")
    total_chunks_deleted: int = Field(..., description="Total number of chunks deleted")
    errors: List[str] = Field(default_factory=list, description="Error messages for failed deletions")

class RAGDocumentIngestRequest(RAGBaseRequest):
    """Schema for reingesting documents into RAG vector database."""
    doc_ids: List[str] = Field(..., description="List of document IDs to reingest", min_length=1, max_length=50)
    generate_vectors: bool = Field(True, description="Whether to generate new vector embeddings")
    force_reingest: bool = Field(False, description="Force reingestion even if already exists")
    
    @field_validator('doc_ids')
    def validate_doc_ids(cls, v):
        if not v:
            raise ValueError("At least one document ID must be provided")
        return v

class RAGDocumentIngestResult(BaseModel):
    """Schema for individual document ingestion result."""
    doc_id: str = Field(..., description="Document ID")
    success: bool = Field(..., description="Whether ingestion was successful")
    chunks_created: int = Field(..., description="Number of chunks created")
    chunks_deleted: int = Field(0, description="Number of old chunks deleted")
    error_message: Optional[str] = Field(None, description="Error message if failed")

class RAGDocumentIngestResponse(BaseModel):
    """Schema for document ingestion response."""
    success: bool = Field(..., description="Whether the overall operation was successful")
    results: List[RAGDocumentIngestResult] = Field(..., description="Individual document results")
    total_documents_processed: int = Field(..., description="Total number of documents processed")
    total_chunks_created: int = Field(..., description="Total number of chunks created")
    total_chunks_deleted: int = Field(..., description="Total number of old chunks deleted")
    errors: List[str] = Field(default_factory=list, description="General error messages")

# --- Status and Analytics Schemas --- #

class RAGStatusResponse(BaseModel):
    """Schema for RAG service status."""
    weaviate_connected: bool = Field(..., description="Whether Weaviate is connected")
    total_chunks: int = Field(..., description="Total number of chunks in vector database")
    total_documents: int = Field(..., description="Estimated number of unique documents")
    collection_info: Dict[str, Any] = Field(..., description="Weaviate collection information")
    last_updated: datetime = Field(..., description="Last status check timestamp")

class RAGDocumentInfo(BaseModel):
    """Schema for document information in vector database."""
    doc_id: str = Field(..., description="Document ID")
    org_segment: str = Field(..., description="Organization segment")
    user_segment: str = Field(..., description="User segment")
    namespace: str = Field(..., description="Document namespace")
    doc_name: str = Field(..., description="Document name")
    version: Optional[str] = Field(None, description="Document version")
    chunk_count: int = Field(..., description="Number of chunks for this document")
    created_at: Optional[datetime] = Field(None, description="Document creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Document update timestamp")

class RAGDocumentListRequest(RAGBaseRequest):
    """Schema for listing documents in vector database."""
    namespace_filter: Optional[str] = Field(None, description="Filter by document namespace")
    doc_name_filter: Optional[str] = Field(None, description="Filter by document name pattern")
    
    # Pagination
    skip: int = Field(0, ge=0, description="Number of documents to skip")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of documents to return")
    
    # Sorting
    sort_by: str = Field("updated_at", description="Field to sort by")
    sort_order: SortOrder = Field(SortOrder.DESC, description="Sort order")

class RAGDocumentListResponse(BaseModel):
    """Schema for document list response."""
    documents: List[RAGDocumentInfo] = Field(..., description="List of documents")
    total_count: int = Field(..., description="Total number of documents matching filters")
    filters_applied: Dict[str, Any] = Field(..., description="Filters applied to the query")

# --- Bulk Operations Schemas --- #

class RAGBulkOperationRequest(RAGBaseRequest):
    """Schema for bulk operations on documents."""
    namespace_pattern: str = Field("*", description="Namespace pattern with wildcards")
    doc_name_pattern: str = Field("*", description="Document name pattern with wildcards")
    
    # Date range for bulk operations
    created_after: Optional[datetime] = Field(None, description="Only process documents created after this date")
    created_before: Optional[datetime] = Field(None, description="Only process documents created before this date")
    updated_after: Optional[datetime] = Field(None, description="Only process documents updated after this date")
    updated_before: Optional[datetime] = Field(None, description="Only process documents updated before this date")
    
    # Safety limits
    max_documents: int = Field(1000, ge=1, le=10000, description="Maximum number of documents to process")
    dry_run: bool = Field(True, description="If true, only count documents without processing")

class RAGBulkDeleteRequest(RAGBulkOperationRequest):
    """Schema for bulk document deletion."""
    confirm_deletion: bool = Field(False, description="Explicit confirmation required for deletion")

class RAGBulkIngestRequest(RAGBulkOperationRequest):
    """Schema for bulk document ingestion."""
    generate_vectors: bool = Field(True, description="Whether to generate new vector embeddings")
    batch_size: int = Field(10, ge=1, le=100, description="Number of documents to process per batch")

class RAGBulkOperationResponse(BaseModel):
    """Schema for bulk operation response."""
    success: bool = Field(..., description="Whether the operation was successful")
    operation_type: str = Field(..., description="Type of operation performed")
    documents_processed: int = Field(..., description="Number of documents processed")
    total_chunks_affected: int = Field(..., description="Total number of chunks affected")
    execution_time_seconds: float = Field(..., description="Operation execution time")
    dry_run: bool = Field(..., description="Whether this was a dry run")
    errors: List[str] = Field(default_factory=list, description="Error messages")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional operation details")

# --- Advanced Search Schemas --- #

class RAGAdvancedSearchRequest(RAGSearchRequest):
    """Schema for advanced RAG search with more filtering options."""
    # Advanced filtering
    org_segments: Optional[List[str]] = Field(None, description="List of organization segments to include")
    user_segments: Optional[List[str]] = Field(None, description="List of user segments to include")
    namespaces: Optional[List[str]] = Field(None, description="List of namespaces to include")
    doc_names: Optional[List[str]] = Field(None, description="List of document names to include")
    versions: Optional[List[str]] = Field(None, description="List of versions to include")
    
    # Chunk-level filtering
    min_chunk_no: Optional[int] = Field(None, ge=1, description="Minimum chunk number")
    max_chunk_no: Optional[int] = Field(None, ge=1, description="Maximum chunk number")
    
    # Content filtering
    content_must_contain: Optional[List[str]] = Field(None, description="Chunk content must contain all these terms")
    content_must_not_contain: Optional[List[str]] = Field(None, description="Chunk content must not contain any of these terms")
    
    # Aggregation options
    group_by_document: bool = Field(False, description="Group results by document ID")
    include_document_summary: bool = Field(False, description="Include document-level summary statistics")

class RAGGroupedSearchResult(BaseModel):
    """Schema for grouped search results by document."""
    doc_id: str = Field(..., description="Document ID")
    doc_metadata: Dict[str, Any] = Field(..., description="Document metadata")
    chunks: List[RAGSearchResult] = Field(..., description="Chunks from this document")
    total_chunks: int = Field(..., description="Total number of chunks in this document")
    avg_score: Optional[float] = Field(None, description="Average relevance score across chunks")
    best_score: Optional[float] = Field(None, description="Best relevance score among chunks")

class RAGAdvancedSearchResponse(BaseModel):
    """Schema for advanced RAG search response."""
    results: Union[List[RAGSearchResult], List[RAGGroupedSearchResult]] = Field(..., description="Search results")
    total_results: int = Field(..., description="Total number of results found")
    total_documents: int = Field(..., description="Total number of unique documents found")
    search_params: Dict[str, Any] = Field(..., description="Search parameters used")
    execution_time_ms: Optional[float] = Field(None, description="Query execution time in milliseconds")
    grouped_by_document: bool = Field(..., description="Whether results are grouped by document")

# --- Error Schemas --- #

class RAGError(BaseModel):
    """Schema for RAG service errors."""
    error_code: str = Field(..., description="Error code")
    error_message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

class RAGValidationError(RAGError):
    """Schema for validation errors."""
    field_errors: Dict[str, List[str]] = Field(..., description="Field-specific validation errors") 