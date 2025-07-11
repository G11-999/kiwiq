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
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

from kiwi_client.workflows.document_models.customer_docs import (
    # LinkedIn Scraping
    LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE,
    LINKEDIN_PROFILE_DOCNAME,
)

from kiwi_client.workflows.llm_inputs.linkedin_profile_analysis_onboarding import (
    PROFILE_INSIGHTS_SCHEMA,
    PERSONALIZED_QUESTIONS_SCHEMA,
    TARGET_AUDIENCE_FRAMEWORK_SCHEMA,
    
    PROFILE_ANALYSIS_SYSTEM_PROMPT,
    PROFILE_ANALYSIS_USER_PROMPT,
    
    QUESTIONS_GENERATION_SYSTEM_PROMPT,
    QUESTIONS_GENERATION_USER_PROMPT,
    
    TARGET_AUDIENCE_SYSTEM_PROMPT,
    TARGET_AUDIENCE_USER_PROMPT,
)

# --- Workflow Configuration Constants ---

# LLM Configuration
LLM_PROVIDER = "openai"
GENERATION_MODEL = "gpt-4.1"
LLM_TEMPERATURE = 0.8
LLM_MAX_TOKENS = 3000

# --- Prompt Template Variables and Options ---

# Profile Analysis Node
PROFILE_ANALYSIS_SYSTEM_PROMPT_VARIABLES = {
    "profile_insights_schema": PROFILE_INSIGHTS_SCHEMA
}

PROFILE_ANALYSIS_USER_PROMPT_VARIABLES = {
    "linkedin_profile_data": None,
}

PROFILE_ANALYSIS_USER_PROMPT_CONSTRUCT_OPTIONS = {
    "linkedin_profile_data": "linkedin_profile_data",
}

# Questions Generation Node
QUESTIONS_GENERATION_SYSTEM_PROMPT_VARIABLES = {
    "questions_schema": PERSONALIZED_QUESTIONS_SCHEMA
}

QUESTIONS_GENERATION_USER_PROMPT_VARIABLES = {
    "linkedin_profile_data": None,
}

QUESTIONS_GENERATION_USER_PROMPT_CONSTRUCT_OPTIONS = {
    "linkedin_profile_data": "linkedin_profile_data",
}

# Target Audience Framework Node
TARGET_AUDIENCE_SYSTEM_PROMPT_VARIABLES = {
    "target_audience_schema": TARGET_AUDIENCE_FRAMEWORK_SCHEMA
}

TARGET_AUDIENCE_USER_PROMPT_VARIABLES = {
    "linkedin_profile_data": None,
}

TARGET_AUDIENCE_USER_PROMPT_CONSTRUCT_OPTIONS = {
    "linkedin_profile_data": "linkedin_profile_data",
}

# --- Edge Configurations ---

field_mappings_from_input_to_state = [
    {"src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs"},
    {"src_field": "entity_username", "dst_field": "entity_username"},
]

field_mappings_from_input_to_load_linkedin_profile = [
    {"src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs"},
    {"src_field": "entity_username", "dst_field": "entity_username"},
]

field_mappings_from_load_linkedin_profile_to_state = [
    {"src_field": "linkedin_profile", "dst_field": "linkedin_profile_data"},
]

field_mappings_from_state_to_profile_analysis = [
    {"src_field": "linkedin_profile_data", "dst_field": "linkedin_profile_data"},
]

field_mappings_from_profile_analysis_to_state = [
    {"src_field": "profile_insights", "dst_field": "profile_insights"},
]

field_mappings_from_state_to_questions_generation = [
    {"src_field": "linkedin_profile_data", "dst_field": "linkedin_profile_data"},
]

field_mappings_from_state_to_target_audience_framework = [
    {"src_field": "linkedin_profile_data", "dst_field": "linkedin_profile_data"},
]

field_mappings_from_questions_generation_to_state = [
    {"src_field": "personalized_questions", "dst_field": "personalized_questions"},
]

field_mappings_from_target_audience_framework_to_state = [
    {"src_field": "target_audience_outline", "dst_field": "target_audience_outline"},
]

# --- Input Fields ---

INPUT_FIELDS = {
    "customer_context_doc_configs": {
        "type": "list",
        "required": True,
        "description": "List of document identifiers (namespace/docname pairs) for customer context like DNA, strategy docs."
    },
    "entity_username": { "type": "str", "required": True, "description": "Name of the entity to generate strategy for."},
    # "entity_name": {"type": "str", "required": True},
}

