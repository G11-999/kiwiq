"""CRUD (Create, Read, Update, Delete) operations for Workflow Service models.

This module provides Data Access Objects (DAOs) for interacting with the 
database models defined in models.py, encapsulating the database query logic.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Type, TypeVar, Generic, Any, Dict, Sequence, Union

from sqlalchemy import select, update, delete, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from pydantic import BaseModel as PydanticBaseModel

from kiwi_app.auth.models import User
from kiwi_app.workflow_app import models, schemas
from kiwi_app.workflow_app.constants import WorkflowRunStatus, NotificationType, HITLJobStatus, LaunchStatus, SchemaType
from kiwi_app.auth.crud_util import build_load_options
from global_utils import datetime_now_utc

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
        result = await db.execute(stmt)
        return result.scalars().first()

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
        result = await db.execute(stmt)
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
        result = await db.execute(stmt)
        return result.scalars().first()

    async def get_latest_prod_version(self, db: AsyncSession, *, name: str) -> Optional[models.NodeTemplate]:
        """Get the latest production-ready node template by name."""
        stmt = select(self.model).where(
            self.model.name == name,
            self.model.launch_status == LaunchStatus.PRODUCTION
        ).order_by(self.model.created_at.desc())
        result = await db.execute(stmt)
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
        result = await db.execute(stmt)
        return result.scalars().all()

# --- Workflow DAO --- #

class WorkflowDAO(BaseDAO[models.Workflow, schemas.WorkflowCreate, schemas.WorkflowUpdate]):
    """DAO for Workflow models."""
    def __init__(self):
        super().__init__(models.Workflow)

    async def get_by_name(self, db: AsyncSession, *, name: str, owner_org_id: uuid.UUID) -> Optional[models.Workflow]:
        """Get a workflow by name within a specific organization."""
        stmt = select(self.model).where(self.model.name == name, self.model.owner_org_id == owner_org_id)
        result = await db.execute(stmt)
        return result.scalars().first()
    
    async def get_by_id_and_org_or_public(self, db: AsyncSession, *, user: User, workflow_id: uuid.UUID, org_id: uuid.UUID) -> Optional[models.Workflow]:
        """Get a workflow by ID, ensuring it belongs to the specified organization or is public."""
        or_clause = or_(
                and_(self.model.owner_org_id == org_id, self.model.owner_org_id != None),
                self.model.is_public == True,
            )
        if user.is_superuser:
            or_clause = or_(or_clause, self.model.owner_org_id == None)

        stmt = select(self.model).where(
            self.model.id == workflow_id,
            or_clause
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def get_by_id_and_org(self, db: AsyncSession, *, workflow_id: uuid.UUID, org_id: uuid.UUID) -> Optional[models.Workflow]:
        """Get a workflow by ID, ensuring it belongs to the specified organization."""
        stmt = select(self.model).where(
            self.model.id == workflow_id, self.model.owner_org_id == org_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def get_multi_by_org(
        self, db: AsyncSession, *,
        owner_org_id: uuid.UUID,
        include_public: bool = True,
        skip: int = 0,
        limit: int = 100
        ) -> Sequence[models.Workflow]:
        """Get multiple workflows for a specific organization."""
        stmt = select(self.model)
        if include_public:
            stmt = stmt.where(
                or_(
                    self.model.owner_org_id == owner_org_id,
                    self.model.is_public == True
                )
            )
        else:
            stmt = stmt.where(self.model.owner_org_id == owner_org_id)
        
        stmt = stmt.order_by(self.model.updated_at.desc()).offset(skip).limit(limit)
        result = await db.execute(stmt)
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
        result = await db.execute(stmt)
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        *,
        workflow_id: uuid.UUID,
        owner_org_id: uuid.UUID,
        triggered_by_user_id: Optional[uuid.UUID] = None,
        inputs: Optional[Dict[str, Any]] = None,
        thread_id: Optional[uuid.UUID] = None,
        status: WorkflowRunStatus = WorkflowRunStatus.SCHEDULED
    ) -> models.WorkflowRun:
        """Creates a new workflow run record."""
        db_obj = self.model(
            workflow_id=workflow_id,
            owner_org_id=owner_org_id,
            triggered_by_user_id=triggered_by_user_id,
            inputs=inputs,
            status=status,
            thread_id=thread_id
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
        result = await db.execute(stmt)
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
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0

    def _build_run_filters(self, filters: Optional[Dict[str, Any]]) -> List:
        conditions = []
        if not filters:
            return conditions

        if filters.get("workflow_id"):
            conditions.append(self.model.workflow_id == filters["workflow_id"])
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

        result = await db.execute(stmt)
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
                self.model.is_system_template == False
            )
            result_org = await db.execute(stmt_org)
            template = result_org.scalars().first()
            if template:
                return template
        
        stmt_sys = select(self.model).where(
            self.model.name == name,
            self.model.version == version,
            self.model.is_system_template == True
        )
        result_sys = await db.execute(stmt_sys)
        return result_sys.scalars().first()

    async def get_multi_by_org(
        self, db: AsyncSession, *, owner_org_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[TemplateModelType]:
        """Retrieves templates owned by a specific organization (non-system)."""
        stmt = select(self.model).where(
            self.model.owner_org_id == owner_org_id,
            self.model.is_system_template == False
        ).order_by(self.model.name, self.model.version).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_multi_system(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> Sequence[TemplateModelType]:
        """Retrieves system templates."""
        stmt = select(self.model).where(
            self.model.is_system_template == True
        ).order_by(self.model.name, self.model.version).offset(skip).limit(limit)
        result = await db.execute(stmt)
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

        db_obj = self.model(
            **create_data,
            owner_org_id=owner_org_id,
            is_system_template=False
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
            self.model.is_system_template == False
        )
        result = await db.execute(stmt)
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
        Prevents modification of `owner_org_id` and `is_system_template`.
        """
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            try:
                update_data = obj_in.model_dump(exclude_unset=True)
            except AttributeError:
                update_data = obj_in.dict(exclude_unset=True)

        update_data.pop('owner_org_id', None)
        update_data.pop('is_system_template', None)
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
        result = await db.execute(stmt)
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
        result = await db.execute(stmt)
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
        stmt = select(self.model).where(
            self.model.user_id == user_id,
            self.model.org_id == org_id
        )

        if is_read is not None:
            stmt = stmt.where(self.model.is_read == is_read)
            
        sort_column = getattr(self.model, sort_by, self.model.created_at)
        if sort_order.lower() == "asc":
            stmt = stmt.order_by(sort_column.asc())
        else:
            stmt = stmt.order_by(sort_column.desc())

        stmt = stmt.offset(skip).limit(limit)

        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_by_run_and_user(self, db: AsyncSession, *, related_run_id: uuid.UUID, user_id: uuid.UUID) -> Sequence[models.UserNotification]:
        """Retrieves notifications for a specific run belonging to a user."""
        stmt = select(self.model).where(
            self.model.related_run_id == related_run_id,
            self.model.user_id == user_id
        ).order_by(self.model.created_at.desc())
        result = await db.execute(stmt)
        return result.scalars().all()

    async def count_unread_by_user(self, db: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID) -> int:
        """Counts unread notifications for a user in an organization."""
        stmt = select(func.count(self.model.id)).select_from(self.model).where(
            self.model.user_id == user_id,
            self.model.org_id == org_id,
            self.model.is_read == False
        )
        result = await db.execute(stmt)
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
        result = await db.execute(stmt)
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
        result = await db.execute(stmt)
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

        result = await db.execute(stmt)
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

