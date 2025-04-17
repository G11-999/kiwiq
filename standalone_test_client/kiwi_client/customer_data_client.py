"""
Test client for the Customer Data API endpoints.
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
)
# Import schemas and constants from the workflow app
from kiwi_client.schemas import workflow_api_schemas as wf_schemas
# Import Template Client for schema creation/cleanup
from kiwi_client.template_client import TemplateTestClient

# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)

# Create TypeAdapters for validating lists of schemas
CustomerDataVersionInfoListAdapter = TypeAdapter(List[wf_schemas.CustomerDataVersionInfo])
CustomerDataVersionHistoryItemListAdapter = TypeAdapter(List[wf_schemas.CustomerDataVersionHistoryItem])
CustomerDocumentMetadataListAdapter = TypeAdapter(List[wf_schemas.CustomerDocumentMetadata])

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
    ) -> Optional[wf_schemas.CustomerDataRead]:
        """
        Tests getting a versioned document via GET /customer-data/versioned/{namespace}/{docname}.
        """
        logger.info(f"Attempting to get versioned document: {namespace}/{docname} (shared={is_shared}, version={version})")
        url = VERSIONED_DOC_URL(namespace, docname)
        params = {"is_shared": is_shared}
        if version:
            params["version"] = version
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
    ) -> bool:
        """
        Tests deleting a versioned document via DELETE /customer-data/versioned/{namespace}/{docname}.
        """
        logger.info(f"Attempting to delete versioned document: {namespace}/{docname} (shared={is_shared})")
        url = VERSIONED_DOC_URL(namespace, docname)
        params = {"is_shared": is_shared}
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
    ) -> Optional[List[wf_schemas.CustomerDataVersionInfo]]:
        """
        Tests listing versions via GET /customer-data/versioned/{namespace}/{docname}/versions.
        """
        logger.info(f"Attempting to list versions for: {namespace}/{docname} (shared={is_shared})")
        url = VERSIONED_DOC_VERSIONS_URL(namespace, docname)
        params = {"is_shared": is_shared}
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
    ) -> Optional[List[wf_schemas.CustomerDataVersionHistoryItem]]:
        """
        Tests getting history via GET /customer-data/versioned/{namespace}/{docname}/history.
        """
        logger.info(f"Attempting to get history for: {namespace}/{docname} (shared={is_shared}, version={version})")
        url = VERSIONED_DOC_HISTORY_URL(namespace, docname)
        params = {"is_shared": is_shared, "limit": limit}
        if version:
            params["version"] = version
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
    ) -> Optional[wf_schemas.CustomerDataRead]:
        """
        Tests previewing restore via GET /customer-data/versioned/{namespace}/{docname}/preview-restore/{sequence}.
        """
        logger.info(f"Attempting to preview restore for: {namespace}/{docname} (seq={sequence}, shared={is_shared}, version={version})")
        url = VERSIONED_DOC_PREVIEW_RESTORE_URL(namespace, docname, sequence)
        params = {"is_shared": is_shared}
        if version:
            params["version"] = version
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
    ) -> Optional[Dict[str, Any]]:
        """
        Tests getting schema via GET /customer-data/versioned/{namespace}/{docname}/schema.
        """
        logger.info(f"Attempting to get schema for: {namespace}/{docname} (shared={is_shared})")
        url = VERSIONED_DOC_SCHEMA_URL(namespace, docname)
        params = {"is_shared": is_shared}
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            response_json = response.json()
            # Assuming the response is a valid JSON schema dictionary
            logger.info(f"Successfully retrieved schema for: {namespace}/{docname}")
            return response_json
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
    ) -> Optional[wf_schemas.CustomerDataUnversionedRead]:
        """
        Tests getting an unversioned document via GET /customer-data/unversioned/{namespace}/{docname}.
        """
        logger.info(f"Attempting to get unversioned document: {namespace}/{docname} (shared={is_shared})")
        url = UNVERSIONED_DOC_URL(namespace, docname)
        params = {"is_shared": is_shared}
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            response_json = response.json()
            validated_response = wf_schemas.CustomerDataUnversionedRead.model_validate(response_json)
            logger.info(f"Successfully retrieved unversioned document: {namespace}/{docname}")
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
    ) -> bool:
        """
        Tests deleting an unversioned document via DELETE /customer-data/unversioned/{namespace}/{docname}.
        """
        logger.info(f"Attempting to delete unversioned document: {namespace}/{docname} (shared={is_shared})")
        url = UNVERSIONED_DOC_URL(namespace, docname)
        params = {"is_shared": is_shared}
        try:
            response = await self._client.delete(url, params=params)
            response.raise_for_status()
            logger.info(f"Successfully deleted unversioned document: {namespace}/{docname}")
            return response.status_code == 204
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
    ) -> Optional[List[wf_schemas.CustomerDocumentMetadata]]:
        """
        Tests listing documents via GET /customer-data/list.
        """
        logger.info(f"Attempting to list documents (namespace={namespace}, shared={include_shared}, user={include_user_specific})")
        params: Dict[str, Any] = {
            "include_shared": include_shared,
            "include_user_specific": include_user_specific,
            "skip": skip,
            "limit": limit,
        }
        if namespace:
            params["namespace"] = namespace
        try:
            response = await self._client.get(LIST_DOCUMENTS_URL, params=params)
            response.raise_for_status()
            response_json = response.json()
            validated_response = CustomerDocumentMetadataListAdapter.validate_python(response_json)
            logger.info(f"Successfully listed {len(validated_response)} documents.")
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
            assert init_result_json.data == expected_init_data, \
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
            assert get_result_json.data == expected_init_data, \
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
            assert update_result_json.data == update_payload_json, \
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
                is_shared=False, data=partial_update_payload_valid, version="v1.0"
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
            assert update_active_result_json.data == expected_update_response, \
                   f"Update active data mismatch. Expected: {expected_update_response}, Got: {update_active_result_json.data}"
            print("   ✓ Updated active version (v1.1, JSON).")
            
            # 8a. Restore document to sequence 0 (initial state)
            restore_data = wf_schemas.CustomerDataVersionedRestore(is_shared=False, sequence=0, version="v1.0")
            restore_result = await data_tester.restore_document(test_ns, v_doc_name_json, restore_data)
            assert restore_result is not None, "Restore document failed, expected a result."
            assert restore_result.data == expected_init_data, \
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
            assert uv_create_result_json.data == uv_create_payload_json, \
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
            assert uv_get_result_json.data == expected_uv_data, \
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
            assert uv_update_result_json.data == uv_update_payload_json, \
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

if __name__ == "__main__":
    print("Running Customer Data Test Client...")
    asyncio.run(main())
