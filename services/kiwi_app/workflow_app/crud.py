"""CRUD (Create, Read, Update, Delete) operations for Workflow Service models.

This module provides Data Access Objects (DAOs) for interacting with the 
database models defined in models.py, encapsulating the database query logic.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Type, TypeVar, Generic, Any, Dict, Sequence, Union, Tuple
import copy
import json
import hashlib

from sqlalchemy import select, update, delete, func, or_, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import text

from pydantic import BaseModel as PydanticBaseModel

from kiwi_app.auth.models import User
from kiwi_app.workflow_app import models, schemas
from kiwi_app.workflow_app.constants import WorkflowRunStatus, NotificationType, HITLJobStatus, LaunchStatus, SchemaType
from kiwi_app.auth.crud_util import build_load_options
from global_utils import datetime_now_utc
from kiwi_app.utils import get_kiwi_logger

crud_logger = get_kiwi_logger(name="kiwi_app.workflow_app.crud")

ModelType = TypeVar("ModelType", bound=models.SQLModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=PydanticBaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=PydanticBaseModel)
TemplateModelType = TypeVar("TemplateModelType", bound=PydanticBaseModel)
TemplateCreateSchemaType = TypeVar("TemplateCreateSchemaType", bound=PydanticBaseModel)
TemplateUpdateSchemaType = TypeVar("TemplateUpdateSchemaType", bound=PydanticBaseModel)


class BaseDAO(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """Generic Base DAO for common CRUD operations."""
    model: Type[ModelType]

    def __init__(self, model: Type[ModelType]):
        """
        CRUD object with default methods to Create, Read, Update, Delete (CRUD).

        Args:
            model: A SQLAlchemy model class (or SQLModel class)
        """
        self.model = model

    async def get(self, db: AsyncSession, id: uuid.UUID) -> Optional[ModelType]:
        """
        Retrieves a single record by its primary key (UUID).

        Args:
            db: AsyncSession instance.
            id: Primary key of the record to retrieve.

        Returns:
            The model instance if found, otherwise None.
        """
        stmt = select(self.model).where(self.model.id == id)
        result = await db.exec(stmt)
        return result.scalars().first()

    async def search_by_name_version(
        self,
        db: AsyncSession,
        *,
        name: str,
        version: Optional[str] = None,
        version_field: str = "version",
        owner_org_id: uuid.UUID,
        include_public: bool = True,
        include_system_entities: bool = False,
        include_public_system_entities: bool = False,
        is_superuser: bool = False,
        sort_by: schemas.SearchSortBy = schemas.SearchSortBy.CREATED_AT,
        sort_order: schemas.SortOrder = schemas.SortOrder.DESC
    ) -> Sequence[ModelType]:
        """
        Generic method to search for templates/entities by name and optional version.
        
        Returns entities that:
        - Match the name
        - Match the version (if provided)
        - Belong to the specified organization OR
        - Are public (if include_public=True) OR
        - Are system entities (if include_system_entities=True and is_superuser=True)
        
        Args:
            db: Database session
            name: Name to search for
            version: Optional version to filter by
            version_field: Field name for version ('version' or 'version_tag')
            owner_org_id: Organization ID context for the search
            include_public: Whether to include public entities
            include_system_entities: Whether to include system entities (only applies for superusers)
            is_superuser: Whether the user is a superuser (controls system entity access)
            sort_by: Field to sort by
            sort_order: Sort order ('asc' or 'desc')
        Returns:
            List of matching entity objects
        """
        # crud_logger.info(f"Searching for {self.model.__name__} by name: {name}, version: {version}, owner_org_id: {owner_org_id}, include_public: {include_public}, include_system_entities: {include_system_entities}, is_superuser: {is_superuser}")
        # Start with name filter
        stmt = select(self.model).where(getattr(self.model, "name") == name)
        
        # Add version filter if provided
        if version:
            stmt = stmt.where(getattr(self.model, version_field) == version)
        
        # Build filter for org-specific, public, and system entities
        or_conditions = [self.model.owner_org_id == owner_org_id]

        if include_public_system_entities and hasattr(self.model, "is_system_entity") and hasattr(self.model, "is_public"):
            or_conditions.append(and_(self.model.is_system_entity == True, self.model.is_public == True))
        
        if include_public and hasattr(self.model, "is_public"):
            or_conditions.append(self.model.is_public == True)
        
        # Add system entities filter if applicable and user is superuser
        if include_system_entities and is_superuser and hasattr(self.model, "is_system_entity"):
            or_conditions.append(self.model.is_system_entity == True)
        
        # Add sort order if provided
        if sort_by and sort_by != schemas.SearchSortBy.SELF_OWNED_FIRST:
            if sort_order == schemas.SortOrder.ASC:
                stmt = stmt.order_by(getattr(self.model, sort_by.value))
            else:
                stmt = stmt.order_by(getattr(self.model, sort_by.value).desc())
        
        stmt = stmt.where(or_(*or_conditions))
        
        # Execute query
        result = await db.exec(stmt)
        response = result.scalars().all()

        if sort_by == schemas.SearchSortBy.SELF_OWNED_FIRST:
            owned = [obj for obj in response if obj.owner_org_id == owner_org_id]
            not_owned = [obj for obj in response if obj.owner_org_id != owner_org_id]
            response = owned + not_owned

        # crud_logger.info(f"Found {len(response)} {self.model.__name__}s")
        return response

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> Sequence[ModelType]:
        """
        Retrieves multiple records with pagination.

        Args:
            db: AsyncSession instance.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            A sequence of model instances.
        """
        stmt = select(self.model).offset(skip).limit(limit).order_by(self.model.id)
        result = await db.exec(stmt)
        return result.scalars().all()

    async def create(self, db: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType:
        """
        Creates a new record in the database.

        Args:
            db: AsyncSession instance.
            obj_in: Pydantic schema containing the data for the new record.

        Returns:
            The newly created model instance.
        """
        try:
            obj_in_data = obj_in.model_dump(exclude_unset=True)
        except AttributeError:
            obj_in_data = obj_in.dict(exclude_unset=True)

        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: ModelType,
        obj_in: Union[UpdateSchemaType, Dict[str, Any]]
    ) -> ModelType:
        """
        Updates an existing record in the database.

        Args:
            db: AsyncSession instance.
            db_obj: The database object to update.
            obj_in: Pydantic schema or dictionary containing the fields to update.

        Returns:
            The updated model instance.
        """
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            try:
                update_data = obj_in.model_dump(exclude_unset=True)
            except AttributeError:
                update_data = obj_in.dict(exclude_unset=True)

        obj_data = db_obj.model_dump()
        for field in obj_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def remove_obj(self, db: AsyncSession, *, obj: ModelType) -> Optional[ModelType]:
        """Removes a record from the database using the object instance."""
        if obj:
            await db.delete(obj)
            await db.commit()
        return obj

    async def remove(self, db: AsyncSession, *, id: uuid.UUID) -> Optional[ModelType]:
        """
        Removes a record from the database by its primary key.

        Args:
            db: AsyncSession instance.
            id: Primary key of the record to remove.

        Returns:
            The removed model instance if found, otherwise None.
        """
        obj = await self.get(db, id=id)
        if obj:
            await db.delete(obj)
            await db.commit()
        return obj

# --- NodeTemplate DAO --- #

class NodeTemplateDAO(BaseDAO[models.NodeTemplate, schemas.NodeTemplateCreate, schemas.NodeTemplateUpdate]):
    """DAO for NodeTemplate models."""
    def __init__(self):
        super().__init__(models.NodeTemplate)

    async def get_by_name_version(self, db: AsyncSession, *, name: str, version: str) -> Optional[models.NodeTemplate]:
        """Get a node template by name and version."""
        stmt = select(self.model).where(self.model.name == name, self.model.version == version)
        result = await db.exec(stmt)
        return result.scalars().first()

    async def get_latest_prod_version(self, db: AsyncSession, *, name: str) -> Optional[models.NodeTemplate]:
        """Get the latest production-ready node template by name."""
        stmt = select(self.model).where(
            self.model.name == name,
            self.model.launch_status == LaunchStatus.PRODUCTION
        ).order_by(self.model.created_at.desc())
        result = await db.exec(stmt)
        return result.scalars().first()

    async def get_multi(
        self,
        db: AsyncSession,
        *,
        launch_statuses: Optional[List[LaunchStatus]] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Sequence[models.NodeTemplate]:
        """
        Retrieves multiple node templates with optional filtering by launch status.
        Defaults to returning non-EXPERIMENTAL templates if no statuses are provided.

        Args:
            db: AsyncSession instance.
            launch_statuses: List of launch statuses to include. If None, defaults to excluding EXPERIMENTAL.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            A sequence of NodeTemplate instances, ordered by name and version.
        """
        stmt = select(self.model)

        if launch_statuses:
            statuses_to_filter = [LaunchStatus(s) if isinstance(s, str) else s for s in launch_statuses]
            stmt = stmt.where(self.model.launch_status.in_(statuses_to_filter))
        else:
            stmt = stmt.where(self.model.launch_status != LaunchStatus.EXPERIMENTAL)

        stmt = stmt.order_by(self.model.name, self.model.version).offset(skip).limit(limit)
        result = await db.exec(stmt)
        return result.scalars().all()

# --- Workflow DAO --- #

class WorkflowDAO(BaseDAO[models.Workflow, schemas.WorkflowCreate, schemas.WorkflowUpdate]):
    """DAO for Workflow models."""
    def __init__(self):
        super().__init__(models.Workflow)

    async def get_by_name(self, db: AsyncSession, *, name: str, owner_org_id: uuid.UUID) -> Optional[models.Workflow]:
        """Get a workflow by name within a specific organization."""
        stmt = select(self.model).where(self.model.name == name, self.model.owner_org_id == owner_org_id)
        result = await db.exec(stmt)
        return result.scalars().first()
    
    async def get_by_id_and_org_or_public(self, db: AsyncSession, *, user: User, workflow_id: uuid.UUID, org_id: uuid.UUID, include_system_entities: bool = False) -> Optional[models.Workflow]:
        """Get a workflow by ID, ensuring it belongs to the specified organization or is public."""
        or_clause = or_(
                and_(self.model.owner_org_id == org_id, self.model.owner_org_id != None),
                self.model.is_public == True,
            )
        if user.is_superuser:
            or_clause = or_(or_clause, self.model.owner_org_id == None)
        if not include_system_entities:
            or_clause = and_(or_clause, self.model.is_system_entity == False)

        stmt = select(self.model).where(
            self.model.id == workflow_id,
            or_clause
        )
        result = await db.exec(stmt)
        return result.scalars().first()

    async def get_by_id_and_org(self, db: AsyncSession, *, workflow_id: uuid.UUID, org_id: uuid.UUID) -> Optional[models.Workflow]:
        """Get a workflow by ID, ensuring it belongs to the specified organization."""
        stmt = select(self.model).where(
            self.model.id == workflow_id, self.model.owner_org_id == org_id
        )
        result = await db.exec(stmt)
        return result.scalars().first()

    async def get_multi_by_org(
        self, db: AsyncSession, *,
        owner_org_id: uuid.UUID,
        include_public: bool = True,
        include_system_entities: bool = False,
        skip: int = 0,
        limit: int = 100
        ) -> Sequence[models.Workflow]:
        """Get multiple workflows for a specific organization."""
        stmt = select(self.model)
        clause = or_(
            self.model.owner_org_id == owner_org_id,
        )
        if include_public:
            clause = or_(clause, self.model.is_public == True)
        if not include_system_entities:
            clause = and_(clause, self.model.is_system_entity == False)
        stmt = stmt.where(clause)
        
        stmt = stmt.order_by(self.model.updated_at.desc()).offset(skip).limit(limit)
        result = await db.exec(stmt)
        return result.scalars().all()

    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: schemas.WorkflowCreate,
        owner_org_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None
    ) -> models.Workflow:
        """Creates a new workflow with owner and creator information."""
        try:
            create_data = obj_in.model_dump()
        except AttributeError:
            create_data = obj_in.dict()

        db_obj = self.model(
            **create_data,
            owner_org_id=owner_org_id,
            created_by_user_id=user_id,
            # updated_by_user_id=user_id
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: models.Workflow,
        obj_in: Union[schemas.WorkflowUpdate, Dict[str, Any]],
        user_id: Optional[uuid.UUID] = None
    ) -> models.Workflow:
        """Updates an existing workflow, setting the updated_by_user_id."""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            try:
                update_data = obj_in.model_dump(exclude_unset=True)
            except AttributeError:
                update_data = obj_in.dict(exclude_unset=True)

        obj_current_data = db_obj.model_dump()
        for field in obj_current_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])

        # db_obj.updated_by_user_id = user_id

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj
    
    async def remove_obj(self, db: AsyncSession, *, obj: models.Workflow) -> Optional[models.Workflow]:
        """Deletes a workflow only if it belongs to the specified organization."""
        if obj:
            await db.delete(obj)
            await db.commit()
        return obj

    async def remove_by_id_and_org(self, db: AsyncSession, *, id: uuid.UUID, owner_org_id: uuid.UUID) -> Optional[models.Workflow]:
        """Deletes a workflow only if it belongs to the specified organization."""
        db_obj = await self.get_by_id_and_org(db, workflow_id=id, org_id=owner_org_id)
        if db_obj:
            await db.delete(db_obj)
            await db.commit()
        return db_obj

# --- WorkflowRun DAO --- #

class WorkflowRunDAO(BaseDAO[models.WorkflowRun, schemas.WorkflowRunCreate, schemas.WorkflowRunUpdate]):
    """DAO for WorkflowRun models."""
    def __init__(self):
        super().__init__(models.WorkflowRun)

    async def get_run_by_id_and_org(self, db: AsyncSession, *, run_id: uuid.UUID, org_id: uuid.UUID) -> Optional[models.WorkflowRun]:
        """Get a workflow run by ID, ensuring it belongs to the specified organization."""
        stmt = select(self.model).options(joinedload(self.model.workflow)).where(
            self.model.id == run_id,
            self.model.owner_org_id == org_id
        )
        result = await db.exec(stmt)
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        *,
        workflow_id: uuid.UUID,
        owner_org_id: uuid.UUID,
        workflow_name: Optional[str] = None,
        triggered_by_user_id: Optional[uuid.UUID] = None,
        inputs: Optional[Dict[str, Any]] = None,
        thread_id: Optional[uuid.UUID] = None,
        status: WorkflowRunStatus = WorkflowRunStatus.SCHEDULED,
        tag: Optional[str] = None,
        applied_workflow_config_overrides: Optional[str] = None,
        parent_run_id: Optional[uuid.UUID] = None
    ) -> models.WorkflowRun:
        """Creates a new workflow run record."""
        # Compute deterministic input hash for caching
        input_hash: Optional[str] = None
        if inputs is not None:
            try:
                normalized = json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                input_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            except Exception:
                # If hashing fails for any reason, leave hash as None (do not block run creation)
                input_hash = None

        db_obj = self.model(
            workflow_id=workflow_id,
            owner_org_id=owner_org_id,
            triggered_by_user_id=triggered_by_user_id,
            inputs=inputs,
            status=status,
            thread_id=thread_id,
            workflow_name=workflow_name,
            tag=tag,
            applied_workflow_config_overrides=applied_workflow_config_overrides,
            parent_run_id=parent_run_id,
            input_hash=input_hash,
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update_status(
        self,
        db: AsyncSession,
        *,
        run_id: uuid.UUID,
        status: WorkflowRunStatus,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        thread_id: Optional[uuid.UUID] = None,
        outputs: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Updates the status and optionally other fields of a workflow run.
        Uses SQLAlchemy `update` for efficiency.

        Returns:
            True if the record was found and updated, False otherwise.
        """
        values_to_update = {"status": status}

        if error_message is not None:
            values_to_update["error_message"] = error_message
        if ended_at is not None:
            values_to_update["ended_at"] = ended_at
        if thread_id is not None:
            values_to_update["thread_id"] = thread_id
        if outputs is not None:
            values_to_update["outputs"] = outputs

        set_started_at = False
        if started_at:
            values_to_update["started_at"] = started_at
            set_started_at = True
        elif status == WorkflowRunStatus.RUNNING:
            current_run_stmt = select(self.model.started_at).where(self.model.id == run_id)
            current_started_at_val = await db.scalar(current_run_stmt)
            if not current_started_at_val:
                values_to_update["started_at"] = datetime_now_utc()
                set_started_at = True

        stmt = (
            update(self.model)
            .where(self.model.id == run_id)
            .values(**values_to_update)
            .execution_options(synchronize_session="fetch")
        )
        result = await db.exec(stmt)
        await db.commit()
        return result.rowcount > 0

    async def update_outputs(
        self,
        db: AsyncSession,
        *,
        run_id: uuid.UUID,
        outputs: Optional[Dict[str, Any]],
        detailed_results_ref: Optional[str] = None
    ) -> bool:
        """
        Updates the outputs and detailed results reference of a workflow run.
        Uses SQLAlchemy `update`.

        Returns:
            True if the record was found and updated, False otherwise.
        """
        values_to_update = {}
        if outputs is not None:
            values_to_update["outputs"] = outputs
        if detailed_results_ref is not None:
            values_to_update["detailed_results_ref"] = detailed_results_ref

        if not values_to_update:
            return False

        stmt = (
            update(self.model)
            .where(self.model.id == run_id)
            .values(**values_to_update)
            .execution_options(synchronize_session="fetch")
        )
        result = await db.exec(stmt)
        await db.commit()
        return result.rowcount > 0

    def _build_run_filters(self, filters: Optional[Dict[str, Any]]) -> List:
        conditions = []
        if not filters:
            return conditions

        if filters.get("workflow_id"):
            conditions.append(self.model.workflow_id == filters["workflow_id"])
        if filters.get("workflow_name"):
            conditions.append(self.model.workflow_name == filters["workflow_name"])
        if filters.get("owner_org_id"):
            conditions.append(self.model.owner_org_id == filters["owner_org_id"])
        if filters.get("triggered_by_user_id"):
            conditions.append(self.model.triggered_by_user_id == filters["triggered_by_user_id"])
        if filters.get("status"):
            status_filter = filters["status"]
            if isinstance(status_filter, str):
                try:
                    status_filter = WorkflowRunStatus(status_filter)
                except ValueError:
                    pass
            conditions.append(self.model.status == status_filter)
        if filters.get("thread_id"):
            conditions.append(self.model.thread_id == filters["thread_id"])
        if filters.get("tag"):
            conditions.append(self.model.tag == filters["tag"])
        if filters.get("applied_workflow_config_overrides"):
            applied_overrides = filters["applied_workflow_config_overrides"]
            if isinstance(applied_overrides, str):
                conditions.append(self.model.applied_workflow_config_overrides == applied_overrides)
            elif isinstance(applied_overrides, list):
                override_conditions = []
                for override_id in applied_overrides:
                    like_pattern = f"%{override_id}%"
                    override_conditions.append(self.model.applied_workflow_config_overrides.like(like_pattern))
                if override_conditions:
                    conditions.append(or_(*override_conditions))

        return conditions

    async def get_multi_filtered(
        self,
        db: AsyncSession,
        *,
        filters: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 100,
        order_by: str = "created_at",
        order_dir: str = "desc"
    ) -> Sequence[models.WorkflowRun]:
        stmt = select(self.model).options(joinedload(self.model.workflow))

        conditions = self._build_run_filters(filters)
        if conditions:
            stmt = stmt.where(and_(*conditions))

        sort_column = getattr(self.model, order_by, self.model.created_at)
        if order_dir.lower() == "asc":
            stmt = stmt.order_by(sort_column.asc())
        else:
            stmt = stmt.order_by(sort_column.desc())

        stmt = stmt.offset(skip).limit(limit)

        result = await db.exec(stmt)
        return result.scalars().all()

    async def get_multi_by_workflow(
        self, db: AsyncSession, *, workflow_id: uuid.UUID, skip: int = 0, limit: int = 100, filters: Optional[Dict[str, Any]] = None
    ) -> Sequence[models.WorkflowRun]:
        """Get runs for a specific workflow, allowing additional filters."""
        combined_filters = {"workflow_id": workflow_id, **(filters or {})}
        order_by = filters.get("order_by", "created_at") if filters else "created_at"
        order_dir = filters.get("order_dir", "desc") if filters else "desc"
        return await self.get_multi_filtered(db, filters=combined_filters, skip=skip, limit=limit, order_by=order_by, order_dir=order_dir)

    async def get_multi_by_org(
        self, db: AsyncSession, *, owner_org_id: uuid.UUID, skip: int = 0, limit: int = 100, filters: Optional[Dict[str, Any]] = None
    ) -> Sequence[models.WorkflowRun]:
        """Get runs for a specific organization, allowing additional filters."""
        combined_filters = {"owner_org_id": owner_org_id, **(filters or {})}
        order_by = filters.get("order_by", "created_at") if filters else "created_at"
        order_dir = filters.get("order_dir", "desc") if filters else "desc"
        return await self.get_multi_filtered(db, filters=combined_filters, skip=skip, limit=limit, order_by=order_by, order_dir=order_dir)
    
    async def find_recent_completed_runs_by_input_hash(
        self,
        db: AsyncSession,
        *,
        workflow_id: uuid.UUID,
        owner_org_id: uuid.UUID,
        input_hash: str,
        since_ts: datetime,
        limit: int = 5,
    ) -> Sequence[models.WorkflowRun]:
        """
        Find recent successful workflow runs that match the same input hash within a lookback window.

        Args:
            db: AsyncSession
            workflow_id: Workflow ID to match
            owner_org_id: Org context
            input_hash: Deterministic hash of normalized inputs
            since_ts: Only consider runs created at or after this timestamp
            limit: Max number of runs to return (ordered newest first)

        Returns:
            A sequence of matching WorkflowRun objects.
        """
        conditions = [
            self.model.workflow_id == workflow_id,
            self.model.owner_org_id == owner_org_id,
            self.model.input_hash == input_hash,
            self.model.status == WorkflowRunStatus.COMPLETED,
            or_(self.model.error_message == None, self.model.error_message == ""),
            self.model.created_at >= since_ts,
        ]
        stmt = (
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.created_at.desc())
            .limit(limit)
        )
        result = await db.exec(stmt)
        return result.scalars().all()

    async def find_recent_completed_runs_by_name_and_input_hash(
        self,
        db: AsyncSession,
        *,
        workflow_name: str,
        owner_org_id: uuid.UUID,
        input_hash: str,
        since_ts: datetime,
        limit: int = 5,
    ) -> Sequence[models.WorkflowRun]:
        """
        Find recent successful workflow runs for a workflow name that match the same input hash.
        Uses the name-based composite index for speed.
        """
        conditions = [
            self.model.workflow_name == workflow_name,
            self.model.owner_org_id == owner_org_id,
            self.model.input_hash == input_hash,
            self.model.status == WorkflowRunStatus.COMPLETED,
            or_(self.model.error_message == None, self.model.error_message == ""),
            self.model.created_at >= since_ts,
        ]
        stmt = (
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.created_at.desc())
            .limit(limit)
        )
        result = await db.exec(stmt)
        return result.scalars().all()

