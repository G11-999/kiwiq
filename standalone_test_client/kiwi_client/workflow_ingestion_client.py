"""
API Client for workflow ingestion, verification, and testing.

This client automates the process of:
1. Importing workflows from definition files
2. Ingesting them into the workflow system
3. Verifying successful ingestion via search
4. Optionally testing the ingested workflow

Typical workflow:
- Identify a workflow schema in the code (e.g., workflows/wf_content_generation.py)
- Check workflow key mapping to get correct name/version to use
- Delete previous workflow with same name if exists
- Verify user has superuser permissions
- Create new workflow with system and public flags
- Search to verify ingestion (including graph schema validation)
- Optionally run test of the workflow with default or overridden inputs
"""
import asyncio
import json
import logging
import httpx
import uuid
from typing import Dict, Any, Optional, List, Tuple, Union, NamedTuple, TypedDict

# Import authenticated client and config
from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from kiwi_client.test_config import (
    CLIENT_LOG_LEVEL,
    WORKFLOWS_URL,
)

# Import the client modules we need
from kiwi_client.workflow_client import WorkflowTestClient
from kiwi_client.app_artifact_client import AppArtifactTestClient
from kiwi_client.test_run_workflow_client import run_workflow_test
from kiwi_client.user_client import UserTestClient

# Import pydantic for validation
from pydantic import ValidationError

# Import schemas
from kiwi_client.schemas import workflow_api_schemas as wf_schemas
from kiwi_client.schemas import app_artifact_schemas as aa_schemas
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus, LaunchStatus

# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)

# Define a type for workflow ingestion configuration
class WorkflowIngestionConfig(TypedDict, total=False):
    """Configuration for a workflow ingestion operation."""
    workflow_key: str
    module_path: str  
    run_test: bool
    test_inputs_override: Optional[Dict[str, Any]]
    test_timeout_sec: int
    hitl_inputs: Optional[List[Dict[str, Any]]]


