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
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    BLOG_AI_VISIBILITY_TEST_DOCNAME,
    BLOG_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
    BLOG_COMPANY_AI_VISIBILITY_TEST_DOCNAME,
    BLOG_COMPANY_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
)
from kiwi_client.workflows.active.document_models.customer_docs import (
    LINKEDIN_USER_PROFILE_DOCNAME,
    LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
    LINKEDIN_SCRAPED_PROFILE_DOCNAME,
    LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE,
    LINKEDIN_USER_AI_VISIBILITY_TEST_DOCNAME,
    LINKEDIN_USER_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
)
from kiwi_client.workflows.active.content_diagnostics.llm_inputs.ai_visibility import (
    COMPETITIVE_ANALYSIS_SYSTEM_PROMPT,
    COMPETITIVE_ANALYSIS_USER_PROMPT_TEMPLATE,
    COMPETITIVE_ANALYSIS_SCHEMA,
    BLOG_COVERAGE_SYSTEM_PROMPT,
    BLOG_COVERAGE_USER_PROMPT_TEMPLATE,
    BLOG_COVERAGE_QUERIES_SCHEMA,
    COMPANY_COMP_SYSTEM_PROMPT,
    COMPANY_COMP_USER_PROMPT_TEMPLATE,
    COMPANY_COMP_QUERIES_SCHEMA,
    EXEC_VISIBILITY_SYSTEM_PROMPT,
    EXEC_VISIBILITY_USER_PROMPT_TEMPLATE,
    EXEC_VISIBILITY_QUERIES_SCHEMA,
    BLOG_COVERAGE_REPORT_SYSTEM_PROMPT,
    BLOG_COVERAGE_REPORT_USER_PROMPT_TEMPLATE,
    BLOG_COVERAGE_REPORT_SCHEMA,
    COMPANY_COMP_REPORT_SYSTEM_PROMPT,
    COMPANY_COMP_REPORT_USER_PROMPT_TEMPLATE,
    COMPANY_COMP_REPORT_SCHEMA,
    EXEC_VISIBILITY_REPORT_SYSTEM_PROMPT,
    EXEC_VISIBILITY_REPORT_USER_PROMPT_TEMPLATE,
    EXEC_VISIBILITY_REPORT_SCHEMA,
)

LLM_PROVIDER_FOR_INITITAL_ANALYSIS = "perplexity"
LLM_MODEL_FOR_INITITAL_ANALYSIS = "sonar-pro"
LLM_TEMPERATURE_FOR_INITITAL_ANALYSIS = 0.8
LLM_MAX_TOKENS_FOR_INITITAL_ANALYSIS = 2000

