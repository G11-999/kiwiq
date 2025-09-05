"""
Content Research & Brief Generation Workflow

This workflow enables comprehensive content research and brief generation with:
- User input collection and company context loading
- Google web search research with real-time data
- Reddit research using Perplexity for user insights
- AI-generated blog topic suggestions
- Human-in-the-loop topic selection
- Comprehensive content brief generation
- Human-in-the-loop brief approval with support for manual edits
- Document storage and output management

Key Features:
- Real web search capabilities for Google and Reddit
- Structured output schemas for each research phase
- HITL approval flows for topic selection and brief approval (with manual editing support)
- Company context integration throughout the process
- Comprehensive content brief generation with SEO, brand guidelines, and structure
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
from kiwi_client.workflows.active.content_studio.llm_inputs.blog_user_input_to_brief import (
    # System prompts
    GOOGLE_RESEARCH_SYSTEM_PROMPT,
    REDDIT_RESEARCH_SYSTEM_PROMPT,
    TOPIC_GENERATION_SYSTEM_PROMPT,
    BRIEF_GENERATION_SYSTEM_PROMPT,
    
    # User prompt templates
    GOOGLE_RESEARCH_USER_PROMPT_TEMPLATE,
    REDDIT_RESEARCH_USER_PROMPT_TEMPLATE,
    TOPIC_GENERATION_USER_PROMPT_TEMPLATE,
    TOPIC_REGENERATION_USER_PROMPT_TEMPLATE,
    BRIEF_GENERATION_USER_PROMPT_TEMPLATE,
    BRIEF_REVISION_USER_PROMPT_TEMPLATE,
    
    
    # Feedback prompts for briefs
    BRIEF_FEEDBACK_SYSTEM_PROMPT,
    BRIEF_FEEDBACK_INITIAL_USER_PROMPT,
    
    # Output schemas
    GOOGLE_RESEARCH_OUTPUT_SCHEMA,
    REDDIT_RESEARCH_OUTPUT_SCHEMA,
    TOPIC_GENERATION_OUTPUT_SCHEMA,
    BRIEF_GENERATION_OUTPUT_SCHEMA,
    
    # Feedback analysis schemas
    BRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA,
)

# LLM Configuration
LLM_PROVIDER = "openai"
LLM_MODEL = "gpt-4.1"
TEMPERATURE = 0.7
MAX_TOKENS = 6000

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
FEEDBACK_LLM_PROVIDER = "openai"
FEEDBACK_ANALYSIS_MODEL = "gpt-4.1"
FEEDBACK_TEMPERATURE = 0.5
FEEDBACK_MAX_TOKENS = 3000 

# Workflow JSON structure
workflow_graph_schema = {
    "nodes": {
        # 1. Input Node - Remove company_context_doc from dynamic output schema
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
                    "user_input": {
                        "type": "str",
                        "required": True,
                        "description": "User's content ideas, brainstorm, or transcript"
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
        
        # 2. Load Company Document - Put company_context_doc configuration directly here
        "load_company_doc": {
            "node_id": "load_company_doc",
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
                        "output_field_name": "content_playbook_doc"
                    }
                ]
            }
        },
        
        # 3. Google Research - Prompt Constructor
        "construct_google_research_prompt": {
            "node_id": "construct_google_research_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "google_research_user_prompt": {
                        "id": "google_research_user_prompt",
                        "template": GOOGLE_RESEARCH_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "company_doc": None,
                            "user_input": None
                        },
                        "construct_options": {
                            "company_doc": "company_doc",
                            "user_input": "user_input"
                        }
                    },
                    "google_research_system_prompt": {
                        "id": "google_research_system_prompt",
                        "template": GOOGLE_RESEARCH_SYSTEM_PROMPT,
                        "variables": {},
                    }
                }
            }
        },
        
        # 4. Google Research - LLM Node
        "google_research_llm": {
            "node_id": "google_research_llm",
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
                    "schema_definition": GOOGLE_RESEARCH_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 5. Reddit Research - Prompt Constructor
        "construct_reddit_research_prompt": {
            "node_id": "construct_reddit_research_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "reddit_research_user_prompt": {
                        "id": "reddit_research_user_prompt",
                        "template": REDDIT_RESEARCH_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "company_doc": None,
                            "google_research_output": None,
                            "user_input": None
                        },
                        "construct_options": {
                            "company_doc": "company_doc",
                            "google_research_output": "google_research_output",
                            "user_input": "user_input"
                        }
                    },
                    "reddit_research_system_prompt": {
                        "id": "reddit_research_system_prompt",
                        "template": REDDIT_RESEARCH_SYSTEM_PROMPT,
                        "variables": {},
                    }
                }
            }
        },
        
        # 6. Reddit Research - LLM Node (Perplexity)
        "reddit_research_llm": {
            "node_id": "reddit_research_llm",
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
                "web_search_options": {
                    "search_domain_filter": [
                        "reddit.com",
                        "quora.com"
                    ]
                },
                "output_schema": {
                    "schema_definition": REDDIT_RESEARCH_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 7. Topic Generation - Prompt Constructor
        "construct_topic_generation_prompt": {
            "node_id": "construct_topic_generation_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "topic_generation_user_prompt": {
                        "id": "topic_generation_user_prompt",
                        "template": TOPIC_GENERATION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "company_doc": None,
                            "content_playbook_doc": None,
                            "google_research_output": None,
                            "reddit_research_output": None,
                            "user_input": None
                        },
                        "construct_options": {
                            "company_doc": "company_doc",
                            "content_playbook_doc": "content_playbook_doc",
                            "google_research_output": "google_research_output",
                            "reddit_research_output": "reddit_research_output",
                            "user_input": "user_input"
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
        
        # 8. Topic Generation - LLM Node
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
        
        # 9. Topic Selection - HITL Node
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
                        "description": "User's decision on topic selection"
                    },
                    "selected_topic_id": {
                        "type": "str",
                        "required": False,
                        "description": "Single topic_id selected by user (required if accept_topic)"
                    },
                    "revision_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "Feedback for topic regeneration (required if regenerate_topics)"
                    }
                }
            }
        },
        
        # 10. Route Topic Selection
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
                        "target_value": "complete"
                    },
                    {
                        "choice_id": "construct_topic_regeneration_prompt",
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
        
        # 13. Topic Feedback - Enhanced Prompt Constructor
        "construct_topic_regeneration_prompt": {
            "node_id": "construct_topic_regeneration_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "topic_regeneration_user_prompt": {
                        "id": "topic_regeneration_user_prompt",
                        "template": TOPIC_REGENERATION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "regeneration_instructions": None
                        },
                        "construct_options": {
                            "regeneration_instructions": "current_regeneration_feedback"
                        }
                    }
                }
            }
        },
        
        # 15. Filter Selected Topic
        "filter_selected_topic": {
            "node_id": "filter_selected_topic",
            "node_name": "filter_data",
            "node_config": {
                "targets": [
                    {
                        "filter_target": "current_topic_suggestions.suggested_blog_topics",  # Target the topics list
                        "condition_groups": [
                            {
                                "conditions": [
                                    {
                                        "field": "current_topic_suggestions.suggested_blog_topics.topic_id",
                                        "operator": "equals",
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
        
        # 16. Brief Generation - Prompt Constructor
        "construct_brief_generation_prompt": {
            "node_id": "construct_brief_generation_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "brief_generation_user_prompt": {
                        "id": "brief_generation_user_prompt",
                        "template": BRIEF_GENERATION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "company_doc": None,
                            "content_playbook_doc": None,
                            "selected_topic": None,
                            "google_research_output": None,
                            "reddit_research_output": None,
                            "user_input": None
                        },
                        "construct_options": {
                            "company_doc": "company_doc",
                            "content_playbook_doc": "content_playbook_doc",
                            "selected_topic": "selected_topics",
                            "google_research_output": "google_research_output",
                            "reddit_research_output": "reddit_research_output",
                            "user_input": "user_input"
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
        
        # 17. Brief Generation - LLM Node
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
                    "is_versioned": BLOG_CONTENT_BRIEF_IS_VERSIONED,
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
                                "input_docname_field_pattern": BLOG_CONTENT_BRIEF_DOCNAME,
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
                            "is_versioned": BLOG_CONTENT_BRIEF_IS_VERSIONED,
                            "operation": "upsert_versioned"
                        }
                    }
                ],
            }
        },
        
        # 18. Brief Approval - HITL Node
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
                        "description": "Feedback for brief revision (required if revise_brief)"
                    },
                    "updated_content_brief": {
                        "type": "dict",
                        "required": True,
                        "description": "Updated content brief"
                    }
                }
            }
        },
        
        # 19. Route Brief Approval
        "route_brief_approval": {
            "node_id": "route_brief_approval",
            "node_name": "router_node",
            "node_config": {
                "choices": ["save_brief", "check_iteration_limit", "delete_draft_on_cancel", "save_as_draft"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "save_brief",
                        "input_path": "user_brief_action",
                        "target_value": "complete"
                    },
                    {
                        "choice_id": "check_iteration_limit",
                        "input_path": "user_brief_action",
                        "target_value": "provide_feedback"
                    },
                    {
                        "choice_id": "delete_draft_on_cancel",
                        "input_path": "user_brief_action",
                        "target_value": "cancel_workflow"
                    },
                    {
                        "choice_id": "save_as_draft",
                        "input_path": "user_brief_action",
                        "target_value": "draft"
                    }
                ],
                "default_choice": "delete_draft_on_cancel"
            }
        },
        # 20. Save Brief as Draft - Store Customer Data
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
                                "input_docname_field_pattern": BLOG_CONTENT_BRIEF_DOCNAME,
                                "input_docname_field": "brief_uuid"
                            }
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
                        ],
                        "versioning": {
                            "is_versioned": True,
                            "operation": "upsert_versioned"
                        }
                    }
                ],
            }
        },
        
        # 21. Check Iteration Limit
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
        
        # 21.5 Delete Draft on Cancel - New node to clean up saved draft
        "delete_draft_on_cancel": {
            "node_id": "delete_draft_on_cancel",
            "node_name": "delete_customer_data",
            "node_config": {
                "search_params": {
                    "input_namespace_field": "company_name",
                    "input_namespace_field_pattern": BLOG_CONTENT_BRIEF_NAMESPACE_TEMPLATE,
                    "input_docname_field": "brief_uuid",
                    "input_docname_field_pattern": BLOG_CONTENT_BRIEF_DOCNAME
                }
            }
        },
        
        # 22. Route Based on Iteration Limit Check
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
                            "company_doc": None,
                            "content_playbook_doc": None,
                            "selected_topic": None,
                            "google_research_output": None,
                            "reddit_research_output": None,
                        },
                        "construct_options": {
                            "content_brief": "current_content_brief",
                            "revision_feedback": "current_revision_feedback",
                            "company_doc": "company_doc",
                            "content_playbook_doc": "content_playbook_doc",
                            "selected_topic": "selected_topics",
                            "google_research_output": "google_research_output",
                            "reddit_research_output": "reddit_research_output",
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
        
        # 20. Brief Feedback Analysis - Analyze user feedback before revision
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

     # 22. Brief Revision - Enhanced Prompt Constructor
        "construct_brief_revision_prompt": {
            "node_id": "construct_brief_revision_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "brief_revision_user_prompt": {
                        "id": "brief_revision_user_prompt",
                        "template": BRIEF_REVISION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "revision_instructions": None
                        },
                        "construct_options": {
                            "revision_instructions": "brief_feedback_analysis.revision_instructions"
                        }
                    }
                }
            }
        },
        
        # 24. Save Brief - Store Customer Data
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
                                "input_docname_field_pattern": BLOG_CONTENT_BRIEF_DOCNAME,
                                "input_docname_field": "brief_uuid"
                            }
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
                        ],
                        "versioning": {
                            "is_versioned": BLOG_CONTENT_BRIEF_IS_VERSIONED,
                            "operation": "upsert_versioned"
                        },
                    }
                ],
            }
        },
        
        # 25. Output Node
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
                {"src_field": "user_input", "dst_field": "user_input"},
                {"src_field": "initial_status", "dst_field": "initial_status"},
                {"src_field": "brief_uuid", "dst_field": "brief_uuid"}            ]
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
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "content_playbook_doc", "dst_field": "content_playbook_doc"}
            ]
        },
        
        # Company Doc -> Google Research Prompt
        {
            "src_node_id": "load_company_doc",
            "dst_node_id": "construct_google_research_prompt",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"}            ]
        },
        
        # State -> Google Research Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_google_research_prompt",
            "mappings": [
                {"src_field": "user_input", "dst_field": "user_input"}
            ]
        },
        
        # Google Research Prompt -> LLM
        {
            "src_node_id": "construct_google_research_prompt",
            "dst_node_id": "google_research_llm",
            "mappings": [
                {"src_field": "google_research_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "google_research_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Google Research LLM -> State
        {
            "src_node_id": "google_research_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "google_research_output"}
            ]
        },
        
        # Google Research LLM -> Reddit Research Prompt (execution trigger)
        {
            "src_node_id": "google_research_llm",
            "dst_node_id": "construct_reddit_research_prompt",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "google_research_output"}
            ]
        },
        
        # State -> Reddit Research Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_reddit_research_prompt",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "user_input", "dst_field": "user_input"}
            ]
        },
        
        # Reddit Research Prompt -> LLM
        {
            "src_node_id": "construct_reddit_research_prompt",
            "dst_node_id": "reddit_research_llm",
            "mappings": [
                {"src_field": "reddit_research_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "reddit_research_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Reddit Research LLM -> State
        {
            "src_node_id": "reddit_research_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "reddit_research_output"}
            ]
        },
        
        # Reddit Research LLM -> Topic Generation Prompt (execution trigger)
        {
            "src_node_id": "reddit_research_llm",
            "dst_node_id": "construct_topic_generation_prompt",
            "mappings": []
        },
        
        # State -> Topic Generation Prompt (provide all required context including reddit data)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_topic_generation_prompt",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "content_playbook_doc", "dst_field": "content_playbook_doc"},
                {"src_field": "google_research_output", "dst_field": "google_research_output"},
                {"src_field": "reddit_research_output", "dst_field": "reddit_research_output"},
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
            "description": "Route to analyze feedback if regeneration requested"
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
                {"src_field": "current_regeneration_feedback", "dst_field": "current_regeneration_feedback"}
            ]
        },
        
        # Topic Regeneration Prompt -> LLM
        {
            "src_node_id": "construct_topic_regeneration_prompt",
            "dst_node_id": "topic_generation_llm",
            "mappings": [
                {"src_field": "topic_regeneration_user_prompt", "dst_field": "user_prompt"},
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
        
        # Filter Selected Topic -> State
        {
            "src_node_id": "filter_selected_topic",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "selected_topics"}
            ]
        },
        
        # Filter Selected Topic -> Brief Generation Prompt
        {
            "src_node_id": "filter_selected_topic",
            "dst_node_id": "construct_brief_generation_prompt",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "selected_topics"}
            ]
        },
        
        # State -> Brief Generation Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_brief_generation_prompt",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "content_playbook_doc", "dst_field": "content_playbook_doc"},
                {"src_field": "google_research_output", "dst_field": "google_research_output"},
                {"src_field": "reddit_research_output", "dst_field": "reddit_research_output"},
                {"src_field": "user_input", "dst_field": "user_input"}
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
        
        # Brief Generation LLM -> Save as Draft After Brief Generation
        {
            "src_node_id": "brief_generation_llm",
            "dst_node_id": "save_as_draft_after_brief_generation",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "current_content_brief"}
            ]
        },
     
        # State -> Save as Draft After Brief Generation
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_as_draft_after_brief_generation",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "initial_status", "dst_field": "initial_status"},
                {"src_field": "brief_uuid", "dst_field": "brief_uuid"}
            ]
        },
        
        # Save as Draft After Brief Generation -> Brief Approval HITL
        { "src_node_id": "save_as_draft_after_brief_generation", "dst_node_id": "brief_approval_hitl", "mappings": [          ] },

        # ---- graph state -> brief approval hitl ----
        { "src_node_id": "$graph_state", "dst_node_id": "brief_approval_hitl", "mappings": [
            { "src_field": "current_content_brief", "dst_field": "content_brief"}
          ]
        },
        
        # Brief Approval HITL -> Route
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
                {"src_field": "user_brief_action", "dst_field": "user_brief_action"}            ]
        },
        
        # --- Brief Approval Router Paths ---
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
            "dst_node_id": "delete_draft_on_cancel",
            "description": "Route to delete draft if workflow cancelled"
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

        # --- State -> Save as Draft ---
        { "src_node_id": "$graph_state", "dst_node_id": "save_as_draft", "mappings": [
            { "src_field": "current_content_brief", "dst_field": "current_content_brief"},
            { "src_field": "user_brief_action", "dst_field": "user_brief_action"},
            { "src_field": "company_name", "dst_field": "company_name"},
            { "src_field": "brief_uuid", "dst_field": "brief_uuid"}
          ]
        },

        # ---- Save as Draft -> brief approval hitl ----
        { "src_node_id": "save_as_draft", "dst_node_id": "brief_approval_hitl", "mappings": [          ]},

        # State -> Delete Draft on Cancel (provide company_name and brief_uuid)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "delete_draft_on_cancel",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "brief_uuid", "dst_field": "brief_uuid"}
            ]
        },
        
        # Delete Draft on Cancel -> Output
        {
            "src_node_id": "delete_draft_on_cancel",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "deleted_count", "dst_field": "cancelled_draft_deleted_count"}
            ]
        },
        
        # State -> Brief Feedback Prompt Constructor
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_brief_feedback_prompt",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "content_playbook_doc", "dst_field": "content_playbook_doc"},
                {"src_field": "current_content_brief", "dst_field": "current_content_brief"},
                {"src_field": "current_revision_feedback", "dst_field": "current_revision_feedback"},
                {"src_field": "selected_topics", "dst_field": "selected_topics"},
                {"src_field": "google_research_output", "dst_field": "google_research_output"},
                {"src_field": "reddit_research_output", "dst_field": "reddit_research_output"},
                {"src_field": "user_input", "dst_field": "user_input"}
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
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "content_playbook_doc", "dst_field": "content_playbook_doc"},
                {"src_field": "selected_topics", "dst_field": "selected_topics"},
                {"src_field": "google_research_output", "dst_field": "google_research_output"},
                {"src_field": "reddit_research_output", "dst_field": "reddit_research_output"},
                {"src_field": "user_input", "dst_field": "user_input"}
            ]
        },
        
        # Brief Revision Prompt -> LLM
        {
            "src_node_id": "construct_brief_revision_prompt",
            "dst_node_id": "brief_generation_llm",
            "mappings": [
                {"src_field": "brief_revision_user_prompt", "dst_field": "user_prompt"}            ]
        },
        
        # State -> Save Brief
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "save_brief",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "current_content_brief", "dst_field": "final_content_brief"},
                {"src_field": "user_brief_action", "dst_field": "user_brief_action"},
                {"src_field": "brief_uuid", "dst_field": "brief_uuid"}            ]
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
            "mappings": []
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
                "generation_metadata": "replace",
                "topic_generation_messages_history": "add_messages",
                "topic_feedback_analysis_messages_history": "add_messages",
                "brief_generation_messages_history": "add_messages",
                "brief_feedback_analysis_messages_history": "add_messages",
                "user_action": "replace",
                "user_brief_action": "replace"
            }
        }
    }
}


# --- Testing Code ---

async def validate_content_brief_workflow_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Validate the content research & brief generation workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run.
        
    Returns:
        True if the outputs are valid, False otherwise.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating content research & brief generation workflow outputs...")
    
    # Check for expected keys
    expected_keys = [
        'google_research_results', 
        'reddit_research_results', 
        'final_topic_suggestions',
        'selected_topic',
        'final_content_brief'
    ]
    
    for key in expected_keys:
        if key in outputs:
            logger.info(f"✓ Found expected key: {key}")
        else:
            logger.warning(f"⚠ Missing optional key: {key}")
    
    # Validate Google research results if present
    if 'google_research_results' in outputs:
        google_results = outputs['google_research_results']
        assert isinstance(google_results, dict), "Google research results should be a dict"
        assert 'research_queries' in google_results, "Google results missing research_queries"
        assert 'source_articles' in google_results, "Google results missing source_articles"
        assert 'people_also_asked' in google_results, "Google results missing people_also_asked"
        logger.info(f"✓ Google research found {len(google_results['source_articles'])} articles")
    
    # Validate Reddit research results if present
    if 'reddit_research_results' in outputs:
        reddit_results = outputs['reddit_research_results']
        assert isinstance(reddit_results, dict), "Reddit research results should be a dict"
        assert 'user_questions_summary' in reddit_results, "Reddit results missing user_questions_summary"
        logger.info(f"✓ Reddit research found {len(reddit_results['user_questions_summary'])} user questions")
    
    # Validate topic suggestions if present
    if 'final_topic_suggestions' in outputs:
        topic_suggestions = outputs['final_topic_suggestions']
        assert isinstance(topic_suggestions, dict), "Topic suggestions should be a dict"
        assert 'suggested_blog_topics' in topic_suggestions, "Topic suggestions missing suggested_blog_topics"
        topics = topic_suggestions['suggested_blog_topics']
        assert isinstance(topics, list), "Topics should be a list"
        assert len(topics) > 0, "Should have at least one topic suggestion"
        logger.info(f"✓ Generated {len(topics)} topic suggestions")
    
    # Validate selected topic if present
    if 'selected_topic' in outputs:
        selected_topic = outputs['selected_topic']
        assert isinstance(selected_topic, dict), "Selected topic should be a dict"
        if 'current_topic_suggestions' in selected_topic and 'suggested_blog_topics' in selected_topic['current_topic_suggestions']:
            topics = selected_topic['current_topic_suggestions']['suggested_blog_topics']
            assert isinstance(topics, list), "Selected topics should be a list"
            assert len(topics) == 1, "Should have exactly one selected topic"
            first_topic = topics[0]
            assert 'title' in first_topic, "Selected topic missing title"
            assert 'angle' in first_topic, "Selected topic missing angle"
            assert 'topic_id' in first_topic, "Selected topic missing topic_id"
            logger.info(f"✓ Selected topic: {first_topic['title']}")
    
    # Validate content brief if present
    if 'final_content_brief' in outputs:
        content_brief = outputs['final_content_brief']
        assert isinstance(content_brief, dict), "Content brief should be a dict"
        assert 'content_brief' in content_brief, "Content brief missing content_brief field"
        brief = content_brief['content_brief']
        
        # Check required brief fields
        required_brief_fields = [
            'title', 'target_audience', 'content_goal', 'key_takeaways',
            'content_structure', 'seo_keywords', 'brand_guidelines',
            'research_sources', 'call_to_action', 'estimated_word_count',
            'difficulty_level', 'writing_instructions'
        ]
        
        for field in required_brief_fields:
            assert field in brief, f"Content brief missing required field: {field}"
        
        logger.info(f"✓ Content brief generated with {len(brief['content_structure'])} sections")
        logger.info(f"✓ Estimated word count: {brief['estimated_word_count']}")
    
    # Check for brief document ID if brief was saved
    if 'brief_document_id' in outputs and outputs['brief_document_id'] is not None:
        brief_id = outputs['brief_document_id']
        if isinstance(brief_id, str) and len(brief_id) > 0:
            logger.info(f"✓ Brief saved with document ID: {brief_id}")
        else:
            logger.info("⚠ Brief document ID present but invalid format")
    
    logger.info("✓ Content research & brief generation workflow output validation passed.")
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
    
    # Test inputs
    test_inputs = {
        "company_name": test_company_name,
        "user_input": "I've been thinking about writing content around how AI is changing project management. I want to explore how small teams can leverage AI tools without losing the human touch in their workflows. Maybe something about the balance between automation and personal connection in remote teams?",
        "brief_uuid": "123e4567-e89b-12d3-a456-426614174000"
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
            'namespace': f"blog_content_strategy_{test_company_name}",
            'docname': BLOG_CONTENT_STRATEGY_DOCNAME,
            'initial_data': {
                "name": test_company_name,
                "content_strategy": "This is a placeholder for the content strategy document. It will be populated with actual strategy details."
            },
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
            'namespace': f"blog_content_strategy_{test_company_name}",
            'docname': BLOG_CONTENT_STRATEGY_DOCNAME,
            'is_shared': False,
            'is_versioned': BLOG_CONTENT_STRATEGY_IS_VERSIONED,
            'is_system_entity': False
        }
    ]
    
    # Predefined HITL inputs - leaving empty to allow for interactive testing
    predefined_hitl_inputs = [
        {
            "user_action": "provide_feedback",
            "selected_topic_id": None,
            "revision_feedback": "Promising directions. Emphasize remote-team collaboration impacts and an exec framework for what to automate vs. where human leadership is essential."
        },
        {
            "user_action": "complete",
            "selected_topic_id": "topic_01",
            "revision_feedback": None
        },
        {
            "user_brief_action": "provide_feedback",
            "revision_feedback": "Please tighten the hook and add one concrete scenario. Keep the framework but make success metrics more specific.",
            "updated_content_brief": {
                "content_brief": {
                    "title": "AI and Human Balance in Project Management: An 80/20 Framework",
                    "target_audience": "Project managers at 50-500 employee tech companies",
                    "content_goal": "Clarify what to automate vs. what requires human leadership",
                    "key_takeaways": [
                        "Automate repetitive PM tasks",
                        "Preserve human judgment for priorities and stakeholder alignment"
                    ],
                    "content_structure": [
                        {"section": "Hook & Context", "word_count": 80, "description": "Execs struggle with where to apply AI; introduce 80/20."},
                        {"section": "80/20 Framework", "word_count": 200, "description": "Automate vs. Keep Human table with examples."},
                        {"section": "Remote Team Scenario", "word_count": 200, "description": "Concrete example with metrics."},
                        {"section": "Implementation Tips", "word_count": 180, "description": "Guardrails and checkpoints."},
                        {"section": "CTA", "word_count": 60, "description": "Invite engagement and next steps."}
                    ],
                    "seo_keywords": {"primary_keyword": "AI in project management", "secondary_keywords": ["human-in-the-loop", "remote teams"]},
                    "call_to_action": "Comment your top AI adoption challenge and get a readiness checklist.",
                    "estimated_word_count": 700,
                    "difficulty_level": "Intermediate",
                    "writing_instructions": ["Conversational yet authoritative", "Data-informed with practical examples"]
                }
            }
        },
        {
            "user_brief_action": "draft",
            "revision_feedback": None,
            "updated_content_brief": {
                "content_brief": {
                    "title": "AI and Human Balance in Project Management: An 80/20 Framework (Draft V2)",
                    "estimated_word_count": 750
                }
            }
        },
        {
            "user_brief_action": "provide_feedback",
            "revision_feedback": "Looks good—make the CTA more outcome-oriented and add a metric example (e.g., 20% faster status reporting).",
            "updated_content_brief": {
                "content_brief": {
                    "title": "AI and Human Balance in Project Management: An 80/20 Framework",
                    "call_to_action": "Download the AI readiness checklist and benchmark your current process.",
                    "writing_instructions": ["Add metric example in Remote Team Scenario"]
                }
            }
        },
        {
            "user_brief_action": "complete",
            "revision_feedback": None,
            "updated_content_brief": {
                "content_brief": {
                    "title": "AI and Human Balance in Project Management: An 80/20 Framework (Final)",
                    "estimated_word_count": 800
                }
            }
        }
    ]
    
    # VALID HUMAN INPUTS FOR MANUAL TESTING:
    # {"user_action": "accept_topic", "selected_topic_id": "topic_01"}
    # {"user_action": "regenerate_topics", "regeneration_feedback": "Please generate more technical topics"}
    # {"user_action": "complete", "updated_content_brief": {content_brief with user edits}}
    # {"user_action": "revise_brief", "revision_feedback": "Please add more practical examples", "updated_content_brief": {manually edited content_brief}}
    
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
        # Show research results
        if 'google_research_results' in final_run_outputs:
            google_results = final_run_outputs['google_research_results']
            print(f"Google Research: {len(google_results.get('source_articles', []))} articles found")
        
        if 'reddit_research_results' in final_run_outputs:
            reddit_results = final_run_outputs['reddit_research_results']
            print(f"Reddit Research: {len(reddit_results.get('user_questions_summary', []))} user questions")
        
        # Show topic suggestions
        if 'final_topic_suggestions' in final_run_outputs:
            topics = final_run_outputs['final_topic_suggestions'].get('suggested_blog_topics', [])
            print(f"Topics Generated: {len(topics)} suggestions")
        
        # Show selected topic
        if 'selected_topic' in final_run_outputs:
            selected = final_run_outputs['selected_topic']
            if 'current_topic_suggestions' in selected and 'suggested_blog_topics' in selected['current_topic_suggestions']:
                topics = selected['current_topic_suggestions']['suggested_blog_topics']
                if topics:
                    print(f"Selected Topic: {topics[0].get('title', 'N/A')}")
            else:
                print(f"Selected Topic: {selected.get('title', 'N/A')}")
        
        # Show brief info
        if 'final_content_brief' in final_run_outputs:
            brief = final_run_outputs['final_content_brief']['content_brief']
            print(f"Brief Generated: {brief.get('estimated_word_count', 'N/A')} words")
            print(f"Brief Title: {brief.get('title', 'N/A')}")
        
        # Show saved document
        if 'brief_document_id' in final_run_outputs:
            print(f"Brief Saved: Document ID {final_run_outputs['brief_document_id']}")


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
    print("Run from project root: PYTHONPATH=. python kiwi_client/workflows_for_blog_teammate/wf_user_input_to_brief.py")