# --- Base Template DAO --- #

class BaseTemplateDAO(BaseDAO[TemplateModelType, TemplateCreateSchemaType, TemplateUpdateSchemaType]):
    """
    Base DAO for template models (PromptTemplate, SchemaTemplate) supporting
    organization-specific and system templates.
    """

    async def get_by_name_version(
        self, db: AsyncSession, *, name: str, version: str, owner_org_id: Optional[uuid.UUID] = None
    ) -> Optional[TemplateModelType]:
        """
        Gets a template by name and version. Checks org-specific first if owner_org_id
        is provided, then falls back to system templates.

        Args:
            db: AsyncSession instance.
            name: Template name.
            version: Template version string.
            owner_org_id: If provided, look for an organization-specific template first.

        Returns:
            The template model instance if found, otherwise None.
        """
        if owner_org_id:
            stmt_org = select(self.model).where(
                self.model.name == name,
                self.model.version == version,
                self.model.owner_org_id == owner_org_id,
                self.model.is_system_entity == False
            )
            result_org = await db.exec(stmt_org)
            template = result_org.scalars().first()
            if template:
                return template
        
        stmt_sys = select(self.model).where(
            self.model.name == name,
            self.model.version == version,
            self.model.is_system_entity == True
        )
        result_sys = await db.exec(stmt_sys)
        return result_sys.scalars().first()

    async def get_multi_by_org(
        self, db: AsyncSession, *, owner_org_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[TemplateModelType]:
        """Retrieves templates owned by a specific organization (non-system)."""
        stmt = select(self.model).where(
            self.model.owner_org_id == owner_org_id,
            self.model.is_system_entity == False
        ).order_by(self.model.name, self.model.version).offset(skip).limit(limit)
        result = await db.exec(stmt)
        return result.scalars().all()

    async def get_multi_system(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> Sequence[TemplateModelType]:
        """Retrieves system templates."""
        stmt = select(self.model).where(
            self.model.is_system_entity == True
        ).order_by(self.model.name, self.model.version).offset(skip).limit(limit)
        result = await db.exec(stmt)
        return result.scalars().all()

    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: TemplateCreateSchemaType,
        owner_org_id: uuid.UUID
    ) -> TemplateModelType:
        """Creates an organization-specific template."""
        try:
            create_data = obj_in.model_dump()
        except AttributeError:
            create_data = obj_in.dict()
        create_data['is_system_entity'] = create_data.pop('is_system_entity', False)
        db_obj = self.model(
            **create_data,
            owner_org_id=owner_org_id,
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def remove_by_id_and_org(
        self, db: AsyncSession, *, id: uuid.UUID, owner_org_id: uuid.UUID
    ) -> Optional[TemplateModelType]:
        """Removes an organization-specific template by ID, ensuring correct ownership."""
        stmt = select(self.model).where(
            self.model.id == id,
            self.model.owner_org_id == owner_org_id,
            self.model.is_system_entity == False
        )
        result = await db.exec(stmt)
        db_obj = result.scalars().first()

        if db_obj:
            await db.delete(db_obj)
            await db.commit()
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: TemplateModelType,
        obj_in: Union[TemplateUpdateSchemaType, Dict[str, Any]]
    ) -> TemplateModelType:
        """
        Updates an organization-specific template.
        Prevents modification of `owner_org_id` and `is_system_entity`.
        """
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            try:
                update_data = obj_in.model_dump(exclude_unset=True)
            except AttributeError:
                update_data = obj_in.dict(exclude_unset=True)

        update_data.pop('owner_org_id', None)
        update_data.pop('is_system_entity', None)
        update_data.pop('id', None)
        update_data.pop('created_at', None)

        obj_current_data = db_obj.model_dump()
        for field in obj_current_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

# --- PromptTemplate DAO --- #

class PromptTemplateDAO(BaseTemplateDAO[models.PromptTemplate, schemas.PromptTemplateCreate, schemas.PromptTemplateUpdate]):
    """DAO for PromptTemplate models."""
    def __init__(self):
        super().__init__(models.PromptTemplate)

# --- SchemaTemplate DAO --- #

class SchemaTemplateDAO(BaseTemplateDAO[models.SchemaTemplate, schemas.SchemaTemplateCreate, schemas.SchemaTemplateUpdate]):
    """DAO for SchemaTemplate models."""
    def __init__(self):
        super().__init__(models.SchemaTemplate)

# --- UserNotification DAO --- #

class UserNotificationDAO(BaseDAO[models.UserNotification, schemas.UserNotificationCreate, PydanticBaseModel]):
    """DAO for UserNotification models."""
    def __init__(self):
        super().__init__(models.UserNotification)

    async def create(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        notification_type: NotificationType,
        message: Dict[str, Any],
        related_run_id: Optional[uuid.UUID] = None
    ) -> models.UserNotification:
        """Creates a new user notification."""
        db_obj = self.model(
            user_id=user_id,
            org_id=org_id,
            notification_type=notification_type.value,
            message=message,
            related_run_id=related_run_id,
            is_read=False
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def mark_as_read(self, db: AsyncSession, *, id: uuid.UUID, user_id: uuid.UUID) -> Optional[models.UserNotification]:
        """
        Marks a specific notification as read if it belongs to the user and is unread.
        Uses SQLAlchemy `update` with `returning` clause for efficiency.

        Args:
            db: AsyncSession instance.
            id: ID of the notification to mark as read.
            user_id: ID of the user (for ownership verification).

        Returns:
            The updated UserNotification object if successful, otherwise None.
        """
        stmt = (
            update(self.model)
            .where(
                self.model.id == id,
                self.model.user_id == user_id,
                self.model.is_read == False
            )
            .values(is_read=True, read_at=datetime_now_utc())
            .returning(self.model)
            .execution_options(synchronize_session="fetch")
        )
        result = await db.exec(stmt)
        await db.commit()
        updated_obj = result.scalars().first()
        return updated_obj

    async def mark_all_as_read(self, db: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID) -> int:
        """
        Marks all unread notifications as read for a user in an organization.
        Uses SQLAlchemy `update`.

        Args:
            db: AsyncSession instance.
            user_id: ID of the user.
            org_id: ID of the organization.

        Returns:
            The number of notifications that were marked as read.
        """
        current_time = datetime_now_utc()
        stmt = (
            update(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.org_id == org_id,
                self.model.is_read == False
            )
            .values(is_read=True, read_at=current_time)
            .execution_options(synchronize_session=False)
        )
        result = await db.exec(stmt)
        await db.commit()
        return result.rowcount

    async def get_multi_by_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        is_read: Optional[bool] = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Sequence[models.UserNotification]:
        """
        Retrieves multiple notifications for a user within an organization,
        with optional filtering by read status and sorting.

        Args:
            db: AsyncSession instance.
            user_id: ID of the user.
            org_id: ID of the organization.
            is_read: Optional filter for read/unread status (True/False).
            skip: Number of records to skip.
            limit: Maximum number of records to return.
            sort_by: Field name to sort by (defaults to 'created_at').
            sort_order: Sort direction ('asc' or 'desc', defaults to 'desc').

        Returns:
            A sequence of UserNotification objects.
        """
        clause = and_(
            self.model.user_id == user_id,
        )
        if org_id is not None:
            clause = and_(clause, self.model.org_id == org_id)

        stmt = select(self.model).where(clause)

        if is_read is not None:
            stmt = stmt.where(self.model.is_read == is_read)
            
        sort_column = getattr(self.model, sort_by, self.model.created_at)
        if sort_order.lower() == "asc":
            stmt = stmt.order_by(sort_column.asc())
        else:
            stmt = stmt.order_by(sort_column.desc())

        stmt = stmt.offset(skip).limit(limit)

        result = await db.exec(stmt)
        return result.scalars().all()

    async def get_by_run_and_user(self, db: AsyncSession, *, related_run_id: uuid.UUID, user_id: uuid.UUID) -> Sequence[models.UserNotification]:
        """Retrieves notifications for a specific run belonging to a user."""
        stmt = select(self.model).where(
            self.model.related_run_id == related_run_id,
            self.model.user_id == user_id
        ).order_by(self.model.created_at.desc())
        result = await db.exec(stmt)
        return result.scalars().all()

    async def count_unread_by_user(self, db: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID) -> int:
        """Counts unread notifications for a user in an organization."""
        stmt = select(func.count(self.model.id)).select_from(self.model).where(
            self.model.user_id == user_id,
            self.model.org_id == org_id,
            self.model.is_read == False
        )
        result = await db.exec(stmt)
        count = result.scalar_one()
        return count if count is not None else 0

# --- HITLJob DAO --- #

class HITLJobDAO(BaseDAO[models.HITLJob, schemas.HITLJobCreate, PydanticBaseModel]):
    """DAO for Human-in-the-Loop (HITL) Job models."""
    def __init__(self):
        super().__init__(models.HITLJob)

    async def create(
        self,
        db: AsyncSession,
        *,
        requesting_run_id: uuid.UUID,
        org_id: uuid.UUID,
        request_details: Dict[str, Any],
        assigned_user_id: Optional[uuid.UUID] = None,
        response_schema: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
        status: HITLJobStatus = HITLJobStatus.PENDING
    ) -> models.HITLJob:
        """Creates a new HITL job."""
        db_obj = self.model(
            requesting_run_id=requesting_run_id,
            org_id=org_id,
            request_details=request_details,
            assigned_user_id=assigned_user_id,
            response_schema=response_schema,
            expires_at=expires_at,
            status=status.value
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update_response(
        self,
        db: AsyncSession,
        *,
        id: uuid.UUID,
        response_data: Dict[str, Any],
        user_id: uuid.UUID
    ) -> Optional[models.HITLJob]:
        """
        Updates the response data for a PENDING HITL job and marks it as RESPONDED.
        Performs a basic check that the job is PENDING. More complex authorization
        (e.g., checking if user_id matches assigned_user_id or user roles)
        should ideally occur in the service layer before calling this DAO method.
        Uses SQLAlchemy `update` with `returning` for efficiency.

        Args:
            db: AsyncSession instance.
            id: ID of the HITL job.
            response_data: The data provided by the user.
            user_id: ID of the user submitting the response (for potential logging/auditing).

        Returns:
            The updated HITLJob object if successful, otherwise None (e.g., job not found or not PENDING).
        """
        current_time = datetime_now_utc()
        stmt = (
            update(self.model)
            .where(
                self.model.id == id,
                self.model.status == HITLJobStatus.PENDING.value
            )
            .values(
                response_data=response_data,
                status=HITLJobStatus.RESPONDED.value,
                responded_at=current_time
            )
            .returning(self.model)
            .execution_options(synchronize_session="fetch")
        )
        result = await db.exec(stmt)
        await db.commit()
        updated_obj = result.scalars().first()
        return updated_obj

    async def update_status(
        self,
        db: AsyncSession,
        *,
        id: uuid.UUID,
        status: HITLJobStatus
    ) -> Optional[models.HITLJob]:
        """
        Updates the status of an HITL job (e.g., to EXPIRED, CANCELLED).
        Uses SQLAlchemy `update` with `returning`.

        Args:
            db: AsyncSession instance.
            id: ID of the HITL job.
            status: The new status enum member.

        Returns:
            The updated HITLJob object if successful, otherwise None.
        """
        values_to_update = {"status": status.value}

        stmt = (
            update(self.model)
            .where(self.model.id == id)
            .values(**values_to_update)
            .returning(self.model)
            .execution_options(synchronize_session="fetch")
        )
        result = await db.exec(stmt)
        await db.commit()
        updated_obj = result.scalars().first()
        return updated_obj

    def _build_hitl_filters(self, filters: Optional[Dict[str, Any]]) -> List:
        conditions = []
        if not filters:
            return conditions

        if filters.get("run_id"):
            conditions.append(self.model.requesting_run_id == filters["run_id"])
        if filters.get("org_id"):
            conditions.append(self.model.org_id == filters["org_id"])
        if filters.get("assigned_user_id"):
            conditions.append(self.model.assigned_user_id == filters["assigned_user_id"])
        if filters.get("status"):
            status_filter = filters["status"]
            if isinstance(status_filter, HITLJobStatus):
                conditions.append(self.model.status == status_filter.value)
            else:
                conditions.append(self.model.status == status_filter)

        if filters.get("pending_only", False):
            conditions.append(self.model.status == HITLJobStatus.PENDING.value)
        if filters.get("responded_only", False):
            conditions.append(self.model.status == HITLJobStatus.RESPONDED.value)
        if filters.get("exclude_cancelled", False):
            conditions.append(self.model.status != HITLJobStatus.CANCELLED.value)
        if filters.get("exclude_expired", False):
            conditions.append(self.model.status != HITLJobStatus.EXPIRED.value)

        if "user_accessible_id" in filters and "org_id" in filters:
            user_id = filters["user_accessible_id"]
            org_id = filters["org_id"]
            if self.model.org_id == filters["org_id"] not in conditions:
                conditions.append(self.model.org_id == org_id)

            conditions.append(
                or_(
                    self.model.assigned_user_id == user_id,
                    self.model.assigned_user_id == None
                )
            )

        now = datetime_now_utc()
        if filters.get("exclude_expired_time", False):
            conditions.append(or_(self.model.expires_at == None, self.model.expires_at > now))
        elif filters.get("only_expired_time", False):
            conditions.append(and_(self.model.expires_at != None, self.model.expires_at <= now))

        return conditions

    async def get_multi_filtered(
        self,
        db: AsyncSession,
        *,
        filters: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 100,
        order_by: str = "created_at",
        order_dir: str = "desc"
    ) -> Sequence[models.HITLJob]:
        stmt = select(self.model)

        conditions = self._build_hitl_filters(filters)
        if conditions:
            stmt = stmt.where(and_(*conditions))

        sort_column = getattr(self.model, order_by, self.model.created_at)
        if order_dir.lower() == "asc":
            stmt = stmt.order_by(sort_column.asc())
        else:
            stmt = stmt.order_by(sort_column.desc())

        stmt = stmt.offset(skip).limit(limit)

        result = await db.exec(stmt)
        return result.scalars().all()

    async def get_pending_by_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        skip: int = 0,
        limit: int = 10
    ) -> Sequence[models.HITLJob]:
        """
        Retrieves PENDING HITL jobs accessible to a user within an organization.
        Includes jobs directly assigned to the user AND unassigned jobs in the org.
        Excludes expired jobs by default.
        Orders by creation time (oldest first).
        """
        filters = {
            "user_accessible_id": user_id,
            "org_id": org_id,
            "pending_only": True,
            "exclude_expired_time": True
        }
        return await self.get_multi_filtered(
            db,
            filters=filters,
            skip=skip,
            limit=limit,
            order_by="created_at",
            order_dir="asc"
        )

    async def get_by_run_id(
        self,
        db: AsyncSession,
        *,
        requesting_run_id: uuid.UUID,
        status: Optional[HITLJobStatus] = None
    ) -> Sequence[models.HITLJob]:
        """Retrieves HITL jobs for a specific run, optionally filtered by status."""
        filters = {"run_id": requesting_run_id}
        if status:
            filters["status"] = status
        return await self.get_multi_filtered(db, filters=filters, order_by="created_at", order_dir="desc")

    async def get_pending_by_run(self, db: AsyncSession, *, requesting_run_id: uuid.UUID) -> Sequence[models.HITLJob]:
        """Retrieves only PENDING HITL jobs for a specific run."""
        filters = {
            "run_id": requesting_run_id,
            "pending_only": True,
            "exclude_expired_time": True
        }
        return await self.get_multi_filtered(db, filters=filters, order_by="created_at", order_dir="desc")

# --- ChatThread DAO --- #

class ChatThreadDAO(BaseDAO[models.ChatThread, schemas.ChatThreadCreate, schemas.ChatThreadUpdate]):
    """DAO for ChatThread model."""
    
    def __init__(self):
        super().__init__(models.ChatThread)
    
    async def get_by_id(self, db: AsyncSession, *, thread_id: uuid.UUID) -> Optional[models.ChatThread]:
        """Get a chat thread by ID."""
        return await self.get(db, thread_id)
    
    async def get_by_id_and_owner(self, db: AsyncSession, *, thread_id: uuid.UUID, user_id: uuid.UUID) -> Optional[models.ChatThread]:
        """Get a chat thread by ID and verify ownership."""
        query = select(self.model).where(
            and_(
                self.model.id == thread_id,
                self.model.user_id == user_id
            )
        )
        result = await db.exec(query)
        return result.scalars().first()
    
    async def get_by_workflow(
        self, 
        db: AsyncSession, 
        *, 
        workflow_name: str,
        workflow_version: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
        tag: Optional[str] = None,
        skip: int = 0, 
        limit: int = 100
    ) -> Sequence[models.ChatThread]:
        """Get chat threads for a specific workflow, optionally filtered by owner and tag."""
        query = select(self.model).where(self.model.workflow_name == workflow_name)
        
        if workflow_version is not None:
            query = query.where(self.model.workflow_version == workflow_version)
            
        if user_id is not None:
            query = query.where(self.model.user_id == user_id)

        if tag is not None:
            query = query.where(self.model.tag == tag)
            
        query = query.offset(skip).limit(limit).order_by(desc(self.model.updated_at))
        result = await db.exec(query)
        return result.scalars().all()
    
    async def get_multi_filtered(
        self,
        db: AsyncSession,
        *,
        workflow_name: Optional[str] = None,
        workflow_version: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
        tag: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Sequence[models.ChatThread]:
        """
        Get chat threads with comprehensive filtering support.
        
        Args:
            db: Database session
            workflow_name: Optional workflow name filter
            workflow_version: Optional workflow version filter  
            user_id: Optional user ID filter (for ownership filtering)
            tag: Optional tag filter
            skip: Number of records to skip (pagination)
            limit: Maximum number of records to return
            
        Returns:
            Sequence of ChatThread models matching the filters
        """
        query = select(self.model)
        
        # Apply filters conditionally
        if workflow_name is not None:
            query = query.where(self.model.workflow_name == workflow_name)
            
        if workflow_version is not None:
            query = query.where(self.model.workflow_version == workflow_version)
            
        if user_id is not None:
            query = query.where(self.model.user_id == user_id)

        if tag is not None:
            query = query.where(self.model.tag == tag)
            
        # Apply pagination and ordering
        query = query.offset(skip).limit(limit).order_by(desc(self.model.updated_at))
        
        result = await db.exec(query)
        return result.scalars().all()
    
    async def get_by_owner(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100
    ) -> Sequence[models.ChatThread]:
        """Get all chat threads for a specific owner."""
        query = select(self.model).where(self.model.user_id == user_id)
        query = query.offset(skip).limit(limit).order_by(desc(self.model.updated_at))
        result = await db.exec(query)
        return result.scalars().all()
    
    async def create_thread(
        self,
        db: AsyncSession,
        *,
        thread_in: schemas.ChatThreadCreate,
        user_id: Optional[uuid.UUID] = None
    ) -> models.ChatThread:
        """Create a new chat thread with specified owner."""
        # Create thread_in dict and overwrite user_id if provided
        obj_in_data = thread_in.model_dump()
        if user_id is not None:
            obj_in_data["user_id"] = str(user_id)
        
        obj_in = schemas.ChatThreadCreate(**obj_in_data)
        return await self.create(db, obj_in=obj_in)
    
    async def update_thread(
        self,
        db: AsyncSession,
        *,
        thread_id: uuid.UUID,
        thread_update: schemas.ChatThreadUpdate,
        user_id: Optional[uuid.UUID] = None
    ) -> Optional[models.ChatThread]:
        """Update an existing chat thread, optionally verifying ownership."""
        if user_id is not None:
            # Only update if user is the owner
            db_obj = await self.get_by_id_and_owner(db, thread_id=thread_id, user_id=user_id)
        else:
            # No ownership check (for superusers)
            db_obj = await self.get(db, thread_id)
            
        if not db_obj:
            return None
        
        return await self.update(db, db_obj=db_obj, obj_in=thread_update)
    
    async def remove_thread(
        self,
        db: AsyncSession,
        *,
        thread_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None
    ) -> Optional[models.ChatThread]:
        """
        Remove a chat thread by ID, optionally verifying ownership.
        
        If user_id is provided, the thread will only be deleted if the
        specified user is the owner.
        """
        if user_id is not None:
            # Only delete if user is the owner
            db_obj = await self.get_by_id_and_owner(db, thread_id=thread_id, user_id=user_id)
            if not db_obj:
                return None
            return await self.remove_obj(db, obj=db_obj)
        else:
            # No ownership check (for superusers)
            return await self.remove(db, id=thread_id)

# --- WorkflowConfigOverrideDAO --- #

class WorkflowConfigOverrideDAO(BaseDAO[models.WorkflowConfigOverride, PydanticBaseModel, PydanticBaseModel]):
    """DAO for WorkflowConfigOverride models."""
    def __init__(self):
        super().__init__(models.WorkflowConfigOverride)

    async def create(
        self,
        db: AsyncSession,
        *,
        workflow_id: Optional[uuid.UUID] = None,
        workflow_name: Optional[str] = None,
        workflow_version: Optional[str] = None,
        override_graph_schema: Dict[str, Any],
        is_system_entity: bool = False,
        user_id: Optional[uuid.UUID] = None,
        org_id: Optional[uuid.UUID] = None,
        is_active: bool = True,
        description: Optional[str] = None,
        tag: Optional[str] = None
    ) -> models.WorkflowConfigOverride:
        """
        Creates a new workflow configuration override.
        Either workflow_id or workflow_name must be provided.
        At least one of is_system_entity, user_id, or org_id must be provided.
        
        Args:
            db: AsyncSession instance
            workflow_id: Optional UUID of the specific workflow to override
            workflow_name: Optional name of workflows to override (alternative to workflow_id)
            workflow_version: Optional version of the workflow to override (only with workflow_name)
            override_graph_schema: The override configuration for the workflow graph schema
            is_system_entity: Whether this is a system-wide override
            user_id: Optional user ID for user-specific overrides
            org_id: Optional organization ID for org-specific overrides
            is_active: Whether this override is active
            description: Optional description of the override
            tag: Optional tag to further identify this override
        
        Returns:
            The created WorkflowConfigOverride
        """
        # # Validate that either workflow_id or workflow_name is provided
        # if workflow_id is None and workflow_name is None:
        #     raise ValueError("Either workflow_id or workflow_name must be provided")
        
        # Validate that at least one scope identifier is provided
        if not is_system_entity and user_id is None and org_id is None:
            raise ValueError("At least one of is_system_entity, user_id, or org_id must be provided")
        
        # Validate that if is_system_entity is True, user_id and org_id are None
        if is_system_entity and (user_id is not None or org_id is not None):
            raise ValueError("If is_system_entity is True, user_id and org_id must be None")
        
        # Validate that workflow_version is only used with workflow_name
        if workflow_id is not None and workflow_version is not None:
            raise ValueError("workflow_version can only be provided when using workflow_name")
        
        db_obj = models.WorkflowConfigOverride(
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            workflow_version=workflow_version,
            override_graph_schema=override_graph_schema,
            is_system_entity=is_system_entity,
            user_id=user_id,
            org_id=org_id,
            is_active=is_active,
            description=description,
            tag=tag
        )
        
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        override_id: uuid.UUID,
        override_graph_schema: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None,
        description: Optional[str] = None,
        tag: Optional[str] = None
    ) -> Optional[models.WorkflowConfigOverride]:
        """
        Updates an existing workflow configuration override.
        Only certain fields can be updated (override_graph_schema, is_active, description, tag).
        The core identifiers (workflow_id/name, scope) cannot be changed.
        
        Args:
            db: AsyncSession instance
            override_id: UUID of the override to update
            override_graph_schema: Updated override configuration
            is_active: Updated active status
            description: Updated description
            tag: Updated tag
        
        Returns:
            The updated WorkflowConfigOverride or None if not found
        """
        db_obj = await self.get(db, id=override_id)
        if not db_obj:
            return None
        
        update_data = {}
        if override_graph_schema is not None:
            update_data["override_graph_schema"] = override_graph_schema
        if is_active is not None:
            update_data["is_active"] = is_active
        if description is not None:
            update_data["description"] = description
        if tag is not None:
            update_data["tag"] = tag
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def get_overrides_for_workflow(
        self,
        db: AsyncSession,
        *,
        workflow_id: uuid.UUID,
        workflow_name: Optional[str] = None,
        workflow_version: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
        user_is_superuser: bool = False,
        org_id: Optional[uuid.UUID] = None,
        include_tags: Optional[List[str]] = None,
        include_global_overrides: bool = True,
        include_active: bool = True,
        include_system_overrides: bool = True,
        include_org_overrides: bool = True,
        include_user_overrides: bool = True
    ) -> Sequence[models.WorkflowConfigOverride]:
        """
        Retrieves active override configurations for a specific workflow,
        ordered by priority (system < org < user < user+org < specific tags).
        
        Args:
            db: AsyncSession instance
            workflow_id: UUID of the workflow
            workflow_name: Name of the workflow
            workflow_version: Version of the workflow
            user_id: Optional user ID for user-specific overrides
            user_is_superuser: Whether the user is a superuser
            org_id: Optional organization ID for org-specific overrides
            include_active: Whether to include active overrides
            include_global_overrides: Whether to include global overrides
            include_tags: Optional list of specific tags to include (even if not active)
            include_system_overrides: Whether to include system-wide overrides
            include_org_overrides: Whether to include org-specific overrides
            include_user_overrides: Whether to include user-specific overrides
        
        Returns:
            Sequence of WorkflowConfigOverride objects in priority order
        """
        # assert workflow_id or workflow_name, "Either workflow_id or workflow_name must be provided"
        # assert not (workflow_id and workflow_version), "Only one of workflow_id or workflow_version can be provided"
        
        # Add workflow identifier condition
        workflow_identifier_conditions = []
        if workflow_id:
            workflow_identifier_conditions.append(self.model.workflow_id == workflow_id)
        if workflow_name:
            workflow_name_and_version_conditions = []
            workflow_name_and_version_conditions.append(self.model.workflow_name == workflow_name)
            if workflow_version:
                workflow_name_and_version_conditions.append(self.model.workflow_version == workflow_version)
            workflow_identifier_conditions.append(and_(*workflow_name_and_version_conditions))
        # Global X-workflow configs
        if include_global_overrides:
            workflow_identifier_conditions.append(and_(self.model.workflow_id == None, self.model.workflow_name == None))
        if workflow_identifier_conditions:
            workflow_identifier_conditions = [or_(*workflow_identifier_conditions)] if len(workflow_identifier_conditions) > 1 else workflow_identifier_conditions
            # conditions.append(workflow_identifier_conditions)
        
        # Add active status condition (unless specific tags are requested)
        tag_conditions = []
        if include_tags:
            tag_conditions.append(self.model.tag.in_(include_tags))
            if not user_is_superuser:
                tag_conditions.append(self.model.is_system_entity == False)
                tag_conditions = [and_(*tag_conditions)]

        
        # Active conditions
        active_conditions = [self.model.is_active == True] if include_active else []
        
        # Build scope conditions based on parameters
        scope_conditions = []
        
        if include_system_overrides:
            scope_conditions.append(
                and_(
                    self.model.is_system_entity == True,
                    self.model.user_id == None,
                    self.model.org_id == None
                )
            )
        
        if include_org_overrides and org_id:
            scope_conditions.append(
                and_(
                    self.model.is_system_entity == False,
                    self.model.user_id == None,
                    self.model.org_id == org_id
                )
            )
        
        if include_user_overrides and user_id:
            # User-only overrides (across all orgs)
            scope_conditions.append(
                and_(
                    self.model.is_system_entity == False,
                    self.model.user_id == user_id,
                    self.model.org_id == None
                )
            )
            
            # User-org specific overrides
            if org_id:
                scope_conditions.append(
                    and_(
                        self.model.is_system_entity == False,
                        self.model.user_id == user_id,
                        self.model.org_id == org_id
                    )
                )
        
        
        workflow_identifier_condition = [or_(*workflow_identifier_conditions)] if len(workflow_identifier_conditions) > 1 else workflow_identifier_conditions
        # workflow_identifier_condition = workflow_identifier_condition[0] if workflow_identifier_condition else None

        scope_condition = [or_(*scope_conditions)] if len(scope_conditions) > 1 else scope_conditions
        # scope_condition = scope_condition[0] if scope_condition else None

        tag_condition = [or_(*tag_conditions)] if len(tag_conditions) > 1 else tag_conditions
        # tag_condition = tag_condition[0] if tag_condition else None

        active_condition = [or_(*active_conditions)] if len(active_conditions) > 1 else active_conditions
        # active_condition = active_condition[0] if active_condition else None
        
        # Build conditions
        conditions = []
        if workflow_identifier_condition:
            conditions.append(workflow_identifier_condition[0])
        if scope_condition:
            conditions.append(scope_condition[0])
        if tag_condition or active_condition:
            tag_or_active_condition = None
            if tag_condition and active_condition:
                tag_or_active_condition = or_(tag_condition[0], active_condition[0])
            elif tag_condition:
                tag_or_active_condition = tag_condition[0]
            elif active_condition:
                tag_or_active_condition = active_condition[0]
            if tag_or_active_condition is not None:
                conditions.append(tag_or_active_condition)
        
        # Build the query
        stmt = select(self.model).where(and_(*conditions))
        
        # Execute and return results
        result = await db.exec(stmt)
        overrides = result.scalars().all()
        
        # Sort by priority: system < org < user < user+org < with tag
        # This is a multi-key sort where we want to prioritize:
        # 1. Overrides with tags (if specified) over those without
        # 2. User+org scope over user-only scope over org-only scope over system-wide scope
        def override_priority(override):
            # First priority: overrides with requested tags
            is_requested_tag = include_tags and override.tag in include_tags

            is_global_override = not (override.workflow_id or override.workflow_name)
            
            # Second priority: scope specificity
            if override.is_system_entity:
                scope_priority = 0  # Lowest priority
            elif override.org_id and not override.user_id:
                scope_priority = 2  # Org-only
            elif override.user_id and not override.org_id:
                scope_priority = 4  # User-only
            elif override.user_id and override.org_id:
                scope_priority = 6  # User+org (highest)
            else:
                scope_priority = -2  # Fallback, shouldn't happen
            
            
            scope_priority -= 1 if is_global_override else 0
                
            # Return tuple for sorting (higher values have higher priority)
            return (1 if is_requested_tag else 0, scope_priority, override.updated_at)
        
        # Sort the overrides by priority
        sorted_overrides = sorted(overrides, key=override_priority, reverse=True)
        return sorted_overrides

    async def get_user_overrides(
        self, 
        db: AsyncSession, 
        *, 
        user_id: uuid.UUID,
        org_id: Optional[uuid.UUID] = None,
        is_active: Optional[bool] = None
    ) -> Sequence[models.WorkflowConfigOverride]:
        """
        Retrieves all override configurations for a specific user.
        
        Args:
            db: AsyncSession instance
            user_id: User ID to filter by
            org_id: Optional organization ID filter
            is_active: Optional filter for active status
        
        Returns:
            Sequence of WorkflowConfigOverride objects
        """
        conditions = [self.model.user_id == user_id]
        
        if org_id:
            conditions.append(self.model.org_id == org_id)
        
        if is_active is not None:
            conditions.append(self.model.is_active == is_active)
        
        stmt = select(self.model).where(and_(*conditions)).order_by(self.model.updated_at.desc())
        result = await db.exec(stmt)
        return result.scalars().all()

    async def get_org_overrides(
        self, 
        db: AsyncSession, 
        *, 
        org_id: uuid.UUID,
        is_active: Optional[bool] = None
    ) -> Sequence[models.WorkflowConfigOverride]:
        """
        Retrieves all override configurations for a specific organization.
        
        Args:
            db: AsyncSession instance
            org_id: Organization ID to filter by
            is_active: Optional filter for active status
        
        Returns:
            Sequence of WorkflowConfigOverride objects
        """
        conditions = [
            self.model.org_id == org_id,
            self.model.user_id == None  # Org-wide overrides have no user_id
        ]
        
        if is_active is not None:
            conditions.append(self.model.is_active == is_active)
        
        stmt = select(self.model).where(and_(*conditions)).order_by(self.model.updated_at.desc())
        result = await db.exec(stmt)
        return result.scalars().all()

    async def get_system_overrides(
        self, 
        db: AsyncSession, 
        *,
        is_active: Optional[bool] = None
    ) -> Sequence[models.WorkflowConfigOverride]:
        """
        Retrieves all system-wide override configurations.
        
        Args:
            db: AsyncSession instance
            is_active: Optional filter for active status
        
        Returns:
            Sequence of WorkflowConfigOverride objects
        """
        conditions = [self.model.is_system_entity == True]
        
        if is_active is not None:
            conditions.append(self.model.is_active == is_active)
        
        stmt = select(self.model).where(and_(*conditions)).order_by(self.model.updated_at.desc())
        result = await db.exec(stmt)
        return result.scalars().all()

    async def deactivate_override(
        self, 
        db: AsyncSession, 
        *, 
        override_id: uuid.UUID
    ) -> Optional[models.WorkflowConfigOverride]:
        """
        Deactivates an override configuration without deleting it.
        
        Args:
            db: AsyncSession instance
            override_id: UUID of the override to deactivate
        
        Returns:
            The updated WorkflowConfigOverride or None if not found
        """
        return await self.update(db, override_id=override_id, is_active=False)

    async def get_override_by_id_for_user(
        self,
        db: AsyncSession,
        *,
        override_id: uuid.UUID,
        user_id: uuid.UUID,
        org_id: Optional[uuid.UUID] = None
    ) -> Optional[models.WorkflowConfigOverride]:
        """
        Retrieves an override by ID ensuring it belongs to the specified user.
        
        Args:
            db: AsyncSession instance
            override_id: UUID of the override
            user_id: User ID (for authorization)
        
        Returns:
            The WorkflowConfigOverride if found and owned by the user, otherwise None
        """
        conditions = [
            self.model.id == override_id,
        ]
        
        # Add user_id or org_id condition
        user_or_org_conditions = [self.model.user_id == user_id]
        if org_id is not None:
            user_or_org_conditions.append(self.model.org_id == org_id)
        conditions.append(or_(*user_or_org_conditions))
            
        stmt = select(self.model).where(and_(*conditions))
        result = await db.exec(stmt)
        return result.scalars().first()

    async def get_overrides_by_tag(
        self, 
        db: AsyncSession, 
        *, 
        tag: str,
        is_active: Optional[bool] = None,
        user_id: Optional[uuid.UUID] = None,
        org_id: Optional[uuid.UUID] = None,
        user_is_superuser: bool = False
    ) -> Sequence[models.WorkflowConfigOverride]:
        """
        Retrieves all override configurations with a specific tag.
        
        Args:
            db: AsyncSession instance
            tag: Tag to filter by
            is_active: Optional filter for active status
            user_id: Optional user ID to filter by
            org_id: Optional organization ID to filter by
            user_is_superuser: Whether the user is a superuser and can see all overrides
        
        Returns:
            Sequence of WorkflowConfigOverride objects
        """
        conditions = [self.model.tag == tag]
        
        if is_active is not None:
            conditions.append(self.model.is_active == is_active)
            
        # If not superuser, add user/org conditions
        if not user_is_superuser:
            # Add user_id or org_id condition
            user_or_org_conditions = []
            if user_id:
                user_or_org_conditions.append(self.model.user_id == user_id)
            if org_id:
                user_or_org_conditions.append(self.model.org_id == org_id)
            if user_or_org_conditions:
                conditions.append(or_(*user_or_org_conditions))
            conditions.append(self.model.is_system_entity == False)
        
        stmt = select(self.model).where(and_(*conditions)).order_by(self.model.updated_at.desc())
        result = await db.exec(stmt)
        return result.scalars().all()

    async def get_overrides_by_ids(
        self,
        db: AsyncSession,
        *,
        override_ids: List[uuid.UUID]
    ) -> Sequence[models.WorkflowConfigOverride]:
        """
        Retrieves workflow configuration overrides by their IDs.

        Args:
            db: AsyncSession instance
            override_ids: List of override UUIDs to retrieve

        Returns:
            Sequence of WorkflowConfigOverride objects matching the provided IDs.
            Note that the result may contain fewer items than requested if some IDs don't exist.
        """
        if not override_ids:
            return []

        stmt = select(self.model).where(
            self.model.id.in_(override_ids)
        ).order_by(self.model.updated_at.desc())
        
        result = await db.exec(stmt)
        return result.scalars().all()


class AssetDAO(BaseDAO[models.Asset, schemas.AssetCreate, schemas.AssetUpdate]):
    """DAO for Asset operations."""
    
    def __init__(self):
        super().__init__(models.Asset)

    async def get_by_type_and_name(
        self,
        db: AsyncSession,
        *,
        org_id: uuid.UUID,
        asset_type: str,
        asset_name: str
    ) -> Optional[models.Asset]:
        """Get an asset by type and name within an organization."""
        stmt = select(self.model).where(
            and_(
                self.model.org_id == org_id,
                self.model.asset_type == asset_type,
                self.model.asset_name == asset_name
            )
        )
        result = await db.exec(stmt)
        return result.scalars().first()

    async def get_accessible_assets(
        self,
        db: AsyncSession,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        asset_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_shared: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "updated_at",
        sort_order: str = "desc"
    ) -> Sequence[models.Asset]:
        """
        Get assets accessible to a user within an organization.
        An asset is accessible if:
        - The user is the managing user, OR
        - The asset is shared within the organization
        """
        conditions = [
            self.model.org_id == org_id,
            or_(
                self.model.managing_user_id == user_id,
                self.model.is_shared == True
            )
        ]
        
        if asset_type is not None:
            conditions.append(self.model.asset_type == asset_type)
        if is_active is not None:
            conditions.append(self.model.is_active == is_active)
        if is_shared is not None:
            conditions.append(self.model.is_shared == is_shared)

        # Build order by clause
        order_column = getattr(self.model, sort_by, self.model.updated_at)
        order_by = order_column.desc() if sort_order == "desc" else order_column.asc()

        stmt = select(self.model).where(
            and_(*conditions)
        ).offset(skip).limit(limit).order_by(order_by)
        
        result = await db.exec(stmt)
        return result.scalars().all()

    async def get_managed_assets(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        org_id: Optional[uuid.UUID] = None,
        asset_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "updated_at",
        sort_order: str = "desc"
    ) -> Sequence[models.Asset]:
        """Get all assets managed by a specific user, optionally filtered by org."""
        conditions = [self.model.managing_user_id == user_id]
        
        if org_id is not None:
            conditions.append(self.model.org_id == org_id)
        if asset_type is not None:
            conditions.append(self.model.asset_type == asset_type)
        if is_active is not None:
            conditions.append(self.model.is_active == is_active)

        # Build order by clause
        order_column = getattr(self.model, sort_by, self.model.updated_at)
        order_by = order_column.desc() if sort_order == "desc" else order_column.asc()

        stmt = select(self.model).where(
            and_(*conditions)
        ).offset(skip).limit(limit).order_by(order_by)
        
        result = await db.exec(stmt)
        return result.scalars().all()

    async def get_all_org_assets(
        self,
        db: AsyncSession,
        *,
        org_id: uuid.UUID,
        asset_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_shared: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "updated_at",
        sort_order: str = "desc"
    ) -> Sequence[models.Asset]:
        """Get all assets in an organization (for org admins)."""
        conditions = [self.model.org_id == org_id]
        
        if asset_type is not None:
            conditions.append(self.model.asset_type == asset_type)
        if is_active is not None:
            conditions.append(self.model.is_active == is_active)
        if is_shared is not None:
            conditions.append(self.model.is_shared == is_shared)

        # Build order by clause
        order_column = getattr(self.model, sort_by, self.model.updated_at)
        order_by = order_column.desc() if sort_order == "desc" else order_column.asc()

        stmt = select(self.model).where(
            and_(*conditions)
        ).offset(skip).limit(limit).order_by(order_by)
        
        result = await db.exec(stmt)
        return result.scalars().all()

    def _navigate_to_path(self, data: Dict[str, Any], path: List[str], create_missing: bool = False) -> Tuple[Any, str, bool]:
        """
        Navigate through nested data structure to the parent of the target path.
        
        Args:
            data: The data structure to navigate
            path: List of keys/indices to navigate
            create_missing: Whether to create missing intermediate structures
            
        Returns:
            Tuple of (parent_container, last_key, success)
            - parent_container: The dict/list containing the target
            - last_key: The final key/index in the path
            - success: Whether navigation was successful
        """
        if not path:
            return data, "", False
            
        current = data
        for i, part in enumerate(path[:-1]):
            if isinstance(current, dict):
                if part not in current:
                    if create_missing:
                        current[part] = {}
                    else:
                        return None, "", False
                current = current[part]
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    if create_missing:
                        # Extend list if needed
                        while len(current) <= idx:
                            current.append({})
                    elif idx >= len(current):
                        return None, "", False
                    current = current[idx]
                except (ValueError, IndexError):
                    return None, "", False
            else:
                # Can't navigate further
                return None, "", False
                
        return current, path[-1], True
    
    def _apply_add_or_update_operation(self, data: Dict[str, Any], path: List[str], value: Any) -> bool:
        """
        Apply add or update operation to the data.
        
        Args:
            data: The data structure to modify
            path: Path to the target location
            value: Value to set
            
        Returns:
            True if successful, False otherwise
        """
        parent, last_key, success = self._navigate_to_path(data, path, create_missing=True)
        if not success:
            return False
            
        if isinstance(parent, dict):
            parent[last_key] = value
            return True
        elif isinstance(parent, list) and last_key.isdigit():
            idx = int(last_key)
            while len(parent) <= idx:
                parent.append(None)
            parent[idx] = value
            return True
        else:
            return False
    
    def _apply_delete_operation(self, data: Dict[str, Any], path: List[str]) -> bool:
        """
        Apply delete operation to the data.
        
        Args:
            data: The data structure to modify
            path: Path to the target location
            
        Returns:
            True if successful (even if key doesn't exist), False if path is invalid
        """
        parent, last_key, success = self._navigate_to_path(data, path, create_missing=False)
        if not success:
            # Path doesn't exist, which is OK for delete
            return True
            
        try:
            if isinstance(parent, dict) and last_key in parent:
                del parent[last_key]
            elif isinstance(parent, list) and last_key.isdigit():
                idx = int(last_key)
                if 0 <= idx < len(parent):
                    parent.pop(idx)
        except (KeyError, IndexError, TypeError):
            # Key doesn't exist or operation failed - still considered success for delete
            pass
            
        return True

    async def update_app_data_jsonb(
        self,
        db: AsyncSession,
        *,
        asset_id: uuid.UUID,
        operation: str,
        path: Optional[List[str]] = None,
        value: Optional[Any] = None
    ) -> bool:
        """
        Update app_data using JSON operations.
        
        Operations:
        - 'add_or_update': Add a new key or update existing value at path
        - 'delete': Delete a key at path
        - 'replace': Replace entire app_data
        
        Args:
            db: Database session
            asset_id: ID of the asset to update
            operation: Operation to perform (AssetAppDataOperation enum or string)
            path: JSON path for add_or_update/delete operations
            value: Value for add_or_update/replace operations
            
        Returns:
            True if update was successful, False otherwise
        """
        from kiwi_app.workflow_app.schemas import AssetAppDataOperation
        import copy
        
        # Convert string operation to enum if needed
        if isinstance(operation, str):
            operation = AssetAppDataOperation(operation)
        
        # Validate operation parameters
        if operation == AssetAppDataOperation.REPLACE and value is None:
            raise ValueError("Value is required for replace operation")
        elif operation in (AssetAppDataOperation.ADD_OR_UPDATE, AssetAppDataOperation.DELETE) and not path:
            raise ValueError(f"Path is required for {operation.value} operation")
        elif operation == AssetAppDataOperation.ADD_OR_UPDATE and value is None:
            raise ValueError("Value is required for add_or_update operation")
        
        
        try:
            # Ensure we're working with the latest data
            # First, close any existing transaction to ensure we get fresh data
            await db.rollback()
            
            # Set READ COMMITTED isolation level to see committed changes immediately
            await db.exec(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
            
            # Start a new transaction with row-level lock to prevent concurrent modifications
            stmt = select(self.model).where(self.model.id == asset_id).with_for_update()
            result = await db.exec(stmt)
            asset = result.scalars().first()
            if not asset:
                return False
            
            # Get current app_data or initialize empty dict
            current_data = asset.app_data or {}
            
            # Apply the operation
            if operation == AssetAppDataOperation.REPLACE:
                new_data = value
            else:
                # Deep copy for modifications
                new_data = copy.deepcopy(current_data)
                
                if operation == AssetAppDataOperation.ADD_OR_UPDATE:
                    success = self._apply_add_or_update_operation(new_data, path, value)
                    if not success:
                        return False
                elif operation == AssetAppDataOperation.DELETE:
                    success = self._apply_delete_operation(new_data, path)
                    if not success:
                        return False
                else:
                    raise ValueError(f"Invalid operation: {operation}")
            
            # Update the asset with new data
            asset.app_data = new_data
            asset.updated_at = datetime_now_utc()
            
            # Mark the JSONB field as modified to ensure SQLAlchemy tracks the change
            from sqlalchemy.orm import attributes
            attributes.flag_modified(asset, 'app_data')
            
            db.add(asset)
            await db.commit()
            await db.refresh(asset)
            
            return True
        except Exception as e:
            await db.rollback()
            raise e
    
    async def increment_app_data_field(
        self,
        db: AsyncSession,
        *,
        asset_id: uuid.UUID,
        path: List[str],
        increment: Union[int, float] = 1
    ) -> bool:
        """
        Atomically increment a numeric field in app_data.
        
        Args:
            db: Database session
            asset_id: ID of the asset to update
            path: JSON path to the numeric field
            increment: Amount to increment by (default 1), can be int or float
            
        Returns:
            True if update was successful, False otherwise
        """
        from sqlalchemy import text
        
        try:
            await db.rollback()
            
            # Set READ COMMITTED isolation level to see committed changes immediately
            await db.exec(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
            
            # Lock the row for update - this will wait if another transaction has the lock
            stmt = select(self.model).where(self.model.id == asset_id).with_for_update()
            result = await db.exec(stmt)
            asset = result.scalars().first()
            if not asset:
                return False
            
            # Get current app_data
            current_data = asset.app_data or {}
            
            # Navigate to the field and increment
            parent, last_key, success = self._navigate_to_path(current_data, path, create_missing=True)
            if not success or not isinstance(parent, dict):
                return False
            
            # Get current value and increment
            current_val = parent.get(last_key, 0)
            
            # If field doesn't exist or is None, treat as 0
            if current_val is None:
                current_val = 0
            
            # Validate that current value is numeric
            if not isinstance(current_val, (int, float)):
                return False
            
            # Validate increment is numeric
            if not isinstance(increment, (int, float)):
                return False
                
            parent[last_key] = current_val + increment
            
            # Update the asset
            asset.app_data = current_data
            asset.updated_at = datetime_now_utc()
            
            # Mark the JSONB field as modified to ensure SQLAlchemy tracks the change
            from sqlalchemy.orm import attributes
            attributes.flag_modified(asset, 'app_data')
            
            db.add(asset)
            await db.commit()
            await db.refresh(asset)
            
            return True
        except Exception as e:
            await db.rollback()
            raise e


class UserAppResumeMetadataDAO(BaseDAO[models.UserAppResumeMetadata, schemas.UserAppResumeMetadataCreate, schemas.UserAppResumeMetadataUpdate]):
    """DAO for UserAppResumeMetadata operations."""
    
    def __init__(self):
        super().__init__(models.UserAppResumeMetadata)

    async def get_by_filters(
        self,
        db: AsyncSession,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        workflow_name: Optional[str] = None,
        asset_id: Optional[uuid.UUID] = None,
        entity_tag: Optional[str] = None,
        frontend_stage: Optional[str] = None,
        run_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Sequence[models.UserAppResumeMetadata]:
        """Get metadata records by various filters."""
        conditions = [
            self.model.org_id == org_id,
            self.model.user_id == user_id
        ]
        
        if workflow_name is not None:
            conditions.append(self.model.workflow_name == workflow_name)
        if asset_id is not None:
            conditions.append(self.model.asset_id == asset_id)
        if entity_tag is not None:
            conditions.append(self.model.entity_tag == entity_tag)
        if frontend_stage is not None:
            conditions.append(self.model.frontend_stage == frontend_stage)
        if run_id is not None:
            conditions.append(self.model.run_id == run_id)

        stmt = select(self.model).where(
            and_(*conditions)
        ).offset(skip).limit(limit).order_by(self.model.updated_at.desc())
        
        result = await db.exec(stmt)
        return result.scalars().all()

    async def get_by_id_and_user(
        self,
        db: AsyncSession,
        *,
        id: uuid.UUID,
        user_id: uuid.UUID
    ) -> Optional[models.UserAppResumeMetadata]:
        """Get a metadata record by ID ensuring it belongs to the user."""
        stmt = select(self.model).where(
            and_(
                self.model.id == id,
                self.model.user_id == user_id
            )
        )
        result = await db.exec(stmt)
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: schemas.UserAppResumeMetadataCreate,
        org_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> models.UserAppResumeMetadata:
        """Create a new metadata record."""
        db_obj = self.model(
            org_id=org_id,
            user_id=user_id,
            workflow_name=obj_in.workflow_name,
            asset_id=obj_in.asset_id,
            entity_tag=obj_in.entity_tag,
            frontend_stage=obj_in.frontend_stage,
            run_id=obj_in.run_id,
            app_metadata=obj_in.app_metadata
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj
