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

from kiwi_client.workflows.document_models.customer_docs import (

    # Linkedin Content Analysis 
    CONTENT_ANALYSIS_DOCNAME,
    CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,

    # Linkedin Scraping
    LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE,
    LINKEDIN_PROFILE_DOCNAME,

    # Content Strategy
    USER_DNA_DOCNAME,
    USER_DNA_NAMESPACE_TEMPLATE,
    USER_DNA_IS_VERSIONED,
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


from kiwi_client.workflows.llm_inputs.user_understanding import (
    GENERATION_SCHEMA,
    USER_PROMPT_TEMPLATE,
    SYSTEM_PROMPT_TEMPLATE,
)


# --- Workflow Configuration Constants ---

# LLM Configuration
LLM_PROVIDER = "openai"
GENERATION_MODEL = "gpt-4.1"
LLM_TEMPERATURE = 1
LLM_MAX_TOKENS = 4000


### SAVE DOCUMENT CONFIG ###
SAVE_DOC_FILENAME_CONFIG = {
    "filename_config": {
        "input_namespace_field_pattern": USER_DNA_NAMESPACE_TEMPLATE, 
        "input_namespace_field": "entity_username",
        "static_docname": USER_DNA_DOCNAME,
    }
}
SAVE_DOC_GLOBAL_VERSIONING = {
    "is_versioned": USER_DNA_IS_VERSIONED,
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
    "content_analysis": None,
    "linkedin_profile": None,
    "user_source_analysis": None,
    "building_blocks": None
}

USER_PROMPT_TEMPLATE_CONSTRUCT_OPTIONS = {
    "methodology_implementation": "methodology_implementation",
    "user_preferences": "user_preferences",
    # "entity_username": "entity_username",
    "core_beliefs_perspectives": "core_beliefs_perspectives",
    "content_pillars": "content_pillars",
    "content_analysis": "content_analysis",
    "linkedin_profile": "linkedin_profile",
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
    { "src_field": "content_analysis", "dst_field": "content_analysis"},
    { "src_field": "linkedin_profile", "dst_field": "linkedin_profile"},
    { "src_field": "user_source_analysis", "dst_field": "user_source_analysis"},
    { "src_field": "building_blocks", "dst_field": "building_blocks"},
]

field_mappings_from_input_to_state = [
    { "src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs" },
    { "src_field": "entity_username", "dst_field": "entity_username" },
]

field_mappings_from_input_to_load_all_context_docs = [
    { "src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs" },
    { "src_field": "entity_username", "dst_field": "entity_username" },
]

field_mappings_from_load_all_context_docs_to_state = [
    { "src_field": "user_preferences", "dst_field": "user_preferences"},
    { "src_field": "methodology_implementation", "dst_field": "methodology_implementation"},
    { "src_field": "core_beliefs_perspectives", "dst_field": "core_beliefs_perspectives"},
    { "src_field": "content_pillars", "dst_field": "content_pillars"},
    { "src_field": "content_analysis", "dst_field": "content_analysis"},
    { "src_field": "linkedin_profile", "dst_field": "linkedin_profile"},
    { "src_field": "user_source_analysis", "dst_field": "user_source_analysis"},
    { "src_field": "building_blocks", "dst_field": "building_blocks"},
]

field_mappings_from_state_to_store_customer_data = [
    { "src_field": "entity_username", "dst_field": "entity_username"}
]

#############

### INPUTS ###

INPUT_FIELDS = {
    "customer_context_doc_configs": {
        "type": "list",
        "required": True,
        "description": "List of document identifiers (namespace/docname pairs) for customer context like DNA, strategy docs."
    },
    "entity_username": { "type": "str", "required": True, "description": "Name of the entity to generate strategy for."},
    # "entity_name": {"type": "str", "required": True},
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
                # Outputs: user_id, weeks_to_generate, customer_context_doc_configs, past_context_posts_limit -> $graph_state
        },

        # --- 2. Load Customer Context Documents and Scraped Posts (Single Node) ---
        "load_all_context_docs": {
            "node_id": "load_all_context_docs",
            "node_name": "load_customer_data",
            "node_config": {
                # Configure to load multiple documents based on the input list
                "load_configs_input_path": "customer_context_doc_configs", # Use the list from input node
                # Global defaults (can be overridden if needed per doc type via input structure)
                "global_is_shared": False,
                "global_is_system_entity": False,
                # "global_version_config": {"version": "default"},
                "global_schema_options": {"load_schema": False},
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
async def main_test_user_understanding_workflow():
    """
    Test for User Understanding Workflow.
    """
    test_name = "User Understanding Workflow Test"
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
        # LinkedIn Content Analysis
        {
            "filename_config": {
                "input_namespace_field_pattern": CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
                "input_namespace_field": "entity_username",
                "static_docname": CONTENT_ANALYSIS_DOCNAME,
            },
            "output_field_name": "content_analysis",  # Field for LinkedIn content analysis
        },
        # LinkedIn Profile
        {
            "filename_config": {
                "input_namespace_field_pattern": LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE,
                "input_namespace_field": "entity_username",
                "static_docname": LINKEDIN_PROFILE_DOCNAME,
            },
            "output_field_name": "linkedin_profile",  # Field for LinkedIn profile data
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

    test_context_docs = INPUT_DOCS_TO_BE_LOADED_IN_WORKFLOW
    
    entity_username = "test_entity"
    
    test_inputs = {
        "customer_context_doc_configs": test_context_docs,
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
        # LinkedIn Content Analysis
        {
            'namespace': CONTENT_ANALYSIS_NAMESPACE_TEMPLATE.format(item=entity_username),
            'docname': CONTENT_ANALYSIS_DOCNAME,
            'initial_data': {
                "theme_reports": [
                    {
                        "theme": "Leadership",
                        "key_insights": ["Focuses on team empowerment", "Emphasizes strategic thinking"],
                        "engagement_metrics": {"avg_likes": 45, "avg_comments": 12}
                    },
                    {
                        "theme": "Industry Trends",
                        "key_insights": ["Regularly discusses digital transformation", "Highlights emerging technologies"],
                        "engagement_metrics": {"avg_likes": 38, "avg_comments": 8}
                    }
                ],
                "overall_analysis": {
                    "content_strengths": ["Thought leadership", "Educational content"],
                    "content_gaps": ["Case studies", "Personal stories"]
                }
            },
            'is_versioned': False,
            'is_shared': False,
            'initial_version': None,
            'is_system_entity': False
        },
        # LinkedIn Profile
        {
            'namespace': LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE.format(item=entity_username),
            'docname': LINKEDIN_PROFILE_DOCNAME,
            'initial_data': {
                "profile_info": {
                    "headline": "Marketing Director | Digital Strategy | Brand Development",
                    "summary": "Experienced marketing professional with 10+ years in digital strategy and brand development.",
                    "experience": [
                        {
                            "title": "Marketing Director",
                            "company": "Tech Solutions Inc.",
                            "duration": "2018-Present"
                        },
                        {
                            "title": "Senior Marketing Manager",
                            "company": "Digital Innovations Co.",
                            "duration": "2015-2018"
                        }
                    ]
                },
                "skills": ["Digital Marketing", "Brand Strategy", "Content Marketing", "Analytics"]
            },
            'is_versioned': False,
            'is_shared': False,
            'initial_version': None,
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
        {'namespace': CONTENT_ANALYSIS_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': CONTENT_ANALYSIS_DOCNAME, 'is_versioned': False, 'is_shared': False, 'is_system_entity': False},
        {'namespace': LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': LINKEDIN_PROFILE_DOCNAME, 'is_versioned': False, 'is_shared': False, 'is_system_entity': False},
        
        # Output document
        {'namespace': CONTENT_STRATEGY_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': CONTENT_STRATEGY_DOCNAME, 'is_versioned': CONTENT_STRATEGY_IS_VERSIONED, 'is_shared': False, 'is_system_entity': False},
        
        # System documents
        {'namespace': METHODOLOGY_IMPLEMENTATION_NAMESPACE_TEMPLATE, 'docname': METHODOLOGY_IMPLEMENTATION_DOCNAME, 'is_versioned': False, 'is_shared': METHODOLOGY_IMPLEMENTATION_IS_SHARED, 'is_system_entity': METHODOLOGY_IMPLEMENTATION_IS_SYSTEM_ENTITY},
        {'namespace': BUILDING_BLOCKS_NAMESPACE_TEMPLATE, 'docname': BUILDING_BLOCKS_DOCNAME, 'is_versioned': False, 'is_shared': BUILDING_BLOCKS_IS_SHARED, 'is_system_entity': BUILDING_BLOCKS_IS_SYSTEM_ENTITY},
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
        Validates the output from the user understanding workflow against expected schema.
        
        Args:
            outputs: The workflow output dictionary to validate
            
        Returns:
            bool: True if validation passes, raises AssertionError otherwise
        """
        from typing import List, Dict, Any
        
        assert outputs is not None, "Validation Failed: Workflow returned no outputs."
        assert 'generated_output' in outputs, "Validation Failed: 'generated_output' missing."
        assert 'paths_processed' in outputs, "Validation Failed: 'paths_processed' missing."
        
        # Validate the user DNA structure
        if 'generated_output' in outputs:
            user_dna = outputs['generated_output']
            
            # Validate professional identity
            assert 'professional_identity' in user_dna, "User DNA missing 'professional_identity' field"
            prof_identity = user_dna['professional_identity']
            assert 'full_name' in prof_identity, "Professional identity missing 'full_name' field"
            assert 'job_title' in prof_identity, "Professional identity missing 'job_title' field"
            assert 'industry_sector' in prof_identity, "Professional identity missing 'industry_sector' field"
            assert 'areas_of_expertise' in prof_identity, "Professional identity missing 'areas_of_expertise' field"
            assert isinstance(prof_identity['areas_of_expertise'], list), "'areas_of_expertise' should be a list"
            
            # Validate LinkedIn profile analysis
            assert 'linkedin_profile_analysis' in user_dna, "User DNA missing 'linkedin_profile_analysis' field"
            linkedin_analysis = user_dna['linkedin_profile_analysis']
            assert 'engagement_metrics' in linkedin_analysis, "LinkedIn analysis missing 'engagement_metrics' field"
            assert 'top_performing_content_pillars' in linkedin_analysis, "LinkedIn analysis missing 'top_performing_content_pillars' field"
            assert isinstance(linkedin_analysis['top_performing_content_pillars'], list), "'top_performing_content_pillars' should be a list"
            
            # Validate brand voice and style
            assert 'brand_voice_and_style' in user_dna, "User DNA missing 'brand_voice_and_style' field"
            brand_voice = user_dna['brand_voice_and_style']
            assert 'communication_style' in brand_voice, "Brand voice missing 'communication_style' field"
            assert 'tone_preferences' in brand_voice, "Brand voice missing 'tone_preferences' field"
            assert isinstance(brand_voice['tone_preferences'], list), "'tone_preferences' should be a list"
            
            # Validate content strategy goals
            assert 'content_strategy_goals' in user_dna, "User DNA missing 'content_strategy_goals' field"
            strategy_goals = user_dna['content_strategy_goals']
            assert 'primary_goal' in strategy_goals, "Content strategy goals missing 'primary_goal' field"
            assert 'secondary_goals' in strategy_goals, "Content strategy goals missing 'secondary_goals' field"
            assert isinstance(strategy_goals['secondary_goals'], list), "'secondary_goals' should be a list"
            assert 'content_pillar_themes' in strategy_goals, "Content strategy goals missing 'content_pillar_themes' field"
            assert isinstance(strategy_goals['content_pillar_themes'], list), "'content_pillar_themes' should be a list"
            
            # Validate personal context
            assert 'personal_context' in user_dna, "User DNA missing 'personal_context' field"
            personal_context = user_dna['personal_context']
            assert 'personal_values' in personal_context, "Personal context missing 'personal_values' field"
            assert isinstance(personal_context['personal_values'], list), "'personal_values' should be a list"
            
            # Validate analytics insights
            assert 'analytics_insights' in user_dna, "User DNA missing 'analytics_insights' field"
            
            # Validate success metrics
            assert 'success_metrics' in user_dna, "User DNA missing 'success_metrics' field"
            success_metrics = user_dna['success_metrics']
            assert 'content_performance_kpis' in success_metrics, "Success metrics missing 'content_performance_kpis' field"
            assert isinstance(success_metrics['content_performance_kpis'], list), "'content_performance_kpis' should be a list"
            
            # Log success message
            print(f"✓ User DNA validated successfully")
            print(f"✓ User: {prof_identity.get('full_name', 'unknown')}")
            print(f"✓ Job Title: {prof_identity.get('job_title', 'unknown')}")
            print(f"✓ Industry: {prof_identity.get('industry_sector', 'unknown')}")
            print(f"✓ Primary Goal: {strategy_goals.get('primary_goal', 'unknown')}")
            print(f"✓ Communication Style: {brand_voice.get('communication_style', 'unknown')}")
        
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
        print(f"Target Audience: {strategy.get('target_audience', 'unknown')}")
        print(f"Content Purpose: {strategy.get('content_purpose', 'unknown')}")
        print(f"Content Format: {strategy.get('content_format', 'unknown')}")
        print(f"Tone and Style: {strategy.get('tone_and_style', 'unknown')}")
        print(f"Relevant Trends: {', '.join(strategy.get('relevant_trends', []))}")
        print(f"Posting Frequency: {strategy.get('posting_schedule', {}).get('frequency', 'unknown')}")

if __name__ == "__main__":
    try:
        asyncio.run(main_test_user_understanding_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")

