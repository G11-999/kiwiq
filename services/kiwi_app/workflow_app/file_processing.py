import json
from enum import Enum
import os
import tempfile
import uuid
from typing import Union, List, Dict, Any, Optional, Tuple

from bson.binary import Binary

from markitdown import MarkItDown
from fastapi import APIRouter, UploadFile, File, Query, Depends, HTTPException, status, Form, Body

from kiwi_app.workflow_app.service_customer_data import CustomerDataService
from kiwi_app.workflow_app import schemas
from kiwi_app.utils import get_kiwi_logger
from kiwi_app.workflow_app.dependencies import RequireOrgDataWriteActiveOrg, get_customer_data_service_dependency
from kiwi_app.auth.dependencies import get_active_org_id, get_current_active_verified_user
from kiwi_app.auth.models import User
from db.session import get_async_db_dependency, AsyncSession

# from kiwi_app.workflow_app.customer_data_routes import upload_router

md = MarkItDown()

logger = get_kiwi_logger(__name__)

# MongoDB document size limit (16MB)
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB in bytes

upload_router = APIRouter(
    tags=["uploads"],
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)] # Apply write permission check globally here
)


def convert_to_markdown_from_raw_file_content(file_content: Union[bytes, str], file_name: str) -> str:
    """
    Convert raw file content to Markdown text.
    """
    filename, ext = os.path.splitext(file_name.lower())
    # assert file_extension in VALID_FILE_EXTENSIONS, f"Unsupported file extension: {file_extension}"
    with tempfile.NamedTemporaryFile(delete=True, prefix = filename, suffix=ext) as tmp:  # f"temp_file_{str(uuid.uuid4())}"
        tmp.write(file_content)
        tmp.flush()
        tmp_path = tmp.name
        return convert_to_markdown(tmp_path)

def convert_to_markdown(input_path: str) -> str:
    """
    Convert .pdf/.docx/.pptx/.xlsx/.html/.jpg/.mp3/.zip/... to Markdown,
    or return raw text for .txt/.md files.
    """
    _, ext = os.path.splitext(input_path.lower())

    # Passthrough for plain text or Markdown files
    if ext in (".txt", ".md"):
        with open(input_path, "r", encoding="utf-8") as f:
            return f.read()

    # Universal converter for all other supported formats
    md = MarkItDown(enable_plugins=False)  # disable plugins by default
    result = md.convert(input_path)
    return result.text_content


class UploadModeEnum(str, Enum):
    create = "create"
    upsert = "upsert"


