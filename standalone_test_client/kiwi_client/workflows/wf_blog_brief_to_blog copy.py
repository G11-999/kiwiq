"""
Brief to Blog Generation Workflow

This workflow enables blog content generation from a brief with:
- Loading blog brief, SEO best practices, and company documentation
- Domain knowledge enrichment from knowledge base using document tools
- Comprehensive content generation with SEO optimization
- Human-in-the-loop approval for content review and feedback
- Feedback processing and content iteration
- Final blog post saving with proper document management

Test Configuration:
- Uses blog document types from the system configuration (blog_content_brief, blog_company_doc, etc.)
- Creates realistic test data matching the blog document schemas
- Tests various scenarios including knowledge enrichment, content generation, and feedback processing
- Includes proper HITL approval flows and document saving
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
    # Blog Content Brief
    BLOG_CONTENT_BRIEF_NAMESPACE_TEMPLATE,
    # Blog Company Doc
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    # Blog Post
    BLOG_POST_DOCNAME,
    BLOG_POST_NAMESPACE_TEMPLATE,
    BLOG_POST_IS_VERSIONED,

    # Blog SEO Best Practices
    BLOG_SEO_BEST_PRACTICES_DOCNAME,
    BLOG_SEO_BEST_PRACTICES_NAMESPACE_TEMPLATE,
    BLOG_SEO_BEST_PRACTICES_IS_SHARED,
    BLOG_SEO_BEST_PRACTICES_IS_SYSTEM_ENTITY,
)

from kiwi_client.workflows.active.content_studio.llm_inputs.blog_brief_to_blog import (
    KNOWLEDGE_ENRICHMENT_SYSTEM_PROMPT,
    KNOWLEDGE_ENRICHMENT_USER_PROMPT_TEMPLATE,
    CONTENT_GENERATION_SYSTEM_PROMPT,
    CONTENT_GENERATION_USER_PROMPT_TEMPLATE,
    FEEDBACK_ANALYSIS_SYSTEM_PROMPT,
    FEEDBACK_ANALYSIS_USER_PROMPT_TEMPLATE,
    CONTENT_UPDATE_USER_PROMPT_TEMPLATE,
    KNOWLEDGE_ENRICHMENT_OUTPUT_SCHEMA,
    CONTENT_GENERATION_OUTPUT_SCHEMA,
    FEEDBACK_ANALYSIS_OUTPUT_SCHEMA,
)

# Configuration constants
# LLM_PROVIDER = "openai"  # anthropic    openai
# LLM_MODEL = "gpt-5"  # o4-mini   gpt-4.1    claude-sonnet-4-20250514
TEMPERATURE = 0.7
MAX_TOKENS = 10000
MAX_TOOL_CALLS = 15  # Maximum total tool calls allowed
MAX_LLM_ITERATIONS = 10  # Maximum LLM loop iterations

# Providers per task
TOOLCALL_LLM_PROVIDER = "openai"
TOOLCALL_LLM_MODEL = "gpt-5"
DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_LLM_MODEL = "gpt-4.1"


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
                        "description": "Name of the company to analyze"
                    },
                    "brief_docname": { "type": "str", "required": True, "description": "Docname of the brief being used for drafting." },
                    "post_uuid": { "type": "str", "required": True, "description": "UUID of the post being generated." },
                    "initial_status": { "type": "str", "required": False, "default": "draft", "description": "Initial status used when saving drafts." }
                }
            }
        },
        
        # 2. Load All Context Documents  
        "load_all_context_docs": {
            "node_id": "load_all_context_docs",
            "node_name": "load_customer_data",
            "node_config": {
                # Global defaults
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
                
                # Configure to load multiple documents
                "load_paths": [
                    # Blog Content Brief
                    {
                        "filename_config": {
                            "input_namespace_field": "company_name",
                            "input_namespace_field_pattern": BLOG_CONTENT_BRIEF_NAMESPACE_TEMPLATE,
                            "input_docname_field": "brief_docname",
                        },
                        "output_field_name": "blog_brief",
                    },
                    # Company Guidelines
                    {
                        "filename_config": {
                            "input_namespace_field": "company_name",
                            "input_namespace_field_pattern": BLOG_COMPANY_NAMESPACE_TEMPLATE,
                            "static_docname": BLOG_COMPANY_DOCNAME,
                        },
                        "output_field_name": "company_guidelines",
                    },
                    # SEO Best Practices (System Document)
                    {
                        "filename_config": {
                            "static_namespace": BLOG_SEO_BEST_PRACTICES_NAMESPACE_TEMPLATE,
                            "static_docname": BLOG_SEO_BEST_PRACTICES_DOCNAME,
                        },
                        "output_field_name": "seo_best_practices",
                        "is_shared": BLOG_SEO_BEST_PRACTICES_IS_SHARED,
                        "is_system_entity": BLOG_SEO_BEST_PRACTICES_IS_SYSTEM_ENTITY
                    }
                ],
            },
        },
        
        # 3. Construct Knowledge Enrichment Prompt
        "construct_knowledge_enrichment_prompt": {
            "node_id": "construct_knowledge_enrichment_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,  # Wait for all data loads before proceeding
            "node_config": {
                "prompt_templates": {
                    "knowledge_enrichment_user_prompt": {
                        "id": "knowledge_enrichment_prompt",
                        "template": KNOWLEDGE_ENRICHMENT_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "blog_brief": None,
                            "company_name": None
                        },
                        "construct_options": {
                            "blog_brief": "blog_brief",
                            "company_name": "company_name"
                        }
                    },
                    "knowledge_enrichment_system_prompt": {
                        "id": "knowledge_enrichment_system_prompt",
                        "template": KNOWLEDGE_ENRICHMENT_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 4. Knowledge Enrichment LLM with Document Tools
        "knowledge_enrichment_llm": {
            "node_id": "knowledge_enrichment_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": TOOLCALL_LLM_PROVIDER,
                        "model": TOOLCALL_LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                    "reasoning_effort_class": "high"
                },
                "tool_calling_config": {
                    "enable_tool_calling": True,
                    "parallel_tool_calls": True
                },
                "tools": [
                    {
                        "tool_name": "search_documents",
                        "is_provider_inbuilt_tool": False,
                        "provider_inbuilt_user_config": {}
                    }
                ],
                "output_schema": {
                    "schema_definition": KNOWLEDGE_ENRICHMENT_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False,
                }
            }
        },
        
        # 5a. Check Conditions for Knowledge Enrichment Tool Use
        "check_conditions": {
            "node_id": "check_conditions",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "iteration_limit_check",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "generation_metadata.iteration_count",
                                "operator": "greater_than_or_equals",
                                "value": MAX_LLM_ITERATIONS
                            }]
                        }]
                    },
                    {
                        "tag": "tool_calls_empty",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "tool_calls",
                                "operator": "is_empty"
                            }]
                        }]
                    },
                    {
                        "tag": "structured_output_empty",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "knowledge_context",
                                "operator": "is_empty"
                            }]
                        }]
                    }
                ],
                "branch_logic_operator": "or"
            }
        },
        
        # 5b. Route Based on Conditions (no HITL)
        "route_from_conditions": {
            "node_id": "route_from_conditions",
            "node_name": "router_node",
            "node_config": {
                "choices": ["tool_executor", "construct_content_generation_prompt"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_content_generation_prompt",
                        "input_path": "tag_results.iteration_limit_check",
                        "target_value": True
                    },
                    {
                        "choice_id": "tool_executor",
                        "input_path": "tag_results.tool_calls_empty",
                        "target_value": False
                    },
                    {
                        "choice_id": "construct_content_generation_prompt",
                        "input_path": "tag_results.structured_output_empty",
                        "target_value": False
                    }
                ],
                "default_choice": "construct_content_generation_prompt"
            }
        },
        
        # 5c. Tool Executor (executes document tools)
        "tool_executor": {
            "node_id": "tool_executor",
            "node_name": "tool_executor",
            "node_config": {
                "default_timeout": 30.0,
                "max_concurrent_executions": 3,
                "continue_on_error": True,
                "include_error_details": True,
                "map_executor_input_fields_to_tool_input": True
            }
        },

        # 6. Construct Content Generation Prompt
        "construct_content_generation_prompt": {
            "node_id": "construct_content_generation_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "content_generation_user_prompt": {
                        "id": "content_generation_user_prompt",
                        "template": CONTENT_GENERATION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "blog_brief": None,
                            "knowledge_context": None,
                        },
                        "construct_options": {
                            "blog_brief": "blog_brief",
                            "knowledge_context": "knowledge_context",
                        }
                    },
                    "content_generation_system_prompt": {
                        "id": "content_generation_system_prompt",
                        "template": CONTENT_GENERATION_SYSTEM_PROMPT,
                        "variables": {
                            "seo_best_practices": None,
                        },
                        "construct_options": {
                            "seo_best_practices": "seo_best_practices",
                        }
                    }
                }
            }
        },
        
        # 7. Content Generation LLM
        "content_generation_llm": {
            "node_id": "content_generation_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": DEFAULT_LLM_PROVIDER,
                        "model": DEFAULT_LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": CONTENT_GENERATION_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False,
                }
            }
        },
        
        # 7b. Store Initial Draft
        "store_draft": {
            "node_id": "store_draft",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": True,
                    "operation": "initialize",
                    "version": "draft_v1"
                },
                "store_configs": [
                    {
                        "input_field_path": "blog_content",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_POST_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "input_docname_field_pattern": BLOG_POST_DOCNAME,
                                "input_docname_field": "post_uuid"
                            }
                        },
                        "versioning": {
                            "is_versioned": BLOG_POST_IS_VERSIONED,
                            "operation": "upsert_versioned"
                        },
                        "extra_fields": [
                            {
                                "src_path": "initial_status",     
                                "dst_path": "status"
                            },
                            {
                                "src_path": "post_uuid",
                                "dst_path": "uuid"
                            }
                        ]
                    }
                ]
            }
        },
        
        # 7c. Save Draft (manual upsert)
        "save_draft": {
            "node_id": "save_draft",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": BLOG_POST_IS_VERSIONED,
                    "operation": "upsert_versioned"
                },
                "store_configs": [
                    {
                        "input_field_path": "blog_content",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_POST_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "input_docname_field_pattern": BLOG_POST_DOCNAME,
                                "input_docname_field": "post_uuid"
                            }
                        },
                        "versioning": {
                            "is_versioned": BLOG_POST_IS_VERSIONED,
                            "operation": "upsert_versioned"
                        },
                        "extra_fields": [
                            {
                                "src_path": "initial_status",
                                "dst_path": "status"
                            },
                            {
                                "src_path": "post_uuid",
                                "dst_path": "uuid"
                            }
                        ]
                    }
                ]
            }
        },
        
        # 7d. Save Final Draft
        "save_final_draft": {
            "node_id": "save_final_draft",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": BLOG_POST_IS_VERSIONED,
                    "operation": "upsert_versioned"
                },
                "store_configs": [
                    {
                        "input_field_path": "blog_content",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_POST_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "input_docname_field_pattern": BLOG_POST_DOCNAME,
                                "input_docname_field": "post_uuid"
                            }
                        },
                        "versioning": {
                            "is_versioned": BLOG_POST_IS_VERSIONED,
                            "operation": "upsert_versioned"
                        },
                        "extra_fields": [
                            {
                                "src_path": "user_action",
                                "dst_path": "status"
                            },
                            {
                                "src_path": "post_uuid",
                                "dst_path": "uuid"
                            }
                        ]
                    }
                ]
            }
        },
        
        # 8. HITL Approval Node
        "content_approval": {
            "node_id": "content_approval",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "user_action": {
                        "type": "enum",
                        "enum_values": ["complete", "provide_feedback", "cancel_workflow", "draft"],
                        "required": True,
                        "description": "User's decision on the generated content"
                    },
                    "revision_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "Feedback for content improvement (required if action is revise_content)"
                    },
                    "updated_content_draft": {
                        "type": "dict",
                        "required": True,
                        "description": "Updated blog content"
                    }
                }
            }
        },
        
        # 9. Route from HITL (content approval)
        "route_content_approval": {
            "node_id": "route_content_approval",
            "node_name": "router_node",
            "node_config": {
                "choices": ["save_final_draft", "check_iteration_limit", "output_node", "save_draft"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "save_final_draft",
                        "input_path": "user_action",
                        "target_value": "complete"
                    },
                    {
                        "choice_id": "check_iteration_limit",
                        "input_path": "user_action",
                        "target_value": "provide_feedback"
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "user_action",
                        "target_value": "cancel_workflow"
                    },
                    {
                        "choice_id": "save_draft",
                        "input_path": "user_action",
                        "target_value": "draft"
                    }
                ],
                "default_choice": "output_node"
            }
        },
        
        # 10. Check Iteration Limit
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
                                "value": MAX_LLM_ITERATIONS
                            } ]
                        } ],
                        "group_logical_operator": "and"
                    }
                ],
                "branch_logic_operator": "and"
            }
        },
        
        # 11. Route Based on Iteration Limit Check
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
        
        # 12. Construct Feedback Analysis Prompt
        "construct_feedback_analysis_prompt": {
            "node_id": "construct_feedback_analysis_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "feedback_analysis_prompt": {
                        "id": "feedback_analysis_prompt",
                        "template": FEEDBACK_ANALYSIS_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "blog_content": None,
                            "user_feedback": None,
                        },
                        "construct_options": {
                            "blog_content": "blog_content",
                            "user_feedback": "user_feedback",
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": FEEDBACK_ANALYSIS_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 13. Feedback Analysis LLM with Tools
        "feedback_analysis_llm": {
            "node_id": "feedback_analysis_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": DEFAULT_LLM_PROVIDER,
                        "model": DEFAULT_LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": FEEDBACK_ANALYSIS_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False,
                }
            }
        },
        
        # 14. Construct Feedback-based Content Update Prompt
        "construct_content_update_prompt": {
            "node_id": "construct_content_update_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "content_update_prompt": {
                        "id": "content_update_prompt",
                        "template": CONTENT_UPDATE_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "original_content": None,
                            "update_instructions": None,
                        },
                        "construct_options": {
                            "original_content": "original_content",
                            "update_instructions": "update_instructions",
                        }
                    }
                }
            }
        },
        
        # 16. Output Node
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
                {"src_field": "brief_docname", "dst_field": "brief_docname"},
                {"src_field": "post_uuid", "dst_field": "post_uuid"},
                {"src_field": "initial_status", "dst_field": "initial_status"}
            ]
        },
        
        # Input -> Load All Context Documents
        {
            "src_node_id": "input_node",
            "dst_node_id": "load_all_context_docs",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "brief_docname", "dst_field": "brief_docname"}
            ]
        },
        
        # Store loaded docs in state
        {
            "src_node_id": "load_all_context_docs",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "blog_brief", "dst_field": "blog_brief"},
                {"src_field": "company_guidelines", "dst_field": "company_guidelines"},
                {"src_field": "seo_best_practices", "dst_field": "seo_best_practices"}
            ]
        },
        
        # Loaded Context Docs -> Knowledge Enrichment Prompt
        {
            "src_node_id": "load_all_context_docs",
            "dst_node_id": "construct_knowledge_enrichment_prompt"
        },
        
        # State -> Knowledge Enrichment Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_knowledge_enrichment_prompt",
            "mappings": [
                {"src_field": "blog_brief", "dst_field": "blog_brief"},
                {"src_field": "company_name", "dst_field": "company_name"}
            ]
        },
        
        # Knowledge Enrichment Prompt -> Knowledge Enrichment LLM
        {
            "src_node_id": "construct_knowledge_enrichment_prompt",
            "dst_node_id": "knowledge_enrichment_llm",
            "mappings": [
                {"src_field": "knowledge_enrichment_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "knowledge_enrichment_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Knowledge Enrichment LLM -> State (store results)
        {
            "src_node_id": "knowledge_enrichment_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "knowledge_context"},
                {"src_field": "current_messages", "dst_field": "messages_history"},
                {"src_field": "metadata", "dst_field": "generation_metadata"},
                {"src_field": "tool_calls", "dst_field": "latest_tool_calls"}
            ]
        },
        
        # Knowledge Enrichment LLM -> Check Conditions (control flow after enrichment)
        {
            "src_node_id": "knowledge_enrichment_llm",
            "dst_node_id": "check_conditions",
            "mappings": [
                {"src_field": "tool_calls", "dst_field": "tool_calls"},
                {"src_field": "structured_output", "dst_field": "knowledge_context"},
                {"src_field": "metadata", "dst_field": "generation_metadata"}
            ]
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "check_conditions",
            "mappings": [
                {"src_field": "latest_tool_calls", "dst_field": "tool_calls"},
                {"src_field": "generation_metadata", "dst_field": "generation_metadata"},
                {"src_field": "knowledge_context", "dst_field": "knowledge_context"}
            ]
        },
        
        # State -> Content Generation Prompt
        
        
        # State -> Check Conditions (pass latest tool calls and metadata)
        
        
        # Check Conditions -> Router
        {
            "src_node_id": "check_conditions",
            "dst_node_id": "route_from_conditions",
            "mappings": [
                {"src_field": "tag_results", "dst_field": "tag_results"},
                {"src_field": "condition_result", "dst_field": "condition_result"}
            ]
        },
        
        # Router -> Tool Executor (control flow)
        {
            "src_node_id": "route_from_conditions",
            "dst_node_id": "tool_executor"
        },
        
        # State -> Tool Executor (provide context)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "tool_executor",
            "mappings": [
                {"src_field": "latest_tool_calls", "dst_field": "tool_calls"},
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "view_context", "dst_field": "view_context"}
            ]
        },
        
        # Tool Executor -> State (update view context and tool outputs)
        {
            "src_node_id": "tool_executor",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "tool_outputs", "dst_field": "latest_tool_outputs"},
                {"src_field": "state_changes", "dst_field": "view_context"}
            ]
        },
        
        # Tool Executor -> Knowledge Enrichment LLM (continue the loop with tool outputs and messages)
        {
            "src_node_id": "tool_executor",
            "dst_node_id": "knowledge_enrichment_llm",
            "mappings": [
                {"src_field": "tool_outputs", "dst_field": "tool_outputs"}
            ]
        },
        
        # State -> Knowledge Enrichment LLM (messages history for next iteration)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "knowledge_enrichment_llm",
            "mappings": [
                {"src_field": "messages_history", "dst_field": "messages_history"}
            ]
        },
        
        # Router -> Construct Content Generation Prompt (control flow when no tools or limit reached)
        {
            "src_node_id": "route_from_conditions",
            "dst_node_id": "construct_content_generation_prompt"
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_content_generation_prompt",
            "mappings": [
                {"src_field": "blog_brief", "dst_field": "blog_brief"},
                {"src_field": "company_guidelines", "dst_field": "company_guidelines"},
                {"src_field": "knowledge_context", "dst_field": "knowledge_context"},
                {"src_field": "seo_best_practices", "dst_field": "seo_best_practices"}
            ]
        },
        
        # Content Generation Prompt -> Content Generation LLM
        {
            "src_node_id": "construct_content_generation_prompt",
            "dst_node_id": "content_generation_llm",
            "mappings": [
                {"src_field": "content_generation_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "content_generation_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Content Generation LLM -> State (store generated content)
        {
            "src_node_id": "content_generation_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "blog_content"},
                {"src_field": "current_messages", "dst_field": "content_generation_messages"},
                {"src_field": "metadata", "dst_field": "generation_metadata", "description": "Store LLM metadata (e.g., token usage, iteration count)."}
            ]
        },
        
        # Content Generation LLM -> HITL
        {
            "src_node_id": "content_generation_llm",
            "dst_node_id": "content_approval",
            "mappings": []
        },
        
        # Content Generation LLM -> Store Initial Draft
        {
            "src_node_id": "content_generation_llm",
            "dst_node_id": "store_draft",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "blog_content"}
            ]
        },
        
        # State -> Store Initial Draft
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "store_draft",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "post_uuid", "dst_field": "post_uuid"},
                {"src_field": "initial_status", "dst_field": "initial_status"}
            ]
        },
        
        # Store Initial Draft -> State (save paths)
        {
            "src_node_id": "store_draft",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "paths_processed", "dst_field": "draft_storage_paths"}
            ]
        },
        
        # HITL -> Router (content approval)
        {
            "src_node_id": "content_approval",
            "dst_node_id": "route_content_approval",
            "mappings": [
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        
        # HITL -> State (store user edits and action)
        {
            "src_node_id": "content_approval",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "revision_feedback", "dst_field": "current_revision_feedback"},
                {"src_field": "updated_content_draft", "dst_field": "blog_content"},
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        
        # Router -> Save Blog Post (control flow)
        {
            "src_node_id": "route_content_approval",
            "dst_node_id": "save_final_draft"
        },
        
        # State -> Save Blog Post
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_final_draft",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "blog_content", "dst_field": "blog_content"},
                {"src_field": "post_uuid", "dst_field": "post_uuid"},
                {"src_field": "brief_docname", "dst_field": "brief_docname"},
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        
        # Router -> Check Iteration Limit (control flow)
        {
            "src_node_id": "route_content_approval",
            "dst_node_id": "check_iteration_limit"
        },
        
        # State -> Check Iteration Limit (provide generation metadata)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "check_iteration_limit",
            "mappings": [
                {"src_field": "generation_metadata", "dst_field": "generation_metadata"}
            ]
        },
        
        # Check Iteration Limit -> Route on Limit Check (pass results for routing)
        {
            "src_node_id": "check_iteration_limit",
            "dst_node_id": "route_on_limit_check",
            "mappings": [
                {"src_field": "branch", "dst_field": "iteration_branch_result"},
                {"src_field": "tag_results", "dst_field": "if_else_condition_tag_results"},
                {"src_field": "condition_result", "dst_field": "if_else_overall_condition_result"}
            ]
        },
        
        # Route on Limit Check -> Construct Feedback Analysis Prompt (control flow)
        {
            "src_node_id": "route_on_limit_check",
            "dst_node_id": "construct_feedback_analysis_prompt"
        },
        
        # Route on Limit Check -> Output Node (control flow)
        {
            "src_node_id": "route_on_limit_check",
            "dst_node_id": "output_node"
        },
        
        # Router -> Save as Draft (control flow)
        {
            "src_node_id": "route_content_approval",
            "dst_node_id": "save_draft"
        },
        
        # Router -> Output Node (workflow cancelled)
        {
            "src_node_id": "route_content_approval",
            "dst_node_id": "output_node"
        },
        
        # State -> Save as Draft
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_draft",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "blog_content", "dst_field": "blog_content"},
                {"src_field": "post_uuid", "dst_field": "post_uuid"},
                {"src_field": "brief_docname", "dst_field": "brief_docname"},
                {"src_field": "initial_status", "dst_field": "initial_status"}
            ]
        },
        
        # Save Draft -> HITL (loop back)
        {
            "src_node_id": "save_draft",
            "dst_node_id": "content_approval"
        },
        
        # State -> HITL (provide current blog content back to HITL)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "content_approval",
            "mappings": [
                {"src_field": "blog_content", "dst_field": "blog_content"}
            ]
        },
        
        # State -> Feedback Analysis Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_feedback_analysis_prompt",
            "mappings": [
                {"src_field": "blog_content", "dst_field": "blog_content"},
                {"src_field": "current_revision_feedback", "dst_field": "user_feedback"}
            ]
        },
        
        # Feedback Analysis Prompt -> Feedback Analysis LLM
        {
            "src_node_id": "construct_feedback_analysis_prompt",
            "dst_node_id": "feedback_analysis_llm",
            "mappings": [
                {"src_field": "feedback_analysis_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Feedback Analysis LLM -> Content Update Prompt
        {
            "src_node_id": "feedback_analysis_llm",
            "dst_node_id": "construct_content_update_prompt",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "update_instructions"}
            ]
        },
        
        # State -> Content Update Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_content_update_prompt",
            "mappings": [
                {"src_field": "blog_content", "dst_field": "original_content"}
            ]
        },
        
        # Content Update Prompt -> Content Generation LLM (for iteration)
        {
            "src_node_id": "construct_content_update_prompt",
            "dst_node_id": "content_generation_llm",
            "mappings": [
                {"src_field": "content_update_prompt", "dst_field": "user_prompt"}            ]
        },
        
        # State -> Content Generation LLM (provide message history for iteration)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "content_generation_llm",
            "mappings": [
                {"src_field": "content_generation_messages", "dst_field": "messages_history"}
            ]
        },
        
        # Save Blog Post -> Output
        {
            "src_node_id": "save_final_draft",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "paths_processed", "dst_field": "final_blog_post_paths"}
            ]
        }
    ],
    
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    "metadata": {
        "$graph_state": {
            "reducer": {
                "messages_history": "add_messages",
                "content_generation_messages": "add_messages",
                "generation_metadata": "replace",
                "latest_tool_calls": "replace",
                "latest_tool_outputs": "replace",
                "view_context": "merge_dicts",
                "user_action": "replace"
            }
        }
    }
}


# --- Testing Code ---

async def validate_brief_to_blog_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Validate the brief to blog workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run.
        
    Returns:
        True if the outputs are valid, False otherwise.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating brief to blog workflow outputs...")
    
    # Check for expected keys
    expected_keys = ['generated_content', 'knowledge_enrichment_results']
    for key in expected_keys:
        assert key in outputs, f"Validation Failed: '{key}' key missing."
    
    # Validate generated content structure
    generated_content = outputs.get('generated_content', {})
    assert isinstance(generated_content, dict), "Validation Failed: generated_content should be a dict."
    
    # Check for essential content fields
    content_fields = ['title', 'main_content']
    for field in content_fields:
        assert field in generated_content, f"Validation Failed: '{field}' missing from generated content."
        assert generated_content[field], f"Validation Failed: '{field}' is empty."
    
    # Validate knowledge enrichment results
    knowledge_results = outputs.get('knowledge_enrichment_results', {})
    assert isinstance(knowledge_results, dict), "Validation Failed: knowledge_enrichment_results should be a dict."
    
    if 'enriched_sections' in knowledge_results:
        enriched_sections = knowledge_results['enriched_sections']
        assert isinstance(enriched_sections, list), "Validation Failed: enriched_sections should be a list."
    
    # Check if blog post was saved (optional)
    final_blog_post_paths = outputs.get('final_blog_post_paths')
    final_blog_post_data = outputs.get('final_blog_post_data')
    if final_blog_post_paths:
        logger.info("✓ Blog post was successfully saved")
        assert isinstance(final_blog_post_paths, list), "Validation Failed: final_blog_post_paths should be a list."
        logger.info(f"   Blog post saved to: {final_blog_post_paths}")
    if final_blog_post_data:
        logger.info(f"   Blog post data available: {type(final_blog_post_data)}")
    
    logger.info("✓ Output validation passed.")
    logger.info(f"   Content title: {generated_content.get('title', 'N/A')}")
    logger.info(f"   Main content length: {len(generated_content.get('main_content', ''))}")
    logger.info(f"   Knowledge sections enriched: {len(knowledge_results.get('enriched_sections', []))}")
    
    return True


async def main_test_brief_to_blog():
    """
    Test the Brief to Blog Generation Workflow.
    """
    test_name = "Brief to Blog Generation Workflow Test"
    print(f"\n--- Starting {test_name} ---")
    
    # Test parameters
    test_company_name = "momentum"
    test_brief_uuid = "test_brief_001"
    test_brief_docname = f"blog_content_brief_{test_brief_uuid}"
    
    # Create test blog brief data
    test_blog_brief_data = {
      "created_at": "2025-08-01T14:47:10.345000Z",
      "updated_at": "2025-08-01T14:47:10.360000Z",
      "title": "Conversation Intelligence ROI Calculator: Quantifying the True Value of Automated Sales Insights for Enterprise Revenue Teams",
      "content_goal": "Provide a clear methodology and downloadable calculator for quantifying the ROI of conversation intelligence platforms, helping revenue leaders build a business case for implementing these solutions while establishing our brand as a thought leader in revenue intelligence and AI-powered sales automation.",
      "seo_keywords": {
        "primary_keyword": "conversation intelligence ROI calculator",
        "long_tail_keywords": [
          "how to calculate conversation intelligence ROI",
          "measuring the value of automated sales insights",
          "quantifying time savings from CRM automation",
          "conversation intelligence business case for enterprise",
          "ROI of sales call recording and analysis",
          "how to justify conversation intelligence investment"
        ],
        "secondary_keywords": [
          "sales automation ROI",
          "CRM data entry automation",
          "revenue intelligence tools",
          "sales coaching ROI",
          "enterprise sales technology ROI"
        ]
      },
      "key_takeaways": [
        "Conversation intelligence platforms deliver measurable ROI across multiple dimensions including time savings, deal velocity, and revenue lift",
        "A structured approach to calculating ROI helps justify technology investments to finance and executive stakeholders",
        "The true value of conversation intelligence extends beyond efficiency to include improved coaching, better customer intelligence, and data-driven decision making",
        "Enterprise revenue teams can expect specific, quantifiable improvements in key metrics when implementing conversation intelligence solutions",
        "Different departments (sales, customer success, revenue operations) benefit from conversation intelligence in distinct, measurable ways"
      ],
      "call_to_action": "Download our free Conversation Intelligence ROI Calculator to build a customized business case for your organization. Enter your specific data to see potential time savings, deal velocity improvements, and revenue lift you could achieve with automated sales insights.",
      "target_audience": "Enterprise SaaS Revenue Teams, specifically Chief Revenue Officers (CROs), VPs of Sales/Sales Operations, and other revenue leaders looking to justify investments in conversation intelligence and sales automation technology.",
      "brand_guidelines": {
        "tone": "Authoritative yet approachable. Position the content as expert guidance from a trusted advisor who understands the challenges revenue leaders face. Use a consultative tone that demonstrates deep expertise while remaining accessible.",
        "voice": "Confident, data-driven, and solutions-oriented. Speak directly to revenue leaders as peers, acknowledging their challenges while providing clear, actionable solutions backed by data and expertise.",
        "style_notes": [
          "Use precise, specific language and avoid vague claims",
          "Include concrete examples and data points to support all assertions",
          "Maintain a balance between technical accuracy and readability",
          "Use active voice and direct address to engage the reader",
          "Include visual elements like charts, tables, and infographics to illustrate complex concepts",
          "Avoid jargon without explanation, but don't oversimplify complex concepts",
          "Frame the content in terms of business outcomes and value, not just features"
        ]
      },
      "difficulty_level": "Intermediate",
      "research_sources": [
        {
          "source": "WalkMe Blog: 10 Native & third-party Salesforce automation tools",
          "key_insights": [
            "AI chatbots and real-time automation are emerging as key tools for Salesforce data entry",
            "Third-party tools often provide more specialized functionality than native Salesforce options",
            "Integration capabilities are critical for seamless workflow automation"
          ]
        },
        {
          "source": "Momentum.io: Which Tools Help in Automating Salesforce Data Entry? 2025 Buyer's Guide",
          "key_insights": [
            "Key features of leading automation platforms include AI-powered data capture and analysis",
            "RevOps teams prioritize tools that maintain data hygiene and accuracy",
            "Common pitfalls include solutions that require extensive customization or lack scalability"
          ]
        },
        {
          "source": "Reddit Research: User Questions on Salesforce Automation",
          "key_insights": [
            "12 mentions of questions about automating Salesforce data entry to save time",
            "9 mentions seeking tools to improve CRM data hygiene and accuracy",
            "7 mentions looking for ways to extract actionable insights from customer conversations",
            "6 mentions seeking to automate post-call tasks and reduce administrative overhead"
          ]
        },
        {
          "source": "Industry Benchmark: Conversation Intelligence Impact Study (2023)",
          "key_insights": [
            "Enterprise sales teams report an average 23% reduction in administrative time after implementing conversation intelligence",
            "Organizations using AI for sales insights see 12-18% improvements in deal velocity",
            "Companies with mature conversation intelligence programs report 7-15% higher win rates"
          ]
        }
      ],
      "content_structure": [
        {
          "section": "Introduction: The Challenge of Quantifying Conversation Intelligence ROI",
          "word_count": 300,
          "description": "Set the context by discussing why it's difficult but essential to quantify the ROI of conversation intelligence platforms. Highlight the pressure revenue leaders face to justify technology investments with hard numbers. Introduce the calculator as a solution to this challenge."
        },
        {
          "section": "Understanding the Full Value Spectrum of Conversation Intelligence",
          "word_count": 500,
          "description": "Break down the various ways conversation intelligence creates value: time savings from automated data entry, improved deal velocity from better insights, revenue lift from coaching opportunities, reduced churn from better customer intelligence, etc. Include real examples and statistics where possible."
        },
        {
          "section": "The ROI Calculator: Methodology and Approach",
          "word_count": 400,
          "description": "Explain the methodology behind the calculator. Detail the key inputs (team size, average deal size, sales cycle length, etc.) and how they factor into the calculations. Provide transparency into the formulas and assumptions used."
        },
        {
          "section": "Time Savings: Quantifying the Value of Automated Data Entry and Task Reduction",
          "word_count": 400,
          "description": "Focus specifically on calculating the value of time saved through automated data entry, automated meeting summaries, and reduced administrative tasks. Include formulas for converting time savings to monetary value based on fully-loaded employee costs."
        },
        {
          "section": "Deal Velocity Improvements: Measuring the Impact on Sales Cycle Length",
          "word_count": 400,
          "description": "Detail how to calculate the value of shortened sales cycles through better visibility into deal progression, faster identification of deal risks, and improved follow-up processes. Include the time value of money concept."
        },
        {
          "section": "Revenue Lift: Quantifying the Impact of Better Coaching and Deal Execution",
          "word_count": 450,
          "description": "Explain how to measure revenue increases from improved coaching effectiveness, better sales execution, and increased win rates. Include formulas for calculating the expected lift based on industry benchmarks and case studies."
        },
        {
          "section": "Customer Success Impact: Calculating Reduced Churn and Expansion Revenue",
          "word_count": 400,
          "description": "Focus on the ROI for customer success teams, including formulas for calculating the value of reduced churn and increased expansion revenue through better customer intelligence and proactive issue identification."
        },
        {
          "section": "Putting It All Together: Your Total Conversation Intelligence ROI",
          "word_count": 350,
          "description": "Explain how to combine all the individual ROI components into a comprehensive business case. Include guidance on presenting the results to executives and finance teams, with tips on addressing common objections."
        },
        {
          "section": "Case Study: How [Enterprise Company] Achieved 327% ROI with Conversation Intelligence",
          "word_count": 400,
          "description": "Present a detailed case study of an enterprise company that successfully implemented conversation intelligence and measured the results. Include specific metrics, challenges overcome, and lessons learned."
        },
        {
          "section": "Conclusion and Next Steps: Building Your Business Case",
          "word_count": 200,
          "description": "Summarize the key points and provide clear next steps for readers to download the calculator and begin building their own ROI analysis. Include a brief overview of implementation considerations to set expectations."
        }
      ],
      "estimated_word_count": 3800,
      "writing_instructions": [
        "Include real-world examples and specific metrics throughout the article to make the ROI calculations tangible",
        "Create or source at least 3 visual elements: 1) a sample ROI calculation, 2) a flowchart of the ROI methodology, and 3) a before/after comparison showing impact of conversation intelligence",
        "Incorporate direct quotes or insights from industry experts or customers to add credibility",
        "Include specific formulas and calculation methods that readers can apply to their own situations",
        "Balance technical detail with clear explanations - assume the reader is knowledgeable about sales processes but may not be a financial or technical expert",
        "Ensure the content addresses the specific pain points of all three ICPs (Enterprise SaaS Revenue Teams, Growth-Stage Sales Organizations, and Customer Success Teams)",
        "Reference the downloadable calculator throughout the article, not just in the conclusion",
        "Use subheadings, bullet points, and numbered lists to make the content scannable and actionable",
        "Include a brief section addressing common objections or concerns about ROI calculations for conversation intelligence"
      ],
      "uuid": "e9a0b9e5-cc45-4794-92ce-b0eb18282161",
      "status": "complete"
    }
    
    # Create test company guidelines data
    test_company_data = {
        "name": "momentum",
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
    
    # Setup test documents
    setup_docs: List[SetupDocInfo] = [
        # Blog brief document
        {
            'namespace': f"blog_brief_namespace_{test_company_name}",
            'docname': test_brief_docname,
            'initial_data': test_blog_brief_data,
            'is_shared': False,
            'is_versioned': True,
            'initial_version': "default",
            'is_system_entity': False
        },
        # Company guidelines document
        {
            'namespace': f"blog_company_profile_{test_company_name}",
            'docname': BLOG_COMPANY_DOCNAME,
            'initial_data': test_company_data,
            'is_shared': False,
            'is_versioned': False,
            'initial_version': "None",
            'is_system_entity': False
        },

        {
            'namespace': f"blog_uploaded_files_{test_company_name}",
            'docname': "ai_marketing_trends_2024",
            'initial_data': {
                "title": "AI Marketing Trends 2024",
                "content": "Recent studies show 73% of marketers use AI tools for content creation. Key trends include automated personalization, predictive analytics, and AI-powered customer segmentation.",
                "statistics": ["73% adoption rate", "40% efficiency improvement", "25% cost reduction"],
                "case_studies": ["Company X increased engagement by 150% using AI personalization"]
            },
            'is_shared': False,
            'is_versioned': False,
            'initial_version': "None",
            'is_system_entity': False
        }
    ]
    
    # Cleanup configuration
    cleanup_docs: List[CleanupDocInfo] = [
        {
            'namespace': f"blog_content_creation_{test_company_name}",
            'docname': test_brief_docname,
            'is_shared': False,
            'is_versioned': True,
            'is_system_entity': False
        },
        {
            'namespace': f"blog_company_profile_{test_company_name}",
            'docname': BLOG_COMPANY_DOCNAME,
            'is_shared': False,
            'is_versioned': False,
            'is_system_entity': False
        },
    ]
    
    # Test scenario
    test_scenario = {
        "name": "Generate Blog Content from Brief",
        "initial_inputs": {
            "company_name": test_company_name,
            "brief_docname": test_brief_docname,
            "post_uuid": f"blog_post_{test_brief_uuid}"
        }
    }
    
    # Predefined HITL inputs for comprehensive testing
    predefined_hitl_inputs = [
        # 1) Content approval: provide feedback first (triggers revision loop)
        # {
        #     "user_action": "provide_feedback",
        #     "revision_feedback": "Great foundation! Please strengthen the introduction with a more compelling hook that directly addresses the pain point of revenue leaders struggling to justify technology investments. Also, add more specific ROI calculation examples in the methodology section, and include at least one real-world case study with actual numbers.",
        #     "updated_content_draft": {
        #         "title": "Conversation Intelligence ROI Calculator: Quantifying the True Value of Automated Sales Insights for Enterprise Revenue Teams",
        #         "main_content": "# Conversation Intelligence ROI Calculator: Quantifying the True Value of Automated Sales Insights for Enterprise Revenue Teams\n\nRevenue leaders face mounting pressure to justify every technology investment with hard numbers. When it comes to conversation intelligence platforms, the benefits are clear—but quantifying them can be challenging. This comprehensive guide provides a structured methodology and downloadable calculator to help you build a compelling business case for conversation intelligence implementation.\n\n## Understanding the Full Value Spectrum of Conversation Intelligence\n\nConversation intelligence creates value across multiple dimensions:\n\n### Time Savings from Automation\n- Automated CRM data entry saves 2-3 hours per rep per week\n- Automated meeting summaries reduce administrative overhead by 40%\n- Real-time insights eliminate manual call analysis\n\n### Deal Velocity Improvements\n- Better visibility into deal progression accelerates sales cycles by 12-18%\n- Early risk identification prevents deal slippage\n- Improved follow-up processes based on conversation insights\n\n### Revenue Lift from Better Execution\n- Enhanced coaching effectiveness increases win rates by 7-15%\n- Better customer intelligence drives expansion opportunities\n- Data-driven decision making improves forecast accuracy\n\n## The ROI Calculator: Methodology and Approach\n\nOur calculator uses a comprehensive methodology that considers:\n\n1. **Team Size and Composition**: Sales reps, managers, and customer success team members\n2. **Deal Metrics**: Average deal size, sales cycle length, and win rates\n3. **Time Investment**: Current time spent on administrative tasks\n4. **Fully-Loaded Costs**: Total compensation including benefits and overhead\n\n### Key Formula Components\n\n**Time Savings Value** = (Hours Saved × Hourly Rate × Team Size) × 52 weeks\n**Deal Velocity Value** = (Deal Size × Deal Volume × Velocity Improvement %) × Time Value of Money\n**Revenue Lift Value** = (Current Revenue × Win Rate Improvement %) - Platform Costs\n\n## Implementation and Next Steps\n\nTo get started with your ROI calculation:\n\n1. Download our free ROI calculator\n2. Input your specific metrics\n3. Review the projected returns\n4. Present the business case to stakeholders\n\nThe calculator provides conservative, realistic, and optimistic scenarios to help you build confidence in your projections.\n\n## Conclusion\n\nConversation intelligence delivers measurable ROI across time savings, deal velocity, and revenue lift. With the right methodology and tools, you can build a compelling business case that demonstrates clear value to your organization.\n\n*Ready to calculate your ROI? Download our free Conversation Intelligence ROI Calculator and start building your business case today.*"
        #     }
        # },
        # # 2) Content approval: save as draft (test draft functionality)
        # {
        #     "user_action": "draft",
        #     "revision_feedback": None,
        #     "updated_content_draft": {
        #         "title": "Conversation Intelligence ROI Calculator: Quantifying the True Value of Automated Sales Insights for Enterprise Revenue Teams",
        #         "main_content": "# Conversation Intelligence ROI Calculator: Quantifying the True Value of Automated Sales Insights for Enterprise Revenue Teams\n\n*Revenue leaders, this one's for you.* You know conversation intelligence works—but proving its worth to the C-suite requires hard numbers. This comprehensive guide provides a structured methodology and downloadable calculator to build an ironclad business case for conversation intelligence implementation.\n\n## The Challenge: Quantifying Intangible Benefits\n\nRevenue leaders face mounting pressure to justify every technology investment with concrete ROI. When it comes to conversation intelligence platforms, the benefits are clear—better coaching, cleaner CRM data, faster deal cycles—but quantifying them can feel like catching smoke.\n\nThe solution? A systematic approach to measuring value across three critical dimensions.\n\n## Understanding the Full Value Spectrum of Conversation Intelligence\n\nConversation intelligence creates measurable value across multiple areas:\n\n### Time Savings: The Efficiency Multiplier\n- **Automated CRM data entry**: Saves 2-3 hours per rep per week\n- **Automated meeting summaries**: Reduces administrative overhead by 40%\n- **Real-time insights**: Eliminates manual call analysis and note-taking\n- **Streamlined coaching prep**: Managers spend 60% less time preparing for coaching sessions\n\n**Example Calculation**: A 50-person sales team saving 2.5 hours per week at $75/hour fully-loaded cost = $487,500 annual value\n\n### Deal Velocity: Accelerating Revenue Recognition\n- **Better visibility**: Deal progression insights accelerate sales cycles by 12-18%\n- **Early risk identification**: Prevents deal slippage through proactive intervention\n- **Improved follow-up**: Conversation insights drive more effective prospect engagement\n- **Faster onboarding**: New reps reach productivity 30% faster\n\n**Example Impact**: Reducing a 90-day sales cycle by 15% (13.5 days) on $50K average deals with 20 deals per month = $1.5M additional quarterly revenue recognition\n\n### Revenue Lift: The Coaching and Intelligence Advantage\n- **Enhanced coaching effectiveness**: Increases win rates by 7-15%\n- **Better customer intelligence**: Drives expansion opportunities and reduces churn\n- **Data-driven decision making**: Improves forecast accuracy by 25%\n- **Competitive intelligence**: Win rates improve 12% when competitive mentions are tracked\n\n## The ROI Calculator: Methodology and Approach\n\nOur calculator uses a comprehensive methodology that considers:\n\n### Input Variables\n1. **Team Composition**: Sales reps, managers, customer success team members\n2. **Deal Metrics**: Average deal size, sales cycle length, monthly deal volume, current win rates\n3. **Time Investment**: Current hours spent on administrative tasks, coaching prep, data entry\n4. **Cost Structure**: Fully-loaded employee costs including benefits and overhead\n5. **Platform Costs**: Subscription fees, implementation costs, training investment\n\n### Core Calculation Framework\n\n**Time Savings Value** = (Hours Saved × Fully-Loaded Hourly Rate × Team Size) × 52 weeks\n\n**Deal Velocity Value** = (Average Deal Size × Monthly Deal Volume × Velocity Improvement %) × (12 months / Original Cycle Length) × Time Value of Money Factor\n\n**Revenue Lift Value** = (Current Annual Revenue × Win Rate Improvement %) - (Platform Annual Cost)\n\n**Total ROI** = (Time Savings + Deal Velocity + Revenue Lift - Platform Costs) / Platform Costs × 100\n\n### Time Savings: Quantifying the Value of Automated Data Entry and Task Reduction\n\nThe most immediate and measurable benefit comes from automation:\n\n- **CRM Data Entry**: Average rep spends 2.1 hours/week on data entry\n- **Meeting Notes and Summaries**: 1.2 hours/week per rep\n- **Call Analysis and Coaching Prep**: 3.5 hours/week per manager\n- **Follow-up Task Creation**: 0.8 hours/week per rep\n\n**Formula**: Weekly Hours Saved × Fully-Loaded Hourly Cost × Team Size × 52 weeks\n\n**Example**: 25 reps saving 3.1 hours/week + 5 managers saving 3.5 hours/week at $85 average hourly cost = $425,100 annual value\n\n### Deal Velocity Improvements: Measuring the Impact on Sales Cycle Length\n\nConversation intelligence accelerates deals through:\n- **Better qualification**: Faster identification of qualified opportunities\n- **Proactive risk management**: Early intervention prevents stalled deals\n- **Improved follow-up**: Conversation insights drive more effective engagement\n- **Enhanced discovery**: Better questions lead to stronger value propositions\n\n**Industry Benchmarks**:\n- 12-18% average cycle time reduction\n- 20% improvement in deal progression visibility\n- 15% increase in qualified opportunity identification\n\n**Time Value Formula**: (Cycle Reduction Days / Original Cycle Days) × Annual Deal Value × Cost of Capital\n\n### Revenue Lift: Quantifying the Impact of Better Coaching and Deal Execution\n\nThe most significant long-term value comes from improved performance:\n\n**Coaching Effectiveness**:\n- Conversation intelligence provides objective coaching data\n- Win rates improve 7-15% with consistent coaching\n- Rep performance variance decreases by 25%\n- Time to productivity for new hires reduces by 30%\n\n**Deal Execution**:\n- Better discovery leads to stronger proposals\n- Competitive intelligence improves positioning\n- Customer insights drive expansion opportunities\n- Churn prediction enables proactive retention\n\n**Calculation**: (Current Annual Revenue × Performance Improvement %) - Platform Investment\n\n### Customer Success Impact: Calculating Reduced Churn and Expansion Revenue\n\nFor customer success teams, conversation intelligence delivers:\n- **Churn Reduction**: 15-25% improvement in retention through early warning signals\n- **Expansion Revenue**: 20% increase in upsell/cross-sell identification\n- **Customer Health Scoring**: Proactive intervention prevents account deterioration\n- **Onboarding Success**: New customer time-to-value improves by 30%\n\n**Customer Success ROI**: (Churn Reduction Value + Expansion Revenue Increase) - (Platform Allocation + Team Time Investment)\n\n## Putting It All Together: Your Total Conversation Intelligence ROI\n\nCombining all components into a comprehensive business case:\n\n### Sample Enterprise Calculation (500-person revenue team)\n\n**Time Savings**: $2.1M annually\n- 400 reps × 3 hours/week × $75/hour × 52 weeks = $2,340,000\n- Less 10% productivity adjustment = $2,106,000\n\n**Deal Velocity**: $3.2M additional revenue recognition\n- 15% cycle reduction on $120M annual bookings\n- Accelerated cash flow value = $3,200,000\n\n**Revenue Lift**: $8.4M incremental revenue\n- 10% win rate improvement on $84M annual pipeline\n- Net of platform costs = $8,400,000\n\n**Total Value**: $13.7M\n**Platform Investment**: $1.2M\n**Net ROI**: 1,042%\n**Payback Period**: 1.3 months\n\n### Presenting to Executives: Addressing Common Objections\n\n**\"The numbers seem too good to be true\"**\n- Provide conservative, realistic, and optimistic scenarios\n- Use industry benchmarks and peer references\n- Offer pilot program with limited scope\n\n**\"What about implementation risk?\"**\n- Phase rollout to minimize disruption\n- Provide detailed change management plan\n- Include training and adoption costs in calculations\n\n**\"How do we measure success?\"**\n- Establish baseline metrics before implementation\n- Create monthly tracking dashboard\n- Set up quarterly business reviews\n\n## Case Study: How TechFlow Achieved 327% ROI with Conversation Intelligence\n\nTechFlow, a 200-employee SaaS company, implemented conversation intelligence across their revenue team:\n\n**Challenge**: Manual CRM updates, inconsistent coaching, poor pipeline visibility\n\n**Implementation**: 6-month rollout across 75 revenue team members\n\n**Results after 12 months**:\n- **Time Savings**: $485,000 (2.8 hours/week per rep)\n- **Deal Velocity**: 22% faster sales cycles = $1.2M additional quarterly revenue\n- **Revenue Lift**: 12% win rate improvement = $2.8M additional bookings\n- **Total Value**: $4.485M\n- **Investment**: $375K (platform + implementation)\n- **ROI**: 1,096%\n\n**Key Success Factors**:\n1. Executive sponsorship and clear success metrics\n2. Gradual rollout with extensive training\n3. Integration with existing sales methodology\n4. Regular coaching and adoption reinforcement\n\n## Conclusion and Next Steps: Building Your Business Case\n\nConversation intelligence delivers measurable ROI across time savings, deal velocity, and revenue lift. The key is using a structured methodology that captures all value dimensions while accounting for implementation costs and risks.\n\n### Your Action Plan:\n\n1. **Download the Calculator**: Get our free ROI calculator with pre-built formulas\n2. **Gather Your Data**: Collect current metrics on team size, deal flow, and time allocation\n3. **Run the Numbers**: Calculate conservative, realistic, and optimistic scenarios\n4. **Build Your Presentation**: Create executive summary with key metrics and implementation plan\n5. **Address Objections**: Prepare responses to common concerns and risk mitigation strategies\n\n### Implementation Considerations:\n\n- **Change Management**: Plan for 6-8 weeks of adoption curve\n- **Training Investment**: Budget 2-3 hours per user for initial training\n- **Integration Complexity**: Factor in CRM and other tool integrations\n- **Success Metrics**: Establish baseline measurements before implementation\n\nThe data is clear: conversation intelligence delivers significant, measurable ROI for revenue teams. With the right approach to quantification and presentation, you can build a compelling business case that demonstrates clear value to your organization.\n\n*Ready to calculate your ROI? Download our free Conversation Intelligence ROI Calculator and start building your business case today. Include your team size and average deal metrics to get customized projections for your organization.*"
        #     }
        # },
        # # 3) Content approval: provide feedback again for another revision
        # {
        #     "user_action": "provide_feedback",
        #     "revision_feedback": "Excellent improvement! The content is much more comprehensive and engaging. Please make two final adjustments: 1) Add a brief executive summary section at the top highlighting the key ROI numbers, and 2) Include a specific call-to-action section with next steps for downloading the calculator.",
        #     "updated_content_draft": {
        #         "title": "Conversation Intelligence ROI Calculator: Quantifying the True Value of Automated Sales Insights for Enterprise Revenue Teams",
        #         "main_content": "# Conversation Intelligence ROI Calculator: Quantifying the True Value of Automated Sales Insights for Enterprise Revenue Teams\n\n## Executive Summary\n\n**The Bottom Line**: Conversation intelligence platforms deliver measurable ROI averaging 327-1,042% for enterprise revenue teams through three key value drivers:\n\n- **Time Savings**: $2.1M annually for a 500-person team through automated data entry and administrative task reduction\n- **Deal Velocity**: $3.2M in accelerated revenue recognition through 15% faster sales cycles  \n- **Revenue Lift**: $8.4M in incremental revenue from 10% win rate improvements via better coaching and execution\n\n**Typical Payback Period**: 1-3 months | **Implementation Investment**: $1-3M | **Net Annual Value**: $10-15M\n\n---\n\n*Revenue leaders, this one's for you.* You know conversation intelligence works—but proving its worth to the C-suite requires hard numbers. This comprehensive guide provides a structured methodology and downloadable calculator to build an ironclad business case for conversation intelligence implementation.\n\n## The Challenge: Quantifying Intangible Benefits\n\nRevenue leaders face mounting pressure to justify every technology investment with concrete ROI. When it comes to conversation intelligence platforms, the benefits are clear—better coaching, cleaner CRM data, faster deal cycles—but quantifying them can feel like catching smoke.\n\nThe solution? A systematic approach to measuring value across three critical dimensions.\n\n## Understanding the Full Value Spectrum of Conversation Intelligence\n\nConversation intelligence creates measurable value across multiple areas:\n\n### Time Savings: The Efficiency Multiplier\n- **Automated CRM data entry**: Saves 2-3 hours per rep per week\n- **Automated meeting summaries**: Reduces administrative overhead by 40%\n- **Real-time insights**: Eliminates manual call analysis and note-taking\n- **Streamlined coaching prep**: Managers spend 60% less time preparing for coaching sessions\n\n**Example Calculation**: A 50-person sales team saving 2.5 hours per week at $75/hour fully-loaded cost = $487,500 annual value\n\n### Deal Velocity: Accelerating Revenue Recognition\n- **Better visibility**: Deal progression insights accelerate sales cycles by 12-18%\n- **Early risk identification**: Prevents deal slippage through proactive intervention\n- **Improved follow-up**: Conversation insights drive more effective prospect engagement\n- **Faster onboarding**: New reps reach productivity 30% faster\n\n**Example Impact**: Reducing a 90-day sales cycle by 15% (13.5 days) on $50K average deals with 20 deals per month = $1.5M additional quarterly revenue recognition\n\n### Revenue Lift: The Coaching and Intelligence Advantage\n- **Enhanced coaching effectiveness**: Increases win rates by 7-15%\n- **Better customer intelligence**: Drives expansion opportunities and reduces churn\n- **Data-driven decision making**: Improves forecast accuracy by 25%\n- **Competitive intelligence**: Win rates improve 12% when competitive mentions are tracked\n\n## The ROI Calculator: Methodology and Approach\n\nOur calculator uses a comprehensive methodology that considers:\n\n### Input Variables\n1. **Team Composition**: Sales reps, managers, customer success team members\n2. **Deal Metrics**: Average deal size, sales cycle length, monthly deal volume, current win rates\n3. **Time Investment**: Current hours spent on administrative tasks, coaching prep, data entry\n4. **Cost Structure**: Fully-loaded employee costs including benefits and overhead\n5. **Platform Costs**: Subscription fees, implementation costs, training investment\n\n### Core Calculation Framework\n\n**Time Savings Value** = (Hours Saved × Fully-Loaded Hourly Rate × Team Size) × 52 weeks\n\n**Deal Velocity Value** = (Average Deal Size × Monthly Deal Volume × Velocity Improvement %) × (12 months / Original Cycle Length) × Time Value of Money Factor\n\n**Revenue Lift Value** = (Current Annual Revenue × Win Rate Improvement %) - (Platform Annual Cost)\n\n**Total ROI** = (Time Savings + Deal Velocity + Revenue Lift - Platform Costs) / Platform Costs × 100\n\n### Time Savings: Quantifying the Value of Automated Data Entry and Task Reduction\n\nThe most immediate and measurable benefit comes from automation:\n\n- **CRM Data Entry**: Average rep spends 2.1 hours/week on data entry\n- **Meeting Notes and Summaries**: 1.2 hours/week per rep\n- **Call Analysis and Coaching Prep**: 3.5 hours/week per manager\n- **Follow-up Task Creation**: 0.8 hours/week per rep\n\n**Formula**: Weekly Hours Saved × Fully-Loaded Hourly Cost × Team Size × 52 weeks\n\n**Example**: 25 reps saving 3.1 hours/week + 5 managers saving 3.5 hours/week at $85 average hourly cost = $425,100 annual value\n\n### Deal Velocity Improvements: Measuring the Impact on Sales Cycle Length\n\nConversation intelligence accelerates deals through:\n- **Better qualification**: Faster identification of qualified opportunities\n- **Proactive risk management**: Early intervention prevents stalled deals\n- **Improved follow-up**: Conversation insights drive more effective engagement\n- **Enhanced discovery**: Better questions lead to stronger value propositions\n\n**Industry Benchmarks**:\n- 12-18% average cycle time reduction\n- 20% improvement in deal progression visibility\n- 15% increase in qualified opportunity identification\n\n**Time Value Formula**: (Cycle Reduction Days / Original Cycle Days) × Annual Deal Value × Cost of Capital\n\n### Revenue Lift: Quantifying the Impact of Better Coaching and Deal Execution\n\nThe most significant long-term value comes from improved performance:\n\n**Coaching Effectiveness**:\n- Conversation intelligence provides objective coaching data\n- Win rates improve 7-15% with consistent coaching\n- Rep performance variance decreases by 25%\n- Time to productivity for new hires reduces by 30%\n\n**Deal Execution**:\n- Better discovery leads to stronger proposals\n- Competitive intelligence improves positioning\n- Customer insights drive expansion opportunities\n- Churn prediction enables proactive retention\n\n**Calculation**: (Current Annual Revenue × Performance Improvement %) - Platform Investment\n\n### Customer Success Impact: Calculating Reduced Churn and Expansion Revenue\n\nFor customer success teams, conversation intelligence delivers:\n- **Churn Reduction**: 15-25% improvement in retention through early warning signals\n- **Expansion Revenue**: 20% increase in upsell/cross-sell identification\n- **Customer Health Scoring**: Proactive intervention prevents account deterioration\n- **Onboarding Success**: New customer time-to-value improves by 30%\n\n**Customer Success ROI**: (Churn Reduction Value + Expansion Revenue Increase) - (Platform Allocation + Team Time Investment)\n\n## Putting It All Together: Your Total Conversation Intelligence ROI\n\nCombining all components into a comprehensive business case:\n\n### Sample Enterprise Calculation (500-person revenue team)\n\n**Time Savings**: $2.1M annually\n- 400 reps × 3 hours/week × $75/hour × 52 weeks = $2,340,000\n- Less 10% productivity adjustment = $2,106,000\n\n**Deal Velocity**: $3.2M additional revenue recognition\n- 15% cycle reduction on $120M annual bookings\n- Accelerated cash flow value = $3,200,000\n\n**Revenue Lift**: $8.4M incremental revenue\n- 10% win rate improvement on $84M annual pipeline\n- Net of platform costs = $8,400,000\n\n**Total Value**: $13.7M\n**Platform Investment**: $1.2M\n**Net ROI**: 1,042%\n**Payback Period**: 1.3 months\n\n### Presenting to Executives: Addressing Common Objections\n\n**\"The numbers seem too good to be true\"**\n- Provide conservative, realistic, and optimistic scenarios\n- Use industry benchmarks and peer references\n- Offer pilot program with limited scope\n\n**\"What about implementation risk?\"**\n- Phase rollout to minimize disruption\n- Provide detailed change management plan\n- Include training and adoption costs in calculations\n\n**\"How do we measure success?\"**\n- Establish baseline metrics before implementation\n- Create monthly tracking dashboard\n- Set up quarterly business reviews\n\n## Case Study: How TechFlow Achieved 327% ROI with Conversation Intelligence\n\nTechFlow, a 200-employee SaaS company, implemented conversation intelligence across their revenue team:\n\n**Challenge**: Manual CRM updates, inconsistent coaching, poor pipeline visibility\n\n**Implementation**: 6-month rollout across 75 revenue team members\n\n**Results after 12 months**:\n- **Time Savings**: $485,000 (2.8 hours/week per rep)\n- **Deal Velocity**: 22% faster sales cycles = $1.2M additional quarterly revenue\n- **Revenue Lift**: 12% win rate improvement = $2.8M additional bookings\n- **Total Value**: $4.485M\n- **Investment**: $375K (platform + implementation)\n- **ROI**: 1,096%\n\n**Key Success Factors**:\n1. Executive sponsorship and clear success metrics\n2. Gradual rollout with extensive training\n3. Integration with existing sales methodology\n4. Regular coaching and adoption reinforcement\n\n## Conclusion and Next Steps: Building Your Business Case\n\nConversation intelligence delivers measurable ROI across time savings, deal velocity, and revenue lift. The key is using a structured methodology that captures all value dimensions while accounting for implementation costs and risks.\n\n### Your Action Plan:\n\n1. **Download the Calculator**: Get our free ROI calculator with pre-built formulas\n2. **Gather Your Data**: Collect current metrics on team size, deal flow, and time allocation\n3. **Run the Numbers**: Calculate conservative, realistic, and optimistic scenarios\n4. **Build Your Presentation**: Create executive summary with key metrics and implementation plan\n5. **Address Objections**: Prepare responses to common concerns and risk mitigation strategies\n\n### Implementation Considerations:\n\n- **Change Management**: Plan for 6-8 weeks of adoption curve\n- **Training Investment**: Budget 2-3 hours per user for initial training\n- **Integration Complexity**: Factor in CRM and other tool integrations\n- **Success Metrics**: Establish baseline measurements before implementation\n\n## Get Your Free ROI Calculator Now\n\n**Ready to build your business case?** Download our comprehensive Conversation Intelligence ROI Calculator and start quantifying your potential returns today.\n\n**What's Included:**\n- Pre-built formulas for all ROI calculations\n- Industry benchmark data and assumptions\n- Customizable inputs for your specific situation\n- Conservative, realistic, and optimistic scenarios\n- Executive presentation template\n- Implementation timeline and checklist\n\n**[Download the Free ROI Calculator →]**\n\n**Need help with your analysis?** Our team of revenue operations experts can provide a customized ROI assessment for your organization. **[Schedule a 15-minute consultation →]**\n\n---\n\n*The data is clear: conversation intelligence delivers significant, measurable ROI for revenue teams. With the right approach to quantification and presentation, you can build a compelling business case that demonstrates clear value to your organization.*"
        #     }
        # },
        # # 4) Content approval: complete (final approval and save)
        # {
        #     "user_action": "complete",
        #     "revision_feedback": None,
        #     "updated_content_draft": {
        #         "title": "Conversation Intelligence ROI Calculator: Quantifying the True Value of Automated Sales Insights for Enterprise Revenue Teams",
        #         "main_content": "# Conversation Intelligence ROI Calculator: Quantifying the True Value of Automated Sales Insights for Enterprise Revenue Teams\n\n## Executive Summary\n\n**The Bottom Line**: Conversation intelligence platforms deliver measurable ROI averaging 327-1,042% for enterprise revenue teams through three key value drivers:\n\n- **Time Savings**: $2.1M annually for a 500-person team through automated data entry and administrative task reduction\n- **Deal Velocity**: $3.2M in accelerated revenue recognition through 15% faster sales cycles  \n- **Revenue Lift**: $8.4M in incremental revenue from 10% win rate improvements via better coaching and execution\n\n**Typical Payback Period**: 1-3 months | **Implementation Investment**: $1-3M | **Net Annual Value**: $10-15M\n\n---\n\n*Revenue leaders, this one's for you.* You know conversation intelligence works—but proving its worth to the C-suite requires hard numbers. This comprehensive guide provides a structured methodology and downloadable calculator to build an ironclad business case for conversation intelligence implementation.\n\n## The Challenge: Quantifying Intangible Benefits\n\nRevenue leaders face mounting pressure to justify every technology investment with concrete ROI. When it comes to conversation intelligence platforms, the benefits are clear—better coaching, cleaner CRM data, faster deal cycles—but quantifying them can feel like catching smoke.\n\nThe solution? A systematic approach to measuring value across three critical dimensions.\n\n## Understanding the Full Value Spectrum of Conversation Intelligence\n\nConversation intelligence creates measurable value across multiple areas:\n\n### Time Savings: The Efficiency Multiplier\n- **Automated CRM data entry**: Saves 2-3 hours per rep per week\n- **Automated meeting summaries**: Reduces administrative overhead by 40%\n- **Real-time insights**: Eliminates manual call analysis and note-taking\n- **Streamlined coaching prep**: Managers spend 60% less time preparing for coaching sessions\n\n**Example Calculation**: A 50-person sales team saving 2.5 hours per week at $75/hour fully-loaded cost = $487,500 annual value\n\n### Deal Velocity: Accelerating Revenue Recognition\n- **Better visibility**: Deal progression insights accelerate sales cycles by 12-18%\n- **Early risk identification**: Prevents deal slippage through proactive intervention\n- **Improved follow-up**: Conversation insights drive more effective prospect engagement\n- **Faster onboarding**: New reps reach productivity 30% faster\n\n**Example Impact**: Reducing a 90-day sales cycle by 15% (13.5 days) on $50K average deals with 20 deals per month = $1.5M additional quarterly revenue recognition\n\n### Revenue Lift: The Coaching and Intelligence Advantage\n- **Enhanced coaching effectiveness**: Increases win rates by 7-15%\n- **Better customer intelligence**: Drives expansion opportunities and reduces churn\n- **Data-driven decision making**: Improves forecast accuracy by 25%\n- **Competitive intelligence**: Win rates improve 12% when competitive mentions are tracked\n\n## The ROI Calculator: Methodology and Approach\n\nOur calculator uses a comprehensive methodology that considers:\n\n### Input Variables\n1. **Team Composition**: Sales reps, managers, customer success team members\n2. **Deal Metrics**: Average deal size, sales cycle length, monthly deal volume, current win rates\n3. **Time Investment**: Current hours spent on administrative tasks, coaching prep, data entry\n4. **Cost Structure**: Fully-loaded employee costs including benefits and overhead\n5. **Platform Costs**: Subscription fees, implementation costs, training investment\n\n### Core Calculation Framework\n\n**Time Savings Value** = (Hours Saved × Fully-Loaded Hourly Rate × Team Size) × 52 weeks\n\n**Deal Velocity Value** = (Average Deal Size × Monthly Deal Volume × Velocity Improvement %) × (12 months / Original Cycle Length) × Time Value of Money Factor\n\n**Revenue Lift Value** = (Current Annual Revenue × Win Rate Improvement %) - (Platform Annual Cost)\n\n**Total ROI** = (Time Savings + Deal Velocity + Revenue Lift - Platform Costs) / Platform Costs × 100\n\n### Time Savings: Quantifying the Value of Automated Data Entry and Task Reduction\n\nThe most immediate and measurable benefit comes from automation:\n\n- **CRM Data Entry**: Average rep spends 2.1 hours/week on data entry\n- **Meeting Notes and Summaries**: 1.2 hours/week per rep\n- **Call Analysis and Coaching Prep**: 3.5 hours/week per manager\n- **Follow-up Task Creation**: 0.8 hours/week per rep\n\n**Formula**: Weekly Hours Saved × Fully-Loaded Hourly Cost × Team Size × 52 weeks\n\n**Example**: 25 reps saving 3.1 hours/week + 5 managers saving 3.5 hours/week at $85 average hourly cost = $425,100 annual value\n\n### Deal Velocity Improvements: Measuring the Impact on Sales Cycle Length\n\nConversation intelligence accelerates deals through:\n- **Better qualification**: Faster identification of qualified opportunities\n- **Proactive risk management**: Early intervention prevents stalled deals\n- **Improved follow-up**: Conversation insights drive more effective engagement\n- **Enhanced discovery**: Better questions lead to stronger value propositions\n\n**Industry Benchmarks**:\n- 12-18% average cycle time reduction\n- 20% improvement in deal progression visibility\n- 15% increase in qualified opportunity identification\n\n**Time Value Formula**: (Cycle Reduction Days / Original Cycle Days) × Annual Deal Value × Cost of Capital\n\n### Revenue Lift: Quantifying the Impact of Better Coaching and Deal Execution\n\nThe most significant long-term value comes from improved performance:\n\n**Coaching Effectiveness**:\n- Conversation intelligence provides objective coaching data\n- Win rates improve 7-15% with consistent coaching\n- Rep performance variance decreases by 25%\n- Time to productivity for new hires reduces by 30%\n\n**Deal Execution**:\n- Better discovery leads to stronger proposals\n- Competitive intelligence improves positioning\n- Customer insights drive expansion opportunities\n- Churn prediction enables proactive retention\n\n**Calculation**: (Current Annual Revenue × Performance Improvement %) - Platform Investment\n\n### Customer Success Impact: Calculating Reduced Churn and Expansion Revenue\n\nFor customer success teams, conversation intelligence delivers:\n- **Churn Reduction**: 15-25% improvement in retention through early warning signals\n- **Expansion Revenue**: 20% increase in upsell/cross-sell identification\n- **Customer Health Scoring**: Proactive intervention prevents account deterioration\n- **Onboarding Success**: New customer time-to-value improves by 30%\n\n**Customer Success ROI**: (Churn Reduction Value + Expansion Revenue Increase) - (Platform Allocation + Team Time Investment)\n\n## Putting It All Together: Your Total Conversation Intelligence ROI\n\nCombining all components into a comprehensive business case:\n\n### Sample Enterprise Calculation (500-person revenue team)\n\n**Time Savings**: $2.1M annually\n- 400 reps × 3 hours/week × $75/hour × 52 weeks = $2,340,000\n- Less 10% productivity adjustment = $2,106,000\n\n**Deal Velocity**: $3.2M additional revenue recognition\n- 15% cycle reduction on $120M annual bookings\n- Accelerated cash flow value = $3,200,000\n\n**Revenue Lift**: $8.4M incremental revenue\n- 10% win rate improvement on $84M annual pipeline\n- Net of platform costs = $8,400,000\n\n**Total Value**: $13.7M\n**Platform Investment**: $1.2M\n**Net ROI**: 1,042%\n**Payback Period**: 1.3 months\n\n### Presenting to Executives: Addressing Common Objections\n\n**\"The numbers seem too good to be true\"**\n- Provide conservative, realistic, and optimistic scenarios\n- Use industry benchmarks and peer references\n- Offer pilot program with limited scope\n\n**\"What about implementation risk?\"**\n- Phase rollout to minimize disruption\n- Provide detailed change management plan\n- Include training and adoption costs in calculations\n\n**\"How do we measure success?\"**\n- Establish baseline metrics before implementation\n- Create monthly tracking dashboard\n- Set up quarterly business reviews\n\n## Case Study: How TechFlow Achieved 327% ROI with Conversation Intelligence\n\nTechFlow, a 200-employee SaaS company, implemented conversation intelligence across their revenue team:\n\n**Challenge**: Manual CRM updates, inconsistent coaching, poor pipeline visibility\n\n**Implementation**: 6-month rollout across 75 revenue team members\n\n**Results after 12 months**:\n- **Time Savings**: $485,000 (2.8 hours/week per rep)\n- **Deal Velocity**: 22% faster sales cycles = $1.2M additional quarterly revenue\n- **Revenue Lift**: 12% win rate improvement = $2.8M additional bookings\n- **Total Value**: $4.485M\n- **Investment**: $375K (platform + implementation)\n- **ROI**: 1,096%\n\n**Key Success Factors**:\n1. Executive sponsorship and clear success metrics\n2. Gradual rollout with extensive training\n3. Integration with existing sales methodology\n4. Regular coaching and adoption reinforcement\n\n## Conclusion and Next Steps: Building Your Business Case\n\nConversation intelligence delivers measurable ROI across time savings, deal velocity, and revenue lift. The key is using a structured methodology that captures all value dimensions while accounting for implementation costs and risks.\n\n### Your Action Plan:\n\n1. **Download the Calculator**: Get our free ROI calculator with pre-built formulas\n2. **Gather Your Data**: Collect current metrics on team size, deal flow, and time allocation\n3. **Run the Numbers**: Calculate conservative, realistic, and optimistic scenarios\n4. **Build Your Presentation**: Create executive summary with key metrics and implementation plan\n5. **Address Objections**: Prepare responses to common concerns and risk mitigation strategies\n\n### Implementation Considerations:\n\n- **Change Management**: Plan for 6-8 weeks of adoption curve\n- **Training Investment**: Budget 2-3 hours per user for initial training\n- **Integration Complexity**: Factor in CRM and other tool integrations\n- **Success Metrics**: Establish baseline measurements before implementation\n\nThe data is clear: conversation intelligence delivers significant, measurable ROI for revenue teams. With the right approach to quantification and presentation, you can build a compelling business case that demonstrates clear value to your organization.\n\n*Ready to calculate your ROI? Download our free Conversation Intelligence ROI Calculator and start building your business case today. Include your team size and average deal metrics to get customized projections for your organization.*"
        #     }
        # }
    ]
    
    print(f"\n--- Running Scenario: {test_scenario['name']} ---")
    
    try:
        final_status, final_outputs = await run_workflow_test(
            test_name=f"{test_name} - {test_scenario['name']}",
            workflow_graph_schema=workflow_graph_schema,
            initial_inputs=test_scenario['initial_inputs'],
            expected_final_status=WorkflowRunStatus.COMPLETED,
            hitl_inputs=predefined_hitl_inputs,
            setup_docs=setup_docs,
            cleanup_docs=cleanup_docs,
            cleanup_docs_created_by_setup=False,
            validate_output_func=validate_brief_to_blog_output,
            stream_intermediate_results=True,
            poll_interval_sec=3,
            timeout_sec=1800
        )
        
        # Display results
        if final_outputs:
            print(f"\nTest Results:")
            generated_content = final_outputs.get('generated_content', {})
            print(f"Generated Title: {generated_content.get('title', 'N/A')}")
            print(f"Content Length: {len(generated_content.get('main_content', ''))} characters")
            
            knowledge_results = final_outputs.get('knowledge_enrichment_results', {})
            enriched_sections = knowledge_results.get('enriched_sections', [])
            print(f"Knowledge Sections Enriched: {len(enriched_sections)}")
            
            if final_outputs.get('final_blog_post_paths'):
                print("✓ Blog post was successfully saved")
                print(f"Saved to: {final_outputs.get('final_blog_post_paths')}")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
    
    print(f"\n--- {test_name} Completed Successfully ---")


# Entry point
if __name__ == "__main__":
    print("="*60)
    print("Brief to Blog Generation Workflow Test")
    print("="*60)
    
    try:
        asyncio.run(main_test_brief_to_blog())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.exception("Test execution failed")
    
    print("\nTest execution finished.")
    print("Run from project root: PYTHONPATH=. python kiwi_client/workflows_for_blog_teammate/wf_brief_to_blog.py")
