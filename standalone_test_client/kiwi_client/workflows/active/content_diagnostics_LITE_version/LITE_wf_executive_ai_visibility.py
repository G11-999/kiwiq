import asyncio
import logging
from typing import Dict, Any, Optional, List, Union, ClassVar, Type
import json
from enum import Enum

# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field

# Added imports for running locally
import asyncio
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)

from kiwi_client.workflows.active.document_models.customer_docs import (
    LITE_LINKEDIN_USER_PROFILE_DOCNAME,
    LITE_LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
    LITE_LINKEDIN_SCRAPED_PROFILE_DOCNAME,
    LITE_LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE,
    LITE_LINKEDIN_USER_AI_VISIBILITY_TEST_DOCNAME,
    LITE_LINKEDIN_USER_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
    LITE_LINKEDIN_USER_AI_VISIBILITY_RAW_DATA_DOCNAME,
    LITE_LINKEDIN_UPLOADED_FILES_NAMESPACE_TEMPLATE,
)

from kiwi_client.workflows.active.content_diagnostics_LITE_version.llm_inputs.executive_ai_visibility import (

    EXEC_VISIBILITY_SYSTEM_PROMPT,
    EXEC_VISIBILITY_USER_PROMPT_TEMPLATE,
    EXEC_VISIBILITY_QUERIES_SCHEMA,
    EXEC_VISIBILITY_REPORT_SYSTEM_PROMPT,
    EXEC_VISIBILITY_REPORT_USER_PROMPT_TEMPLATE,
    EXEC_VISIBILITY_REPORT_SCHEMA,
)

# LLM defaults
LLM_PROVIDER = "openai"
LLM_MODEL = "gpt-5"
LLM_TEMPERATURE = 0.5
LLM_MAX_TOKENS = 5000

