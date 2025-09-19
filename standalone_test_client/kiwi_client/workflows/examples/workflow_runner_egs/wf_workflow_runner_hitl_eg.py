"""
Workflow Runner HITL Example: External Research Orchestration

This workflow demonstrates advanced workflow orchestration with HITL support by using 
the workflow_runner node to execute the on-demand external research workflow.

Key Features Demonstrated:
1. **Workflow Runner Integration**: Execute child workflows from parent workflows
2. **HITL Bubbling**: Handle HITL requests from subworkflows by bubbling them up to parent HITL nodes
3. **Dynamic Input Mapping**: Map parent workflow inputs to child workflow requirements
4. **HITL Resume Flow**: Resume subworkflows from HITL state with user-provided inputs
5. **Conditional Routing**: Route execution based on subworkflow status (completed vs HITL)

HITL Flow:
1. Parent workflow runs external research workflow via workflow_runner
2. If subworkflow reaches HITL (research approval), workflow_runner returns with HITL details
3. Parent workflow routes to its own HITL node, presenting subworkflow HITL request
4. User provides input to parent HITL node
5. Parent workflow loops back to workflow_runner with HITL inputs to resume subworkflow
6. Process continues until subworkflow completes

This pattern enables complex multi-workflow HITL scenarios while maintaining clean separation.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from functools import partial

# Import workflow testing utilities
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.test_config import CLIENT_LOG_LEVEL
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

# Import document model constants for external research
from kiwi_client.workflows.active.document_models.customer_docs import (
    EXTERNAL_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
)

# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)

# Configuration constants
MAX_HITL_ITERATIONS = 5  # Maximum number of HITL iterations to prevent infinite loops
EXTERNAL_RESEARCH_WORKFLOW_NAME = "external_research_workflow"

# --- Workflow Graph Definition ---
workflow_graph_schema = {
    "nodes": {
        # --- 1. Input Node ---
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    # External research workflow inputs
                    "research_context": {
                        "type": "str",
                        "required": True,
                        "description": "The research topic or context to investigate"
                    },
                    "asset_name": {
                        "type": "str",
                        "required": True,
                        "description": "Asset name used for namespace and docname placeholder replacement"
                    },
                    "namespace": {
                        "type": "str",
                        "required": False,
                        "default": EXTERNAL_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
                        "description": "Optional namespace for saving research report. Use {item} placeholder for asset name insertion"
                    },
                    "docname": {
                        "type": "str", 
                        "required": False,
                        "description": "Optional docname for saving research report. Use {item} for random UUID suffix insertion"
                    },
                    "is_shared": {
                        "type": "bool",
                        "required": False,
                        "default": False,
                        "description": "Optional flag to determine if research report should be shared. Defaults to False"
                    }
                }
            }
        },
        
        # --- 2. External Research Workflow Runner ---
        "research_workflow_runner": {
            "node_id": "research_workflow_runner",
            "node_name": "workflow_runner",
            "node_config": {
                # Target workflow identification
                "workflow_name": EXTERNAL_RESEARCH_WORKFLOW_NAME,
                
                # Execution settings
                "execution_mode": "subprocess",  # Run as subprocess with parent-child relationship
                "poll_interval_seconds": 3,
                "timeout_seconds": 1800,  # 30 minutes for comprehensive research
                
                # Error handling
                "fail_on_workflow_error": False,  # Don't fail on HITL - we handle it
                
                # Input mapping - direct field matching since names align
                "input_mapping": None,  # Use direct field name matching
                
                # Output filtering - we want all outputs to handle HITL properly
                "output_fields": None  # Return all workflow outputs
            }
        },
        
        # --- 3. Check Subworkflow Status ---
        "check_subworkflow_status": {
            "node_id": "check_subworkflow_status",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "subworkflow_completed",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "status",
                                "operator": "equals",
                                "value": "completed"
                            }]
                        }]
                    },
                    {
                        "tag": "subworkflow_hitl",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "status", 
                                "operator": "equals",
                                "value": "waiting_hitl"
                            }]
                        }]
                    }
                ],
                "branch_logic_operator": "and"
            }
        },
        
        # --- 4. Route Based on Subworkflow Status ---
        "route_subworkflow_status": {
            "node_id": "route_subworkflow_status", 
            "node_name": "router_node",
            "node_config": {
                "choices": ["output_node", "parent_hitl_handler"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "output_node",
                        "input_path": "tag_results.subworkflow_completed",
                        "target_value": True
                    },
                    {
                        "choice_id": "parent_hitl_handler", 
                        "input_path": "tag_results.subworkflow_hitl",
                        "target_value": True
                    },
                ],
                "default_choice": "output_node"
            }
        },
        
        # --- 7. Parent HITL Handler (Bubbles up subworkflow HITL) ---
        "parent_hitl_handler": {
            "node_id": "parent_hitl_handler",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "hitl_inputs": {
                        "type": "dict",
                        "required": False,
                        "description": "Feedback for research improvements (required if action is request_revisions)"
                    }
                }
            }
        },
        
        # --- 9. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node", 
            "node_config": {}
        }
    },
    
    # --- Edges Defining Data Flow ---
    "edges": [
        # Input -> Store initial values in state
        {
            "src_node_id": "input_node",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "research_context", "dst_field": "research_context"},
                {"src_field": "asset_name", "dst_field": "asset_name"},
                {"src_field": "namespace", "dst_field": "namespace"},
                {"src_field": "docname", "dst_field": "docname"}, 
                {"src_field": "is_shared", "dst_field": "is_shared"}
            ]
        },
        
        # Input -> Research Workflow Runner: Pass all required inputs
        {
            "src_node_id": "input_node",
            "dst_node_id": "research_workflow_runner",
            "mappings": [
                {"src_field": "research_context", "dst_field": "research_context"},
                {"src_field": "asset_name", "dst_field": "asset_name"}, 
                {"src_field": "namespace", "dst_field": "namespace"},
                {"src_field": "docname", "dst_field": "docname"},
                {"src_field": "is_shared", "dst_field": "is_shared"}
            ]
        },
        
        # Research Workflow Runner -> State: Store execution results 
        {
            "src_node_id": "research_workflow_runner",
            "dst_node_id": "$graph_state", 
            "mappings": [
                {"src_field": "run_id", "dst_field": "subworkflow_run_id"},
                {"src_field": "status", "dst_field": "subworkflow_status"},
                {"src_field": "workflow_outputs", "dst_field": "subworkflow_outputs"},
                {"src_field": "error_message", "dst_field": "subworkflow_error"},
                {"src_field": "hitl_job_id", "dst_field": "hitl_job_id"},
                {"src_field": "hitl_request_schema", "dst_field": "hitl_request_schema"},
                {"src_field": "hitl_request_details", "dst_field": "hitl_request_details"}
            ]
        },
        
        # Research Workflow Runner -> Check Status
        {
            "src_node_id": "research_workflow_runner",
            "dst_node_id": "check_subworkflow_status",
            "mappings": [
                {"src_field": "status", "dst_field": "status"}
            ]
        },
        
        # Check Status -> Route Status
        {
            "src_node_id": "check_subworkflow_status", 
            "dst_node_id": "route_subworkflow_status",
            "mappings": [
                {"src_field": "tag_results", "dst_field": "tag_results"}
            ]
        },
        
        # Route -> Parent HITL Handler
        {
            "src_node_id": "route_subworkflow_status", 
            "dst_node_id": "parent_hitl_handler"
        },
        
        # State -> Parent HITL Handler (bubble up subworkflow HITL details)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "parent_hitl_handler",
            "mappings": [
                {"src_field": "hitl_job_id", "dst_field": "hitl_job_id"},
                {"src_field": "hitl_request_schema", "dst_field": "hitl_request_schema"},
                {"src_field": "hitl_request_details", "dst_field": "hitl_request_details"},
                {"src_field": "subworkflow_outputs", "dst_field": "subworkflow_outputs"}
            ]
        },
        
        # Parent HITL -> State (store user response and increment iteration count)
        {
            "src_node_id": "parent_hitl_handler",
            "dst_node_id": "$graph_state", 
            "mappings": [
                {"src_field": "hitl_inputs", "dst_field": "hitl_inputs"},
            ]
        },
        
        # Parent HITL -> Research Workflow Runner (resume with HITL inputs)
        {
            "src_node_id": "parent_hitl_handler",
            "dst_node_id": "research_workflow_runner",
            "mappings": [
                {"src_field": "hitl_inputs", "dst_field": "hitl_inputs"},
            ]
        },
        
        # State -> Research Workflow Runner (provide subworkflow run ID for HITL resume)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "research_workflow_runner", 
            "mappings": [
                {"src_field": "subworkflow_run_id", "dst_field": "subworkflow_run_id"}
            ]
        },
        
        # Route -> Output Node (multiple paths)
        {
            "src_node_id": "route_subworkflow_status",
            "dst_node_id": "output_node"
        },
        
        # State -> Output Node (pass final results)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "subworkflow_outputs", "dst_field": "research_results"},
                {"src_field": "subworkflow_status", "dst_field": "final_status"},
                {"src_field": "subworkflow_error", "dst_field": "error_message"},
            ]
        },
    ],
    
    # --- Define Start and End ---
    "input_node_id": "input_node", 
    "output_node_id": "output_node",
    
    # --- State Management ---
    "metadata": {
        "$graph_state": {
            "reducer": {
            }
        }
    }
}

# --- Validation Function ---
async def validate_workflow_runner_hitl_output(
    outputs: Optional[Dict[str, Any]], 
    expected_inputs: Dict[str, Any]
) -> bool:
    """
    Custom validation function for the workflow runner HITL outputs.
    
    Validates both the orchestration metadata and the actual research results.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run
        expected_inputs: The original inputs for comparison
        
    Returns:
        True if outputs are valid, False otherwise
        
    Raises:
        AssertionError: If validation fails
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating workflow runner HITL outputs...")
    
    # Check final status
    final_status = outputs.get('final_status')
    assert final_status is not None, "Validation Failed: 'final_status' missing in outputs."
    logger.info(f"   Final Status: {final_status}")
    
    # If completed successfully, validate research results
    if final_status == 'completed':
        research_results = outputs.get('research_results')
        assert research_results is not None, "Validation Failed: 'research_results' missing for completed workflow."
        
        # Validate research content structure
        if 'research_content' in research_results:
            research_content = research_results['research_content']
            assert 'report' in research_content, "Research content missing 'report' field"
            logger.info(f"   Research Report Length: {len(research_content.get('report', ''))} characters")
            
            if 'citations' in research_content:
                citations = research_content['citations']
                logger.info(f"   Citations Available: {bool(citations)}")
        
        # Check for saved paths
        if 'final_research_paths' in research_results:
            paths = research_results['final_research_paths']
            if paths:
                logger.info(f"   Research Saved: {len(paths)} documents")
    
    # Check HITL iteration usage
    hitl_iterations = outputs.get('hitl_iterations_used', 0)
    logger.info(f"   HITL Iterations Used: {hitl_iterations}")
    
    # Check for error cases
    if outputs.get('error_message'):
        logger.info(f"   Error Message: {outputs['error_message']}")
    
    logger.info("✓ Workflow runner HITL validation passed.")
    return True

