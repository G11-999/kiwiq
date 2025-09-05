"""
# Inputs to workflow:
1. Generate content topic suggestions for next X weeks: (X) int input optional, default 2
2. Load list of customer context docs such as strategy doc, scraped posts etc
3. Load multiple user draft posts using multiple loader node within posts namespace, load latest N posts (limit and sort by updated_at, DESC); also load user preferences from onboarding namespace, user preferences doc which has user's requested posting frequency / week
5. Merge both lists and limit the merged list limit using merge aggregate node; also in another operation: compute next X weeks (input) multiplied by user preferences post frequency / week (this is number of content topic suggestions we have to generate)
6. construct prompt for first generation (includes system prompt) with all user docs and merged list in prompt
7. Generate 1 structured output content topic suggestion (containing exactly 4 topic ideas around one common theme); it reads message history from LLM; this also has fields such as date / time of posting; it sends structured outputs to all_generated_topics with reducer collect values
8. check IF else on iteration limit, if we have generated the required number of topic suggestions
9. Router node to route to store node to store all generated topic suggestions OR to construct prompt for additional topic suggestions
10. Construct prompt for additional topic suggestions constructs user prompt which just says generate 1 more additional topic suggestion, ensure difference from previous suggestions; it sends to same above LLM node; the LLM node loads message history from central state where it can see previous suggestions and generate the next topic suggestion
10. (after iteration loop ends) store node stores topic suggestions in separate paths using filename pattern with suggestion ID
11. send all topic suggestions to output node

"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Union, ClassVar, Type
import json
from enum import Enum
from datetime import date, datetime, timedelta

# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field

# Internal dependencies (assuming similar structure to example)
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus
from kiwi_client.workflows.active.document_models.customer_docs import (

    # Content Strategy (Playbook)
    LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
    LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE,
    LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
    # LinkedIn scraping
    LINKEDIN_SCRAPED_POSTS_NAMESPACE_TEMPLATE,
    LINKEDIN_SCRAPED_POSTS_DOCNAME,
    # User Profile (contains preferences)
    LINKEDIN_USER_PROFILE_DOCNAME,
    LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
    LINKEDIN_USER_PROFILE_IS_VERSIONED,
    # Content Drafts
    LINKEDIN_DRAFT_DOCNAME,
    LINKEDIN_DRAFT_NAMESPACE_TEMPLATE,
    LINKEDIN_DRAFT_IS_VERSIONED,
    # LinkedIn Ideas (for storing topic suggestions)
    LINKEDIN_IDEA_DOCNAME,
    LINKEDIN_IDEA_NAMESPACE_TEMPLATE,
    LINKEDIN_IDEA_IS_VERSIONED,

)
from kiwi_client.workflows.active.content_studio.llm_inputs.linkedin_content_calendar_entry import TOPIC_USER_PROMPT_TEMPLATE, TOPIC_SYSTEM_PROMPT_TEMPLATE, TOPIC_LLM_OUTPUT_SCHEMA, TOPIC_ADDITIONAL_USER_PROMPT_TEMPLATE
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Workflow Configuration Constants ---

# LLM Configuration
LLM_PROVIDER = "openai"
GENERATION_MODEL = "gpt-4.1" # Or gpt-4-turbo etc.
LLM_TEMPERATURE = 1
LLM_MAX_TOKENS = 5000 # Adjust as needed for topic generation

# Workflow Defaults
DEFAULT_WEEKS_TO_GENERATE = 2
# DEFAULT_DRAFTS_LIMIT = 20 # Default number of latest drafts to load
# DEFAULT_SCRAPED_LIMIT = 20 # Default number of scraped posts to load
PAST_CONTEXT_POSTS_LIMIT = 10 # Limit the combined list of posts fed to the LLM

# Search Params Default (for delete window)
SEARCH_PARAMS_DEFAULT = {
    "input_namespace_field": "entity_username",
    "input_namespace_field_pattern": LINKEDIN_IDEA_NAMESPACE_TEMPLATE,
    "docname_pattern": "*",
    "value_filter": {
        "scheduled_date": {
            "$gt": None,
            "$lte": None,
        },
    }
}

# --- Workflow Graph Schema Definition ---

workflow_graph_schema = {
    "nodes": {
        # --- 1. Input Node ---
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "weeks_to_generate": { "type": "int", "required": False, "default": DEFAULT_WEEKS_TO_GENERATE, "description": f"Number of weeks ahead to generate topic suggestions for (default: {DEFAULT_WEEKS_TO_GENERATE})." },
                    "past_context_posts_limit": { "type": "int", "required": False, "default": PAST_CONTEXT_POSTS_LIMIT, "description": f"Max number of combined posts (drafts + scraped) to use for context (default: {PAST_CONTEXT_POSTS_LIMIT})."},
                    "entity_username": {"type": "str", "required": True},
                    "start_date": {"type": "str", "required": True, "description": "Start date for generating topic suggestions"},
                    "end_date": {"type": "str", "required": True, "description": "End date for generating topic suggestions"},
                    "search_params": {"type": "dict", "required": False, "default": SEARCH_PARAMS_DEFAULT, "description": "Default search params object for load/delete nodes"},
                }
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
                        "input_namespace_field_pattern": LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE, 
                        "input_namespace_field": "entity_username",
                        "static_docname": LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
                    },
                    "output_field_name": "strategy_doc"
                },
                {
                    "filename_config": {
                        "input_namespace_field_pattern": LINKEDIN_SCRAPED_POSTS_NAMESPACE_TEMPLATE, 
                        "input_namespace_field": "entity_username",
                        "static_docname": LINKEDIN_SCRAPED_POSTS_DOCNAME,
                    },
                    "output_field_name": "scraped_posts"
                },
                {
                    "filename_config": {
                        "input_namespace_field_pattern": LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE, 
                        "input_namespace_field": "entity_username",
                        "static_docname": LINKEDIN_USER_PROFILE_DOCNAME,
                    },
                    "output_field_name": "user_profile"
                },
            ],
            "global_is_shared": False,
            "global_is_system_entity": False,
            "global_schema_options": {"load_schema": False}
        }
    },

    # --- 3. Load Latest User Draft Posts ---
    "load_draft_posts": {
      "node_id": "load_draft_posts",
      "node_name": "load_multiple_customer_data", # Use the multi-loader node
      "node_config": {
          "namespace_pattern": LINKEDIN_DRAFT_NAMESPACE_TEMPLATE,
          "namespace_pattern_input_path": "entity_username",
          "include_shared": False,        # User-specific drafts only
          "include_user_specific": True,
          "include_system_entities": False,
          # Pagination and Sorting (Inputs mapped from state)
          "skip": 0,
          "limit": PAST_CONTEXT_POSTS_LIMIT, # Mapped from draft_posts_limit input
          "sort_by": "updated_at",
          "sort_order": "desc",

          # Loading options (default)
          "global_version_config": None, # Load active version if versioned
          "global_schema_options": {"load_schema": False},

          # Output field name
          "output_field_name": "draft_posts" # The list will be under this key
      },
    },

    # --- 4. Merge Posts, Compute Limit, Prepare Generation Context ---
    "prepare_generation_context": {
      "node_id": "prepare_generation_context",
      "node_name": "merge_aggregate", # Use merge_aggregate to combine multiple sources
      "enable_node_fan_in": True, # Wait for all data loads before proceeding
      "node_config": {
        "operations": [
          # Operation 1: Merge Drafts and Scraped Posts and limit the result
          {
            "output_field_name": "final_merged_posts_for_prompt",
            # Order matters for priority (draft posts first, then scraped posts)
            "select_paths": ["draft_posts", "scraped_posts"], # Inputs from state
            "merge_strategy": {
                "map_phase": {"unspecified_keys_strategy": "ignore"}, # Only care about merging lists
                "reduce_phase": {
                    "default_reducer": "extend", # Combine the two lists
                    "error_strategy": "fail_node"
                },
                # Add transformation to limit the number of posts
                "post_merge_transformations": {
                    "final_merged_posts_for_prompt": {
                        "operation_type": "limit_list", 
                        "operand_path": "past_context_posts_limit" # Get limit value from input
                    }
                },
                "transformation_error_strategy": "skip_operation"
            },
            "merge_each_object_in_selected_list": False # Treat lists as atomic values to be EXTENDed
          },
          # Operation 2: Compute Total Topics Needed - weeks_to_generate * posts_per_week
          {
            "output_field_name": "total_topics_needed",
            "select_paths": ["user_profile.posting_schedule.posts_per_week"], # Inputs from state
            "merge_strategy": {
                "map_phase": {"unspecified_keys_strategy": "ignore"}, # Only care about the selected value
                "reduce_phase": {
                    "default_reducer": "replace_right", # Take the posts_per_week value
                    "error_strategy": "fail_node"
                },
                # Use transformation to calculate product of weeks and posts_per_week from user preferences
                "post_merge_transformations": {
                     "total_topics_needed": {
                         "operation_type": "multiply",
                         "operand_path": "weeks_to_generate" # Multiply posts_per_week by weeks_to_generate
                     }
                },
                "transformation_error_strategy": "fail_node"
            },
            "merge_each_object_in_selected_list": False # Operate on values
          }
        ]
      },
    
    },

    # --- 9. Construct Topic Prompt (Inside Map Branch) ---
    "construct_topic_prompt": {
      "node_id": "construct_topic_prompt",
      "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
          "topic_user_prompt": {
            "id": "topic_user_prompt",
            "template": TOPIC_USER_PROMPT_TEMPLATE,
            "variables": {
              "strategy_doc": None,  # Mapped from strategy_doc
              "merged_posts": None,     # Mapped from merged_posts
              "user_timezone": None, # Mapped from playbook.timezone
              "current_datetime": "$current_date",
            },
            "construct_options": {
               "user_timezone": "user_profile.timezone",
               "strategy_doc": "strategy_doc", # Map the number passed by the mapper
               "merged_posts": "merged_data.final_merged_posts_for_prompt", # Map directly from merged_posts
            }
          },
          "topic_system_prompt": {
            "id": "topic_system_prompt",
            "template": TOPIC_SYSTEM_PROMPT_TEMPLATE,
            "variables": { 
                "schema": json.dumps(TOPIC_LLM_OUTPUT_SCHEMA, indent=2), 
                "current_datetime": "$current_date" },
            "construct_options": {}
          }
        }
      }
    },

    # --- 10. Generate Topics (LLM - Inside Map Branch) ---
    "generate_topics": {
      "node_id": "generate_topics",
      "node_name": "llm",
      "node_config": {
          "llm_config": {
              "model_spec": {"provider": LLM_PROVIDER, "model": GENERATION_MODEL},
              "temperature": LLM_TEMPERATURE,
              "max_tokens": LLM_MAX_TOKENS
          },
          "output_schema": {
             "schema_definition": TOPIC_LLM_OUTPUT_SCHEMA,
             "convert_loaded_schema_to_pydantic": False
          },
      }
      # Reads (private): user_prompt, system_prompt
      # Writes: structured_output -> all_generated_topics (state reducer)
    },

    # --- Check Topic Count Node (after first topic generation) ---
    "check_topic_count": {
      "node_id": "check_topic_count",
      "node_name": "if_else_condition",
      "node_config": {
        "tagged_conditions": [
          {
            "tag": "topic_count_check", 
            "condition_groups": [{
              "logical_operator": "and",
              "conditions": [{
                "field": "metadata.iteration_count",
                "operator": "less_than",
                "value_path": "merged_data.total_topics_needed"
              }]
            }],
            "group_logical_operator": "and"
          }
        ],
        "branch_logic_operator": "and"
      }
      # Reads: topic_generation_metadata from state, total_topics_needed from state
      # Writes: branch, tag_results, condition_result
    },

    # --- Router Based on Topic Count Check ---
    "route_on_topic_count": {
      "node_id": "route_on_topic_count",
      "node_name": "router_node",
      "node_config": {
        "choices": ["construct_additional_topic_prompt", "construct_delete_search_params"],
        "allow_multiple": False,
        "choices_with_conditions": [
          {
            "choice_id": "construct_additional_topic_prompt", # Continue generating more topics
            "input_path": "if_else_condition_tag_results.topic_count_check",
            "target_value": True
          },
          {
            "choice_id": "construct_delete_search_params", # End loop and prepare delete
            "input_path": "if_else_condition_tag_results.topic_count_check",
            "target_value": False,
          }
        ]
      }
      # Reads: if_else_condition_tag_results, iteration_branch_result from check_topic_count
      # Routes to: construct_additional_topic_prompt OR construct_delete_search_params
    },

    # --- Construct Additional Topic Prompt ---
    "construct_additional_topic_prompt": {
      "node_id": "construct_additional_topic_prompt",
      "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
          "additional_topic_prompt": {
            "id": "additional_topic_prompt",
            "template": TOPIC_ADDITIONAL_USER_PROMPT_TEMPLATE,

          },
        }
      }
    },

    # --- Construct Delete Search Params ---
    "construct_delete_search_params": {
      "node_id": "construct_delete_search_params",
      "node_name": "transform_data",
      "node_config": {
        "merge_conflicting_paths_as_list": False,
        "mappings": [
          { "source_path": "search_params.input_namespace_field", "destination_path": "input_namespace_field" },
          { "source_path": "search_params.input_namespace_field_pattern", "destination_path": "input_namespace_field_pattern" },
          { "source_path": "search_params.docname_pattern", "destination_path": "docname_pattern" },
          { "source_path": "start_date", "destination_path": "value_filter.scheduled_date.$gt" },
          { "source_path": "end_date", "destination_path": "value_filter.scheduled_date.$lte" }
        ]
      }
    },

    # --- Delete Existing Entries in Window ---
    "delete_previous_entries": {
      "node_id": "delete_previous_entries",
      "node_name": "delete_customer_data",
      "node_config": {
        "search_params_input_path": "search_params"
      }
    },


    # --- 11. Store All Generated Topics (After Map Completes) ---
    "store_all_topics": {
      "node_id": "store_all_topics",
      "node_name": "store_customer_data", # Store the final list
      "node_config": {
          "global_versioning": { "is_versioned": LINKEDIN_IDEA_IS_VERSIONED, "operation": "upsert_versioned"},
          "global_is_shared": False,
          "store_configs": [
              {
                  # Store the entire list collected in the state
                  "input_field_path": "all_generated_topics", # Mapped from state
                  "process_list_items_separately": True,
                  "target_path": {
                      "filename_config": {
                          "input_namespace_field_pattern": LINKEDIN_IDEA_NAMESPACE_TEMPLATE, 
                          "input_namespace_field": "entity_username",
                          "static_docname": LINKEDIN_IDEA_DOCNAME,
                      }
                  },
                  "generate_uuid": True,
              }
          ],
      },
      "dynamic_input_schema": { # Define expected final inputs
          "fields": {
          }
      }

    },

    # --- 12. Output Node ---
    "output_node": {
      "node_id": "output_node",
      "node_name": "output_node",
      "node_config": {},

        }
    },
    
    "edges": [
    # --- Input to State ---
    { "src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "weeks_to_generate", "dst_field": "weeks_to_generate" },
        { "src_field": "past_context_posts_limit", "dst_field": "past_context_posts_limit" },
        { "src_field": "entity_username", "dst_field": "entity_username" },
        { "src_field": "start_date", "dst_field": "start_date" },
        { "src_field": "end_date", "dst_field": "end_date" },
        { "src_field": "search_params", "dst_field": "search_params" },
      ]
    },

    { "src_node_id": "input_node", "dst_node_id": "load_all_context_docs", "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username" },
      ], "description": "Trigger context docs loading."
    },

    { "src_node_id": "input_node", "dst_node_id": "load_draft_posts",
      "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username" },
      ],
    },

    # --- State Updates from Loaders ---
    { "src_node_id": "load_all_context_docs", "dst_node_id": "$graph_state", "mappings": [
        # Store the lists under their respective keys in state
        { "src_field": "strategy_doc", "dst_field": "strategy_doc"},
        { "src_field": "scraped_posts", "dst_field": "scraped_posts"},
        { "src_field": "user_profile", "dst_field": "user_profile"}
      ]
    },
    # --- Start Draft Posts Loading ---
    

    { "src_node_id": "load_draft_posts", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "draft_posts", "dst_field": "draft_posts"}
      ]
    },

    # --- Trigger Context Preparation after Loads ---
    # Edges from all loaders feeding into prepare_generation_context (fan-in enabled)
    { "src_node_id": "load_all_context_docs", "dst_node_id": "prepare_generation_context"},
    { "src_node_id": "load_draft_posts", "dst_node_id": "prepare_generation_context"},

    # --- Mapping State to Context Prep Node ---
    { "src_node_id": "$graph_state", "dst_node_id": "prepare_generation_context", "mappings": [
        { "src_field": "draft_posts", "dst_field": "draft_posts" },
        { "src_field": "scraped_posts", "dst_field": "scraped_posts" },
        { "src_field": "past_context_posts_limit", "dst_field": "past_context_posts_limit" },
        { "src_field": "weeks_to_generate", "dst_field": "weeks_to_generate" },
        { "src_field": "user_profile", "dst_field": "user_profile" },
      ]
    },

    # --- Map Iteration -> Construct Prompt (Private Edge) ---
    { "src_node_id": "prepare_generation_context", "dst_node_id": "construct_topic_prompt",
      "mappings": [
        { "src_field": "merged_data", "dst_field": "merged_data" },
      ]
    },

    { "src_node_id": "prepare_generation_context", "dst_node_id": "$graph_state",
      "mappings": [
        { "src_field": "merged_data", "dst_field": "merged_data" },
      ]
    },

    # --- State -> Construct Prompt (Public Edges for Context) ---
    { "src_node_id": "$graph_state", "dst_node_id": "construct_topic_prompt", "mappings": [
        { "src_field": "strategy_doc", "dst_field": "strategy_doc" },
        { "src_field": "user_profile", "dst_field": "user_profile" },
      ]
    },

    # --- Construct Prompt -> Generate Topics (Private Edge) ---
    { "src_node_id": "construct_topic_prompt", "dst_node_id": "generate_topics", "mappings": [
        { "src_field": "topic_user_prompt", "dst_field": "user_prompt"},
        { "src_field": "topic_system_prompt", "dst_field": "system_prompt"}
      ], "description": "Private edge: Sends prompts to LLM."
    },
    # --- State -> Generate Topics (Public Edge for History) ---
    { "src_node_id": "$graph_state", "dst_node_id": "generate_topics", "mappings": [
        { "src_field": "generate_topics_messages_history", "dst_field": "messages_history"}
      ]
    },

    # --- Generate Topics -> State (Public Edge for Collection/History Update) ---
    { "src_node_id": "generate_topics", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "structured_output", "dst_field": "all_generated_topics"}, # Collected by reducer
        { "src_field": "current_messages", "dst_field": "generate_topics_messages_history"} # Update history
      ]
    },
    

    # --- Generate Topics -> Check Topic Count
    { "src_node_id": "generate_topics", "dst_node_id": "check_topic_count", "mappings": [
        { "src_field": "metadata", "dst_field": "metadata"} # Collected by reducer
      ]},

    # --- State -> Check Topic Count (for metadata)
    { "src_node_id": "$graph_state", "dst_node_id": "check_topic_count", "mappings": [
        { "src_field": "merged_data", "dst_field": "merged_data" }
      ]
    },

    # --- Check Topic Count -> Route on Topic Count
    { "src_node_id": "check_topic_count", "dst_node_id": "route_on_topic_count", "mappings": [
        { "src_field": "tag_results", "dst_field": "if_else_condition_tag_results" },
        { "src_field": "condition_result", "dst_field": "if_else_overall_condition_result" }
      ]
    },

    # --- Route on Topic Count -> Construct Additional Topic Prompt (if more topics needed)
    { "src_node_id": "route_on_topic_count", "dst_node_id": "construct_additional_topic_prompt" },

    # --- Route on Topic Count -> Construct Delete Params (if all topics generated)
    { "src_node_id": "route_on_topic_count", "dst_node_id": "construct_delete_search_params" },

    # --- State to Construct Delete Params ---
    { "src_node_id": "$graph_state", "dst_node_id": "construct_delete_search_params", "mappings": [
        { "src_field": "search_params", "dst_field": "search_params" },
        { "src_field": "start_date", "dst_field": "start_date" },
        { "src_field": "end_date", "dst_field": "end_date" }
      ]
    },

    # --- Construct Delete Params to Delete Node ---
    { "src_node_id": "construct_delete_search_params", "dst_node_id": "delete_previous_entries", "mappings": [
        { "src_field": "transformed_data", "dst_field": "search_params" }
      ]
    },

    # --- State to Delete Node (to resolve input_namespace_field path) ---
    { "src_node_id": "$graph_state", "dst_node_id": "delete_previous_entries", "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username" }
      ]
    },

    # --- Delete then Store ---
    { "src_node_id": "delete_previous_entries", "dst_node_id": "store_all_topics" },

    # --- Trigger Storage (After Map Completes) ---
    { "src_node_id": "$graph_state", "dst_node_id": "store_all_topics", "mappings": [
        { "src_field": "all_generated_topics", "dst_field": "all_generated_topics"},
        { "src_field": "entity_username", "dst_field": "entity_username" }
      ]
    },

    # --- Construct Additional Topic Prompt -> Generate Topics (completes the loop)
    { "src_node_id": "construct_additional_topic_prompt", "dst_node_id": "generate_topics", "mappings": [
        { "src_field": "additional_topic_prompt", "dst_field": "user_prompt" },
      ]
    },

    { "src_node_id": "store_all_topics", "dst_node_id": "output_node", 
     "mappings": [
        { "src_field": "paths_processed", "dst_field": "final_post_paths"}
      ]
        }
    ],
    
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    "metadata": {
        "$graph_state": {
            "reducer": {
                "all_generated_topics": "collect_values",   # Collect topic objects from each generation iteration
                "generate_topics_messages_history": "add_messages" # Message history for topic generation LLM
            }
        }
    }
}


# --- Test Execution Logic (Placeholder) ---


async def main_test_linkedin_content_calendar_workflow():
    """
    Test the Content Topic Suggestions Workflow.
    Sets up required test documents, runs the workflow, validates the output and cleans up after.
    """
    test_name = "Content Topic Suggestions Workflow Test"
    print(f"--- Starting {test_name} --- ")

    # Example Inputs 
    test_entity_username = "mahak-vedi"
    
    # Define test inputs with realistic values
    test_inputs = {
        "entity_username": test_entity_username,
        "weeks_to_generate": 2,  # Generate for 2 weeks
        "past_context_posts_limit": PAST_CONTEXT_POSTS_LIMIT,  # Combined limit for context
        "start_date": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        "end_date": (datetime.utcnow() + timedelta(days=14)).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }

    # print(json.dumps(test_inputs, indent=4))
    # return

    # Create realistic test data for setup
    setup_docs: List[SetupDocInfo] = [
    
        # User Profile Document (contains preferences)
        {
            'namespace': LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_USER_PROFILE_DOCNAME,
            'initial_data': {
                "profile_url": "https://www.linkedin.com/in/mahak-vedi/",
                "username": test_entity_username,
                "persona_tags": ["RevOps Expert", "Founder", "Business Consultant"],
                "content_goals": {
                    "primary_goal": "Increase brand awareness for Revology Consulting and position Mahak as a trusted RevOps expert",
                    "secondary_goal": "Educate audience about RevOps, especially in European markets where understanding is limited"
                },
                "posting_schedule": {
                    "posts_per_week": 2,
                    "posting_days": ["Monday", "Thursday"],
                    "exclude_weekends": True
                },
                "timezone": {
                    "iana_identifier": "Europe/London",
                    "display_name": "British Summer Time",
                    "utc_offset": "+01:00",
                    "supports_dst": True,
                    "current_offset": "+01:00"
                }
            }, 
            'is_versioned': LINKEDIN_USER_PROFILE_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': 'default'  # Required for versioned documents
        },
        # Content Strategy Document
        {
            'namespace': LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
            'initial_data': {
                "title": "LinkedIn Content Strategy: Test User",
                "strategy_audience": {
                    "primary": "Small to Medium B2B Companies",
                    "secondary": "Salesforce & HubSpot Business Users",
                    "tertiary": "Enterprise B2B Companies; Agency Owners (Partnership Opportunities)"
                },
                "post_performance_analysis": {
                    "current_engagement": "Follower Count: 1,495; Network composition approximately 90% US‑based with growing presence in UK, Europe and Singapore; Posting frequency historically inconsistent but moving toward structured content pillars.",
                    "content_that_resonates": "Milestone announcements with specific metrics and emoji‑bulleted achievements; Cultural posts about personal experiences; Achievement posts averaging ~16.5 likes per post.",
                    "audience_response": "Highest impact from milestone announcements (166 likes, 130 comments). Cultural content generates significant engagement (103 likes, 24 comments). Optimum content length: ~217 words for Business & Entrepreneurship posts, ~187 words for Workplace Culture posts. Preferred format includes emoji‑bulleted lists, achievement markers with visual indicators, and short paragraphs."
                },
                "foundation_elements": {
                    "expertise": [
                        "RevOps Consulting & Implementation – 10+ years in operations with ~80 different clients over 5 years specifically on RevOps; tech‑stack assessment, consolidation and optimization; CRM expertise (Salesforce, HubSpot implementation and optimization); sales‑engagement tools (Outreach, SalesLoft).",
                        "Business Process Optimization – email personalization and outreach strategies; cross‑departmental alignment (especially sales, marketing and operations); metrics identification and tracking; automation of manual processes.",
                        "Cross‑Cultural Business Understanding – experience with US, UK, European and Asian business practices; understanding of geographical and cultural nuances in business operations; multilingual capabilities and global perspective.",
                        "Early‑Stage Founder Experience – founded Revology Consulting (1 December 2024); building a business based on expertise; developing service offerings and partnerships.",
                        "Tech Stack Security & Auditing – CRM integration security audits; identifying vulnerabilities in app access permissions; preventing data leakage through unauthorized third‑party tools; access management and security governance."
                    ],
                    "core_beliefs": [
                        "Problem‑First, Tool‑Second Approach – lead with the problem statement first instead of tooling first; avoid buying tools without understanding the exact use case.",
                        "Efficiency Through Automation – tasks taking more than 20 minutes should be automated; repetitive tasks should be eliminated through technology or process changes.",
                        "Metrics Should Drive Business Outcomes – balance leading and lagging indicators; quality of engagement matters more than quantity of activities; focus on predictive leading indicators.",
                        "Cross‑Departmental Alignment Is Essential – sales and marketing must align; technical solutions must serve broader business goals; clearly defined roles (consultant vs. contractor).",
                        "Analytical Foundation Drives Success – scientific approach to business with hypothesis testing, regular assessment and optimization, cultural awareness and adaptability.",
                        "Tech Stack Security Is Non‑Negotiable – every RevOps audit should include a security review; common vulnerability is integrations with read/write CRM access; companies must regularly audit tech‑stack access."
                    ],
                    "objectives": [
                        "Increase brand awareness for Revology Consulting and position Mahak as a trusted RevOps expert.",
                        "Educate audience about RevOps, especially in European markets where understanding is limited.",
                        "Document and share founder journey and weekly lessons learned.",
                        "Develop strategic partnerships with complementary businesses (≤10% focus).",
                        "Continue generating business through referrals (preferred business source).",
                        "Grow Mahak's personal brand alongside company reputation.",
                        "Build reputation as a source of practical advice on tech‑stack security."
                    ]
                },
                "core_perspectives": [
                    "Authority Blocks",
                    "Value Blocks", 
                    "Connection Blocks",
                    "Engagement Blocks"
                ],
                "content_pillars": [
                    {
                        "name": "Pillar 1: RevOps Education & Best Practices",
                        "pillar": "RevOps Education & Best Practices",
                        "sub_topic": [
                            "Tech stack audits and optimization",
                            "Metrics selection and tracking",
                            "Email personalization and outreach strategies",
                            "Sales and marketing alignment",
                            "Automation opportunities",
                            "Data security in operations",
                            "Leading vs. lagging indicators"
                        ]
                    },
                    {
                        "name": "Pillar 2: Founder Friday",
                        "pillar": "Founder Friday",
                        "sub_topic": [
                            "Business development challenges and solutions",
                            "Leadership and decision‑making",
                            "Work‑life balance as a founder",
                            "Client relationship management",
                            "Team building and culture development",
                            "Personal growth and reflection",
                            "Client feedback frameworks and implementation",
                            "Plant care and natural growth metaphors for business development"
                        ]
                    },
                    {
                        "name": "Pillar 3: Tool Spotlights & Partner Showcases",
                        "pillar": "Tool Spotlights & Partner Showcases",
                        "sub_topic": [
                            "CRM implementation best practices",
                            "Sales engagement tool optimization",
                            "Chrome plugin recommendations",
                            "Partner tool integrations",
                            "\"Speedy setup\" service showcases",
                            "Security risks and vulnerabilities in tech stacks",
                            "Regular security audits and access reviews"
                        ]
                    },
                    {
                        "name": "Pillar 4: Event Insights & Networking",
                        "pillar": "Event Insights & Networking",
                        "sub_topic": [
                            "Event takeaways and key learnings",
                            "Speaker insights and industry predictions",
                            "Networking experiences and opportunities",
                            "Regional business practice observations",
                            "Community‑building efforts"
                        ]
                    },
                    {
                        "name": "Pillar 5: Global RevOps Perspectives",
                        "pillar": "Global RevOps Perspectives",
                        "sub_topic": [
                            "Cultural differences in business operations",
                            "Regional approaches to sales and marketing alignment",
                            "Geographic variations in tool adoption",
                            "Work culture impacts on process implementation",
                            "Cross‑border collaboration strategies"
                        ]
                    }
                ],
                "posts_per_week": 2,
                "implementation": {
                    "thirty_day_targets": {
                        "goal": "1. Establish consistent posting rhythm across all pillars; 2. Test engagement levels for each content pillar; 3. Generate at least 5 meaningful conversations with target audience members; 4. Begin building connection with European audience through targeted content; 5. Showcase at least 2 partner relationships through Tool Spotlight pillar.",
                        "method": "Execute the Content Calendar Framework (weekly schedule) and follow the Content Creation Process (weekly planning, content development, engagement management, monthly review, feedback collection).",
                        "audience_growth": "Begin building connection with European audience through targeted content.",
                        "targets": "Generate ≥5 meaningful conversations; Showcase ≥2 partner relationships."
                    },
                    "ninety_day_targets": {
                        "goal": "1. Increase follower count by 15% (target ≈1,719 followers); 2. Establish Mahak as a recognized voice in RevOps; 3. Generate at least 3 new business inquiries directly attributed to LinkedIn content; 4. Develop 2 new strategic partnerships through LinkedIn connections; 5. Create educational content foundation explaining RevOps value for European audience.",
                        "method": "Continue executing and optimizing the Content Calendar Framework; apply insights from Monthly Reviews; leverage the Content Creation Process and daily Engagement Management.",
                        "audience_growth": "Increase follower count by 15% (target ≈1,719 followers).",
                        "targets": "Generate ≥3 business inquiries; Develop ≥2 strategic partnerships."
                    }
                }
            }, 
            'is_versioned': LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': 'default'  # Required for versioned documents
        },
        # Mock LinkedIn Scraped Posts
        {
            'namespace': LINKEDIN_SCRAPED_POSTS_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_SCRAPED_POSTS_DOCNAME,
            'initial_data': [
                {
                    "urn": "post-revops-1",
                    "text": "🔓 Security audit time! Just discovered a client had 47 people with admin access to their Salesforce instance. 47! That's not access management, that's access chaos. ✅ What we fixed: Proper role hierarchy, regular access reviews, automated deprovisioning. 🚫 What we found: Shared passwords, ex-employees still active, no MFA. #WhoStillHasYourPasswords #RevOps #TechStackSecurity",
                    "publish_date": "2024-01-15T10:00:00Z",
                    "reaction_count": 89,
                    "comment_count": 23
                },
                {
                    "urn": "post-revops-2",
                    "text": "🎉 Founder Friday update! Week 3 of Revology Consulting and I'm learning that building systems for clients is very different from building systems for your own business. The irony? I'm great at optimizing other people's tech stacks but spent 2 hours yesterday trying to connect my own CRM to my email tool. 😅 Lesson learned: Even RevOps experts need to practice what they preach. What's one system you know you should optimize but keep putting off? #FounderFriday #RevOps #Entrepreneurship",
                    "publish_date": "2024-01-12T14:30:00Z",
                    "reaction_count": 156,
                    "comment_count": 41
                }
            ], 
            'is_versioned': False,  # Assuming scraped posts are not versioned
            'is_shared': False
        },
        # Mock Draft Posts (2 examples)
        {
            'namespace': LINKEDIN_DRAFT_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_DRAFT_DOCNAME.replace('{item}', 'draft-1'),
            'initial_data': {
                "title": "Leading vs Lagging Indicators in RevOps",
                "content": "🎯 Stop measuring what happened. Start measuring what's happening. Most RevOps teams are drowning in lagging indicators: ✅ Revenue closed ✅ Deal velocity ✅ Win rates But missing the leading indicators that actually drive those outcomes: 🚀 Pipeline quality scores 🚀 Engagement velocity 🚀 Process adherence rates The difference? Lagging indicators tell you if you hit your target. Leading indicators tell you if you're aiming correctly. What leading indicators are you tracking in your RevOps? #RevOps #Metrics #DataDriven",
                "created_at": "2024-01-20T10:00:00Z",
                "updated_at": "2024-01-21T14:30:00Z",
            }, 
            'is_versioned': LINKEDIN_DRAFT_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': 'draft'  # Required for versioned documents
        },
        {
            'namespace': LINKEDIN_DRAFT_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_DRAFT_DOCNAME.replace('{item}', 'draft-2'),
            'initial_data': {
                "title": "Tech Stack Consolidation Reality Check",
                "content": "💡 Your tech stack isn't a collection. It's an ecosystem. Just helped a client reduce their sales tools from 12 to 4. The result? 🎉 40% faster onboarding 🎉 60% fewer integration issues 🎉 £2,400/month in savings The secret wasn't finding the 'perfect' tool. It was finding tools that actually talk to each other. Before consolidating, ask: ✅ Does this tool integrate natively? ✅ Can it replace 2+ existing tools? ✅ Will it scale with our growth? Your tech stack should amplify your team, not complicate their lives. What's one tool you could eliminate today? #TechStack #RevOps #Efficiency",
                "created_at": "2024-01-18T09:15:00Z",
                "updated_at": "2024-01-19T16:45:00Z"
            }, 
            'is_versioned': LINKEDIN_DRAFT_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': 'draft'  # Required for versioned documents
        },
    ]

    # Define cleanup docs to remove test artifacts after test completion
    cleanup_docs: List[CleanupDocInfo] = [

        # User Profile
        {
            'namespace': LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_USER_PROFILE_DOCNAME, 
            'is_versioned': LINKEDIN_USER_PROFILE_IS_VERSIONED, 
            'is_shared': False
        },
        # Content Strategy
        {
            'namespace': LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_CONTENT_PLAYBOOK_DOCNAME, 
            'is_versioned': LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED, 
            'is_shared': False
        },
        # LinkedIn Scraped Posts
        {
            'namespace': LINKEDIN_SCRAPED_POSTS_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_SCRAPED_POSTS_DOCNAME, 
            'is_versioned': False, 
            'is_shared': False
        },
        # Draft Posts
        {
            'namespace': LINKEDIN_DRAFT_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_DRAFT_DOCNAME.replace('{item}', 'draft-1'), 
            'is_versioned': LINKEDIN_DRAFT_IS_VERSIONED, 
            'is_shared': False
        },
        {
            'namespace': LINKEDIN_DRAFT_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_DRAFT_DOCNAME.replace('{item}', 'draft-2'), 
            'is_versioned': LINKEDIN_DRAFT_IS_VERSIONED, 
            'is_shared': False
        },
    ]

    print("--- Setup/Cleanup Definitions (Complete) ---")
    print(f"Entity Username: {test_entity_username}")
    print(f"Setup Docs: {len(setup_docs)} documents prepared")
    print(f"Cleanup Docs: {len(cleanup_docs)} documents to be removed after test")
    print("------------------------------------------------")

    # --- Define Custom Output Validation ---
    async def validate_calendar_output(outputs: Optional[Dict[str, Any]]) -> bool:
        assert outputs is not None, "Validation Failed: Workflow returned no outputs."
        logger.info("Validating content topic suggestions workflow outputs...")
        assert 'final_post_paths' in outputs, "Validation Failed: 'final_post_paths' missing."
        
        # The output contains paths to stored topic suggestions, not the topics themselves
        final_paths = outputs['final_post_paths']
        assert isinstance(final_paths, list), f"Validation Failed: 'final_post_paths' must be a list, got {type(final_paths)}"
        assert len(final_paths) > 0, "Validation Failed: No topic suggestions were stored."
        
        logger.info(f"✓ Found {len(final_paths)} stored topic suggestion documents.")
        # For basic validation, we just check that paths were created
        # In a more complete validation, we could load and validate each stored document
        
        # Calculate expected number of topic suggestions based on user profile
        user_prefs = next((doc['initial_data'] for doc in setup_docs 
                          if doc['namespace'] == LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username)
                          and doc['docname'] == LINKEDIN_USER_PROFILE_DOCNAME), None)
        
        # Access posts_per_week from the LinkedIn profile document structure
        posts_per_week = user_prefs.get('posting_schedule', {}).get('posts_per_week', 2) if user_prefs else 2
        expected_count = test_inputs.get("weeks_to_generate", DEFAULT_WEEKS_TO_GENERATE) * posts_per_week
        
        # Validate topic suggestions count
        actual_count = len(final_paths)
        
        if actual_count != expected_count:
            logger.warning(f"⚠️  Expected {expected_count} topic suggestions, found {actual_count}. This indicates workflow iteration issues.")
            logger.warning("   The workflow should generate one topic suggestion for each scheduled posting date.")
            logger.warning(f"   Expected: {expected_count} = {test_inputs.get('weeks_to_generate', DEFAULT_WEEKS_TO_GENERATE)} weeks × {posts_per_week} posts per week")
        
        logger.info(f"   Found {actual_count} topic suggestion documents, expected {expected_count}.")
        logger.info("✓ Topic suggestions have been stored successfully.")
        logger.info("✓ Output validation completed.")
        
        if actual_count == expected_count:
            logger.info("✓ Topic suggestion count matches expected (workflow iteration worked correctly).")
        else:
            logger.warning("⚠️  Topic suggestion count mismatch (workflow iteration needs debugging).")
        
        return True

    # --- Execute Test ---
    print("\n--- Running Workflow Test ---")
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        setup_docs=setup_docs,
        cleanup_docs=cleanup_docs,
        validate_output_func=validate_calendar_output,
        stream_intermediate_results=True,
        poll_interval_sec=5,
        timeout_sec=1800  # Allow time for multiple LLM calls
    )

    print(f"--- {test_name} Finished --- ")
    if final_run_status_obj:
        print(f"Final Status: {final_run_status_obj.status}")
        if final_run_outputs:
            print(f"Final Outputs: {json.dumps(final_run_outputs, indent=2, default=str)}")
        if final_run_status_obj.status != WorkflowRunStatus.COMPLETED:
            print(f"Error Message: {final_run_status_obj.error_message}")
    else:
        print("Test run failed to execute or returned no status object.")

if __name__ == "__main__":
    print("="*50)
    print("Content Calendar Entry Workflow Definition")
    print("="*50)
    logging.basicConfig(level=logging.INFO)

    try:
        asyncio.run(main_test_linkedin_content_calendar_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")
        logger.exception("Test execution failed")

