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
    BLOG_COMPANY_ANALYSIS_DOCNAME,
    BLOG_COMPANY_ANALYSIS_NAMESPACE_TEMPLATE,
    # Final diagnostic reports
    LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
    LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
)

from kiwi_client.workflows.active.content_diagnostics.orchestrator_workflow_sandbox.wf_llm_inputs import (
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
    # No-Blog Content Scenario Prompts
    BLOG_STRATEGIC_RECOMMENDATIONS_NO_BLOG_USER_PROMPT,
    BLOG_STRATEGIC_RECOMMENDATIONS_NO_BLOG_SYSTEM_PROMPT,
    BLOG_EXECUTIVE_SUMMARY_NO_BLOG_USER_PROMPT,
    BLOG_EXECUTIVE_SUMMARY_NO_BLOG_SYSTEM_PROMPT,
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
NO_BLOG_POST_COMPANY_AI_VISIBILITY_WORKFLOW_NAME = "company_ai_visibility_edge_case_workflow"
COMPANY_ANALYSIS_WORKFLOW_NAME = "blog_company_analysis_workflow"
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
LLM_MAX_TOKENS = 8000

CACHE_ENABLED = True

# --- Workflow Graph Definition ---
workflow_graph_schema = {
    "nodes": {
        # --- 1. Input Node ---
        "input_node": {
            "node_id": "input_node",
            "node_category": "system",
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
                    },
                    "allowed_domains": {
                        "type": "list",
                        "items_type": "str",
                        "required": False,
                        "description": "Optional list of allowed domains; derived from start_urls if omitted"
                    },
                    "max_urls_per_domain": {
                        "type": "int",
                        "required": False,
                        "default": 250,
                        "description": "Maximum URLs to discover per domain"
                    },
                    "max_processed_urls_per_domain": {
                        "type": "int",
                        "required": False,
                        "default": 200,
                        "description": "Maximum URLs to actually scrape per domain"
                    },
                    "max_crawl_depth": {
                        "type": "int",
                        "required": False,
                        "default": 3,
                        "description": "How deep to follow links from start URLs"
                    },
                    "use_cached_scraping_results": {
                        "type": "bool",
                        "required": False,
                        "default": True,
                        "description": "Whether to use cached results if available"
                    },
                    "cache_lookback_period_days": {
                        "type": "int",
                        "required": False,
                        "default": 7,
                        "description": "How many days back to look for cached results"
                    },
                    "is_shared": {
                        "type": "bool",
                        "required": False,
                        "default": False,
                        "description": "Store data as organization-shared (vs user-specific)"
                    },
                    "include_only_paths": {
                        "type": "list",
                        "items_type": "str",
                        "required": False,
                        "description": "Optional list of paths to include in the analysis"
                    },
                    "exclude_paths": {
                        "type": "list",
                        "items_type": "str",
                        "required": False,
                        "description": "Optional list of paths to exclude from the analysis"
                    }
                }
            }
        },
        
        # --- 2. Data Collection Router ---
        "data_collection_router": {
            "node_id": "data_collection_router",
            "node_category": "system",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "run_linkedin_scraping",
                    "run_blog_crawler",
                ],
                "allow_multiple": True,
                "default_choice": None,
                "choices_with_conditions": [
                    {"choice_id": "run_linkedin_scraping", "input_path": "run_linkedin_exec", "target_value": True},
                    {"choice_id": "run_blog_crawler", "input_path": "run_blog_analysis", "target_value": True},
                ]
            }
        },

        # --- 3a. Run LinkedIn Scraping Workflow ---
        "run_linkedin_scraping": {
            "node_id": "run_linkedin_scraping",
            "node_category": "system",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": LINKEDIN_SCRAPING_WORKFLOW_NAME,
                "timeout_seconds": SCRAPING_TIMEOUT,
                "enable_workflow_cache": CACHE_ENABLED
                }
        },

        # --- 3b. Blog Crawler Node ---
        "run_blog_crawler": {
            "node_id": "run_blog_crawler",
            "node_category": "scraping",
            "node_name": "crawler_scraper",
            "node_config": {
                # Using defaults; blog classification is enabled by default
            }
        },

        # --- 4. Initial Router - Routes to appropriate workflow groups ---
        "initial_router": {
            "node_id": "initial_router",
            "node_category": "system",
            "node_name": "router_node",
            "defer_node": True,
            "node_config": {
                "choices": [
                    "run_blog_content_analysis",
                    "run_deep_research",
                    "run_executive_ai_visibility",
                    "run_company_ai_visibility",
                    "run_no_blog_post_company_ai_visibility",
                    "run_company_analysis",
                    "run_competitor_content_analysis",
                    "run_linkedin_analysis"
                ],
                "allow_multiple": True,
                "default_choice": None,
                "choices_with_conditions": [
                    # Simple routing conditions - complex logic will need if_else_condition nodes
                    {"choice_id": "run_blog_content_analysis", "input_path": "has_insufficient_blog_and_page_count", "target_value": False},
                    {"choice_id": "run_company_ai_visibility", "input_path": "has_insufficient_blog_and_page_count", "target_value": False},
                    {"choice_id": "run_no_blog_post_company_ai_visibility", "input_path": "has_insufficient_blog_and_page_count", "target_value": True},
                    
                    # Run Company Analysis when blog analysis is enabled BUT has insufficient content
                    {
                        "choice_id": "run_company_analysis", "input_path": "run_blog_analysis", "target_value": True
                    },
                    
                    # Run Competitor Content Analysis only when blog analysis is enabled AND has sufficient content
                    {
                        "choice_id": "run_competitor_content_analysis", "input_path": "run_blog_analysis", "target_value": True
                    },

                    # Conditionally route to LinkedIn workflows
                    {"choice_id": "run_deep_research", "input_path": "run_linkedin_exec", "target_value": True},

                    {"choice_id": "run_deep_research", "input_path": "run_linkedin_exec", "target_value": False},

                    # Conditionally run Executive AI Visibility when LinkedIn exec is enabled
                    {"choice_id": "run_executive_ai_visibility", "input_path": "run_linkedin_exec", "target_value": True},

                    {"choice_id": "run_linkedin_analysis", "input_path": "run_linkedin_exec", "target_value": True}
                ]
            }
        },

        # --- 5. Deep Research Workflow ---
        "run_deep_research": {
            "node_id": "run_deep_research",
            "node_category": "system",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": DEEP_RESEARCH_WORKFLOW_NAME,
                "timeout_seconds": DEEP_RESEARCH_TIMEOUT,
                "enable_workflow_cache": CACHE_ENABLED
            }
        },

        # --- 6. Blog Content Analysis Workflow ---
        "run_blog_content_analysis": {
            "node_id": "run_blog_content_analysis",
            "node_category": "system",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": BLOG_CONTENT_ANALYSIS_WORKFLOW_NAME,
                "timeout_seconds": BLOG_ANALYSIS_TIMEOUT,
                "enable_workflow_cache": CACHE_ENABLED
            }
        },

        # --- 7. Executive AI Visibility Workflow ---
        "run_executive_ai_visibility": {
            "node_id": "run_executive_ai_visibility",
            "node_category": "system",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": EXECUTIVE_AI_VISIBILITY_WORKFLOW_NAME,
                "timeout_seconds": AI_VISIBILITY_TIMEOUT,
                "check_error_free_logs": False,
                "enable_workflow_cache": CACHE_ENABLED
            }
        },

        # --- 8. Company AI Visibility Workflow ---
        "run_company_ai_visibility": {
            "node_id": "run_company_ai_visibility",
            "node_category": "system",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": COMPANY_AI_VISIBILITY_WORKFLOW_NAME,
                "timeout_seconds": AI_VISIBILITY_TIMEOUT,
                "check_error_free_logs": False,
                "enable_workflow_cache": CACHE_ENABLED
            }
        },

        # --- 9. No Blog Post Company AI Visibility Workflow ---
        "run_no_blog_post_company_ai_visibility": {
            "node_id": "run_no_blog_post_company_ai_visibility",
            "node_category": "system",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": NO_BLOG_POST_COMPANY_AI_VISIBILITY_WORKFLOW_NAME,
                "timeout_seconds": AI_VISIBILITY_TIMEOUT,
                "check_error_free_logs": False,
                "enable_workflow_cache": CACHE_ENABLED
            }
        },

        # --- 10. Company Analysis Workflow ---
        "run_company_analysis": {
            "node_id": "run_company_analysis",
            "node_category": "system",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": COMPANY_ANALYSIS_WORKFLOW_NAME,
                "timeout_seconds": ANALYSIS_TIMEOUT,
                # "check_error_free_logs": False,
                "enable_workflow_cache": CACHE_ENABLED
            }
        },

        # --- 11. Run LinkedIn Content Analysis Workflow ---
        "run_linkedin_analysis": {
            "node_id": "run_linkedin_analysis",
            "node_category": "system",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": LINKEDIN_ANALYSIS_WORKFLOW_NAME,
                "timeout_seconds": ANALYSIS_TIMEOUT,
                "enable_workflow_cache": CACHE_ENABLED
                }
        },

        # --- 12. Run Competitor Content Analysis Workflow ---
        "run_competitor_content_analysis": {
            "node_id": "run_competitor_content_analysis",
            "node_category": "system",
            "node_name": "workflow_runner",
            "node_config": {
                "workflow_name": BLOG_COMPETITOR_CONTENT_ANALYSIS_WORKFLOW_NAME,
                "timeout_seconds": BLOG_ANALYSIS_TIMEOUT,
                "enable_workflow_cache": CACHE_ENABLED
                }
        },

        # --- 13. Wait for Core Workflows - Synchronization point ---
        "wait_for_core_workflows": {
            "node_id": "wait_for_core_workflows",
            "node_category": "system",
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

        # --- 14. Load Document Router - Routes to document loading nodes ---
        "load_document_router": {
            "node_id": "load_document_router",
            "node_category": "system",
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

        # --- 15. Load LinkedIn-related documents ---
        "load_linkedin_documents": {
            "node_id": "load_linkedin_documents",
            "node_category": "system",
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

        # --- 16. Load Company/Blog-related documents ---
        "load_company_documents": {
            "node_id": "load_company_documents",
            "node_category": "system",
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
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_COMPANY_ANALYSIS_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_COMPANY_ANALYSIS_DOCNAME
                        },
                        "output_field_name": "company_analysis_doc"
                    }
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
            },
        },

        # --- 17. Load Multiple Competitor Content Analysis documents (list) ---
        "load_competitor_content_docs": {
            "node_id": "load_competitor_content_docs",
            "node_category": "system",
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

        # --- 18. Wait for All Documents ---
        "wait_for_documents": {
            "node_id": "wait_for_documents",
            "node_category": "system",
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

        # --- 19. Report Generation Router ---
        "report_generation_router": {
            "node_id": "report_generation_router",
            "node_category": "system",
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

        # --- 20. Executive Reports Router ---
        "generate_executive_reports_router": {
            "node_id": "generate_executive_reports_router",
            "node_category": "system",
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

        # --- 21. Company Reports Router ---
        "generate_company_reports_router": {
            "node_id": "generate_company_reports_router",
            "node_category": "system",
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
                    {"choice_id": "construct_blog_performance_report_prompt", "input_path": "has_insufficient_blog_and_page_count", "target_value": False},
                    {"choice_id": "construct_gap_analysis_validation_prompt", "input_path": "has_insufficient_blog_and_page_count", "target_value": False}
                ]
            }
        },

        # --- EXECUTIVE REPORT GENERATION NODES ---
        
        # --- 22. LinkedIn Competitive Intelligence Prompt Constructor ---
        "construct_linkedin_competitive_intelligence_prompt": {
            "node_id": "construct_linkedin_competitive_intelligence_prompt",
            "node_category": "analysis",
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

        # --- 23. LinkedIn Competitive Intelligence Report ---
        "generate_linkedin_competitive_intelligence": {
            "node_id": "generate_linkedin_competitive_intelligence",
            "node_category": "analysis",
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
 
        # --- 24. Content Performance Analysis Prompt Constructor ---
        "construct_content_performance_analysis_prompt": {
            "node_id": "construct_content_performance_analysis_prompt",
            "node_category": "analysis",
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

        # --- 25. Content Performance Analysis Report ---
        "generate_content_performance_analysis": {
            "node_id": "generate_content_performance_analysis",
            "node_category": "analysis",
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
 
        # --- 26. Content Strategy Gaps Prompt Constructor ---
        "construct_content_strategy_gaps_prompt": {
            "node_id": "construct_content_strategy_gaps_prompt",
            "node_category": "analysis",
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

        # --- 27. Content Strategy Gaps Report ---
        "generate_content_strategy_gaps": {
            "node_id": "generate_content_strategy_gaps",
            "node_category": "analysis",
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
 
        # --- 28. Strategic LinkedIn Recommendations Prompt Constructor ---
        "construct_strategic_linkedin_recommendations_prompt": {
            "node_id": "construct_strategic_linkedin_recommendations_prompt",
            "node_category": "analysis",
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

        # --- 29. Strategic LinkedIn Recommendations Report ---
        "generate_strategic_linkedin_recommendations": {
            "node_id": "generate_strategic_linkedin_recommendations",
            "node_category": "analysis",
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

        # --- 30. LinkedIn Executive Summary Prompt Constructor ---
        "construct_linkedin_executive_summary_prompt": {
            "node_id": "construct_linkedin_executive_summary_prompt",
            "node_category": "analysis",
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

        # --- 31. LinkedIn Executive Summary Report ---
        "generate_linkedin_executive_summary": {
            "node_id": "generate_linkedin_executive_summary",
            "node_category": "analysis",
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

        # --- 32. Executive Reports Aggregator ---
        "aggregate_executive_reports": {
            "node_id": "aggregate_executive_reports",
            "node_category": "system",
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

        # --- COMPANY REPORT GENERATION NODES ---
        
        # --- 33. AI Visibility Report Prompt Constructor ---
        "construct_ai_visibility_report_prompt": {
            "node_id": "construct_ai_visibility_report_prompt",
            "node_category": "analysis",
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

        # --- 34. AI Visibility Report ---
        "generate_ai_visibility_report": {
            "node_id": "generate_ai_visibility_report",
            "node_category": "analysis",
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

        # --- 35. Competitive Intelligence Report Prompt Constructor ---
        "construct_competitive_intelligence_report_prompt": {
            "node_id": "construct_competitive_intelligence_report_prompt",
            "node_category": "analysis",
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

        # --- 36. Competitive Intelligence Report ---
        "generate_competitive_intelligence_report": {
            "node_id": "generate_competitive_intelligence_report",
            "node_category": "analysis",
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

        # --- 37. Blog Performance Report Prompt Constructor ---
        "construct_blog_performance_report_prompt": {
            "node_id": "construct_blog_performance_report_prompt",
            "node_category": "analysis",
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

        # --- 38. Blog Performance Report ---
        "generate_blog_performance_report": {
            "node_id": "generate_blog_performance_report",
            "node_category": "analysis",
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

        # --- 39. Gap Analysis and Validation Prompt Constructor ---
        "construct_gap_analysis_validation_prompt": {
            "node_id": "construct_gap_analysis_validation_prompt",
            "node_category": "analysis",
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

        # --- 40. Gap Analysis and Validation Report ---
        "generate_gap_analysis_validation": {
            "node_id": "generate_gap_analysis_validation",
            "node_category": "analysis",
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

        # --- 41. Wait for Company Reports ---
        "wait_for_company_reports": {
            "node_id": "wait_for_company_reports",
            "node_category": "system",
            "node_name": "transform_data",
            "defer_node": True,
            "node_config": {
                "mappings": [
                    {
                        "source_path": "company_name",
                        "destination_path": "company_name"
                    }
                ]
            }
        },

        # --- 42. Blog Content Availability Router ---
        "blog_content_availability_router": {
            "node_id": "blog_content_availability_router",
            "node_category": "system",
            "node_name": "router_node",
            # "defer_node": True,
            "node_config": {
                "choices": [
                    "construct_blog_executive_summary_prompt",
                    "construct_strategic_recommendations_prompt", 
                    "construct_blog_executive_summary_no_blog_prompt",
                    "construct_strategic_recommendations_no_blog_prompt"
                ],
                "allow_multiple": True,
                "default_choice": None,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_blog_executive_summary_prompt",
                        "input_path": "has_insufficient_blog_and_page_count",
                        "target_value": False
                    },
                    {
                        "choice_id": "construct_strategic_recommendations_prompt", 
                        "input_path": "has_insufficient_blog_and_page_count",
                        "target_value": False
                    },
                    {
                        "choice_id": "construct_blog_executive_summary_no_blog_prompt",
                        "input_path": "has_insufficient_blog_and_page_count",
                        "target_value": True
                    },
                    {
                        "choice_id": "construct_strategic_recommendations_no_blog_prompt",
                        "input_path": "has_insufficient_blog_and_page_count",
                        "target_value": True
                    }
                ]
            }
        },

        # --- 43. Strategic Recommendations Prompt Constructor ---
        "construct_strategic_recommendations_prompt": {
            "node_id": "construct_strategic_recommendations_prompt",
            "node_category": "analysis",
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
                            "technical_seo_report": None,
                            "company_analysis_doc": None
                        },
                        "construct_options": {
                            "ai_visibility_report": "ai_visibility_report",
                            "competitive_intelligence_report": "competitive_intelligence_report",
                            "blog_performance_report": "blog_performance_report",
                            "gap_analysis_validation": "gap_analysis_validation",
                            "technical_seo_report": "technical_seo_report",
                            "company_analysis_doc": "company_analysis_doc"
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

        # --- 44. Blog Executive Summary Prompt Constructor ---
        "construct_blog_executive_summary_prompt": {
            "node_id": "construct_blog_executive_summary_prompt",
            "node_category": "analysis",
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
                            "technical_seo_report": None,
                            "company_analysis_doc": None
                        },
                        "construct_options": {
                            "ai_visibility_report": "ai_visibility_report",
                            "competitive_intelligence_report": "competitive_intelligence_report",
                            "blog_performance_report": "blog_performance_report",
                            "gap_analysis_validation": "gap_analysis_validation",
                            "technical_seo_report": "technical_seo_report",
                            "company_analysis_doc": "company_analysis_doc"
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

        # --- 45. No Blog Content Executive Summary Prompt Constructor ---
        "construct_blog_executive_summary_no_blog_prompt": {
            "node_id": "construct_blog_executive_summary_no_blog_prompt",
            "node_category": "analysis",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": BLOG_EXECUTIVE_SUMMARY_NO_BLOG_USER_PROMPT,
                        "variables": {
                            "ai_visibility_report": None,
                            "competitive_intelligence_report": None,
                            "company_analysis_doc": None
                        },
                        "construct_options": {
                            "ai_visibility_report": "ai_visibility_report",
                            "competitive_intelligence_report": "competitive_intelligence_report",
                            "company_analysis_doc": "company_analysis_doc"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": BLOG_EXECUTIVE_SUMMARY_NO_BLOG_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },

        # --- 46. No Blog Content Strategic Recommendations Prompt Constructor ---
        "construct_strategic_recommendations_no_blog_prompt": {
            "node_id": "construct_strategic_recommendations_no_blog_prompt",
            "node_category": "analysis",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": BLOG_STRATEGIC_RECOMMENDATIONS_NO_BLOG_USER_PROMPT,
                        "variables": {
                            "ai_visibility_report": None,
                            "competitive_intelligence_report": None,
                            "company_analysis_doc": None
                        },
                        "construct_options": {
                            "ai_visibility_report": "ai_visibility_report",
                            "competitive_intelligence_report": "competitive_intelligence_report",
                            "company_analysis_doc": "company_analysis_doc"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": BLOG_STRATEGIC_RECOMMENDATIONS_NO_BLOG_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },

        # --- 47. Strategic Recommendations & Action Plan Report ---
        "generate_strategic_recommendations": {
            "node_id": "generate_strategic_recommendations",
            "node_category": "analysis",
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

        # --- 48. Blog Executive Summary ---
        "generate_blog_executive_summary": {
            "node_id": "generate_blog_executive_summary",
            "node_category": "analysis",
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

        # --- 49. Company Reports Aggregator ---
        "aggregate_company_reports": {
            "node_id": "aggregate_company_reports",
            "node_category": "system",
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
                    },
                    {
                        "source_path": "company_analysis_doc",
                        "destination_path": "company_reports.company_analysis"
                    }
                ]
            }
        },

        # --- 50. Store Executive Reports ---
        "store_executive_diagnostic_report": {
            "node_id": "store_executive_diagnostic_report",
            "node_category": "system",
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

        # --- 51. Store Company Reports ---
        "store_company_diagnostic_report": {
            "node_id": "store_company_diagnostic_report",
            "node_category": "system",
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
                        },
                        "extra_fields": [
                            {
                                "src_path": "has_insufficient_blog_and_page_count",
                                "dst_path": "has_insufficient_blog_and_page_count"
                            }
                        ]
                    }
                ]
            }
        },

        # --- 52. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_category": "system",
            "node_name": "output_node",
            "enable_node_fan_in": True,
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
                {"src_field": "blog_start_urls", "dst_field": "blog_start_urls"},
                {"src_field": "allowed_domains", "dst_field": "allowed_domains"},
                {"src_field": "max_urls_per_domain", "dst_field": "max_urls_per_domain"},
                {"src_field": "max_processed_urls_per_domain", "dst_field": "max_processed_urls_per_domain"},
                {"src_field": "max_crawl_depth", "dst_field": "max_crawl_depth"},
                {"src_field": "use_cached_scraping_results", "dst_field": "use_cached_scraping_results"},
                {"src_field": "cache_lookback_period_days", "dst_field": "cache_lookback_period_days"},
                {"src_field": "is_shared", "dst_field": "is_shared"},
                {"src_field": "include_only_paths", "dst_field": "include_only_paths"},
                {"src_field": "exclude_paths", "dst_field": "exclude_paths"},
            ]
        },

        {
            "src_node_id": "input_node",
            "dst_node_id": "data_collection_router",
            "mappings": [
                {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"},
                {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"}
            ]
        },

        {
            "src_node_id": "data_collection_router",
            "dst_node_id": "run_linkedin_scraping",
            "mappings": []
        },

        {
            "src_node_id": "data_collection_router",
            "dst_node_id": "run_blog_crawler",
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

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "run_blog_crawler",
            "mappings": [
                {"src_field": "blog_start_urls", "dst_field": "start_urls"},
                {"src_field": "allowed_domains", "dst_field": "allowed_domains"},
                {"src_field": "max_urls_per_domain", "dst_field": "max_urls_per_domain"},
                {"src_field": "max_processed_urls_per_domain", "dst_field": "max_processed_urls_per_domain"},
                {"src_field": "max_crawl_depth", "dst_field": "max_crawl_depth"},
                {"src_field": "use_cached_scraping_results", "dst_field": "use_cached_scraping_results"},
                {"src_field": "cache_lookback_period_days", "dst_field": "cache_lookback_period_days"},
                {"src_field": "is_shared", "dst_field": "is_shared"},
                {"src_field": "include_only_paths", "dst_field": "include_only_paths"},
                {"src_field": "exclude_paths", "dst_field": "exclude_paths"},
            ]
        },

        # # Store blog crawler results in graph state
        {
            "src_node_id": "run_blog_crawler",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "scraped_data", "dst_field": "blog_scraped_data"},
                {"src_field": "technical_seo_summary", "dst_field": "blog_technical_seo_summary"},
                {"src_field": "robots_analysis", "dst_field": "blog_robots_analysis"},
                {"src_field": "has_insufficient_blog_and_page_count", "dst_field": "has_insufficient_blog_and_page_count"}
            ]
        },

        # Scraping nodes -> Initial Router (for defer_node synchronization)
        {
            "src_node_id": "run_linkedin_scraping",
            "dst_node_id": "initial_router",
            "mappings": []
        },

        {
            "src_node_id": "run_blog_crawler",
            "dst_node_id": "initial_router",
            "mappings": []
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "initial_router",
            "mappings": [
                {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"},
                {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"},
                {"src_field": "has_insufficient_blog_and_page_count", "dst_field": "has_insufficient_blog_and_page_count"}
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
                {"src_field": "blog_start_urls", "dst_field": "start_urls"},
                {"src_field": "allowed_domains", "dst_field": "allowed_domains"},
                {"src_field": "max_urls_per_domain", "dst_field": "max_urls_per_domain"},
                {"src_field": "max_processed_urls_per_domain", "dst_field": "max_processed_urls_per_domain"},
                {"src_field": "max_crawl_depth", "dst_field": "max_crawl_depth"},
                {"src_field": "use_cached_scraping_results", "dst_field": "use_cached_scraping_results"},
                {"src_field": "cache_lookback_period_days", "dst_field": "cache_lookback_period_days"},
                {"src_field": "is_shared", "dst_field": "is_shared"},
                {"src_field": "include_only_paths", "dst_field": "include_only_paths"},
                {"src_field": "exclude_paths", "dst_field": "exclude_paths"},
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

        # Initial Router -> No Blog Post Company AI Visibility (control flow)
        {
            "src_node_id": "initial_router",
            "dst_node_id": "run_no_blog_post_company_ai_visibility",
            "mappings": []
        },
        # Pass required inputs to No Blog Post Company AI Visibility
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "run_no_blog_post_company_ai_visibility",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"}
            ]
        },

        # Initial Router -> Company Analysis (control flow)
        {
            "src_node_id": "initial_router",
            "dst_node_id": "run_company_analysis",
            "mappings": []
        },
        # Pass required inputs to Company Analysis (company_name, scraped_data, and has_insufficient_blog_and_page_count)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "run_company_analysis",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "blog_scraped_data", "dst_field": "scraped_data"},
                {"src_field": "has_insufficient_blog_and_page_count", "dst_field": "has_insufficient_blog_and_page_count"}
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
            "src_node_id": "run_no_blog_post_company_ai_visibility",
            "dst_node_id": "wait_for_core_workflows",
            "mappings": []
        },
        {
            "src_node_id": "run_company_analysis",
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
                {"src_field": "company_context_doc", "dst_field": "company_context_doc"},
                {"src_field": "company_analysis_doc", "dst_field": "company_analysis_doc"}
            ]
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
                {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"},
                {"src_field": "has_insufficient_blog_and_page_count", "dst_field": "has_insufficient_blog_and_page_count"}
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
        # Now routed through blog_content_availability_router
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_strategic_recommendations_prompt",
            "mappings": [
                {"src_field": "ai_visibility_report", "dst_field": "ai_visibility_report"},
                {"src_field": "competitive_intelligence_report", "dst_field": "competitive_intelligence_report"},
                {"src_field": "blog_performance_report", "dst_field": "blog_performance_report"},
                {"src_field": "gap_analysis_validation", "dst_field": "gap_analysis_validation"},
                {"src_field": "technical_seo_doc", "dst_field": "technical_seo_report"},
                {"src_field": "company_analysis_doc", "dst_field": "company_analysis_doc"}
            ]
        },
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
            "src_node_id": "construct_strategic_recommendations_prompt",
            "dst_node_id": "generate_strategic_recommendations",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },
        # No-Blog Strategic Recommendations: constructor -> LLM
        {
            "src_node_id": "construct_strategic_recommendations_no_blog_prompt",
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
        # Now routed through blog_content_availability_router
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_blog_executive_summary_prompt",
            "mappings": [
                {"src_field": "ai_visibility_report", "dst_field": "ai_visibility_report"},
                {"src_field": "competitive_intelligence_report", "dst_field": "competitive_intelligence_report"},
                {"src_field": "blog_performance_report", "dst_field": "blog_performance_report"},
                {"src_field": "gap_analysis_validation", "dst_field": "gap_analysis_validation"},
                {"src_field": "technical_seo_doc", "dst_field": "technical_seo_report"},
                {"src_field": "company_analysis_doc", "dst_field": "company_analysis_doc"}
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
        {
            "src_node_id": "generate_ai_visibility_report",
            "dst_node_id": "construct_blog_executive_summary_prompt",
            "mappings": []
        },
        {
            "src_node_id": "generate_competitive_intelligence_report",
            "dst_node_id": "construct_blog_executive_summary_prompt",
            "mappings": []
        },
        {
            "src_node_id": "generate_blog_performance_report",
            "dst_node_id": "construct_blog_executive_summary_prompt",
            "mappings": []
        },
        {
            "src_node_id": "generate_gap_analysis_validation",
            "dst_node_id": "construct_blog_executive_summary_prompt",
            "mappings": []
        },
        # No-Blog Executive Summary: constructor -> LLM
        {
            "src_node_id": "construct_blog_executive_summary_no_blog_prompt",
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
        # Wait for all company reports to complete before aggregating
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
                {"src_field": "blog_executive_summary", "dst_field": "blog_executive_summary"},
                {"src_field": "company_analysis_doc", "dst_field": "company_analysis_doc"}
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
                {"src_field": "company_reports", "dst_field": "company_reports"},
                {"src_field": "has_insufficient_blog_and_page_count", "dst_field": "has_insufficient_blog_and_page_count"}
            ]
        },

        # --- Final Output ---
        {
            "src_node_id": "store_executive_diagnostic_report",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "paths_processed", "dst_field": "paths_processed"}
            ]
        },
        {
            "src_node_id": "store_company_diagnostic_report",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "paths_processed", "dst_field": "paths_processed"}
            ]
        },

        # All company reports -> Wait for Company Reports (synchronization point)
        # Only include reports that will always execute regardless of blog content availability
        {
            "src_node_id": "generate_ai_visibility_report",
            "dst_node_id": "wait_for_company_reports",
            "mappings": []
        },
        {
            "src_node_id": "generate_competitive_intelligence_report",
            "dst_node_id": "wait_for_company_reports",
            "mappings": []
        },

        # Pass company_name from graph state to wait node
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "wait_for_company_reports",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"}
            ]
        },

        # --- Blog Content Availability Router ---
        {
            "src_node_id": "wait_for_company_reports",
            "dst_node_id": "blog_content_availability_router",
            "mappings": []
        },

        # # Optional blog reports -> Blog Content Availability Router (when they execute)
        {
            "src_node_id": "generate_blog_performance_report",
            "dst_node_id": "blog_content_availability_router",
            "mappings": []
        },
        {
            "src_node_id": "generate_gap_analysis_validation",
            "dst_node_id": "blog_content_availability_router",
            "mappings": []
        },

        # --- Blog Content Availability Router ---
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "blog_content_availability_router",
            "mappings": [
                {"src_field": "has_insufficient_blog_and_page_count", "dst_field": "has_insufficient_blog_and_page_count"}
            ]
        },

        # --- Blog Content Availability Router Edges ---
        {
            "src_node_id": "blog_content_availability_router",
            "dst_node_id": "construct_blog_executive_summary_prompt",
            "mappings": []
        },
        {
            "src_node_id": "blog_content_availability_router",
            "dst_node_id": "construct_strategic_recommendations_prompt",
            "mappings": []
        },
        {
            "src_node_id": "blog_content_availability_router",
            "dst_node_id": "construct_blog_executive_summary_no_blog_prompt",
            "mappings": []
        },
        {
            "src_node_id": "blog_content_availability_router",
            "dst_node_id": "construct_strategic_recommendations_no_blog_prompt",
            "mappings": []
        },

        # Graph state mappings for no-blog prompt constructors
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_blog_executive_summary_no_blog_prompt",
            "mappings": [
                {"src_field": "ai_visibility_report", "dst_field": "ai_visibility_report"},
                {"src_field": "competitive_intelligence_report", "dst_field": "competitive_intelligence_report"},
                {"src_field": "company_analysis_doc", "dst_field": "company_analysis_doc"}
            ]
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_strategic_recommendations_no_blog_prompt",
            "mappings": [
                {"src_field": "ai_visibility_report", "dst_field": "ai_visibility_report"},
                {"src_field": "competitive_intelligence_report", "dst_field": "competitive_intelligence_report"},
                {"src_field": "company_analysis_doc", "dst_field": "company_analysis_doc"}
            ]
        },
        # {
        #     "src_node_id": "generate_ai_visibility_report",
        #     "dst_node_id": "construct_blog_executive_summary_no_blog_prompt",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_competitive_intelligence_report",
        #     "dst_node_id": "construct_blog_executive_summary_no_blog_prompt",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_ai_visibility_report",
        #     "dst_node_id": "construct_strategic_recommendations_no_blog_prompt",
        #     "mappings": []
        # },
        # {
        #     "src_node_id": "generate_competitive_intelligence_report",
        #     "dst_node_id": "construct_strategic_recommendations_no_blog_prompt",
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
                "blog_start_urls": "replace",
                "has_insufficient_blog_and_page_count": "replace",
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
                "competitor_content_docs": "replace",
                "blog_scraped_data": "replace",
                "blog_technical_seo_summary": "replace",
                "blog_robots_analysis": "replace",
                "company_analysis_doc": "replace"
            }
        }
    },

    # --- Define Start and End ---
    "input_node_id": "input_node",
    "output_node_id": "output_node"
}