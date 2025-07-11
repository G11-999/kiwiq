"""
Data Jobs CRUD operations for KiwiQ system.

This module defines Data Access Objects (DAOs) for data job-related database operations,
following KiwiQ's established patterns for CRUD operations. Simplified for system-level jobs.
"""

import uuid
from typing import Optional, List, Sequence, Dict, Any
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy import delete, and_, or_, func, desc, asc, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from global_utils import datetime_now_utc
from kiwi_app.utils import get_kiwi_logger
from kiwi_app.auth.base_crud import BaseDAO
from kiwi_app.data_jobs.models import DataJobStatus, DataJobType
from kiwi_app.data_jobs import models, schemas
from kiwi_app.data_jobs.exceptions import (
    DataJobNotFoundException,
    DataJobInvalidStatusException,
    DataJobAlreadyStartedException
)

# Get logger for data job operations
data_jobs_logger = get_kiwi_logger(name="kiwi_app.data_jobs.crud")


class DataJobDAO(BaseDAO[models.DataJob, schemas.DataJobCreate, schemas.DataJobUpdate]):
    """Data Access Object for data job operations."""
    
    def __init__(self):
        super().__init__(models.DataJob)
    
    async def create_job(
        self,
        db: AsyncSession,
        job_data: schemas.DataJobCreate,
        commit: bool = True
    ) -> models.DataJob:
        """
        Create a new data job.
        
        Args:
            db: Database session
            job_data: Job creation data
            commit: Whether to commit the transaction
            
        Returns:
            Created data job
        """
        try:
            # Create job with current timestamp
            job = models.DataJob(
                job_name=job_data.job_name,
                job_type=job_data.job_type,
                job_metadata=job_data.job_metadata,
                processed_timestamp_start=job_data.processed_timestamp_start,
                processed_timestamp_end=job_data.processed_timestamp_end,
                processing_duration_seconds=job_data.processing_duration_seconds,
                status=DataJobStatus.PENDING,
                created_at=datetime_now_utc(),
                updated_at=datetime_now_utc()
            )
            
            db.add(job)
            if commit:
                await db.commit()
                await db.refresh(job)
            
            data_jobs_logger.info(f"Created data job {job.id} of type {job.job_type}")
            return job
            
        except Exception as e:
            data_jobs_logger.error(f"Error creating data job: {e}", exc_info=True)
            raise
    
    async def update_job_status(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        status_update: schemas.DataJobStatusUpdate,
        commit: bool = True
    ) -> models.DataJob:
        """
        Update job status with validation.
        
        Args:
            db: Database session
            job_id: Job ID to update
            status_update: Status update data
            commit: Whether to commit the transaction
            
        Returns:
            Updated data job
        """
        try:
            # Get the job
            job = await self.get(db, job_id)
            if not job:
                raise DataJobNotFoundException(
                    status_code=404,
                    detail=f"Data job {job_id} not found"
                )
            
            # Validate status transition
            if job.status == DataJobStatus.STARTED and status_update.status == DataJobStatus.STARTED:
                raise DataJobAlreadyStartedException(
                    status_code=409,
                    detail=f"Data job {job_id} is already started"
                )
            
            # Update status and timestamps
            job.status = status_update.status
            job.updated_at = datetime_now_utc()
            
            if status_update.error_message:
                job.error_message = status_update.error_message
            
            # Update processed timestamps if provided (set by cron jobs)
            if status_update.processed_timestamp_start is not None:
                job.processed_timestamp_start = status_update.processed_timestamp_start
            if status_update.processed_timestamp_end is not None:
                job.processed_timestamp_end = status_update.processed_timestamp_end
            if status_update.processing_duration_seconds is not None:
                job.processing_duration_seconds = status_update.processing_duration_seconds
            
            if commit:
                await db.commit()
                await db.refresh(job)
            
            data_jobs_logger.info(f"Updated job {job_id} status to {status_update.status.value}")
            return job
            
        except Exception as e:
            data_jobs_logger.error(f"Error updating job status: {e}", exc_info=True)
            raise
    
    async def start_job(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        commit: bool = True
    ) -> models.DataJob:
        """Start a data job execution."""
        status_update = schemas.DataJobStatusUpdate(status=DataJobStatus.STARTED)
        return await self.update_job_status(db, job_id, status_update, commit)
    
    async def complete_job(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        records_processed: Optional[int] = None,
        records_failed: Optional[int] = None,
        commit: bool = True
    ) -> models.DataJob:
        """Complete a data job execution."""
        try:
            job = await self.get(db, job_id)
            if not job:
                raise DataJobNotFoundException(
                    status_code=404,
                    detail=f"Data job {job_id} not found"
                )
            
            # Update status and records
            job.status = DataJobStatus.COMPLETED
            job.updated_at = datetime_now_utc()
            
            if records_processed is not None:
                job.records_processed = records_processed
            if records_failed is not None:
                job.records_failed = records_failed
            
            # Note: processed timestamps are set manually by cron jobs, not automatically
            
            if commit:
                await db.commit()
                await db.refresh(job)
            
            data_jobs_logger.info(f"Completed job {job_id}")
            return job
            
        except Exception as e:
            data_jobs_logger.error(f"Error completing job: {e}", exc_info=True)
            raise
    
    async def fail_job(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        error_message: str,
        records_processed: Optional[int] = None,
        records_failed: Optional[int] = None,
        commit: bool = True
    ) -> models.DataJob:
        """Mark a data job as failed."""
        try:
            job = await self.get(db, job_id)
            if not job:
                raise DataJobNotFoundException(
                    status_code=404,
                    detail=f"Data job {job_id} not found"
                )
            
            # Update status and error info
            job.status = DataJobStatus.FAILED
            job.error_message = error_message
            job.updated_at = datetime_now_utc()
            
            if records_processed is not None:
                job.records_processed = records_processed
            if records_failed is not None:
                job.records_failed = records_failed
            
            # Note: processed timestamps are set manually by cron jobs, not automatically
            
            if commit:
                await db.commit()
                await db.refresh(job)
            
            data_jobs_logger.info(f"Failed job {job_id}: {error_message}")
            return job
            
        except Exception as e:
            data_jobs_logger.error(f"Error failing job: {e}", exc_info=True)
            raise
    
    async def get_jobs_by_status(
        self,
        db: AsyncSession,
        status: DataJobStatus,
        limit: int = 100,
        skip: int = 0
    ) -> Sequence[models.DataJob]:
        """Get jobs by status."""
        statement = (
            select(self.model)
            .where(self.model.status == status)
            .order_by(desc(self.model.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def get_jobs_by_type(
        self,
        db: AsyncSession,
        job_type: str,
        limit: int = 100,
        skip: int = 0
    ) -> Sequence[models.DataJob]:
        """Get jobs by type."""
        statement = (
            select(self.model)
            .where(self.model.job_type == job_type)
            .order_by(desc(self.model.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def get_latest_successful_job(
        self,
        db: AsyncSession,
        job_type: str
    ) -> Optional[models.DataJob]:
        """Get the latest successful job of a specific type."""
        statement = (
            select(self.model)
            .where(
                and_(
                    self.model.job_type == job_type,
                    self.model.status == DataJobStatus.COMPLETED
                )
            )
            .order_by(desc(self.model.processed_timestamp_end))
            .limit(1)
        )
        result = await db.exec(statement)
        return result.scalars().first()
    
    async def get_successful_jobs_in_range(
        self,
        db: AsyncSession,
        job_type: str,
        start_time: datetime,
        end_time: datetime
    ) -> Sequence[models.DataJob]:
        """Get successful jobs of a specific type within a time range."""
        statement = (
            select(self.model)
            .where(
                and_(
                    self.model.job_type == job_type,
                    self.model.status == DataJobStatus.COMPLETED,
                    self.model.processed_timestamp_end >= start_time,
                    self.model.processed_timestamp_end <= end_time
                )
            )
            .order_by(desc(self.model.processed_timestamp_end))
        )
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def get_running_jobs(self, db: AsyncSession) -> Sequence[models.DataJob]:
        """Get all currently running jobs."""
        statement = (
            select(self.model)
            .where(self.model.status == DataJobStatus.STARTED)
            .order_by(self.model.processed_timestamp_start)
        )
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def get_failed_jobs(
        self,
        db: AsyncSession,
        hours_back: int = 24,
        limit: int = 100
    ) -> Sequence[models.DataJob]:
        """Get failed jobs from the last N hours."""
        cutoff_time = datetime_now_utc() - timedelta(hours=hours_back)
        statement = (
            select(self.model)
            .where(
                and_(
                    self.model.status == DataJobStatus.FAILED,
                    self.model.created_at >= cutoff_time
                )
            )
            .order_by(desc(self.model.created_at))
            .limit(limit)
        )
        result = await db.exec(statement)
        return result.scalars().all()
    
    async def query_jobs(
        self,
        db: AsyncSession,
        query_params: schemas.DataJobQuery
    ) -> schemas.PaginatedDataJobs:
        """
        Query data jobs with filtering and pagination.
        
        Args:
            db: Database session
            query_params: Query parameters including filters and pagination
            
        Returns:
            Paginated list of data jobs matching the query
        """
        try:
            # Build base query
            query = select(self.model)
            count_query = select(func.count(self.model.id))
            
            # Apply filters
            conditions = []
            filters_applied = {}
            
            # Job type filtering
            if query_params.job_types:
                conditions.append(self.model.job_type.in_(query_params.job_types))
                filters_applied["job_types"] = query_params.job_types
            
            # Status filtering
            if query_params.statuses:
                conditions.append(self.model.status.in_(query_params.statuses))
                filters_applied["statuses"] = [s.value for s in query_params.statuses]
            
            # Date range filtering - created
            if query_params.created_after:
                conditions.append(self.model.created_at >= query_params.created_after)
                filters_applied["created_after"] = query_params.created_after
            
            if query_params.created_before:
                conditions.append(self.model.created_at <= query_params.created_before)
                filters_applied["created_before"] = query_params.created_before
            
            # Date range filtering - started
            if query_params.started_after:
                conditions.append(self.model.processed_timestamp_start >= query_params.started_after)
                filters_applied["started_after"] = query_params.started_after
            
            if query_params.started_before:
                conditions.append(self.model.processed_timestamp_start <= query_params.started_before)
                filters_applied["started_before"] = query_params.started_before
            
            # Date range filtering - completed
            if query_params.completed_after:
                conditions.append(self.model.processed_timestamp_end >= query_params.completed_after)
                filters_applied["completed_after"] = query_params.completed_after
            
            if query_params.completed_before:
                conditions.append(self.model.processed_timestamp_end <= query_params.completed_before)
                filters_applied["completed_before"] = query_params.completed_before
            
            # Performance filtering
            if query_params.min_duration_seconds is not None:
                conditions.append(self.model.processing_duration_seconds >= query_params.min_duration_seconds)
                filters_applied["min_duration_seconds"] = query_params.min_duration_seconds
            
            if query_params.max_duration_seconds is not None:
                conditions.append(self.model.processing_duration_seconds <= query_params.max_duration_seconds)
                filters_applied["max_duration_seconds"] = query_params.max_duration_seconds
            
            # Text search
            if query_params.search_text:
                search_pattern = f"%{query_params.search_text}%"
                conditions.append(
                    or_(
                        self.model.job_name.ilike(search_pattern),
                        self.model.error_message.ilike(search_pattern)
                    )
                )
                filters_applied["search_text"] = query_params.search_text
            
            # Metadata search
            if query_params.metadata_search:
                search_condition = func.cast(self.model.job_metadata, sa.String).contains(query_params.metadata_search)
                conditions.append(search_condition)
                filters_applied["metadata_search"] = query_params.metadata_search
            
            # Error filtering
            if query_params.has_errors is not None:
                if query_params.has_errors:
                    conditions.append(self.model.error_message.is_not(None))
                else:
                    conditions.append(self.model.error_message.is_(None))
                filters_applied["has_errors"] = query_params.has_errors
            
            # Apply all conditions
            if conditions:
                filter_condition = and_(*conditions)
                query = query.where(filter_condition)
                count_query = count_query.where(filter_condition)
            
            # Get total count
            count_result = await db.exec(count_query)
            total = count_result.scalar() or 0
            
            # Apply sorting
            sort_column = getattr(self.model, query_params.sort_by, self.model.created_at)
            if query_params.sort_order == schemas.SortOrder.DESC:
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(asc(sort_column))
            
            # Apply pagination
            query = query.offset(query_params.skip).limit(query_params.limit)
            
            # Execute query
            result = await db.exec(query)
            jobs = result.scalars().all()
            
            # Calculate pagination info
            page = (query_params.skip // query_params.limit) + 1
            per_page = query_params.limit
            pages = (total + per_page - 1) // per_page
            
            # Convert to read schemas
            job_reads = [schemas.DataJobRead.model_validate(job) for job in jobs]
            
            data_jobs_logger.debug(
                f"Queried data jobs: {len(jobs)} results, {total} total"
            )
            
            return schemas.PaginatedDataJobs(
                items=job_reads,
                total=total,
                page=page,
                per_page=per_page,
                pages=pages,
                filters_applied=filters_applied
            )
            
        except Exception as e:
            data_jobs_logger.error(f"Error querying data jobs: {e}", exc_info=True)
            raise
    
    async def get_job_statistics(
        self,
        db: AsyncSession,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> schemas.DataJobStats:
        """
        Get comprehensive statistics about data jobs.
        
        Args:
            db: Database session
            date_from: Start date for analysis
            date_to: End date for analysis
            
        Returns:
            Comprehensive statistics about data jobs
        """
        try:
            # Build base conditions
            conditions = []
            if date_from:
                conditions.append(self.model.created_at >= date_from)
            if date_to:
                conditions.append(self.model.created_at <= date_to)
            
            base_condition = and_(*conditions) if conditions else True
            
            # Total jobs
            total_query = select(func.count(self.model.id)).where(base_condition)
            total_result = await db.exec(total_query)
            total_jobs = total_result.scalar() or 0
            
            # Jobs by status
            status_query = (
                select(self.model.status, func.count(self.model.id).label('count'))
                .where(base_condition)
                .group_by(self.model.status)
            )
            status_result = await db.exec(status_query)
            jobs_by_status = {row.status.value: row.count for row in status_result}
            
            # Jobs by type
            type_query = (
                select(self.model.job_type, func.count(self.model.id).label('count'))
                .where(base_condition)
                .group_by(self.model.job_type)
                .order_by(desc('count'))
            )
            type_result = await db.exec(type_query)
            jobs_by_type = {row.job_type: row.count for row in type_result}
            
            # Jobs by date (daily aggregation)
            date_query = (
                select(
                    func.date(self.model.created_at).label('job_date'),
                    func.count(self.model.id).label('count')
                )
                .where(base_condition)
                .group_by(func.date(self.model.created_at))
                .order_by('job_date')
            )
            date_result = await db.exec(date_query)
            jobs_by_date = {str(row.job_date): row.count for row in date_result}
            
            # Average duration
            duration_query = (
                select(func.avg(self.model.processing_duration_seconds))
                .where(
                    and_(
                        base_condition,
                        self.model.processing_duration_seconds.is_not(None)
                    )
                )
            )
            duration_result = await db.exec(duration_query)
            avg_duration = duration_result.scalar()
            
            # Success rate
            success_query = (
                select(
                    func.count(self.model.id).label('total'),
                    func.sum(case((self.model.status == DataJobStatus.COMPLETED, 1), else_=0)).label('successful')
                )
                .where(
                    and_(
                        base_condition,
                        self.model.status.in_([DataJobStatus.COMPLETED, DataJobStatus.FAILED])
                    )
                )
            )
            success_result = await db.exec(success_query)
            success_row = success_result.first()
            success_rate = (
                (success_row.successful / success_row.total * 100)
                if success_row.total > 0 else 100.0
            )
            
            # Records processed
            records_query = (
                select(
                    func.coalesce(func.sum(self.model.records_processed), 0).label('total_processed'),
                    func.coalesce(func.sum(self.model.records_failed), 0).label('total_failed')
                )
                .where(base_condition)
            )
            records_result = await db.exec(records_query)
            records_row = records_result.first()
            total_records_processed = records_row.total_processed or 0
            total_records_failed = records_row.total_failed or 0
            
            # Most common errors
            error_query = (
                select(
                    self.model.error_message,
                    func.count(self.model.id).label('count')
                )
                .where(
                    and_(
                        base_condition,
                        self.model.error_message.is_not(None),
                        self.model.error_message != ''
                    )
                )
                .group_by(self.model.error_message)
                .order_by(desc('count'))
                .limit(10)
            )
            error_result = await db.exec(error_query)
            most_common_errors = [
                {"error_message": row.error_message, "count": row.count}
                for row in error_result
            ]
            
            # Recent activity summary
            recent_activity = {
                "jobs_last_24h": 0,
                "failed_jobs_last_24h": 0
            }
            
            recent_cutoff = datetime_now_utc() - timedelta(hours=24)
            recent_query = (
                select(
                    func.count(self.model.id).label('total_recent'),
                    func.sum(case((self.model.status == DataJobStatus.FAILED, 1), else_=0)).label('failed_recent')
                )
                .where(
                    and_(
                        base_condition,
                        self.model.created_at >= recent_cutoff
                    )
                )
            )
            recent_result = await db.exec(recent_query)
            recent_row = recent_result.first()
            
            if recent_row:
                recent_activity["jobs_last_24h"] = recent_row.total_recent or 0
                recent_activity["failed_jobs_last_24h"] = recent_row.failed_recent or 0
            
            return schemas.DataJobStats(
                total_jobs=total_jobs,
                jobs_by_status=jobs_by_status,
                jobs_by_type=jobs_by_type,
                jobs_by_date=jobs_by_date,
                average_duration_seconds=float(avg_duration) if avg_duration else None,
                success_rate_percentage=float(success_rate),
                total_records_processed=total_records_processed,
                total_records_failed=total_records_failed,
                most_common_errors=most_common_errors,
                recent_activity_summary=recent_activity
            )
            
        except Exception as e:
            data_jobs_logger.error(f"Error getting job statistics: {e}", exc_info=True)
            raise
    
    async def bulk_update_status(
        self,
        db: AsyncSession,
        job_ids: List[uuid.UUID],
        status: DataJobStatus,
        error_message: Optional[str] = None,
        commit: bool = True
    ) -> schemas.DataJobBulkStatusResult:
        """
        Bulk update status for multiple jobs.
        
        Args:
            db: Database session
            job_ids: List of job IDs to update
            status: New status for all jobs
            error_message: Error message if status is FAILED
            commit: Whether to commit the transaction
            
        Returns:
            Bulk update result with success/failure details
        """
        try:
            updated_job_ids = []
            failed_updates = []
            
            for job_id in job_ids:
                try:
                    status_update = schemas.DataJobStatusUpdate(
                        status=status,
                        error_message=error_message
                    )
                    
                    await self.update_job_status(db, job_id, status_update, commit=False)
                    updated_job_ids.append(job_id)
                    
                except Exception as e:
                    failed_updates.append({
                        "job_id": str(job_id),
                        "error": str(e)
                    })
            
            if commit:
                await db.commit()
            
            success = len(failed_updates) == 0
            updated_count = len(updated_job_ids)
            failed_count = len(failed_updates)
            
            message = f"Updated {updated_count} jobs, {failed_count} failed"
            
            data_jobs_logger.info(f"Bulk status update: {message}")
            
            return schemas.DataJobBulkStatusResult(
                success=success,
                updated_count=updated_count,
                failed_count=failed_count,
                updated_job_ids=updated_job_ids,
                failed_updates=failed_updates,
                message=message
            )
            
        except Exception as e:
            if commit:
                await db.rollback()
            data_jobs_logger.error(f"Error in bulk status update: {e}", exc_info=True)
            raise
    
    async def delete_old_jobs(
        self,
        db: AsyncSession,
        older_than_days: int = 90,
        exclude_statuses: Optional[List[DataJobStatus]] = None,
        commit: bool = True
    ) -> int:
        """
        Delete old jobs based on age and status criteria.
        
        Args:
            db: Database session
            older_than_days: Delete jobs older than this many days
            exclude_statuses: List of statuses to exclude from deletion
            commit: Whether to commit the transaction
            
        Returns:
            Number of jobs deleted
        """
        try:
            cutoff_date = datetime_now_utc() - timedelta(days=older_than_days)
            
            conditions = [self.model.created_at < cutoff_date]
            
            if exclude_statuses:
                conditions.append(~self.model.status.in_(exclude_statuses))
            
            delete_query = delete(self.model).where(and_(*conditions))
            
            result = await db.exec(delete_query)
            deleted_count = result.rowcount
            
            if commit:
                await db.commit()
            
            data_jobs_logger.info(f"Deleted {deleted_count} old jobs (older than {older_than_days} days)")
            return deleted_count
            
        except Exception as e:
            if commit:
                await db.rollback()
            data_jobs_logger.error(f"Error deleting old jobs: {e}", exc_info=True)
            raise
    
    async def delete_job_by_id(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        commit: bool = True
    ) -> bool:
        """
        Delete a specific job by ID.
        
        Args:
            db: Database session
            job_id: ID of the job to delete
            commit: Whether to commit the transaction
            
        Returns:
            True if job was deleted, False if not found
        """
        try:
            # Check if job exists
            job = await self.get(db, job_id)
            if not job:
                return False
            
            delete_query = delete(self.model).where(self.model.id == job_id)
            result = await db.exec(delete_query)
            deleted_count = result.rowcount
            
            if commit:
                await db.commit()
            
            data_jobs_logger.info(f"Deleted job {job_id}")
            return deleted_count > 0
            
        except Exception as e:
            if commit:
                await db.rollback()
            data_jobs_logger.error(f"Error deleting job {job_id}: {e}", exc_info=True)
            raise
    
    async def delete_jobs_by_filter(
        self,
        db: AsyncSession,
        job_types: Optional[List[str]] = None,
        statuses: Optional[List[DataJobStatus]] = None,
        created_before: Optional[datetime] = None,
        created_after: Optional[datetime] = None,
        exclude_statuses: Optional[List[DataJobStatus]] = None,
        commit: bool = True
    ) -> int:
        """
        Delete jobs based on filter criteria.
        
        Args:
            db: Database session
            job_types: List of job types to include
            statuses: List of statuses to include
            created_before: Delete jobs created before this date
            created_after: Delete jobs created after this date
            exclude_statuses: List of statuses to exclude from deletion
            commit: Whether to commit the transaction
            
        Returns:
            Number of jobs deleted
        """
        try:
            conditions = []
            
            # Job type filtering
            if job_types:
                conditions.append(self.model.job_type.in_(job_types))
            
            # Status filtering
            if statuses:
                conditions.append(self.model.status.in_(statuses))
            
            # Date filtering
            if created_before:
                conditions.append(self.model.created_at <= created_before)
            
            if created_after:
                conditions.append(self.model.created_at >= created_after)
            
            # Exclude certain statuses (for safety)
            if exclude_statuses:
                conditions.append(~self.model.status.in_(exclude_statuses))
            
            if not conditions:
                # Don't allow deletion of all jobs without any criteria
                raise ValueError("At least one filter condition must be provided for bulk deletion")
            
            delete_query = delete(self.model).where(and_(*conditions))
            result = await db.exec(delete_query)
            deleted_count = result.rowcount
            
            if commit:
                await db.commit()
            
            data_jobs_logger.info(f"Deleted {deleted_count} jobs using filter criteria")
            return deleted_count
            
        except Exception as e:
            if commit:
                await db.rollback()
            data_jobs_logger.error(f"Error deleting jobs by filter: {e}", exc_info=True)
            raise
    
    async def delete_all_jobs(
        self,
        db: AsyncSession,
        exclude_statuses: Optional[List[DataJobStatus]] = None,
        commit: bool = True
    ) -> int:
        """
        Delete all jobs with optional status exclusions.
        
        Args:
            db: Database session
            exclude_statuses: List of statuses to exclude from deletion
            commit: Whether to commit the transaction
            
        Returns:
            Number of jobs deleted
        """
        try:
            conditions = []
            
            # Exclude certain statuses (for safety)
            if exclude_statuses:
                conditions.append(~self.model.status.in_(exclude_statuses))
            
            if conditions:
                delete_query = delete(self.model).where(and_(*conditions))
            else:
                delete_query = delete(self.model)
            
            result = await db.exec(delete_query)
            deleted_count = result.rowcount
            
            if commit:
                await db.commit()
            
            data_jobs_logger.warning(f"Deleted ALL {deleted_count} jobs from database")
            return deleted_count
            
        except Exception as e:
            if commit:
                await db.rollback()
            data_jobs_logger.error(f"Error deleting all jobs: {e}", exc_info=True)
            raise 