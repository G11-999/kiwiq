from kiwi_client.workflows.active.sandbox_identifiers import (
    test_sandbox_company_name,
)

from kiwi_client.workflows.active.content_studio.blog_brief_to_blog_sandbox.wf_testing.sandbox_setup_docs import (
    test_brief_uuid,
    test_brief_docname,
)


test_name = "Brief to Blog Generation Workflow Test"
print(f"\n--- Starting {test_name} ---")

# Create test blog brief data

# Test scenario
test_scenario = {
    "name": "Generate Blog Content from Brief",
    "initial_inputs": {
        "company_name": test_sandbox_company_name,
        "brief_docname": test_brief_docname,
        "post_uuid": f"blog_post_{test_brief_uuid}",
        # Example of optional additional user files to load during content generation
        "load_additional_user_files": [
            # {
            #     "namespace": "blog_uploaded_files_otter",
            #     "docname": "blog_ai_visibility_raw_data_8d0f51bb-6e56-4075-9f22-134932205805",
            #     "is_shared": False
            # },
        ]
    }
}
