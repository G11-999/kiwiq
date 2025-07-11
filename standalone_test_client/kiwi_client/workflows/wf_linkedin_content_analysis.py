"""
batch ID -> 10 posts
- post ID
- theme 1, confidence score, relevance score

# NOTE: don't use a filter node to filter by confidence score; instruct LLM to only assign a theme if confidence score is high


1. Inputs: entity name
2. Load posts using entity name and scraping namespace
3. Optional: Posts filtering -> only get text content
4. Extract upto 5 themes using all posts in context with LLM (you can use generated theme name to be theme ID potentially?)
5. create batches of 10 posts each
6. For each batch classify posts into the most relevant theme with LLM -> check above structure for classification
7. Map each post to the most relevant theme to create theme groups; merge all batches together
8. Analyze each theme group with LLM to create a detailed report for each group
9. combine all reports together
10. Store combined results

"""

from kiwi_client.workflows.document_models.customer_docs import (
    LINKEDIN_POST_DOCNAME,
    # Namespace and docname for storing the final analysis result
    LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE,
    CONTENT_ANALYSIS_DOCNAME,
    CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
)

from kiwi_client.workflows.llm_inputs.linkedin_content_analysis import (
    EXTRACTED_THEMES_SCHEMA,
    BATCH_CLASSIFICATION_SCHEMA,
    THEME_ANALYSIS_REPORT_SCHEMA,
    THEME_EXTRACTION_USER_PROMPT_TEMPLATE,
    THEME_EXTRACTION_SYSTEM_PROMPT_TEMPLATE,
    POST_CLASSIFICATION_USER_PROMPT_TEMPLATE,
    POST_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE,
    THEME_ANALYSIS_USER_PROMPT_TEMPLATE,
    THEME_ANALYSIS_SYSTEM_PROMPT_TEMPLATE,
)

import json
import asyncio
from typing import List, Optional, Dict, Any, Literal


# --- Workflow Constants ---
# LLM Configuration (Placeholders - Adjust as needed)
LLM_PROVIDER = "openai"
EXTRACTION_MODEL = "gpt-4.1" # Model for theme extraction, classification, analysis
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS_CLASSIFY = 2000 # Adjust based on batch size and theme complexity
LLM_MAX_TOKENS_THEMES = 4000 # Adjust based on total post text length
LLM_MAX_TOKENS_ANALYSIS = 4000 # Adjust based on theme group size

POST_BATCH_SIZE = 10

# --- Workflow Graph Definition ---
# Based on the 10 steps provided

