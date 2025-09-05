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
    LITE_BLOG_COMPANY_DOCNAME,
    LITE_BLOG_COMPANY_NAMESPACE_TEMPLATE,
    LITE_BLOG_AI_VISIBILITY_TEST_DOCNAME,
    LITE_BLOG_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
    LITE_BLOG_COMPANY_AI_VISIBILITY_TEST_DOCNAME,
    LITE_BLOG_COMPANY_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
    LITE_BLOG_AI_VISIBILITY_RAW_DATA_DOCNAME,
    LITE_BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE
)

from kiwi_client.workflows.active.content_diagnostics_LITE_version.llm_inputs.company_ai_visibility import (
    COMPETITIVE_ANALYSIS_SYSTEM_PROMPT,
    COMPETITIVE_ANALYSIS_USER_PROMPT_TEMPLATE,
    COMPETITIVE_ANALYSIS_SCHEMA,
    BLOG_COVERAGE_SYSTEM_PROMPT,
    BLOG_COVERAGE_USER_PROMPT_TEMPLATE,
    BLOG_COVERAGE_QUERIES_SCHEMA,
    COMPANY_COMP_SYSTEM_PROMPT,
    COMPANY_COMP_USER_PROMPT_TEMPLATE,
    COMPANY_COMP_QUERIES_SCHEMA,
    BLOG_AI_VISIBILITY_REPORT_SCHEMA,
    BLOG_AI_VISIBILITY_REPORT_USER_PROMPT,
    BLOG_AI_VISIBILITY_REPORT_SYSTEM_PROMPT
)

LLM_PROVIDER_FOR_INITITAL_ANALYSIS = "perplexity"
LLM_MODEL_FOR_INITITAL_ANALYSIS = "sonar-pro"
LLM_TEMPERATURE_FOR_INITITAL_ANALYSIS = 0.8
LLM_MAX_TOKENS_FOR_INITITAL_ANALYSIS = 2000

# LLM defaults
LLM_PROVIDER = "openai"
LLM_MODEL = "gpt-5"
LLM_TEMPERATURE = 0.5
LLM_MAX_TOKENS = 8000

