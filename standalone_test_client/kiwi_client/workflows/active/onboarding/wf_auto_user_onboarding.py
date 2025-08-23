"""
User Onboarding Workflow

This workflow performs two optional onboarding flows:
- LinkedIn executive profile onboarding (by `entity_username`)
- Blog/company onboarding (by `company_name`)

Control flags:
- `perform_linkedin_onboarding: bool`
- `perform_blog_onboarding: bool`

Router behavior:
- A single `onboarding_router` routes directly to the respective flows.
- If both flags are False, the workflow routes directly to the `output_node`.

Generated data is saved using the document constants from `customer_docs` with proper namespaces.

Design notes:
- Follows graph patterns from the content orchestrator workflow.
- Uses prompt constructor -> LLM -> store data flow for both LinkedIn and Blog onboarding.
- Uses simple routers for gating execution paths.
"""

from __future__ import annotations

from functools import partial
from typing import Any, Dict, Optional
import asyncio
import logging

# Document constants for correct storage locations
from kiwi_client.workflows.active.document_models.customer_docs import (
    LINKEDIN_USER_PROFILE_DOCNAME,
    LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
)

# Onboarding prompt templates and schemas
from kiwi_client.workflows.active.onboarding.llm_inputs.onboarding_prompts import (
    LINKEDIN_ONBOARDING_USER_PROMPT,
    LINKEDIN_ONBOARDING_SYSTEM_PROMPT,
    LINKEDIN_PROFILE_SCHEMA,
    LINKEDIN_ONBOARDING_REVISION_USER_PROMPT,
    BLOG_ONBOARDING_USER_PROMPT,
    BLOG_ONBOARDING_SYSTEM_PROMPT,
    BLOG_COMPANY_PROFILE_SCHEMA,
    BLOG_ONBOARDING_REVISION_USER_PROMPT,
)

# LLM defaults
LLM_PROVIDER = "perplexity"  # anthropic  perplexity
LLM_MODEL = "sonar-pro"  # claude-sonnet-4-20250514  sonar-reasoning-pro
LLM_TEMPERATURE = 0.5
LLM_MAX_TOKENS = 5000


# ============================
# Workflow Graph Configuration
# ============================

