"""Routes for customer data management."""

import uuid
import mimetypes
from typing import List, Dict, Any, Optional, Union

from bson.binary import Binary

from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, Body, Response
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_async_db_dependency
from kiwi_app.auth.dependencies import get_current_active_verified_user, get_current_active_superuser
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

from kiwi_app.workflow_app.file_processing import upload_router

customer_data_logger = get_kiwi_logger(name="kiwi_app.customer_data")
# Create router
customer_data_router = APIRouter(prefix="/customer-data", tags=["customer-data"])
customer_data_router.include_router(upload_router)


@customer_data_router.get(
    "/{namespace}/{docname}",
    response_model=schemas.CustomerDocumentSearchResult,
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Get a document (versioned or unversioned)",
    description="""Retrieves a document by automatically detecting if it's versioned or unversioned.
    
    This endpoint first checks the document metadata to determine its type, then retrieves the document using the appropriate method:
    - For versioned documents: Returns the specified version (or active version if not specified)
    - For unversioned documents: Returns the document data (version parameter is ignored)
    
    This provides a unified interface for document retrieval without needing to know the document type in advance.
    
    Returns comprehensive metadata including document type, version info, path details, and the actual document contents.
    """,
    tags=["customer-data"],
)
async def get_document(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    version: Optional[str] = Query(None, description="Specific version to retrieve (only used for versioned documents). If not provided and document is versioned, retrieves the active version."),
    is_system_entity: bool = Query(False, description="Whether this is a system entity (superusers only)."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="Optional user ID to act on behalf of (superusers only)."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Get a document (automatically detects versioned vs unversioned)."""
    customer_data_logger.info(f"Getting document: {namespace}/{docname} for org {active_org_id}, version {version}")
    document_result = await service.get_document(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=is_shared,
        user=current_user,
        version=version,
        on_behalf_of_user_id=on_behalf_of_user_id,
        is_system_entity=is_system_entity,
    )

    if ("raw_content" in document_result.document_contents and "source_filename" in document_result.document_contents):
        document_result.document_contents = {"source_filename": document_result.document_contents["source_filename"], "status_message": "File uploaded as raw content. Use `/download` endpoint to download it."}

    if not document_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {namespace}/{docname} not found")
    
    customer_data_logger.debug(f"Retrieved document {namespace}/{docname} (versioned: {document_result.metadata.is_versioned})")
    return document_result


@customer_data_router.get(
    "/{namespace}/{docname}/download",
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Download a file uploaded as raw content",
    description="""Downloads a file that was uploaded with save_as_raw=True option.
    
    This endpoint:
    - Retrieves the document and checks if it contains raw_content (binary data)
    - Returns the raw file content with appropriate Content-Type and Content-Disposition headers
    - Preserves the original filename from the upload
    - Only works with documents that have raw_content field (files uploaded with save_as_raw=True)
    
    Returns a binary file download response with appropriate headers.
    """,
    tags=["customer-data", "file-download"],
)
async def download_file(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    version: Optional[str] = Query(None, description="Specific version to retrieve (only used for versioned documents). If not provided and document is versioned, retrieves the active version."),
    is_system_entity: bool = Query(False, description="Whether this is a system entity (superusers only)."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="Optional user ID to act on behalf of (superusers only)."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Download a file that was uploaded as raw content."""
    customer_data_logger.info(f"Downloading file: {namespace}/{docname} for org {active_org_id}, version {version}")
    
    # Get the document using the existing service method
    document_result = await service.get_document(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=is_shared,
        user=current_user,
        version=version,
        on_behalf_of_user_id=on_behalf_of_user_id,
        is_system_entity=is_system_entity,
    )

    if not document_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {namespace}/{docname} not found")
    
    document_contents = document_result.document_contents
    
    # Check if the document contains raw_content (binary data)
    if not isinstance(document_contents, dict) or ("raw_content" not in document_contents or "source_filename" not in document_contents):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Document {namespace}/{docname} does not contain raw binary content. Only files uploaded with save_as_raw=True can be downloaded."
        )
    
    raw_content = document_contents.get("raw_content")
    if not (isinstance(raw_content, Binary) or isinstance(raw_content, bytes)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document {namespace}/{docname} raw_content is not in binary format."
        )
    
    # Extract file information
    source_filename = document_contents.get("source_filename", docname)
    file_data = raw_content  # This is the BSON Binary object
    
    # Convert Binary to bytes
    if hasattr(file_data, '__bytes__'):
        file_bytes = bytes(file_data)
    else:
        file_bytes = file_data
    
    # Determine content type based on filename
    content_type, _ = mimetypes.guess_type(source_filename)
    if content_type is None:
        content_type = "application/octet-stream"  # Default for unknown file types
    
    # Prepare headers for file download
    headers = {
        "Content-Disposition": f"attachment; filename=\"{source_filename}\"",
        "Content-Length": str(len(file_bytes)),
    }
    
    customer_data_logger.info(f"Downloaded file {namespace}/{docname} ({source_filename}, {len(file_bytes)} bytes, {content_type})")
    
    # Return the binary content as a response
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers=headers
    )


