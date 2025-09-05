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

workflow_key = "content_calendar_entry_workflow"

entity_username = "mahak-vedi"
workflow_inputs =  {
    "entity_username": entity_username,
    "weeks_to_generate": 1,
    "customer_context_doc_configs": [
        {
            "filename_config": {
                "input_namespace_field_pattern": "user_strategy_{item}",
                "input_namespace_field": "entity_username",
                "static_docname": "user_dna_doc"
            },
            "output_field_name": "user_dna"
        },
        {
            "filename_config": {
                "input_namespace_field_pattern": "user_inputs_{item}",
                "input_namespace_field": "entity_username",
                "static_docname": "user_preferences_doc"
            },
            "output_field_name": "user_preferences"
        },
        {
            "filename_config": {
                "input_namespace_field_pattern": "user_strategy_{item}",
                "input_namespace_field": "entity_username",
                "static_docname": "content_strategy_doc"
            },
            "output_field_name": "strategy_doc"
        },
        {
            "filename_config": {
                "input_namespace_field_pattern": "scraping_results_{item}",
                "input_namespace_field": "entity_username",
                "static_docname": "linkedin_scraped_posts_doc"
            },
            "output_field_name": "scraped_posts"
        }
    ],
    "past_context_posts_limit": 20
}

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
            submitted_run = await run_client.submit_run(
                workflow_id=resolved_workflow_id, 
                inputs=inputs,
                # streaming_mode=False,
                # on_behalf_of_user_id=on_behalf_of_user_id,
                # thread_id=thread_id
            )

if __name__ == "__main__":
    asyncio.run(test(workflow_name=workflow_key, inputs=workflow_inputs, parallel_submit_limit=50))