# LLM defaults
LLM_PROVIDER = "anthropic"
LLM_MODEL = "claude-sonnet-4-20250514"
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 3000

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
                    "entity_username": {"type": "str", "required": True},
                    "run_linkedin_exec": {"type": "bool", "required": True},
                    "run_blog_analysis": {"type": "bool", "required": True},
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
                            "input_namespace_field_pattern": BLOG_COMPANY_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_COMPANY_DOCNAME,
                        },
                        "output_field_name": "blog_company_doc",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_USER_PROFILE_DOCNAME,
                        },
                        "output_field_name": "linkedin_user_profile_doc",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_SCRAPED_PROFILE_DOCNAME,
                        },
                        "output_field_name": "linkedin_scraped_profile_doc",
                    },
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
            },
        },

        # 3) Route analysis branches (blog path executes both competitive + queries; exec path handles executive)
        "route_analysis": {
            "node_id": "route_analysis",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "construct_competitive_analysis_prompt",
                    "construct_exec_queries_prompt",
                    "output_node",
                ],
                "allow_multiple": True,
                "default_choice": "output_node",
                "choices_with_conditions": [
                    {"choice_id": "construct_competitive_analysis_prompt", "input_path": "run_blog_analysis", "target_value": True},
                    {"choice_id": "construct_exec_queries_prompt", "input_path": "run_linkedin_exec", "target_value": True},
                ],
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
                        "variables": {"blog_company_data": None, "competitive_analysis": None},
                        "construct_options": {
                            "blog_company_data": "blog_company_doc",
                            "competitive_analysis": "competitive_analysis",
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
                },
                "output_schema": {"schema_definition": COMPANY_COMP_QUERIES_SCHEMA, "convert_loaded_schema_to_pydantic": False},
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
                        "variables": {"linkedin_user_profile": None, "linkedin_scraped_profile": None},
                        "construct_options": {
                            "linkedin_user_profile": "linkedin_user_profile_doc",
                            "linkedin_scraped_profile": "linkedin_scraped_profile_doc",
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
                    "max_tokens": 1500,
                },
                "output_schema": {"schema_definition": EXEC_VISIBILITY_QUERIES_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },

        # --- 5. LLM Analysis Phase: Execute queries on answer engines ---
        "blog_coverage_ai_query": {
            "node_id": "blog_coverage_ai_query",
            "node_name": "ai_answer_engine_scraper",
            "node_config": {
                "return_nested_entity_results": True,
                "entity_name_path": "entity_name"
            }
        },
        "company_comp_ai_query": {
            "node_id": "company_comp_ai_query",
            "node_name": "ai_answer_engine_scraper",
            "node_config": {
                "return_nested_entity_results": True,
                "entity_name_path": "entity_name"
            }
        },
        "exec_ai_query": {
            "node_id": "exec_ai_query",
            "node_name": "ai_answer_engine_scraper",
            "node_config": {
                "return_nested_entity_results": True,
                "entity_name_path": "entity_name"
            }
        },

        # # --- Collect minimal results for report prompts ---
        # "collect_blog_coverage_results": {
        #     "node_id": "collect_blog_coverage_results",
        #     "node_name": "transform_data",
        #     "node_config": {"mappings": [
        #         {"source_path": "query_results", "destination_path": "loaded_query_results"}
        #     ]},
        # },
        # "collect_company_comp_results": {
        #     "node_id": "collect_company_comp_results",
        #     "node_name": "transform_data",
        #     "node_config": {"mappings": [
        #         {"source_path": "query_results", "destination_path": "loaded_query_results"}
        #     ]},
        # },
        # "collect_exec_results": {
        #     "node_id": "collect_exec_results",
        #     "node_name": "transform_data",
        #     "node_config": {"mappings": [
        #         {"source_path": "query_results", "destination_path": "loaded_query_results"}
        #     ]},
        # },

        # --- 6. Report Generation ---
        # 6.1 Blog Coverage Report
        "construct_blog_coverage_report_prompt": {
            "node_id": "construct_blog_coverage_report_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "system_prompt": {"id": "system_prompt", "template": BLOG_COVERAGE_REPORT_SYSTEM_PROMPT, "variables": {}},
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": BLOG_COVERAGE_REPORT_USER_PROMPT_TEMPLATE,
                        "variables": {"loaded_query_results": None},
                        "construct_options": {"loaded_query_results": "loaded_query_results"},
                    },
                }
            },
        },
        "generate_blog_coverage_report": {
            "node_id": "generate_blog_coverage_report",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": 0.4,
                    "max_tokens": 3000,
                },
                "output_schema": {"schema_definition": BLOG_COVERAGE_REPORT_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },
        "store_blog_coverage_report": {
            "node_id": "store_blog_coverage_report",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {"is_versioned": True, "operation": "upsert_versioned"},
                "store_configs": [
                    {
                        "input_field_path": "structured_output",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": BLOG_AI_VISIBILITY_TEST_DOCNAME,
                            }
                        },
                    }
                ],
            },
        },

        # 6.2 Company & Competitor Report
        "construct_company_comp_report_prompt": {
            "node_id": "construct_company_comp_report_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "system_prompt": {"id": "system_prompt", "template": COMPANY_COMP_REPORT_SYSTEM_PROMPT, "variables": {}},
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": COMPANY_COMP_REPORT_USER_PROMPT_TEMPLATE,
                        "variables": {"loaded_query_results": None},
                        "construct_options": {"loaded_query_results": "loaded_query_results"},
                    },
                }
            },
        },
        "generate_company_comp_report": {
            "node_id": "generate_company_comp_report",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": 0.4,
                    "max_tokens": 3500,
                },
                "output_schema": {"schema_definition": COMPANY_COMP_REPORT_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },
        "store_company_comp_report": {
            "node_id": "store_company_comp_report",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {"is_versioned": True, "operation": "upsert_versioned"},
                "store_configs": [
                    {
                        "input_field_path": "structured_output",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_COMPANY_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": BLOG_COMPANY_AI_VISIBILITY_TEST_DOCNAME,
                            }
                        },
                    }
                ],
            },
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
                    "temperature": 0.4,
                    "max_tokens": 3500,
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
                                "input_namespace_field_pattern": LINKEDIN_USER_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "entity_username",
                                "static_docname": LINKEDIN_USER_AI_VISIBILITY_TEST_DOCNAME,
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
            "dynamic_input_schema": {
                "fields": {
                    "blog_ai_job_id": {"type": "str", "required": False},
                    "company_comp_ai_job_id": {"type": "str", "required": False},
                    "exec_ai_job_id": {"type": "str", "required": False},
                    "stored_blog_report_paths": {"type": "any", "required": False},
                    "stored_company_report_paths": {"type": "any", "required": False},
                    "stored_exec_report_paths": {"type": "any", "required": False},
                }
            },
        },
    },
    "edges": [
        # --- Initial Setup: Store inputs to graph state ---
        {"src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
            {"src_field": "entity_username", "dst_field": "entity_username"},
            {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"},
            {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"},
            {"src_field": "enable_cache", "dst_field": "enable_cache"},
            {"src_field": "cache_lookback_days", "dst_field": "cache_lookback_days"},
        ]},

        # Input -> Load context
        {"src_node_id": "input_node", "dst_node_id": "load_context_docs", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
            {"src_field": "entity_username", "dst_field": "entity_username"},
        ]},

        # Load context -> State
        {"src_node_id": "load_context_docs", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "blog_company_doc", "dst_field": "blog_company_doc"},
            {"src_field": "linkedin_user_profile_doc", "dst_field": "linkedin_user_profile_doc"},
            {"src_field": "linkedin_scraped_profile_doc", "dst_field": "linkedin_scraped_profile_doc"},
        ]},
        {"src_node_id": "load_context_docs", "dst_node_id": "route_analysis"},
        
        # State -> Router (routing decisions based on flags)
        {"src_node_id": "$graph_state", "dst_node_id": "route_analysis", "mappings": [
            {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"},
            {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"},
        ]},

        # Router -> Downstream branches (control flow only)
        {"src_node_id": "route_analysis", "dst_node_id": "construct_competitive_analysis_prompt"},
        {"src_node_id": "route_analysis", "dst_node_id": "construct_exec_queries_prompt"},
        {"src_node_id": "route_analysis", "dst_node_id": "output_node"},

        # Blog path: State -> competitive analysis prompt
        {"src_node_id": "$graph_state", "dst_node_id": "construct_competitive_analysis_prompt", "mappings": [
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

        # Exec path: State -> exec queries prompt
        {"src_node_id": "$graph_state", "dst_node_id": "construct_exec_queries_prompt", "mappings": [
            {"src_field": "linkedin_user_profile_doc", "dst_field": "linkedin_user_profile_doc"},
            {"src_field": "linkedin_scraped_profile_doc", "dst_field": "linkedin_scraped_profile_doc"},
        ]},
        {"src_node_id": "construct_exec_queries_prompt", "dst_node_id": "generate_exec_queries", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"},
        ]},

        # Store query outputs in state
        # {"src_node_id": "generate_blog_queries", "dst_node_id": "$graph_state", "mappings": [
        #     {"src_field": "structured_output", "dst_field": "blog_coverage_queries"},
        # ]},
        # {"src_node_id": "generate_company_comp_queries", "dst_node_id": "$graph_state", "mappings": [
        #     {"src_field": "structured_output", "dst_field": "company_comp_queries"},
        # ]},
        # {"src_node_id": "generate_exec_queries", "dst_node_id": "$graph_state", "mappings": [
        #     {"src_field": "structured_output", "dst_field": "exec_queries"},
        # ]},

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
        {"src_node_id": "generate_exec_queries", "dst_node_id": "exec_ai_query", "mappings": [
            {"src_field": "structured_output", "dst_field": "query_templates"},
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "exec_ai_query", "mappings": [
            {"src_field": "enable_cache", "dst_field": "enable_mongodb_cache"},
            {"src_field": "cache_lookback_days", "dst_field": "cache_lookback_days"},
            {"src_field": "entity_username", "dst_field": "entity_name"}
        ]},

        # Store AI query results in state
        # {"src_node_id": "blog_coverage_ai_query", "dst_node_id": "$graph_state", "mappings": [
        #     {"src_field": "query_results", "dst_field": "blog_coverage_query_results"},
        #     {"src_field": "job_id", "dst_field": "blog_ai_job_id"},
        # ]},
        # {"src_node_id": "company_comp_ai_query", "dst_node_id": "$graph_state", "mappings": [
        #     {"src_field": "query_results", "dst_field": "company_comp_query_results"},
        #     {"src_field": "job_id", "dst_field": "company_comp_ai_job_id"},
        # ]},
        # {"src_node_id": "exec_ai_query", "dst_node_id": "$graph_state", "mappings": [
        #     {"src_field": "query_results", "dst_field": "exec_query_results"},
        #     {"src_field": "job_id", "dst_field": "exec_ai_job_id"},
        # ]},

        # Collect results for reports
        # {"src_node_id": "blog_coverage_ai_query", "dst_node_id": "collect_blog_coverage_results", "mappings": [
        #     {"src_field": "query_results", "dst_field": "query_results"},
        # ]},
        # {"src_node_id": "company_comp_ai_query", "dst_node_id": "collect_company_comp_results", "mappings": [
        #     {"src_field": "query_results", "dst_field": "query_results"},
        # ]},
        # {"src_node_id": "exec_ai_query", "dst_node_id": "collect_exec_results", "mappings": [
        #     {"src_field": "query_results", "dst_field": "query_results"},
        # ]},

        # Store collected results in state
        # {"src_node_id": "collect_blog_coverage_results", "dst_node_id": "$graph_state", "mappings": [
        #     {"src_field": "transformed_data.loaded_query_results", "dst_field": "blog_loaded_query_results"}
        # ]},
        # {"src_node_id": "collect_company_comp_results", "dst_node_id": "$graph_state", "mappings": [
        #     {"src_field": "transformed_data.loaded_query_results", "dst_field": "company_loaded_query_results"}
        # ]},
        # {"src_node_id": "collect_exec_results", "dst_node_id": "$graph_state", "mappings": [
        #     {"src_field": "transformed_data.loaded_query_results", "dst_field": "exec_loaded_query_results"}
        # ]},

        # Construct report prompts
        {"src_node_id": "blog_coverage_ai_query", "dst_node_id": "construct_blog_coverage_report_prompt", "mappings": [
            {"src_field": "query_results", "dst_field": "loaded_query_results"}
        ]},
        {"src_node_id": "company_comp_ai_query", "dst_node_id": "construct_company_comp_report_prompt", "mappings": [
            {"src_field": "query_results", "dst_field": "loaded_query_results"}
        ]},
        {"src_node_id": "exec_ai_query", "dst_node_id": "construct_exec_report_prompt", "mappings": [
            {"src_field": "query_results", "dst_field": "loaded_query_results"}
        ]},

        # Generate reports
        {"src_node_id": "construct_blog_coverage_report_prompt", "dst_node_id": "generate_blog_coverage_report", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"},
        ]},
        {"src_node_id": "construct_company_comp_report_prompt", "dst_node_id": "generate_company_comp_report", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"},
        ]},
        {"src_node_id": "construct_exec_report_prompt", "dst_node_id": "generate_exec_report", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"},
        ]},

        # Store generated reports in state
        {"src_node_id": "generate_blog_coverage_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "blog_coverage_report"},
        ]},
        {"src_node_id": "generate_company_comp_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "company_comp_report"},
        ]},
        {"src_node_id": "generate_exec_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "exec_report"},
        ]},

        # Store reports
        {"src_node_id": "generate_blog_coverage_report", "dst_node_id": "store_blog_coverage_report", "mappings": [
            {"src_field": "structured_output", "dst_field": "structured_output"},
        ]},
        {"src_node_id": "generate_company_comp_report", "dst_node_id": "store_company_comp_report", "mappings": [
            {"src_field": "structured_output", "dst_field": "structured_output"},
        ]},
        {"src_node_id": "generate_exec_report", "dst_node_id": "store_exec_report", "mappings": [
            {"src_field": "structured_output", "dst_field": "structured_output"},
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "store_blog_coverage_report", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "store_company_comp_report", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "store_exec_report", "mappings": [
            {"src_field": "entity_username", "dst_field": "entity_username"},
        ]},

        # Store paths in state
        {"src_node_id": "store_blog_coverage_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "paths_processed", "dst_field": "stored_blog_report_paths"},
        ]},
        {"src_node_id": "store_company_comp_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "paths_processed", "dst_field": "stored_company_report_paths"},
        ]},
        {"src_node_id": "store_exec_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "paths_processed", "dst_field": "stored_exec_report_paths"},
        ]},

        # Output mapping from state
        {"src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
            {"src_field": "blog_ai_job_id", "dst_field": "blog_ai_job_id"},
            {"src_field": "company_comp_ai_job_id", "dst_field": "company_comp_ai_job_id"},
            {"src_field": "exec_ai_job_id", "dst_field": "exec_ai_job_id"},
            {"src_field": "stored_blog_report_paths", "dst_field": "stored_blog_report_paths"},
            {"src_field": "stored_company_report_paths", "dst_field": "stored_company_report_paths"},
            {"src_field": "stored_exec_report_paths", "dst_field": "stored_exec_report_paths"},
        ]},

        # Direct output connections from storage nodes
        {"src_node_id": "store_blog_coverage_report", "dst_node_id": "output_node"},
        {"src_node_id": "store_company_comp_report", "dst_node_id": "output_node"},
        {"src_node_id": "store_exec_report", "dst_node_id": "output_node"},
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
                "exec_queries": "replace",
                "blog_coverage_query_results": "replace",
                "company_comp_query_results": "replace",
                "exec_query_results": "replace",
                "blog_loaded_query_results": "replace",
                "company_loaded_query_results": "replace",
                "exec_loaded_query_results": "replace",
                "blog_coverage_report": "replace",
                "company_comp_report": "replace",
                "exec_report": "replace",
                "stored_blog_report_paths": "replace",
                "stored_company_report_paths": "replace",
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

    test_company_name = "momentum"
    test_entity_username = "jmkmba"
    
    test_inputs = {
        "company_name": test_company_name,
        "entity_username": test_entity_username,
        "run_linkedin_exec": True,
        "run_blog_analysis": True,
        "enable_cache": True,
        "cache_lookback_days": 14,
    }

    # Define setup documents
    setup_docs = [
        # Blog Company Document
        {
            'namespace': BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item=test_company_name),
            'docname': BLOG_COMPANY_DOCNAME,
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
        # LinkedIn User Profile Document
        {
            'namespace': LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username),
            'docname': LINKEDIN_USER_PROFILE_DOCNAME,
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
            'namespace': LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username),
            'docname': LINKEDIN_SCRAPED_PROFILE_DOCNAME,
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
        {'namespace': BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item=test_company_name), 'docname': BLOG_COMPANY_DOCNAME, 'is_versioned': False, 'is_shared': False},
        {'namespace': LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username), 'docname': LINKEDIN_USER_PROFILE_DOCNAME, 'is_versioned': False, 'is_shared': False},
        {'namespace': LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username), 'docname': LINKEDIN_SCRAPED_PROFILE_DOCNAME, 'is_versioned': False, 'is_shared': False},
        # Cleanup generated test documents
        {'namespace': BLOG_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE.format(item=test_company_name), 'docname': BLOG_AI_VISIBILITY_TEST_DOCNAME, 'is_versioned': True, 'is_shared': False},
        {'namespace': BLOG_COMPANY_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE.format(item=test_company_name), 'docname': BLOG_COMPANY_AI_VISIBILITY_TEST_DOCNAME, 'is_versioned': True, 'is_shared': False},
        {'namespace': LINKEDIN_USER_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE.format(item=test_entity_username), 'docname': LINKEDIN_USER_AI_VISIBILITY_TEST_DOCNAME, 'is_versioned': True, 'is_shared': False},
    ]

    # No HITL inputs for this workflow
    predefined_hitl_inputs = []

    # Output validation function
    async def validate_ai_visibility_output(outputs):
        """Validates the workflow output to ensure it meets expected structure and content requirements."""
        assert outputs is not None, "Validation Failed: Workflow returned no outputs."
        
        # Check for job IDs from AI queries
        if outputs.get('run_blog_analysis'):
            assert 'blog_ai_job_id' in outputs, "Validation Failed: 'blog_ai_job_id' missing when blog analysis was run."
            assert 'company_comp_ai_job_id' in outputs, "Validation Failed: 'company_comp_ai_job_id' missing when blog analysis was run."
            assert 'stored_blog_report_paths' in outputs, "Validation Failed: 'stored_blog_report_paths' missing."
            assert 'stored_company_report_paths' in outputs, "Validation Failed: 'stored_company_report_paths' missing."
            print(f"✓ Blog analysis outputs validated successfully")
        
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
        if 'blog_ai_job_id' in final_run_outputs:
            print(f"Blog Coverage AI Job ID: {final_run_outputs.get('blog_ai_job_id')}")
        if 'company_comp_ai_job_id' in final_run_outputs:
            print(f"Company Comparison AI Job ID: {final_run_outputs.get('company_comp_ai_job_id')}")
        if 'exec_ai_job_id' in final_run_outputs:
            print(f"Executive Visibility AI Job ID: {final_run_outputs.get('exec_ai_job_id')}")
        if 'stored_blog_report_paths' in final_run_outputs:
            print(f"Stored Blog Report Paths: {final_run_outputs.get('stored_blog_report_paths')}")
        if 'stored_company_report_paths' in final_run_outputs:
            print(f"Stored Company Report Paths: {final_run_outputs.get('stored_company_report_paths')}")
        if 'stored_exec_report_paths' in final_run_outputs:
            print(f"Stored Exec Report Paths: {final_run_outputs.get('stored_exec_report_paths')}")

if __name__ == "__main__":
    try:
        asyncio.run(main_test_ai_visibility_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")