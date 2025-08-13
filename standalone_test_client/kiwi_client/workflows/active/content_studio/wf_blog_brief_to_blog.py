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
    BLOG_SEO_BEST_PRACTICES_IS_VERSIONED,
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
LLM_PROVIDER = "openai"  # anthropic    openai
LLM_MODEL = "gpt-4.1"  # o4-mini   gpt-4.1    claude-sonnet-4-20250514
TEMPERATURE = 0.7
MAX_TOKENS = 4000
MAX_TOOL_CALLS = 15  # Maximum total tool calls allowed
MAX_LLM_ITERATIONS = 10  # Maximum LLM loop iterations

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
                        },
                        "construct_options": {
                            "blog_brief": "blog_brief",
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
                        "provider": LLM_PROVIDER,
                        "model": LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS
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
                    },
                    {
                        "tool_name": "view_documents",
                        "is_provider_inbuilt_tool": False,
                        "provider_inbuilt_user_config": {}
                    },
                    {
                        "tool_name": "list_documents",
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
        
        # 5. Construct Content Generation Prompt
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
                            "seo_best_practices": None,
                            "company_guidelines": None,
                        },
                        "construct_options": {
                            "blog_brief": "blog_brief",
                            "knowledge_context": "knowledge_context",
                            "seo_best_practices": "seo_best_practices",
                            "company_guidelines": "company_guidelines",
                        }
                    },
                    "content_generation_system_prompt": {
                        "id": "content_generation_system_prompt",
                        "template": CONTENT_GENERATION_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 6. Content Generation LLM
        "content_generation_llm": {
            "node_id": "content_generation_llm",
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
                    "schema_definition": CONTENT_GENERATION_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False,
                }
            }
        },
        
        # 7. HITL Approval Node
        "content_approval": {
            "node_id": "content_approval",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "user_action": {
                        "type": "enum",
                        "enum_values": ["save_content", "provide_feedback"],
                        "required": True,
                        "description": "User's decision on the generated content"
                    },
                    "user_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "User feedback for content improvement (required if action is provide_feedback)"
                    }
                }
            }
        },
        
        # 8. Route from HITL
        "route_from_hitl": {
            "node_id": "route_from_hitl",
            "node_name": "router_node",
            "node_config": {
                "choices": ["save_blog_post", "check_iteration_limit"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "save_blog_post",
                        "input_path": "user_action",
                        "target_value": "save_content"
                    },
                    {
                        "choice_id": "check_iteration_limit",
                        "input_path": "user_action",
                        "target_value": "provide_feedback"
                    }
                ]
            }
        },
        
        # 9. Check Iteration Limit
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
        
        # 10. Route Based on Iteration Limit Check
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
        
        # 11. Construct Feedback Analysis Prompt
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
        
        # 10. Feedback Analysis LLM with Tools
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
                    "schema_definition": FEEDBACK_ANALYSIS_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False,
                }
            }
        },
        
        # 11. Construct Feedback-based Content Update Prompt
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
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": CONTENT_GENERATION_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 12. Save Blog Post Document
        "save_blog_post": {
            "node_id": "save_blog_post",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": True,
                    "operation": "initialize",  # Must not exist yet
                    "version": "draft_v1"  # Name the initial version
                },
                "store_configs": [
                    {
                        "input_field_path": "blog_content",  # Source field containing the blog content
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_POST_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "input_docname_field_pattern": BLOG_POST_DOCNAME,
                                "input_docname_field": "post_uuid",
                            }
                        },
                        "versioning": {
                            "is_versioned": BLOG_POST_IS_VERSIONED,
                            "operation": "upsert_versioned",
                        }
                    }
                ]
            }
        },
        
        # 13. Output Node
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
                {"src_field": "post_uuid", "dst_field": "post_uuid"}
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
                {"src_field": "blog_brief", "dst_field": "blog_brief"}
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
                {"src_field": "structured_output", "dst_field": "knowledge_context"}
            ]
        },
        
        # State -> Content Generation Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_content_generation_prompt",
            "mappings": [
                {"src_field": "blog_brief", "dst_field": "blog_brief"},
                {"src_field": "company_guidelines", "dst_field": "company_guidelines"},
                {"src_field": "seo_best_practices", "dst_field": "seo_best_practices"}
            ]
        },
        
        # Knowledge Enrichment LLM -> Content Generation Prompt
        {
            "src_node_id": "knowledge_enrichment_llm",
            "dst_node_id": "construct_content_generation_prompt",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "knowledge_context"}
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
            "mappings": [
                {"src_field": "structured_output", "dst_field": "generated_content"}
            ]
        },
        
        # HITL -> Router
        {
            "src_node_id": "content_approval",
            "dst_node_id": "route_from_hitl",
            "mappings": [
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        
        # HITL -> State (store user feedback)
        {
            "src_node_id": "content_approval",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "user_feedback", "dst_field": "user_feedback"}
            ]
        },
        
        # Router -> Save Blog Post (control flow)
        {
            "src_node_id": "route_from_hitl",
            "dst_node_id": "save_blog_post"
        },
        
        # State -> Save Blog Post
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_blog_post",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "blog_content", "dst_field": "blog_content"},
                {"src_field": "post_uuid", "dst_field": "post_uuid"},
                {"src_field": "brief_docname", "dst_field": "brief_docname"}
            ]
        },
        
        # Router -> Check Iteration Limit (control flow)
        {
            "src_node_id": "route_from_hitl",
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
        
        # State -> Feedback Analysis Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_feedback_analysis_prompt",
            "mappings": [
                {"src_field": "blog_content", "dst_field": "blog_content"},
                {"src_field": "user_feedback", "dst_field": "user_feedback"}
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
                {"src_field": "content_update_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
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
            "src_node_id": "save_blog_post",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "paths_processed", "dst_field": "final_blog_post_paths"},
                {"src_field": "passthrough_data", "dst_field": "final_blog_post_data"}
            ]
        }
    ],
    
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    "metadata": {
        "$graph_state": {
            "reducer": {
                "content_generation_messages": "add_messages",
                "generation_metadata": "replace"
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
    test_company_name = "Momentum"
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
    
    # Create test SEO best practices data
    test_seo_data = {
        "title_best_practices": [
            "Include primary keyword in title",
            "Keep titles between 50-60 characters",
            "Make titles compelling and clickable"
        ],
        "content_optimization": [
            "Use header tags (H1, H2, H3) for structure",
            "Include keywords naturally throughout content",
            "Optimize for featured snippets with clear answers",
            "Use internal and external links strategically"
        ],
        "meta_description_guidelines": [
            "Keep between 150-160 characters",
            "Include primary keyword",
            "Write compelling copy that encourages clicks"
        ]
    }
    
    # Setup test documents
    setup_docs: List[SetupDocInfo] = [
        # Blog brief document
        {
            'namespace': f"blog_content_creation_{test_company_name}",
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
            'initial_version': None,
            'is_system_entity': False
        },
        # SEO best practices document (System Document)
        {
            'namespace': BLOG_SEO_BEST_PRACTICES_NAMESPACE_TEMPLATE,
            'docname': BLOG_SEO_BEST_PRACTICES_DOCNAME,
            'initial_data': test_seo_data,
            'is_shared': BLOG_SEO_BEST_PRACTICES_IS_SHARED,
            'is_versioned': BLOG_SEO_BEST_PRACTICES_IS_VERSIONED,
            'initial_version': None,
            'is_system_entity': BLOG_SEO_BEST_PRACTICES_IS_SYSTEM_ENTITY
        },
        # Knowledge base documents for enrichment
        {
            'namespace': f"knowledge_base_{test_company_name}",
            'docname': "ai_marketing_trends_2024",
            'initial_data': {
                "title": "AI Marketing Trends 2024",
                "content": "Recent studies show 73% of marketers use AI tools for content creation. Key trends include automated personalization, predictive analytics, and AI-powered customer segmentation.",
                "statistics": ["73% adoption rate", "40% efficiency improvement", "25% cost reduction"],
                "case_studies": ["Company X increased engagement by 150% using AI personalization"]
            },
            'is_shared': False,
            'is_versioned': False,
            'initial_version': None,
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
        {
            'namespace': BLOG_SEO_BEST_PRACTICES_NAMESPACE_TEMPLATE,
            'docname': BLOG_SEO_BEST_PRACTICES_DOCNAME,
            'is_shared': BLOG_SEO_BEST_PRACTICES_IS_SHARED,
            'is_versioned': BLOG_SEO_BEST_PRACTICES_IS_VERSIONED,
            'is_system_entity': BLOG_SEO_BEST_PRACTICES_IS_SYSTEM_ENTITY
        },
        {
            'namespace': f"knowledge_base_{test_company_name}",
            'docname': "ai_marketing_trends_2024",
            'is_shared': False,
            'is_versioned': False,
            'is_system_entity': False
        }
    ]
    
    # Test scenario
    test_scenario = {
        "name": "Generate Blog Content from Brief",
        "initial_inputs": {
            "company_name": test_company_name,
            "brief_docname": test_brief_docname,
            "post_uuid": f"blog_post_{test_brief_uuid}"
        },
        # Example HITL inputs for testing (can be used manually)
        # "hitl_inputs": [
        #     {
        #         "user_action": "save_content",
        #         "user_feedback": ""
        #     }
        # ]
    }
    
    print(f"\n--- Running Scenario: {test_scenario['name']} ---")
    
    try:
        final_status, final_outputs = await run_workflow_test(
            test_name=f"{test_name} - {test_scenario['name']}",
            workflow_graph_schema=workflow_graph_schema,
            initial_inputs=test_scenario['initial_inputs'],
            expected_final_status=WorkflowRunStatus.COMPLETED,
            hitl_inputs=test_scenario.get('hitl_inputs', None),
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