workflow_graph_schema = {
    "nodes": {
        # 1) Input
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "entity_username": {"type": "str", "required": True},
                    "enable_cache": {"type": "bool", "required": False},
                    "cache_lookback_days": {"type": "int", "required": False},
                }
            },
        },

        # 2) Load required context docs
        "load_context_docs": {
            "node_id": "load_context_docs",
            "node_name": "load_customer_data",
            "node_config": {
                "load_paths": [
                    {
                        "filename_config": {
                                    "input_namespace_field_pattern": LITE_LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
        "input_namespace_field": "entity_username",
        "static_docname": LITE_LINKEDIN_USER_PROFILE_DOCNAME,
                        },
                        "output_field_name": "linkedin_user_profile_doc",
                    },
                    {
                        "filename_config": {
                                    "input_namespace_field_pattern": LITE_LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE,
        "input_namespace_field": "entity_username",
        "static_docname": LITE_LINKEDIN_SCRAPED_PROFILE_DOCNAME,
                        },
                        "output_field_name": "linkedin_scraped_profile_doc",
                    },
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
            },
        },

        # --- 4.3 Executive Query Generation ---
        "construct_exec_queries_prompt": {
            "node_id": "construct_exec_queries_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "system_prompt": {"id": "system_prompt", "template": EXEC_VISIBILITY_SYSTEM_PROMPT, "variables": {}},
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": EXEC_VISIBILITY_USER_PROMPT_TEMPLATE,
                        "variables": {"linkedin_user_profile": None, 
                                      "linkedin_scraped_profile": None,
                                      "current_date": "$current_date"
                                      },
                        "construct_options": {
                            "linkedin_user_profile": "linkedin_user_profile_doc",
                            "linkedin_scraped_profile": "linkedin_scraped_profile_doc"
                        },
                    },
                }
            },
        },
        "generate_exec_queries": {
            "node_id": "generate_exec_queries",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": 0.3,
                    "max_tokens": 2000,
                    "reasoning_effort_class": "low",
                    "verbosity": "low"
                },
                "output_schema": {"schema_definition": EXEC_VISIBILITY_QUERIES_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },

        "exec_ai_query": {
            "node_id": "exec_ai_query",
            "node_name": "ai_answer_engine_scraper",
            "node_config": {
                "return_nested_entity_results": True,
                "entity_name_path": "entity_name",
                "default_providers_config": {
                    "google": {"enabled": False, "max_retries": 2, "retry_delay": 2.0},
                    "openai": {"enabled": True, "max_retries": 3, "retry_delay": 2.0},
                    "perplexity": {"enabled": True, "max_retries": 2, "retry_delay": 2.0}
                }
            }
        },

        # Store raw scraper results to uploaded_files namespace
        "store_exec_raw_scraper_results": {
            "node_id": "store_exec_raw_scraper_results",
            "node_name": "store_customer_data",
            "node_config": {
                "store_configs": [
                    {
                        "input_field_path": "query_results",
                        "target_path": {
                            "filename_config": {
                                        "input_namespace_field_pattern": LITE_LINKEDIN_UPLOADED_FILES_NAMESPACE_TEMPLATE,
        "input_namespace_field": "entity_username",
        "static_docname": LITE_LINKEDIN_USER_AI_VISIBILITY_RAW_DATA_DOCNAME
                            }
                        },
                        "generate_uuid": True
                    }
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_versioning": {"is_versioned": False, "operation": "upsert"}
            }
        },

        # 6.3 Executive Visibility Report
        "construct_exec_report_prompt": {
            "node_id": "construct_exec_report_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "system_prompt": {"id": "system_prompt", "template": EXEC_VISIBILITY_REPORT_SYSTEM_PROMPT, "variables": {}},
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": EXEC_VISIBILITY_REPORT_USER_PROMPT_TEMPLATE,
                        "variables": {"loaded_query_results": None},
                        "construct_options": {"loaded_query_results": "loaded_query_results"},
                    },
                }
            },
        },
        "generate_exec_report": {
            "node_id": "generate_exec_report",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": 0.5,
                    "max_tokens": 5000,
                    "reasoning_effort_class": "low",
                    "verbosity": "low"
                },
                "output_schema": {"schema_definition": EXEC_VISIBILITY_REPORT_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },
        "store_exec_report": {
            "node_id": "store_exec_report",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {"is_versioned": True, "operation": "upsert_versioned"},
                "store_configs": [
                    {
                        "input_field_path": "structured_output",
                        "target_path": {
                            "filename_config": {
                                        "input_namespace_field_pattern": LITE_LINKEDIN_USER_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
        "input_namespace_field": "entity_username",
        "static_docname": LITE_LINKEDIN_USER_AI_VISIBILITY_TEST_DOCNAME,
                            }
                        },
                    }
                ],
            },
        },

        # Final output
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {},
            "enable_node_fan_in": True,
        },
    },
    "edges": [
        # --- Initial Setup: Store inputs to graph state ---
        {"src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "entity_username", "dst_field": "entity_username"},
            {"src_field": "enable_cache", "dst_field": "enable_cache"},
            {"src_field": "cache_lookback_days", "dst_field": "cache_lookback_days"},
        ]},

        # Input -> Load context
        {"src_node_id": "input_node", "dst_node_id": "load_context_docs", "mappings": [
            {"src_field": "entity_username", "dst_field": "entity_username"},
        ]},

        # Load context -> State
        {"src_node_id": "load_context_docs", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "linkedin_user_profile_doc", "dst_field": "linkedin_user_profile_doc"},
            {"src_field": "linkedin_scraped_profile_doc", "dst_field": "linkedin_scraped_profile_doc"},
        ]},

        # Exec path: State -> exec queries prompt
        {"src_node_id": "load_context_docs", "dst_node_id": "construct_exec_queries_prompt", "mappings": [
            {"src_field": "linkedin_user_profile_doc", "dst_field": "linkedin_user_profile_doc"},
            {"src_field": "linkedin_scraped_profile_doc", "dst_field": "linkedin_scraped_profile_doc"},
        ]},
        {"src_node_id": "construct_exec_queries_prompt", "dst_node_id": "generate_exec_queries", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"},
        ]},

       
        {"src_node_id": "generate_exec_queries", "dst_node_id": "exec_ai_query", "mappings": [
            {"src_field": "structured_output", "dst_field": "query_templates"},
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "exec_ai_query", "mappings": [
            {"src_field": "enable_cache", "dst_field": "enable_mongodb_cache"},
            {"src_field": "cache_lookback_days", "dst_field": "cache_lookback_days"},
            {"src_field": "entity_username", "dst_field": "entity_name"}
        ]},

        # Store raw scraper results to uploaded_files namespace
        {"src_node_id": "exec_ai_query", "dst_node_id": "store_exec_raw_scraper_results", "mappings": [
            {"src_field": "query_results", "dst_field": "query_results"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "store_exec_raw_scraper_results", "mappings": [
            {"src_field": "entity_username", "dst_field": "entity_username"}
        ]},

        # Construct report prompts
        {"src_node_id": "exec_ai_query", "dst_node_id": "construct_exec_report_prompt", "mappings": [
            {"src_field": "query_results", "dst_field": "loaded_query_results"}
        ]},

        {"src_node_id": "construct_exec_report_prompt", "dst_node_id": "generate_exec_report", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"},
        ]},

        # Store generated reports in state
        {"src_node_id": "generate_exec_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "exec_report"},
        ]},

        # Store reports
        {"src_node_id": "generate_exec_report", "dst_node_id": "store_exec_report", "mappings": [
            {"src_field": "structured_output", "dst_field": "structured_output"},
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "store_exec_report", "mappings": [
            {"src_field": "entity_username", "dst_field": "entity_username"},
        ]},

        # Store paths in state
        {"src_node_id": "store_exec_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "paths_processed", "dst_field": "stored_exec_report_paths"},
        ]},

        # Direct output connections from storage nodes
        {"src_node_id": "store_exec_report", "dst_node_id": "output_node", "mappings": [
            {"src_field": "passthrough_data", "dst_field": "passthrough_data"}
        ]},
    ],
    # --- Define Start and End ---
    "input_node_id": "input_node",
    "output_node_id": "output_node",

    # --- State Reducers ---
    "metadata": {
        "$graph_state": {
            "reducer": {
                # Define how to merge values for specific fields
                "exec_queries": "replace",
                "exec_query_results": "replace",
                "exec_loaded_query_results": "replace",
                "exec_report": "replace",
                "stored_exec_report_paths": "replace",
            }
        }
    }
}


