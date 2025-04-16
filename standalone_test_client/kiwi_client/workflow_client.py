"""
# poetry run python -m kiwi_client.workflow_client

API Test client for Workflow endpoints (/workflows/).

Tests:
- Create Workflow
- List Workflows
- Get Workflow by ID
- Update Workflow
- Delete Workflow
"""
import asyncio
import json
import httpx
import logging
import uuid
import jsonschema
from typing import Dict, Any, Optional, List, Union, TypeVar, Tuple

# Import authenticated client and config
from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from kiwi_client.test_config import (
    WORKFLOWS_URL,
    WORKFLOW_DETAIL_URL,
    NODE_TEMPLATES_URL,
    NODE_TEMPLATE_DETAIL_URL,
    EXAMPLE_BASIC_LLM_GRAPH_CONFIG, # Use the example graph from config
    CLIENT_LOG_LEVEL,
    VALIDATE_GRAPH_URL,  # Import validation URL
)

# Import pydantic for validation
from pydantic import ValidationError, TypeAdapter

# Import schemas from the workflow app
# try:
# from kiwi_app.workflow_app import schemas as wf_schemas
from kiwi_client.schemas import workflow_api_schemas as wf_schemas
# from kiwi_app.workflow_app.constants import LaunchStatus
from kiwi_client.schemas.workflow_constants import LaunchStatus
# from workflow_service.services import events as event_schemas
# from .schemas import events_schema as event_schemas
# from services.kiwi_app.workflow_app import schemas as wf_schemas
# from services.kiwi_app.workflow_app.constants import LaunchStatus
from kiwi_client.schemas.graph_schema import GraphSchema
# except ImportError:
#     # Fallback if schemas can't be imported
#     logging.warning("Could not import workflow schemas. Using fallback dummy schemas.")
#     class DummySchema: pass
#     class WorkflowRead(DummySchema): pass
#     class LaunchStatus:
#         DEVELOPMENT = "DEVELOPMENT"
#         STAGING = "STAGING"
#         PRODUCTION = "PRODUCTION"
#     wf_schemas = type('obj', (object,), {
#         'WorkflowRead': WorkflowRead,
#         'LaunchStatus': LaunchStatus
#     })()

# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)

# Create TypeAdapters for validating lists of schemas
try:
    WorkflowReadListAdapter = TypeAdapter(List[wf_schemas.WorkflowRead])
    NodeTemplateReadListAdapter = TypeAdapter(List[wf_schemas.NodeTemplateRead])
except (AttributeError, NameError):
    logger.warning("TypeAdapter for WorkflowRead could not be created")
    WorkflowReadListAdapter = None
    NodeTemplateReadListAdapter = None

# Type variable for workflow schema responses
T = TypeVar('T')

