"""
API Test client for App Artifacts endpoints (/app-artifacts/).

Allows testing of:
- Getting processed workflow configurations.
- Getting information about workflow processing.
- Getting built document configurations.
- Getting information about document configurations.
"""
import asyncio
import httpx
import logging
import uuid
from typing import Dict, Any, Optional, List, Union

# Import authenticated client and config
from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from kiwi_client.test_config import (
    CLIENT_LOG_LEVEL,
    APP_ARTIFACT_GET_WORKFLOW_URL,
    APP_ARTIFACT_DOC_CONFIGS_URL,
)

# Import schemas for app artifacts
from kiwi_client.schemas import app_artifact_schemas as aa_schemas

# Import pydantic for validation
from pydantic import ValidationError

# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)

class AppArtifactTestClient:
    """
    Provides methods to test the /app-artifacts/ endpoints.
    Uses schemas from kiwi_client.schemas.app_artifact_schemas for requests and response validation.
    """
    def __init__(self, auth_client: AuthenticatedClient):
        """
        Initializes the AppArtifactTestClient.

        Args:
            auth_client (AuthenticatedClient): An instance of AuthenticatedClient, assumed to be logged in.
        """
        self._auth_client: AuthenticatedClient = auth_client
        self._client: httpx.AsyncClient = auth_client.client
        logger.info("AppArtifactTestClient initialized.")

    async def get_workflow(
        self,
        request_data: aa_schemas.GetWorkflowRequest
    ) -> Optional[aa_schemas.GetWorkflowResponse]:
        """
        Retrieves a predefined workflow definition with its inputs resolved.
        Corresponds to POST /app-artifacts/get-workflow.

        Args:
            request_data (aa_schemas.GetWorkflowRequest): The request payload.

        Returns:
            Optional[aa_schemas.GetWorkflowResponse]: The processed workflow details or None on failure.
        """
        logger.info(f"Attempting to get workflow: {request_data.workflow_key}")
        try:
            payload = request_data.model_dump(exclude_none=True)
            response = await self._client.post(APP_ARTIFACT_GET_WORKFLOW_URL, json=payload)
            response.raise_for_status()
            response_json = response.json()

            validated_response = aa_schemas.GetWorkflowResponse.model_validate(response_json)
            logger.info(f"Successfully retrieved workflow: {validated_response.original_workflow_name}")
            logger.debug(f"Get workflow response validated: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting workflow {request_data.workflow_key}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting workflow {request_data.workflow_key}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error for workflow {request_data.workflow_key}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error getting workflow {request_data.workflow_key}.")
        return None

    # async def get_workflow_processing_info(
    #     self,
    #     request_data: aa_schemas.WorkflowInfoRequest
    # ) -> Optional[aa_schemas.WorkflowInfoResponse]:
    #     """
    #     Gets information about unresolved inputs and variables for a predefined workflow.
    #     Corresponds to OPTIONS /app-artifacts/get-workflow.

    #     Args:
    #         request_data (aa_schemas.WorkflowInfoRequest): The request payload.

    #     Returns:
    #         Optional[aa_schemas.WorkflowInfoResponse]: The workflow analysis or None on failure.
    #     """
    #     logger.info(f"Attempting to get workflow processing info for: {request_data.workflow_key}")
    #     try:
    #         payload = request_data.model_dump(exclude_none=True)
    #         # FastAPI maps OPTIONS requests with a JSON body, httpx client needs to send it via json param.
    #         response = await self._client.request("OPTIONS", APP_ARTIFACT_GET_WORKFLOW_URL, json=payload)
    #         response.raise_for_status()
    #         response_json = response.json()

    #         validated_response = aa_schemas.WorkflowInfoResponse.model_validate(response_json)
    #         logger.info(f"Successfully retrieved workflow info for: {validated_response.workflow_name}")
    #         logger.debug(f"Get workflow info response: {validated_response.model_dump_json(indent=2)}")
    #         return validated_response
    #     except httpx.HTTPStatusError as e:
    #         logger.error(f"Error getting workflow info for {request_data.workflow_key}: {e.response.status_code} - {e.response.text}")
    #     except httpx.RequestError as e:
    #         logger.error(f"Request error getting workflow info for {request_data.workflow_key}: {e}")
    #     except ValidationError as e:
    #         logger.error(f"Response validation error for workflow info {request_data.workflow_key}: {e}")
    #     except Exception as e:
    #         logger.exception(f"Unexpected error getting workflow info for {request_data.workflow_key}.")
    #     return None

    async def get_built_document_configurations(
        self,
        request_data: aa_schemas.GetBuiltDocConfigsRequest
    ) -> Optional[aa_schemas.BuiltDocConfigsResponse]:
        """
        Gets built document configurations for a list of document keys.
        Corresponds to POST /app-artifacts/doc-configs.

        Args:
            request_data (aa_schemas.GetBuiltDocConfigsRequest): The request payload.

        Returns:
            Optional[aa_schemas.BuiltDocConfigsResponse]: The list of built doc configs or None on failure.
        """
        logger.info(f"Attempting to get built document configurations for keys: {request_data.doc_keys}")
        try:
            payload = request_data.model_dump(exclude_none=True)
            response = await self._client.post(APP_ARTIFACT_DOC_CONFIGS_URL, json=payload)
            response.raise_for_status()
            response_json = response.json()

            validated_response = aa_schemas.BuiltDocConfigsResponse.model_validate(response_json)
            logger.info(f"Successfully retrieved {len(validated_response.results)} built document configurations.")
            logger.debug(f"Get built doc configs response: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting built doc configs for {request_data.doc_keys}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting built doc configs for {request_data.doc_keys}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error for built doc configs {request_data.doc_keys}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error getting built doc configs for {request_data.doc_keys}.")
        return None

    async def get_document_configurations_info(
        self,
        request_data: aa_schemas.DocConfigsInfoRequest
    ) -> Optional[aa_schemas.DocConfigsInfoResponse]:
        """
        Gets template information for specified document configurations.
        Corresponds to OPTIONS /app-artifacts/doc-configs.

        Args:
            request_data (aa_schemas.DocConfigsInfoRequest): The request payload.

        Returns:
            Optional[aa_schemas.DocConfigsInfoResponse]: The list of doc config infos or None on failure.
        """
        doc_keys_str = str(request_data.doc_keys) if request_data.doc_keys else "all"
        logger.info(f"Attempting to get document configurations info for keys: {doc_keys_str}")
        try:
            payload = request_data.model_dump(exclude_none=True)
            response = await self._client.request("OPTIONS", APP_ARTIFACT_DOC_CONFIGS_URL, json=payload)
            response.raise_for_status()
            response_json = response.json()

            validated_response = aa_schemas.DocConfigsInfoResponse.model_validate(response_json)
            logger.info(f"Successfully retrieved info for {len(validated_response.results)} document configurations.")
            logger.debug(f"Get doc configs info response: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting doc configs info for {doc_keys_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting doc configs info for {doc_keys_str}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error for doc configs info {doc_keys_str}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error getting doc configs info for {doc_keys_str}.")
        return None