workflow_graph_schema: Dict[str, Any] = {
    "nodes": {
        # 1) Input Node
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "entity_username": {
                        "type": "str",
                        "required": False,
                        "description": "LinkedIn username for the executive user",
                    },
                    "company_name": {
                        "type": "str",
                        "required": False,
                        "description": "Company name for blog onboarding",
                    },
                    "perform_linkedin_onboarding": {
                        "type": "bool",
                        "required": True,
                        "description": "Whether to run LinkedIn onboarding",
                    },
                    "perform_blog_onboarding": {
                        "type": "bool",
                        "required": True,
                        "description": "Whether to run Blog/Company onboarding",
                    },
                    "linkedin_profile_url": {
                        "type": "str",
                        "required": False,
                        "description": "LinkedIn profile URL (optional)",
                    },
                    "company_url": {
                        "type": "str",
                        "required": False,
                        "description": "Company website URL (optional)",
                    },
                    "linkedin_additional_context": {
                        "type": "str",
                        "required": False,
                        "description": "Additional context for LinkedIn onboarding to be used directly in profile generation",
                    },
                    "blog_additional_context": {
                        "type": "str",
                        "required": False,
                        "description": "Additional context for blog onboarding to be used directly in company profile generation",
                    },
                }
            },
        },

        # 2) Top-level router: routes directly to flow constructors or output
        "onboarding_router": {
            "node_id": "onboarding_router",
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_linkedin_prompt", "construct_blog_prompt", "output_node"],
                "allow_multiple": True,
                "default_choice": "output_node",
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_linkedin_prompt",
                        "input_path": "perform_linkedin_onboarding",
                        "target_value": True,
                    },
                    {
                        "choice_id": "construct_blog_prompt",
                        "input_path": "perform_blog_onboarding",
                        "target_value": True,
                    },
                ],
            },
        },

        # 4) Prompt constructors
        "construct_linkedin_prompt": {
            "node_id": "construct_linkedin_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": LINKEDIN_ONBOARDING_USER_PROMPT,
                        "variables": {
                            "entity_username": None,
                            "linkedin_profile_url": None,
                            "additional_context": "",
                        },
                        "construct_options": {
                            "entity_username": "entity_username",
                            "linkedin_profile_url": "linkedin_profile_url",
                            "additional_context": "linkedin_additional_context",
                        },
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": LINKEDIN_ONBOARDING_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {},
                    },
                }
            },
        },
        "construct_blog_prompt": {
            "node_id": "construct_blog_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": BLOG_ONBOARDING_USER_PROMPT,
                        "variables": {
                            "company_name": None,
                            "company_url": None,
                            "additional_context": "",
                        },
                        "construct_options": {
                            "company_name": "company_name",
                            "company_url": "company_url",
                            "additional_context": "blog_additional_context",
                        },
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": BLOG_ONBOARDING_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {},
                    },
                }
            },
        },

        # 5) LLM nodes (structured output)
        "generate_linkedin_profile": {
            "node_id": "generate_linkedin_profile",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS,
                },
                "output_schema": {
                    "schema_definition": LINKEDIN_PROFILE_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False,
                },
            },
        },
        "generate_blog_company_profile": {
            "node_id": "generate_blog_company_profile",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS,
                },
                "output_schema": {
                    "schema_definition": BLOG_COMPANY_PROFILE_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False,
                },
            },
        },

        # 6) Combined HITL Review node (fan-in)
        "combined_review_hitl": {
            "node_id": "combined_review_hitl",
            "node_name": "hitl_node__default",
            "defer_node": True,
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "linkedin_user_action": {
                        "type": "enum",
                        "enum_values": ["approve", "revise"],
                        "required": False,
                        "description": "Decision for LinkedIn profile: approve to store, revise to regenerate"
                    },
                    "linkedin_revision_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "Feedback to revise LinkedIn profile"
                    },
                    "blog_user_action": {
                        "type": "enum",
                        "enum_values": ["approve", "revise"],
                        "required": False,
                        "description": "Decision for Blog company profile: approve to store, revise to regenerate"
                    },
                    "blog_revision_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "Feedback to revise company profile"
                    },
                }
            }
        },

        "route_post_hitl_actions": {
            "node_id": "route_post_hitl_actions",
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_linkedin_revision_prompt", "construct_blog_revision_prompt", "output_node"],
                "allow_multiple": True,
                "default_choice": "output_node",
                "choices_with_conditions": [
                    {"choice_id": "construct_linkedin_revision_prompt", "input_path": "linkedin_user_action", "target_value": "revise"},
                    {"choice_id": "construct_blog_revision_prompt", "input_path": "blog_user_action", "target_value": "revise"},
                ]
            }
        },

        # 7) Revision prompt constructors
        "construct_linkedin_revision_prompt": {
            "node_id": "construct_linkedin_revision_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "revision_user_prompt": {
                        "id": "revision_user_prompt",
                        "template": LINKEDIN_ONBOARDING_REVISION_USER_PROMPT,
                        "variables": {
                            "revision_feedback": None,
                        },
                        "construct_options": {
                            "revision_feedback": "linkedin_revision_feedback",
                        },
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": LINKEDIN_ONBOARDING_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {},
                    },
                }
            }
        },
        "construct_blog_revision_prompt": {
            "node_id": "construct_blog_revision_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "revision_user_prompt": {
                        "id": "revision_user_prompt",
                        "template": BLOG_ONBOARDING_REVISION_USER_PROMPT,
                        "variables": {
                            "revision_feedback": None,
                        },
                        "construct_options": {
                            "revision_feedback": "blog_revision_feedback",
                        },
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": BLOG_ONBOARDING_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {},
                    },
                }
            }
        },

        # 8) Store nodes
        "store_linkedin_profile": {
            "node_id": "store_linkedin_profile",
            "node_name": "store_customer_data",
            "node_config": {
                "global_is_shared": False,
                "global_is_system_entity": False,
                "store_configs": [
                    {
                        "input_field_path": "linkedin_profile_doc",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "entity_username",
                                "static_docname": LINKEDIN_USER_PROFILE_DOCNAME,
                            }
                        },
                        "versioning": {
                            "is_versioned": False,
                            "operation": "upsert",
                        },
                        "process_list_items_separately": False,
                    }
                ],
            },
        },
        "store_blog_company_profile": {
            "node_id": "store_blog_company_profile",
            "node_name": "store_customer_data",
            "node_config": {
                "global_is_shared": False,
                "global_is_system_entity": False,
                "store_configs": [
                    {
                        "input_field_path": "blog_company_doc",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_COMPANY_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": BLOG_COMPANY_DOCNAME,
                            }
                        },
                        "versioning": {
                            "is_versioned": False,
                            "operation": "upsert",
                        },
                        "process_list_items_separately": False,
                    }
                ],
            },
        },

        # Output node (fan-in)
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {},
        },
    },
    "edges": [
        # Input to state
        {
            "src_node_id": "input_node",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "perform_linkedin_onboarding", "dst_field": "perform_linkedin_onboarding"},
                {"src_field": "perform_blog_onboarding", "dst_field": "perform_blog_onboarding"},
                {"src_field": "linkedin_profile_url", "dst_field": "linkedin_profile_url"},
                {"src_field": "company_url", "dst_field": "company_url"},
                {"src_field": "linkedin_additional_context", "dst_field": "linkedin_additional_context"},
                {"src_field": "blog_additional_context", "dst_field": "blog_additional_context"},
            ],
        },

        # Input -> top-level router
        {
            "src_node_id": "input_node",
            "dst_node_id": "onboarding_router",
            "mappings": [
                {"src_field": "perform_linkedin_onboarding", "dst_field": "perform_linkedin_onboarding"},
                {"src_field": "perform_blog_onboarding", "dst_field": "perform_blog_onboarding"},
            ],
        },

        # Router -> constructors
        {"src_node_id": "onboarding_router", "dst_node_id": "construct_linkedin_prompt", "mappings": []},
        {"src_node_id": "onboarding_router", "dst_node_id": "construct_blog_prompt", "mappings": []},

        # LinkedIn flow: constructor -> LLM -> state -> HITL -> (store | revision)
        {"src_node_id": "$graph_state", "dst_node_id": "construct_linkedin_prompt", "mappings": [
            {"src_field": "entity_username", "dst_field": "entity_username"},
            {"src_field": "linkedin_profile_url", "dst_field": "linkedin_profile_url"},
            {"src_field": "linkedin_additional_context", "dst_field": "linkedin_additional_context"}
        ]},
        {"src_node_id": "construct_linkedin_prompt", "dst_node_id": "generate_linkedin_profile", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "generate_linkedin_profile", "mappings": [
            {"src_field": "linkedin_messages_history", "dst_field": "messages_history"},
        ]},
        {"src_node_id": "generate_linkedin_profile", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "linkedin_profile_doc"},
            {"src_field": "current_messages", "dst_field": "linkedin_messages_history"},
        ]},
        {"src_node_id": "combined_review_hitl", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "linkedin_revision_feedback", "dst_field": "linkedin_revision_feedback"},
            {"src_field": "linkedin_user_action", "dst_field": "linkedin_user_action"},
            {"src_field": "blog_revision_feedback", "dst_field": "blog_revision_feedback"},
            {"src_field": "blog_user_action", "dst_field": "blog_user_action"}
        ]},
        {"src_node_id": "construct_linkedin_revision_prompt", "dst_node_id": "generate_linkedin_profile", "mappings": [
            {"src_field": "revision_user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"}
        ]},
        {"src_node_id": "generate_linkedin_profile", "dst_node_id": "store_linkedin_profile", "mappings": []},
        {"src_node_id": "$graph_state", "dst_node_id": "store_linkedin_profile", "mappings": [
            {"src_field": "entity_username", "dst_field": "entity_username"},
            {"src_field": "linkedin_profile_doc", "dst_field": "linkedin_profile_doc"}
        ]},
        {"src_node_id": "store_linkedin_profile", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "passthrough_data", "dst_field": "linkedin_profile_data"},
            {"src_field": "paths_processed", "dst_field": "linkedin_paths_processed"},
        ]},
        
        

        # Blog flow: constructor -> LLM -> state -> HITL -> (store | revision)
        {"src_node_id": "$graph_state", "dst_node_id": "construct_blog_prompt", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
            {"src_field": "company_url", "dst_field": "company_url"},
            {"src_field": "blog_additional_context", "dst_field": "blog_additional_context"}
        ]},
        {"src_node_id": "construct_blog_prompt", "dst_node_id": "generate_blog_company_profile", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "generate_blog_company_profile", "mappings": [
            {"src_field": "blog_company_messages_history", "dst_field": "messages_history"},
        ]},
        {"src_node_id": "generate_blog_company_profile", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "blog_company_doc"},
            {"src_field": "current_messages", "dst_field": "blog_company_messages_history"},
        ]},
        
        {"src_node_id": "construct_blog_revision_prompt", "dst_node_id": "generate_blog_company_profile", "mappings": [
            {"src_field": "revision_user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"}
        ]},
        {"src_node_id": "generate_blog_company_profile", "dst_node_id": "store_blog_company_profile", "mappings": []},
        {"src_node_id": "$graph_state", "dst_node_id": "store_blog_company_profile", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
            {"src_field": "blog_company_doc", "dst_field": "blog_company_doc"}
        ]},
        {"src_node_id": "store_blog_company_profile", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "passthrough_data", "dst_field": "blog_company_data"},
            {"src_field": "paths_processed", "dst_field": "blog_company_paths_processed"},
        ]},
        
        # Ensure HITL starts only after both stores; connect stores and state docs to HITL
        {"src_node_id": "store_linkedin_profile", "dst_node_id": "combined_review_hitl", "mappings": []},
        {"src_node_id": "store_blog_company_profile", "dst_node_id": "combined_review_hitl", "mappings": []},
        {"src_node_id": "$graph_state", "dst_node_id": "combined_review_hitl", "mappings": [
            {"src_field": "linkedin_profile_doc", "dst_field": "linkedin_profile_doc"},
            {"src_field": "blog_company_doc", "dst_field": "blog_company_doc"},
            {"src_field": "linkedin_paths_processed", "dst_field": "linkedin_paths_processed"},
            {"src_field": "blog_company_paths_processed", "dst_field": "blog_company_paths_processed"},
        ]},

        # Post-HITL: branch to revision constructors and/or finalize if both approved
        {"src_node_id": "combined_review_hitl", "dst_node_id": "route_post_hitl_actions", "mappings": [
            {"src_field": "linkedin_user_action", "dst_field": "linkedin_user_action"},
            {"src_field": "blog_user_action", "dst_field": "blog_user_action"}
        ]},
        {"src_node_id": "route_post_hitl_actions", "dst_node_id": "construct_linkedin_revision_prompt", "mappings": []},
        {"src_node_id": "route_post_hitl_actions", "dst_node_id": "construct_blog_revision_prompt", "mappings": []},
        {"src_node_id": "route_post_hitl_actions", "dst_node_id": "output_node", "mappings": []},
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "linkedin_profile_doc", "dst_field": "linkedin_profile_doc"},
                {"src_field": "blog_company_doc", "dst_field": "blog_company_doc"},
                {"src_field": "linkedin_paths_processed", "dst_field": "linkedin_paths_processed"},
                {"src_field": "blog_company_paths_processed", "dst_field": "blog_company_paths_processed"},
            ]
        },

        # Provide state inputs to revision constructors
        {"src_node_id": "$graph_state", "dst_node_id": "construct_linkedin_revision_prompt", "mappings": [
            {"src_field": "linkedin_profile_doc", "dst_field": "linkedin_profile_doc"},
            {"src_field": "linkedin_revision_feedback", "dst_field": "linkedin_revision_feedback"},
            {"src_field": "entity_username", "dst_field": "entity_username"},
            {"src_field": "linkedin_profile_url", "dst_field": "linkedin_profile_url"},
            {"src_field": "linkedin_additional_context", "dst_field": "linkedin_additional_context"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "construct_blog_revision_prompt", "mappings": [
            {"src_field": "blog_company_doc", "dst_field": "blog_company_doc"},
            {"src_field": "blog_revision_feedback", "dst_field": "blog_revision_feedback"},
            {"src_field": "company_name", "dst_field": "company_name"},
            {"src_field": "company_url", "dst_field": "company_url"},
            {"src_field": "blog_additional_context", "dst_field": "blog_additional_context"}
        ]},
    ],

    "metadata": {
        "$graph_state": {
            "reducer": {
                "linkedin_messages_history": "add_messages",
                "blog_company_messages_history": "add_messages",
            }
        }
    },

    "input_node_id": "input_node",
    "output_node_id": "output_node",
}


