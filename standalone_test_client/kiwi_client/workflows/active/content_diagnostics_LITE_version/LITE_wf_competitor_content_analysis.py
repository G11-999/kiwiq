"""
Competitor Content Analysis Workflow

This workflow:
1. Loads company document with competitor information
2. Uses map_list_router_node to distribute competitors for parallel analysis
3. Analyzes each competitor's content strategy using Perplexity LLM
4. Saves analysis results to shared documents with proper naming conventions

Document Storage Convention:
- Document Name: blog_competitor_content_analysis_{competitor_name}
- Namespace: blog_competitive_intelligence_{company_name}
"""

from typing import Dict, Any, List, Optional
import asyncio
import logging
import json
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import workflow testing utilities
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

# Import document model constants
from kiwi_client.workflows.active.document_models.customer_docs import (
    LITE_BLOG_COMPANY_DOCNAME,
    LITE_BLOG_COMPANY_NAMESPACE_TEMPLATE,
    LITE_BLOG_COMPETITOR_CONTENT_ANALYSIS_DOCNAME,
    LITE_BLOG_COMPETITOR_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
    LITE_BLOG_COMPANY_IS_VERSIONED,
)

# Import LLM inputs
from kiwi_client.workflows.active.content_diagnostics_LITE_version.llm_inputs.competitor_content_analysis import (
    COMPETITOR_CONTENT_ANALYSIS_SYSTEM_PROMPT,
    COMPETITOR_CONTENT_ANALYSIS_USER_PROMPT_TEMPLATE,
    COMPETITOR_CONTENT_ANALYSIS_OUTPUT_SCHEMA,
)

# LLM Configuration
PERPLEXITY_PROVIDER = "perplexity"
PERPLEXITY_MODEL = "sonar-pro"
PERPLEXITY_TEMPERATURE = 0.5
PERPLEXITY_MAX_TOKENS = 4000