# --- Workflow Graph Schema ---

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

        # --- 2. Load LinkedIn Profile ---
        "load_linkedin_profile": {
            "node_id": "load_linkedin_profile",
            "node_name": "load_customer_data",
            "node_config": {
                # Configure to load documents based on the input list
                "load_configs_input_path": "customer_context_doc_configs",
                # Global defaults
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
            }
        },

        # --- 3. Construct Profile Analysis Prompt ---
        "construct_profile_analysis_prompt": {
            "node_id": "construct_profile_analysis_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,  # Wait for all data loads before proceeding
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": PROFILE_ANALYSIS_USER_PROMPT,
                        "variables": PROFILE_ANALYSIS_USER_PROMPT_VARIABLES,
                        "construct_options": PROFILE_ANALYSIS_USER_PROMPT_CONSTRUCT_OPTIONS
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": PROFILE_ANALYSIS_SYSTEM_PROMPT,
                        "variables": PROFILE_ANALYSIS_SYSTEM_PROMPT_VARIABLES,
                        "construct_options": {}
                    }
                }
            }
        },

        # --- 4. Generate Profile Analysis ---
        "generate_profile_analysis": {
            "node_id": "generate_profile_analysis",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": GENERATION_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": PROFILE_INSIGHTS_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                },
            }
        },

        # --- 5. Construct Questions Generation Prompt ---
        "construct_questions_prompt": {
            "node_id": "construct_questions_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": QUESTIONS_GENERATION_USER_PROMPT,
                        "variables": QUESTIONS_GENERATION_USER_PROMPT_VARIABLES,
                        "construct_options": QUESTIONS_GENERATION_USER_PROMPT_CONSTRUCT_OPTIONS
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": QUESTIONS_GENERATION_SYSTEM_PROMPT,
                        "variables": QUESTIONS_GENERATION_SYSTEM_PROMPT_VARIABLES,
                        "construct_options": {}
                    }
                }
            }
        },

        # --- 6. Generate Questions ---
        "generate_questions": {
            "node_id": "generate_questions",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": GENERATION_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": PERSONALIZED_QUESTIONS_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                },
            }
        },

        # --- 7. Construct Target Audience Prompt ---
        "construct_target_audience_prompt": {
            "node_id": "construct_target_audience_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": TARGET_AUDIENCE_USER_PROMPT,
                        "variables": TARGET_AUDIENCE_USER_PROMPT_VARIABLES,
                        "construct_options": TARGET_AUDIENCE_USER_PROMPT_CONSTRUCT_OPTIONS
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": TARGET_AUDIENCE_SYSTEM_PROMPT,
                        "variables": TARGET_AUDIENCE_SYSTEM_PROMPT_VARIABLES,
                        "construct_options": {}
                    }
                }
            }
        },

        # --- 8. Generate Target Audience Framework ---
        "generate_target_audience_framework": {
            "node_id": "generate_target_audience_framework",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": GENERATION_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": TARGET_AUDIENCE_FRAMEWORK_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                },
            }
        },

        # --- 9. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {},
            "dynamic_input_schema": {
                "fields": {
                    "profile_insights": {
                        "type": "dict",
                        "required": True,
                        "description": "Analyzed profile insights including position, industry, skills, etc."
                    },
                    "personalized_questions": {
                        "type": "dict", 
                        "required": True,
                        "description": "Generated personalized questions about content creation goals."
                    },
                    "target_audience_outline": {
                        "type": "dict",
                        "required": True,
                        "description": "Target audience framework with audience type and description."
                    },
                    "generate_questions_output": {
                        "type": "dict",
                        "required": False,
                        "description": "Direct output from questions generation LLM node."
                    },
                    "generate_target_audience_framework_output": {
                        "type": "dict", 
                        "required": False,
                        "description": "Direct output from target audience framework LLM node."
                    }
                }
            }
        }
    },

    # --- Edges Defining Data Flow ---
    "edges": [
        # --- Initial Setup ---
        # Input -> State: Store initial inputs globally
        {
            "src_node_id": "input_node",
            "dst_node_id": "$graph_state",
            "mappings": field_mappings_from_input_to_state
        },
        
        # Input -> Load operations
        {
            "src_node_id": "input_node",
            "dst_node_id": "load_linkedin_profile",
            "mappings": field_mappings_from_input_to_load_linkedin_profile,
            "description": "Trigger LinkedIn profile loading."
        },

        # --- State Updates from Loaders ---
        {
            "src_node_id": "load_linkedin_profile",
            "dst_node_id": "$graph_state",
            "mappings": field_mappings_from_load_linkedin_profile_to_state
        },

        # --- Trigger Profile Analysis ---
        {
            "src_node_id": "load_linkedin_profile",
            "dst_node_id": "construct_profile_analysis_prompt"
        },

        # --- Mapping State to Profile Analysis ---
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_profile_analysis_prompt",
            "mappings": field_mappings_from_state_to_profile_analysis
        },

        # --- Construct Profile Analysis Prompt → Generate Profile Analysis ---
        {
            "src_node_id": "construct_profile_analysis_prompt",
            "dst_node_id": "generate_profile_analysis",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ],
            "description": "Send prompts to LLM for profile analysis."
        },

        # --- State -> Generate Profile Analysis ---
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "generate_profile_analysis",
            "mappings": [
                {"src_field": "messages_history", "dst_field": "messages_history"}
            ]
        },

        # --- Profile Analysis -> State ---
        {
            "src_node_id": "generate_profile_analysis",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "profile_insights"}
            ]
        },

        # --- Questions Generation Flow ---
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_questions_prompt",
            "mappings": field_mappings_from_state_to_questions_generation
        },

        # --- Trigger Questions Generation after Profile Analysis ---
        {
            "src_node_id": "generate_profile_analysis",
            "dst_node_id": "construct_questions_prompt"
        },

        # --- Construct Questions Prompt → Generate Questions ---
        {
            "src_node_id": "construct_questions_prompt",
            "dst_node_id": "generate_questions",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ],
            "description": "Send prompts to LLM for questions generation."
        },

        # --- State -> Generate Questions ---
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "generate_questions",
            "mappings": [
                {"src_field": "messages_history", "dst_field": "messages_history"}
            ]
        },

        # --- Questions Generation -> State ---
        {
            "src_node_id": "generate_questions",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "personalized_questions"}
            ]
        },

        # --- Target Audience Framework Flow ---
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_target_audience_prompt",
            "mappings": field_mappings_from_state_to_target_audience_framework
        },

        # --- Trigger Target Audience Framework after Profile Analysis ---
        {
            "src_node_id": "generate_profile_analysis",
            "dst_node_id": "construct_target_audience_prompt"
        },

        # --- Construct Target Audience Prompt → Generate Target Audience ---
        {
            "src_node_id": "construct_target_audience_prompt",
            "dst_node_id": "generate_target_audience_framework",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ],
            "description": "Send prompts to LLM for target audience generation."
        },

        # --- State -> Generate Target Audience ---
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "generate_target_audience_framework",
            "mappings": [
                {"src_field": "messages_history", "dst_field": "messages_history"}
            ]
        },

        # --- Target Audience Generation -> State ---
        {
            "src_node_id": "generate_target_audience_framework",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "target_audience_outline"}
            ]
        },

        # --- Final Output ---
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "profile_insights", "dst_field": "profile_insights"},
                {"src_field": "personalized_questions", "dst_field": "personalized_questions"},
                {"src_field": "target_audience_outline", "dst_field": "target_audience_outline"}
            ]
        },

        # --- Direct LLM Outputs ---
        {
            "src_node_id": "generate_questions",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "generate_questions_output"}
            ]
        },

        {
            "src_node_id": "generate_target_audience_framework",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "generate_target_audience_framework_output"}
            ]
        }
    ],

    # --- Define Start and End ---
    "input_node_id": "input_node",
    "output_node_id": "output_node",

    # --- State Reducers ---
    "metadata": {
        "$graph_state": {
            "reducer": {}
        }
    }
}