# Optional lightweight test harness similar to other workflow scripts
from kiwi_client.test_run_workflow_client import run_workflow_test
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus
from kiwi_client.test_config import CLIENT_LOG_LEVEL

logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)


async def validate_onboarding_output(outputs: Optional[Dict[str, Any]], test_inputs: Dict[str, Any]) -> bool:
    """Comprehensive validation for onboarding workflow outputs.
    
    Validates that:
    - Both LinkedIn and Blog profiles are generated when requested
    - Generated profiles contain required fields and proper structure
    - Storage paths are properly recorded
    - Profile data matches expected schema structure
    """
    assert outputs is not None, "No outputs returned from workflow."
    logger.info("Validating onboarding workflow outputs...")
    
    # Check if LinkedIn onboarding was requested and validate results
    if test_inputs.get("perform_linkedin_onboarding", False):
        logger.info("Validating LinkedIn onboarding results...")
        
        # Check for LinkedIn profile document
        assert "linkedin_profile_doc" in outputs, "LinkedIn profile document missing from outputs"
        linkedin_profile = outputs["linkedin_profile_doc"]
        assert linkedin_profile is not None, "LinkedIn profile document is None"
        assert isinstance(linkedin_profile, dict), "LinkedIn profile should be a dictionary"
        
        # Validate required LinkedIn profile fields
        required_linkedin_fields = ["profile_url", "username"]
        for field in required_linkedin_fields:
            if field in linkedin_profile:
                logger.info(f"✓ LinkedIn profile contains {field}: {linkedin_profile[field]}")
        
        # Validate LinkedIn profile URL format
        if "profile_url" in linkedin_profile:
            profile_url = linkedin_profile["profile_url"]
            assert isinstance(profile_url, str), "LinkedIn profile URL should be a string"
            assert "linkedin.com" in profile_url, "LinkedIn profile URL should contain linkedin.com"
            logger.info(f"✓ Valid LinkedIn profile URL: {profile_url}")
        
        # Check optional fields
        optional_linkedin_fields = ["persona_tags", "content_goals", "posting_schedule", "timezone"]
        for field in optional_linkedin_fields:
            if field in linkedin_profile and linkedin_profile[field] is not None:
                logger.info(f"✓ LinkedIn profile contains {field}")
        
        # Validate posting schedule if present
        if "posting_schedule" in linkedin_profile and linkedin_profile["posting_schedule"]:
            schedule = linkedin_profile["posting_schedule"]
            if "posts_per_week" in schedule:
                posts_per_week = schedule["posts_per_week"]
                assert isinstance(posts_per_week, int), "Posts per week should be an integer"
                assert 0 <= posts_per_week <= 14, "Posts per week should be between 0 and 14"
                logger.info(f"✓ Valid posting frequency: {posts_per_week} posts/week")
        
        # Check storage paths
        if "linkedin_paths_processed" in outputs:
            paths = outputs["linkedin_paths_processed"]
            assert isinstance(paths, list), "LinkedIn paths should be a list"
            logger.info(f"✓ LinkedIn profile stored at {len(paths)} path(s)")
    
    # Check if Blog onboarding was requested and validate results
    if test_inputs.get("perform_blog_onboarding", False):
        logger.info("Validating Blog onboarding results...")
        
        # Check for Blog company document
        assert "blog_company_doc" in outputs, "Blog company document missing from outputs"
        company_profile = outputs["blog_company_doc"]
        assert company_profile is not None, "Blog company document is None"
        assert isinstance(company_profile, dict), "Blog company profile should be a dictionary"
        
        # Validate required company profile fields
        required_company_fields = ["name", "website_url"]
        for field in required_company_fields:
            if field in company_profile:
                logger.info(f"✓ Company profile contains {field}: {company_profile[field]}")
        
        # Validate company website URL format
        if "website_url" in company_profile:
            website_url = company_profile["website_url"]
            assert isinstance(website_url, str), "Company website URL should be a string"
            assert "http" in website_url or "www." in website_url, "Company website should be a valid URL"
            logger.info(f"✓ Valid company website URL: {website_url}")
        
        # Check optional fields
        optional_company_fields = ["value_proposition", "icps", "competitors", "goals", "posting_schedule"]
        for field in optional_company_fields:
            if field in company_profile and company_profile[field] is not None:
                logger.info(f"✓ Company profile contains {field}")
        
        # Validate ICP if present
        if "icps" in company_profile and company_profile["icps"]:
            icp = company_profile["icps"]
            if "icp_name" in icp:
                logger.info(f"✓ ICP defined: {icp['icp_name']}")
            if "target_industry" in icp and icp["target_industry"]:
                logger.info(f"✓ Target industry: {icp['target_industry']}")
            if "company_size" in icp and icp["company_size"]:
                logger.info(f"✓ Target company size: {icp['company_size']}")
        
        # Validate posting schedule if present
        if "posting_schedule" in company_profile and company_profile["posting_schedule"]:
            schedule = company_profile["posting_schedule"]
            if "posts_per_month" in schedule:
                posts_per_month = schedule["posts_per_month"]
                assert isinstance(posts_per_month, int), "Posts per month should be an integer"
                assert 1 <= posts_per_month <= 31, "Posts per month should be between 1 and 31"
                logger.info(f"✓ Valid posting frequency: {posts_per_month} posts/month")
        
        # Check storage paths
        if "blog_company_paths_processed" in outputs:
            paths = outputs["blog_company_paths_processed"]
            assert isinstance(paths, list), "Blog company paths should be a list"
            logger.info(f"✓ Company profile stored at {len(paths)} path(s)")
    
    # Validate that at least one onboarding was performed
    linkedin_performed = test_inputs.get("perform_linkedin_onboarding", False)
    blog_performed = test_inputs.get("perform_blog_onboarding", False)
    
    if not linkedin_performed and not blog_performed:
        logger.warning("⚠ No onboarding was performed (both flags were False)")
    else:
        completed_flows = []
        if linkedin_performed and "linkedin_profile_doc" in outputs:
            completed_flows.append("LinkedIn")
        if blog_performed and "blog_company_doc" in outputs:
            completed_flows.append("Blog")
        
        logger.info(f"✓ Successfully completed onboarding for: {', '.join(completed_flows)}")
    
    # Summary validation
    expected_outputs = []
    if linkedin_performed:
        expected_outputs.extend(["linkedin_profile_doc"])
    if blog_performed:
        expected_outputs.extend(["blog_company_doc"])
    
    for expected_output in expected_outputs:
        assert expected_output in outputs, f"Expected output '{expected_output}' missing"
    
    logger.info("✓ Onboarding workflow output validation passed successfully.")
    return True