workflow_graph_schema = {
  "nodes": {
    # --- 1. Input Node ---
    "input_node": {
      "node_id": "input_node",
      "node_name": "input_node",
      "node_config": {},
      "dynamic_output_schema": {
          "fields": {
              "entity_username": { "type": "str", "required": True, "description": "Name of the LinkedIn entity (person or company) whose posts are to be analyzed." },
          }
        }
    },

    # --- 2. Load Posts ---
    "load_posts": {
      "node_id": "load_posts",
      "node_name": "load_customer_data",
      "node_config": {
          # Assumes posts were saved unversioned by the scraping workflow
          # NOTE: LoadCustomerDataNode typically outputs a dict like {"output_field_name": [data...]}
          # Need to adjust paths based on actual node output structure. Assuming it outputs {"raw_posts_data": [list_of_posts]}
          "load_paths": [
              {
                  "filename_config": {
                      "input_namespace_field_pattern": LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE, 
                      "input_namespace_field": "entity_username",
                      "static_docname": LINKEDIN_POST_DOCNAME,
                  },
                  "output_field_name": "raw_posts_data" # Expect output containing LinkedIn posts
              },
              
          ]
      },
      "dynamic_output_schema": {
          "fields": {
              "raw_posts_data": { "type": "list", "required": True, "description": "List of posts from the LinkedIn entity." },
          }
        }
      # Input: entity_username
      # Output: {"raw_posts_data": [list_of_posts]}
    },

    # --- 4. Extract Themes (using LLM) ---
    "construct_theme_extraction_prompt": {
      "node_id": "construct_theme_extraction_prompt",
      "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
          "theme_user_prompt": {
            "id": "theme_user_prompt",
            # Template expects a single JSON string containing the list of posts (or just texts)
            "template": THEME_EXTRACTION_USER_PROMPT_TEMPLATE,
            "variables": {
              "posts_json": None # Mapped from prepare_posts
            },
            "construct_options": {
                 # Map the list directly, prompt constructor might handle JSON conversion
                "posts_json": "prepared_posts_list" # Expect this field in input
            }
          },
          "theme_system_prompt": {
            "id": "theme_system_prompt",
            "template": THEME_EXTRACTION_SYSTEM_PROMPT_TEMPLATE,
            "variables": { "schema":  EXTRACTED_THEMES_SCHEMA}, # Pass schema as string
            "construct_options": {}
          }
        }
      }
      # Input: entity_username (from state), prepared_posts_list (from prepare_posts)
      # Output: user_prompt, system_prompt
    },
    "extract_themes": {
        "node_id": "extract_themes",
        "node_name": "llm",
        "node_config": {
            "llm_config": {
              "model_spec": {"provider": LLM_PROVIDER, "model": EXTRACTION_MODEL},
              "temperature": LLM_TEMPERATURE,
              "max_tokens": LLM_MAX_TOKENS_THEMES
            },
            "output_schema": {
                "schema_definition": EXTRACTED_THEMES_SCHEMA,
                "convert_loaded_schema_to_pydantic": False
            }
        }
        # Input: user_prompt, system_prompt (from construct_theme_extraction_prompt)
        # Output: structured_output (containing extracted_themes object) -> store in state
    },

    # --- 5. Batch Posts (using MapListRouterNode) ---
    "batch_and_route_posts": {
        "node_id": "batch_and_route_posts",
        "node_name": "map_list_router_node",
        "node_config": {
            "choices": ["construct_classification_prompt"], # Target node for each batch
            "map_targets": [
                {
                    # Path to the list of prepared posts within this node's input data
                    "source_path": "prepared_posts_list", # From prepare_posts output
                    "destinations": ["construct_classification_prompt"],
                    "batch_size": POST_BATCH_SIZE,
                    "batch_field_name": "post_batch" # Wraps output: {"post_batch": [post1, post2, ...]}
                }
            ]
        }
        # Input: {"prepared_posts_list": [list_of_posts]} (from prepare_posts)
        # Output: Sends {"post_batch": [...]} to construct_classification_prompt
    },

    # --- 6. Classify Posts per Batch (using LLM) ---
    "construct_classification_prompt": {
      "node_id": "construct_classification_prompt",
      "node_name": "prompt_constructor",
      "private_input_mode": True, # Receives input from batch_and_route_posts
      "output_private_output_to_central_state": True,
      "private_output_mode": True, # Sends output to classify_batch
      "node_config": {
        "prompt_templates": {
          "classify_user_prompt": {
            "id": "classify_user_prompt",
            "template": POST_CLASSIFICATION_USER_PROMPT_TEMPLATE,
            "variables": {
              "themes_json": None,      # Mapped from state (extracted_themes_list)
              "posts_batch_json": None # Mapped from input (post_batch field)
            },
            "construct_options": {
                # Input field names expected by this node
                "themes_json": "themes_data_json", # Needs JSON string representation from state
                "posts_batch_json": "post_batch" # Map the list from the batcher's output field directly
            }
          },
          "classify_system_prompt": {
            "id": "classify_system_prompt",
            "template": POST_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE,
            "variables": { "schema": json.dumps(BATCH_CLASSIFICATION_SCHEMA, indent=2) },
            "construct_options": {}
          }
        }
      }
      # Input (private): {"post_batch": [...]}, themes_data_json (mapped from state)
      # Output (private): user_prompt, system_prompt
    },
    "classify_batch": {
        "node_id": "classify_batch",
        "node_name": "llm",
        "private_input_mode": True, # Receives input from construct_classification_prompt
        "output_private_output_to_central_state": True,
        # Output goes to graph state for aggregation
        "node_config": {
            "llm_config": {
                "model_spec": {"provider": LLM_PROVIDER, "model": EXTRACTION_MODEL},
                "temperature": LLM_TEMPERATURE,
                "max_tokens": LLM_MAX_TOKENS_CLASSIFY
            },
            "output_schema": {
                "schema_definition": BATCH_CLASSIFICATION_SCHEMA,
                "convert_loaded_schema_to_pydantic": False
            }
        }
        # Input (private): user_prompt, system_prompt
        # Output: structured_output (containing batch_classifications) -> sent to state: all_classifications_batches
    },

    # --- 7a. Flatten Classification Results ---
    # The reducer 'collect_values' will create a list of lists. We need a flat list for joining.
    # Using merge_aggregate node to flatten the list.
    "flatten_classifications": {
        "node_id": "flatten_classifications",
        "node_name": "merge_aggregate", # Use merge_aggregate for list operations
        "node_config": {
            "operations": [
                {
                    "output_field_name": "flat_classifications",
                    # Path to the list of lists collected in the state
                    "select_paths": ["all_classifications_batches"], # Input field name, mapped from state
                    # "merge_each_object_in_selected_list": False,
                    "merge_strategy": {
                        "reduce_phase": {
                            # Use 'append' or similar list flattening reducer
                            "default_reducer": "nested_merge_aggregate", # Assuming 'append_flatten' exists
                            "error_strategy": "fail_node",
                        },
                        # "post_merge_transformations": {
                        #     # Key doesn't matter for non-dict, config is used
                        #     "flatten_op": {
                        #         "operation_type": "recursive_flatten_list"
                        #     }
                        # },
                        
                    }
                }
            ]
        },
        # "dynamic_input_schema": {  # NOTE: CRITICAL: this needs to be explicitly defined so its type is not incorrectly inferred at runtime since it will be a dict/boject rather than list!
        #   "fields": {
        #       "all_classifications_batches": {
        #           "type": "list", "required": True,
        #           "description": "A list of lists of PostClassificationSchema objects."
        #       }
        #   }
        # },
        # Input: {"all_classifications_batches": [[batch1_results], [batch2_results], ...]} (from state)
        # Output: merged_data --> {"flat_classifications": [result1, result2, ...]}
    },

    # --- 7b. Join Classifications to Posts ---
    "join_classifications_to_posts": {
        "node_id": "join_classifications_to_posts",
        "node_name": "data_join_data", # Use the DataJoinNode
        "node_config": {
            "joins": [
                {
                    "primary_list_path": "prepared_posts_list", # From state or prepare_posts output
                    "secondary_list_path": "merged_data.flat_classifications.classifications", # From flatten_classifications output
                    "primary_join_key": "urn", # Assuming 'urn' is the unique ID in prepared posts
                    "secondary_join_key": "post_id", # Matches 'urn' based on classification prompt
                    "output_nesting_field": "mapped_theme", # Nest classification under this key in post
                    "join_type": "one_to_one"
                }
            ]
        },
        # Input: prepared_posts_list (from state), flat_classifications (from flatten_classifications)
        # Output: {"mapped_data": {"prepared_posts_list": [post_with_theme1, post_with_theme2, ...]}}
    },

    # --- 7c. Group Posts under Themes ---
    "group_posts_under_themes": {
        "node_id": "group_posts_under_themes",
        "node_name": "data_join_data",
        "node_config": {
            "joins": [
                {
                    "primary_list_path": "extracted_themes.themes", # From state (list of ThemeSchema)
                    # Path to the modified posts list *within* the previous node's output
                    "secondary_list_path": "mapped_data.prepared_posts_list", # From join_classifications_to_posts output
                    "primary_join_key": "theme_id", # Key in ThemeSchema
                    "secondary_join_key": "mapped_theme.assigned_theme_id", # Key nested in post object
                    "output_nesting_field": "mapped_posts", # Nest list of posts under this key in theme
                    "join_type": "one_to_many"
                }
            ]
        },
        # Input: extracted_themes_list (from state), mapped_data (from join_classifications_to_posts)
        # Output: {"mapped_data": {"extracted_themes_list": [theme_with_posts1, theme_with_posts2, ...]}}
    },


    # --- 8. Analyze Each Theme Group (Map/Reduce Pattern) ---
    "route_theme_groups": {
        "node_id": "route_theme_groups",
        "node_name": "map_list_router_node",
        "node_config": {
            "choices": ["construct_analysis_prompt"], # Target for each theme group
            "map_targets": [
                {
                    # Path to the list of themes (which now contain mapped_posts)
                    # from the output of the previous join node.
                    "source_path": "mapped_data.extracted_themes.themes", # Adjust based on group_posts_under_themes output key
                    "destinations": ["construct_analysis_prompt"],
                    "batch_size": 1, # Process one theme group at a time
                    "batch_field_name": "theme_group_data" # Wraps output: {"theme_group_data": {theme_info + mapped_posts}}
                }
            ]
        }
        # Input: {"mapped_data": {"extracted_themes_list": [...]}} (from group_posts_under_themes)
        # Output: Sends {"theme_group_data": {...}} to construct_analysis_prompt
    },
    "construct_analysis_prompt": {
      "node_id": "construct_analysis_prompt",
      "node_name": "prompt_constructor",
      "private_input_mode": True,
      "output_private_output_to_central_state": True,
      "private_output_mode": True,
      "node_config": {
        "prompt_templates": {
          "analyze_user_prompt": {
            "id": "analyze_user_prompt",
            # Template expects a single theme group object (theme info + mapped_posts list)
            "template": THEME_ANALYSIS_USER_PROMPT_TEMPLATE,
            "variables": {
              "theme_id": None,    # Mapped from theme_group_data input
              "theme_name": None,  # Mapped from theme_group_data input
              "theme_description": None, # Mapped from theme_group_data input
              "theme_group_json": None # Mapped from theme_group_data input (entire object)
            },
            # Assumes input 'theme_group_data' has keys: theme_id, theme_name, theme_description, mapped_posts
            "construct_options": {
                "theme_id": "theme_group_data.theme_id",
                "theme_name": "theme_group_data.theme_name",
                "theme_description": "theme_group_data.theme_description",
                "theme_group_json": "theme_group_data" # Pass the whole theme group object as JSON
            }
          },
          "analyze_system_prompt": {
            "id": "analyze_system_prompt",
            "template": THEME_ANALYSIS_SYSTEM_PROMPT_TEMPLATE,
            "variables": { "schema": json.dumps(THEME_ANALYSIS_REPORT_SCHEMA, indent=2) },
            "construct_options": {}
          }
        }
      }
      # Input (private): {"theme_group_data": {...}}, entity_username (from state)
      # Output (private): user_prompt, system_prompt
    },
    "analyze_theme_group": {
        "node_id": "analyze_theme_group",
        "node_name": "llm",
        "private_input_mode": True,
        "output_private_output_to_central_state": True,
        # Output goes to graph state for aggregation
        "node_config": {
            "llm_config": {
                "model_spec": {"provider": LLM_PROVIDER, "model": EXTRACTION_MODEL},
                "temperature": LLM_TEMPERATURE,
                "max_tokens": LLM_MAX_TOKENS_ANALYSIS
            },
            "output_schema": {
                "schema_definition": THEME_ANALYSIS_REPORT_SCHEMA,
                "convert_loaded_schema_to_pydantic": False
            }
        }
        # Input (private): user_prompt, system_prompt
        # Output: structured_output (containing theme_analysis_report) -> sent to state: all_theme_reports
    },

    # --- 9. Combine All Reports ---
    "combine_reports": {
        "node_id": "combine_reports",
        "node_name": "transform_data", # Or a custom node
        "node_config": {
            "mappings": [
                { "source_path": "entity_username", "destination_path": "final_report_data.entity_username"},
                # Embed the collected list of report objects
                { "source_path": "all_reports_list", "destination_path": "final_report_data.theme_reports"},
            ]
        },
         # Define input schema for clarity (needs a static value source)
        # "dynamic_input_schema": {
        #      "fields": {
        #         "all_reports_list": {"type": "list", "required": True},
        #          "entity_username": {"type": "str", "required": True}, 
        #      }
        #  }
        # Input: all_reports_list (from state: all_theme_reports), entity_username (from state), static_summary (provided statically or from another node)
        # Output: transformed_data -> fin
    },

    # --- 10. Store Combined Results ---
    "store_analysis": {
      "node_id": "store_analysis",
      "node_name": "store_customer_data",
      "node_config": {
        "global_versioning": { "is_versioned": False, "operation": "upsert" },
        "global_is_shared": False,
        "store_configs": [
          {
            "input_field_path": "transformed_data.final_report_data", # From combine_reports output
            "target_path": {
              "filename_config": {
                "input_namespace_field_pattern": CONTENT_ANALYSIS_NAMESPACE_TEMPLATE, 
                "input_namespace_field": "entity_username",
                "static_docname": CONTENT_ANALYSIS_DOCNAME,
              }
            }
          }
        ]
      }
      # Input: final_report_data (from combine_reports), entity_username (from $graph_state)
      # Output: passthrough_data, paths_processed
    },

    # --- 11. Output Node ---
    "output_node": {
      "node_id": "output_node",
      "node_name": "output_node",
      "node_config": {},
      # "dynamic_input_schema": {
      #     "fields": {
      #         "analysis_storage_path": { "type": "list", "required": False, "description": "Path where the final analysis report was stored." },
      #         "processed_entity_username": { "type": "str", "required": False, "description": "The name of the entity processed." }
      #     }
      #   }
    }
  },

  # --- Edges Defining Data Flow ---
  "edges": [
    # --- Input & Setup ---
    { "src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username", "description": "Store entity name globally." }
      ]
    },
    { "src_node_id": "input_node", "dst_node_id": "load_posts", "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username", "description": "Pass entity name to load posts."}
      ]
    },
    # Store prepared posts list in state for later joins
    { "src_node_id": "load_posts", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "raw_posts_data", "dst_field": "prepared_posts_list", "description": "Store prepared posts list in state."}
      ]
    },

    # --- Step 4: Theme Extraction ---
    { "src_node_id": "load_posts", "dst_node_id": "construct_theme_extraction_prompt", "mappings": [
         # Pass the list needed for the prompt
         { "src_field": "raw_posts_data", "dst_field": "prepared_posts_list"}
      ]
    },
    { "src_node_id": "construct_theme_extraction_prompt", "dst_node_id": "extract_themes", "mappings": [
        { "src_field": "theme_user_prompt", "dst_field": "user_prompt"},
        { "src_field": "theme_system_prompt", "dst_field": "system_prompt"}
      ]
    },

    # --- State -> Extract Themes (Message History) ---
    { "src_node_id": "$graph_state", "dst_node_id": "extract_themes", "mappings": [
        { "src_field": "extract_themes_messages_history", "dst_field": "messages_history"}
      ]
    },

    { "src_node_id": "extract_themes", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "structured_output", "dst_field": "extracted_themes", "description": "Store extracted themes structure."},
        { "src_field": "current_messages", "dst_field": "extract_themes_messages_history", "description": "Update message history with theme extraction interaction."}
      ]
    },
    
    # --- Step 5 & 6: Batching and Classification ---
    { "src_node_id": "extract_themes", "dst_node_id": "batch_and_route_posts", "mappings": [
      ]
    },
    { "src_node_id": "$graph_state", "dst_node_id": "batch_and_route_posts", "mappings": [
        # Pass the prepared list for batching
        { "src_field": "prepared_posts_list", "dst_field": "prepared_posts_list" }
      ]
    },
    { "src_node_id": "batch_and_route_posts", "dst_node_id": "construct_classification_prompt", "mappings": [
      ]
    },

    { "src_node_id": "$graph_state", "dst_node_id": "construct_classification_prompt", "mappings": [
        # Pass themes as JSON string (assuming prompt node handles conversion)
        { "src_field": "extracted_themes", "dst_field": "themes_data_json", "description": "Pass themes list to classification prompt."}
      ]
    },
    { "src_node_id": "construct_classification_prompt", "dst_node_id": "classify_batch", "mappings": [
        { "src_field": "classify_user_prompt", "dst_field": "user_prompt"},
        { "src_field": "classify_system_prompt", "dst_field": "system_prompt"}
      ]
    },

    # --- State -> Classify Batch (Message History) ---
    { "src_node_id": "$graph_state", "dst_node_id": "classify_batch", "mappings": [
        { "src_field": "classify_batch_messages_history", "dst_field": "messages_history"}
      ]
    },

    { "src_node_id": "classify_batch", "dst_node_id": "$graph_state", "mappings": [
        # Store the list of classifications *from this batch*
        { "src_field": "structured_output", "dst_field": "all_classifications_batches", "description": "Collect classification results from each batch."},
        { "src_field": "current_messages", "dst_field": "classify_batch_messages_history", "description": "Update message history with classification interaction."}
      ]
    },

    { "src_node_id": "classify_batch", "dst_node_id": "flatten_classifications", "mappings": [
      ]
    },

    # --- Step 7a: Flatten Classifications (Runs after map completes) ---
    { "src_node_id": "$graph_state", "dst_node_id": "flatten_classifications", "mappings": [
        { "src_field": "all_classifications_batches", "dst_field": "all_classifications_batches", "description": "Pass collected batches for flattening."}
      ]
    },
    # Store flattened list in state? Optional, can pass directly. Let's pass directly.
    # { "src_node_id": "flatten_classifications", "dst_node_id": "$graph_state", "mappings": [
    #     { "src_field": "flat_classifications", "dst_field": "flat_classifications"}
    #   ]
    # },

    # --- Step 7b: Join Classifications to Posts ---
    { "src_node_id": "flatten_classifications", "dst_node_id": "join_classifications_to_posts", "mappings": [
        { "src_field": "merged_data", "dst_field": "merged_data", "description": "Pass flattened classifications to join node."}
      ]
    },
    { "src_node_id": "$graph_state", "dst_node_id": "join_classifications_to_posts", "mappings": [
        { "src_field": "prepared_posts_list", "dst_field": "prepared_posts_list", "description": "Pass original prepared posts for join."}
      ]
    },

    # --- Step 7c: Group Posts under Themes ---
    { "src_node_id": "join_classifications_to_posts", "dst_node_id": "group_posts_under_themes", "mappings": [
        # Pass the output of the previous join (which contains the modified posts list)
        { "src_field": "mapped_data", "dst_field": "mapped_data", "description": "Pass posts with mapped themes."}
      ]
    },
    { "src_node_id": "$graph_state", "dst_node_id": "group_posts_under_themes", "mappings": [
        { "src_field": "extracted_themes", "dst_field": "extracted_themes", "description": "Pass original themes list for grouping."}
      ]
    },

    # --- Step 8: Theme Analysis ---
    { "src_node_id": "group_posts_under_themes", "dst_node_id": "route_theme_groups", "mappings": [
        # Pass the output of the grouping join (themes with mapped posts)
        { "src_field": "mapped_data", "dst_field": "mapped_data", "description": "Pass theme groups for analysis routing."}
      ]
    },
    
    # Router edge no mapping!
    { "src_node_id": "route_theme_groups", "dst_node_id": "construct_analysis_prompt", "mappings": [
      ]
    },

    { "src_node_id": "construct_analysis_prompt", "dst_node_id": "analyze_theme_group", "mappings": [
        { "src_field": "analyze_user_prompt", "dst_field": "user_prompt"},
        { "src_field": "analyze_system_prompt", "dst_field": "system_prompt"}
      ]
    },

    # --- State -> Analyze Theme Group (Message History) ---
    { "src_node_id": "$graph_state", "dst_node_id": "analyze_theme_group", "mappings": [
        { "src_field": "analyze_theme_group_messages_history", "dst_field": "messages_history"}
      ]
    },

    { "src_node_id": "analyze_theme_group", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "structured_output", "dst_field": "all_theme_reports", "description": "Collect all theme analysis reports."},
        { "src_field": "current_messages", "dst_field": "analyze_theme_group_messages_history", "description": "Update message history with theme analysis interaction."}
      ]
    },

    # --- Step 9: Combine Reports (Runs after map completes) ---
    { "src_node_id": "analyze_theme_group", "dst_node_id": "combine_reports", "mappings": [
      ]
    },
    { "src_node_id": "$graph_state", "dst_node_id": "combine_reports", "mappings": [
        { "src_field": "all_theme_reports", "dst_field": "all_reports_list"},
        { "src_field": "entity_username", "dst_field": "entity_username"},
      ]
    },

    # --- Step 10: Store Results ---
    { "src_node_id": "combine_reports", "dst_node_id": "store_analysis", "mappings": [
        { "src_field": "transformed_data", "dst_field": "transformed_data" }
      ]
    },
    { "src_node_id": "$graph_state", "dst_node_id": "store_analysis", "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username" }
      ]
    },

    # --- Step 11: Output ---
    { "src_node_id": "store_analysis", "dst_node_id": "output_node", "mappings": [
        { "src_field": "paths_processed", "dst_field": "analysis_storage_path" }
      ]
    },
    { "src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
        { "src_field": "entity_username", "dst_field": "processed_entity_username" },
        # NOTE: BUG: this field changes types from dict to list due to aggregation!
        #     So disabling this and piping output via another route!
        # { "src_field": "all_theme_reports", "dst_field": "all_reports_list"},
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
          # Collect results from parallel branches
          "all_classifications_batches": "collect_values", # Collect lists of lists from each batch classification
          "all_theme_reports": "collect_values",   # Collect report objects from each theme analysis
          # Message histories for LLM nodes
          "extract_themes_messages_history": "add_messages",
          "classify_batch_messages_history": "add_messages", 
          "analyze_theme_group_messages_history": "add_messages"
          # Other state variables
        #   "entity_username": "replace",
        #   "prepared_posts_list": "replace", # Store the prepared posts list
        #   "extracted_themes_output": "replace",
        #   "extracted_themes_list": "replace"
        }
      }
  }
}


