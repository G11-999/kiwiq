"""Customer Data Service for managing versioned and unversioned customer data."""

import uuid
from typing import List, Dict, Any, Optional, Tuple, Union, Type, cast
from datetime import datetime

from fastapi import HTTPException, status
from jsonschema import Draft202012Validator, ValidationError
import jsonschema
from sqlalchemy.ext.asyncio import AsyncSession

from kiwi_app.auth.models import User
from kiwi_app.workflow_app import schemas, services, models
from kiwi_app.workflow_app import crud
from kiwi_app.workflow_app.constants import SchemaType
from mongo_client import AsyncMongoDBClient, AsyncMongoVersionedClient
from kiwi_app.settings import settings
from kiwi_app.utils import get_kiwi_logger

customer_data_logger = get_kiwi_logger(name="kiwi_app.service_customer_data")

class CustomerDataService:
    """
    Service for managing customer data stored in MongoDB.
    
    Supports both versioned and unversioned documents with:
    - Organization-shared data
    - User-specific data within organizations
    - Schema validation using templates from the schema template service
    - Version control for documents (only with versioned documents)
    """
    
    # Constant for shared document user ID placeholder
    SHARED_DOC_PLACEHOLDER = "_shared_"
    
    def __init__(
        self,
        mongo_client: AsyncMongoDBClient,
        versioned_mongo_client: Optional[AsyncMongoVersionedClient] = None,
        schema_template_dao: Optional[crud.SchemaTemplateDAO] = None,
    ):
        """
        Initialize the CustomerDataService.
        
        Args:
            mongo_client: MongoDB client for unversioned documents
            versioned_mongo_client: MongoDB client for versioned documents (optional)
            workflow_service: WorkflowService for schema template lookup (optional)
        """
        self.mongo_client = mongo_client
        self.versioned_mongo_client = versioned_mongo_client
        self.schema_template_dao = schema_template_dao
        
        # Verify segment names match expectations
        expected_segments = ["org_id", "user_id", "namespace", "docname"]
        if not settings.MONGO_CUSTOMER_SEGMENTS == expected_segments:
            raise ValueError(
                f"MongoDB customer segments must be {expected_segments}, "
                f"got {settings.MONGO_CUSTOMER_SEGMENTS}"
            )
    
    def _get_user_id_segment(self, is_shared: bool, user: User) -> str:
        """
        Get the user_id segment for document paths.
        
        Args:
            is_shared: Whether this is a shared document
            user: User object for user-specific documents
            
        Returns:
            The user_id segment (either user ID or shared placeholder)
        """
        if is_shared:
            return self.SHARED_DOC_PLACEHOLDER
        return str(user.id)
    
    def _build_base_path(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
    ) -> List[str]:
        """
        Build the base path for a document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object for user-specific documents
            
        Returns:
            The base path as a list of segments
        """
        user_id_segment = self._get_user_id_segment(is_shared, user)
        return [str(org_id), user_id_segment, namespace, docname]
    
    def _get_allowed_prefixes(self, org_id: uuid.UUID, user: User) -> List[List[str]]:
        """
        Get the allowed prefixes for the current user.
        
        Args:
            org_id: Organization ID
            user: User object
            
        Returns:
            List of allowed path prefixes
        """
        # User can access:
        # 1. Organization shared data: org_id/shared/*
        # 2. User-specific data: org_id/user_id/*
        return [
            [str(org_id), self.SHARED_DOC_PLACEHOLDER],  # Shared docs
            [str(org_id), str(user.id)],  # User-specific docs
        ]
    
    async def _get_schema_from_template(
        self,
        db: AsyncSession,
        template_name: str,
        template_version: Optional[str],
        org_id: uuid.UUID,
        user: User,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a schema from a schema template.
        
        Args:
            db: Database session
            template_name: Schema template name
            template_version: Schema template version (optional)
            org_id: Organization ID
            user: User object
            
        Returns:
            Schema definition from the template or None if not found
        """
        if not self.schema_template_dao:
            raise ValueError("`schema_template_dao` is required for schema template lookup")
        
        # TODO: REFACTOR to not use workflow service, instead use DAO here! since workflow service is bulky and not used as much!
        
        # Use the generic search method from the DAO
        results = await self.schema_template_dao.search_by_name_version(
            db=db,
            name=template_name,
            version=template_version,
            version_field="version",
            owner_org_id=org_id,
            include_public=True,
            include_system_entities=False,
            include_public_system_entities=True,
            is_superuser=user.is_superuser
        )
        
        templates = list(results)

        # customer_data_logger.info(f" CUSTOMER DATA SERVICE: Found {len(templates)} templates")
        if not templates:
            return None
            
        # If no specific version provided, use the first one returned (likely the latest)
        # TODO: FIXME: prioritize fetching owned templates over system templates!
        template = templates[0]
        
        if template.schema_type != SchemaType.JSON_SCHEMA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Schema template '{template_name}' is not a JSON Schema",
            )
            
        return template.schema_definition
    
    # --- Versioned Document Methods --- #
    
    async def initialize_versioned_document(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
        initial_version: str = "default",
        schema_template_name: Optional[str] = None,
        schema_template_version: Optional[str] = None,
        initial_data: Any = None,
        is_complete: bool = False,
    ) -> bool:
        """
        Initialize a new versioned document.
        
        Args:
            db: Database session
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether to create a shared document
            user: User object
            initial_version: Name for the initial version (default: "default")
            schema_template_name: Name of schema template to use (optional)
            schema_template_version: Version of schema template (optional)
            initial_data: Initial document data
            is_complete: Whether the initial data is complete (for validation)
            
        Returns:
            True if document was initialized, False if already exists
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
            
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        # Get schema from template if provided
        schema = None
        if schema_template_name:
            schema = await self._get_schema_from_template(
                db, schema_template_name, schema_template_version, org_id, user
            )
            if not schema:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Schema template '{schema_template_name}' not found",
                )
        
        # Set initial data to empty object if None
        if initial_data is None:
            initial_data = {}
            
        # Initialize document with schema if provided
        try:
            result = await self.versioned_mongo_client.initialize_document(
                base_path=base_path,
                initial_version=initial_version,
                schema=schema,
                allowed_prefixes=allowed_prefixes,
            )

            if not result:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Document '{namespace}/{docname}' already exists for org {org_id}"
                )
            
            # Update with initial data if initialization was successful
            if result and initial_data:
                await self.versioned_mongo_client.update_document(
                    base_path=base_path,
                    data=initial_data,
                    version=initial_version,
                    is_complete=is_complete,
                    allowed_prefixes=allowed_prefixes,
                )
                
            return result
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initialize document: {str(e)}",
            )
    
    async def update_versioned_document(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
        data: Any,
        version: Optional[str] = None,
        is_complete: Optional[bool] = None,
        schema_template_name: Optional[str] = None,
        schema_template_version: Optional[str] = None,
    ) -> bool:
        """
        Update a versioned document.
        
        Args:
            db: Database session
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            data: Data to update the document with
            version: Specific version to update (optional)
            is_complete: Whether the document is complete after update (optional)
            schema_template_name: Name of schema template to update with (optional)
            schema_template_version: Version of schema template (optional)
            
        Returns:
            True if document was updated successfully
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
            
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        # Update schema if template provided
        if schema_template_name:
            schema = await self._get_schema_from_template(
                db, schema_template_name, schema_template_version, org_id, user
            )
            if not schema:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Schema template '{schema_template_name}' not found",
                )
                
            await self.versioned_mongo_client.update_schema(
                base_path=base_path,
                schema=schema,
                allowed_prefixes=allowed_prefixes,
            )
        
        # Update document
        try:
            await self.versioned_mongo_client.update_document(
                base_path=base_path,
                data=data,
                version=version,
                is_complete=is_complete,
                allowed_prefixes=allowed_prefixes,
            )
            return True
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update document: {str(e)}",
            )
    
    async def get_versioned_document(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
        version: Optional[str] = None,
    ) -> Any:
        """
        Get a versioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            version: Specific version to retrieve (optional)
            
        Returns:
            The document data
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
            
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        try:
            document = await self.versioned_mongo_client.get_document(
                base_path=base_path,
                version=version,
                allowed_prefixes=allowed_prefixes,
            )
            
            if document is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document '{namespace}/{docname}' not found",
                )
                
            return document
        except Exception as e:
            # Check if this is a 404 we already raised
            if isinstance(e, HTTPException):
                raise e
                
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get document: {str(e)}",
            )
    
    async def delete_versioned_document(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
    ) -> bool:
        """
        Delete a versioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            
        Returns:
            True if document was deleted successfully
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
            
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        try:
            result = await self.versioned_mongo_client.delete_document(
                base_path=base_path,
                allowed_prefixes=allowed_prefixes,
            )
            
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document '{namespace}/{docname}' not found",
                )
                
            return result
        except Exception as e:
            # Check if this is a 404 we already raised
            if isinstance(e, HTTPException):
                raise e
                
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete document: {str(e)}",
            )
    
    async def list_versioned_document_versions(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
    ) -> List[schemas.CustomerDataVersionInfo]:
        """
        List all versions of a versioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            
        Returns:
            List of version info objects
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
            
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        try:
            versions = await self.versioned_mongo_client.list_versions(
                base_path=base_path,
                allowed_prefixes=allowed_prefixes,
            )
            
            if versions is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document '{namespace}/{docname}' not found",
                )
                
            # Convert to schema objects
            return [schemas.CustomerDataVersionInfo(**version) for version in versions]
        except Exception as e:
            # Check if this is a 404 we already raised
            if isinstance(e, HTTPException):
                raise e
                
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list versions: {str(e)}",
            )
    
    async def create_versioned_document_version(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
        new_version: str,
        from_version: Optional[str] = None,
    ) -> bool:
        """
        Create a new version of a versioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            new_version: Name for the new version
            from_version: Version to branch from (optional)
            
        Returns:
            True if version was created successfully
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
            
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        try:
            await self.versioned_mongo_client.create_version(
                base_path=base_path,
                new_version=new_version,
                from_version=from_version,
                allowed_prefixes=allowed_prefixes,
            )
            return True
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create version: {str(e)}",
            )
    
    async def set_active_version(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
        version: str,
    ) -> bool:
        """
        Set the active version of a versioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            version: Version to set as active
            
        Returns:
            True if active version was set successfully
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
            
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        try:
            await self.versioned_mongo_client.set_active_version(
                base_path=base_path,
                version=version,
                allowed_prefixes=allowed_prefixes,
            )
            return True
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to set active version: {str(e)}",
            )
    
    async def get_version_history(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
        version: Optional[str] = None,
        limit: int = 100,
    ) -> List[schemas.CustomerDataVersionHistoryItem]:
        """
        Get the history of a versioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            version: Specific version to get history for (optional)
            limit: Maximum number of history entries to return
            
        Returns:
            List of version history items
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
            
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        try:
            history = await self.versioned_mongo_client.get_version_history(
                base_path=base_path,
                version=version,
                limit=limit,
                allowed_prefixes=allowed_prefixes,
            )
            
            if history is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document '{namespace}/{docname}' not found",
                )
                
            # Convert to schema objects
            return [schemas.CustomerDataVersionHistoryItem(**item) for item in history]
        except Exception as e:
            # Check if this is a 404 we already raised
            if isinstance(e, HTTPException):
                raise e
                
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get version history: {str(e)}",
            )
    
    async def preview_restore(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
        sequence: int,
        version: Optional[str] = None,
    ) -> Any:
        """
        Preview restoring a versioned document to a previous state.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            sequence: Sequence number to restore to
            version: Specific version to restore (optional)
            
        Returns:
            The document state at the specified sequence number
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
            
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        try:
            data = await self.versioned_mongo_client.preview_restore(
                base_path=base_path,
                sequence=sequence,
                version=version,
                allowed_prefixes=allowed_prefixes,
            )
            
            if data is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document '{namespace}/{docname}' or sequence {sequence} not found",
                )
                
            return data
        except Exception as e:
            # Check if this is a 404 we already raised
            if isinstance(e, HTTPException):
                raise e
                
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to preview restore: {str(e)}",
            )
    
    async def restore_document(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
        sequence: int,
        version: Optional[str] = None,
    ) -> bool:
        """
        Restore a versioned document to a previous state.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            sequence: Sequence number to restore to
            version: Specific version to restore (optional)
            
        Returns:
            True if document was restored successfully
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
            
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        try:
            result = await self.versioned_mongo_client.restore(
                base_path=base_path,
                sequence=sequence,
                version=version,
                allowed_prefixes=allowed_prefixes,
            )
            
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document '{namespace}/{docname}' or sequence {sequence} not found",
                )
                
            return result
        except Exception as e:
            # Check if this is a 404 we already raised
            if isinstance(e, HTTPException):
                raise e
                
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to restore document: {str(e)}",
            )
    
    async def get_versioned_document_schema(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the schema of a versioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            
        Returns:
            The document schema or None if not found
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
            
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        try:
            schema = await self.versioned_mongo_client.get_schema(
                base_path=base_path,
                allowed_prefixes=allowed_prefixes,
            )
            
            return schema
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get schema: {str(e)}",
            )
    
    # --- Unversioned Document Methods --- #
    
    async def create_or_update_unversioned_document(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
        data: Any,
        schema_template_name: Optional[str] = None,
        schema_template_version: Optional[str] = None,
    ) -> Tuple[str, bool]:
        """
        Create or update an unversioned document.
        
        Args:
            db: Database session
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            data: Document data
            schema_template_name: Name of schema template to validate against (optional)
            schema_template_version: Version of schema template (optional)
            
        Returns:
            Tuple of (document_id, is_created)
        """
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        # Validate against schema if provided
        if schema_template_name:
            schema = await self._get_schema_from_template(
                db, schema_template_name, schema_template_version, org_id, user
            )
            if not schema:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Schema template '{schema_template_name}' not found",
                )
                
            # TODO: Implement schema validation for unversioned documents
            # This requires custom validation since unversioned client doesn't have built-in schema validation
            # For now, we'll skip this and just store the data
            try:
                jsonschema.validate(instance=data, schema=schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
            except ValidationError as e:
                error_path = "/".join(str(part) for part in e.path)
                error_msg = f"{error_path}: {e.message}" if error_path else e.message
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"HITL input validation failed: {error_msg}"
                )
            
        try:
            result = await self.mongo_client.create_or_update_object(
                path=base_path,
                data=data,
                allowed_prefixes=allowed_prefixes,
                update_subfields=True,
            )
            
            return result
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create or update document: {str(e)}",
            )
    
    async def get_unversioned_document(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
    ) -> Any:
        """
        Get an unversioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            
        Returns:
            The document data
        """
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        try:
            document = await self.mongo_client.fetch_object(
                path=base_path,
                allowed_prefixes=allowed_prefixes,
            )
            
            if document is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document '{namespace}/{docname}' not found",
                )
                
            return document.get("data", {})
        except Exception as e:
            # Check if this is a 404 we already raised
            if isinstance(e, HTTPException):
                raise e
                
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get document: {str(e)}",
            )
    
    async def delete_unversioned_document(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
    ) -> bool:
        """
        Delete an unversioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            
        Returns:
            True if document was deleted successfully
        """
        base_path = self._build_base_path(org_id, namespace, docname, is_shared, user)
        allowed_prefixes = self._get_allowed_prefixes(org_id, user)
        
        try:
            result = await self.mongo_client.delete_object(
                path=base_path,
                allowed_prefixes=allowed_prefixes,
            )
            
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document '{namespace}/{docname}' not found",
                )
                
            return result
        except Exception as e:
            # Check if this is a 404 we already raised
            if isinstance(e, HTTPException):
                raise e
                
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete document: {str(e)}",
            )
    
    # --- List Documents --- #
    
    async def list_documents(
        self,
        org_id: uuid.UUID,
        user: User,
        namespace_filter: Optional[str] = None,
        include_shared: bool = True,
        include_user_specific: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> List[schemas.CustomerDocumentMetadata]:
        """
        List documents accessible to the user.
        
        Args:
            org_id: Organization ID
            user: User object
            namespace_filter: Filter by namespace (optional)
            include_shared: Include shared documents
            include_user_specific: Include user-specific documents
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            
        Returns:
            List of document metadata
        """
        if not include_shared and not include_user_specific:
            return []
            
        allowed_prefixes = []
        if include_shared:
            allowed_prefixes.append([str(org_id), self.SHARED_DOC_PLACEHOLDER])
        if include_user_specific:
            allowed_prefixes.append([str(org_id), str(user.id)])
            
        # Build pattern based on namespace filter
        if namespace_filter:
            # Filter by specific namespace
            pattern = [str(org_id), "*", namespace_filter, "*"]
        else:
            # List all documents
            pattern = [str(org_id), "*", "*", "*"]
            
        try:
            # Fetch both versioned and unversioned documents
            # Approach: First query the base mongo client to get all document paths
            docs = await self.mongo_client.list_objects(
                pattern=pattern,
                allowed_prefixes=allowed_prefixes,
                include_data=False,
            )
            
            # Process results into metadata objects
            result = []
            for doc_path in docs:
                # Skip if not a list (should not happen)
                if not isinstance(doc_path, list) or len(doc_path) != 4:
                    continue
                    
                # Extract path components
                org_id_str, user_id_str, namespace, docname = doc_path
                
                # Determine if shared
                is_shared = user_id_str == self.SHARED_DOC_PLACEHOLDER
                
                # We don't know if it's versioned yet - need to check if a metadata document exists
                # For simplicity, let's assume it's versioned if we can use a versioned client
                # A more robust approach would inspect the document structure
                is_versioned = self.versioned_mongo_client is not None
                
                # Create metadata object
                metadata = schemas.CustomerDocumentMetadata(
                    org_id=uuid.UUID(org_id_str),
                    user_id_or_shared_placeholder=user_id_str,
                    namespace=namespace,
                    docname=docname,
                    is_versioned=is_versioned,
                    is_shared=is_shared,
                )
                
                result.append(metadata)
                
            # Apply pagination
            paginated_result = result[skip:skip + limit]
            
            return paginated_result
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list documents: {str(e)}",
            )
