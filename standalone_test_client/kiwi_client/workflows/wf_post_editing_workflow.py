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
    # User DNA
    USER_DNA_DOCNAME,
    USER_DNA_NAMESPACE_TEMPLATE,
    USER_DNA_IS_VERSIONED,
)

from kiwi_client.workflows.llm_inputs.post_draft_edit_workflow import (
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

# Use the imported schema directly
GENERATION_SCHEMA_JSON = GENERATION_SCHEMA

# Prompt template variables and construct options
USER_PROMPT_TEMPLATE_VARIABLES = {
    "content_draft": None,
    "user_dna": None,
    "feedback_section": None  
}

USER_PROMPT_TEMPLATE_CONSTRUCT_OPTIONS = {
    "content_draft": "complete_content_doc",
    "user_dna": "user_dna",
    "feedback_section": "user_feedback"
}

SYSTEM_PROMPT_TEMPLATE_VARIABLES = {
    "schema": GENERATION_SCHEMA_JSON
}

SYSTEM_PROMPT_TEMPLATE_CONSTRUCT_OPTIONS = {}

### INPUTS ###
INPUT_FIELDS = {
    "customer_context_doc_configs": {
        "type": "list",
        "required": True,
        "description": "List of document identifiers (namespace/docname pairs) for customer context like DNA, strategy docs."
    },
    "complete_content_doc": {
        "type": "str",
        "required": True,
        "description": "The complete post draft text to be enhanced"
    },
    "user_feedback": {
        "type": "str",
        "required": True,
        "description": "Feedback from the user about how they want the post to be improved"
    },
    "entity_username": { 
        "type": "str", 
        "required": True, 
        "description": "Name of the entity to generate the enhanced post for."
    }
}

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

        # --- 2. Load User DNA ---
        "load_all_context_docs": {
            "node_id": "load_all_context_docs",
            "node_name": "load_customer_data",
            "node_config": {
                "load_configs_input_path": "customer_context_doc_configs",
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
            },
        },

        # --- 3. Construct Prompt ---
        "construct_prompt": {
            "node_id": "construct_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
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

        # --- 4. Generate Alternatives ---
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
                    "schema_definition": GENERATION_SCHEMA_JSON,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 5. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {
                "dynamic_input_schema": {
                    "fields": {
                        "generated_output": {
                            "type": "dict",
                            "required": True,
                            "description": "The enhanced post draft with hashtags"
                        }
                    }
                }
            }
        },
    },

    "edges": [
        # Input -> State
        { 
            "src_node_id": "input_node", 
            "dst_node_id": "$graph_state", 
            "mappings": [
                { "src_field": "complete_content_doc", "dst_field": "complete_content_doc" },
                { "src_field": "user_feedback", "dst_field": "user_feedback" },
                { "src_field": "entity_username", "dst_field": "entity_username" }
            ]
        },
        
        # Input -> Load User DNA
        { 
            "src_node_id": "input_node", 
            "dst_node_id": "load_all_context_docs", 
            "mappings": [
                { "src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs" },
                { "src_field": "entity_username", "dst_field": "entity_username" }
            ]
        },
        
        # Load User DNA -> State
        { 
            "src_node_id": "load_all_context_docs", 
            "dst_node_id": "$graph_state", 
            "mappings": [
                { "src_field": "user_dna", "dst_field": "user_dna" }
            ]
        },

        # Load User DNA -> Construct Prompt (Direct connection)
        { 
            "src_node_id": "load_all_context_docs", 
            "dst_node_id": "construct_prompt"
        },
        
        # State -> Construct Prompt
        { 
            "src_node_id": "$graph_state", 
            "dst_node_id": "construct_prompt", 
            "mappings": [
                { "src_field": "complete_content_doc", "dst_field": "complete_content_doc" },
                { "src_field": "user_feedback", "dst_field": "user_feedback" },
                { "src_field": "user_dna", "dst_field": "user_dna" }
            ]
        },
        
        # Construct Prompt -> Generate Alternatives
        { 
            "src_node_id": "construct_prompt", 
            "dst_node_id": "generate_content", 
            "mappings": [
                { "src_field": "user_prompt", "dst_field": "user_prompt" },
                { "src_field": "system_prompt", "dst_field": "system_prompt" }
            ]
        },
        
        # Generate Alternatives -> Output
        { 
            "src_node_id": "generate_content", 
            "dst_node_id": "output_node", 
            "mappings": [
                { "src_field": "structured_output", "dst_field": "generated_output" }
            ]
        }
    ],

    "input_node_id": "input_node",
    "output_node_id": "output_node"
}

