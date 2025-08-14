"""
Data Jobs routers for KiwiQ system.

This module defines the FastAPI routers for data job-related endpoints,
including job management, monitoring, and analytics. These are admin-only
endpoints for system-level job management.
"""

import uuid
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_async_db_dependency
from kiwi_app.utils import get_kiwi_logger
from kiwi_app.auth.dependencies import get_current_active_superuser
from kiwi_app.auth.models import User

from kiwi_app.data_jobs import schemas, services, dependencies
from kiwi_app.data_jobs.models import DataJobStatus
from kiwi_app.data_jobs.exceptions import (
    DataJobNotFoundException,
    DataJobInvalidStatusException,
    DataJobAlreadyStartedException,
    DataJobException
)

# Get logger for data job operations
data_jobs_logger = get_kiwi_logger(name="kiwi_app.data_jobs.routers")

# Create router instances
data_jobs_admin_router = APIRouter(prefix="/data-jobs", tags=["data-jobs-admin"])


# --- Flow Trigger Endpoints --- #

@data_jobs_admin_router.post("/triggers/rag-ingestion", response_model=schemas.RAGIngestionTriggerResult)
async def trigger_rag_ingestion_flow(
    trigger_params: schemas.RAGIngestionTrigger,
    current_user: User = Depends(get_current_active_superuser),
    data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
):
    """
    Trigger RAG data ingestion flow (Admin only).
    
    Manually triggers the RAG data ingestion Prefect flow with custom parameters.
    This flow ingests updated customer documents into Weaviate for RAG applications.
    
    The flow will:
    - Process documents updated between start_timestamp and end_timestamp
    - Use incremental processing based on last successful ingestion if no start_timestamp
    - Process documents in configurable batches for memory efficiency
    - Generate embeddings and store chunks in Weaviate
    - Track progress in a DataJob record
    
    Requires superuser permissions.
    """
    try:
        result = await data_jobs_service.trigger_rag_ingestion(
            trigger_params=trigger_params
        )
        
        data_jobs_logger.info(
            f"Admin {current_user.id} triggered RAG ingestion flow: {result.flow_run_id}"
        )
        
        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.message
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        data_jobs_logger.error(f"Error triggering RAG ingestion: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger RAG ingestion flow"
        ) 

# --- Job Management Endpoints --- #

# @data_jobs_admin_router.post("", response_model=schemas.DataJobRead)
# async def create_data_job(
#     job_data: schemas.DataJobCreate,
#     current_user: User = Depends(get_current_active_superuser),
#     db: AsyncSession = Depends(get_async_db_dependency),
#     data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
# ):
#     """
#     Create a new data job (Admin only).
    
#     Creates a new system-level data job for background processing.
#     Only superusers can create data jobs since these are system operations.
    
#     Note: processed_timestamp_start and processed_timestamp_end are set manually
#     by cron jobs to track data processing timeframes, not job execution times.
    
#     Requires superuser permissions.
#     """
#     try:
#         job = await data_jobs_service.create_job(
#             db=db,
#             job_data=job_data
#         )
        
#         data_jobs_logger.info(f"Admin {current_user.id} created data job {job.id}")
#         return job
        
#     except DataJobException as e:
#         raise HTTPException(
#             status_code=e.status_code,
#             detail=e.detail
#         )
#     except Exception as e:
#         data_jobs_logger.error(f"Error creating data job: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to create data job"
#         )


# @data_jobs_admin_router.post("/{job_id}/start", response_model=schemas.DataJobRead)
# async def start_job(
#     job_id: uuid.UUID,
#     current_user: User = Depends(get_current_active_superuser),
#     db: AsyncSession = Depends(get_async_db_dependency),
#     data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
# ):
#     """
#     Start a data job execution (Admin only).
    
#     Initiates execution of a pending data job by updating status to STARTED
#     and recording the start timestamp.
    
#     Requires superuser permissions.
#     """
#     try:
#         job = await data_jobs_service.start_job(
#             db=db,
#             job_id=job_id
#         )
        
#         data_jobs_logger.info(f"Admin {current_user.id} started job {job_id}")
#         return job
        
