"""
Content Orchestrator Workflow

This workflow orchestrates the execution of multiple content analysis workflows.
It uses router nodes to enable parallel execution based on flags:
1. Deep Research Workflow - Performs deep research on the entity
2. Blog Content Analysis Workflow - Analyzes blog content  
3. Executive AI Visibility Workflow - Executive visibility and recognition
4. Company AI Visibility Workflow - Company blog coverage and AI visibility
4. LinkedIn Scraping Workflow - Scrapes LinkedIn profile and posts (if run_linkedin_exec is True)
5. LinkedIn Content Analysis Workflow - Analyzes the scraped content for themes (if run_linkedin_exec is True)

The workflow handles conditional execution based on flags and manages the data flow
through document storage/loading pattern.
"""

import json
import asyncio
from typing import List, Optional, Dict, Any
from functools import partial

# Import document model constants
from kiwi_client.workflows.active.document_models.customer_docs import (
    # LinkedIn documents
    LINKEDIN_CONTENT_ANALYSIS_DOCNAME,
    LINKEDIN_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
    LINKEDIN_USER_AI_VISIBILITY_TEST_DOCNAME,
    LINKEDIN_USER_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
    LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE,
    LINKEDIN_SCRAPED_PROFILE_DOCNAME,
    LINKEDIN_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
    LINKEDIN_DEEP_RESEARCH_REPORT_DOCNAME,
    LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
    LINKEDIN_USER_PROFILE_DOCNAME,
    # Blog/Company documents
    BLOG_CONTENT_ANALYSIS_DOCNAME,
    BLOG_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
    BLOG_AI_VISIBILITY_TEST_DOCNAME,
    BLOG_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
    BLOG_COMPANY_AI_VISIBILITY_TEST_DOCNAME,
    BLOG_COMPANY_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
    BLOG_TECHNICAL_ANALYSIS_DOCNAME,
    BLOG_TECHNICAL_ANALYSIS_NAMESPACE_TEMPLATE,
    BLOG_DEEP_RESEARCH_REPORT_DOCNAME,
    BLOG_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
    BLOG_CONTENT_PORTFOLIO_ANALYSIS_DOCNAME,
    BLOG_CONTENT_PORTFOLIO_ANALYSIS_NAMESPACE_TEMPLATE,
    BLOG_COMPETITOR_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
    BLOG_COMPETITOR_CONTENT_ANALYSIS_DOCNAME,
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
)

from kiwi_client.workflows.active.content_diagnostics.llm_inputs.orchestrator_final_reports import (
    EXECUTIVE_CONTENT_PERFORMANCE_PROMPT,
    EXECUTIVE_INDUSTRY_BENCHMARKING_PROMPT,
    PERSONAL_BRAND_OPPORTUNITIES_PROMPT,
    EXECUTIVE_ACTION_PLAN_PROMPT,
    BLOG_PERFORMANCE_HEALTH_PROMPT,
    CONTENT_QUALITY_STRUCTURE_PROMPT,
    COMPETITIVE_INTELLIGENCE_PROMPT,
    CONTENT_GAP_ANALYSIS_PROMPT,
    STRATEGIC_OPPORTUNITIES_PROMPT,
    COMPANY_ACTION_PLAN_PROMPT,
    BUSINESS_IMPACT_PROJECTION_PROMPT,
    EXECUTIVE_CONTENT_PERFORMANCE_SCHEMA,
    EXECUTIVE_INDUSTRY_BENCHMARKING_SCHEMA,
    PERSONAL_BRAND_OPPORTUNITIES_SCHEMA,
    EXECUTIVE_ACTION_PLAN_SCHEMA,
    BLOG_PERFORMANCE_HEALTH_SCHEMA,
    CONTENT_QUALITY_STRUCTURE_SCHEMA,
    COMPETITIVE_INTELLIGENCE_SCHEMA,
    CONTENT_GAP_ANALYSIS_SCHEMA,
    STRATEGIC_OPPORTUNITIES_SCHEMA,
    COMPANY_ACTION_PLAN_SCHEMA,
    BUSINESS_IMPACT_PROJECTION_SCHEMA
)

# --- Workflow Constants ---
# Workflow names to execute
DEEP_RESEARCH_WORKFLOW_NAME = "deep_research_workflow"
BLOG_CONTENT_ANALYSIS_WORKFLOW_NAME = "blog_content_analysis_workflow"
EXECUTIVE_AI_VISIBILITY_WORKFLOW_NAME = "executive_ai_visibility_workflow"
COMPANY_AI_VISIBILITY_WORKFLOW_NAME = "company_ai_visibility_workflow"
BLOG_COMPETITOR_CONTENT_ANALYSIS_WORKFLOW_NAME = "blog_competitor_content_analysis_workflow"
LINKEDIN_SCRAPING_WORKFLOW_NAME = "linkedin_linkedin_scraping_workflow"
LINKEDIN_ANALYSIS_WORKFLOW_NAME = "linkedin_linkedin_content_analysis_workflow"

# Timeouts for each workflow (in seconds)
DEEP_RESEARCH_TIMEOUT = 1200  # 20 minutes for deep research
BLOG_ANALYSIS_TIMEOUT = 1200  # 20 minutes for blog analysis
AI_VISIBILITY_TIMEOUT = 1200  # 20 minutes for AI visibility (multiple LLM calls)
SCRAPING_TIMEOUT = 600  # 10 minutes for scraping
ANALYSIS_TIMEOUT = 1200  # 20 minutes for analysis (LLM processing can take time)