# --- Test Execution Logic ---
async def main_test_idea_to_brief_workflow():
    """
    Test for Alternate Text Suggestion Workflow.
    """
    test_name = "Alternate Text Suggestion Workflow Test"
    print(f"--- Starting {test_name} --- ")

    # Example Inputs
    test_context_docs = [
        {
            "filename_config": {
                "input_namespace_field_pattern": USER_DNA_NAMESPACE_TEMPLATE, 
                "input_namespace_field": "entity_username",
                "static_docname": USER_DNA_DOCNAME,
            },
            "output_field_name": "user_dna"  # Field where the loaded DNA doc will be stored
        }
    ]
    
    entity_username = "test_entity"
    
    test_inputs = {
        "customer_context_doc_configs": test_context_docs,
        "complete_content_doc": "Military commanders never keep mission-critical information in their heads—yet 83% of founders I've advised do exactly that.\n\nIn the military, this approach would be considered a strategic vulnerability. No mission depends on one person knowing everything, but rather the opposite: Every soldier needs to know as much as is feasible about the mission to contribute in the best way possible.\n\nAt Wing, we implemented the military's 5-Point Operations Order for every strategic decision:\n\nSituation: What are we facing?\nMission: What must be accomplished?\nExecution: How specifically will we do it?\nSupport: What resources are required?\nCommand/Signal: Who makes decisions when things change?\n\nAs we've implemented this approach in our operations, we saw churn plummet by 60% and decisions being made faster than ever.\n\nYour business can't scale if critical knowledge remains trapped in your head.\n\nHow do you extract and distribute your expertise across your organization?",
        "user_feedback": "Make it more engaging and professional",
        "entity_username": entity_username
    }

    # Define setup documents
    setup_docs: List[SetupDocInfo] = [
        {
            'namespace': USER_DNA_NAMESPACE_TEMPLATE.format(item=entity_username), 
            'docname': USER_DNA_DOCNAME,
            'initial_data': {
                "background": "Experienced content strategist with 10+ years in digital marketing",
                "expertise": ["Content Strategy", "Digital Marketing", "Social Media"],
                "tone_preferences": {
                    "style": "Professional yet conversational",
                    "voice": "Authoritative but approachable",
                    "formality": "Semi-formal"
                },
                "content_goals": [
                    "Establish thought leadership",
                    "Share industry insights",
                    "Engage with professional community"
                ],
                "target_audience": {
                    "primary": "Marketing professionals",
                    "secondary": "Business leaders",
                    "tertiary": "Industry enthusiasts"
                }
            }, 
            'is_versioned': USER_DNA_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': "default",
            'is_system_entity': False
        }
    ]

    # Define cleanup docs
    cleanup_docs: List[CleanupDocInfo] = [
        {'namespace': USER_DNA_NAMESPACE_TEMPLATE.format(item=entity_username), 'docname': USER_DNA_DOCNAME, 'is_versioned': USER_DNA_IS_VERSIONED, 'is_shared': False, 'is_system_entity': False},
    ]

    # Output validation function
    async def validate_content_strategy_output(outputs) -> bool:
        """
        Validates the output from the post draft enhancement workflow.
        """
        assert outputs is not None, "Validation Failed: Workflow returned no outputs."
        assert 'generated_output' in outputs, "Validation Failed: 'generated_output' missing."
        
        if 'generated_output' in outputs:
            enhanced_post = outputs['generated_output']
            assert 'post_text' in enhanced_post, "Output missing 'post_text' field"
            assert 'hashtags' in enhanced_post, "Output missing 'hashtags' field"
            assert isinstance(enhanced_post['hashtags'], list), "'hashtags' should be a list"
            assert len(enhanced_post['hashtags']) > 0, "Should provide at least one hashtag"
            
            print(f"✓ Enhanced post draft validated successfully")
            print(f"✓ Post text length: {len(enhanced_post['post_text'])} characters")
            print(f"✓ Number of hashtags: {len(enhanced_post['hashtags'])}")
            print(f"✓ First few hashtags: {enhanced_post['hashtags'][:3]}")
        
        return True

    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=[],
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
        enhanced_post = final_run_outputs['generated_output']
        print("\nEnhanced Post:")
        print(f"\n{enhanced_post['post_text']}")
        print("\nHashtags:")
        for hashtag in enhanced_post['hashtags']:
            print(f"{hashtag}")

if __name__ == "__main__":
    try:
        asyncio.run(main_test_idea_to_brief_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")