# --- Test Functions ---

async def validate_linkedin_profile_analysis_onboarding_output(
    outputs: Optional[Dict[str, Any]]
) -> bool:
    """Validate the workflow output"""
    if not outputs:
        logging.error("No outputs received from workflow")
        return False
    
    # Required fields from state
    required_fields = ["personalized_questions", "target_audience_outline", "profile_insights"]
    
    for field in required_fields:
        if field not in outputs:
            logging.error("Missing required output field")
            return False
    
    # Check for direct LLM outputs (optional but expected)
    direct_output_fields = ["generate_questions_output", "generate_target_audience_framework_output"]
    for field in direct_output_fields:
        if field not in outputs:
            logging.warning("Missing direct LLM output field")
    
    # Validate personalized questions structure
    questions = outputs.get("personalized_questions", {})
    question_categories = ["content_goals"]
    
    for category in question_categories:
        if category not in questions:
            logging.error(f"Missing question category: {category}")
            return False
        
        if not isinstance(questions[category], list) or len(questions[category]) == 0:
            logging.error(f"Question category {category} should be a non-empty list")
            return False
    
    # Validate target audience framework structure
    audience_framework = outputs.get("target_audience_outline", {})
    if not isinstance(audience_framework, dict):
        logging.error("target_audience_outline should be a dictionary")
        return False
    
    # Check for audience_segments array
    audience_segments = audience_framework.get("audience_segments", [])
    if not isinstance(audience_segments, list) or len(audience_segments) == 0:
        logging.error("target_audience_outline should contain a non-empty audience_segments list")
        return False
    
    # Check for required fields in each audience segment
    required_audience_fields = ["audience_type", "description"]
    for i, segment in enumerate(audience_segments):
        if not isinstance(segment, dict):
            logging.error(f"Audience segment {i} should be a dictionary")
            return False
        
        for field in required_audience_fields:
            if field not in segment:
                logging.error(f"Missing required audience field '{field}' in segment {i}")
                return False
    
    # Validate profile insights structure
    profile_insights = outputs.get("profile_insights", {})
    required_insight_fields = ["current_position", "industry", "experience_years", "top_skills"]
    
    for field in required_insight_fields:
        if field not in profile_insights:
            logging.error("Missing required profile insight field")
            return False
    
    logging.info("LinkedIn Profile Analysis Onboarding workflow output validation passed")
    return True