workflow_graph_schema = {
    "nodes": {
        # 1) Input
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "company_name": {"type": "str", "required": True},
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
                                                    "input_namespace_field_pattern": LITE_BLOG_COMPANY_NAMESPACE_TEMPLATE,
                        "input_namespace_field": "company_name",
                        "static_docname": LITE_BLOG_COMPANY_DOCNAME,
                        },
                        "output_field_name": "blog_company_doc",
                    }
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
            },
        },

        # --- Blog Path: 3. Competitive Analysis ---
        "construct_competitive_analysis_prompt": {
            "node_id": "construct_competitive_analysis_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "system_prompt": {"id": "system_prompt", "template": COMPETITIVE_ANALYSIS_SYSTEM_PROMPT, "variables": {}},
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": COMPETITIVE_ANALYSIS_USER_PROMPT_TEMPLATE,
                        "variables": {"blog_company_data": None},
                        "construct_options": {"blog_company_data": "blog_company_doc"},
                    },
                }
            },
        },
        "competitive_analysis_llm": {
            "node_id": "competitive_analysis_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_FOR_INITITAL_ANALYSIS, "model": LLM_MODEL_FOR_INITITAL_ANALYSIS},
                    "temperature": LLM_TEMPERATURE_FOR_INITITAL_ANALYSIS,
                    "max_tokens": LLM_MAX_TOKENS_FOR_INITITAL_ANALYSIS,
                },
                "output_schema": {"schema_definition": COMPETITIVE_ANALYSIS_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },

        # --- 4.1 Blog Coverage Query Generation ---
        "construct_blog_queries_prompt": {
            "node_id": "construct_blog_queries_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "system_prompt": {"id": "system_prompt", "template": BLOG_COVERAGE_SYSTEM_PROMPT, "variables": {}},
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": BLOG_COVERAGE_USER_PROMPT_TEMPLATE,
                        "variables": {"blog_company_data": None, 
                                      "competitive_analysis": None, 
                                      "current_date": "$current_date"
                                      },
                        "construct_options": {
                            "blog_company_data": "blog_company_doc",
                            "competitive_analysis": "competitive_analysis"
                        },
                    },
                }
            },
        },
        "generate_blog_queries": {
            "node_id": "generate_blog_queries",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": 0.3,
                    "max_tokens": 2000,
                    "reasoning_effort_class": "low",
                    "verbosity": "low"
                },
                "output_schema": {"schema_definition": BLOG_COVERAGE_QUERIES_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },

        # --- 4.2 Company & Competitor Query Generation ---
        "construct_company_comp_queries_prompt": {
            "node_id": "construct_company_comp_queries_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "system_prompt": {"id": "system_prompt", "template": COMPANY_COMP_SYSTEM_PROMPT, "variables": {}},
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": COMPANY_COMP_USER_PROMPT_TEMPLATE,
                        "variables": {"blog_company_data": None, "competitive_analysis": None},
                        "construct_options": {
                            "blog_company_data": "blog_company_doc",
                            "competitive_analysis": "competitive_analysis",
                        },
                    },
                }
            },
        },
        "generate_company_comp_queries": {
            "node_id": "generate_company_comp_queries",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": 0.3,
                    "max_tokens": 2000,
                    "reasoning_effort_class": "low",
                    "verbosity": "low"
                },
                "output_schema": {"schema_definition": COMPANY_COMP_QUERIES_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },

        # --- 5. LLM Analysis Phase: Execute queries on answer engines ---
        "blog_coverage_ai_query": {
            "node_id": "blog_coverage_ai_query",
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
        "company_comp_ai_query": {
            "node_id": "company_comp_ai_query",
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
        "store_blog_raw_scraper_results": {
            "node_id": "store_blog_raw_scraper_results",
            "node_name": "store_customer_data",
            "node_config": {
                "store_configs": [
                    {
                        "input_field_path": "query_results",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": LITE_BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": LITE_BLOG_AI_VISIBILITY_RAW_DATA_DOCNAME
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
        "store_company_comp_raw_scraper_results": {
            "node_id": "store_company_comp_raw_scraper_results",
            "node_name": "store_customer_data",
            "node_config": {
                "store_configs": [
                    {
                        "input_field_path": "query_results",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": LITE_BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": LITE_BLOG_AI_VISIBILITY_RAW_DATA_DOCNAME
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

        "construct_ai_visibility_report_prompt": {
            "node_id": "construct_ai_visibility_report_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": BLOG_AI_VISIBILITY_REPORT_USER_PROMPT,
                        "variables": {
                            "company_ai_visibility_data": None,
                            "blog_ai_visibility_data": None,
                            "company_context_doc": None
                        },
                        "construct_options": {
                            "company_context_doc": "company_context_doc",
                            "company_ai_visibility_data": "company_ai_visibility_data",
                            "blog_ai_visibility_data": "blog_ai_visibility_data"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": BLOG_AI_VISIBILITY_REPORT_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },


        "generate_ai_visibility_report": {
            "node_id": "generate_ai_visibility_report",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS,
                    "reasoning_effort_class": "low",
                    "verbosity": "low"
                },
                "output_schema": {"schema_definition": BLOG_AI_VISIBILITY_REPORT_SCHEMA, "convert_loaded_schema_to_pydantic": False}
            }
        },

        "store_ai_visibility_report": {
            "node_id": "store_ai_visibility_report",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {"is_versioned": True, "operation": "upsert_versioned"},
                "store_configs": [
                    {
                        "input_field_path": "structured_output",
                        "target_path": {
                            "filename_config": {
                                                            "input_namespace_field_pattern": LITE_BLOG_COMPANY_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": LITE_BLOG_COMPANY_AI_VISIBILITY_TEST_DOCNAME,
                            }
                        },
                    }
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
            },
        },

        # Final output
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "enable_node_fan_in": True,
            "node_config": {},
        },
    },
    "edges": [
        # --- Initial Setup: Store inputs to graph state ---
        {"src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
            {"src_field": "enable_cache", "dst_field": "enable_cache"},
            {"src_field": "cache_lookback_days", "dst_field": "cache_lookback_days"},
        ]},

        # Input -> Load context
        {"src_node_id": "input_node", "dst_node_id": "load_context_docs", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
        ]},

        # Load context -> State
        {"src_node_id": "load_context_docs", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "blog_company_doc", "dst_field": "blog_company_doc"},
        ]},        

        # Blog path: State -> competitive analysis prompt
        {"src_node_id": "load_context_docs", "dst_node_id": "construct_competitive_analysis_prompt", "mappings": [
            {"src_field": "blog_company_doc", "dst_field": "blog_company_doc"},
        ]},
        {"src_node_id": "construct_competitive_analysis_prompt", "dst_node_id": "competitive_analysis_llm", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"},
        ]},
        # Store competitive analysis in state
        {"src_node_id": "competitive_analysis_llm", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "competitive_analysis"},
        ]},
        
        {"src_node_id": "competitive_analysis_llm", "dst_node_id": "construct_blog_queries_prompt", "mappings": [
            {"src_field": "structured_output", "dst_field": "competitive_analysis"},
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "construct_blog_queries_prompt", "mappings": [
            {"src_field": "blog_company_doc", "dst_field": "blog_company_doc"},
        ]},
        {"src_node_id": "construct_blog_queries_prompt", "dst_node_id": "generate_blog_queries", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"},
        ]},

        # Company & Competitor queries path (after competitive analysis as well)
        {"src_node_id": "competitive_analysis_llm", "dst_node_id": "construct_company_comp_queries_prompt", "mappings": [
            {"src_field": "structured_output", "dst_field": "competitive_analysis"},
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "construct_company_comp_queries_prompt", "mappings": [
            {"src_field": "blog_company_doc", "dst_field": "blog_company_doc"},
        ]},
        {"src_node_id": "construct_company_comp_queries_prompt", "dst_node_id": "generate_company_comp_queries", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"},
        ]},

        # Prepare AI inputs: map generated queries + entity + cache
        {"src_node_id": "generate_blog_queries", "dst_node_id": "blog_coverage_ai_query", "mappings": [
            {"src_field": "structured_output", "dst_field": "query_templates"},
        ]},
        # AI query execution
        {"src_node_id": "$graph_state", "dst_node_id": "blog_coverage_ai_query", "mappings": [
            {"src_field": "enable_cache", "dst_field": "enable_mongodb_cache"},
            {"src_field": "cache_lookback_days", "dst_field": "cache_lookback_days"},
            {"src_field": "company_name", "dst_field": "entity_name"}
        ]},
        {"src_node_id": "generate_company_comp_queries", "dst_node_id": "company_comp_ai_query", "mappings": [
            {"src_field": "structured_output", "dst_field": "query_templates"},
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "company_comp_ai_query", "mappings": [
            {"src_field": "enable_cache", "dst_field": "enable_mongodb_cache"},
            {"src_field": "cache_lookback_days", "dst_field": "cache_lookback_days"},
            {"src_field": "company_name", "dst_field": "entity_name"}
        ]},

        # Store raw scraper results to uploaded_files namespace
        {"src_node_id": "blog_coverage_ai_query", "dst_node_id": "store_blog_raw_scraper_results", "mappings": [
            {"src_field": "query_results", "dst_field": "query_results"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "store_blog_raw_scraper_results", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},
        {"src_node_id": "company_comp_ai_query", "dst_node_id": "store_company_comp_raw_scraper_results", "mappings": [
            {"src_field": "query_results", "dst_field": "query_results"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "store_company_comp_raw_scraper_results", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},

        # Connect AI query results to report generation
        {"src_node_id": "blog_coverage_ai_query", "dst_node_id": "construct_ai_visibility_report_prompt", "mappings": [
            {"src_field": "query_results", "dst_field": "blog_ai_visibility_data"}
        ]},
        {"src_node_id": "company_comp_ai_query", "dst_node_id": "construct_ai_visibility_report_prompt", "mappings": [
            {"src_field": "query_results", "dst_field": "company_ai_visibility_data"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "construct_ai_visibility_report_prompt", "mappings": [
            {"src_field": "blog_company_doc", "dst_field": "company_context_doc"}
        ]},

        # Generate the AI visibility report
        {"src_node_id": "construct_ai_visibility_report_prompt", "dst_node_id": "generate_ai_visibility_report", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"}
        ]},

        # Store the AI visibility report
        {"src_node_id": "generate_ai_visibility_report", "dst_node_id": "store_ai_visibility_report", "mappings": [
            {"src_field": "structured_output", "dst_field": "structured_output"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "store_ai_visibility_report", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},

        # Store report in state and connect to output
        {"src_node_id": "generate_ai_visibility_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "ai_visibility_report"}
        ]},
        {"src_node_id": "store_ai_visibility_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "paths_processed", "dst_field": "stored_ai_report_paths"},
            {"src_field": "passthrough_data", "dst_field": "ai_visibility_report"}
        ]},

        # Connect to output
        {"src_node_id": "store_ai_visibility_report", "dst_node_id": "output_node", "mappings": [
        ]},

        # Connect raw data storage to output (kept for debugging)
        {"src_node_id": "store_blog_raw_scraper_results", "dst_node_id": "output_node", "mappings": [
        ]},

        {"src_node_id": "store_company_comp_raw_scraper_results", "dst_node_id": "output_node", "mappings": [
        ]},

        # Output mapping from state
        {"src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
            {"src_field": "ai_visibility_report", "dst_field": "ai_visibility_report"},
            {"src_field": "stored_ai_report_paths", "dst_field": "stored_ai_report_paths"}
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
                "competitive_analysis": "replace",
                "blog_coverage_queries": "replace",
                "company_comp_queries": "replace",
                "blog_coverage_query_results": "replace",
                "company_comp_query_results": "replace",
                "ai_visibility_report": "replace",
                "stored_ai_report_paths": "replace",
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

    test_company_name = "momentum"
    
    test_inputs = {
        "company_name": test_company_name,
        "enable_cache": True,
        "cache_lookback_days": 14,
    }

    # Define setup documents
    setup_docs = [
        # Blog Company Document
        {
            'namespace': LITE_BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item=test_company_name),
            'docname': LITE_BLOG_COMPANY_DOCNAME,
            'initial_data': {
                "company_name": test_company_name,
                "industry": "AI Revenue Orchestration Platform",
                "primary_products": [
                    "Deal Execution Agent",
                    "Customer Retention Agent",
                    "Coaching Agent",
                    "AI CRO"
                ],
                "target_market": "B2B GTM teams (Sales, CS, RevOps)",
                "competitors": ["Gong", "Clari", "Salesforce Einstein", "People.ai"],
                "unique_value_proposition": "Capture structured data from every customer interaction, update CRM, route insights, and automate GTM workflows",
                "blog_topics": ["AI for Revenue Ops", "Deal Execution", "Churn Prevention", "AI Coaching"],
                "key_differentiators": ["AI Signals + Alerts", "MEDDIC Autopilot", "Executive Briefs", "Slack-first orchestration"],
            },
            'is_versioned': False,
            'is_shared': False
        },
    ]

    # Define cleanup docs
    cleanup_docs = [
        {'namespace': LITE_BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item=test_company_name), 'docname': LITE_BLOG_COMPANY_DOCNAME, 'is_versioned': False, 'is_shared': False},
        # Cleanup generated test documents
        {'namespace': LITE_BLOG_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE.format(item=test_company_name), 'docname': LITE_BLOG_AI_VISIBILITY_TEST_DOCNAME, 'is_versioned': True, 'is_shared': False},
        {'namespace': LITE_BLOG_COMPANY_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE.format(item=test_company_name), 'docname': LITE_BLOG_COMPANY_AI_VISIBILITY_TEST_DOCNAME, 'is_versioned': True, 'is_shared': False},
    ]

    # No HITL inputs for this workflow
    predefined_hitl_inputs = []

    # Output validation function
    async def validate_ai_visibility_output(outputs):
        """Validates the workflow output to ensure it meets expected structure and content requirements."""
        assert outputs is not None, "Validation Failed: Workflow returned no outputs."
        
        # Check for AI visibility report
        if 'ai_visibility_report' in outputs:
            assert outputs['ai_visibility_report'] is not None, "Validation Failed: AI visibility report is None"
            print(f"✓ AI visibility report generated successfully")
        
        if 'stored_ai_report_paths' in outputs:
            assert outputs['stored_ai_report_paths'] is not None, "Validation Failed: Stored AI report paths is None"
            print(f"✓ AI visibility report stored successfully")
        
        # Basic validation that workflow completed
        print(f"✓ AI visibility workflow completed successfully")
        
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
        print(f"Workflow completed successfully with outputs: {list(final_run_outputs.keys())}")
        if 'stored_ai_report_paths' in final_run_outputs:
            print(f"AI Visibility Report Paths: {final_run_outputs.get('stored_ai_report_paths')}")
        if 'ai_visibility_report' in final_run_outputs and final_run_outputs['ai_visibility_report']:
            report = final_run_outputs['ai_visibility_report']
            if isinstance(report, dict) and 'visibility_snapshot' in report:
                print(f"Overall AI Visibility Score: {report['visibility_snapshot'].get('overall_score', 'N/A')}")
                print(f"Industry Position: {report['visibility_snapshot'].get('industry_position', 'N/A')}")

if __name__ == "__main__":
    try:
        asyncio.run(main_test_ai_visibility_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")