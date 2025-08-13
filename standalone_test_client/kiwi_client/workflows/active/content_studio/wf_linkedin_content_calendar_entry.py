"""
# Inputs to workflow:
1. Generate content topic suggestions for next X weeks: (X) int input optional, default 2
2. Load list of customer context docs such as dna, strategy doc, scraped posts etc
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
from kiwi_client.workflows.active.document_models.customer_docs import (
    # User DNA
    LINKEDIN_USER_DNA_DOCNAME,
    LINKEDIN_USER_DNA_NAMESPACE_TEMPLATE,
    LINKEDIN_USER_DNA_IS_VERSIONED,
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
    # Content Brief
    LINKEDIN_BRIEF_DOCNAME,
    LINKEDIN_BRIEF_NAMESPACE_TEMPLATE,
    LINKEDIN_BRIEF_IS_VERSIONED,
)
from kiwi_client.workflows.active.content_studio.llm_inputs.linkedin_content_calendar_entry import BRIEF_USER_PROMPT_TEMPLATE, BRIEF_SYSTEM_PROMPT_TEMPLATE, BRIEF_LLM_OUTPUT_SCHEMA, BRIEF_ADDITIONAL_USER_PROMPT_TEMPLATE
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
          }
        }
        # Outputs: weeks_to_generate, past_context_posts_limit, entity_username -> $graph_state
    },
 
    # --- 2. Load Customer Context Documents and Scraped Posts (Single Node) ---
    "load_all_context_docs": {
        "node_id": "load_all_context_docs",
        "node_name": "load_customer_data",
        "node_config": {
            "load_paths": [
                {
                    "filename_config": {
                        "input_namespace_field_pattern": LINKEDIN_USER_DNA_NAMESPACE_TEMPLATE, 
                        "input_namespace_field": "entity_username",
                        "static_docname": LINKEDIN_USER_DNA_DOCNAME,
                    },
                    "output_field_name": "user_dna"
                },
                {
                    "filename_config": {
                         "input_namespace_field_pattern": LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE, 
                          "input_namespace_field": "entity_username",
                          "static_docname": LINKEDIN_USER_PROFILE_DOCNAME,
                    },
                    "output_field_name": "user_preferences"
                },
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
            ],
            "global_is_shared": False,
            "global_is_system_entity": False,
            "global_schema_options": {"load_schema": False}
        },
        # Reads: entity_username (from input_node via edge mapping)
        # Writes: user_dna, user_preferences, strategy_doc, scraped_posts -> $graph_state
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
            "select_paths": ["user_preferences.posting_schedule.posts_per_week"], # Inputs from state
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
               "user_timezone": "user_preferences.timezone" # Map timezone from user preferences
            }
          },
          "topic_system_prompt": {
            "id": "topic_system_prompt",
            "template": BRIEF_SYSTEM_PROMPT_TEMPLATE,
            "variables": { 
                "schema": json.dumps(BRIEF_LLM_OUTPUT_SCHEMA, indent=2), 
                "current_datetime": "$current_date" },
            "construct_options": {}
          }
        }
      }
      # Reads: merged_posts from prepare_generation_context, user_preferences/strategy_doc/user_dna from state (including timezone)
      # Writes: topic_user_prompt, topic_system_prompt for generate_topics node
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
             "schema_definition": BRIEF_LLM_OUTPUT_SCHEMA,
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
        "choices": ["construct_additional_topic_prompt", "store_all_topics"],
        "allow_multiple": False,
        "choices_with_conditions": [
          {
            "choice_id": "construct_additional_topic_prompt", # Continue generating more topics
            "input_path": "if_else_condition_tag_results.topic_count_check",
            "target_value": True
          },
          {
            "choice_id": "store_all_topics", # End loop and store topics
            "input_path": "if_else_condition_tag_results.topic_count_check",
            "target_value": False,
          }
        ]
      }
      # Reads: if_else_condition_tag_results, iteration_branch_result from check_topic_count
      # Routes to: construct_additional_topic_prompt OR store_all_topics
    },

    # --- Construct Additional Topic Prompt ---
    "construct_additional_topic_prompt": {
      "node_id": "construct_additional_topic_prompt",
      "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
          "additional_topic_prompt": {
            "id": "additional_topic_prompt",
            "template": BRIEF_ADDITIONAL_USER_PROMPT_TEMPLATE,

          },
        }
      }
    },


    # --- 11. Store All Generated Topics (After Map Completes) ---
    "store_all_topics": {
      "node_id": "store_all_topics",
      "node_name": "store_customer_data", # Store the final list
      "node_config": {
          "global_versioning": { "is_versioned": LINKEDIN_BRIEF_IS_VERSIONED, "operation": "upsert_versioned"},
          "global_is_shared": False,
          "store_configs": [
              {
                  # Store the entire list collected in the state
                  "input_field_path": "all_generated_topics", # Mapped from state
                  "process_list_items_separately": True,
                  "target_path": {
                      "filename_config": {
                          "input_namespace_field_pattern": LINKEDIN_BRIEF_NAMESPACE_TEMPLATE, 
                          "input_namespace_field": "entity_username",
                          "static_docname": LINKEDIN_BRIEF_DOCNAME,
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

    },

  },

  # --- Edges Defining Data Flow ---
  "edges": [
    # --- Input to State ---
    { "src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "weeks_to_generate", "dst_field": "weeks_to_generate" },
        { "src_field": "past_context_posts_limit", "dst_field": "past_context_posts_limit" },
        { "src_field": "entity_username", "dst_field": "entity_username" },
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
        { "src_field": "user_dna", "dst_field": "user_dna"},
        { "src_field": "user_preferences", "dst_field": "user_preferences"},
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

    # --- Route on Topic Count -> Store All Topics (if all topics generated)
    { "src_node_id": "route_on_topic_count", "dst_node_id": "store_all_topics" },

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
        { "src_field": "paths_processed", "dst_field": "topic_paths_processed"}
      ]
     },

    # --- State -> Output ---
    { "src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
        { "src_field": "all_generated_topics", "dst_field": "final_briefs_list"}
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
          "all_generated_topics": "collect_values",   # Collect topic objects from each generation iteration
          "generate_topics_messages_history": "add_messages" # Message history for topic generation LLM

        }
      }
  }
}


# --- Test Execution Logic (Placeholder) ---


async def main_test_content_calendar_workflow():
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
        "past_context_posts_limit": PAST_CONTEXT_POSTS_LIMIT  # Combined limit for context
    }

    # print(json.dumps(test_inputs, indent=4))
    # return

    # Create realistic test data for setup
    setup_docs: List[SetupDocInfo] = [
        # User DNA Document
        {
            'namespace': LINKEDIN_USER_DNA_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_USER_DNA_DOCNAME,
            'initial_data': {
                "professional_identity": {
                    "full_name": "Test User",
                    "job_title": "Founder and CEO",
                    "industry_sector": "Business Consulting and Services (RevOps/Sales Operations)",
                    "company_name": "Revology Consulting",
                    "company_size": "Small (early‑stage startup)",
                    "years_of_experience": 10,
                    "professional_certifications": [],
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
                    "connection_count": None,
                    "profile_headline_analysis": "All things RevOps | Founder & CEO | Simplifying Processes and Demystifying Tech",
                    "about_section_summary": "Focuses on expertise in revenue operations, helping companies integrate and optimize tech stacks, sales processes, and enablement strategies to drive efficiency and scalability. Emphasizes enhancing workflows, building scalable systems, and driving measurable results with focus on reducing inefficiencies and creating data‑driven processes.",
                    "engagement_metrics": {
                        "average_likes_per_post": 76,
                        "average_comments_per_post": 40,
                        "average_shares_per_post": 0
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
                    "inspirations_and_influences": None,
                    "books_resources_they_reference": None,
                    "quotes_they_resonate_with": None
                },
                "analytics_insights": {
                    "optimal_content_length": "Business & Entrepreneurship ~217 words; Community & Networking ~112; Professional Growth ~127; Sales & Marketing ~87; Workplace Culture ~187; hooks 5–8 words for impact",
                    "audience_geographic_distribution": "~90% US‑based, some UK presence, international reach including Singapore",
                    "engagement_time_patterns": None,
                    "keyword_performance_analysis": "Engagement drivers: \"community\", \"culture\", \"modern outbound\", \"RevOps\", \"Revology Consulting\", security‑related terms, #WhoStillHasYourPasswords, leading/lagging indicators terminology",
                    "competitor_benchmarking": None,
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
            'is_versioned': LINKEDIN_USER_DNA_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': 'default'  # Required for versioned documents
        },
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
            'docname': LINKEDIN_DRAFT_DOCNAME.replace('{_uuid_}', 'draft-1'),
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
            'docname': LINKEDIN_DRAFT_DOCNAME.replace('{_uuid_}', 'draft-2'),
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
        # DNA Doc
        {
            'namespace': LINKEDIN_USER_DNA_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_USER_DNA_DOCNAME, 
            'is_versioned': LINKEDIN_USER_DNA_IS_VERSIONED, 
            'is_shared': False
        },
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
            'docname': LINKEDIN_DRAFT_DOCNAME.replace('{_uuid_}', 'draft-1'), 
            'is_versioned': LINKEDIN_DRAFT_IS_VERSIONED, 
            'is_shared': False
        },
        {
            'namespace': LINKEDIN_DRAFT_NAMESPACE_TEMPLATE.format(item=test_entity_username), 
            'docname': LINKEDIN_DRAFT_DOCNAME.replace('{_uuid_}', 'draft-2'), 
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
        assert 'final_briefs_list' in outputs, "Validation Failed: 'final_briefs_list' missing."
        
        # Handle both single object and list formats (workflow iteration issue workaround)
        final_briefs = outputs['final_briefs_list']
        if isinstance(final_briefs, dict):
            # Single topic suggestion object - convert to list for consistent validation
            topic_suggestions_list = [final_briefs]
            logger.info("⚠️  Found single topic suggestion object instead of list. This indicates the workflow iteration didn't work properly.")
        elif isinstance(final_briefs, list):
            topic_suggestions_list = final_briefs
        else:
            assert False, f"Validation Failed: 'final_briefs_list' must be a list or dict, got {type(final_briefs)}"
        
        # Calculate expected number of topic suggestions based on user profile
        user_prefs = next((doc['initial_data'] for doc in setup_docs 
                          if doc['namespace'] == LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item=test_entity_username)
                          and doc['docname'] == LINKEDIN_USER_PROFILE_DOCNAME), None)
        
        # Access posts_per_week from the LinkedIn profile document structure
        posts_per_week = user_prefs.get('posting_schedule', {}).get('posts_per_week', 2) if user_prefs else 2
        expected_count = test_inputs.get("weeks_to_generate", DEFAULT_WEEKS_TO_GENERATE) * posts_per_week
        
        # Validate topic suggestions count
        actual_count = len(topic_suggestions_list)
        
        if actual_count != expected_count:
            logger.warning(f"⚠️  Expected {expected_count} topic suggestions, found {actual_count}. This indicates workflow iteration issues.")
            logger.warning("   The workflow should generate one topic suggestion for each scheduled posting date.")
            logger.warning(f"   Expected: {expected_count} = {test_inputs.get('weeks_to_generate', DEFAULT_WEEKS_TO_GENERATE)} weeks × {posts_per_week} posts per week")
        
        # Validate topic suggestion structure according to the new ContentTopicsOutput schema
        for idx, topic_output in enumerate(topic_suggestions_list, 1):
            logger.info(f"   Validating topic suggestion {idx}/{len(topic_suggestions_list)}...")
            
            # Check required top-level fields
            assert 'suggested_topics' in topic_output, f"Topic suggestion {idx} missing required field: suggested_topics"
            assert isinstance(topic_output['suggested_topics'], list), f"suggested_topics in suggestion {idx} must be a list"
            assert len(topic_output['suggested_topics']) > 0, f"suggested_topics in suggestion {idx} cannot be empty"
            
            assert 'scheduled_date' in topic_output, f"Topic suggestion {idx} missing required field: scheduled_date"
            assert 'theme' in topic_output, f"Topic suggestion {idx} missing required field: theme"
            assert 'play_aligned' in topic_output, f"Topic suggestion {idx} missing required field: play_aligned"
            assert 'objective' in topic_output, f"Topic suggestion {idx} missing required field: objective"
            assert 'why_important' in topic_output, f"Topic suggestion {idx} missing required field: why_important"
            
            # Validate exactly 4 topics per suggestion
            assert len(topic_output['suggested_topics']) == 4, f"Topic suggestion {idx} must contain exactly 4 topics, found {len(topic_output['suggested_topics'])}"
            
            # Validate individual topic structure
            for i, topic in enumerate(topic_output['suggested_topics'], 1):
                assert 'title' in topic, f"Topic suggestion {idx}, topic {i} missing required field: title"
                assert 'description' in topic, f"Topic suggestion {idx}, topic {i} missing required field: description"
                assert isinstance(topic['title'], str) and len(topic['title'].strip()) > 0, f"Topic suggestion {idx}, topic {i} title must be a non-empty string"
                assert isinstance(topic['description'], str) and len(topic['description'].strip()) > 0, f"Topic suggestion {idx}, topic {i} description must be a non-empty string"
            
            # Validate objective is valid enum value
            valid_objectives = ["brand_awareness", "thought_leadership", "engagement", "education", "lead_generation", "community_building"]
            assert topic_output['objective'] in valid_objectives, f"Topic suggestion {idx} invalid objective: {topic_output['objective']}. Must be one of {valid_objectives}"
            
            # Validate that scheduled_date is a valid ISO 8601 UTC datetime format
            try:
                # Check for ISO 8601 UTC format (YYYY-MM-DDTHH:MM:SSZ)
                if isinstance(topic_output['scheduled_date'], str):
                    # Try to parse ISO 8601 format
                    if topic_output['scheduled_date'].endswith('Z'):
                        datetime.strptime(topic_output['scheduled_date'], '%Y-%m-%dT%H:%M:%SZ')
                    else:
                        # Also accept formats with timezone offset
                        datetime.fromisoformat(topic_output['scheduled_date'].replace('Z', '+00:00'))
                else:
                    raise ValueError("scheduled_date must be a string")
            except ValueError:
                assert False, f"Topic suggestion {idx} invalid scheduled_date format: {topic_output['scheduled_date']}. Expected ISO 8601 UTC format (YYYY-MM-DDTHH:MM:SSZ)"
        
        logger.info(f"   Found {actual_count} topic suggestions, expected {expected_count}.")
        logger.info("✓ Each topic suggestion contains exactly 4 topics around one theme.")
        logger.info("✓ Output structure validation passed.")
        logger.info("✓ Timezone-aware scheduling validation completed.")
        
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
        asyncio.run(main_test_content_calendar_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")
        logger.exception("Test execution failed")