class WorkflowTestClient:
    """
    Provides methods to test the /workflows/ endpoints defined in routes.py.
    Uses schemas from schemas.py for requests and response validation.
    """
    def __init__(self, auth_client: AuthenticatedClient):
        """
        Initializes the WorkflowTestClient.

        Args:
            auth_client (AuthenticatedClient): An instance of AuthenticatedClient, assumed to be logged in.
        """
        self._auth_client = auth_client
        self._client: httpx.AsyncClient = auth_client.client
        self._created_workflow_id: Optional[uuid.UUID] = None # Store ID for cleanup/chaining
        self._node_templates_cache: Dict[Tuple[str, str], wf_schemas.NodeTemplateRead] = {}  # Cache for node templates by (name, version)
        logger.info("WorkflowTestClient initialized.")

    async def create_workflow(self,
                              name: str = "Test Workflow via Client",
                              description: str = "Workflow created for testing purposes.",
                              graph_config: Dict[str, Any] = EXAMPLE_BASIC_LLM_GRAPH_CONFIG,
                              is_template: bool = False,
                              version_tag: Optional[str] = None,
                              is_public: bool = False,
                              launch_status: str = LaunchStatus.DEVELOPMENT) -> Optional[wf_schemas.WorkflowRead]:
        """
        Tests creating a new workflow via POST /workflows/.

        Corresponds to the `create_workflow` route which expects `schemas.WorkflowCreate`.

        Args:
            name (str): The name of the workflow.
            description (str): The description of the workflow.
            graph_config (Dict[str, Any]): The graph configuration dictionary.
            is_template (bool): Whether the workflow is a template.
            version_tag (Optional[str]): User-defined tag for versioning.
            is_public (bool): Whether the workflow is publicly accessible.
            launch_status (str): The launch status (e.g., DEVELOPMENT, STAGING).

        Returns:
            Optional[wf_schemas.WorkflowRead]: The parsed and validated created workflow, or None on failure.
        """
        logger.info(f"Attempting to create workflow: {name}")
        # Prepare payload according to schemas.WorkflowCreate
        payload = {
            "name": name,
            "description": description,
            "graph_config": graph_config,
            "is_template": is_template,
            "version_tag": version_tag,
            "is_public": is_public,
            "launch_status": launch_status
        }
        try:
            # API returns 201 Created, body is WorkflowRead
            response = await self._client.post(WORKFLOWS_URL, json=payload)
            response.raise_for_status() # Check for HTTP errors
            response_json = response.json()
            
            # Validate the response against WorkflowRead schema
            validated_workflow = wf_schemas.WorkflowRead.model_validate(response_json)
            self._created_workflow_id = validated_workflow.id
            logger.info(f"Successfully created workflow ID: {self._created_workflow_id}")
            logger.debug(f"Create response validated: {validated_workflow.model_dump_json(indent=2)}")
            return validated_workflow
        except httpx.HTTPStatusError as e:
            logger.error(f"Error creating workflow: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error creating workflow: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error creating workflow: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error during workflow creation.")
        return None

    async def list_workflows(self, 
                            skip: int = 0, 
                            limit: int = 10,
                            include_public: bool = True,
                            owner_org_id: Optional[Union[str, uuid.UUID]] = None) -> Optional[List[wf_schemas.WorkflowRead]]:
        """
        Tests listing workflows via GET /workflows/.

        Corresponds to the `list_workflows` route which uses `schemas.WorkflowListQuery`.

        Args:
            skip (int): Number of workflows to skip.
            limit (int): Maximum number of workflows to return.
            include_public (bool): Whether to include public workflows.
            owner_org_id (Optional[Union[str, uuid.UUID]]): Filter by owning organization ID (superuser only).

        Returns:
            Optional[List[wf_schemas.WorkflowRead]]: A list of parsed and validated workflows, or None on failure.
        """
        logger.info(f"Attempting to list workflows (skip={skip}, limit={limit})...")
        params = {"skip": skip, "limit": limit, "include_public": include_public}
        if owner_org_id:
            params["owner_org_id"] = str(owner_org_id)

        try:
            # API returns 200 OK, body is List[WorkflowRead]
            response = await self._client.get(WORKFLOWS_URL, params=params)
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response list against List[WorkflowRead]
            if WorkflowReadListAdapter:
                validated_workflows = WorkflowReadListAdapter.validate_python(response_json)
                logger.info(f"Successfully listed and validated {len(validated_workflows)} workflows.")
                logger.debug(f"List workflows response (first item): {validated_workflows[0].model_dump() if validated_workflows else 'None'}")
                return validated_workflows
            else:
                # Fallback if schemas weren't imported
                logger.warning("Schema validation skipped for list_workflows due to import failure.")
                return response_json
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing workflows: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error listing workflows: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error listing workflows: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error during workflow listing.")
        return None

    async def get_workflow(self, workflow_id: Union[str, uuid.UUID]) -> Optional[wf_schemas.WorkflowRead]:
        """
        Tests getting a specific workflow by its ID via GET /workflows/{workflow_id}.

        Corresponds to the `get_workflow` route which returns `schemas.WorkflowRead`.

        Args:
            workflow_id (Union[str, uuid.UUID]): The ID of the workflow to retrieve.

        Returns:
            Optional[wf_schemas.WorkflowRead]: The parsed and validated workflow details, or None on failure.
        """
        workflow_id_str = str(workflow_id)
        logger.info(f"Attempting to get workflow ID: {workflow_id_str}")
        url = WORKFLOW_DETAIL_URL(workflow_id_str)
        try:
            # API returns 200 OK, body is WorkflowRead
            response = await self._client.get(url)
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response against WorkflowRead schema
            validated_workflow = wf_schemas.WorkflowRead.model_validate(response_json)
            logger.info(f"Successfully retrieved and validated workflow ID: {validated_workflow.id}")
            logger.debug(f"Get workflow response validated: {validated_workflow.model_dump_json(indent=2)}")
            return validated_workflow
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting workflow {workflow_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting workflow {workflow_id_str}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error getting workflow {workflow_id_str}: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception(f"Unexpected error getting workflow {workflow_id_str}.")
        return None

    async def update_workflow(self, 
                             workflow_id: Union[str, uuid.UUID], 
                             update_data: Dict[str, Any]) -> Optional[wf_schemas.WorkflowRead]:
        """
        Tests updating a specific workflow via PUT /workflows/{workflow_id}.

        Corresponds to the `update_workflow` route which expects `schemas.WorkflowUpdate` and returns `schemas.WorkflowRead`.

        Args:
            workflow_id (Union[str, uuid.UUID]): The ID of the workflow to update.
            update_data (Dict[str, Any]): A dictionary containing the fields to update.
                                         Example: {"name": "New Name", "description": "New Desc"}

        Returns:
            Optional[wf_schemas.WorkflowRead]: The parsed and validated updated workflow details, or None on failure.
        """
        workflow_id_str = str(workflow_id)
        logger.info(f"Attempting to update workflow ID: {workflow_id_str}")
        url = WORKFLOW_DETAIL_URL(workflow_id_str)
        try:
            # API returns 200 OK, body is WorkflowRead
            response = await self._client.put(url, json=update_data)
            response.raise_for_status()
            response_json = response.json()
            
            # Validate the response against WorkflowRead schema
            validated_workflow = wf_schemas.WorkflowRead.model_validate(response_json)
            logger.info(f"Successfully updated and validated workflow ID: {validated_workflow.id}")
            logger.debug(f"Update workflow response validated: {validated_workflow.model_dump_json(indent=2)}")
            return validated_workflow
        except httpx.HTTPStatusError as e:
            logger.error(f"Error updating workflow {workflow_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error updating workflow {workflow_id_str}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error updating workflow {workflow_id_str}: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception(f"Unexpected error updating workflow {workflow_id_str}.")
        return None

    async def delete_workflow(self, workflow_id: Union[str, uuid.UUID]) -> Optional[wf_schemas.WorkflowRead]:
        """
        Tests deleting a specific workflow via DELETE /workflows/{workflow_id}.

        Corresponds to the `delete_workflow` route which returns `schemas.WorkflowRead`.

        Args:
            workflow_id (Union[str, uuid.UUID]): The ID of the workflow to delete.

        Returns:
            Optional[wf_schemas.WorkflowRead]: The parsed and validated deleted workflow details, or None on failure.
        """
        workflow_id_str = str(workflow_id)
        logger.info(f"Attempting to delete workflow ID: {workflow_id_str}")
        url = WORKFLOW_DETAIL_URL(workflow_id_str)
        try:
            # Routes.py shows this returns 200 OK with the deleted workflow, not 204 No Content
            response = await self._client.delete(url)
            response.raise_for_status() 
            
            # Clear the stored ID if it matches the deleted one
            if self._created_workflow_id and str(self._created_workflow_id) == workflow_id_str:
                self._created_workflow_id = None
                
            # If the response is empty (204 No Content), return True for backward compatibility
            if response.status_code == 204:
                logger.info(f"Successfully deleted workflow ID: {workflow_id_str} (No content)")
                return True
                
            # Otherwise, validate the response as WorkflowRead
            response_json = response.json()
            validated_workflow = wf_schemas.WorkflowRead.model_validate(response_json)
            logger.info(f"Successfully deleted workflow ID: {validated_workflow.id}")
            logger.debug(f"Delete workflow response validated: {validated_workflow.model_dump_json(indent=2)}")
            return validated_workflow
        except httpx.HTTPStatusError as e:
            logger.error(f"Error deleting workflow {workflow_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error deleting workflow {workflow_id_str}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error deleting workflow {workflow_id_str}: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception(f"Unexpected error deleting workflow {workflow_id_str}.")
        return None

    async def list_node_templates(self, 
                                  skip: int = 0, 
                                  limit: int = 100,
                                  launch_status: Optional[List[str]] = None) -> Optional[List[wf_schemas.NodeTemplateRead]]:
        """
        Fetches a list of available node templates from the API.
        
        Args:
            skip (int): Number of templates to skip.
            limit (int): Maximum number of templates to return.
            launch_status (Optional[List[str]]): Filter templates by launch status.
            
        Returns:
            Optional[List[wf_schemas.NodeTemplateRead]]: List of node templates or None if the request fails.
        """
        logger.info(f"Fetching node templates (skip={skip}, limit={limit})...")
        params = {"skip": skip, "limit": limit}
        
        if launch_status:
            params["launch_status"] = launch_status
        
        try:
            response = await self._client.get(NODE_TEMPLATES_URL, params=params)
            response.raise_for_status()
            response_json = response.json()
            
            if NodeTemplateReadListAdapter:
                templates = NodeTemplateReadListAdapter.validate_python(response_json)
                logger.info(f"Successfully fetched {len(templates)} node templates.")
                
                # Update cache with fetched templates
                for template in templates:
                    self._node_templates_cache[(template.name, template.version)] = template
                
                return templates
            else:
                # Fallback if adapter not available
                logger.warning("Schema validation skipped for node templates due to import failure.")
                return response_json
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Error fetching node templates: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error fetching node templates: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error fetching node templates: {e}")
        except Exception as e:
            logger.exception("Unexpected error fetching node templates.")
        
        return None
    
    async def get_node_template(self, name: str, version: str) -> Optional[wf_schemas.NodeTemplateRead]:
        """
        Fetches a specific node template by name and version.
        
        Args:
            name (str): The name of the node template.
            version (str): The version of the node template.
            
        Returns:
            Optional[wf_schemas.NodeTemplateRead]: The node template or None if not found or request fails.
        """
        # Check cache first
        cache_key = (name, version)
        if cache_key in self._node_templates_cache:
            logger.info(f"Using cached node template: {name} v{version}")
            return self._node_templates_cache[cache_key]
        
        logger.info(f"Fetching node template: {name} v{version}")
        try:
            url = NODE_TEMPLATE_DETAIL_URL(name, version)
            response = await self._client.get(url)
            response.raise_for_status()
            response_json = response.json()
            
            template = wf_schemas.NodeTemplateRead.model_validate(response_json)
            logger.info(f"Successfully fetched node template: {name} v{version}")
            
            # Update cache
            self._node_templates_cache[cache_key] = template
            return template
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error fetching node template {name} v{version}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error fetching node template {name} v{version}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error fetching node template {name} v{version}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error fetching node template {name} v{version}.")
        
        return None
    
    async def validate_graph_api(self, 
                              graph_config: Dict[str, Any], 
                              validate_nodes: bool = True) -> Optional[wf_schemas.WorkflowGraphValidationResult]:
        """
        Validates a workflow graph configuration using the server API endpoint.
        
        This makes a POST request to the validation endpoint with the graph configuration,
        and returns the validation results.
        
        Args:
            graph_config (Dict[str, Any]): The graph configuration to validate.
            validate_nodes (bool): Whether to validate node configurations against templates.
                                  Defaults to True.
                                  
        Returns:
            Optional[wf_schemas.WorkflowGraphValidationResult]: Validation results or None if request fails.
        """
        logger.info(f"Validating graph configuration via API (validate_nodes={validate_nodes})...")
        
        try:
            # Prepare query parameters
            params = {"validate_nodes": validate_nodes}
            
            # Make the API request
            response = await self._client.post(VALIDATE_GRAPH_URL, json=graph_config, params=params)
            response.raise_for_status()
            response_json = response.json()
            
            # Parse the response into the WorkflowGraphValidationResult schema
            validation_result = wf_schemas.WorkflowGraphValidationResult.model_validate(response_json)
            
            # Log the result
            if validation_result.is_valid:
                logger.info("Graph validation passed successfully!")
            else:
                error_count = sum(len(errors) for errors in validation_result.errors.values())
                logger.warning(f"Graph validation failed with {error_count} errors")
                
            return validation_result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Error validating graph: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error validating graph: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error validating graph: {e}")
            
        return None

    def validate_graph_schema(self, graph_config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validates a graph configuration against the GraphSchema model.
        
        This is a client-side method that performs basic schema validation
        without requiring a server API call. For full validation including
        node configurations, use validate_workflow().
        
        Args:
            graph_config (Dict[str, Any]): The graph configuration to validate.
            
        Returns:
            Tuple[bool, List[str]]: A tuple containing:
                - bool: True if validation passed, False otherwise
                - List[str]: List of validation error messages, empty if validation passed
        """
        logger.info("Validating graph schema structure locally...")
        errors = []
        
        try:
            # Convert dict to GraphSchema for validation
            graph_schema = GraphSchema.model_validate(graph_config)
            logger.info("Graph schema local validation passed!")
            return True, []
        except ValidationError as e:
            logger.error(f"Graph schema validation failed: {e}")
            # Extract error messages
            for error in e.errors():
                loc = " -> ".join(str(l) for l in error["loc"])
                msg = error["msg"]
                errors.append(f"{loc}: {msg}")
            return False, errors
        except Exception as e:
            logger.exception("Unexpected error validating graph schema")
            errors.append(f"Unexpected validation error: {str(e)}")
            return False, errors
    
    async def validate_workflow(self, 
                               graph_config: Dict[str, Any], 
                               validate_nodes: bool = True) -> Tuple[bool, Dict[str, List[str]]]:
        """
        Performs comprehensive validation of a workflow graph configuration using the API endpoint.
        
        This method is a wrapper around the validate_graph_api method, which calls the server
        to validate both the structure and node configurations in the workflow graph.
        
        Args:
            graph_config (Dict[str, Any]): The graph configuration to validate.
            validate_nodes (bool): Whether to also validate node configurations
                                  against their templates. Default is True.
                                  
        Returns:
            Tuple[bool, Dict[str, List[str]]]: A tuple containing:
                - bool: True if all validation passes, False otherwise
                - Dict[str, List[str]]: Dictionary of validation errors by category/node
        """
        logger.info("Starting comprehensive workflow validation via API...")
        
        # Call the API to validate the graph
        validation_result = await self.validate_graph_api(graph_config, validate_nodes)
        
        if validation_result is None:
            # If the API call failed, fall back to local validation
            logger.warning("API validation failed, falling back to local schema validation...")
            is_valid_schema, schema_errors = self.validate_graph_schema(graph_config)
            return is_valid_schema, {"graph_schema": schema_errors} if not is_valid_schema else {}
        
        # Return validation results from the API
        return validation_result.is_valid, validation_result.errors

    # --- Helper property --- 
    @property
    def created_workflow_id(self) -> Optional[uuid.UUID]:
        """Returns the UUID of the last successfully created workflow in this session."""
        return self._created_workflow_id

# --- Example Usage --- (for testing this module directly)
async def main():
    """Demonstrates using the updated WorkflowTestClient with API-based validation."""
    print("--- Starting Workflow API Test --- ")
    temp_workflow_id: Optional[uuid.UUID] = None
    try:
        async with AuthenticatedClient() as auth_client:
            print("Authenticated.")
            workflow_tester = WorkflowTestClient(auth_client)

            # Test workflow validation using the API
            print("\nTesting Workflow Validation via API...")
            
            # Perform comprehensive validation via API
            print("\nValidating workflow graph via API...")
            validation_result = await workflow_tester.validate_graph_api(EXAMPLE_BASIC_LLM_GRAPH_CONFIG)
            
            if validation_result:
                if validation_result.is_valid:
                    print("   ✓ Workflow validation completed successfully!")
                    print(f"   - Graph schema valid: {validation_result.graph_schema_valid}")
                    print(f"   - Node configs valid: {validation_result.node_configs_valid}")
                else:
                    print("   ✗ Workflow validation failed:")
                    for category, errors in validation_result.errors.items():
                        print(f"     {category}:")
                        for error in errors:
                            print(f"       - {error}")
            else:
                print("   ✗ API validation request failed")
                
                # Fall back to local validation
                print("\nFalling back to local validation...")
                valid_schema, schema_errors = workflow_tester.validate_graph_schema(EXAMPLE_BASIC_LLM_GRAPH_CONFIG)
                if valid_schema:
                    print("   ✓ Graph schema is valid! (local validation)")
                else:
                    print("   ✗ Graph schema validation failed (local validation):")
                    for error in schema_errors:
                        print(f"     - {error}")

            # Original workflow API tests
            print("\nTesting Workflow API...")

            # 1. Create Workflow
            print("\n1. Creating Workflow...")
            created = await workflow_tester.create_workflow(name="My API Test Workflow")
            if created:
                temp_workflow_id = created.id  # Access UUID directly from schema
                print(f"   Workflow Created: ID = {temp_workflow_id}")
                print(f"   Name: {created.name}, Launch Status: {created.launch_status}")
            else:
                print("   Workflow creation failed.")
                return # Stop if creation failed

            # 2. List Workflows (check if created one appears)
            print("\n2. Listing Workflows...")
            workflows = await workflow_tester.list_workflows(limit=5)
            if workflows is not None:
                print(f"   Found {len(workflows)} workflows.")
                # Check if our created workflow is in the list
                found_workflow = next((wf for wf in workflows if wf.id == temp_workflow_id), None)
                if found_workflow:
                    print(f"   Newly created workflow {temp_workflow_id} found in list.")
                    print(f"   Name: {found_workflow.name}, Created at: {found_workflow.created_at}")
                else:
                    print(f"   WARN: Newly created workflow {temp_workflow_id} not found in first 5.")
            else:
                print("   Workflow listing failed.")

            # 3. Get Workflow by ID
            print(f"\n3. Getting Workflow {temp_workflow_id}...")
            fetched = await workflow_tester.get_workflow(temp_workflow_id)
            if fetched:
                print(f"   Successfully fetched workflow: {fetched.name}")
                print(f"   Description: {fetched.description}")
                print(f"   Created at: {fetched.created_at}, Updated at: {fetched.updated_at}")
                assert fetched.id == temp_workflow_id
            else:
                print("   Failed to fetch workflow.")

            # 4. Update Workflow
            print(f"\n4. Updating Workflow {temp_workflow_id}...")
            update_payload = {"description": "Updated description via API test."}
            updated = await workflow_tester.update_workflow(temp_workflow_id, update_payload)
            if updated:
                print(f"   Successfully updated workflow. New Description: {updated.description}")
                print(f"   Name: {updated.name}, Updated at: {updated.updated_at}")
                assert updated.description == update_payload["description"]
            else:
                print("   Failed to update workflow.")

            # 5. Delete Workflow
            print(f"\n5. Deleting Workflow {temp_workflow_id}...")
            deleted = await workflow_tester.delete_workflow(temp_workflow_id)
            if deleted:
                if isinstance(deleted, bool):
                    print("   Workflow successfully deleted (No content response).")
                else:
                    print(f"   Workflow successfully deleted. ID: {deleted.id}, Name: {deleted.name}")
                
                # Verify deletion by trying to get it again (should fail)
                print(f"   Verifying deletion by trying to fetch {temp_workflow_id} again...")
                verify_fetch = await workflow_tester.get_workflow(temp_workflow_id)
                if verify_fetch is None:
                    print("   Verification successful: Workflow not found after deletion.")
                else:
                    print("   WARN: Workflow still found after attempting deletion.")
                temp_workflow_id = None # Clear ID after successful deletion
            else:
                print("   Failed to delete workflow.")

    except AuthenticationError as e:
        print(f"Authentication Error: {e}")
    except ImportError as e:
        print(f"Import Error: {e}. Check PYTHONPATH and schema locations.")
    except Exception as e:
        print(f"An unexpected error occurred in the main test execution: {e}")
        logger.exception("Main test execution error:")
    finally:
        # Attempt cleanup if an error occurred before delete and ID exists
        if temp_workflow_id:
             print(f"\nAttempting cleanup: Deleting workflow {temp_workflow_id}...")
             # Need a new client for cleanup if the context manager exited prematurely
             try:
                 async with AuthenticatedClient() as cleanup_auth_client:
                     cleanup_tester = WorkflowTestClient(cleanup_auth_client)
                     await cleanup_tester.delete_workflow(temp_workflow_id)
                     print("   Cleanup successful.")
             except Exception as cleanup_e:
                 print(f"   Cleanup failed: {cleanup_e}")

        print("--- Workflow API Test Finished --- ")

if __name__ == "__main__":
    # Ensure API server is running and config is correct
    # Run with: PYTHONPATH=. python services/kiwi_app/workflow_app/test_clients/test_workflow_client.py
    print("Attempting to run test client main function...")
    asyncio.run(main()) # Uncomment to run
    print("\nRun this script with `PYTHONPATH=[path_to_project_root] python services/kiwi_app/workflow_app/test_clients/test_workflow_client.py`")
    print("Note: Example usage in main() is commented out by default. Uncomment `asyncio.run(main())` to execute.")