#     except DataJobNotFoundException:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Data job {job_id} not found"
#         )
#     except DataJobAlreadyStartedException:
#         raise HTTPException(
#             status_code=status.HTTP_409_CONFLICT,
#             detail="Data job is already started"
#         )
#     except Exception as e:
#         data_jobs_logger.error(f"Error starting job: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to start job"
#         )

# @data_jobs_admin_router.post("/{job_id}/complete", response_model=schemas.DataJobRead)
# async def complete_job(
#     job_id: uuid.UUID,
#     completion_data: schemas.DataJobCompletion,
#     current_user: User = Depends(get_current_active_superuser),
#     db: AsyncSession = Depends(get_async_db_dependency),
#     data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
# ):
#     """
#     Complete a data job execution (Admin only).
    
#     Marks a data job as completed with optional performance metrics
#     and result metadata.
    
#     Requires superuser permissions.
#     """
#     try:
#         job = await data_jobs_service.complete_job(
#             db=db,
#             job_id=job_id,
#             completion_data=completion_data
#         )
        
#         data_jobs_logger.info(f"Admin {current_user.id} completed job {job_id}")
#         return job
        
#     except DataJobNotFoundException:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Data job {job_id} not found"
#         )
#     except Exception as e:
#         data_jobs_logger.error(f"Error completing job: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to complete job"
#         )

# @data_jobs_admin_router.post("/{job_id}/fail", response_model=schemas.DataJobRead)
# async def fail_job(
#     job_id: uuid.UUID,
#     failure_data: schemas.DataJobFailure,
#     current_user: User = Depends(get_current_active_superuser),
#     db: AsyncSession = Depends(get_async_db_dependency),
#     data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
# ):
#     """
#     Mark a data job as failed (Admin only).
    
#     Records job failure with error message and optional failure metadata.
    
#     Requires superuser permissions.
#     """
#     try:
#         job = await data_jobs_service.fail_job(
#             db=db,
#             job_id=job_id,
#             failure_data=failure_data
#         )
        
#         data_jobs_logger.info(f"Admin {current_user.id} failed job {job_id}")
#         return job
        
#     except DataJobNotFoundException:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Data job {job_id} not found"
#         )
#     except Exception as e:
#         data_jobs_logger.error(f"Error failing job: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to record job failure"
#         )

# --- Query and Analytics Endpoints --- #

@data_jobs_admin_router.post("/query", response_model=schemas.PaginatedDataJobs)
async def query_data_jobs(
    query_params: schemas.DataJobQuery,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
):
    """
    Query data jobs with filtering and pagination (Admin only).
    
    Provides comprehensive querying capabilities with filtering by:
    - Job type and status
    - Date ranges (created, started, completed)
    - Performance metrics (duration)
    - Text search in job names and error messages
    - Metadata search
    
    Supports sorting and pagination for efficient data retrieval.
    
    Requires superuser permissions.
    """
    try:
        result = await data_jobs_service.query_jobs(
            db=db,
            query_params=query_params
        )
        
        data_jobs_logger.info(
            f"Admin {current_user.id} queried data jobs: {len(result.items)} results"
        )
        
        return result
        
    except Exception as e:
        data_jobs_logger.error(f"Error querying data jobs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query data jobs"
        )

