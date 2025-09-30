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

import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Import LLM inputs and configurations
from kiwi_client.workflows.active.content_studio.linkedin_user_input_to_brief_sandbox.wf_llm_inputs import (
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

    # Topic feedback prompts
    TOPIC_FEEDBACK_SYSTEM_PROMPT,
    TOPIC_FEEDBACK_INITIAL_USER_PROMPT,

    # Revision prompts (new)
    BRIEF_REVISION_SYSTEM_PROMPT,
    BRIEF_REVISION_USER_PROMPT_TEMPLATE,

    # Output schemas
    TOPIC_GENERATION_OUTPUT_SCHEMA,
    TOPIC_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA,
    KNOWLEDGE_BASE_QUERY_OUTPUT_SCHEMA,
    BRIEF_GENERATION_OUTPUT_SCHEMA,
    BRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA,

    # LLM Configuration
    TEMPERATURE,
    MAX_TOKENS,
    MAX_LLM_ITERATIONS,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LLM_MODEL,
    MAX_ITERATIONS,
    MAX_REGENERATION_ATTEMPTS,
    MAX_REVISION_ATTEMPTS,

    # Keep for backward compatibility
    LLM_PROVIDER,
    LLM_MODEL,
    FEEDBACK_LLM_PROVIDER,
    FEEDBACK_ANALYSIS_MODEL,
    FEEDBACK_TEMPERATURE,
    FEEDBACK_MAX_TOKENS,
) 

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
                    },
                    "load_additional_user_files": {
                        "type": "list",
                        "required": False,
                        "default": [],
                        "description": "Optional list of additional user files to load. Each item should have 'namespace', 'docname', and 'is_shared' fields."
                    }
                }
            }
        },
        
        # 2. Transform Additional User Files Format (if provided)
        "transform_additional_files_config": {
            "node_id": "transform_additional_files_config",
            "node_name": "transform_data",
            "node_config": {
                "apply_transform_to_each_item_in_list_at_path": "load_additional_user_files",
                "base_object": {
                    "output_field_name": "additional_user_files"
                },
                "mappings": [
                    {"source_path": "namespace", "destination_path": "filename_config.static_namespace"},
                    {"source_path": "docname", "destination_path": "filename_config.static_docname"},
                    {"source_path": "is_shared", "destination_path": "is_shared"}
                ]
            }
        },

        # 3. Load Additional User Files (conditional)
        "load_additional_user_files_node": {
            "node_id": "load_additional_user_files_node",
            "node_name": "load_customer_data",
            "node_config": {
                "load_configs_input_path": "transformed_data"
            }
        },

        # 4. Load Customer Documents (Content Strategy and Executive Profile)
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
                    },
                    "load_additional_user_files": {
                        "type": "list",
                        "required": False,
                        "default": [],
                        "description": "Optional list of additional user files to load for topic feedback."
                    }
                }
            }
        },

        # 6.1. Transform Topic HITL Additional Files Format
        "transform_topic_hitl_additional_files_config": {
            "node_id": "transform_topic_hitl_additional_files_config",
            "node_name": "transform_data",
            "node_config": {
                "apply_transform_to_each_item_in_list_at_path": "load_additional_user_files",
                "base_object": {
                    "output_field_name": "topic_hitl_additional_user_files"
                },
                "mappings": [
                    {"source_path": "namespace", "destination_path": "filename_config.static_namespace"},
                    {"source_path": "docname", "destination_path": "filename_config.static_docname"},
                    {"source_path": "is_shared", "destination_path": "is_shared"}
                ]
            }
        },

        # 6.2. Load Topic HITL Additional User Files
        "load_topic_hitl_additional_user_files_node": {
            "node_id": "load_topic_hitl_additional_user_files_node",
            "node_name": "load_customer_data",
            "node_config": {
                "load_configs_input_path": "transformed_data"
            }
        },

        # 6.3. Topic Feedback Prompt Constructor
        "construct_topic_feedback_prompt": {
            "node_id": "construct_topic_feedback_prompt",
            "node_name": "prompt_constructor",
            "defer_node": True,  # Wait for all data loads before proceeding
            "node_config": {
                "prompt_templates": {
                    "topic_feedback_user_prompt": {
                        "id": "topic_feedback_user_prompt",
                        "template": TOPIC_FEEDBACK_INITIAL_USER_PROMPT,
                        "variables": {
                            "current_topics": None,
                            "user_feedback": None,
                            "executive_profile": None,
                            "content_strategy": None,
                            "user_input": None,
                            "topic_hitl_additional_user_files": "",
                        },
                        "construct_options": {
                            "current_topics": "current_topic_suggestions",
                            "user_feedback": "regeneration_feedback",
                            "executive_profile": "executive_profile_doc",
                            "content_strategy": "content_strategy_doc",
                            "user_input": "user_input",
                            "topic_hitl_additional_user_files": "topic_hitl_additional_user_files"
                        }
                    },
                    "topic_feedback_system_prompt": {
                        "id": "topic_feedback_system_prompt",
                        "template": TOPIC_FEEDBACK_SYSTEM_PROMPT,
                        "variables": {},
                    }
                }
            }
        },

        # 6.4. Topic Feedback Analysis - Analyze user feedback before topic regeneration
        "analyze_topic_feedback": {
            "node_id": "analyze_topic_feedback",
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
                    "schema_definition": TOPIC_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 6.5. Route Topic Selection
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
                "choices": ["construct_topic_feedback_prompt", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_topic_feedback_prompt",
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
                            "regeneration_feedback": None,
                            "regeneration_instructions": None,
                            "topic_hitl_additional_user_files": ""
                        },
                        "construct_options": {
                            "user_input": "user_input",
                            "executive_profile": "executive_profile_doc",
                            "content_strategy": "content_strategy_doc",
                            "regeneration_feedback": "regeneration_feedback",
                            "regeneration_instructions": "topic_feedback_analysis.revision_instructions",
                            "topic_hitl_additional_user_files": "topic_hitl_additional_user_files"
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
                    },
                    "load_additional_user_files": {
                        "type": "list",
                        "required": False,
                        "default": [],
                        "description": "Optional list of additional user files to load for brief feedback."
                    }
                }
            }
        },

        # 14.1. Transform Brief HITL Additional Files Format
        "transform_brief_hitl_additional_files_config": {
            "node_id": "transform_brief_hitl_additional_files_config",
            "node_name": "transform_data",
            "node_config": {
                "apply_transform_to_each_item_in_list_at_path": "load_additional_user_files",
                "base_object": {
                    "output_field_name": "brief_hitl_additional_user_files"
                },
                "mappings": [
                    {"source_path": "namespace", "destination_path": "filename_config.static_namespace"},
                    {"source_path": "docname", "destination_path": "filename_config.static_docname"},
                    {"source_path": "is_shared", "destination_path": "is_shared"}
                ]
            }
        },

        # 14.2. Load Brief HITL Additional User Files
        "load_brief_hitl_additional_user_files_node": {
            "node_id": "load_brief_hitl_additional_user_files_node",
            "node_name": "load_customer_data",
            "node_config": {
                "load_configs_input_path": "transformed_data"
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
                {"src_field": "brief_uuid", "dst_field": "brief_uuid"},
                {"src_field": "load_additional_user_files", "dst_field": "load_additional_user_files"}
            ]
        },

        # Input -> Transform Additional Files Config
        {
            "src_node_id": "input_node",
            "dst_node_id": "transform_additional_files_config",
            "mappings": [
                {"src_field": "load_additional_user_files", "dst_field": "load_additional_user_files"}
            ]
        },

        # Transform Additional Files -> Load Additional Files
        {
            "src_node_id": "transform_additional_files_config",
            "dst_node_id": "load_additional_user_files_node",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "transformed_data"}
            ]
        },

        # Load Additional Files -> State
        {
            "src_node_id": "load_additional_user_files_node",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "additional_user_files", "dst_field": "additional_user_files"}
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
                {"src_field": "regeneration_feedback", "dst_field": "current_regeneration_feedback"},
                {"src_field": "load_additional_user_files", "dst_field": "topic_hitl_load_additional_user_files"}
            ]
        },

        # Topic HITL -> Transform Topic HITL Additional Files Config
        {
            "src_node_id": "topic_selection_hitl",
            "dst_node_id": "transform_topic_hitl_additional_files_config",
            "mappings": [
                {"src_field": "load_additional_user_files", "dst_field": "load_additional_user_files"}
            ]
        },

        # Transform Topic HITL -> Load Topic HITL Additional Files
        {
            "src_node_id": "transform_topic_hitl_additional_files_config",
            "dst_node_id": "load_topic_hitl_additional_user_files_node",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "transformed_data"}
            ]
        },

        # Load Topic HITL Additional Files -> State
        {
            "src_node_id": "load_topic_hitl_additional_user_files_node",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "topic_hitl_additional_user_files", "dst_field": "topic_hitl_additional_user_files"}
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

        # Topic Feedback Prompt Constructor edges
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_topic_feedback_prompt",
            "mappings": [
                {"src_field": "executive_profile_doc", "dst_field": "executive_profile_doc"},
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"},
                {"src_field": "current_topic_suggestions", "dst_field": "current_topic_suggestions"},
                {"src_field": "regeneration_feedback", "dst_field": "regeneration_feedback"},
                {"src_field": "user_input", "dst_field": "user_input"}
            ]
        },
        {
            "src_node_id": "load_topic_hitl_additional_user_files_node",
            "dst_node_id": "construct_topic_feedback_prompt",
            "data_only_edge": True,
            "mappings": [
                {"src_field": "topic_hitl_additional_user_files", "dst_field": "topic_hitl_additional_user_files"}
            ]
        },

        # Topic Feedback Prompt -> LLM
        {
            "src_node_id": "construct_topic_feedback_prompt",
            "dst_node_id": "analyze_topic_feedback",
            "mappings": [
                {"src_field": "topic_feedback_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "topic_feedback_system_prompt", "dst_field": "system_prompt"}
            ]
        },

        # State -> Topic Feedback Analysis LLM (for message history)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "analyze_topic_feedback",
            "mappings": [
                {"src_field": "topic_feedback_analysis_messages_history", "dst_field": "messages_history"}
            ]
        },

        # Topic Feedback Analysis -> State
        {
            "src_node_id": "analyze_topic_feedback",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "topic_feedback_analysis"},
                {"src_field": "current_messages", "dst_field": "topic_feedback_analysis_messages_history"}
            ]
        },

        # Topic Feedback Analysis -> Check Iteration Limit
        {
            "src_node_id": "analyze_topic_feedback",
            "dst_node_id": "check_topic_iteration_limit",
            "mappings": [],
            "description": "After analyzing feedback, check if we can iterate"
        },

        # Topic Feedback Analysis -> Topic Regeneration Prompt Constructor
        {
            "src_node_id": "analyze_topic_feedback",
            "dst_node_id": "construct_topic_regeneration_prompt",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "topic_feedback_analysis"}
            ]
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
                {"src_field": "tag_results", "dst_field": "if_else_condition_tag_results", "description": "Pass detailed results per condition tag."}
            ]
        },
        {
            "src_node_id": "route_on_topic_limit_check",
            "dst_node_id": "construct_topic_feedback_prompt",
            "description": "Trigger topic feedback analysis if iterations remain"
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

        # Load Topic HITL Additional Files -> Topic Regeneration Prompt (data-only edge)
        {
            "src_node_id": "load_topic_hitl_additional_user_files_node",
            "dst_node_id": "construct_topic_regeneration_prompt",
            "data_only_edge": True,
            "mappings": [
                {"src_field": "topic_hitl_additional_user_files", "dst_field": "topic_hitl_additional_user_files"}
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
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"}
            ]
        },

        # Load Additional Files -> Knowledge Base Query Prompt (data-only edge)
        {
            "src_node_id": "load_additional_user_files_node",
            "dst_node_id": "construct_knowledge_base_query_prompt",
            "data_only_edge": True,
            "mappings": [
                {"src_field": "additional_user_files", "dst_field": "additional_user_files"}
            ]
        },

        # Load Topic HITL Additional Files -> Knowledge Base Query Prompt (data-only edge)
        {
            "src_node_id": "load_topic_hitl_additional_user_files_node",
            "dst_node_id": "construct_knowledge_base_query_prompt",
            "data_only_edge": True,
            "mappings": [
                {"src_field": "topic_hitl_additional_user_files", "dst_field": "topic_hitl_additional_user_files"}
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

        # Load Additional Files -> Brief Generation Prompt (data-only edge)
        {
            "src_node_id": "load_additional_user_files_node",
            "dst_node_id": "construct_brief_generation_prompt",
            "data_only_edge": True,
            "mappings": [
                {"src_field": "additional_user_files", "dst_field": "additional_user_files"}
            ]
        },

        # Load Topic HITL Additional Files -> Brief Generation Prompt (data-only edge)
        {
            "src_node_id": "load_topic_hitl_additional_user_files_node",
            "dst_node_id": "construct_brief_generation_prompt",
            "data_only_edge": True,
            "mappings": [
                {"src_field": "topic_hitl_additional_user_files", "dst_field": "topic_hitl_additional_user_files"}
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
                {"src_field": "user_brief_action", "dst_field": "user_brief_action"},
                {"src_field": "load_additional_user_files", "dst_field": "brief_hitl_load_additional_user_files"}
            ]
        },

        # Brief HITL -> Transform Brief HITL Additional Files Config
        {
            "src_node_id": "brief_approval_hitl",
            "dst_node_id": "transform_brief_hitl_additional_files_config",
            "mappings": [
                {"src_field": "load_additional_user_files", "dst_field": "load_additional_user_files"}
            ]
        },

        # Transform Brief HITL -> Load Brief HITL Additional Files
        {
            "src_node_id": "transform_brief_hitl_additional_files_config",
            "dst_node_id": "load_brief_hitl_additional_user_files_node",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "transformed_data"}
            ]
        },

        # Load Brief HITL Additional Files -> State
        {
            "src_node_id": "load_brief_hitl_additional_user_files_node",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "brief_hitl_additional_user_files", "dst_field": "brief_hitl_additional_user_files"}
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
                {"src_field": "tag_results", "dst_field": "if_else_condition_tag_results", "description": "Pass detailed results per condition tag."}
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

        # Load Brief HITL Additional Files -> Brief Feedback Prompt (data-only edge)
        {
            "src_node_id": "load_brief_hitl_additional_user_files_node",
            "dst_node_id": "construct_brief_feedback_prompt",
            "data_only_edge": True,
            "mappings": [
                {"src_field": "brief_hitl_additional_user_files", "dst_field": "brief_hitl_additional_user_files"}
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

        # Load Brief HITL Additional Files -> Brief Revision Prompt (data-only edge)
        {
            "src_node_id": "load_brief_hitl_additional_user_files_node",
            "dst_node_id": "construct_brief_revision_prompt",
            "data_only_edge": True,
            "mappings": [
                {"src_field": "brief_hitl_additional_user_files", "dst_field": "brief_hitl_additional_user_files"}
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
                "topic_feedback_analysis": "replace",
                "brief_feedback_analysis": "replace",
                "user_action": "replace",
                "user_brief_action": "replace",
                "generation_metadata": "replace",
                "topic_generation_messages_history": "add_messages",
                "topic_feedback_analysis_messages_history": "add_messages",
                "brief_generation_messages_history": "add_messages",
                "brief_feedback_analysis_messages_history": "add_messages",
                "topic_generation_metadata": "replace",
                "additional_user_files": "collect_values",
                "topic_hitl_additional_user_files": "collect_values",
                "brief_hitl_additional_user_files": "collect_values"
            }
        }
    }
}
