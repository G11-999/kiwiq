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
    BRIEF_FEEDBACK_ADDITIONAL_USER_PROMPT,
    
    # Output schemas
    TOPIC_GENERATION_OUTPUT_SCHEMA,
    KNOWLEDGE_BASE_QUERY_OUTPUT_SCHEMA,
    BRIEF_GENERATION_OUTPUT_SCHEMA,
    BRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA,
)

# LLM Configuration
LLM_PROVIDER = "anthropic"
LLM_MODEL = "claude-3-7-sonnet-20250219"
TEMPERATURE = 0.7
MAX_TOKENS = 4000

# Perplexity Configuration for Reddit Research
PERPLEXITY_PROVIDER = "perplexity"
PERPLEXITY_MODEL = "sonar-pro"
PERPLEXITY_TEMPERATURE = 0.3
PERPLEXITY_MAX_TOKENS = 3000

# Workflow Limits
MAX_REGENERATION_ATTEMPTS = 3
MAX_REVISION_ATTEMPTS = 3
MAX_ITERATIONS = 10  # Maximum iterations for HITL feedback loops

# Feedback LLM Configuration
FEEDBACK_LLM_PROVIDER = "anthropic"
FEEDBACK_ANALYSIS_MODEL = "claude-3-7-sonnet-20250219"
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
                        "required": True,
                        "default": "draft",
                        "description": "Initial status of the workflow"
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
                        "enum_values": ["accept_topic", "regenerate_topics", "cancel_workflow"],
                        "required": True,
                        "description": "User's decision on topic and content type selection"
                    },
                    "selected_topic_id": {
                        "type": "str",
                        "required": False,
                        "description": "Single topic_id selected by user (required if accept_topic)"
                    },
                    "regeneration_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "Feedback for topic regeneration (required if regenerate_topics)"
                    }
                }
            }
        },
        
        # 6. Route Topic Selection
        "route_topic_selection": {
            "node_id": "route_topic_selection",
            "node_name": "router_node",
            "node_config": {
                "choices": ["filter_selected_topic", "construct_topic_regeneration_prompt", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "filter_selected_topic",
                        "input_path": "user_action",
                        "target_value": "accept_topic"
                    },
                    {
                        "choice_id": "construct_topic_regeneration_prompt",
                        "input_path": "user_action",
                        "target_value": "regenerate_topics"
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
                            "revision_feedback": None
                        },
                        "construct_options": {
                            "user_input": "user_input",
                            "selected_topic": "selected_topic",
                            "executive_profile": "executive_profile_doc",
                            "content_strategy": "content_strategy_doc",
                            "knowledge_base_research": "knowledge_base_queries",
                            "revision_feedback": ""
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
                                "static_docname": LINKEDIN_BRIEF_DOCNAME,
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
                            "is_versioned": LINKEDIN_BRIEF_IS_VERSIONED,
                            "operation": "upsert_versioned"                        }
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
                        "description": "Updated content brief with any manual edits"
                    }
                }
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
                                "input_docname_field_pattern": "{item}",
                                "input_docname_field": "brief_document_paths_processed.0.3.docname"
                            }
                        },
                        "generate_uuid": True,
                        "extra_fields": [
                            {
                                "src_path": "initial_status",
                                "dst_path": "status"
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

        # 15. Route Brief Approval
        "route_brief_approval": {
            "node_id": "route_brief_approval",
            "node_name": "router_node",
            "node_config": {
                "choices": ["check_iteration_limit", "output_node", "brief_approval_hitl", "save_final_brief"],
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
                        "target_value": "revise_brief"
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "user_brief_action",
                        "target_value": "cancel_workflow"
                    },
                    {
                        "choice_id": "brief_approval_hitl",
                        "input_path": "user_brief_action",
                        "target_value": "draft"
                    }
                ],
                "default_choice": "output_node"
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
                        "template": BRIEF_GENERATION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "user_input": None,
                            "selected_topic": None,
                            "executive_profile": None,
                            "content_strategy": None,
                            "knowledge_base_research": None,
                            "revision_instructions": None
                        },
                        "construct_options": {
                            "user_input": "user_input",
                            "selected_topic": "selected_topics",
                            "executive_profile": "executive_profile_doc",
                            "content_strategy": "content_strategy_doc",
                            "knowledge_base_research": "knowledge_base_queries",
                            "revision_instructions": "brief_feedback_analysis.overall_direction"
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
                                "input_docname_field_pattern": "{item}",
                                "input_docname_field": "brief_document_paths_processed.0.3.docname"
                            }
                        },
                        "versioning": {
                            "is_versioned": LINKEDIN_BRIEF_IS_VERSIONED,
                            "operation": "upsert_versioned"
                        },
                        "generate_uuid": True,
                        "extra_fields": [
                            {
                                "src_path": "user_action",
                                "dst_path": "status"
                            }
                        ]
                    }
                ],
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
                {"src_field": "initial_status", "dst_field": "initial_status"}
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
                {"src_field": "current_messages", "dst_field": "topic_generation_messages_history"}
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
            "dst_node_id": "construct_topic_regeneration_prompt",
            "description": "Route to regenerate topics if requested"
        },
        {
            "src_node_id": "route_topic_selection",
            "dst_node_id": "output_node",
            "description": "Route to output if workflow cancelled"
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
                {"src_field": "current_messages", "dst_field": "topic_generation_messages_history"}
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
                {"src_field": "initial_status", "dst_field": "user_action"},
                {"src_field": "entity_username", "dst_field": "entity_username"}            ]
        },

        # Brief Generation LLM -> Brief Approval HITL
        {
            "src_node_id": "save_as_draft_after_brief_generation",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "paths_processed", "dst_field": "brief_document_paths_processed"}
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

        # Brief Approval HITL -> Save as Draft
        {
            "src_node_id": "brief_approval_hitl",
            "dst_node_id": "save_brief",
            "mappings": [
                {"src_field": "updated_content_brief", "dst_field": "current_content_brief"}
            ]
        },

        # Brief Approval HITL -> Brief Revision LLM
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_brief",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "initial_status", "dst_field": "initial_status"},
                {"src_field": "brief_document_paths_processed", "dst_field": "brief_document_paths_processed"}
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
            "dst_node_id": "output_node",
            "description": "Route to output if workflow cancelled"
        },
        {
            "src_node_id": "route_brief_approval",
            "dst_node_id": "brief_approval_hitl",
            "description": "Route to brief approval if draft"
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
                {"src_field": "user_input", "dst_field": "user_input"},
                {"src_field": "selected_topics", "dst_field": "selected_topics"},
                {"src_field": "executive_profile_doc", "dst_field": "executive_profile_doc"},
                {"src_field": "content_strategy_doc", "dst_field": "content_strategy_doc"},
                {"src_field": "knowledge_base_queries", "dst_field": "knowledge_base_queries"}
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
                {"src_field": "user_brief_action", "dst_field": "user_action"},
                {"src_field": "brief_document_paths_processed", "dst_field": "brief_document_paths_processed"}
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
                "generation_metadata": "replace",
                "topic_generation_messages_history": "add_messages",
                "brief_generation_messages_history": "add_messages",
                "brief_feedback_analysis_messages_history": "add_messages"
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
        "user_input": "I want to write about how AI is transforming project management for remote teams. I'm particularly interested in discussing the balance between automation and human leadership, and how executives can leverage AI tools without losing the personal connection with their teams. I'd also like to touch on the challenges we've seen with AI adoption in the workplace and practical tips for implementation."
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
    
    # Predefined HITL inputs - testing check_iteration_limit functionality
    predefined_hitl_inputs = [
        # # First HITL: Topic selection - accept first topic
        # {"user_action": "accept_topic", "selected_topic_id": "topic_01"},
        # # Second HITL: Brief approval - request revision to test iteration tracking
        # {"user_brief_action": "revise_brief", "user_feedback": "Please add more specific examples and data points"},
        # # Third HITL: Brief approval - request another revision
        # {"user_brief_action": "revise_brief", "user_feedback": "Need more detail on implementation strategies"},
        # # Fourth HITL: Brief approval - complete the workflow
        # {"user_brief_action": "complete"}
    ]
    
    # VALID HUMAN INPUTS FOR MANUAL TESTING:
    # Topic Selection HITL:
    # {"user_action": "regenerate_topics", "regeneration_feedback": "Please generate more technical topics"}
    # {"user_action": "cancel_workflow"}
    # 
    # Brief Approval HITL:
    # {"user_action": "complete", "updated_content_brief": {content_brief with user edits}}
    # {"user_action": "revise_brief", "revision_feedback": "Please add more practical examples", "updated_content_brief": {manually edited content_brief}}
    # {"user_action": "draft", "updated_content_brief": {content_brief}}
    # {"user_action": "cancel_workflow", "updated_content_brief": {content_brief}}
    
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