@data_jobs_admin_router.get("/statistics", response_model=schemas.DataJobStats)
async def get_job_statistics(
    date_from: Optional[datetime] = Query(None, description="Start date for analysis"),
    date_to: Optional[datetime] = Query(None, description="End date for analysis"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
):
    """
    Get data job statistics (Admin only).
    
    Returns comprehensive analytics including:
    - Job counts by status and type
    - Success rates and performance metrics
    - Error analysis and trends
    - Recent activity summary
    
    Defaults to last 30 days if no date range provided.
    
    Requires superuser permissions.
    """
    try:
        stats = await data_jobs_service.get_job_statistics(
            db=db,
            date_from=date_from,
            date_to=date_to
        )
        
        data_jobs_logger.info(f"Admin {current_user.id} retrieved job statistics")
        return stats
        
    except Exception as e:
        data_jobs_logger.error(f"Error getting job statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get job statistics"
        )

@data_jobs_admin_router.get("/dashboard", response_model=schemas.DataJobDashboard)
async def get_dashboard_data(
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
):
    """
    Get data jobs dashboard data (Admin only).
    
    Returns comprehensive dashboard information including:
    - Recent statistics (last 24 hours)
    - Currently running jobs
    - Recent failed jobs
    - Last updated timestamp
    
    Designed for admin monitoring and system health overview.
    
    Requires superuser permissions.
    """
    try:
        dashboard = await data_jobs_service.get_dashboard_data(db=db)
        
        data_jobs_logger.info(f"Admin {current_user.id} retrieved dashboard data")
        return dashboard
        
    except Exception as e:
        data_jobs_logger.error(f"Error getting dashboard data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get dashboard data"
        )

# --- Helper Endpoints --- #

@data_jobs_admin_router.get("/latest-successful/{job_type}", response_model=Optional[schemas.DataJobRead])
async def get_latest_successful_job(
    job_type: str = Path(..., description="Job type to search for"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
):
    """
    Get the latest successful job of a specific type (Admin only).
    
    Returns the most recently completed job of the specified type,
    useful for tracking job history and success patterns.
    
    Requires superuser permissions.
    """
    try:
        job = await data_jobs_service.get_latest_successful_job(
            db=db,
            job_type=job_type
        )
        
        data_jobs_logger.info(f"Admin {current_user.id} retrieved latest successful {job_type} job")
        return job
        
    except Exception as e:
        data_jobs_logger.error(f"Error getting latest successful job: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get latest successful job"
        )

@data_jobs_admin_router.get("/successful-in-range/{job_type}", response_model=List[schemas.DataJobRead])
async def get_successful_jobs_in_range(
    job_type: str = Path(..., description="Job type to search for"),
    start_time: datetime = Query(..., description="Start of time range"),
    end_time: datetime = Query(..., description="End of time range"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
):
    """
    Get successful jobs of a specific type within a time range (Admin only).
    
    Returns all successfully completed jobs of the specified type
    within the given time range. Useful for analysis and reporting.
    
    Requires superuser permissions.
    """
    try:
        jobs = await data_jobs_service.get_successful_jobs_in_range(
            db=db,
            job_type=job_type,
            start_time=start_time,
            end_time=end_time
        )
        
        data_jobs_logger.info(
            f"Admin {current_user.id} retrieved {len(jobs)} successful {job_type} jobs "
            f"between {start_time} and {end_time}"
        )
        
        return jobs
        
    except Exception as e:
        data_jobs_logger.error(f"Error getting successful jobs in range: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get successful jobs in range"
        )

# --- Bulk Operations --- #

# @data_jobs_admin_router.post("/bulk/update-status", response_model=schemas.DataJobBulkStatusResult)
# async def bulk_update_job_status(
#     job_ids: List[uuid.UUID],
#     status: DataJobStatus,
#     error_message: Optional[str] = None,
#     current_user: User = Depends(get_current_active_superuser),
#     db: AsyncSession = Depends(get_async_db_dependency),
#     data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
# ):
#     """
#     Bulk update status for multiple jobs (Admin only).
    
#     Updates the status of multiple data jobs in a single operation.
#     Provides detailed results about successful and failed updates.
    
#     Requires superuser permissions.
#     """
#     try:
#         result = await data_jobs_service.bulk_update_status(
#             db=db,
#             job_ids=job_ids,
#             status=status,
#             error_message=error_message
#         )
        
#         data_jobs_logger.info(
#             f"Admin {current_user.id} bulk updated {result.updated_count} jobs to {status.value}"
#         )
        
#         return result
        
#     except Exception as e:
#         data_jobs_logger.error(f"Error in bulk status update: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to bulk update job status"
#         )

@data_jobs_admin_router.post("/cleanup", response_model=schemas.DataJobCleanupResult)
async def cleanup_old_jobs(
    older_than_days: int = Query(90, ge=1, le=365, description="Delete jobs older than this many days"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
):
    """
    Clean up old data jobs (Admin only).
    
    Removes old completed and failed jobs to manage database size.
    Excludes running and pending jobs from cleanup for safety.
    
    Requires superuser permissions.
    """
    try:
        result = await data_jobs_service.cleanup_old_jobs(
            db=db,
            older_than_days=older_than_days
        )
        
        data_jobs_logger.info(
            f"Admin {current_user.id} cleaned up {result.deleted_count} old jobs"
        )
        
        return result
        
    except Exception as e:
        data_jobs_logger.error(f"Error cleaning up old jobs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cleanup old jobs"
        )

# --- Deletion Endpoints --- #



@data_jobs_admin_router.delete("/bulk/filter", response_model=schemas.DataJobDeleteResult)
async def delete_jobs_by_filter(
    filter_criteria: schemas.DataJobDeleteFilter,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
):
    """
    Delete multiple data jobs based on filter criteria (Admin only).
    
    Permanently removes data jobs matching the provided criteria.
    Automatically excludes running and pending jobs for safety.
    This action cannot be undone.
    
    Requires superuser permissions.
    """
    try:
        result = await data_jobs_service.delete_jobs_by_filter(
            db=db,
            filter_criteria=filter_criteria
        )
        
        data_jobs_logger.info(
            f"Admin {current_user.id} deleted {result.deleted_count} jobs by filter"
        )
        
        return result
        
    except Exception as e:
        data_jobs_logger.error(f"Error deleting jobs by filter: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete jobs by filter"
        )

@data_jobs_admin_router.delete("/all", response_model=schemas.DataJobDeleteResult)
async def delete_all_jobs(
    force: bool = Query(False, description="Force deletion of all jobs including running ones"),
    confirm: bool = Query(True, description="Confirmation flag to prevent accidental deletion"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
):
    """
    Delete ALL data jobs (Admin only).
    
    **DANGER**: This endpoint deletes ALL data jobs from the system.
    By default, excludes running and pending jobs unless 'force=true'.
    Requires explicit confirmation flag to prevent accidental usage.
    This action cannot be undone.
    
    Requires superuser permissions and confirmation flag.
    """
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required: add '?confirm=true' to delete all jobs"
        )
    
    try:
        result = await data_jobs_service.delete_all_jobs(
            db=db,
            force=force
        )
        
        data_jobs_logger.warning(
            f"Admin {current_user.id} deleted ALL {result.deleted_count} jobs (force={force})"
        )
        
        return result
        
    except Exception as e:
        data_jobs_logger.error(f"Error deleting all jobs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete all jobs"
        )


@data_jobs_admin_router.get("/{job_id}", response_model=schemas.DataJobRead)
async def get_data_job(
    job: schemas.DataJobRead = Depends(dependencies.get_data_job_by_id)
):
    """
    Get a data job by ID (Admin only).
    
    Returns detailed information about a specific data job.
    Requires superuser permissions.
    """
    return job

@data_jobs_admin_router.patch("/{job_id}/status", response_model=schemas.DataJobRead)
async def update_job_status(
    job_id: uuid.UUID,
    status_update: schemas.DataJobStatusUpdate,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
):
    """
    Update data job status (Admin only).
    
    Updates the status of a data job with optional error message and processing timestamps.
    The processed timestamps track data processing timeframes, not job execution times.
    
    Requires superuser permissions.
    """
    try:
        job = await data_jobs_service.update_job_status(
            db=db,
            job_id=job_id,
            status_update=status_update
        )
        
        data_jobs_logger.info(f"Admin {current_user.id} updated job {job_id} status")
        return job
        
    except DataJobNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Data job {job_id} not found"
        )
    except DataJobAlreadyStartedException:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Data job is already started"
        )
    except DataJobException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail
        )
    except Exception as e:
        data_jobs_logger.error(f"Error updating job status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update job status"
        )

@data_jobs_admin_router.delete("/{job_id}", response_model=schemas.DataJobDeleteResult)
async def delete_data_job_by_id(
    job_id: uuid.UUID = Path(..., description="ID of the job to delete"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_async_db_dependency),
    data_jobs_service: services.DataJobService = Depends(dependencies.get_data_jobs_service)
):
    """
    Delete a specific data job by ID (Admin only).
    
    Permanently removes a data job from the system. This action cannot be undone.
    
    Requires superuser permissions.
    """
    try:
        result = await data_jobs_service.delete_job_by_id(
            db=db,
            job_id=job_id
        )
        
        data_jobs_logger.info(f"Admin {current_user.id} deleted job {job_id}")
        
        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.message
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        data_jobs_logger.error(f"Error deleting job by ID: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete job"
        )