@customer_data_router.post(
    "/versioned/{namespace}/{docname}/upsert",
    response_model=schemas.CustomerDataVersionedUpsertResponse,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Upsert a versioned document",
    description=(
        "Updates a versioned document if it exists, or initializes it if it doesn't. "
        "This operation combines update and initialization logic.\n\n"
        "**Behavior:**\n"
        "- If the document at the path exists and is versioned:\n"
        "  - Attempts to update the specified `version` (or the active version if `version` is null)."
        "  - If the update targets a specific `version` that *doesn't* exist, it will first attempt to **create** that version (branching from `from_version` or active) and then apply the update."
        "  - For dictionary document types, updates are treated as partial updates - the provided data will be merged with existing data, preserving any keys not explicitly overwritten."
        "- If the document does not exist:\n"
        "  - Initializes a new versioned document using the provided `data`. The initial version name will be the specified `version` (or 'default' if null)."
        "- If a document exists at the path but is *unversioned*, the operation will fail.\n\n"
        "**Schema Handling:**\n"
        "- If `schema_template_name` is provided, the corresponding schema will be fetched and applied/validated during the update or initialization.\n\n"
        "**Permissions:**\n"
        "- Requires write permissions for the organization's customer data."
        "- `is_system_entity=True` and `on_behalf_of_user_id` require superuser privileges."
    ),
    status_code=status.HTTP_200_OK, # Or 201 if we want to distinguish creation?
                                   # Let's use 200 for simplicity, response indicates action.
    tags=["versioned-customer-data"],
)
async def upsert_versioned_document_route(
    data: schemas.CustomerDataVersionedUpsert,
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Upsert a versioned document (create or update)."""
    customer_data_logger.info(f"Upserting versioned document: {namespace}/{docname} for org {active_org_id}, target version: {data.version or 'active/default'}")

    try:
        operation_performed, document_identifier = await service.upsert_versioned_document(
            db=db,
            org_id=active_org_id,
            namespace=namespace,
            docname=docname,
            is_shared=data.is_shared,
            user=current_user,
            data=data.data,
            version=data.version,
            from_version=data.from_version,
            is_complete=data.is_complete,
            schema_template_name=data.schema_template_name,
            schema_template_version=data.schema_template_version,
            # schema_definition=data.schema_definition, # Not exposing direct definition via API
            on_behalf_of_user_id=data.on_behalf_of_user_id,
            is_system_entity=data.is_system_entity,
            set_active_version=data.set_active_version,
            create_only_fields=data.create_only_fields,
            keep_create_fields_if_missing=data.keep_create_fields_if_missing,
        )

        customer_data_logger.info(f"Upsert successful for {namespace}/{docname}. Operation: {operation_performed}")

        # Manually create the response object as the service returns a tuple
        # The document_identifier dict from the service matches the schema
        return schemas.CustomerDataVersionedUpsertResponse(
            operation_performed=operation_performed,
            document_identifier=schemas.CustomerDocumentIdentifier(**document_identifier)
        )

    except HTTPException as e:
        # Re-raise known HTTP exceptions from the service
        customer_data_logger.warning(f"Upsert failed for {namespace}/{docname} with status {e.status_code}: {e.detail}")
        raise e
    except ValueError as e:
         # Catch potential ValueErrors (e.g., versioned client not configured)
        customer_data_logger.error(f"Upsert failed for {namespace}/{docname} due to configuration error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        # Catch any other unexpected errors
        customer_data_logger.error(f"Unexpected error during upsert for {namespace}/{docname}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during the upsert operation: {str(e)}"
        )


# --- Unversioned document routes --- #

@customer_data_router.put(
    "/unversioned/{namespace}/{docname}",
    response_model=schemas.CustomerDataUnversionedRead,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Create or update an unversioned document",
    description="Creates or updates an unversioned document with new data.",
    tags=["unversioned-customer-data"],
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
        on_behalf_of_user_id=data.on_behalf_of_user_id,
        is_system_entity=data.is_system_entity,
        create_only_fields=data.create_only_fields,
        keep_create_fields_if_missing=data.keep_create_fields_if_missing,
    )
    
    action = "Created" if is_created else "Updated"
    customer_data_logger.info(f"{action} unversioned document: {namespace}/{docname} for org {active_org_id}")
    # Return the updated document
    return schemas.CustomerDataUnversionedRead(data=data.data)


# --- Versioned document routes --- #

@customer_data_router.post(
    "/versioned/{namespace}/{docname}",
    response_model=schemas.CustomerDataRead,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Initialize a new versioned document",
    description="Creates a new versioned document with optional schema validation and initial data.",
    tags=["versioned-customer-data"],
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
        on_behalf_of_user_id=data.on_behalf_of_user_id,
        is_system_entity=data.is_system_entity,
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
        on_behalf_of_user_id=data.on_behalf_of_user_id,
        is_system_entity=data.is_system_entity,
    )
    customer_data_logger.info(f"Document: {document}")
    
    return schemas.CustomerDataRead(data=document)

@customer_data_router.put(
    "/versioned/{namespace}/{docname}",
    response_model=schemas.CustomerDataRead,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Update a versioned document",
    description="""Updates a versioned document with new data. Notes: 
    - For dictionary document types, updates are treated as partial updates
    - Partial dictionaries will be merged with existing data
    - The final dictionary will retain previous keys that are not explicitly overwritten""",
    tags=["versioned-customer-data"],
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
        on_behalf_of_user_id=data.on_behalf_of_user_id,
        is_system_entity=data.is_system_entity,
        create_only_fields=data.create_only_fields,
        keep_create_fields_if_missing=data.keep_create_fields_if_missing,
    )
    
    # Get the updated document to return it
    document = await service.get_versioned_document(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        version=data.version,  # Use the same version as the update
        on_behalf_of_user_id=data.on_behalf_of_user_id,
        is_system_entity=data.is_system_entity,
    )
    
    customer_data_logger.debug(f"Updated document: {namespace}/{docname} for org {active_org_id}")
    return schemas.CustomerDataRead(data=document)

@customer_data_router.get(
    "/versioned/{namespace}/{docname}",
    response_model=schemas.CustomerDataRead,
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Get a versioned document",
    description="Retrieves a versioned document.",
    tags=["versioned-customer-data"],
)
async def get_versioned_document(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    version: Optional[str] = Query(None, description="Specific version to retrieve. If not provided, retrieves the active version."),
    is_system_entity: bool = Query(False, description="Whether this is a system entity (superusers only)."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="Optional user ID to act on behalf of (superusers only)."),
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
        on_behalf_of_user_id=on_behalf_of_user_id,
        is_system_entity=is_system_entity,
    )
    
    return schemas.CustomerDataRead(data=document)

@customer_data_router.delete(
    "/versioned/{namespace}/{docname}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Delete a versioned document",
    description="Deletes a versioned document and all its versions.",
    tags=["versioned-customer-data"],
)
async def delete_versioned_document(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    is_system_entity: bool = Query(False, description="Whether this is a system entity (superusers only)."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="Optional user ID to act on behalf of (superusers only)."),
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
        on_behalf_of_user_id=on_behalf_of_user_id,
        is_system_entity=is_system_entity,
    )
    
    customer_data_logger.info(f"Deleted versioned document: {namespace}/{docname} for org {active_org_id}")
    return None

@customer_data_router.get(
    "/versioned/{namespace}/{docname}/versions",
    response_model=List[schemas.CustomerDataVersionInfo],
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="List versions of a document",
    description="Lists all versions of a versioned document.",
    tags=["versioned-customer-data"],
)
async def list_versioned_document_versions(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    is_system_entity: bool = Query(False, description="Whether this is a system entity (superusers only)."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="Optional user ID to act on behalf of (superusers only)."),
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
        on_behalf_of_user_id=on_behalf_of_user_id,
        is_system_entity=is_system_entity,
    )
    
    return versions

@customer_data_router.post(
    "/versioned/{namespace}/{docname}/versions",
    response_model=schemas.CustomerDataVersionInfo,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Create a new version",
    description="Creates a new version (branch) of a versioned document.",
    tags=["versioned-customer-data"],
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
        on_behalf_of_user_id=data.on_behalf_of_user_id,
        is_system_entity=data.is_system_entity,
    )
    
    # Get all versions to find the newly created one
    versions = await service.list_versioned_document_versions(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        on_behalf_of_user_id=data.on_behalf_of_user_id,
        is_system_entity=data.is_system_entity,
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
    description="Sets the active version of a versioned document.",
    tags=["versioned-customer-data"],
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
        on_behalf_of_user_id=data.on_behalf_of_user_id,
        is_system_entity=data.is_system_entity,
    )
    
    # Get all versions to find the newly activated one
    versions = await service.list_versioned_document_versions(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        on_behalf_of_user_id=data.on_behalf_of_user_id,
        is_system_entity=data.is_system_entity,
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
    description="Gets the history of a versioned document.",
    tags=["versioned-customer-data"],
)
async def get_version_history(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    version: Optional[str] = Query(None, description="Specific version to get history for. If not provided, gets history for the active version."),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of history entries to return."),
    is_system_entity: bool = Query(False, description="Whether this is a system entity (superusers only)."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="Optional user ID to act on behalf of (superusers only)."),
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
        on_behalf_of_user_id=on_behalf_of_user_id,
        is_system_entity=is_system_entity,
    )
    
    return history

@customer_data_router.get(
    "/versioned/{namespace}/{docname}/preview-restore/{sequence}",
    response_model=schemas.CustomerDataRead,
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Preview restore",
    description="Previews restoring a versioned document to a previous state.",
    tags=["versioned-customer-data"],
)
async def preview_restore(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    sequence: int = Path(..., ge=0, description="Sequence number to restore to."),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    version: Optional[str] = Query(None, description="Specific version to restore. If not provided, restores the active version."),
    is_system_entity: bool = Query(False, description="Whether this is a system entity (superusers only)."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="Optional user ID to act on behalf of (superusers only)."),
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
        on_behalf_of_user_id=on_behalf_of_user_id,
        is_system_entity=is_system_entity,
    )
    
    return schemas.CustomerDataRead(data=data)

@customer_data_router.post(
    "/versioned/{namespace}/{docname}/restore",
    response_model=schemas.CustomerDataRead,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Restore document",
    description="Restores a versioned document to a previous state.",
    tags=["versioned-customer-data"],
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
        on_behalf_of_user_id=data.on_behalf_of_user_id,
        is_system_entity=data.is_system_entity,
    )
    
    # Get the restored document to return it
    document = await service.get_versioned_document(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=data.is_shared,
        user=current_user,
        version=data.version,
        on_behalf_of_user_id=data.on_behalf_of_user_id,
        is_system_entity=data.is_system_entity,
    )
    
    customer_data_logger.info(f"Restored document to sequence {data.sequence} for document: {namespace}/{docname}")
    return schemas.CustomerDataRead(data=document)

@customer_data_router.get(
    "/versioned/{namespace}/{docname}/schema",
    response_model=Dict[str, Any],
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Get document schema",
    description="Gets the schema of a versioned document.",
    tags=["versioned-customer-data"],
)
async def get_versioned_document_schema(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    is_system_entity: bool = Query(False, description="Whether this is a system entity (superusers only)."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="Optional user ID to act on behalf of (superusers only)."),
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
        on_behalf_of_user_id=on_behalf_of_user_id,
        is_system_entity=is_system_entity,
    )
    
    if schema is None:
        return {}
    
    return schema

@customer_data_router.put(
    "/versioned/{namespace}/{docname}/schema",
    response_model=Dict[str, Any],
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Update document schema",
    description="Updates the schema of a versioned document.",
    tags=["versioned-customer-data"],
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
            on_behalf_of_user_id=data.on_behalf_of_user_id,
            is_system_entity=data.is_system_entity,
        ),
        schema=schema,
        allowed_prefixes=service._get_allowed_prefixes(
            org_id=active_org_id, 
            user=current_user,
            on_behalf_of_user_id=data.on_behalf_of_user_id,
            is_mutation=True,
            is_system_entity=data.is_system_entity,
        ),
    )
    
    customer_data_logger.info(f"Updated schema for document: {namespace}/{docname} for org {active_org_id}")
    return schema

@customer_data_router.get(
    "/unversioned/{namespace}/{docname}",
    response_model=schemas.CustomerDataUnversionedRead,
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Get an unversioned document",
    description="Retrieves an unversioned document.",
    tags=["unversioned-customer-data"],
)
async def get_unversioned_document(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    is_system_entity: bool = Query(False, description="Whether this is a system entity (superusers only)."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="Optional user ID to act on behalf of (superusers only)."),
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
        on_behalf_of_user_id=on_behalf_of_user_id,
        is_system_entity=is_system_entity,
    )
    
    return schemas.CustomerDataUnversionedRead(data=document)

@customer_data_router.delete(
    "/unversioned/{namespace}/{docname}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Delete an unversioned document",
    description="Deletes an unversioned document.",
    tags=["unversioned-customer-data"],
)
async def delete_unversioned_document(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    is_system_entity: bool = Query(False, description="Whether this is a system entity (superusers only)."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="Optional user ID to act on behalf of (superusers only)."),
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
        on_behalf_of_user_id=on_behalf_of_user_id,
        is_system_entity=is_system_entity,
    )
    
    customer_data_logger.info(f"Deleted unversioned document: {namespace}/{docname} for org {active_org_id}")
    return None

# --- Document listing routes --- #

@customer_data_router.get(
    "/list",
    response_model=List[schemas.CustomerDocumentMetadata],
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="List documents",
    description="Lists documents accessible to the user.",
    tags=["customer-data-listing"],
)
async def list_documents(
    namespace: Optional[str] = Query(None, description="Filter by namespace."),
    include_shared: bool = Query(True, description="Include shared documents."),
    include_user_specific: bool = Query(True, description="Include user-specific documents."),
    include_system_entities: bool = Query(False, description="Include system entities (superusers only)."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="Optional user ID to act on behalf of (superusers only)."),
    skip: int = Query(0, ge=0, description="Number of documents to skip."),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of documents to return."),
    sort_by: Optional[schemas.CustomerDataSortBy] = Query(None, description="Field to sort by."),
    sort_order: Optional[schemas.CustomerDataSortBy] = Query(None, description="Sort order."),
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
        sort_by=sort_by,
        sort_order=sort_order,
        on_behalf_of_user_id=on_behalf_of_user_id,
        include_system_entities=include_system_entities,
    )
    
    customer_data_logger.debug(f"Found {len(documents)} documents for org {active_org_id}")
    return documents

@customer_data_router.post(
    "/search",
    response_model=List[schemas.CustomerDocumentSearchResult],
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Search documents",
    description="Searches documents accessible to the user based on various criteria including namespace, text query, and value filters.",
    tags=["customer-data-listing"],
)
async def search_documents_route(
    search_query: schemas.CustomerDataSearchQuery = Body(...),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Search documents accessible to the user based on query parameters."""
    customer_data_logger.info(f"Searching documents for org {active_org_id} with query: {search_query.model_dump_json(indent=2)}")
    
    documents = await service.search_documents(
        org_id=active_org_id,
        user=current_user,
        namespace_filter=search_query.namespace_filter,
        text_search_query=search_query.text_search_query,
        value_filter=search_query.value_filter,
        include_shared=search_query.include_shared,
        include_user_specific=search_query.include_user_specific,
        skip=search_query.skip,
        limit=search_query.limit,
        on_behalf_of_user_id=search_query.on_behalf_of_user_id,
        include_system_entities=search_query.include_system_entities,
        sort_by=search_query.sort_by,
        sort_order=search_query.sort_order,
        # is_called_from_workflow=False # Assuming this route is not directly called from an internal workflow step
    )

    for document in documents:
        if "raw_content" in document.document_contents and "source_filename" in document.document_contents:
            document.document_contents = {"source_filename": document.document_contents["source_filename"], "status_message": "File uploaded as raw content. Use `/download` endpoint to download it."}
    
    customer_data_logger.debug(f"Found {len(documents)} documents matching search criteria for org {active_org_id}")
    return documents

@customer_data_router.get(
    "/metadata/{namespace}/{docname}",
    response_model=schemas.CustomerDocumentMetadata,
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Get document metadata",
    description="Gets metadata for a document by path.",
    tags=["customer-data-listing"],
)
async def get_document_metadata(
    namespace: str = Path(..., description="Namespace for the document"),
    docname: str = Path(..., description="Name of the document"),
    is_shared: bool = Query(..., description="Specify true for shared org document, false for user-specific document."),
    is_system_entity: bool = Query(False, description="Whether this is a system entity (superusers only)."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="Optional user ID to act on behalf of (superusers only)."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Get metadata for a document."""
    customer_data_logger.info(f"Getting metadata for document: {namespace}/{docname} for org {active_org_id}")
    metadata = await service.get_document_metadata(
        org_id=active_org_id,
        namespace=namespace,
        docname=docname,
        is_shared=is_shared,
        user=current_user,
        on_behalf_of_user_id=on_behalf_of_user_id,
        is_system_entity=is_system_entity,
    )
    
    return metadata

@customer_data_router.delete(
    "/delete-by-pattern",
    response_model=schemas.CustomerDataDeleteResponse,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Delete documents by pattern",
    description="""Deletes multiple documents matching a pattern.
    
    **Security Warning:** This endpoint can delete multiple documents at once.
    Use the `dry_run=true` parameter first to check how many documents would be affected.
    
    Pattern supports wildcards (*) in both namespace and docname. For example:
    - namespace="invoices", docname="*" would delete all documents in the invoices namespace
    - namespace="invoice*", docname="2023*" would delete all documents with namespace starting with "invoice" and name starting with "2023"
    
    Note that this operation deletes both versioned and unversioned documents matching the pattern.
    """,
    tags=["customer-data-management"],
)
async def delete_objects_by_pattern(
    data: schemas.CustomerDataDeleteByPattern,
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_superuser),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """Delete documents matching a pattern."""
    deleted_count = await service.delete_objects_by_pattern(
        org_id=active_org_id,
        namespace_pattern=data.namespace,
        docname_pattern=data.docname,
        is_shared=data.is_shared,
        user=current_user,
        on_behalf_of_user_id=data.on_behalf_of_user_id,
        is_system_entity=data.is_system_entity,
        dry_run=data.dry_run,
    )
    
    return schemas.CustomerDataDeleteResponse(
        deleted_count=deleted_count,
        dry_run=data.dry_run
    )
