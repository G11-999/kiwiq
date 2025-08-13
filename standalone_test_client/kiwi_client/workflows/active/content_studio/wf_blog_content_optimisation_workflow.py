"""
Content Optimization Workflow

This workflow enables comprehensive blog content optimization with:
- Multi-faceted content analysis (structure, SEO, readability, content gaps)
- Parallel analysis execution using dynamic router
- Human-in-the-loop approval for analysis results and final content
- Sequential improvement application (content gaps → SEO → structure/readability)
- Feedback analysis and revision loops
- Company context integration throughout the process

Key Features:
- Parallel execution of content analysis steps
- Web search capabilities for competitive content gap analysis
- Structured output schemas for each analysis phase
- HITL approval flows for analysis review and final approval
- Sequential improvement processing with message history management
- Feedback-driven revision cycles
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
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    BLOG_COMPANY_IS_VERSIONED,
    # Blog Post constants for saving
    BLOG_POST_DOCNAME,
    BLOG_POST_NAMESPACE_TEMPLATE,
    BLOG_POST_IS_VERSIONED,
    BLOG_POST_IS_SHARED,
    BLOG_POST_IS_SYSTEM_ENTITY,
)

# Import LLM inputs
from kiwi_client.workflows.active.content_studio.llm_inputs.blog_content_optimisation_workflow import (
    # System prompts
    CONTENT_ANALYZER_SYSTEM_PROMPT,
    SEO_INTENT_ANALYZER_SYSTEM_PROMPT,
    CONTENT_GAP_FINDER_SYSTEM_PROMPT,
    CONTENT_GAP_IMPROVEMENT_SYSTEM_PROMPT,
    SEO_INTENT_IMPROVEMENT_SYSTEM_PROMPT,
    STRUCTURE_READABILITY_IMPROVEMENT_SYSTEM_PROMPT,
    FEEDBACK_ANALYSIS_SYSTEM_PROMPT,
    
    # User prompt templates
    CONTENT_ANALYZER_USER_PROMPT_TEMPLATE,
    SEO_INTENT_ANALYZER_USER_PROMPT_TEMPLATE,
    CONTENT_GAP_FINDER_USER_PROMPT_TEMPLATE,
    CONTENT_GAP_IMPROVEMENT_USER_PROMPT_TEMPLATE,
    SEO_INTENT_IMPROVEMENT_USER_PROMPT_TEMPLATE,
    STRUCTURE_READABILITY_IMPROVEMENT_USER_PROMPT_TEMPLATE,
    FEEDBACK_ANALYSIS_USER_PROMPT_TEMPLATE,
    
    # Output schemas
    CONTENT_ANALYZER_OUTPUT_SCHEMA,
    SEO_INTENT_ANALYZER_OUTPUT_SCHEMA,
    CONTENT_GAP_FINDER_OUTPUT_SCHEMA,
    FINAL_OUTPUT_SCHEMA,
)

# LLM Configuration
LLM_PROVIDER = "anthropic"
LLM_MODEL = "claude-3-7-sonnet-20250219"
TEMPERATURE = 0.7
MAX_TOKENS = 4000

# Perplexity Configuration for Content Gap Research
PERPLEXITY_PROVIDER = "perplexity"
PERPLEXITY_MODEL = "sonar-pro"
PERPLEXITY_TEMPERATURE = 0.3
PERPLEXITY_MAX_TOKENS = 3000

# Workflow Limits
MAX_REVISION_ATTEMPTS = 3
MAX_ITERATIONS = 10  # Maximum iterations for HITL feedback loops

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
                    },
                    "original_blog": {
                        "type": "str",
                        "required": True,
                        "description": "Original blog content to be optimized"
                    },
                    "route_all_choices": {
                        "type": "bool",
                        "required": False,
                        "default": True,
                        "description": "Whether to route all choices to all nodes"
                    }
                }
            }
        },
        
        # 2. Load Company Document
        "load_company_doc": {
            "node_id": "load_company_doc",
            "node_name": "load_customer_data",
            "node_config": {
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_COMPANY_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_COMPANY_DOCNAME,
                        },
                        "output_field_name": "company_doc"
                    }
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False}
            }
        },
        
        # 3. Analysis Trigger Router
        "analysis_trigger_router": {
            "node_id": "analysis_trigger_router",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "construct_content_analyzer_prompt",
                    "construct_seo_intent_analyzer_prompt", 
                    "construct_content_gap_finder_prompt"
                ],
                "allow_multiple": True,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_content_analyzer_prompt",
                        "input_path": "route_all_choices",
                        "target_value": True
                    },
                    {
                        "choice_id": "construct_seo_intent_analyzer_prompt",
                        "input_path": "route_all_choices",
                        "target_value": True
                    },
                    {
                        "choice_id": "construct_content_gap_finder_prompt",
                        "input_path": "route_all_choices",
                        "target_value": True
                    }
                ]
            }
        },
        
        # 4a. Content Analyzer - Prompt Constructor
        "construct_content_analyzer_prompt": {
            "node_id": "construct_content_analyzer_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "content_analyzer_user_prompt": {
                        "id": "content_analyzer_user_prompt",
                        "template": CONTENT_ANALYZER_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "target_audience": None,
                            "content_goals": None,
                            "original_blog": None
                        },
                        "construct_options": {
                            "target_audience": "company_doc.icps",
                            "content_goals": "company_doc.goals",
                            "original_blog": "original_blog"
                        }
                    },
                    "content_analyzer_system_prompt": {
                        "id": "content_analyzer_system_prompt",
                        "template": CONTENT_ANALYZER_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 4b. Content Analyzer - LLM Node
        "content_analyzer_llm": {
            "node_id": "content_analyzer_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER,
                        "model": LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": CONTENT_ANALYZER_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 5a. SEO Intent Analyzer - Prompt Constructor
        "construct_seo_intent_analyzer_prompt": {
            "node_id": "construct_seo_intent_analyzer_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "seo_intent_analyzer_user_prompt": {
                        "id": "seo_intent_analyzer_user_prompt",
                        "template": SEO_INTENT_ANALYZER_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "target_audience": None,
                            "content_goals": None,
                            "competitors": None,
                            "original_blog": None
                        },
                        "construct_options": {
                            "target_audience": "company_doc.icps",
                            "content_goals": "company_doc.goals",
                            "competitors": "company_doc.competitors",
                            "original_blog": "original_blog"
                        }
                    },
                    "seo_intent_analyzer_system_prompt": {
                        "id": "seo_intent_analyzer_system_prompt",
                        "template": SEO_INTENT_ANALYZER_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 5b. SEO Intent Analyzer - LLM Node
        "seo_intent_analyzer_llm": {
            "node_id": "seo_intent_analyzer_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER,
                        "model": LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": SEO_INTENT_ANALYZER_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 6a. Content Gap Finder - Prompt Constructor
        "construct_content_gap_finder_prompt": {
            "node_id": "construct_content_gap_finder_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "content_gap_finder_user_prompt": {
                        "id": "content_gap_finder_user_prompt",
                        "template": CONTENT_GAP_FINDER_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "original_blog": None
                        },
                        "construct_options": {
                            "original_blog": "original_blog"
                        }
                    },
                    "content_gap_finder_system_prompt": {
                        "id": "content_gap_finder_system_prompt",
                        "template": CONTENT_GAP_FINDER_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 6b. Content Gap Finder - LLM Node (with web search)
        "content_gap_finder_llm": {
            "node_id": "content_gap_finder_llm",
            "node_name": "llm",
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
                    "schema_definition": CONTENT_GAP_FINDER_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 7. Analysis Review - HITL Node (receives all three analysis results directly)
        "analysis_review_hitl": {
            "node_id": "analysis_review_hitl",
            "node_name": "hitl_node__default",
            "enable_node_fan_in": True,
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "final_gap_improvement": {
                        "type": "str",
                        "required": False,
                        "description": "Final user-reviewed suggestions for content gap improvements"
                    },
                    "final_seo_improvement": {
                        "type": "str",
                        "required": False,
                        "description": "Final user-reviewed suggestions for SEO improvements"
                    },
                    "final_structure_improvement": {
                        "type": "str",
                        "required": False,
                        "description": "Final user-reviewed suggestions for structure and readability improvements"
                    },
                    "gap_improvement_instructions": {
                        "type": "str",
                        "required": False,
                        "description": "Instructions for content gap improvements"
                    },
                    "seo_improvement_instructions": {
                        "type": "str",
                        "required": False,
                        "description": "Instructions for SEO improvements"
                    },
                    "structure_improvement_instructions": {
                        "type": "str",
                        "required": False,
                        "description": "Instructions for structure and readability improvements"
                    }
                }
            }
        },
        
        # 8a. Content Gap Improvement - Prompt Constructor
        "construct_content_gap_improvement_prompt": {
            "node_id": "construct_content_gap_improvement_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "content_gap_improvement_user_prompt": {
                        "id": "content_gap_improvement_user_prompt",
                        "template": CONTENT_GAP_IMPROVEMENT_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "original_blog": None,
                            "content_gap_analysis": None,
                            "gap_improvement_instructions": None
                        },
                        "construct_options": {
                            "original_blog": "original_blog",
                            "content_gap_analysis": "final_gap_improvement",
                            "gap_improvement_instructions": "gap_improvement_instructions"
                        }
                    },
                    "content_gap_improvement_system_prompt": {
                        "id": "content_gap_improvement_system_prompt",
                        "template": CONTENT_GAP_IMPROVEMENT_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 8b. Content Gap Improvement - LLM Node
        "content_gap_improvement_llm": {
            "node_id": "content_gap_improvement_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER,
                        "model": LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS
                }
            }
        },
        
        # 9a. SEO Intent Improvement - Prompt Constructor
        "construct_seo_intent_improvement_prompt": {
            "node_id": "construct_seo_intent_improvement_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "seo_intent_improvement_user_prompt": {
                        "id": "seo_intent_improvement_user_prompt",
                        "template": SEO_INTENT_IMPROVEMENT_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "current_blog_content": None,
                            "seo_analysis": None,
                            "seo_improvement_instructions": None
                        },
                        "construct_options": {
                            "current_blog_content": "text_content",
                            "seo_analysis": "final_seo_improvement",
                            "seo_improvement_instructions": "seo_improvement_instructions"
                        }
                    },
                    "seo_intent_improvement_system_prompt": {
                        "id": "seo_intent_improvement_system_prompt",
                        "template": SEO_INTENT_IMPROVEMENT_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 9b. SEO Intent Improvement - LLM Node
        "seo_intent_improvement_llm": {
            "node_id": "seo_intent_improvement_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER,
                        "model": LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS
                }
            }
        },
        
        # 10a. Structure Readability Improvement - Prompt Constructor
        "construct_structure_readability_improvement_prompt": {
            "node_id": "construct_structure_readability_improvement_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "structure_readability_improvement_user_prompt": {
                        "id": "structure_readability_improvement_user_prompt",
                        "template": STRUCTURE_READABILITY_IMPROVEMENT_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "current_blog_content": None,
                            "structure_analysis": None,
                            "structure_improvement_instructions": None
                        },
                        "construct_options": {
                            "current_blog_content": "text_content",
                            "structure_analysis": "final_structure_improvement",
                            "structure_improvement_instructions": "structure_improvement_instructions"
                        }
                    },
                    "structure_readability_improvement_system_prompt": {
                        "id": "structure_readability_improvement_system_prompt",
                        "template": STRUCTURE_READABILITY_IMPROVEMENT_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 10b. Structure Readability Improvement - LLM Node
        "structure_readability_improvement_llm": {
            "node_id": "structure_readability_improvement_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER,
                        "model": LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": FINAL_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 11. Final Approval - HITL Node
        "final_approval_hitl": {
            "node_id": "final_approval_hitl",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "approval_status": {
                        "type": "enum",
                        "enum_values": ["approve", "reject"],
                        "required": True,
                        "description": "User's approval decision"
                    },
                    "optimized_content": {
                        "type": "dict",
                        "required": True,
                        "description": "The optimized content to review and approve"
                    },
                    "user_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "Feedback for revision (required if reject)"
                    }
                }
            }
        },
        
        # 12. Route Final Approval
        "route_final_approval": {
            "node_id": "route_final_approval",
            "node_name": "router_node",
            "node_config": {
                "choices": ["save_blog_post", "check_iteration_limit"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "save_blog_post",
                        "input_path": "approval_status",
                        "target_value": "approve"
                    },
                    {
                        "choice_id": "check_iteration_limit",
                        "input_path": "approval_status",
                        "target_value": "reject"
                    }
                ],
                "default_choice": "save_blog_post"
            }
        },
        
        # 13. Check Iteration Limit
        "check_iteration_limit": {
            "node_id": "check_iteration_limit",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "iteration_limit_check",
                        "condition_groups": [ {
                            "logical_operator": "and",
                            "conditions": [ {
                                "field": "generation_metadata.iteration_count",
                                "operator": "less_than",
                                "value": MAX_ITERATIONS
                            } ]
                        } ],
                        "group_logical_operator": "and"
                    }
                ],
                "branch_logic_operator": "and"
            }
        },
        
        # 14. Route Based on Iteration Limit Check
        "route_on_limit_check": {
            "node_id": "route_on_limit_check",
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_feedback_analysis_prompt", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_feedback_analysis_prompt",
                        "input_path": "if_else_condition_tag_results.iteration_limit_check",
                        "target_value": True
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "iteration_branch_result",
                        "target_value": "false_branch"
                    },
                ]
            }
        },
        
        # 15. Feedback Analysis - Prompt Constructor
        "construct_feedback_analysis_prompt": {
            "node_id": "construct_feedback_analysis_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "feedback_analysis_user_prompt": {
                        "id": "feedback_analysis_user_prompt",
                        "template": FEEDBACK_ANALYSIS_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "current_blog_content": None,
                            "user_feedback": None
                        },
                        "construct_options": {
                            "current_blog_content": "final_optimized_content",
                            "user_feedback": "user_feedback"
                        }
                    },
                    "feedback_analysis_system_prompt": {
                        "id": "feedback_analysis_system_prompt",
                        "template": FEEDBACK_ANALYSIS_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 13b. Feedback Analysis - LLM Node
        "feedback_analysis_llm": {
            "node_id": "feedback_analysis_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER,
                        "model": LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": FINAL_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 14. Save Blog Post
        "save_blog_post": {
            "node_id": "save_blog_post",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": True,
                    "operation": "initialize",
                    "version": "optimized_v1"
                },
                "store_configs": [
                    {
                        "input_field_path": "final_optimized_content",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_POST_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": "blog_post_{_uuid_}",
                            }
                        },
                        "generate_uuid": True,
                        "versioning": {
                            "is_versioned": BLOG_POST_IS_VERSIONED,
                            "operation": "upsert_versioned",
                        }
                    }
                ]
            }
        },
        
        # 15. Output Node
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
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
                {"src_field": "original_blog", "dst_field": "original_blog"},
                {"src_field": "post_uuid", "dst_field": "post_uuid"},
                {"src_field": "route_all_choices", "dst_field": "route_all_choices"}
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
        
        # Company Doc -> Analysis Router (trigger with company context loaded)
        {
            "src_node_id": "load_company_doc",
            "dst_node_id": "analysis_trigger_router"
        },

        # Analysis Router -> State: Store route_all_choices
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "analysis_trigger_router",
            "mappings": [
                {"src_field": "route_all_choices", "dst_field": "route_all_choices"}
            ]
        },
        # --- Analysis Router to Prompt Constructors ---
        {
            "src_node_id": "analysis_trigger_router",
            "dst_node_id": "construct_content_analyzer_prompt"
        },
        {
            "src_node_id": "analysis_trigger_router",
            "dst_node_id": "construct_seo_intent_analyzer_prompt"
        },
        {
            "src_node_id": "analysis_trigger_router",
            "dst_node_id": "construct_content_gap_finder_prompt"
        },
        
        # State -> All Prompt Constructors (provide context)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_content_analyzer_prompt",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "original_blog", "dst_field": "original_blog"}
            ]
        },
        {
            "src_node_id": "$graph_state", 
            "dst_node_id": "construct_seo_intent_analyzer_prompt",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "original_blog", "dst_field": "original_blog"}
            ]
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_content_gap_finder_prompt",
            "mappings": [
                {"src_field": "original_blog", "dst_field": "original_blog"}
            ]
        },
        
        # Prompt Constructors -> LLM Nodes
        {
            "src_node_id": "construct_content_analyzer_prompt",
            "dst_node_id": "content_analyzer_llm",
            "mappings": [
                {"src_field": "content_analyzer_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "content_analyzer_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        {
            "src_node_id": "construct_seo_intent_analyzer_prompt",
            "dst_node_id": "seo_intent_analyzer_llm",
            "mappings": [
                {"src_field": "seo_intent_analyzer_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "seo_intent_analyzer_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        {
            "src_node_id": "construct_content_gap_finder_prompt",
            "dst_node_id": "content_gap_finder_llm",
            "mappings": [
                {"src_field": "content_gap_finder_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "content_gap_finder_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # LLM Nodes -> HITL Review (direct connection, no merge)
        {
            "src_node_id": "content_analyzer_llm",
            "dst_node_id": "analysis_review_hitl",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "content_analysis"}
            ]
        },
        {
            "src_node_id": "seo_intent_analyzer_llm",
            "dst_node_id": "analysis_review_hitl", 
            "mappings": [
                {"src_field": "structured_output", "dst_field": "seo_analysis"}
            ]
        },
        {
            "src_node_id": "content_gap_finder_llm",
            "dst_node_id": "analysis_review_hitl",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "content_gap_analysis"}
            ]
        },
        
        # HITL Review -> State: Store user-reviewed suggestions
        {
            "src_node_id": "analysis_review_hitl",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "final_gap_improvement", "dst_field": "final_gap_improvement"},
                {"src_field": "final_seo_improvement", "dst_field": "final_seo_improvement"},
                {"src_field": "final_structure_improvement", "dst_field": "final_structure_improvement"},
                {"src_field": "gap_improvement_instructions", "dst_field": "gap_improvement_instructions"},
                {"src_field": "seo_improvement_instructions", "dst_field": "seo_improvement_instructions"},
                {"src_field": "structure_improvement_instructions", "dst_field": "structure_improvement_instructions"}
            ]
        },
        
        # HITL Review -> Content Gap Improvement (start sequential chain)
        {
            "src_node_id": "analysis_review_hitl",
            "dst_node_id": "construct_content_gap_improvement_prompt"
        },
        
        # --- Sequential Improvement Chain ---
        
        # State -> Content Gap Improvement Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_content_gap_improvement_prompt",
            "mappings": [
                {"src_field": "original_blog", "dst_field": "original_blog"},
                {"src_field": "final_gap_improvement", "dst_field": "final_gap_improvement"},
                {"src_field": "gap_improvement_instructions", "dst_field": "gap_improvement_instructions"}
            ]
        },
        
        # Content Gap Improvement Prompt -> LLM
        {
            "src_node_id": "construct_content_gap_improvement_prompt",
            "dst_node_id": "content_gap_improvement_llm",
            "mappings": [
                {"src_field": "content_gap_improvement_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "content_gap_improvement_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Content Gap Improvement LLM -> SEO Improvement Prompt
        {
            "src_node_id": "content_gap_improvement_llm",
            "dst_node_id": "construct_seo_intent_improvement_prompt",
            "mappings": [
                {"src_field": "text_content", "dst_field": "text_content"}
            ]
        },
        
        # State -> SEO Improvement Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_seo_intent_improvement_prompt",
            "mappings": [
                {"src_field": "final_seo_improvement", "dst_field": "final_seo_improvement"},
                {"src_field": "seo_improvement_instructions", "dst_field": "seo_improvement_instructions"}
            ]
        },
        
        # SEO Improvement Prompt -> LLM
        {
            "src_node_id": "construct_seo_intent_improvement_prompt",
            "dst_node_id": "seo_intent_improvement_llm",
            "mappings": [
                {"src_field": "seo_intent_improvement_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "seo_intent_improvement_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # SEO Improvement LLM -> Structure Improvement Prompt
        {
            "src_node_id": "seo_intent_improvement_llm",
            "dst_node_id": "construct_structure_readability_improvement_prompt",
            "mappings": [
                {"src_field": "text_content", "dst_field": "text_content"}
            ]
        },
        
        # State -> Structure Improvement Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_structure_readability_improvement_prompt",
            "mappings": [
                {"src_field": "final_structure_improvement", "dst_field": "final_structure_improvement"},
                {"src_field": "structure_improvement_instructions", "dst_field": "structure_improvement_instructions"}
            ]
        },
        
        # Structure Improvement Prompt -> LLM
        {
            "src_node_id": "construct_structure_readability_improvement_prompt",
            "dst_node_id": "structure_readability_improvement_llm",
            "mappings": [
                {"src_field": "structure_readability_improvement_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "structure_readability_improvement_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Structure Improvement LLM -> State
        {
            "src_node_id": "structure_readability_improvement_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "final_optimized_content"},
                {"src_field": "metadata", "dst_field": "generation_metadata", "description": "Store LLM metadata (e.g., token usage, iteration count)."}
            ]
        },
        
        # Structure Improvement LLM -> Final Approval HITL
        {
            "src_node_id": "structure_readability_improvement_llm",
            "dst_node_id": "final_approval_hitl"
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "final_approval_hitl",
            "mappings": [
                {"src_field": "final_optimized_content", "dst_field": "final_optimized_content"}
            ]
        },
        
        # Final Approval HITL -> Route
        {
            "src_node_id": "final_approval_hitl",
            "dst_node_id": "route_final_approval",
            "mappings": [
                {"src_field": "approval_status", "dst_field": "approval_status"}
            ]
        },
        
        # Final Approval HITL -> State
        {
            "src_node_id": "final_approval_hitl",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "optimized_content", "dst_field": "final_optimized_content"},
                {"src_field": "user_feedback", "dst_field": "user_feedback"}
            ]
        },
        
        # --- Final Approval Router Paths ---
        {
            "src_node_id": "route_final_approval",
            "dst_node_id": "save_blog_post"
        },
        {
            "src_node_id": "route_final_approval",
            "dst_node_id": "check_iteration_limit"
        },
        
        # Check Iteration Limit edges
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "check_iteration_limit",
            "mappings": [
                {"src_field": "generation_metadata", "dst_field": "generation_metadata", "description": "Pass LLM metadata containing iteration count."}
            ]
        },
        {
            "src_node_id": "check_iteration_limit",
            "dst_node_id": "route_on_limit_check",
            "mappings": [
                {"src_field": "branch", "dst_field": "iteration_branch_result", "description": "Pass the branch taken ('true_branch' if limit not reached, 'false_branch' if reached)."},
                {"src_field": "tag_results", "dst_field": "if_else_condition_tag_results", "description": "Pass detailed results per condition tag."},
                {"src_field": "condition_result", "dst_field": "if_else_overall_condition_result", "description": "Pass the overall boolean result of the check."}
            ]
        },
        {
            "src_node_id": "route_on_limit_check",
            "dst_node_id": "construct_feedback_analysis_prompt",
            "description": "Trigger feedback interpretation if iterations remain"
        },
        {
            "src_node_id": "route_on_limit_check",
            "dst_node_id": "output_node",
            "description": "Trigger finalization if iteration limit reached"
        },
        
        # State -> Save Blog Post
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_blog_post",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "final_optimized_content", "dst_field": "final_optimized_content"}            ]
        },
        
        # Save Blog Post -> Output
        {
            "src_node_id": "save_blog_post",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "paths_processed", "dst_field": "final_blog_post_paths"},
                {"src_field": "passthrough_data", "dst_field": "final_blog_post_data"}
            ]
        },
        
        # --- Feedback Loop ---
        
        # State -> Feedback Analysis Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_feedback_analysis_prompt",
            "mappings": [
                {"src_field": "final_optimized_content", "dst_field": "final_optimized_content"},
                {"src_field": "user_feedback", "dst_field": "user_feedback"}
            ]
        },
        
        # Feedback Analysis Prompt -> LLM
        {
            "src_node_id": "construct_feedback_analysis_prompt",
            "dst_node_id": "feedback_analysis_llm",
            "mappings": [
                {"src_field": "feedback_analysis_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "feedback_analysis_system_prompt", "dst_field": "system_prompt"}
            ]
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "feedback_analysis_llm",
            "mappings": [
                {"src_field": "feedback_analysis_message_history", "dst_field": "messages_history"}
            ]
        },
        
        # Feedback Analysis LLM -> Final Approval HITL (loop back)
        {
            "src_node_id": "feedback_analysis_llm",
            "dst_node_id": "final_approval_hitl",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "optimized_content"}
            ]
        },
        
        # Feedback Analysis LLM -> State
        {
            "src_node_id": "feedback_analysis_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "final_optimized_content"},
                {"src_field": "current_messages", "dst_field": "feedback_analysis_message_history"}
            ]
        },
        
        # State -> Output
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "final_optimized_content", "dst_field": "final_optimized_content"}
            ]
        }
    ],
    
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    "metadata": {
        "$graph_state": {
            "reducer": {
                "final_optimized_content": "replace",
                "final_gap_improvement": "replace",
                "final_seo_improvement": "replace", 
                "final_structure_improvement": "replace",
                "user_feedback": "replace",
                "generation_metadata": "replace",
                "feedback_analysis_message_history": "add_messages"
            }
        }
    }
}


# --- Testing Code ---

async def validate_content_optimization_workflow_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Validate the content optimization workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run.
        
    Returns:
        True if the outputs are valid, False otherwise.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating content optimization workflow outputs...")
    
    # Check for expected keys
    expected_keys = [
        'content_analysis_results',
        'seo_analysis_results', 
        'content_gap_analysis_results',
        'final_optimized_content'
    ]
    
    for key in expected_keys:
        if key in outputs:
            logger.info(f"✓ Found expected key: {key}")
        else:
            logger.warning(f"⚠ Missing optional key: {key}")
    
    # Validate content analysis results if present
    if 'content_analysis_results' in outputs:
        content_analysis = outputs['content_analysis_results']
        assert isinstance(content_analysis, dict), "Content analysis results should be a dict"
        assert 'structure_analysis' in content_analysis, "Content analysis missing structure_analysis"
        assert 'readability_analysis' in content_analysis, "Content analysis missing readability_analysis"
        assert 'tone_analysis' in content_analysis, "Content analysis missing tone_analysis"
        logger.info("✓ Content analysis results validated")
    
    # Validate SEO analysis results if present
    if 'seo_analysis_results' in outputs:
        seo_analysis = outputs['seo_analysis_results']
        assert isinstance(seo_analysis, dict), "SEO analysis results should be a dict"
        assert 'search_intent_analysis' in seo_analysis, "SEO analysis missing search_intent_analysis"
        assert 'keyword_analysis' in seo_analysis, "SEO analysis missing keyword_analysis"
        logger.info("✓ SEO analysis results validated")
    
    # Validate content gap analysis results if present
    if 'content_gap_analysis_results' in outputs:
        gap_analysis = outputs['content_gap_analysis_results']
        assert isinstance(gap_analysis, dict), "Content gap analysis results should be a dict"
        assert 'content_gaps' in gap_analysis, "Content gap analysis missing content_gaps"
        assert 'competitive_insights' in gap_analysis, "Content gap analysis missing competitive_insights"
        logger.info("✓ Content gap analysis results validated")
    
    # Validate final optimized content if present
    if 'final_optimized_content' in outputs:
        final_content = outputs['final_optimized_content']
        assert isinstance(final_content, dict), "Final optimized content should be a dict"
        assert 'optimized_blog_content' in final_content, "Final content missing optimized_blog_content"
        assert 'optimization_summary' in final_content, "Final content missing optimization_summary"
        
        # Check that optimized content is not empty
        optimized_text = final_content['optimized_blog_content']
        assert isinstance(optimized_text, str), "Optimized blog content should be a string"
        assert len(optimized_text.strip()) > 0, "Optimized blog content should not be empty"
        
        logger.info("✓ Final optimized content validated")
        logger.info(f"✓ Optimized content length: {len(optimized_text)} characters")
    
    # Check if blog post was saved
    final_blog_post_paths = outputs.get('final_blog_post_paths')
    final_blog_post_data = outputs.get('final_blog_post_data')
    if final_blog_post_paths:
        logger.info("✓ Optimized blog post was successfully saved")
        assert isinstance(final_blog_post_paths, list), "Final blog post paths should be a list"
        logger.info(f"   Blog post saved to: {final_blog_post_paths}")
    if final_blog_post_data:
        logger.info(f"   Blog post data available: {type(final_blog_post_data)}")
    
    logger.info("✓ Content optimization workflow output validation passed.")
    return True


async def main_test_content_optimization_workflow():
    """
    Test for Content Optimization Workflow.
    
    This function sets up test data, executes the workflow, and validates the output.
    The workflow analyzes blog content across multiple dimensions, provides HITL approval,
    applies sequential improvements, and produces optimized content.
    """
    test_name = "Content Optimization Workflow Test"
    print(f"--- Starting {test_name} ---")
    
    # Test parameters
    test_company_name = "Momentum"
    
    # Create test company document data
    company_data = {
        "name": "Momentum",
        "website_url": "https://www.momentum.io",
        "value_proposition": "AI-native Revenue Orchestration Platform that extracts, structures, and moves GTM data automatically. Momentum tracks what's said in every customer interaction and turns it into structured, usable data, updating CRM fields in real time for cleaner pipeline, better reporting, and smarter AI agents with context.",
        "company_offerings": [
            {
                "offering": "AI-powered Revenue Orchestration Platform",
                "use_case": [
                    "Automated CRM data entry and hygiene",
                    "Real-time deal tracking and forecasting",
                    "Customer conversation intelligence and insights",
                    "Sales process automation and optimization",
                    "Revenue pipeline visibility and reporting"
                ],
                "ideal_users": [
                    "Chief Revenue Officers",
                    "VP of Sales",
                    "Sales Operations Managers",
                    "VP of Customer Success",
                    "Revenue Operations Teams"
                ]
            },
            {
                "offering": "Conversation Intelligence and Analytics",
                "use_case": [
                    "Call transcription and sentiment analysis",
                    "Customer feedback extraction and categorization",
                    "Competitive intelligence gathering",
                    "Product feedback and feature request tracking",
                    "Risk signal identification and churn prevention"
                ],
                "ideal_users": [
                    "Sales Representatives",
                    "Customer Success Managers",
                    "Product Marketing Managers",
                    "Business Development Teams",
                    "Executive Leadership"
                ]
            },
            {
                "offering": "Automated GTM Data Workflows",
                "use_case": [
                    "Salesforce integration and data synchronization",
                    "Multi-platform data orchestration",
                    "Custom field mapping and data transformation",
                    "Workflow automation and trigger management",
                    "Data quality monitoring and alerts"
                ],
                "ideal_users": [
                    "Sales Operations Analysts",
                    "CRM Administrators",
                    "Revenue Operations Directors",
                    "IT and Systems Integration Teams",
                    "Data Analytics Teams"
                ]
            }
        ],
        "icps": [
            {
                "icp_name": "Enterprise SaaS Revenue Teams",
                "target_industry": "SaaS/Technology",
                "company_size": "Enterprise (1000+ employees)",
                "buyer_persona": "Chief Revenue Officer (CRO)",
                "pain_points": [
                    "Manual, repetitive Salesforce data entry",
                    "Poor CRM data hygiene and accuracy",
                    "Lack of visibility into deal progression and forecast risk",
                    "Difficulty extracting insights from customer conversations",
                    "Revenue team inefficiencies and administrative overhead"
                ]
            },
            {
                "icp_name": "Growth-Stage Sales Organizations",
                "target_industry": "B2B SaaS",
                "company_size": "Mid-market (200-1000 employees)",
                "buyer_persona": "VP of Sales/Sales Operations",
                "pain_points": [
                    "Inconsistent sales process execution",
                    "Manual deal room management and collaboration",
                    "Missing customer intelligence and buying signals",
                    "Time-consuming post-call administrative tasks",
                    "Lack of real-time coaching and performance insights"
                ]
            },
            {
                "icp_name": "Customer Success Teams",
                "target_industry": "Technology/SaaS",
                "company_size": "Mid-market to Enterprise (500+ employees)",
                "buyer_persona": "VP of Customer Success",
                "pain_points": [
                    "Inability to predict and prevent customer churn",
                    "Manual tracking of customer health and satisfaction",
                    "Difficulty identifying expansion opportunities",
                    "Lack of visibility into customer feedback and product insights",
                    "Inefficient handoff processes from sales to customer success"
                ]
            }
        ],
        "content_distribution_mix": {
            "awareness_percent": 30.0,
            "consideration_percent": 40.0,
            "purchase_percent": 20.0,
            "retention_percent": 10.0
        },
        "competitors": [
            {
                "website_url": "https://www.gong.io",
                "name": "Gong"
            },
            {
                "website_url": "https://www.outreach.io",
                "name": "Outreach"
            },
            {
                "website_url": "https://www.avoma.com",
                "name": "Avoma"
            }
        ],
        "goals": [
            "Establish thought leadership in revenue intelligence and AI-powered sales automation",
            "Educate target audience about the benefits of automated GTM data workflows",
            "Generate qualified leads through valuable content addressing CRM and sales operation challenges",
            "Build brand awareness among enterprise revenue teams and sales operations professionals",
            "Create content that drives organic traffic for high-intent keywords related to revenue orchestration and conversation intelligence"
        ]
    }
    
    # Sample blog content to optimize
    original_blog_content = """