# LLM defaults
LLM_PROVIDER = "anthropic"
LLM_MODEL = "claude-sonnet-4-20250514"
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 4000

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
                    "entity_username": {
                        "type": "str",
                        "required": True,
                        "description": "LinkedIn username for the entity (used for document naming)"
                    },
                    "company_name": {
                        "type": "str",
                        "required": True,
                        "description": "Company name for company-related processing"
                    },
                    "run_linkedin_exec": {
                        "type": "bool",
                        "required": True,
                        "description": "Flag to execute LinkedIn workflows"
                    },
                    "run_blog_analysis": {
                        "type": "bool",
                        "required": True,
                        "description": "Flag to execute company workflows"
                    },
                    "linkedin_profile_url": {
                        "type": "str",
                        "required": True,
                        "description": "LinkedIn URL of the entity"
                    },
                    "company_url": {
                        "type": "str",
                        "required": True,
                        "description": "Company website URL for company-related analysis"
                    },
                    "blog_start_urls": {
                        "type": "list",
                        "items_type": "str",
                        "required": False,
                        "description": "Start URLs for blog crawling (required if blog analysis is enabled)"
                    }
                }
            }
        },

        # --- 2. Initial Router - Routes to appropriate workflow groups ---
        "initial_router": {
            "node_id": "initial_router",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "run_blog_content_analysis",
                    "linkedin_router",
                    "company_router",
                    "run_executive_ai_visibility",
                    "run_company_ai_visibility"
                ],
                "allow_multiple": True,
                "default_choice": None,
                "choices_with_conditions": [
                    # Conditionally run Blog Content Analysis only when company workflows are enabled
                    {"choice_id": "run_blog_content_analysis", "input_path": "run_blog_analysis", "target_value": True},
                    # Conditionally route to LinkedIn workflows
                    {"choice_id": "linkedin_router", "input_path": "run_linkedin_exec", "target_value": True},
                    # Conditionally route to company workflows
                    {"choice_id": "company_router", "input_path": "run_blog_analysis", "target_value": True},
                    # Conditionally run Executive AI Visibility when LinkedIn exec is enabled
                    {"choice_id": "run_executive_ai_visibility", "input_path": "run_linkedin_exec", "target_value": True},
                    # Conditionally run Company AI Visibility when blog analysis is enabled
                    {"choice_id": "run_company_ai_visibility", "input_path": "run_blog_analysis", "target_value": True}
                ]
            }
        },

        # --- 3. Deep Research Workflow ---
        "run_deep_research": {
            "node_id": "run_deep_research",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": DEEP_RESEARCH_WORKFLOW_NAME,
                "execution_mode": "subprocess",
                "timeout_seconds": DEEP_RESEARCH_TIMEOUT,
                "poll_interval_seconds": 5,
                "fail_on_workflow_error": True
            }
        },

        # --- 4. Blog Content Analysis Workflow ---
        "run_blog_content_analysis": {
            "node_id": "run_blog_content_analysis",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": BLOG_CONTENT_ANALYSIS_WORKFLOW_NAME,
                "execution_mode": "subprocess",
                "timeout_seconds": BLOG_ANALYSIS_TIMEOUT,
                "poll_interval_seconds": 5,
                "fail_on_workflow_error": True
            }
        },

        # --- 5. Executive AI Visibility Workflow ---
        "run_executive_ai_visibility": {
            "node_id": "run_executive_ai_visibility",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": EXECUTIVE_AI_VISIBILITY_WORKFLOW_NAME,
                "execution_mode": "subprocess",
                "timeout_seconds": AI_VISIBILITY_TIMEOUT,
                "poll_interval_seconds": 5,
                "fail_on_workflow_error": True
            }
        },

        # --- 5b. Company AI Visibility Workflow ---
        "run_company_ai_visibility": {
            "node_id": "run_company_ai_visibility",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": COMPANY_AI_VISIBILITY_WORKFLOW_NAME,
                "execution_mode": "subprocess",
                "timeout_seconds": AI_VISIBILITY_TIMEOUT,
                "poll_interval_seconds": 5,
                "fail_on_workflow_error": True
            }
        },

        # --- 6. LinkedIn Router - Routes to LinkedIn workflows sequentially ---
        "linkedin_router": {
            "node_id": "linkedin_router",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "run_linkedin_scraping"
                ],
                "allow_multiple": False,
                "default_choice": "run_linkedin_scraping",
                "choices_with_conditions": [
                    {"choice_id": "run_linkedin_scraping", "input_path": "run_linkedin_exec", "target_value": True}
                ]
            }
        },

        # --- 7. Run LinkedIn Scraping Workflow ---
        "run_linkedin_scraping": {
            "node_id": "run_linkedin_scraping",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": LINKEDIN_SCRAPING_WORKFLOW_NAME,
                "execution_mode": "subprocess",
                "timeout_seconds": SCRAPING_TIMEOUT,
                "poll_interval_seconds": 5,
                "fail_on_workflow_error": True
            }
        },

        # --- 8. Run LinkedIn Content Analysis Workflow ---
        "run_linkedin_analysis": {
            "node_id": "run_linkedin_analysis",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": LINKEDIN_ANALYSIS_WORKFLOW_NAME,
                "execution_mode": "subprocess",
                "timeout_seconds": ANALYSIS_TIMEOUT,
                "poll_interval_seconds": 5,
                "fail_on_workflow_error": True
            }
        },

        # --- 9. Company Router - Routes to company workflows ---
        "company_router": {
            "node_id": "company_router",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "run_company_workflows"
                ],
                "allow_multiple": False,
                "default_choice": "run_company_workflows",
                "choices_with_conditions": [
                    {"choice_id": "run_company_workflows", "input_path": "run_blog_analysis", "target_value": True}
                ]
            }
        },

        # --- 10. Run Company Workflows (Actual) ---
        "run_company_workflows": {
            "node_id": "run_company_workflows",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "run_competitor_content_analysis"
                ],
                "allow_multiple": True,
                "default_choice": None,
                "choices_with_conditions": [
                    {"choice_id": "run_competitor_content_analysis", "input_path": "run_blog_analysis", "target_value": True}
                ]
            }
        },

        # 10b. Run Competitor Content Analysis Workflow
        "run_competitor_content_analysis": {
            "node_id": "run_competitor_content_analysis",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": BLOG_COMPETITOR_CONTENT_ANALYSIS_WORKFLOW_NAME,
                "execution_mode": "subprocess",
                "timeout_seconds": BLOG_ANALYSIS_TIMEOUT,
                "poll_interval_seconds": 5,
                "fail_on_workflow_error": True
            }
        },

        # --- 11. Wait for Core Workflows - Synchronization point ---
        "wait_for_core_workflows": {
            "node_id": "wait_for_core_workflows",
            "node_name": "transform_data",
            "enable_node_fan_in": True,
            "node_config": {
                "mappings": [
                    {
                        "source_path": "entity_username",
                        "destination_path": "entity_username"
                    }
                ]
            }
        },

        # # --- 12. Load Document Router - Routes to document loading nodes ---
        # "load_document_router": {
        #     "node_id": "load_document_router",
        #     "node_name": "router_node",
        #     "node_config": {
        #         "choices": [
        #             "load_linkedin_documents",
        #             "load_company_documents",
        #             "load_competitor_content_docs"
        #         ],
        #         "allow_multiple": True,
        #         "default_choice": None,
        #         "choices_with_conditions": [
        #             {"choice_id": "load_linkedin_documents", "input_path": "run_linkedin_exec", "target_value": True},
        #             {"choice_id": "load_company_documents", "input_path": "run_blog_analysis", "target_value": True},
        #             {"choice_id": "load_competitor_content_docs", "input_path": "run_blog_analysis", "target_value": True}
        #         ]
        #     }
        # },

        # # --- 13. Load LinkedIn-related documents ---
        # "load_linkedin_documents": {
        #     "node_id": "load_linkedin_documents",
        #     "node_name": "load_customer_data",
        #     "node_config": {
        #         "load_paths": [
        #             {
        #                 "filename_config": {
        #                     "input_namespace_field_pattern": LINKEDIN_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
        #                     "input_namespace_field": "entity_username",
        #                     "static_docname": LINKEDIN_CONTENT_ANALYSIS_DOCNAME,
        #                 },
        #                 "output_field_name": "linkedin_content_doc",
        #             },
        #             {
        #                 "filename_config": {
        #                     "input_namespace_field_pattern": LINKEDIN_USER_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
        #                     "input_namespace_field": "entity_username",
        #                     "static_docname": LINKEDIN_USER_AI_VISIBILITY_TEST_DOCNAME,
        #                 },
        #                 "output_field_name": "linkedin_ai_visibility_doc",
        #             },
        #             {
        #                 "filename_config": {
        #                     "input_namespace_field_pattern": LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE,
        #                     "input_namespace_field": "entity_username",
        #                     "static_docname": LINKEDIN_SCRAPED_PROFILE_DOCNAME
        #                 },
        #                 "output_field_name": "linkedin_scraped_profile_doc"
        #             },
        #             {
        #                 "filename_config": {
        #                     "input_namespace_field_pattern": LINKEDIN_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
        #                     "input_namespace_field": "entity_username",
        #                     "static_docname": LINKEDIN_DEEP_RESEARCH_REPORT_DOCNAME
        #                 },
        #                 "output_field_name": "linkedin_deep_research_doc"
        #             },
        #             {
        #                 "filename_config": {
        #                     "input_namespace_field_pattern": LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
        #                     "input_namespace_field": "entity_username",
        #                     "static_docname": LINKEDIN_USER_PROFILE_DOCNAME
        #                 },
        #                 "output_field_name": "linkedin_user_profile_doc"
        #             }
        #         ],
        #         "global_is_shared": False,
        #         "global_is_system_entity": False,
        #         "global_schema_options": {"load_schema": False},
        #     },
        # },

        # # Load Company/Blog-related documents
        # "load_company_documents": {
        #     "node_id": "load_company_documents",
        #     "node_name": "load_customer_data",
        #     "node_config": {
        #         "load_paths": [
        #             {
        #                 "filename_config": {
        #                     "input_namespace_field_pattern": BLOG_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
        #                     "input_namespace_field": "company_name",
        #                     "static_docname": BLOG_CONTENT_ANALYSIS_DOCNAME,
        #                 },
        #                 "output_field_name": "blog_content_doc",
        #             },
        #             {
        #                 "filename_config": {
        #                     "input_namespace_field_pattern": BLOG_CONTENT_PORTFOLIO_ANALYSIS_NAMESPACE_TEMPLATE,
        #                     "input_namespace_field": "company_name",
        #                     "static_docname": BLOG_CONTENT_PORTFOLIO_ANALYSIS_DOCNAME,
        #                 },
        #                 "output_field_name": "blog_portfolio_analysis_doc",
        #             },
        #             {
        #                 "filename_config": {
        #                     "input_namespace_field_pattern": BLOG_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
        #                     "input_namespace_field": "company_name",
        #                     "static_docname": BLOG_AI_VISIBILITY_TEST_DOCNAME,
        #                 },
        #                 "output_field_name": "blog_ai_visibility_doc",
        #             },
        #             {
        #                 "filename_config": {
        #                     "input_namespace_field_pattern": BLOG_COMPANY_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
        #                     "input_namespace_field": "company_name",
        #                     "static_docname": BLOG_COMPANY_AI_VISIBILITY_TEST_DOCNAME,
        #                 },
        #                 "output_field_name": "company_ai_visibility_doc",
        #             },
        #             {
        #                 "filename_config": {
        #                     "input_namespace_field_pattern": BLOG_TECHNICAL_ANALYSIS_NAMESPACE_TEMPLATE,
        #                     "input_namespace_field": "company_name",
        #                     "static_docname": BLOG_TECHNICAL_ANALYSIS_DOCNAME,
        #                 },
        #                 "output_field_name": "technical_seo_doc",
        #             },
        #             {
        #                 "filename_config": {
        #                     "input_namespace_field_pattern": BLOG_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
        #                     "input_namespace_field": "company_name",
        #                     "static_docname": BLOG_DEEP_RESEARCH_REPORT_DOCNAME,
        #                 },
        #                 "output_field_name": "deep_research_doc",
        #             },
        #             {
        #                 "filename_config": {
        #                     "input_namespace_field_pattern": BLOG_COMPANY_NAMESPACE_TEMPLATE,
        #                     "input_namespace_field": "company_name",
        #                     "static_docname": BLOG_COMPANY_DOCNAME
        #                 },
        #                 "output_field_name": "company_content_doc"
        #             }
        #         ],
        #         "global_is_shared": False,
        #         "global_is_system_entity": False,
        #         "global_schema_options": {"load_schema": False},
        #     },
        # },

        # # Load Multiple Competitor Content Analysis documents (list)
        # "load_competitor_content_docs": {
        #     "node_id": "load_competitor_content_docs",
        #     "node_name": "load_multiple_customer_data",
        #     "node_config": {
        #         "namespace_pattern": BLOG_COMPETITOR_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
        #         "namespace_pattern_input_path": "company_name",
        #         "include_shared": False,
        #         "include_user_specific": True,
        #         "include_system_entities": False,
        #         "limit": 5,
        #         "sort_by": "created_at",
        #         "sort_order": "desc",
        #         "output_field_name": "competitor_content_docs",
        #         "global_version_config": None,
        #         "global_schema_options": {"load_schema": False}
        #     }
        # },

        # # Merge competitor content docs list into a single document
        # "merge_competitor_content_docs": {
        #     "node_id": "merge_competitor_content_docs",
        #     "node_name": "merge_aggregate",
        #     "node_config": {
        #         "operations": [
        #             {
        #                 "output_field_name": "competitor_content_analysis_doc",
        #                 "select_paths": [
        #                     "competitor_content_docs"
        #                 ],
        #                 "merge_each_object_in_selected_list": True,
        #                 "merge_strategy": {
        #                     "map_phase": {
        #                         "key_mappings": [],
        #                         "unspecified_keys_strategy": "auto_merge"
        #                     },
        #                     "reduce_phase": {
        #                         "default_reducer": "nested_merge_aggregate",
        #                         "reducers": {},
        #                         "error_strategy": "coalesce_keep_non_empty"
        #                     },
        #                     "post_merge_transformations": {},
        #                     "transformation_error_strategy": "skip_operation"
        #                 }
        #             }
        #         ]
        #     }
        # },

        # # --- Wait for All Documents ---
        # "wait_for_documents": {
        #     "node_id": "wait_for_documents",
        #     "node_name": "transform_data",
        #     "enable_node_fan_in": True,
        #     "node_config": {
        #         "mappings": []
        #     }
        # },

        # # --- Report Generation Router ---
        # "report_generation_router": {
        #     "node_id": "report_generation_router",
        #     "node_name": "router_node",
        #     "node_config": {
        #         "choices": [
        #             "generate_executive_reports_router",
        #             "generate_company_reports_router"
        #         ],
        #         "allow_multiple": True,
        #         "default_choice": None,
        #         "choices_with_conditions": [
        #             {"choice_id": "generate_executive_reports_router", "input_path": "run_linkedin_exec", "target_value": True},
        #             {"choice_id": "generate_company_reports_router", "input_path": "run_blog_analysis", "target_value": True}
        #         ]
        #     }
        # },

        # # --- Executive Reports Router ---
        # "generate_executive_reports_router": {
        #     "node_id": "generate_executive_reports_router",
        #     "node_name": "router_node",
        #     "node_config": {
        #         "choices": [
        #             "construct_executive_content_performance_prompt",
        #             "construct_executive_industry_benchmarking_prompt",
        #             "construct_personal_brand_opportunities_prompt"
        #         ],
        #         "allow_multiple": True,
        #         "default_choice": None,
        #         "choices_with_conditions": [
        #             {"choice_id": "construct_executive_content_performance_prompt", "input_path": "run_linkedin_exec", "target_value": True},
        #             {"choice_id": "construct_executive_industry_benchmarking_prompt", "input_path": "run_linkedin_exec", "target_value": True},
        #             {"choice_id": "construct_personal_brand_opportunities_prompt", "input_path": "run_linkedin_exec", "target_value": True}
        #         ]
        #     }
        # },

        # # --- Company Reports Router ---
        # "generate_company_reports_router": {
        #     "node_id": "generate_company_reports_router",
        #     "node_name": "router_node",
        #     "node_config": {
        #         "choices": [
        #             "construct_blog_performance_health_prompt",
        #             "construct_content_quality_structure_prompt",
        #             "construct_competitive_intelligence_prompt",
        #             "construct_content_gap_analysis_prompt",
        #             "construct_strategic_opportunities_prompt"
        #         ],
        #         "allow_multiple": True,
        #         "default_choice": None,
        #         "choices_with_conditions": [
        #             {"choice_id": "construct_blog_performance_health_prompt", "input_path": "run_blog_analysis", "target_value": True},
        #             {"choice_id": "construct_content_quality_structure_prompt", "input_path": "run_blog_analysis", "target_value": True},
        #             {"choice_id": "construct_competitive_intelligence_prompt", "input_path": "run_blog_analysis", "target_value": True},
        #             {"choice_id": "construct_content_gap_analysis_prompt", "input_path": "run_blog_analysis", "target_value": True},
        #             {"choice_id": "construct_strategic_opportunities_prompt", "input_path": "run_blog_analysis", "target_value": True}
        #         ]
        #     }
        # },

        # # --- EXECUTIVE REPORT GENERATION NODES ---
        
        # # Executive Content Performance Prompt Constructor
        # "construct_executive_content_performance_prompt": {
        #     "node_id": "construct_executive_content_performance_prompt",
        #     "node_name": "prompt_constructor",
        #     "node_config": {
        #         "prompt_templates": {
        #             "user_prompt": {
        #                 "id": "user_prompt",
        #                 "template": EXECUTIVE_CONTENT_PERFORMANCE_PROMPT,
        #                 "variables": {
        #                     "linkedin_content_data": None,
        #                     "ai_visibility_data": None
        #                 },
        #                 "construct_options": {
        #                     "linkedin_content_data": "linkedin_content_data",
        #                     "ai_visibility_data": "ai_visibility_data"
        #                 }
        #             },
        #             "system_prompt": {
        #                 "id": "system_prompt",
        #                 "template": "You are an expert at analyzing LinkedIn content performance and generating structured JSON reports.",
        #                 "variables": {},
        #                 "construct_options": {}
        #             }
        #         }
        #     }
        # },

        # # Executive Content Performance Report
        # "generate_executive_content_performance": {
        #     "node_id": "generate_executive_content_performance",
        #     "node_name": "llm",
        #     "node_config": {
        #         "llm_config": {
        #             "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        #             "temperature": LLM_TEMPERATURE,
        #             "max_tokens": LLM_MAX_TOKENS
        #         },
        #         "output_schema": {"schema_definition": EXECUTIVE_CONTENT_PERFORMANCE_SCHEMA, "convert_loaded_schema_to_pydantic": False}
        #     }
        # },
 
        # # Executive Industry Benchmarking Prompt Constructor
        # "construct_executive_industry_benchmarking_prompt": {
        #     "node_id": "construct_executive_industry_benchmarking_prompt",
        #     "node_name": "prompt_constructor",
        #     "node_config": {
        #         "prompt_templates": {
        #             "user_prompt": {
        #                 "id": "user_prompt",
        #                 "template": EXECUTIVE_INDUSTRY_BENCHMARKING_PROMPT,
        #                 "variables": {
        #                     "linkedin_content_data": None,
        #                     "competitor_data": None,
        #                     "deep_research_data": None
        #                 },
        #                 "construct_options": {
        #                     "linkedin_content_data": "linkedin_content_data",
        #                     "competitor_data": "competitor_data",
        #                     "deep_research_data": "deep_research_data"
        #                 }
        #             },
        #             "system_prompt": {
        #                 "id": "system_prompt",
        #                 "template": "You are an expert at competitive benchmarking and industry analysis.",
        #                 "variables": {},
        #                 "construct_options": {}
        #             }
        #         }
        #     }
        # },

        # # Executive Industry Benchmarking Report
        # "generate_executive_industry_benchmarking": {
        #     "node_id": "generate_executive_industry_benchmarking",
        #     "node_name": "llm",
        #     "node_config": {
        #         "llm_config": {
        #             "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        #             "temperature": LLM_TEMPERATURE,
        #             "max_tokens": LLM_MAX_TOKENS
        #         },
        #         "output_schema": {"schema_definition": EXECUTIVE_INDUSTRY_BENCHMARKING_SCHEMA, "convert_loaded_schema_to_pydantic": False}
        #     }
        # },
 
        # # Personal Brand Opportunities Prompt Constructor
        # "construct_personal_brand_opportunities_prompt": {
        #     "node_id": "construct_personal_brand_opportunities_prompt",
        #     "node_name": "prompt_constructor",
        #     "node_config": {
        #         "prompt_templates": {
        #             "user_prompt": {
        #                 "id": "user_prompt",
        #                 "template": PERSONAL_BRAND_OPPORTUNITIES_PROMPT,
        #                 "variables": {
        #                     "linkedin_content_data": None,
        #                     "ai_visibility_data": None
        #                 },
        #                 "construct_options": {
        #                     "linkedin_content_data": "linkedin_content_data",
        #                     "ai_visibility_data": "ai_visibility_data"
        #                 }
        #             },
        #             "system_prompt": {
        #                 "id": "system_prompt",
        #                 "template": "You are an expert at identifying personal branding opportunities and strategic initiatives.",
        #                 "variables": {},
        #                 "construct_options": {}
        #             }
        #         }
        #     }
        # },

        # # Personal Brand Opportunities Report
        # "generate_personal_brand_opportunities": {
        #     "node_id": "generate_personal_brand_opportunities",
        #     "node_name": "llm",
        #     "node_config": {
        #         "llm_config": {
        #             "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        #             "temperature": LLM_TEMPERATURE,
        #             "max_tokens": LLM_MAX_TOKENS
        #         },
        #         "output_schema": {"schema_definition": PERSONAL_BRAND_OPPORTUNITIES_SCHEMA, "convert_loaded_schema_to_pydantic": False}
        #     }
        # },
 
        # # Executive Action Plan Prompt Constructor
        # "construct_executive_action_plan_prompt": {
        #     "node_id": "construct_executive_action_plan_prompt",
        #     "node_name": "prompt_constructor",
        #     "node_config": {
        #         "prompt_templates": {
        #             "user_prompt": {
        #                 "id": "user_prompt",
        #                 "template": EXECUTIVE_ACTION_PLAN_PROMPT,
        #                 "variables": {
        #                     "visibility_scorecard": None,
        #                     "content_performance": None,
        #                     "industry_benchmarking": None,
        #                     "ai_recognition": None,
        #                     "brand_opportunities": None
        #                 },
        #                 "construct_options": {
        #                     "visibility_scorecard": "visibility_scorecard",
        #                     "content_performance": "content_performance",
        #                     "industry_benchmarking": "industry_benchmarking",
        #                     "ai_recognition": "ai_recognition",
        #                     "brand_opportunities": "brand_opportunities"
        #                 }
        #             },
        #             "system_prompt": {
        #                 "id": "system_prompt",
        #                 "template": "You are an expert at creating strategic action plans for executives.",
        #                 "variables": {},
        #                 "construct_options": {}
        #             }
        #         }
        #     }
        # },

        # # Executive Action Plan Report
        # "generate_executive_action_plan": {
        #     "node_id": "generate_executive_action_plan",
        #     "node_name": "llm",
        #     "node_config": {
        #         "llm_config": {
        #             "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        #             "temperature": LLM_TEMPERATURE,
        #             "max_tokens": LLM_MAX_TOKENS
        #         },
        #         "output_schema": {"schema_definition": EXECUTIVE_ACTION_PLAN_SCHEMA, "convert_loaded_schema_to_pydantic": False}
        #     }
        # },

        # # Executive Reports Aggregator
        # "aggregate_executive_reports": {
        #     "node_id": "aggregate_executive_reports",
        #     "node_name": "transform_data",
        #     "enable_node_fan_in": True,
        #     "node_config": {
        #         "mappings": [
        #             {
        #                 "source_path": "executive_visibility_scorecard",
        #                 "destination_path": "executive_reports.visibility_scorecard"
        #             },
        #             {
        #                 "source_path": "executive_content_performance",
        #                 "destination_path": "executive_reports.content_performance"
        #             },
        #             {
        #                 "source_path": "executive_industry_benchmarking",
        #                 "destination_path": "executive_reports.industry_benchmarking"
        #             },
        #             {
        #                 "source_path": "executive_ai_recognition",
        #                 "destination_path": "executive_reports.ai_recognition"
        #             },
        #             {
        #                 "source_path": "personal_brand_opportunities",
        #                 "destination_path": "executive_reports.brand_opportunities"
        #             },
        #             {
        #                 "source_path": "executive_action_plan",
        #                 "destination_path": "executive_reports.action_plan"
        #             }
        #         ]
        #     }
        # },

        # # --- COMPANY REPORT GENERATION NODES ---
        
        # # Blog Performance Health Prompt Constructor
        # "construct_blog_performance_health_prompt": {
        #     "node_id": "construct_blog_performance_health_prompt",
        #     "node_name": "prompt_constructor",
        #     "node_config": {
        #         "prompt_templates": {
        #             "user_prompt": {
        #                 "id": "user_prompt",
        #                 "template": BLOG_PERFORMANCE_HEALTH_PROMPT,
        #                 "variables": {
        #                     "blog_content_data": None,
        #                     "blog_portfolio_data": None
        #                 },
        #                 "construct_options": {
        #                     "blog_content_data": "blog_content_data",
        #                     "blog_portfolio_data": "blog_portfolio_data"
        #                 }
        #             },
        #             "system_prompt": {
        #                 "id": "system_prompt",
        #                 "template": "You are an expert at analyzing blog content performance and health metrics.",
        #                 "variables": {},
        #                 "construct_options": {}
        #             }
        #         }
        #     }
        # },

        # # Content Quality & Structure Prompt Constructor
        # "construct_content_quality_structure_prompt": {
        #     "node_id": "construct_content_quality_structure_prompt",
        #     "node_name": "prompt_constructor",
        #     "node_config": {
        #         "prompt_templates": {
        #             "user_prompt": {
        #                 "id": "user_prompt",
        #                 "template": CONTENT_QUALITY_STRUCTURE_PROMPT,
        #                 "variables": {
        #                     "classified_posts_data": None,
        #                     "content_analysis_data": None
        #                 },
        #                 "construct_options": {
        #                     "classified_posts_data": "classified_posts_data",
        #                     "content_analysis_data": "content_analysis_data"
        #                 }
        #             },
        #             "system_prompt": {
        #                 "id": "system_prompt",
        #                 "template": "You are an expert at evaluating content quality, E-E-A-T, and content structure.",
        #                 "variables": {},
        #                 "construct_options": {}
        #             }
        #         }
        #     }
        # },

        # # Competitive Intelligence Prompt Constructor
        # "construct_competitive_intelligence_prompt": {
        #     "node_id": "construct_competitive_intelligence_prompt",
        #     "node_name": "prompt_constructor",
        #     "node_config": {
        #         "prompt_templates": {
        #             "user_prompt": {
        #                 "id": "user_prompt",
        #                 "template": COMPETITIVE_INTELLIGENCE_PROMPT,
        #                 "variables": {
        #                     "blog_content_data": None,
        #                     "competitor_data": None,
        #                     "deep_research_data": None
        #                 },
        #                 "construct_options": {
        #                     "blog_content_data": "blog_content_data",
        #                     "competitor_data": "competitor_data",
        #                     "deep_research_data": "deep_research_data"
        #                 }
        #             },
        #             "system_prompt": {
        #                 "id": "system_prompt",
        #                 "template": "You are an expert at competitive analysis and market intelligence.",
        #                 "variables": {},
        #                 "construct_options": {}
        #             }
        #         }
        #     }
        # },

        # # Content Gap Analysis Prompt Constructor
        # "construct_content_gap_analysis_prompt": {
        #     "node_id": "construct_content_gap_analysis_prompt",
        #     "node_name": "prompt_constructor",
        #     "node_config": {
        #         "prompt_templates": {
        #             "user_prompt": {
        #                 "id": "user_prompt",
        #                 "template": CONTENT_GAP_ANALYSIS_PROMPT,
        #                 "variables": {
        #                     "blog_content_data": None,
        #                     "competitor_data": None,
        #                     "deep_research_data": None
        #                 },
        #                 "construct_options": {
        #                     "blog_content_data": "blog_content_data",
        #                     "competitor_data": "competitor_data",
        #                     "deep_research_data": "deep_research_data"
        #                 }
        #             },
        #             "system_prompt": {
        #                 "id": "system_prompt",
        #                 "template": "You are an expert at identifying content gaps and opportunities.",
        #                 "variables": {},
        #                 "construct_options": {}
        #             }
        #         }
        #     }
        # },

        # # Strategic Opportunities Prompt Constructor
        # "construct_strategic_opportunities_prompt": {
        #     "node_id": "construct_strategic_opportunities_prompt",
        #     "node_name": "prompt_constructor",
        #     "node_config": {
        #         "prompt_templates": {
        #             "user_prompt": {
        #                 "id": "user_prompt",
        #                 "template": STRATEGIC_OPPORTUNITIES_PROMPT,
        #                 "variables": {
        #                     "deep_research_data": None,
        #                     "blog_portfolio_data": None,
        #                     "blog_content_data": None
        #                 },
        #                 "construct_options": {
        #                     "deep_research_data": "deep_research_data",
        #                     "blog_portfolio_data": "blog_portfolio_data",
        #                     "blog_content_data": "blog_content_data"
        #                 }
        #             },
        #             "system_prompt": {
        #                 "id": "system_prompt",
        #                 "template": "You are an expert at identifying strategic business opportunities.",
        #                 "variables": {},
        #                 "construct_options": {}
        #             }
        #         }
        #     }
        # },

        # # Blog Performance Health Report
        # "generate_blog_performance_health": {
        #     "node_id": "generate_blog_performance_health",
        #     "node_name": "llm",
        #     "node_config": {
        #         "llm_config": {
        #             "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        #             "temperature": LLM_TEMPERATURE,
        #             "max_tokens": LLM_MAX_TOKENS
        #         },
        #         "system_prompt": "You are an expert at analyzing blog content performance and health metrics.",
        #         "user_prompt_template": BLOG_PERFORMANCE_HEALTH_PROMPT,
        #         "output_schema": {"schema_definition": BLOG_PERFORMANCE_HEALTH_SCHEMA, "convert_loaded_schema_to_pydantic": False}
        #     }
        # },

        # # Content Quality & Structure Report
        # "generate_content_quality_structure": {
        #     "node_id": "generate_content_quality_structure",
        #     "node_name": "llm",
        #     "node_config": {
        #         "llm_config": {
        #             "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        #             "temperature": LLM_TEMPERATURE,
        #             "max_tokens": LLM_MAX_TOKENS
        #         },
        #         "system_prompt": "You are an expert at evaluating content quality, E-E-A-T, and content structure.",
        #         "user_prompt_template": CONTENT_QUALITY_STRUCTURE_PROMPT,
        #         "output_schema": {"schema_definition": CONTENT_QUALITY_STRUCTURE_SCHEMA, "convert_loaded_schema_to_pydantic": False}
        #     }
        # },

        # # Competitive Intelligence Report
        # "generate_competitive_intelligence": {
        #     "node_id": "generate_competitive_intelligence",
        #     "node_name": "llm",
        #     "node_config": {
        #         "llm_config": {
        #             "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        #             "temperature": LLM_TEMPERATURE,
        #             "max_tokens": LLM_MAX_TOKENS
        #         },
        #         "system_prompt": "You are an expert at competitive analysis and market intelligence.",
        #         "user_prompt_template": COMPETITIVE_INTELLIGENCE_PROMPT,
        #         "output_schema": {"schema_definition": COMPETITIVE_INTELLIGENCE_SCHEMA, "convert_loaded_schema_to_pydantic": False}
        #     }
        # },

        # # Content Gap Analysis Report
        # "generate_content_gap_analysis": {
        #     "node_id": "generate_content_gap_analysis",
        #     "node_name": "llm",
        #     "node_config": {
        #         "llm_config": {
        #             "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        #             "temperature": LLM_TEMPERATURE,
        #             "max_tokens": LLM_MAX_TOKENS
        #         },
        #         "system_prompt": "You are an expert at identifying content gaps and opportunities.",
        #         "user_prompt_template": CONTENT_GAP_ANALYSIS_PROMPT,
        #         "output_schema": {"schema_definition": CONTENT_GAP_ANALYSIS_SCHEMA, "convert_loaded_schema_to_pydantic": False}
        #     }
        # },

        # # Strategic Opportunities Report
        # "generate_strategic_opportunities": {
        #     "node_id": "generate_strategic_opportunities",
        #     "node_name": "llm",
        #     "node_config": {
        #         "llm_config": {
        #             "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        #             "temperature": LLM_TEMPERATURE,
        #             "max_tokens": LLM_MAX_TOKENS
        #         },
        #         "system_prompt": "You are an expert at identifying strategic business opportunities.",
        #         "user_prompt_template": STRATEGIC_OPPORTUNITIES_PROMPT,
        #         "output_schema": {"schema_definition": STRATEGIC_OPPORTUNITIES_SCHEMA, "convert_loaded_schema_to_pydantic": False}
        #     }
        # },
 
        # "construct_company_action_plan_prompt": {
        #     "node_id": "construct_company_action_plan_prompt",
        #     "node_name": "prompt_constructor",
        #     "node_config": {
        #         "prompt_templates": {
        #             "user_prompt": {
        #                 "id": "user_prompt",
        #                 "template": COMPANY_ACTION_PLAN_PROMPT,
        #                 "variables": {
        #                     "ai_visibility_overview": None,
        #                     "blog_performance": None,
        #                     "technical_seo": None,
        #                     "content_quality": None,
        #                     "competitive_intel": None,
        #                     "content_gaps": None,
        #                     "strategic_opps": None
        #                 },
        #                 "construct_options": {
        #                     "ai_visibility_overview": "ai_visibility_overview",
        #                     "blog_performance": "blog_performance",
        #                     "technical_seo": "technical_seo_foundation",
        #                     "content_quality": "content_quality_structure",
        #                     "competitive_intel": "competitive_intelligence",
        #                     "content_gaps": "content_gap_analysis",
        #                     "strategic_opps": "strategic_opportunities"
        #                 }
        #             },
        #             "system_prompt": {
        #                 "id": "system_prompt",
        #                 "template": "You are an expert at creating comprehensive strategic action plans.",
        #                 "variables": {},
        #                 "construct_options": {}
        #             }
        #         }
        #     }
        # },

        # # Company Action Plan Report
        # "generate_company_action_plan": {
        #     "node_id": "generate_company_action_plan",
        #     "node_name": "llm",
        #     "node_config": {
        #         "llm_config": {
        #             "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        #             "temperature": LLM_TEMPERATURE,
        #             "max_tokens": LLM_MAX_TOKENS
        #         },
        #         "output_schema": {"schema_definition": COMPANY_ACTION_PLAN_SCHEMA, "convert_loaded_schema_to_pydantic": False}
        #     }
        # },

        # # Company Reports Aggregator
        # "aggregate_company_reports": {
        #     "node_id": "aggregate_company_reports",
        #     "node_name": "transform_data",
        #     "enable_node_fan_in": True,
        #     "node_config": {
        #         "mappings": [
        #             {
        #                 "source_path": "company_ai_visibility_overview",
        #                 "destination_path": "company_reports.ai_visibility_overview"
        #             },
        #             {
        #                 "source_path": "blog_performance_health",
        #                 "destination_path": "company_reports.blog_performance_health"
        #             },
        #             {
        #                 "source_path": "technical_seo_foundation",
        #                 "destination_path": "company_reports.technical_seo_foundation"
        #             },
        #             {
        #                 "source_path": "content_quality_structure",
        #                 "destination_path": "company_reports.content_quality_structure"
        #             },
        #             {
        #                 "source_path": "competitive_intelligence",
        #                 "destination_path": "company_reports.competitive_intelligence"
        #             },
        #             {
        #                 "source_path": "content_gap_analysis",
        #                 "destination_path": "company_reports.content_gap_analysis"
        #             },
        #             {
        #                 "source_path": "strategic_opportunities",
        #                 "destination_path": "company_reports.strategic_opportunities"
        #             },
        #             {
        #                 "source_path": "company_action_plan",
        #                 "destination_path": "company_reports.action_plan"
        #             }
        #         ]
        #     }
        # },

        # # --- Business Impact Projection (Final Report) ---
        # "construct_business_impact_projection_prompt": {
        #     "node_id": "construct_business_impact_projection_prompt",
        #     "node_name": "prompt_constructor",
        #     "node_config": {
        #         "prompt_templates": {
        #             "user_prompt": {
        #                 "id": "user_prompt",
        #                 "template": BUSINESS_IMPACT_PROJECTION_PROMPT,
        #                 "variables": {
        #                     "executive_action_plan": None,
        #                     "company_action_plan": None,
        #                     "all_reports": None
        #                 },
        #                 "construct_options": {
        #                     "executive_action_plan": "executive_action_plan",
        #                     "company_action_plan": "company_action_plan",
        #                     "all_reports": "all_reports"
        #                 }
        #             },
        #             "system_prompt": {
        #                 "id": "system_prompt",
        #                 "template": "You are an expert at business impact analysis and ROI projection.",
        #                 "variables": {},
        #                 "construct_options": {}
        #             }
        #         }
        #     }
        # },
        # "generate_business_impact_projection": {
        #     "node_id": "generate_business_impact_projection",
        #     "node_name": "llm",
        #     "node_config": {
        #         "llm_config": {
        #             "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        #             "temperature": LLM_TEMPERATURE,
        #             "max_tokens": LLM_MAX_TOKENS
        #         },
        #         "output_schema": {"schema_definition": BUSINESS_IMPACT_PROJECTION_SCHEMA, "convert_loaded_schema_to_pydantic": False}
        #     }
        # },

        # # --- Final Report Aggregator ---
        # "combine_results": {
        #     "node_id": "combine_results",
        #     "node_name": "transform_data",
        #     "enable_node_fan_in": True,
        #     "node_config": {
        #         "mappings": [
        #             {
        #                 "source_path": "entity_username",
        #                 "destination_path": "final_results.entity_username"
        #             },
        #             {
        #                 "source_path": "company_name",
        #                 "destination_path": "final_results.company_name"
        #             },
        #             {
        #                 "source_path": "executive_reports",
        #                 "destination_path": "final_results.executive_reports",
        #                 "default_value": {}
        #             },
        #             {
        #                 "source_path": "company_reports",
        #                 "destination_path": "final_results.company_reports",
        #                 "default_value": {}
        #             },
        #             {
        #                 "source_path": "business_impact_projection",
        #                 "destination_path": "final_results.business_impact_projection",
        #                 "default_value": {}
        #             }
        #         ]
        #     }
        # },

        # --- 12. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {}
                            }
    },

    # --- Edges Defining Data Flow ---
    "edges": [
        # Store essential data in graph state
        {
            "src_node_id": "input_node",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"},
                {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"},
                {"src_field": "linkedin_profile_url", "dst_field": "linkedin_profile_url"},
                {"src_field": "company_url", "dst_field": "company_url"},
                {"src_field": "blog_start_urls", "dst_field": "blog_start_urls"}
            ]
        },

        # Input -> Initial Router
        {
            "src_node_id": "input_node",
            "dst_node_id": "initial_router",
            "mappings": [
                {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"},
                {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"}
            ]
        },

        # Router -> Blog Content Analysis (control flow)
        {
            "src_node_id": "initial_router",
            "dst_node_id": "run_blog_content_analysis",
            "mappings": []
        },

        # Pass required inputs to Blog Content Analysis
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "run_blog_content_analysis",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "blog_start_urls", "dst_field": "start_urls"}
            ]
        },

        # Input -> Deep Research (control flow)
        {
            "src_node_id": "input_node",
            "dst_node_id": "run_deep_research",
            "mappings": []
        },

        # Pass required inputs to Deep Research
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "run_deep_research",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "run_blog_analysis", "dst_field": "run_content_strategy"},
                {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_research"}
            ]
        },

        # Input -> Executive AI Visibility (control flow)
        {
            "src_node_id": "input_node",
            "dst_node_id": "run_executive_ai_visibility",
            "mappings": []
        },
        # Pass required inputs to Executive AI Visibility
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "run_executive_ai_visibility",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"}
            ]
        },

        # Input -> Company AI Visibility (control flow)
        {
            "src_node_id": "input_node",
            "dst_node_id": "run_company_ai_visibility",
            "mappings": []
        },
        # Pass required inputs to Company AI Visibility
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "run_company_ai_visibility",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"}
            ]
        },
 
         # Router -> LinkedIn Router (control flow)
         {
            "src_node_id": "initial_router",
            "dst_node_id": "linkedin_router",
            "mappings": []
        },

        # LinkedIn Router -> LinkedIn Scraping
        {
            "src_node_id": "linkedin_router",
            "dst_node_id": "run_linkedin_scraping",
            "mappings": []
        },

        # Pass data to LinkedIn scraping
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "run_linkedin_scraping",
            "mappings": [
                {"src_field": "linkedin_profile_url", "dst_field": "entity_url"},
                {"src_field": "entity_username", "dst_field": "entity_username"}
            ]
        },

        # LinkedIn Scraping -> LinkedIn Analysis (sequential)
        {
            "src_node_id": "run_linkedin_scraping",
            "dst_node_id": "run_linkedin_analysis",
            "mappings": []
        },

        # Pass entity_username to LinkedIn analysis
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "run_linkedin_analysis",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"}
            ]
        },

        # Router -> Company Router (control flow)
        {
            "src_node_id": "initial_router",
            "dst_node_id": "company_router",
            "mappings": []
        },

        # Company Router -> Company Workflows
        {
            "src_node_id": "company_router",
            "dst_node_id": "run_company_workflows",
            "mappings": []
        },

        # Pass data to company workflows
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "run_company_workflows",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "company_url", "dst_field": "company_url"}
            ]
        },
        {
            "src_node_id": "run_company_workflows",
            "dst_node_id": "run_competitor_content_analysis",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "run_competitor_content_analysis",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"}
            ]
        },

        # Store all results in state
        {
            "src_node_id": "run_deep_research",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "workflow_outputs", "dst_field": "deep_research_result"}
            ]
        },
        {
            "src_node_id": "run_blog_content_analysis",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "workflow_outputs", "dst_field": "blog_analysis_result"}
            ]
        },
        {
            "src_node_id": "run_executive_ai_visibility",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "workflow_outputs", "dst_field": "executive_ai_visibility_result"}
            ]
        },
        {
            "src_node_id": "run_company_ai_visibility",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "workflow_outputs", "dst_field": "company_ai_visibility_result"}
            ]
        },
        {
            "src_node_id": "run_linkedin_scraping",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "workflow_outputs", "dst_field": "linkedin_scraping_result"}
            ]
        },
        {
            "src_node_id": "run_linkedin_analysis",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "workflow_outputs", "dst_field": "linkedin_analysis_result"}
            ]
        },
        {
            "src_node_id": "run_company_workflows",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "company_result"}
            ]
        },

        # All workflows -> Wait for Core Workflows (fan-in)
        {
            "src_node_id": "run_deep_research",
            "dst_node_id": "wait_for_core_workflows",
            "mappings": []
        },
        {
            "src_node_id": "run_blog_content_analysis",
            "dst_node_id": "wait_for_core_workflows",
            "mappings": []
        },
        {
            "src_node_id": "run_executive_ai_visibility",
            "dst_node_id": "wait_for_core_workflows",
            "mappings": []
        },
        {
            "src_node_id": "run_company_ai_visibility",
            "dst_node_id": "wait_for_core_workflows",
            "mappings": []
        },
        {
            "src_node_id": "run_linkedin_analysis",
            "dst_node_id": "wait_for_core_workflows",
            "mappings": []
        },
        {
            "src_node_id": "run_company_workflows",
            "dst_node_id": "wait_for_core_workflows",
            "mappings": []
        },

        # Wait for Core Workflows -> Load Document Router
        # {
        #     "src_node_id": "wait_for_core_workflows",
        #     "dst_node_id": "load_document_router",
        #     "mappings": []
        # },
        {
            "src_node_id": "wait_for_core_workflows",
            "dst_node_id": "output_node",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "orchestration_results.entity_username"},
                {"src_field": "company_name", "dst_field": "orchestration_results.company_name"},
                {"src_field": "executive_ai_visibility_result", "dst_field": "orchestration_results"},
                {"src_field": "company_ai_visibility_result", "dst_field": "orchestration_results"}
            ]
        },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "load_document_router",
        #     "mappings": [
        #         {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"},
        #         {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"}
        #     ]
        # },

        # # --- Document Loading Edges ---
        
        # # Router -> LinkedIn Documents
        # {
        #     "src_node_id": "load_document_router",
        #     "dst_node_id": "load_linkedin_documents",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "load_linkedin_documents",
        #     "mappings": [
        #         {"src_field": "entity_username", "dst_field": "entity_username"}
        #     ]
        # },
        
        # # Router -> Company Documents
        # {
        #     "src_node_id": "load_document_router",
        #     "dst_node_id": "load_company_documents",
        #     "mappings": []
        # },
        # # Router -> Competitor Content Documents
        # {
        #     "src_node_id": "load_document_router",
        #     "dst_node_id": "load_competitor_content_docs",
        #     "mappings": []
        # },
        # # Router -> Competitor Content Documents input mapping
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "load_competitor_content_docs",
        #     "mappings": [
        #         {"src_field": "company_name", "dst_field": "company_name"}
        #     ]
        # },
        
        # # Store loaded documents in state
        # {
        #     "src_node_id": "load_linkedin_documents",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "linkedin_content_doc", "dst_field": "linkedin_content_doc"},
        #         {"src_field": "linkedin_ai_visibility_doc", "dst_field": "linkedin_ai_visibility_doc"},
        #         {"src_field": "linkedin_scraped_profile_doc", "dst_field": "linkedin_scraped_profile_doc"},
        #         {"src_field": "linkedin_scraped_posts_doc", "dst_field": "linkedin_scraped_posts_doc"},
        #         {"src_field": "linkedin_scraped_profile_raw_doc", "dst_field": "linkedin_scraped_profile_raw_doc"},
        #         {"src_field": "linkedin_scraped_posts_raw_doc", "dst_field": "linkedin_scraped_posts_raw_doc"},
        #         {"src_field": "linkedin_deep_research_doc", "dst_field": "linkedin_deep_research_doc"},
        #         {"src_field": "linkedin_user_profile_doc", "dst_field": "linkedin_user_profile_doc"}
        #     ]
        # },
        # {
        #     "src_node_id": "load_company_documents",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "blog_content_doc", "dst_field": "blog_content_doc"},
        #         {"src_field": "blog_portfolio_analysis_doc", "dst_field": "blog_portfolio_analysis_doc"},
        #         {"src_field": "blog_ai_visibility_doc", "dst_field": "blog_ai_visibility_doc"},
        #         {"src_field": "company_ai_visibility_doc", "dst_field": "company_ai_visibility_doc"},
        #         {"src_field": "technical_seo_doc", "dst_field": "technical_seo_doc"},
        #         {"src_field": "classified_posts_doc", "dst_field": "classified_posts_doc"},
        #         {"src_field": "deep_research_doc", "dst_field": "deep_research_doc"},
        #         {"src_field": "blog_company_doc", "dst_field": "blog_company_doc"},
        #         {"src_field": "competitor_content_analysis_doc", "dst_field": "competitor_content_analysis_doc"}
        #     ]
        # },
        # {
        #     "src_node_id": "load_competitor_content_docs",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "competitor_content_docs", "dst_field": "competitor_content_docs"}
        #     ]
        # },
        
        # # All document loads -> Wait for Documents
        # {
        #     "src_node_id": "load_linkedin_documents",
        #     "dst_node_id": "wait_for_documents",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "load_company_documents",
        #     "dst_node_id": "wait_for_documents",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "load_competitor_content_docs",
        #     "dst_node_id": "wait_for_documents",
        #     "mappings": []
        # },

        # # Wait for Documents -> Report Generation Router
        # {
        #     "src_node_id": "wait_for_documents",
        #     "dst_node_id": "report_generation_router",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "report_generation_router",
        #     "mappings": [
        #         {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"},
        #         {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"}
        #     ]
        # },

        # # --- EXECUTIVE REPORTS ROUTING ---
        
        # # Report Router -> Executive Reports Router (conditional)
        # {
        #     "src_node_id": "report_generation_router",
        #     "dst_node_id": "generate_executive_reports_router",
        #     "mappings": []
        # },
        
        # # Executive Reports Router -> Exec Content Performance Constructor
        # {
        #     "src_node_id": "generate_executive_reports_router",
        #     "dst_node_id": "construct_executive_content_performance_prompt",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "construct_executive_content_performance_prompt",
        #     "mappings": [
        #         {"src_field": "linkedin_content_doc", "dst_field": "linkedin_content_data"},
        #         {"src_field": "linkedin_ai_visibility_doc", "dst_field": "ai_visibility_data"}
        #     ]
        # },
        # {
        #     "src_node_id": "construct_executive_content_performance_prompt",
        #     "dst_node_id": "generate_executive_content_performance",
        #     "mappings": [
        #         {"src_field": "user_prompt", "dst_field": "user_prompt"},
        #         {"src_field": "system_prompt", "dst_field": "system_prompt"}
        #     ]
        # },
        # {
        #     "src_node_id": "generate_executive_content_performance",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "structured_ouput", "dst_field": "executive_content_performance"}
        #     ]
        # },
        
        # # Executive Reports Router -> Exec Industry Benchmarking Constructor
        # {
        #     "src_node_id": "generate_executive_reports_router",
        #     "dst_node_id": "construct_executive_industry_benchmarking_prompt",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "construct_executive_industry_benchmarking_prompt",
        #     "mappings": [
        #         {"src_field": "linkedin_content_doc", "dst_field": "linkedin_content_data"},
        #         {"src_field": "competitor_content_docs", "dst_field": "competitor_data"},
        #         {"src_field": "linkedin_deep_research_doc", "dst_field": "deep_research_data"}
        #     ]
        # },
        # {
        #     "src_node_id": "construct_executive_industry_benchmarking_prompt",
        #     "dst_node_id": "generate_executive_industry_benchmarking",
        #     "mappings": [
        #         {"src_field": "user_prompt", "dst_field": "user_prompt"},
        #         {"src_field": "system_prompt", "dst_field": "system_prompt"}
        #     ]
        # },
        
        # {
        #     "src_node_id": "generate_executive_industry_benchmarking",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "structured_ouput", "dst_field": "executive_industry_benchmarking"}
        #     ]
        # },
        
        # # Executive Reports Router -> Personal Brand Opps Constructor
        # {
        #     "src_node_id": "generate_executive_reports_router",
        #     "dst_node_id": "construct_personal_brand_opportunities_prompt",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "construct_personal_brand_opportunities_prompt",
        #     "mappings": [
        #         {"src_field": "linkedin_content_doc", "dst_field": "linkedin_content_data"},
        #         {"src_field": "linkedin_ai_visibility_doc", "dst_field": "ai_visibility_data"}
        #     ]
        # },
        # {
        #     "src_node_id": "construct_personal_brand_opportunities_prompt",
        #     "dst_node_id": "generate_personal_brand_opportunities",
        #     "mappings": [
        #         {"src_field": "user_prompt", "dst_field": "user_prompt"},
        #         {"src_field": "system_prompt", "dst_field": "system_prompt"}
        #     ]
        # },

        # # Personal Brand Opportunities Report
        # {
        #     "src_node_id": "generate_personal_brand_opportunities",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "structured_ouput", "dst_field": "personal_brand_opportunities"}
        #     ]
        # },

        # # All executive reports -> Executive Action Plan
        # {
        #     "src_node_id": "generate_executive_content_performance",
        #     "dst_node_id": "generate_executive_action_plan",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_executive_industry_benchmarking",
        #     "dst_node_id": "generate_executive_action_plan",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_personal_brand_opportunities",
        #     "dst_node_id": "generate_executive_action_plan",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "generate_executive_action_plan",
        #     "mappings": [
        #         {"src_field": "linkedin_ai_visibility_doc", "dst_field": "visibility_scorecard"},
        #         {"src_field": "executive_content_performance", "dst_field": "content_performance"},
        #         {"src_field": "executive_industry_benchmarking", "dst_field": "industry_benchmarking"},
        #         {"src_field": "linkedin_ai_visibility_doc", "dst_field": "ai_recognition"},
        #         {"src_field": "personal_brand_opportunities", "dst_field": "brand_opportunities"}
        #     ]
        # },
        
        # {
        #     "src_node_id": "generate_executive_action_plan",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "structured_ouput", "dst_field": "executive_action_plan"}
        #     ]
        # },

        # # All Executive reports -> Aggregator
        # {
        #     "src_node_id": "generate_executive_content_performance",
        #     "dst_node_id": "aggregate_executive_reports",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_executive_industry_benchmarking",
        #     "dst_node_id": "aggregate_executive_reports",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_personal_brand_opportunities",
        #     "dst_node_id": "aggregate_executive_reports",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_executive_action_plan",
        #     "dst_node_id": "aggregate_executive_reports",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "aggregate_executive_reports",
        #     "mappings": [
        #         {"src_field": "linkedin_ai_visibility_doc", "dst_field": "executive_visibility_scorecard"},
        #         {"src_field": "executive_content_performance", "dst_field": "executive_content_performance"},
        #         {"src_field": "executive_industry_benchmarking", "dst_field": "executive_industry_benchmarking"},
        #         {"src_field": "linkedin_ai_visibility_doc", "dst_field": "executive_ai_recognition"},
        #         {"src_field": "personal_brand_opportunities", "dst_field": "personal_brand_opportunities"},
        #         {"src_field": "executive_action_plan", "dst_field": "executive_action_plan"}
        #     ]
        # },
        # {
        #     "src_node_id": "aggregate_executive_reports",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "transformed_data", "dst_field": "executive_reports"}
        #     ]
        # },

        # # --- COMPANY REPORTS ROUTING ---
        
        # # Report Router -> Company Reports Router (conditional)
        # {
        #     "src_node_id": "report_generation_router",
        #     "dst_node_id": "generate_company_reports_router",
        #     "mappings": []
        # },
        
        # # Company Reports Router -> Individual Report Constructors
        # {
        #     "src_node_id": "generate_company_reports_router",
        #     "dst_node_id": "construct_blog_performance_health_prompt",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "construct_blog_performance_health_prompt",
        #     "mappings": [
        #         {"src_field": "blog_content_doc", "dst_field": "blog_content_data"},
        #         {"src_field": "blog_portfolio_analysis_doc", "dst_field": "blog_portfolio_data"}
        #     ]
        # },
        # {
        #     "src_node_id": "construct_blog_performance_health_prompt",
        #     "dst_node_id": "generate_blog_performance_health",
        #     "mappings": [
        #         {"src_field": "user_prompt", "dst_field": "user_prompt"},
        #         {"src_field": "system_prompt", "dst_field": "system_prompt"}
        #     ]
        # },
        
        # {
        #     "src_node_id": "generate_company_reports_router",
        #     "dst_node_id": "construct_content_quality_structure_prompt",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "construct_content_quality_structure_prompt",
        #     "mappings": [
        #         {"src_field": "blog_content_doc", "dst_field": "classified_posts_data"},
        #         {"src_field": "blog_content_doc", "dst_field": "content_analysis_data"}
        #     ]
        # },
        # {
        #     "src_node_id": "construct_content_quality_structure_prompt",
        #     "dst_node_id": "generate_content_quality_structure",
        #     "mappings": [
        #         {"src_field": "user_prompt", "dst_field": "user_prompt"},
        #         {"src_field": "system_prompt", "dst_field": "system_prompt"}
        #     ]
        # },
        
        # {
        #     "src_node_id": "generate_company_reports_router",
        #     "dst_node_id": "construct_competitive_intelligence_prompt",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "construct_competitive_intelligence_prompt",
        #     "mappings": [
        #         {"src_field": "blog_content_doc", "dst_field": "blog_content_data"},
        #         {"src_field": "competitor_content_analysis_doc", "dst_field": "competitor_data"},
        #         {"src_field": "deep_research_doc", "dst_field": "deep_research_data"}
        #     ]
        # },
        # {
        #     "src_node_id": "construct_competitive_intelligence_prompt",
        #     "dst_node_id": "generate_competitive_intelligence",
        #     "mappings": [
        #         {"src_field": "user_prompt", "dst_field": "user_prompt"},
        #         {"src_field": "system_prompt", "dst_field": "system_prompt"}
        #     ]
        # },
        
        # {
        #     "src_node_id": "generate_company_reports_router",
        #     "dst_node_id": "construct_content_gap_analysis_prompt",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "construct_content_gap_analysis_prompt",
        #     "mappings": [
        #         {"src_field": "blog_content_doc", "dst_field": "blog_content_data"},
        #         {"src_field": "competitor_content_analysis_doc", "dst_field": "competitor_data"},
        #         {"src_field": "deep_research_doc", "dst_field": "deep_research_data"}
        #     ]
        # },
        # {
        #     "src_node_id": "construct_content_gap_analysis_prompt",
        #     "dst_node_id": "generate_content_gap_analysis",
        #     "mappings": [
        #         {"src_field": "user_prompt", "dst_field": "user_prompt"},
        #         {"src_field": "system_prompt", "dst_field": "system_prompt"}
        #     ]
        # },
        
        # {
        #     "src_node_id": "generate_company_reports_router",
        #     "dst_node_id": "construct_strategic_opportunities_prompt",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "construct_strategic_opportunities_prompt",
        #     "mappings": [
        #         {"src_field": "deep_research_doc", "dst_field": "deep_research_data"},
        #         {"src_field": "blog_portfolio_analysis_doc", "dst_field": "blog_portfolio_data"},
        #         {"src_field": "blog_content_doc", "dst_field": "blog_content_data"}
        #     ]
        # },
        # {
        #     "src_node_id": "construct_strategic_opportunities_prompt",
        #     "dst_node_id": "generate_strategic_opportunities",
        #     "mappings": [
        #         {"src_field": "user_prompt", "dst_field": "user_prompt"},
        #         {"src_field": "system_prompt", "dst_field": "system_prompt"}
        #     ]
        # },

        # # Store company report outputs in state
        # {
        #     "src_node_id": "generate_blog_performance_health",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "structured_ouput", "dst_field": "blog_performance_health"}
        #     ]
        # },
        # {
        #     "src_node_id": "generate_content_quality_structure",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "structured_ouput", "dst_field": "content_quality_structure"}
        #     ]
        # },
        # {
        #     "src_node_id": "generate_competitive_intelligence",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "structured_ouput", "dst_field": "competitive_intelligence"}
        #     ]
        # },
        # {
        #     "src_node_id": "generate_content_gap_analysis",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "structured_ouput", "dst_field": "content_gap_analysis"}
        #     ]
        # },
        # {
        #     "src_node_id": "generate_strategic_opportunities",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "structured_ouput", "dst_field": "strategic_opportunities"}
        #     ]
        # },

        # # All company reports -> Company Action Plan
        # {
        #     "src_node_id": "generate_blog_performance_health",
        #     "dst_node_id": "generate_company_action_plan",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_content_quality_structure",
        #     "dst_node_id": "generate_company_action_plan",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_competitive_intelligence",
        #     "dst_node_id": "generate_company_action_plan",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_content_gap_analysis",
        #     "dst_node_id": "generate_company_action_plan",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_strategic_opportunities",
        #     "dst_node_id": "generate_company_action_plan",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "construct_company_action_plan_prompt",
        #     "mappings": [
        #         {"src_field": "company_ai_visibility_doc", "dst_field": "ai_visibility_overview"},
        #         {"src_field": "blog_performance_health", "dst_field": "blog_performance"},
        #         {"src_field": "technical_seo_doc", "dst_field": "technical_seo"},
        #         {"src_field": "content_quality_structure", "dst_field": "content_quality"},
        #         {"src_field": "competitive_intelligence", "dst_field": "competitive_intel"},
        #         {"src_field": "content_gap_analysis", "dst_field": "content_gaps"},
        #         {"src_field": "strategic_opportunities", "dst_field": "strategic_opps"}
        #     ]
        # },
        # {
        #     "src_node_id": "construct_company_action_plan_prompt",
        #     "dst_node_id": "generate_company_action_plan",
        #     "mappings": [
        #         {"src_field": "user_prompt", "dst_field": "user_prompt"},
        #         {"src_field": "system_prompt", "dst_field": "system_prompt"}
        #     ]
        # },
        # {
        #     "src_node_id": "generate_company_action_plan",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "structured_ouput", "dst_field": "company_action_plan"}
        #     ]
        # },

        # # All Company reports -> Aggregator
        # {
        #     "src_node_id": "generate_blog_performance_health",
        #     "dst_node_id": "aggregate_company_reports",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_content_quality_structure",
        #     "dst_node_id": "aggregate_company_reports",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_competitive_intelligence",
        #     "dst_node_id": "aggregate_company_reports",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_content_gap_analysis",
        #     "dst_node_id": "aggregate_company_reports",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_strategic_opportunities",
        #     "dst_node_id": "aggregate_company_reports",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_company_action_plan",
        #     "dst_node_id": "aggregate_company_reports",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "aggregate_company_reports",
        #     "mappings": [
        #         {"src_field": "company_ai_visibility_doc", "dst_field": "company_ai_visibility_overview"},
        #         {"src_field": "blog_ai_visibility_doc", "dst_field": "company_ai_visibility_overview.blog_ai_visibility"},
        #         {"src_field": "company_ai_visibility_doc", "dst_field": "company_ai_visibility_overview.company_ai_visibility"},
        #         {"src_field": "blog_performance_health", "dst_field": "blog_performance_health"},
        #         {"src_field": "technical_seo_doc", "dst_field": "technical_seo_foundation"},
        #         {"src_field": "content_quality_structure", "dst_field": "content_quality_structure"},
        #         {"src_field": "competitive_intelligence", "dst_field": "competitive_intelligence"},
        #         {"src_field": "content_gap_analysis", "dst_field": "content_gap_analysis"},
        #         {"src_field": "strategic_opportunities", "dst_field": "strategic_opportunities"},
        #         {"src_field": "company_action_plan", "dst_field": "company_action_plan"}
        #     ]
        # },
        # {
        #     "src_node_id": "aggregate_company_reports",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "transformed_data", "dst_field": "company_reports"}
        #     ]
        # },

        # # Build All Reports Summary for Business Impact
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "construct_business_impact_projection_prompt",
        #     "mappings": [
        #         {"src_field": "executive_action_plan", "dst_field": "executive_action_plan"},
        #         {"src_field": "company_action_plan", "dst_field": "company_action_plan"},
        #         {"src_field": "company_reports", "dst_field": "all_reports"}
        #     ]
        # },
        # {
        #     "src_node_id": "construct_business_impact_projection_prompt",
        #     "dst_node_id": "generate_business_impact_projection",
        #     "mappings": [
        #         {"src_field": "user_prompt", "dst_field": "user_prompt"},
        #         {"src_field": "system_prompt", "dst_field": "system_prompt"}
        #     ]
        # },
        # {
        #     "src_node_id": "generate_business_impact_projection",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "structured_ouput", "dst_field": "business_impact_projection"}
        #     ]
        # },

        # # Direct output mapping without final combine or projection
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "output_node",
        #     "mappings": [
        #         {"src_field": "entity_username", "dst_field": "orchestration_results.entity_username"},
        #         {"src_field": "company_name", "dst_field": "orchestration_results.company_name"},
        #         {"src_field": "executive_reports", "dst_field": "orchestration_results.executive_reports"},
        #         {"src_field": "company_reports", "dst_field": "orchestration_results.company_reports"},
        #         {"src_field": "business_impact_projection", "dst_field": "orchestration_results.business_impact_projection"},
        #         {"src_field": "executive_reports", "dst_field": "shared.executive_reports"},
        #         {"src_field": "company_reports", "dst_field": "shared.company_reports"}
        #     ]
        # },
        # {
        #     "src_node_id": "run_company_workflows",
        #     "dst_node_id": "run_competitor_content_analysis",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "$graph_state",
        #     "dst_node_id": "run_competitor_content_analysis",
        #     "mappings": [
        #         {"src_field": "company_name", "dst_field": "company_name"}
        #     ]
        # },
        # {
        #     "src_node_id": "run_competitor_content_analysis",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "workflow_outputs", "dst_field": "competitor_content_analysis_result"}
        #     ]
        # },
        {
            "src_node_id": "run_competitor_content_analysis",
            "dst_node_id": "wait_for_core_workflows",
            "mappings": []
        },
        # {
        #     "src_node_id": "load_competitor_content_docs",
        #     "dst_node_id": "merge_competitor_content_docs",
        #     "mappings": [
        #         {"src_field": "competitor_content_docs", "dst_field": "competitor_content_docs"}
        #     ]
        # },
        # {
        #     "src_node_id": "merge_competitor_content_docs",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "merged_data.competitor_content_analysis_doc", "dst_field": "competitor_content_analysis_doc"}
        #     ]
        # },
        # {
        #     "src_node_id": "merge_competitor_content_docs",
        #     "dst_node_id": "wait_for_documents",
        #     "mappings": []
        # }
    ],

    # --- State Reducer Configuration ---
    "metadata": {
        "$graph_state": {
            "reducer": {
                "entity_username": "replace",
                "company_name": "replace",
                "run_linkedin_exec": "replace",
                "run_blog_analysis": "replace",
                "linkedin_profile_url": "replace",
                "company_url": "replace",
                "deep_research_result": "replace",
                "blog_analysis_result": "replace",
                "executive_ai_visibility_result": "replace",
                "company_ai_visibility_result": "replace",
                "linkedin_scraping_result": "replace",
                "linkedin_analysis_result": "replace",
                "company_result": "replace",
                "linkedin_content_doc": "replace",
                "blog_content_doc": "replace",
                "linkedin_ai_visibility_doc": "replace",
                "company_ai_visibility_doc": "replace",
                 "deep_research_doc": "replace",
                 "competitor_content_analysis_result": "replace",
                "competitor_content_docs": "replace",
                "executive_reports": "replace",
                "company_reports": "replace",
                "business_impact_projection": "replace",
                "executive_content_performance": "replace",
                "executive_industry_benchmarking": "replace",
                "personal_brand_opportunities": "replace",
                "executive_action_plan": "replace",
                "blog_performance_health": "replace",
                "content_quality_structure": "replace",
                "competitive_intelligence": "replace",
                "content_gap_analysis": "replace",
                "strategic_opportunities": "replace",
                "company_action_plan": "replace",
                "linkedin_ai_visibility_doc": "replace",
                "linkedin_scraped_profile_doc": "replace",
                "linkedin_scraped_posts_doc": "replace",
                "linkedin_scraped_profile_raw_doc": "replace",
                "linkedin_scraped_posts_raw_doc": "replace",
                "linkedin_deep_research_doc": "replace",
                "linkedin_user_profile_doc": "replace",
                "blog_portfolio_analysis_doc": "replace",
                "blog_ai_visibility_doc": "replace",
                "company_ai_visibility_doc": "replace",
                "technical_seo_doc": "replace",
                "classified_posts_doc": "replace",
                "blog_company_doc": "replace",
                "competitor_content_analysis_doc": "replace"
            }
        }
    },

    # --- Define Start and End ---
    "input_node_id": "input_node",
    "output_node_id": "output_node"
}


