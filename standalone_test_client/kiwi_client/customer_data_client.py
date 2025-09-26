"""
Test client for the Customer Data API endpoints.


is_shared is both for within org and system wide
is_system_entity is for creating /reading from system paths

paths can be of 4 components in hierarchy:
org/system --/ --user / is_shared --/ -- doc category --/ -- doc name (edited) 


is_shared toggles the 2nd component in path

is_system toggles the first component

its liek filesystem paths for system paths or org specific paths which can be both private or user specific or is_shared

system paths can only be private / is_shared (edited) 


As a rule of thumb:
Put any docs which all users need and should be able to read in system / is_shared
Put any docs which we need / our private system docs or even docs which user doesn't need to read directly but needs to be injected in workflows (we can discuss how) in system / private
"""

import asyncio
import json
import httpx
import logging
import uuid
from typing import Dict, Any, Optional, List, Union, Tuple

# Import pydantic for validation
from pydantic import ValidationError, TypeAdapter

# Import authenticated client and config
from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from kiwi_client.test_config import (
    VERSIONED_DOC_URL,
    VERSIONED_DOC_VERSIONS_URL,
    VERSIONED_DOC_ACTIVE_VERSION_URL,
    VERSIONED_DOC_HISTORY_URL,
    VERSIONED_DOC_PREVIEW_RESTORE_URL,
    VERSIONED_DOC_RESTORE_URL,
    VERSIONED_DOC_SCHEMA_URL,
    UNVERSIONED_DOC_URL,
    LIST_DOCUMENTS_URL,
    CLIENT_LOG_LEVEL,
    TEST_ORG_ID,
    DOCUMENT_METADATA_URL,
    VERSIONED_DOC_UPSERT_URL,
    SEARCH_DOCUMENTS_URL,
    DELETE_BY_PATTERN_URL,
    FILE_UPLOAD_URL,
    FILE_UPLOAD_VALIDATION_URL,
)
# Import schemas and constants from the workflow app
from kiwi_client.schemas import workflow_api_schemas as wf_schemas
from kiwi_client.schemas.workflow_api_schemas import SortOrder, CustomerDataSortBy # Added SortOrder, CustomerDataSortBy
# Import Template Client for schema creation/cleanup
from kiwi_client.template_client import TemplateTestClient

# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)

# Create TypeAdapters for validating lists of schemas
CustomerDataVersionInfoListAdapter = TypeAdapter(List[wf_schemas.CustomerDataVersionInfo])
CustomerDataVersionHistoryItemListAdapter = TypeAdapter(List[wf_schemas.CustomerDataVersionHistoryItem])
CustomerDocumentMetadataListAdapter = TypeAdapter(List[wf_schemas.CustomerDocumentMetadata])
CustomerDocumentSearchResultListAdapter = TypeAdapter(List[wf_schemas.CustomerDocumentSearchResult])