# --- Test Execution Logic ---
async def main_test_ai_visibility_workflow():
    """
    Test for AI Visibility Full Workflow.
    
    This function sets up test data, executes the workflow, and validates the output.
    The workflow performs AI visibility analysis including competitive analysis,
    blog coverage, company comparisons, and executive visibility assessments.
    """
    test_name = "AI Visibility Full Workflow Test"
    print(f"--- Starting {test_name} ---")

    test_entity_username = "jmkmba"
    
    test_inputs = {
        "entity_username": test_entity_username,
        "enable_cache": True,
        "cache_lookback_days": 14,
    }

    # Define setup documents
    setup_docs = [
        # LinkedIn User Profile Document
        {
            'namespace': LITE_LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username),
            'docname': LITE_LINKEDIN_USER_PROFILE_DOCNAME,
            'initial_data': {
                "username": test_entity_username,
                "full_name": "Jayaram M",
                "headline": "AI Sales & GTM Leader | Revenue Orchestration | RevOps Strategy",
                "summary": "Go-to-market and revenue operations leader focused on AI-driven workflows, data quality, and pipeline execution.",
                "experience": [
                    {"title": "Head of GTM", "company": "Momentum", "duration": "2+ years"},
                    {"title": "Revenue Operations Leader", "company": "Prior Companies", "duration": "5+ years"}
                ],
                "skills": ["Revenue Operations", "Sales Strategy", "AI in GTM", "Salesforce"],
            },
            'is_versioned': False,
            'is_shared': False
        },
        # LinkedIn Scraped Profile Document
        {
            'namespace': LITE_LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username),
            'docname': LITE_LINKEDIN_SCRAPED_PROFILE_DOCNAME,
            'initial_data': {
                "recent_posts": [
                    {
                        "content": "How to operationalize AI in your revenue workflows without breaking your CRM.",
                        "date": "2025-07-20",
                        "engagement": {"likes": 120, "comments": 15, "shares": 10}
                    },
                    {
                        "content": "3 steps to turn conversations into structured data that actually updates Salesforce.",
                        "date": "2025-07-10",
                        "engagement": {"likes": 95, "comments": 12, "shares": 8}
                    }
                ],
                "follower_count": 15000,
                "connection_count": 500,
                "engagement_rate": 0.045
            },
            'is_versioned': False,
            'is_shared': False
        },
    ]

    # Define cleanup docs
    cleanup_docs = [
        {'namespace': LITE_LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username), 'docname': LITE_LINKEDIN_USER_PROFILE_DOCNAME, 'is_versioned': False, 'is_shared': False},
        {'namespace': LITE_LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username), 'docname': LITE_LINKEDIN_SCRAPED_PROFILE_DOCNAME, 'is_versioned': False, 'is_shared': False},
        # Cleanup generated test documents
        {'namespace': LITE_LINKEDIN_USER_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE.format(item=test_entity_username), 'docname': LITE_LINKEDIN_USER_AI_VISIBILITY_TEST_DOCNAME, 'is_versioned': True, 'is_shared': False},
    ]

    # No HITL inputs for this workflow
    predefined_hitl_inputs = []

    # Output validation function
    async def validate_ai_visibility_output(outputs):
        """Validates the workflow output to ensure it meets expected structure and content requirements."""
        assert outputs is not None, "Validation Failed: Workflow returned no outputs."
        
        # Check for job IDs from AI queries
        
        
        if outputs.get('run_linkedin_exec'):
            assert 'exec_ai_job_id' in outputs, "Validation Failed: 'exec_ai_job_id' missing when LinkedIn exec analysis was run."
            assert 'stored_exec_report_paths' in outputs, "Validation Failed: 'stored_exec_report_paths' missing."
            print(f"✓ Executive visibility outputs validated successfully")
        
        return True

    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=predefined_hitl_inputs,
        setup_docs=setup_docs,
        cleanup_docs=cleanup_docs,
        cleanup_docs_created_by_setup=False,
        validate_output_func=validate_ai_visibility_output,
        stream_intermediate_results=True,
        poll_interval_sec=5,
        timeout_sec=900
    )

    print(f"--- {test_name} Finished ---")
    if final_run_outputs:
        if 'exec_ai_job_id' in final_run_outputs:
            print(f"Executive Visibility AI Job ID: {final_run_outputs.get('exec_ai_job_id')}")
        if 'stored_exec_report_paths' in final_run_outputs:
            print(f"Stored Exec Report Paths: {final_run_outputs.get('stored_exec_report_paths')}")

if __name__ == "__main__":
    try:
        asyncio.run(main_test_ai_visibility_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")