# Workflow JSON structure
workflow_graph_schema = {
    "nodes": {
        # 1. Input Node
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "company_name": {
                        "type": "str",
                        "required": True,
                        "description": "Name of the company for document operations"
                    }
                }
            }
        },
        
        # 2. Load Company Document
        "load_company_doc": {
            "node_id": "load_company_doc",
            "node_name": "load_customer_data",
            "node_config": {
                # Use dynamic configuration from input
                "load_paths": [
                    {
                        "filename_config": {
                                                    "input_namespace_field_pattern": LITE_BLOG_COMPANY_NAMESPACE_TEMPLATE,
                        "input_namespace_field": "company_name",
                        "static_docname": LITE_BLOG_COMPANY_DOCNAME,
                        },
                    "output_field_name": "company_doc"
                    }
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False}
            }
        },
        
                 # 3. Distribute Competitors for Parallel Processing
         "distribute_competitors": {
             "node_id": "distribute_competitors",
             "node_name": "map_list_router_node",
             "node_config": {
                 "choices": ["construct_analysis_prompt"],
                 "map_targets": [
                     {
                         "source_path": "company_doc.competitors",
                         "destinations": ["construct_analysis_prompt"],
                         "batch_size": 1,
                         "batch_field_name": "competitor_item"
                     }
                 ]
             }
         },
         
         # 4. Construct Analysis Prompt
         "construct_analysis_prompt": {
             "node_id": "construct_analysis_prompt",
             "node_name": "prompt_constructor",
             "private_input_mode": True,
             "output_private_output_to_central_state": True,
             "private_output_mode": True,
             "node_config": {
                 "prompt_templates": {
                     "competitor_analysis_user_prompt": {
                         "id": "competitor_analysis_user_prompt",
                         "template": COMPETITOR_CONTENT_ANALYSIS_USER_PROMPT_TEMPLATE,
                         "variables": {
                             "competitor_name": None,
                             "competitor_website": None
                         },
                         "construct_options": {
                             "competitor_name": "competitor_item.name",
                             "competitor_website": "competitor_item.website_url"
                         }
                     },
                     "competitor_analysis_system_prompt": {
                         "id": "competitor_analysis_system_prompt",
                         "template": COMPETITOR_CONTENT_ANALYSIS_SYSTEM_PROMPT,
                         "variables": {}
                     }
                 }
             }
         },
         # 5. Analyze Competitor Content Using Perplexity
         "analyze_competitor_content": {
             "node_id": "analyze_competitor_content",
             "node_name": "llm",
             "private_input_mode": True,
             "output_private_output_to_central_state": True,
             "node_config": {
                 "llm_config": {
                     "model_spec": {
                         "provider": PERPLEXITY_PROVIDER,
                         "model": PERPLEXITY_MODEL
                     },
                     "temperature": PERPLEXITY_TEMPERATURE,
                     "max_tokens": PERPLEXITY_MAX_TOKENS
                 },
                 "output_schema": {
                     "schema_definition": COMPETITOR_CONTENT_ANALYSIS_OUTPUT_SCHEMA,
                     "convert_loaded_schema_to_pydantic": False
                 }
             }
         },
        
        # 7. Route Structured Data for Saving
        "route_for_saving": {
            "node_id": "route_for_saving",
            "enable_node_fan_in": True,
            "node_name": "map_list_router_node",
            "node_config": {
                "choices": ["save_competitor_analysis"],
                "map_targets": [
                    {
                        "source_path": "all_competitor_analysis_results",
                        "destinations": ["save_competitor_analysis"],
                        "batch_size": 1,
                        "batch_field_name": "competitor_data"
                    }
                ]
            }
        },
        
        # 8. Save Competitor Analysis to Shared Documents
        "save_competitor_analysis": {
            "node_id": "save_competitor_analysis",
            "node_name": "store_customer_data",
            "node_config": {
                "global_is_shared": False,
                "global_is_system_entity": False,
                "store_configs": [
                    {
                        "input_field_path": "competitor_data",
                        "target_path": {
                            "filename_config": {
                                                            "input_namespace_field_pattern": LITE_BLOG_COMPETITOR_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "input_docname_field_pattern": LITE_BLOG_COMPETITOR_CONTENT_ANALYSIS_DOCNAME,
                                "input_docname_field": "competitor_data.name"
                            }
                        },
                        "versioning": {
                            "is_versioned": False,
                            "operation": "upsert"
                        },
                        "generate_uuid": True
                    }
                ]
            },
            "private_input_mode": True,
            "output_private_output_to_central_state": True
        },
        
                 # 6. Output Node
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "enable_node_fan_in": True,
            "node_config": {}
        }
    },
    
    "edges": [
        # Input -> State: Store initial values
        {
            "src_node_id": "input_node",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
            ]
        },
        
        # Input -> Load Company Doc
        {
            "src_node_id": "input_node",
            "dst_node_id": "load_company_doc",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"}
            ]
        },
        
        # Company Doc -> State: Store company context
        {
            "src_node_id": "load_company_doc",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"}
            ]
        },
        
        # Company Doc -> Distribute Competitors
        {
            "src_node_id": "load_company_doc",
            "dst_node_id": "distribute_competitors",
            "mappings": [
                
            ]
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "distribute_competitors",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"}
            ]
        },
                # Distribute Competitors -> Construct Analysis Prompt
        {
            "src_node_id": "distribute_competitors",
            "dst_node_id": "construct_analysis_prompt",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_analysis_prompt",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"}
            ]
        },
        
        # Construct Analysis Prompt -> Analyze Competitor Content
        {
            "src_node_id": "construct_analysis_prompt",
            "dst_node_id": "analyze_competitor_content",
            "mappings": [
                {"src_field": "competitor_analysis_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "competitor_analysis_system_prompt", "dst_field": "system_prompt"}
            ]
        },

        # Analyze Competitor Content -> Merge analysis with competitor metadata
        {
            "src_node_id": "analyze_competitor_content",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "all_competitor_analysis_results"}
            ]
        },

        # Merge analysis with metadata -> Route for Saving
        {
            "src_node_id": "analyze_competitor_content",
            "dst_node_id": "route_for_saving",
            "mappings": [
            ]
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "route_for_saving",
            "mappings": [
                {"src_field": "all_competitor_analysis_results", "dst_field": "all_competitor_analysis_results"}
            ]
        },
        # Route for Saving -> Save Analysis
        {
            "src_node_id": "route_for_saving",
            "dst_node_id": "save_competitor_analysis",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_competitor_analysis",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"}
            ]
        },
        
        # Save Analysis -> Output
        {
            "src_node_id": "save_competitor_analysis",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "passthrough_data", "dst_field": "competitor_analysis_passthrough_data"}
            ]
        },

        {
            "src_node_id": "save_competitor_analysis",
            "dst_node_id": "output_node",
            "mappings": []
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "competitor_analysis_passthrough_data", "dst_field": "competitor_analysis_passthrough_data"}
            ]
        }
    ],
    
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    "metadata": {
        "$graph_state": {
            "reducer": {
                "company_doc": "replace",
                "all_competitor_analysis_results": "collect_values",
                "competitor_analysis_passthrough_data": "collect_values"
            }
        }
    }
}

