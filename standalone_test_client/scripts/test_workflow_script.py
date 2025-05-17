import asyncio
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus
from kiwi_client.test_run_workflow_client import run_workflow_test

# from kiwi_client.test_config import TEST_USER_EMAIL

# print(TEST_USER_EMAIL)

workflow_key = "content_strategy_workflow"
workflow_inputs =  {
    "customer_context_doc_configs": [
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
                "input_namespace_field_pattern": "user_analysis_{item}",
                "input_namespace_field": "entity_username",
                "static_docname": "user_source_analysis"
            },
            "output_field_name": "user_source_analysis"
        },
        {
            "filename_config": {
                "input_namespace_field_pattern": "user_inputs_{item}",
                "input_namespace_field": "entity_username",
                "static_docname": "core_beliefs_perspectives_doc"
            },
            "output_field_name": "core_beliefs_perspectives"
        },
        {
            "filename_config": {
                "input_namespace_field_pattern": "user_inputs_{item}",
                "input_namespace_field": "entity_username",
                "static_docname": "content_pillars_doc"
            },
            "output_field_name": "content_pillars"
        },
        {
            "filename_config": {
                "static_namespace": "system_strategy_docs_namespace",
                "static_docname": "methodology_implementation_ai_copilot"
            },
            "output_field_name": "methodology_implementation",
            "is_shared": True,
            "is_system_entity": True
        },
        {
            "filename_config": {
                "static_namespace": "system_strategy_docs_namespace",
                "static_docname": "building_blocks_content_methodology"
            },
            "output_field_name": "building_blocks",
            "is_shared": True,
            "is_system_entity": True
        }
    ],
    "entity_username": "test_entity"
}
predefined_hitl_inputs = []
validate_workflow_output = None
test_name = "test_run_1"
async def test():
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_key=workflow_key,
        initial_inputs=workflow_inputs,
        # OPTIONAL: if not provided, user is prompted to enter input in JSON during workflow execution
        hitl_inputs=predefined_hitl_inputs,
        # OPTIONAL: can be None, a function to assert and only to validate final workflow output
        validate_output_func=validate_workflow_output,
        # Don't change unless necessary
        expected_final_status=WorkflowRunStatus.COMPLETED,
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=600,
        # on_behalf_of_user_id="700ddb39-23b2-4426-be12-9db263a9c7a8"
    )
if __name__ == "__main__":
    asyncio.run(test())
