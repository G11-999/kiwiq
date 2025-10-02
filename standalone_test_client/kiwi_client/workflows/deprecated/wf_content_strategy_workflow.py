import asyncio
import logging
from typing import Dict, Any, Optional, List, Union, ClassVar, Type
import json
from enum import Enum

# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field

# Internal dependencies
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

from kiwi_client.workflows.deprecated.document_models.older_customer_docs import (
    # Content Strategy
    CONTENT_STRATEGY_DOCNAME,
    CONTENT_STRATEGY_NAMESPACE_TEMPLATE,
    CONTENT_STRATEGY_IS_VERSIONED,
    # User Preferences
    USER_PREFERENCES_DOCNAME,
    USER_PREFERENCES_NAMESPACE_TEMPLATE,
    USER_PREFERENCES_IS_VERSIONED,
    # Source Analysis
    USER_SOURCE_ANALYSIS_DOCNAME,
    USER_SOURCE_ANALYSIS_NAMESPACE_TEMPLATE,
    USER_SOURCE_ANALYSIS_IS_VERSIONED,
    # Core Beliefs and Perspectives
    CORE_BELIEFS_PERSPECTIVES_DOCNAME,
    CORE_BELIEFS_PERSPECTIVES_NAMESPACE_TEMPLATE,
    CORE_BELIEFS_PERSPECTIVES_IS_VERSIONED,
    # Content Pillars
    CONTENT_PILLARS_DOCNAME,
    CONTENT_PILLARS_NAMESPACE_TEMPLATE,
    CONTENT_PILLARS_IS_VERSIONED,

    # System Strategy Documents
    
    # Methodology Implementation
    METHODOLOGY_IMPLEMENTATION_DOCNAME,
    METHODOLOGY_IMPLEMENTATION_NAMESPACE_TEMPLATE,
    METHODOLOGY_IMPLEMENTATION_IS_SHARED,
    METHODOLOGY_IMPLEMENTATION_IS_SYSTEM_ENTITY,

    # Build Blocks
    BUILDING_BLOCKS_DOCNAME,
    BUILDING_BLOCKS_NAMESPACE_TEMPLATE,
    BUILDING_BLOCKS_IS_SHARED,
    BUILDING_BLOCKS_IS_SYSTEM_ENTITY,
)

from kiwi_client.workflows.deprecated.llm_inputs.content_strategy import (
    GENERATION_SCHEMA,
    USER_PROMPT_TEMPLATE,
    SYSTEM_PROMPT_TEMPLATE,
)

# --- Workflow Configuration Constants ---

# LLM Configuration
LLM_PROVIDER = "anthropic"  # 
GENERATION_MODEL = "claude-sonnet-4-5-20250929"
LLM_TEMPERATURE = 1
LLM_MAX_TOKENS = 4000


### SAVE DOCUMENT CONFIG ###
SAVE_DOC_FILENAME_CONFIG = {
    "filename_config": {
        "input_namespace_field_pattern": CONTENT_STRATEGY_NAMESPACE_TEMPLATE, 
        "input_namespace_field": "entity_username",
        "static_docname": CONTENT_STRATEGY_DOCNAME,
    }
}
SAVE_DOC_GLOBAL_VERSIONING = {
    "is_versioned": CONTENT_STRATEGY_IS_VERSIONED,
    "operation": "upsert_versioned", # Must not exist yet
    # "version": "generated_draft" # Name the initial version
}
########################


USER_PROMPT_TEMPLATE_VARIABLES = {
    "user_preferences": None,
    "methodology_implementation": None,
    # "entity_username": None,
    "core_beliefs_perspectives": None,
    "content_pillars": None,
    "user_source_analysis": None,
    "building_blocks": None
}

USER_PROMPT_TEMPLATE_CONSTRUCT_OPTIONS = {
    "methodology_implementation": "methodology_implementation",
    "user_preferences": "user_preferences",
    # "entity_username": "entity_username",
    "core_beliefs_perspectives": "core_beliefs_perspectives",
    "content_pillars": "content_pillars",
    "user_source_analysis": "user_source_analysis",
    "building_blocks": "building_blocks"
}
##############################

