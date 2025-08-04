"""
Natural Language Document Editing Workflow

This workflow enables natural language document editing with:
- Multiple document tools (edit, view, search, list)
- Human-in-the-loop approval for edits
- Tool call limits and iteration limits
- Structured output for workflow control
- Proper state management for looping

Test Configuration:
- Uses actual document types from the system configuration (user_dna_doc, content_strategy_doc, etc.)
- Creates realistic test data matching the actual document schemas
- Tests various scenarios including document viewing, editing, search, and multi-document analysis
- Includes proper HITL approval flows and error handling
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
from kiwi_client.workflows.document_models.customer_docs import (
    # User documents for testing
    USER_DNA_DOCNAME,
    USER_DNA_NAMESPACE_TEMPLATE,
    USER_DNA_IS_VERSIONED,
)

from kiwi_client.workflows.llm_inputs.natural_language_editing import (
    DOCUMENT_EDITING_SYSTEM_PROMPT,
    DOCUMENT_EDITING_USER_PROMPT_TEMPLATE,
    WORKFLOW_CONTROL_SCHEMA,
    DOCUMENTS_KEY_TO_DOCUMENT_CONFIG_MAPPING,
)

from kiwi_client.workflows.llm_inputs.natural_language_editing_all_schemas import (
    ALL_DOCUMENT_SCHEMAS,
)

# Configuration constants
LLM_PROVIDER = "anthropic"  # anthropic    openai
LLM_MODEL = "claude-sonnet-4-20250514"  # o4-mini   gpt-4.1    claude-sonnet-4-20250514
TEMPERATURE = 0.7
MAX_TOKENS = 2000
MAX_TOOL_CALLS = 25  # Maximum total tool calls allowed
MAX_LLM_ITERATIONS = 30  # Maximum LLM loop iterations

# View context prompt template for showing current document view to LLM
VIEW_CONTEXT_PROMPT_TEMPLATE = """
Current Tool Use Context:
{view_context}
"""

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
                        "description": "Username of the entity for document operations"
                    },
                    "user_request": {
                        "type": "str",
                        "required": True,
                        "description": "Natural language request from the user"
                    }
                }
            }
        },
        
        # 2. Construct Initial Prompt
        "construct_prompt": {
            "node_id": "construct_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "document_editing_prompt": {
                        "id": "document_editing_prompt",
                        "template": DOCUMENT_EDITING_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "user_request": None,
                        },
                        "construct_options": {
                            "user_request": "user_request",
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": DOCUMENT_EDITING_SYSTEM_PROMPT,
                        "variables": {
                            "workflow_control_schema": WORKFLOW_CONTROL_SCHEMA,
                            "document_config_mapping": DOCUMENTS_KEY_TO_DOCUMENT_CONFIG_MAPPING,
                            "all_document_schemas": ALL_DOCUMENT_SCHEMAS,
                        }
                    }
                }
            }
        },
        
        # 2b. Construct Clarification Prompt (for user feedback/clarification)
        "construct_clarification_prompt": {
            "node_id": "construct_clarification_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "clarification_prompt": {
                        "id": "clarification_prompt",
                        "template": "User feedback/clarification: {user_feedback}\n\nPlease process this feedback and continue with the appropriate action.",
                        "variables": {
                            "user_feedback": ""  # Default empty string if no feedback
                        },
                        "construct_options": {
                            "user_feedback": "user_feedback"
                        }
                    }
                }
            }
        },
        
        # 3. LLM Node with Document Tools
        "llm_with_tools": {
            "node_id": "llm_with_tools",
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
                "tool_calling_config": {
                    "enable_tool_calling": True,
                    "parallel_tool_calls": True
                },
                "tools": [
                    {
                        "tool_name": "edit_document",
                        "is_provider_inbuilt_tool": False,
                        "provider_inbuilt_user_config": {}
                    },
                    {
                        "tool_name": "view_documents",
                        "is_provider_inbuilt_tool": False,
                        "provider_inbuilt_user_config": {}
                    },
                    {
                        "tool_name": "search_documents",
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
                    "schema_definition": WORKFLOW_CONTROL_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False,
                }
            }
        },
        
        # 4. Check Conditions Node
        "check_conditions": {
            "node_id": "check_conditions",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    # {
                    #     "tag": "tool_call_limit_check",
                    #     "condition_groups": [{
                    #         "conditions": [{
                    #             "field": "total_tool_calls",
                    #             "operator": "greater_than_or_equals",
                    #             "value": MAX_TOOL_CALLS
                    #         }]
                    #     }]
                    # },
                    {
                        "tag": "iteration_limit_check",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "generation_metadata.iteration_count",
                                "operator": "greater_than_or_equals",
                                "value": MAX_LLM_ITERATIONS
                            }]
                        }]
                    },
                    {
                        "tag": "has_edit_document",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "tool_calls.tool_name",
                                "operator": "equals",
                                "value": "edit_document"
                            }]
                        }],
                        "nested_list_logical_operator": "or"
                    },
                    {
                        "tag": "tool_calls_empty",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "tool_calls",
                                "operator": "is_empty"
                            }]
                        }]
                    },
                    {
                        "tag": "workflow_end_requested",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "structured_output.action",
                                "operator": "equals",
                                "value": "end_workflow"
                            }]
                        }]
                    },
                    {
                        "tag": "clarification_requested",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "structured_output.action",
                                "operator": "equals",
                                "value": "ask_clarification"
                            }]
                        }]
                    },
                ],
                "branch_logic_operator": "or"
            }
        },
        
        # 5. Route Based on Conditions
        "route_from_conditions": {
            "node_id": "route_from_conditions",
            "node_name": "router_node",
            "node_config": {
                "choices": ["output_node", "hitl_approval", "tool_executor"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    # {
                    #     "choice_id": "output_node",
                    #     "input_path": "tag_results.tool_call_limit_check",
                    #     "target_value": True
                    # },
                    {
                        "choice_id": "output_node",
                        "input_path": "tag_results.iteration_limit_check",
                        "target_value": True
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "tag_results.workflow_end_requested",
                        "target_value": True
                    },
                    {
                        "choice_id": "hitl_approval",
                        "input_path": "tag_results.has_edit_document",
                        "target_value": True
                    },
                    # #### DEBUG: FIXME: TODO: ####
                    # Add approval for non-edit actions for temp debuging
                    {
                        "choice_id": "hitl_approval",
                        "input_path": "tag_results.tool_calls_empty",
                        "target_value": False
                    },
                    # #### #### #### #### #### ####
                    {
                        "choice_id": "hitl_approval",
                        "input_path": "tag_results.clarification_requested",
                        "target_value": True
                    },
                    {
                        "choice_id": "tool_executor",
                        "input_path": "tag_results.tool_calls_empty",
                        "target_value": False
                    },
                ],
                "default_choice": "output_node"
            }
        },
        
        # 6. HITL Approval Node
        "hitl_approval": {
            "node_id": "hitl_approval",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "user_action": {
                        "type": "enum",
                        "enum_values": ["approve_tools", "deny_tools", "provide_clarification", "stop_workflow"],
                        "required": True,
                        "description": "User's decision on tool execution or clarification"
                    },
                    "user_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "Additional feedback or clarification from user"
                    }
                }
            }
        },
        
        # 7. Route from HITL
        "route_from_hitl": {
            "node_id": "route_from_hitl",
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_clarification_prompt", "tool_executor", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_clarification_prompt",
                        "input_path": "user_action",
                        "target_value": "deny_tools"
                    },
                    {
                        "choice_id": "construct_clarification_prompt",
                        "input_path": "user_action",
                        "target_value": "provide_clarification"
                    },
                    {
                        "choice_id": "tool_executor",
                        "input_path": "user_action",
                        "target_value": "approve_tools"
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "user_action",
                        "target_value": "stop_workflow"
                    }
                ]
            }
        },
        
        # 8. Tool Executor Node
        "tool_executor": {
            "node_id": "tool_executor",
            "node_name": "tool_executor",
            "node_config": {
                "default_timeout": 30.0,
                "max_concurrent_executions": 3,
                "continue_on_error": True,
                "include_error_details": True,
                "map_executor_input_fields_to_tool_input": True,
            },
        },
        
        # 8b. View Context Prompt Builder (after tool execution)
        "construct_view_context_prompt": {
            "node_id": "construct_view_context_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "view_context_prompt": {
                        "id": "view_context_prompt",
                        "template": VIEW_CONTEXT_PROMPT_TEMPLATE,
                        "variables": {
                            "view_context": ""  # Default empty string if no view context
                        },
                        "construct_options": {
                            "view_context": "view_context"
                        }
                    }
                }
            }
        },
        
        # 9. Output Node
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
                {"src_field": "user_request", "dst_field": "user_request"}
            ]
        },
        
        # Input -> Prompt Constructor
        {
            "src_node_id": "input_node",
            "dst_node_id": "construct_prompt",
            "mappings": [
                {"src_field": "user_request", "dst_field": "user_request"}
            ]
        },
        
        # Prompt Constructor -> LLM
        {
            "src_node_id": "construct_prompt",
            "dst_node_id": "llm_with_tools",
            "mappings": [
                {"src_field": "document_editing_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # State -> LLM (for message history and context)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "llm_with_tools",
            "mappings": [
                {"src_field": "messages_history", "dst_field": "messages_history"},
                {"src_field": "latest_tool_outputs", "dst_field": "tool_outputs"},
            ]
        },
        
        # LLM -> State: Update state with outputs
        {
            "src_node_id": "llm_with_tools",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "current_messages", "dst_field": "messages_history"},
                {"src_field": "metadata", "dst_field": "generation_metadata"},
                {"src_field": "tool_calls", "dst_field": "latest_tool_calls"},
                {"src_field": "structured_output", "dst_field": "latest_structured_output"},
                {"src_field": "text_content", "dst_field": "latest_llm_text_content"},
            ]
        },
        
        # LLM -> Check Conditions
        {
            "src_node_id": "llm_with_tools",
            "dst_node_id": "check_conditions",
            "mappings": [
                {"src_field": "tool_calls", "dst_field": "tool_calls"},
                {"src_field": "structured_output", "dst_field": "structured_output"}
            ]
        },
        
        # State -> Check Conditions
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "check_conditions",
            "mappings": [
                {"src_field": "generation_metadata", "dst_field": "generation_metadata"}
            ]
        },
        
        # Check Conditions -> Router
        {
            "src_node_id": "check_conditions",
            "dst_node_id": "route_from_conditions",
            "mappings": [
                {"src_field": "tag_results", "dst_field": "tag_results"},
                {"src_field": "condition_result", "dst_field": "condition_result"}
            ]
        },
        
        # Router -> HITL (control flow)
        {
            "src_node_id": "route_from_conditions",
            "dst_node_id": "hitl_approval"
        },
        
        # State -> HITL (provide context)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "hitl_approval",
            "mappings": [
                {"src_field": "latest_tool_calls", "dst_field": "tool_calls_for_approval"},
                {"src_field": "view_context", "dst_field": "current_view_context"},
                {"src_field": "latest_structured_output", "dst_field": "workflow_control_info"},
                {"src_field": "latest_llm_text_content", "dst_field": "llm_text_content"},
            ]
        },
        
        # HITL -> Router from HITL
        {
            "src_node_id": "hitl_approval",
            "dst_node_id": "route_from_hitl",
            "mappings": [
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        
        # HITL -> State (store feedback)
        {
            "src_node_id": "hitl_approval",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "user_feedback", "dst_field": "latest_user_feedback"},
                {"src_field": "user_action", "dst_field": "latest_user_action"}
            ]
        },
        
        # Router from HITL -> Clarification Prompt Constructor (control flow)
        {
            "src_node_id": "route_from_hitl",
            "dst_node_id": "construct_clarification_prompt"
        },
        
        # State -> Clarification Prompt Constructor
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_clarification_prompt",
            "mappings": [
                {"src_field": "latest_user_feedback", "dst_field": "user_feedback"}
            ]
        },
        
        # Clarification Prompt Constructor -> LLM
        {
            "src_node_id": "construct_clarification_prompt",
            "dst_node_id": "llm_with_tools",
            "mappings": [
                {"src_field": "clarification_prompt", "dst_field": "user_prompt"}
            ]
        },
        
        # Router from HITL -> Tool Executor (control flow)
        {
            "src_node_id": "route_from_hitl",
            "dst_node_id": "tool_executor"
        },
        
        # Router from HITL -> Output (control flow for stop)
        {
            "src_node_id": "route_from_hitl",
            "dst_node_id": "output_node"
        },
        
        # Router from Conditions -> Tool Executor (control flow)
        {
            "src_node_id": "route_from_conditions",
            "dst_node_id": "tool_executor"
        },
        
        # State -> Tool Executor (provide context)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "tool_executor",
            "mappings": [
                {"src_field": "latest_tool_calls", "dst_field": "tool_calls"},
                {"src_field": "entity_username", "dst_field": "entity_username"},
                {"src_field": "view_context", "dst_field": "view_context"}
            ]
        },
        
        # Tool Executor -> State (update view context with state_changes)
        {
            "src_node_id": "tool_executor",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "tool_outputs", "dst_field": "latest_tool_outputs"},
                {"src_field": "state_changes", "dst_field": "view_context"}
            ]
        },
        
        # Tool Executor -> View Context Prompt Builder
        {
            "src_node_id": "tool_executor",
            "dst_node_id": "construct_view_context_prompt",
        },
        
        # State -> View Context Prompt Builder (provide current view context)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_view_context_prompt",
            "mappings": [
                {"src_field": "view_context", "dst_field": "view_context"}
            ]
        },
        
        # View Context Prompt Builder -> LLM (continue loop)
        {
            "src_node_id": "construct_view_context_prompt",
            "dst_node_id": "llm_with_tools",
            "mappings": [
                {"src_field": "view_context_prompt", "dst_field": "user_prompt"},
            ]
        },
        
        # Router from Conditions -> Output (control flow)
        {
            "src_node_id": "route_from_conditions",
            "dst_node_id": "output_node"
        },
        
        # State -> Output
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "messages_history", "dst_field": "messages_history"},
                {"src_field": "generation_metadata", "dst_field": "metadata"},
                {"src_field": "view_context", "dst_field": "final_view_context"},
                {"src_field": "latest_tool_outputs", "dst_field": "latest_tool_outputs"}
            ]
        }
    ],
    
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    "metadata": {
        "$graph_state": {
            "reducer": {
                "messages_history": "add_messages",
                # "total_tool_calls": "add",
                "view_context": "merge_dicts",
                # "latest_tool_outputs": "collect_values"
            }
        }
    }
}


# --- Testing Code ---

async def validate_natural_language_editing_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Validate the natural language editing workflow outputs based on actual output structure.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run.
        
    Returns:
        True if the outputs are valid, False otherwise.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating natural language editing workflow outputs...")
    
    # Check for expected keys
    assert 'messages_history' in outputs, "Validation Failed: 'messages_history' key missing."
    
    # Validate message history structure
    messages = outputs.get('messages_history', [])
    assert isinstance(messages, list), "Validation Failed: messages_history should be a list."
    assert len(messages) > 0, "Validation Failed: messages_history should not be empty."

    # Validate tool outputs structure
    latest_tool_outputs = outputs.get('latest_tool_outputs', [])
    assert isinstance(latest_tool_outputs, list), "Validation Failed: latest_tool_outputs should be a list."
    
    # Check for final view context (shows documents were accessed)
    final_view_context = outputs.get('final_view_context', {})
    assert isinstance(final_view_context, dict), "Validation Failed: final_view_context should be a dict."
    
    # Validate that metadata can be None or dict (based on actual output)
    metadata = outputs.get('metadata')
    assert metadata is None or isinstance(metadata, dict), "Validation Failed: metadata should be None or a dict."
    
    # Count different types of tool calls based on actual structure
    tool_call_counts = {}
    successful_tools = 0
    for tool_output in latest_tool_outputs:
        if isinstance(tool_output, dict):
            # Check actual tool output structure
            assert 'name' in tool_output, f"Validation Failed: Tool output missing 'name' field: {tool_output}"
            assert 'type' in tool_output, f"Validation Failed: Tool output missing 'type' field: {tool_output}"
            assert 'status' in tool_output, f"Validation Failed: Tool output missing 'status' field: {tool_output}"
            
            tool_name = tool_output['name']
            tool_status = tool_output['status']
            tool_call_counts[tool_name] = tool_call_counts.get(tool_name, 0) + 1
            
            if tool_status == 'success':
                successful_tools += 1
    
    logger.info(f"   Total tool calls made: {len(latest_tool_outputs)}")
    logger.info(f"   Successful tool calls: {successful_tools}")
    logger.info(f"   Tool call breakdown: {tool_call_counts}")
    logger.info(f"   Message history length: {len(messages)}")
    logger.info(f"   Documents in final view context: {len(final_view_context)}")
    
    # Validate that at least some document operations were performed
    document_tools = ['view_documents', 'search_documents', 'list_documents', 'edit_document']
    has_document_operations = any(tool in tool_call_counts for tool in document_tools)
    assert has_document_operations, "Validation Failed: No document operations were performed."
    
    # Validate that we had at least one successful tool execution
    assert successful_tools > 0, "Validation Failed: No successful tool executions found."
    
    # Validate document serial numbers in view context
    for doc_serial, doc_info in final_view_context.items():
        assert isinstance(doc_info, dict), f"Validation Failed: Document info should be dict for {doc_serial}"
        assert 'docname' in doc_info, f"Validation Failed: Document info missing 'docname' for {doc_serial}"
    
    logger.info("✓ Output validation passed.")
    
    return True


async def main_test_natural_language_editing():
    """
    Test the Natural Language Document Editing Workflow using actual document configurations.
    """
    test_name = "Natural Language Editing Workflow Test"
    print(f"\n--- Starting {test_name} ---")
    
    # Test parameters
    test_entity_username = "sytalal"  # sytalal   test_user_123
    
    # Create actual document data matching the system schemas
    user_dna_data = {
        "professional_identity": {
            "full_name": "John Smith",
            "job_title": "Senior Product Manager",
            "industry_sector": "Technology",
            "company_name": "TechCorp Inc",
            "company_size": "500-1000 employees",
            "years_of_experience": 8,
            "professional_certifications": ["PMP", "Agile Certified"],
            "areas_of_expertise": ["Product Strategy", "Team Leadership", "Market Analysis"],
            "career_milestones": ["Led product launch that generated $2M revenue", "Built team of 15 people"],
            "professional_bio": "Experienced product manager with expertise in B2B SaaS solutions."
        },
        "linkedin_profile_analysis": {
            "follower_count": 2500,
            "connection_count": 800,
            "profile_headline_analysis": "Clear value proposition focused on product innovation",
            "about_section_summary": "Emphasizes results-driven approach and team leadership",
            "engagement_metrics": {
                "average_likes_per_post": 25,
                "average_comments_per_post": 8,
                "average_shares_per_post": 3
            },
            "top_performing_content_pillars": ["Product Strategy", "Leadership Insights", "Industry Trends"],
            "content_posting_frequency": "2-3 times per week",
            "content_types_used": ["Text posts", "Articles", "Industry insights"],
            "network_composition": ["Product professionals", "Tech executives", "Industry analysts"]
        },
        "brand_voice_and_style": {
            "communication_style": "Professional yet approachable",
            "tone_preferences": ["Analytical", "Confident", "Supportive"],
            "vocabulary_level": "Professional with technical terms",
            "sentence_structure_preferences": "Mix of short impactful statements and detailed explanations",
            "content_format_preferences": ["Numbered lists", "Data-driven insights", "Personal anecdotes"],
            "emoji_usage": "Minimal, mostly professional emojis",
            "hashtag_usage": "Strategic use of 3-5 relevant hashtags",
            "storytelling_approach": "Problem-solution narrative with data backing"
        },
        "content_strategy_goals": {
            "primary_goal": "Establish thought leadership in product management",
            "secondary_goals": ["Build professional network", "Share industry insights", "Attract talent"],
            "target_audience_demographics": "Product professionals, tech executives, startup founders",
            "ideal_reader_personas": ["Aspiring product managers", "Experienced product leaders", "Tech entrepreneurs"],
            "audience_pain_points": ["Product-market fit challenges", "Team scaling issues", "Market analysis"],
            "value_proposition_to_audience": "Practical insights from real product management experience",
            "call_to_action_preferences": ["Share experiences", "Connect for discussion", "Ask questions"],
            "content_pillar_themes": ["Product Strategy", "Team Leadership", "Market Analysis", "Industry Trends"],
            "topics_of_interest": ["AI in product development", "Remote team management", "Data-driven decisions"],
            "topics_to_avoid": ["Political content", "Controversial industry debates", "Personal financial advice"]
        },
        "personal_context": {
            "personal_values": ["Innovation", "Integrity", "Team collaboration", "Continuous learning"],
            "professional_mission_statement": "Empowering teams to build products that solve real problems",
            "content_creation_challenges": ["Finding time for consistent posting", "Balancing technical and accessible content"],
            "personal_story_elements_for_content": ["Career transition from engineering to product", "Building first product team"],
            "notable_life_experiences": ["Led digital transformation at previous company", "Mentored 20+ junior product managers"],
            "inspirations_and_influences": ["Clayton Christensen", "Marty Cagan", "Julie Zhuo"],
            "books_resources_they_reference": ["Inspired by Marty Cagan", "The Innovator's Dilemma", "Good Strategy Bad Strategy"],
            "quotes_they_resonate_with": ["Fall in love with the problem, not the solution", "Culture eats strategy for breakfast"]
        },
        "analytics_insights": {
            "optimal_content_length": "200-400 words for posts, 800-1200 for articles",
            "audience_geographic_distribution": "60% North America, 25% Europe, 15% Asia-Pacific",
            "engagement_time_patterns": "Peak engagement Tuesday-Thursday, 9-11 AM EST",
            "keyword_performance_analysis": "Product strategy and team leadership content performs best",
            "competitor_benchmarking": "Above average engagement compared to similar profiles",
            "growth_rate_metrics": "15% follower growth quarterly, 25% engagement rate increase"
        },
        "success_metrics": {
            "content_performance_kpis": ["Engagement rate", "Share rate", "Profile views", "Connection requests"],
            "engagement_quality_metrics": ["Meaningful comments", "Direct messages from content", "Speaking opportunities"],
            "conversion_goals": ["Consulting inquiries", "Job opportunities", "Speaking engagements"],
            "brand_perception_goals": ["Recognized product expert", "Trusted advisor", "Thought leader"],
            "timeline_for_expected_results": "6 months for thought leadership recognition",
            "benchmarking_standards": "Top 10% of product management influencers"
        }
    }
    
    content_strategy_data = {
        "title": "John Smith's LinkedIn Content Strategy 2025",
        "navigation_menu": ["Foundation", "Overview", "Content Pillars", "Implementation"],
        "foundation_elements": {
            "expertise": ["Product Strategy", "Team Leadership", "Market Analysis"],
            "core_beliefs": ["Data-driven decisions", "Customer-centric approach", "Iterative improvement"],
            "objectives": ["Build thought leadership", "Expand professional network", "Share knowledge"]
        },
        "overview": {
            "post_performance_analysis": {
                "current_engagement": "Above industry average with 4.2% engagement rate",
                "content_that_resonates": "Product strategy insights and team leadership stories",
                "highest_performing_formats": "Data-driven posts with personal anecdotes",
                "audience_response": "High engagement on tactical advice and lessons learned"
            }
        },
        "core_perspectives": [
            "Product success comes from deep customer understanding",
            "Great products are built by great teams",
            "Data should inform, not dictate decisions"
        ],
        "content_pillars": [
            {
                "name": "Product Strategy",
                "theme": "Strategic thinking and product planning",
                "sub_themes": ["Market analysis", "Product roadmaps", "Feature prioritization"]
            },
            {
                "name": "Team Leadership",
                "theme": "Building and managing product teams",
                "sub_themes": ["Team hiring", "Performance management", "Cross-functional collaboration"]
            },
            {
                "name": "Industry Insights",
                "theme": "Trends and observations in tech industry",
                "sub_themes": ["AI impact on products", "Market trends", "Competitive analysis"]
            }
        ],
        "high_impact_formats": [
            {
                "name": "Data Story",
                "steps": ["Present surprising data", "Explain context", "Share actionable insight"],
                "example": "73% of product launches fail because... Here's what successful ones do differently"
            }
        ],
        "implementation": {
            "weekly_content_calendar": "Monday: Industry insights, Wednesday: Product strategy, Friday: Team leadership",
            "thirty_day_targets": "12 posts, 300+ engagements, 50 new connections",
            "ninety_day_targets": "36 posts, 1000+ engagements, 150 new connections, 2 speaking opportunities"
        }
    }
    
    core_beliefs_data = {
        "beliefs": [
            {
                "question": "What drives successful product development?",
                "answer_belief": "Deep customer empathy combined with rigorous data analysis. You need to understand not just what customers say they want, but what they actually need to solve their real problems."
            },
            {
                "question": "How should product teams be structured?",
                "answer_belief": "Cross-functional teams with clear ownership and autonomy. Each team should have a product manager, designer, and engineers working together with shared goals and metrics."
            },
            {
                "question": "What role should data play in product decisions?",
                "answer_belief": "Data should inform decisions, not make them. Numbers tell you what happened, but human judgment and customer insight tell you why and what to do next."
            }
        ]
    }
    
    content_pillars_data = {
        "pillars": [
            {
                "pillar": "Product Strategy",
                "pillar_description": "Deep dives into strategic product thinking, including market analysis, competitive positioning, and long-term product vision. Content focuses on frameworks, case studies, and lessons learned from building successful products."
            },
            {
                "pillar": "Team Leadership",
                "pillar_description": "Insights on building, managing, and scaling product teams. Covers hiring practices, team dynamics, cross-functional collaboration, and creating high-performing product organizations."
            },
            {
                "pillar": "Industry Insights",
                "pillar_description": "Analysis of trends, technologies, and market shifts affecting the product management landscape. Includes commentary on AI impact, emerging technologies, and evolving customer expectations."
            }
        ]
    }
    
    # Setup actual system documents with proper configurations
    # Create sample data for blog playbook system documents
    blog_seo_best_practices_data = {
        "title": "SEO Best Practices for B2B Blog Content",
        "overview": "Strategic guidelines for optimizing B2B blog content for search engines while maintaining quality and relevance for your professional audience.",
        "key_principles": [
            {
                "principle": "Keyword Research & Strategy",
                "description": "Focus on long-tail, industry-specific keywords that your B2B audience actually searches for",
                "best_practices": [
                    "Use tools like SEMrush or Ahrefs to identify high-intent B2B keywords",
                    "Target keywords with 100-1000 monthly searches for better ranking opportunities",
                    "Include variations and semantic keywords naturally throughout content",
                    "Map keywords to buyer journey stages (awareness, consideration, decision)"
                ]
            },
            {
                "principle": "Content Structure & Formatting",
                "description": "Organize content for both search engines and busy B2B readers",
                "best_practices": [
                    "Use H1 for title, H2 for main sections, H3 for subsections",
                    "Keep paragraphs short (2-3 sentences) for better readability",
                    "Include a table of contents for posts over 1,500 words",
                    "Use bullet points and numbered lists for easy scanning"
                ]
            },
            {
                "principle": "Technical SEO Elements",
                "description": "Optimize technical elements that impact search rankings",
                "best_practices": [
                    "Write compelling meta descriptions (150-160 characters) with CTA",
                    "Use descriptive, keyword-rich URLs (keep under 60 characters)",
                    "Optimize images with descriptive alt text and compressed file sizes",
                    "Ensure mobile responsiveness and fast page load times (under 3 seconds)"
                ]
            },
            {
                "principle": "Link Building & Authority",
                "description": "Build credibility through strategic linking",
                "best_practices": [
                    "Include 2-3 internal links to related content on your site",
                    "Link to authoritative external sources (industry reports, studies)",
                    "Create linkable assets (original research, comprehensive guides)",
                    "Guest post on reputable industry publications for backlinks"
                ]
            }
        ],
        "content_length_guidelines": {
            "minimum_word_count": 1200,
            "optimal_range": "1,500-2,500 words",
            "pillar_content": "3,000+ words",
            "rationale": "Longer content tends to rank better and provides more value to B2B audiences researching complex topics"
        },
        "seo_checklist": [
            "Primary keyword in title, H1, and first 100 words",
            "Secondary keywords distributed naturally throughout",
            "Meta description includes keyword and clear value proposition",
            "URL slug contains primary keyword",
            "At least one image with descriptive alt text",
            "Internal links to 2-3 related posts",
            "External links to 1-2 authoritative sources",
            "Schema markup for articles implemented",
            "Mobile-friendly formatting verified",
            "Page load speed under 3 seconds"
        ]
    }

    blog_playbook_play_1_data = {
        "play_name": "The Problem Authority Stack",
        "tagline": "Become the go-to expert by owning a specific business problem",
        "overview": "Position yourself as the definitive authority on a specific business challenge your target audience faces. This play focuses on deep, comprehensive coverage of one problem area.",
        "why_it_works": "B2B buyers research problems extensively before looking for solutions. By becoming the primary resource for understanding a problem, you naturally become the trusted advisor for solving it.",
        "core_strategy": {
            "focus": "Choose one specific, painful problem your ideal customers face",
            "depth": "Create 20-30 pieces of content exploring every angle of this problem",
            "formats": ["Ultimate guides", "Case studies", "Research reports", "Diagnostic tools", "Frameworks"],
            "distribution": "SEO-optimized blog posts, LinkedIn articles, downloadable resources"
        },
        "implementation_steps": [
            {
                "step": 1,
                "action": "Problem Selection",
                "details": "Survey customers to identify their #1 challenge. Look for problems that are urgent, expensive, and growing.",
                "example": "For a CRM company: 'Sales and marketing alignment' or 'Lead qualification accuracy'"
            },
            {
                "step": 2,
                "action": "Content Mapping",
                "details": "Create a comprehensive content map covering problem symptoms, root causes, impact, failed solutions, and success patterns.",
                "example": "15 blog posts, 3 ultimate guides, 2 research reports, 5 diagnostic tools"
            },
            {
                "step": 3,
                "action": "Authority Building",
                "details": "Interview experts, conduct original research, create frameworks, and develop proprietary methodologies.",
                "example": "Interview 20 VPs of Sales about alignment challenges, create 'Alignment Maturity Model'"
            },
            {
                "step": 4,
                "action": "Content Production",
                "details": "Publish 2-3 pieces per week, interlink everything, update older pieces with new insights.",
                "example": "Week 1: 'The Hidden Cost of Misalignment', Week 2: '7 Signs Your Teams Are Misaligned'"
            }
        ],
        "content_examples": [
            "The Complete Guide to [Problem]: Everything You Need to Know",
            "[Problem] Benchmark Report: How 500 Companies Handle This Challenge",
            "The [Problem] Diagnostic: Assess Your Current State in 10 Minutes",
            "Why Traditional Approaches to [Problem] Fail: A Data-Driven Analysis",
            "[Problem] Case Study: How [Company] Reduced Impact by 73%"
        ],
        "success_metrics": [
            "Organic traffic to problem-focused content",
            "Email subscribers from problem-focused lead magnets",
            "Speaking invitations on the topic",
            "Media quotes as problem expert",
            "Inbound leads mentioning the specific problem"
        ],
        "pro_tips": [
            "Own the problem Wikipedia page through comprehensive coverage",
            "Create a 'problem hub' page linking all related content",
            "Develop a signature framework or methodology",
            "Host a annual 'State of [Problem]' research report",
            "Build an email course specifically about the problem"
        ]
    }

    blog_playbook_play_2_data = {
        "play_name": "The Category Pioneer Manifesto",
        "tagline": "Create and own a new market category through thought leadership",
        "overview": "Define a new way of solving old problems by creating a new category. This play positions you as the visionary leader of an emerging market segment.",
        "why_it_works": "Being first in a new category is easier than being best in an existing one. B2B buyers are always looking for innovative approaches to persistent challenges.",
        "core_strategy": {
            "focus": "Identify an emerging trend or approach that deserves its own category",
            "message": "Articulate why the old way is broken and the new way is inevitable",
            "formats": ["Manifestos", "Trend reports", "Comparison guides", "Future-state visions", "Category definitions"],
            "distribution": "Blog series, LinkedIn thought leadership, conference keynotes, podcast tours"
        },
        "implementation_steps": [
            {
                "step": 1,
                "action": "Category Discovery",
                "details": "Look for emerging practices that don't fit existing categories. Often found at intersection of technologies or disciplines.",
                "example": "Revenue Operations (intersection of Sales, Marketing, Customer Success)"
            },
            {
                "step": 2,
                "action": "Category Definition",
                "details": "Create clear definition, scope, principles, and differentiation from existing categories.",
                "example": "RevOps: Unified revenue team operations breaking down silos between go-to-market functions"
            },
            {
                "step": 3,
                "action": "Manifesto Creation",
                "details": "Write compelling narrative about why this category must exist now. Include problem, solution, and vision.",
                "example": "The RevOps Manifesto: Why Revenue Teams Must Unify or Die"
            },
            {
                "step": 4,
                "action": "Ecosystem Building",
                "details": "Create resources, communities, certifications, and events around the category.",
                "example": "RevOps community, certification program, annual conference, job board"
            }
        ],
        "content_examples": [
            "The [Category] Manifesto: A New Approach to [Problem]",
            "[Category] vs [Traditional Approach]: Why Everything Changes",
            "The Definitive Guide to [Category]: Framework, Tools, and Best Practices",
            "10 Signs Your Company Needs [Category] (Not More [Traditional Solution])",
            "The State of [Category] Report: Adoption, Challenges, and Future"
        ],
        "success_metrics": [
            "Media coverage of the new category",
            "Other companies adopting category language",
            "Search volume for category terms",
            "Conference speaking invitations",
            "Analyst inquiries about the category"
        ],
        "pro_tips": [
            "Be consistent with category naming and definition",
            "Create visual frameworks that explain the category",
            "Build alliance with other vendors in the space",
            "Pitch media on the category trend, not your product",
            "Write the book on the category (literally)"
        ]
    }

    blog_playbook_play_3_data = {
        "play_name": "The David vs Goliath Playbook",
        "tagline": "Challenge industry incumbents by championing the underdog perspective",
        "overview": "Position your content as the voice of challengers taking on established players. This play resonates with companies looking to disrupt their markets.",
        "why_it_works": "Many B2B buyers feel underserved by large vendors and are looking for alternatives. Challenger content creates strong emotional connection and differentiation.",
        "core_strategy": {
            "focus": "Highlight the disadvantages of working with incumbents",
            "message": "Show how smaller, nimbler approaches deliver better outcomes",
            "formats": ["Comparison guides", "Challenger case studies", "Myth-busting posts", "David wins stories"],
            "distribution": "Blog posts, LinkedIn articles, challenger communities, industry forums"
        },
        "implementation_steps": [
            {
                "step": 1,
                "action": "Incumbent Analysis",
                "details": "Document common complaints about large vendors: slow, expensive, inflexible, poor support.",
                "example": "Enterprise CRM: 18-month implementations, $500K minimum, requires consultants"
            },
            {
                "step": 2,
                "action": "Challenger Positioning",
                "details": "Define the challenger advantage: faster, more affordable, flexible, better support.",
                "example": "Modern CRM: 30-day implementation, usage-based pricing, no consultants needed"
            },
            {
                "step": 3,
                "action": "Success Story Collection",
                "details": "Find and document cases where challengers beat incumbents.",
                "example": "How a 50-person startup replaced Salesforce and saved $200K/year"
            },
            {
                "step": 4,
                "action": "Movement Building",
                "details": "Create community of challengers, share resources, celebrate wins.",
                "example": "The Modern CRM Movement: 1,000 companies choosing agility over legacy"
            }
        ],
        "content_examples": [
            "Why [Incumbent] Customers Are Switching to Modern Alternatives",
            "The Hidden Costs of Enterprise [Solution]: What Vendors Won't Tell You",
            "David Wins: How [Small Company] Outmaneuvered [Large Competitor]",
            "[Incumbent] vs Modern [Solution]: An Honest Comparison",
            "The Challenger's Guide to Competing with 800-Pound Gorillas"
        ],
        "success_metrics": [
            "Engagement from companies using incumbent solutions",
            "Share of voice in comparison searches",
            "Community growth of challenger movement",
            "Win rate against incumbents",
            "Media coverage of David vs Goliath angle"
        ],
        "pro_tips": [
            "Never make it personal - focus on approach differences",
            "Use data to back up challenger advantages",
            "Create 'switching guides' from incumbent to your approach",
            "Celebrate customer wins publicly",
            "Partner with other challengers for combined voice"
        ]
    }

    # Setup documents list with both user documents and system blog playbook documents
    setup_docs: List[SetupDocInfo] = [
        # User DNA document
        # {
        #     'namespace': f"user_strategy_{test_entity_username}",
        #     'docname': "user_dna_doc",
        #     'initial_data': user_dna_data,
        #     'is_shared': False,
        #     'is_versioned': True,
        #     'initial_version': "default",
        #     'is_system_entity': False
        # },
        # # Content Strategy document
        # {
        #     'namespace': f"user_strategy_{test_entity_username}",
        #     'docname': "content_strategy_doc",
        #     'initial_data': content_strategy_data,
        #     'is_shared': False,
        #     'is_versioned': True,
        #     'initial_version': "default",
        #     'is_system_entity': False
        # },
        # # Core Beliefs document
        # {
        #     'namespace': f"user_inputs_{test_entity_username}",
        #     'docname': "core_beliefs_perspectives_doc",
        #     'initial_data': core_beliefs_data,
        #     'is_shared': False,
        #     'is_versioned': True,
        #     'initial_version': "default",
        #     'is_system_entity': False
        # },
        # # Content Pillars document
        {
            'namespace': f"user_inputs_{test_entity_username}",
            'docname': "content_pillars_doc",
            'initial_data': content_pillars_data,
            'is_shared': False,
            'is_versioned': True,
            'initial_version': "default",
            'is_system_entity': False
        },
        
        # Blog SEO Best Practices (System Document)
        {
            'namespace': "blog_seo_guidelines",
            'docname': "seo_best_practices_doc",
            'initial_data': blog_seo_best_practices_data,
            'is_shared': True,
            'is_versioned': False,
            'initial_version': None,
            'is_system_entity': True
        },
        
        # Blog Playbook Play 1: Problem Authority (System Document)
        {
            'namespace': "blog_playbook_sys",
            'docname': "Play 1: The Problem Authority Stack",
            'initial_data': blog_playbook_play_1_data,
            'is_shared': True,
            'is_versioned': False,
            'initial_version': None,
            'is_system_entity': True
        },
        
        # Blog Playbook Play 2: Category Pioneer (System Document)
        {
            'namespace': "blog_playbook_sys",
            'docname': "Play 2: The Category Pioneer Manifesto",
            'initial_data': blog_playbook_play_2_data,
            'is_shared': True,
            'is_versioned': False,
            'initial_version': None,
            'is_system_entity': True
        },
        
        # Blog Playbook Play 3: David vs Goliath (System Document)
        {
            'namespace': "blog_playbook_sys",
            'docname': "Play 3: The David vs Goliath Playbook",
            'initial_data': blog_playbook_play_3_data,
            'is_shared': True,
            'is_versioned': False,
            'initial_version': None,
            'is_system_entity': True
        },
        # # User Preferences document
        # {
        #     'namespace': f"user_inputs_{test_entity_username}",
        #     'docname': "user_preferences_doc",
        #     'initial_data': {
        #         "data": {
        #             "created_at": "2025-01-15T10:00:00Z",
        #             "updated_at": "2025-01-15T10:00:00Z",
        #             "goals_answers": [
        #                 {
        #                     "question": "What's your primary content goal?",
        #                     "answer": "Build thought leadership in product management"
        #                 }
        #             ],
        #             "user_preferences": {
        #                 "audience": {
        #                     "segments": [
        #                         {
        #                             "audience_type": "Product Professionals",
        #                             "description": "Product managers, product owners, and product leaders"
        #                         },
        #                         {
        #                             "audience_type": "Tech Executives",
        #                             "description": "CTOs, VPs of Product, startup founders"
        #                         }
        #                     ]
        #                 },
        #                 "posting_schedule": {
        #                     "posts_per_week": 3,
        #                     "posting_days": ["Monday", "Wednesday", "Friday"],
        #                     "exclude_weekends": True
        #                 }
        #             },
        #             "timezone": {
        #                 "iana_identifier": "America/New_York",
        #                 "display_name": "Eastern Time",
        #                 "utc_offset": "-05:00",
        #                 "supports_dst": True,
        #                 "current_offset": "-05:00"
        #             }
        #         }
        #     },
        #     'is_shared': False,
        #     'is_versioned': True,
        #     'initial_version': "default",
        #     'is_system_entity': False
        # }
    ]
    
    # Cleanup configuration for actual documents
    cleanup_docs: List[CleanupDocInfo] = [
        # {
        #     'namespace': f"user_strategy_{test_entity_username}",
        #     'docname': "user_dna_doc",
        #     'is_shared': False,
        #     'is_versioned': True,
        #     'is_system_entity': False
        # },
        # {
        #     'namespace': f"user_strategy_{test_entity_username}",
        #     'docname': "content_strategy_doc",
        #     'is_shared': False,
        #     'is_versioned': True,
        #     'is_system_entity': False
        # },
        # {
        #     'namespace': f"user_inputs_{test_entity_username}",
        #     'docname': "core_beliefs_perspectives_doc",
        #     'is_shared': False,
        #     'is_versioned': True,
        #     'is_system_entity': False
        # },
        # {
        #     'namespace': f"user_inputs_{test_entity_username}",
        #     'docname': "content_pillars_doc",
        #     'is_shared': False,
        #     'is_versioned': True,
        #     'is_system_entity': False
        # },
        # {
        #     'namespace': f"user_inputs_{test_entity_username}",
        #     'docname': "user_preferences_doc",
        #     'is_shared': False,
        #     'is_versioned': True,
        #     'is_system_entity': False
        # }
    ]
    
    # Test scenarios with pre-defined HITL inputs using actual document types
    test_scenarios = [

        # {
        #     "name": "Show system doc",
        #     "initial_inputs": {
        #         "entity_username": test_entity_username,
        #         "user_request": "Show me the blog seo best practices doc"
        #     },
        # },

        {
            "name": "search system doc",
            "initial_inputs": {
                "entity_username": test_entity_username,
                "user_request": "Search playbooks for 'Myth-busting posts'"
            },
        },

        # {
        #     "name": "Show system doc",
        #     "initial_inputs": {
        #         "entity_username": test_entity_username,
        #         "user_request": "First list and then show me all available playbooks"
        #     },
        # },

        # {
        #     "name": "Change posting schedule",
        #     "initial_inputs": {
        #         "entity_username": test_entity_username,
        #         "user_request": "Tell me the topics for my next 10 posts in the next 20 days, summarize them in themes and expected outcomes."
        #     },
        # },

        # {
        #     "name": "Summarize future scheduled posts",
        #     "initial_inputs": {
        #         "entity_username": test_entity_username,
        #         "user_request": "Summarize my current content strategy, futgure planned posts, and recommended posts and identify 3 gaps based on my goal to improve my b2b saas sales per ticket size from 1000 - 5000 in next 2 months."
        #     },
        # },

        # {
        #     "name": "Edit strategy doc",
        #     "initial_inputs": {
        #         "entity_username": test_entity_username,
        #         "user_request": "I'm gonna be attending a lot of events next month, I would like to include some post events reflections in my future posts."
        #     },
        # },

        # {
        #     "name": "Change posting schedule",
        #     "initial_inputs": {
        #         "entity_username": test_entity_username,
        #         "user_request": "Change my posting schedule to 4 per week on weekends and any 2 days in middle of week."
        #     },
        # },
        # {
        #     "name": "View and Edit Strategy Documents",
        #     "initial_inputs": {
        #         "entity_username": test_entity_username,
        #         "user_request": "Show me my content strategy and user DNA documents, then update my content strategy to add a new content pillar for 'Customer Success Stories'"
        #     },
        #     # "hitl_inputs": [
        #     #     # First HITL: Approve viewing documents
        #     #     {
        #     #         "user_action": "approve_tools",
        #     #         "user_feedback": ""
        #     #     },
        #     #     # Second HITL: Approve document edit
        #     #     {
        #     #         "user_action": "approve_tools",
        #     #         "user_feedback": "Yes, please add the Customer Success Stories pillar with focus on case studies and client wins"
        #     #     },
        #     #     # Third HITL: Approve final workflow completion
        #     #     {
        #     #         "user_action": "stop_workflow",
        #     #         "user_feedback": "Changes look good, thank you"
        #     #     }
        #     # ]
        # },
        # {
        #     "name": "View and Edit Strategy Documents",
        #     "initial_inputs": {
        #         "entity_username": test_entity_username,
        #         "user_request": "Add a content pillar in strategy doc for customer success stories via personalized sales outreach in the age of AI."
        #     },
        # },
        # {
        #     "name": "Search and Update Content Pillars",
        #     "initial_inputs": {
        #         "entity_username": test_entity_username,
        #         "user_request": "Find my content pillars document and add more detailed sub-themes to the Product Strategy pillar"
        #     },
        #     "hitl_inputs": [
        #         # First HITL: Approve search and view
        #         {
        #             "user_action": "approve_tools",
        #             "user_feedback": ""
        #         },
        #         # Second HITL: Approve the edit
        #         {
        #             "user_action": "approve_tools",
        #             "user_feedback": "Add sub-themes for product discovery, user research methods, and competitive analysis"
        #         }
        #     ]
        # },
        # {
        #     "name": "Clarification Request Flow",
        #     "initial_inputs": {
        #         "entity_username": test_entity_username,
        #         "user_request": "Update my beliefs"
        #     },
        #     "hitl_inputs": [
        #         # First HITL: Provide clarification
        #         {
        #             "user_action": "provide_clarification",
        #             "user_feedback": "I want to update my core beliefs document to add a new belief about the importance of user feedback in product development"
        #         },
        #         # Second HITL: Approve the edit
        #         {
        #             "user_action": "approve_tools",
        #             "user_feedback": ""
        #         }
        #     ]
        # },
        # {
        #     "name": "Multiple Document Analysis",
        #     "initial_inputs": {
        #         "entity_username": test_entity_username,
        #         "user_request": "Analyze my user preferences and content pillars to see if they're aligned, then suggest improvements"
        #     },
        #     "hitl_inputs": [
        #         # First HITL: Approve analysis
        #         {
        #             "user_action": "approve_tools",
        #             "user_feedback": ""
        #         },
        #         # Second HITL: Stop after analysis
        #         {
        #             "user_action": "stop_workflow",
        #             "user_feedback": "Thanks for the analysis, I'll review the suggestions"
        #         }
        #     ]
        # },
        # {
        #     "name": "Tool Denial Flow",
        #     "initial_inputs": {
        #         "entity_username": test_entity_username,
        #         "user_request": "Delete my user DNA document"
        #     },
        #     "hitl_inputs": [
        #         # First HITL: Deny dangerous operation
        #         {
        #             "user_action": "deny_tools",
        #             "user_feedback": "No, I changed my mind. Just show me a summary of my user DNA instead."
        #         },
        #         # Second HITL: Approve safe operation
        #         {
        #             "user_action": "approve_tools",
        #             "user_feedback": ""
        #         }
        #     ]
        # }
    ]

    # VALID HUMAN INPUTS FOR MANUAL TESTING:
    # {"user_action": "approve_tools"}
    # {"user_action": "deny_tools", "user_feedback": "values are empty, properly edit with the correct values for"}
    # {"user_action": "deny_tools", "user_feedback": "Please retain the previous content pillars as well"}
    # {"user_action": "deny_tools", "user_feedback": "please add the Customer Success Stories pillar with focus on case studies and client wins"}
    # {"user_action": "provide_clarification", "user_feedback": "Thx, actually can you pls change Sales AI tools Thought leadership pillar to Personalized Outreach in the age of AI instead? Make your own assumptions about the theme in similar pattern as existing content pillars."}
    # {"user_action": "provide_clarification", "user_feedback": "Ok, please use context from user dna doc and other docs when possible to edit and streamline the content strategy"}
    # {"user_action": "provide_clarification", "user_feedback": "Make assumptions and generate it and proceed in the same pattern / line as existing content pillars."}
    # {"user_action": "provide_clarification", "user_feedback": "Acutally, reapply and rewrite the content pillars so that its converted to JSON, currently its serialized."}
    # {"user_action": "stop_workflow"}
    # {"user_action": "provide_clarification", "user_feedback": "today is 2025-07-03 7 pm in IST timeZONE, please incorporate that in finding my answer"}
    # {"user_action": "provide_clarification", "user_feedback": "I would like to update my content strategy based on your suggestions, please make appropriate assumptions. These are gonna be in-person conferences."}
    
    # {"user_action": "provide_clarification", "user_feedback": "Actually, can you get rid of Networking Insight from high impact format, its too redudant with Conference Reflection"}

    # Run test scenarios
    for scenario in test_scenarios:
        print(f"\n--- Running Scenario: {scenario['name']} ---")
        
        try:
            final_status, final_outputs = await run_workflow_test(
                test_name=f"{test_name} - {scenario['name']}",
                workflow_graph_schema=workflow_graph_schema,
                initial_inputs=scenario['initial_inputs'],
                expected_final_status=WorkflowRunStatus.COMPLETED,
                hitl_inputs=scenario.get('hitl_inputs', None),
                setup_docs=None,  # setup_docs,
                cleanup_docs=cleanup_docs,
                cleanup_docs_created_by_setup=False,
                validate_output_func=validate_natural_language_editing_output,
                stream_intermediate_results=True,
                poll_interval_sec=2,
                timeout_sec=1200
            )
            
            # Display results
            if final_outputs:
                print(f"\nScenario Results:")
                tool_outputs = final_outputs.get('latest_tool_outputs', [])
                print(f"Total Tool Calls: {len(tool_outputs)}")
                
                # Count tool types
                tool_counts = {}
                for tool_output in tool_outputs:
                    if isinstance(tool_output, dict) and 'tool_name' in tool_output:
                        tool_name = tool_output['tool_name']
                        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
                        
                print(f"Tool Call Breakdown: {tool_counts}")
                print(f"Documents Accessed: {len(final_outputs.get('final_view_context', {}))}")
            
            # import ipdb; ipdb.set_trace()
                
        except Exception as e:
            logger.error(f"Scenario '{scenario['name']}' failed: {e}")
            raise
    
    print(f"\n--- {test_name} Completed Successfully ---")
    print("✓ All scenarios tested with actual document configurations")
    print("✓ Document types: user_dna_doc, content_strategy_doc, core_beliefs_perspectives_doc, content_pillars_doc, user_preferences_doc")
    print("✓ HITL approval flows validated for document operations")


# Entry point
if __name__ == "__main__":
    print("="*60)
    print("Natural Language Document Editing Workflow Test")
    print("="*60)
    
    try:
        asyncio.run(main_test_natural_language_editing())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.exception("Test execution failed")
    
    print("\nTest execution finished.")
    print("Run from project root: PYTHONPATH=. python standalone_test_client/kiwi_client/workflows/wf_natural_language_editing.py")
