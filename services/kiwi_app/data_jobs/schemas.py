"""
Data Jobs schemas for KiwiQ system.

This module defines Pydantic schemas for data job operations including
CRUD operations, queries, and responses. Simplified for system-level jobs.
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict

from kiwi_app.data_jobs.models import DataJobStatus, DataJobType

# --- Enums --- #

class SortOrder(str, Enum):
    """Sort order options."""
    ASC = "asc"
    DESC = "desc"

# --- Base Schemas --- #

class DataJobBase(BaseModel):
    """Base schema for data job fields."""
    job_name: Optional[str] = Field(None, description="Optional human-readable name for the job")
    job_type: str = Field(..., description="Type of job being performed")
    job_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional job-specific metadata")

# --- CRUD Schemas --- #

class DataJobCreate(DataJobBase):
    """Schema for creating a new data job."""
    processed_timestamp_start: Optional[datetime] = Field(None, description="Data processing start timestamp (set by cron jobs)")
    processed_timestamp_end: Optional[datetime] = Field(None, description="Data processing end timestamp (set by cron jobs)")
    processing_duration_seconds: Optional[float] = Field(None, description="Total processing duration in seconds")

class DataJobUpdate(BaseModel):
    """Schema for updating a data job."""
    job_name: Optional[str] = None
    status: Optional[DataJobStatus] = None
    error_message: Optional[str] = None
    records_processed: Optional[int] = None
    records_failed: Optional[int] = None
    processed_timestamp_start: Optional[datetime] = None
    processed_timestamp_end: Optional[datetime] = None
    processing_duration_seconds: Optional[float] = None
    job_metadata: Optional[Dict[str, Any]] = None

class DataJobStatusUpdate(BaseModel):
    """Schema for updating job status."""
    status: DataJobStatus = Field(..., description="New status for the job")
    error_message: Optional[str] = Field(None, description="Error message if status is FAILED")
    processed_timestamp_start: Optional[datetime] = Field(None, description="Data processing start timestamp")
    processed_timestamp_end: Optional[datetime] = Field(None, description="Data processing end timestamp")
    processing_duration_seconds: Optional[float] = Field(None, description="Total processing duration in seconds")

class DataJobRead(DataJobBase):
    """Schema for reading data job information."""
    id: uuid.UUID
    status: DataJobStatus
    processed_timestamp_start: Optional[datetime]
    processed_timestamp_end: Optional[datetime]
    error_message: Optional[str]
    records_processed: Optional[int]
    records_failed: Optional[int]
    processing_duration_seconds: Optional[float]
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# --- Job Completion Schemas --- #

class DataJobCompletion(BaseModel):
    """Schema for completing a data job."""
    records_processed: Optional[int] = None
    records_failed: Optional[int] = None
    result_metadata: Optional[Dict[str, Any]] = None

class DataJobFailure(BaseModel):
    """Schema for failing a data job."""
    error_message: str = Field(..., description="Error message describing the failure")
    records_processed: Optional[int] = None
    records_failed: Optional[int] = None
    failure_metadata: Optional[Dict[str, Any]] = None

# --- Query Schemas --- #

class DataJobQuery(BaseModel):
    """Schema for querying data jobs with filtering and pagination."""
    # Job filtering
    job_types: Optional[List[str]] = Field(None, description="Filter by job types")
    statuses: Optional[List[DataJobStatus]] = Field(None, description="Filter by job statuses")
    
    # Date range filtering
    created_after: Optional[datetime] = Field(None, description="Filter jobs created after this date")
    created_before: Optional[datetime] = Field(None, description="Filter jobs created before this date")
    started_after: Optional[datetime] = Field(None, description="Filter jobs started after this date")
    started_before: Optional[datetime] = Field(None, description="Filter jobs started before this date")
    completed_after: Optional[datetime] = Field(None, description="Filter jobs completed after this date")
    completed_before: Optional[datetime] = Field(None, description="Filter jobs completed before this date")
    
    # Text search
    search_text: Optional[str] = Field(None, description="Search in job name or error message")
    metadata_search: Optional[str] = Field(None, description="Search text in job metadata JSON")
    
    # Performance filtering
    min_duration_seconds: Optional[float] = Field(None, description="Minimum processing duration filter")
    max_duration_seconds: Optional[float] = Field(None, description="Maximum processing duration filter")
    
    # Error filtering
    has_errors: Optional[bool] = Field(None, description="Filter jobs with/without errors")
    
    # Sorting and pagination
    sort_by: str = Field("created_at", description="Field to sort by")
    sort_order: SortOrder = Field(SortOrder.DESC, description="Sort order")
    skip: int = Field(0, ge=0, description="Number of records to skip")
    limit: int = Field(50, ge=1, le=1000, description="Maximum number of records to return")

# --- Response Schemas --- #

class PaginatedDataJobs(BaseModel):
    """Paginated response for data job queries."""
    items: List[DataJobRead]
    total: int
    page: int
    per_page: int
    pages: int
    filters_applied: Dict[str, Any]

class DataJobStats(BaseModel):
    """Statistics about data jobs."""
    total_jobs: int
    jobs_by_status: Dict[str, int]
    jobs_by_type: Dict[str, int]
    jobs_by_date: Dict[str, int]
    average_duration_seconds: Optional[float]
    success_rate_percentage: float
    total_records_processed: int
    total_records_failed: int
    most_common_errors: List[Dict[str, Any]]
    recent_activity_summary: Dict[str, Any]

class DataJobDashboard(BaseModel):
    """Dashboard data for data jobs."""
    statistics: DataJobStats
    running_jobs: List[DataJobRead]
    recent_failed_jobs: List[DataJobRead]
    last_updated: datetime

# --- Bulk Operations --- #

class DataJobBulkStatusResult(BaseModel):
    """Result of bulk status update operation."""
    success: bool
    updated_count: int
    failed_count: int
    updated_job_ids: List[uuid.UUID]
    failed_updates: List[Dict[str, str]]
    message: str

class DataJobCleanupResult(BaseModel):
    """Result of job cleanup operation."""
    success: bool
    deleted_count: int
    older_than_days: int
    excluded_statuses: List[str]
    message: str

# --- Deletion Schemas --- #

class DataJobDeleteFilter(BaseModel):
    """Filter criteria for bulk job deletion."""
    job_types: Optional[List[str]] = Field(None, description="Job types to delete")
    statuses: Optional[List[DataJobStatus]] = Field(None, description="Job statuses to delete")
    created_before: Optional[datetime] = Field(None, description="Delete jobs created before this date")
    created_after: Optional[datetime] = Field(None, description="Delete jobs created after this date")

class DataJobDeleteResult(BaseModel):
    """Result of job deletion operation."""
    success: bool = Field(..., description="Whether the deletion was successful")
    deleted_count: int = Field(..., description="Number of jobs deleted")
    message: str = Field(..., description="Descriptive message about the deletion")

# --- Ingestion Trigger Schemas --- #

class RAGIngestionTrigger(BaseModel):
    """Parameters for triggering RAG data ingestion flow."""
    start_timestamp: Optional[datetime] = Field(None, description="Start timestamp for document filtering")
    end_timestamp: Optional[datetime] = Field(None, description="End timestamp for document filtering (defaults to now)")
    batch_size: int = Field(1000, ge=100, le=5000, description="Number of documents to process per batch")
    max_batches: int = Field(50, ge=1, le=200, description="Maximum number of batches to process")
    generate_vectors: bool = Field(True, description="Whether to generate embeddings during ingestion")

class RAGIngestionTriggerResult(BaseModel):
    """Result of triggering RAG ingestion flow."""
    success: bool = Field(..., description="Whether the trigger was successful")
    flow_run_id: str = Field(..., description="Prefect flow run ID")
    message: str = Field(..., description="Descriptive message about the trigger")
    parameters_used: Dict[str, Any] = Field(default_factory=dict, description="Parameters used for the flow") 