# --- Test Execution Logic (Placeholder) ---

# Import necessary components for testing
import logging
# from kiwi_client.test_run_workflow_client import run_workflow_test, CleanupDocInfo, SetupDocInfo
# from kiwi_client.schemas.workflow_constants import WorkflowRunStatus
# from kiwi_client.test_config import CLIENT_LOG_LEVEL

# Internal dependencies (assuming similar structure to example)
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

logger = logging.getLogger(__name__)
# logging.basicConfig(level=CLIENT_LOG_LEVEL) # Uncomment if using test client logger

# Example Input
TEST_INPUTS = {
    "entity_username": "test_username" # Replace with a real entity name for testing
}

async def validate_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """Custom validation function for the workflow outputs."""
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating LinkedIn content analysis workflow outputs...")
    assert 'analysis_storage_path' in outputs, "Validation Failed: 'analysis_storage_path' key missing."
    assert 'processed_entity_username' in outputs, "Validation Failed: 'processed_entity_username' key missing."
    assert outputs['processed_entity_username'] == TEST_INPUTS['entity_username'], "Validation Failed: Entity name mismatch."
    assert isinstance(outputs.get('analysis_storage_path'), list), "Validation Failed: analysis_storage_path should be a list."
    assert len(outputs.get('analysis_storage_path', [])) > 0, "Validation Failed: analysis_storage_path is empty."
    # Add more checks if needed, e.g., structure of stored data
    logger.info(f"   Storage path: {outputs.get('analysis_storage_path')}")
    logger.info("✓ Output structure and content validation passed.")
    return True