# How AI is Revolutionizing Project Management

Project management has been around for decades, but artificial intelligence is changing everything. Companies are using AI to make their projects better.

## What is AI in Project Management?

AI helps with project management by using smart algorithms to analyze data and make predictions. This is useful for project managers who want to be more efficient.

## Benefits of AI

- Better planning
- Faster execution
- Cost savings
- Improved teamwork

AI can help with scheduling, resource allocation, and risk management. Many companies are starting to use these tools.

## Challenges

There are some challenges with AI implementation:
- Cost of implementation
- Training requirements
- Change management

## Conclusion

AI is the future of project management. Companies should consider adopting these technologies to stay competitive.

Contact us to learn more about our AI-powered project management solutions.
"""
    
    # Test inputs
    test_inputs = {
        "company_name": test_company_name,
        "original_blog": original_blog_content
    }
    
    # Setup test documents
    setup_docs: List[SetupDocInfo] = [
        {
            'namespace': f"blog_company_profile_{test_company_name}",
            'docname': BLOG_COMPANY_DOCNAME,
            'initial_data': company_data,
            'is_shared': False,
            'is_versioned': BLOG_COMPANY_IS_VERSIONED,
            'initial_version': "default",
            'is_system_entity': False
        }
    ]
    
    # Cleanup configuration - force recreation of document
    cleanup_docs: List[CleanupDocInfo] = [
        {
            'namespace': f"blog_company_profile_{test_company_name}",
            'docname': BLOG_COMPANY_DOCNAME,
            'is_shared': False,
            'is_versioned': BLOG_COMPANY_IS_VERSIONED,
            'is_system_entity': False
        }
    ]
    
    # Predefined HITL inputs - leaving empty to allow for interactive testing
    predefined_hitl_inputs = []
    
    # VALID HUMAN INPUTS FOR MANUAL TESTING:
    
    # For analysis review HITL:
    # {"user_action": "proceed_with_improvements", "gap_improvement_instructions": "Add more specific examples and case studies", "seo_improvement_instructions": "Focus on long-tail keywords for project management AI", "structure_improvement_instructions": "Improve readability with better subheadings and bullet points"}
    
    # For final approval HITL:
    # {"approval_status": "approve"}
    # {"approval_status": "reject", "user_feedback": "The content is too technical, please make it more accessible for non-technical project managers"}
    
    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=predefined_hitl_inputs,
        setup_docs=setup_docs,
        cleanup_docs=cleanup_docs,
        cleanup_docs_created_by_setup=True,
        validate_output_func=validate_content_optimization_workflow_output,
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=1800  # 30 minutes for comprehensive analysis and optimization
    )
    
    print(f"--- {test_name} Finished ---")
    if final_run_outputs:
        # Show analysis results
        if 'content_analysis_results' in final_run_outputs:
            content_analysis = final_run_outputs['content_analysis_results']
            structure_issues = len(content_analysis.get('structure_analysis', {}).get('content_flow_issues', []))
            print(f"Content Analysis: {structure_issues} structural issues identified")
        
        if 'seo_analysis_results' in final_run_outputs:
            seo_analysis = final_run_outputs['seo_analysis_results']
            intent = seo_analysis.get('search_intent_analysis', {}).get('primary_intent', 'N/A')
            print(f"SEO Analysis: Primary intent identified as '{intent}'")
        
        if 'content_gap_analysis_results' in final_run_outputs:
            gap_analysis = final_run_outputs['content_gap_analysis_results']
            gaps_found = len(gap_analysis.get('content_gaps', []))
            print(f"Content Gap Analysis: {gaps_found} content gaps identified")
        
        # Show final optimized content info
        if 'final_optimized_content' in final_run_outputs:
            final_content = final_run_outputs['final_optimized_content']
            optimized_text = final_content.get('optimized_blog_content', '')
            optimization_summary = final_content.get('optimization_summary', {})
            
            print(f"Final Content: {len(optimized_text)} characters")
            print(f"Gaps Filled: {len(optimization_summary.get('content_gaps_filled', []))}")
            print(f"SEO Improvements: {len(optimization_summary.get('seo_improvements_made', []))}")
            print(f"Structure Enhancements: {len(optimization_summary.get('structure_enhancements', []))}")
        
        # Show blog post saving info
        if 'final_blog_post_paths' in final_run_outputs:
            print("✓ Optimized blog post was successfully saved")
            print(f"Saved to: {final_run_outputs['final_blog_post_paths']}")
        if 'final_blog_post_data' in final_run_outputs:
            print(f"Blog post data available: {type(final_run_outputs['final_blog_post_data'])}")


# Entry point
if __name__ == "__main__":
    print("="*80)
    print("Content Optimization Workflow Test")
    print("="*80)
    
    try:
        asyncio.run(main_test_content_optimization_workflow())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.exception("Test execution failed")
    
    print("\nTest execution finished.")
    print("Run from project root: PYTHONPATH=. python kiwi_client/workflows_for_blog_teammate/wf_content_optimisation_workflow.py")
