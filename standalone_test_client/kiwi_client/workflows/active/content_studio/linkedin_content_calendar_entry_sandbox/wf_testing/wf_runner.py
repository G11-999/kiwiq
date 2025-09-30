from typing import Dict, Any, List, Optional
import asyncio
import logging
import json
import os
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import workflow testing utilities
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

from kiwi_client.workflows.active.content_studio.linkedin_content_calendar_entry_sandbox.wf_linkedin_content_calendar_entry_json import (
    workflow_graph_schema,
)

from kiwi_client.workflows.active.content_studio.linkedin_content_calendar_entry_sandbox.wf_testing.wf_inputs import (
    test_name,
    test_scenario,
)

from kiwi_client.workflows.active.content_studio.linkedin_content_calendar_entry_sandbox.wf_testing.sandbox_setup_docs import (
    setup_docs,
    cleanup_docs,
)

# from kiwi_client.workflows.active.content_studio.linkedin_content_calendar_entry_sandbox.wf_testing.wf_run_hitl_inputs import (
#     hitl_inputs,
# )

WORKFLOW_NAME_TO_INGEST_AS_FOR_TESTING = "test_linkedin_content_calendar_entry_workflow"


# --- Path Configuration ---
def get_workflow_paths():
    """
    Determine default paths relative to the workflow folder.
    
    Assumes the user runs the workflow from wf_runner.py folder and navigates
    to find the parent workflow folder accordingly.
    
    Returns:
        tuple: (hitl_inputs_file_path, runs_folder_path, state_filter_mapping_file_path)
    """
    # Current file is in: workflow_folder/wf_testing/wf_runner.py
    current_file_dir = Path(__file__).parent  # wf_testing folder
    workflow_folder = current_file_dir.parent  # workflow main folder (linkedin_content_calendar_entry_sandbox)
    
    # Default HITL inputs file path
    hitl_inputs_file_path = current_file_dir / "wf_run_hitl_inputs.py"
    
    # Default runs folder path
    runs_folder_path = current_file_dir / "runs"
    
    # Default state mapping file path
    state_filter_mapping_file_path = current_file_dir / "wf_state_filter_mapping.py"
    
    return str(hitl_inputs_file_path), str(runs_folder_path), str(state_filter_mapping_file_path)


