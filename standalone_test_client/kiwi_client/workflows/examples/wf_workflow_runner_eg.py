"""
Example Workflow: Workflow Runner Node Demonstration

This workflow demonstrates how to use the workflow_runner node to:
1. Execute another workflow (linkedin_content_strategy_workflow) from within a workflow
2. Pass dynamic inputs to the child workflow
3. Handle the outputs from the executed workflow
4. Validate the results based on expected schema

The workflow is useful for:
- Orchestrating complex multi-workflow pipelines
- Reusing existing workflows as building blocks
- Creating workflow hierarchies with parent-child relationships
- Conditional workflow execution based on previous results
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
from functools import partial
from datetime import datetime

# Import necessary components for workflow testing
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.test_config import CLIENT_LOG_LEVEL
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

# Import document models for content strategy workflow
from kiwi_client.workflows.examples.document_models.customer_docs import (
    # Content Strategy
    CONTENT_STRATEGY_DOCNAME,
    CONTENT_STRATEGY_NAMESPACE_TEMPLATE,
    CONTENT_STRATEGY_IS_VERSIONED,
    # User Preferences
    USER_PREFERENCES_DOCNAME,
    USER_PREFERENCES_NAMESPACE_TEMPLATE,
    USER_PREFERENCES_IS_VERSIONED,
    # Source Analysis
    USER_SOURCE_ANALYSIS_DOCNAME,
    USER_SOURCE_ANALYSIS_NAMESPACE_TEMPLATE,
    USER_SOURCE_ANALYSIS_IS_VERSIONED,
    # Core Beliefs and Perspectives
    CORE_BELIEFS_PERSPECTIVES_DOCNAME,
    CORE_BELIEFS_PERSPECTIVES_NAMESPACE_TEMPLATE,
    CORE_BELIEFS_PERSPECTIVES_IS_VERSIONED,
    # Content Pillars
    CONTENT_PILLARS_DOCNAME,
    CONTENT_PILLARS_NAMESPACE_TEMPLATE,
    CONTENT_PILLARS_IS_VERSIONED,
    # System Strategy Documents
    METHODOLOGY_IMPLEMENTATION_DOCNAME,
    METHODOLOGY_IMPLEMENTATION_NAMESPACE_TEMPLATE,
    METHODOLOGY_IMPLEMENTATION_IS_SHARED,
    METHODOLOGY_IMPLEMENTATION_IS_SYSTEM_ENTITY,
    BUILDING_BLOCKS_DOCNAME,
    BUILDING_BLOCKS_NAMESPACE_TEMPLATE,
    BUILDING_BLOCKS_IS_SHARED,
    BUILDING_BLOCKS_IS_SYSTEM_ENTITY,
)

# Setup logger
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)


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
                    # Required fields for content strategy workflow
                    "entity_username": {
                        "type": "str",
                        "required": True,
                        "description": "Username of the entity for content strategy generation"
                    },
                    # "customer_context_doc_configs": {
                    #     "type": "list",
                    #     "required": True,
                    #     "description": "List of document configs for loading context"
                    # },
                    
                    # Optional workflow runner control fields
                    "execution_mode": {
                        "type": "str",
                        "required": False,
                        "default": "subprocess",
                        "description": "Execution mode: 'subprocess' or 'independent'"
                    },
                    "timeout_seconds": {
                        "type": "int",
                        "required": False,
                        "default": 600,
                        "description": "Timeout for workflow execution in seconds"
                    }
                }
            }
        },
        
        # --- 2. Workflow Runner Node ---
        "strategy_workflow_runner": {
            "node_id": "strategy_workflow_runner",
            "node_name": "workflow_runner",
            "node_config": {
                # Identify the workflow to run by name
                "workflow_name": "linkedin_content_strategy_workflow",
                
                # Execution settings
                "execution_mode": "subprocess",  # Run as subprocess with parent-child relationship
                "poll_interval_seconds": 3,
                "timeout_seconds": 600,
                
                # Error handling
                "fail_on_workflow_error": True,
                
                # Input mapping - direct field matching since we're passing the exact inputs
                # No input_mapping needed as field names match exactly
                
                # Output filtering - extract specific fields we care about
                "output_fields": [
                    "generated_output",
                    "paths_processed"
                ]
            }
            # The node accepts dynamic inputs that will be mapped to the child workflow
        },
        
        # --- 3. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {},
            # Will receive the execution results from the workflow runner
        }
    },
    
    # --- Edges Defining Data Flow ---
    "edges": [
        # Input -> Workflow Runner: Pass all required inputs
        {
            "src_node_id": "input_node",
            "dst_node_id": "strategy_workflow_runner",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"},
                # {"src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs"},
                # Pass optional control field for thread ID if needed
                # {"src_field": "thread_id", "dst_field": "_thread_id"}
            ]
        },
        
        # Workflow Runner -> Output: Pass execution results
        {
            "src_node_id": "strategy_workflow_runner",
            "dst_node_id": "output_node",
            "mappings": [
                # Workflow metadata
                {"src_field": "workflow_id", "dst_field": "executed_workflow_id"},
                {"src_field": "workflow_name", "dst_field": "executed_workflow_name"},
                {"src_field": "workflow_version", "dst_field": "executed_workflow_version"},
                {"src_field": "run_id", "dst_field": "child_run_id"},
                
                # Execution results
                {"src_field": "status", "dst_field": "execution_status"},
                {"src_field": "workflow_outputs", "dst_field": "strategy_results"},
                
                # Execution metadata
                {"src_field": "execution_mode", "dst_field": "execution_mode"},
                {"src_field": "started_at", "dst_field": "started_at"},
                {"src_field": "completed_at", "dst_field": "completed_at"},
                {"src_field": "duration_seconds", "dst_field": "duration_seconds"},
                {"src_field": "parent_run_id", "dst_field": "parent_run_id"},
                
                # Error info if any
                {"src_field": "error_message", "dst_field": "error_message"},
                {"src_field": "error_details", "dst_field": "error_details"}
            ]
        },
    ],
    
    # --- Define Start and End ---
    "input_node_id": "input_node",
    "output_node_id": "output_node"
}


# --- Test Execution Logic ---

async def validate_workflow_runner_output(
    outputs: Optional[Dict[str, Any]], 
    expected_inputs: Dict[str, Any]
) -> bool:
    """
    Custom validation function for the workflow runner outputs.
    
    Validates both the workflow execution metadata and the actual
    content strategy outputs from the child workflow.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run
        expected_inputs: The original inputs for comparison
        
    Returns:
        True if outputs are valid, False otherwise
        
    Raises:
        AssertionError: If validation fails
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating workflow runner outputs...")
    
    # Check for workflow execution metadata
    required_metadata_fields = [
        'executed_workflow_id', 'executed_workflow_name', 'child_run_id',
        'execution_status', 'execution_mode', 'started_at', 'completed_at',
        'duration_seconds'
    ]
    
    for field in required_metadata_fields:
        assert field in outputs, f"Validation Failed: '{field}' key missing in outputs."
    
    # Check execution status
    assert outputs['execution_status'] == 'completed', \
        f"Validation Failed: Workflow execution status was '{outputs['execution_status']}', expected 'completed'"
    
    # Log execution metadata
    logger.info(f"   Executed Workflow: {outputs.get('executed_workflow_name')}")
    logger.info(f"   Child Run ID: {outputs.get('child_run_id')}")
    logger.info(f"   Execution Status: {outputs.get('execution_status')}")
    logger.info(f"   Execution Mode: {outputs.get('execution_mode')}")
    logger.info(f"   Duration: {outputs.get('duration_seconds', 0):.2f} seconds")
    if outputs.get('parent_run_id'):
        logger.info(f"   Parent Run ID: {outputs.get('parent_run_id')}")
    
    # Validate the content strategy results from the child workflow
    assert 'strategy_results' in outputs, "Validation Failed: 'strategy_results' missing."
    
    strategy_results = outputs['strategy_results']
    if strategy_results:
        # Validate based on content strategy schema structure
        assert 'generated_output' in strategy_results, \
            "Validation Failed: 'generated_output' missing in strategy results."
        
        strategy = strategy_results['generated_output']
        
        # Basic structure validation
        assert 'title' in strategy, "Strategy missing 'title' field"
        assert 'target_audience' in strategy, "Strategy missing 'target_audience' field"
        assert 'foundation_elements' in strategy, "Strategy missing 'foundation_elements' field"
        assert 'content_pillars' in strategy, "Strategy missing 'content_pillars' field"
        assert 'implementation' in strategy, "Strategy missing 'implementation' field"
        
        # Log strategy details
        logger.info(f"   Strategy Title: {strategy.get('title', 'unknown')}")
        
        target_audience = strategy.get('target_audience', {})
        logger.info(f"   Primary Audience: {target_audience.get('primary', 'unknown')}")
        
        content_pillars = strategy.get('content_pillars', [])
        logger.info(f"   Content Pillars: {len(content_pillars)} pillars defined")
        
        # Check if paths were processed (documents saved)
        if 'paths_processed' in strategy_results:
            paths = strategy_results['paths_processed']
            logger.info(f"   Documents Saved: {len(paths) if paths else 0} paths processed")
    
    logger.info("✓ Workflow runner validation passed.")
    logger.info("✓ Child workflow executed successfully.")
    return True


