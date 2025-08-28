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
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    # Final diagnostic reports
    LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
    LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
)

from kiwi_client.workflows.active.content_diagnostics.llm_inputs.orchestrator_final_reports import (
    # LinkedIn Executive Reports
    LINKEDIN_COMPETITIVE_INTELLIGENCE_USER_PROMPT,
    LINKEDIN_COMPETITIVE_INTELLIGENCE_SYSTEM_PROMPT,
    LINKEDIN_CONTENT_PERFORMANCE_ANALYSIS_USER_PROMPT,
    LINKEDIN_CONTENT_PERFORMANCE_ANALYSIS_SYSTEM_PROMPT,
    LINKEDIN_CONTENT_STRATEGY_GAPS_USER_PROMPT,
    LINKEDIN_CONTENT_STRATEGY_GAPS_SYSTEM_PROMPT,
    LINKEDIN_STRATEGIC_RECOMMENDATIONS_USER_PROMPT,
    LINKEDIN_STRATEGIC_RECOMMENDATIONS_SYSTEM_PROMPT,
    # Blog/Company Reports
    BLOG_AI_VISIBILITY_REPORT_USER_PROMPT,
    BLOG_AI_VISIBILITY_REPORT_SYSTEM_PROMPT,
    BLOG_COMPETITIVE_INTELLIGENCE_REPORT_USER_PROMPT,
    BLOG_COMPETITIVE_INTELLIGENCE_REPORT_SYSTEM_PROMPT,
    BLOG_PERFORMANCE_REPORT_USER_PROMPT,
    BLOG_PERFORMANCE_REPORT_SYSTEM_PROMPT,
    BLOG_GAP_ANALYSIS_VALIDATION_USER_PROMPT,
    BLOG_GAP_ANALYSIS_VALIDATION_SYSTEM_PROMPT,
    BLOG_STRATEGIC_RECOMMENDATIONS_USER_PROMPT,
    BLOG_STRATEGIC_RECOMMENDATIONS_SYSTEM_PROMPT,
    # Executive Summary Reports
    BLOG_EXECUTIVE_SUMMARY_USER_PROMPT,
    BLOG_EXECUTIVE_SUMMARY_SYSTEM_PROMPT,
    LINKEDIN_EXECUTIVE_SUMMARY_USER_PROMPT,
    LINKEDIN_EXECUTIVE_SUMMARY_SYSTEM_PROMPT,
    # Schemas
    LINKEDIN_COMPETITIVE_INTELLIGENCE_SCHEMA,
    LINKEDIN_CONTENT_PERFORMANCE_ANALYSIS_SCHEMA,
    LINKEDIN_CONTENT_STRATEGY_GAPS_SCHEMA,
    LINKEDIN_STRATEGIC_RECOMMENDATIONS_SCHEMA,
    BLOG_AI_VISIBILITY_REPORT_SCHEMA,
    BLOG_COMPETITIVE_INTELLIGENCE_REPORT_SCHEMA,
    BLOG_PERFORMANCE_REPORT_SCHEMA,
    BLOG_GAP_ANALYSIS_VALIDATION_SCHEMA,
    BLOG_STRATEGIC_RECOMMENDATIONS_SCHEMA,
    # Executive Summary Schemas
    LINKEDIN_EXECUTIVE_SUMMARY_SCHEMA,
    # Pydantic Schemas
    BLOG_EXECUTIVE_SUMMARY_SCHEMA_PYDANTIC,
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
DEEP_RESEARCH_TIMEOUT = 1800  # 30 minutes for deep research
BLOG_ANALYSIS_TIMEOUT = 1200  # 20 minutes for blog analysis
AI_VISIBILITY_TIMEOUT = 1200  # 20 minutes for AI visibility (multiple LLM calls)
SCRAPING_TIMEOUT = 600  # 10 minutes for scraping
ANALYSIS_TIMEOUT = 1200  # 20 minutes for analysis (LLM processing can take time)

LLM_PROVIDER_FOR_STRATEGIC_RECOMMENDATIONS = "openai"
LLM_MODEL_FOR_STRATEGIC_RECOMMENDATIONS = "gpt-5"
LLM_TEMPERATURE_FOR_STRATEGIC_RECOMMENDATIONS = 0.5
LLM_MAX_TOKENS_FOR_STRATEGIC_RECOMMENDATIONS = 20000

# LLM defaults
LLM_PROVIDER = "anthropic"
LLM_MODEL = "claude-sonnet-4-20250514"
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 4000

CACHE_ENABLED = True

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
                        "required": False,
                        "description": "LinkedIn username for the entity (used for document naming)"
                    },
                    "company_name": {
                        "type": "str",
                        "required": False,
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
                        "required": False,
                        "description": "LinkedIn URL of the entity"
                    },
                    "company_url": {
                        "type": "str",
                        "required": False,
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
        
        "linkedin_router": {
            "node_id": "linkedin_router",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "run_linkedin_scraping",
                    "initial_router"
                ],
                "allow_multiple": True,
                "default_choice": None,
                "choices_with_conditions": [
                    {"choice_id": "run_linkedin_scraping", "input_path": "run_linkedin_exec", "target_value": True},
                    {"choice_id": "initial_router", "input_path": "run_linkedin_exec", "target_value": False}
                ]
            }
        },


        # --- 2. Initial Router - Routes to appropriate workflow groups ---
        "initial_router": {
            "node_id": "initial_router",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "run_blog_content_analysis",
                    "run_deep_research",
                    "run_executive_ai_visibility",
                    "run_company_ai_visibility",
                    "run_competitor_content_analysis",
                    "run_linkedin_analysis"
                ],
                "allow_multiple": True,
                "default_choice": None,
                "choices_with_conditions": [
                    # Conditionally run Blog Content Analysis only when company workflows are enabled
                    {"choice_id": "run_blog_content_analysis", "input_path": "run_blog_analysis", "target_value": True},
                    # Conditionally run Blog Content Analysis only when company workflows are enabled
                    {"choice_id": "run_competitor_content_analysis", "input_path": "run_blog_analysis", "target_value": True},

                    # Conditionally route to LinkedIn workflows
                    {"choice_id": "run_deep_research", "input_path": "run_linkedin_exec", "target_value": True},

                    {"choice_id": "run_deep_research", "input_path": "run_linkedin_exec", "target_value": False},

                    # Conditionally run Executive AI Visibility when LinkedIn exec is enabled
                    {"choice_id": "run_executive_ai_visibility", "input_path": "run_linkedin_exec", "target_value": True},
                    # Conditionally run Company AI Visibility when blog analysis is enabled
                    {"choice_id": "run_company_ai_visibility", "input_path": "run_blog_analysis", "target_value": True},

                    {"choice_id": "run_linkedin_analysis", "input_path": "run_linkedin_exec", "target_value": True}
                ]
            }
        },

        # --- 3. Deep Research Workflow ---
        "run_deep_research": {
            "node_id": "run_deep_research",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": DEEP_RESEARCH_WORKFLOW_NAME,
                "timeout_seconds": DEEP_RESEARCH_TIMEOUT,
                "enable_workflow_cache": CACHE_ENABLED
            }
        },

        # --- 4. Blog Content Analysis Workflow ---
        "run_blog_content_analysis": {
            "node_id": "run_blog_content_analysis",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": BLOG_CONTENT_ANALYSIS_WORKFLOW_NAME,
                "timeout_seconds": BLOG_ANALYSIS_TIMEOUT,
                "enable_workflow_cache": CACHE_ENABLED
            }
        },

        # --- 5. Executive AI Visibility Workflow ---
        "run_executive_ai_visibility": {
            "node_id": "run_executive_ai_visibility",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": EXECUTIVE_AI_VISIBILITY_WORKFLOW_NAME,
                "timeout_seconds": AI_VISIBILITY_TIMEOUT,
                "check_error_free_logs": False,
                "enable_workflow_cache": CACHE_ENABLED
            }
        },

        # --- 5b. Company AI Visibility Workflow ---
        "run_company_ai_visibility": {
            "node_id": "run_company_ai_visibility",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": COMPANY_AI_VISIBILITY_WORKFLOW_NAME,
                "timeout_seconds": AI_VISIBILITY_TIMEOUT,
                "check_error_free_logs": False,
                "enable_workflow_cache": CACHE_ENABLED
            }
        },

        # --- 7. Run LinkedIn Scraping Workflow ---
        "run_linkedin_scraping": {
            "node_id": "run_linkedin_scraping",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": LINKEDIN_SCRAPING_WORKFLOW_NAME,
                "timeout_seconds": SCRAPING_TIMEOUT,
                "enable_workflow_cache": CACHE_ENABLED
                }
        },

        # --- 8. Run LinkedIn Content Analysis Workflow ---
        "run_linkedin_analysis": {
            "node_id": "run_linkedin_analysis",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": LINKEDIN_ANALYSIS_WORKFLOW_NAME,
                "timeout_seconds": ANALYSIS_TIMEOUT,
                "enable_workflow_cache": CACHE_ENABLED
                }
        },

        # 10b. Run Competitor Content Analysis Workflow
        "run_competitor_content_analysis": {
            "node_id": "run_competitor_content_analysis",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": BLOG_COMPETITOR_CONTENT_ANALYSIS_WORKFLOW_NAME,
                "timeout_seconds": BLOG_ANALYSIS_TIMEOUT,
                "enable_workflow_cache": CACHE_ENABLED
                }
        },

        # --- 11. Wait for Core Workflows - Synchronization point ---
        "wait_for_core_workflows": {
            "node_id": "wait_for_core_workflows",
            "node_name": "transform_data",
            "defer_node": True,
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
        "load_document_router": {
            "node_id": "load_document_router",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "load_linkedin_documents",
                    "load_company_documents",
                    "load_competitor_content_docs"
                ],
                "allow_multiple": True,
                "default_choice": None,
                "choices_with_conditions": [
                    {"choice_id": "load_linkedin_documents", "input_path": "run_linkedin_exec", "target_value": True},
                    {"choice_id": "load_company_documents", "input_path": "run_blog_analysis", "target_value": True},
                    {"choice_id": "load_competitor_content_docs", "input_path": "run_blog_analysis", "target_value": True}
                ]
            }
        },

        # # --- 13. Load LinkedIn-related documents ---
        "load_linkedin_documents": {
            "node_id": "load_linkedin_documents",
            "node_name": "load_customer_data",
            "node_config": {
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_CONTENT_ANALYSIS_DOCNAME,
                        },
                        "output_field_name": "linkedin_content_doc",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_USER_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_USER_AI_VISIBILITY_TEST_DOCNAME,
                        },
                        "output_field_name": "linkedin_ai_visibility_doc",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_SCRAPED_PROFILE_DOCNAME
                        },
                        "output_field_name": "linkedin_scraped_profile_doc"
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_DEEP_RESEARCH_REPORT_DOCNAME
                        },
                        "output_field_name": "linkedin_deep_research_doc"
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_USER_PROFILE_DOCNAME
                        },
                        "output_field_name": "linkedin_user_profile_doc"
                    }
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
            },
        },

        # # Load Company/Blog-related documents
        "load_company_documents": {
            "node_id": "load_company_documents",
            "node_name": "load_customer_data",
            "node_config": {
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_CONTENT_ANALYSIS_DOCNAME,
                        },
                        "output_field_name": "blog_content_analysis_doc",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_CONTENT_PORTFOLIO_ANALYSIS_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_CONTENT_PORTFOLIO_ANALYSIS_DOCNAME,
                        },
                        "output_field_name": "blog_portfolio_analysis_doc",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_AI_VISIBILITY_TEST_DOCNAME,
                        },
                        "output_field_name": "blog_ai_visibility_doc",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_COMPANY_AI_VISIBILITY_TEST_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_COMPANY_AI_VISIBILITY_TEST_DOCNAME,
                        },
                        "output_field_name": "company_ai_visibility_doc",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_TECHNICAL_ANALYSIS_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_TECHNICAL_ANALYSIS_DOCNAME,
                        },
                        "output_field_name": "technical_seo_doc",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_DEEP_RESEARCH_REPORT_DOCNAME,
                        },
                        "output_field_name": "deep_research_doc",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_COMPANY_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_COMPANY_DOCNAME
                        },
                        "output_field_name": "company_context_doc"
                    }
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
            },
        },

        # # Load Multiple Competitor Content Analysis documents (list)
        "load_competitor_content_docs": {
            "node_id": "load_competitor_content_docs",
            "node_name": "load_multiple_customer_data",
            "node_config": {
                "namespace_pattern": BLOG_COMPETITOR_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
                "namespace_pattern_input_path": "company_name",
                "include_shared": False,
                "include_user_specific": True,
                "include_system_entities": False,
                "limit": 5,
                "sort_by": "created_at",
                "sort_order": "desc",
                "output_field_name": "competitor_content_docs",
                "global_version_config": None,
                "global_schema_options": {"load_schema": False}
            }
        },

        # # --- Wait for All Documents ---
        "wait_for_documents": {
            "node_id": "wait_for_documents",
            "node_name": "transform_data",
            "defer_node": True,
            "node_config": {
                "mappings": [
                    {
                        "source_path": "entity_username",
                        "destination_path": "entity_username"
                    }
                ]
            }
        },

        # # --- Report Generation Router ---
        "report_generation_router": {
            "node_id": "report_generation_router",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "generate_executive_reports_router",
                    "generate_company_reports_router"
                ],
                "allow_multiple": True,
                "default_choice": None,
                "choices_with_conditions": [
                    {"choice_id": "generate_executive_reports_router", "input_path": "run_linkedin_exec", "target_value": True},
                    {"choice_id": "generate_company_reports_router", "input_path": "run_blog_analysis", "target_value": True}
                ]
            }
        },

        # # --- Executive Reports Router ---
        "generate_executive_reports_router": {
            "node_id": "generate_executive_reports_router",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "construct_linkedin_competitive_intelligence_prompt",
                    "construct_content_performance_analysis_prompt",
                    "construct_content_strategy_gaps_prompt"
                ],
                "allow_multiple": True,
                "default_choice": None,
                "choices_with_conditions": [
                    {"choice_id": "construct_linkedin_competitive_intelligence_prompt", "input_path": "run_linkedin_exec", "target_value": True},
                    {"choice_id": "construct_content_performance_analysis_prompt", "input_path": "run_linkedin_exec", "target_value": True},
                    {"choice_id": "construct_content_strategy_gaps_prompt", "input_path": "run_linkedin_exec", "target_value": True}
                ]
            }
        },

        # --- Company Reports Router ---
        "generate_company_reports_router": {
            "node_id": "generate_company_reports_router",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "construct_ai_visibility_report_prompt",
                    "construct_competitive_intelligence_report_prompt",
                    "construct_blog_performance_report_prompt",
                    "construct_gap_analysis_validation_prompt"
                ],
                "allow_multiple": True,
                "default_choice": None,
                "choices_with_conditions": [
                    {"choice_id": "construct_ai_visibility_report_prompt", "input_path": "run_blog_analysis", "target_value": True},
                    {"choice_id": "construct_competitive_intelligence_report_prompt", "input_path": "run_blog_analysis", "target_value": True},
                    {"choice_id": "construct_blog_performance_report_prompt", "input_path": "run_blog_analysis", "target_value": True},
                    {"choice_id": "construct_gap_analysis_validation_prompt", "input_path": "run_blog_analysis", "target_value": True}
                ]
            }
        },

        # # --- EXECUTIVE REPORT GENERATION NODES ---
        
        # # 1. LinkedIn Competitive Intelligence Prompt Constructor
        "construct_linkedin_competitive_intelligence_prompt": {
            "node_id": "construct_linkedin_competitive_intelligence_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": LINKEDIN_COMPETITIVE_INTELLIGENCE_USER_PROMPT,
                        "variables": {
                            "linkedin_user_profile_data": None,
                            "linkedin_deep_research_data": None
                        },
                        "construct_options": {
                            "linkedin_user_profile_data": "linkedin_user_profile_data",
                            "linkedin_deep_research_data": "linkedin_deep_research_data"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": LINKEDIN_COMPETITIVE_INTELLIGENCE_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },

        # # LinkedIn Competitive Intelligence Report
        "generate_linkedin_competitive_intelligence": {
            "node_id": "generate_linkedin_competitive_intelligence",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {"schema_definition": LINKEDIN_COMPETITIVE_INTELLIGENCE_SCHEMA, "convert_loaded_schema_to_pydantic": False}
            }
        },
 
        # # 2. Content Performance Analysis Prompt Constructor
        "construct_content_performance_analysis_prompt": {
            "node_id": "construct_content_performance_analysis_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": LINKEDIN_CONTENT_PERFORMANCE_ANALYSIS_USER_PROMPT,
                        "variables": {
                            "linkedin_content_analysis_data": None,
                            "linkedin_user_profile_data": None
                        },
                        "construct_options": {
                            "linkedin_content_analysis_data": "linkedin_content_analysis_data",
                            "linkedin_user_profile_data": "linkedin_user_profile_data"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": LINKEDIN_CONTENT_PERFORMANCE_ANALYSIS_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },

        # # Content Performance Analysis Report
        "generate_content_performance_analysis": {
            "node_id": "generate_content_performance_analysis",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {"schema_definition": LINKEDIN_CONTENT_PERFORMANCE_ANALYSIS_SCHEMA, "convert_loaded_schema_to_pydantic": False}
            }
        },
 
        # # 3. Content Strategy Gaps Prompt Constructor
        "construct_content_strategy_gaps_prompt": {
            "node_id": "construct_content_strategy_gaps_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": LINKEDIN_CONTENT_STRATEGY_GAPS_USER_PROMPT,
                        "variables": {
                            "deep_research_data": None,
                            "linkedin_user_profile_data": None,
                            "linkedin_content_analysis_data": None
                        },
                        "construct_options": {
                            "deep_research_data": "deep_research_data",
                            "linkedin_user_profile_data": "linkedin_user_profile_data",
                            "linkedin_content_analysis_data": "linkedin_content_analysis_data"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": LINKEDIN_CONTENT_STRATEGY_GAPS_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },

        # Content Strategy Gaps Report
        "generate_content_strategy_gaps": {
            "node_id": "generate_content_strategy_gaps",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {"schema_definition": LINKEDIN_CONTENT_STRATEGY_GAPS_SCHEMA, "convert_loaded_schema_to_pydantic": False}
            }
        },
 
        # # 4. Strategic LinkedIn Recommendations Prompt Constructor  
        "construct_strategic_linkedin_recommendations_prompt": {
            "node_id": "construct_strategic_linkedin_recommendations_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": LINKEDIN_STRATEGIC_RECOMMENDATIONS_USER_PROMPT,
                        "variables": {
                            "linkedin_visibility_assessment": None,
                            "linkedin_competitive_intelligence": None,
                            "content_performance_analysis": None,
                            "content_strategy_gaps": None,
                            "linkedin_user_profile_doc": None
                        },
                        "construct_options": {
                            "linkedin_visibility_assessment": "linkedin_visibility_assessment",
                            "linkedin_competitive_intelligence": "linkedin_competitive_intelligence",
                            "content_performance_analysis": "content_performance_analysis",
                            "content_strategy_gaps": "content_strategy_gaps",
                            "linkedin_user_profile_doc": "linkedin_user_profile_doc"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": LINKEDIN_STRATEGIC_RECOMMENDATIONS_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },

        # # Strategic LinkedIn Recommendations Report
        "generate_strategic_linkedin_recommendations": {
            "node_id": "generate_strategic_linkedin_recommendations",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_FOR_STRATEGIC_RECOMMENDATIONS, "model": LLM_MODEL_FOR_STRATEGIC_RECOMMENDATIONS},
                    "temperature": LLM_TEMPERATURE_FOR_STRATEGIC_RECOMMENDATIONS,
                    "max_tokens": LLM_MAX_TOKENS_FOR_STRATEGIC_RECOMMENDATIONS,
                    "reasoning_effort_class": "high"
                },
                "output_schema": {"schema_definition": LINKEDIN_STRATEGIC_RECOMMENDATIONS_SCHEMA, "convert_loaded_schema_to_pydantic": False}
            }
        },

                # # 4. Strategic LinkedIn Recommendations Prompt Constructor  
        "construct_linkedin_executive_summary_prompt": {
            "node_id": "construct_linkedin_executive_summary_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": LINKEDIN_EXECUTIVE_SUMMARY_USER_PROMPT,
                        "variables": {
                            "linkedin_visibility_assessment": None,
                            "linkedin_competitive_intelligence": None,
                            "content_performance_analysis": None,
                            "content_strategy_gaps": None,
                            "linkedin_user_profile_doc": None
                        },
                        "construct_options": {
                            "linkedin_visibility_assessment": "linkedin_visibility_assessment",
                            "linkedin_competitive_intelligence": "linkedin_competitive_intelligence",
                            "content_performance_analysis": "content_performance_analysis",
                            "content_strategy_gaps": "content_strategy_gaps",
                            "linkedin_user_profile_doc": "linkedin_user_profile_doc"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": LINKEDIN_EXECUTIVE_SUMMARY_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },

        # # Strategic LinkedIn Recommendations Report
        "generate_linkedin_executive_summary": {
            "node_id": "generate_linkedin_executive_summary",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_FOR_STRATEGIC_RECOMMENDATIONS, "model": LLM_MODEL_FOR_STRATEGIC_RECOMMENDATIONS},
                    "temperature": LLM_TEMPERATURE_FOR_STRATEGIC_RECOMMENDATIONS,
                    "max_tokens": LLM_MAX_TOKENS_FOR_STRATEGIC_RECOMMENDATIONS,
                    "reasoning_effort_class": "high"
                },
                "output_schema": {"schema_definition": LINKEDIN_EXECUTIVE_SUMMARY_SCHEMA, "convert_loaded_schema_to_pydantic": False}
            }
        },

        # Executive Reports Aggregator
        "aggregate_executive_reports": {
            "node_id": "aggregate_executive_reports",
            "node_name": "transform_data",
            "enable_node_fan_in": True,
            "node_config": {
                "mappings": [
                    {
                        "source_path": "linkedin_user_ai_visibility_doc",
                        "destination_path": "executive_reports.linkedin_visibility_assessment"
                    },
                    {
                        "source_path": "linkedin_competitive_intelligence",
                        "destination_path": "executive_reports.linkedin_competitive_intelligence"
                    },
                    {
                        "source_path": "content_performance_analysis",
                        "destination_path": "executive_reports.content_performance_analysis"
                    },
                    {
                        "source_path": "content_strategy_gaps",
                        "destination_path": "executive_reports.content_strategy_gaps"
                    },
                    {
                        "source_path": "strategic_linkedin_recommendations",
                        "destination_path": "executive_reports.strategic_linkedin_recommendations"
                    },
                    {
                        "source_path": "linkedin_executive_summary",
                        "destination_path": "executive_reports.executive_summary"
                    }
                ]
            }
        },

        # # --- COMPANY REPORT GENERATION NODES ---
        # # 1. AI Visibility Report Prompt Constructor
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

        # # 2. Competitive Intelligence Report Prompt Constructor
        "construct_competitive_intelligence_report_prompt": {
            "node_id": "construct_competitive_intelligence_report_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": BLOG_COMPETITIVE_INTELLIGENCE_REPORT_USER_PROMPT,
                        "variables": {
                            "competitor_data": None,
                            "deep_research_data": None,
                            "company_context_doc": None
                        },
                        "construct_options": {
                            "competitor_data": "competitor_data",
                            "deep_research_data": "deep_research_data",
                            "company_context_doc": "company_context_doc"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": BLOG_COMPETITIVE_INTELLIGENCE_REPORT_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },



        # # 4. Blog Performance Report Prompt Constructor
        "construct_blog_performance_report_prompt": {
            "node_id": "construct_blog_performance_report_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": BLOG_PERFORMANCE_REPORT_USER_PROMPT,
                        "variables": {
                            "blog_content_data": None,
                            "blog_portfolio_data": None
                        },
                        "construct_options": {
                            "blog_content_data": "blog_content_data",
                            "blog_portfolio_data": "blog_portfolio_data"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": BLOG_PERFORMANCE_REPORT_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },

        # # 5. Gap Analysis and Validation Prompt Constructor
        "construct_gap_analysis_validation_prompt": {
            "node_id": "construct_gap_analysis_validation_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": BLOG_GAP_ANALYSIS_VALIDATION_USER_PROMPT,
                        "variables": {
                            "blog_content_data": None,
                            "blog_portfolio_data": None,
                            "deep_research_data": None,
                            "competitor_data": None
                        },
                        "construct_options": {
                            "blog_content_data": "blog_content_data",
                            "blog_portfolio_data": "blog_portfolio_data",
                            "deep_research_data": "deep_research_data",
                            "competitor_data": "competitor_data"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": BLOG_GAP_ANALYSIS_VALIDATION_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },

        # # 6. Strategic Recommendations & Action Plan Prompt Constructor
        "construct_strategic_recommendations_prompt": {
            "node_id": "construct_strategic_recommendations_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": BLOG_STRATEGIC_RECOMMENDATIONS_USER_PROMPT,
                        "variables": {
                            "ai_visibility_report": None,
                            "competitive_intelligence_report": None,
                            "blog_performance_report": None,
                            "gap_analysis_validation": None,
                            "technical_seo_report": None
                        },
                        "construct_options": {
                            "ai_visibility_report": "ai_visibility_report",
                            "competitive_intelligence_report": "competitive_intelligence_report",
                            "blog_performance_report": "blog_performance_report",
                            "gap_analysis_validation": "gap_analysis_validation",
                            "technical_seo_report": "technical_seo_report"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": BLOG_STRATEGIC_RECOMMENDATIONS_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },

        "construct_blog_executive_summary_prompt": {
            "node_id": "construct_blog_executive_summary_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": BLOG_EXECUTIVE_SUMMARY_USER_PROMPT,
                        "variables": {
                            "ai_visibility_report": None,
                            "competitive_intelligence_report": None,
                            "blog_performance_report": None,
                            "gap_analysis_validation": None,
                            "technical_seo_report": None
                        },
                        "construct_options": {
                            "ai_visibility_report": "ai_visibility_report",
                            "competitive_intelligence_report": "competitive_intelligence_report",
                            "blog_performance_report": "blog_performance_report",
                            "gap_analysis_validation": "gap_analysis_validation",
                            "technical_seo_report": "technical_seo_report"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": BLOG_EXECUTIVE_SUMMARY_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },

        # # 1. AI Visibility Report
        "generate_ai_visibility_report": {
            "node_id": "generate_ai_visibility_report",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {"schema_definition": BLOG_AI_VISIBILITY_REPORT_SCHEMA, "convert_loaded_schema_to_pydantic": False}
            }
        },

        # # 2. Competitive Intelligence Report
        "generate_competitive_intelligence_report": {
            "node_id": "generate_competitive_intelligence_report",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {"schema_definition": BLOG_COMPETITIVE_INTELLIGENCE_REPORT_SCHEMA, "convert_loaded_schema_to_pydantic": False}
            }
        },



        # # 4. Blog Performance Report
        "generate_blog_performance_report": {
            "node_id": "generate_blog_performance_report",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {"schema_definition": BLOG_PERFORMANCE_REPORT_SCHEMA, "convert_loaded_schema_to_pydantic": False}
            }
        },

        # # 5. Gap Analysis and Validation Report
        "generate_gap_analysis_validation": {
            "node_id": "generate_gap_analysis_validation",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {"schema_definition": BLOG_GAP_ANALYSIS_VALIDATION_SCHEMA, "convert_loaded_schema_to_pydantic": False}
            }
        },

        # # 6. Strategic Recommendations & Action Plan Report (depends on other reports)
        "generate_strategic_recommendations": {
            "node_id": "generate_strategic_recommendations",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_FOR_STRATEGIC_RECOMMENDATIONS, "model": LLM_MODEL_FOR_STRATEGIC_RECOMMENDATIONS},
                    "temperature": LLM_TEMPERATURE_FOR_STRATEGIC_RECOMMENDATIONS,
                    "max_tokens": LLM_MAX_TOKENS_FOR_STRATEGIC_RECOMMENDATIONS,
                    "reasoning_effort_class": "high"
                },
                "output_schema": {"schema_definition": BLOG_STRATEGIC_RECOMMENDATIONS_SCHEMA, "convert_loaded_schema_to_pydantic": False}
            }
        },

        "generate_blog_executive_summary": {
            "node_id": "generate_blog_executive_summary",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_FOR_STRATEGIC_RECOMMENDATIONS, "model": LLM_MODEL_FOR_STRATEGIC_RECOMMENDATIONS},
                    "temperature": LLM_TEMPERATURE_FOR_STRATEGIC_RECOMMENDATIONS,
                    "max_tokens": LLM_MAX_TOKENS_FOR_STRATEGIC_RECOMMENDATIONS,
                    "reasoning_effort_class": "high"
                },
                "output_schema": {"schema_definition": BLOG_EXECUTIVE_SUMMARY_SCHEMA_PYDANTIC, "convert_loaded_schema_to_pydantic": False}
            }
        },

        # # Company Reports Aggregator
        "aggregate_company_reports": {
            "node_id": "aggregate_company_reports",
            "node_name": "transform_data",
            "enable_node_fan_in": True,
            "node_config": {
                "mappings": [
                    {
                        "source_path": "ai_visibility_report",
                        "destination_path": "company_reports.ai_visibility_overview"
                    },
                    {
                        "source_path": "blog_performance_report",
                        "destination_path": "company_reports.blog_performance_health"
                    },
                    {
                        "source_path": "technical_seo_report",
                        "destination_path": "company_reports.technical_seo_foundation"
                    },
                    {
                        "source_path": "competitive_intelligence_report",
                        "destination_path": "company_reports.competitive_intelligence"
                    },
                    {
                        "source_path": "gap_analysis_validation",
                        "destination_path": "company_reports.content_gap_analysis"
                    },
                    {
                        "source_path": "strategic_recommendations",
                        "destination_path": "company_reports.strategic_opportunities"
                    },
                    {
                        "source_path": "blog_executive_summary",
                        "destination_path": "company_reports.executive_summary"
                    }
                ]
            }
        },

        # --- Store Executive Reports ---
        "store_executive_diagnostic_report": {
            "node_id": "store_executive_diagnostic_report",
            "node_name": "store_customer_data",
            "node_config": {
                "global_is_shared": False,
                "global_is_system_entity": False,
                "store_configs": [
                    {
                        "input_field_path": "executive_reports.executive_reports",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "entity_username",
                                "static_docname": LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_DOCNAME
                            }
                        }
                    }
                ]
            }
        },

        # --- Store Company Reports ---
        "store_company_diagnostic_report": {
            "node_id": "store_company_diagnostic_report",
            "node_name": "store_customer_data",
            "node_config": {
                "global_is_shared": False,
                "global_is_system_entity": False,
                "store_configs": [
                    {
                        "input_field_path": "company_reports.company_reports",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME
                            }
                        }
                    }
                ]
            }
        },

        # --- 12. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "defer_node": True,
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

        {
            "src_node_id": "input_node",
            "dst_node_id": "linkedin_router",
            "mappings": [
                {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"}
            ]
        },

        {
            "src_node_id": "linkedin_router",
            "dst_node_id": "initial_router",
            "mappings": []
        },
        {
            "src_node_id": "linkedin_router",
            "dst_node_id": "run_linkedin_scraping",
            "mappings": []
                },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "run_linkedin_scraping",
            "mappings": [
                {"src_field": "linkedin_profile_url", "dst_field": "entity_url"},
                {"src_field": "entity_username", "dst_field": "entity_username"}
            ]
        },

        # Input -> Initial Router
        {
            "src_node_id": "run_linkedin_scraping",
            "dst_node_id": "initial_router",
            "mappings": [
            ]
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "initial_router",
            "mappings": [
                {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"},
                {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"}
            ]
        },

        # Initial Router -> Deep Research (sequential)
        {
            "src_node_id": "initial_router",
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
                {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"},
                {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"}
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

        # LinkedIn Scraping -> Executive AI Visibility (sequential)
        {
            "src_node_id": "initial_router",
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
            "src_node_id": "initial_router",
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

        # LinkedIn Scraping -> LinkedIn Analysis (sequential)
        {
            "src_node_id": "initial_router",
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

        {
            "src_node_id": "initial_router",
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
            "src_node_id": "run_competitor_content_analysis",
            "dst_node_id": "wait_for_core_workflows",
            "mappings": []
        },


        {
            "src_node_id": "$graph_state",
            "dst_node_id": "wait_for_core_workflows",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"}
            ]
        },




        # Wait for Core Workflows -> Load Document Router
        {
            "src_node_id": "wait_for_core_workflows",
            "dst_node_id": "load_document_router",
            "mappings": []
        },

        

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "load_document_router",
            "mappings": [
                {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"},
                {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"}
            ]
        },

    #     # --- Document Loading Edges ---
        
    #     # Router -> LinkedIn Documents
        {
            "src_node_id": "load_document_router",
            "dst_node_id": "load_linkedin_documents",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "load_linkedin_documents",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"}
            ]
        },
        
    #     # Router -> Company Documents
        {
            "src_node_id": "load_document_router",
            "dst_node_id": "load_company_documents",
            "mappings": []
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "load_company_documents",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"}
            ]
        },
        # Router -> Competitor Content Documents
        {
            "src_node_id": "load_document_router",
            "dst_node_id": "load_competitor_content_docs",
            "mappings": []
        },
        # Router -> Competitor Content Documents input mapping
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "load_competitor_content_docs",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"}
            ]
        },
        
    #     # Store loaded documents in state
        {
            "src_node_id": "load_linkedin_documents",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "linkedin_content_doc", "dst_field": "linkedin_content_doc"},
                {"src_field": "linkedin_ai_visibility_doc", "dst_field": "linkedin_ai_visibility_doc"},
                {"src_field": "linkedin_scraped_profile_doc", "dst_field": "linkedin_scraped_profile_doc"},
                {"src_field": "linkedin_deep_research_doc", "dst_field": "linkedin_deep_research_doc"},
                {"src_field": "linkedin_user_profile_doc", "dst_field": "linkedin_user_profile_doc"}
            ]
        },
        {
            "src_node_id": "load_company_documents",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "blog_content_analysis_doc", "dst_field": "blog_content_analysis_doc"},
                {"src_field": "blog_portfolio_analysis_doc", "dst_field": "blog_portfolio_analysis_doc"},
                {"src_field": "blog_ai_visibility_doc", "dst_field": "blog_ai_visibility_doc"},
                {"src_field": "company_ai_visibility_doc", "dst_field": "company_ai_visibility_doc"},
                {"src_field": "technical_seo_doc", "dst_field": "technical_seo_doc"},
                {"src_field": "deep_research_doc", "dst_field": "deep_research_doc"},
                {"src_field": "company_context_doc", "dst_field": "company_context_doc"}            ]
        },
        {
            "src_node_id": "load_competitor_content_docs",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "competitor_content_docs", "dst_field": "competitor_content_docs"}
            ]
        },
    #     # All document loads -> Wait for Documents
        {
            "src_node_id": "load_linkedin_documents",
            "dst_node_id": "wait_for_documents",
            "mappings": []
        },
        {
            "src_node_id": "load_company_documents",
            "dst_node_id": "wait_for_documents",
            "mappings": []
        },
        {
            "src_node_id": "load_competitor_content_docs",
            "dst_node_id": "wait_for_documents",
            "mappings": []
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "wait_for_documents",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"}            ]
        },
    #     # Wait for Documents -> Report Generation Router
        {
            "src_node_id": "wait_for_documents",
            "dst_node_id": "report_generation_router",
            "mappings": []
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "report_generation_router",
            "mappings": [
                {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"},
                {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"}
            ]
        },

    #     # --- EXECUTIVE REPORTS ROUTING ---
        
    #     # Report Router -> Executive Reports Router (conditional)
        {
            "src_node_id": "report_generation_router",
            "dst_node_id": "generate_executive_reports_router",
            "mappings": []
        },
        # Pass run_linkedin_exec flag to executive reports router
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "generate_executive_reports_router",
            "mappings": [
                {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"}
            ]
        },
        
        # 1. LinkedIn Competitive Intelligence
        {
            "src_node_id": "generate_executive_reports_router",
            "dst_node_id": "construct_linkedin_competitive_intelligence_prompt",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_linkedin_competitive_intelligence_prompt",
            "mappings": [
                {"src_field": "linkedin_user_profile_doc", "dst_field": "linkedin_user_profile_data"},
                {"src_field": "linkedin_deep_research_doc", "dst_field": "linkedin_deep_research_data"}
            ]
        },
        {
            "src_node_id": "construct_linkedin_competitive_intelligence_prompt",
            "dst_node_id": "generate_linkedin_competitive_intelligence",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },
        {
            "src_node_id": "generate_linkedin_competitive_intelligence",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "linkedin_competitive_intelligence"}
            ]
        },
        
        # 2. Content Performance Analysis
        {
            "src_node_id": "generate_executive_reports_router",
            "dst_node_id": "construct_content_performance_analysis_prompt",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_content_performance_analysis_prompt",
            "mappings": [
                {"src_field": "linkedin_content_doc", "dst_field": "linkedin_content_analysis_data"},
                {"src_field": "linkedin_user_profile_doc", "dst_field": "linkedin_user_profile_data"}
            ]
        },
        {
            "src_node_id": "construct_content_performance_analysis_prompt",
            "dst_node_id": "generate_content_performance_analysis",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        {
            "src_node_id": "generate_content_performance_analysis",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "content_performance_analysis"}
            ]
        },
        
        # 3. Content Strategy Gaps
        {
            "src_node_id": "generate_executive_reports_router",
            "dst_node_id": "construct_content_strategy_gaps_prompt",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_content_strategy_gaps_prompt",
            "mappings": [
                {"src_field": "deep_research_doc", "dst_field": "deep_research_data"},
                {"src_field": "linkedin_user_profile_doc", "dst_field": "linkedin_user_profile_data"},
                {"src_field": "linkedin_content_doc", "dst_field": "linkedin_content_analysis_data"}
            ]
        },
        {
            "src_node_id": "construct_content_strategy_gaps_prompt",
            "dst_node_id": "generate_content_strategy_gaps",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },

        # Content Strategy Gaps Report
        {
            "src_node_id": "generate_content_strategy_gaps",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "content_strategy_gaps"}
            ]
        },

        # 4. Strategic LinkedIn Recommendations (depends on other LinkedIn reports)
        {
            "src_node_id": "generate_linkedin_competitive_intelligence",
            "dst_node_id": "construct_strategic_linkedin_recommendations_prompt",
            "mappings": []
        },
        {
            "src_node_id": "generate_content_performance_analysis",
            "dst_node_id": "construct_strategic_linkedin_recommendations_prompt",
            "mappings": []
        },
        {
            "src_node_id": "generate_content_strategy_gaps",
            "dst_node_id": "construct_strategic_linkedin_recommendations_prompt",
            "mappings": []
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_strategic_linkedin_recommendations_prompt",
            "mappings": [
                {"src_field": "linkedin_ai_visibility_doc", "dst_field": "linkedin_visibility_assessment"},
                {"src_field": "linkedin_competitive_intelligence", "dst_field": "linkedin_competitive_intelligence"},
                {"src_field": "content_performance_analysis", "dst_field": "content_performance_analysis"},
                {"src_field": "content_strategy_gaps", "dst_field": "content_strategy_gaps"},
                {"src_field": "linkedin_user_profile_doc", "dst_field": "linkedin_user_profile_doc"}
            ]
        },
        
        # Strategic LinkedIn Recommendations Constructor -> LLM
        {
            "src_node_id": "construct_strategic_linkedin_recommendations_prompt",
            "dst_node_id": "generate_strategic_linkedin_recommendations",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Store Strategic LinkedIn Recommendations in state
        {
            "src_node_id": "generate_strategic_linkedin_recommendations",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "strategic_linkedin_recommendations"}
            ]
        },

        # LinkedIn Executive Summary: dependencies -> constructor
        {
            "src_node_id": "generate_content_performance_analysis",
            "dst_node_id": "construct_linkedin_executive_summary_prompt",
            "mappings": []
        },
        {
            "src_node_id": "generate_content_strategy_gaps",
            "dst_node_id": "construct_linkedin_executive_summary_prompt",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_linkedin_executive_summary_prompt",
            "mappings": [
                {"src_field": "linkedin_ai_visibility_doc", "dst_field": "linkedin_visibility_assessment"},
                {"src_field": "linkedin_competitive_intelligence", "dst_field": "linkedin_competitive_intelligence"},
                {"src_field": "content_performance_analysis", "dst_field": "content_performance_analysis"},
                {"src_field": "content_strategy_gaps", "dst_field": "content_strategy_gaps"},
                {"src_field": "linkedin_user_profile_doc", "dst_field": "linkedin_user_profile_doc"}
            ]
        },
        # LinkedIn Executive Summary: constructor -> LLM
        {
            "src_node_id": "construct_linkedin_executive_summary_prompt",
            "dst_node_id": "generate_linkedin_executive_summary",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },
        # LinkedIn Executive Summary: store in state
        {
            "src_node_id": "generate_linkedin_executive_summary",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "linkedin_executive_summary"}
            ]
        },

    #     # All Executive reports -> Aggregator
        {
            "src_node_id": "generate_strategic_linkedin_recommendations",
            "dst_node_id": "aggregate_executive_reports",
            "mappings": []
        },
        {
            "src_node_id": "generate_linkedin_executive_summary",
            "dst_node_id": "aggregate_executive_reports",
            "mappings": []
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "aggregate_executive_reports",
            "mappings": [
                {"src_field": "linkedin_ai_visibility_doc", "dst_field": "linkedin_user_ai_visibility_doc"},
                {"src_field": "linkedin_competitive_intelligence", "dst_field": "linkedin_competitive_intelligence"},
                {"src_field": "content_performance_analysis", "dst_field": "content_performance_analysis"},
                {"src_field": "content_strategy_gaps", "dst_field": "content_strategy_gaps"},
                {"src_field": "strategic_linkedin_recommendations", "dst_field": "strategic_linkedin_recommendations"},
                {"src_field": "linkedin_executive_summary", "dst_field": "linkedin_executive_summary"}
            ]
        },
        {
            "src_node_id": "aggregate_executive_reports",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "executive_reports"}
            ]
        },

    #     # --- COMPANY REPORTS ROUTING ---
        
    #     # Report Router -> Company Reports Router (conditional)
        {
            "src_node_id": "report_generation_router",
            "dst_node_id": "generate_company_reports_router",
            "mappings": []
        },
        # Pass run_blog_analysis flag to company reports router
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "generate_company_reports_router",
            "mappings": [
                {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"}
            ]
        },
        
    #     # Company Reports Router -> Individual Report Constructors
        # 1. AI Visibility Report
        {
            "src_node_id": "generate_company_reports_router",
            "dst_node_id": "construct_ai_visibility_report_prompt",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_ai_visibility_report_prompt",
            "mappings": [
                {"src_field": "company_context_doc", "dst_field": "company_context_doc"},
                {"src_field": "company_ai_visibility_doc", "dst_field": "company_ai_visibility_data"},
                {"src_field": "blog_ai_visibility_doc", "dst_field": "blog_ai_visibility_data"}
            ]
        },
        {
            "src_node_id": "construct_ai_visibility_report_prompt",
            "dst_node_id": "generate_ai_visibility_report",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # 2. Competitive Intelligence Report
        {
            "src_node_id": "generate_company_reports_router",
            "dst_node_id": "construct_competitive_intelligence_report_prompt",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_competitive_intelligence_report_prompt",
            "mappings": [
                {"src_field": "competitor_content_docs", "dst_field": "competitor_data"},
                {"src_field": "deep_research_doc", "dst_field": "deep_research_data"},
                {"src_field": "company_context_doc", "dst_field": "company_context_doc"}
            ]
        },
        {
            "src_node_id": "construct_competitive_intelligence_report_prompt",
            "dst_node_id": "generate_competitive_intelligence_report",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },

        
        # 4. Blog Performance Report
        {
            "src_node_id": "generate_company_reports_router",
            "dst_node_id": "construct_blog_performance_report_prompt",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_blog_performance_report_prompt",
            "mappings": [
                {"src_field": "blog_content_analysis_doc", "dst_field": "blog_content_data"},
                {"src_field": "blog_portfolio_analysis_doc", "dst_field": "blog_portfolio_data"}
            ]
        },
        {
            "src_node_id": "construct_blog_performance_report_prompt",
            "dst_node_id": "generate_blog_performance_report",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # 5. Gap Analysis and Validation Report
        {
            "src_node_id": "generate_company_reports_router",
            "dst_node_id": "construct_gap_analysis_validation_prompt",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_gap_analysis_validation_prompt",
            "mappings": [
                {"src_field": "blog_content_analysis_doc", "dst_field": "blog_content_data"},
                {"src_field": "blog_portfolio_analysis_doc", "dst_field": "blog_portfolio_data"},
                {"src_field": "deep_research_doc", "dst_field": "deep_research_data"},
                {"src_field": "competitor_content_docs", "dst_field": "competitor_data"}
            ]
        },
        {
            "src_node_id": "construct_gap_analysis_validation_prompt",
            "dst_node_id": "generate_gap_analysis_validation",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # 6. Strategic Recommendations & Action Plan Report (depends on other reports)
        {
            "src_node_id": "generate_ai_visibility_report",
            "dst_node_id": "construct_strategic_recommendations_prompt",
            "mappings": []
        },
        {
            "src_node_id": "generate_competitive_intelligence_report",
            "dst_node_id": "construct_strategic_recommendations_prompt",
            "mappings": []
        },
        {
            "src_node_id": "generate_blog_performance_report",
            "dst_node_id": "construct_strategic_recommendations_prompt",
            "mappings": []
        },
        {
            "src_node_id": "generate_gap_analysis_validation",
            "dst_node_id": "construct_strategic_recommendations_prompt",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_strategic_recommendations_prompt",
            "mappings": [
                {"src_field": "ai_visibility_report", "dst_field": "ai_visibility_report"},
                {"src_field": "competitive_intelligence_report", "dst_field": "competitive_intelligence_report"},
                {"src_field": "blog_performance_report", "dst_field": "blog_performance_report"},
                {"src_field": "gap_analysis_validation", "dst_field": "gap_analysis_validation"},
                {"src_field": "technical_seo_doc", "dst_field": "technical_seo_report"}
            ]
        },
        {
            "src_node_id": "construct_strategic_recommendations_prompt",
            "dst_node_id": "generate_strategic_recommendations",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },

    #     # Store company report outputs in state
        {
            "src_node_id": "generate_ai_visibility_report",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "ai_visibility_report"}
            ]
        },
        {
            "src_node_id": "generate_competitive_intelligence_report",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "competitive_intelligence_report"}
            ]
        },

        {
            "src_node_id": "generate_blog_performance_report",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "blog_performance_report"}
            ]
        },
        {
            "src_node_id": "generate_gap_analysis_validation",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "gap_analysis_validation"}
            ]
        },
        {
            "src_node_id": "generate_strategic_recommendations",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "strategic_recommendations"}
            ]
        },
        # {
        #     "src_node_id": "generate_strategic_opportunities",
        #     "dst_node_id": "$graph_state",
        #     "mappings": [
        #         {"src_field": "structured_output", "dst_field": "strategic_opportunities"}
        #     ]
        # },

        # Blog Executive Summary: dependencies -> constructor
        {
            "src_node_id": "generate_gap_analysis_validation",
            "dst_node_id": "construct_blog_executive_summary_prompt",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_blog_executive_summary_prompt",
            "mappings": [
                {"src_field": "ai_visibility_report", "dst_field": "ai_visibility_report"},
                {"src_field": "competitive_intelligence_report", "dst_field": "competitive_intelligence_report"},
                {"src_field": "blog_performance_report", "dst_field": "blog_performance_report"},
                {"src_field": "gap_analysis_validation", "dst_field": "gap_analysis_validation"},
                {"src_field": "technical_seo_doc", "dst_field": "technical_seo_report"}
            ]
        },
        # Blog Executive Summary: constructor -> LLM
        {
            "src_node_id": "construct_blog_executive_summary_prompt",
            "dst_node_id": "generate_blog_executive_summary",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },
        # Blog Executive Summary: store in state
        {
            "src_node_id": "generate_blog_executive_summary",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "blog_executive_summary"}
            ]
        },

    #     # All company reports -> Company Action Plan
        # Wait for all company reports to complete before constructing action plan
        {
            "src_node_id": "generate_ai_visibility_report",
            "dst_node_id": "aggregate_company_reports",
            "mappings": []
        },
        {
            "src_node_id": "generate_competitive_intelligence_report",
            "dst_node_id": "aggregate_company_reports",
            "mappings": []
        },
        {
            "src_node_id": "generate_blog_performance_report",
            "dst_node_id": "aggregate_company_reports",
            "mappings": []
        },
        {
            "src_node_id": "generate_gap_analysis_validation",
            "dst_node_id": "aggregate_company_reports",
            "mappings": []
        },
        {
            "src_node_id": "generate_strategic_recommendations",
            "dst_node_id": "aggregate_company_reports",
            "mappings": []
        },
        {
            "src_node_id": "generate_blog_executive_summary",
            "dst_node_id": "aggregate_company_reports",
            "mappings": []
        },

    #     # All Company reports -> Aggregator

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "aggregate_company_reports",
            "mappings": [
                {"src_field": "ai_visibility_report", "dst_field": "ai_visibility_report"},
                {"src_field": "competitive_intelligence_report", "dst_field": "competitive_intelligence_report"},
                {"src_field": "technical_seo_doc", "dst_field": "technical_seo_report"},
                {"src_field": "blog_performance_report", "dst_field": "blog_performance_report"},
                {"src_field": "gap_analysis_validation", "dst_field": "gap_analysis_validation"},
                {"src_field": "strategic_recommendations", "dst_field": "strategic_recommendations"},
                {"src_field": "blog_executive_summary", "dst_field": "blog_executive_summary"}
            ]
        },
        {
            "src_node_id": "aggregate_company_reports",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "company_reports"}
            ]
        },

        # --- Store Executive Reports (conditional) ---
        {
            "src_node_id": "aggregate_executive_reports",
            "dst_node_id": "store_executive_diagnostic_report",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "store_executive_diagnostic_report",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "executive_reports", "dst_field": "executive_reports"}
            ]
        },

        # --- Store Company Reports (conditional) ---
        {
            "src_node_id": "aggregate_company_reports",
            "dst_node_id": "store_company_diagnostic_report",
            "mappings": []
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "store_company_diagnostic_report",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "company_reports", "dst_field": "company_reports"}
            ]
        },

        # --- Final Output ---
        {
            "src_node_id": "store_executive_diagnostic_report",
            "dst_node_id": "output_node",
            "mappings": []
        },
        {
            "src_node_id": "store_company_diagnostic_report",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "passthrough_data", "dst_field": "passthrough_data"}
            ]
        }
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
                "blog_start_urls": "replace",
                "deep_research_result": "replace",
                "blog_analysis_result": "replace",
                "executive_ai_visibility_result": "replace",
                "company_ai_visibility_result": "replace",
                "linkedin_scraping_result": "replace",
                "linkedin_analysis_result": "replace",
                "company_result": "replace",
                "linkedin_content_doc": "replace",
                "blog_content_analysis_doc": "replace",
                "linkedin_ai_visibility_doc": "replace",
                "company_ai_visibility_doc": "replace",
                 "deep_research_doc": "replace",
                 "competitor_content_analysis_result": "replace",
                "competitor_content_docs": "replace",
                "executive_reports": "replace",
                "company_reports": "replace",
                "business_impact_projection": "replace",
                "linkedin_competitive_intelligence": "replace",
                "content_performance_analysis": "replace",
                "content_strategy_gaps": "replace",
                "strategic_linkedin_recommendations": "replace",
                "linkedin_executive_summary": "replace",
                "ai_visibility_report": "replace",
                "competitive_intelligence_report": "replace",
                "blog_performance_report": "replace",
                "gap_analysis_validation": "replace",
                "strategic_recommendations": "replace",
                "blog_executive_summary": "replace",
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
                "company_context_doc": "replace",
                "competitor_content_docs": "replace"
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
        "entity_username": "hungweiwu",  # LinkedIn username
        "company_name": "momentic",  # Company name for analysis
        "run_linkedin_exec": True,  # Execute LinkedIn workflows
        "run_blog_analysis": True,  # Skip company workflows for now
        "linkedin_profile_url": "https://www.linkedin.com/in/hungweiwu/",  # LinkedIn URL
        "company_url": "https://momentic.ai",  # Company website URL (optional)
        "blog_start_urls": ["https://momentic.ai"] # Example blog start URL
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
        tag="orchestrator_workflow_test",
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