class WorkflowIngestionClient:
    """
    Client for ingesting, verifying, and testing workflow definitions.
    
    This client provides end-to-end workflow management including:
    - Ingestion of workflow schemas into the system
    - Verification of successful ingestion via search
    - Optional testing of ingested workflows
    - Superuser validation
    """
    
    # Define expected superuser email - should be configurable via ENV in future
    SUPERUSER_EMAIL = "admin@example.com"
    
    def __init__(self, auth_client: AuthenticatedClient):
        """
        Initializes the WorkflowIngestionClient.
        
        Args:
            auth_client (AuthenticatedClient): An instance of AuthenticatedClient, assumed to be logged in.
        """
        if not auth_client:
            raise ValueError("AuthenticatedClient is required.")
            
        self._auth_client: AuthenticatedClient = auth_client
        self._client: httpx.AsyncClient = auth_client.client
        
        # Initialize sub-clients
        self._workflow_client: WorkflowTestClient = WorkflowTestClient(auth_client)
        self._artifact_client: AppArtifactTestClient = AppArtifactTestClient(auth_client)
        self._user_client: UserTestClient = UserTestClient(auth_client)
        
        logger.info("WorkflowIngestionClient initialized.")
    
    async def verify_superuser_status(self) -> bool:
        """
        Verifies that the authenticated user is a superuser and has the expected email.
        
        Returns:
            bool: True if user is a superuser with expected email, False otherwise.
        
        Raises:
            AuthenticationError: If client is not authenticated.
        """
        logger.info(f"Verifying superuser status for expected email: {self.SUPERUSER_EMAIL}")
        
        try:
            # Get current user details
            current_user = await self._user_client.get_current_user()
            
            if not current_user:
                logger.error("Failed to retrieve current user details.")
                return False
                
            # Check if user is a superuser and has expected email
            if current_user.is_superuser and current_user.email == self.SUPERUSER_EMAIL:
                logger.info(f"Verified user {current_user.email} is a superuser.")
                return True
            else:
                if current_user.email != self.SUPERUSER_EMAIL:
                    logger.error(f"User email {current_user.email} does not match expected superuser email {self.SUPERUSER_EMAIL}")
                if not current_user.is_superuser:
                    logger.error(f"User {current_user.email} is not a superuser")
                return False
                
        except Exception as e:
            logger.exception(f"Error verifying superuser status: {e}")
            return False
    
    async def get_workflow_info_from_key(self, workflow_key: str) -> Optional[Tuple[str, Optional[str]]]:
        """
        Retrieves workflow name and version from a workflow key using the app artifacts API.
        
        Args:
            workflow_key (str): The workflow key to look up.
            
        Returns:
            Optional[Tuple[str, Optional[str]]]: A tuple containing (workflow_name, workflow_version) if found,
                                               or None if the lookup fails.
        """
        logger.info(f"Looking up workflow information for key: {workflow_key}")
        
        try:
            # Create a request to get workflow info
            workflow_info_req = aa_schemas.WorkflowInfoRequest(workflow_key=workflow_key)
            workflow_info = await self._artifact_client.get_workflow_processing_info(workflow_info_req)
            
            if not workflow_info:
                logger.error(f"Failed to get workflow info for key '{workflow_key}'")
                return None
                
            workflow_name = workflow_info.workflow_name
            workflow_version = workflow_info.workflow_version
            
            logger.info(f"Retrieved workflow info: name='{workflow_name}', version='{workflow_version}'")
            return workflow_name, workflow_version
            
        except Exception as e:
            logger.exception(f"Error retrieving workflow info for key '{workflow_key}': {e}")
            return None
    
    async def search_and_delete_existing_workflow(self, workflow_name: str, workflow_version: Optional[str] = None) -> bool:
        """
        Searches for an existing workflow by name and version, and deletes it if found.
        
        Args:
            workflow_name (str): The name of the workflow to search for.
            workflow_version (Optional[str]): The version of the workflow. If None, works with any version.
            
        Returns:
            bool: True if a workflow was found and deleted, or if no matching workflow was found.
                 False if the search or deletion failed.
        """
        logger.info(f"Searching for existing workflow: name='{workflow_name}', version='{workflow_version}'")
        
        try:
            # Search for the workflow
            search_results = await self._workflow_client.search_workflows(
                name=workflow_name,
                version_tag=workflow_version,
                include_public=True,
                include_system_entities=True
            )
            
            if not search_results:
                logger.info(f"No existing workflow found with name '{workflow_name}'{f' and version {workflow_version}' if workflow_version else ''}.")
                return True  # No workflow to delete, so operation is successful
                
            # Delete each matching workflow (usually just one)
            for workflow in search_results:
                if workflow.owner_org_id != self._auth_client.active_org_id or (not workflow.is_public):
                    logger.info(f"Skipping workflow: ID={workflow.id}, Name={workflow.name}, Version={workflow.version_tag} because it is not owned by the active organization")
                    continue
                logger.info(f"Found existing workflow: ID={workflow.id}, Name={workflow.name}, Version={workflow.version_tag}")
                
                # Delete the workflow
                deleted = await self._workflow_client.delete_workflow(workflow.id)
                
                if deleted:
                    logger.info(f"Successfully deleted workflow: {workflow.name} (ID: {workflow.id})")
                else:
                    logger.error(f"Failed to delete workflow: {workflow.name} (ID: {workflow.id})")
                    return False
                    
            return True
            
        except Exception as e:
            logger.exception(f"Error during search and delete operation: {e}")
            return False
    
    async def ingest_workflow(
        self, 
        workflow_schema: Dict[str, Any],
        workflow_key: str,
        run_test: bool = False,
        test_inputs_override: Optional[Dict[str, Any]] = None,
        test_timeout_sec: int = 600,
        hitl_inputs: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Tuple[uuid.UUID, bool]]:
        """
        Ingests a workflow into the system.
        
        This method:
        1. Gets workflow name and version from the workflow key
        2. Verifies the user is a superuser
        3. Deletes any existing workflow with the same name/version
        4. Creates the new workflow as a system entity
        5. Verifies successful ingestion via search
        6. Optionally tests the workflow
        
        Args:
            workflow_schema (Dict[str, Any]): The workflow graph schema to ingest.
            workflow_key (str): The workflow key to use for name/version lookup.
            run_test (bool): Whether to run a test of the workflow after ingestion.
            test_inputs_override (Optional[Dict[str, Any]]): Override values for workflow inputs when testing.
            test_timeout_sec (int): Timeout in seconds for test execution. Default is 600 (10 minutes).
            hitl_inputs (Optional[List[Dict[str, Any]]]): Predefined responses for HITL steps in the workflow.
            
        Returns:
            Optional[Tuple[uuid.UUID, bool]]: A tuple containing:
                - The UUID of the created workflow
                - A boolean indicating if the test (if run) was successful
              Returns None if the ingestion process fails.
        """
        logger.info(f"Starting workflow ingestion process for key: {workflow_key}")
        
        # Step 1: Verify superuser status
        if not await self.verify_superuser_status():
            logger.error("User is not a superuser or doesn't have expected email. Aborting ingestion.")
            return None
            
        # Step 2: Get workflow name and version from key
        workflow_info = await self.get_workflow_info_from_key(workflow_key)
        if not workflow_info:
            logger.error(f"Failed to get workflow information for key: {workflow_key}")
            return None
            
        workflow_name, workflow_version = workflow_info

        # Step 3: Validate the workflow schema before ingestion
        logger.info("Validating workflow schema before ingestion...")
        validation_result = await self._workflow_client.validate_graph_api(workflow_schema)
        
        if not validation_result or not validation_result.is_valid:
            error_details = validation_result.errors if validation_result else {"error": "Validation request failed"}
            logger.error(f"Workflow schema validation failed. Errors: {json.dumps(error_details, indent=2)}")
            return None
        
        # Step 4: Delete existing workflow with same name/version if it exists
        if not await self.search_and_delete_existing_workflow(workflow_name, workflow_version):
            logger.error(f"Failed to delete existing workflow. Aborting ingestion.")
            return None
            
        logger.info("Workflow schema validation passed.")
        
        # Step 5: Create the new workflow
        logger.info(f"Creating workflow: name='{workflow_name}', version='{workflow_version}'")
        
        try:
            created_workflow = await self._workflow_client.create_workflow(
                name=workflow_name,
                description=f"System workflow for {workflow_key}",
                graph_config=workflow_schema,
                is_template=False,
                version_tag=workflow_version,
                is_public=True,
                is_system_entity=True,
                launch_status=LaunchStatus.PRODUCTION
            )
            
            if not created_workflow or not created_workflow.id:
                logger.error("Failed to create workflow.")
                return None
                
            workflow_id = created_workflow.id
            logger.info(f"Successfully created workflow: {workflow_name} (ID: {workflow_id})")
            
            # Step 6: Verify ingestion via search
            logger.info(f"Verifying workflow ingestion via search...")
            search_results = await self._workflow_client.search_workflows(
                name=workflow_name,
                version_tag=workflow_version,
                include_public=True,
                include_system_entities=True
            )
            
            if not search_results:
                logger.error(f"Verification failed: Could not find newly created workflow via search.")
                return None
                
            # Find the created workflow in the results
            found_workflow = next((w for w in search_results if str(w.id) == str(workflow_id)), None)
            
            if not found_workflow:
                logger.error(f"Verification failed: Newly created workflow not found in search results.")
                return None
                
            logger.info(f"Verification successful: Found workflow in search results.")
            
            # Step 7: Run test if requested
            test_success = False
            if run_test:
                test_success = await self._run_workflow_test(
                    workflow_id=workflow_id,
                    workflow_key=workflow_key,
                    test_inputs_override=test_inputs_override,
                    timeout_sec=test_timeout_sec,
                    hitl_inputs=hitl_inputs
                )
                
            return workflow_id, test_success
            
        except Exception as e:
            logger.exception(f"Error during workflow ingestion: {e}")
            return None
    
    async def _run_workflow_test(
        self, 
        workflow_id: uuid.UUID, 
        workflow_key: str,
        test_inputs_override: Optional[Dict[str, Any]] = None,
        timeout_sec: int = 600,
        hitl_inputs: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Runs a test of an ingested workflow.
        
        Args:
            workflow_id (uuid.UUID): The UUID of the workflow to test.
            workflow_key (str): The workflow key for looking up inputs.
            test_inputs_override (Optional[Dict[str, Any]]): Override values for workflow inputs.
            timeout_sec (int): Timeout in seconds for test execution.
            hitl_inputs (Optional[List[Dict[str, Any]]]): Predefined responses for HITL steps in the workflow.
            
        Returns:
            bool: True if the test was successful, False otherwise.
        """
        logger.info(f"Starting test for workflow ID: {workflow_id}, key: {workflow_key}")
        
        try:
            # Step 1: Get workflow inputs from artifacts API
            workflow_inputs = await self._get_workflow_inputs(workflow_key)
            
            if not workflow_inputs:
                logger.error(f"Failed to get workflow inputs for key: {workflow_key}")
                return False
                
            # Step 2: Apply input overrides
            if test_inputs_override:
                logger.info(f"Applying input overrides: {json.dumps(test_inputs_override, indent=2)}")
                workflow_inputs.update(test_inputs_override)
                
            # Check for any required inputs that are still None
            missing_inputs = [key for key, value in workflow_inputs.items() if value is None]
            if missing_inputs:
                logger.error(f"Required inputs missing values: {missing_inputs}")
                return False
                
            logger.info(f"Final workflow inputs: {json.dumps(workflow_inputs, indent=2)}")
            
            # Step 3: Run the workflow test
            logger.info(f"Running workflow test...")
            final_run_status_obj, final_run_outputs = await run_workflow_test(
                test_name=f"IngestionTest_{workflow_key}",
                workflow_id=workflow_id,
                initial_inputs=workflow_inputs,
                expected_final_status=WorkflowRunStatus.COMPLETED,
                hitl_inputs=hitl_inputs,
                stream_intermediate_results=True,
                poll_interval_sec=3,
                timeout_sec=timeout_sec
            )
            
            # Step 4: Evaluate test results
            if not final_run_status_obj:
                logger.error("Test failed: No status object returned.")
                return False
                
            if final_run_status_obj.status != WorkflowRunStatus.COMPLETED:
                logger.error(f"Test failed: Final status was {final_run_status_obj.status} instead of COMPLETED.")
                if final_run_status_obj.error_message:
                    logger.error(f"Error message: {final_run_status_obj.error_message}")
                return False
                
            logger.info(f"Workflow test completed successfully!")
            if final_run_outputs:
                logger.info(f"Test outputs: {json.dumps(final_run_outputs, indent=2, default=str)}")
                
            return True
            
        except Exception as e:
            logger.exception(f"Error during workflow test: {e}")
            return False
            
    async def _get_workflow_inputs(self, workflow_key: str) -> Optional[Dict[str, Any]]:
        """
        Gets the expected inputs for a workflow from the artifacts API.
        
        Args:
            workflow_key (str): The workflow key to get inputs for.
            
        Returns:
            Optional[Dict[str, Any]]: The workflow inputs dictionary or None if retrieval fails.
        """
        logger.info(f"Getting workflow inputs for key: {workflow_key}")
        
        try:
            # Use get_workflow to directly get the processed inputs
            request_data = aa_schemas.GetWorkflowRequest(workflow_key=workflow_key)
            workflow_response = await self._artifact_client.get_workflow(request_data)
            
            if not workflow_response:
                logger.error(f"Failed to get workflow data for key '{workflow_key}'")
                return None
                
            # Return the processed inputs directly
            workflow_inputs = workflow_response.processed_inputs
            logger.info(f"Successfully retrieved workflow inputs for {workflow_key}")
            return workflow_inputs
            
        except Exception as e:
            logger.exception(f"Error getting workflow inputs for key '{workflow_key}': {e}")
            return None

    async def ingest_workflows(
        self,
        workflow_configs: List[WorkflowIngestionConfig]
    ) -> Dict[str, Tuple[Optional[uuid.UUID], bool]]:
        """
        Ingests multiple workflows based on the provided configurations.
        
        Args:
            workflow_configs: List of configurations for workflows to ingest.
                Each config should include workflow_key, module_path and optionally
                run_test, test_inputs_override, test_timeout_sec, and hitl_inputs.
                
        Returns:
            A dictionary mapping workflow keys to tuples of (workflow_id, test_success).
            If ingestion fails for a workflow, its tuple will be (None, False).
        """
        results = {}
        
        for config in workflow_configs:
            workflow_key = config["workflow_key"]
            module_path = config["module_path"]
            
            logger.info(f"Processing workflow: {workflow_key} from {module_path}")
            
            # Import the workflow schema
            workflow_schema = import_workflow_schema_from_path(module_path)
            if not workflow_schema:
                logger.error(f"Failed to import workflow schema from {module_path}")
                results[workflow_key] = (None, False)
                continue
            
            # Set default values for optional parameters
            run_test = config.get("run_test", False)
            test_inputs_override = config.get("test_inputs_override")
            test_timeout_sec = config.get("test_timeout_sec", 600)
            hitl_inputs = config.get("hitl_inputs")
            
            # Ingest the workflow
            result = await self.ingest_workflow(
                workflow_schema=workflow_schema,
                workflow_key=workflow_key,
                run_test=run_test,
                test_inputs_override=test_inputs_override,
                test_timeout_sec=test_timeout_sec,
                hitl_inputs=hitl_inputs
            )
            
            if result:
                workflow_id, test_success = result
                results[workflow_key] = (workflow_id, test_success)
            else:
                results[workflow_key] = (None, False)
        
        return results

# Helper function to import workflow schema from a module path
def import_workflow_schema_from_path(module_path: str) -> Optional[Dict[str, Any]]:
    """
    Imports a workflow graph schema from a Python module path.
    
    Args:
        module_path (str): The full Python module path (e.g., 'kiwi_client.workflows.wf_content_generation')
        
    Returns:
        Optional[Dict[str, Any]]: The workflow graph schema dictionary if found, None otherwise.
    """
    try:
        # Dynamically import the module
        module_parts = module_path.split('.')
        module_name = module_parts[-1]
        
        # Import the module
        import importlib
        module = importlib.import_module(module_path)
        
        # Look for typical workflow schema variable names
        schema_var_names = ['workflow_graph_schema', 'graph_schema', 'WORKFLOW_GRAPH_SCHEMA']
        
        for var_name in schema_var_names:
            if hasattr(module, var_name):
                schema = getattr(module, var_name)
                logger.info(f"Successfully imported workflow schema from {module_path}.{var_name}")
                return schema
                
        # If we couldn't find a standard name, log the available attributes
        logger.warning(f"Could not find workflow schema in {module_path}. Available attributes: {dir(module)}")
        return None
        
    except ImportError as e:
        logger.error(f"Failed to import module {module_path}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Error importing workflow schema from {module_path}: {e}")
        return None

# Example usage in a script
async def main():
    """Example usage of the WorkflowIngestionClient."""
    print("=== Workflow Ingestion Client Example ===")
    
    # Define multiple workflow configurations
    workflow_configs = [
        # First workflow - content creation workflow
        {
            "workflow_key": "content_creation_workflow",
            "module_path": "kiwi_client.workflows.wf_linkedin_scraping",
        },
        # {
        #     "workflow_key": "content_creation_workflow",
        #     "module_path": "kiwi_client.workflows.wf_content_generation",
        #     "run_test": True,
        #     "test_inputs_override": {
        #         "post_uuid": "test_post_uuid",
        #         "brief_docname": "brief_docname",
        #         "entity_username": "example-user",
        #     },
        #     "hitl_inputs": [
        #         # First HITL step - request revisions
        #         {
        #             "approval_status": "needs_work",
        #             "feedback_text": "The content is good but needs to be more specific to SaaS companies. Also, can you add more statistics to back up the claims and make the call to action stronger?"
        #         },
        #         # Second HITL step - approve
        #         {
        #             "approval_status": "approved",
        #             "feedback_text": ""
        #         }
        #     ]
        # },
        # Second workflow - example of another workflow (commented out for now)
        # {
        #     "workflow_key": "user_dna_workflow",
        #     "module_path": "kiwi_client.workflows.wf_user_dna",
        #     "run_test": False,
        # }
    ]
    
    try:
        print("\nInitializing client and authenticating...")
        async with AuthenticatedClient() as auth_client:
            ingestion_client = WorkflowIngestionClient(auth_client)
            
            # Ingest multiple workflows
            print(f"\nIngesting {len(workflow_configs)} workflows...")
            results = await ingestion_client.ingest_workflows(workflow_configs)
            
            # Print results
            print("\nWorkflow Ingestion Results:")
            for workflow_key, (workflow_id, test_success) in results.items():
                status = "SUCCESS" if workflow_id else "FAILED"
                test_result = "Test Passed" if test_success else "Test Failed/Not Run"
                print(f"- {workflow_key}: {status} (ID: {workflow_id}) - {test_result}")
                
    except AuthenticationError as e:
        print(f"Authentication Error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
        
    print("\n=== Workflow Ingestion Client Example Completed ===")

if __name__ == "__main__":
    print("Attempting to run workflow ingestion client example...")
    asyncio.run(main())
    print("\nRun this script with: PYTHONPATH=. python standalone_test_client/kiwi_client/workflow_ingestion_client.py")