# --- Test Execution Function ---
async def main_test_workflow_runner_hitl(
    research_topic: str = "Impact of AI on software development in 2024",
    asset_name: str = "ai_software_dev_2024",
    include_hitl_test: bool = True
):
    """
    Test the Workflow Runner HITL Example by orchestrating external research.
    
    Args:
        research_topic: Research context/topic for investigation
        asset_name: Asset name for document organization  
        include_hitl_test: Whether to test HITL flow with predefined inputs
    """
    test_name = "Workflow Runner HITL Test"
    print(f"\n--- Starting {test_name} ---")
    print(f"Research Topic: {research_topic}")
    print(f"Asset Name: {asset_name}")
    print(f"Execution Mode: subprocess (hardcoded)")
    print(f"HITL Testing: {'Enabled' if include_hitl_test else 'Disabled'}")
    
    # Prepare workflow inputs
    workflow_inputs = {
        "research_context": research_topic,
        "asset_name": asset_name,
        "namespace": EXTERNAL_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
        # "docname": None,  # Let it auto-generate
        "is_shared": False
    }
    
    # Predefined HITL inputs for testing the bubbling mechanism
    predefined_hitl_inputs = []
    if include_hitl_test:
        predefined_hitl_inputs = [
            # 1) First HITL: Request revisions (simulating subworkflow HITL bubble-up)
            {"hitl_inputs": {
                "user_action": "request_revisions",
                "revision_feedback": "Please expand the analysis on AI code generation tools and add more specific examples of productivity improvements with metrics."
            }},
            # 2) Second HITL: Approve final version 
            {"hitl_inputs": {
                "user_action": "approve",
                "revision_feedback": None
            }}
        ]
    
    # Setup and cleanup (no special docs needed for this orchestration example)
    setup_docs: List[SetupDocInfo] = []
    cleanup_docs: List[CleanupDocInfo] = []
    
    print(f"\n--- Executing Orchestration Workflow ---")
    
    try:
        final_status, final_outputs = await run_workflow_test(
            test_name=test_name,
            workflow_graph_schema=workflow_graph_schema,
            initial_inputs=workflow_inputs,
            expected_final_status=WorkflowRunStatus.COMPLETED,
            hitl_inputs=predefined_hitl_inputs if include_hitl_test else None,
            setup_docs=setup_docs,
            cleanup_docs=cleanup_docs,
            cleanup_docs_created_by_setup=False,
            validate_output_func=partial(
                validate_workflow_runner_hitl_output,
                expected_inputs=workflow_inputs
            ),
            stream_intermediate_results=True,
            poll_interval_sec=5,  # Longer interval since subworkflow may take time
            timeout_sec=2400  # 40 minutes total (subworkflow + orchestration overhead)
        )
        
        # Display detailed results
        if final_outputs:
            print(f"\n--- Orchestration Results ---")
            final_status_value = final_outputs.get('final_status', 'unknown')
            print(f"Final Status: {final_status_value}")
            
            hitl_iterations = final_outputs.get('hitl_iterations_used', 0)
            print(f"HITL Iterations: {hitl_iterations}")
            
            if final_status_value == 'completed':
                research_results = final_outputs.get('research_results', {})
                
                # Research content details
                research_content = research_results.get('research_content', {})
                if research_content:
                    report = research_content.get('report', '')
                    print(f"Research Report Length: {len(report)} characters")
                    
                    citations = research_content.get('citations', {})
                    if citations and isinstance(citations, dict):
                        citation_count = len(citations.get('citations', []))
                        print(f"Sources Cited: {citation_count}")
                
                # Document storage
                final_paths = research_results.get('final_research_paths', [])
                if final_paths:
                    print(f"Documents Saved: {len(final_paths)} paths")
                    print("✓ Research successfully completed and saved")
                
                print("\n✓ External research workflow orchestrated successfully!")
                
            else:
                error_msg = final_outputs.get('error_message', 'Unknown error')
                print(f"Error: {error_msg}")
                
        else:
            print("No outputs received from orchestration workflow")
        
    except Exception as e:
        logger.error(f"Orchestration test failed: {e}", exc_info=True)
        raise
    
    print(f"\n--- {test_name} Finished ---")
    return final_status, final_outputs