SYSTEM_PROMPT_TEMPLATE_VARIABLES = {
    "schema": GENERATION_SCHEMA
}

SYSTEM_PROMPT_TEMPLATE_CONSTRUCT_OPTIONS = {}
##############################

### EDGES CONFIG ###
field_mappings_from_state_to_prompt_constructor = [
    { "src_field": "user_preferences", "dst_field": "user_preferences"},
    { "src_field": "methodology_implementation", "dst_field": "methodology_implementation" },
    # { "src_field": "entity_username", "dst_field": "entity_username" },
    { "src_field": "core_beliefs_perspectives", "dst_field": "core_beliefs_perspectives"},
    { "src_field": "content_pillars", "dst_field": "content_pillars"},
    { "src_field": "user_source_analysis", "dst_field": "user_source_analysis"},
    { "src_field": "building_blocks", "dst_field": "building_blocks"},
]

field_mappings_from_input_to_state = [
    { "src_field": "entity_username", "dst_field": "entity_username" },
]

field_mappings_from_input_to_load_all_context_docs = [
    { "src_field": "entity_username", "dst_field": "entity_username" },
]

field_mappings_from_load_all_context_docs_to_state = [
    { "src_field": "user_preferences", "dst_field": "user_preferences"},
    { "src_field": "methodology_implementation", "dst_field": "methodology_implementation"},
    { "src_field": "core_beliefs_perspectives", "dst_field": "core_beliefs_perspectives"},
    { "src_field": "content_pillars", "dst_field": "content_pillars"},
    { "src_field": "user_source_analysis", "dst_field": "user_source_analysis"},
    { "src_field": "building_blocks", "dst_field": "building_blocks"},
]

field_mappings_from_state_to_store_customer_data = [
    { "src_field": "entity_username", "dst_field": "entity_username"}
]

#############

### INPUTS ###

INPUT_FIELDS = {
    "entity_username": { "type": "str", "required": True, "description": "Name of the entity to generate strategy for."},
}

##############


