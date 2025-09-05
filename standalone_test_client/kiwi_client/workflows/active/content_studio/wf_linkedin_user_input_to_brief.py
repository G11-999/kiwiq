"""
Content Strategy Brief Generation Workflow

This workflow creates strategic content briefs based on executive profiles and content strategy:
- Load content strategy and executive profile documents
- Generate strategic topic suggestions with content type recommendations
- Human-in-the-loop topic and content type selection
- Knowledge base research for selected topic
- Comprehensive content brief generation with strategic alignment
- Human-in-the-loop brief approval and revision
- Document storage and output management

Key Features:
- Executive profile and content strategy integration
- Strategic topic generation with content type diversity
- Knowledge base research and integration
- HITL approval flows for topic selection and brief approval
- Comprehensive content brief with strategic alignment
- Multiple content type suggestions per topic
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
    LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
    LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE,
    LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
    LINKEDIN_USER_PROFILE_DOCNAME,
    LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
    LINKEDIN_USER_PROFILE_IS_VERSIONED,
    LINKEDIN_BRIEF_DOCNAME,
    LINKEDIN_BRIEF_NAMESPACE_TEMPLATE,
    LINKEDIN_BRIEF_IS_VERSIONED,
)

# Import LLM inputs
from kiwi_client.workflows.active.content_studio.llm_inputs.linkedin_user_input_to_brief import (
    # System prompts
    TOPIC_GENERATION_SYSTEM_PROMPT,
    KNOWLEDGE_BASE_QUERY_SYSTEM_PROMPT,
    BRIEF_GENERATION_SYSTEM_PROMPT,
    
    # User prompt templates
    TOPIC_GENERATION_USER_PROMPT_TEMPLATE,
    TOPIC_REGENERATION_USER_PROMPT_TEMPLATE,
    KNOWLEDGE_BASE_QUERY_USER_PROMPT_TEMPLATE,
    BRIEF_GENERATION_USER_PROMPT_TEMPLATE,
    
    # Brief feedback prompts
    BRIEF_FEEDBACK_SYSTEM_PROMPT,
    BRIEF_FEEDBACK_INITIAL_USER_PROMPT,
    
    # Revision prompts (new)
    BRIEF_REVISION_SYSTEM_PROMPT,
    BRIEF_REVISION_USER_PROMPT_TEMPLATE,
    
    # Output schemas
    TOPIC_GENERATION_OUTPUT_SCHEMA,
    KNOWLEDGE_BASE_QUERY_OUTPUT_SCHEMA,
    BRIEF_GENERATION_OUTPUT_SCHEMA,
    BRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA,
)

# LLM Configuration
LLM_PROVIDER = "anthropic"
LLM_MODEL = "claude-sonnet-4-20250514"
TEMPERATURE = 0.7
MAX_TOKENS = 4000

# # Perplexity Configuration for Reddit Research
# PERPLEXITY_PROVIDER = "perplexity"
# PERPLEXITY_MODEL = "sonar-pro"
# PERPLEXITY_TEMPERATURE = 0.5
# PERPLEXITY_MAX_TOKENS = 3000

# Workflow Limits
MAX_REGENERATION_ATTEMPTS = 3
MAX_REVISION_ATTEMPTS = 3
MAX_ITERATIONS = 10  # Maximum iterations for HITL feedback loops

# Feedback LLM Configuration
FEEDBACK_LLM_PROVIDER = "anthropic"
FEEDBACK_ANALYSIS_MODEL = "claude-sonnet-4-20250514"
FEEDBACK_TEMPERATURE = 0.5
FEEDBACK_MAX_TOKENS = 3000 

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
                    "entity_username": {
                        "type": "str",
                        "required": True,
                        "description": "Name of the entity for document operations"
                    },
                    "user_input": {
                        "type": "str",
                        "required": True,
                        "description": "User input for the workflow"
                    },
                    "initial_status": {
                        "type": "str",
                        "required": False,
                        "default": "draft",
                        "description": "Initial status of the workflow"
                    },
                    "brief_uuid": {
                        "type": "str",
                        "required": True,
                        "description": "UUID of the brief being generated"
                    }
                }
            }
        },
        
        # 2. Load Customer Documents (Content Strategy and Executive Profile)
        "load_customer_documents": {
            "node_id": "load_customer_documents",
            "node_name": "load_customer_data",
            "node_config": {
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
                        },
                        "output_field_name": "content_strategy_doc"
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_USER_PROFILE_DOCNAME,
                        },
                        "output_field_name": "executive_profile_doc"
                    }
                ]
            }
        },
        
        # 3. Topic Generation - Prompt Constructor
        "construct_topic_generation_prompt": {
            "node_id": "construct_topic_generation_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "topic_generation_user_prompt": {
                        "id": "topic_generation_user_prompt",
                        "template": TOPIC_GENERATION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "user_input": None,
                            "executive_profile": None,
                            "content_strategy": None,
                        },
                        "construct_options": {
                            "user_input": "user_input",
                            "executive_profile": "executive_profile_doc",
                            "content_strategy": "content_strategy_doc",
                        }
                    },
                    "topic_generation_system_prompt": {
                        "id": "topic_generation_system_prompt",
                        "template": TOPIC_GENERATION_SYSTEM_PROMPT,
                        "variables": {},
                    }
                }
            }
        },
        
        # 4. Topic Generation - LLM Node
        "topic_generation_llm": {
            "node_id": "topic_generation_llm",
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
                    "schema_definition": TOPIC_GENERATION_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 5. Topic Selection - HITL Node
        "topic_selection_hitl": {
            "node_id": "topic_selection_hitl",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "user_action": {
                        "type": "enum",
                        "enum_values": ["complete", "provide_feedback", "cancel_workflow"],
                        "required": True,
                        "description": "User's decision on topic and content type selection"
                    },
                    "selected_topic_id": {
                        "type": "str",
                        "required": False,
                        "description": "Single topic_id selected by user (required if complete)"
                    },
                    "revision_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "Feedback for topic regeneration (required if provide_feedback)"
                    }
                }
            }
        },
        
        # 6. Route Topic Selection
        "route_topic_selection": {
            "node_id": "route_topic_selection",
            "node_name": "router_node",
            "node_config": {
                "choices": ["filter_selected_topic", "check_topic_iteration_limit", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "filter_selected_topic",
                        "input_path": "user_action",
                        "target_value": "complete"
                    },
                    {
                        "choice_id": "check_topic_iteration_limit",
                        "input_path": "user_action",
                        "target_value": "provide_feedback"
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
        
        # 6.5. Check Topic Iteration Limit
        "check_topic_iteration_limit": {
            "node_id": "check_topic_iteration_limit",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "topic_iteration_limit_check",
                        "condition_groups": [ {
                            "logical_operator": "and",
                            "conditions": [ {
                                "field": "topic_generation_metadata.iteration_count",
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

        # 6.6. Route Based on Topic Iteration Limit Check
        "route_on_topic_limit_check": {
            "node_id": "route_on_topic_limit_check",
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_topic_regeneration_prompt", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_topic_regeneration_prompt",
                        "input_path": "if_else_condition_tag_results.topic_iteration_limit_check",
                        "target_value": True
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "iteration_branch_result",
                        "target_value": "false_branch"
                    }
                ]
            }
        },

        # 7. Topic Regeneration - Enhanced Prompt Constructor
        "construct_topic_regeneration_prompt": {
            "node_id": "construct_topic_regeneration_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "topic_regeneration_user_prompt": {
                        "id": "topic_regeneration_user_prompt",
                        "template": TOPIC_REGENERATION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "user_input": None,
                            "executive_profile": None,
                            "content_strategy": None,
                            "regeneration_feedback": None
                        },
                        "construct_options": {
                            "user_input": "user_input",
                            "executive_profile": "executive_profile_doc",
                            "content_strategy": "content_strategy_doc",
                            "regeneration_feedback": "regeneration_feedback"
                        }
                    },
                    "topic_regeneration_system_prompt": {
                        "id": "topic_regeneration_system_prompt",
                        "template": TOPIC_GENERATION_SYSTEM_PROMPT,
                        "variables": {},
                    }
                }
            }
        },
        
        # 8. Topic Regeneration - LLM Node
        "topic_regeneration_llm": {
            "node_id": "topic_regeneration_llm",
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
                    "schema_definition": TOPIC_GENERATION_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 9. Filter Selected Topic
        "filter_selected_topic": {
            "node_id": "filter_selected_topic",
            "node_name": "filter_data",
            "node_config": {
                "targets": [
                    {
                        "filter_target": "current_topic_suggestions.suggested_topics",  # Target the topics list
                        "condition_groups": [
                            {
                                "conditions": [
                                    {
                                        "field": "current_topic_suggestions.suggested_topics.topic_id",
                                        "operator": "equals_any_of",
                                        "value_path": "selected_topic_id"
                                    }
                                ]
                            }
                        ],
                        "filter_mode": "allow"  # Only allow topics that match the condition
                    }
                ]
            }
        },
        
        # 10. Knowledge Base Query - Prompt Constructor
        "construct_knowledge_base_query_prompt": {
            "node_id": "construct_knowledge_base_query_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "knowledge_base_query_user_prompt": {
                        "id": "knowledge_base_query_user_prompt",
                        "template": KNOWLEDGE_BASE_QUERY_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "user_input": None,
                            "selected_topic": None,
                            "content_strategy": None
                        },
                        "construct_options": {
                            "user_input": "user_input",
                            "selected_topic": "selected_topic",
                            "content_strategy": "content_strategy_doc"
                        }
                    },
                    "knowledge_base_query_system_prompt": {
                        "id": "knowledge_base_query_system_prompt",
                        "template": KNOWLEDGE_BASE_QUERY_SYSTEM_PROMPT,
                        "variables": {},
                    }
                }
            }
        },
        
        # 11. Knowledge Base Query - LLM Node
        "knowledge_base_query_llm": {
            "node_id": "knowledge_base_query_llm",
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
                    "schema_definition": KNOWLEDGE_BASE_QUERY_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 12. Brief Generation - Prompt Constructor
        "construct_brief_generation_prompt": {
            "node_id": "construct_brief_generation_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "brief_generation_user_prompt": {
                        "id": "brief_generation_user_prompt",
                        "template": BRIEF_GENERATION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "user_input": None,
                            "selected_topic": None,
                            "executive_profile": None,
                            "content_strategy": None,
                            "knowledge_base_research": None,
                        },
                        "construct_options": {
                            "user_input": "user_input",
                            "selected_topic": "selected_topic",
                            "executive_profile": "executive_profile_doc",
                            "content_strategy": "content_strategy_doc",
                            "knowledge_base_research": "knowledge_base_queries",
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
        
        # 13. Brief Generation - LLM Node
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

        "save_as_draft_after_brief_generation": {
            "node_id": "save_as_draft_after_brief_generation",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": LINKEDIN_BRIEF_IS_VERSIONED,
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
                                "input_docname_field_pattern": LINKEDIN_BRIEF_DOCNAME,
                                "input_docname_field": "brief_uuid"
                            }
                        },
                        "extra_fields": [
                            {
                                "src_path": "initial_status",
                                "dst_path": "status"
                            },
                            {
                                "src_path": "brief_uuid",
                                "dst_path": "uuid"
                            }
                        ],
                        "versioning": {
                            "is_versioned": LINKEDIN_BRIEF_IS_VERSIONED,
                            "operation": "upsert_versioned"                        
                    }
                    }
                ],
            }
        },
        
        # 14. Brief Approval - HITL Node
        "brief_approval_hitl": {
            "node_id": "brief_approval_hitl",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "user_brief_action": {
                        "type": "enum",
                        "enum_values": ["complete", "provide_feedback", "cancel_workflow", "draft"],
                        "required": True,
                        "description": "User's decision on brief approval"
                    },
                    "revision_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "Feedback for brief revision (required if provide_feedback)"
                    },
                    "updated_content_brief": {
                        "type": "dict",
                        "required": True,
                        "description": "Updated content brief with any manual edits"
                    }
                }
            }
        },

        # 15. Route Brief Approval
        "route_brief_approval": {
            "node_id": "route_brief_approval",
            "node_name": "router_node",
            "node_config": {
                "choices": ["check_iteration_limit", "delete_draft_brief", "save_brief", "save_final_brief"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "save_final_brief",
                        "input_path": "user_brief_action",
                        "target_value": "complete"
                    },
                    {
                        "choice_id": "check_iteration_limit",
                        "input_path": "user_brief_action",
                        "target_value": "provide_feedback"
                    },
                    {
                        "choice_id": "delete_draft_brief",
                        "input_path": "user_brief_action",
                        "target_value": "cancel_workflow"
                    },
                    {
                        "choice_id": "save_brief",
                        "input_path": "user_brief_action",
                        "target_value": "draft"
                    }
                ],
                "default_choice": "delete_draft_brief"
            }
        },

        "save_brief": {
            "node_id": "save_brief",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": LINKEDIN_BRIEF_IS_VERSIONED,
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
                                "input_docname_field_pattern": LINKEDIN_BRIEF_DOCNAME,
                                "input_docname_field": "brief_uuid"
                            }
                        },
                        "extra_fields": [
                            {
                                "src_path": "initial_status",
                                "dst_path": "status"
                            },
                            {
                                "src_path": "brief_uuid",
                                "dst_path": "uuid"
                            }
                        ]
                    }
                ],
            }
        },
        
        # 16. Check Iteration Limit
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
        
        # 17. Route Based on Iteration Limit Check
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
        
        # 18. Brief Feedback Prompt Constructor
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
                            "executive_profile": None,
                            "content_strategy": None,
                            "selected_topic": None,
                            "knowledge_base_research": None
                        },
                        "construct_options": {
                            "content_brief": "current_content_brief",
                            "revision_feedback": "current_revision_feedback",
                            "executive_profile": "executive_profile_doc",
                            "content_strategy": "content_strategy_doc",
                            "selected_topic": "selected_topics",
                            "knowledge_base_research": "knowledge_base_queries"
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
        
        # 19. Brief Feedback Analysis - Analyze user feedback before revision
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
        
        # 20. Brief Revision - Enhanced Prompt Constructor
        "construct_brief_revision_prompt": {
            "node_id": "construct_brief_revision_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "brief_revision_user_prompt": {
                        "id": "brief_revision_user_prompt",
                        "template": BRIEF_REVISION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "current_content_brief": None,
                            "brief_feedback_analysis": None
                        },
                        "construct_options": {
                            "current_content_brief": "current_content_brief",
                            "brief_feedback_analysis": "brief_feedback_analysis"
                        }
                    },
                    "brief_revision_system_prompt": {
                        "id": "brief_revision_system_prompt",
                        "template": BRIEF_REVISION_SYSTEM_PROMPT,
                        "variables": {},
                    }
                }
            }
        },
        
        # 21. Brief Revision - LLM Node
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
        
        # 22. Save Brief - Store Customer Data
        "save_final_brief": {
            "node_id": "save_final_brief",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": LINKEDIN_BRIEF_IS_VERSIONED,
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
                                "input_docname_field_pattern": LINKEDIN_BRIEF_DOCNAME,
                                "input_docname_field": "brief_uuid"
                            }
                        },
                        "versioning": {
                            "is_versioned": LINKEDIN_BRIEF_IS_VERSIONED,
                            "operation": "upsert_versioned"
                        },
                        "extra_fields": [
                            {
                                "src_path": "user_brief_action",
                                "dst_path": "status"
                            },
                            {
                                "src_path": "brief_uuid",
                                "dst_path": "uuid"
                            }
                        ]
                    }
                ],
            }
        },
        
        # 22.5. Delete Draft Brief - When user cancels at brief approval
        "delete_draft_brief": {
            "node_id": "delete_draft_brief", 
            "node_name": "delete_customer_data",
            "node_config": {
                "search_params": {
                    "input_namespace_field": "entity_username",
                    "input_namespace_field_pattern": LINKEDIN_BRIEF_NAMESPACE_TEMPLATE,
                    "input_docname_field": "brief_uuid",
                    "input_docname_field_pattern": LINKEDIN_BRIEF_DOCNAME
                }
            }
        },
        
        # 23. Extract Document Name - Transform Node
        "extract_document_name": {
            "node_id": "extract_document_name",
            "node_name": "transform_data",
            "node_config": {
                "mappings": [
                    {
                        "source_path": "final_paths_processed.0.1",
                        "destination_path": "document_id"
                    }
                ]
            }
        },
        
        # 24. Output Node
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
                {"src_field": "user_input", "dst_field": "user_input"},
                {"src_field": "initial_status", "dst_field": "initial_status"},
                {"src_field": "brief_uuid", "dst_field": "brief_uuid"}
            ]
        },
        
        # Input -> Load Customer Documents
        {
            "src_node_id": "input_node",
            "dst_node_id": "load_customer_documents",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"}
            ]
        },
        
        # Customer Documents -> State
        {
            "src_node_id": "load_customer_documents",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"},
                {"src_field": "executive_profile_doc", "dst_field": "executive_profile_doc"}
            ]
        },
        
        # Customer Documents -> Topic Generation Prompt Constructor
        {
            "src_node_id": "load_customer_documents",
            "dst_node_id": "construct_topic_generation_prompt",
            "mappings": [
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"},
                {"src_field": "executive_profile_doc", "dst_field": "executive_profile_doc"}
            ]
        },
        
        # State -> Topic Generation Prompt Constructor (user_input)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_topic_generation_prompt",
            "mappings": [
                {"src_field": "user_input", "dst_field": "user_input"}
            ]
        },
        
        # Topic Generation Prompt -> LLM
        {
            "src_node_id": "construct_topic_generation_prompt",
            "dst_node_id": "topic_generation_llm",
            "mappings": [
                {"src_field": "topic_generation_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "topic_generation_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # State -> Topic Generation LLM (message history)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "topic_generation_llm",
            "mappings": [
                {"src_field": "topic_generation_messages_history", "dst_field": "messages_history"}
            ]
        },
        
        # Topic Generation LLM -> State
        {
            "src_node_id": "topic_generation_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "current_topic_suggestions"},
                {"src_field": "current_messages", "dst_field": "topic_generation_messages_history"},
                {"src_field": "metadata", "dst_field": "topic_generation_metadata", "description": "Store topic generation LLM metadata (e.g., iteration count)."}
            ]
        },
        
        # Topic Generation LLM -> HITL
        {
            "src_node_id": "topic_generation_llm",
            "dst_node_id": "topic_selection_hitl",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "topic_suggestions"}
            ]
        },
        
        # HITL -> Route Topic Selection
        {
            "src_node_id": "topic_selection_hitl",
            "dst_node_id": "route_topic_selection",
            "mappings": [
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        
        # HITL -> State
        {
            "src_node_id": "topic_selection_hitl",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "user_action", "dst_field": "user_action"},
                {"src_field": "selected_topic_id", "dst_field": "selected_topic_id"},
                {"src_field": "regeneration_feedback", "dst_field": "current_regeneration_feedback"}
            ]
        },
        
        # --- Topic Selection Router Paths ---
        {
            "src_node_id": "route_topic_selection",
            "dst_node_id": "filter_selected_topic",
            "description": "Route to filter selected topics if accepted"
        },
        {
            "src_node_id": "route_topic_selection",
            "dst_node_id": "check_topic_iteration_limit",
            "description": "Route to check iteration limit if topic regeneration requested"
        },
        {
            "src_node_id": "route_topic_selection",
            "dst_node_id": "output_node",
            "description": "Route to output if workflow cancelled"
        },

        # Check Topic Iteration Limit edges
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "check_topic_iteration_limit",
            "mappings": [
                {"src_field": "topic_generation_metadata", "dst_field": "topic_generation_metadata", "description": "Pass topic LLM metadata containing iteration count."}
            ]
        },
        {
            "src_node_id": "check_topic_iteration_limit",
            "dst_node_id": "route_on_topic_limit_check",
            "mappings": [
                {"src_field": "branch", "dst_field": "iteration_branch_result", "description": "Pass the branch taken ('true_branch' if limit not reached, 'false_branch' if reached)."},
                {"src_field": "tag_results", "dst_field": "if_else_condition_tag_results", "description": "Pass detailed results per condition tag."}            ]
        },
        {
            "src_node_id": "route_on_topic_limit_check",
            "dst_node_id": "construct_topic_regeneration_prompt",
            "description": "Trigger topic regeneration if iterations remain"
        },
        {
            "src_node_id": "route_on_topic_limit_check",
            "dst_node_id": "output_node",
            "description": "Exit if topic iteration limit reached"
        },
        
        # State -> Topic Regeneration Prompt Constructor
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_topic_regeneration_prompt",
            "mappings": [
                {"src_field": "user_input", "dst_field": "user_input"},
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"},
                {"src_field": "executive_profile_doc", "dst_field": "executive_profile_doc"},
                {"src_field": "current_regeneration_feedback", "dst_field": "regeneration_feedback"}
            ]
        },
        
        # Topic Regeneration Prompt -> LLM
        {
            "src_node_id": "construct_topic_regeneration_prompt",
            "dst_node_id": "topic_regeneration_llm",
            "mappings": [
                {"src_field": "topic_regeneration_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "topic_regeneration_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # State -> Topic Regeneration LLM (message history)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "topic_regeneration_llm",
            "mappings": [
                {"src_field": "topic_generation_messages_history", "dst_field": "messages_history"}
            ]
        },
        
        # Topic Regeneration LLM -> HITL (loop back)
        {
            "src_node_id": "topic_regeneration_llm",
            "dst_node_id": "topic_selection_hitl",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "topic_suggestions"}
            ]
        },
        
        # Topic Regeneration LLM -> State
        {
            "src_node_id": "topic_regeneration_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "current_topic_suggestions"},
                {"src_field": "current_messages", "dst_field": "topic_generation_messages_history"},
                {"src_field": "metadata", "dst_field": "topic_generation_metadata", "description": "Store topic regeneration LLM metadata (e.g., iteration count)."}
            ]
        },
        
        # State -> Filter Selected Topic
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "filter_selected_topic",
            "mappings": [
                {"src_field": "current_topic_suggestions", "dst_field": "current_topic_suggestions"},
                {"src_field": "selected_topic_id", "dst_field": "selected_topic_id"}
            ]
        },
        
        # Filter Selected Topic -> State (store selected topic)
        {
            "src_node_id": "filter_selected_topic",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "selected_topics"}
            ]
        },
        
        # Filter Selected Topic -> Knowledge Base Query Prompt
        {
            "src_node_id": "filter_selected_topic",
            "dst_node_id": "construct_knowledge_base_query_prompt",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "selected_topic"}
            ]
        },
        
        # State -> Knowledge Base Query Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_knowledge_base_query_prompt",
            "mappings": [
                {"src_field": "user_input", "dst_field": "user_input"},
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"},
                {"src_field": "selected_topics", "dst_field": "selected_topic"}
            ]
        },
        
        # Knowledge Base Query Prompt -> LLM
        {
            "src_node_id": "construct_knowledge_base_query_prompt",
            "dst_node_id": "knowledge_base_query_llm",
            "mappings": [
                {"src_field": "knowledge_base_query_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "knowledge_base_query_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Knowledge Base Query LLM -> State
        {
            "src_node_id": "knowledge_base_query_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "knowledge_base_queries"}
            ]
        },
        
        # Knowledge Base Query LLM -> Brief Generation Prompt
        {
            "src_node_id": "knowledge_base_query_llm",
            "dst_node_id": "construct_brief_generation_prompt",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "knowledge_base_queries"}
            ]
        },
        
        # State -> Brief Generation Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_brief_generation_prompt",
            "mappings": [
                {"src_field": "user_input", "dst_field": "user_input"},
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"},
                {"src_field": "executive_profile_doc", "dst_field": "executive_profile_doc"},
                {"src_field": "selected_topics", "dst_field": "selected_topic"},
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
                {"src_field": "metadata", "dst_field": "generation_metadata", "description": "Store LLM metadata (e.g., token usage, iteration count)."}
            ]
        },
        
        # Brief Generation LLM -> Save as Draft
        {
            "src_node_id": "brief_generation_llm",
            "dst_node_id": "save_as_draft_after_brief_generation",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "current_content_brief"}
            ]
        },

        # Brief Generation LLM -> Brief Approval HITL
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_as_draft_after_brief_generation",
            "mappings": [
                {"src_field": "initial_status", "dst_field": "initial_status"},
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "brief_uuid", "dst_field": "brief_uuid"}
            ]
        },
        
        # Brief Generation LLM -> Brief Approval HITL
        {
            "src_node_id": "save_as_draft_after_brief_generation",
            "dst_node_id": "brief_approval_hitl"
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "brief_approval_hitl",
            "mappings": [
                {"src_field": "current_content_brief", "dst_field": "content_brief"}
            ]
        },

                # Brief Approval HITL -> Route Brief Approval
        {
            "src_node_id": "brief_approval_hitl",
            "dst_node_id": "route_brief_approval",
            "mappings": [
                {"src_field": "user_brief_action", "dst_field": "user_brief_action"}
            ]
        },
        
        # Brief Approval HITL -> State
        {
            "src_node_id": "brief_approval_hitl",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "revision_feedback", "dst_field": "current_revision_feedback"},
                {"src_field": "updated_content_brief", "dst_field": "current_content_brief"},
                {"src_field": "user_brief_action", "dst_field": "user_brief_action"}
            ]
        },


        {
            "src_node_id": "route_brief_approval",
            "dst_node_id": "check_iteration_limit",
            "description": "Route to check iteration limit if revision requested"
        },
        {
            "src_node_id": "route_brief_approval",
            "dst_node_id": "delete_draft_brief",
            "description": "Route to delete draft if workflow cancelled"
        },
        {
            "src_node_id": "route_brief_approval",
            "dst_node_id": "save_brief",
            "description": "Route to brief approval if draft"
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_brief",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "initial_status", "dst_field": "initial_status"},
                {"src_field": "brief_uuid", "dst_field": "brief_uuid"},
                {"src_field": "current_content_brief", "dst_field": "current_content_brief"}
            ]
        },

        {
            "src_node_id": "save_brief",
            "dst_node_id": "brief_approval_hitl"
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
                {"src_field": "tag_results", "dst_field": "if_else_condition_tag_results", "description": "Pass detailed results per condition tag."}            ]
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
        
        # State -> Brief Feedback Prompt Constructor
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_brief_feedback_prompt",
            "mappings": [
                {"src_field": "current_content_brief", "dst_field": "current_content_brief"},
                {"src_field": "current_revision_feedback", "dst_field": "current_revision_feedback"},
                {"src_field": "executive_profile_doc", "dst_field": "executive_profile_doc"},
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"},
                {"src_field": "selected_topics", "dst_field": "selected_topics"},
                {"src_field": "knowledge_base_queries", "dst_field": "knowledge_base_queries"}
            ]
        },
        
        # Brief Feedback Prompt -> Analysis LLM
        {
            "src_node_id": "construct_brief_feedback_prompt",
            "dst_node_id": "analyze_brief_feedback",
            "mappings": [
                {"src_field": "brief_feedback_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "brief_feedback_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # State -> Brief Feedback Analysis LLM (message history)
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
                {"src_field": "current_content_brief", "dst_field": "current_content_brief"}
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
        
        # Brief Revision LLM -> Brief Approval HITL (loop back)
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
                {"src_field": "metadata", "dst_field": "generation_metadata", "description": "Store LLM metadata (e.g., token usage, iteration count)."}
            ]
        },

        {
            "src_node_id": "route_brief_approval",
            "dst_node_id": "save_final_brief",
            "description": "Route to save final brief if complete"
        },

        # Brief Revision LLM -> Save Final Brief
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_final_brief",
            "mappings": [
                {"src_field": "current_content_brief", "dst_field": "final_content_brief"},
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "user_brief_action", "dst_field": "user_brief_action"},
                {"src_field": "brief_uuid", "dst_field": "brief_uuid"}
            ]
        },

        {
            "src_node_id": "save_final_brief",
            "dst_node_id": "extract_document_name",
            "mappings": [
                {"src_field": "paths_processed", "dst_field": "final_paths_processed"}
            ]
        },

        {
            "src_node_id": "extract_document_name",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "transformed_data"}
            ]
        },
        
        # Delete Draft Brief edges (when user cancels at brief approval)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "delete_draft_brief",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "brief_uuid", "dst_field": "brief_uuid"}
            ],
            "description": "Pass entity_username and brief_uuid to delete the draft"
        },
        {
            "src_node_id": "delete_draft_brief",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "deleted_count", "dst_field": "draft_deleted_count"},
                {"src_field": "deleted_documents", "dst_field": "deleted_draft_documents"}
            ],
            "description": "Route to output after deleting draft"
        }
    ],
    
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    "metadata": {
        "$graph_state": {
            "reducer": {
                "current_topic_suggestions": "replace",
                "current_content_brief": "replace",
                "current_regeneration_feedback": "replace",
                "current_revision_feedback": "replace",
                "knowledge_base_queries": "replace",
                "selected_topics": "replace",
                "brief_feedback_analysis": "replace",
                "user_action": "replace",
                "user_brief_action": "replace",
                "generation_metadata": "replace",
                "topic_generation_messages_history": "add_messages",
                "brief_generation_messages_history": "add_messages",
                "brief_feedback_analysis_messages_history": "add_messages",
                "topic_generation_metadata": "replace"
            }
        }
    }
}


# --- Testing Code ---

async def validate_content_brief_workflow_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Validate the content strategy brief generation workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run.
        
    Returns:
        True if the outputs are valid, False otherwise.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating content strategy brief generation workflow outputs...")
    
    # Check for expected keys
    expected_keys = [
        'final_topic_suggestions',
        'selected_topic',
        'knowledge_base_research',
        'final_content_brief',
        'document_name'
    ]
    
    for key in expected_keys:
        if key in outputs:
            logger.info(f"✓ Found expected key: {key}")
        else:
            logger.warning(f"⚠ Missing optional key: {key}")
    
    # Validate topic suggestions if present
    if 'final_topic_suggestions' in outputs:
        topic_suggestions = outputs['final_topic_suggestions']
        assert isinstance(topic_suggestions, dict), "Topic suggestions should be a dict"
        assert 'suggested_topics' in topic_suggestions, "Topic suggestions missing suggested_topics"
        topics = topic_suggestions['suggested_topics']
        assert isinstance(topics, list), "Topics should be a list"
        assert len(topics) == 5, "Should have exactly 5 topic suggestions"
        
        for topic in topics:
            assert 'topic_id' in topic, "Topic missing topic_id"
            assert 'title' in topic, "Topic missing title"
            assert 'angle' in topic, "Topic missing angle"
        
        logger.info(f"✓ Generated {len(topics)} simplified topic suggestions")
    
    # Validate selected topic if present
    if 'selected_topic' in outputs:
        selected_topic = outputs['selected_topic']
        assert isinstance(selected_topic, dict), "Selected topic should be a dict"
        if 'current_topic_suggestions' in selected_topic and 'suggested_topics' in selected_topic['current_topic_suggestions']:
            topics = selected_topic['current_topic_suggestions']['suggested_topics']
            assert isinstance(topics, list), "Selected topics should be a list"
            assert len(topics) == 1, "Should have exactly one selected topic"
            first_topic = topics[0]
            assert 'title' in first_topic, "Selected topic missing title"
            assert 'angle' in first_topic, "Selected topic missing angle"
            assert 'topic_id' in first_topic, "Selected topic missing topic_id"
            logger.info(f"✓ Selected topic: {first_topic['title']}")
    
    # Validate knowledge base research if present
    if 'knowledge_base_research' in outputs:
        kb_research = outputs['knowledge_base_research']
        assert isinstance(kb_research, dict), "Knowledge base research should be a dict"
        assert 'search_queries' in kb_research, "Knowledge base research missing search_queries"
        assert 'content_focus_areas' in kb_research, "Knowledge base research missing content_focus_areas"
        queries = kb_research['search_queries']
        assert isinstance(queries, list), "Search queries should be a list"
        assert len(queries) >= 3, "Should have at least 3 search queries"
        logger.info(f"✓ Knowledge base research generated {len(queries)} search queries")
    
    # Validate content brief if present
    if 'final_content_brief' in outputs:
        content_brief = outputs['final_content_brief']
        assert isinstance(content_brief, dict), "Content brief should be a dict"
        assert 'content_brief' in content_brief, "Content brief missing content_brief field"
        brief = content_brief['content_brief']
        
        # Check required brief fields
        required_brief_fields = [
            'title', 'content_type', 'content_format', 'target_audience', 
            'content_goal', 'key_message', 'content_structure', 'seo_keywords',
            'call_to_action', 'success_metrics', 'estimated_total_word_count',
            'difficulty_level', 'writing_guidelines', 'knowledge_base_sources'
        ]
        
        for field in required_brief_fields:
            assert field in brief, f"Content brief missing required field: {field}"
        
        # Validate content structure
        content_structure = brief['content_structure']
        assert isinstance(content_structure, list), "Content structure should be a list"
        assert len(content_structure) > 0, "Should have at least one content section"
        
        for section in content_structure:
            assert 'section_title' in section, "Content section missing section_title"
            assert 'key_points' in section, "Content section missing key_points"
            assert 'estimated_word_count' in section, "Content section missing estimated_word_count"
        
        logger.info(f"✓ Content brief generated with {len(content_structure)} sections")
        logger.info(f"✓ Content type: {brief['content_type']}")
        logger.info(f"✓ Content format: {brief['content_format']}")
        logger.info(f"✓ Estimated total word count: {brief['estimated_total_word_count']}")
    
    # Check for brief document ID if brief was saved
    if 'brief_document_id' in outputs and outputs['brief_document_id'] is not None:
        brief_id = outputs['brief_document_id']
        if isinstance(brief_id, str) and len(brief_id) > 0:
            logger.info(f"✓ Brief saved with document ID: {brief_id}")
        else:
            logger.info("⚠ Brief document ID present but invalid format")
    
    # Check for extracted document name
    if 'document_name' in outputs:
        doc_name = outputs['document_name']
        assert isinstance(doc_name, str), "Document name should be a string"
        assert len(doc_name) > 0, "Document name should not be empty"
        assert doc_name.startswith('linkedin_brief_'), "Document name should start with 'linkedin_brief_'"
        logger.info(f"✓ Document name extracted: {doc_name}")
    
    logger.info("✓ Content strategy brief generation workflow output validation passed.")
    return True


async def main_test_content_brief_workflow():
    """
    Test for Content Research & Brief Generation Workflow.
    
    This function sets up test data, executes the workflow, and validates the output.
    The workflow takes user input, conducts research, generates topic suggestions,
    and creates a comprehensive content brief with human-in-the-loop approval.
    """
    test_name = "Content Research & Brief Generation Workflow Test"
    print(f"--- Starting {test_name} ---")
    
    # Test parameters
    test_entity_username = "TechSolutions"
    
    # Create test content strategy document data
    content_strategy_data = {
        "content_strategy": {
            "primary_content_pillars": [
                "Thought Leadership in Project Management",
                "AI and Automation Best Practices",
                "Team Productivity and Efficiency",
                "Remote Work Solutions"
            ],
            "target_audience": {
                "primary": "Operations Managers and Project Managers",
                "secondary": "Team Leads and CTOs at growing tech companies",
                "demographics": "50-500 employee companies in the tech sector"
            },
            "brand_voice": {
                "tone": "Expert yet approachable",
                "style": "Data-driven insights with practical examples",
                "personality": "Innovative, reliable, and forward-thinking"
            },
            "content_goals": [
                "Establish thought leadership in AI-powered project management",
                "Generate qualified leads from target audience",
                "Build brand awareness in the project management space",
                "Drive product adoption through educational content"
            ],
            "content_types": [
                "Blog posts", "LinkedIn articles", "Whitepapers", "Case studies"
            ],
            "distribution_channels": [
                "Company blog", "LinkedIn", "Industry publications", "Email newsletter"
            ]
        }
    }
    
    # Create test executive profile document data
    executive_profile_data = {
        "executive_profile": {
            "name": "Alex Johnson",
            "title": "CEO & Founder",
            "company": "TechSolutions Pro",
            "industry_experience": "15 years in project management and SaaS",
            "expertise_areas": [
                "AI-powered project management",
                "Team productivity optimization",
                "Remote work culture",
                "SaaS product development"
            ],
            "thought_leadership_focus": [
                "The future of work and AI integration",
                "Building efficient remote teams",
                "Project management best practices",
                "Technology adoption in growing companies"
            ],
            "writing_style": {
                "tone": "Conversational yet authoritative",
                "approach": "Story-driven with actionable insights",
                "perspective": "Practical experience-based advice"
            },
            "personal_interests": [
                "Technology innovation",
                "Team building",
                "Work-life balance",
                "Continuous learning"
            ]
        }
    }
    
    # Test inputs
    test_inputs = {
        "entity_username": test_entity_username,
        "user_input": "I want to write about how AI is transforming project management for remote teams. I'm particularly interested in discussing the balance between automation and human leadership, and how executives can leverage AI tools without losing the personal connection with their teams. I'd also like to touch on the challenges we've seen with AI adoption in the workplace and practical tips for implementation.",
        "brief_uuid": "draft_brief_uuid"
    }
    
    # Setup test documents
    setup_docs: List[SetupDocInfo] = [
        {
            'namespace': f"linkedin_executive_strategy_{test_entity_username}",
            'docname': LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
            'initial_data': content_strategy_data,
            'is_shared': False,
            'is_versioned': LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
            'initial_version': "default",
            'is_system_entity': False
        },
        {
            'namespace': f"linkedin_executive_profile_namespace_{test_entity_username}",
            'docname': LINKEDIN_USER_PROFILE_DOCNAME,
            'initial_data': executive_profile_data,
            'is_shared': False,
            'is_versioned': LINKEDIN_USER_PROFILE_IS_VERSIONED,
            'initial_version': "default",
            'is_system_entity': False
        }
    ]
    
    # Cleanup configuration
    cleanup_docs: List[CleanupDocInfo] = [
        {
            'namespace': f"linkedin_executive_strategy_{test_entity_username}",
            'docname': LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
            'is_shared': False,
            'is_versioned': LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
            'is_system_entity': False
        },
        {
            'namespace': f"linkedin_executive_profile_namespace_{test_entity_username}",
            'docname': LINKEDIN_USER_PROFILE_DOCNAME,
            'is_shared': False,
            'is_versioned': LINKEDIN_USER_PROFILE_IS_VERSIONED,
            'is_system_entity': False
        }
    ]
    
    # Predefined HITL inputs
    predefined_hitl_inputs = [
        # 1) Topic selection: provide feedback once (triggers one regeneration loop)
        {
            "user_action": "provide_feedback",
            "selected_topic_id": None,
            "regeneration_feedback": "These are promising. Please propose options that emphasize remote team connection impact and an executive decision framework for what to automate vs. where human leadership is essential."
        },
        # 2) Topic selection (after regeneration): accept a specific topic
        {
            "user_action": "complete",
            "selected_topic_id": "topic_01",
            "regeneration_feedback": None
        },
        # 3) Brief approval: provide feedback first (allows one revision loop)
        # {
        #     "user_brief_action": "provide_feedback",
        #     "revision_feedback": "Tighten the hook and add one concrete remote-team scenario. Keep the 80/20 framing, but make success metrics more specific.",
        #     "updated_content_brief": {
        #         "content_brief": {
        #             "title": "The 80/20 Rule of AI in Project Management",
        #             "content_type": "LinkedIn Post",
        #             "content_format": "Thought leadership with practical framework",
        #             "target_audience": "Operations Managers and Project Managers at 50-500 employee tech companies",
        #             "content_goal": "Educate executives on where to apply AI vs. retain human leadership in PM",
        #             "key_message": "Use AI for high-leverage, repetitive PM tasks and preserve human judgment for people, priorities, and context.",
        #             "content_structure": [
        #                 {
        #                     "section_title": "Hook & Context",
        #                     "key_points": [
        #                         "Executives wrestle with what to automate vs. what needs human leadership",
        #                         "A simple 80/20 model clarifies where AI delivers outsized leverage"
        #                     ],
        #                     "estimated_word_count": 60
        #                 },
        #                 {
        #                     "section_title": "80/20 Framework",
        #                     "key_points": [
        #                         "Automate: status reporting, basic risk flags, capacity snapshots, meeting notes",
        #                         "Keep Human: prioritization trade-offs, stakeholder alignment, coaching, escalation calls"
        #                     ],
        #                     "estimated_word_count": 140
        #                 },
        #                 {
        #                     "section_title": "Examples & Tools",
        #                     "key_points": [
        #                         "Real examples of AI assisting remote teams without reducing connection",
        #                         "Tool patterns that augment—not replace—relationships"
        #                     ],
        #                     "estimated_word_count": 120
        #                 },
        #                 {
        #                     "section_title": "Implementation Tips",
        #                     "key_points": [
        #                         "Start with low-risk automations and expand",
        #                         "Define decision guardrails and human-in-the-loop checkpoints"
        #                     ],
        #                     "estimated_word_count": 120
        #                 },
        #                 {
        #                     "section_title": "CTA",
        #                     "key_points": [
        #                         "Invite readers to share their biggest AI adoption challenge",
        #                         "Offer a checklist to assess AI readiness"
        #                     ],
        #                     "estimated_word_count": 60
        #                 }
        #             ],
        #             "seo_keywords": [
        #                 "AI in project management",
        #                 "human-in-the-loop",
        #                 "remote teams",
        #                 "automation best practices"
        #             ],
        #             "call_to_action": "Comment your top AI adoption challenge and get the AI readiness checklist.",
        #             "success_metrics": "Engagement rate, saves, qualified inbound conversations, and 2 exec follow-up calls",
        #             "estimated_total_word_count": 500,
        #             "difficulty_level": "Intermediate",
        #             "writing_guidelines": [
        #                 "Conversational yet authoritative tone",
        #                 "Data-informed with practical examples",
        #                 "Emphasize augmentation over replacement"
        #             ],
        #             "knowledge_base_sources": [
        #                 "Internal implementation notes",
        #                 "Public case studies on AI-assisted PM",
        #                 "Vendor documentation for summarization and risk flagging tools"
        #             ]
        #         }
        #     }
        # },
        # # 4) Brief approval: save as draft (avoid hitting iteration limits)
        # {
        #     "user_brief_action": "draft",
        #     "revision_feedback": None,
        #     "updated_content_brief": {
        #         "content_brief": {
        #             "title": "The 80/20 Rule of AI in Project Management",
        #             "content_type": "LinkedIn Post",
        #             "content_format": "Thought leadership with practical framework",
        #             "target_audience": "Operations Managers and Project Managers at 50-500 employee tech companies",
        #             "content_goal": "Educate executives on where to apply AI vs. retain human leadership in PM",
        #             "key_message": "Use AI for high-leverage, repetitive PM tasks and preserve human judgment for people, priorities, and context.",
        #             "content_structure": [
        #                 {
        #                     "section_title": "Hook & Context",
        #                     "key_points": [
        #                         "Executives wrestle with what to automate vs. what needs human leadership",
        #                         "A simple 80/20 model clarifies where AI delivers outsized leverage"
        #                     ],
        #                     "estimated_word_count": 60
        #                 },
        #                 {
        #                     "section_title": "80/20 Framework",
        #                     "key_points": [
        #                         "Automate: status reporting, basic risk flags, capacity snapshots, meeting notes",
        #                         "Keep Human: prioritization trade-offs, stakeholder alignment, coaching, escalation calls"
        #                     ],
        #                     "estimated_word_count": 140
        #                 },
        #                 {
        #                     "section_title": "Examples & Tools",
        #                     "key_points": [
        #                         "Real examples of AI assisting remote teams without reducing connection",
        #                         "Tool patterns that augment—not replace—relationships"
        #                     ],
        #                     "estimated_word_count": 120
        #                 },
        #                 {
        #                     "section_title": "Implementation Tips",
        #                     "key_points": [
        #                         "Start with low-risk automations and expand",
        #                         "Define decision guardrails and human-in-the-loop checkpoints"
        #                     ],
        #                     "estimated_word_count": 120
        #                 },
        #                 {
        #                     "section_title": "CTA",
        #                     "key_points": [
        #                         "Invite readers to share their biggest AI adoption challenge",
        #                         "Offer a checklist to assess AI readiness"
        #                     ],
        #                     "estimated_word_count": 60
        #                 }
        #             ],
        #             "seo_keywords": [
        #                 "AI in project management",
        #                 "human-in-the-loop",
        #                 "remote teams",
        #                 "automation best practices"
        #             ],
        #             "call_to_action": "Comment your top AI adoption challenge and get the AI readiness checklist.",
        #             "success_metrics": "Engagement rate, saves, and qualified inbound conversations",
        #             "estimated_total_word_count": 500,
        #             "difficulty_level": "Intermediate",
        #             "writing_guidelines": [
        #                 "Conversational yet authoritative tone",
        #                 "Data-informed with practical examples",
        #                 "Emphasize augmentation over replacement"
        #             ],
        #             "knowledge_base_sources": [
        #                 "Internal implementation notes",
        #                 "Public case studies on AI-assisted PM",
        #                 "Vendor documentation for summarization and risk flagging tools"
        #             ]
        #         }
        #     }
        # },
        # # 5) Brief approval: provide feedback again, then proceed to save in next step
        # {
        #     "user_brief_action": "provide_feedback",
        #     "revision_feedback": "Looks good. Please make the CTA more outcome-oriented and add one metric example (e.g., 20% faster status reporting).",
        #     "updated_content_brief": {
        #         "content_brief": {
        #             "title": "The 80/20 Rule of AI in Project Management",
        #             "content_type": "LinkedIn Post",
        #             "content_format": "Thought leadership with practical framework",
        #             "target_audience": "Operations Managers and Project Managers at 50-500 employee tech companies",
        #             "content_goal": "Educate executives on where to apply AI vs. retain human leadership in PM",
        #             "key_message": "Use AI for high-leverage, repetitive PM tasks and preserve human judgment for people, priorities, and context.",
        #             "content_structure": [
        #                 {
        #                     "section_title": "Hook & Context",
        #                     "key_points": [
        #                         "Executives wrestle with what to automate vs. what needs human leadership",
        #                         "A simple 80/20 model clarifies where AI delivers outsized leverage"
        #                     ],
        #                     "estimated_word_count": 60
        #                 },
        #                 {
        #                     "section_title": "80/20 Framework",
        #                     "key_points": [
        #                         "Automate: status reporting, basic risk flags, capacity snapshots, meeting notes",
        #                         "Keep Human: prioritization trade-offs, stakeholder alignment, coaching, escalation calls"
        #                     ],
        #                     "estimated_word_count": 140
        #                 },
        #                 {
        #                     "section_title": "Examples & Tools",
        #                     "key_points": [
        #                         "Real examples of AI assisting remote teams without reducing connection",
        #                         "Tool patterns that augment—not replace—relationships"
        #                     ],
        #                     "estimated_word_count": 120
        #                 },
        #                 {
        #                     "section_title": "Implementation Tips",
        #                     "key_points": [
        #                         "Start with low-risk automations and expand",
        #                         "Define decision guardrails and human-in-the-loop checkpoints"
        #                     ],
        #                     "estimated_word_count": 120
        #                 },
        #                 {
        #                     "section_title": "CTA",
        #                     "key_points": [
        #                         "Invite readers to share their biggest AI adoption challenge",
        #                         "Offer a checklist to assess AI readiness"
        #                     ],
        #                     "estimated_word_count": 60
        #                 }
        #             ],
        #             "seo_keywords": [
        #                 "AI in project management",
        #                 "human-in-the-loop",
        #                 "remote teams",
        #                 "automation best practices"
        #             ],
        #             "call_to_action": "Comment your top AI adoption challenge and get the AI readiness checklist.",
        #             "success_metrics": "Engagement rate, saves, qualified inbound conversations, and 2 exec follow-up calls",
        #             "estimated_total_word_count": 500,
        #             "difficulty_level": "Intermediate",
        #             "writing_guidelines": [
        #                 "Conversational yet authoritative tone",
        #                 "Data-informed with practical examples",
        #                 "Emphasize augmentation over replacement"
        #             ],
        #             "knowledge_base_sources": [
        #                 "Internal implementation notes",
        #                 "Public case studies on AI-assisted PM",
        #                 "Vendor documentation for summarization and risk flagging tools"
        #             ]
        #         }
        #     }
        # },
        # 6) Brief approval: complete (save final)
        {
            "user_brief_action": "cancel_workflow",
            "revision_feedback": None,
            "updated_content_brief": {
                "content_brief": {
                    "title": "The 80/20 Rule of AI in Project Management",
                    "content_type": "LinkedIn Post",
                    "content_format": "Thought leadership with practical framework",
                    "target_audience": "Operations Managers and Project Managers at 50-500 employee tech companies",
                    "content_goal": "Educate executives on where to apply AI vs. retain human leadership in PM",
                    "key_message": "Use AI for high-leverage, repetitive PM tasks and preserve human judgment for people, priorities, and context.",
                    "content_structure": [
                        {
                            "section_title": "Hook & Context",
                            "key_points": [
                                "Executives wrestle with what to automate vs. what needs human leadership",
                                "A simple 80/20 model clarifies where AI delivers outsized leverage"
                            ],
                            "estimated_word_count": 60
                        },
                        {
                            "section_title": "80/20 Framework",
                            "key_points": [
                                "Automate: status reporting, basic risk flags, capacity snapshots, meeting notes",
                                "Keep Human: prioritization trade-offs, stakeholder alignment, coaching, escalation calls"
                            ],
                            "estimated_word_count": 140
                        },
                        {
                            "section_title": "Examples & Tools",
                            "key_points": [
                                "Real examples of AI assisting remote teams without reducing connection",
                                "Tool patterns that augment—not replace—relationships"
                            ],
                            "estimated_word_count": 120
                        },
                        {
                            "section_title": "Implementation Tips",
                            "key_points": [
                                "Start with low-risk automations and expand",
                                "Define decision guardrails and human-in-the-loop checkpoints"
                            ],
                            "estimated_word_count": 120
                        },
                        {
                            "section_title": "CTA",
                            "key_points": [
                                "Invite readers to share their biggest AI adoption challenge",
                                "Offer a checklist to assess AI readiness"
                            ],
                            "estimated_word_count": 60
                        }
                    ],
                    "seo_keywords": [
                        "AI in project management",
                        "human-in-the-loop",
                        "remote teams",
                        "automation best practices"
                    ],
                    "call_to_action": "Comment your top AI adoption challenge and get the AI readiness checklist.",
                    "success_metrics": "Engagement rate, saves, and qualified inbound conversations",
                    "estimated_total_word_count": 500,
                    "difficulty_level": "Intermediate",
                    "writing_guidelines": [
                        "Conversational yet authoritative tone",
                        "Data-informed with practical examples",
                        "Emphasize augmentation over replacement"
                    ],
                    "knowledge_base_sources": [
                        "Internal implementation notes",
                        "Public case studies on AI-assisted PM",
                        "Vendor documentation for summarization and risk flagging tools"
                    ]
                }
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
        validate_output_func=validate_content_brief_workflow_output,
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=1800  # 30 minutes for research and generation
    )
    
    print(f"--- {test_name} Finished ---")
    if final_run_outputs:
        # Show knowledge base research
        if 'knowledge_base_research' in final_run_outputs:
            kb_research = final_run_outputs['knowledge_base_research']
            queries = kb_research.get('search_queries', [])
            print(f"Knowledge Base Research: {len(queries)} search queries generated")
        
        # Show topic suggestions
        if 'final_topic_suggestions' in final_run_outputs:
            topics = final_run_outputs['final_topic_suggestions'].get('suggested_topics', [])
            print(f"Topics Generated: {len(topics)} suggestions")
        
        # Show selected topic
        if 'selected_topic' in final_run_outputs:
            selected = final_run_outputs['selected_topic']
            if 'current_topic_suggestions' in selected and 'suggested_topics' in selected['current_topic_suggestions']:
                topics = selected['current_topic_suggestions']['suggested_topics']
                if topics:
                    print(f"Selected Topic: {topics[0].get('title', 'N/A')}")
            else:
                print(f"Selected Topic: {selected.get('title', 'N/A')}")
        
        # Show brief info
        if 'final_content_brief' in final_run_outputs:
            brief = final_run_outputs['final_content_brief']['content_brief']
            print(f"Brief Generated: {brief.get('estimated_total_word_count', 'N/A')} words")
            print(f"Brief Title: {brief.get('title', 'N/A')}")
        
        # Show saved document
        if 'brief_document_id' in final_run_outputs:
            print(f"Brief Saved: Document ID {final_run_outputs['brief_document_id']}")
        
        # Show extracted document name
        if 'document_name' in final_run_outputs:
            print(f"Document Name: {final_run_outputs['document_name']}")


# Entry point
if __name__ == "__main__":
    print("="*80)
    print("Content Research & Brief Generation Workflow Test")
    print("="*80)
    
    try:
        asyncio.run(main_test_content_brief_workflow())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.exception("Test execution failed")
    
    print("\nTest execution finished.")
    print("Run from project root: PYTHONPATH=. python kiwi_client/workflows/wf_user_input_to_brief.py")