# --- Entry Point ---
if __name__ == "__main__":
    print("="*60)
    print("Workflow Runner HITL Example")  
    print("="*60)
    print("\nThis example demonstrates advanced workflow orchestration with HITL support.")
    print("The parent workflow uses workflow_runner to execute the external research workflow")
    print("and handles HITL requests by bubbling them up to its own HITL node.")
    print("\nKey Features:")
    print("1. Subworkflow execution with HITL support")
    print("2. HITL request bubbling from child to parent workflow") 
    print("3. HITL resume flow with user input propagation")
    print("4. Iteration limits to prevent infinite HITL loops")
    
    # Configuration for the test
    test_config = {
        "research_topic": "Impact of generative AI on software engineering productivity and code quality in 2024-2025",
        "asset_name": "genai_software_eng_2024",
        "include_hitl_test": True
    }
    
    print(f"\nRunning with configuration:")
    print(f"  Research Topic: {test_config['research_topic']}")
    print(f"  Asset Name: {test_config['asset_name']}")
    print(f"  Execution Mode: subprocess (hardcoded)")
    print(f"  HITL Testing: {test_config['include_hitl_test']}")
    
    # Handle async execution
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        print("\nAsync event loop already running. Adding task...")
        task = loop.create_task(main_test_workflow_runner_hitl(**test_config))
    else:
        print("\nStarting new async event loop...")
        asyncio.run(main_test_workflow_runner_hitl(**test_config))
    
    print("\n" + "-"*60)
    print("Run this script from the project root directory using:")
    print("PYTHONPATH=$(pwd):$(pwd)/services poetry run python standalone_test_client/kiwi_client/workflows/examples/workflow_runner_egs/wf_workflow_runner_hitl_eg.py")
    print("-"*60)
