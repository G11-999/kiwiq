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

from kiwi_client.workflows.active.document_models.customer_docs import (
    # User DNA
    USER_DNA_DOCNAME,
    USER_DNA_NAMESPACE_TEMPLATE,
    USER_DNA_IS_VERSIONED,
)

from kiwi_client.workflows.active.content_studio.llm_inputs.linkedin_alternate_text_suggestion_workflow import (
    GENERATION_SCHEMA,
    FEEDBACK_SCHEMA,
    USER_PROMPT_TEMPLATE,
    SYSTEM_PROMPT_TEMPLATE,
    FEEDBACK_SYSTEM_PROMPT,
    FEEDBACK_INITIAL_USER_PROMPT,
    FEEDBACK_ADDITIONAL_USER_PROMPT,
)

# --- Workflow Configuration Constants ---
# LLM Configuration
LLM_PROVIDER = "openai"
GENERATION_MODEL = "gpt-4.1"
LLM_TEMPERATURE = 1
LLM_MAX_TOKENS = 4000
MAX_ITERATIONS = 5

# Use the imported schema directly
GENERATION_SCHEMA_JSON = GENERATION_SCHEMA
FEEDBACK_SCHEMA_JSON = FEEDBACK_SCHEMA

# Prompt template variables and construct options
USER_PROMPT_TEMPLATE_VARIABLES = {
    "selected_text": None,
    "content_draft": None,
    "user_dna": None,
    "feedback_section": None
}

