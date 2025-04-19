"""Customer Data Service for managing versioned and unversioned customer data."""

import json
import uuid
from typing import List, Dict, Any, Optional, Tuple, Union, Type, cast, Set
from datetime import datetime

from fastapi import HTTPException, status
from jsonschema import Draft202012Validator, ValidationError
import jsonschema
from sqlalchemy.ext.asyncio import AsyncSession

from kiwi_app.auth.models import User
from kiwi_app.workflow_app import schemas
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

    TODO: FIXME: detect if document exists anf if its versioned or not before mutating a path!
    """
    
    # Constant for shared document user ID placeholder
    SHARED_DOC_PLACEHOLDER = "_shared_"
    PRIVATE_DOC_PLACEHOLDER = "_private_"
    SYSTEM_DOC_PLACEHOLDER = "_system_"
    
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
    
    def _get_user_id_segment(
        self, 
        is_shared: bool, 
        user: User, 
        on_behalf_of_user_id: Optional[uuid.UUID] = None
    ) -> str:
        """
        Get the user_id segment for document paths.
        
        Args:
            is_shared: Whether this is a shared document
            user: User object for user-specific documents
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            
        Returns:
            The user_id segment (either user ID, on-behalf user ID, or shared placeholder)
        """
        if is_shared:
            return self.SHARED_DOC_PLACEHOLDER
            
        if on_behalf_of_user_id and user.is_superuser:
            return str(on_behalf_of_user_id)
            
        return str(user.id)
    
    def _build_base_path(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
    ) -> List[str]:
        """
        Build the base path for a document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object for user-specific documents
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity (superusers only)
            
        Returns:
            The base path as a list of segments
        """
        # For system entities, use CustomerDataService.SYSTEM_DOC_PLACEHOLDER instead of org_id
        org_id_segment = CustomerDataService.SYSTEM_DOC_PLACEHOLDER if is_system_entity else str(org_id)
        
        # Get user ID segment (handles shared docs and on-behalf actions)
        user_id_segment = self._get_user_id_segment(is_shared, user, on_behalf_of_user_id)
        
        return [org_id_segment, user_id_segment, namespace, docname]
    
    def _get_allowed_prefixes(
        self, 
        org_id: uuid.UUID, 
        user: User, 
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_mutation: bool = False,
        is_system_entity: bool = False,
    ) -> List[List[str]]:
        """
        Get the allowed prefixes for the current user.
        
        Args:
            org_id: Organization ID
            user: User object
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_mutation: Whether this operation modifies data
            is_system_entity: Whether this is a system entity
            
        Returns:
            List of allowed path prefixes
        """
        prefixes: List[List[str]] = []
    

        prefixes.extend([
            [str(org_id), self.SHARED_DOC_PLACEHOLDER],  # Shared docs
            [str(org_id), str(user.id)],                # Their own docs
        ])

        if not is_mutation:
            prefixes.append([CustomerDataService.SYSTEM_DOC_PLACEHOLDER, self.SHARED_DOC_PLACEHOLDER])
            
        # Regular organization prefixes
        if user.is_superuser:
            if on_behalf_of_user_id:
                # Superuser acting on behalf of another user
                prefixes.extend([
                    [str(org_id), str(on_behalf_of_user_id)],    # Specific user docs
                ])
            # System prefixes for superusers regardless of context
            prefixes.extend([
                [CustomerDataService.SYSTEM_DOC_PLACEHOLDER, self.SHARED_DOC_PLACEHOLDER],
                [CustomerDataService.SYSTEM_DOC_PLACEHOLDER, self.PRIVATE_DOC_PLACEHOLDER],
            ])
                
        return prefixes
    
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
        schema_definition: Optional[Dict[str, Any]] = None,
        initial_data: Any = None,
        is_complete: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
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
            schema_definition: Schema definition to use (optional)
            initial_data: Initial document data
            is_complete: Whether the initial data is complete (for validation)
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity (superusers only)
            
        Returns:
            True if document was initialized, False if already exists
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
        
        # Permission checks for acting on behalf of another user or system entities
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        if is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can create system entities"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=True,
            is_system_entity=is_system_entity
        )
        
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
        elif schema_definition:
            schema = schema_definition
        
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
        schema_definition: Optional[Dict[str, Any]] = None,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
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
            schema_definition: Schema definition to use (optional)
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity (superusers only)
            
        Returns:
            True if document was updated successfully
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
        
        # Permission checks for acting on behalf of another user or system entities
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        if is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can modify system entities"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=True,
            is_system_entity=is_system_entity
        )
        
        schema = None
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
        elif schema_definition:
            schema = schema_definition
                
        if schema:
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
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
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
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity
            
        Returns:
            The document data
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
        
        # Permission check for acting on behalf of another user
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=False,
            is_system_entity=is_system_entity
        )
        
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
            # customer_data_logger.warning(f"-------Retrieved document at path {base_path}, version {version}\n\n\n\n{json.dumps(document, indent=4)}\n\n\n\n")
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
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
    ) -> bool:
        """
        Delete a versioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity (superusers only)
            
        Returns:
            True if document was deleted successfully
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
        
        # Permission checks for acting on behalf of another user or system entities
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        if is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can delete system entities"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=True,
            is_system_entity=is_system_entity
        )
        
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
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
    ) -> List[schemas.CustomerDataVersionInfo]:
        """
        List all versions of a versioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity
            
        Returns:
            List of version info objects
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
        
        # Permission check for acting on behalf of another user
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=False,
            is_system_entity=is_system_entity
        )
        
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
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
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
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity (superusers only)
            
        Returns:
            True if version was created successfully
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
        
        # Permission checks for acting on behalf of another user or system entities
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        if is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can modify system entities"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=True,
            is_system_entity=is_system_entity
        )
        
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
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
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
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity (superusers only)
            
        Returns:
            True if active version was set successfully
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
        
        # Permission checks for acting on behalf of another user or system entities
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        if is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can modify system entities"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=True,
            is_system_entity=is_system_entity
        )
        
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
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
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
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity
            
        Returns:
            List of version history items
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
        
        # Permission check for acting on behalf of another user
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=False,
            is_system_entity=is_system_entity
        )
        
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
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
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
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity
            
        Returns:
            The document state at the specified sequence number
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
        
        # Permission check for acting on behalf of another user
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
        
        if is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can modify system entities"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=True,
            is_system_entity=is_system_entity
        )
        
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
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
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
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity (superusers only)
            
        Returns:
            True if document was restored successfully
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
        
        # Permission checks for acting on behalf of another user or system entities
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        if is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can modify system entities"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=True,
            is_system_entity=is_system_entity
        )
        
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
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the schema of a versioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity
            
        Returns:
            The document schema or None if not found
        """
        if not self.versioned_mongo_client:
            raise ValueError("Versioned MongoDB client is required")
        
        # Permission check for acting on behalf of another user
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=False,
            is_system_entity=is_system_entity
        )
        
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
        schema_definition: Optional[Dict[str, Any]] = None,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
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
            schema_definition: Schema definition to validate against (optional)
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity (superusers only)
            
        Returns:
            Tuple of (document_id, is_created)
        """
        # Permission checks for acting on behalf of another user or system entities
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        if is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can create or update system entities"
            )
        
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=True,
            is_system_entity=is_system_entity
        )
        
        schema = None
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
        elif schema_definition:
            schema = schema_definition
        if schema:
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
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
    ) -> Any:
        """
        Get an unversioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity
            
        Returns:
            The document data
        """
        # Permission check for acting on behalf of another user
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=False,
            is_system_entity=is_system_entity
        )
        
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
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
    ) -> bool:
        """
        Delete an unversioned document.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity (superusers only)
            
        Returns:
            True if document was deleted successfully
        """
        # Permission checks for acting on behalf of another user or system entities
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        if is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can delete system entities"
            )
            
        base_path = self._build_base_path(
            org_id=org_id, 
            namespace=namespace, 
            docname=docname, 
            is_shared=is_shared, 
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id, 
            user=user, 
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=True,
            is_system_entity=is_system_entity
        )
        
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
    
    async def get_document_metadata(
        self,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        is_system_entity: bool = False,
    ) -> schemas.CustomerDocumentMetadata:
        """
        Retrieve document metadata at the specified path.
        
        Args:
            org_id: Organization ID
            namespace: Document namespace
            docname: Document name
            is_shared: Whether this is a shared document
            user: User object
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            is_system_entity: Whether this is a system entity (superusers only)
            
        Returns:
            Document metadata including versioning information
            
        Raises:
            HTTPException: If document not found or access denied
        """
        # Permission checks
        if on_behalf_of_user_id and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        if is_system_entity and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can access system entities"
            )
        
        # Build the document path
        base_path = self._build_base_path(
            org_id=org_id,
            namespace=namespace,
            docname=docname,
            is_shared=is_shared,
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=is_system_entity
        )
        
        # Get allowed prefixes for permission checking
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id,
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=False,  # This is a read operation
            is_system_entity=is_system_entity
        )
        
        try:
            # Include the document type field to determine if it's versioned
            include_fields = [self.mongo_client.DOC_TYPE_KEY]

            # print(f"Fetching document at path: {base_path}")
            # print(f"Allowed prefixes: {allowed_prefixes}")
            # print(f"Include fields: {include_fields}")
            
            # Fetch the document
            document = await self.versioned_mongo_client.client.fetch_object(
                path=base_path,
                allowed_prefixes=allowed_prefixes,
                include_fields=include_fields
            )

            # print(f"Document: {document}")
            
            # Check if document exists
            if not document:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document '{namespace}/{docname}' not found"
                )
            
            # Determine if document is versioned
            is_versioned = document.get(self.mongo_client.DOC_TYPE_KEY) == self.mongo_client.DOC_TYPE_VERSIONED
            # customer_data_logger.warning(f"-------Document at path {base_path} is versioned: {is_versioned} ---> **** DOC_TYPE_KEY *** : {document.get(self.mongo_client.DOC_TYPE_KEY)}")
            
            # Extract path components
            org_id_str = str(org_id) if not is_system_entity else CustomerDataService.SYSTEM_DOC_PLACEHOLDER
            user_id_str = self.SHARED_DOC_PLACEHOLDER if is_shared else (
                str(on_behalf_of_user_id) if on_behalf_of_user_id and user.is_superuser else str(user.id)
            )
            
            # Create and return metadata
            return schemas.CustomerDocumentMetadata(
                org_id=uuid.UUID(org_id_str) if not is_system_entity else None,
                user_id_or_shared_placeholder=user_id_str,
                namespace=namespace,
                docname=docname,
                is_versioned=is_versioned,
                is_shared=is_shared,
                is_system_entity=is_system_entity,
            )
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            customer_data_logger.error(f"Error fetching document at path {base_path}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve document: {str(e)}"
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
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        include_system_entities: bool = False,
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
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            include_system_entities: Whether to include system entities (superusers only)
            
        Returns:
            List of document metadata
        """
        if not include_shared and not include_user_specific and not include_system_entities:
            customer_data_logger.info("No document types included, returning empty list")
            return []
         
        # Permission checks for acting on behalf of another user or system entities
        if on_behalf_of_user_id and not user.is_superuser:
            customer_data_logger.warning(f"Permission denied: Non-superuser {user.id} attempted to act on behalf of {on_behalf_of_user_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
            
        if include_system_entities and not user.is_superuser:
            customer_data_logger.warning(f"Permission denied: Non-superuser {user.id} attempted to list system entities")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can list all system entities"
            )
        
        customer_data_logger.debug(f"Getting allowed prefixes for org_id={org_id}, user={user.id}, on_behalf_of_user_id={on_behalf_of_user_id}")
        # Get allowed prefixes from our helper method
        allowed_prefixes = self._get_allowed_prefixes(
            org_id=org_id,
            user=user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_mutation=False,  # Listing is not a mutation operation
            is_system_entity=False  # Basic prefixes, specific system patterns added below
        )
        customer_data_logger.debug(f"Allowed prefixes: {allowed_prefixes}")
        
        # Build patterns to search for
        patterns = []
        
        # Organization patterns
        namespace_filter_pattern = namespace_filter if namespace_filter else "*"
        customer_data_logger.debug(f"Namespace filter pattern: {namespace_filter_pattern}")
        
        if include_shared or include_user_specific:
            if include_shared:
                customer_data_logger.debug(f"Including shared documents for org_id={org_id}")
                patterns.append([str(org_id), self.SHARED_DOC_PLACEHOLDER, namespace_filter_pattern, "*"])
            if include_user_specific:
                user_id = str(on_behalf_of_user_id) if on_behalf_of_user_id and user.is_superuser else str(user.id)
                customer_data_logger.debug(f"Including user-specific documents for user_id={user_id}")
                patterns.append([str(org_id), user_id, namespace_filter_pattern, "*"])
        
        # System patterns
        if include_system_entities or (not user.is_superuser):  # Regular users can still see shared system docs
            customer_data_logger.debug("Including shared system documents")
            patterns.append([CustomerDataService.SYSTEM_DOC_PLACEHOLDER, self.SHARED_DOC_PLACEHOLDER, namespace_filter_pattern, "*"])
            # Only superusers can access private system docs
            if user.is_superuser and include_system_entities:
                customer_data_logger.debug("Including private system documents (superuser only)")
                patterns.append([CustomerDataService.SYSTEM_DOC_PLACEHOLDER, self.PRIVATE_DOC_PLACEHOLDER, namespace_filter_pattern, "*"])
        
        try:
            customer_data_logger.debug(f"Beginning document search with {len(patterns)} patterns")
            # Process each pattern and combine results
            all_docs = {}
            customer_data_logger.debug(f"Patterns: {patterns}")
            for pattern in patterns:
                customer_data_logger.debug(f"Processing pattern: {pattern}")
                docs = await self.versioned_mongo_client.client.search_objects(
                    # NOTE: we only wanna fetch all docs where the version/sequence no. segments are unset!
                    key_pattern=pattern + [None] * len(self.versioned_mongo_client.VERSION_SEGMENT_NAMES),
                    allowed_prefixes=allowed_prefixes,
                    include_fields=self.versioned_mongo_client.segment_names + [self.mongo_client.DOC_TYPE_KEY],
                )
                customer_data_logger.debug(f"Found {len(docs)} documents for pattern: {pattern}")
                all_docs.update(
                    {tuple(self.versioned_mongo_client.client._segments_to_path(doc)): doc for doc in docs}
                )
            
            customer_data_logger.debug(f"Total unique documents found: {len(all_docs)}")
            
            # Process results into metadata objects
            result = []
            for doc_path, _doc_metadata in all_docs.items():
                # Skip if not a list (should not happen)
                if not isinstance(doc_path, (list, tuple)) or len(doc_path) != 4:
                    customer_data_logger.warning(f"Skipping invalid doc_path: {doc_path}")
                    continue
                    
                # Extract path components
                org_id_str, user_id_str, namespace, docname = doc_path
                
                # Determine if shared and system
                is_shared = user_id_str == self.SHARED_DOC_PLACEHOLDER
                is_system = org_id_str == CustomerDataService.SYSTEM_DOC_PLACEHOLDER
                
                # Skip system entities if not requested
                if is_system and not include_system_entities and not is_shared:
                    customer_data_logger.debug(f"Skipping system entity not requested: {doc_path}")
                    continue
                
                is_versioned = _doc_metadata.get(self.mongo_client.DOC_TYPE_KEY) == self.mongo_client.DOC_TYPE_VERSIONED
                
                # Create metadata object
                metadata = schemas.CustomerDocumentMetadata(
                    org_id=uuid.UUID(org_id_str) if not is_system else None,
                    user_id_or_shared_placeholder=user_id_str,
                    namespace=namespace,
                    docname=docname,
                    is_versioned=is_versioned,
                    is_shared=is_shared,
                    is_system_entity=is_system,
                )
                
                result.append(metadata)
            
            customer_data_logger.debug(f"Raw result count: {len(result)}")
            
            # Remove duplicates (in case the same document matched multiple patterns)
            unique_result = []
            seen_paths = set()
            
            for metadata in result:
                path_key = f"{metadata.org_id or CustomerDataService.SYSTEM_DOC_PLACEHOLDER}/{metadata.user_id_or_shared_placeholder}/{metadata.namespace}/{metadata.docname}"
                if path_key not in seen_paths:
                    seen_paths.add(path_key)
                    unique_result.append(metadata)
                else:
                    customer_data_logger.debug(f"Skipping duplicate: {path_key}")
            
            customer_data_logger.debug(f"Unique result count: {len(unique_result)}")
            
            # Apply pagination
            paginated_result = unique_result[skip:skip + limit]
            customer_data_logger.debug(f"Paginated result count: {len(paginated_result)} (skip={skip}, limit={limit})")
            return paginated_result
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list documents: {str(e)}",
            )
