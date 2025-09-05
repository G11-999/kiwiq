"""
LinkedIn Content Playbook Generation Workflow

This workflow generates a comprehensive LinkedIn content playbook by:
- Loading LinkedIn documents
- Selecting relevant content plays based on LinkedIn profile
- Creating detailed implementation strategies for each play
- Providing actionable recommendations and timelines

Key Features:
- Automatic play selection based on LinkedIn profile
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
    LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
    LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE,
    LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
    LINKEDIN_CONTENT_PLAYBOOK_IS_SHARED,
    LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
    LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,  
)

# Import LLM inputs
from kiwi_client.workflows.active.playbook.llm_inputs.linkedin_content_playbook_generation import (
    # System prompts
    PLAY_SELECTION_SYSTEM_PROMPT,
    PLAYBOOK_GENERATOR_SYSTEM_PROMPT,
    FEEDBACK_MANAGEMENT_SYSTEM_PROMPT_TEMPLATE,
    
    # User prompt templates
    PLAY_SELECTION_USER_PROMPT_TEMPLATE,
    PLAY_SELECTION_REVISION_USER_PROMPT_TEMPLATE,
    FEEDBACK_MANAGEMENT_PROMPT_TEMPLATE,
    PLAYBOOK_GENERATOR_USER_PROMPT_TEMPLATE,
    PLAYBOOK_GENERATOR_REVISION_PROMPT_TEMPLATE,
    ENHANCED_FEEDBACK_PROMPT_TEMPLATE,
    ADDITIONAL_FEEDBACK_USER_PROMPT_TEMPLATE,
    PLAY_ID_CORRECTION_USER_PROMPT_TEMPLATE,
    
    # Output schemas
    PLAY_SELECTION_OUTPUT_SCHEMA,
    FEEDBACK_MANAGEMENT_OUTPUT_SCHEMA,
    PLAYBOOK_GENERATOR_OUTPUT_SCHEMA,
)

# Configuration constants
LLM_PROVIDER = "openai"  # anthropic    openai
LLM_MODEL = "gpt-5"  # o4-mini   gpt-4.1    claude-sonnet-4-20250514
TEMPERATURE = 0.7
MAX_TOKENS = 30000
MAX_TOOL_CALLS = 25  # Maximum total tool calls allowed
MAX_FEEDBACK_ITERATIONS = 30  # Maximum LLM loop iterations # Maximum feedback loops to prevent infinite iterations

MAX_TOKENS_FOR_TOOLS = 10000
LLM_PROVIDER_FOR_TOOLS = "openai"  # anthropic    openai
LLM_MODEL_FOR_TOOLS = "gpt-5"  # o4-mini   gpt-4.1    claude-sonnet-4-20250514

CONFIG = [
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "linkedin_playbook_sys",
        "static_docname": "LinkedIn Play 1: The Transparent Founder Journey"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_transparent_founder_journey",
    "play_name": "The Transparent Founder Journey",
    "description": "Build trust and connection by sharing real, unvarnished founder experiences including metrics, mistakes, decision-making processes, and personal challenges to create authentic relationships that convert to business value.",
    "perfect_for": [
      "First-time founders",
      "Building in public advocates",
      "Community-driven growth strategies",
      "Leaders comfortable with vulnerability"
    ],
    "when_to_use": [
      "When authenticity and relatability drive audience connection",
      "When you want to build parasocial relationships that convert to business",
      "When transparency aligns with company culture",
      "When you have interesting behind-the-scenes insights to share"
    ],
    "success_metrics": [
      "10x follower growth in 6 months",
      "High engagement rates (5%+ average)",
      "Investor/advisor inbound",
      "Talent reaching out proactively"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "linkedin_playbook_sys",
        "static_docname": "LinkedIn Play 2: The Teaching CEO"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_teaching_ceo",
    "play_name": "The Teaching CEO",
    "description": "Establish expertise by teaching complex concepts in accessible ways, positioning yourself as the professor of your niche through educational content that demonstrates mastery and builds authority.",
    "perfect_for": [
      "Technical founders",
      "Domain experts",
      "Complex B2B products",
      "Education-oriented personalities"
    ],
    "when_to_use": [
      "When you have deep expertise worth sharing",
      "When your market needs education on complex topics",
      "When teaching demonstrates mastery better than claiming it",
      "When you can simplify difficult concepts effectively"
    ],
    "success_metrics": [
      "Recognition as subject expert",
      "Speaking invitations",
      "Media quotes/interviews",
      "Consulting inquiries"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "linkedin_playbook_sys",
        "static_docname": "LinkedIn Play 3: The Industry Contrarian"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_industry_contrarian",
    "play_name": "The Industry Contrarian",
    "description": "Cut through noise by thoughtfully challenging industry orthodoxy with well-reasoned contrarian views that generate engagement and position you as an independent thinker and fearless truth-teller.",
    "perfect_for": [
      "Industry veterans",
      "Data-driven leaders",
      "Strong personal brands",
      "Thick-skinned executives"
    ],
    "when_to_use": [
      "When you have well-reasoned views that contradict conventional wisdom",
      "When data or experience supports alternative viewpoints",
      "When industry needs independent thinking",
      "When you can handle debate and pushback"
    ],
    "success_metrics": [
      "High engagement/debate",
      "Thought leader positioning",
      "Conference keynotes",
      "Industry influence"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "linkedin_playbook_sys",
        "static_docname": "LinkedIn Play 4: The Customer Champion"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_customer_champion",
    "play_name": "The Customer Champion",
    "description": "Make customers the heroes of your LinkedIn narrative by consistently highlighting customer success, challenges, and feedback to build trust, social proof, and a community of advocates.",
    "perfect_for": [
      "PLG companies",
      "High NPS products",
      "Customer success focus",
      "Community-driven brands"
    ],
    "when_to_use": [
      "When customer success stories demonstrate value better than features",
      "When you want to show customer obsession, not just claim it",
      "When customers are willing to be highlighted publicly",
      "When social proof drives conversion"
    ],
    "success_metrics": [
      "Customer engagement rates",
      "User-generated content",
      "Customer referrals",
      "Community growth"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "linkedin_playbook_sys",
        "static_docname": "LinkedIn Play 5: The Connector CEO"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_connector_ceo",
    "play_name": "The Connector CEO",
    "description": "Build social capital by spotlighting others and facilitating valuable connections, consistently highlighting achievements, making introductions, and sharing opportunities to become central in valuable networks.",
    "perfect_for": [
      "Natural networkers",
      "Partnership-focused strategies",
      "Community builders",
      "Collaborative leaders"
    ],
    "when_to_use": [
      "When networking and relationships drive business growth",
      "When you can create value by connecting others",
      "When reciprocity and social capital matter",
      "When you want to become a central node in valuable networks"
    ],
    "success_metrics": [
      "Network growth rate",
      "Reciprocal support",
      "Partnership opportunities",
      "Community leadership"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "linkedin_playbook_sys",
        "static_docname": "LinkedIn Play 6: The Ecosystem Builder"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_ecosystem_builder",
    "play_name": "The Ecosystem Builder",
    "description": "Showcase how collaboration and partnerships drive mutual success by highlighting partner wins, collaborative innovations, and ecosystem growth to attract more ecosystem participants.",
    "perfect_for": [
      "Platform companies",
      "Marketplace models",
      "Integration-heavy products",
      "Partnership strategies"
    ],
    "when_to_use": [
      "When platform success requires ecosystem health",
      "When highlighting partner wins drives more partnerships",
      "When collaboration creates competitive moats",
      "When network effects are core to business model"
    ],
    "success_metrics": [
      "Partner applications",
      "Ecosystem growth",
      "Platform GMV",
      "Partner retention"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "linkedin_playbook_sys",
        "static_docname": "LinkedIn Play 7: The Data-Driven Executive"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_data_driven_executive",
    "play_name": "The Data-Driven Executive",
    "description": "Share exclusive data and insights that others can't access, leveraging proprietary data, customer insights, and industry intelligence to create unique thought leadership content.",
    "perfect_for": [
      "Analytics products",
      "Network effects businesses",
      "Research-oriented leaders",
      "Transparent cultures"
    ],
    "when_to_use": [
      "When you have access to unique, proprietary data",
      "When original insights can't be replicated by competitors",
      "When data storytelling is your strength",
      "When market hungers for reliable data and trends"
    ],
    "success_metrics": [
      "Content reshares",
      "Media citations",
      "Data partnership requests",
      "Thought leader status"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "linkedin_playbook_sys",
        "static_docname": "LinkedIn Play 8: The Future-Back Leader"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_future_back_leader",
    "play_name": "The Future-Back Leader",
    "description": "Build authority by painting vivid pictures of where your industry is heading through specific, reasoned predictions and detailed scenarios that help others prepare for change.",
    "perfect_for": [
      "Category creators",
      "Transformation leaders",
      "Technical visionaries",
      "Long-term thinkers"
    ],
    "when_to_use": [
      "When you have deep insights into industry evolution",
      "When vision and prediction align with your brand",
      "When forward-thinking content attracts your audience",
      "When you can make specific, reasoned predictions"
    ],
    "success_metrics": [
      "Visionary recognition",
      "Investor interest",
      "Media interviews",
      "Conference keynotes"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "linkedin_playbook_sys",
        "static_docname": "LinkedIn Play 9: The Vulnerable Leader"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_vulnerable_leader",
    "play_name": "The Vulnerable Leader",
    "description": "Build deep connections by sharing struggles, failures, and personal growth through strategic vulnerability that makes you more relatable and creates emotional bonds with your audience.",
    "perfect_for": [
      "Authentic personalities",
      "Mental health advocates",
      "Culture-first companies",
      "Personal brand builders"
    ],
    "when_to_use": [
      "When strategic vulnerability accelerates trust",
      "When authenticity in leadership is valued by your audience",
      "When personal struggles relate to professional insights",
      "When you're comfortable sharing meaningful challenges"
    ],
    "success_metrics": [
      "Highest engagement rates",
      "Deep DM conversations",
      "Culture fit hires",
      "Authentic brand perception"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "linkedin_playbook_sys",
        "static_docname": "LinkedIn Play 10: The Grateful Leader"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_grateful_leader",
    "play_name": "The Grateful Leader",
    "description": "Build loyalty and positive culture through consistent, specific gratitude by regularly acknowledging others' contributions to create a magnetic leadership brand that attracts talent, partners, and customers.",
    "perfect_for": [
      "Team-first leaders",
      "Positive cultures",
      "Relationship builders",
      "Service-oriented brands"
    ],
    "when_to_use": [
      "When public gratitude creates positive cycles",
      "When making others feel valued is core to your leadership style",
      "When positive culture and relationships drive business success",
      "When you want to build magnetic leadership brand"
    ],
    "success_metrics": [
      "Team retention",
      "Culture scores",
      "Community loyalty",
      "Positive brand association"
    ]
  }
]

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
                    "entity_username": {
                        "type": "str",
                        "required": True,
                        "description": "Entity username for document operations"
                    },
                    "playbook_selection_config": {
                        "type": "list",
                        "required": False,
                        "default": CONFIG,
                        "description": "Configuration for the playbook generation"
                    }
                }
            }
        },
        
        # 2. Load LinkedIn Documents
        "load_linkedin_doc": {
            "node_id": "load_linkedin_doc",
            "node_name": "load_customer_data",
            "node_config": {
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_USER_PROFILE_DOCNAME,
                        },
                        "output_field_name": "linkedin_profile_doc"
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
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
        
        # 3. Extract Playbooks (from CONFIG) - Filter to only play_id and flattened play fields
        "extract_playbooks": {
            "node_id": "extract_playbooks",
            "node_name": "filter_data",
            "node_config": {
                "targets": [
                    {
                        "filter_target": "playbook_selection_config.play_id",
                        "filter_mode": "allow",
                        "condition_groups": [
                            { "conditions": [ { "field": "playbook_selection_config.play_id", "operator": "is_not_empty" } ], "logical_operator": "and" }
                        ],
                        "group_logical_operator": "and"
                    },
                    {
                        "filter_target": "playbook_selection_config.play_name",
                        "filter_mode": "allow",
                        "condition_groups": [
                            { "conditions": [ { "field": "playbook_selection_config.play_name", "operator": "is_not_empty" } ], "logical_operator": "and" }
                        ],
                        "group_logical_operator": "and"
                    },
                    {
                        "filter_target": "playbook_selection_config.description",
                        "filter_mode": "allow",
                        "condition_groups": [
                            { "conditions": [ { "field": "playbook_selection_config.description", "operator": "is_not_empty" } ], "logical_operator": "and" }
                        ],
                        "group_logical_operator": "and"
                    },
                    # {
                    #     "filter_target": "playbook_selection_config.perfect_for",
                    #     "filter_mode": "allow",
                    #     "condition_groups": [
                    #         { "conditions": [ { "field": "playbook_selection_config.perfect_for", "operator": "is_not_empty" } ], "logical_operator": "and" }
                    #     ],
                    #     "group_logical_operator": "and"
                    # },
                    # {
                    #     "filter_target": "playbook_selection_config.when_to_use",
                    #     "filter_mode": "allow",
                    #     "condition_groups": [
                    #         { "conditions": [ { "field": "playbook_selection_config.when_to_use", "operator": "is_not_empty" } ], "logical_operator": "and" }
                    #     ],
                    #     "group_logical_operator": "and"
                    # },
                    # {
                    #     "filter_target": "playbook_selection_config.success_metrics",
                    #     "filter_mode": "allow",
                    #     "condition_groups": [
                    #         { "conditions": [ { "field": "playbook_selection_config.success_metrics", "operator": "is_not_empty" } ], "logical_operator": "and" }
                    #     ],
                    #     "group_logical_operator": "and"
                    # }
                ],
                "non_target_fields_mode": "deny"
            }
        },
        
        # 4. Play Selection - Prompt Constructor
        "construct_play_selection_prompt": {
            "node_id": "construct_play_selection_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "play_selection_user_prompt": {
                        "id": "play_selection_user_prompt",
                        "template": PLAY_SELECTION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "linkedin_info": None,
                            "diagnostic_report_info": None
                        },
                        "construct_options": {
                            "linkedin_info": "linkedin_profile_doc",
                            "diagnostic_report_info": "diagnostic_report_doc"
                        }
                    },
                    "play_selection_system_prompt": {
                        "id": "play_selection_system_prompt",
                        "template": PLAY_SELECTION_SYSTEM_PROMPT,
                        "variables": {
                            "available_playbooks": None
                        },
                        "construct_options": {
                            "available_playbooks": "available_playbooks"
                        }
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
        
        # 4.b Validate Play IDs
        "validate_play_ids": {
            "node_id": "validate_play_ids",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "selected_ids_valid",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "structured_output.selected_plays.play_id",
                                "operator": "equals_any_of",
                                "value_path": "playbook_selection_config.play_id",
                                "apply_to_each_value_in_list_field": True,
                                "list_field_logical_operator": "and"
                            }],
                            "logical_operator": "and"
                        }],
                        "group_logical_operator": "and",
                        "nested_list_logical_operator": "and"
                    }
                ],
                "branch_logic_operator": "and"
            }
        },
        
        # 4.c Route based on validation
        "route_play_id_validation": {
            "node_id": "route_play_id_validation",
            "node_name": "router_node",
            "node_config": {
                "choices": ["filter_playbook_selection_config", "construct_play_id_correction_prompt"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "filter_playbook_selection_config",
                        "input_path": "ids_valid",
                        "target_value": True
                    },
                    {
                        "choice_id": "construct_play_id_correction_prompt",
                        "input_path": "ids_valid",
                        "target_value": False
                    }
                ],
                "default_choice": "construct_play_id_correction_prompt"
            }
        },
        
        # 4.d Construct Play ID Correction Prompt
        "construct_play_id_correction_prompt": {
            "node_id": "construct_play_id_correction_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "play_id_correction_user_prompt": {
                        "id": "play_id_correction_user_prompt",
                        "template": PLAY_ID_CORRECTION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "playbook_selection_config": None
                        },
                        "construct_options": {
                            "playbook_selection_config": "playbook_selection_config"
                        }
                    }
                }
            }
        },

                # 4.d.i Filter Playbook Selection Config (remove load_config)
        "filter_playbook_selection_config": {
            "node_id": "filter_playbook_selection_config",
            "node_name": "filter_data",
            "node_config": {
                "targets": [
                    {
                        "filter_target": "playbook_selection_config.play_id",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    { "field": "playbook_selection_config.play_id", "operator": "is_not_empty" }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and"
                    },
                    {
                        "filter_target": "playbook_selection_config.play_name",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    { "field": "playbook_selection_config.play_name", "operator": "is_not_empty" }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and"
                    },
                    {
                        "filter_target": "playbook_selection_config.description",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    { "field": "playbook_selection_config.description", "operator": "is_not_empty" }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and"
                    }
                ],
                "non_target_fields_mode": "deny"
            }
        },
        
        # 4.e Join Play Metadata
        "join_play_metadata": {
            "node_id": "join_play_metadata",
            "node_name": "data_join_data",
            "node_config": {
                "joins": [
                    {
                        "primary_list_path": "filtered_data.playbook_selection_config",
                        "secondary_list_path": "selected_plays.selected_plays",
                        "primary_join_key": "play_id",
                        "secondary_join_key": "play_id",
                        "output_nesting_field": "selection_reasoning",
                        "join_type": "one_to_one"
                    }
                ]
            }
        },

        "filter_joined_plays_with_reasoning": {
            "node_id": "filter_joined_plays_with_reasoning",
            "node_name": "filter_data",
            "node_config": {
                "targets": [
                    {
                        "filter_target": "mapped_data.filtered_data.playbook_selection_config",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    { "field": "mapped_data.filtered_data.playbook_selection_config.selection_reasoning", "operator": "is_not_empty" }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and"
                    }
                ],
                "non_target_fields_mode": "deny"
            }
        },

        "flatten_play_recommendations": {
            "node_id": "flatten_play_recommendations",
            "node_name": "transform_data",
            "node_config": {
                "merge_conflicting_paths_as_list": False,
                "mappings": [
                    { "source_path": "input_data.mapped_data.filtered_data.playbook_selection_config", "destination_path": "play_recommendations" }
                ]
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
                "choices": ["filter_plays_data", "construct_play_selection_revision_prompt", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "filter_plays_data",
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
                            "user_feedback": None,
                        },
                        "construct_options": {
                            "user_feedback": "user_feedback",
                        }
                    },
                }
            }
        },
        
        # 8. Filter Plays Data
        "filter_plays_data": {
            "node_id": "filter_plays_data",
            "node_name": "filter_data",
            "node_config": {
                "targets": [
                    {
                        "filter_target": "playbook_selection_config",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    {
                                        "field": "playbook_selection_config.play_id",
                                        "operator": "equals_any_of",
                                        "value_path": "approved_plays.play_id"
                                    }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and",
                        "nested_list_logical_operator": "and"
                    }
                ],
                "non_target_fields_mode": "deny"
            }
        },

        # 9. Prepare Load Configs (transform filtered structure to flat list)
        "prepare_load_configs": {
            "node_id": "prepare_load_configs",
            "node_name": "transform_data",
            "node_config": {
                "merge_conflicting_paths_as_list": False,
                "mappings": [
                    { "source_path": "available_playbooks.playbook_selection_config.load_config", "destination_path": "load_configs" }
                ]
            }
        },

        # 10. Load Playbooks
        "load_selected_playbooks": {
            "node_id": "load_selected_playbooks",
            "node_name": "load_customer_data",
            "node_config": {
                "load_configs_input_path": "available_playbooks.load_configs",
                "global_is_shared": True,
                "global_is_system_entity": True,
                "global_schema_options": {"load_schema": False},
            }
            
        },
        
        # 12. Playbook Generator - Prompt Constructor
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
                            "linkedin_profile_doc": None,
                            "diagnostic_report_info": None
                        },
                        "construct_options": {
                            "fetched_information": "fetched_information",
                            "linkedin_profile_doc": "linkedin_profile_doc",
                            "diagnostic_report_info": "diagnostic_report_doc",
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
                    "max_tokens": MAX_TOKENS,
                    "reasoning_effort_class": "high"
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
                "choices": ["store_playbook", "check_revision_iteration", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "store_playbook",
                        "input_path": "user_action",
                        "target_value": "approve_playbook"
                    },
                    {
                        "choice_id": "check_revision_iteration",
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

        "check_revision_iteration": {
            "node_id": "check_revision_iteration",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "is_additional_iteration",
                        "condition_groups": [{
                            "logical_operator": "and",
                            "conditions": [{
                                "field": "metadata.iteration_count",
                                "operator": "greater_than",
                                "value": 1
                            }]
                        }],
                        "group_logical_operator": "and"
                    }
                ],
                "branch_logic_operator": "and"
            }
        },

        "route_revision_iteration": {
            "node_id": "route_revision_iteration",
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_feedback_management_prompt", "construct_additional_feedback_prompt"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_additional_feedback_prompt",
                        "input_path": "if_else_condition_tag_results.is_additional_iteration",
                        "target_value": True
                    },
                    {
                        "choice_id": "construct_feedback_management_prompt",
                        "input_path": "if_else_condition_tag_results.is_additional_iteration",
                        "target_value": False
                    }
                ]
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
                        "template": FEEDBACK_MANAGEMENT_PROMPT_TEMPLATE,
                        "variables": {
                            "revision_feedback": None,
                            "current_playbook": None,
                            "selected_plays": None,
                            "linkedin_info": None,
                            "diagnostic_report_info": None
                        },
                        "construct_options": {
                            "revision_feedback": "revision_feedback",
                            "current_playbook": "current_playbook",
                            "selected_plays": "approved_plays",
                            "linkedin_info": "linkedin_profile_doc",
                            "diagnostic_report_info": "diagnostic_report_doc",
                        }
                    },
                    "feedback_management_system_prompt": {
                        "id": "feedback_management_system_prompt",
                        "template": FEEDBACK_MANAGEMENT_SYSTEM_PROMPT_TEMPLATE,
                        "variables": {
                            "available_plays_list": None
                        },
                        "construct_options": {
                            "available_plays_list": "playbook_selection_config"
                        }
                    }
                }
            }
        },

        "construct_additional_feedback_prompt": {
            "node_id": "construct_additional_feedback_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "additional_feedback_user_prompt": {
                        "id": "additional_feedback_user_prompt",
                        "template": ADDITIONAL_FEEDBACK_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "revision_feedback": None,
                            "current_playbook": None,
                        },
                        "construct_options": {
                            "revision_feedback": "revision_feedback",
                            "current_playbook": "current_playbook",
                        }
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
                        "provider": LLM_PROVIDER_FOR_TOOLS,
                        "model": LLM_MODEL_FOR_TOOLS
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS_FOR_TOOLS,
                    # "reasoning_tokens_budget": 2048,
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
                    "schema_definition": FEEDBACK_MANAGEMENT_OUTPUT_SCHEMA,
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
                "choices": ["feedback_tool_executor", "check_play_ids_to_fetch", "feedback_clarification_hitl", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "feedback_tool_executor",
                        "input_path": "tag_results.has_tool_calls",
                        "target_value": True
                    },
                    {
                        "choice_id": "check_play_ids_to_fetch",
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
                            "linkedin_profile_doc": None,
                            "additional_play_data": ""
                        },
                        "construct_options": {
                            "current_playbook": "current_playbook",
                            "revision_feedback": "revision_feedback",
                            "additional_information": "additional_information",
                            "linkedin_profile_doc": "linkedin_profile_doc",
                            "additional_play_data": "additional_play_data"
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
                                "input_namespace_field": "entity_username",
                                "static_docname": LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
                            }
                        },
                        "versioning": {
                            "is_versioned": LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
                            "operation": "upsert_versioned",
                            "version": "default"
                        }
                    }
                ],
            }
        },

        # 24.d Check Play IDs to Fetch
        "check_play_ids_to_fetch": {
            "node_id": "check_play_ids_to_fetch",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "has_play_ids_to_fetch",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "feedback_management_output.play_ids_to_fetch",
                                "operator": "is_not_empty"
                            }],
                            "logical_operator": "and"
                        }],
                        "group_logical_operator": "and"
                    }
                ],
                "branch_logic_operator": "and"
            }
        },

        # 24.e Route based on play_ids_to_fetch
        "route_play_ids_to_fetch": {
            "node_id": "route_play_ids_to_fetch",
            "node_name": "router_node",
            "node_config": {
                "choices": ["filter_plays_for_update", "construct_playbook_update_prompt"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "filter_plays_for_update",
                        "input_path": "tag_results.has_play_ids_to_fetch",
                        "target_value": True
                    },
                    {
                        "choice_id": "construct_playbook_update_prompt",
                        "input_path": "tag_results.has_play_ids_to_fetch",
                        "target_value": False
                    }
                ],
                "default_choice": "construct_playbook_update_prompt"
            }
        },

        # 24.f Filter Plays for Update
        "filter_plays_for_update": {
            "node_id": "filter_plays_for_update",
            "node_name": "filter_data",
            "node_config": {
                "targets": [
                    {
                        "filter_target": "playbook_selection_config",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    {
                                        "field": "playbook_selection_config.play_id",
                                        "operator": "equals_any_of",
                                        "value_path": "play_ids_to_fetch"
                                    }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and",
                        "nested_list_logical_operator": "and"
                    }
                ],
                "non_target_fields_mode": "deny"
            }
        },

        # 24.g Prepare Load Configs for Update
        "prepare_load_configs_for_update": {
            "node_id": "prepare_load_configs_for_update",
            "node_name": "transform_data",
            "node_config": {
                "merge_conflicting_paths_as_list": False,
                "mappings": [
                    { "source_path": "available_playbooks.playbook_selection_config.load_config", "destination_path": "load_configs" }
                ]
            }
        },

        # 24.h Load Selected Playbooks for Update
        "load_selected_playbooks_for_update": {
            "node_id": "load_selected_playbooks_for_update",
            "node_name": "load_customer_data",
            "node_config": {
                "load_configs_input_path": "available_playbooks.load_configs",
                "global_is_shared": True,
                "global_is_system_entity": True,
                "global_schema_options": {"load_schema": False}
            }
        },

        # 35. Output Node
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {}
        },
    },
    
    "edges": [
        # Input -> State
        {
            "src_node_id": "input_node",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"}
            ]
        },
        
        # Input -> Load LinkedIn Doc
        {
            "src_node_id": "input_node",
            "dst_node_id": "load_linkedin_doc",
            "mappings": [
                {"src_field": "entity_username", "dst_field": "entity_username"}
            ]
        },
        
        # Input -> Extract Playbooks
        {
            "src_node_id": "input_node",
            "dst_node_id": "extract_playbooks",
            "mappings": [
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"}
            ]
        },

        # LinkedIn Doc -> State
        {
            "src_node_id": "load_linkedin_doc",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "linkedin_profile_doc", "dst_field": "linkedin_profile_doc"},
                {"src_field": "diagnostic_report_doc", "dst_field": "diagnostic_report_doc"}
            ]
        },
        
        # Extract Playbooks -> State
        {
            "src_node_id": "extract_playbooks",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "available_playbooks"}
            ]
        },

        {
            "src_node_id": "extract_playbooks",
            "dst_node_id": "construct_play_selection_prompt",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "available_playbooks"}
            ]
        },
        
        # LinkedIn Doc -> Play Selection Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_play_selection_prompt",
            "mappings": [
                {"src_field": "linkedin_profile_doc", "dst_field": "linkedin_profile_doc"},
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
        
        # Play Selection LLM -> Validate Play IDs
        {
            "src_node_id": "play_suggestion_llm",
            "dst_node_id": "validate_play_ids",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "structured_output"}
            ]
        },
        # State -> Validate Play IDs (available plays list)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "validate_play_ids",
            "mappings": [
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"}
            ]
        },
        # Validate -> Route Validation
        {
            "src_node_id": "validate_play_ids",
            "dst_node_id": "route_play_id_validation",
            "mappings": [
                {"src_field": "condition_result", "dst_field": "ids_valid"}
            ]
        },
        # Route Validation -> Join Metadata (valid)
        {
            "src_node_id": "route_play_id_validation",
            "dst_node_id": "filter_playbook_selection_config"
        },
        # Route Validation -> Construct Correction Prompt (invalid)
        {
            "src_node_id": "route_play_id_validation",
            "dst_node_id": "construct_play_id_correction_prompt"
        },
        # State -> Construct Correction Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_play_id_correction_prompt",
            "mappings": [
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"}
            ]
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "filter_playbook_selection_config",
            "mappings": [
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"}
            ]
        },

        {
            "src_node_id": "filter_playbook_selection_config",
            "dst_node_id": "join_play_metadata",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "filtered_data"}
            ]
        },
        # Correction Prompt -> Play Selection LLM (loop)
        {
            "src_node_id": "construct_play_id_correction_prompt",
            "dst_node_id": "play_suggestion_llm",
            "mappings": [
                {"src_field": "play_id_correction_user_prompt", "dst_field": "user_prompt"}
            ]
        },
        # State -> Prepare Join Inputs
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "join_play_metadata",
            "mappings": [
                {"src_field": "selected_plays", "dst_field": "selected_plays"},
            ]
        },

        # Join -> Extract Joined Lists
        {
            "src_node_id": "join_play_metadata",
            "dst_node_id": "filter_joined_plays_with_reasoning",
            "mappings": [
                {"src_field": "mapped_data", "dst_field": "mapped_data"}
            ]
        },
        # Extract Joined Lists -> Shape Recommendations
        {
            "src_node_id": "filter_joined_plays_with_reasoning",
            "dst_node_id": "flatten_play_recommendations",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "input_data"}
            ]
        },

        {
            "src_node_id": "flatten_play_recommendations",
            "dst_node_id": "play_selection_hitl",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "play_recommendations"}
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
        
        # Router -> Filter Plays Data (on approve)
        {
            "src_node_id": "route_play_selection",
            "dst_node_id": "filter_plays_data"
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "filter_plays_data",
            "mappings": [
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"},
                {"src_field": "approved_plays", "dst_field": "approved_plays"}
            ]
        },
        {
            "src_node_id": "filter_plays_data",
            "dst_node_id": "prepare_load_configs",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "available_playbooks"}
            ]
        },

        {
            "src_node_id": "prepare_load_configs",
            "dst_node_id": "load_selected_playbooks",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "available_playbooks"}
            ]
        },

        {
            "src_node_id": "load_selected_playbooks",
            "dst_node_id": "construct_playbook_generator_prompt",
            "mappings": [
                {"src_field": "playbook", "dst_field": "fetched_information"}
            ]
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_playbook_generator_prompt",
            "mappings": [
                {"src_field": "linkedin_profile_doc", "dst_field": "linkedin_profile_doc"},
                {"src_field": "diagnostic_report_doc", "dst_field": "diagnostic_report_doc"}
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
                {"src_field": "current_user_feedback_on_plays", "dst_field": "user_feedback"},
            ]
        },

        
        # Play Selection Revision Prompt -> Revision LLM
        {
            "src_node_id": "construct_play_selection_revision_prompt",
            "dst_node_id": "play_suggestion_llm",
            "mappings": [
                {"src_field": "play_selection_revision_user_prompt", "dst_field": "user_prompt"}            ]
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
                {"src_field": "current_messages", "dst_field": "playbook_generator_message_history"},
                {"src_field": "metadata", "dst_field": "playbook_generator_metadata"}
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
        
        # Route Playbook Review -> Check Revision Iteration (revise)
        {
            "src_node_id": "route_playbook_review",
            "dst_node_id": "check_revision_iteration"
        },
        
        # Route Playbook Review -> Output (cancel)
        {
            "src_node_id": "route_playbook_review",
            "dst_node_id": "output_node"
        },
        
        # State -> Check Revision Iteration (provide generator metadata)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "check_revision_iteration",
            "mappings": [
                {"src_field": "playbook_generator_metadata", "dst_field": "metadata"}
            ]
        },
        
        # Check Revision Iteration -> Route
        {
            "src_node_id": "check_revision_iteration",
            "dst_node_id": "route_revision_iteration",
            "mappings": [
                {"src_field": "tag_results", "dst_field": "if_else_condition_tag_results"},
                {"src_field": "condition_result", "dst_field": "if_else_overall_condition_result"}
            ]
        },
        
        # Route -> Initial Feedback Prompt (first iteration)
        {
            "src_node_id": "route_revision_iteration",
            "dst_node_id": "construct_feedback_management_prompt"
        },
        
        # Route -> Additional Feedback Prompt (additional iterations)
        {
            "src_node_id": "route_revision_iteration",
            "dst_node_id": "construct_additional_feedback_prompt"
        },
        
        # State -> Additional Feedback Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_additional_feedback_prompt",
            "mappings": [
                {"src_field": "revision_feedback", "dst_field": "revision_feedback"},
                {"src_field": "user_edited_generated_playbook", "dst_field": "current_playbook"},
            ]
        },
        
        # Additional Feedback Prompt -> Feedback Management LLM
        {
            "src_node_id": "construct_additional_feedback_prompt",
            "dst_node_id": "feedback_management_llm",
            "mappings": [
                {"src_field": "additional_feedback_user_prompt", "dst_field": "user_prompt"}
            ]
        },
        
        # State -> Feedback Management Prompt Constructor
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_feedback_management_prompt",
            "mappings": [
                {"src_field": "revision_feedback", "dst_field": "revision_feedback"},
                {"src_field": "user_edited_generated_playbook", "dst_field": "current_playbook"},
                {"src_field": "approved_plays", "dst_field": "approved_plays"},
                {"src_field": "linkedin_profile_doc", "dst_field": "linkedin_info"},
                {"src_field": "diagnostic_report_doc", "dst_field": "diagnostic_report_doc"},
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"}
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

        # State -> Feedback Management LLM (provide message history)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "feedback_management_llm",
            "mappings": [
                {"src_field": "feedback_management_messages", "dst_field": "messages_history"}
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
        
        # Route Feedback Management -> Check Play IDs to Fetch
        {
            "src_node_id": "route_feedback_management",
            "dst_node_id": "check_play_ids_to_fetch"
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
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "feedback_tool_calls", "dst_field": "tool_calls"}
            ]
        },
        
        # Feedback Tool Executor -> Feedback Management LLM (continue loop)
        {
            "src_node_id": "feedback_tool_executor",
            "dst_node_id": "feedback_management_llm",
            "mappings": [
                {"src_field": "tool_outputs", "dst_field": "tool_outputs"}
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
                {"src_field": "linkedin_profile_doc", "dst_field": "linkedin_profile_doc"}
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
                {"src_field": "entity_username", "dst_field": "entity_username"}
            ]
        },
        
        # Store Playbook -> Output
        {
            "src_node_id": "store_playbook",
            "dst_node_id": "output_node",
            "mappings": [      
                {"src_field": "paths_processed", "dst_field": "final_paths_processed"}
            ]
        },

        # State -> Check Play IDs to Fetch (provide feedback output)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "check_play_ids_to_fetch",
            "mappings": [
                {"src_field": "feedback_management_output", "dst_field": "feedback_management_output"}
            ]
        },
        
        # Check Play IDs to Fetch -> Route Play IDs to Fetch
        {
            "src_node_id": "check_play_ids_to_fetch",
            "dst_node_id": "route_play_ids_to_fetch",
            "mappings": [
                {"src_field": "tag_results", "dst_field": "tag_results"},
                {"src_field": "branch", "dst_field": "branch_decision"}
            ]
        },
        
        # Route Play IDs to Fetch -> Filter Plays for Update (if has ids)
        {
            "src_node_id": "route_play_ids_to_fetch",
            "dst_node_id": "filter_plays_for_update"
        },
        
        # Route Play IDs to Fetch -> Construct Playbook Update Prompt (if empty)
        {
            "src_node_id": "route_play_ids_to_fetch",
            "dst_node_id": "construct_playbook_update_prompt"
        },
        
        # State -> Filter Plays for Update (available config + ids)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "filter_plays_for_update",
            "mappings": [
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"},
                {"src_field": "feedback_management_output.play_ids_to_fetch", "dst_field": "play_ids_to_fetch"}
            ]
        },
        
        # Filter Plays for Update -> Prepare Load Configs for Update
        {
            "src_node_id": "filter_plays_for_update",
            "dst_node_id": "prepare_load_configs_for_update",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "available_playbooks"}
            ]
        },
        
        # Prepare Load Configs for Update -> Load Selected Playbooks for Update
        {
            "src_node_id": "prepare_load_configs_for_update",
            "dst_node_id": "load_selected_playbooks_for_update",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "available_playbooks"}
            ]
        },
        
        # Load Selected Playbooks for Update -> Construct Playbook Update Prompt
        {
            "src_node_id": "load_selected_playbooks_for_update",
            "dst_node_id": "construct_playbook_update_prompt",
            "mappings": [
                {"src_field": "playbook", "dst_field": "additional_play_data"}
            ]
        }
    ],
    
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    "metadata": {
        "$graph_state": {
            "reducer": {
                "entity_username": "replace",
                "linkedin_profile_doc": "replace",
                "diagnostic_report_doc": "replace",
                "selected_plays": "replace",
                "approved_plays": "replace",
                "current_user_feedback_on_plays": "replace",               
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
                "playbook_generator_clarification_response": "replace",
                "clarification_response": "replace",
                "available_playbooks": "replace",
                "playbook_selection_config": "replace",
                "playbook_generator_metadata": "replace"
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
    test_entity_username = "mahak"
    
    # Create test LinkedIn profile document data
    linkedin_profile_data = {
        "entity_username": test_entity_username,
        "company_name": "TechVenture Solutions",
        "industry": "B2B SaaS",
        "company_size": "50-200 employees",
        "target_audience": "C-suite executives and decision makers in mid-market companies",
        "business_model": "SaaS subscription with professional services",
        "business_goals": [
            "Build founder personal brand and thought leadership",
            "Generate enterprise leads through LinkedIn content",
            "Establish industry authority in digital transformation",
            "Attract top-tier talent and strategic partnerships"
        ],
        "current_content_challenges": [
            "Low LinkedIn engagement rates (under 2%)",
            "Difficulty converting connections to qualified leads",
            "Inconsistent posting schedule and content quality",
            "Limited reach beyond existing network"
        ],
        "competitive_landscape": "Competing with established enterprise players like Salesforce and emerging AI-first startups",
        "unique_value_proposition": "Only platform combining AI automation with human expertise specifically for mid-market digital transformation",
        "founder_profile": {
            "name": "Sarah Chen",
            "title": "CEO & Founder",
            "background": "Former CTO at Fortune 500 company, 15+ years in enterprise technology",
            "expertise": ["Digital transformation", "AI implementation", "Scaling operations", "Enterprise architecture"],
            "personality": "Technical but approachable, data-driven decision maker, authentic thought leader",
            "linkedin_followers": 3500,
            "current_posting_frequency": "2-3 times per week",
            "top_content_topics": ["AI trends", "Leadership lessons", "Company updates"]
        },
        "content_preferences": {
            "preferred_content_types": ["Educational posts", "Behind-the-scenes stories", "Industry insights"],
            "tone_of_voice": "Professional yet conversational, authentic, data-backed",
            "content_pillars": ["Innovation", "Leadership", "Digital Transformation", "Team Building"],
            "posting_frequency_goal": "Daily during weekdays"
        },
        "business_context": {
            "recent_milestones": ["Series A funding", "50% team growth", "Major enterprise client wins"],
            "upcoming_goals": ["Product launch", "Market expansion", "Team scaling"],
            "key_metrics": {
                "monthly_revenue": "$2.5M ARR",
                "customer_count": 150,
                "team_size": 85
            }
        }
    }
    
    # Create comprehensive diagnostic report data for LinkedIn
    diagnostic_report_data = {
        "executive_summary": {
            "current_position": "TechVenture Solutions founder has moderate LinkedIn presence but lacks strategic content approach, missing significant thought leadership opportunities in the competitive B2B SaaS space.",
            "biggest_opportunity": "Building authentic founder-led content strategy leveraging technical expertise and recent business milestones to drive qualified enterprise leads and attract top talent.",
            "critical_risk": "Competitors are rapidly building LinkedIn authority while TechVenture remains underutilized in key industry conversations, potentially losing market positioning.",
            "overall_diagnostic_score": 6.2,
            "key_findings": [
                "Strong technical credibility but limited personal brand visibility",
                "Inconsistent content strategy limiting reach and engagement",
                "Untapped potential for thought leadership in AI/digital transformation"
            ]
        },
        "immediate_opportunities": {
            "top_content_opportunities": [
                {
                    "title": "Founder Journey & Transparency",
                    "content_type": "Personal Stories + Business Lessons",
                    "impact_score": 9.5,
                    "implementation_effort": "Low",
                    "timeline": "2-3 weeks",
                    "reasoning": "Authentic founder stories resonate strongly with target audience and build trust"
                },
                {
                    "title": "Technical Deep Dives & Education",
                    "content_type": "Educational Posts & Tutorials",
                    "impact_score": 8.8,
                    "implementation_effort": "Medium",
                    "timeline": "4-6 weeks",
                    "reasoning": "Technical expertise differentiates from competitors and establishes authority"
                },
                {
                    "title": "Customer Success Spotlights",
                    "content_type": "Case Studies & Success Stories",
                    "impact_score": 9.0,
                    "implementation_effort": "Medium",
                    "timeline": "3-4 weeks",
                    "reasoning": "Social proof drives conversion and showcases real business value"
                },
                {
                    "title": "Industry Contrarian Views",
                    "content_type": "Opinion Leadership",
                    "impact_score": 8.5,
                    "implementation_effort": "High",
                    "timeline": "6-8 weeks",
                    "reasoning": "Well-reasoned contrarian views generate engagement and position as thought leader"
                }
            ],
            "linkedin_quick_wins": [
                {
                    "action": "Optimize founder profile with strategic keywords and compelling headline",
                    "estimated_impact": "3x profile views in 30 days",
                    "timeline": "1 week",
                    "effort": "Low"
                },
                {
                    "action": "Launch weekly thought leadership series on AI in enterprise",
                    "estimated_impact": "5x engagement rate increase",
                    "timeline": "2 weeks",
                    "effort": "Medium"
                },
                {
                    "action": "Create content calendar with consistent posting schedule",
                    "estimated_impact": "Improved reach and follower growth",
                    "timeline": "1 week",
                    "effort": "Low"
                }
            ],
            "executive_visibility_actions": [
                {
                    "platform": "LinkedIn",
                    "action": "Daily engagement with target audience posts and industry conversations",
                    "frequency": "30 minutes daily",
                    "timeline": "Immediate",
                    "impact": "Increased visibility and network growth"
                },
                {
                    "platform": "LinkedIn Newsletter",
                    "action": "Launch bi-weekly industry insights newsletter",
                    "frequency": "Bi-weekly",
                    "timeline": "3 weeks",
                    "impact": "Direct communication channel with audience"
                },
                {
                    "platform": "LinkedIn Events",
                    "action": "Host monthly virtual events on digital transformation",
                    "frequency": "Monthly",
                    "timeline": "6 weeks",
                    "impact": "Position as industry convener and expert"
                }
            ]
        },
        "content_audit_summary": {
            "analysis_period": "Last 90 days",
            "total_posts_last_90_days": 24,
            "avg_engagement_rate": 3.2,
            "follower_growth_rate": 8.5,
            "reach_metrics": {
                "avg_impressions_per_post": 1250,
                "avg_clicks_per_post": 45,
                "avg_comments_per_post": 8
            },
            "top_performing_topics": [
                {"topic": "AI Implementation", "avg_engagement": 4.8},
                {"topic": "Team Building", "avg_engagement": 4.2},
                {"topic": "Product Updates", "avg_engagement": 3.1}
            ],
            "content_gaps": [
                "Thought Leadership on industry trends",
                "Personal insights and founder journey",
                "Customer success stories and case studies",
                "Technical tutorials and educational content"
            ],
            "posting_patterns": {
                "best_posting_times": ["Tuesday 9AM", "Thursday 2PM", "Friday 10AM"],
                "content_type_performance": {
                    "text_posts": 3.8,
                    "image_posts": 2.9,
                    "video_posts": 5.2,
                    "document_posts": 4.1
                }
            }
        },
        "competitive_analysis": {
            "main_competitors_linkedin": [
                {
                    "name": "TechCorp CEO",
                    "followers": 52000,
                    "posting_frequency": "Daily",
                    "engagement_rate": 4.2,
                    "content_focus": "Industry trends and company culture"
                },
                {
                    "name": "InnovateSoft Founder", 
                    "followers": 38000,
                    "posting_frequency": "3-4x per week",
                    "engagement_rate": 3.8,
                    "content_focus": "Technical deep dives and product demos"
                }
            ],
            "competitive_advantages": [
                "Deep technical expertise with business acumen",
                "Authentic founder story with recent milestones",
                "Unique positioning in mid-market digital transformation",
                "Strong customer success stories and case studies"
            ],
            "content_opportunities": [
                "Technical tutorials that competitors avoid",
                "Contrarian viewpoints on industry trends",
                "Behind-the-scenes content from scaling a startup",
                "Data-driven insights from customer implementations"
            ],
            "market_positioning": {
                "current_position": "Under-recognized technical expert",
                "target_position": "Leading voice in mid-market digital transformation",
                "differentiation_strategy": "Combine technical depth with business results"
            }
        },
        "recommendations": {
            "content_strategy": "Focus on authentic founder journey combined with technical expertise",
            "posting_frequency": "5-7 posts per week with mix of content types",
            "engagement_strategy": "Proactive commenting and conversation starting",
            "growth_targets": {
                "followers": "10K in 6 months",
                "engagement_rate": "5%+ average",
                "leads_generated": "50+ qualified leads per quarter"
            }
        }
    }
    
    # Setup test documents
    setup_docs: List[SetupDocInfo] = [
        {
            'namespace': LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username),
            'docname': LINKEDIN_USER_PROFILE_DOCNAME,
            'initial_data': linkedin_profile_data,
            'is_shared': False,
            'is_versioned': True,
            'initial_version': "default",
            'is_system_entity': False
        },
        {
            'namespace': LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE.format(item=test_entity_username),
            'docname': LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
            'initial_data': diagnostic_report_data,
            'is_shared': False,
            'is_versioned': False,
            'initial_version': "default",
            'is_system_entity': False
        }
    ]
    
    # Cleanup configuration
    cleanup_docs: List[CleanupDocInfo] = [
        {
            'namespace': LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username),
            'docname': LINKEDIN_USER_PROFILE_DOCNAME,
            'is_shared': False,
            'is_versioned': True,
            'is_system_entity': False
        },
        {
            'namespace': LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE.format(item=test_entity_username),
            'docname': LINKEDIN_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
            'is_shared': False,
            'is_versioned': False,
            'is_system_entity': False
        },
        {
            'namespace': LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE.format(item=test_entity_username),
            'docname': LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
            'is_shared': False,
            'is_versioned': True,
            'is_system_entity': False
        }
    ]
    
    # Test inputs - just entity username
    test_inputs = {
        "entity_username": test_entity_username
    }
    
    # Predefined HITL inputs - leaving empty for interactive testing
    predefined_hitl_inputs = []
    
#     {
#   "user_action": "approve_plays",
#   "feedback": null,
#   "final_selected_plays": [
#     {
#       "play_id": "the_transparent_founder_journey",
#       "play_name": "The Transparent Founder Journey"
#     },
#     {
#       "play_id": "the_teaching_ceo",
#       "play_name": "The Teaching CEO"
#     },
#     {
#       "play_id": "the_industry_contrarian",
#       "play_name": "The Industry Contrarian"
#     },
#     {
#       "play_id": "the_customer_champion",
#       "play_name": "The Customer Champion"
#     },
#     {
#       "play_id": "the_data_driven_executive",
#       "play_name": "The Data-Driven Executive"
#     }
#   ]
# }

    
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
        cleanup_docs_created_by_setup=True,
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