async def _validate_file_upload_configs(
    filenames: List[str],
    config_payload: Union[schemas.FileUploadRequestPayload, str],
    active_org_id: uuid.UUID,
    current_user: User,
    service: CustomerDataService
) -> Tuple[List[str], Dict[str, List[str]], Dict[str, Tuple[schemas.FileUploadConfig, bool, Optional[schemas.CustomerDocumentMetadata]]]]:
    """
    Validates configurations, checks existence, compatibility, and permissions for all files.

    Args:
        filenames: List of uploaded file names.
        config_payload: FileUploadRequestPayload or JSON string of FileUploadRequestPayload.
        active_org_id: Current organization ID.
        current_user: Current authenticated user.
        service: CustomerDataService instance.

    Returns:
        A tuple containing:
        - List[str]: List of global validation errors (not specific to a file).
        - Dict[str, List[str]]: Dictionary mapping filenames to their specific validation errors.
        - Dict[str, Tuple[schemas.FileUploadConfig, bool, Optional[schemas.CustomerDocumentMetadata]]]:
          Dictionary mapping filename to its validated config, existence status, and existing metadata
          (only contains entries for files that passed all validations).
    """
    global_validation_errors: List[str] = []
    file_validation_errors: Dict[str, List[str]] = {}
    pre_check_results: Dict[str, Tuple[schemas.FileUploadConfig, bool, Optional[schemas.CustomerDocumentMetadata]]] = {}

    # --- 1. Parse Base Configuration Payload ---

    try:
        if isinstance(config_payload, str):
            payload_dict = json.loads(config_payload)
            upload_payload = schemas.FileUploadRequestPayload.model_validate(payload_dict)
        else:
            upload_payload = config_payload
        
        global_defaults = upload_payload.global_defaults or schemas.FileUploadConfig()
        file_configs = upload_payload.file_configs or {}
    except json.JSONDecodeError:
        global_validation_errors.append("Invalid configuration payload: Not valid JSON.")
        return global_validation_errors, file_validation_errors, pre_check_results # Cannot proceed
    except Exception as e:
        global_validation_errors.append(f"Invalid configuration payload: {e}")
        return global_validation_errors, file_validation_errors, pre_check_results # Cannot proceed

    # --- 2. Validate Each File Config & Perform Checks ---
    logger.info("Starting pre-validation and metadata checks for all files...")
    for filename in filenames:
        if not filename:
            global_validation_errors.append("File upload error: A file was provided without a filename.")
            continue # Skip to next file

        current_file_errors: List[str] = []
        validated_config: Optional[schemas.FileUploadConfig] = None
        doc_exists = False
        existing_metadata: Optional[schemas.CustomerDocumentMetadata] = None

        # --- 2a. Determine & Validate File Configuration ---
        try:
            config = global_defaults.model_copy(deep=True)
            if filename in file_configs:
                file_specific_config = file_configs[filename]
                config_update_dict = file_specific_config.model_dump(exclude_unset=True)
                config = config.model_copy(update=config_update_dict)

            if config.docname is None:
                config.docname = filename

            validated_config = schemas.FileUploadConfig.model_validate(config.model_dump())
            logger.debug(f"Config validated for {filename}: {validated_config.model_dump(exclude_unset=True)}")

            # --- 2b. Superuser Permission Checks ---
            if not current_user.is_superuser:
                if validated_config.on_behalf_of_user_id:
                    current_file_errors.append(f"{filename}: Using 'on_behalf_of_user_id' requires superuser privileges.")
                if validated_config.is_system_entity:
                    current_file_errors.append(f"{filename}: Setting 'is_system_entity' requires superuser privileges.")

        except Exception as e:
            logger.warning(f"Configuration validation failed for {filename}: {e}")
            current_file_errors.append(f"Invalid configuration - {e}")
            # Add errors and skip further checks for this file
            file_validation_errors.setdefault(filename, []).extend(current_file_errors)
            continue # Skip to next file

        # Proceed only if config is valid and basic permission checks passed
        if validated_config and not current_file_errors:
            # --- 2c. Check Document Existence & Compatibility ---
            try:
                logger.debug(f"Fetching metadata for {filename} at {validated_config.namespace}/{validated_config.docname}")
                existing_metadata = await service.get_document_metadata(
                    org_id=active_org_id,
                    namespace=validated_config.namespace,
                    docname=validated_config.docname,
                    is_shared=validated_config.is_shared,
                    user=current_user,
                    on_behalf_of_user_id=validated_config.on_behalf_of_user_id,
                    is_system_entity=validated_config.is_system_entity,
                )
                doc_exists = True
                logger.debug(f"Metadata found for {filename}. Exists: True, Versioned: {existing_metadata.is_versioned}")
            except HTTPException as e:
                if e.status_code == status.HTTP_404_NOT_FOUND:
                    doc_exists = False
                    logger.debug(f"Metadata not found for {filename}. Exists: False")
                else:
                    logger.error(f"HTTP error fetching metadata for {filename}: {e.detail}")
                    current_file_errors.append(f"Error checking existing document - {e.detail}")
            except Exception as e:
                logger.error(f"Unexpected error fetching metadata for {filename}: {e}", exc_info=True)
                current_file_errors.append(f"Unexpected error checking existing document - {e}")

            # --- 2d. Apply Mode/Compatibility Validation Rules ---
            if not current_file_errors: # Only apply rules if metadata check didn't fail
                mode = validated_config.mode
                is_versioned_request = validated_config.is_versioned

                if mode == schemas.FileUploadModeEnum.create and doc_exists:
                    err = f"{filename}: Cannot create document at '{validated_config.namespace}/{validated_config.docname}' because it already exists."
                    logger.warning(err)
                    current_file_errors.append(err)

                elif mode == schemas.FileUploadModeEnum.upsert and doc_exists:
                    if existing_metadata is None:
                         err = f"{filename}: Internal inconsistency - document exists but metadata unavailable for validation."
                         logger.error(err)
                         current_file_errors.append(err)
                    elif existing_metadata.is_versioned != is_versioned_request:
                        type_existing = "versioned" if existing_metadata.is_versioned else "unversioned"
                        type_requested = "versioned" if is_versioned_request else "unversioned"
                        err = f"Cannot perform {type_requested} upsert on '{validated_config.namespace}/{validated_config.docname}'. Document exists and is {type_existing}."
                        logger.warning(err)
                        current_file_errors.append(err)

        # --- 2e. Store Pre-check Result or Errors ---
        if current_file_errors:
            file_validation_errors.setdefault(filename, []).extend(current_file_errors)
        elif validated_config: # Ensure config was successfully validated
            # All checks passed for this file
            pre_check_results[filename] = (validated_config, doc_exists, existing_metadata)
            logger.info(f"Pre-validation successful for {filename}. Mode: {validated_config.mode}, Exists: {doc_exists}")

    return global_validation_errors, file_validation_errors, pre_check_results