async def main_test_linkedin_profile_analysis_onboarding():
    """Test the LinkedIn Profile Analysis Onboarding workflow"""
    
    entity_username = "test_user_123"
    
    # LinkedIn Profile document configuration
    linkedin_profile_doc_config = [
        {
            "filename_config": {
                "input_namespace_field_pattern": LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE,
                "input_namespace_field": "entity_username",
                "static_docname": LINKEDIN_PROFILE_DOCNAME,
            },
            "output_field_name": "linkedin_profile",
            "is_shared": False,
            "is_system_entity": False
        }
    ]
    
    # Test inputs using customer_context_doc_configs pattern
    test_inputs = {
        "entity_username": entity_username,
        "customer_context_doc_configs": linkedin_profile_doc_config
    }
    
    # Setup documents - create LinkedIn profile document
    setup_docs = [
        {
            'namespace': LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE.format(item=entity_username),
            'docname': LINKEDIN_PROFILE_DOCNAME,
            'initial_data':{
      "geo": {
        "country": "United States",
        "city": "San Francisco Bay Area",
        "full": "San Francisco Bay Area",
        "countryCode": "us"
      },
      "username": "example-user",
      "summary": "Entrepreneurial product leader passionate about building futuristic customer solutions, using technology, behavioral understanding, a lot of enthusiasm and some patience. I get energized by bold ideas, smart cross-functional teams and meaningful problem spaces. \n\nIf you want to connect, feel free to drop me a line on user9@example.com.",
      "firstName": "Founder B",
      "headline": "Founder at KiwiQ AI | Building Intelligent Teammates for Marketers",
      "lastName": "Bharadwaj",
      "educations": [
        {
          "end": {
            "year": 2017,
            "month": 0,
            "day": 0
          },
          "fieldOfStudy": "Business Administration and Management, General",
          "start": {
            "year": 2015,
            "month": 0,
            "day": 0
          },
          "degree": "MBA",
          "schoolName": "University of Michigan - Stephen M. Ross School of Business"
        },
        {
          "end": {
            "year": 2011,
            "month": 0,
            "day": 0
          },
          "fieldOfStudy": "Mechanical Engineering",
          "start": {
            "year": 2007,
            "month": 0,
            "day": 0
          },
          "degree": "B.Tech",
          "schoolName": "National Institute of Technology, Tiruchirappalli"
        }
      ],
      
      "position": [
        {
          "location": "San Francisco Bay Area",
          "companyName": "Pavilion",
          "companyIndustry": "Think Tanks"
        },
        {
          "location": "San Francisco Bay Area",
          "description": "Building Agent helpers for Marketing teams",
          "companyName": "KiwiQ AI",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "San Francisco Bay Area",
          "description": "OnDeck Founder Fellow",
          "companyName": "On Deck",
          "companyIndustry": "Computer Software"
        },
        {
          "description": "Advising B2B startups with their GTM\n\nAngel invested in a few startups (B2B, Deeptech)",
          "companyName": "Various Startups",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "San Francisco, California, United States",
          "description": "Led research, planning, and delivery of 0-to-1 self-serve product targeting Brand Managers and Ad Agencies, scaling to 15 beta users first $100K ARR. \n\nWorked closely with the Founders, leading a cross-functional team of 4 Engineers and 1 UX Designer.",
          "companyName": "Swayable",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "San Francisco Bay Area",
          "description": "Closely partnered with an enterprise beta client to deliver Sounding Board's first SaaS product (0-to-1),\nmanaging a team of 9 engineers and 2 designers.",
          "companyName": "Sounding Board, Inc",
          "companyIndustry": "Professional Training & Coaching"
        },
        {
          "location": "Cupertino, California, United States",
          "description": "Single-threaded leader of the 3P fulfillment workstream for Amazon B2B; developed multi-\nyear product roadmap, driving feature prioritization and technical delivery plan.",
          "companyName": "Amazon",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "Santa Clara, California, United States",
          "description": "Led the internal GTM for a 0-to-1 customer insights product using NLP, growing to 50+ internal team users",
          "companyName": "Amazon",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "Luxembourg",
          "description": "Led product for personalization and customer experience for Amazon's launch in the Netherlands.",
          "companyName": "Amazon",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "Greater Seattle Area",
          "description": "Set up an NLP-powered Voice of Customer product function within Amazon's used products business.",
          "companyName": "Amazon",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "Austin, Texas Area",
          "companyName": "Dell",
          "companyIndustry": "Computer Hardware"
        },
        {
          "location": "São Paulo Area, Brazil",
          "companyName": "Bunzl plc",
          "companyIndustry": "Wholesale"
        },
        {
          "location": "Bengaluru Area, India",
          "description": "Launched the company's fastest growing category (0-to-1), wearing multiple hats to make it happen.",
          "companyName": "Urban Ladder",
          "companyIndustry": "Computer Software"
        }
      ],
      "created_at": "2025-05-24T05:10:33.407000",
      "updated_at": "2025-05-24T05:10:33.407000"
    },
            'is_versioned': False,
            'is_shared': False,
            'initial_version': None,
            'is_system_entity': False
        }
    ]
    
    # Cleanup documents
    cleanup_docs = [
        {
            'namespace': LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE.format(item=entity_username),
            'docname': LINKEDIN_PROFILE_DOCNAME,
            'is_versioned': False,
            'is_shared': False,
            'is_system_entity': False
        }
    ]
    
    # Run the test
    result = await run_workflow_test(
        test_name="LinkedIn Profile Analysis Onboarding Test",
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=[],
        setup_docs=setup_docs,
        cleanup_docs_created_by_setup=True,
        cleanup_docs=cleanup_docs,
        validate_output_func=validate_linkedin_profile_analysis_onboarding_output,
        stream_intermediate_results=True,
        poll_interval_sec=5,
        timeout_sec=600
    )
    
    if result[0].status == WorkflowRunStatus.COMPLETED:
        print("LinkedIn Profile Analysis Onboarding workflow test passed!")
        outputs = result[1]
        if outputs:
            # Show processed outputs (from state)
            audience_outline = outputs.get('target_audience_outline', {})
            if audience_outline.get('audience_type'):
                print("Generated target audience")
            
            # Show direct LLM outputs
            if 'generate_questions_output' in outputs:
                print("Direct Questions Output")
            
            if 'generate_target_audience_framework_output' in outputs:
                target_output = outputs['generate_target_audience_framework_output']
                if target_output.get('audience_type'):
                    print("Direct Target Audience Output")
                else:
                    print("Direct Target Audience Output: Generated single audience segment")
                
            # Show profile insights
            profile_insights = outputs.get('profile_insights', {})
            if profile_insights:
                print("Profile Analysis")
    else:
        print("LinkedIn Profile Analysis Onboarding workflow test failed!")
        print("Error")
    
    return result


if __name__ == "__main__":
    asyncio.run(main_test_linkedin_profile_analysis_onboarding()) 