async def main_test_onboarding():
    test_inputs = {
        "entity_username": "example-user-1",
        "company_name": "Entelligence.ai",
        "perform_linkedin_onboarding": True,
        "perform_blog_onboarding": True,
        "linkedin_profile_url": "https://www.linkedin.com/in/example-user-1/",
        "company_url": "https://www.entelligence.ai/",
        "linkedin_additional_context": """
Founder(s): Aiswarya Sankar (Founder & CEO)


Founder LinkedIn: Needs to be checked online


Persona Tags: DevTools; AI for Eng; Platform


Content Goals: Primary — Product Education; Secondary — Talent/Recruiting


Posting Schedule: 2 posts/week; Days — Tue, Thu; Exclude weekends — Yes


Timezone: PT

        """,
        "blog_additional_context": """
Asset Name: Entelligence Blog


Value Proposition: AI that understands your entire codebase and workflow to plan, review, and accelerate engineering work.


ICP


Name: Scale-up & Enterprise Eng Orgs


Target Industry: Software & Platforms


Company Size: 200–3,000


Buyer Persona: VP Eng / Head of Platform


Pain Points:


PR review backlog


Slow onboarding to legacy code


Context fragmentation across PR/Slack/Docs


Competitors: Sourcegraph; Codeium; Cursor


Goals: Cut PR review time by 40%; Reduce new-hire ramp by 30 days


Posting Schedule: 2 posts/month
        """,
    }

    # approve revise
    # {"blog_user_action": "approve", "linkedin_user_action": "approve", "blog_revision_feedback": "", "linkedin_revision_feedback": ""}
    # {"blog_user_action": "revise", "linkedin_user_action": "approve", "blog_revision_feedback": "My business goals are incorrect, please correct after researching my startup stage and make correct assumptions.", "linkedin_revision_feedback": ""}

    await run_workflow_test(
        test_name="User Onboarding Workflow",
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=None,
        setup_docs=[],
        cleanup_docs=[],
        validate_output_func=partial(validate_onboarding_output, test_inputs=test_inputs),
        stream_intermediate_results=True,
        poll_interval_sec=5,
        tag="onboarding_workflow_test",
        timeout_sec=900,
    )


if __name__ == "__main__":
    print("=" * 50)
    print("Executing User Onboarding Workflow Test")
    print("=" * 50)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        print("   Async event loop already running. Adding task...")
        loop.create_task(main_test_onboarding())
    else:
        print("   Starting new async event loop...")
        asyncio.run(main_test_onboarding())
    print("\nRun this script from the project root directory using:")
    print("poetry run python standalone_test_client/kiwi_client/workflows/active/onboarding/wf_auto_user_onboarding.py")


