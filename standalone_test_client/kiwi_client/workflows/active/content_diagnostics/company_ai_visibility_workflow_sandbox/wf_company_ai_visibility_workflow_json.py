import asyncio
import logging
from typing import Dict, Any, Optional, List, Union, ClassVar, Type
import json
from enum import Enum

# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field


from kiwi_client.workflows.active.document_models.customer_docs import (
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    BLOG_AI_VISIBILITY_TEST_DOCNAME,
    BLOG_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
    BLOG_COMPANY_AI_VISIBILITY_TEST_DOCNAME,
    BLOG_COMPANY_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
    BLOG_AI_VISIBILITY_RAW_DATA_DOCNAME,
    BLOG_AI_VISIBILITY_RAW_DATA_NAMESPACE
)

from kiwi_client.workflows.active.content_diagnostics.company_ai_visibility_workflow_sandbox.wf_llm_inputs import (
    # LLM Configuration
    LLM_PROVIDER_FOR_INITITAL_ANALYSIS,
    LLM_MODEL_FOR_INITITAL_ANALYSIS,
    LLM_TEMPERATURE_FOR_INITIAL_ANALYSIS,
    LLM_MAX_TOKENS_FOR_INITIAL_ANALYSIS,
    LLM_PROVIDER_FOR_REPORT,
    LLM_MODEL_FOR_REPORT,
    LLM_TEMPERATURE_FOR_REPORT,
    LLM_MAX_TOKENS_FOR_REPORT,
    MAX_TOKENS_FOR_COVERAGE_REPORT,
    # Prompts and Schemas
    COMPETITIVE_ANALYSIS_SYSTEM_PROMPT,
    COMPETITIVE_ANALYSIS_USER_PROMPT_TEMPLATE,
    COMPETITIVE_ANALYSIS_SCHEMA,
    BLOG_COVERAGE_SYSTEM_PROMPT,
    BLOG_COVERAGE_USER_PROMPT_TEMPLATE,
    BLOG_COVERAGE_QUERIES_SCHEMA,
    COMPANY_COMP_SYSTEM_PROMPT,
    COMPANY_COMP_USER_PROMPT_TEMPLATE,
    COMPANY_COMP_QUERIES_SCHEMA,
    BLOG_COVERAGE_REPORT_SYSTEM_PROMPT,
    BLOG_COVERAGE_REPORT_USER_PROMPT_TEMPLATE,
    BLOG_COVERAGE_REPORT_SCHEMA,
    COMPANY_COMP_REPORT_SYSTEM_PROMPT,
    COMPANY_COMP_REPORT_USER_PROMPT_TEMPLATE,
    COMPANY_COMP_REPORT_SCHEMA,
)