@upload_router.post("/upload", response_model=List[Dict[str, Any]]) # Define a more specific response schema later if needed
async def upload_documents(
    files: List[UploadFile] = File(..., description="List of files to upload."),
    config_payload: str = Form(default='{}', description="JSON string containing FileUploadRequestPayload schema for upload configurations."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """
    Uploads one or more files, converts them to Markdown or stores as raw binary,
    and stores them as customer data documents according to the provided configuration.

    - Accepts a list of files via multipart/form-data.
    - Accepts a JSON string (`config_payload`) in the form data containing global
      and per-file configurations based on the `FileUploadRequestPayload` schema.
    - Uses the `CustomerDataService` to handle creation or upserting of
      versioned or unversioned documents in MongoDB.
    - **File Size Limit**: Individual files cannot exceed 16MB due to MongoDB document size limit.

    **Configuration Defaults (if not specified):**
    - `namespace`: "uploaded_files"
    - `docname`: Inferred from filename (without extension)
    - `description`: None
    - `is_shared`: False
    - `is_system_entity`: False
    - `on_behalf_of_user_id`: None
    - `mode`: "create"
    - `is_versioned`: False
    - `save_as_raw`: False (converts to markdown by default)
    - `versioned_config`: None

    **Storage Options:**
    - `save_as_raw=False` (default): Converts files to markdown text using MarkItDown
    - `save_as_raw=True`: Stores files as raw binary data using MongoDB Binary format

    Returns:
        A list of dictionaries, each detailing the result for a processed file.
        Includes `filename`, `status` ('success' or 'error'), `message`, and
        potentially `document_path` or `document_identifier`.
    """
    # --- 1. Validate All Configurations and Pre-checks ---
    global_validation_errors: List[str] = []
    file_validation_errors: Dict[str, List[str]] = {}
    pre_check_results: Dict[str, Tuple[schemas.FileUploadConfig, bool, Optional[schemas.CustomerDocumentMetadata]]] = {}
    global_validation_errors, file_validation_errors, pre_check_results = await _validate_file_upload_configs(
        filenames=[file.filename for file in files],
        config_payload=config_payload,
        active_org_id=active_org_id,
        current_user=current_user,
        service=service
    )

    if global_validation_errors or file_validation_errors:
        # Format error message
        error_detail = "File upload validation failed:\n"
        if global_validation_errors:
            error_detail += "Global Errors:\n" + "\n".join(f"- {err}" for err in global_validation_errors) + "\n"
        if file_validation_errors:
            error_detail += "File Errors:\n"
            for fname, errors in file_validation_errors.items():
                error_detail += f"  {fname}:\n" + "\n".join(f"  - {err}" for err in errors) + "\n"

        logger.error(f"Aborting upload due to validation errors: {error_detail}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_detail)

    # --- 2. Process Each Validated File ---
    logger.info(f"All pre-validations passed. Proceeding to process {len(pre_check_results)} files.")
    results = []
    file_map = {f.filename: f for f in files if f.filename} # Assumes filenames are unique in the batch

    for filename, (config, doc_exists_precheck, existing_metadata_precheck) in pre_check_results.items():
        file = file_map.get(filename)
        if not file:
            logger.error(f"Internal error: File object not found for pre-validated filename {filename}")
            results.append({"filename": filename, "status": "error", "message": "Internal error: File object missing during processing."})
            continue

        logger.info(f"Processing file {filename}...")
        doc_identifier: Optional[schemas.CustomerDocumentIdentifier] = None
        message: str = ""

        # --- 2a. Read and Convert ---
        try:
            file_content_bytes = await file.read()
            
            # Validate file size (MongoDB has 16MB document limit)
            if len(file_content_bytes) > MAX_FILE_SIZE:
                logger.warning(f"File {filename} exceeds size limit: {len(file_content_bytes)} bytes > {MAX_FILE_SIZE} bytes")
                results.append({
                    "filename": filename, 
                    "status": "error", 
                    "message": f"File size exceeds 16MB limit. File size: {len(file_content_bytes):,} bytes ({len(file_content_bytes) / 1024 / 1024:.2f} MB)"
                })
                await file.close()
                continue
            
            # Prepare base data structure
            data_to_store = {"source_filename": filename}
            
            # Add description if provided
            if config.description:
                data_to_store["description"] = config.description
            
            # Choose storage format based on save_as_raw config
            if config.save_as_raw:
                # Save as raw bytes using MongoDB Binary format
                data_to_store["raw_content"] = Binary(file_content_bytes)
                logger.debug(f"Saving file {filename} as raw binary content ({len(file_content_bytes):,} bytes, {len(file_content_bytes) / 1024 / 1024:.2f} MB)")
            else:
                # Convert to markdown as before
                markdown_content = convert_to_markdown_from_raw_file_content(file_content_bytes, filename)
                data_to_store["markdown_content"] = markdown_content
                logger.debug(f"Converted file {filename} to markdown (original: {len(file_content_bytes):,} bytes, markdown: {len(markdown_content):,} characters)")
                
        except Exception as e:
            logger.error(f"Error reading or converting file {filename} during processing: {e}", exc_info=True)
            results.append({"filename": filename, "status": "error", "message": f"File processing error: {e}"})
            await file.close()
            continue

        # --- 2b. Store Document (Checks already passed) ---
        try:
            final_version: Optional[str] = None # Track version for identifier

            # Determine the exact operation based on pre-checked state
            if config.mode == schemas.FileUploadModeEnum.create:
                # Pre-check ensured doc_exists_precheck is False
                if config.is_versioned:
                    if config.versioned_config is None: raise ValueError("Versioned config missing") # Should be caught earlier
                    final_version = config.versioned_config.version or "default"
                    logger.debug(f"Executing: Initialize versioned ({final_version}) for {filename}")
                    await service.initialize_versioned_document(
                        db=db, org_id=active_org_id, namespace=config.namespace, docname=config.docname,
                        is_shared=config.is_shared, user=current_user, initial_version=final_version,
                        initial_data=data_to_store, is_complete=config.versioned_config.is_complete or False,
                        on_behalf_of_user_id=config.on_behalf_of_user_id, is_system_entity=config.is_system_entity,
                    )
                    message = f"Creation successful (versioned: {final_version})"
                else:
                    final_version = None
                    logger.debug(f"Executing: Create unversioned for {filename}")
                    _, is_created = await service.create_or_update_unversioned_document(
                        db=db, org_id=active_org_id, namespace=config.namespace, docname=config.docname,
                        is_shared=config.is_shared, user=current_user, data=data_to_store,
                        on_behalf_of_user_id=config.on_behalf_of_user_id, is_system_entity=config.is_system_entity,
                    )
                    if not is_created: raise RuntimeError("Internal Error: Create conflict after pre-check passed.") # Should not happen
                    message = "Creation successful (unversioned)"

            elif config.mode == schemas.FileUploadModeEnum.upsert:
                 # Upsert logic (can be create or update)
                 if config.is_versioned:
                     if config.versioned_config is None: raise ValueError("Versioned config missing")
                     logger.debug(f"Executing: Upsert versioned for {filename}")
                     op_performed, doc_identifier_dict = await service.upsert_versioned_document(
                         db=db, org_id=active_org_id, namespace=config.namespace, docname=config.docname,
                         is_shared=config.is_shared, user=current_user, data=data_to_store,
                         version=config.versioned_config.version,
                         from_version=config.versioned_config.from_version,
                         is_complete=config.versioned_config.is_complete,
                         on_behalf_of_user_id=config.on_behalf_of_user_id, is_system_entity=config.is_system_entity,
                     )
                     doc_identifier = schemas.CustomerDocumentIdentifier.model_validate(doc_identifier_dict)
                     message = f"Upsert successful ({op_performed})"
                     # Extract final version from identifier if possible (might be None if active)
                     final_version = doc_identifier.version
                 else:
                     logger.debug(f"Executing: Upsert unversioned for {filename}")
                     _, is_created = await service.create_or_update_unversioned_document(
                         db=db, org_id=active_org_id, namespace=config.namespace, docname=config.docname,
                         is_shared=config.is_shared, user=current_user, data=data_to_store,
                         on_behalf_of_user_id=config.on_behalf_of_user_id, is_system_entity=config.is_system_entity,
                     )
                     # For unversioned upsert, create_or_update handles both cases
                     message = "Upsert successful (created/updated unversioned)"
                     final_version = None # Unversioned docs don't have a version
            else:
                 # Should not happen due to earlier validation
                 raise ValueError(f"Unsupported mode encountered during processing: {config.mode}")

            # Construct identifier if not already set (e.g., for create ops or unversioned upsert)
            if doc_identifier is None:
                 
                 base_path = service._build_base_path(
                    org_id=active_org_id, namespace=config.namespace, docname=config.docname, 
                    is_shared=config.is_shared, user=current_user, on_behalf_of_user_id=config.on_behalf_of_user_id, 
                    is_system_entity=config.is_system_entity
                 )
                 org_id_segment = base_path[0]
                 user_id_segment = base_path[1]

                 doc_identifier = schemas.CustomerDocumentIdentifier(
                     doc_path_segments={
                            "org_id_segment": org_id_segment,
                            "user_id_segment": user_id_segment,
                            "namespace": config.namespace,
                            "docname": config.docname,
                        },
                     operation_params={
                         "org_id": active_org_id, "is_shared": config.is_shared,
                         "on_behalf_of_user_id": config.on_behalf_of_user_id, "is_system_entity": config.is_system_entity,
                         "namespace": config.namespace, "docname": config.docname,
                         "is_versioned": config.is_versioned,
                         "version": config.versioned_config.version if config.versioned_config is not None else None,
                     },
                     version=final_version,
                 )

            # Append success result
            results.append({
                "filename": filename,
                "status": "success",
                "message": message,
                "document_identifier": doc_identifier.model_dump(),
                "config_used": config.model_dump()
            })
            logger.info(f"Successfully processed file: {filename}. Result: {message}")

        except HTTPException as e:
            logger.error(f"HTTP error processing file {filename}: {e.detail}", exc_info=True)
            results.append({"filename": filename, "status": "error", "message": f"HTTP {e.status_code}: {e.detail}"})
        except Exception as e:
            logger.error(f"Error processing file {filename}: {e}", exc_info=True)
            results.append({"filename": filename, "status": "error", "message": f"Processing error: {str(e)}"})
        finally:
            await file.close()

    logger.info(f"Finished processing files for org {active_org_id}.")
    return results


@upload_router.post("/validate-upload-config", response_model=schemas.FileUploadValidationResult)
async def validate_upload_configs(
    config_payload: schemas.FileUploadValidationRequest = Body(..., description="The payload containing global defaults and per-file configurations."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """
    Validates the file upload configuration payload against the provided file list,
    including existence checks, compatibility checks, and permission checks,
    without actually uploading or processing file content.

    Returns:
        A `FileUploadValidationResult` indicating overall validity and listing specific errors if any.
    """
    logger.info(f"Validating upload config for {len(config_payload.files)} potential files for org {active_org_id}.")

    global_errors, file_errors, _ = await _validate_file_upload_configs(
        filenames=config_payload.files,
        config_payload=config_payload.payload,
        active_org_id=active_org_id,
        current_user=current_user,
        service=service
    )

    is_valid = not global_errors and not file_errors
    if not is_valid:
        logger.warning(f"Upload config validation failed for org {active_org_id}. Global: {global_errors}, Files: {file_errors}")
        return schemas.FileUploadValidationResult(is_valid=False, global_errors=global_errors, file_errors=file_errors)
    else:
        logger.info(f"Upload config validation successful for org {active_org_id}.")
        return schemas.FileUploadValidationResult(is_valid=True, global_errors=[], file_errors={})
