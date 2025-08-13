"""
LinkedIn Content Playbook Generation Workflow

This workflow generates a comprehensive LinkedIn content playbook by:
- Loading company LinkedIn documents
- Selecting relevant content plays based on company context
- Creating detailed implementation strategies for each play
- Providing actionable recommendations and timelines

Key Features:
- Automatic play selection based on company profile
- Human-in-the-loop approval for play selection and playbook review
- Document search integration for informed recommendations
- Structured playbook output with implementation details
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
    LINKEDIN_USER_PROFILE_DOCNAME,
    LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
    LINKEDIN_USER_PROFILE_IS_VERSIONED,
    LINKEDIN_USER_PROFILE_IS_SHARED,
    LINKEDIN_USER_PROFILE_IS_SYSTEM_ENTITY,
    LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
    LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE,
    LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
    LINKEDIN_CONTENT_PLAYBOOK_IS_SHARED,
    LINKEDIN_CONTENT_PLAYBOOK_IS_SYSTEM_ENTITY,
    LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
    LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
    LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_IS_VERSIONED,
    LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_IS_SHARED,
    LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_IS_SYSTEM_ENTITY
)

# Import LLM inputs
from kiwi_client.workflows.active.playbook.llm_inputs.linkedin_content_playbook_generation import (
    # System prompts
    PLAY_SELECTION_SYSTEM_PROMPT,
    DOCUMENT_FETCHER_SYSTEM_PROMPT,
    PLAYBOOK_GENERATOR_SYSTEM_PROMPT,
    PLAYBOOK_REVISION_SYSTEM_PROMPT,
    
    # User prompt templates
    PLAY_SELECTION_USER_PROMPT_TEMPLATE,
    PLAY_SELECTION_REVISION_USER_PROMPT_TEMPLATE,
    DOCUMENT_FETCHER_USER_PROMPT_TEMPLATE,
    DOCUMENT_FETCHER_REVISION_PROMPT_TEMPLATE,
    PLAYBOOK_GENERATOR_USER_PROMPT_TEMPLATE,
    PLAYBOOK_GENERATOR_REVISION_PROMPT_TEMPLATE,
    FEEDBACK_CONTEXT_PROMPT_TEMPLATE,
    ENHANCED_FEEDBACK_PROMPT_TEMPLATE,
    
    # Output schemas
    PLAY_SELECTION_OUTPUT_SCHEMA,
    DOCUMENT_FETCHER_OUTPUT_SCHEMA,
    INITIAL_DOCUMENT_FETCHER_OUTPUT_SCHEMA,
    PLAYBOOK_GENERATOR_OUTPUT_SCHEMA,
    PLAYBOOK_GENERATION_OUTPUT_SCHEMA,
    
    # Namespace template
    LINKEDIN_PLAYBOOK_SYSTEM_DOCUMENT_NAMESPACE_TEMPLATE,
)

# Configuration constants
LLM_PROVIDER = "anthropic"  # anthropic    openai
LLM_MODEL = "claude-sonnet-4-20250514"  # o4-mini   gpt-4.1    claude-sonnet-4-20250514
TEMPERATURE = 0.7
MAX_TOKENS = 4000
MAX_TOOL_CALLS = 25  # Maximum total tool calls allowed
MAX_FEEDBACK_ITERATIONS = 30  # Maximum LLM loop iterations # Maximum feedback loops to prevent infinite iterations

# Workflow JSON structure
workflow_graph_schema = {
    "nodes": {
        # 1. Input Node - No input required
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "company_name": {
                        "type": "str",
                        "required": True,
                        "description": "Entity username for document operations"
                    }
                }
            }
        },
        
        # 2. Load Company LinkedIn Documents
        "load_company_doc": {
            "node_id": "load_company_doc",
            "node_name": "load_customer_data",
            "node_config": {
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": LINKEDIN_USER_PROFILE_DOCNAME,
                        },
                        "output_field_name": "company_doc"
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
                        },
                        "output_field_name": "diagnostic_report_doc"
                    }
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False}
            }
        },
        
        # 3. Play Selection - Prompt Constructor
        "construct_play_selection_prompt": {
            "node_id": "construct_play_selection_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "play_selection_user_prompt": {
                        "id": "play_selection_user_prompt",
                        "template": PLAY_SELECTION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "company_info": None,
                            "diagnostic_report_info": None
                        },
                        "construct_options": {
                            "company_info": "company_doc",
                            "diagnostic_report_info": "diagnostic_report_doc"
                        }
                    },
                    "play_selection_system_prompt": {
                        "id": "play_selection_system_prompt",
                        "template": PLAY_SELECTION_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 4. Play Selection - LLM Node
        "play_suggestion_llm": {
            "node_id": "play_suggestion_llm",
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
                    "schema_definition": PLAY_SELECTION_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 5. Play Selection HITL
        "play_selection_hitl": {
            "node_id": "play_selection_hitl",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "user_action": {
                        "type": "enum",
                        "enum_values": ["approve_plays", "revise_plays", "cancel_workflow"],
                        "required": True,
                        "description": "User's decision on the selected plays"
                    },
                    "feedback": {
                        "type": "str",
                        "required": False,
                        "description": "User feedback for play modifications"
                    },
                    "final_selected_plays": {
                        "type": "list",
                        "required": False,
                        "description": "Final list of plays approved/modified by user"
                    }
                }
            }
        },
        
        # 6. Route Play Selection
        "route_play_selection": {
            "node_id": "route_play_selection", 
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_document_fetcher_prompt", "construct_play_selection_revision_prompt", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_document_fetcher_prompt",
                        "input_path": "user_action",
                        "target_value": "approve_plays"
                    },
                    {
                        "choice_id": "construct_play_selection_revision_prompt",
                        "input_path": "user_action",
                        "target_value": "revise_plays"
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "user_action",
                        "target_value": "cancel_workflow"
                    }
                ],
                "default_choice": "output_node"
            }
        },
        
        # 7. Play Selection Revision - Prompt Constructor
        "construct_play_selection_revision_prompt": {
            "node_id": "construct_play_selection_revision_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "play_selection_revision_user_prompt": {
                        "id": "play_selection_revision_user_prompt",
                        "template": PLAY_SELECTION_REVISION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "company_info": None,
                            "diagnostic_report_info": None,
                            "user_feedback": None,
                            "previous_recommendations": None
                        },
                        "construct_options": {
                            "company_info": "company_doc",
                            "diagnostic_report_info": "diagnostic_report_doc",
                            "user_feedback": "user_feedback",
                            "previous_recommendations": "selected_plays"
                        }
                    },
                    "play_selection_revision_system_prompt": {
                        "id": "play_selection_revision_system_prompt",
                        "template": PLAY_SELECTION_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 9. Document Fetcher - Prompt Constructor
        "construct_document_fetcher_prompt": {
            "node_id": "construct_document_fetcher_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "document_fetcher_user_prompt": {
                        "id": "document_fetcher_user_prompt",
                        "template": DOCUMENT_FETCHER_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "approved_plays": None,
                            "company_doc": None
                        },
                        "construct_options": {
                            "approved_plays": "approved_plays",
                            "company_doc": "company_doc"
                        }
                    },
                    "document_fetcher_system_prompt": {
                        "id": "document_fetcher_system_prompt",
                        "template": DOCUMENT_FETCHER_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 10. Document Fetcher - LLM Node with Tools
        "document_fetcher_llm": {
            "node_id": "document_fetcher_llm",  
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER,
                        "model": LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                    "reasoning_tokens_budget": 2048,
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
                    "schema_definition": INITIAL_DOCUMENT_FETCHER_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 11. Check Document Fetcher Conditions
        "check_document_fetcher_conditions": {
            "node_id": "check_document_fetcher_conditions",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "has_tool_calls",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "tool_calls",
                                "operator": "is_not_empty"
                            }]
                        }]
                    },
                    {
                        "tag": "send_to_playbook_generator",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "structured_output",
                                "operator": "is_not_empty",
                                "value": None
                            }]
                        }]
                    }
                ],
                "branch_logic_operator": "or"
            }
        },
        
        # 12. Route Document Fetcher Actions
        "route_document_fetcher_actions": {
            "node_id": "route_document_fetcher_actions",
            "node_name": "router_node",
            "node_config": {
                "choices": ["document_fetcher_tool_executor", "construct_playbook_generator_prompt"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "document_fetcher_tool_executor",
                        "input_path": "tag_results.has_tool_calls",
                        "target_value": True
                    },
                    {
                        "choice_id": "construct_playbook_generator_prompt",
                        "input_path": "tag_results.send_to_playbook_generator",
                        "target_value": True
                    }
                ],
                "default_choice": "construct_playbook_generator_prompt"
            }
        },
        
        # 13. Tool Executor for Document Fetcher
        "document_fetcher_tool_executor": {
            "node_id": "document_fetcher_tool_executor",
            "node_name": "tool_executor",
            "node_config": {
                "default_timeout": 30.0,
                "max_concurrent_executions": 3,
                "continue_on_error": True,
                "include_error_details": True,
                "map_executor_input_fields_to_tool_input": True
            }
        },
        
        # 15. Playbook Generator - Prompt Constructor
        "construct_playbook_generator_prompt": {
            "node_id": "construct_playbook_generator_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "playbook_generator_user_prompt": {
                        "id": "playbook_generator_user_prompt",
                        "template": PLAYBOOK_GENERATOR_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "fetched_information": None,
                            "company_info": None,
                            "diagnostic_report_info": None
                        },
                        "construct_options": {
                            "fetched_information": "fetched_information",
                            "company_info": "company_doc",
                            "diagnostic_report_info": "diagnostic_report_doc",
                            "approved_plays": "approved_plays"
                        }
                    },
                    "playbook_generator_system_prompt": {
                        "id": "playbook_generator_system_prompt",
                        "template": PLAYBOOK_GENERATOR_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 16. Playbook Generator - LLM Node (no tools, just synthesis)
        "playbook_generator_llm": {
            "node_id": "playbook_generator_llm",
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
                    "schema_definition": PLAYBOOK_GENERATOR_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 22. Playbook Review HITL
        "playbook_review_hitl": {
            "node_id": "playbook_review_hitl",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "user_action": {
                        "type": "enum",
                        "enum_values": ["approve_playbook", "request_revisions", "cancel"],
                        "required": True,
                        "description": "User's decision on the generated playbook"
                    },
                    "revision_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "Feedback for playbook revisions"
                    },
                    "generated_playbook": {
                        "type": "dict",
                        "required": True,
                        "description": "Generated playbook"
                    }
                }
            }
        },
        
        # 23. Route Playbook Review
        "route_playbook_review": {
            "node_id": "route_playbook_review",
            "node_name": "router_node",
            "node_config": {
                "choices": ["store_playbook", "construct_feedback_management_prompt", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "store_playbook",
                        "input_path": "user_action",
                        "target_value": "approve_playbook"
                    },
                    {
                        "choice_id": "construct_feedback_management_prompt",
                        "input_path": "user_action",
                        "target_value": "request_revisions"
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "user_action",
                        "target_value": "cancel"
                    }
                ],
                "default_choice": "output_node"
            }
        },
        
        # 24. Feedback Management Prompt Constructor
        "construct_feedback_management_prompt": {
            "node_id": "construct_feedback_management_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "feedback_management_user_prompt": {
                        "id": "feedback_management_user_prompt",
                        "template": DOCUMENT_FETCHER_REVISION_PROMPT_TEMPLATE,
                        "variables": {
                            "revision_feedback": None,
                            "current_playbook": None,
                            "selected_plays": None,
                            "company_info": None,
                            "diagnostic_report_info": None
                        },
                        "construct_options": {
                            "revision_feedback": "revision_feedback",
                            "current_playbook": "current_playbook",
                            "selected_plays": "approved_plays",
                            "company_info": "company_doc",
                            "diagnostic_report_info": "diagnostic_report_doc"
                        }
                    },
                    "feedback_management_system_prompt": {
                        "id": "feedback_management_system_prompt",
                        "template": PLAYBOOK_REVISION_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 25. Feedback Management LLM (Central Feedback Controller)
        "feedback_management_llm": {
            "node_id": "feedback_management_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER,
                        "model": LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                    "reasoning_tokens_budget": 2048,
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
                    "schema_definition": DOCUMENT_FETCHER_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 26. Check Feedback Management Action
        "check_feedback_management_action": {
            "node_id": "check_feedback_management_action",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "has_tool_calls",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "tool_calls",
                                "operator": "is_not_empty"
                            }]
                        }]
                    },
                    {
                        "tag": "send_to_playbook_generator",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "structured_output.workflow_control.action",
                                "operator": "equals",
                                "value": "send_to_playbook_generator"
                            }]
                        }]
                    },
                    {
                        "tag": "ask_user_clarification",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "structured_output.workflow_control.action",
                                "operator": "equals",
                                "value": "ask_user_clarification"
                            }]
                        }]
                    },
                    {
                        "tag": "iteration_limit_reached",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "feedback_iteration_count",
                                "operator": "greater_than_or_equals",
                                "value": MAX_FEEDBACK_ITERATIONS
                            }]
                        }]
                    }
                ],
                "branch_logic_operator": "or"
            }
        },
        
        # 27. Route Feedback Management
        "route_feedback_management": {
            "node_id": "route_feedback_management",
            "node_name": "router_node",
            "node_config": {
                "choices": ["feedback_tool_executor", "construct_playbook_update_prompt", "feedback_clarification_hitl", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "feedback_tool_executor",
                        "input_path": "tag_results.has_tool_calls",
                        "target_value": True
                    },
                    {
                        "choice_id": "construct_playbook_update_prompt",
                        "input_path": "tag_results.send_to_playbook_generator",
                        "target_value": True
                    },
                    {
                        "choice_id": "feedback_clarification_hitl",
                        "input_path": "tag_results.ask_user_clarification",
                        "target_value": True
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "tag_results.iteration_limit_reached",
                        "target_value": True
                    }
                ],
                "default_choice": "output_node"
            }
        },
        
        # 28. Feedback Tool Executor
        "feedback_tool_executor": {
            "node_id": "feedback_tool_executor",
            "node_name": "tool_executor",
            "node_config": {
                "default_timeout": 30.0,
                "max_concurrent_executions": 3,
                "continue_on_error": True,
                "include_error_details": True,
                "map_executor_input_fields_to_tool_input": True
            }
        },
        
        # 29. Construct Feedback Context Prompt
        "construct_feedback_context_prompt": {
            "node_id": "construct_feedback_context_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "feedback_context_prompt": {
                        "id": "feedback_context_prompt",
                        "template": FEEDBACK_CONTEXT_PROMPT_TEMPLATE,
                        "variables": {
                            "tool_outputs": None,
                            "revision_feedback": None
                        },
                        "construct_options": {
                            "tool_outputs": "tool_outputs",
                            "revision_feedback": "revision_feedback"
                        }
                    }
                }
            }
        },
        
        # 30. Feedback Clarification HITL
        "feedback_clarification_hitl": {
            "node_id": "feedback_clarification_hitl",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "user_action": {
                        "type": "enum",
                        "enum_values": ["provide_clarification", "cancel_workflow"],
                        "required": True,
                        "description": "User's response to clarification request"
                    },
                    "clarification_response": {
                        "type": "str",
                        "required": False,
                        "description": "Additional clarification from user"
                    }
                }
            }
        },
        
        # 31. Route Feedback Clarification
        "route_feedback_clarification": {
            "node_id": "route_feedback_clarification",
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_enhanced_feedback_prompt", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_enhanced_feedback_prompt",
                        "input_path": "user_action",
                        "target_value": "provide_clarification"
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "user_action",
                        "target_value": "cancel_workflow"
                    }
                ],
                "default_choice": "output_node"
            }
        },
        
        # 32. Construct Enhanced Feedback Prompt
        "construct_enhanced_feedback_prompt": {
            "node_id": "construct_enhanced_feedback_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "enhanced_feedback_prompt": {
                        "id": "enhanced_feedback_prompt",
                        "template": ENHANCED_FEEDBACK_PROMPT_TEMPLATE,
                        "variables": {
                            "revision_feedback": None,
                            "clarification_response": None
                        },
                        "construct_options": {
                            "revision_feedback": "revision_feedback",
                            "clarification_response": "clarification_response"
                        }
                    }
                }
            }
        },
        
        # 33. Construct Playbook Update Prompt
        "construct_playbook_update_prompt": {
            "node_id": "construct_playbook_update_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "playbook_update_user_prompt": {
                        "id": "playbook_update_user_prompt",
                        "template": PLAYBOOK_GENERATOR_REVISION_PROMPT_TEMPLATE,
                        "variables": {
                            "current_playbook": None,
                            "revision_feedback": None,
                            "additional_information": None,
                            "company_info": None
                        },
                        "construct_options": {
                            "current_playbook": "current_playbook",
                            "revision_feedback": "revision_feedback",
                            "additional_information": "additional_information",
                            "company_info": "company_doc"
                        }
                    }
                }
            }
        },
        
        # 34. Store Playbook
        "store_playbook": {
            "node_id": "store_playbook",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
                    "operation": "upsert_versioned"
                },
                "global_is_shared": LINKEDIN_CONTENT_PLAYBOOK_IS_SHARED,
                "store_configs": [
                    {
                        "input_field_path": "final_playbook",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
                            }
                        },
                        "versioning": {
                            "is_versioned": LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
                            "operation": "upsert_versioned",
                            "version": "default"
                        },
                        "generate_uuid": True,
                    }
                ],
            }
        },
        
        # 35. Output Node
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {}
        }
    },
    
    "edges": [
        # Input -> State
        {
            "src_node_id": "input_node",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"}
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
        
        # Company Doc -> State
        {
            "src_node_id": "load_company_doc",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "diagnostic_report_doc", "dst_field": "diagnostic_report_doc"}
            ]
        },
        
        # Company Doc -> Play Selection Prompt
        {
            "src_node_id": "load_company_doc",
            "dst_node_id": "construct_play_selection_prompt",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "diagnostic_report_doc", "dst_field": "diagnostic_report_doc"}
            ]
        },
                
        # Play Selection Prompt -> LLM
        {
            "src_node_id": "construct_play_selection_prompt",
            "dst_node_id": "play_suggestion_llm",
            "mappings": [
                {"src_field": "play_selection_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "play_selection_system_prompt", "dst_field": "system_prompt"}
            ]
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "play_suggestion_llm",
            "mappings": [
                {"src_field": "play_suggestion_message_history", "dst_field": "messages_history"}
            ]
        },
        
        # Play Selection LLM -> State
        {
            "src_node_id": "play_suggestion_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "selected_plays"},
                {"src_field": "current_messages", "dst_field": "play_suggestion_message_history"}
            ]
        },
        
        # Play Selection LLM -> HITL
        {
            "src_node_id": "play_suggestion_llm",
            "dst_node_id": "play_selection_hitl",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "play_recommendations"}
            ]
        },
        
        # HITL -> State
        {
            "src_node_id": "play_selection_hitl",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "final_selected_plays", "dst_field": "approved_plays"},
                {"src_field": "feedback", "dst_field": "current_user_feedback_on_plays"}
            ]
        },
        
        # HITL -> Router
        {
            "src_node_id": "play_selection_hitl",
            "dst_node_id": "route_play_selection",
            "mappings": [
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        
        # Router -> Document Fetcher Prompt
        {
            "src_node_id": "route_play_selection",
            "dst_node_id": "construct_document_fetcher_prompt"
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_document_fetcher_prompt",
            "mappings": [
                {"src_field": "approved_plays", "dst_field": "approved_plays"},
                {"src_field": "company_doc", "dst_field": "company_doc"}
            ]
        },
        
        # Router -> Output (cancel)
        {
            "src_node_id": "route_play_selection",
            "dst_node_id": "output_node"
        },
        
        # Router -> Play Selection Revision Prompt (revise plays)
        {
            "src_node_id": "route_play_selection",
            "dst_node_id": "construct_play_selection_revision_prompt"
        },
        
        # State -> Play Selection Revision Prompt (provide documents and feedback)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_play_selection_revision_prompt",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "diagnostic_report_doc", "dst_field": "diagnostic_report_doc"},
                {"src_field": "current_user_feedback_on_plays", "dst_field": "user_feedback"},
                {"src_field": "selected_plays", "dst_field": "selected_plays"}
            ]
        },
        
        # Play Selection Revision Prompt -> Revision LLM
        {
            "src_node_id": "construct_play_selection_revision_prompt",
            "dst_node_id": "play_suggestion_llm",
            "mappings": [
                {"src_field": "play_selection_revision_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "play_selection_revision_system_prompt", "dst_field": "system_prompt"}
            ]
        },


        
        # Document Fetcher Prompt -> LLM
        {
            "src_node_id": "construct_document_fetcher_prompt",
            "dst_node_id": "document_fetcher_llm",
            "mappings": [
                {"src_field": "document_fetcher_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "document_fetcher_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Document Fetcher LLM -> State
        {
            "src_node_id": "document_fetcher_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "document_fetcher_output"},
                {"src_field": "tool_calls", "dst_field": "document_fetcher_tool_calls"},
                {"src_field": "current_messages", "dst_field": "document_fetcher_messages"}
            ]
        },
        
        # Document Fetcher LLM -> Check Conditions
        {
            "src_node_id": "document_fetcher_llm",
            "dst_node_id": "check_document_fetcher_conditions",
            "mappings": [
                {"src_field": "tool_calls", "dst_field": "tool_calls"},
                {"src_field": "structured_output", "dst_field": "structured_output"}
            ]
        },
        
        # Check Conditions -> Route Document Fetcher Actions
        {
            "src_node_id": "check_document_fetcher_conditions",
            "dst_node_id": "route_document_fetcher_actions",
            "mappings": [
                {"src_field": "tag_results", "dst_field": "tag_results"}
            ]
        },
        
        # Route -> Document Fetcher Tool Executor
        {
            "src_node_id": "route_document_fetcher_actions",
            "dst_node_id": "document_fetcher_tool_executor"
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "document_fetcher_tool_executor",
            "mappings": [
                {"src_field": "company_name", "dst_field": "entity_username"},
                {"src_field": "document_fetcher_tool_calls", "dst_field": "tool_calls"}
            ]
        },
        
        # Route -> Playbook Generator Prompt Constructor
        {
            "src_node_id": "route_document_fetcher_actions",
            "dst_node_id": "construct_playbook_generator_prompt"
        },

        {
            "src_node_id": "$graph_state",  
            "dst_node_id": "construct_playbook_generator_prompt",
            "mappings": [
                {"src_field": "document_fetcher_output", "dst_field": "fetched_information"},
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "diagnostic_report_doc", "dst_field": "diagnostic_report_doc"},
                {"src_field": "approved_plays", "dst_field": "approved_plays"}
            ]
        },
        
        # Document Fetcher Tool Executor -> Document Fetcher LLM (continue loop)
        {
            "src_node_id": "document_fetcher_tool_executor",
            "dst_node_id": "document_fetcher_llm",
            "mappings": [
                {"src_field": "tool_outputs", "dst_field": "tool_outputs"}
            ]
        },
        
        # State -> Document Fetcher LLM (provide message history)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "document_fetcher_llm",
            "mappings": [
                {"src_field": "document_fetcher_messages", "dst_field": "messages_history"}
            ]
        },
        
        # Playbook Generator Prompt -> Playbook Generator LLM
        {
            "src_node_id": "construct_playbook_generator_prompt",
            "dst_node_id": "playbook_generator_llm",
            "mappings": [
                {"src_field": "playbook_generator_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "playbook_generator_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Playbook Generator LLM -> State
        {
            "src_node_id": "playbook_generator_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "playbook_generator_output"},
                {"src_field": "current_messages", "dst_field": "playbook_generator_message_history"}
            ]
        },
        
        # Playbook Generator LLM -> Playbook Review HITL (when playbook generated)
        {
            "src_node_id": "playbook_generator_llm",
            "dst_node_id": "playbook_review_hitl",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "generated_playbook"}
            ]
        },
        
        # HITL Review -> Route Playbook Review
        {
            "src_node_id": "playbook_review_hitl",
            "dst_node_id": "route_playbook_review",
            "mappings": [
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        # HITL Review -> State (store revision feedback)
        {
            "src_node_id": "playbook_review_hitl",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "user_action", "dst_field": "final_approval"},
                {"src_field": "revision_feedback", "dst_field": "revision_feedback"},
                {"src_field": "generated_playbook", "dst_field": "user_edited_generated_playbook"}
            ]
        },
        
        # Route Playbook Review -> Store Playbook (approve)
        {
            "src_node_id": "route_playbook_review",
            "dst_node_id": "store_playbook"
        },
        
        # Route Playbook Review -> Feedback Management Prompt Constructor (revise)
        {
            "src_node_id": "route_playbook_review",
            "dst_node_id": "construct_feedback_management_prompt"
        },
        
        # Route Playbook Review -> Output (cancel)
        {
            "src_node_id": "route_playbook_review",
            "dst_node_id": "output_node"
        },
        
        # State -> Feedback Management Prompt Constructor
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_feedback_management_prompt",
            "mappings": [
                {"src_field": "revision_feedback", "dst_field": "revision_feedback"},
                {"src_field": "user_edited_generated_playbook", "dst_field": "current_playbook"},
                {"src_field": "approved_plays", "dst_field": "approved_plays"},
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "diagnostic_report_doc", "dst_field": "diagnostic_report_doc"}
            ]
        },
        
        # Feedback Management Prompt Constructor -> Feedback Management LLM
        {
            "src_node_id": "construct_feedback_management_prompt",
            "dst_node_id": "feedback_management_llm",
            "mappings": [
                {"src_field": "feedback_management_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "feedback_management_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Feedback Management LLM -> State
        {
            "src_node_id": "feedback_management_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "feedback_management_output"},
                {"src_field": "tool_calls", "dst_field": "feedback_tool_calls"},
                {"src_field": "current_messages", "dst_field": "feedback_management_messages"}
            ]
        },
        
        # Feedback Management LLM -> Check Feedback Management Action
        {
            "src_node_id": "feedback_management_llm",
            "dst_node_id": "check_feedback_management_action",
            "mappings": [
                {"src_field": "tool_calls", "dst_field": "tool_calls"},
                {"src_field": "structured_output", "dst_field": "structured_output"}
            ]
        },
        
        # State -> Check Feedback Management Action (provide iteration count)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "check_feedback_management_action",
            "mappings": [
                {"src_field": "feedback_iteration_count", "dst_field": "feedback_iteration_count"}
            ]
        },
        
        # Check Feedback Management Action -> Route Feedback Management
        {
            "src_node_id": "check_feedback_management_action",
            "dst_node_id": "route_feedback_management",
            "mappings": [
                {"src_field": "tag_results", "dst_field": "tag_results"}
            ]
        },
        
        # Route Feedback Management -> Feedback Tool Executor
        {
            "src_node_id": "route_feedback_management",
            "dst_node_id": "feedback_tool_executor"
        },
        
        # Route Feedback Management -> Construct Playbook Update Prompt
        {
            "src_node_id": "route_feedback_management",
            "dst_node_id": "construct_playbook_update_prompt"
        },
        
        # Route Feedback Management -> Feedback Clarification HITL
        {
            "src_node_id": "route_feedback_management",
            "dst_node_id": "feedback_clarification_hitl"
        },
        
        # Route Feedback Management -> Output (iteration limit)
        {
            "src_node_id": "route_feedback_management",
            "dst_node_id": "output_node"
        },
        
        # State -> Feedback Tool Executor
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "feedback_tool_executor",
            "mappings": [
                {"src_field": "company_name", "dst_field": "entity_username"},
                {"src_field": "feedback_tool_calls", "dst_field": "tool_calls"}
            ]
        },
        
        # Feedback Tool Executor -> Construct Feedback Context Prompt
        {
            "src_node_id": "feedback_tool_executor",
            "dst_node_id": "construct_feedback_context_prompt",
            "mappings": [
                {"src_field": "tool_outputs", "dst_field": "tool_outputs"}
            ]
        },
        
        # State -> Construct Feedback Context Prompt (provide revision feedback)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_feedback_context_prompt",
            "mappings": [
                {"src_field": "revision_feedback", "dst_field": "revision_feedback"}
            ]
        },
        
        # Construct Feedback Context Prompt -> Feedback Management LLM (continue loop)
        {
            "src_node_id": "construct_feedback_context_prompt",
            "dst_node_id": "feedback_management_llm",
            "mappings": [
                {"src_field": "feedback_context_prompt", "dst_field": "user_prompt"}
            ]
        },
        
        # State -> Feedback Management LLM (provide message history)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "feedback_management_llm",
            "mappings": [
                {"src_field": "feedback_management_messages", "dst_field": "messages_history"}
            ]
        },
        
        # State -> Feedback Clarification HITL (provide clarification question)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "feedback_clarification_hitl",
            "mappings": [
                {"src_field": "feedback_management_output", "dst_field": "clarification_question"}
            ]
        },
        
        # Feedback Clarification HITL -> Route Feedback Clarification
        {
            "src_node_id": "feedback_clarification_hitl",
            "dst_node_id": "route_feedback_clarification",
            "mappings": [
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        
        # Feedback Clarification HITL -> State (store clarification)
        {
            "src_node_id": "feedback_clarification_hitl",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "clarification_response", "dst_field": "clarification_response"}
            ]
        },
        
        # Route Feedback Clarification -> Construct Enhanced Feedback Prompt
        {
            "src_node_id": "route_feedback_clarification",
            "dst_node_id": "construct_enhanced_feedback_prompt"
        },
        
        # Route Feedback Clarification -> Output (cancel)
        {
            "src_node_id": "route_feedback_clarification",
            "dst_node_id": "output_node"
        },
        
        # State -> Construct Enhanced Feedback Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_enhanced_feedback_prompt",
            "mappings": [
                {"src_field": "revision_feedback", "dst_field": "revision_feedback"},
                {"src_field": "clarification_response", "dst_field": "clarification_response"}
            ]
        },
        
        # Construct Enhanced Feedback Prompt -> Feedback Management LLM (continue with clarification)
        {
            "src_node_id": "construct_enhanced_feedback_prompt",
            "dst_node_id": "feedback_management_llm",
            "mappings": [
                {"src_field": "enhanced_feedback_prompt", "dst_field": "user_prompt"}
            ]
        },
        
        # State -> Construct Playbook Update Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_playbook_update_prompt",
            "mappings": [
                {"src_field": "playbook_generator_output", "dst_field": "current_playbook"},
                {"src_field": "revision_feedback", "dst_field": "revision_feedback"},
                {"src_field": "feedback_management_output", "dst_field": "additional_information"},
                {"src_field": "company_doc", "dst_field": "company_doc"}
            ]
        },
        
        # Construct Playbook Update Prompt -> Playbook Generator LLM (update playbook)
        {
            "src_node_id": "construct_playbook_update_prompt",
            "dst_node_id": "playbook_generator_llm",
            "mappings": [
                {"src_field": "playbook_update_user_prompt", "dst_field": "user_prompt"}
            ]
        },
        
        # State -> Playbook Generator LLM (provide message history for updates)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "playbook_generator_llm",
            "mappings": [
                {"src_field": "playbook_generator_message_history", "dst_field": "messages_history"}
            ]
        },
        
        # State -> Store Playbook
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "store_playbook",
            "mappings": [
                {"src_field": "playbook_generator_output", "dst_field": "final_playbook"},
                {"src_field": "company_name", "dst_field": "company_name"}
            ]
        },
        
        # Store Playbook -> Output
        {
            "src_node_id": "store_playbook",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "document_serial_number", "dst_field": "playbook_document_id"}
            ]
        },
        
        # State -> Output
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "playbook_generator_output", "dst_field": "final_playbook"},
                {"src_field": "selected_plays", "dst_field": "original_play_recommendations"},
                {"src_field": "approved_plays", "dst_field": "approved_plays"}
            ]
        }
    ],
    
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    "metadata": {
        "$graph_state": {
            "reducer": {
                "company_doc": "replace",
                "diagnostic_report_doc": "replace",
                "selected_plays": "replace",
                "approved_plays": "replace",
                "current_user_feedback_on_plays": "replace",
                "document_fetcher_output": "replace",
                "document_fetcher_tool_calls": "replace",
                "document_fetcher_messages": "add_messages",
                "clarification_response_during_document_fetcher": "replace",
                "playbook_generator_output": "replace",
                "user_feedback": "replace",
                "revision_feedback": "replace",
                "play_suggestion_message_history": "add_messages",
                "feedback_management_output": "replace",
                "feedback_tool_calls": "replace",
                "user_edited_generated_playbook": "replace",
                "feedback_management_messages": "add_messages",
                "playbook_generator_message_history": "add_messages",
                "feedback_iteration_count": "replace",
                "playbook_generator_clarification_response": "replace"
            }
        }
    }
}


# --- Testing Code ---

async def validate_playbook_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Validate the LinkedIn content playbook generation workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run.
        
    Returns:
        True if the outputs are valid, False otherwise.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating LinkedIn content playbook generation workflow outputs...")
    
    # Check for expected keys
    expected_keys = [
        'final_playbook',
        'original_play_recommendations',
        'approved_plays'
    ]
    
    for key in expected_keys:
        if key in outputs:
            logger.info(f"✓ Found expected key: {key}")
        else:
            logger.warning(f"⚠ Missing optional key: {key}")
    
    # Validate final playbook structure
    if 'final_playbook' in outputs:
        playbook = outputs['final_playbook']
        assert isinstance(playbook, dict), "Final playbook should be a dict"
        
        required_fields = ['playbook_title', 'executive_summary', 'content_plays']
        for field in required_fields:
            assert field in playbook, f"Playbook missing required field: {field}"
        
        # Validate content plays
        content_plays = playbook['content_plays']
        assert isinstance(content_plays, list), "Content plays should be a list"
        assert len(content_plays) > 0, "Should have at least one content play"
        
        logger.info(f"✓ Generated playbook with {len(content_plays)} content plays")
        logger.info(f"✓ Playbook title: {playbook['playbook_title']}")
    
    # Check for playbook document ID if saved
    if 'playbook_document_id' in outputs and outputs['playbook_document_id'] is not None:
        doc_id = outputs['playbook_document_id']
        if isinstance(doc_id, str) and len(doc_id) > 0:
            logger.info(f"✓ Playbook saved with document ID: {doc_id}")
    
    logger.info("✓ LinkedIn content playbook generation workflow output validation passed.")
    return True


async def main_test_playbook_workflow():
    """
    Test for LinkedIn Content Playbook Generation Workflow.
    """
    test_name = "LinkedIn Content Playbook Generation Workflow Test"
    print(f"--- Starting {test_name} ---")
    
    # Test parameters
    test_company_name = "test_linkedin_company"
    
    # Create test company document data
    company_data = {
        "company_name": "TechVenture Solutions",
        "industry": "B2B SaaS",
        "target_audience": "C-suite executives and decision makers in mid-market companies",
        "business_goals": [
            "Build founder personal brand",
            "Generate enterprise leads through thought leadership",
            "Establish industry authority in digital transformation"
        ],
        "current_content_challenges": [
            "Low LinkedIn engagement rates",
            "Difficulty converting connections to leads",
            "Inconsistent posting schedule"
        ],
        "competitive_landscape": "Competing with established enterprise players and emerging startups",
        "unique_value_proposition": "Only platform combining AI automation with human expertise for mid-market digital transformation",
        "founder_profile": {
            "background": "Former CTO at Fortune 500, 15 years in enterprise tech",
            "expertise": "Digital transformation, AI implementation, scaling operations",
            "personality": "Technical but approachable, data-driven, thought leader"
        }
    }
    
    # Create comprehensive diagnostic report data for LinkedIn
    diagnostic_report_data = {
        "executive_summary": {
            "current_position": "TechVenture Solutions founder has minimal LinkedIn presence with sporadic posting and low engagement, missing significant thought leadership opportunities.",
            "biggest_opportunity": "Building authentic founder-led content strategy leveraging technical expertise and enterprise experience to drive qualified leads.",
            "critical_risk": "Competitors are rapidly building LinkedIn authority while TechVenture remains invisible in key conversations.",
            "overall_diagnostic_score": 4.2
        },
        "immediate_opportunities": {
            "top_content_opportunities": [
                {
                    "title": "Founder Journey Content",
                    "content_type": "Personal Stories + Lessons",
                    "impact_score": 9.5,
                    "implementation_effort": "Low",
                    "timeline": "2-3 weeks"
                },
                {
                    "title": "Technical Deep Dives",
                    "content_type": "Educational Posts",
                    "impact_score": 8.8,
                    "implementation_effort": "Medium",
                    "timeline": "4-6 weeks"
                },
                {
                    "title": "Customer Success Spotlights",
                    "content_type": "Case Studies",
                    "impact_score": 9.0,
                    "implementation_effort": "Medium",
                    "timeline": "3-4 weeks"
                }
            ],
            "linkedin_quick_wins": [
                {
                    "action": "Optimize founder profile with strategic keywords",
                    "estimated_impact": "2x profile views in 30 days",
                    "timeline": "1 week"
                },
                {
                    "action": "Launch weekly thought leadership series",
                    "estimated_impact": "5x engagement rate",
                    "timeline": "2 weeks"
                }
            ],
            "executive_visibility_actions": [
                {
                    "platform": "LinkedIn",
                    "action": "Daily engagement with target audience posts",
                    "frequency": "30 minutes daily",
                    "timeline": "Immediate"
                },
                {
                    "platform": "LinkedIn Newsletter",
                    "action": "Launch bi-weekly industry insights newsletter",
                    "frequency": "Bi-weekly",
                    "timeline": "3 weeks"
                }
            ]
        },
        "content_audit_summary": {
            "total_posts_last_90_days": 8,
            "avg_engagement_rate": 1.8,
            "follower_growth_rate": 0.5,
            "top_performing_topics": ["AI Implementation", "Team Building"],
            "content_gaps": ["Thought Leadership", "Industry Trends", "Personal Insights"]
        },
        "competitive_analysis": {
            "main_competitors_linkedin": ["TechCorp CEO - 50K followers", "InnovateSoft Founder - 35K followers"],
            "competitive_advantages": ["Technical depth", "Enterprise experience", "Authentic voice"],
            "content_opportunities": ["Technical tutorials", "Contrarian viewpoints", "Behind-the-scenes content"]
        }
    }
    
    # Setup test documents
    setup_docs: List[SetupDocInfo] = [
        {
            'namespace': LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item=test_company_name),
            'docname': LINKEDIN_USER_PROFILE_DOCNAME,
            'initial_data': company_data,
            'is_shared': LINKEDIN_USER_PROFILE_IS_SHARED,
            'is_versioned': LINKEDIN_USER_PROFILE_IS_VERSIONED,
            'initial_version': None,
            'is_system_entity': LINKEDIN_USER_PROFILE_IS_SYSTEM_ENTITY
        },
        {
            'namespace': f"linkedin_content_diagnostic_report_{test_company_name}",
            'docname': LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
            'initial_data': diagnostic_report_data,
            'is_shared': LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_IS_SHARED,
            'is_versioned': LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_IS_VERSIONED,
            'initial_version': None,
            'is_system_entity': LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_IS_SYSTEM_ENTITY
        }
    ]
    
    # Cleanup configuration
    cleanup_docs: List[CleanupDocInfo] = [
        {
            'namespace': LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item=test_company_name),
            'docname': LINKEDIN_USER_PROFILE_DOCNAME,
            'is_shared': LINKEDIN_USER_PROFILE_IS_SHARED,
            'is_versioned': LINKEDIN_USER_PROFILE_IS_VERSIONED,
            'is_system_entity': LINKEDIN_USER_PROFILE_IS_SYSTEM_ENTITY
        },
        {
            'namespace': f"linkedin_content_diagnostic_report_{test_company_name}",
            'docname': LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
            'is_shared': LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_IS_SHARED,
            'is_versioned': LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_IS_VERSIONED,
            'is_system_entity': LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_IS_SYSTEM_ENTITY
        }
    ]
    
    # Test inputs - just entity username
    test_inputs = {
        "company_name": test_company_name
    }
    
    # Predefined HITL inputs - leaving empty for interactive testing
    predefined_hitl_inputs = []
    
    # VALID HUMAN INPUTS FOR MANUAL TESTING:
    # Play Selection HITL:
    # {"user_action": "approve_plays", "final_selected_plays": [...]}
    # {"user_action": "modify_plays", "feedback": "Add more technical plays", "final_selected_plays": [...]}
    # {"user_action": "revise_plays", "feedback": "Please regenerate different play recommendations"}
    # {"user_action": "cancel_workflow"}
    
    # Playbook Review HITL:
    # {"user_action": "approve_playbook"}
    # {"user_action": "request_revisions", "revision_feedback": "Need more specific timelines and better examples"}
    # {"user_action": "cancel"}
    
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
        validate_output_func=validate_playbook_output,
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=1800  # 30 minutes
    )
    
    print(f"--- {test_name} Finished ---")
    if final_run_outputs:
        if 'final_playbook' in final_run_outputs:
            playbook = final_run_outputs['final_playbook']
            print(f"Generated Playbook: {playbook.get('playbook_title', 'N/A')}")
            print(f"Content Plays: {len(playbook.get('content_plays', []))}")
        
        if 'playbook_document_id' in final_run_outputs:
            print(f"Playbook Saved: Document ID {final_run_outputs['playbook_document_id']}")


# Entry point
if __name__ == "__main__":
    print("="*80)
    print("LinkedIn Content Playbook Generation Workflow Test")
    print("="*80)
    
    try:
        asyncio.run(main_test_playbook_workflow())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.exception("Test execution failed")
    
    print("\nTest execution finished.")
    print("Run from project root: PYTHONPATH=. python kiwi_client/active/playbook/wf_linkedin_content_playbook_generation.py")