workflow_graph_schema = {
    "nodes": {
        # 1) Input
        "input_node": {
            "node_id": "input_node",

            "node_category": "system",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "company_name": {"type": "str", "required": True},
                    "enable_cache": {"type": "bool", "default": True, "required": False},
                    "cache_lookback_days": {"type": "int", "default": 7, "required": False},
                }
            },
        },

        # 2) Load required context docs
        "load_context_docs": {
            "node_id": "load_context_docs",

            "node_category": "system",
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

            "node_category": "analysis",
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

            "node_category": "analysis",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_FOR_INITITAL_ANALYSIS, "model": LLM_MODEL_FOR_INITITAL_ANALYSIS},
                    "temperature": LLM_TEMPERATURE_FOR_INITIAL_ANALYSIS,
                    "max_tokens": LLM_MAX_TOKENS_FOR_INITIAL_ANALYSIS,
                },
                "output_schema": {"schema_definition": COMPETITIVE_ANALYSIS_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },

        # --- 4.1 Blog Coverage Query Generation ---
        "construct_blog_queries_prompt": {
            "node_id": "construct_blog_queries_prompt",

            "node_category": "query_generation",
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

            "node_category": "query_generation",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_FOR_REPORT, "model": LLM_MODEL_FOR_REPORT},
                    "temperature": LLM_TEMPERATURE_FOR_REPORT,
                    "max_tokens": LLM_MAX_TOKENS_FOR_REPORT,
                },
                "output_schema": {"schema_definition": BLOG_COVERAGE_QUERIES_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },

        # --- 4.2 Company & Competitor Query Generation ---
        "construct_company_comp_queries_prompt": {
            "node_id": "construct_company_comp_queries_prompt",

            "node_category": "query_generation",
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

            "node_category": "query_generation",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_FOR_REPORT, "model": LLM_MODEL_FOR_REPORT},
                    "temperature": LLM_TEMPERATURE_FOR_REPORT,
                    "max_tokens": LLM_MAX_TOKENS_FOR_REPORT,
                },
                "output_schema": {"schema_definition": COMPANY_COMP_QUERIES_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },

        # --- 5. LLM Analysis Phase: Execute queries on answer engines ---
        "blog_coverage_ai_query": {
            "node_id": "blog_coverage_ai_query",

            "node_category": "ai_visibility_analysis",
            "node_name": "ai_answer_engine_scraper",
            "node_config": {
                "return_nested_entity_results": True,
                "entity_name_path": "entity_name"
            }
        },
        "company_comp_ai_query": {
            "node_id": "company_comp_ai_query",

            "node_category": "ai_visibility_analysis",
            "node_name": "ai_answer_engine_scraper",
            "node_config": {
                "return_nested_entity_results": True,
                "entity_name_path": "entity_name"
            }
        },

        # Store raw scraper results to uploaded_files namespace
        "store_blog_raw_scraper_results": {
            "node_id": "store_blog_raw_scraper_results",

            "node_category": "system",
            "node_name": "store_customer_data",
            "node_config": {
                "store_configs": [
                    {
                        "input_field_path": "query_results",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_AI_VISIBILITY_RAW_DATA_NAMESPACE,
                                "input_namespace_field": "company_name",
                                "static_docname": BLOG_AI_VISIBILITY_RAW_DATA_DOCNAME
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

            "node_category": "system",
            "node_name": "store_customer_data",
            "node_config": {
                "store_configs": [
                    {
                        "input_field_path": "query_results",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_AI_VISIBILITY_RAW_DATA_NAMESPACE,
                                "input_namespace_field": "company_name",
                                "static_docname": BLOG_AI_VISIBILITY_RAW_DATA_DOCNAME
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
        
        # --- 6. Report Generation ---
        # 6.1 Blog Coverage Report
        "construct_blog_coverage_report_prompt": {
            "node_id": "construct_blog_coverage_report_prompt",

            "node_category": "ai_visibility_analysis",
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

            "node_category": "ai_visibility_analysis",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_FOR_REPORT, "model": LLM_MODEL_FOR_REPORT},
                    "temperature": LLM_TEMPERATURE_FOR_REPORT,
                    "max_tokens": MAX_TOKENS_FOR_COVERAGE_REPORT,
                },
                "output_schema": {"schema_definition": BLOG_COVERAGE_REPORT_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },
        "store_blog_coverage_report": {
            "node_id": "store_blog_coverage_report",

            "node_category": "system",
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

            "node_category": "ai_visibility_analysis",
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

            "node_category": "ai_visibility_analysis",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_FOR_REPORT, "model": LLM_MODEL_FOR_REPORT},
                    "temperature": LLM_TEMPERATURE_FOR_REPORT,
                    "max_tokens": MAX_TOKENS_FOR_COVERAGE_REPORT,
                },
                "output_schema": {"schema_definition": COMPANY_COMP_REPORT_SCHEMA, "convert_loaded_schema_to_pydantic": False},
            },
        },
        "store_company_comp_report": {
            "node_id": "store_company_comp_report",

            "node_category": "system",
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

        # Final output
        "output_node": {
            "node_id": "output_node",

            "node_category": "system",
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

        # Construct report prompts
        {"src_node_id": "blog_coverage_ai_query", "dst_node_id": "construct_blog_coverage_report_prompt", "mappings": [
            {"src_field": "query_results", "dst_field": "loaded_query_results"}
        ]},
        {"src_node_id": "company_comp_ai_query", "dst_node_id": "construct_company_comp_report_prompt", "mappings": [
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

        # Store generated reports in state
        {"src_node_id": "generate_blog_coverage_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "blog_coverage_report"},
        ]},
        {"src_node_id": "generate_company_comp_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "company_comp_report"},
        ]},

        # Store reports
        {"src_node_id": "generate_blog_coverage_report", "dst_node_id": "store_blog_coverage_report", "mappings": [
            {"src_field": "structured_output", "dst_field": "structured_output"},
        ]},
        {"src_node_id": "generate_company_comp_report", "dst_node_id": "store_company_comp_report", "mappings": [
            {"src_field": "structured_output", "dst_field": "structured_output"},
        ]},

        {"src_node_id": "$graph_state", "dst_node_id": "store_blog_coverage_report", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "store_company_comp_report", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
        ]},

        # Store paths and passthrough data in state
        {"src_node_id": "store_blog_coverage_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "paths_processed", "dst_field": "stored_blog_report_paths"},
            {"src_field": "passthrough_data", "dst_field": "blog_coverage_report"}
        ]},
        {"src_node_id": "store_company_comp_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "paths_processed", "dst_field": "stored_company_report_paths"},
            {"src_field": "passthrough_data", "dst_field": "company_comp_report"}
        ]},

        {"src_node_id": "store_blog_coverage_report", "dst_node_id": "output_node", "mappings": [
        ]},

        {"src_node_id": "store_company_comp_report", "dst_node_id": "output_node", "mappings": [
        ]},

        # Output mapping from state
        {"src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
            {"src_field": "blog_coverage_report", "dst_field": "blog_coverage_report"},
            {"src_field": "company_comp_report", "dst_field": "company_comp_report"}
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
                "blog_loaded_query_results": "replace",
                "company_loaded_query_results": "replace",
                "blog_coverage_report": "replace",
                "company_comp_report": "replace",
                "stored_blog_report_paths": "replace",
                "stored_company_report_paths": "replace",
            }
        }
    }
}