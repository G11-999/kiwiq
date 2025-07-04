"""
# Inputs to workflow:
1. Generate content briefs for next X weeks: (X) int input optional, default 1
2. Load list of customer context docs such as dna, strategy doc, scraped posts etc
3. Load multiple user draft posts using multiple loader node within posts namespace, load latest N posts (limit and sort by updated_at, DESC); also load user preferences from onboarding namespace, user preferences doc which has user's requested posting frequency / week
5. Merge both lists and limit the merged list limit using merge aggregate node; also in another operation: compute next X weeks (input) multiplied by user preferences post frequency / week (this is number of content briefs we have to generate)
6. construct prompt for first generation (includes system prompt) with all user docs and merged list in prompt
7. Generate 1 structured output content brief; it reads message history from LLM; this also has fields such as date / time of posting; it sends structured outputs to all_generated_briefs with reducer collect values
8. check IF else on iteration limit, if we have generated the required number of briefs
9. Router node to route to store node to store all generated briefs OR to construct prompt for additional briefs
10. Construct prompt for additional briefs constructs user prompt which just says generate 1 more additional briefs, ensure difference from previous briefs; it sends to same above LLM node; the LLM node loads message history from central state where it can see previous briefs and generate the next brief
10. (after iteration loop ends) store node stores draft briefs in separate paths using filename pattern with draft ID
11. send all briefs to output node

"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Union, ClassVar, Type
import json
from enum import Enum
from datetime import date, datetime

# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field

# Internal dependencies (assuming similar structure to example)
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
    # Content Strategy
    CONTENT_STRATEGY_DOCNAME,
    CONTENT_STRATEGY_NAMESPACE_TEMPLATE,
    CONTENT_STRATEGY_IS_VERSIONED,
    # LinkedIn scraping
    LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE,
    LINKEDIN_POST_DOCNAME,
    # User Preferences
    USER_PREFERENCES_DOCNAME,
    USER_PREFERENCES_NAMESPACE_TEMPLATE,
    USER_PREFERENCES_IS_VERSIONED,
    # Content Drafts
    CONTENT_DRAFT_DOCNAME,
    CONTENT_DRAFT_NAMESPACE_TEMPLATE,
    CONTENT_DRAFT_IS_VERSIONED,
    # Content Brief
    CONTENT_BRIEF_DOCNAME,
    CONTENT_BRIEF_NAMESPACE_TEMPLATE,
    CONTENT_BRIEF_IS_VERSIONED,
    CONTENT_BRIEF_DEFAULT_VERSION
)
from kiwi_client.workflows.llm_inputs.content_calendar_brief import BRIEF_USER_PROMPT_TEMPLATE, BRIEF_SYSTEM_PROMPT_TEMPLATE, BRIEF_LLM_OUTPUT_SCHEMA, BRIEF_ADDITIONAL_USER_PROMPT_TEMPLATE
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Workflow Configuration Constants ---

# LLM Configuration
LLM_PROVIDER = "anthropic"
GENERATION_MODEL = "claude-3-7-sonnet-20250219" # Latest Claude Sonnet model
LLM_TEMPERATURE = 1
LLM_MAX_TOKENS = 5000 # Adjust as needed for brief generation

# Workflow Defaults
DEFAULT_WEEKS_TO_GENERATE = 1
# DEFAULT_DRAFTS_LIMIT = 20 # Default number of latest drafts to load
# DEFAULT_SCRAPED_LIMIT = 20 # Default number of scraped posts to load
PAST_CONTEXT_POSTS_LIMIT = 10 # Limit the combined list of posts fed to the LLM

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
              "weeks_to_generate": { "type": "int", "required": False, "default": DEFAULT_WEEKS_TO_GENERATE, "description": f"Number of weeks ahead to generate briefs for (default: {DEFAULT_WEEKS_TO_GENERATE})." },
              "customer_context_doc_configs": {
                  "type": "list",
                  "required": True,
                  "description": "List of document identifiers (namespace/docname pairs) for customer context like DNA, strategy docs."
              },
              "past_context_posts_limit": { "type": "int", "required": False, "default": PAST_CONTEXT_POSTS_LIMIT, "description": f"Max number of combined posts (drafts + scraped) to use for context (default: {PAST_CONTEXT_POSTS_LIMIT})."},
              "entity_username": {"type": "str", "required": True},
          }
        }
        # Outputs: user_id, weeks_to_generate, customer_context_doc_configs, draft_posts_limit, scraped_posts_limit, past_context_posts_limit -> $graph_state
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
            "global_version_config": {
                # "version": "default"
            },
            "global_schema_options": {"load_schema": False},
        },
        
        # "dynamic_output_schema": { # Explicitly define expected output structure
        #     "fields": {
        #         # These keys MUST match the output_field_name in each config item
        #         "loaded_context_docs_list": {
        #             "type": "list", 
        #             "required": True,
        #             "description": "List containing the loaded content of each context document."
        #         },
        #         "loaded_scraped_posts": {
        #             "type": "list",
        #             "required": True,
        #             "description": "List of loaded scraped posts for the user."
        #         }
        #     }
        # }
        # Reads: context_and_scraped_configs (from input_node via edge mapping)
        # Writes: loaded_context_docs_list, loaded_scraped_posts -> $graph_state
    },

    # --- 3. Load Latest User Draft Posts ---
    "load_draft_posts": {
      "node_id": "load_draft_posts",
      "node_name": "load_multiple_customer_data", # Use the multi-loader node
      "node_config": {
          "namespace_pattern": CONTENT_DRAFT_NAMESPACE_TEMPLATE,
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
    #   "dynamic_output_schema": { # Define expected output
    #       "fields": {
    #           "draft_posts": { "type": "list", "required": True, "description": "List of loaded user draft posts." },
    #           "load_metadata": { "type": "dict", "required": True, "description": "Metadata about the loading operation."}
    #       }
    #   }
      # Reads: user_id (for filtering/permissions), draft_posts_limit (for config.limit) from state
      # Writes: draft_posts -> $graph_state
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
          # Operation 2: Compute Total Briefs Needed - weeks_to_generate * posts_per_week
          {
            "output_field_name": "total_briefs_needed",
            "select_paths": ["user_preferences.posting_schedule.posts_per_week"], # Inputs from state
             "merge_strategy": {
                #  "map_phase": {"unspecified_keys_strategy": "ignore"},
                #  "reduce_phase": {"default_reducer": ReducerType.REPLACE_RIGHT}, # Values overwrite
                 # Use transformation to calculate product of weeks and posts_per_week from user preferences
                 "post_merge_transformations": {
                      "total_briefs_needed": {
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
      #  "dynamic_input_schema": { # Define inputs from state
      #     "fields": {
      #         "loaded_draft_posts": { "type": "list", "required": True },
      #         "loaded_scraped_posts": { "type": "list", "required": True },
      #         "loaded_context_docs_list": { "type": "dict", "required": True, "description": "Dict containing loaded context docs, including user preferences with posting frequency"},
      #         "weeks_to_generate": { "type": "int", "required": True },
      #         "past_context_posts_limit": { "type": "int", "required": True }
      #     }
      #  }
      # Reads: loaded_draft_posts, loaded_scraped_posts, loaded_context_docs_list, weeks_to_generate, past_context_posts_limit (from state)
      # Writes: merged_data containing final_merged_posts_for_prompt and total_briefs_needed -> $graph_state
    },

    # --- 9. Construct Brief Prompt (Inside Map Branch) ---
    "construct_brief_prompt": {
      "node_id": "construct_brief_prompt",
      "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
          "brief_user_prompt": {
            "id": "brief_user_prompt",
            "template": BRIEF_USER_PROMPT_TEMPLATE,
            "variables": {
              "user_preferences": None, # Mapped from user_preferences
              "strategy_doc": None,  # Mapped from strategy_doc and user_dna
              "merged_posts": None,     # Mapped from merged_posts
              "user_dna": None,
              "user_timezone": None, # Mapped from user_preferences.timezone
              "current_datetime": "$current_date",
            },
            "construct_options": {
               "strategy_doc": "strategy_doc", # Map the number passed by the mapper
               "user_preferences": "user_preferences", # Map directly from user_preferences
               "merged_posts": "merged_data.final_merged_posts_for_prompt", # Map directly from merged_posts
               "user_dna": "user_dna",
               "user_timezone": "user_preferences.timezone" # Map timezone from nested user preferences
            }
          },
          "brief_system_prompt": {
            "id": "brief_system_prompt",
            "template": BRIEF_SYSTEM_PROMPT_TEMPLATE,
            "variables": { 
                "schema": json.dumps(BRIEF_LLM_OUTPUT_SCHEMA, indent=2), 
                "current_datetime": "$current_date" },
            "construct_options": {}
          }
        }
      }
      # Reads: merged_posts from prepare_generation_context, user_preferences/strategy_doc/user_dna from state (including timezone)
      # Writes: brief_user_prompt, brief_system_prompt for generate_brief node
    },

    # --- 10. Generate Brief (LLM - Inside Map Branch) ---
    "generate_brief": {
      "node_id": "generate_brief",
      "node_name": "llm",
      "node_config": {
          "llm_config": {
              "model_spec": {"provider": LLM_PROVIDER, "model": GENERATION_MODEL},
              "temperature": LLM_TEMPERATURE,
              "max_tokens": LLM_MAX_TOKENS
          },
          "output_schema": {
             "schema_definition": BRIEF_LLM_OUTPUT_SCHEMA,
             "convert_loaded_schema_to_pydantic": False
          },
      }
      # Reads (private): user_prompt, system_prompt
      # Writes: structured_output -> all_generated_briefs (state reducer)
    },

    # --- Check Brief Count Node (after first brief generation) ---
    "check_brief_count": {
      "node_id": "check_brief_count",
      "node_name": "if_else_condition",
      "node_config": {
        "tagged_conditions": [
          {
            "tag": "brief_count_check", 
            "condition_groups": [{
              "logical_operator": "and",
              "conditions": [{
                "field": "metadata.iteration_count",
                "operator": "less_than",
                "value_path": "merged_data.total_briefs_needed"
              }]
            }],
            "group_logical_operator": "and"
          }
        ],
        "branch_logic_operator": "and"
      }
      # Reads: brief_generation_metadata from state, total_briefs_needed from state
      # Writes: branch, tag_results, condition_result
    },

    # --- Router Based on Brief Count Check ---
    "route_on_brief_count": {
      "node_id": "route_on_brief_count",
      "node_name": "router_node",
      "node_config": {
        "choices": ["construct_additional_brief_prompt", "store_all_briefs"],
        "allow_multiple": False,
        "choices_with_conditions": [
          {
            "choice_id": "construct_additional_brief_prompt", # Continue generating more briefs
            "input_path": "if_else_condition_tag_results.brief_count_check",
            "target_value": True
          },
          {
            "choice_id": "store_all_briefs", # End loop and store briefs
            "input_path": "if_else_condition_tag_results.brief_count_check",
            "target_value": False,
          }
        ]
      }
      # Reads: if_else_condition_tag_results, iteration_branch_result from check_brief_count
      # Routes to: construct_additional_brief_prompt OR store_all_briefs
    },

    # --- Construct Additional Brief Prompt ---
    "construct_additional_brief_prompt": {
      "node_id": "construct_additional_brief_prompt",
      "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
          "additional_brief_prompt": {
            "id": "additional_brief_prompt",
            "template": BRIEF_ADDITIONAL_USER_PROMPT_TEMPLATE,
            # "variables": {
            #   "prev_briefs_summary": None
            # },
            # "construct_options": {
            #   "prev_briefs_summary": "all_generated_briefs" # From state
            # }
          },
        }
      }
      # Reads: all_generated_briefs from state
      # Writes: additional_brief_prompt, system_prompt
    },


    # --- 11. Store All Generated Briefs (After Map Completes) ---
    "store_all_briefs": {
      "node_id": "store_all_briefs",
      "node_name": "store_customer_data", # Store the final list
      "node_config": {
          "global_versioning": { "is_versioned": CONTENT_BRIEF_IS_VERSIONED, "operation": "upsert_versioned", "version": CONTENT_BRIEF_DEFAULT_VERSION },
          "global_is_shared": False,
          "store_configs": [
              {
                  # Store the entire list collected in the state
                  "input_field_path": "all_generated_briefs", # Mapped from state
                  "process_list_items_separately": True,
                  "target_path": {
                      "filename_config": {
                          "input_namespace_field_pattern": CONTENT_BRIEF_NAMESPACE_TEMPLATE, 
                          "input_namespace_field": "entity_username",
                          "static_docname": CONTENT_BRIEF_DOCNAME,
                      }
                  },
                  "generate_uuid": True,
              }
          ],
      },
      "dynamic_input_schema": { # Define expected final inputs
          "fields": {
              # "all_generated_briefs": { "type": "list", "required": True, "description": "The complete list of generated content briefs." },
          }
      }
      # Reads: all_generated_briefs, user_id (from state)
      # Writes: paths_processed
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
      # Reads: all_generated_briefs (mapped to final_briefs_list), paths_processed (mapped to save_confirmation)
    },

  },

  # --- Edges Defining Data Flow ---
  "edges": [
    # --- Input to State ---
    { "src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "weeks_to_generate", "dst_field": "weeks_to_generate" },
        { "src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs" },
        { "src_field": "past_context_posts_limit", "dst_field": "past_context_posts_limit" },
        { "src_field": "entity_username", "dst_field": "entity_username" },
      ]
    },
    
    

    { "src_node_id": "input_node", "dst_node_id": "load_all_context_docs", "mappings": [
        { "src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs" },
        { "src_field": "entity_username", "dst_field": "entity_username" },
      ], "description": "Trigger draft posts load."
    },

    { "src_node_id": "input_node", "dst_node_id": "load_draft_posts",
      "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username" },
      ],
    },

    # --- State Updates from Loaders ---
    { "src_node_id": "load_all_context_docs", "dst_node_id": "$graph_state", "mappings": [
        # Store the lists under their respective keys in state
        { "src_field": "user_dna", "dst_field": "user_dna"},
        { "src_field": "user_preferences", "dst_field": "user_preferences"},
        { "src_field": "strategy_doc", "dst_field": "strategy_doc"},
        { "src_field": "scraped_posts", "dst_field": "scraped_posts"}
      ]
    },
    # --- Start Draft Posts Loading ---
    

    { "src_node_id": "load_draft_posts", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "draft_posts", "dst_field": "draft_posts"}
      ]
    },

    # --- Trigger Context Preparation after Loads ---
    # Edges from all loaders feeding into prepare_generation_context (fan-in enabled)





    # --- Trigger Context Preparation after Loads ---
    # Edges from all loaders feeding into prepare_generation_context (fan-in enabled)
    { "src_node_id": "load_all_context_docs", "dst_node_id": "prepare_generation_context"},
    { "src_node_id": "load_draft_posts", "dst_node_id": "prepare_generation_context"},

    # --- Mapping State to Context Prep Node ---
    { "src_node_id": "$graph_state", "dst_node_id": "prepare_generation_context", "mappings": [
        { "src_field": "draft_posts", "dst_field": "draft_posts" },
        { "src_field": "scraped_posts", "dst_field": "scraped_posts" },
        { "src_field": "past_context_posts_limit", "dst_field": "past_context_posts_limit" },
        { "src_field": "user_preferences", "dst_field": "user_preferences"},
        { "src_field": "weeks_to_generate", "dst_field": "weeks_to_generate" },
      ]
    },

    # --- State Update from Context Prep ---
    # { "src_node_id": "prepare_generation_context", "dst_node_id": "$graph_state", "mappings": [
    #     # Map relevant outputs to state
    #     { "src_field": "merged_data", "dst_field": "merged_posts" },
    #   ]
    # },



    # --- Map Iteration -> Construct Prompt (Private Edge) ---
    { "src_node_id": "prepare_generation_context", "dst_node_id": "construct_brief_prompt",
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
    { "src_node_id": "$graph_state", "dst_node_id": "construct_brief_prompt", "mappings": [
        { "src_field": "strategy_doc", "dst_field": "strategy_doc" },
        { "src_field": "user_dna", "dst_field": "user_dna"},
        { "src_field": "user_preferences", "dst_field": "user_preferences"},
      ]
    },

    # --- Construct Prompt -> Generate Brief (Private Edge) ---
    { "src_node_id": "construct_brief_prompt", "dst_node_id": "generate_brief", "mappings": [
        { "src_field": "brief_user_prompt", "dst_field": "user_prompt"},
        { "src_field": "brief_system_prompt", "dst_field": "system_prompt"}
      ], "description": "Private edge: Sends prompts to LLM."
    },
    # --- State -> Generate Brief (Public Edge for History) ---
    { "src_node_id": "$graph_state", "dst_node_id": "generate_brief", "mappings": [
        { "src_field": "generate_brief_messages_history", "dst_field": "messages_history"}
      ]
    },

    # --- Generate Brief -> State (Public Edge for Collection/History Update) ---
    { "src_node_id": "generate_brief", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "structured_output", "dst_field": "all_generated_briefs"}, # Collected by reducer
        { "src_field": "current_messages", "dst_field": "generate_brief_messages_history"} # Update history
      ]
    },
    

    # --- Generate Brief -> Check Brief Count
    { "src_node_id": "generate_brief", "dst_node_id": "check_brief_count", "mappings": [
        { "src_field": "metadata", "dst_field": "metadata"} # Collected by reducer
      ]},

    # --- State -> Check Brief Count (for metadata)
    { "src_node_id": "$graph_state", "dst_node_id": "check_brief_count", "mappings": [
        { "src_field": "merged_data", "dst_field": "merged_data" }
      ]
    },

    # --- Check Brief Count -> Route on Brief Count
    { "src_node_id": "check_brief_count", "dst_node_id": "route_on_brief_count", "mappings": [
        { "src_field": "tag_results", "dst_field": "if_else_condition_tag_results" },
        { "src_field": "condition_result", "dst_field": "if_else_overall_condition_result" }
      ]
    },

    # --- Route on Brief Count -> Construct Additional Brief Prompt (if more briefs needed)
    { "src_node_id": "route_on_brief_count", "dst_node_id": "construct_additional_brief_prompt" },

    # --- Route on Brief Count -> Store All Briefs (if all briefs generated)
    { "src_node_id": "route_on_brief_count", "dst_node_id": "store_all_briefs" },

     # --- Trigger Storage (After Map Completes) ---
    { "src_node_id": "$graph_state", "dst_node_id": "store_all_briefs", "mappings": [
        { "src_field": "all_generated_briefs", "dst_field": "all_generated_briefs"},
        { "src_field": "entity_username", "dst_field": "entity_username" }
      ]
    },


    # # --- State -> Construct Additional Brief
    # { "src_node_id": "$graph_state", "dst_node_id": "construct_additional_brief_prompt", "mappings": [
    #     { "src_field": "all_generated_briefs", "dst_field": "all_generated_briefs" }
    #   ]
    # },

    # --- Construct Additional Brief -> Generate Brief (completes the loop)
    { "src_node_id": "construct_additional_brief_prompt", "dst_node_id": "generate_brief", "mappings": [
        { "src_field": "additional_brief_prompt", "dst_field": "user_prompt" },
      ]
    },

    { "src_node_id": "store_all_briefs", "dst_node_id": "output_node", 
     "mappings": [
        { "src_field": "paths_processed", "dst_field": "brief_paths_processed"}
      ]
     },

    # --- State -> Output ---
    { "src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
        { "src_field": "all_generated_briefs", "dst_field": "final_briefs_list"}
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
          "all_generated_briefs": "collect_values",   # Collect brief objects from each generation iteration
          "generate_brief_messages_history": "add_messages" # Message history for brief generation LLM
          # "brief_generation_metadata": {
          #   "reducer_type": "replace", 
          #   "transform": {
          #     "iteration_count": {
          #       "expression": "value.get('iteration_count', 0) + 1"
          #     }
          #   }
          # }
        }
      }
  }
}


# --- Test Execution Logic (Placeholder) ---


async def main_test_content_calendar_workflow():
    """
    Test the Content Calendar Entry Workflow.
    Sets up required test documents, runs the workflow, validates the output and cleans up after.
    """
    test_name = "Content Calendar Entry Workflow Test"
    print(f"--- Starting {test_name} --- ")

    # Example Inputs 
    test_entity_username = "mahak-vedi"
    test_context_docs = [
        {
            "filename_config": {
                "input_namespace_field_pattern": USER_DNA_NAMESPACE_TEMPLATE, 
                "input_namespace_field": "entity_username",
                "static_docname": USER_DNA_DOCNAME,
            },
            "output_field_name": "user_dna"  # Field where the loaded DNA doc will be stored
        },
        {
            "filename_config": {
                 "input_namespace_field_pattern": USER_PREFERENCES_NAMESPACE_TEMPLATE, 
                  "input_namespace_field": "entity_username",
                  "static_docname": USER_PREFERENCES_DOCNAME,
            },
            "output_field_name": "user_preferences"  # Field for user preferences
        },
        {
            "filename_config": {
                "input_namespace_field_pattern": CONTENT_STRATEGY_NAMESPACE_TEMPLATE, 
                "input_namespace_field": "entity_username",
                # "static_namespace": CONTENT_STRATEGY_NAMESPACE_TEMPLATE.format(item=test_entity_username),
                "static_docname": CONTENT_STRATEGY_DOCNAME,
                
            },
            "output_field_name": "strategy_doc"  # Field for strategy document
        },
        {
            "filename_config": {
                "input_namespace_field_pattern": LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE, 
                "input_namespace_field": "entity_username",
                "static_docname": LINKEDIN_POST_DOCNAME,
            },
            "output_field_name": "scraped_posts" # Expect output containing LinkedIn posts
        },
    ]
    
    # Define test inputs with realistic values
    test_inputs = {
        "entity_username": test_entity_username,
        "weeks_to_generate": 1,  # Generate for 1 week
        "customer_context_doc_configs": test_context_docs,
        "past_context_posts_limit": PAST_CONTEXT_POSTS_LIMIT  # Combined limit for context
    }

    # print(json.dumps(test_inputs, indent=4))
    # return

    # Create realistic test data for setup
    setup_docs: List[SetupDocInfo] = [
        # User DNA Document
        {
            'namespace': USER_DNA_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': USER_DNA_DOCNAME,
            'initial_data': {
                "professional_identity": {
                    "full_name": "Test User",
                    "job_title": "Founder and CEO",
                    "industry_sector": "Business Consulting and Services (RevOps/Sales Operations)",
                    "company_name": "Revology Consulting",
                    "company_size": "Small (early‑stage startup)",
                    "years_of_experience": 10,
                    "professional_certifications": ["Salesforce Certified Administrator", "HubSpot Revenue Operations Certification"],
                    "areas_of_expertise": [
                        "RevOps consulting and implementation",
                        "Sales operations strategy and enablement",
                        "Tech stack assessment, consolidation, and optimization",
                        "CRM expertise (Salesforce, HubSpot implementation and optimization)",
                        "Sales engagement tools (Outreach, SalesLoft)",
                        "Business process optimization and automation",
                        "Metrics identification and tracking",
                        "Email personalization and outreach strategies",
                        "Cross‑departmental alignment (sales and marketing)",
                        "Tech stack security auditing and vulnerability assessment",
                        "Leading vs. lagging indicator frameworks for business measurement"
                    ],
                    "career_milestones": [
                        "Founded Revology Consulting (December 2024)",
                        "Senior RevOps Consultant at Skaled Consulting (2021‑Present)",
                        "Worked with ~80 different clients over 5 years on RevOps",
                        "Worked with notable companies including OpenAI, UiPath, SurveyMonkey",
                        "Roles at Groupon, Microsoft, Verizon, Zebra Technologies",
                        "Scientific background with transition to operations roles"
                    ],
                    "professional_bio": "Test User is the Founder and CEO of Revology Consulting, a firm specializing in helping companies streamline their revenue operations. With an analytical foundation (Master's in Genetics and Genetic Manipulation) and over a decade in operations roles, she helps businesses optimize their tech stack, sales processes, and revenue operations to drive efficiency and growth. Her expertise spans multiple industries, company sizes, and global markets, giving her unique insights into operational excellence across diverse business contexts."
                },
                "linkedin_profile_analysis": {
                    "follower_count": 1495,
                    "connection_count": 2100,
                    "profile_headline_analysis": "All things RevOps | Founder & CEO | Simplifying Processes and Demystifying Tech",
                    "about_section_summary": "Focuses on expertise in revenue operations, helping companies integrate and optimize tech stacks, sales processes, and enablement strategies to drive efficiency and scalability. Emphasizes enhancing workflows, building scalable systems, and driving measurable results with focus on reducing inefficiencies and creating data‑driven processes.",
                    "engagement_metrics": {
                        "average_likes_per_post": 76,
                        "average_comments_per_post": 40,
                        "average_shares_per_post": 8
                    },
                    "top_performing_content_pillars": [
                        "Business & Entrepreneurship",
                        "Workplace Culture & Employee Experience",
                        "Community & Networking"
                    ],
                    "content_posting_frequency": "Inconsistent historically; moving forward: RevOps education/brand awareness, weekly Founder Friday, tool spotlights, and event recaps (2 per week)",
                    "content_types_used": [
                        "Text posts with emoji bullets",
                        "Milestone updates with specific metrics",
                        "Personal narratives with reflections",
                        "Lists with emoji markers",
                        "Short, direct posts for simple updates",
                        "Security‑focused content with lock emojis (🔓)",
                        "Contrast formats highlighting what works vs. what doesn't",
                        "Relatable analogies connecting with everyday experiences"
                    ],
                    "network_composition": [
                        "Predominantly US‑based connections (~90%)",
                        "Connections in UK, Europe, and globally (including Singapore)",
                        "Mix of B2B and B2C companies",
                        "Focus on companies using Salesforce and HubSpot",
                        "Strong ties to RevOps, sales operations, and SaaS sectors",
                        "Growing network of agency owners"
                    ]
                },
                "brand_voice_and_style": {
                    "communication_style": "Straightforward, authoritative yet approachable",
                    "tone_preferences": [
                        "Enthusiastic",
                        "Confident but not overly technical",
                        "Occasionally vulnerable/authentic",
                        "Celebratory for achievements",
                        "Reflective when sharing lessons",
                        "Definitive on security vulnerabilities",
                        "Direct in content body"
                    ],
                    "vocabulary_level": "Professional but accessible; uses industry‑specific terms without excessive jargon; occasionally employs scientific references, relatable analogies, and humor with cultural references.",
                    "sentence_structure_preferences": "Mix of short declarative statements for impact and longer explanatory sentences for complex topics; questions mainly used as CTAs at post ends; bulleted lists; preference for direct statements in body.",
                    "content_format_preferences": [
                        "Emoji‑bulleted lists",
                        "Achievement markers with visual indicators",
                        "Short paragraphs (2‑3 sentences)",
                        "Clear headline formats for announcements",
                        "\"Statement‑Problem‑Solution\" advice structure",
                        "Contrasting sections with emojis (✅ vs. 🚫)",
                        "Leading vs. lagging indicator differentiation"
                    ],
                    "emoji_usage": "Frequent emoji use, especially in milestone posts (average 14.3 per post in Business & Entrepreneurship); common emojis include 🎉, ✅, 🚀, ❤️, 🔓; 4‑14 emojis per post depending on content.",
                    "hashtag_usage": "Moderate; placed at post ends; present in 55‑62% of posts; uses relevant industry tags; strong preference for #WhoStillHasYourPasswords in security content.",
                    "storytelling_approach": "Personal founder narratives with practical takeaways; celebratory announcements; personal declarations for community posts; combines vulnerability with expertise; uses plant care and scientific metaphors for business."
                },
                "content_strategy_goals": {
                    "primary_goal": "Increase brand awareness for Revology Consulting and position Mahak as a trusted RevOps expert",
                    "secondary_goals": [
                        "Educate audience about RevOps, especially in Europe",
                        "Document and share founder journey and weekly lessons",
                        "Develop strategic partnerships with complementary businesses",
                        "Generate business through referrals",
                        "Grow Mahak's personal brand",
                        "Establish reputation for tech stack security expertise"
                    ],
                    "target_audience_demographics": "SMBs (<5 M USD revenue, <200 employees) primarily B2B; similar B2C companies; users of Salesforce and HubSpot; agency owners",
                    "ideal_reader_personas": [
                        "SMB decision‑makers needing RevOps expertise",
                        "Operations leaders optimizing tech stack",
                        "Founders focused on operational excellence",
                        "Sales and marketing leaders seeking alignment"
                    ],
                    "audience_pain_points": [
                        "Poor tech stack optimization",
                        "Bad email personalization practices",
                        "Measuring wrong metrics",
                        "Lack of sales and marketing alignment",
                        "Excessive manual processes",
                        "Security risks from unmonitored tool access",
                        "Over‑focus on lagging indicators",
                        "Neglected security risks in tech stack integrations",
                        "Unmonitored tool access security vulnerabilities",
                        "Customer engagement patterns not tracked properly",
                        "Using insecure platforms for sensitive data"
                    ],
                    "value_proposition_to_audience": "Expertise in identifying and solving operational inefficiencies; tech stack optimization to reduce redundancy and cost; proper metrics selection; task automation; global perspective; practical advice; security auditing expertise; frameworks for leading indicators.",
                    "call_to_action_preferences": [
                        "Direct engagement in comments",
                        "Open invitations for connections",
                        "Occasional discussion questions"
                    ],
                    "content_pillar_themes": [
                        "RevOps education and best practices",
                        "Founder journey insights (Founder Friday)",
                        "Tool spotlights and collaborations",
                        "Event recaps and insights",
                        "Tech stack security and vulnerability assessments",
                        "Leading vs. lagging indicator frameworks"
                    ],
                    "topics_of_interest": [
                        "Tech stack audits and optimization",
                        "Metrics selection and tracking",
                        "Email personalization strategies",
                        "Sales and marketing alignment challenges and solutions",
                        "Automation opportunities and implementation",
                        "Data security in operations",
                        "Tool comparison and selection criteria",
                        "Revology product developments (speedy setup)",
                        "Tech stack security vulnerabilities",
                        "Integration security risks with CRMs",
                        "Leading vs. lagging indicators contrast",
                        "Plant care metaphors for business growth",
                        "Client feedback collection and implementation"
                    ],
                    "topics_to_avoid": [
                        "Overly technical jargon without context",
                        "Controversial political topics",
                        "Negative commentary about specific competitors",
                        "Personal financial information",
                        "Unsubstantiated claims about tools or services"
                    ]
                },
                "personal_context": {
                    "personal_values": [
                        "Efficiency and optimization",
                        "Authenticity and cultural pride",
                        "Cross‑cultural understanding and global perspective",
                        "Analytical thinking",
                        "Continuous learning and knowledge sharing",
                        "Continuous improvement through feedback",
                        "Growth through consistency and patience"
                    ],
                    "professional_mission_statement": "Helping companies streamline revenue operations by integrating and optimizing tech stack and processes to reduce inefficiencies, empower teams, and create data‑driven processes that support long‑term growth.",
                    "content_creation_challenges": [
                        "Consistency and structure in content",
                        "Strategic approach to content pillars",
                        "Time management balancing content creation with running business",
                        "Desire for specific, detailed feedback on content",
                        "Rapid implementation of constructive feedback",
                        "Appreciation for high ratings with actionable feedback"
                    ],
                    "personal_story_elements_for_content": [
                        "Cultural background and international perspective",
                        "Scientific/analytical foundation (Master's in Genetics)",
                        "Global experience with clients across regions",
                        "Early‑stage founder experiences and challenges",
                        "Plant care and gardening metaphors for business growth",
                        "Scientific method applied to client feedback",
                        "Collecting and implementing feedback via Typeform",
                        "Dropping \"golden nuggets\" during focused training"
                    ],
                    "notable_life_experiences": [
                        "Transition from science to operations roles",
                        "Working across multiple countries and cultures",
                        "Observations of regional work culture differences",
                        "Recent marriage and related cultural traditions",
                        "Connection to plant care and growth enthusiasm"
                    ],
                    "inspirations_and_influences": [
                        "Seth Godin's marketing philosophy",
                        "Scientific methodology applied to business",
                        "Cross-cultural business practices",
                        "Nature and growth metaphors"
                    ],
                    "books_resources_they_reference": [
                        "The Lean Startup by Eric Ries",
                        "Predictably Irrational by Dan Ariely",
                        "The Hard Thing About Hard Things by Ben Horowitz",
                        "Various RevOps and sales operations publications"
                    ],
                    "quotes_they_resonate_with": [
                        "\"Measure twice, cut once\" - applied to RevOps strategy",
                        "\"The best time to plant a tree was 20 years ago. The second best time is now.\"",
                        "\"Culture eats strategy for breakfast\" - Peter Drucker"
                    ]
                },
                "analytics_insights": {
                    "optimal_content_length": "Business & Entrepreneurship ~217 words; Community & Networking ~112; Professional Growth ~127; Sales & Marketing ~87; Workplace Culture ~187; hooks 5–8 words for impact",
                    "audience_geographic_distribution": "~90% US‑based, some UK presence, international reach including Singapore",
                    "engagement_time_patterns": "Peak engagement Tuesday-Thursday 9-11 AM EST and 2-4 PM EST; Friday posts perform well for founder journey content",
                    "keyword_performance_analysis": "Engagement drivers: \"community\", \"culture\", \"modern outbound\", \"RevOps\", \"Revology Consulting\", security‑related terms, #WhoStillHasYourPasswords, leading/lagging indicators terminology",
                    "competitor_benchmarking": "Higher engagement than average RevOps consultants due to personal storytelling approach; security focus differentiates from typical RevOps content",
                    "growth_rate_metrics": "7 clients, 3 partnerships, £77,100 closed deals within first 3 months"
                },
                "success_metrics": {
                    "content_performance_kpis": [
                        "Engagement metrics by post type",
                        "Follower growth",
                        "Brand recognition for Revology",
                        "Content quality feedback ratings (9–10/10)"
                    ],
                    "engagement_quality_metrics": [
                        "Comments and meaningful conversations",
                        "Quality engagement from target audience",
                        "Styling preference feedback"
                    ],
                    "conversion_goals": [
                        "Generate new business through referrals",
                        "Establish and grow partnerships",
                        "Drive awareness of Revology's services"
                    ],
                    "brand_perception_goals": [
                        "Establish Revology's market reputation",
                        "Position Mahak as a trusted RevOps expert",
                        "Increase knowledge of RevOps in Europe",
                        "Authoritative yet approachable brand",
                        "Reputation for tech stack security expertise"
                    ],
                    "timeline_for_expected_results": "3–6 months",
                    "benchmarking_standards": "Previous post performance and business growth metrics serve as baseline; content rated on 10‑point feedback scale"
                }
            }, 
            'is_versioned': USER_DNA_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': 'default'
        },
        # User Preferences Document
        {
            'namespace': USER_PREFERENCES_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': USER_PREFERENCES_DOCNAME,
            'initial_data': {
                "goals_answers": [
                    {
                        "question": "What is your primary goal for LinkedIn content?",
                        "answer": "Increase brand awareness for Revology Consulting and position Mahak as a trusted RevOps expert."
                    },
                    {
                        "question": "What secondary goals do you want to achieve?",
                        "answer": "Educate audience about RevOps, document founder journey, develop strategic partnerships, generate referral business, grow personal brand, establish tech stack security expertise."
                    },
                    {
                        "question": "What does success look like for your content strategy?",
                        "answer": "Consistent engagement from target audience, 3-5 new business inquiries per month, growing partnerships, and establishing thought leadership in RevOps space."
                    }
                ],
                "audience": {
                    "segments": [
                        {
                            "audience_type": "SMB Decision‑Makers",
                            "description": "Leaders in small‑to‑medium B2B companies (<$5 M revenue, <200 employees) needing RevOps expertise."
                        },
                        {
                            "audience_type": "Salesforce & HubSpot Users",
                            "description": "Operations and sales teams using Salesforce or HubSpot seeking optimization and security guidance."
                        },
                        {
                            "audience_type": "Agency Owners & Partners",
                            "description": "Agency founders interested in RevOps partnerships, tool spotlights, and collaboration opportunities."
                        }
                    ]
                },
                "posting_schedule": {
                    "posts_per_week": 2,
                    "posting_days": ["TUE", "FRI"],
                    "exclude_weekends": True
                },
                "timezone": {
                    "iana_identifier": "Europe/London",
                    "display_name": "British Time - London", 
                    "utc_offset": "+00:00",
                    "supports_dst": True,
                    "current_offset": "+01:00"
                }
            }, 
            'is_versioned': USER_PREFERENCES_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': 'default'
        },
        # Content Strategy Document
        {
            'namespace': CONTENT_STRATEGY_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': CONTENT_STRATEGY_DOCNAME,
            'initial_data': {
                "title": "LinkedIn Content Strategy: Test User - RevOps Authority",
                "target_audience": {
                    "primary": "Small to Medium B2B Companies (<$5M revenue, <200 employees)",
                    "secondary": "Salesforce & HubSpot Business Users and Operations Teams",
                    "tertiary": "Agency Owners and RevOps Professionals seeking partnerships"
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
                    "Authority Blocks - Establishing expertise through specific examples and metrics",
                    "Value Blocks - Practical frameworks and actionable advice", 
                    "Connection Blocks - Personal stories and relatable experiences",
                    "Engagement Blocks - Questions and conversation starters that drive interaction"
                ],
                "content_pillars": [
                    {
                        "name": "RevOps Education & Best Practices",
                        "theme": "Educational content about revenue operations",
                        "sub_themes": [
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
                        "name": "Founder Friday",
                        "theme": "Weekly founder journey insights",
                        "sub_themes": [
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
                        "name": "Tool Spotlights & Security Audits",
                        "theme": "Tool reviews and security insights",
                        "sub_themes": [
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
                        "name": "Event Insights & Networking",
                        "theme": "Industry events and networking experiences",
                        "sub_themes": [
                            "Event takeaways and key learnings",
                            "Speaker insights and industry predictions",
                            "Networking experiences and opportunities",
                            "Regional business practice observations",
                            "Community‑building efforts"
                        ]
                    },
                    {
                        "name": "Global RevOps Perspectives",
                        "theme": "Cross-cultural business insights",
                        "sub_themes": [
                            "Cultural differences in business operations",
                            "Regional approaches to sales and marketing alignment",
                            "Geographic variations in tool adoption",
                            "Work culture impacts on process implementation",
                            "Cross‑border collaboration strategies"
                        ]
                    }
                ],
                "post_performance_analysis": {
                    "current_engagement": "Follower Count: 1,495; Average likes per post: 76; Average comments per post: 40; Network composition approximately 90% US‑based with growing presence in UK, Europe and Singapore; Posting frequency historically inconsistent but moving toward structured content pillars.",
                    "content_that_resonates": "Milestone announcements with specific metrics and emoji‑bulleted achievements; Cultural posts about personal experiences; Security-focused content with practical examples; Achievement posts averaging ~16.5 likes per post.",
                    "audience_response": "Highest impact from milestone announcements (166 likes, 130 comments). Cultural content generates significant engagement (103 likes, 24 comments). Security posts perform well with technical audience. Optimum content length: ~217 words for Business & Entrepreneurship posts, ~187 words for Workplace Culture posts. Preferred format includes emoji‑bulleted lists, achievement markers with visual indicators, and short paragraphs."
                },
                "implementation": {
                    "thirty_day_targets": {
                        "goal": "Establish consistent posting rhythm across all pillars and test engagement levels for each content pillar",
                        "method": "Execute the Content Calendar Framework with weekly schedule and follow structured content creation process",
                        "targets": "Generate ≥5 meaningful conversations with target audience; Showcase ≥2 partner relationships; Maintain 2 posts per week schedule"
                    },
                    "ninety_day_targets": {
                        "goal": "Increase follower count by 15% and establish Mahak as recognized voice in RevOps while generating business inquiries",
                        "method": "Continue executing and optimizing Content Calendar Framework; apply insights from monthly reviews; leverage structured engagement management",
                        "targets": "Reach ≈1,719 followers (15% growth); Generate ≥3 business inquiries; Develop ≥2 strategic partnerships; Create educational content foundation for European audience"
                    }
                }
            }, 
            'is_versioned': CONTENT_STRATEGY_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': 'default'
        },
        # Mock LinkedIn Scraped Posts
        {
            'namespace': LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_POST_DOCNAME,
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
                },
                {
                    "urn": "post-revops-3",
                    "text": "🎯 Stop measuring what happened. Start measuring what's happening. Most RevOps teams are drowning in lagging indicators: ✅ Revenue closed ✅ Deal velocity ✅ Win rates But missing the leading indicators that actually drive those outcomes: 🚀 Pipeline quality scores 🚀 Engagement velocity 🚀 Process adherence rates The difference? Lagging indicators tell you if you hit your target. Leading indicators tell you if you're aiming correctly. What leading indicators are you tracking in your RevOps? #RevOps #Metrics #DataDriven",
                    "publish_date": "2024-01-10T09:15:00Z",
                    "reaction_count": 134,
                    "comment_count": 52
                },
                {
                    "urn": "post-revops-4",
                    "text": "💡 Your tech stack isn't a collection. It's an ecosystem. Just helped a client reduce their sales tools from 12 to 4. The result? 🎉 40% faster onboarding 🎉 60% fewer integration issues 🎉 £2,400/month in savings The secret wasn't finding the 'perfect' tool. It was finding tools that actually talk to each other. Before consolidating, ask: ✅ Does this tool integrate natively? ✅ Can it replace 2+ existing tools? ✅ Will it scale with our growth? Your tech stack should amplify your team, not complicate their lives. What's one tool you could eliminate today?",
                    "publish_date": "2024-01-08T11:45:00Z",
                    "reaction_count": 98,
                    "comment_count": 31
                }
            ], 
            'is_versioned': False,
            'is_shared': False
        },
        # Mock Draft Posts (2 examples)
        {
            'namespace': CONTENT_DRAFT_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': CONTENT_DRAFT_DOCNAME.replace('{_uuid_}', 'draft-1'),
            'initial_data': {
                "status": "draft",
                "scheduled_date": "2024-01-25T10:00:00Z",
                "post_text": "🎯 Stop measuring what happened. Start measuring what's happening. Most RevOps teams are drowning in lagging indicators: ✅ Revenue closed ✅ Deal velocity ✅ Win rates But missing the leading indicators that actually drive those outcomes: 🚀 Pipeline quality scores 🚀 Engagement velocity 🚀 Process adherence rates The difference? Lagging indicators tell you if you hit your target. Leading indicators tell you if you're aiming correctly. What leading indicators are you tracking in your RevOps?",
                "hashtags": ["#RevOps", "#Metrics", "#DataDriven"]
            }, 
            'is_versioned': CONTENT_DRAFT_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': 'draft'
        },
        {
            'namespace': CONTENT_DRAFT_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': CONTENT_DRAFT_DOCNAME.replace('{_uuid_}', 'draft-2'),
            'initial_data': {
                "status": "draft",
                "scheduled_date": "2024-01-23T14:30:00Z",
                "post_text": "💡 Your tech stack isn't a collection. It's an ecosystem. Just helped a client reduce their sales tools from 12 to 4. The result? 🎉 40% faster onboarding 🎉 60% fewer integration issues 🎉 £2,400/month in savings The secret wasn't finding the 'perfect' tool. It was finding tools that actually talk to each other. Before consolidating, ask: ✅ Does this tool integrate natively? ✅ Can it replace 2+ existing tools? ✅ Will it scale with our growth? Your tech stack should amplify your team, not complicate their lives. What's one tool you could eliminate today?",
                "hashtags": ["#TechStack", "#RevOps", "#Efficiency"]
            }, 
            'is_versioned': CONTENT_DRAFT_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': 'draft'
        },
        # Core Beliefs Document
        {
            'namespace': f"user_data_beliefs_{test_entity_username}",
            'docname': "core_beliefs.json",
            'initial_data': {
                "beliefs": [
                    {
                        "question": "What is your fundamental approach to solving business problems?",
                        "answer_belief": "I believe in taking a problem-first, tool-second approach. Too many companies buy tools without understanding the exact use case, leading to inefficiencies and wasted resources."
                    },
                    {
                        "question": "How do you view the role of automation in business operations?",
                        "answer_belief": "Any task that takes more than 20 minutes should be automated. Repetitive manual processes are opportunity costs that prevent teams from focusing on strategic work."
                    },
                    {
                        "question": "What is your philosophy on business metrics and measurement?",
                        "answer_belief": "Metrics should drive business outcomes, not just activity. I believe in balancing leading and lagging indicators, with focus on predictive leading indicators that help you aim correctly rather than just measure results."
                    },
                    {
                        "question": "How important is cross-departmental alignment in business success?",
                        "answer_belief": "Cross-departmental alignment is essential. Sales and marketing must work together, and technical solutions must serve broader business goals. Silos kill efficiency."
                    },
                    {
                        "question": "What role does security play in revenue operations?",
                        "answer_belief": "Tech stack security is non-negotiable. Every RevOps audit should include a security review because data breaches can destroy business trust and operations overnight."
                    },
                    {
                        "question": "How do you approach decision-making in business?",
                        "answer_belief": "I apply scientific methodology to business decisions - hypothesis testing, regular assessment, and optimization based on data rather than assumptions."
                    }
                ]
            },
            'is_versioned': False,
            'is_shared': False
        },
        # Content Pillars Document
        {
            'namespace': f"content_pillars_{test_entity_username}",
            'docname': "content_pillars.json",
            'initial_data': {
                "pillars": [
                    {
                        "pillar": "RevOps Education & Best Practices",
                        "pillar_description": "Educational content focused on revenue operations best practices, including tech stack optimization, metrics selection, sales and marketing alignment, and process automation. This pillar positions Mahak as a thought leader while providing practical value to the audience."
                    },
                    {
                        "pillar": "Founder Friday",
                        "pillar_description": "Weekly personal insights from Mahak's founder journey, including challenges, lessons learned, business development experiences, and reflections on building Revology Consulting. This pillar humanizes the brand and builds authentic connections."
                    },
                    {
                        "pillar": "Tool Spotlights & Security Audits",
                        "pillar_description": "Reviews and insights about sales and marketing tools, with special focus on security considerations, integration capabilities, and practical implementation advice. This pillar showcases expertise while building partnership opportunities."
                    },
                    {
                        "pillar": "Event Insights & Networking",
                        "pillar_description": "Takeaways from industry events, conferences, and networking experiences, including speaker insights, trend observations, and community building efforts. This pillar demonstrates thought leadership and industry engagement."
                    },
                    {
                        "pillar": "Global RevOps Perspectives",
                        "pillar_description": "Cross-cultural business insights highlighting differences in operations practices across regions, work cultures, and business approaches. This pillar leverages Mahak's international experience and appeals to global audience."
                    }
                ]
            },
            'is_versioned': False,
            'is_shared': False
        },
        # Content Analysis Document
        {
            'namespace': f"content_analysis_{test_entity_username}",
            'docname': "content_theme_analysis.json",
            'initial_data': {
                "theme_id": "revops_authority",
                "theme_name": "RevOps Authority & Expertise",
                "theme_description": "Content theme focused on establishing Mahak as a trusted RevOps expert through practical insights, real client examples, and actionable advice for SMB operations teams.",
                "tone_analysis": {
                    "dominant_tones": ["Authoritative", "Practical", "Enthusiastic"],
                    "sentiment": {
                        "label": "Positive",
                        "average_score": 0.75
                    },
                    "tone_distribution": [
                        {"tone": "Authoritative", "percentage": 40.0},
                        {"tone": "Practical", "percentage": 35.0},
                        {"tone": "Enthusiastic", "percentage": 25.0}
                    ],
                    "tone_description": "Content maintains an authoritative yet approachable tone, combining expertise with enthusiasm. Uses practical examples and specific metrics to build credibility while remaining accessible to non-technical audiences."
                },
                "structure_analysis": {
                    "post_format": {
                        "primary_format": "Bullet Points with Emojis",
                        "metrics": [
                            {"metric_name": "Average Word Count", "metric_value": 187},
                            {"metric_name": "Average Bullet Points", "metric_value": 6}
                        ],
                        "example": "🎯 Stop measuring what happened. Start measuring what's happening.\n✅ Revenue closed\n✅ Deal velocity\n🚀 Pipeline quality scores"
                    },
                    "conciseness": {
                        "level": "Highly Concise",
                        "metrics": [
                            {"metric_name": "Average Sentence Length", "metric_value": 12.5},
                            {"metric_name": "Average Paragraph Length", "metric_value": 2.3}
                        ],
                        "description": "Content is highly concise with short, punchy sentences and brief paragraphs that are easy to scan and digest on LinkedIn."
                    },
                    "data_intensity": {
                        "level": "Moderate",
                        "metrics": [
                            {"metric_name": "Numeric References per Post", "metric_value": 3.2},
                            {"metric_name": "Percentage-based Claims", "metric_value": 1.8}
                        ],
                        "example": "40% faster onboarding, 60% fewer integration issues, £2,400/month in savings"
                    },
                    "common_structures": [
                        {"structure": "Problem-Solution-Question", "frequency": "45%"},
                        {"structure": "List-Example-CTA", "frequency": "30%"},
                        {"structure": "Story-Lesson-Application", "frequency": "25%"}
                    ],
                    "structure_description": "Content follows predictable patterns that work well for LinkedIn engagement, typically starting with a hook, providing value through lists or examples, and ending with engagement questions."
                },
                "hook_analysis": {
                    "hook_type": {
                        "type": "Bold Claim",
                        "metrics": [
                            {"metric_name": "Hook Length (words)", "metric_value": 6.8},
                            {"metric_name": "Question Hooks", "metric_value": 0.3}
                        ]
                    },
                    "hook_text": "🎯 Stop measuring what happened. Start measuring what's happening.",
                    "engagement_correlation": [
                        {"average_likes": 89, "average_comments": 23, "average_reposts": 5}
                    ],
                    "hook_description": "Hooks typically use bold, contrarian statements that challenge conventional thinking, supported by emojis for visual impact and enhanced engagement."
                },
                "linguistic_style": {
                    "unique_terms": [
                        {"term": "RevOps", "frequency": 15, "example": "RevOps teams are drowning in lagging indicators"},
                        {"term": "tech stack", "frequency": 12, "example": "Your tech stack isn't a collection. It's an ecosystem."},
                        {"term": "leading indicators", "frequency": 8, "example": "Leading indicators tell you if you're aiming correctly"}
                    ],
                    "emoji_usage": {
                        "category": "Frequently",
                        "metrics": [
                            {"average_frequency": 8.5, "emoji": "🎯"},
                            {"average_frequency": 6.2, "emoji": "✅"},
                            {"average_frequency": 4.8, "emoji": "🚀"}
                        ]
                    },
                    "linguistic_description": "Language is professional but accessible, using industry-specific terms without excessive jargon. Frequent strategic use of emojis for visual appeal and to break up text blocks."
                },
                "recent_topics": [
                    {
                        "topic": "Leading vs Lagging Indicators",
                        "date": "2024-01-10",
                        "summary": "Explained difference between measuring outcomes vs measuring predictive factors",
                        "engagement": {"average_likes": 134, "average_comments": 52, "average_reposts": 8}
                    },
                    {
                        "topic": "Tech Stack Consolidation",
                        "date": "2024-01-08",
                        "summary": "Client case study showing how reducing tools from 12 to 4 improved efficiency",
                        "engagement": {"average_likes": 98, "average_comments": 31, "average_reposts": 6}
                    },
                    {
                        "topic": "Security Audit Discovery",
                        "date": "2024-01-15",
                        "summary": "Real example of client with 47 admin users highlighting security vulnerabilities",
                        "engagement": {"average_likes": 89, "average_comments": 23, "average_reposts": 4}
                    }
                ]
            },
            'is_versioned': False,
            'is_shared': False
        },
        # Knowledge Base Analysis Document
        {
            'namespace': f"knowledge_base_analysis_{test_entity_username}",
            'docname': "kb_analysis.json",
            'initial_data': {
                "key_information": [
                    "RevOps consulting requires balancing technical expertise with business acumen",
                    "SMB companies struggle most with tech stack optimization and metrics selection",
                    "Security vulnerabilities in CRM integrations are commonly overlooked",
                    "European markets have less RevOps awareness compared to US markets",
                    "Personal storytelling significantly increases engagement rates"
                ],
                "main_themes": [
                    "Revenue Operations Optimization",
                    "Tech Stack Security and Integration",
                    "Cross-Cultural Business Practices",
                    "Founder Journey and Personal Branding",
                    "Metrics-Driven Decision Making"
                ],
                "important_details": [
                    "Average engagement: 76 likes, 40 comments per post",
                    "90% of network is US-based with growing UK/European presence",
                    "Content length optimal at 187-217 words for best performance",
                    "Security-focused content performs well with technical audiences",
                    "Emoji usage averages 8.5 per post for visual engagement"
                ],
                "actionable_insights": [
                    "Focus on problem-first approach rather than tool-first in content",
                    "Use specific metrics and client examples to build credibility",
                    "Incorporate personal founder stories to humanize the brand",
                    "Address security concerns as differentiator from other RevOps content",
                    "Maintain consistent posting schedule of 2 posts per week"
                ],
                "relevant_quotes": [
                    "Your tech stack isn't a collection. It's an ecosystem.",
                    "Stop measuring what happened. Start measuring what's happening.",
                    "Even RevOps experts need to practice what they preach."
                ],
                "data_points": [
                    "7 clients acquired in first 3 months",
                    "£77,100 in closed deals within 3 months",
                    "40% faster onboarding through tech stack consolidation",
                    "60% fewer integration issues after optimization"
                ],
                "recommendations": [
                    "Continue using real client examples with specific metrics",
                    "Expand European market education content",
                    "Develop security-focused content pillar further",
                    "Leverage cross-cultural experiences for unique perspectives",
                    "Maintain authentic founder journey storytelling"
                ],
                "summary": "Analysis reveals a strong foundation for RevOps thought leadership through combination of technical expertise, practical client examples, and authentic personal storytelling. Content performance is strong with consistent engagement, particularly for security-focused and founder journey content.",
                "content_implications": "Content should continue emphasizing practical value through real examples, maintain security focus as differentiator, and leverage international perspective for unique market positioning. Personal storytelling elements significantly boost engagement and should be preserved.",
                "focus_area_analysis": "RevOps education content performs best when combined with specific metrics and client outcomes. Security-focused content serves as strong differentiator in crowded RevOps space. Founder journey content builds authentic connections and humanizes expertise."
            },
            'is_versioned': False,
            'is_shared': False
        },
        # Post Concepts Document
        {
            'namespace': f"post_concepts_{test_entity_username}",
            'docname': "post_concepts.json",
            'initial_data': {
                "concepts": [
                    {
                        "concept_id": "revops_metrics_misconception",
                        "hook": "🎯 Stop measuring what happened. Start measuring what's happening.",
                        "message": "Most RevOps teams focus on lagging indicators but miss the leading indicators that actually drive outcomes. Leading indicators help you aim correctly, not just measure if you hit the target."
                    },
                    {
                        "concept_id": "tech_stack_ecosystem",
                        "hook": "💡 Your tech stack isn't a collection. It's an ecosystem.",
                        "message": "Tools should work together seamlessly. The secret to tech stack optimization isn't finding perfect tools, it's finding tools that actually communicate with each other."
                    },
                    {
                        "concept_id": "security_audit_reality",
                        "hook": "🔓 Security audit time! Just discovered a client had 47 people with admin access to their Salesforce instance.",
                        "message": "Most companies have access chaos instead of access management. Regular security audits reveal shocking vulnerabilities that could destroy business operations overnight."
                    },
                    {
                        "concept_id": "founder_learning_curve",
                        "hook": "🎉 Founder Friday update! The irony of being a RevOps expert...",
                        "message": "Building systems for clients is very different from building systems for your own business. Even experts need to practice what they preach and stay humble about their own operational challenges."
                    },
                    {
                        "concept_id": "automation_threshold",
                        "hook": "⏰ If it takes more than 20 minutes, automate it.",
                        "message": "Repetitive manual processes are opportunity costs that prevent teams from focusing on strategic work. Automation isn't just about efficiency—it's about freeing human potential for higher-value activities."
                    }
                ]
            },
            'is_versioned': False,
            'is_shared': False
        },
        # Post Ideas Document
        {
            'namespace': f"post_ideas_{test_entity_username}",
            'docname': "post_ideas.json",
            'initial_data': {
                "ideas": [
                    {
                        "idea_id": "crm_integration_security",
                        "hook": "🚨 Your CRM integrations are probably leaking data right now.",
                        "message": "Most companies don't realize that third-party app integrations often have read/write access to all CRM data. A comprehensive security audit should be part of every RevOps implementation."
                    },
                    {
                        "idea_id": "european_revops_gap",
                        "hook": "🌍 Why European companies are 2 years behind in RevOps adoption.",
                        "message": "Having worked with clients across continents, I've noticed significant differences in RevOps maturity. European companies often have better process discipline but lag in tech stack optimization."
                    },
                    {
                        "idea_id": "email_personalization_myths",
                        "hook": "📧 Stop calling it 'personalization' when you just insert a first name.",
                        "message": "Real email personalization requires understanding buyer behavior, engagement patterns, and decision-making processes. True personalization drives 3x better response rates than basic merge tags."
                    },
                    {
                        "idea_id": "sales_marketing_alignment_reality",
                        "hook": "🤝 Sales and marketing alignment isn't about more meetings.",
                        "message": "Real alignment happens through shared metrics, integrated systems, and clear handoff processes. The best aligned teams I've worked with have fewer meetings but better systems."
                    },
                    {
                        "idea_id": "founder_imposter_syndrome",
                        "hook": "💭 Founder Friday: The day I realized I was making the same mistakes I help clients avoid.",
                        "message": "Imposter syndrome hits different when you're advising others on problems you're still solving yourself. The key is being transparent about the learning journey while still providing value."
                    }
                ]
            },
            'is_versioned': False,
            'is_shared': False
        },
    ]

    # Define cleanup docs to remove test artifacts after test completion
    cleanup_docs: List[CleanupDocInfo] = [
        # DNA Doc
        # {
        #     'namespace': USER_DNA_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
        #     'docname': USER_DNA_DOCNAME, 
        #     'is_versioned': USER_DNA_IS_VERSIONED, 
        #     'is_shared': False
        # },
        # # User Preferences
        # {
        #     'namespace': USER_PREFERENCES_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
        #     'docname': USER_PREFERENCES_DOCNAME, 
        #     'is_versioned': USER_PREFERENCES_IS_VERSIONED, 
        #     'is_shared': False
        # },
        # # Content Strategy
        # {
        #     'namespace': CONTENT_STRATEGY_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
        #     'docname': CONTENT_STRATEGY_DOCNAME, 
        #     'is_versioned': CONTENT_STRATEGY_IS_VERSIONED, 
        #     'is_shared': False
        # },
        # # LinkedIn Scraped Posts
        # {
        #     'namespace': LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
        #     'docname': LINKEDIN_POST_DOCNAME, 
        #     'is_versioned': False, 
        #     'is_shared': False
        # },
        # # Draft Posts
        # {
        #     'namespace': CONTENT_DRAFT_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
        #     'docname': CONTENT_DRAFT_DOCNAME.replace('{_uuid_}', 'draft-1'), 
        #     'is_versioned': CONTENT_DRAFT_IS_VERSIONED, 
        #     'is_shared': False
        # },
        # {
        #     'namespace': CONTENT_DRAFT_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
        #     'docname': CONTENT_DRAFT_DOCNAME.replace('{_uuid_}', 'draft-2'), 
        #     'is_versioned': CONTENT_DRAFT_IS_VERSIONED, 
        #     'is_shared': False
        # },
        # # Core Beliefs
        # {
        #     'namespace': f"user_data_beliefs_{test_entity_username}",
        #     'docname': "core_beliefs.json",
        #     'is_versioned': False,
        #     'is_shared': False
        # },
        # # Content Pillars
        # {
        #     'namespace': f"content_pillars_{test_entity_username}",
        #     'docname': "content_pillars.json",
        #     'is_versioned': False,
        #     'is_shared': False
        # },
        # # Content Analysis
        # {
        #     'namespace': f"content_analysis_{test_entity_username}",
        #     'docname': "content_theme_analysis.json",
        #     'is_versioned': False,
        #     'is_shared': False
        # },
        # # Knowledge Base Analysis
        # {
        #     'namespace': f"knowledge_base_analysis_{test_entity_username}",
        #     'docname': "kb_analysis.json",
        #     'is_versioned': False,
        #     'is_shared': False
        # },
        # # Post Concepts
        # {
        #     'namespace': f"post_concepts_{test_entity_username}",
        #     'docname': "post_concepts.json",
        #     'is_versioned': False,
        #     'is_shared': False
        # },
        # # Post Ideas
        # {
        #     'namespace': f"post_ideas_{test_entity_username}",
        #     'docname': "post_ideas.json",
        #     'is_versioned': False,
        #     'is_shared': False
        # },
        # # # Also clean up any generated briefs
        # # {
        # #     'namespace': CONTENT_BRIEF_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
        # #     'docname': "*",  # Wildcard to clean up all briefs in this namespace
        # #     'is_versioned': CONTENT_BRIEF_IS_VERSIONED, 
        # #     'is_shared': False
        # # },
    ]

    print("--- Setup/Cleanup Definitions (Complete) ---")
    print(f"Entity Username: {test_entity_username}")
    print(f"Setup Docs: {len(setup_docs)} documents prepared")
    print(f"Cleanup Docs: {len(cleanup_docs)} documents to be removed after test")
    print("Test Documents Created:")
    print("  • User DNA Document - Complete professional profile with LinkedIn analysis")
    print("  • User Preferences Document - Goals, audience segments, posting schedule, and timezone")
    print("  • Content Strategy Document - Comprehensive content strategy with pillars and targets")
    print("  • LinkedIn Scraped Posts - 4 realistic example posts with engagement metrics")
    print("  • Content Draft Posts - 2 draft posts with proper schema structure")
    print("  • Core Beliefs Document - 6 foundational business beliefs")
    print("  • Content Pillars Document - 5 content pillars with detailed descriptions")
    print("  • Content Analysis Document - Comprehensive content theme analysis")
    print("  • Knowledge Base Analysis Document - Key insights and recommendations")
    print("  • Post Concepts Document - 5 post concepts with hooks and messages")
    print("  • Post Ideas Document - 5 additional post ideas for future content")
    print("------------------------------------------------")

    # --- Define Custom Output Validation ---
    async def validate_calendar_output(outputs: Optional[Dict[str, Any]]) -> bool:
        assert outputs is not None, "Validation Failed: Workflow returned no outputs."
        logger.info("Validating content calendar workflow outputs...")
        assert 'final_briefs_list' in outputs, "Validation Failed: 'final_briefs_list' missing."
        assert isinstance(outputs['final_briefs_list'], list), "Validation Failed: 'final_briefs_list' is not a list."
        
        # Calculate expected number of briefs based on user preferences
        user_prefs = next((doc['initial_data'] for doc in setup_docs 
                          if doc['namespace'] == USER_PREFERENCES_NAMESPACE_TEMPLATE.format(item=test_entity_username)
                          and doc['docname'] == USER_PREFERENCES_DOCNAME), None)
        
        # Access posts_per_week from the new nested structure
        posts_per_week = user_prefs.get('posting_schedule', {}).get('posts_per_week', 2) if user_prefs else 2
        expected_count = test_inputs.get("weeks_to_generate", DEFAULT_WEEKS_TO_GENERATE) * posts_per_week
        
        # Validate brief count
        actual_count = len(outputs.get('final_briefs_list', []))
        assert actual_count == expected_count, f"Validation Failed: Expected {expected_count} briefs, found {actual_count}."
        
        # Validate brief structure according to the new ContentBriefSchema
        for brief in outputs.get('final_briefs_list', []):
            # Check required top-level fields
            # assert 'uuid' in brief, "Brief missing required field: uuid"
            assert 'title' in brief, "Brief missing required field: title"
            assert 'scheduled_date' in brief, "Brief missing required field: scheduled_date"
            assert 'content_pillar' in brief, "Brief missing required field: content_pillar"
            assert 'core_perspective' in brief, "Brief missing required field: core_perspective"
            
            # Check list fields
            assert 'post_objectives' in brief and isinstance(brief['post_objectives'], list), "post_objectives must be a list"
            assert 'key_messages' in brief and isinstance(brief['key_messages'], list), "key_messages must be a list"
            assert 'evidence_and_examples' in brief and isinstance(brief['evidence_and_examples'], list), "evidence_and_examples must be a list"
            assert 'suggested_hook_options' in brief and isinstance(brief['suggested_hook_options'], list), "suggested_hook_options must be a list"
            assert 'hashtags' in brief and isinstance(brief['hashtags'], list), "hashtags must be a list"
            
            # Check nested objects
            assert 'target_audience' in brief and isinstance(brief['target_audience'], dict), "target_audience must be an object"
            assert 'primary' in brief['target_audience'], "target_audience missing required field: primary"
            
            assert 'structure_outline' in brief and isinstance(brief['structure_outline'], dict), "structure_outline must be an object"
            assert 'opening_hook' in brief['structure_outline'], "structure_outline missing required field: opening_hook" 
            assert 'common_misconception' in brief['structure_outline'], "structure_outline missing required field: common_misconception"
            assert 'core_perspective' in brief['structure_outline'], "structure_outline missing required field: core_perspective"
            assert 'supporting_evidence' in brief['structure_outline'], "structure_outline missing required field: supporting_evidence"
            assert 'practical_framework' in brief['structure_outline'], "structure_outline missing required field: practical_framework"
            assert 'strategic_takeaway' in brief['structure_outline'], "structure_outline missing required field: strategic_takeaway"
            assert 'engagement_question' in brief['structure_outline'], "structure_outline missing required field: engagement_question"
            
            assert 'post_length' in brief and isinstance(brief['post_length'], dict), "post_length must be an object"
            assert 'min' in brief['post_length'], "post_length missing required field: min"
            assert 'max' in brief['post_length'], "post_length missing required field: max"
            
            # Validate that scheduled_date is a valid ISO 8601 UTC datetime format
            try:
                # Check for ISO 8601 UTC format (YYYY-MM-DDTHH:MM:SSZ)
                if isinstance(brief['scheduled_date'], str):
                    # Try to parse ISO 8601 format
                    if brief['scheduled_date'].endswith('Z'):
                        datetime.strptime(brief['scheduled_date'], '%Y-%m-%dT%H:%M:%SZ')
                    else:
                        # Also accept formats with timezone offset
                        datetime.fromisoformat(brief['scheduled_date'].replace('Z', '+00:00'))
                else:
                    raise ValueError("scheduled_date must be a string")
            except ValueError:
                assert False, f"Invalid scheduled_date format: {brief['scheduled_date']}. Expected ISO 8601 UTC format (YYYY-MM-DDTHH:MM:SSZ)"
        
        logger.info(f"   Found {actual_count} briefs, expected {expected_count}.")
        logger.info("✓ Output structure validation passed.")
        logger.info("✓ Timezone-aware scheduling validation completed.")
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
        cleanup_docs_created_by_setup=False,
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
        asyncio.run(main_test_content_calendar_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")
        logger.exception("Test execution failed")