workflow_graph_schema = {
  "nodes": {
        # --- 1. Input Node ---
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                    "fields": INPUT_FIELDS
            }
        },

        # --- 2. Load Customer Context Documents and Scraped Posts (Single Node) ---
        "load_all_context_docs": {
            "node_id": "load_all_context_docs",
            "node_name": "load_customer_data",
            "node_config": {
                "load_paths": [
                    {
                        "filename_config": {
                             "input_namespace_field_pattern": USER_PREFERENCES_NAMESPACE_TEMPLATE, 
                              "input_namespace_field": "entity_username",
                              "static_docname": USER_PREFERENCES_DOCNAME,
                        },
                        "output_field_name": "user_preferences",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": USER_SOURCE_ANALYSIS_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": USER_SOURCE_ANALYSIS_DOCNAME,
                        },
                        "output_field_name": "user_source_analysis",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": CORE_BELIEFS_PERSPECTIVES_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": CORE_BELIEFS_PERSPECTIVES_DOCNAME,
                        },
                        "output_field_name": "core_beliefs_perspectives",
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": CONTENT_PILLARS_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": CONTENT_PILLARS_DOCNAME,
                        },
                        "output_field_name": "content_pillars",
                    },
                    {
                        "filename_config": {
                            "static_namespace": METHODOLOGY_IMPLEMENTATION_NAMESPACE_TEMPLATE,
                            "static_docname": METHODOLOGY_IMPLEMENTATION_DOCNAME,
                        },
                        "output_field_name": "methodology_implementation",
                        "is_shared": METHODOLOGY_IMPLEMENTATION_IS_SHARED,
                        "is_system_entity": METHODOLOGY_IMPLEMENTATION_IS_SYSTEM_ENTITY
                    },
                    {
                        "filename_config": {
                            "static_namespace": BUILDING_BLOCKS_NAMESPACE_TEMPLATE,
                            "static_docname": BUILDING_BLOCKS_DOCNAME,
                        },
                        "output_field_name": "building_blocks",
                        "is_shared": BUILDING_BLOCKS_IS_SHARED,
                        "is_system_entity": BUILDING_BLOCKS_IS_SYSTEM_ENTITY
                    }
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False}
            },
        },

        # --- 9. Construct Brief Prompt (Inside Map Branch) ---
        "construct_prompt": {
            "node_id": "construct_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,  # Wait for all data loads before proceeding
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": USER_PROMPT_TEMPLATE,
                        "variables": USER_PROMPT_TEMPLATE_VARIABLES,
                        "construct_options": USER_PROMPT_TEMPLATE_CONSTRUCT_OPTIONS
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": SYSTEM_PROMPT_TEMPLATE,
                        "variables": SYSTEM_PROMPT_TEMPLATE_VARIABLES,
                        "construct_options": SYSTEM_PROMPT_TEMPLATE_CONSTRUCT_OPTIONS
                    }
                }
            }
        },

        # --- 10. Generate Brief (LLM - Inside Map Branch) ---
        "generate_content": {
            "node_id": "generate_content",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": GENERATION_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": GENERATION_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                },
            }
        },

        # --- 5. Store Concepts ---
        "store_customer_data": {
            "node_id": "store_customer_data",
            "node_name": "store_customer_data",
            "node_config": {
                    "global_versioning": SAVE_DOC_GLOBAL_VERSIONING,
                "store_configs": [
                {
                    "input_field_path": "structured_output", # Field name in node input containing the value to save
                    "target_path": SAVE_DOC_FILENAME_CONFIG
                }
                ]
            }
            },


        # --- 12. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {},
            # "dynamic_input_schema": { # Define expected final inputs
            #     "fields": {
            #         "final_briefs_list": { "type": "list", "required": True, "description": "The complete list of generated content briefs." },
            #         "brief_paths_processed": { "type": "list", "required": False, "description": "Confirmation/path from the storage operation." }
            #     }
            # }
            # Reads: updated_brief (mapped to final_briefs_list), paths_processed (mapped to save_confirmation)
        },

    },

    # --- Edges Defining Data Flow ---
    "edges": [
        # --- Initial Setup ---
        # Input -> State: Store initial inputs globally
        { "src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": field_mappings_from_input_to_state
        },
        
        # Input -> Load operations
        { "src_node_id": "input_node", "dst_node_id": "load_all_context_docs", "mappings": field_mappings_from_input_to_load_all_context_docs, "description": "Trigger context docs loading."
        },


        # --- State Updates from Loaders ---
        { "src_node_id": "load_all_context_docs", "dst_node_id": "$graph_state", "mappings": field_mappings_from_load_all_context_docs_to_state
        },

        # --- Trigger Initial Concept Generation ---
        { "src_node_id": "load_all_context_docs", "dst_node_id": "construct_prompt" },

        # --- Mapping State to Initial Concepts Prompt ---
        { "src_node_id": "$graph_state", "dst_node_id": "construct_prompt", "mappings": field_mappings_from_state_to_prompt_constructor
        },

        # --- Construct Prompt → Generate Concepts ---
        { "src_node_id": "construct_prompt", "dst_node_id": "generate_content", "mappings": [
            { "src_field": "user_prompt", "dst_field": "user_prompt"},
            { "src_field": "system_prompt", "dst_field": "system_prompt"}
          ], "description": "Send prompts to LLM for concept generation."
        },

        # --- State -> Generate Concepts ---
        { "src_node_id": "$graph_state", "dst_node_id": "generate_content", "mappings": [
            { "src_field": "messages_history", "dst_field": "messages_history"}
          ]
        },

        # # --- Generate Concepts -> Store & State ---
        # { "src_node_id": "generate_content", "dst_node_id": "$graph_state", "mappings": [
        #     { "src_field": "structured_output", "dst_field": "current_generated_concepts"},
        #     { "src_field": "current_messages", "dst_field": "messages_history"}
        #   ]
        # },

        { "src_node_id": "generate_content", "dst_node_id": "store_customer_data", "mappings": [
            { "src_field": "structured_output", "dst_field": "structured_output"},
          ]
        },

        { "src_node_id": "generate_content", "dst_node_id": "$graph_state", "mappings": [
            { "src_field": "structured_output", "dst_field": "generated_output"},
          ]
        },

        # --- State -> Store Concepts ---
        { "src_node_id": "$graph_state", "dst_node_id": "store_customer_data", "mappings": field_mappings_from_state_to_store_customer_data
        },

        # --- Store Concepts -> User Choice ---
        { "src_node_id": "store_customer_data", "dst_node_id": "output_node", "mappings": [
            { "src_field": "paths_processed", "dst_field": "paths_processed"}
          ]
        },

        # --- State -> User Choice ---
        { "src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
            { "src_field": "generated_output", "dst_field": "generated_output"}
          ]
        },
    ],

    # --- Define Start and End ---
    "input_node_id": "input_node",
    "output_node_id": "output_node",

    # --- State Reducers ---
    "metadata": {
        "$graph_state": {
            "reducer": {
                # NOTE: If you set collect_values reducer here, it distorts / nests the concepts structure and fails the FILTER NODE!
                # "current_generated_concepts": "collect_values",
                # "messages_history": "add_messages"
            }
        }
    }
}

