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

        # if not is_mutation:
        #     prefixes.append([CustomerDataService.SYSTEM_DOC_PLACEHOLDER, self.SHARED_DOC_PLACEHOLDER])
            
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
            success = await self.versioned_mongo_client.update_document(
                base_path=base_path,
                data=data,
                version=version,
                is_complete=is_complete,
                allowed_prefixes=allowed_prefixes,
            )
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document '{namespace}/{docname}' not found",
                )
            return success
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{namespace}/{docname}' not found",
            ) from e
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
    
    async def upsert_versioned_document(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        namespace: str,
        docname: str,
        is_shared: bool,
        user: User,
        data: Any,
        version: Optional[str] = None,
        from_version: Optional[str] = None, # Used only if creating a new version during upsert
        is_complete: Optional[bool] = None,
        schema_template_name: Optional[str] = None,
        schema_template_version: Optional[str] = None,
        schema_definition: Optional[Dict[str, Any]] = None,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        set_active_version: bool = True,
        is_system_entity: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Upserts a versioned document: updates if exists, initializes if not.
        Handles creating a specific version if the update targets a non-existent one.

        Args:
            db: Database session.
            org_id: Organization ID.
            namespace: Document namespace.
            docname: Document name.
            is_shared: Whether this is a shared document.
            user: User object performing the operation.
            data: Data to upsert into the document.
            version: Specific version to target for upsert (optional).
                     If None, targets the currently active version.
            from_version: Version to branch from if creating a new version during upsert
                          (only relevant if `version` is specified and doesn't exist).
            is_complete: Whether the document is considered complete after this operation.
                         Used during both update and initialization.
            schema_template_name: Name of schema template to apply/validate against (optional).
            schema_template_version: Version of schema template (optional).
            schema_definition: Explicit schema definition to use (optional). Takes precedence
                               over template if both are provided.
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only).
            is_system_entity: Whether this is a system entity (superusers only).

        Returns:
            Tuple[str, Dict[str, Any]]:
                - operation_performed (str): A string indicating the action taken, e.g.,
                    "updated_active", "updated_version_x", "created_and_updated_version_x",
                    "initialized_version_x".
                - document_identifier (Dict[str, Any]): A dictionary containing the path to the affected
                    document version, e.g., "org_id/user_id/namespace/docname/version".
                    The version part will be the targeted version or the initial version.

        Raises:
            HTTPException:
                - 403 Forbidden: If permissions are insufficient.
                - 404 Not Found: If schema template is specified but not found, or if an
                                 operation fails because the underlying document/version
                                 cannot be found when expected.
                - 400 Bad Request: If the document exists but is not versioned.
                - 500 Internal Server Error: For unexpected errors during database operations.

        Upsert Logic Sequence:
        1. **Check Document Existence & Type:** Use `get_document_metadata` to see if the
           document at the base path exists and if it's versioned.
        2. **If Exists (and Versioned):**
           a. **Attempt Update:** Call `update_versioned_document` targeting the specified
              `version` (or active if `version` is None).
           b. **If Update Succeeds:** Return "updated_active" or "updated_version_{version}".
           c. **If Update Fails (and `version` was specified):** This implies the target version
              might not exist.
              i. **Attempt Create Version:** Call `create_versioned_document_version` to
                 create the target `version` (optionally branching from `from_version`).
             ii. **If Create Succeeds:** Retry the `update_versioned_document` call, now
                 targeting the newly created `version`.
            iii. **If Retry Succeeds:** Return "created_and_updated_version_{version}".
             iv. **If Retry Fails (or Create Fails):** Raise an error (indicates a problem
                  like permissions or conflicting state).
           d. **If Update Fails (and `version` was None):** This implies a failure updating
              the active version. Raise an error (likely permissions).
        3. **If Not Exists (or Metadata Check Failed):**
           a. **Attempt Initialize:** Call `initialize_versioned_document`. The initial
              version name will be the specified `version` or "default" if `version` is None.
              The `initial_data` will be the provided `data`, and `is_complete` is passed.
           b. **If Initialize Succeeds:** Return "initialized_version_{initial_version}".
           c. **If Initialize Fails:** Raise an error (likely permissions or conflict).
        4. **Schema Handling:** If `schema_definition` or `schema_template_name` is provided,
           the schema is fetched/validated and applied during the update or initialization step.
        """
        # Ensure versioned client is configured
        if not self.versioned_mongo_client:
            customer_data_logger.error("Upsert failed: Versioned MongoDB client is not configured.")
            raise ValueError("Versioned MongoDB client is required for upsert_versioned_document")

        # --- Permission Checks ---
        if on_behalf_of_user_id and not user.is_superuser:
            customer_data_logger.warning(f"Permission denied for user {user.id} trying to upsert on behalf of {on_behalf_of_user_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can act on behalf of other users"
            )
        if is_system_entity and not user.is_superuser:
            customer_data_logger.warning(f"Permission denied for non-superuser {user.id} trying to upsert a system entity")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can modify system entities"
            )

        # --- Build Path & Prefixes ---
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
            is_mutation=True, # Upsert is a mutation
            is_system_entity=is_system_entity
        )

        # --- Resolve Schema ---
        schema: Optional[Dict[str, Any]] = None
        if schema_definition:
            schema = schema_definition
            customer_data_logger.debug(f"Using provided schema definition for upsert of '{'/'.join(base_path)}'.")
        elif schema_template_name:
            customer_data_logger.debug(f"Fetching schema from template '{schema_template_name}' (version: {schema_template_version}) for upsert.")
            try:
                schema = await self._get_schema_from_template(
                    db, schema_template_name, schema_template_version, org_id, user
                )
                if not schema:
                    customer_data_logger.warning(f"Schema template '{schema_template_name}' not found for org {org_id}.")
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Schema template '{schema_template_name}' not found",
                    )
            except HTTPException as e:
                # Propagate HTTP exceptions from schema fetching
                raise e
            except Exception as e:
                customer_data_logger.error(f"Unexpected error fetching schema template '{schema_template_name}': {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to fetch schema template: {str(e)}"
                )

        # --- Check Document Existence and Type ---
        doc_exists = False
        target_metadata: Optional[schemas.CustomerDocumentMetadata] = None
        try:
            customer_data_logger.debug(f"Checking metadata for document path: {base_path}")
            target_metadata = await self.get_document_metadata(
                org_id=org_id,
                namespace=namespace,
                docname=docname,
                is_shared=is_shared,
                user=user,
                is_system_entity=is_system_entity,
                on_behalf_of_user_id=on_behalf_of_user_id
            )
            if target_metadata:
                doc_exists = True
                if not target_metadata.is_versioned:
                    customer_data_logger.error(f"Upsert failed: Document '{'/'.join(base_path)}' exists but is not versioned.")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Document '{namespace}/{docname}' exists but is not versioned. Cannot perform versioned upsert."
                    )
                customer_data_logger.info(f"Document '{'/'.join(base_path)}' exists and is versioned. Proceeding with update logic.")
            # If metadata is None, doc_exists remains False

        except HTTPException as e:
            # Log only if it's not a 404 (Not Found) or 403 (Forbidden)
            if e.status_code not in [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN]:
                customer_data_logger.warning(f"Error checking metadata for '{'/'.join(base_path)}' during upsert: {e.detail}", exc_info=True)
            else:
                 customer_data_logger.info(f"Metadata check for '{'/'.join(base_path)}' resulted in {e.status_code}. Assuming document does not exist or is inaccessible.")
            # Continue, assuming document might not exist or is inaccessible initially
            pass # doc_exists remains False
        except Exception as e:
            # Catch unexpected errors during metadata check
            customer_data_logger.error(f"Unexpected error during metadata check for '{'/'.join(base_path)}': {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to check document metadata: {str(e)}"
            )


        # --- Construct Helper Args for Sub-operations ---
        # Consolidate args used by both update and initialize
        common_args = {
            "db": db,
            "org_id": org_id,
            "namespace": namespace,
            "docname": docname,
            "is_shared": is_shared,
            "user": user,
            "schema_definition": schema, # Use resolved schema
             # Pass schema args only if schema wasn't directly provided
            "schema_template_name": None if schema else schema_template_name,
            "schema_template_version": None if schema else schema_template_version,
            "is_system_entity": is_system_entity,
            "on_behalf_of_user_id": on_behalf_of_user_id,
        }


        # --- Perform Upsert Operation ---
        operation_performed = "unknown"
        final_version = version # Keep track of the version we end up targeting
        is_active_version = version is None

        if doc_exists:
            # --- Document Exists - Attempt Update ---
            customer_data_logger.info(f"Attempting upsert (update phase) for versioned doc '{'/'.join(base_path)}' (target version: {version or 'active'}).")
            try:
                # Attempt to update the target version (or active if version is None)
                await self.update_versioned_document(
                    **common_args, # type: ignore
                    data=data,
                    version=version,
                    is_complete=is_complete,
                )
                # If update_versioned_document succeeds without raising an exception
                operation_performed = f"updated_{version or '$active'}"
                # If version was None, we updated the active one. We might not know *which* one that is without another query.
                # For the path, we'll return the requested target ('active' if None)
                final_version = version  # Represent active symbolically if None was passed
                customer_data_logger.info(f"Upsert (update phase) successful for '{'/'.join(base_path)}' (version: {final_version}).")

            except HTTPException as update_exc:
                # Check if the update failed specifically because the version wasn't found (difficult to be certain from generic exception)
                # A common reason for update failure is the specific version not existing.
                # We'll infer this possibility if a specific version was targeted.
                if version is not None and update_exc.status_code == status.HTTP_404_NOT_FOUND:
                    customer_data_logger.warning(f"Upsert update failed for specific version '{version}' of '{'/'.join(base_path)}', likely because version does not exist. Attempting to create version.", exc_info=True)

                    # --- Attempt to Create the Missing Version ---
                    try:
                        await self.create_versioned_document_version(
                            org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, new_version=version, from_version=from_version,
                            is_system_entity=is_system_entity,
                            on_behalf_of_user_id=on_behalf_of_user_id
                        )
                        customer_data_logger.info(f"Successfully created missing version '{version}' for '{'/'.join(base_path)}'. Retrying update.")

                        # --- Retry Update on Newly Created Version ---
                        try:
                            await self.update_versioned_document(
                                **common_args, # type: ignore
                                data=data,
                                version=version, # Target the newly created version
                                is_complete=is_complete,
                            )
                            operation_performed = f"created_and_updated_version_{version}"
                            final_version = version
                            customer_data_logger.info(f"Upsert (retry update phase) successful for '{'/'.join(base_path)}' (version: {version}).")
                        except Exception as retry_update_err:
                            customer_data_logger.error(f"Upsert failed: Created version '{version}' for '{'/'.join(base_path)}', but failed the subsequent update: {retry_update_err}", exc_info=True)
                            # This is a problematic state, raise an error
                            raise HTTPException(
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=f"Created version '{version}' but failed to update it: {str(retry_update_err)}"
                            ) from retry_update_err

                    except Exception as create_err:
                        customer_data_logger.error(f"Upsert failed: Update for version '{version}' failed, and subsequent attempt to create version also failed: {create_err}", exc_info=True)
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to create target version '{version}' after initial update failed: {str(create_err)}"
                        ) from create_err
                else:
                    # Update failed for a reason other than the specific version not existing,
                    # or it failed when targeting the active version. This is likely a permission issue or other internal error.
                    customer_data_logger.error(f"Upsert failed: Update phase failed for '{'/'.join(base_path)}' (target version: {version or 'active'}): {update_exc.detail}", exc_info=True)
                    # Re-raise the original exception from update_versioned_document
                    raise update_exc
            except Exception as update_err:
                 # Catch unexpected errors during the update phase
                customer_data_logger.error(f"Upsert failed: Unexpected error during update phase for '{'/'.join(base_path)}' (target version: {version or 'active'}): {update_err}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Unexpected error updating document: {str(update_err)}"
                ) from update_err

        else:
            # --- Document Does Not Exist (or metadata failed) - Attempt Initialize ---
            init_version = version or "default" # Use specified version or default for init
            customer_data_logger.info(f"Upsert: Document '{'/'.join(base_path)}' not found or metadata check failed. Attempting initialization with version '{init_version}'.")

            try:
                initialize_success = await self.initialize_versioned_document(
                    **common_args, # type: ignore
                    initial_version=init_version,
                    initial_data=data,
                    is_complete=is_complete or False, # Default is_complete to False for init if not provided
                )
                if initialize_success:
                    operation_performed = f"initialized_version_{init_version}"
                    final_version = init_version
                    customer_data_logger.info(f"Upsert (initialize phase) successful for '{'/'.join(base_path)}' with version '{init_version}'.")
                    is_active_version = True
                else:
                    # Should ideally be caught by exception, but defensive check
                    customer_data_logger.error(f"Upsert failed: Initialization returned False for '{'/'.join(base_path)}' with version '{init_version}'.")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Document initialization failed unexpectedly for version '{init_version}."
                    )
            except HTTPException as init_http_exc:
                 # Re-raise HTTP exceptions from initialization (e.g., 409 Conflict if it somehow exists now)
                 customer_data_logger.error(f"Upsert failed: Initialization phase for '{'/'.join(base_path)}' (version: '{init_version}') failed with HTTP error {init_http_exc.status_code}: {init_http_exc.detail}", exc_info=True)
                 raise init_http_exc
            except Exception as init_err:
                customer_data_logger.error(f"Upsert failed: Initialization phase encountered an error for '{'/'.join(base_path)}' (version: '{init_version}'): {init_err}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to initialize document with version '{init_version}': {str(init_err)}"
                ) from init_err

        # --- Construct Final Path String ---
        # Use the determined org_id and user_id segments from base_path
        org_id_segment = base_path[0]
        user_id_segment = base_path[1]
        # Include the final version (which might be 'active' symbolically)
        document_identifier = {
            "doc_path_segments": {
                "org_id_segment": org_id_segment,
                "user_id_segment": user_id_segment,
                "namespace": namespace,
                "docname": docname,
            },
            "operation_params": {
                "org_id": org_id,
                "is_shared": is_shared,
                "on_behalf_of_user_id": on_behalf_of_user_id,
                "is_system_entity": is_system_entity,
                "namespace": namespace,
                "docname": docname,
                "set_active_version": set_active_version,
                "is_complete": is_complete,
            },
            "version": final_version,
        }
        document_path_str = f"{org_id_segment}/{user_id_segment}/{namespace}/{docname}/{final_version}"

        if (not is_active_version) and final_version and set_active_version:
            # If we didn't target the active version, and we're supposed to set it, do that now
            try:
                await self.set_active_version(
                    org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                    user=user, version=final_version, on_behalf_of_user_id=on_behalf_of_user_id, is_system_entity=is_system_entity
                )
            except Exception as set_active_err:
                customer_data_logger.error(f"Failed to set active version during upsert for '{'/'.join(base_path)}': {set_active_err} - DOC IDENTIFIER: {json.dumps(document_identifier, indent=2)}", exc_info=True)

        customer_data_logger.info(f"Upsert completed for path '{'/'.join(base_path)}'. Operation: {operation_performed}, Final Path: {document_path_str}")
        return operation_performed, document_identifier

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
        sort_by: Optional[schemas.CustomerDataSortBy] = None,
        sort_order: Optional[schemas.SortOrder] = schemas.SortOrder.DESC,
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
            sort_by: Field to sort results by
            sort_order: Order to sort results (ASC or DESC)
            
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
            
            # Define sort options based on provided parameters
            sort_direction = 1 if sort_order == schemas.SortOrder.ASC else -1
            value_sort_by = None
            
            if sort_by:
                if sort_by == schemas.CustomerDataSortBy.CREATED_AT:
                    value_sort_by = [("created_at", sort_direction)]
                elif sort_by == schemas.CustomerDataSortBy.UPDATED_AT:
                    value_sort_by = [("updated_at", sort_direction)]
            
            for pattern in patterns:
                customer_data_logger.debug(f"Processing pattern: {pattern}")
                docs = await self.versioned_mongo_client.client.search_objects(
                    # NOTE: we only wanna fetch all docs where the version/sequence no. segments are unset!
                    key_pattern=pattern + [None] * len(self.versioned_mongo_client.VERSION_SEGMENT_NAMES),
                    allowed_prefixes=allowed_prefixes,
                    include_fields=self.versioned_mongo_client.segment_names + [self.mongo_client.DOC_TYPE_KEY],
                    skip=skip,
                    limit=limit,
                    value_sort_by=value_sort_by
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
            
            # Return unique result (sorting and pagination is now done by the search_objects function)
            return unique_result
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list documents: {str(e)}",
            )