async def main_test_workflow_runner(
    entity_username: str = "test_entity",
    execution_mode: str = "subprocess",
    setup_test_docs: bool = True
):
    """
    Test the Workflow Runner Node by executing the content strategy workflow.
    
    Args:
        entity_username: Username for the test entity
        execution_mode: 'subprocess' or 'independent' execution mode
        setup_test_docs: Whether to create prerequisite documents
    """
    test_name = f"Workflow Runner Test - {execution_mode.capitalize()} Mode"
    print(f"\n--- Starting {test_name} ---")
    print(f"Target Workflow: linkedin_content_strategy_workflow")
    print(f"Entity Username: {entity_username}")
    print(f"Execution Mode: {execution_mode}")
    
    # Prepare document configs for the content strategy workflow
    # INPUT_DOCS_TO_BE_LOADED = [
    #     {
    #         "filename_config": {
    #             "input_namespace_field_pattern": USER_PREFERENCES_NAMESPACE_TEMPLATE,
    #             "input_namespace_field": "entity_username",
    #             "static_docname": USER_PREFERENCES_DOCNAME,
    #         },
    #         "output_field_name": "user_preferences",
    #     },
    #     {
    #         "filename_config": {
    #             "input_namespace_field_pattern": USER_SOURCE_ANALYSIS_NAMESPACE_TEMPLATE,
    #             "input_namespace_field": "entity_username",
    #             "static_docname": USER_SOURCE_ANALYSIS_DOCNAME,
    #         },
    #         "output_field_name": "user_source_analysis",
    #     },
    #     {
    #         "filename_config": {
    #             "input_namespace_field_pattern": CORE_BELIEFS_PERSPECTIVES_NAMESPACE_TEMPLATE,
    #             "input_namespace_field": "entity_username",
    #             "static_docname": CORE_BELIEFS_PERSPECTIVES_DOCNAME,
    #         },
    #         "output_field_name": "core_beliefs_perspectives",
    #     },
    #     {
    #         "filename_config": {
    #             "input_namespace_field_pattern": CONTENT_PILLARS_NAMESPACE_TEMPLATE,
    #             "input_namespace_field": "entity_username",
    #             "static_docname": CONTENT_PILLARS_DOCNAME,
    #         },
    #         "output_field_name": "content_pillars",
    #     },
    #     {
    #         "filename_config": {
    #             "static_namespace": METHODOLOGY_IMPLEMENTATION_NAMESPACE_TEMPLATE,
    #             "static_docname": METHODOLOGY_IMPLEMENTATION_DOCNAME,
    #         },
    #         "output_field_name": "methodology_implementation",
    #         "is_shared": METHODOLOGY_IMPLEMENTATION_IS_SHARED,
    #         "is_system_entity": METHODOLOGY_IMPLEMENTATION_IS_SYSTEM_ENTITY
    #     },
    #     {
    #         "filename_config": {
    #             "static_namespace": BUILDING_BLOCKS_NAMESPACE_TEMPLATE,
    #             "static_docname": BUILDING_BLOCKS_DOCNAME,
    #         },
    #         "output_field_name": "building_blocks",
    #         "is_shared": BUILDING_BLOCKS_IS_SHARED,
    #         "is_system_entity": BUILDING_BLOCKS_IS_SYSTEM_ENTITY
    #     }
    # ]
    
    # Prepare workflow inputs
    WORKFLOW_RUNNER_INPUTS = {
        "entity_username": entity_username,
        # "customer_context_doc_configs": INPUT_DOCS_TO_BE_LOADED,
        "execution_mode": execution_mode,
        "timeout_seconds": 600
    }
    
    # Setup documents if requested
    setup_docs: List[SetupDocInfo] = []
    cleanup_docs: List[CleanupDocInfo] = []
    
    if setup_test_docs:
        # Define prerequisite documents for the content strategy workflow
        setup_docs = [
            # User Preferences
            {
                'namespace': USER_PREFERENCES_NAMESPACE_TEMPLATE.format(item=entity_username),
                'docname': USER_PREFERENCES_DOCNAME,
                'initial_data': {
                    "posts_per_week": 3,
                    "preferred_posting_days": ["Tuesday", "Thursday", "Saturday"],
                    "preferred_topics": ["AI Innovation", "Tech Leadership", "Digital Transformation"],
                    "content_tone": "Thought Leadership"
                },
                'is_versioned': USER_PREFERENCES_IS_VERSIONED,
                'is_shared': False,
                'initial_version': "default",
                'is_system_entity': False
            },
            # Source Analysis
            {
                'namespace': USER_SOURCE_ANALYSIS_NAMESPACE_TEMPLATE.format(item=entity_username),
                'docname': USER_SOURCE_ANALYSIS_DOCNAME,
                'initial_data': {
                    "primary_sources": ["Tech blogs", "Research papers", "Industry reports"],
                    "content_gaps": ["Practical implementation guides", "ROI case studies"],
                    "audience_interests": ["AI applications", "Automation", "Future of work"],
                    "engagement_patterns": {
                        "high_engagement": ["Tutorial content", "Industry predictions"],
                        "low_engagement": ["Product updates", "Company announcements"]
                    }
                },
                'is_versioned': USER_SOURCE_ANALYSIS_IS_VERSIONED,
                'is_shared': False,
                'initial_version': "default",
                'is_system_entity': False
            },
            # Core Beliefs and Perspectives
            {
                'namespace': CORE_BELIEFS_PERSPECTIVES_NAMESPACE_TEMPLATE.format(item=entity_username),
                'docname': CORE_BELIEFS_PERSPECTIVES_DOCNAME,
                'initial_data': {
                    "core_beliefs": [
                        "AI should augment human capabilities, not replace them",
                        "Ethical AI development is non-negotiable",
                        "Continuous learning is essential in tech"
                    ],
                    "key_perspectives": [
                        "The future of work is human-AI collaboration",
                        "Data privacy and AI advancement can coexist",
                        "Open-source accelerates innovation"
                    ],
                    "unique_viewpoints": [
                        "Small teams with AI can outperform large traditional teams",
                        "AI literacy should be universal education"
                    ]
                },
                'is_versioned': CORE_BELIEFS_PERSPECTIVES_IS_VERSIONED,
                'is_shared': False,
                'initial_version': "default",
                'is_system_entity': False
            },
            # Content Pillars
            {
                'namespace': CONTENT_PILLARS_NAMESPACE_TEMPLATE.format(item=entity_username),
                'docname': CONTENT_PILLARS_DOCNAME,
                'initial_data': {
                    "pillars": [
                        {
                            "name": "AI Innovation",
                            "topics": ["Machine Learning", "Natural Language Processing", "Computer Vision"],
                            "audience_pain_points": ["Implementation complexity", "ROI uncertainty", "Skill gaps"]
                        },
                        {
                            "name": "Tech Leadership",
                            "topics": ["Team building", "Strategic planning", "Change management"],
                            "audience_pain_points": ["Talent retention", "Technology adoption", "Cultural transformation"]
                        },
                        {
                            "name": "Future of Work",
                            "topics": ["Automation impact", "Skill evolution", "Remote collaboration"],
                            "audience_pain_points": ["Job displacement fears", "Reskilling needs", "Productivity concerns"]
                        }
                    ]
                },
                'is_versioned': CONTENT_PILLARS_IS_VERSIONED,
                'is_shared': False,
                'initial_version': "default",
                'is_system_entity': False
            },
            # System documents (Methodology and Building Blocks)
            {
                'namespace': METHODOLOGY_IMPLEMENTATION_NAMESPACE_TEMPLATE,
                'docname': METHODOLOGY_IMPLEMENTATION_DOCNAME,
                'initial_data': {
                    "methodology_name": "AI-Driven Content Strategy",
                    "implementation_steps": [
                        "Analyze user profile and preferences",
                        "Generate strategic content framework",
                        "Create targeted content briefs",
                        "Optimize for audience engagement"
                    ],
                    "best_practices": [
                        "Data-driven content decisions",
                        "Consistent brand voice",
                        "Audience-first approach",
                        "Iterative improvement"
                    ]
                },
                'is_versioned': False,
                'is_shared': METHODOLOGY_IMPLEMENTATION_IS_SHARED,
                'initial_version': None,
                'is_system_entity': METHODOLOGY_IMPLEMENTATION_IS_SYSTEM_ENTITY
            },
            {
                'namespace': BUILDING_BLOCKS_NAMESPACE_TEMPLATE,
                'docname': BUILDING_BLOCKS_DOCNAME,
                'initial_data': {
                    "core_building_blocks": [
                        "Target audience analysis",
                        "Content pillar definition",
                        "Engagement optimization",
                        "Performance measurement",
                        "Content calendar planning"
                    ],
                    "implementation_framework": {
                        "phase_1": "Strategic foundation",
                        "phase_2": "Content development",
                        "phase_3": "Distribution strategy",
                        "phase_4": "Performance analysis",
                        "phase_5": "Continuous optimization"
                    },
                    "success_indicators": [
                        "Engagement rate increase",
                        "Audience growth",
                        "Content consistency",
                        "Brand authority"
                    ]
                },
                'is_versioned': False,
                'is_shared': BUILDING_BLOCKS_IS_SHARED,
                'initial_version': None,
                'is_system_entity': BUILDING_BLOCKS_IS_SYSTEM_ENTITY
            }
        ]
        
        # Define cleanup documents
        cleanup_docs = [
            # User-specific documents
            {'namespace': USER_PREFERENCES_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': USER_PREFERENCES_DOCNAME, 'is_versioned': USER_PREFERENCES_IS_VERSIONED, 'is_shared': False, 'is_system_entity': False},
            {'namespace': USER_SOURCE_ANALYSIS_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': USER_SOURCE_ANALYSIS_DOCNAME, 'is_versioned': USER_SOURCE_ANALYSIS_IS_VERSIONED, 'is_shared': False, 'is_system_entity': False},
            {'namespace': CORE_BELIEFS_PERSPECTIVES_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': CORE_BELIEFS_PERSPECTIVES_DOCNAME, 'is_versioned': CORE_BELIEFS_PERSPECTIVES_IS_VERSIONED, 'is_shared': False, 'is_system_entity': False},
            {'namespace': CONTENT_PILLARS_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': CONTENT_PILLARS_DOCNAME, 'is_versioned': CONTENT_PILLARS_IS_VERSIONED, 'is_shared': False, 'is_system_entity': False},
            # Output document created by the child workflow
            {'namespace': CONTENT_STRATEGY_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': CONTENT_STRATEGY_DOCNAME, 'is_versioned': CONTENT_STRATEGY_IS_VERSIONED, 'is_shared': False, 'is_system_entity': False},
        ]
    
    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=WORKFLOW_RUNNER_INPUTS,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=None,  # No HITL needed for this test
        setup_docs=setup_docs,
        cleanup_docs=cleanup_docs,
        cleanup_docs_created_by_setup=True,
        validate_output_func=partial(
            validate_workflow_runner_output,
            expected_inputs=WORKFLOW_RUNNER_INPUTS
        ),
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=700  # Allow extra time for nested workflow execution
    )
    
    # Display detailed results
    if final_run_outputs:
        print(f"\n--- Workflow Execution Summary ---")
        print(f"Executed Workflow: {final_run_outputs.get('executed_workflow_name', 'unknown')}")
        print(f"Child Run ID: {final_run_outputs.get('child_run_id', 'unknown')}")
        print(f"Execution Status: {final_run_outputs.get('execution_status', 'unknown')}")
        print(f"Execution Mode: {final_run_outputs.get('execution_mode', 'unknown')}")
        print(f"Duration: {final_run_outputs.get('duration_seconds', 0):.2f} seconds")
        
        if final_run_outputs.get('strategy_results'):
            strategy_results = final_run_outputs['strategy_results']
            if 'generated_output' in strategy_results:
                strategy = strategy_results['generated_output']
                print(f"\n--- Generated Content Strategy ---")
                print(f"Title: {strategy.get('title', 'unknown')}")
                
                # Target audience
                audience = strategy.get('target_audience', {})
                print(f"Primary Audience: {audience.get('primary', 'unknown')}")
                if audience.get('secondary'):
                    print(f"Secondary Audience: {audience.get('secondary')}")
                
                # Foundation elements
                foundation = strategy.get('foundation_elements', {})
                if foundation.get('expertise'):
                    print(f"Areas of Expertise: {', '.join(foundation['expertise'][:3])}...")
                if foundation.get('objectives'):
                    print(f"Strategy Objectives: {len(foundation['objectives'])} defined")
                
                # Content pillars
                pillars = strategy.get('content_pillars', [])
                print(f"Content Pillars: {len(pillars)} pillars")
                for i, pillar in enumerate(pillars[:3], 1):
                    print(f"  {i}. {pillar.get('name', 'unknown')}")
                
                # Implementation timeline
                implementation = strategy.get('implementation', {})
                if implementation.get('thirty_day_targets'):
                    print(f"30-Day Goal: {implementation['thirty_day_targets'].get('goal', 'unknown')}")
                if implementation.get('ninety_day_targets'):
                    print(f"90-Day Goal: {implementation['ninety_day_targets'].get('goal', 'unknown')}")
        
        # Show any errors if present
        if final_run_outputs.get('error_message'):
            print(f"\n--- Errors ---")
            print(f"Error: {final_run_outputs['error_message']}")
            if final_run_outputs.get('error_details'):
                print(f"Details: {json.dumps(final_run_outputs['error_details'], indent=2)}")
    
    print(f"\n--- {test_name} Finished ---")
    
    return final_run_status_obj, final_run_outputs


if __name__ == "__main__":
    print("="*60)
    print("Workflow Runner Node Example")
    print("="*60)
    print("\nThis example demonstrates executing a child workflow from a parent workflow.")
    print("The parent workflow uses the workflow_runner node to execute")
    print("the 'linkedin_content_strategy_workflow' and capture its results.")
    print("\nExecution modes:")
    print("1. Subprocess - Run as child with parent-child relationship")
    print("2. Independent - Run as separate workflow with monitoring")
    
    # Configuration for the test
    test_config = {
        "entity_username": "demo_user",
        "execution_mode": "subprocess",  # or "independent"
        "setup_test_docs": True  # Create prerequisite documents
    }
    
    print(f"\nRunning with configuration:")
    print(f"  Entity: {test_config['entity_username']}")
    print(f"  Mode: {test_config['execution_mode']}")
    print(f"  Setup Docs: {test_config['setup_test_docs']}")
    
    # Handle async execution
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        print("\nAsync event loop already running. Adding task...")
        task = loop.create_task(main_test_workflow_runner(**test_config))
    else:
        print("\nStarting new async event loop...")
        asyncio.run(main_test_workflow_runner(**test_config))
    
    print("\n" + "-"*60)
    print("Run this script from the project root directory using:")
    print("PYTHONPATH=. python standalone_test_client/kiwi_client/workflows/examples/wf_workflow_runner_eg.py")
    print("-"*60)