# --- Test Execution Logic ---
async def main_test_idea_to_brief_workflow():
    """
    Test for Content Strategy Workflow.
    """
    test_name = "Content Strategy Workflow Test"
    print(f"--- Starting {test_name} --- ")

    # Example Inputs

    INPUT_DOCS_TO_BE_LOADED_IN_WORKFLOW = [
        {
            "filename_config": {
                 "input_namespace_field_pattern": USER_PREFERENCES_NAMESPACE_TEMPLATE, 
                  "input_namespace_field": "entity_username",
                  "static_docname": USER_PREFERENCES_DOCNAME,
            },
            "output_field_name": "user_preferences",  # Field for user preferences
        },
        # Source Analysis
        {
            "filename_config": {
                "input_namespace_field_pattern": USER_SOURCE_ANALYSIS_NAMESPACE_TEMPLATE,
                "input_namespace_field": "entity_username",
                "static_docname": USER_SOURCE_ANALYSIS_DOCNAME,
            },
            "output_field_name": "user_source_analysis",  # Field for source analysis
        },
        # Core Beliefs and Perspectives
        {
            "filename_config": {
                "input_namespace_field_pattern": CORE_BELIEFS_PERSPECTIVES_NAMESPACE_TEMPLATE,
                "input_namespace_field": "entity_username",
                "static_docname": CORE_BELIEFS_PERSPECTIVES_DOCNAME,
            },
            "output_field_name": "core_beliefs_perspectives",  # Field for core beliefs
        },
        # Content Pillars
        {
            "filename_config": {
                "input_namespace_field_pattern": CONTENT_PILLARS_NAMESPACE_TEMPLATE,
                "input_namespace_field": "entity_username",
                "static_docname": CONTENT_PILLARS_DOCNAME,
            },
            "output_field_name": "content_pillars",  # Field for content pillars
        },
        # Methodology Implementation
        {
            "filename_config": {
                "static_namespace": METHODOLOGY_IMPLEMENTATION_NAMESPACE_TEMPLATE,
                "static_docname": METHODOLOGY_IMPLEMENTATION_DOCNAME,
            },
            "output_field_name": "methodology_implementation",  # Field for methodology implementation
            "is_shared": METHODOLOGY_IMPLEMENTATION_IS_SHARED,
            "is_system_entity": METHODOLOGY_IMPLEMENTATION_IS_SYSTEM_ENTITY
        },
        # Building Blocks
        {
            "filename_config": {
                "static_namespace": BUILDING_BLOCKS_NAMESPACE_TEMPLATE,
                "static_docname": BUILDING_BLOCKS_DOCNAME,
            },
            "output_field_name": "building_blocks",  # Field for building blocks
            "is_shared": BUILDING_BLOCKS_IS_SHARED,
            "is_system_entity": BUILDING_BLOCKS_IS_SYSTEM_ENTITY
        }
    ]

    entity_username = "test_entity"
    
    test_inputs = {
        "entity_username": entity_username
    }

    # Define setup documents
    setup_docs: List[SetupDocInfo] = [
        # User Preferences
        {
            'namespace': USER_PREFERENCES_NAMESPACE_TEMPLATE.format(item=entity_username), 
            'docname': USER_PREFERENCES_DOCNAME,
            'initial_data': {
                "posts_per_week": 2,
                "preferred_posting_days": ["Monday", "Thursday"],
                "preferred_topics": ["Leadership", "Marketing Trends"],
                "content_tone": "Professional"
            }, 
            'is_versioned': USER_PREFERENCES_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': "default",
            'is_system_entity': False
        },
        # Source Analysis
        {
            'namespace': USER_SOURCE_ANALYSIS_NAMESPACE_TEMPLATE.format(item=entity_username),
            'docname': USER_SOURCE_ANALYSIS_DOCNAME,
            'initial_data': {
                "primary_sources": ["Industry reports", "Competitor analysis"],
                "content_gaps": ["Technical deep dives", "Case studies"],
                "audience_interests": ["Innovation", "Best practices", "Industry trends"],
                "engagement_patterns": {
                    "high_engagement": ["How-to content", "Industry insights"],
                    "low_engagement": ["Company news", "Generic updates"]
                }
            },
            'is_versioned': USER_SOURCE_ANALYSIS_IS_VERSIONED,
            'is_shared': False,
            'initial_version': "default",
            'is_system_entity': False
        },
        # Core Beliefs and Perspectives
        {
            'namespace': CORE_BELIEFS_PERSPECTIVES_NAMESPACE_TEMPLATE.format(item=entity_username),
            'docname': CORE_BELIEFS_PERSPECTIVES_DOCNAME,
            'initial_data': {
                "core_beliefs": [
                    "Marketing should drive measurable business outcomes",
                    "Authenticity creates stronger customer relationships",
                    "Data-driven decisions lead to better marketing performance"
                ],
                "key_perspectives": [
                    "Digital transformation is essential for modern marketing",
                    "Content should educate and provide value before selling",
                    "Brand consistency builds trust across all touchpoints"
                ],
                "unique_viewpoints": [
                    "Marketing ROI can be precisely measured with the right attribution models",
                    "Community building is more valuable than traditional advertising"
                ]
            },
            'is_versioned': CORE_BELIEFS_PERSPECTIVES_IS_VERSIONED,
            'is_shared': False,
            'initial_version': "default",
            'is_system_entity': False
        },
        # Content Pillars
        {
            'namespace': CONTENT_PILLARS_NAMESPACE_TEMPLATE.format(item=entity_username),
            'docname': CONTENT_PILLARS_DOCNAME,
            'initial_data': {
                "pillars": [
                    {
                        "name": "Digital Marketing Strategies",
                        "topics": ["SEO best practices", "Social media marketing", "Email automation"],
                        "audience_pain_points": ["Low conversion rates", "Poor engagement", "Unclear ROI"]
                    },
                    {
                        "name": "Brand Development",
                        "topics": ["Brand positioning", "Visual identity", "Brand messaging"],
                        "audience_pain_points": ["Brand inconsistency", "Market differentiation", "Customer perception"]
                    },
                    {
                        "name": "Marketing Analytics",
                        "topics": ["KPI development", "Attribution modeling", "Performance tracking"],
                        "audience_pain_points": ["Data silos", "Measuring impact", "Actionable insights"]
                    }
                ]
            },
            'is_versioned': CONTENT_PILLARS_IS_VERSIONED,
            'is_shared': False,
            'initial_version': "default",
            'is_system_entity': False
        },
        # Methodology Implementation (System document)
        {
            'namespace': METHODOLOGY_IMPLEMENTATION_NAMESPACE_TEMPLATE,
            'docname': METHODOLOGY_IMPLEMENTATION_DOCNAME,
            'initial_data': {
                "methodology_name": "AI Copilot Content Strategy",
                "implementation_steps": [
                    "Analyze user DNA and preferences",
                    "Generate content strategy aligned with user goals",
                    "Create content briefs based on strategy",
                    "Develop multiple content concepts for review"
                ],
                "best_practices": [
                    "Maintain consistent brand voice",
                    "Focus on audience pain points",
                    "Incorporate industry trends",
                    "Balance educational and promotional content"
                ]
            },
            'is_versioned': False,
            'is_shared': METHODOLOGY_IMPLEMENTATION_IS_SHARED,
            'initial_version': None,
            'is_system_entity': METHODOLOGY_IMPLEMENTATION_IS_SYSTEM_ENTITY
        },
        # Building Blocks (System document)
        {
            'namespace': BUILDING_BLOCKS_NAMESPACE_TEMPLATE,
            'docname': BUILDING_BLOCKS_DOCNAME,
            'initial_data': {
                "core_building_blocks": [
                    "Audience analysis",
                    "Content pillars",
                    "Content formats",
                    "Distribution channels",
                    "Performance metrics"
                ],
                "implementation_framework": {
                    "phase_1": "Discovery and analysis",
                    "phase_2": "Strategy development",
                    "phase_3": "Content creation",
                    "phase_4": "Distribution and promotion",
                    "phase_5": "Measurement and optimization"
                },
                "success_indicators": [
                    "Engagement rate",
                    "Conversion metrics",
                    "Audience growth",
                    "Content consistency"
                ]
            },
            'is_versioned': False,
            'is_shared': BUILDING_BLOCKS_IS_SHARED,
            'initial_version': None,
            'is_system_entity': BUILDING_BLOCKS_IS_SYSTEM_ENTITY
        }
    ]

    # Define cleanup docs
    cleanup_docs: List[CleanupDocInfo] = [
        # User-specific documents
        {'namespace': USER_PREFERENCES_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': USER_PREFERENCES_DOCNAME, 'is_versioned': USER_PREFERENCES_IS_VERSIONED, 'is_shared': False, 'is_system_entity': False},
        {'namespace': USER_SOURCE_ANALYSIS_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': USER_SOURCE_ANALYSIS_DOCNAME, 'is_versioned': USER_SOURCE_ANALYSIS_IS_VERSIONED, 'is_shared': False, 'is_system_entity': False},
        {'namespace': CORE_BELIEFS_PERSPECTIVES_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': CORE_BELIEFS_PERSPECTIVES_DOCNAME, 'is_versioned': CORE_BELIEFS_PERSPECTIVES_IS_VERSIONED, 'is_shared': False, 'is_system_entity': False},
        {'namespace': CONTENT_PILLARS_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': CONTENT_PILLARS_DOCNAME, 'is_versioned': CONTENT_PILLARS_IS_VERSIONED, 'is_shared': False, 'is_system_entity': False},
        
        # Output document
        {'namespace': CONTENT_STRATEGY_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': CONTENT_STRATEGY_DOCNAME, 'is_versioned': CONTENT_STRATEGY_IS_VERSIONED, 'is_shared': False, 'is_system_entity': False},
        
        # # System documents
        # {'namespace': METHODOLOGY_IMPLEMENTATION_NAMESPACE_TEMPLATE, 'docname': METHODOLOGY_IMPLEMENTATION_DOCNAME, 'is_versioned': False, 'is_shared': METHODOLOGY_IMPLEMENTATION_IS_SHARED, 'is_system_entity': METHODOLOGY_IMPLEMENTATION_IS_SYSTEM_ENTITY},
        # {'namespace': BUILDING_BLOCKS_NAMESPACE_TEMPLATE, 'docname': BUILDING_BLOCKS_DOCNAME, 'is_versioned': False, 'is_shared': BUILDING_BLOCKS_IS_SHARED, 'is_system_entity': BUILDING_BLOCKS_IS_SYSTEM_ENTITY},
    ]

    # Predefined HITL inputs
    predefined_hitl_inputs = [
        # {
        #     "approval_status": "select_concepts",  # "regenerate", "restart_from_idea_generation"
        #     "selected_concepts": ["concept_1", "concept_2"],
        # }
        # feedback_text  ;  
    ]
    # VALID HUMAN INPUTS TYPE TO CONSOLE DIRECTLY, ENSURE SELECTED ID IS EXACT MATCH TO GENERATED!
    # {"approval_status": "select_concepts", "selected_concepts": ["concept_004"]}
    # {"approval_status": "regenerate"}
    # {"approval_status": "restart_from_idea_generation"}
    # Output validation function
    async def validate_content_strategy_output(outputs) -> bool:
        """
        Validates the output from the content strategy workflow against expected schema.
        
        Args:
            outputs: The workflow output dictionary to validate
            
        Returns:
            bool: True if validation passes, raises AssertionError otherwise
        """
        from typing import List, Dict, Any
        
        assert outputs is not None, "Validation Failed: Workflow returned no outputs."
        assert 'generated_output' in outputs, "Validation Failed: 'generated_output' missing."
        assert 'paths_processed' in outputs, "Validation Failed: 'paths_processed' missing."
        
        # Validate the content structure
        if 'generated_output' in outputs:
            strategy = outputs['generated_output']
            
            # Validate strategy structure based on ContentStrategySchema
            assert 'title' in strategy, "Strategy is missing 'title' field"
            
            # Validate target audience
            assert 'target_audience' in strategy, "Strategy is missing 'target_audience' field"
            audience = strategy['target_audience']
            assert 'primary' in audience, "Target audience missing 'primary' field"
            assert isinstance(audience['primary'], str), "'primary' audience should be a string"
            # secondary and tertiary are optional
            
            # Validate foundation elements
            assert 'foundation_elements' in strategy, "Strategy is missing 'foundation_elements' field"
            foundation = strategy['foundation_elements']
            assert 'expertise' in foundation, "Foundation elements missing 'expertise' field"
            assert isinstance(foundation['expertise'], list), "'expertise' should be a list"
            assert 'core_beliefs' in foundation, "Foundation elements missing 'core_beliefs' field"
            assert isinstance(foundation['core_beliefs'], list), "'core_beliefs' should be a list"
            assert 'objectives' in foundation, "Foundation elements missing 'objectives' field"
            assert isinstance(foundation['objectives'], list), "'objectives' should be a list"
            
            # Validate core perspectives
            assert 'core_perspectives' in strategy, "Strategy is missing 'core_perspectives' field"
            assert isinstance(strategy['core_perspectives'], list), "'core_perspectives' should be a list"
            
            # Validate content pillars
            assert 'content_pillars' in strategy, "Strategy is missing 'content_pillars' field"
            assert isinstance(strategy['content_pillars'], list), "'content_pillars' should be a list"
            for pillar in strategy['content_pillars']:
                assert 'name' in pillar, "Content pillar missing 'name' field"
                assert 'pillar' in pillar, "Content pillar missing 'pillar' field"
                assert 'sub_topic' in pillar, "Content pillar missing 'sub_topic' field"
                assert isinstance(pillar['sub_topic'], list), "Content pillar 'sub_topic' should be a list"
            
            # Validate post performance analysis (optional field)
            if 'post_performance_analysis' in strategy and strategy['post_performance_analysis'] is not None:
                performance = strategy['post_performance_analysis']
                assert 'current_engagement' in performance, "Post performance analysis missing 'current_engagement' field"
                assert 'content_that_resonates' in performance, "Post performance analysis missing 'content_that_resonates' field"
                assert 'audience_response' in performance, "Post performance analysis missing 'audience_response' field"
            
            # Validate implementation
            assert 'implementation' in strategy, "Strategy is missing 'implementation' field"
            implementation = strategy['implementation']
            
            # Validate 30-day targets
            assert 'thirty_day_targets' in implementation, "Implementation missing 'thirty_day_targets' field"
            thirty_day = implementation['thirty_day_targets']
            assert 'goal' in thirty_day, "30-day targets missing 'goal' field"
            assert 'method' in thirty_day, "30-day targets missing 'method' field"
            assert 'targets' in thirty_day, "30-day targets missing 'targets' field"
            
            # Validate 90-day targets
            assert 'ninety_day_targets' in implementation, "Implementation missing 'ninety_day_targets' field"
            ninety_day = implementation['ninety_day_targets']
            assert 'goal' in ninety_day, "90-day targets missing 'goal' field"
            assert 'method' in ninety_day, "90-day targets missing 'method' field"
            assert 'targets' in ninety_day, "90-day targets missing 'targets' field"
            
            # Log success message
            print(f"✓ Content strategy validated successfully")
            print(f"✓ Strategy title: {strategy.get('title', 'unknown')}")
            print(f"✓ Primary audience: {audience.get('primary', 'unknown')}")
            print(f"✓ Core beliefs: {', '.join(foundation.get('core_beliefs', []))[:100]}...")
            print(f"✓ Content pillars: {len(strategy.get('content_pillars', []))} defined")
            if 'post_performance_analysis' in strategy and strategy['post_performance_analysis']:
                print(f"✓ Post performance analysis included")
        
        return True

    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=predefined_hitl_inputs,
        setup_docs=setup_docs,
        cleanup_docs_created_by_setup=True,
        cleanup_docs=cleanup_docs,
        validate_output_func=validate_content_strategy_output,
        stream_intermediate_results=True,
        poll_interval_sec=5,
        timeout_sec=600
    )

    print(f"--- {test_name} Finished --- ")
    if final_run_outputs and 'generated_output' in final_run_outputs:
        strategy = final_run_outputs['generated_output']
        # Log based on actual schema structure
        print(f"Strategy Title: {strategy.get('title', 'unknown')}")
        
        # Target audience information
        target_audience = strategy.get('target_audience', {})
        print(f"Primary Audience: {target_audience.get('primary', 'unknown')}")
        if target_audience.get('secondary'):
            print(f"Secondary Audience: {target_audience.get('secondary')}")
        if target_audience.get('tertiary'):
            print(f"Tertiary Audience: {target_audience.get('tertiary')}")
        
        # Foundation elements
        foundation = strategy.get('foundation_elements', {})
        print(f"Areas of Expertise: {', '.join(foundation.get('expertise', []))}")
        print(f"Core Beliefs: {len(foundation.get('core_beliefs', []))} beliefs defined")
        print(f"Strategy Objectives: {len(foundation.get('objectives', []))} objectives defined")
        
        # Content pillars
        content_pillars = strategy.get('content_pillars', [])
        print(f"Content Pillars: {len(content_pillars)} pillars defined")
        for i, pillar in enumerate(content_pillars[:3], 1):  # Show first 3 pillars
            print(f"  Pillar {i}: {pillar.get('name', 'unknown')}")
        
        # Implementation timeline
        implementation = strategy.get('implementation', {})
        thirty_day = implementation.get('thirty_day_targets', {})
        ninety_day = implementation.get('ninety_day_targets', {})
        print(f"30-day Goal: {thirty_day.get('goal', 'unknown')}")
        print(f"90-day Goal: {ninety_day.get('goal', 'unknown')}")
        
        # Post performance analysis (if included)
        if strategy.get('post_performance_analysis'):
            print(f"Post Performance Analysis: Included")
        else:
            print(f"Post Performance Analysis: Not included")

if __name__ == "__main__":
    try:
        asyncio.run(main_test_idea_to_brief_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")