class CustomerDataTestClient:
    """
    Provides methods to test the /customer-data/ endpoints.
    Uses schemas from schemas.py for requests and response validation.
    """
    def __init__(self, auth_client: AuthenticatedClient):
        """
        Initializes the CustomerDataTestClient.

        Args:
            auth_client (AuthenticatedClient): An instance of AuthenticatedClient, assumed to be logged in.
        """
        self._auth_client: AuthenticatedClient = auth_client
        self._client: httpx.AsyncClient = auth_client.client
        logger.info("CustomerDataTestClient initialized.")

    # --- Versioned Document Methods ---

    async def initialize_versioned_document(
        self,
        namespace: str,
        docname: str,
        data: wf_schemas.CustomerDataVersionedInitialize,
    ) -> Optional[wf_schemas.CustomerDataRead]:
        """
        Tests initializing a new versioned document via POST /customer-data/versioned/{namespace}/{docname}.
        """
        logger.info(f"Attempting to initialize versioned document: {namespace}/{docname}")
        url = VERSIONED_DOC_URL(namespace, docname)
        # Send model_dump directly as the request body
        payload = data.model_dump()
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")
        try:
            response = await self._client.post(url, json=payload)
            if response.status_code != 200: # Assuming 200 OK on success for initialization + get
                logger.error(f"Error initializing document: Status {response.status_code} - {response.text}")
                response.raise_for_status()
            
            response_json = response.json()
            validated_response = wf_schemas.CustomerDataRead.model_validate(response_json)
            logger.info(f"Successfully initialized and validated document: {namespace}/{docname}")
            logger.debug(f"Initialize response validated: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.debug(f"HTTP Status Error Detail: {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error initializing document: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error initializing document: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error during document initialization.")
        return None

    async def update_versioned_document(
        self,
        namespace: str,
        docname: str,
        data: wf_schemas.CustomerDataVersionedUpdate,
    ) -> Optional[wf_schemas.CustomerDataRead]:
        """
        Tests updating a versioned document via PUT /customer-data/versioned/{namespace}/{docname}.
        """
        logger.info(f"Attempting to update versioned document: {namespace}/{docname}")
        url = VERSIONED_DOC_URL(namespace, docname)
        # Send model_dump directly as the request body
        payload = data.model_dump()
        try:
            response = await self._client.put(url, json=payload)
            if response.status_code != 200: # Assuming 200 OK on success for update + get
                logger.error(f"Error updating document: Status {response.status_code} - {response.text}")
                response.raise_for_status()

            response_json = response.json()
            validated_response = wf_schemas.CustomerDataRead.model_validate(response_json)
            logger.info(f"Successfully updated and validated document: {namespace}/{docname}")
            logger.debug(f"Update response validated: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.debug(f"HTTP Status Error Detail: {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error updating document: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error updating document: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error during document update.")
        return None

    async def get_versioned_document(
        self,
        namespace: str,
        docname: str,
        is_shared: bool,
        version: Optional[str] = None,
        is_system_entity: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[wf_schemas.CustomerDataRead]:
        """
        Tests getting a versioned document via GET /customer-data/versioned/{namespace}/{docname}.
        
        Args:
            namespace (str): The namespace of the document.
            docname (str): The name of the document.
            is_shared (bool): Whether this is a shared document.
            version (Optional[str]): Specific version to retrieve. If not provided, retrieves the active version.
            is_system_entity (bool): Whether this is a system entity (superusers only). When True, data is stored in 
                                     system paths instead of organization-specific paths. The is_shared parameter 
                                     still applies normally to determine if it's shared with the org or user-specific.
            on_behalf_of_user_id (Optional[uuid.UUID]): Optional user ID to act on behalf of (superusers only).
                                                       Note: This parameter won't work if accessing system entities or
                                                       shared documents, as these are not tied to specific users.
            
        Returns:
            Optional[wf_schemas.CustomerDataRead]: Document data if successful, None otherwise.
        """
        logger.info(f"Attempting to get versioned document: {namespace}/{docname} (shared={is_shared}, version={version})")
        url = VERSIONED_DOC_URL(namespace, docname)
        params = {"is_shared": is_shared}
        if version:
            params["version"] = version
        if is_system_entity:
            params["is_system_entity"] = is_system_entity
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            response_json = response.json()
            validated_response = wf_schemas.CustomerDataRead.model_validate(response_json)
            logger.info(f"Successfully retrieved and validated document: {namespace}/{docname}")
            logger.debug(f"Get response validated: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting document: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting document: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error getting document: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error during document retrieval.")
        return None

    async def delete_versioned_document(
        self,
        namespace: str,
        docname: str,
        is_shared: bool,
        is_system_entity: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """
        Tests deleting a versioned document via DELETE /customer-data/versioned/{namespace}/{docname}.
        
        Args:
            namespace (str): The namespace of the document.
            docname (str): The name of the document.
            is_shared (bool): Whether this is a shared document.
            is_system_entity (bool): Whether this is a system entity (superusers only). When True, data is deleted from 
                                     system paths instead of organization-specific paths. The is_shared parameter 
                                     still applies normally to determine if it's shared with the org or user-specific.
            on_behalf_of_user_id (Optional[uuid.UUID]): Optional user ID to act on behalf of (superusers only).
                                                       Note: This parameter won't work if accessing system entities or
                                                       shared documents, as these are not tied to specific users.
            
        Returns:
            bool: True if deletion was successful, False otherwise.
        """
        logger.info(f"Attempting to delete versioned document: {namespace}/{docname} (shared={is_shared})")
        url = VERSIONED_DOC_URL(namespace, docname)
        params = {"is_shared": is_shared}
        if is_system_entity:
            params["is_system_entity"] = is_system_entity
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
        try:
            response = await self._client.delete(url, params=params)
            response.raise_for_status() # Raises for non-2xx
            logger.info(f"Successfully deleted document: {namespace}/{docname}")
            return response.status_code == 204 # Check for No Content
        except httpx.HTTPStatusError as e:
            logger.error(f"Error deleting document: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error deleting document: {e}")
        except Exception as e:
            logger.exception("Unexpected error during document deletion.")
        return False

    async def list_versioned_document_versions(
        self,
        namespace: str,
        docname: str,
        is_shared: bool,
        is_system_entity: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[List[wf_schemas.CustomerDataVersionInfo]]:
        """
        Tests listing versions via GET /customer-data/versioned/{namespace}/{docname}/versions.
        
        Args:
            namespace (str): The namespace of the document.
            docname (str): The name of the document.
            is_shared (bool): Whether this is a shared document.
            is_system_entity (bool): Whether this is a system entity (superusers only). When True, data is accessed from 
                                     system paths instead of organization-specific paths. The is_shared parameter 
                                     still applies normally to determine if it's shared with the org or user-specific.
            on_behalf_of_user_id (Optional[uuid.UUID]): Optional user ID to act on behalf of (superusers only).
                                                       Note: This parameter won't work if accessing system entities or
                                                       shared documents, as these are not tied to specific users.
            
        Returns:
            Optional[List[wf_schemas.CustomerDataVersionInfo]]: List of version info objects if successful, None otherwise.
        """
        logger.info(f"Attempting to list versions for: {namespace}/{docname} (shared={is_shared})")
        url = VERSIONED_DOC_VERSIONS_URL(namespace, docname)
        params = {"is_shared": is_shared}
        if is_system_entity:
            params["is_system_entity"] = is_system_entity
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            response_json = response.json()
            validated_response = CustomerDataVersionInfoListAdapter.validate_python(response_json)
            logger.info(f"Successfully listed {len(validated_response)} versions for: {namespace}/{docname}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing versions: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error listing versions: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error listing versions: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error listing versions.")
        return None

    async def create_versioned_document_version(
        self,
        namespace: str,
        docname: str,
        data: wf_schemas.CustomerDataCreateVersion,
    ) -> Optional[wf_schemas.CustomerDataVersionInfo]:
        """
        Tests creating a version via POST /customer-data/versioned/{namespace}/{docname}/versions.
        """
        logger.info(f"Attempting to create version '{data.new_version}' for: {namespace}/{docname}")
        url = VERSIONED_DOC_VERSIONS_URL(namespace, docname)
        # Send model_dump directly as the request body
        payload = data.model_dump()
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            response_json = response.json()
            validated_response = wf_schemas.CustomerDataVersionInfo.model_validate(response_json)
            logger.info(f"Successfully created version '{validated_response.version}' for: {namespace}/{docname}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error creating version: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error creating version: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error creating version: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error creating version.")
        return None

    async def set_active_version(
        self,
        namespace: str,
        docname: str,
        data: wf_schemas.CustomerDataSetActiveVersion,
    ) -> Optional[wf_schemas.CustomerDataVersionInfo]:
        """
        Tests setting active version via POST /customer-data/versioned/{namespace}/{docname}/active-version.
        """
        logger.info(f"Attempting to set active version to '{data.version}' for: {namespace}/{docname}")
        url = VERSIONED_DOC_ACTIVE_VERSION_URL(namespace, docname)
        # Send model_dump directly as the request body
        payload = data.model_dump()
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            response_json = response.json()
            validated_response = wf_schemas.CustomerDataVersionInfo.model_validate(response_json)
            logger.info(f"Successfully set active version to '{validated_response.version}' for: {namespace}/{docname}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error setting active version: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error setting active version: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error setting active version: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error setting active version.")
        return None

    async def get_version_history(
        self,
        namespace: str,
        docname: str,
        is_shared: bool,
        version: Optional[str] = None,
        limit: int = 100,
        is_system_entity: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[List[wf_schemas.CustomerDataVersionHistoryItem]]:
        """
        Tests getting history via GET /customer-data/versioned/{namespace}/{docname}/history.
        
        Args:
            namespace (str): The namespace of the document.
            docname (str): The name of the document.
            is_shared (bool): Whether this is a shared document.
            version (Optional[str]): Specific version to get history for.
            limit (int): Maximum number of history entries to return.
            is_system_entity (bool): Whether this is a system entity (superusers only). When True, data is accessed from 
                                     system paths instead of organization-specific paths. The is_shared parameter 
                                     still applies normally to determine if it's shared with the org or user-specific.
            on_behalf_of_user_id (Optional[uuid.UUID]): Optional user ID to act on behalf of (superusers only).
                                                       Note: This parameter won't work if accessing system entities or
                                                       shared documents, as these are not tied to specific users.
            
        Returns:
            Optional[List[wf_schemas.CustomerDataVersionHistoryItem]]: List of history items if successful, None otherwise.
        """
        logger.info(f"Attempting to get history for: {namespace}/{docname} (shared={is_shared}, version={version})")
        url = VERSIONED_DOC_HISTORY_URL(namespace, docname)
        params = {"is_shared": is_shared, "limit": limit}
        if version:
            params["version"] = version
        if is_system_entity:
            params["is_system_entity"] = is_system_entity
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            response_json = response.json()
            validated_response = CustomerDataVersionHistoryItemListAdapter.validate_python(response_json)
            logger.info(f"Successfully got {len(validated_response)} history items for: {namespace}/{docname}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting history: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting history: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error getting history: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error getting history.")
        return None

    async def preview_restore(
        self,
        namespace: str,
        docname: str,
        sequence: int,
        is_shared: bool,
        version: Optional[str] = None,
        is_system_entity: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[wf_schemas.CustomerDataRead]:
        """
        Tests previewing restore via GET /customer-data/versioned/{namespace}/{docname}/preview-restore/{sequence}.
        
        Args:
            namespace (str): The namespace of the document.
            docname (str): The name of the document.
            sequence (int): Sequence number to restore to.
            is_shared (bool): Whether this is a shared document.
            version (Optional[str]): Specific version to restore.
            is_system_entity (bool): Whether this is a system entity (superusers only). When True, data is accessed from 
                                     system paths instead of organization-specific paths. The is_shared parameter 
                                     still applies normally to determine if it's shared with the org or user-specific.
            on_behalf_of_user_id (Optional[uuid.UUID]): Optional user ID to act on behalf of (superusers only).
                                                       Note: This parameter won't work if accessing system entities or
                                                       shared documents, as these are not tied to specific users.
            
        Returns:
            Optional[wf_schemas.CustomerDataRead]: Preview of restored document if successful, None otherwise.
        """
        logger.info(f"Attempting to preview restore for: {namespace}/{docname} (seq={sequence}, shared={is_shared}, version={version})")
        url = VERSIONED_DOC_PREVIEW_RESTORE_URL(namespace, docname, sequence)
        params = {"is_shared": is_shared}
        if version:
            params["version"] = version
        if is_system_entity:
            params["is_system_entity"] = is_system_entity
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            response_json = response.json()
            validated_response = wf_schemas.CustomerDataRead.model_validate(response_json)
            logger.info(f"Successfully previewed restore for: {namespace}/{docname} (seq={sequence})")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error previewing restore: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error previewing restore: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error previewing restore: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error previewing restore.")
        return None

    async def restore_document(
        self,
        namespace: str,
        docname: str,
        data: wf_schemas.CustomerDataVersionedRestore,
    ) -> Optional[wf_schemas.CustomerDataRead]:
        """
        Tests restoring a document via POST /customer-data/versioned/{namespace}/{docname}/restore.
        """
        logger.info(f"Attempting to restore: {namespace}/{docname} (seq={data.sequence}, version={data.version})")
        url = VERSIONED_DOC_RESTORE_URL(namespace, docname)
        # Send model_dump directly as the request body
        payload = data.model_dump()
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            response_json = response.json()
            validated_response = wf_schemas.CustomerDataRead.model_validate(response_json)
            logger.info(f"Successfully restored: {namespace}/{docname} (seq={data.sequence})")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error restoring document: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error restoring document: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error restoring document: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error restoring document.")
        return None

    async def get_versioned_document_schema(
        self,
        namespace: str,
        docname: str,
        is_shared: bool,
        is_system_entity: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Tests getting document schema via GET /customer-data/versioned/{namespace}/{docname}/schema.
        
        Args:
            namespace (str): The namespace of the document.
            docname (str): The name of the document.
            is_shared (bool): Whether this is a shared document.
            is_system_entity (bool): Whether this is a system entity (superusers only). When True, data is accessed from 
                                     system paths instead of organization-specific paths. The is_shared parameter 
                                     still applies normally to determine if it's shared with the org or user-specific.
            on_behalf_of_user_id (Optional[uuid.UUID]): Optional user ID to act on behalf of (superusers only).
                                                       Note: This parameter won't work if accessing system entities or
                                                       shared documents, as these are not tied to specific users.
            
        Returns:
            Optional[Dict[str, Any]]: Document schema if successful, None otherwise.
        """
        logger.info(f"Attempting to get schema for: {namespace}/{docname} (shared={is_shared})")
        url = VERSIONED_DOC_SCHEMA_URL(namespace, docname)
        params = {"is_shared": is_shared}
        if is_system_entity:
            params["is_system_entity"] = is_system_entity
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            # Schema response is a raw JSON Schema object
            schema = response.json()
            logger.info(f"Successfully got schema for: {namespace}/{docname}")
            return schema
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting schema: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting schema: {e}")
        except Exception as e:
            logger.exception("Unexpected error getting schema.")
        return None

    async def update_versioned_document_schema(
        self,
        namespace: str,
        docname: str,
        data: wf_schemas.CustomerDataSchemaUpdate,
    ) -> Optional[Dict[str, Any]]:
        """
        Tests updating schema via PUT /customer-data/versioned/{namespace}/{docname}/schema.
        """
        logger.info(f"Attempting to update schema for: {namespace}/{docname} using template '{data.schema_template_name}'")
        url = VERSIONED_DOC_SCHEMA_URL(namespace, docname)
        # Send model_dump directly as the request body
        payload = data.model_dump()
        try:
            response = await self._client.put(url, json=payload)
            response.raise_for_status()
            response_json = response.json()
            # Assuming the response is the updated JSON schema dictionary
            logger.info(f"Successfully updated schema for: {namespace}/{docname}")
            return response_json
        except httpx.HTTPStatusError as e:
            logger.error(f"Error updating schema: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error updating schema: {e}")
        except Exception as e:
            logger.exception("Unexpected error updating schema.")
        return None

    # --- Versioned Document Upsert ---

    async def upsert_versioned_document(
        self,
        namespace: str,
        docname: str,
        data: wf_schemas.CustomerDataVersionedUpsert,
    ) -> Optional[wf_schemas.CustomerDataVersionedUpsertResponse]:
        """
        Tests upserting a versioned document via POST /customer-data/versioned/{namespace}/{docname}/upsert.
        This endpoint updates the document if it exists, or initializes it if it doesn't.
        It can target specific versions or the active version, and handle version creation if needed.

        Args:
            namespace (str): The namespace of the document.
            docname (str): The name of the document.
            data (wf_schemas.CustomerDataVersionedUpsert): The upsert payload containing data,
                versioning info, schema info, and other parameters.

        Returns:
            Optional[wf_schemas.CustomerDataVersionedUpsertResponse]: Response indicating the
                operation performed and document identifier if successful, None otherwise.
        """
        logger.info(f"Attempting to upsert versioned document: {namespace}/{docname} (target version: {data.version or 'active/default'})")
        url = VERSIONED_DOC_UPSERT_URL(namespace, docname)
        # Send model_dump directly as the request body
        payload = data.model_dump(exclude_none=True) # Exclude None values for cleaner payload
        logger.debug(f"Upsert payload: {json.dumps(payload, indent=2)}")

        try:
            response = await self._client.post(url, json=payload)

            # Upsert should return 200 OK on success (whether it updated or created)
            if response.status_code != 200:
                logger.error(f"Error upserting document: Status {response.status_code} - {response.text}")
                response.raise_for_status() # Raise for non-200 status codes

            response_json = response.json()
            validated_response = wf_schemas.CustomerDataVersionedUpsertResponse.model_validate(response_json)
            logger.info(f"Successfully upserted document: {namespace}/{docname}. Operation: {validated_response.operation_performed}")
            logger.debug(f"Upsert response validated: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            # Log specific details if available (e.g., 404, 409, 422 for validation)
            logger.error(f"HTTP Status Error upserting document: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error upserting document: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error upserting document: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error during document upsert.")
        return None

    # --- Unversioned Document Methods ---

    async def create_or_update_unversioned_document(
        self,
        namespace: str,
        docname: str,
        data: wf_schemas.CustomerDataUnversionedCreateUpdate,
    ) -> Optional[wf_schemas.CustomerDataUnversionedRead]:
        """
        Tests creating/updating an unversioned document via PUT /customer-data/unversioned/{namespace}/{docname}.
        """
        logger.info(f"Attempting to create/update unversioned document: {namespace}/{docname}")
        url = UNVERSIONED_DOC_URL(namespace, docname)
        # Send model_dump directly as the request body
        payload = data.model_dump()
        try:
            response = await self._client.put(url, json=payload)
            response.raise_for_status()
            response_json = response.json()
            validated_response = wf_schemas.CustomerDataUnversionedRead.model_validate(response_json)
            logger.info(f"Successfully created/updated unversioned document: {namespace}/{docname}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error creating/updating unversioned document: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error creating/updating unversioned document: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error creating/updating unversioned document: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error creating/updating unversioned document.")
        return None

    async def get_unversioned_document(
        self,
        namespace: str,
        docname: str,
        is_shared: bool,
        is_system_entity: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[wf_schemas.CustomerDataUnversionedRead]:
        """
        Tests getting an unversioned document via GET /customer-data/unversioned/{namespace}/{docname}.
        
        Args:
            namespace (str): The namespace of the document.
            docname (str): The name of the document.
            is_shared (bool): Whether this is a shared document.
            is_system_entity (bool): Whether this is a system entity (superusers only). When True, data is accessed from 
                                     system paths instead of organization-specific paths. The is_shared parameter 
                                     still applies normally to determine if it's shared with the org or user-specific.
            on_behalf_of_user_id (Optional[uuid.UUID]): Optional user ID to act on behalf of (superusers only).
                                                       Note: This parameter won't work if accessing system entities or
                                                       shared documents, as these are not tied to specific users.
            
        Returns:
            Optional[wf_schemas.CustomerDataUnversionedRead]: Document data if successful, None otherwise.
        """
        logger.info(f"Attempting to get unversioned document: {namespace}/{docname} (shared={is_shared})")
        url = UNVERSIONED_DOC_URL(namespace, docname)
        params = {"is_shared": is_shared}
        if is_system_entity:
            params["is_system_entity"] = is_system_entity
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            response_json = response.json()
            validated_response = wf_schemas.CustomerDataUnversionedRead.model_validate(response_json)
            logger.info(f"Successfully retrieved unversioned document: {namespace}/{docname}")
            logger.debug(f"Get response validated: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting unversioned document: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting unversioned document: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error getting unversioned document: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error getting unversioned document.")
        return None

    async def delete_unversioned_document(
        self,
        namespace: str,
        docname: str,
        is_shared: bool,
        is_system_entity: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """
        Tests deleting an unversioned document via DELETE /customer-data/unversioned/{namespace}/{docname}.
        
        Args:
            namespace (str): The namespace of the document.
            docname (str): The name of the document.
            is_shared (bool): Whether this is a shared document.
            is_system_entity (bool): Whether this is a system entity (superusers only). When True, data is deleted from 
                                     system paths instead of organization-specific paths. The is_shared parameter 
                                     still applies normally to determine if it's shared with the org or user-specific.
            on_behalf_of_user_id (Optional[uuid.UUID]): Optional user ID to act on behalf of (superusers only).
                                                       Note: This parameter won't work if accessing system entities or
                                                       shared documents, as these are not tied to specific users.
            
        Returns:
            bool: True if deletion was successful, False otherwise.
        """
        logger.info(f"Attempting to delete unversioned document: {namespace}/{docname} (shared={is_shared})")
        url = UNVERSIONED_DOC_URL(namespace, docname)
        params = {"is_shared": is_shared}
        if is_system_entity:
            params["is_system_entity"] = is_system_entity
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
        try:
            response = await self._client.delete(url, params=params)
            response.raise_for_status() # Raises for non-2xx
            logger.info(f"Successfully deleted unversioned document: {namespace}/{docname}")
            return response.status_code == 204 # Check for No Content
        except httpx.HTTPStatusError as e:
            logger.error(f"Error deleting unversioned document: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error deleting unversioned document: {e}")
        except Exception as e:
            logger.exception("Unexpected error deleting unversioned document.")
        return False

    # --- List Documents ---

    async def list_documents(
        self,
        namespace: Optional[str] = None,
        include_shared: bool = True,
        include_user_specific: bool = True,
        skip: int = 0,
        limit: int = 100,
        include_system_entities: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[List[wf_schemas.CustomerDocumentMetadata]]:
        """
        Tests listing documents via GET /customer-data/list.
        
        Args:
            namespace (Optional[str]): Filter by namespace.
            include_shared (bool): Include shared documents.
            include_user_specific (bool): Include user-specific documents.
            skip (int): Number of documents to skip.
            limit (int): Maximum number of documents to return.
            include_system_entities (bool): Include system entities (superusers only). When True, documents from 
                                           system paths are included along with organization-specific paths. 
                                           System documents use a separate storage path from regular organization 
                                           documents but still respect the is_shared flag for access control.
            on_behalf_of_user_id (Optional[uuid.UUID]): Optional user ID to act on behalf of (superusers only).
                                                       Note: This parameter only affects user-specific documents,
                                                       not shared documents or system entities. It lets superusers
                                                       view documents belonging to a specific user.
            
        Returns:
            Optional[List[wf_schemas.CustomerDocumentMetadata]]: List of document metadata if successful, None otherwise.
        """
        logger.info(f"Attempting to list documents (namespace filter: {namespace})")
        url = LIST_DOCUMENTS_URL
        
        params: Dict[str, Any] = {
            "include_shared": include_shared,
            "include_user_specific": include_user_specific,
            "skip": skip,
            "limit": limit,
        }
        
        if namespace:
            params["namespace"] = namespace
        if include_system_entities:
            params["include_system_entities"] = include_system_entities
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
            
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            response_json = response.json()
            # Use Pydantic to validate a list of CustomerDocumentMetadata objects
            CustomerDocumentMetadataListAdapter = TypeAdapter(List[wf_schemas.CustomerDocumentMetadata])
            validated_response = CustomerDocumentMetadataListAdapter.validate_python(response_json)
            logger.info(f"Successfully listed {len(validated_response)} documents")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing documents: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error listing documents: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error listing documents: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error listing documents.")
        return None

    async def get_document_metadata(
        self,
        namespace: str,
        docname: str,
        is_system_entity: bool = False,
        is_shared: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
    ) -> Optional[wf_schemas.CustomerDocumentMetadata]:
        """
        Tests retrieving metadata for a document via GET /customer-data/metadata/{namespace}/{docname}.
        
        Args:
            namespace (str): The namespace of the document.
            docname (str): The name of the document.
            is_system_entity (bool): Whether this is a system entity (superusers only). When True, data is stored in 
                                     system paths instead of organization-specific paths. The is_shared parameter in the
                                     query still applies normally to determine if it's shared with the org or user-specific.
            is_shared (bool): Whether this is a shared document.
            on_behalf_of_user_id (Optional[uuid.UUID]): Optional user ID to act on behalf of (superusers only).
                                                       Note: This parameter won't work if accessing system entities or
                                                       shared documents, as these are not tied to specific users.
            
        Returns:
            Optional[wf_schemas.CustomerDocumentMetadata]: Document metadata if successful, None otherwise.
        """
        logger.info(f"Attempting to get metadata for document: {namespace}/{docname}")
        url = DOCUMENT_METADATA_URL(namespace, docname)
        
        params: Dict[str, Any] = {}
        if is_system_entity:
            params["is_system_entity"] = is_system_entity
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
        params["is_shared"] = is_shared
            
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            response_json = response.json()
            validated_response = wf_schemas.CustomerDocumentMetadata.model_validate(response_json)
            logger.info(f"Successfully retrieved metadata for document: {namespace}/{docname}")
            logger.debug(f"Metadata: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting document metadata: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting document metadata: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error getting document metadata: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error getting document metadata.")
        return None
            
    async def delete_objects_by_pattern(
        self,
        namespace: str,
        docname: str,
        is_shared: bool = False,
        is_system_entity: bool = False,
        on_behalf_of_user_id: Optional[uuid.UUID] = None,
        dry_run: bool = False,
    ) -> Optional[wf_schemas.CustomerDataDeleteResponse]:
        """
        Delete multiple objects matching a pattern.
        
        Args:
            namespace: Namespace pattern with wildcards (e.g., "invoices*")
            docname: Document name pattern with wildcards (e.g., "2023*")
            is_shared: Whether to delete shared documents
            is_system_entity: Whether to delete system entities (superusers only)
            on_behalf_of_user_id: Optional user ID to act on behalf of (superusers only)
            dry_run: If true, only returns count without deleting anything
            
        Returns:
            CustomerDataDeleteResponse with count of deleted documents, or None if error
        """
        logger.info(f"Attempting to delete objects by pattern: namespace={namespace}, docname={docname}, shared={is_shared}, dry_run={dry_run}")
        url = DELETE_BY_PATTERN_URL
        data = {
            "is_shared": is_shared,
            "namespace": namespace,
            "docname": docname,
            "is_system_entity": is_system_entity,
            "dry_run": dry_run,
        }
        
        if on_behalf_of_user_id:
            data["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
            
        try:
            response = await self._client.request("DELETE", url, json=data)
            response.raise_for_status()
            response_json = response.json()
            validated_response = wf_schemas.CustomerDataDeleteResponse.model_validate(response_json)
            logger.info(f"Successfully deleted objects by pattern. Count: {validated_response.deleted_count}, Dry Run: {validated_response.dry_run}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Status Error deleting objects by pattern: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error deleting objects by pattern: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error deleting objects by pattern: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error deleting objects by pattern")
        return None

    async def search_documents(
        self,
        query: wf_schemas.CustomerDataSearchQuery,
    ) -> Optional[List[wf_schemas.CustomerDocumentSearchResult]]:
        """
        Tests searching documents via POST /customer-data/search.

        Args:
            query (wf_schemas.CustomerDataSearchQuery): The search query parameters.

        Returns:
            Optional[List[wf_schemas.CustomerDocumentSearchResult]]: List of search results if successful, None otherwise.
        """
        logger.info(f"Attempting to search documents with query: {query.model_dump_json(indent=2)}")
        url = SEARCH_DOCUMENTS_URL # Defined in test_config.py
        payload = query.model_dump(exclude_none=True) # Exclude None values for a cleaner payload

        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status() # Raise for non-2xx status codes

            response_json = response.json()
            validated_response = CustomerDocumentSearchResultListAdapter.validate_python(response_json)
            logger.info(f"Successfully searched and validated {len(validated_response)} documents.")
            logger.debug(f"Search response validated: {validated_response}") # May be long
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Status Error searching documents: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error searching documents: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error searching documents: {e}")
            logger.debug(f"Invalid response JSON: {response_json if 'response_json' in locals() else 'No response JSON'}")
        except Exception as e:
            logger.exception("Unexpected error during document search.")
        return None

    # --- File Upload Methods ---

    async def upload_files(
        self,
        files: List[Tuple[str, bytes, str]],  # (filename, content, content_type)
        config_payload: Optional[Union[wf_schemas.FileUploadRequestPayload, str]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Upload multiple files to the customer data service.
        
        Args:
            files: List of tuples containing (filename, file_content_bytes, content_type)
            config_payload: FileUploadRequestPayload or JSON string containing upload configuration
            
        Returns:
            List of upload results if successful, None otherwise
        """
        logger.info(f"Attempting to upload {len(files)} files")
        
        # Prepare config payload
        if config_payload:
            if isinstance(config_payload, wf_schemas.FileUploadRequestPayload):
                config_json = config_payload.model_dump_json()
            else:
                config_json = config_payload
        else:
            config_json = "{}"
        
        try:
            # Manual multipart encoding - the only approach that works with FastAPI List[UploadFile]
            # httpx's built-in multipart handling doesn't work correctly with FastAPI
            import time
            boundary = f"----formdata-httpx-{int(time.time() * 1000000)}"
            
            # Build multipart body manually
            multipart_body = b''
            
            # Add config_payload field
            config_part = f'--{boundary}\r\nContent-Disposition: form-data; name="config_payload"\r\n\r\n{config_json}\r\n'
            multipart_body += config_part.encode('utf-8')
            
            # Add each file with the same field name "files"
            for filename, content, content_type in files:
                file_part_header = f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'
                multipart_body += file_part_header.encode('utf-8')
                multipart_body += content
                multipart_body += b'\r\n'
            
            # Add final boundary
            multipart_body += f'--{boundary}--\r\n'.encode('utf-8')
            
            response = await self._client.post(
                FILE_UPLOAD_URL,
                content=multipart_body,
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
            )
            response.raise_for_status()
            
            response_json = response.json()
            logger.info(f"Successfully uploaded {len(files)} files")
            return response_json
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Status Error uploading files: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error uploading files: {e}")
        except Exception as e:
            logger.exception("Unexpected error during file upload")
        return None

    async def validate_upload_config(
        self,
        config_payload: wf_schemas.FileUploadValidationRequest,
    ) -> Optional[wf_schemas.FileUploadValidationResult]:
        """
        Validate file upload configuration without actually uploading files.
        
        Args:
            config_payload: FileUploadValidationRequest containing config and file list
            
        Returns:
            FileUploadValidationResult if successful, None otherwise
        """
        logger.info(f"Validating upload config for {len(config_payload.files)} files")
        
        try:
            response = await self._client.post(
                FILE_UPLOAD_VALIDATION_URL,
                json=config_payload.model_dump()
            )
            response.raise_for_status()
            
            response_json = response.json()
            validated_response = wf_schemas.FileUploadValidationResult.model_validate(response_json)
            logger.info(f"Upload config validation completed. Valid: {validated_response.is_valid}")
            return validated_response
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Status Error validating upload config: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error validating upload config: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error: {e}")
        except Exception as e:
            logger.exception("Unexpected error during upload config validation")
        return None

    async def upload_file_from_path(
        self,
        file_path: str,
        config_payload: Optional[Union[wf_schemas.FileUploadRequestPayload, str]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Upload a single file from a file path.
        
        Args:
            file_path: Path to the file to upload
            config_payload: FileUploadRequestPayload or JSON string containing upload configuration
            
        Returns:
            List containing single upload result if successful, None otherwise
        """
        import mimetypes
        from pathlib import Path
        
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            logger.error(f"File not found: {file_path}")
            return None
        
        # Read file content
        try:
            with open(file_path_obj, "rb") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return None
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = "application/octet-stream"
        
        # Upload the file
        return await self.upload_files(
            files=[(file_path_obj.name, content, content_type)],
            config_payload=config_payload
        )


# --- Example Usage ---
async def main():
    """Demonstrates using the CustomerDataTestClient."""
    print("--- Starting Customer Data API Test --- ")
    test_ns = f"test_ns_{uuid.uuid4().hex[:6]}"
    v_doc_name_json = f"versioned_json_{uuid.uuid4().hex[:6]}"
    v_doc_name_str = f"versioned_str_{uuid.uuid4().hex[:6]}"
    uv_doc_name_json = f"unversioned_json_{uuid.uuid4().hex[:6]}"
    uv_doc_name_int = f"unversioned_int_{uuid.uuid4().hex[:6]}"
    schema_template_name = f"cust_data_test_schema_{uuid.uuid4().hex[:6]}"
    schema_template_version = "1.0.0"
    temp_schema_template_id: Optional[uuid.UUID] = None

    # List to keep track of created documents for cleanup
    created_docs_for_cleanup = []

    # Flag to control cleanup
    cleanup_successful = True
    
    try:
        async with AuthenticatedClient() as auth_client:
            print("Authenticated.")
            data_tester = CustomerDataTestClient(auth_client)
            template_tester = TemplateTestClient(auth_client) # Instantiate template client

            # --- Setup: Create Schema Template ---
            print(f"\n--- Setup: Creating Schema Template: {schema_template_name} v{schema_template_version} ---")
            test_json_schema = {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "The primary key"},
                    "count": {"type": "integer", "description": "A counter value"},
                    "nested": {
                        "type": "object",
                        "properties": {"flag": {"type": "boolean"}},
                        "required": ["flag"] # Make nested flag required
                    },
                    "optional_field": {"type": "string"}
                },
                "required": ["key", "count"],
                "additionalProperties": False # 'nested' is optional at top level
            }
            schema_create_payload = wf_schemas.SchemaTemplateCreate(
                name=schema_template_name,
                version=schema_template_version,
                description="Schema for customer data client tests (JSON)",
                schema_definition=test_json_schema,
                schema_type=wf_schemas.SchemaType.JSON_SCHEMA,
                is_public=False, # Org-specific
                is_system_entity=False
            )
            created_schema_template = await template_tester.create_schema_template(schema_create_payload)
            assert created_schema_template is not None, "Failed to create schema template"
            temp_schema_template_id = created_schema_template.id # Store for cleanup
            print(f"   ✓ Created Schema Template ID: {temp_schema_template_id}")


            # --- Versioned Document Tests (JSON) ---
            print(f"\n--- Testing Versioned Document (JSON): {test_ns}/{v_doc_name_json} ---")

            # 1. Initialize (User Specific, JSON)
            init_data_json = wf_schemas.CustomerDataVersionedInitialize(
                is_shared=False,
                initial_data={"key": "value1", "count": 0},
                initial_version="v1.0"
            )
            init_result_json = await data_tester.initialize_versioned_document(test_ns, v_doc_name_json, init_data_json)
            created_docs_for_cleanup.append({
                "namespace": test_ns, "docname": v_doc_name_json, 
                "is_shared": False, "is_versioned": True
            })
            assert init_result_json is not None, "Initialization failed, expected a result."
            expected_init_data = {"key": "value1", "count": 0}
            assert {k: v for k,v in init_result_json.data.items() if k not in ["created_at", "updated_at"]} == expected_init_data, \
                   f"Initialized data mismatch. Expected: {expected_init_data}, Got: {init_result_json.data}"
            print("   ✓ Initialized user-specific JSON document.")
            
            # 1a. Apply Schema to Versioned Document
            print(f"   Applying schema '{schema_template_name}' to versioned doc...")
            schema_update_payload = wf_schemas.CustomerDataSchemaUpdate(
                is_shared=False,
                schema_template_name=schema_template_name,
                schema_template_version=schema_template_version
                # Alternatively, could provide schema_content directly
            )
            applied_schema = await data_tester.update_versioned_document_schema(test_ns, v_doc_name_json, schema_update_payload)
            assert applied_schema is not None, "Failed to apply schema to versioned document"
            assert applied_schema == test_json_schema, "Applied schema content doesn't match expected"
            print("   ✓ Applied schema to versioned document.")

            # 2. Get (User Specific, JSON, version v1.0)
            get_result_json = await data_tester.get_versioned_document(test_ns, v_doc_name_json, is_shared=False, version="v1.0")
            assert get_result_json is not None, "Get document failed, expected a result."
            assert {k: v for k,v in get_result_json.data.items() if k not in ["created_at", "updated_at"]} == expected_init_data, \
                   f"Get document data mismatch. Expected: {expected_init_data}, Got: {get_result_json.data}"
            print("   ✓ Got user-specific JSON document v1.0.")

            # 3. Update (Valid Full, User Specific, JSON, version v1.0) - Should pass schema
            update_payload_json = {"key": "value_updated", "count": 1, "nested": {"flag": True}}
            update_data_json = wf_schemas.CustomerDataVersionedUpdate(
                is_shared=False,
                data=update_payload_json,
                version="v1.0"
            )
            update_result_json = await data_tester.update_versioned_document(test_ns, v_doc_name_json, update_data_json)
            assert update_result_json is not None, "Update document failed, expected a result."
            assert {k: v for k,v in update_result_json.data.items() if k not in ["created_at", "updated_at"]} == update_payload_json, \
                   f"Updated data mismatch. Expected: {update_payload_json}, Got: {update_result_json.data}"
            print("   ✓ Updated (Valid Full) user-specific JSON document v1.0 - Schema OK.")

            # 3a. Update (Invalid Full, User Specific, JSON, version v1.0) - Missing required 'key'
            print("   Testing Invalid Full Update (non-existent-key 'non-existent-key')...")
            update_invalid_payload_missing = {"non-existent-key": "value", "nested": {"flag": False}}
            update_invalid_data_missing = wf_schemas.CustomerDataVersionedUpdate(
                is_shared=False, data=update_invalid_payload_missing, version="v1.0"
            )
            update_invalid_result_missing = await data_tester.update_versioned_document(test_ns, v_doc_name_json, update_invalid_data_missing)
            print(f"   ✗ Invalid Full Update (non-existent-key 'non-existent-key') result: {update_invalid_result_missing}")
            assert update_invalid_result_missing is None, "Expected invalid update (missing key) to fail"
            print("   ✓ Invalid Full Update (missing 'key') correctly failed.")

            # 3b. Update (Invalid Full, User Specific, JSON, version v1.0) - Wrong type for 'count'
            print("   Testing Invalid Full Update (wrong type for 'count')...")
            update_invalid_payload_type = {"key": "another_key", "count": "not_an_integer", "nested": {"flag": True}}
            update_invalid_data_type = wf_schemas.CustomerDataVersionedUpdate(
                is_shared=False, data=update_invalid_payload_type, version="v1.0"
            )
            update_invalid_result_type = await data_tester.update_versioned_document(test_ns, v_doc_name_json, update_invalid_data_type)
            assert update_invalid_result_type is None, "Expected invalid update (wrong type) to fail"
            print("   ✓ Invalid Full Update (wrong type) correctly failed.")

            # 3c. Update (Valid Partial, User Specific, JSON, version v1.0) - Update only 'count'
            print("   Testing Valid Partial Update (only 'count')...")
            # Fetch current data first to simulate partial update
            current_data_for_partial = await data_tester.get_versioned_document(test_ns, v_doc_name_json, is_shared=False, version="v1.0")
            assert current_data_for_partial is not None, "Failed to get data for partial update"
            partial_update_payload_valid = current_data_for_partial.data.copy() # Get existing data
            partial_update_payload_valid["count"] = 99 # Modify only count
            # Add an optional field
            partial_update_payload_valid["optional_field"] = "partial update value"

            update_partial_valid_data = wf_schemas.CustomerDataVersionedUpdate(
                is_shared=False, data={k: v for k,v in partial_update_payload_valid.items() if k not in ["created_at", "updated_at"]}, version="v1.0"
            )
            update_partial_valid_result = await data_tester.update_versioned_document(test_ns, v_doc_name_json, update_partial_valid_data)
            assert update_partial_valid_result is not None, "Expected valid partial update to succeed"
            assert update_partial_valid_result.data["count"] == 99, "Valid partial update 'count' failed"
            assert update_partial_valid_result.data["key"] == "value_updated", "Valid partial update modified 'key' unexpectedly"
            assert update_partial_valid_result.data["optional_field"] == "partial update value", "Valid partial update 'optional_field' failed"
            print("   ✓ Valid Partial Update (only 'count' + optional) succeeded.")

            # 3d. Update (Invalid Partial, User Specific, JSON, version v1.0) - Change 'count' to wrong type
            print("   Testing Invalid Partial Update ('count' wrong type)...")
            # Fetch current data again
            current_data_for_partial_invalid = await data_tester.get_versioned_document(test_ns, v_doc_name_json, is_shared=False, version="v1.0")
            assert current_data_for_partial_invalid is not None
            partial_update_payload_invalid = current_data_for_partial_invalid.data.copy()
            partial_update_payload_invalid["count"] = "ninety-nine" # Invalid type

            update_partial_invalid_data = wf_schemas.CustomerDataVersionedUpdate(
                is_shared=False, data=partial_update_payload_invalid, version="v1.0"
            )
            update_partial_invalid_result = await data_tester.update_versioned_document(test_ns, v_doc_name_json, update_partial_invalid_data)
            assert update_partial_invalid_result is None, "Expected invalid partial update (wrong type) to fail"
            print("   ✓ Invalid Partial Update (wrong type) correctly failed.")


            # 4. Get History (JSON, version v1.0)
            history_json = await data_tester.get_version_history(test_ns, v_doc_name_json, is_shared=False, version="v1.0")
            assert history_json is not None, "Get history failed, expected a result."
            assert len(history_json) >= 2, f"Expected at least 2 history items, got {len(history_json)}"
            print(f"   ✓ Got history for JSON v1.0 ({len(history_json)} items).")
            # Simple check on patch structure (might need more robust validation)
            try:
                patch_content = json.loads(history_json[-1].patch)
                assert isinstance(patch_content, list) and len(patch_content) > 0 and 'op' in patch_content[0], \
                       f"Last history patch content seems invalid: {patch_content}"
            except (json.JSONDecodeError, IndexError, KeyError) as e:
                assert False, f"Error validating last history patch structure: {e}, Patch: {history_json[-1].patch}"

            # 5. Create Version (v1.1 from v1.0, JSON)
            create_version_data_json = wf_schemas.CustomerDataCreateVersion(is_shared=False, new_version="v1.1", from_version="v1.0")
            created_version_info_json = await data_tester.create_versioned_document_version(test_ns, v_doc_name_json, create_version_data_json)
            assert created_version_info_json is not None, "Create version failed, expected a result."
            assert created_version_info_json.version == "v1.1", \
                   f"Created version name mismatch. Expected: v1.1, Got: {created_version_info_json.version}"
            print("   ✓ Created version v1.1 (JSON).")

            # 6. List Versions (JSON)
            versions_json = await data_tester.list_versioned_document_versions(test_ns, v_doc_name_json, is_shared=False)
            assert versions_json is not None, "List versions failed, expected a result."
            version_names = [v.version for v in versions_json]
            assert len(versions_json) >= 2, f"Expected at least 2 versions, got {len(versions_json)}: {version_names}"
            assert "v1.0" in version_names, f"Expected 'v1.0' in listed versions: {version_names}"
            assert "v1.1" in version_names, f"Expected 'v1.1' in listed versions: {version_names}"
            print(f"   ✓ Listed JSON versions: {version_names}.")

            # 7. Set Active Version (to v1.1, JSON)
            set_active_data_json = wf_schemas.CustomerDataSetActiveVersion(is_shared=False, version="v1.1")
            active_version_info_json = await data_tester.set_active_version(test_ns, v_doc_name_json, set_active_data_json)
            assert active_version_info_json is not None, "Set active version failed, expected a result."
            assert active_version_info_json.is_active, f"Expected version v1.1 to be active, but it wasn't. Info: {active_version_info_json}"
            assert active_version_info_json.version == "v1.1", f"Expected active version to be v1.1, got {active_version_info_json.version}"
            print("   ✓ Set v1.1 as active (JSON).")

            # 8. Update Active Version (v1.1, JSON)
            update_active_payload_json = {"key": "value_v1.1", "count": 2}
            update_active_data_json = wf_schemas.CustomerDataVersionedUpdate(
                is_shared=False,
                data=update_active_payload_json # No version specified
            )
            update_active_result_json = await data_tester.update_versioned_document(test_ns, v_doc_name_json, update_active_data_json)
            assert update_active_result_json is not None, "Update active version failed, expected a result."
            expected_update_response = {'nested': {'flag': True}, 'optional_field': 'partial update value'} | update_active_payload_json
            assert {k: v for k,v in update_active_result_json.data.items() if k not in ["created_at", "updated_at"]} == expected_update_response, \
                   f"Update active data mismatch. Expected: {expected_update_response}, Got: {update_active_result_json.data}"
            print("   ✓ Updated active version (v1.1, JSON).")
            
            # 8a. Restore document to sequence 0 (initial state)
            restore_data = wf_schemas.CustomerDataVersionedRestore(is_shared=False, sequence=0, version="v1.0")
            restore_result = await data_tester.restore_document(test_ns, v_doc_name_json, restore_data)
            assert restore_result is not None, "Restore document failed, expected a result."
            assert {k: v for k,v in restore_result.data.items() if k not in ["created_at", "updated_at"]} == expected_init_data, \
                   f"Restored data mismatch. Expected: {expected_init_data}, Got: {restore_result.data}" # Check if back to initial state
            print("   ✓ Restored JSON document v1.0 to initial state (seq 0).")


            # --- Versioned Document Tests (String Primitive) ---
            print(f"\n--- Testing Versioned Document (String): {test_ns}/{v_doc_name_str} ---")

            # 9. Initialize (Shared, String)
            init_payload_str = "Initial string value"
            init_data_str = wf_schemas.CustomerDataVersionedInitialize(
                is_shared=True,
                initial_data=init_payload_str,
                initial_version="vA"
            )
            init_result_str = await data_tester.initialize_versioned_document(test_ns, v_doc_name_str, init_data_str)
            created_docs_for_cleanup.append({
                "namespace": test_ns, "docname": v_doc_name_str,
                "is_shared": True, "is_versioned": True
            })
            assert init_result_str is not None, "Initialize string doc failed, expected a result."
            assert init_result_str.data == init_payload_str, \
                   f"Initialized string data mismatch. Expected: {init_payload_str}, Got: {init_result_str.data}"
            print("   ✓ Initialized shared string document.")
            

            # 10. Get (Shared, String, version vA)
            get_result_str = await data_tester.get_versioned_document(test_ns, v_doc_name_str, is_shared=True, version="vA")
            assert get_result_str is not None, "Get string doc failed, expected a result."
            assert get_result_str.data == init_payload_str, \
                   f"Get string data mismatch. Expected: {init_payload_str}, Got: {get_result_str.data}"
            print("   ✓ Got shared string document vA.")

            # 11. Update (Shared, String, version vA)
            update_payload_str = "Updated string value for vA"
            update_data_str = wf_schemas.CustomerDataVersionedUpdate(
                is_shared=True,
                data=update_payload_str,
                version="vA"
            )
            update_result_str = await data_tester.update_versioned_document(test_ns, v_doc_name_str, update_data_str)
            assert update_result_str is not None, "Update string doc failed, expected a result."
            assert update_result_str.data == update_payload_str, \
                   f"Updated string data mismatch. Expected: {update_payload_str}, Got: {update_result_str.data}"
            print("   ✓ Updated shared string document vA.")
            
            # 12. Get History (String, version vA)
            history_str = await data_tester.get_version_history(test_ns, v_doc_name_str, is_shared=True, version="vA")
            assert history_str is not None, "Get string history failed, expected a result."
            assert len(history_str) >= 2, f"Expected at least 2 history items for string, got {len(history_str)}" # Init + Update
            print(f"   ✓ Got history for String vA ({len(history_str)} items).")
            # Check primitive flag in history
            assert any(h.is_primitive for h in history_str), f"Expected at least one history item to have is_primitive=True. History: {history_str}"


            # --- Unversioned Document Tests (JSON) ---
            print(f"\n--- Testing Unversioned Document (JSON): {test_ns}/{uv_doc_name_json} ---")

            # 13. Create/Update Unversioned (Shared, JSON)
            uv_create_payload_json = {"config": "shared_config_value", "items": [1, 2]}
            uv_create_data_json = wf_schemas.CustomerDataUnversionedCreateUpdate(
                is_shared=True,
                data=uv_create_payload_json
            )
            uv_create_result_json = await data_tester.create_or_update_unversioned_document(test_ns, uv_doc_name_json, uv_create_data_json)
            created_docs_for_cleanup.append({
                "namespace": test_ns, "docname": uv_doc_name_json,
                "is_shared": True, "is_versioned": False
            })

            assert uv_create_result_json is not None, "Create unversioned JSON failed, expected result."
            assert {k: v for k,v in uv_create_result_json.data.items() if k not in ["created_at", "updated_at"]} == uv_create_payload_json, \
                   f"Create unversioned JSON data mismatch. Expected: {uv_create_payload_json}, Got: {uv_create_result_json.data}"
            print("   ✓ Created/Updated shared unversioned JSON document.")
            
            # 13a. Update Unversioned (Shared, JSON) - Make it conform to schema
            print("   Updating unversioned doc to conform to schema...")
            uv_conform_payload_json = {"key": "uv_key", "count": 10, "optional_field": "optional_value"} # 'config' is not in schema, should be ignored or error depending on backend strictness
            uv_conform_data_json = wf_schemas.CustomerDataUnversionedCreateUpdate(
                is_shared=True,
                data=uv_conform_payload_json,
                schema_template_name=schema_template_name,
                schema_template_version=schema_template_version,
            )
            uv_conform_result_json = await data_tester.create_or_update_unversioned_document(test_ns, uv_doc_name_json, uv_conform_data_json)
            # Assertion depends on whether backend validation is strict for extra fields.
            # If strict=False (default for Pydantic usually), extra fields are ignored.
            # If strict=True or backend uses other validation, this might fail.
            # Let's assume non-strict validation for now.
            assert uv_conform_result_json is not None, "Update unversioned JSON to conform failed, expected result."
            # Check if the expected *schema* fields are present and correct
            assert uv_conform_result_json.data.get("key") == "uv_key", "Unversioned conforming update 'key' mismatch"
            assert uv_conform_result_json.data.get("count") == 10, "Unversioned conforming update 'count' mismatch"
            print("   ✓ Updated unversioned JSON document to likely conform.")

            # 13b. Update Unversioned (Invalid - Missing required 'count', Shared, JSON)
            print("   Testing Invalid Unversioned Update (missing 'count')...")
            uv_invalid_payload_missing = {"key": "uv_key_invalid"} # Missing 'count'
            uv_invalid_data_missing = wf_schemas.CustomerDataUnversionedCreateUpdate(
                is_shared=True, data=uv_invalid_payload_missing,
                schema_template_name=schema_template_name,
                schema_template_version=schema_template_version,
            )
            uv_invalid_result_missing = await data_tester.create_or_update_unversioned_document(test_ns, uv_doc_name_json, uv_invalid_data_missing)
            assert uv_invalid_result_missing is None, "Expected invalid unversioned update (missing count) to fail"
            print("   ✓ Invalid Unversioned Update (missing 'count') correctly failed (assuming schema is applied).")

            # 13c. Update Unversioned (Valid Partial - update 'count', Shared, JSON)
            print("   Testing Valid Partial Unversioned Update...")
            current_uv_data = await data_tester.get_unversioned_document(test_ns, uv_doc_name_json, is_shared=True)
            assert current_uv_data is not None
            uv_partial_valid_payload = current_uv_data.data.copy()
            uv_partial_valid_payload["count"] = 11 # Update count
            uv_partial_valid_data = wf_schemas.CustomerDataUnversionedCreateUpdate(
                is_shared=True, data=uv_partial_valid_payload
            )
            uv_partial_valid_result = await data_tester.create_or_update_unversioned_document(test_ns, uv_doc_name_json, uv_partial_valid_data)
            assert uv_partial_valid_result is not None, "Expected valid partial unversioned update to succeed"
            assert uv_partial_valid_result.data["count"] == 11, "Valid partial unversioned update 'count' mismatch"
            print("   ✓ Valid Partial Unversioned Update succeeded.")

            # 14. Get Unversioned (Shared, JSON)
            uv_get_result_json = await data_tester.get_unversioned_document(test_ns, uv_doc_name_json, is_shared=True)
            assert uv_get_result_json is not None, "Get unversioned JSON failed, expected result."
            # NOTE: subfields are updated when we update an existing document!
            expected_uv_data = {'config': 'shared_config_value', 'items': [1, 2], 'count': 11, 'key': 'uv_key', 'optional_field': 'optional_value'}
            assert {k: v for k,v in uv_get_result_json.data.items() if k not in ["created_at", "updated_at"]} == expected_uv_data, \
                   f"Get unversioned JSON data mismatch. Expected: {expected_uv_data}, Got: {uv_get_result_json.data}"
            print("   ✓ Got shared unversioned JSON document.")

            # 15. Update Unversioned (Shared, JSON)
            uv_update_payload_json = {"config": "updated_shared_value", "new_field": True}
            uv_update_data_json = wf_schemas.CustomerDataUnversionedCreateUpdate(
                is_shared=True,
                data=uv_update_payload_json # Full replacement
            )
            uv_update_result_json = await data_tester.create_or_update_unversioned_document(test_ns, uv_doc_name_json, uv_update_data_json)
            assert uv_update_result_json is not None, "Update unversioned JSON failed, expected result."
            assert {k: v for k,v in uv_update_result_json.data.items() if k not in ["created_at", "updated_at"]} == uv_update_payload_json, \
                   f"Update unversioned JSON data mismatch. Expected: {uv_update_payload_json}, Got: {uv_update_result_json.data}"
            print("   ✓ Updated shared unversioned JSON document.")

            # --- Unversioned Document Tests (Integer Primitive) ---
            print(f"\n--- Testing Unversioned Document (Integer): {test_ns}/{uv_doc_name_int} ---")

            # 16. Create/Update Unversioned (User Specific, Integer)
            uv_create_payload_int = 12345
            uv_create_data_int = wf_schemas.CustomerDataUnversionedCreateUpdate(
                is_shared=False,
                data=uv_create_payload_int
            )
            uv_create_result_int = await data_tester.create_or_update_unversioned_document(test_ns, uv_doc_name_int, uv_create_data_int)
            created_docs_for_cleanup.append({
                "namespace": test_ns, "docname": uv_doc_name_int,
                "is_shared": False, "is_versioned": False
            })
            assert uv_create_result_int is not None, "Create unversioned Int failed, expected result."
            assert uv_create_result_int.data == uv_create_payload_int, \
                   f"Create unversioned Int data mismatch. Expected: {uv_create_payload_int}, Got: {uv_create_result_int.data}"
            print("   ✓ Created/Updated user-specific unversioned integer document.")

            # 17. Get Unversioned (User Specific, Integer)
            uv_get_result_int = await data_tester.get_unversioned_document(test_ns, uv_doc_name_int, is_shared=False)
            assert uv_get_result_int is not None, "Get unversioned Int failed, expected result."
            assert uv_get_result_int.data == uv_create_payload_int, \
                   f"Get unversioned Int data mismatch. Expected: {uv_create_payload_int}, Got: {uv_get_result_int.data}"
            print("   ✓ Got user-specific unversioned integer document.")

            # 18. Update Unversioned (User Specific, Integer)
            uv_update_payload_int = 54321
            uv_update_data_int = wf_schemas.CustomerDataUnversionedCreateUpdate(
                is_shared=False,
                data=uv_update_payload_int
            )
            uv_update_result_int = await data_tester.create_or_update_unversioned_document(test_ns, uv_doc_name_int, uv_update_data_int)
            assert uv_update_result_int is not None, "Update unversioned Int failed, expected result."
            assert uv_update_result_int.data == uv_update_payload_int, \
                   f"Update unversioned Int data mismatch. Expected: {uv_update_payload_int}, Got: {uv_update_result_int.data}"
            print("   ✓ Updated user-specific unversioned integer document.")


            # --- List Documents ---
            print("\n--- Testing Document Listing ---")

            # 19. List all documents
            all_docs = await data_tester.list_documents()
            assert all_docs is not None, "List documents returned None, expected a list."
            doc_paths = [(d.namespace, d.docname, d.is_shared) for d in all_docs]
            # Check presence of all created test documents
            expected_paths = [
                (test_ns, v_doc_name_json, False), # User-specific versioned JSON
                (test_ns, v_doc_name_str, True),   # Shared versioned String
                (test_ns, uv_doc_name_json, True),  # Shared unversioned JSON
                (test_ns, uv_doc_name_int, False) # User-specific unversioned Int
            ]
            for expected_path in expected_paths:
                assert expected_path in doc_paths, f"Expected path {expected_path} not found in listed documents: {doc_paths}"
            
            print(f"   ✓ Listed documents (found {len(all_docs)}):")
            for doc in all_docs:
                 if doc.namespace == test_ns: # Only print test docs
                    print(f"     - {doc.namespace}/{doc.docname} (Shared: {doc.is_shared}, Versioned: {doc.is_versioned})")

            # 20. List documents in the test namespace
            ns_docs = await data_tester.list_documents(namespace=test_ns)
            assert ns_docs is not None, f"List documents with namespace '{test_ns}' returned None."
            # Check count specifically for the created namespace
            assert len(ns_docs) >= 4, f"Expected at least 4 documents in namespace '{test_ns}', found {len(ns_docs)}: {[d.docname for d in ns_docs]}"
            print(f"   ✓ Listed documents in namespace '{test_ns}' (found {len(ns_docs)}).")

            # --- Upsert Tests ---
            print(f"\n--- Testing Versioned Upsert: {test_ns}/upsert_doc ---")
            upsert_doc_name = f"upsert_doc_{uuid.uuid4().hex[:6]}"
            upsert_ns = test_ns

            # 21. Upsert to Initialize
            upsert_init_payload = wf_schemas.CustomerDataVersionedUpsert(
                is_shared=False,
                data={"initial": "data", "count": 0},
                version="v_init", # Initialize with a specific version
                # schema_template_name=schema_template_name, # Can add schema on init
                # schema_template_version=schema_template_version,
            )
            upsert_init_result = await data_tester.upsert_versioned_document(upsert_ns, upsert_doc_name, upsert_init_payload)
            assert upsert_init_result is not None, "Upsert (initialize) failed"
            assert "initialize" in upsert_init_result.operation_performed, f"Expected 'initialize' in operation, got {upsert_init_result.operation_performed}"
            assert upsert_init_result.document_identifier.version == "v_init", f"Expected version v_init, got {upsert_init_result.document_identifier.version}"
            print("   ✓ Upsert initialized document.")
            created_docs_for_cleanup.append({
                "namespace": upsert_ns, "docname": upsert_doc_name, 
                "is_shared": False, "is_versioned": True
            })

            # 22. Upsert to Update Existing Version (v_init)
            upsert_update_payload = wf_schemas.CustomerDataVersionedUpsert(
                is_shared=False,
                data={"initial": "updated", "count": 1}, # Overwrite data
                version="v_init",
            )
            upsert_update_result = await data_tester.upsert_versioned_document(upsert_ns, upsert_doc_name, upsert_update_payload)
            assert upsert_update_result is not None, "Upsert (update v_init) failed"
            assert "update" in upsert_update_result.operation_performed, f"Expected 'update' in operation, got {upsert_update_result.operation_performed}"
            assert upsert_update_result.document_identifier.version == "v_init", f"Expected version v_init, got {upsert_update_result.document_identifier.version}"
            # Verify update
            get_updated_vinit = await data_tester.get_versioned_document(upsert_ns, upsert_doc_name, is_shared=False, version="v_init")
            assert get_updated_vinit is not None and {k: v for k,v in get_updated_vinit.data.items() if k not in ["created_at", "updated_at"]} == {"initial": "updated", "count": 1}
            print("   ✓ Upsert updated existing version (v_init).")

            # 23. Upsert to Create and Update a New Version (v_new)
            upsert_new_version_payload = wf_schemas.CustomerDataVersionedUpsert(
                is_shared=False,
                data={"new_version_data": True, "count": 100},
                version="v_new", # Target a version that doesn't exist
                from_version="v_init" # Branch from v_init
            )
            upsert_new_version_result = await data_tester.upsert_versioned_document(upsert_ns, upsert_doc_name, upsert_new_version_payload)
            assert upsert_new_version_result is not None, "Upsert (create + update v_new) failed"
            # The operation should reflect the *update* after the creation
            assert "update" in upsert_new_version_result.operation_performed, f"Expected 'update' in operation, got {upsert_new_version_result.operation_performed}"
            assert upsert_new_version_result.document_identifier.version == "v_new", f"Expected version v_new, got {upsert_new_version_result.document_identifier.version}"
            # Verify new version exists and has the data
            get_vnew = await data_tester.get_versioned_document(upsert_ns, upsert_doc_name, is_shared=False, version="v_new")
            assert get_vnew is not None and {k: v for k,v in get_vnew.data.items() if k not in ["created_at", "updated_at"]} == {"new_version_data": True, "count": 100, "initial": "updated"}
            print("   ✓ Upsert created and updated new version (v_new).")

            # 24. Upsert to Update Active Version (assuming v_init is still active, or default)
            # First, set v_new as active
            set_active_vnew = wf_schemas.CustomerDataSetActiveVersion(is_shared=False, version="v_new")
            await data_tester.set_active_version(upsert_ns, upsert_doc_name, set_active_vnew)
            # Now upsert without specifying version (targets active: v_new)
            upsert_active_payload = wf_schemas.CustomerDataVersionedUpsert(
                is_shared=False,
                data={"active_update": "done", "count": 101},
                # version=None implicitly targets active
            )
            upsert_active_result = await data_tester.upsert_versioned_document(upsert_ns, upsert_doc_name, upsert_active_payload)
            assert upsert_active_result is not None, "Upsert (update active) failed"
            assert "update" in upsert_active_result.operation_performed
            print(upsert_active_result.document_identifier.model_dump_json(indent=4))
            assert upsert_active_result.document_identifier.version is None, "Expected active version represented by None to be updated"
            # Verify active version (v_new) was updated
            get_active = await data_tester.get_versioned_document(upsert_ns, upsert_doc_name, is_shared=False) # Gets active
            assert get_active is not None and {k: v for k,v in get_active.data.items() if k not in ["created_at", "updated_at"]} == {"new_version_data": True, "count": 101, "active_update": "done", "initial": "updated"}
            print("   ✓ Upsert updated active version (v_new).")

            # --- Search Documents --- 
            print(f"\n--- Testing Document Search in namespace {test_ns} ---")
            search_query_payload = wf_schemas.CustomerDataSearchQuery(
                namespace_filter=test_ns,
                text_search_query="initial", # Should match some of the upserted/initialized docs
                include_shared=True,
                include_user_specific=True,
                limit=10
            )
            search_results = await data_tester.search_documents(search_query_payload)
            assert search_results is not None, "Document search failed, expected results."
            print(f"   ✓ Found {len(search_results)} documents matching 'initial' in namespace {test_ns}.")
            for res in search_results:
                print(f"     - Doc: {res.metadata.namespace}/{res.metadata.docname}, Version: {res.metadata.version}, Shared: {res.metadata.is_shared}, Data: {res.data}")
                # Basic check if text_search_query worked (very simplified)
                assert "initial" in json.dumps(res.data).lower() or res.metadata.docname == upsert_doc_name, \
                    f"Search result {res.metadata.docname} data doesn't seem to contain 'initial': {res.data}"

            # --- Run Comprehensive Search API Tests ---
            print(f"\n--- Testing Comprehensive Document Search in namespace starting with {test_ns} ---")
            # `test_ns` will be the base for search-specific namespaces to keep them somewhat grouped
            search_test_created_docs = await run_search_tests(data_tester, template_tester, test_ns, created_docs_for_cleanup)
            # created_docs_for_cleanup.extend(search_test_created_docs)
            print("   ✓ Comprehensive search tests completed.")

    except AuthenticationError as e:
        print(f"Authentication Error: {e}")
        # cleanup_successful = False # Mark cleanup as potentially failed
    except ImportError as e:
        print(f"Import Error: {e}. Check PYTHONPATH and schema locations.")
        # cleanup_successful = False # Mark cleanup as potentially failed
    except Exception as e:
        print(f"An unexpected error occurred in the main test execution: {e}")
        logger.exception("Main test execution error:")
        # cleanup_successful = False # Mark cleanup as potentially failed
    finally:
        # --- Cleanup ---
        print("\n--- Cleanup --- ")
        if not cleanup_successful:
             print("   Skipping cleanup due to errors during testing.")
        elif not created_docs_for_cleanup:
             print("   No documents were recorded for cleanup.")
        else:
            print(f"   Attempting cleanup for {len(created_docs_for_cleanup)} created documents...")
            try:
                async with AuthenticatedClient() as auth_client:
                    cleanup_tester = CustomerDataTestClient(auth_client)
                    for doc_info in created_docs_for_cleanup:
                        ns = doc_info["namespace"]
                        dn = doc_info["docname"]
                        shared = doc_info["is_shared"]
                        versioned = doc_info["is_versioned"]
                        doc_type = "Versioned" if versioned else "Unversioned"
                        print(f"   Deleting {doc_type} doc: {ns}/{dn} (Shared: {shared})...")
                        deleted = False
                        try:
                            if versioned:
                                deleted = await cleanup_tester.delete_versioned_document(ns, dn, is_shared=shared)
                            else:
                                deleted = await cleanup_tester.delete_unversioned_document(ns, dn, is_shared=shared)
                            print(f"     {'✓' if deleted else '✗'} Deleted.")
                        except Exception as del_e:
                             print(f"     ✗ Deletion failed for {ns}/{dn}: {del_e}")

            except Exception as cleanup_e:
                print(f"   Overall document cleanup process failed: {cleanup_e}")
                logger.exception("Document cleanup error:")

            # Cleanup Schema Template if ID exists
            if temp_schema_template_id:
                print(f"   Cleaning up Schema Template {temp_schema_template_id}...")
                try:
                    # Need a new client context for cleanup if the main one closed due to error
                    async with AuthenticatedClient() as auth_client:
                        template_tester = TemplateTestClient(auth_client)
                        deleted_schema = await template_tester.delete_schema_template(temp_schema_template_id)
                        print(f"     {'✓' if deleted_schema else '✗'} Deleted Schema Template.")
                except Exception as schema_cleanup_e:
                    print(f"   Schema Template cleanup failed: {schema_cleanup_e}")
                    logger.exception("Schema Template cleanup error:")
            else:
                 print("   No Schema Template ID recorded for cleanup.")


        print("\n--- Customer Data API Test Finished --- ")

# --- Example Usage for System Entity Features and Metadata Route ---
async def main2():
    """
    Demonstrates testing advanced Customer Data API features including:
    - System entities: These are stored in system paths instead of organization paths but still respect is_shared
    - Acting on behalf of other users: Only works for user-specific docs, not shared or system entities
    - Document metadata retrieval: Shows how to access document metadata information
    """
    print("\n--- Starting Advanced Customer Data API Test --- ")
    
    # Generate unique test names with UUIDs to avoid collisions
    test_ns = f"test_sys_ns_{uuid.uuid4().hex[:6]}"
    v_doc_name = f"sys_versioned_{uuid.uuid4().hex[:6]}"
    uv_doc_name = f"sys_unversioned_{uuid.uuid4().hex[:6]}"
    
    # List to keep track of created documents for cleanup
    created_docs_for_cleanup = []
    
    try:
        async with AuthenticatedClient() as auth_client:
            print("Authenticated.")
            data_tester = CustomerDataTestClient(auth_client)
            
            # --- Test 1: Initialize a Versioned Document as System Entity ---
            print(f"\n--- Test 1: Creating System Entity Versioned Document: {test_ns}/{v_doc_name} ---")
            print("  (When is_system_entity=True, document is stored in system paths instead of org paths)")
            init_data = wf_schemas.CustomerDataVersionedInitialize(
                is_shared=True,  # Make it a shared document
                initial_data={"key": "system_value", "count": 42},
                initial_version="v1.0",
                is_system_entity=True  # Mark as system entity - puts it in system path, not org-specific path
            )
            init_result = await data_tester.initialize_versioned_document(test_ns, v_doc_name, init_data)
            created_docs_for_cleanup.append({
                "namespace": test_ns, "docname": v_doc_name, 
                "is_shared": True, "is_versioned": True, "is_system_entity": True
            })
            
            if init_result:
                print(f"   ✓ Created system entity versioned document: {init_result.data}")
            else:
                print(f"   ✗ Failed to create system entity versioned document")
                
            # --- Test 2: Get Document Metadata ---
            print(f"\n--- Test 2: Getting Document Metadata: {test_ns}/{v_doc_name} ---")
            print("  (Metadata shows is_system_entity=True and is_shared=True from prior step)")
            metadata = await data_tester.get_document_metadata(
                namespace=test_ns, 
                docname=v_doc_name,
                is_shared=True,
                is_system_entity=True  # Must specify this flag to access system entities
            )
            
            if metadata:
                print(f"   ✓ Got document metadata: {metadata}")
                print(f"     - Organization ID: {metadata.org_id}")
                print(f"     - Is System Entity: {metadata.is_system_entity}")
                print(f"     - Is Shared: {metadata.is_shared}")
                print(f"     - Is Versioned: {metadata.is_versioned}")
            else:
                print(f"   ✗ Failed to get document metadata")
                
            # --- Test 3: Create Unversioned Document as System Entity ---
            print(f"\n--- Test 3: Creating System Entity Unversioned Document: {test_ns}/{uv_doc_name} ---")
            print("  (Using is_system_entity=True with is_shared=True stores in system/shared path)")
            uv_data = wf_schemas.CustomerDataUnversionedCreateUpdate(
                is_shared=True,  # Document accessible by anyone in the organization
                data={"type": "system_config", "settings": {"feature_flags": {"advanced_mode": True}}},
                is_system_entity=True  # Store in system paths not org-specific paths
            )
            uv_result = await data_tester.create_or_update_unversioned_document(test_ns, uv_doc_name, uv_data)
            created_docs_for_cleanup.append({
                "namespace": test_ns, "docname": uv_doc_name, 
                "is_shared": True, "is_versioned": False, "is_system_entity": True
            })
            
            if uv_result:
                print(f"   ✓ Created system entity unversioned document: {uv_result.data}")
            else:
                print(f"   ✗ Failed to create system entity unversioned document")
                
            # --- Test 4: List Documents Including System Entities ---
            print(f"\n--- Test 4: Listing Documents Including System Entities ---")
            print("  (Need to specify include_system_entities=True to see system path documents)")
            documents = await data_tester.list_documents(
                namespace=test_ns, 
                include_system_entities=True  # Without this, system entities would be excluded from results
            )
            
            if documents:
                print(f"   ✓ Listed {len(documents)} documents")
                sys_docs = [doc for doc in documents if doc.is_system_entity]
                print(f"     - Found {len(sys_docs)} system entity documents")
                for doc in sys_docs:
                    print(f"     - {doc.namespace}/{doc.docname} (shared={doc.is_shared}, versioned={doc.is_versioned})")
            else:
                print(f"   ✗ Failed to list documents")
                
            # --- Optional Test 5: On Behalf of User operations (if you're a superuser) ---
            # This test requires superuser privileges and a valid user ID to act on behalf of
            print(f"\n--- Test 5: On Behalf of User Operations (Superuser Only) ---")
            print("  (Note: on_behalf_of_user_id won't work with system entities or shared docs)")
            # For demonstration purposes only - this would fail for non-superusers
            target_user_id = uuid.uuid4()  # Replace with a real user ID if available
            print(f"   Attempting to get document on behalf of user {target_user_id}")
            try:
                on_behalf_result = await data_tester.get_versioned_document(
                    namespace=test_ns, 
                    docname=v_doc_name, 
                    is_shared=True,
                    is_system_entity=True,
                    on_behalf_of_user_id=target_user_id  # This param is ignored for system entities & shared docs
                )
                if on_behalf_result:
                    print(f"   ✓ Got document on behalf of user {target_user_id} : \n\n{on_behalf_result}\n\n")
                    print("   Note: When getting system/shared documents, on_behalf_of_user_id has no effect")
                else:
                    print(f"   ✗ Failed to get document on behalf of user")
            except Exception as e:
                print(f"   ✗ Error in on-behalf-of operation (expected for non-superusers): {e}")
                
    finally:
        # --- Cleanup ---
        print("\n--- Cleanup ---")
        if len(created_docs_for_cleanup) > 0:
            print(f"Cleaning up {len(created_docs_for_cleanup)} documents...")
            async with AuthenticatedClient() as auth_client:
                data_tester = CustomerDataTestClient(auth_client)
                for doc in created_docs_for_cleanup:
                    try:
                        if doc.get("is_versioned", True):
                            result = await data_tester.delete_versioned_document(
                                namespace=doc["namespace"], 
                                docname=doc["docname"], 
                                is_shared=doc["is_shared"],
                                is_system_entity=doc.get("is_system_entity", False)
                            )
                        else:
                            result = await data_tester.delete_unversioned_document(
                                namespace=doc["namespace"], 
                                docname=doc["docname"], 
                                is_shared=doc["is_shared"],
                                is_system_entity=doc.get("is_system_entity", False)
                            )
                        print(f"{'✓' if result else '✗'} Deleted {doc['namespace']}/{doc['docname']}")
                    except Exception as e:
                        print(f"✗ Error deleting {doc['namespace']}/{doc['docname']}: {e}")
        
        print("--- Advanced Customer Data API Test Completed ---")


async def run_search_tests(
    data_tester: CustomerDataTestClient, 
    template_tester: TemplateTestClient, 
    base_namespace: str,
    created_docs_for_cleanup: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Runs a comprehensive suite of tests for the customer data search API.
    Creates a set of documents and then performs various search queries to validate functionality.

    Args:
        data_tester: An initialized CustomerDataTestClient.
        template_tester: An initialized TemplateTestClient (not used in this version but kept for consistency).
        base_namespace: The base namespace string to prefix search-specific namespaces.

    Returns:
        A list of dictionaries, where each dictionary contains info about a created document
        for cleanup purposes.
    """
    search_docs_for_cleanup: List[Dict[str, Any]] = []
    
    # Define unique namespaces and docnames for search tests
    # Using a common prefix derived from base_namespace to group these test documents
    search_ns_1 = f"{base_namespace}_search1"
    search_ns_2 = f"{base_namespace}_search2"
    search_ns_3_special = f"{base_namespace}_search3_special"
    custom_ns_for_deletion = []  # ["test_ns_df598e_search1", "test_ns_5e5d54_search1", "test_ns_e51d82_search1", "test_ns_810298_search1", "test_ns_e51d82_search2", "test_ns_810298_search2", "test_ns_df598e_search2", "test_ns_5970d7_search2", "test_ns_5970d7_search1", "test_ns_e51d82_search3_special", "test_ns_5e5d54_search3_special", "test_ns_810298_search3_special", "test_ns_df598e_search3_special"]
    # x = [('test_ns_271b50_search1', 's_v_json_shared1_45e4'), ('test_ns_271b50_search1', 's_v_json_shared2_sort_d087'), ('test_ns_c280fc_search1', 's_v_json_shared1_8d74'), ('test_ns_c280fc_search1', 's_v_json_shared2_sort_1592'), ('test_ns_271b50_search1', 's_v_json_user1_19cf'), ('test_ns_c280fc_search1', 's_v_json_user1_fa93')] + [('test_ns_1221bd_search2', 's_uv_json_user1_6f49'), ('test_ns_5e5d54_search2', 's_uv_json_user1_e20d'), ('test_ns_c280fc_search2', 's_uv_json_user1_8784')]
    # custom_ns_for_deletion.extend([a[0] for a in x])
    # --- Pre-cleanup: List and delete any existing documents in test namespaces ---
    print("   --- Pre-cleanup of test namespaces ---")
    namespaces_to_pre_clean = [search_ns_1, search_ns_2, search_ns_3_special, ] + custom_ns_for_deletion
    for ns_to_clean in namespaces_to_pre_clean:
        print(f"     Cleaning namespace: {ns_to_clean}")
        existing_docs_in_ns = await data_tester.list_documents(
            namespace=ns_to_clean,
            include_shared=True,
            include_user_specific=True,
            include_system_entities=False, # Assuming test docs are not system entities by default
            limit=1000 # High limit to get all
        )
        if existing_docs_in_ns:
            print(f"       Found {len(existing_docs_in_ns)} documents to delete in {ns_to_clean}.")
            for doc_meta in existing_docs_in_ns:
                print(f"         Deleting {doc_meta.namespace}/{doc_meta.docname} (Shared: {doc_meta.is_shared}, Versioned: {doc_meta.is_versioned})")
                deleted = False
                try:
                    if doc_meta.is_versioned:
                        deleted = await data_tester.delete_versioned_document(
                            namespace=doc_meta.namespace, 
                            docname=doc_meta.docname, 
                            is_shared=doc_meta.is_shared
                        )
                    else:
                        deleted = await data_tester.delete_unversioned_document(
                            namespace=doc_meta.namespace, 
                            docname=doc_meta.docname, 
                            is_shared=doc_meta.is_shared
                        )
                    if not deleted:
                        print(f"         WARN: Failed to delete {doc_meta.namespace}/{doc_meta.docname}")
                except Exception as e:
                    print(f"         ERROR deleting {doc_meta.namespace}/{doc_meta.docname}: {e}")
        else:
            print(f"       Namespace {ns_to_clean} is already clean or does not exist.")
    print("   --- Pre-cleanup finished ---")

    # Doc details
    # Format: (namespace, docname, is_versioned, is_shared, data_payload_creator_func, init_version_if_versioned)
    # data_payload_creator_func is a function that returns the data for initialization/creation
    doc_specs = [
        (search_ns_1, f"s_v_json_user1_{uuid.uuid4().hex[:4]}", True, False, lambda: {"description": "apple banana orange", "category": "fruit", "id_num": 1, "is_ripe": True, "rank": 10}, "v1"),
        (search_ns_1, f"s_v_json_shared1_{uuid.uuid4().hex[:4]}", True, True, lambda: {"description": "banana kiwi grape", "category": "fruit", "id_num": 2, "is_ripe": False, "source": "storeA", "rank": 20}, "v1"),
        (search_ns_2, f"s_uv_json_user1_{uuid.uuid4().hex[:4]}", False, False, lambda: {"description": "A blue car with stripes", "color": "blue", "id_num": 3, "year": 2020, "rank": 5}, None),
        (search_ns_2, f"s_uv_str_shared1_{uuid.uuid4().hex[:4]}", False, True, lambda: {"description": "This is a document about orange and red apples."}, None),
        (search_ns_3_special, f"s_v_json_user2_spchar_{uuid.uuid4().hex[:4]}", True, False, lambda: {"description": "special characters like !@#$%^&*()_+ and the word orange", "category": "symbols", "id_num": 4, "value_float": 100.5, "rank": 15}, "vAlpha"),
        (search_ns_1, f"s_v_json_shared2_sort_{uuid.uuid4().hex[:4]}", True, True, lambda: {"description": "yet another fruit document: cherry", "category": "fruit", "id_num": 5, "count_int": 50, "rank": 1}, "vS1"),
    ]

    created_doc_names_map: Dict[Tuple[str, str], Any] = {} # (ns, docname) -> original_data

    print("   Setting up documents for search tests...")
    for ns, dn, is_versioned, is_shared, data_creator, version in doc_specs:
        doc_data = data_creator()
        created_doc_names_map[(ns, dn)] = doc_data 
        print(f"     Creating {'versioned' if is_versioned else 'unversioned'} doc: {ns}/{dn} (shared={is_shared})")
        if is_versioned:
            init_payload = wf_schemas.CustomerDataVersionedInitialize(
                is_shared=is_shared,
                initial_data=doc_data,
                initial_version=version
            )
            init_res = await data_tester.initialize_versioned_document(ns, dn, init_payload)
            assert init_res is not None, f"Failed to initialize search test doc {ns}/{dn}"
        else:
            create_payload = wf_schemas.CustomerDataUnversionedCreateUpdate(
                is_shared=is_shared,
                data=doc_data
            )
            create_res = await data_tester.create_or_update_unversioned_document(ns, dn, create_payload)
            assert create_res is not None, f"Failed to create search test doc {ns}/{dn}"
        
        search_docs_for_cleanup.append({
            "namespace": ns, "docname": dn,
            "is_shared": is_shared, "is_versioned": is_versioned, "is_system_entity": False
        })
    print(f"   ✓ Created {len(search_docs_for_cleanup)} documents for search tests.")
    created_docs_for_cleanup.extend(search_docs_for_cleanup)

    # Helper to check results
    def _check_search_results(results: Optional[List[wf_schemas.CustomerDocumentSearchResult]], expected_count: Optional[int] = None, expected_docs: Optional[List[Tuple[str, str]]] = None):
        assert results is not None, "Search results were None"
        if expected_count is not None:
            assert len(results) == expected_count, f"Expected {expected_count} results, got {len(results)}: {[ (r.metadata.namespace, r.metadata.docname) for r in results]}"
        if expected_docs is not None:
            found_docs_paths = set((r.metadata.namespace, r.metadata.docname) for r in results)
            for expected_ns, expected_dn in expected_docs:
                assert (expected_ns, expected_dn) in found_docs_paths, f"Expected doc {(expected_ns, expected_dn)} not found in results: {found_docs_paths}"
            # Also check that no unexpected docs are present if count matches
            if expected_count is not None and len(results) == expected_count:
                 assert len(found_docs_paths) == len(expected_docs), f"Result count matches, but specific docs mismatch. Expected: {expected_docs}, Found: {found_docs_paths}"
        return results


    # --- Search Test Scenarios ---
    print("\n   --- Running Search Test Scenarios ---")

    # 1. Text Search
    print("   1. Testing Text Search...")
    search_query_apple = wf_schemas.CustomerDataSearchQuery(text_search_query="apple", include_shared=True, include_user_specific=True)
    results_apple = await data_tester.search_documents(search_query_apple)
    _check_search_results(results_apple, expected_count=2, expected_docs=[
        (doc_specs[0][0], doc_specs[0][1]), # s_v_json_user1 (apple banana orange)
        (doc_specs[3][0], doc_specs[3][1]), # s_uv_str_shared1 (orange and red apples)
    ])
    print("     ✓ Text search 'apple' OK.")

    search_query_banana = wf_schemas.CustomerDataSearchQuery(text_search_query="banana", include_shared=True, include_user_specific=True)
    results_banana = await data_tester.search_documents(search_query_banana)
    _check_search_results(results_banana, expected_count=2, expected_docs=[
        (doc_specs[0][0], doc_specs[0][1]), # s_v_json_user1 (apple banana orange)
        (doc_specs[1][0], doc_specs[1][1]), # s_v_json_shared1 (banana kiwi grape)
    ])
    print("     ✓ Text search 'banana' OK.")
    
    search_query_orange = wf_schemas.CustomerDataSearchQuery(text_search_query="orange", include_shared=True, include_user_specific=True)
    results_orange = await data_tester.search_documents(search_query_orange)
    _check_search_results(results_orange, expected_count=3, expected_docs=[
        (doc_specs[0][0], doc_specs[0][1]), # s_v_json_user1 (apple banana orange)
        (doc_specs[3][0], doc_specs[3][1]), # s_uv_str_shared1 (orange and red apples)
        (doc_specs[4][0], doc_specs[4][1]), # s_v_json_user2_spchar (word orange)
    ])
    print("     ✓ Text search 'orange' OK.")

    search_query_nonexistent = wf_schemas.CustomerDataSearchQuery(text_search_query="supercalifragilisticexpialidocious", include_shared=True, include_user_specific=True)
    results_nonexistent = await data_tester.search_documents(search_query_nonexistent)
    _check_search_results(results_nonexistent, expected_count=0)
    print("     ✓ Text search 'nonexistentword' OK.")

    search_query_spchar = wf_schemas.CustomerDataSearchQuery(text_search_query="special characters", namespace_filter=search_ns_3_special, include_shared=True, include_user_specific=True)
    results_spchar = await data_tester.search_documents(search_query_spchar)
    _check_search_results(results_spchar, expected_count=1, expected_docs=[(doc_specs[4][0], doc_specs[4][1])])
    print("     ✓ Text search 'special characters' OK.")

    # 2. Namespace Filter
    print("   2. Testing Namespace Filter...")
    search_query_ns1 = wf_schemas.CustomerDataSearchQuery(namespace_filter=search_ns_1, include_shared=True, include_user_specific=True)
    results_ns1 = await data_tester.search_documents(search_query_ns1)
    _check_search_results(results_ns1, expected_count=3, expected_docs=[
        (doc_specs[0][0], doc_specs[0][1]), 
        (doc_specs[1][0], doc_specs[1][1]),
        (doc_specs[5][0], doc_specs[5][1]),
    ])
    print(f"     ✓ Namespace filter '{search_ns_1}' OK.")

    search_query_ns_nonexistent = wf_schemas.CustomerDataSearchQuery(namespace_filter="nonexistent_namespace_filter_test", include_shared=True, include_user_specific=True)
    results_ns_nonexistent = await data_tester.search_documents(search_query_ns_nonexistent)
    _check_search_results(results_ns_nonexistent, expected_count=0)
    print("     ✓ Namespace filter 'nonexistent_namespace' OK.")

    # 3. Value Filter
    print("   3. Testing Value Filter...")
    search_query_val_fruit = wf_schemas.CustomerDataSearchQuery(value_filter={"category": "fruit"}, include_shared=True, include_user_specific=True)
    results_val_fruit = await data_tester.search_documents(search_query_val_fruit)
    _check_search_results(results_val_fruit, expected_count=3, expected_docs=[
        (doc_specs[0][0], doc_specs[0][1]),
        (doc_specs[1][0], doc_specs[1][1]),
        (doc_specs[5][0], doc_specs[5][1]),
    ])
    print("     ✓ Value filter {'category': 'fruit'} OK.")

    search_query_val_id3 = wf_schemas.CustomerDataSearchQuery(value_filter={"id_num": 3}, include_shared=True, include_user_specific=True)
    results_val_id3 = await data_tester.search_documents(search_query_val_id3)
    _check_search_results(results_val_id3, expected_count=1, expected_docs=[(doc_specs[2][0], doc_specs[2][1])])
    
    import pprint
    print("\n\n\n\n***** Results:")
    print(pprint.pformat([r.model_dump() for r in results_val_id3]))
    print("\n\n\n\n")

    assert results_val_id3[0].data.get("color") == "blue" # Check specific data
    print("     ✓ Value filter {'id_num': 3} OK.")
    
    search_query_val_ripe_true = wf_schemas.CustomerDataSearchQuery(value_filter={"is_ripe": True}, include_shared=True, include_user_specific=True)
    results_val_ripe_true = await data_tester.search_documents(search_query_val_ripe_true)
    _check_search_results(results_val_ripe_true, expected_count=1, expected_docs=[(doc_specs[0][0], doc_specs[0][1])])
    print("     ✓ Value filter {'is_ripe': True} OK.")

    search_query_val_multi = wf_schemas.CustomerDataSearchQuery(value_filter={"color": "blue", "year": 2020}, include_shared=True, include_user_specific=True)
    results_val_multi = await data_tester.search_documents(search_query_val_multi)
    _check_search_results(results_val_multi, expected_count=1, expected_docs=[(doc_specs[2][0], doc_specs[2][1])])
    print("     ✓ Value filter {'color': 'blue', 'year': 2020} OK.")
    
    search_query_val_float = wf_schemas.CustomerDataSearchQuery(value_filter={"value_float": 100.5}, include_shared=True, include_user_specific=True)
    results_val_float = await data_tester.search_documents(search_query_val_float)
    _check_search_results(results_val_float, expected_count=1, expected_docs=[(doc_specs[4][0], doc_specs[4][1])])
    print("     ✓ Value filter {'value_float': 100.5} OK.")

    # 4. Shared/User-Specific Flags
    print("   4. Testing Shared/User-Specific Flags...")
    # Only shared in search_ns_1
    search_query_shared_only_ns1 = wf_schemas.CustomerDataSearchQuery(namespace_filter=search_ns_1, include_shared=True, include_user_specific=False)
    results_shared_only_ns1 = await data_tester.search_documents(search_query_shared_only_ns1)
    _check_search_results(results_shared_only_ns1, expected_count=2, expected_docs=[
        (doc_specs[1][0], doc_specs[1][1]),
        (doc_specs[5][0], doc_specs[5][1]),
    ])
    print(f"     ✓ Shared only in '{search_ns_1}' OK.")

    # Only user-specific in search_ns_1
    search_query_user_only_ns1 = wf_schemas.CustomerDataSearchQuery(namespace_filter=search_ns_1, include_shared=False, include_user_specific=True)
    results_user_only_ns1 = await data_tester.search_documents(search_query_user_only_ns1)
    _check_search_results(results_user_only_ns1, expected_count=1, expected_docs=[(doc_specs[0][0], doc_specs[0][1])])
    print(f"     ✓ User-specific only in '{search_ns_1}' OK.")
    
    # None (shared=F, user=F)
    search_query_none_selected = wf_schemas.CustomerDataSearchQuery(namespace_filter=search_ns_1, include_shared=False, include_user_specific=False)
    results_none_selected = await data_tester.search_documents(search_query_none_selected)
    _check_search_results(results_none_selected, expected_count=0)
    print(f"     ✓ No docs (shared=F, user_specific=F) in '{search_ns_1}' OK.")

    # 5. Combinations
    print("   5. Testing Combinations of Filters...")
    search_query_combo1 = wf_schemas.CustomerDataSearchQuery(namespace_filter=search_ns_1, text_search_query="banana", include_shared=True, include_user_specific=True)
    results_combo1 = await data_tester.search_documents(search_query_combo1)
    _check_search_results(results_combo1, expected_count=2, expected_docs=[
        (doc_specs[0][0], doc_specs[0][1]),
        (doc_specs[1][0], doc_specs[1][1]),
    ])
    print(f"     ✓ Combo: namespace '{search_ns_1}' + text 'banana' OK.")

    search_query_combo2 = wf_schemas.CustomerDataSearchQuery(
        namespace_filter=search_ns_1, 
        value_filter={"category": "fruit"}, 
        text_search_query="kiwi",
        include_shared=True, include_user_specific=True
    )
    results_combo2 = await data_tester.search_documents(search_query_combo2)
    _check_search_results(results_combo2, expected_count=1, expected_docs=[(doc_specs[1][0], doc_specs[1][1])]) # Only s_v_json_shared1
    print(f"     ✓ Combo: namespace '{search_ns_1}' + value_filter + text 'kiwi' OK.")

    # 6. Pagination
    print("   6. Testing Pagination...")
    # All docs in search_ns_1 (3 docs)
    search_query_paginate_base = wf_schemas.CustomerDataSearchQuery(namespace_filter=search_ns_1, include_shared=True, include_user_specific=True, sort_by=CustomerDataSortBy.CREATED_AT, sort_order=SortOrder.ASC) # Sort for stable pagination

    # Limit 1
    results_paginate_l1 = await data_tester.search_documents(search_query_paginate_base.model_copy(update={"limit": 1}))
    _check_search_results(results_paginate_l1, expected_count=1)
    first_doc_path_l1 = (results_paginate_l1[0].metadata.namespace, results_paginate_l1[0].metadata.docname)
    print("     ✓ Pagination limit=1 OK.")

    # Skip 1, Limit 2
    results_paginate_s1_l2 = await data_tester.search_documents(search_query_paginate_base.model_copy(update={"skip": 1, "limit": 2}))
    _check_search_results(results_paginate_s1_l2, expected_count=2)
    # Ensure the skipped doc is not present
    for res_doc in results_paginate_s1_l2:
        assert (res_doc.metadata.namespace, res_doc.metadata.docname) != first_doc_path_l1, "Skipped document appeared in results"
    print("     ✓ Pagination skip=1, limit=2 OK.")
    
    # Skip past all results
    results_paginate_skip_all = await data_tester.search_documents(search_query_paginate_base.model_copy(update={"skip": 100}))
    _check_search_results(results_paginate_skip_all, expected_count=0)
    print("     ✓ Pagination skip past all results OK.")

    # 7. Sorting
    print("   7. Testing Sorting...")
    # Sort by 'rank' (custom field) using value_filter to get comparable items, then by CREATED_AT
    # Docs with 'rank':
    # doc0: rank 10
    # doc1: rank 20
    # doc2: rank 5
    # doc4: rank 15
    # doc5: rank 1
    
    # # For this test, we'll sort all documents by created_at as 'rank' is not a direct sort_by option in CustomerDataSortBy
    # all_docs_created_asc_query = wf_schemas.CustomerDataSearchQuery(
    #     include_shared=True, include_user_specific=True, 
    #     sort_by=CustomerDataSortBy.CREATED_AT, sort_order=SortOrder.ASC,
    #     limit=len(doc_specs) # Get all
    # )
    # all_docs_created_asc = await data_tester.search_documents(all_docs_created_asc_query)
    # _check_search_results(all_docs_created_asc, expected_count=len(doc_specs))
    # # Assuming creation order matches doc_specs order for this simple check
    # for i, res_doc in enumerate(all_docs_created_asc):
    #     expected_ns, expected_dn = doc_specs[i][0], doc_specs[i][1]
    #     assert (res_doc.metadata.namespace, res_doc.metadata.docname) == (expected_ns, expected_dn), \
    #         f"Sort by CREATED_AT ASC mismatch at index {i}. Expected ({expected_ns},{expected_dn}), got ({res_doc.metadata.namespace},{res_doc.metadata.docname})"
    # print("     ✓ Sort by CREATED_AT ASC OK.")

    # all_docs_created_desc_query = wf_schemas.CustomerDataSearchQuery(
    #     include_shared=True, include_user_specific=True, 
    #     sort_by=CustomerDataSortBy.CREATED_AT, sort_order=SortOrder.DESC,
    #     limit=len(doc_specs)
    # )
    # all_docs_created_desc = await data_tester.search_documents(all_docs_created_desc_query)
    # _check_search_results(all_docs_created_desc, expected_count=len(doc_specs))
    # for i, res_doc in enumerate(all_docs_created_desc):
    #     expected_idx = len(doc_specs) - 1 - i
    #     expected_ns, expected_dn = doc_specs[expected_idx][0], doc_specs[expected_idx][1]
    #     assert (res_doc.metadata.namespace, res_doc.metadata.docname) == (expected_ns, expected_dn), \
    #         f"Sort by CREATED_AT DESC mismatch at index {i}. Expected ({expected_ns},{expected_dn}), got ({res_doc.metadata.namespace},{res_doc.metadata.docname})"
    # print("     ✓ Sort by CREATED_AT DESC OK.")
    
    # # Test UPDATED_AT - this is harder to control precisely without explicit updates after creation
    # # For now, we'll assume UPDATED_AT is similar to CREATED_AT on initial creation for a basic check.
    # # A more robust test would involve updating some documents and then checking.
    # all_docs_updated_asc_query = wf_schemas.CustomerDataSearchQuery(
    #     include_shared=True, include_user_specific=True, 
    #     sort_by=CustomerDataSortBy.UPDATED_AT, sort_order=SortOrder.ASC,
    #     limit=len(doc_specs)
    # )
    # all_docs_updated_asc = await data_tester.search_documents(all_docs_updated_asc_query)
    # _check_search_results(all_docs_updated_asc, expected_count=len(doc_specs))
    # # We cannot reliably check order here without updates, just that it returns sorted results.
    # print("     ✓ Sort by UPDATED_AT ASC (basic check) OK.")


    # 8. Edge Cases
    print("   8. Testing Edge Cases...")
    # Empty query (no filters, default shared/user flags)
    search_query_empty = wf_schemas.CustomerDataSearchQuery(include_shared=True, include_user_specific=True, sort_by=CustomerDataSortBy.CREATED_AT, sort_order=SortOrder.DESC, limit=len(doc_specs)) # ensure limit is high enough
    results_empty = await data_tester.search_documents(search_query_empty)
    # This should return all created test documents if they are within the default org scope
    # Count should match the number of docs created in this test function.
    _check_search_results(results_empty, expected_count=len(doc_specs))
    print("     ✓ Empty query (all test docs) OK.")

    print("   ✓ All search test scenarios completed.")
    return search_docs_for_cleanup


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
    asyncio.run(main2())  # Run the advanced tests