USER_PROMPT_TEMPLATE_CONSTRUCT_OPTIONS = {
    "selected_text": "selected_text",
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
    "selected_text": {
        "type": "str",
        "required": True,
        "description": "The text that was selected by the user for alternate suggestions"
    },
    "complete_content_doc": {
        "type": "str",
        "required": True,
        "description": "The complete content text (e.g., full LinkedIn post) containing the selected text"
    },
    "user_feedback": {
        "type": "str",
        "required": False,
        "description": "Optional feedback from the user about what kind of alternate text they want"
    },
    "entity_username": { 
        "type": "str", 
        "required": True, 
        "description": "Name of the entity to generate alternate text suggestions for."
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
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": USER_DNA_NAMESPACE_TEMPLATE, 
                            "input_namespace_field": "entity_username",
                            "static_docname": USER_DNA_DOCNAME,
                        },
                        "output_field_name": "user_dna"
                    }
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False}
            },
        },

        # --- 3. Construct Prompt ---
        "construct_prompt": {
            "node_id": "construct_prompt",
            "node_name": "prompt_constructor",
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

        # --- 5. Capture Approval ---
        "capture_approval": {
            "node_id": "capture_approval",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "approval_status": { 
                        "type": "enum", 
                        "enum_values": ["approved", "needs_work"], 
                        "required": True, 
                        "description": "User decision on the alternatives." 
                    },
                    "feedback_text": { 
                        "type": "str", 
                        "required": False, 
                        "description": "Optional feedback text from the user." 
                    }
                }
            }
        },

        # --- 6. Route Based on Approval ---
        "route_on_approval": {
            "node_id": "route_on_approval",
            "node_name": "router_node",
            "node_config": {
                "choices": ["check_iteration_limit", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "check_iteration_limit",
                        "input_path": "approval_status_from_hitl",
                        "target_value": "needs_work"
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "approval_status_from_hitl",
                        "target_value": "approved"
                    }
                ]
            }
        },

        # --- 7. Check Iteration Limit ---
        "check_iteration_limit": {
            "node_id": "check_iteration_limit",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "iteration_limit_check",
                        "condition_groups": [{
                            "logical_operator": "and",
                            "conditions": [{
                                "field": "generation_metadata.iteration_count",
                                "operator": "less_than",
                                "value": MAX_ITERATIONS
                            }]
                        }],
                        "group_logical_operator": "and"
                    }
                ],
                "branch_logic_operator": "and"
            }
        },

        # --- 8. Route Based on Iteration Limit ---
        "route_on_limit_check": {
            "node_id": "route_on_limit_check",
            "node_name": "router_node",
            "node_config": {
                "choices": ["route_to_initial_or_additional_prompt", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "route_to_initial_or_additional_prompt",
                        "input_path": "if_else_condition_tag_results.iteration_limit_check",
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

        # --- 9. Route to Appropriate Prompt Constructor ---
        "route_to_initial_or_additional_prompt": {
            "node_id": "route_to_initial_or_additional_prompt",
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_user_feedback_initial_prompt", "construct_user_feedback_additional_prompt"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_user_feedback_initial_prompt",
                        "input_path": "generation_metadata.iteration_count",
                        "target_value": 1
                    }
                ],
                "default_choice": "construct_user_feedback_additional_prompt"
            }
        },

        # --- 10. Construct Initial Feedback Prompt ---
        "construct_user_feedback_initial_prompt": {
            "node_id": "construct_user_feedback_initial_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "interpret_feedback_prompt": {
                        "id": "interpret_feedback_prompt",
                        "template": FEEDBACK_INITIAL_USER_PROMPT,
                        "variables": {
                            "current_alternatives": None,
                            "feedback_text": None,
                            "content_draft": None,
                            "user_dna": None
                        },
                        "construct_options": {
                            "current_alternatives": "current_alternatives",
                            "feedback_text": "current_feedback_text",
                            "content_draft": "complete_content_doc",
                            "user_dna": "user_dna"
                        }
                    }
                }
            }
        },

        # --- 11. Construct Additional Feedback Prompt ---
        "construct_user_feedback_additional_prompt": {
            "node_id": "construct_user_feedback_additional_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "interpret_feedback_prompt": {
                        "id": "interpret_feedback_prompt",
                        "template": FEEDBACK_ADDITIONAL_USER_PROMPT,
                        "variables": {
                            "current_alternatives": None,
                            "feedback_text": None,
                            "content_draft": None
                        },
                        "construct_options": {
                            "current_alternatives": "current_alternatives",
                            "feedback_text": "current_feedback_text",
                            "content_draft": "complete_content_doc"
                        }
                    }
                }
            }
        },

        # --- 12. Interpret Feedback ---
        "interpret_feedback": {
            "node_id": "interpret_feedback",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER,
                        "model": GENERATION_MODEL
                    },
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "default_system_prompt": FEEDBACK_SYSTEM_PROMPT,
                "output_schema": {
                    "schema_definition": FEEDBACK_SCHEMA_JSON,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 13. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {
                "dynamic_input_schema": {
                    "fields": {
                        "generated_output": {
                            "type": "dict",
                            "required": True,
                            "description": "The generated alternative text suggestions"
                        }
                    }
                }
            }
        }
    },

    "edges": [
        # Input -> State
        { 
            "src_node_id": "input_node", 
            "dst_node_id": "$graph_state", 
            "mappings": [
                { "src_field": "selected_text", "dst_field": "selected_text" },
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

        # Load User DNA -> Construct Prompt: Direct flow to next step
        { 
            "src_node_id": "load_all_context_docs", 
            "dst_node_id": "construct_prompt", 
            "mappings": [
                { "src_field": "user_dna", "dst_field": "user_dna" }
            ]
        },

        # State -> Construct Prompt: Provide all required data
        { 
            "src_node_id": "$graph_state", 
            "dst_node_id": "construct_prompt", 
            "mappings": [
                { "src_field": "selected_text", "dst_field": "selected_text" },
                { "src_field": "complete_content_doc", "dst_field": "complete_content_doc" },
                { "src_field": "user_feedback", "dst_field": "user_feedback" }
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

        # State (Messages) -> Generate Content: Provide conversation history if any
        { 
            "src_node_id": "$graph_state", 
            "dst_node_id": "generate_content", 
            "mappings": [
                { "src_field": "generate_content_messages_history", "dst_field": "messages_history", "description": "Pass existing message history for context."}
            ]
        },

        # Generate Content -> State
        { 
            "src_node_id": "generate_content", 
            "dst_node_id": "$graph_state", 
            "mappings": [
                { "src_field": "current_messages", "dst_field": "generate_content_messages_history" },
                { "src_field": "metadata", "dst_field": "generation_metadata", "description": "Store LLM metadata (e.g., token usage, iteration count)."},
                { "src_field": "structured_output", "dst_field": "current_alternatives" }
            ]
        },

        # Generate Content -> Capture Approval
        { 
            "src_node_id": "generate_content", 
            "dst_node_id": "capture_approval", 
            "mappings": [
                { "src_field": "structured_output", "dst_field": "current_alternatives" }
            ]
        },

        # Capture Approval -> State
        { 
            "src_node_id": "capture_approval", 
            "dst_node_id": "$graph_state", 
            "mappings": [
                { "src_field": "approval_status", "dst_field": "approval_status_from_hitl" },
                { "src_field": "feedback_text", "dst_field": "current_feedback_text" }
            ]
        },

        # Capture Approval -> Route on Approval
        { 
            "src_node_id": "capture_approval", 
            "dst_node_id": "route_on_approval", 
            "mappings": [
                { "src_field": "approval_status", "dst_field": "approval_status_from_hitl" }
            ]
        },

        # Route on Approval -> Check Iteration Limit
        { 
            "src_node_id": "route_on_approval", 
            "dst_node_id": "check_iteration_limit", 
            "mappings": []
        },

        # Route on Approval -> Output Node (approved case)
        { 
            "src_node_id": "route_on_approval", 
            "dst_node_id": "output_node", 
            "mappings": []
        },

        # State -> Output Node (for approved case)
        { 
            "src_node_id": "$graph_state", 
            "dst_node_id": "output_node", 
            "mappings": [
                { "src_field": "current_alternatives", "dst_field": "generated_output" }
            ]
        },

        # State -> Check Iteration Limit
        { 
            "src_node_id": "$graph_state", 
            "dst_node_id": "check_iteration_limit", 
            "mappings": [
                { "src_field": "generation_metadata", "dst_field": "generation_metadata" }
            ]
        },

        # Check Iteration Limit -> Route on Limit Check
        { 
            "src_node_id": "check_iteration_limit", 
            "dst_node_id": "route_on_limit_check", 
            "mappings": [
                { "src_field": "if_else_condition_tag_results", "dst_field": "if_else_condition_tag_results" },
                { "src_field": "iteration_branch_result", "dst_field": "iteration_branch_result" }
            ]
        },

        # Route on Limit Check -> Route to Initial or Additional Prompt
        { 
            "src_node_id": "route_on_limit_check", 
            "dst_node_id": "route_to_initial_or_additional_prompt", 
            "mappings": []
        },

        # Route on Limit Check -> Output Node (limit exceeded case)
        { 
            "src_node_id": "route_on_limit_check", 
            "dst_node_id": "output_node", 
            "mappings": []
        },

        # State -> Route to Initial or Additional Prompt
        { 
            "src_node_id": "$graph_state", 
            "dst_node_id": "route_to_initial_or_additional_prompt", 
            "mappings": [
                { "src_field": "generation_metadata", "dst_field": "generation_metadata" }
            ]
        },

        # Route to Initial or Additional Prompt -> Construct User Feedback Initial Prompt
        { 
            "src_node_id": "route_to_initial_or_additional_prompt", 
            "dst_node_id": "construct_user_feedback_initial_prompt", 
            "mappings": []
        },

        # Route to Initial or Additional Prompt -> Construct User Feedback Additional Prompt
        { 
            "src_node_id": "route_to_initial_or_additional_prompt", 
            "dst_node_id": "construct_user_feedback_additional_prompt", 
            "mappings": []
        },

        # State -> Construct User Feedback Initial Prompt
        { 
            "src_node_id": "$graph_state", 
            "dst_node_id": "construct_user_feedback_initial_prompt", 
            "mappings": [
                { "src_field": "current_alternatives", "dst_field": "current_alternatives" },
                { "src_field": "current_feedback_text", "dst_field": "current_feedback_text" },
                { "src_field": "complete_content_doc", "dst_field": "complete_content_doc" },
                { "src_field": "user_dna", "dst_field": "user_dna" }
            ]
        },

        # State -> Construct User Feedback Additional Prompt
        { 
            "src_node_id": "$graph_state", 
            "dst_node_id": "construct_user_feedback_additional_prompt", 
            "mappings": [
                { "src_field": "current_alternatives", "dst_field": "current_alternatives" },
                { "src_field": "current_feedback_text", "dst_field": "current_feedback_text" },
                { "src_field": "complete_content_doc", "dst_field": "complete_content_doc" }
            ]
        },

        # Construct User Feedback Initial Prompt -> Interpret Feedback
        { 
            "src_node_id": "construct_user_feedback_initial_prompt", 
            "dst_node_id": "interpret_feedback", 
            "mappings": [
                { "src_field": "interpret_feedback_prompt", "dst_field": "user_prompt" }
            ]
        },

        # Construct User Feedback Additional Prompt -> Interpret Feedback
        { 
            "src_node_id": "construct_user_feedback_additional_prompt", 
            "dst_node_id": "interpret_feedback", 
            "mappings": [
                { "src_field": "interpret_feedback_prompt", "dst_field": "user_prompt" }
            ]
        },

        # State -> Interpret Feedback
        { 
            "src_node_id": "$graph_state", 
            "dst_node_id": "interpret_feedback", 
            "mappings": [
                { "src_field": "interpret_feedback_messages_history", "dst_field": "messages_history" }
            ]
        },

        # Interpret Feedback -> State
        { 
            "src_node_id": "interpret_feedback", 
            "dst_node_id": "$graph_state", 
            "mappings": [
                { "src_field": "current_messages", "dst_field": "interpret_feedback_messages_history" },
                { "src_field": "structured_output", "dst_field": "interpreted_feedback" }
            ]
        },

        # Interpret Feedback -> Construct Prompt (back to generation)
        { 
            "src_node_id": "interpret_feedback", 
            "dst_node_id": "construct_prompt", 
            "mappings": [
                { "src_field": "structured_output", "dst_field": "feedback_section" }
            ]
        }
    ],

    "input_node_id": "input_node",
    "output_node_id": "output_node",

    "metadata": {
        "$graph_state": {
            "reducer": {
                "generate_content_messages_history": "add_messages",
                "interpret_feedback_messages_history": "add_messages"
            }
        }
    }
}

# --- Test Execution Logic ---
async def main_test_alternate_text_suggestion_workflow():
    """
    Test for Alternate Text Suggestion Workflow.
    """
    test_name = "Alternate Text Suggestion Workflow Test"
    print(f"--- Starting {test_name} --- ")

    # Example Inputs
    entity_username = "test_entity"
    
    test_inputs = {
        "selected_text": "Military commanders never keep mission-critical information in their heads—yet 83% of founders I've advised do exactly that.",
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
    async def validate_alternate_text_output(outputs) -> bool:
        """
        Validates the output from the alternate text suggestion workflow.
        """
        assert outputs is not None, "Validation Failed: Workflow returned no outputs."
        assert 'generated_output' in outputs, "Validation Failed: 'generated_output' missing."
        
        if 'generated_output' in outputs:
            suggestions = outputs['generated_output']
            assert 'alternatives' in suggestions, "Output missing 'alternatives' field"
            assert isinstance(suggestions['alternatives'], list), "'alternatives' should be a list"
            assert len(suggestions['alternatives']) >= 3, "Should provide at least 3 alternatives"
            
            print(f"✓ Alternate text suggestions validated successfully")
            print(f"✓ Number of alternatives: {len(suggestions['alternatives'])}")
            print(f"✓ First alternative: {suggestions['alternatives'][0][:100]}...")
        
        return True

    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=None,
        setup_docs=setup_docs,
        cleanup_docs_created_by_setup=True,
        cleanup_docs=cleanup_docs,
        validate_output_func=validate_alternate_text_output,
        stream_intermediate_results=True,
        poll_interval_sec=5,
        timeout_sec=600
    )

    print(f"--- {test_name} Finished --- ")
    if final_run_outputs and 'generated_output' in final_run_outputs:
        suggestions = final_run_outputs['generated_output']
        print("\nGenerated Alternatives:")
        for i, alt in enumerate(suggestions['alternatives'], 1):
            print(f"\n{i}. {alt}")

if __name__ == "__main__":
    try:
        asyncio.run(main_test_alternate_text_suggestion_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")
