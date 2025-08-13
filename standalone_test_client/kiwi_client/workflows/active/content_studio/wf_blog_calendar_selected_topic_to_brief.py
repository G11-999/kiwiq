"""
Selected Topic to Brief Generation Workflow

This workflow takes a pre-selected topic from ContentTopicsOutput and:
- Loads company context
- Generates a comprehensive content brief based on the selected topic
- Provides HITL editing and approval with iteration limits
- Saves the approved brief

Key Features:
- Starts with a pre-selected topic (no topic selection phase)
- Comprehensive brief generation with strategic alignment
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
from kiwi_client.workflows.active.document_models.customer_docs import (
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    BLOG_COMPANY_IS_VERSIONED,
    BLOG_CONTENT_BRIEF_NAMESPACE_TEMPLATE,
    BLOG_CONTENT_BRIEF_DOCNAME,
    BLOG_CONTENT_BRIEF_IS_VERSIONED,
    BLOG_CONTENT_STRATEGY_DOCNAME,
    BLOG_CONTENT_STRATEGY_NAMESPACE_TEMPLATE,
    BLOG_CONTENT_STRATEGY_IS_VERSIONED
)

# Import LLM inputs
from kiwi_client.workflows.active.content_studio.llm_inputs.blog_calendar_selected_topic_to_brief import (
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
                    "company_name": {
                        "type": "str",
                        "required": True,
                        "description": "Name of the company for document operations"
                    },
                    "selected_topic": {
                        "type": "dict",
                        "required": True,
                        "description": "The selected topic from ContentTopicsOutput containing title, description, theme, objective, etc."
                    }
                }
            }
        },
        
        # 2. Load Company and Content Strategy Documents
        "load_company_and_playbook": {
            "node_id": "load_company_and_playbook",
            "node_name": "load_customer_data",
            "node_config": {
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_COMPANY_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_COMPANY_DOCNAME,
                        },
                        "output_field_name": "company_doc"
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_CONTENT_STRATEGY_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_CONTENT_STRATEGY_DOCNAME,
                        },
                        "output_field_name": "playbook_doc"
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
                            "company_doc": None,
                            "playbook_doc": None
                        },
                        "construct_options": {
                            "selected_topic": "selected_topic",
                            "company_doc": "company_doc",
                            "playbook_doc": "playbook_doc"
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
                                "input_namespace_field_pattern": BLOG_CONTENT_BRIEF_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": BLOG_CONTENT_BRIEF_DOCNAME
                            }
                        },
                        "generate_uuid": True,
                        "extra_fields": [
                            {
                                "src_path": "user_action",
                                "dst_path": "status"
                            },
                            {
                                "src_path": "selected_topic",
                                "dst_path": "source_topic"
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
                            "company_doc": None,
                            "playbook_doc": None
                        },
                        "construct_options": {
                            "content_brief": "current_content_brief",
                            "revision_feedback": "current_revision_feedback",
                            "selected_topic": "selected_topic",
                            "company_doc": "company_doc",
                            "playbook_doc": "playbook_doc"
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
                            "company_doc": None,
                            "playbook_doc": None,
                            "revision_instructions": None
                        },
                        "construct_options": {
                            "selected_topic": "selected_topic",
                            "company_doc": "company_doc",
                            "playbook_doc": "playbook_doc",
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
                                "input_namespace_field_pattern": BLOG_CONTENT_BRIEF_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": BLOG_CONTENT_BRIEF_DOCNAME
                            }
                        },
                        "generate_uuid": True,
                        "extra_fields": [
                            {
                                "src_path": "user_action",
                                "dst_path": "status"
                            }
                        ],
                        "versioning": {
                            "is_versioned": BLOG_CONTENT_BRIEF_IS_VERSIONED,
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
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "selected_topic", "dst_field": "selected_topic"}
            ]
        },
        
        # Input -> Load Company and Playbook
        {
            "src_node_id": "input_node",
            "dst_node_id": "load_company_and_playbook",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"}
            ]
        },
        
        # Company and Playbook -> State
        {
            "src_node_id": "load_company_and_playbook",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "playbook_doc", "dst_field": "playbook_doc"}
            ]
        },
        
        # Load Company and Playbook -> Brief Generation Prompt (trigger)
        {
            "src_node_id": "load_company_and_playbook",
            "dst_node_id": "construct_brief_generation_prompt",
            "mappings": []
        },
        
        # State -> Brief Generation Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_brief_generation_prompt",
            "mappings": [
                {"src_field": "selected_topic", "dst_field": "selected_topic"},
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "playbook_doc", "dst_field": "playbook_doc"}
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
                {"src_field": "company_name", "dst_field": "company_name"}
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
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "playbook_doc", "dst_field": "playbook_doc"}
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
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "playbook_doc", "dst_field": "playbook_doc"}
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
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "current_content_brief", "dst_field": "final_content_brief"},
                {"src_field": "user_action", "dst_field": "user_action"}
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
                "company_doc": "replace",
                "playbook_doc": "replace"
            }
        }
    }
}


# --- Testing Code ---

async def validate_selected_topic_brief_workflow_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Validate the selected topic to brief generation workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run.
        
    Returns:
        True if the outputs are valid, False otherwise.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating selected topic to brief generation workflow outputs...")
    
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
            'title', 'target_audience', 'content_goal', 'key_takeaways',
            'content_structure', 'seo_keywords', 'brand_guidelines',
            'research_sources', 'call_to_action', 'estimated_word_count',
            'difficulty_level', 'writing_instructions'
        ]
        
        for field in required_brief_fields:
            assert field in content_brief, f"Content brief missing required field: {field}"
        
        logger.info(f"✓ Content brief generated with {len(content_brief['content_structure'])} sections")
        logger.info(f"✓ Estimated word count: {content_brief['estimated_word_count']}")
    
    # Check for brief document ID if brief was saved
    if 'final_paths_processed' in outputs:
        paths = outputs['final_paths_processed']
        if paths and len(paths) > 0:
            logger.info(f"✓ Brief saved successfully")
    
    logger.info("✓ Selected topic to brief generation workflow output validation passed.")
    return True


async def main_test_selected_topic_brief_workflow():
    """
    Test for Selected Topic to Brief Generation Workflow.
    
    This function sets up test data, executes the workflow, and validates the output.
    The workflow takes a pre-selected topic and generates a comprehensive content brief.
    """
    test_name = "Selected Topic to Brief Generation Workflow Test"
    print(f"--- Starting {test_name} ---")
    
    # Test parameters
    test_company_name = "Momentum"
    
    # Create test company document data
    company_data = {
        "name": "Momentum",
        "website_url": "https://www.momentum.io",
        "value_proposition": "AI-native Revenue Orchestration Platform that extracts, structures, and moves GTM data automatically.",
        "company_offerings": [
            {
                "offering": "AI-powered Revenue Orchestration Platform",
                "use_case": [
                    "Automated CRM data entry and hygiene",
                    "Real-time deal tracking and forecasting"
                ],
                "ideal_users": [
                    "Chief Revenue Officers",
                    "VP of Sales"
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
                    "Poor CRM data hygiene and accuracy"
                ]
            }
        ],
        "goals": [
            "Establish thought leadership in revenue intelligence",
            "Educate target audience about automated GTM data workflows"
        ]
    }
    
    # Create test playbook document data
    playbook_data = {
        "playbook_name": "Blog Content Best Practices",
        "content_guidelines": {
            "tone_and_voice": {
                "tone": "Professional yet approachable",
                "voice": "Expert and authoritative",
                "style": "Clear, concise, and actionable"
            },
            "structure_guidelines": [
                "Start with a compelling hook or statistic",
                "Use clear headings and subheadings",
                "Include practical examples and case studies",
                "End with actionable takeaways",
                "Keep paragraphs short (3-4 sentences max)"
            ],
            "seo_best_practices": [
                "Include primary keyword in title and first paragraph",
                "Use semantic keywords naturally throughout",
                "Optimize meta descriptions to 155 characters",
                "Include internal and external links",
                "Use alt text for all images"
            ]
        },
        "content_types": {
            "thought_leadership": {
                "word_count": "1500-2500",
                "structure": "Problem-Solution-Impact",
                "elements": ["Industry insights", "Original research", "Expert opinions"]
            },
            "how_to_guides": {
                "word_count": "1000-2000",
                "structure": "Step-by-step process",
                "elements": ["Clear instructions", "Screenshots/visuals", "Common pitfalls"]
            },
            "case_studies": {
                "word_count": "1200-1800",
                "structure": "Challenge-Solution-Results",
                "elements": ["Metrics and data", "Customer quotes", "Lessons learned"]
            }
        },
        "quality_checklist": [
            "Fact-check all statistics and claims",
            "Include relevant internal/external links",
            "Proofread for grammar and clarity",
            "Ensure mobile-friendly formatting",
            "Add compelling CTAs"
        ]
    }
    
    # Create a test selected topic (as if selected from ContentTopicsOutput)
    test_selected_topic = {
        "suggested_topics": [
            {
                "title": "The Hidden Cost of Manual CRM Data Entry: A CFO's Perspective",
                "description": "Explore the financial impact of manual data entry on revenue teams, including lost productivity, opportunity costs, and the ROI of automation solutions"
            }
        ],
        "scheduled_date": "2025-08-15T14:00:00Z",
        "theme": "Revenue Operations Efficiency",
        "play_aligned": "Thought Leadership",
        "objective": "thought_leadership",
        "why_important": "CFOs are increasingly involved in RevOps technology decisions and need to understand the financial impact of manual processes"
    }
    
    # Test inputs
    test_inputs = {
        "company_name": test_company_name,
        "selected_topic": test_selected_topic
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
        },
        {
            'namespace': f"blog_company_strategy_{test_company_name}",
            'docname': BLOG_CONTENT_STRATEGY_DOCNAME,
            'initial_data': playbook_data,
            'is_shared': False,
            'is_versioned': BLOG_CONTENT_STRATEGY_IS_VERSIONED,
            'initial_version': "default",
            'is_system_entity': False
        }
    ]
    
    # Cleanup configuration
    cleanup_docs: List[CleanupDocInfo] = [
        {
            'namespace': f"blog_company_profile_{test_company_name}",
            'docname': BLOG_COMPANY_DOCNAME,
            'is_shared': False,
            'is_versioned': BLOG_COMPANY_IS_VERSIONED,
            'is_system_entity': False
        },
        {
            'namespace': f"blog_company_strategy_{test_company_name}",
            'docname': BLOG_CONTENT_STRATEGY_DOCNAME,
            'is_shared': False,
            'is_versioned': BLOG_CONTENT_STRATEGY_IS_VERSIONED,
            'is_system_entity': False
        }
    ]
    
    # Predefined HITL inputs for testing
    predefined_hitl_inputs = [
        {
            "user_action": "complete",
            "updated_content_brief": {
                "title": "The Hidden Cost of Manual CRM Data Entry: A CFO's Perspective",
                "target_audience": "CFOs and Finance Leaders at Enterprise SaaS companies",
                "content_goal": "Demonstrate financial impact of manual data entry and ROI of automation",
                "key_takeaways": [
                    "Manual CRM data entry costs enterprises $1M+ annually in lost productivity",
                    "Poor data quality leads to 20% revenue leakage",
                    "Automation delivers 10x ROI within 6 months"
                ],
                "content_structure": [
                    {
                        "section": "Introduction",
                        "description": "Hook with shocking statistics about manual data entry costs",
                        "word_count": 200
                    },
                    {
                        "section": "The True Cost Breakdown",
                        "description": "Detailed analysis of direct and indirect costs",
                        "word_count": 600
                    },
                    {
                        "section": "Impact on Revenue Forecasting",
                        "description": "How bad data affects financial planning",
                        "word_count": 500
                    },
                    {
                        "section": "ROI of Automation",
                        "description": "Financial benefits and payback period",
                        "word_count": 400
                    },
                    {
                        "section": "Conclusion",
                        "description": "Call to action for CFOs",
                        "word_count": 300
                    }
                ],
                "seo_keywords": {
                    "primary_keyword": "CRM data entry costs",
                    "secondary_keywords": ["revenue operations ROI", "sales productivity"],
                    "long_tail_keywords": ["manual CRM data entry financial impact"]
                },
                "brand_guidelines": {
                    "tone": "Professional and data-driven",
                    "voice": "Authoritative yet approachable",
                    "style_notes": ["Use financial metrics", "Include case studies"]
                },
                "research_sources": [
                    {
                        "source": "Industry Reports",
                        "key_insights": ["Average cost per manual entry", "Time spent on data entry"]
                    }
                ],
                "call_to_action": "Calculate your CRM data entry costs with our ROI calculator",
                "estimated_word_count": 2000,
                "difficulty_level": "intermediate",
                "writing_instructions": [
                    "Include specific dollar amounts and percentages",
                    "Use CFO-friendly language and metrics",
                    "Add comparison table of manual vs automated costs"
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
        validate_output_func=validate_selected_topic_brief_workflow_output,
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
            print(f"Brief Generated: {brief.get('estimated_word_count', 'N/A')} words")
            print(f"Brief Title: {brief.get('title', 'N/A')}")
            print(f"Sections: {len(brief.get('content_structure', []))}")
        
        # Show saved document
        if 'final_paths_processed' in final_run_outputs:
            print(f"Brief Saved: Successfully stored in database")


# Entry point
if __name__ == "__main__":
    print("="*80)
    print("Selected Topic to Brief Generation Workflow Test")
    print("="*80)
    
    try:
        asyncio.run(main_test_selected_topic_brief_workflow())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.exception("Test execution failed")
    
    print("\nTest execution finished.")
    print("Run from project root: PYTHONPATH=. python kiwi_client/workflows_for_blog_teammate/wf_selected_topic_to_brief.py")