async def main_test_linkedin_analysis():
    test_name = "LinkedIn Content Analysis Workflow Test V2 -with Joins"
    print(f"--- Starting {test_name} --- ")

    CREATE_FAKE_POSTS = True
    entity_username = TEST_INPUTS["entity_username"]
    test_scraping_namespace = LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE.format(item=entity_username)
    
    # # --- Define Setup & Cleanup Docs ---
    # Setup: Create the input posts document expected by load_posts
    # Example post data (replace with realistic scraped data)
    example_posts_data = [
        # AI and Machine Learning Topic Group
        {
            "urn": "urn:li:share:1",
            "text": "Excited to announce our new AI-powered analytics platform that helps businesses make data-driven decisions faster than ever before. #DataScience #AI #BusinessIntelligence",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2023-05-15",
            "postedDateTimestamp": 1684108800,
            "totalReactionCount": 156,
            "commentsCount": 23,
            "repostsCount": 12
        },
        {
            "urn": "urn:li:share:2",
            "text": "Just published a new article on how machine learning is transforming customer experience in the financial sector. Check it out in the link below! #MachineLearning #FinTech #CustomerExperience",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2023-05-10",
            "postedDateTimestamp": 1683676800,
            "totalReactionCount": 89,
            "commentsCount": 14,
            "repostsCount": 7
        },
        {
            "urn": "urn:li:share:3",
            "text": "Our AI research team just made a breakthrough in natural language processing that improves sentiment analysis accuracy by 23%. This will revolutionize how companies understand customer feedback. #AI #NLP #MachineLearning",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2023-04-28",
            "postedDateTimestamp": 1682640000,
            "totalReactionCount": 203,
            "commentsCount": 35,
            "repostsCount": 19
        },
        {
            "urn": "urn:li:share:4",
            "text": "The future of AI is not just about automation, but augmentation. How can we design systems that enhance human capabilities rather than replace them? Thoughts? #AI #FutureOfWork #HumanAICollaboration",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2023-04-15",
            "postedDateTimestamp": 1681516800,
            "totalReactionCount": 178,
            "commentsCount": 42,
            "repostsCount": 15
        },
        
        # Healthcare Technology Topic Group
        {
            "urn": "urn:li:share:5",
            "text": "Honored to speak at the Global Tech Summit next month about the ethical implications of AI in healthcare. Looking forward to connecting with industry leaders and innovators! #HealthTech #AIEthics #TechConference",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2023-05-05",
            "postedDateTimestamp": 1683244800,
            "totalReactionCount": 211,
            "commentsCount": 31,
            "repostsCount": 18
        },
        {
            "urn": "urn:li:share:6",
            "text": "Our new telemedicine platform has helped rural communities access specialized healthcare services, reducing diagnosis time by 40%. Technology can truly bridge healthcare gaps. #HealthTech #Telemedicine #RuralHealthcare",
            "reposted": False,
            "isBrandPartnership": True,
            "postedDate": "2023-03-22",
            "postedDateTimestamp": 1679443200,
            "totalReactionCount": 167,
            "commentsCount": 29,
            "repostsCount": 24
        },
        {
            "urn": "urn:li:share:7",
            "text": "Wearable health monitoring devices are generating unprecedented amounts of patient data. How do we balance privacy concerns with the potential for improved health outcomes? #HealthTech #DataPrivacy #WearableTech",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2023-03-10",
            "postedDateTimestamp": 1678406400,
            "totalReactionCount": 132,
            "commentsCount": 27,
            "repostsCount": 14
        },
        
        # Cloud Computing Topic Group
        {
            "urn": "urn:li:share:8",
            "text": "Our team just completed a successful implementation of a cloud migration strategy for a Fortune 500 client, resulting in 40% cost reduction and improved system reliability. Proud of what we've accomplished! #CloudComputing #DigitalTransformation #ProjectSuccess",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2023-04-28",
            "postedDateTimestamp": 1682640000,
            "totalReactionCount": 178,
            "commentsCount": 27,
            "repostsCount": 15
        },
        {
            "urn": "urn:li:share:9",
            "text": "Multi-cloud strategies are becoming essential for enterprise resilience. Our latest case study shows how we helped a client avoid vendor lock-in while optimizing for performance. #CloudComputing #MultiCloud #EnterpriseIT",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2023-02-18",
            "postedDateTimestamp": 1676678400,
            "totalReactionCount": 95,
            "commentsCount": 18,
            "repostsCount": 12
        },
        {
            "urn": "urn:li:share:10",
            "text": "Serverless architecture isn't just about cost savings—it's about developer productivity and faster time-to-market. Here's how we're implementing it for our startup clients. #Serverless #CloudComputing #DevOps",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2023-02-05",
            "postedDateTimestamp": 1675555200,
            "totalReactionCount": 143,
            "commentsCount": 22,
            "repostsCount": 17
        },
        
        # Blockchain and Cryptocurrency Topic Group
        {
            "urn": "urn:li:share:11",
            "text": "Interesting research on how blockchain technology is being applied to supply chain management. The potential for transparency and efficiency gains is remarkable. #Blockchain #SupplyChain #Innovation",
            "reposted": True,
            "isBrandPartnership": False,
            "postedDate": "2023-04-20",
            "postedDateTimestamp": 1681948800,
            "totalReactionCount": 132,
            "commentsCount": 19,
            "repostsCount": 22
        },
        {
            "urn": "urn:li:share:12",
            "text": "Beyond cryptocurrency: How blockchain is revolutionizing identity verification and reducing fraud in financial services. Our team's latest project cut verification times by 75%. #Blockchain #DigitalIdentity #FinTech",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2023-01-25",
            "postedDateTimestamp": 1674604800,
            "totalReactionCount": 187,
            "commentsCount": 31,
            "repostsCount": 26
        },
        {
            "urn": "urn:li:share:13",
            "text": "Smart contracts are eliminating intermediaries in legal agreements, but what are the implications for regulatory compliance? Join our webinar next week to learn more. #Blockchain #SmartContracts #LegalTech",
            "reposted": False,
            "isBrandPartnership": True,
            "postedDate": "2023-01-12",
            "postedDateTimestamp": 1673481600,
            "totalReactionCount": 112,
            "commentsCount": 24,
            "repostsCount": 19
        },
        
        # Career and Hiring Topic Group
        {
            "urn": "urn:li:share:14",
            "text": "Thrilled to announce that we're expanding our team! Looking for talented data scientists and ML engineers who are passionate about solving complex problems. DM me if interested or tag someone who might be a good fit. #Hiring #DataScience #MachineLearning #JobOpportunity",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2023-04-15",
            "postedDateTimestamp": 1681516800,
            "totalReactionCount": 245,
            "commentsCount": 42,
            "repostsCount": 31
        },
        {
            "urn": "urn:li:share:15",
            "text": "Career advice for tech professionals: Specialize deeply, but maintain breadth of knowledge. T-shaped skills are still the most valuable in our rapidly evolving industry. #CareerAdvice #TechCareers #ProfessionalDevelopment",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2022-12-10",
            "postedDateTimestamp": 1670630400,
            "totalReactionCount": 321,
            "commentsCount": 57,
            "repostsCount": 42
        },
        {
            "urn": "urn:li:share:16",
            "text": "Remote work has transformed our hiring strategy. We're now able to access global talent and build more diverse teams. How has your organization adapted? #RemoteWork #Hiring #WorkplaceEvolution",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2022-11-28",
            "postedDateTimestamp": 1669593600,
            "totalReactionCount": 276,
            "commentsCount": 48,
            "repostsCount": 33
        },
        
        # Cybersecurity Topic Group
        {
            "urn": "urn:li:share:17",
            "text": "The rise in ransomware attacks demands a new approach to cybersecurity. Our latest white paper outlines a zero-trust architecture that has proven effective for our enterprise clients. #Cybersecurity #ZeroTrust #RansomwareProtection",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2022-11-15",
            "postedDateTimestamp": 1668470400,
            "totalReactionCount": 198,
            "commentsCount": 34,
            "repostsCount": 27
        },
        {
            "urn": "urn:li:share:18",
            "text": "Human error remains the biggest cybersecurity vulnerability. Our security awareness training program has reduced phishing susceptibility by 62% across client organizations. #Cybersecurity #SecurityTraining #PhishingAwareness",
            "reposted": False,
            "isBrandPartnership": True,
            "postedDate": "2022-10-30",
            "postedDateTimestamp": 1667088000,
            "totalReactionCount": 154,
            "commentsCount": 29,
            "repostsCount": 23
        },
        {
            "urn": "urn:li:share:19",
            "text": "As IoT devices proliferate in industrial settings, securing operational technology becomes critical. Here's our approach to OT security that doesn't compromise performance. #Cybersecurity #IoTSecurity #OperationalTechnology",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2022-10-12",
            "postedDateTimestamp": 1665532800,
            "totalReactionCount": 167,
            "commentsCount": 31,
            "repostsCount": 25
        },
        
        # Sustainability and Green Tech Topic Group
        {
            "urn": "urn:li:share:20",
            "text": "Proud that our data centers have achieved carbon neutrality this quarter. Technology companies have a responsibility to lead on climate action. #Sustainability #GreenTech #CarbonNeutral",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2022-09-28",
            "postedDateTimestamp": 1664323200,
            "totalReactionCount": 289,
            "commentsCount": 43,
            "repostsCount": 37
        },
        {
            "urn": "urn:li:share:21",
            "text": "AI is helping optimize energy consumption in smart buildings, reducing costs and environmental impact. Our latest project achieved 28% energy savings for a commercial client. #GreenTech #SmartBuildings #EnergyEfficiency",
            "reposted": False,
            "isBrandPartnership": False,
            "postedDate": "2022-09-15",
            "postedDateTimestamp": 1663200000,
            "totalReactionCount": 213,
            "commentsCount": 37,
            "repostsCount": 29
        },
        {
            "urn": "urn:li:share:22",
            "text": "The circular economy requires rethinking product design from the ground up. Our engineering team is implementing cradle-to-cradle principles in all new hardware development. #CircularEconomy #SustainableDesign #GreenTech",
            "reposted": True,
            "isBrandPartnership": False,
            "postedDate": "2022-08-30",
            "postedDateTimestamp": 1661817600,
            "totalReactionCount": 176,
            "commentsCount": 32,
            "repostsCount": 24
        }
    ]
    setup_docs: List[SetupDocInfo] = [
        {
            'namespace': test_scraping_namespace, 'docname': LINKEDIN_POST_DOCNAME, 'is_versioned': False,
            'initial_data': example_posts_data, # Store the list directly
            'is_shared': False, 'is_system_entity': False,
        }
    ]

    # # Cleanup: Remove the input posts doc and the generated analysis doc
    test_analysis_namespace = CONTENT_ANALYSIS_NAMESPACE_TEMPLATE.format(item=entity_username)
    cleanup_docs: List[CleanupDocInfo] = [
        {'namespace': test_scraping_namespace, 
         'docname': LINKEDIN_POST_DOCNAME, 
         'is_versioned': False, 
         'is_shared': False},
        {'namespace': test_analysis_namespace, 
         'docname': CONTENT_ANALYSIS_DOCNAME, 
         'is_versioned': False, 
         'is_shared': False},
    ]

    # print("--- Setup/Cleanup Definitions ---")
    # print(f"Input Posts Doc: {LINKEDIN_SCRAPING_NAMESPACE}/{input_posts_docname}")
    # print(f"Output Analysis Doc: {ANALYSIS_OUTPUT_NAMESPACE}/{output_analysis_docname}")
    # print("---------------------------------")


    # --- Execute Test (Commented out) ---
    print("\n--- Running Workflow Test (Execution part commented out) ---")
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=TEST_INPUTS,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        setup_docs=setup_docs if CREATE_FAKE_POSTS else [],
        cleanup_docs=cleanup_docs if CREATE_FAKE_POSTS else [],
        validate_output_func=validate_output,
        stream_intermediate_results=True,
        poll_interval_sec=5,
        timeout_sec=1800 # Allow time for multiple LLM calls
    )

    # if 'final_run_status_obj' in locals(): # Check if run_workflow_test was actually called
    #      print(f"Final Status: {final_run_status_obj.status}")
    #      if final_run_outputs:
    #          print(f"Final Outputs: {final_run_outputs}")
    #      if final_run_status_obj.status != WorkflowRunStatus.COMPLETED:
    #           print(f"Error Message: {final_run_status_obj.error_message}")


if __name__ == "__main__":
    print("="*50)
    print("LinkedIn Content Analysis Workflow Definition V2 (with Joins)")
    print("="*50)
    logging.basicConfig(level=logging.INFO) # Basic logging for validation function if run standalone
    # Example placeholder for running the async test function if needed
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
         print("Async event loop already running. Scheduling task...")
         loop.create_task(main_test_linkedin_analysis())
         # In a script, you might need something to keep it alive or run tasks to completion
    else:
         print("Starting new async event loop...")
         asyncio.run(main_test_linkedin_analysis())
