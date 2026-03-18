import asyncio
import logging
from typing import Optional
from kiwi_client.auth_client import AuthenticatedClient
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus
from kiwi_client.test_run_workflow_client import run_workflow_test
from kiwi_client.run_client import WorkflowRunTestClient
from kiwi_client.workflow_client import WorkflowTestClient
from kiwi_client.schemas import workflow_api_schemas as wf_schemas

# from kiwi_client.test_config import TEST_USER_EMAIL

# print(TEST_USER_EMAIL)

logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)

workflow_key = "orchestrator_workflow"

workflow_inputs = {
    "entity_username": "example-user-1",  # LinkedIn username
    "company_name": "ExampleCorp",  # Company name for analysis
    "run_linkedin_exec": True,  # Execute LinkedIn workflows
    "run_blog_analysis": True,  # Skip company workflows for now
    "linkedin_profile_url": "https://www.linkedin.com/in/example-user-1/",  # LinkedIn URL
    "company_url": "https://www.example.com/",  # Company website URL (optional)
    "blog_start_urls": ["https://www.example.com/blog"] # Example blog start URL
}

workflow_inputs_1 = {
    "entity_username": "example-user-2",  # LinkedIn username
    "company_name": "ExampleCorp",  # Company name for analysis
    "run_linkedin_exec": True,  # Execute LinkedIn workflows
    "run_blog_analysis": True,  # Skip company workflows for now
    "linkedin_profile_url": "https://www.linkedin.com/in/example-user-2/",  # LinkedIn URL
    "company_url": "https://www.example.com/blog",  # Company website URL (optional)
    "blog_start_urls": ["https://www.example.com/blog"], # Example blog start URL
    "include_only_paths": ["/blog*"],
}

workflow_inputs_2 = {
    "entity_username": "example-user-3",  # LinkedIn username
    "company_name": "ExampleCorp2",  # Company name for analysis
    "run_linkedin_exec": True,  # Execute LinkedIn workflows
    "run_blog_analysis": True,  # Skip company workflows for now
    "linkedin_profile_url": "https://www.linkedin.com/in/example-user-3/",  # LinkedIn URL
    "company_url": "https://www.example2.com/blog",  # Company website URL (optional)
    "blog_start_urls": ["https://www.example2.com/blog"] # Example blog start URL
}

workflow_inputs_3 = {
    "entity_username": "example-user-4",  # LinkedIn username
    "company_name": "ExampleCorp3",  # Company name for analysis
    "run_linkedin_exec": True,  # Execute LinkedIn workflows
    "run_blog_analysis": True,  # Skip company workflows for now
    "linkedin_profile_url": "https://www.linkedin.com/in/example-user-4/",  # LinkedIn URL
    "company_url": "https://www.example3.com/blog/",  # Company website URL (optional)
    "blog_start_urls": ["https://www.example3.com/blog/"] # Example blog start URL
}

workflow_inputs = [workflow_inputs_1]  # , workflow_inputs_2, workflow_inputs_3

workflow_version = None
predefined_hitl_inputs = []
validate_workflow_output = None
test_name = "test_run_1"


async def search_workflow_by_name(name: str, workflow_tester: WorkflowTestClient, version: Optional[str] = None) -> Optional[wf_schemas.WorkflowRead]:
    """Search for a workflow by name and optional version tag."""
    search_results = await workflow_tester.search_workflows(
        name=name,
        version_tag=version,
        include_public=True,
        include_system_entities=True
    )
    
    if not search_results or len(search_results) == 0:
        return None
    
    if len(search_results) > 1:
        # If multiple workflows found, use the most recently updated one but log a warning
        logger.warning(f"[{test_name}] Multiple workflows ({len(search_results)}) found with name '{name}'. Using the most recently updated one.")
        print(f"   ⚠ Multiple workflows ({len(search_results)}) found with name '{name}'. Using the most recently updated one.")
    
    # Return the first (most recently updated) workflow
    return search_results[0]


async def test(workflow_name, inputs, workflow_version=None, parallel_submit_limit=5):
    # final_run_status_obj, final_run_outputs = await run_workflow_test(
    #     test_name=test_name,
    #     workflow_key=workflow_key,
    #     initial_inputs=workflow_inputs,
    #     # OPTIONAL: if not provided, user is prompted to enter input in JSON during workflow execution
    #     hitl_inputs=predefined_hitl_inputs,
    #     # OPTIONAL: can be None, a function to assert and only to validate final workflow output
    #     validate_output_func=validate_workflow_output,
    #     # Don't change unless necessary
    #     expected_final_status=WorkflowRunStatus.COMPLETED,
    #     stream_intermediate_results=True,
    #     poll_interval_sec=3,
    #     timeout_sec=600,
    #     # on_behalf_of_user_id="700ddb39-23b2-4426-be12-9db263a9c7a8"
    # )
    async with AuthenticatedClient() as auth_client:
        run_client: WorkflowRunTestClient = WorkflowRunTestClient(auth_client)
        workflow_tester: WorkflowTestClient = WorkflowTestClient(auth_client) # Added for validation


        found_workflow = await search_workflow_by_name(workflow_name, workflow_tester, workflow_version)
                    
        if not found_workflow:
            error_msg = f"No workflow found with name '{workflow_name}'{f' and version {workflow_version}' if workflow_version else ''}"
            logger.error(f"[{test_name}] {error_msg}")
            print(f"   ✗ {error_msg}")
            raise RuntimeError(error_msg)
        
        resolved_workflow_id = found_workflow.id

        for i in range(parallel_submit_limit):
            if not isinstance(inputs, list):
                inputs = [inputs]
            for input in inputs:
                submitted_run = await run_client.submit_run(
                    workflow_id=resolved_workflow_id, 
                    inputs=input,
                    # streaming_mode=False,
                    # on_behalf_of_user_id=on_behalf_of_user_id,
                    # thread_id=thread_id
                )

if __name__ == "__main__":
    asyncio.run(test(workflow_name=workflow_key, inputs=workflow_inputs, parallel_submit_limit=1))