async def validate_competitor_analysis_workflow_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Validate the competitor content analysis workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run.
        
    Returns:
        True if the outputs are valid, False otherwise.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating competitor content analysis workflow outputs...")
    
    # Check for analysis document ID
    if 'analysis_document_id' in outputs and outputs['analysis_document_id'] is not None:
        analysis_id = outputs['analysis_document_id']
        if isinstance(analysis_id, str) and len(analysis_id) > 0:
            logger.info(f"✓ Analysis saved with document ID: {analysis_id}")
        else:
            logger.info("⚠ Analysis document ID present but invalid format")
    
    logger.info("✓ Competitor content analysis workflow output validation passed.")
    return True


async def main_test_competitor_analysis_workflow():
    """
    Test for Competitor Content Analysis Workflow.
    
    This function sets up test data, executes the workflow, and validates the output.
    The workflow loads company data, distributes competitors for parallel analysis,
    and saves comprehensive competitive intelligence reports.
    """
    test_name = "Competitor Content Analysis Workflow Test"
    print(f"--- Starting {test_name} ---")
    
    # Test parameters
    test_company_name = "momentum"
    
    # Create test company document data
    company_data = {
        "company_name": "Writer",
        "website_url": "https://writer.com",
        "positioning_headline": "Writer is an AI writing platform built for teams, helping enterprises ensure consistent, on-brand, and high-quality content across all departments.",
        "icp": {
            "icp_name": "Enterprise Marketing and Operations Teams",
            "target_industry": "Technology, Financial Services, Healthcare, and Professional Services",
            "company_size": "Mid-market to Enterprise (500+ employees)",
            "buyer_persona": "CMO, Head of Content, VP of Marketing, Operations Lead",
            "pain_points": [
                "Inconsistent brand voice across departments",
                "Low content velocity",
                "Difficulty scaling content creation while maintaining quality",
                "Inefficiencies in cross-functional communication and documentation"
            ],
            "goals": [
                "Standardize brand voice across all content",
                "Improve writing quality at scale",
                "Enable all team members to write clearly and efficiently",
                "Speed up content production processes"
            ]
        },
        "content_distribution_mix": {
            "awareness_percent": 40.0,
            "consideration_percent": 30.0,
            "purchase_percent": 20.0,
            "retention_percent": 10.0
        },
        "competitors": [
            {
                "website_url": "https://grammarly.com",
                "name": "Grammarly Business"
            },
            {
                "website_url": "https://jasper.ai",
                "name": "Jasper"
            },
            {
                "website_url": "https://copy.ai",
                "name": "Copy.ai"
            }
        ]
    }
    
    # Test inputs
    test_inputs = {
        "company_name": test_company_name
    }
    
    # Setup test documents
    setup_docs: List[SetupDocInfo] = [
        {
            'namespace': f"blog_company_profile_{test_company_name}",
            'docname': LITE_BLOG_COMPANY_DOCNAME,
            'initial_data': company_data,
            'is_shared': False,
            'is_versioned': LITE_BLOG_COMPANY_IS_VERSIONED,
            'initial_version': "default",
            'is_system_entity': False
        }
    ]
    
    # Cleanup configuration
    cleanup_docs: List[CleanupDocInfo] = [
        {
            'namespace': f"blog_company_profile_{test_company_name}",
            'docname': LITE_BLOG_COMPANY_DOCNAME,
            'is_shared': False,
            'is_versioned': LITE_BLOG_COMPANY_IS_VERSIONED,
            'is_system_entity': False
        }
    ]
    
    # No HITL inputs needed for this workflow
    predefined_hitl_inputs = []
    
    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=predefined_hitl_inputs,
        # setup_docs=setup_docs,
        # cleanup_docs=cleanup_docs,
        cleanup_docs_created_by_setup=False,
        validate_output_func=validate_competitor_analysis_workflow_output,
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=1200  # 20 minutes for analysis
    )
    
    print(f"--- {test_name} Finished ---")
    if final_run_outputs:
        print(f"Analysis completed and saved: {final_run_outputs.get('analysis_document_id', 'N/A')}")


# Entry point
if __name__ == "__main__":
    print("="*80)
    print("Competitor Content Analysis Workflow Test")
    print("="*80)
    
    try:
        asyncio.run(main_test_competitor_analysis_workflow())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.exception("Test execution failed")
    
    print("\nTest execution finished.")
    print("Run from project root: PYTHONPATH=. python kiwi_client/workflows_for_blog_teammate/wf_competitor_content_analysis.py") 