# --- Example Usage --- (for testing this module directly)
async def main():
    """Demonstrates using the AppArtifactTestClient."""
    print("--- Starting App Artifacts API Test Client ---")

    # Example entity_username and uuid for testing templates
    # These would typically come from your specific test case context
    test_entity_username = "testuser123"
    test_uuid = str(uuid.uuid4())

    try:
        async with AuthenticatedClient() as auth_client:

            print("Authenticated successfully.")
            artifact_tester = AppArtifactTestClient(auth_client)

            # 1. Get Document Configurations Info (OPTIONS /doc-configs)
            print("\n1. Getting Document Configurations Info (all default)...")
            doc_info_req = aa_schemas.DocConfigsInfoRequest(doc_keys=None) # Get info for all
            doc_info_resp = await artifact_tester.get_document_configurations_info(doc_info_req)
            if doc_info_resp:
                print(f"   Retrieved info for {len(doc_info_resp.results)} doc configs.")
                # print(f"   Example: {doc_info_resp.results[0].doc_key if doc_info_resp.results else 'N/A'}")
            else:
                print("   Failed to get document configurations info.")

            print("\n1b. Getting Document Configurations Info (specific keys)...")
            specific_doc_keys = ["user_dna_doc", "brief"] # Example keys from USER_DOCUMENTS_CONFIG_JSON_STR
            doc_info_req_specific = aa_schemas.DocConfigsInfoRequest(doc_keys=specific_doc_keys)
            doc_info_resp_specific = await artifact_tester.get_document_configurations_info(doc_info_req_specific)
            if doc_info_resp_specific:
                print(f"   Retrieved info for {len(doc_info_resp_specific.results)} specific doc configs.")
            else:
                print("   Failed to get specific document configurations info.")

            # 2. Get Built Document Configurations (POST /doc-configs)
            print("\n2. Getting Built Document Configurations...")
            build_doc_req_payload = aa_schemas.GetBuiltDocConfigsRequest(
                doc_keys=["user_dna_doc", "brief"], # Must exist in DEFAULT_USER_DOCUMENTS_CONFIG
                variables={
                    "user_dna_doc": {"entity_username": test_entity_username},
                    "brief": {"entity_username": test_entity_username, "uuid": test_uuid}
                },
                template_specific_variables=True,
                partial_build=False
            )
            built_docs_resp = await artifact_tester.get_built_document_configurations(build_doc_req_payload)
            if built_docs_resp:
                print(f"   Retrieved {len(built_docs_resp.results)} built doc configs.")
                for item in built_docs_resp.results:
                    if item.built_config:
                        print(f"     - {item.doc_key}: {item.built_config.get('namespace')}/{item.built_config.get('docname')}")
                    else:
                        print(f"     - {item.doc_key}: Error - {item.error}")
            else:
                print("   Failed to get built document configurations.")

            # # 3. Get Workflow Processing Info (OPTIONS /get-workflow)
            # # Assuming 'user_dna' is a valid workflow key in DEFAULT_ALL_WORKFLOWS
            # test_workflow_key_info = "user_dna"
            # print(f"\n3. Getting Workflow Processing Info for workflow: '{test_workflow_key_info}'...")
            # workflow_info_req = aa_schemas.WorkflowInfoRequest(workflow_key=test_workflow_key_info)
            # workflow_info_resp = await artifact_tester.get_workflow_processing_info(workflow_info_req)
            # if workflow_info_resp:
            #     print(f"   Retrieved info for workflow: {workflow_info_resp.workflow_name}")
            #     # print(f"   Unresolved analysis: {workflow_info_resp.unresolved_inputs_analysis}")
            # else:
            #     print(f"   Failed to get workflow processing info for '{test_workflow_key_info}'.")

            # 4. Get Workflow (POST /get-workflow)
            # Assuming 'content_strategy' is a valid workflow key
            test_workflow_key_get = "content_strategy"
            print(f"\n4. Getting (processed) Workflow: '{test_workflow_key_get}'...")
            get_workflow_req = aa_schemas.GetWorkflowRequest(
                workflow_key=test_workflow_key_get,
                override_variables={"entity_username": test_entity_username}, # Global override for this workflow
                override_template_specific=False # Indicates override_variables is Dict[str,Any]
            )
            processed_workflow_resp = await artifact_tester.get_workflow(get_workflow_req)
            if processed_workflow_resp:
                print(f"   Retrieved processed workflow: {processed_workflow_resp.original_workflow_name}")
                # print(f"   Processed inputs: {processed_workflow_resp.processed_inputs}")
            else:
                print(f"   Failed to get processed workflow for '{test_workflow_key_get}'.")

    except AuthenticationError as e:
        print(f"Authentication Error: {e}. Ensure credentials in .env are correct and user is verified.")
    except ImportError as e:
        print(f"Import Error: {e}. Check PYTHONPATH and schema locations.")
    except httpx.ConnectError as e:
        print(f"Connection Error: Could not connect to the API server. Ensure the server is running. Details: {e}")
    except Exception as e:
        print(f"An unexpected error occurred in the main test execution: {e}")
        logger.exception("Main test execution error:")
    finally:
        print("\n--- App Artifacts API Test Client Finished ---")

if __name__ == "__main__":
    # Ensure API server is running, .env is populated (TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_ORG_ID)
    # and the user is verified for login.
    # The default workflows and document configs must be loaded on the server for these examples to work.
    # Run this script with:
    # PYTHONPATH=[path_to_project_root] python standalone_test_client/kiwi_client/app_artifact_client.py
    # (Adjust path as necessary)
    asyncio.run(main())