# --- Test Execution Logic ---
import logging
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    CleanupDocInfo
)
from kiwi_client.test_config import CLIENT_LOG_LEVEL
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)


async def validate_orchestrator_output(outputs: Optional[Dict[str, Any]], test_inputs: Dict[str, Any]) -> bool:
    """
    Custom validation function for the orchestrator workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run.
        test_inputs: The test input data for comparison.
    
    Returns:
        True if the outputs are valid, False otherwise.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating Content Orchestrator workflow outputs...")
    
    # Check for expected keys
    assert 'orchestration_results' in outputs, "Validation Failed: 'orchestration_results' key missing in outputs."
    
    results = outputs['orchestration_results']
    
    # Verify entity information
    if test_inputs.get('entity_username'):
        assert results.get('entity_username') == test_inputs['entity_username'], \
            f"Validation Failed: Expected entity_username '{test_inputs['entity_username']}' but got '{results.get('entity_username')}'."
    
    assert results.get('company_name') == test_inputs['company_name'], \
        f"Validation Failed: Expected company_name '{test_inputs['company_name']}' but got '{results.get('company_name')}'."
    
    # Check executive reports if LinkedIn was executed
    if test_inputs['run_linkedin_exec']:
        assert 'executive_reports' in results, "Validation Failed: Executive reports missing."
        exec_reports = results.get('executive_reports', {})
        if exec_reports:
            logger.info("   ✓ Executive reports generated:")
            if 'visibility_scorecard' in exec_reports:
                logger.info("      - Visibility Scorecard")
            if 'content_performance' in exec_reports:
                logger.info("      - Content Performance")
            if 'industry_benchmarking' in exec_reports:
                logger.info("      - Industry Benchmarking")
            if 'ai_recognition' in exec_reports:
                logger.info("      - AI Recognition")
            if 'brand_opportunities' in exec_reports:
                logger.info("      - Brand Opportunities")
            if 'action_plan' in exec_reports:
                logger.info("      - Executive Action Plan")
    
    # Check company reports if company analysis was executed
    if test_inputs['run_blog_analysis']:
        assert 'company_reports' in results, "Validation Failed: Company reports missing."
        comp_reports = results.get('company_reports', {})
        if comp_reports:
            logger.info("   ✓ Company reports generated:")
            if 'ai_visibility_overview' in comp_reports:
                logger.info("      - AI Visibility Overview")
            if 'blog_performance_health' in comp_reports:
                logger.info("      - Blog Performance Health")
            if 'technical_seo_foundation' in comp_reports:
                logger.info("      - Technical SEO Foundation")
            if 'content_quality_structure' in comp_reports:
                logger.info("      - Content Quality & Structure")
            if 'competitive_intelligence' in comp_reports:
                logger.info("      - Competitive Intelligence")
            if 'content_gap_analysis' in comp_reports:
                logger.info("      - Content Gap Analysis")
            if 'strategic_opportunities' in comp_reports:
                logger.info("      - Strategic Opportunities")
            if 'action_plan' in comp_reports:
                logger.info("      - Company Action Plan")
    
    # Check business impact projection
    if 'business_impact_projection' in results:
        logger.info("   ✓ Business Impact Projection generated")
    
    logger.info("✓ Orchestrator output structure and content validation passed.")
    return True


async def main_test_orchestrator():
    """
    Tests the Content Orchestrator Workflow using the run_workflow_test helper function.
    """
    # --- Test Inputs ---
    TEST_INPUTS = {
        "entity_username": "santiycr",  # LinkedIn username
        "company_name": "momentum",  # Company name for analysis
        "run_linkedin_exec": True,  # Execute LinkedIn workflows
        "run_blog_analysis": True,  # Skip company workflows for now
        "linkedin_profile_url": "https://www.linkedin.com/in/santiycr/",  # LinkedIn URL
        "company_url": "https://www.momentum.io",  # Company website URL (optional)
        "blog_start_urls": ["https://www.momentum.io"] # Example blog start URL
    }
    
    test_name = "Content Orchestrator Workflow Test"
    print(f"--- Starting {test_name} ---")
    
    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=TEST_INPUTS,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=None,  # No HITL steps in this workflow
        setup_docs=[],  # No prerequisite documents
        cleanup_docs=[],  # Documents are managed by sub-workflows
        validate_output_func=partial(validate_orchestrator_output, test_inputs=TEST_INPUTS),
        stream_intermediate_results=True,
        poll_interval_sec=5,
        timeout_sec=2400  # 40 minutes total timeout (multiple workflows)
    )
    
    print(f"\n--- {test_name} Finished ---")


if __name__ == "__main__":
    print("=" * 50)
    print("Executing Content Orchestrator Workflow Test")
    print("=" * 50)
    
    # Handle potential nested asyncio loop issues
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        print("   Async event loop already running. Adding task...")
        tsk = loop.create_task(main_test_orchestrator())
    else:
        print("   Starting new async event loop...")
        asyncio.run(main_test_orchestrator())
    
    print("\nRun this script from the project root directory using:")
    print("poetry run python kiwi_client/workflows/active/content_diagnostics/wf_orchestrator_workflow.py")