def load_state_filter_mapping(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Load state mapping from a Python file for filtering workflow state dumps.
    
    Args:
        file_path: Path to the Python file containing state_filter_mapping variable
        
    Returns:
        Dictionary mapping for state filtering, or None if file doesn't exist or has issues
    """
    try:
        if not os.path.exists(file_path):
            logger.warning(f"State mapping file not found: {file_path}. Using unfiltered state dumps.")
            return None
            
        # Load the mapping file dynamically
        import importlib.util
        import sys
        
        spec = importlib.util.spec_from_file_location("wf_state_filter_mapping", file_path)
        if spec is None or spec.loader is None:
            logger.warning(f"Could not load state mapping spec from {file_path}")
            return None
            
        mapping_module = importlib.util.module_from_spec(spec)
        sys.modules["wf_state_filter_mapping"] = mapping_module
        spec.loader.exec_module(mapping_module)
        
        # Extract the state_filter_mapping variable
        if hasattr(mapping_module, 'state_filter_mapping'):
            mapping = mapping_module.state_filter_mapping
            if mapping:
                logger.info(f"Loaded state mapping with {len(mapping)} sections from {file_path}")
                return mapping
            else:
                logger.info(f"Empty state mapping loaded from {file_path}. Using unfiltered state dumps.")
                return None
        else:
            logger.warning(f"No 'state_filter_mapping' variable found in {file_path}")
            return None
            
    except Exception as e:
        logger.warning(f"Error loading state mapping from {file_path}: {e}. Using unfiltered state dumps.")
        return None


# --- Testing Code ---

async def validate_brief_to_blog_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Validate the brief to blog workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run.
        
    Returns:
        True if the outputs are valid, False otherwise.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating brief to blog workflow outputs...")
    
    # Check for expected keys
    expected_keys = ['generated_content', 'knowledge_enrichment_results']
    for key in expected_keys:
        assert key in outputs, f"Validation Failed: '{key}' key missing."
    
    # Validate generated content structure
    generated_content = outputs.get('generated_content', {})
    assert isinstance(generated_content, dict), "Validation Failed: generated_content should be a dict."
    
    # Check for essential content fields
    content_fields = ['title', 'main_content']
    for field in content_fields:
        assert field in generated_content, f"Validation Failed: '{field}' missing from generated content."
        assert generated_content[field], f"Validation Failed: '{field}' is empty."
    
    # Validate knowledge enrichment results
    knowledge_results = outputs.get('knowledge_enrichment_results', {})
    assert isinstance(knowledge_results, dict), "Validation Failed: knowledge_enrichment_results should be a dict."
    
    if 'enriched_sections' in knowledge_results:
        enriched_sections = knowledge_results['enriched_sections']
        assert isinstance(enriched_sections, list), "Validation Failed: enriched_sections should be a list."
    
    # Check if blog post was saved (optional)
    final_blog_post_paths = outputs.get('final_blog_post_paths')
    final_blog_post_data = outputs.get('final_blog_post_data')
    if final_blog_post_paths:
        logger.info("✓ Blog post was successfully saved")
        assert isinstance(final_blog_post_paths, list), "Validation Failed: final_blog_post_paths should be a list."
        logger.info(f"   Blog post saved to: {final_blog_post_paths}")
    if final_blog_post_data:
        logger.info(f"   Blog post data available: {type(final_blog_post_data)}")
    
    logger.info("✓ Output validation passed.")
    logger.info(f"   Content title: {generated_content.get('title', 'N/A')}")
    logger.info(f"   Main content length: {len(generated_content.get('main_content', ''))}")
    logger.info(f"   Knowledge sections enriched: {len(knowledge_results.get('enriched_sections', []))}")
    
    return True


async def main_test_brief_to_blog():
    """
    Test the Brief to Blog Generation Workflow with enhanced functionality.
    """
    
    # Get default paths  
    default_hitl_inputs_path, default_runs_folder_path, default_state_filter_mapping_path = get_workflow_paths()
    
    # Load state mapping for filtering dumps
    state_filter_mapping = load_state_filter_mapping(default_state_filter_mapping_path)
    
    print(f"\n--- Running Scenario: {test_scenario['name']} ---")
    # print(f"HITL Inputs: Using predefined inputs ({len(hitl_inputs)} inputs)")
    print(f"HITL Inputs File (fallback): {default_hitl_inputs_path}")
    print(f"Runs Folder: {default_runs_folder_path}")
    print(f"State Mapping File: {default_state_filter_mapping_path}")
    if state_filter_mapping:
        print(f"State Filtering: Enabled ({len(state_filter_mapping)} sections)")
    else:
        print(f"State Filtering: Disabled (full state dumps)")
    
    try:
        # Using HITL inputs directly imported from wf_run_hitl_inputs.py
        # Fallback option: can also use hitl_inputs_file_path=default_hitl_inputs_path
        final_status, final_outputs = await run_workflow_test(
            test_name=f"{test_name} - {test_scenario['name']}",
            workflow_graph_schema=workflow_graph_schema,
            workflow_name_to_ingest_as_for_testing=WORKFLOW_NAME_TO_INGEST_AS_FOR_TESTING,
            initial_inputs=test_scenario['initial_inputs'],
            expected_final_status=WorkflowRunStatus.COMPLETED,
            # hitl_inputs=hitl_inputs,
            runs_folder_path=default_runs_folder_path,
            state_filter_mapping=state_filter_mapping,
            setup_docs=setup_docs,
            cleanup_docs=cleanup_docs,
            cleanup_docs_created_by_setup=False,
            validate_output_func=validate_brief_to_blog_output,
            stream_intermediate_results=True,
            poll_interval_sec=3,
            timeout_sec=1800
        )
        
        # Display results
        if final_outputs:
            print(f"\nTest Results:")
            generated_content = final_outputs.get('generated_content', {})
            print(f"Generated Title: {generated_content.get('title', 'N/A')}")
            print(f"Content Length: {len(generated_content.get('main_content', ''))} characters")
            
            knowledge_results = final_outputs.get('knowledge_enrichment_results', {})
            enriched_sections = knowledge_results.get('enriched_sections', [])
            print(f"Knowledge Sections Enriched: {len(enriched_sections)}")
            
            if final_outputs.get('final_blog_post_paths'):
                print("✓ Blog post was successfully saved")
                print(f"Saved to: {final_outputs.get('final_blog_post_paths')}")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
    
    print(f"\n--- {test_name} Completed Successfully ---")


# Entry point
if __name__ == "__main__":
    print("="*60)
    print("Brief to Blog Generation Workflow Test")
    print("="*60)
    
    try:
        asyncio.run(main_test_brief_to_blog())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.exception("Test execution failed")
    
    print("\nTest execution finished.")
    print("Run from project root: PYTHONPATH=. python kiwi_client/workflows_for_blog_teammate/wf_brief_to_blog.py")
