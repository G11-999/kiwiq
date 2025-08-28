"""
LinkedIn Selected Topic to Brief Generation Workflow

This workflow takes a pre-selected topic from ContentTopicsOutput and:
- Loads executive profile and content strategy documents
- Generates a comprehensive LinkedIn content brief based on the selected topic
- Provides HITL editing and approval with iteration limits
- Saves the approved brief

Key Features:
- Starts with a pre-selected topic (no topic selection phase)
- Comprehensive brief generation with LinkedIn optimization
- HITL approval flow with manual editing support
- Iteration limits to prevent infinite loops
- Document storage for approved briefs
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
from kiwi_client.workflows.document_models.customer_docs import (
    LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
    LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE,
    LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
    LINKEDIN_USER_PROFILE_DOCNAME,
    LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
    LINKEDIN_USER_PROFILE_IS_VERSIONED,
    LINKEDIN_BRIEF_DOCNAME,
    LINKEDIN_BRIEF_NAMESPACE_TEMPLATE,
    LINKEDIN_BRIEF_IS_VERSIONED
)

# Import LLM inputs
from kiwi_client.workflows.llm_inputs.linkedin_selected_topic_to_brief import (
    # System prompts
    BRIEF_GENERATION_SYSTEM_PROMPT,
    BRIEF_FEEDBACK_SYSTEM_PROMPT,
    
    # User prompt templates
    BRIEF_GENERATION_USER_PROMPT_TEMPLATE,
    BRIEF_FEEDBACK_INITIAL_USER_PROMPT,
    BRIEF_FEEDBACK_ADDITIONAL_USER_PROMPT,
    
    # Output schemas
    BRIEF_GENERATION_OUTPUT_SCHEMA,
    BRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA,
)

# LLM Configuration
LLM_PROVIDER = "anthropic"
LLM_MODEL = "claude-3-7-sonnet-20250219"
TEMPERATURE = 0.7
MAX_TOKENS = 4000

# Workflow Limits
MAX_ITERATIONS = 10  # Maximum iterations for HITL feedback loops

# Feedback LLM Configuration
FEEDBACK_LLM_PROVIDER = "anthropic"
FEEDBACK_ANALYSIS_MODEL = "claude-3-7-sonnet-20250219"
FEEDBACK_TEMPERATURE = 0.5
FEEDBACK_MAX_TOKENS = 3000

# Workflow JSON structure
workflow_graph_schema = {
    "nodes": {
        # 1. Input Node - Receives selected topic
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "entity_username": {
                        "type": "str",
                        "required": True,
                        "description": "LinkedIn username/entity for document operations"
                    },
                    "selected_topic": {
                        "type": "dict",
                        "required": True,
                        "description": "The selected topic from ContentTopicsOutput containing title, description, theme, objective, etc."
                    }
                }
            }
        },
        
        # 2. Load Executive Profile and Content Strategy Documents
        "load_profile_and_strategy": {
            "node_id": "load_profile_and_strategy",
            "node_name": "load_customer_data",
            "node_config": {
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_USER_PROFILE_DOCNAME,
                        },
                        "output_field_name": "executive_profile_doc"
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
                        },
                        "output_field_name": "content_strategy_doc"
                    }
                ]
            }
        },
        
        # 3. Brief Generation - Prompt Constructor
        "construct_brief_generation_prompt": {
            "node_id": "construct_brief_generation_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "brief_generation_user_prompt": {
                        "id": "brief_generation_user_prompt",
                        "template": BRIEF_GENERATION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "selected_topic": None,
                            "executive_profile_doc": None,
                            "content_strategy_doc": None
                        },
                        "construct_options": {
                            "selected_topic": "selected_topic",
                            "executive_profile_doc": "executive_profile_doc",
                            "content_strategy_doc": "content_strategy_doc"
                        }
                    },
                    "brief_generation_system_prompt": {
                        "id": "brief_generation_system_prompt",
                        "template": BRIEF_GENERATION_SYSTEM_PROMPT,
                        "variables": {},
                    }
                }
            }
        },
        
        # 4. Brief Generation - LLM Node
        "brief_generation_llm": {
            "node_id": "brief_generation_llm",
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
                    "schema_definition": BRIEF_GENERATION_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 5. Brief Approval - HITL Node
        "brief_approval_hitl": {
            "node_id": "brief_approval_hitl",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "user_action": {
                        "type": "enum",
                        "enum_values": ["complete", "revise_brief", "cancel_workflow", "draft"],
                        "required": True,
                        "description": "User's decision on brief approval"
                    },
                    "revision_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "Feedback for brief revision (required if revise_brief)"
                    },
                    "updated_content_brief": {
                        "type": "dict",
                        "required": True,
                        "description": "Updated content brief (may contain user edits)"
                    }
                }
            }
        },
        
        # 6. Route Brief Approval
        "route_brief_approval": {
            "node_id": "route_brief_approval",
            "node_name": "router_node",
            "node_config": {
                "choices": ["save_brief", "check_iteration_limit", "output_node", "save_as_draft"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "save_brief",
                        "input_path": "user_action",
                        "target_value": "complete"
                    },
                    {
                        "choice_id": "check_iteration_limit",
                        "input_path": "user_action",
                        "target_value": "revise_brief"
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "user_action",
                        "target_value": "cancel_workflow"
                    },
                    {
                        "choice_id": "save_as_draft",
                        "input_path": "user_action",
                        "target_value": "draft"
                    }
                ],
                "default_choice": "output_node"
            }
        },
        
        # 7. Save Brief as Draft
        "save_as_draft": {
            "node_id": "save_as_draft",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": True,
                    "operation": "upsert_versioned"
                },
                "global_is_shared": False,
                "store_configs": [
                    {
                        "input_field_path": "current_content_brief",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": LINKEDIN_BRIEF_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "entity_username",
                                "static_docname": LINKEDIN_BRIEF_DOCNAME
                            }
                        },
                        "generate_uuid": True,
                        "extra_fields": [
                            {
                                "src_path": " status",
                                "dst_path": "user_action"
                            }
                        ],
                        "versioning": {
                            "is_versioned": True,
                            "operation": "upsert_versioned"
                        }
                    }
                ],
            }
        },
        
        # 8. Check Iteration Limit
        "check_iteration_limit": {
            "node_id": "check_iteration_limit",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "iteration_limit_check",
                        "condition_groups": [{
                            "logical_operator": "and",
                            "conditions": [{
                                "field": "generation_metadata.iteration_count",
                                "operator": "less_than",
                                "value": MAX_ITERATIONS
                            }]
                        }],
                        "group_logical_operator": "and"
                    }
                ],
                "branch_logic_operator": "and"
            }
        },
        
        # 9. Route Based on Iteration Limit Check
        "route_on_limit_check": {
            "node_id": "route_on_limit_check",
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_brief_feedback_prompt", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_brief_feedback_prompt",
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
        
        # 10. Brief Feedback Prompt Constructor
        "construct_brief_feedback_prompt": {
            "node_id": "construct_brief_feedback_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "brief_feedback_user_prompt": {
                        "id": "brief_feedback_user_prompt",
                        "template": BRIEF_FEEDBACK_INITIAL_USER_PROMPT,
                        "variables": {
                            "content_brief": None,
                            "revision_feedback": None,
                            "selected_topic": None,
                            "executive_profile_doc": None,
                            "content_strategy_doc": None
                        },
                        "construct_options": {
                            "content_brief": "current_content_brief",
                            "revision_feedback": "current_revision_feedback",
                            "selected_topic": "selected_topic",
                            "executive_profile_doc": "executive_profile_doc",
                            "content_strategy_doc": "content_strategy_doc"
                        }
                    },
                    "brief_feedback_system_prompt": {
                        "id": "brief_feedback_system_prompt",
                        "template": BRIEF_FEEDBACK_SYSTEM_PROMPT,
                        "variables": {},
                    }
                }
            }
        },
        
        # 11. Brief Feedback Analysis
        "analyze_brief_feedback": {
            "node_id": "analyze_brief_feedback",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": FEEDBACK_LLM_PROVIDER,
                        "model": FEEDBACK_ANALYSIS_MODEL
                    },
                    "temperature": FEEDBACK_TEMPERATURE,
                    "max_tokens": FEEDBACK_MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": BRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 12. Brief Revision - Enhanced Prompt Constructor
        "construct_brief_revision_prompt": {
            "node_id": "construct_brief_revision_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "brief_revision_user_prompt": {
                        "id": "brief_revision_user_prompt",
                        "template": BRIEF_GENERATION_USER_PROMPT_TEMPLATE + "\n\n**Revision Instructions:**\n{revision_instructions}",
                        "variables": {
                            "selected_topic": None,
                            "executive_profile_doc": None,
                            "content_strategy_doc": None,
                            "revision_instructions": None
                        },
                        "construct_options": {
                            "selected_topic": "selected_topic",
                            "executive_profile_doc": "executive_profile_doc",
                            "content_strategy_doc": "content_strategy_doc",
                            "revision_instructions": "brief_feedback_analysis.revision_instructions"
                        }
                    },
                    "brief_revision_system_prompt": {
                        "id": "brief_revision_system_prompt",
                        "template": BRIEF_GENERATION_SYSTEM_PROMPT,
                        "variables": {},
                    }
                }
            }
        },
        
        # 13. Brief Revision - LLM Node
        "brief_revision_llm": {
            "node_id": "brief_revision_llm",
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
                    "schema_definition": BRIEF_GENERATION_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 14. Save Brief - Store Customer Data
        "save_brief": {
            "node_id": "save_brief",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": True,
                    "operation": "upsert_versioned"
                },
                "global_is_shared": False,
                "store_configs": [
                    {
                        "input_field_path": "final_content_brief",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": LINKEDIN_BRIEF_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "entity_username",
                                "static_docname": LINKEDIN_BRIEF_DOCNAME
                            }
                        },
                        "generate_uuid": True,
                        "extra_fields": [
                            {
                                "src_path": "status",
                                "dst_path": "user_action"
                            }
                        ],
                        "versioning": {
                            "is_versioned": LINKEDIN_BRIEF_IS_VERSIONED,
                            "operation": "upsert_versioned"
                        },
                    }
                ],
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
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "selected_topic", "dst_field": "selected_topic"}
            ]
        },
        
        # Input -> Load Profile and Strategy
        {
            "src_node_id": "input_node",
            "dst_node_id": "load_profile_and_strategy",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"}
            ]
        },
        
        # Profile and Strategy -> State
        {
            "src_node_id": "load_profile_and_strategy",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "executive_profile_doc", "dst_field": "executive_profile_doc"},
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"}
            ]
        },
        
        # Load Profile and Strategy -> Brief Generation Prompt (trigger)
        {
            "src_node_id": "load_profile_and_strategy",
            "dst_node_id": "construct_brief_generation_prompt",
            "mappings": []
        },
        
        # State -> Brief Generation Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_brief_generation_prompt",
            "mappings": [
                {"src_field": "selected_topic", "dst_field": "selected_topic"},
                {"src_field": "executive_profile_doc", "dst_field": "executive_profile_doc"},
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"}
            ]
        },
        
        # Brief Generation Prompt -> LLM
        {
            "src_node_id": "construct_brief_generation_prompt",
            "dst_node_id": "brief_generation_llm",
            "mappings": [
                {"src_field": "brief_generation_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "brief_generation_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # State -> Brief Generation LLM (message history)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "brief_generation_llm",
            "mappings": [
                {"src_field": "brief_generation_messages_history", "dst_field": "messages_history"}
            ]
        },
        
        # Brief Generation LLM -> State
        {
            "src_node_id": "brief_generation_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "current_content_brief"},
                {"src_field": "current_messages", "dst_field": "brief_generation_messages_history"},
                {"src_field": "metadata", "dst_field": "generation_metadata"}
            ]
        },
        
        # Brief Generation LLM -> HITL
        {
            "src_node_id": "brief_generation_llm",
            "dst_node_id": "brief_approval_hitl",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "content_brief"}
            ]
        },
        
        # Brief Approval HITL -> Route
        {
            "src_node_id": "brief_approval_hitl",
            "dst_node_id": "route_brief_approval",
            "mappings": [
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        
        # Brief Approval HITL -> State
        {
            "src_node_id": "brief_approval_hitl",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "revision_feedback", "dst_field": "current_revision_feedback"},
                {"src_field": "updated_content_brief", "dst_field": "current_content_brief"},
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        
        # Route Brief Approval paths
        {
            "src_node_id": "route_brief_approval",
            "dst_node_id": "save_brief",
            "description": "Route to save brief if approved"
        },
        {
            "src_node_id": "route_brief_approval",
            "dst_node_id": "check_iteration_limit",
            "description": "Route to check iteration limit if revision requested"
        },
        {
            "src_node_id": "route_brief_approval",
            "dst_node_id": "output_node",
            "description": "Route to output if workflow cancelled"
        },
        {
            "src_node_id": "route_brief_approval",
            "dst_node_id": "save_as_draft",
            "description": "Route to save as draft if requested"
        },
        
        # Check Iteration Limit edges
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "check_iteration_limit",
            "mappings": [
                {"src_field": "generation_metadata", "dst_field": "generation_metadata"}
            ]
        },
        {
            "src_node_id": "check_iteration_limit",
            "dst_node_id": "route_on_limit_check",
            "mappings": [
                {"src_field": "branch", "dst_field": "iteration_branch_result"},
                {"src_field": "tag_results", "dst_field": "if_else_condition_tag_results"},
                {"src_field": "condition_result", "dst_field": "if_else_overall_condition_result"}
            ]
        },
        {
            "src_node_id": "route_on_limit_check",
            "dst_node_id": "construct_brief_feedback_prompt",
            "description": "Trigger feedback interpretation if iterations remain"
        },
        {
            "src_node_id": "route_on_limit_check",
            "dst_node_id": "output_node",
            "description": "Trigger finalization if iteration limit reached"
        },
        
        # State -> Save as Draft
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_as_draft",
            "mappings": [
                {"src_field": "current_content_brief", "dst_field": "current_content_brief"},
                {"src_field": "user_action", "dst_field": "user_action"},
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "selected_topic", "dst_field": "selected_topic"}
            ]
        },
        
        # Save as Draft -> brief approval hitl
        {"src_node_id": "save_as_draft", "dst_node_id": "brief_approval_hitl"},
        
        # graph state -> brief approval hitl
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "brief_approval_hitl",
            "mappings": [
                {"src_field": "current_content_brief", "dst_field": "content_brief"}
            ]
        },
        
        # State -> Brief Feedback Prompt Constructor
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_brief_feedback_prompt",
            "mappings": [
                {"src_field": "current_content_brief", "dst_field": "current_content_brief"},
                {"src_field": "current_revision_feedback", "dst_field": "current_revision_feedback"},
                {"src_field": "selected_topic", "dst_field": "selected_topic"},
                {"src_field": "executive_profile_doc", "dst_field": "executive_profile_doc"},
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"}
            ]
        },
        
        # Brief Feedback Prompt -> LLM
        {
            "src_node_id": "construct_brief_feedback_prompt",
            "dst_node_id": "analyze_brief_feedback",
            "mappings": [
                {"src_field": "brief_feedback_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "brief_feedback_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # State -> Brief Feedback Analysis (message history)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "analyze_brief_feedback",
            "mappings": [
                {"src_field": "brief_feedback_analysis_messages_history", "dst_field": "messages_history"}
            ]
        },
        
        # Brief Feedback Analysis -> State
        {
            "src_node_id": "analyze_brief_feedback",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "brief_feedback_analysis"},
                {"src_field": "current_messages", "dst_field": "brief_feedback_analysis_messages_history"}
            ]
        },
        
        # Brief Feedback Analysis -> Brief Revision Prompt Constructor
        {
            "src_node_id": "analyze_brief_feedback",
            "dst_node_id": "construct_brief_revision_prompt",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "brief_feedback_analysis"}
            ]
        },
        
        # State -> Brief Revision Prompt Constructor
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_brief_revision_prompt",
            "mappings": [
                {"src_field": "selected_topic", "dst_field": "selected_topic"},
                {"src_field": "executive_profile_doc", "dst_field": "executive_profile_doc"},
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"}
            ]
        },
        
        # Brief Revision Prompt -> LLM
        {
            "src_node_id": "construct_brief_revision_prompt",
            "dst_node_id": "brief_revision_llm",
            "mappings": [
                {"src_field": "brief_revision_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "brief_revision_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # State -> Brief Revision LLM (message history)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "brief_revision_llm",
            "mappings": [
                {"src_field": "brief_generation_messages_history", "dst_field": "messages_history"}
            ]
        },
        
        # Brief Revision LLM -> HITL (loop back)
        {
            "src_node_id": "brief_revision_llm",
            "dst_node_id": "brief_approval_hitl",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "content_brief"}
            ]
        },
        
        # Brief Revision LLM -> State
        {
            "src_node_id": "brief_revision_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "current_content_brief"},
                {"src_field": "current_messages", "dst_field": "brief_generation_messages_history"},
                {"src_field": "metadata", "dst_field": "generation_metadata"}
            ]
        },
        
        # State -> Save Brief
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_brief",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "current_content_brief", "dst_field": "final_content_brief"},
                {"src_field": "user_action", "dst_field": "user_action"},
                {"src_field": "selected_topic", "dst_field": "selected_topic"}
            ]
        },
        
        # Save Brief -> Output
        {
            "src_node_id": "save_brief",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "paths_processed", "dst_field": "final_paths_processed"}
            ]
        },
        
        # State -> Output
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "selected_topic", "dst_field": "source_topic"},
                {"src_field": "current_content_brief", "dst_field": "final_content_brief"}
            ]
        }
    ],
    
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    "metadata": {
        "$graph_state": {
            "reducer": {
                "current_content_brief": "replace",
                "current_revision_feedback": "replace",
                "generation_metadata": "replace",
                "brief_generation_messages_history": "add_messages",
                "brief_feedback_analysis_messages_history": "add_messages",
                "user_action": "replace",
                "selected_topic": "replace",
                "executive_profile_doc": "replace",
                "content_strategy_doc": "replace"
            }
        }
    }
}


# --- Testing Code ---

async def validate_linkedin_topic_brief_workflow_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Validate the LinkedIn selected topic to brief generation workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run.
        
    Returns:
        True if the outputs are valid, False otherwise.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating LinkedIn selected topic to brief generation workflow outputs...")
    
    # Check for expected keys
    expected_keys = ['source_topic', 'final_content_brief']
    
    for key in expected_keys:
        if key in outputs:
            logger.info(f"✓ Found expected key: {key}")
        else:
            logger.warning(f"⚠ Missing optional key: {key}")
    
    # Validate source topic if present
    if 'source_topic' in outputs:
        source_topic = outputs['source_topic']
        assert isinstance(source_topic, dict), "Source topic should be a dict"
        assert 'suggested_topics' in source_topic, "Source topic missing suggested_topics"
        assert 'theme' in source_topic, "Source topic missing theme"
        assert 'objective' in source_topic, "Source topic missing objective"
        logger.info(f"✓ Source topic validated: {source_topic.get('theme', 'N/A')}")
    
    # Validate content brief if present
    if 'final_content_brief' in outputs:
        content_brief = outputs['final_content_brief']
        assert isinstance(content_brief, dict), "Content brief should be a dict"
        
        # Check required brief fields
        required_brief_fields = [
            'title', 'content_type', 'content_format', 'target_audience',
            'content_goal', 'key_message', 'content_structure', 'linkedin_formatting',
            'call_to_action', 'engagement_tactics', 'success_metrics',
            'estimated_reading_time', 'writing_guidelines'
        ]
        
        for field in required_brief_fields:
            assert field in content_brief, f"Content brief missing required field: {field}"
        
        # Validate LinkedIn-specific formatting
        linkedin_formatting = content_brief.get('linkedin_formatting', {})
        assert 'hook_style' in linkedin_formatting, "Missing hook_style in LinkedIn formatting"
        assert 'emoji_strategy' in linkedin_formatting, "Missing emoji_strategy in LinkedIn formatting"
        assert 'hashtag_strategy' in linkedin_formatting, "Missing hashtag_strategy in LinkedIn formatting"
        
        logger.info(f"✓ LinkedIn content brief generated with {len(content_brief['content_structure'])} sections")
        logger.info(f"✓ Content type: {content_brief['content_type']}")
        logger.info(f"✓ Estimated reading time: {content_brief['estimated_reading_time']}")
    
    # Check for brief document ID if brief was saved
    if 'final_paths_processed' in outputs:
        paths = outputs['final_paths_processed']
        if paths and len(paths) > 0:
            logger.info(f"✓ LinkedIn brief saved successfully")
    
    logger.info("✓ LinkedIn selected topic to brief generation workflow output validation passed.")
    return True


async def main_test_linkedin_topic_brief_workflow():
    """
    Test for LinkedIn Selected Topic to Brief Generation Workflow.
    
    This function sets up test data, executes the workflow, and validates the output.
    The workflow takes a pre-selected topic and generates a comprehensive LinkedIn content brief.
    """
    test_name = "LinkedIn Selected Topic to Brief Generation Workflow Test"
    print(f"--- Starting {test_name} ---")
    
    # Test parameters
    test_entity_username = "alex_johnson_tech"
    
    # Create test executive profile document data
    executive_profile_data = {
        "name": "Alex Johnson",
        "title": "CEO & Founder",
        "company": "TechSolutions Pro",
        "linkedin_url": "https://linkedin.com/in/alexjohnsontech",
        "industry": "Technology & SaaS",
        "expertise_areas": [
            "AI-powered project management",
            "Team productivity optimization",
            "Remote work culture",
            "SaaS product development"
        ],
        "thought_leadership_topics": [
            "The future of AI in business",
            "Building high-performance remote teams",
            "Scaling SaaS companies",
            "Leadership in the digital age"
        ],
        "content_voice": {
            "tone": "Conversational yet authoritative",
            "style": "Story-driven with data-backed insights",
            "personality": "Innovative, practical, and empathetic leader"
        },
        "target_audience": [
            "C-suite executives in tech",
            "SaaS founders and entrepreneurs",
            "Operations and project managers",
            "Remote team leaders"
        ]
    }
    
    # Create test content strategy document data
    content_strategy_data = {
        "content_pillars": [
            "AI and Automation in Business",
            "Remote Team Leadership",
            "SaaS Growth Strategies",
            "Operational Excellence"
        ],
        "content_objectives": [
            "Build thought leadership in AI-powered business solutions",
            "Generate leads for consulting services",
            "Expand LinkedIn network with target audience",
            "Drive traffic to company website"
        ],
        "posting_schedule": {
            "frequency": "3-4 times per week",
            "best_times": ["Tuesday 9 AM", "Wednesday 2 PM", "Thursday 10 AM"],
            "content_mix": {
                "thought_leadership": "40%",
                "how-to_guides": "30%",
                "industry_insights": "20%",
                "personal_stories": "10%"
            }
        },
        "engagement_strategy": {
            "hooks": ["Questions", "Controversial takes", "Statistics", "Personal stories"],
            "cta_types": ["Comment for insights", "Share your experience", "Follow for more", "Visit link in comments"],
            "hashtag_strategy": "3-5 relevant hashtags per post"
        },
        "linkedin_best_practices": [
            "Start with a strong hook in first 2 lines",
            "Use line breaks for readability",
            "Include relevant emojis sparingly",
            "Add a clear CTA at the end",
            "Engage with comments within first hour"
        ]
    }
    
    # Create a test selected topic (as if selected from ContentTopicsOutput)
    test_selected_topic = {
        "suggested_topics": [
            {
                "title": "Why 90% of AI Implementation Fails (And How to Be in the 10% That Succeeds)",
                "description": "Share insights on common AI implementation pitfalls and provide a practical framework for successful AI adoption in businesses"
            }
        ],
        "scheduled_date": "2025-08-15T14:00:00Z",
        "theme": "AI and Automation in Business",
        "play_aligned": "Thought Leadership",
        "objective": "thought_leadership",
        "why_important": "Executives need practical guidance on AI implementation to avoid costly failures and drive real business value"
    }
    
    # Test inputs
    test_inputs = {
        "entity_username": test_entity_username,
        "selected_topic": test_selected_topic
    }
    
    # Setup test documents
    setup_docs: List[SetupDocInfo] = [
        {
            'namespace': f"linkedin_executive_profile_namespace_{test_entity_username}",
            'docname': LINKEDIN_USER_PROFILE_DOCNAME,
            'initial_data': executive_profile_data,
            'is_shared': False,
            'is_versioned': LINKEDIN_USER_PROFILE_IS_VERSIONED,
            'initial_version': "default",
            'is_system_entity': False
        },
        {
            'namespace': f"linkedin_executive_strategy_{test_entity_username}",
            'docname': LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
            'initial_data': content_strategy_data,
            'is_shared': False,
            'is_versioned': LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
            'initial_version': "default",
            'is_system_entity': False
        }
    ]
    
    # Cleanup configuration
    cleanup_docs: List[CleanupDocInfo] = [
        {
            'namespace': f"linkedin_executive_profile_namespace_{test_entity_username}",
            'docname': LINKEDIN_USER_PROFILE_DOCNAME,
            'is_shared': False,
            'is_versioned': LINKEDIN_USER_PROFILE_IS_VERSIONED,
            'is_system_entity': False
        },
        {
            'namespace': f"linkedin_executive_strategy_{test_entity_username}",
            'docname': LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
            'is_shared': False,
            'is_versioned': LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
            'is_system_entity': False
        }
    ]
    
    # Predefined HITL inputs for testing
    predefined_hitl_inputs = [
        {
            "user_action": "complete",
            "updated_content_brief": {
                "title": "Why 90% of AI Implementation Fails (And How to Be in the 10% That Succeeds)",
                "content_type": "LinkedIn Article",
                "content_format": "Long-form thought leadership piece",
                "target_audience": "C-suite executives and tech leaders considering AI adoption",
                "content_goal": "Establish thought leadership and generate consulting leads",
                "key_message": "AI success requires strategic planning, not just technology",
                "content_structure": [
                    {
                        "section_title": "Hook - The Shocking Statistics",
                        "key_points": [
                            "90% of AI projects fail to deliver expected ROI",
                            "Personal story of witnessing failures",
                            "The promise vs reality gap"
                        ],
                        "estimated_word_count": 150
                    },
                    {
                        "section_title": "The 3 Fatal Mistakes",
                        "key_points": [
                            "Starting with technology instead of strategy",
                            "Ignoring change management",
                            "Lack of clear success metrics"
                        ],
                        "estimated_word_count": 400
                    },
                    {
                        "section_title": "The Success Framework",
                        "key_points": [
                            "Start with business problems, not solutions",
                            "Build AI literacy across teams",
                            "Implement incremental wins strategy"
                        ],
                        "estimated_word_count": 400
                    },
                    {
                        "section_title": "Call to Action",
                        "key_points": [
                            "Invitation to share experiences",
                            "Offer of free AI readiness assessment",
                            "Link to detailed guide"
                        ],
                        "estimated_word_count": 100
                    }
                ],
                "linkedin_formatting": {
                    "hook_style": "Shocking statistic with personal observation",
                    "emoji_strategy": "Use sparingly - ❌ for failures, ✅ for solutions, 🎯 for key points",
                    "hashtag_strategy": "#AIImplementation #DigitalTransformation #Leadership #TechStrategy #Innovation",
                    "formatting_notes": [
                        "Use short paragraphs with line breaks",
                        "Bold key statistics",
                        "Include 1-2 questions to drive engagement",
                        "Add link to resources in first comment"
                    ]
                },
                "call_to_action": "What's been your experience with AI implementation? Share in the comments below 👇",
                "engagement_tactics": [
                    "Ask controversial question in opening",
                    "Include poll about AI readiness",
                    "Respond to comments within first hour",
                    "Tag relevant thought leaders"
                ],
                "success_metrics": [
                    "500+ reactions within 24 hours",
                    "50+ meaningful comments",
                    "20+ shares",
                    "10+ qualified leads generated"
                ],
                "estimated_reading_time": "4-5 minutes",
                "writing_guidelines": [
                    "Use 'you' and 'we' language",
                    "Include specific examples and data",
                    "Balance expertise with accessibility",
                    "End sections with thought-provoking questions"
                ]
            }
        }
    ]
    
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
        validate_output_func=validate_linkedin_topic_brief_workflow_output,
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=600  # 10 minutes for brief generation
    )
    
    print(f"--- {test_name} Finished ---")
    if final_run_outputs:
        # Show source topic
        if 'source_topic' in final_run_outputs:
            topic = final_run_outputs['source_topic']
            if 'suggested_topics' in topic and len(topic['suggested_topics']) > 0:
                print(f"Source Topic: {topic['suggested_topics'][0].get('title', 'N/A')}")
                print(f"Theme: {topic.get('theme', 'N/A')}")
                print(f"Objective: {topic.get('objective', 'N/A')}")
        
        # Show brief info
        if 'final_content_brief' in final_run_outputs:
            brief = final_run_outputs['final_content_brief']
            print(f"Brief Generated: {brief.get('content_type', 'N/A')}")
            print(f"Brief Title: {brief.get('title', 'N/A')}")
            print(f"Sections: {len(brief.get('content_structure', []))}")
            print(f"Reading Time: {brief.get('estimated_reading_time', 'N/A')}")
        
        # Show saved document
        if 'final_paths_processed' in final_run_outputs:
            print(f"LinkedIn Brief Saved: Successfully stored in database")


# Entry point
if __name__ == "__main__":
    print("="*80)
    print("LinkedIn Selected Topic to Brief Generation Workflow Test")
    print("="*80)
    
    try:
        asyncio.run(main_test_linkedin_topic_brief_workflow())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.exception("Test execution failed")
    
    print("\nTest execution finished.")
    print("Run from project root: PYTHONPATH=. python kiwi_client/workflows/wf_linkedin_selected_topic_to_brief.py")