"""Routes for customer data management."""

import uuid
from typing import List, Dict, Any, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_async_db_dependency
from kiwi_app.auth.dependencies import get_current_active_verified_user
from kiwi_app.auth.models import User
from kiwi_app.workflow_app import schemas
from kiwi_app.workflow_app.dependencies import (
    get_active_org_id,
    RequireOrgDataReadActiveOrg,
    RequireOrgDataWriteActiveOrg,
    get_customer_data_service_dependency,
)
from kiwi_app.workflow_app.service_customer_data import CustomerDataService
from kiwi_app.utils import get_kiwi_logger

customer_data_logger = get_kiwi_logger(name="kiwi_app.customer_data")
# Create router
customer_data_router = APIRouter(prefix="/customer-data", tags=["customer-data"])

# --- Versioned document routes --- #

@customer_data_router.post(
    "/versioned/{namespace}/{docname}",
    response_model=schemas.CustomerDataRead,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Initialize a new versioned document",
    description="Creates a new versioned document with optional schema validation and initial data."
)
async def initialize_versioned_document(
    data: schemas.CustomerDataVersionedInitialize,
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Initialize a new versioned document."""
    customer_data_logger.info(f"Initializing versioned document: {namespace}/{docname} for org {active_org_id} data: {data.initial_data}")
    result = await service.initialize_versioned_document(
        db=db,
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        initial_version=data.initial_version,
        schema_template_name=data.schema_template_name,
        schema_template_version=data.schema_template_version,
        initial_data=data.initial_data,
        is_complete=data.is_complete,
    )
    
    if not result:
        customer_data_logger.warning(f"Document '{namespace}/{docname}' already exists for org {active_org_id}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document '{namespace}/{docname}' already exists",
        )
    
    # Get the document to return it
    document = await service.get_versioned_document(
        org_id=active_org_id,
        namespace=namespace, 
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        version=data.initial_version,
    )
    customer_data_logger.info(f"Document: {document}")
    
    return schemas.CustomerDataRead(data=document)

@customer_data_router.put(
    "/versioned/{namespace}/{docname}",
    response_model=schemas.CustomerDataRead,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Update a versioned document",
    description="Updates a versioned document with new data."
)
async def update_versioned_document(
    data: schemas.CustomerDataVersionedUpdate,
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Update a versioned document."""
    customer_data_logger.info(f"Updating versioned document: {namespace}/{docname} for org {active_org_id}, version {data.version}")
    await service.update_versioned_document(
        db=db,
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        data=data.data,
        version=data.version,
        is_complete=data.is_complete,
        schema_template_name=data.schema_template_name,
        schema_template_version=data.schema_template_version,
    )
    
    # Get the updated document to return it
    document = await service.get_versioned_document(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        version=data.version,  # Use the same version as the update
    )
    
    customer_data_logger.debug(f"Updated document: {namespace}/{docname} for org {active_org_id}")
    return schemas.CustomerDataRead(data=document)

@customer_data_router.get(
    "/versioned/{namespace}/{docname}",
    response_model=schemas.CustomerDataRead,
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Get a versioned document",
    description="Retrieves a versioned document."
)
async def get_versioned_document(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    version: Optional[str] = Query(None, description="Specific version to retrieve. If not provided, retrieves the active version."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Get a versioned document."""
    customer_data_logger.info(f"Getting versioned document: {namespace}/{docname} for org {active_org_id}, version {version}")
    document = await service.get_versioned_document(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=is_shared,
        user=current_user,
        version=version,
    )
    
    return schemas.CustomerDataRead(data=document)

@customer_data_router.delete(
    "/versioned/{namespace}/{docname}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Delete a versioned document",
    description="Deletes a versioned document and all its versions."
)
async def delete_versioned_document(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Delete a versioned document."""
    customer_data_logger.info(f"Deleting versioned document: {namespace}/{docname} for org {active_org_id}")
    await service.delete_versioned_document(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=is_shared,
        user=current_user,
    )
    
    customer_data_logger.info(f"Deleted versioned document: {namespace}/{docname} for org {active_org_id}")
    return None

@customer_data_router.get(
    "/versioned/{namespace}/{docname}/versions",
    response_model=List[schemas.CustomerDataVersionInfo],
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="List versions of a document",
    description="Lists all versions of a versioned document."
)
async def list_versioned_document_versions(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """List versions of a versioned document."""
    customer_data_logger.info(f"Listing versions for document: {namespace}/{docname} for org {active_org_id}")
    versions = await service.list_versioned_document_versions(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=is_shared,
        user=current_user,
    )
    
    return versions

@customer_data_router.post(
    "/versioned/{namespace}/{docname}/versions",
    response_model=schemas.CustomerDataVersionInfo,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Create a new version",
    description="Creates a new version (branch) of a versioned document."
)
async def create_versioned_document_version(
    data: schemas.CustomerDataCreateVersion,
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Create a new version of a versioned document."""
    customer_data_logger.info(f"Creating new version {data.new_version} from {data.from_version} for document: {namespace}/{docname} for org {active_org_id}")
    await service.create_versioned_document_version(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        new_version=data.new_version,
        from_version=data.from_version,
    )
    
    # Get all versions to find the newly created one
    versions = await service.list_versioned_document_versions(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
    )
    
    # Find the newly created version in the list
    for version in versions:
        if version.version == data.new_version:
            customer_data_logger.info(f"Created new version {data.new_version} for document: {namespace}/{docname}")
            return version
    
    # This should not happen if version creation succeeded
    customer_data_logger.error(f"Version {data.new_version} was created but not found in the version list for document: {namespace}/{docname}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Version was created but not found in the version list",
    )

@customer_data_router.post(
    "/versioned/{namespace}/{docname}/active-version",
    response_model=schemas.CustomerDataVersionInfo,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Set active version",
    description="Sets the active version of a versioned document."
)
async def set_active_version(
    data: schemas.CustomerDataSetActiveVersion,
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Set the active version of a versioned document."""
    customer_data_logger.info(f"Setting active version to {data.version} for document: {namespace}/{docname} for org {active_org_id}")
    await service.set_active_version(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        version=data.version,
    )
    
    # Get all versions to find the newly activated one
    versions = await service.list_versioned_document_versions(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
    )
    
    # Find the active version in the list
    for version in versions:
        if version.version == data.version:
            customer_data_logger.info(f"Set active version to {data.version} for document: {namespace}/{docname}")
            return version
    
    # This should not happen if version activation succeeded
    customer_data_logger.error(f"Version {data.version} was activated but not found in the version list for document: {namespace}/{docname}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Version was activated but not found in the version list",
    )

@customer_data_router.get(
    "/versioned/{namespace}/{docname}/history",
    response_model=List[schemas.CustomerDataVersionHistoryItem],
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Get version history",
    description="Gets the history of a versioned document."
)
async def get_version_history(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    version: Optional[str] = Query(None, description="Specific version to get history for. If not provided, gets history for the active version."),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of history entries to return."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Get the history of a versioned document."""
    customer_data_logger.info(f"Getting history for document: {namespace}/{docname} for org {active_org_id}, version {version}")
    history = await service.get_version_history(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=is_shared,
        user=current_user,
        version=version,
        limit=limit,
    )
    
    return history

@customer_data_router.get(
    "/versioned/{namespace}/{docname}/preview-restore/{sequence}",
    response_model=schemas.CustomerDataRead,
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Preview restore",
    description="Previews restoring a versioned document to a previous state."
)
async def preview_restore(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    sequence: int = Path(..., ge=0, description="Sequence number to restore to."),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    version: Optional[str] = Query(None, description="Specific version to restore. If not provided, restores the active version."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Preview restoring a versioned document to a previous state."""
    customer_data_logger.info(f"Previewing restore to sequence {sequence} for document: {namespace}/{docname} for org {active_org_id}, version {version}")
    data = await service.preview_restore(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=is_shared,
        user=current_user,
        sequence=sequence,
        version=version,
    )
    
    return schemas.CustomerDataRead(data=data)

@customer_data_router.post(
    "/versioned/{namespace}/{docname}/restore",
    response_model=schemas.CustomerDataRead,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Restore document",
    description="Restores a versioned document to a previous state."
)
async def restore_document(
    data: schemas.CustomerDataVersionedRestore,
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Restore a versioned document to a previous state."""
    customer_data_logger.info(f"Restoring document to sequence {data.sequence} for document: {namespace}/{docname} for org {active_org_id}, version {data.version}")
    await service.restore_document(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        sequence=data.sequence,
        version=data.version,
    )
    
    # Get the restored document to return it
    document = await service.get_versioned_document(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        version=data.version,
    )
    
    customer_data_logger.info(f"Restored document to sequence {data.sequence} for document: {namespace}/{docname}")
    return schemas.CustomerDataRead(data=document)

@customer_data_router.get(
    "/versioned/{namespace}/{docname}/schema",
    response_model=Dict[str, Any],
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Get document schema",
    description="Gets the schema of a versioned document."
)
async def get_versioned_document_schema(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Get the schema of a versioned document."""
    customer_data_logger.info(f"Getting schema for document: {namespace}/{docname} for org {active_org_id}")
    schema = await service.get_versioned_document_schema(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=is_shared,
        user=current_user,
    )
    
    if schema is None:
        return {}
    
    return schema

@customer_data_router.put(
    "/versioned/{namespace}/{docname}/schema",
    response_model=Dict[str, Any],
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Update document schema",
    description="Updates the schema of a versioned document."
)
async def update_versioned_document_schema(
    data: schemas.CustomerDataSchemaUpdate,
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Update the schema of a versioned document."""
    customer_data_logger.info(f"Updating schema for document: {namespace}/{docname} for org {active_org_id} using template {data.schema_template_name} v{data.schema_template_version}")
    # Get schema from template
    schema = await service._get_schema_from_template(
        db=db,
        template_name=data.schema_template_name,
        template_version=data.schema_template_version,
        org_id=active_org_id,
        user=current_user,
    )
    
    if schema is None:
        customer_data_logger.warning(f"Schema template '{data.schema_template_name}' not found for org {active_org_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema template '{data.schema_template_name}' not found",
        )
    
    # Update schema
    await service.versioned_mongo_client.update_schema(
        base_path=service._build_base_path(
            org_id=active_org_id,
            namespace=namespace,
            docname=docname,
            is_shared=data.is_shared,
            user=current_user,
        ),
        schema=schema,
        allowed_prefixes=service._get_allowed_prefixes(active_org_id, current_user),
    )
    
    customer_data_logger.info(f"Updated schema for document: {namespace}/{docname} for org {active_org_id}")
    return schema

# --- Unversioned document routes --- #

@customer_data_router.put(
    "/unversioned/{namespace}/{docname}",
    response_model=schemas.CustomerDataUnversionedRead,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Create or update an unversioned document",
    description="Creates or updates an unversioned document with new data."
)
async def create_or_update_unversioned_document(
    data: schemas.CustomerDataUnversionedCreateUpdate,
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Create or update an unversioned document."""
    customer_data_logger.info(f"Creating or updating unversioned document: {namespace}/{docname} for org {active_org_id}")
    doc_id, is_created = await service.create_or_update_unversioned_document(
        db=db,
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        data=data.data,
        schema_template_name=data.schema_template_name,
        schema_template_version=data.schema_template_version,
    )
    
    action = "Created" if is_created else "Updated"
    customer_data_logger.info(f"{action} unversioned document: {namespace}/{docname} for org {active_org_id}")
    # Return the updated document
    return schemas.CustomerDataUnversionedRead(data=data.data)

@customer_data_router.get(
    "/unversioned/{namespace}/{docname}",
    response_model=schemas.CustomerDataUnversionedRead,
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Get an unversioned document",
    description="Retrieves an unversioned document."
)
async def get_unversioned_document(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Get an unversioned document."""
    customer_data_logger.info(f"Getting unversioned document: {namespace}/{docname} for org {active_org_id}")
    document = await service.get_unversioned_document(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=is_shared,
        user=current_user,
    )
    
    return schemas.CustomerDataUnversionedRead(data=document)

@customer_data_router.delete(
    "/unversioned/{namespace}/{docname}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Delete an unversioned document",
    description="Deletes an unversioned document."
)
async def delete_unversioned_document(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Delete an unversioned document."""
    customer_data_logger.info(f"Deleting unversioned document: {namespace}/{docname} for org {active_org_id}")
    await service.delete_unversioned_document(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=is_shared,
        user=current_user,
    )
    
    customer_data_logger.info(f"Deleted unversioned document: {namespace}/{docname} for org {active_org_id}")
    return None

# --- Document listing routes --- #

@customer_data_router.get(
    "/list",
    response_model=List[schemas.CustomerDocumentMetadata],
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="List documents",
    description="Lists documents accessible to the user."
)
async def list_documents(
    namespace: Optional[str] = Query(None, description="Filter by namespace."),
    include_shared: bool = Query(True, description="Include shared documents."),
    include_user_specific: bool = Query(True, description="Include user-specific documents."),
    skip: int = Query(0, ge=0, description="Number of documents to skip."),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of documents to return."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """List documents accessible to the user."""
    # # TODO: FIXME: pre workflow builder launch, we wanna prevent listing of user documents by anyone but the superuser, remove it later!
    # if not current_user.is_superuser:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="You are not authorized to access this resource.",
    #     )

    customer_data_logger.info(f"Listing documents for org {active_org_id}, namespace filter: {namespace}")
    documents = await service.list_documents(
        org_id=active_org_id,
        user=current_user,
        namespace_filter=namespace,
        include_shared=include_shared,
        include_user_specific=include_user_specific,
        skip=skip,
        limit=limit,
    )
    
    customer_data_logger.debug(f"Found {len(documents)} documents for org {active_org_id}")
    return documents
