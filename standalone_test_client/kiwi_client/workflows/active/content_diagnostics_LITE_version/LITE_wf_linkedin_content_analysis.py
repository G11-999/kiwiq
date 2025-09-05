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

from kiwi_client.workflows.active.document_models.customer_docs import (
    LITE_LINKEDIN_SCRAPED_POSTS_DOCNAME,
    # Namespace and docname for storing the final analysis result
    LITE_LINKEDIN_SCRAPED_POSTS_NAMESPACE_TEMPLATE,
    LITE_LINKEDIN_CONTENT_ANALYSIS_DOCNAME,
    LITE_LINKEDIN_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
)

from kiwi_client.workflows.active.content_diagnostics_LITE_version.llm_inputs.linkedin_content_analysis import (
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
EXTRACTION_MODEL_FOR_CLASSIFY = "gpt-5-mini"
EXTRACTION_MODEL = "gpt-5" # Model for theme extraction, classification, analysis
LLM_TEMPERATURE = 0.5
LLM_MAX_TOKENS_CLASSIFY = 10000 # Adjust based on batch size and theme complexity
LLM_MAX_TOKENS_THEMES = 10000 # Adjust based on total post text length
LLM_MAX_TOKENS_ANALYSIS = 10000 # Adjust based on theme group size

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
                                                  "input_namespace_field_pattern": LITE_LINKEDIN_SCRAPED_POSTS_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LITE_LINKEDIN_SCRAPED_POSTS_DOCNAME,
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
              "max_tokens": LLM_MAX_TOKENS_THEMES,
              "reasoning_effort_class": "low"
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
                "model_spec": {"provider": LLM_PROVIDER, "model": EXTRACTION_MODEL_FOR_CLASSIFY},
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
        }
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
            "variables": {},
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
                "max_tokens": LLM_MAX_TOKENS_ANALYSIS,
                "reasoning_effort_class": "low"
            },
            "output_schema": {
                "schema_definition": THEME_ANALYSIS_REPORT_SCHEMA,
                "convert_loaded_schema_to_pydantic": False
            }
        }
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
                                            "input_namespace_field_pattern": LITE_LINKEDIN_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LITE_LINKEDIN_CONTENT_ANALYSIS_DOCNAME,
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
      "enable_node_fan_in": True,
      "node_config": {},
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
      ]
    },

    { "src_node_id": "extract_themes", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "structured_output", "dst_field": "extracted_themes", "description": "Store extracted themes structure."},
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
        { "src_field": "mapped_data", "dst_field": "mapped_data", "description": "Pass posts with mapped themes."}
      ]
    },
    { "src_node_id": "$graph_state", "dst_node_id": "group_posts_under_themes", "mappings": [
        { "src_field": "extracted_themes", "dst_field": "extracted_themes", "description": "Pass original themes list for grouping."}
      ]
    },

    # --- Step 8: Theme Analysis ---
    { "src_node_id": "group_posts_under_themes", "dst_node_id": "route_theme_groups", "mappings": [
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

    { "src_node_id": "analyze_theme_group", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "structured_output", "dst_field": "all_theme_reports", "description": "Collect all theme analysis reports."}      ]
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
        { "src_field": "passthrough_data", "dst_field": "passthrough_data" }
    ]}
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
    test_scraping_namespace = LITE_LINKEDIN_SCRAPED_POSTS_NAMESPACE_TEMPLATE.format(item=entity_username)
    
    # # --- Define Setup & Cleanup Docs ---
    # Setup: Create the input posts document expected by load_posts
    # Example post data (replace with realistic scraped data)
    example_posts_data = [
        # AI and Machine Learning Topic Group
        {
          "commentsCount": 3,
          "totalReactionCount": 8,
          "postedDateTimestamp": 1754481636546,
          "urn": "7358829346091945984",
          "text": "Your posts look good but they don’t work.\n\nThat’s what most founders hear when aesthetics \nwin over actual strategy.\n\nThe truth?\n\nYour audience decides in 8 seconds whether they’ll scroll or stay.\n\nThis is where a well-designed carousel \nsteps in like a silent salesperson.\n\nIt builds trust, communicates value, and drives DMs \nwithout being pushy.\n\nThis post breaks down the psychology of high-converting \ncarousels.\n\nNo jargon. No fluff. Just real strategy.\nRead it like your business depends on it because it does.\n\nDive in, \nsave for later, \nand let me know which slide hit you the most.",
          "postedDate": "2025-08-06 12:00:36.546 +0000 UTC",
          "isBrandPartnership": False,
          "contentType": "document"
        },
        # {
        #   "commentsCount": 10,
        #   "totalReactionCount": 18,
        #   "postedDateTimestamp": 1754375788091,
        #   "urn": "7358385385493651456",
        #   "repostsCount": 1,
        #   "postedDate": "2025-08-05 06:36:28.091 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 16,
        #   "totalReactionCount": 14,
        #   "postedDateTimestamp": 1754304924892,
        #   "urn": "7358088163694727169",
        #   "text": "You cannot do designs if you haven't studied in design school\n\nsome random people told me. 🫢 \n\nYet here I am, earning a full-time income doing what I love. \n\nWhen I started, I didn't even know what 'hierarchy' or 'white space' meant. \n\nAll I had was a crazy passion to design something every single day. \n\nI watched tutorials, practiced, failed, created ugly designs, cried, and then designed again. It took me months to land my first paid project. \n\nToday, I'm earning through graphic design and helping others achieve their dreams, too. \n\nIf you're a beginner, remember: It's not about having a fancy degree. \n\n📌 It’s all about consistency, curiosity, and courage. \n\nAre you someone who wants to build a career in freelancing without a degree?\n\nLet’s connect! ✨️",
        #   "postedDate": "2025-08-04 10:55:24.892 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 11,
        #   "totalReactionCount": 22,
        #   "postedDateTimestamp": 1754143002716,
        #   "urn": "7357409012864200704",
        #   "text": "Most designers are stuck in the “post and pray” cycle.\n\n Posting daily. Creating trendy carousels.\nStill invisible. Still no leads. Still wondering what went wrong.\n\nI’ve been there designing in the dark, \nhoping someone notices.\n\nHere’s the truth no one tells you:\nYour content isn’t just about showing your work.\nIt’s about selling your brain.\nThe right content strategy turns strangers into clients \nwithout shouting or selling out.\n\nThat’s why I created a simple 3-part formula that \nchanged the game for me as a solo designer.\n\nNo jargon. No fluff. Just pure, honest strategy.\n\nSwipe through this carousel till the end.\nYou’ll learn how to show up like a brand \nand sell like one too.",
        #   "postedDate": "2025-08-02 13:56:42.716 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 8,
        #   "totalReactionCount": 15,
        #   "postedDateTimestamp": 1753875011727,
        #   "urn": "7356284977187115010",
        #   "text": "You just watched 3 hours of Netflix last night\n\nThat was me too.\n \nSaying I was busy when I was just... distracted.\n\nScrolling, binge-watching, overthinking.\nUntil one day I asked myself\n\nWhat if I gave even 1 hour daily to a skill instead?\n\nI didn’t start with a course.\nI started by Googling things.\nPracticed. Posted.\nFailed. Showed up again.\n\nThat “one hour” turned into a portfolio.\nThat portfolio turned into my first client.\n\nToday, that first ₹500 design turned into ₹XX,XXX/month doing what I love.\n\nAnd I don’t ask my parents for travel money anymore.\n\nSo if you’re a student dreaming of earning\n\nbut waiting for the “right time” to learn—\nmaybe check your screen time instead.\n\nIt’s not lack of time.\nIt’s where you’re spending it.\n\nP.S. What’s stopping you from turning your scroll-time into skill-time?\n\nNetflix won’t fund your weekend plans but freelancing might.",
        #   "postedDate": "2025-07-30 11:30:11.727 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 9,
        #   "totalReactionCount": 26,
        #   "postedDateTimestamp": 1753788623787,
        #   "urn": "7355922639904788480",
        #   "text": "You're not just another soft-spoken coach with beige vibes \nand a Montserrat font... right?\n\nBecause if your content feels like déjà vu, \nyour audience scrolls right past. \n\nThis carousel calls out the copy-paste branding epidemic\nand shows you how to break the blend-in cycle.\n\nIf your visuals vanished tomorrow, would anyone notice?\n\nSwipe through. Audit your brand.\n\nIt’s time to go from forgettable to unmistakable",
        #   "postedDate": "2025-07-29 11:30:23.787 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 16,
        #   "totalReactionCount": 22,
        #   "postedDateTimestamp": 1753702207936,
        #   "urn": "7355560185555243011",
        #   "text": "Tired of asking your parents for money?\n\nRead this 👇\n\nJust 3 year ago, I was that girl:\n\n— No savings\n— No job\n— Always broke after paying tuition & mobile recharge\n— Scared to even ask for travel money\n\nBut today?\nI make ₹XX,XXX/month as a freelancer doing design work from home.\nNo degree from abroad. No fancy laptop.\nJust WiFi, patience & real skills.\n\nWhat changed?\n\nWhile others were preparing for govt jobs,\nI was learning Canva and watching free tutorials.\n\nWhile friends were chilling,\nI built my portfolio using random passion projects.\n\nWhile others waited for placement,\nI created my own client opportunities online.\n\n\n💸 What I learned:\n\n✔ You don’t need a job to start earning.\n✔ Freelancing won’t make you rich overnight but it will teach you freedom.\n✔ It’s okay to start small (even at ₹500).\n✔ No one pays you for being “good at study.” They pay for value.\n\n\n📌 If you’re a student and want to:\n→ Pay your own internet bills\n→ Cover your college trips\n→ Treat your parents without guilt\n\nThen stop waiting.\nStart learning.\nShow up online.\nAsk for opportunities.\n\nOne year from now your bank balance will thank you.\n\n\nLet me know in the comments\nif you want a guide on how to start with zero budget but full passion. \n\nWill share it for free 🌼\n\n#freelancing #students",
        #   "postedDate": "2025-07-28 11:30:07.936 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 11,
        #   "totalReactionCount": 24,
        #   "postedDateTimestamp": 1752924610967,
        #   "urn": "7352298707477778434",
        #   "text": "If you’re not building your name,\nsomeone else will decide your price.\n\nAre you the face of your craft \nor just another profile in the crowd?\n\nFreelancing platforms gave us reach.\nBut did they also remove the reason people choose us?\n\nWhen every designer sells “fast delivery,”\nWhen every gig sounds like “minimal logo in 24 hours,”\nWhat actually separates you from 500 others?\n\nGood work alone isn’t rare anymore.\n\nBut a strong voice, a unique POV, and trust? Still rare.\n\nClients don’t just hire you for what you do.\nThey stay for how you think.\n\nOn platforms, you're defined by keywords, ratings, and delivery time.\nThere’s no room to explain why you design the way you do.\n\nNo space to build a connection, or lead with strategy.\nAnd when price becomes the biggest differentiator\nCreativity often takes a back seat.\n\nBut when you build your personal brand\nYou start attracting, not chasing.\n\nYou share your process, your story, your thinking.\nYou go from “just another designer” to a go-to creative mind.\n\nYou shift from being found by chance\nTo being remembered by choice.\n\nSo tell me\nIs freelancing supposed to make us more visible?\nOr just more replaceable?",
        #   "postedDate": "2025-07-19 11:30:10.967 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 23,
        #   "totalReactionCount": 35,
        #   "postedDateTimestamp": 1752665403610,
        #   "urn": "7351211513023516673",
        #   "text": "Your content has 3 seconds to impress.  \n\nWhat are you doing with it?\n\nMost posts never get that far. A strong hook question, stat, or surprise can boost retention by up to 30% \n\nBut words aren’t enough. \n \nVisuals, lead‑in formatting, and fast story cues matter just as much.\n\nImagine your scroll‑stopping intro and visuals \nworking together drawing people in, not scrolling past.  \n\n📌 DM me “FIRST 3” \n\nI’ll send you my exact hook + visual formula authentic, \nhuman, and proven to convert.  \n\nLet’s make your next post impossible to ignore. 💫",
        #   "postedDate": "2025-07-16 11:30:03.61 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 14,
        #   "totalReactionCount": 37,
        #   "postedDateTimestamp": 1752649938250,
        #   "urn": "7351146646602199042",
        #   "reposted": True,
        #   "repostsCount": 2,
        #   "text": "Stop designing for likes.  \nStart designing for leads.\nSounds harsh? Maybe.  \nBut I learned it the hard way.\n\nI used to spend hours perfecting pretty posts.  \nThey got likes, but never led to real clients.\n\nThen I shifted:\n\n→ I designed for *problems*, not applause  \n→ Wrote for *people*, not algorithms  \n→ And started getting leads consistently\n\nBecause design isn’t decoration.  \n\nIt’s communication.\n\nIf you’re tired of being the “underrated designer”  \nand ready to be the go-to designer\n\nDM me “REAL DESIGN”  \nI’ll show you how I made the switch. 💫",
        #   "postedDate": "2025-07-16 07:12:18.25 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 14,
        #   "totalReactionCount": 37,
        #   "postedDateTimestamp": 1752579001706,
        #   "urn": "7350849117171896322",
        #   "repostsCount": 2,
        #   "text": "Stop designing for likes.  \nStart designing for leads.\nSounds harsh? Maybe.  \nBut I learned it the hard way.\n\nI used to spend hours perfecting pretty posts.  \nThey got likes, but never led to real clients.\n\nThen I shifted:\n\n→ I designed for *problems*, not applause  \n→ Wrote for *people*, not algorithms  \n→ And started getting leads consistently\n\nBecause design isn’t decoration.  \n\nIt’s communication.\n\nIf you’re tired of being the “underrated designer”  \nand ready to be the go-to designer\n\nDM me “REAL DESIGN”  \nI’ll show you how I made the switch. 💫",
        #   "postedDate": "2025-07-15 11:30:01.706 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 13,
        #   "totalReactionCount": 22,
        #   "postedDateTimestamp": 1752235204700,
        #   "urn": "7349407128014528512",
        #   "text": "My first-ever client paid me ₹500.\nAnd honestly? It was a disaster.\n\nI was excited. Nervous.\nDesperate to prove myself.\nSo I said yes to everything:\n → Unlimited revisions\n → Midnight edits\n → Free extras\n → Constant calls\n\n All for ₹500.\n\nBy the time I delivered the final design,\nI was exhausted, frustrated, and questioning if I was even meant for this.\n\nBut here’s what I learned:\n1. Saying “yes” to everything ≠ being professional.\n It just burns you out.\n Clear boundaries build real respect.\n2. Charging less doesn’t make clients value you more.\n If anything, they value you less.\n3. Confidence doesn’t come before action.\n It comes from doing the hard things, learning, and growing.\nThat ₹500 project was messy but it taught me the foundation of everything I do today.\n\nSo if you’re charging peanuts and feeling stuck—\nPlease don’t quit.\nYou’re not failing.\n\nYou’re learning.\n\nYour ₹500 client is not the full story.\nIt’s just the first chapter.\n\nStill stuck at low-paying clients?\nDM me “GROWTH” \nI’ll share what helped me level up.",
        #   "postedDate": "2025-07-11 12:00:04.7 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 20,
        #   "totalReactionCount": 34,
        #   "postedDateTimestamp": 1752065882327,
        #   "urn": "7348696938508185600",
        #   "text": "“You must be burning out managing all that!”\n\n I hear this every time I share what I do.\n👉 3 businesses.\n 👉 Client projects, content creation, coaching.\n 👉 All while staying consistent without burning out.\n\nBut here’s the truth:\nI don’t rely on motivation.\nI don’t work till midnight.\nAnd I never guess what I’m doing each day.\n\nI run on systems, not stress.\nClarity + structure = calm productivity.\nMy weekly system helps me:\n ✅ Plan high-priority work ahead of time\n ✅ Pre-schedule client and content tasks\n ✅ Keep coaching aligned with my goals\n ✅ Make time for growth and rest\n\nAnd nope, it’s not complicated. It’s intentional.\n\nIf you’re juggling between:\n — Design projects\n — Building your content brand\n — And mentoring or coaching\n\nDM me “SYSTEM”\n\nI’ll share my personal weekly planner + task map with you \n\n(the exact one I use to run 3 businesses without overwhelm).\n\nLet’s build your calm, profitable workflow.\nOne system at a time.",
        #   "postedDate": "2025-07-09 12:58:02.327 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 5,
        #   "totalReactionCount": 20,
        #   "postedDateTimestamp": 1751976902139,
        #   "urn": "7348323728549691392",
        #   "text": "Why 95% of designers never get consistent clients\n(even if they’re incredibly talented)\n\nHard truth?\nPosting your work isn't enough anymore.\nI used to be stuck in that loop.\nProjects came in randomly...\nThen nothing for weeks.\n\nI did everything:\n — Posted my carousels\n — Replied to job boards\n — Tried freelancing platforms\n\nBut still—\nNo system.\nNo stability.\nNo clients I actually wanted to work with.\n\nHere’s what changed the game for me:\nI stopped selling “designs”\nand started selling solutions.\n\nInstead of saying:\n“I design carousels”\n\nI started saying:\n“I help entrepreneurs turn their knowledge into scroll-stopping content that drives leads and sales.”\n\nThat tiny shift?\nBooked me out for three months straight.\n\nHere’s the truth:\nClients don’t care about pretty designs.\n They care about what those designs do for their business.\nWhen you position yourself as a partner\n not just a designer\n everything shifts.\n\nIf you're tired of the income rollercoaster,\n you don’t need to work harder.\n You need to position smarter.\n\nWant to know how I did it?\n\nDM me “POSITIONING”\n and I’ll walk you through the exact shift.",
        #   "postedDate": "2025-07-08 12:15:02.139 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 22,
        #   "totalReactionCount": 35,
        #   "postedDateTimestamp": 1751946777917,
        #   "urn": "7348197378404904961",
        #   "reposted": True,
        #   "repostsCount": 3,
        #   "text": "I didn’t feel like I belonged.”\nThat one thought almost made me quit.\n\nEvery time I hit publish,\nI’d second-guess myself.\n“Who am I to talk about design?”\n“Why would anyone listen to me?”\n“I’m not expert enough. Not skilled enough. Not ‘ready’ yet.”\n\nIt wasn’t lack of skill holding me back\nIt was imposter syndrome.\n\nBut here’s what changed everything for me:\nI stopped waiting to feel confident.\nI started showing up with the doubt, not in spite of it.\n\nInstead of fighting those thoughts, I studied them:\n → Where were they coming from?\n → Were they even true?\n → Would I say the same things to a friend in my shoes?\nThe truth is:\n You don’t overcome imposter syndrome by proving yourself to others.\n You overcome it by learning to trust your journey.\nI built confidence not from validation—\n but from consistency.\nI kept creating.\n Kept sharing.\n Kept learning out loud.\nAnd slowly, I became the kind of designer I once thought I could never be.\nIf you’re in that spiral right now, this is your reminder:\nYou're not alone.\n You're not behind.\n You're not an imposter.\nYou’re just early.\nAnd that’s exactly where you’re supposed to be.\nIf this hits home, DM me CONFIDENCE.\n\nLet’s talk about how you can grow as a designer \nwithout waiting for permission.",
        #   "postedDate": "2025-07-08 03:52:57.917 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 22,
        #   "totalReactionCount": 35,
        #   "postedDateTimestamp": 1751889608616,
        #   "urn": "7347957592977043457",
        #   "repostsCount": 3,
        #   "text": "I didn’t feel like I belonged.”\nThat one thought almost made me quit.\n\nEvery time I hit publish,\nI’d second-guess myself.\n“Who am I to talk about design?”\n“Why would anyone listen to me?”\n“I’m not expert enough. Not skilled enough. Not ‘ready’ yet.”\n\nIt wasn’t lack of skill holding me back\nIt was imposter syndrome.\n\nBut here’s what changed everything for me:\nI stopped waiting to feel confident.\nI started showing up with the doubt, not in spite of it.\n\nInstead of fighting those thoughts, I studied them:\n → Where were they coming from?\n → Were they even true?\n → Would I say the same things to a friend in my shoes?\nThe truth is:\n You don’t overcome imposter syndrome by proving yourself to others.\n You overcome it by learning to trust your journey.\nI built confidence not from validation—\n but from consistency.\nI kept creating.\n Kept sharing.\n Kept learning out loud.\nAnd slowly, I became the kind of designer I once thought I could never be.\nIf you’re in that spiral right now, this is your reminder:\nYou're not alone.\n You're not behind.\n You're not an imposter.\nYou’re just early.\nAnd that’s exactly where you’re supposed to be.\nIf this hits home, DM me CONFIDENCE.\n\nLet’s talk about how you can grow as a designer \nwithout waiting for permission.",
        #   "postedDate": "2025-07-07 12:00:08.616 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 13,
        #   "totalReactionCount": 39,
        #   "postedDateTimestamp": 1751630418018,
        #   "urn": "7346870468815069186",
        #   "repostsCount": 2,
        #   "text": "Freelancers, \nIf burnout is your BFF right now... \nthis one’s for you.\n\nYou didn’t become a freelancer to burn out like a corporate robot.\n\nBut here we are.  \nNo boundaries.  \nNo systems.  \nJust guilt and deadlines.\n\nThis carousel is your permission slip to slow down, reset, and protect your creative energy.\n\nRead it. Breathe.  \nAnd if you want my burnout-busting system, DM me “SYSTEM.”\n\nP.S. Your laptop isn’t your life partner. Shut it down sometimes. 🤭",
        #   "postedDate": "2025-07-04 12:00:18.018 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 11,
        #   "totalReactionCount": 32,
        #   "postedDateTimestamp": 1751512399176,
        #   "urn": "7346375461913956352",
        #   "reposted": True,
        #   "repostsCount": 1,
        #   "text": "I just saw another entrepreneur trying to DIY their brand \nwith ChatGPT and Canva… and calling it branding.\n\nAnd I couldn’t help but smile.\nBecause I get it. We’ve all been there.\nDoing everything alone. Keeping costs low.\n\nTrying to make it work with tools that feel easy and accessible.\n\n✋🏼 But let’s get real for a sec.\n\nCanva? Love it.\nChatGPT? Big fan.\nBut if you think branding = logo + colors + pretty templates…\nYou’re missing the soul of it.\n\nA brand is not a Canva template.\n\nIt’s not pastel shades or a catchy tagline.\nIt’s the memory you leave behind.\n\nThe emotion someone feels when they land on your page.\nThe vibe. The voice. The energy.\n\nThat’s not something AI can fully create.\nIt can only mimic it. Never feel it.\n\nSo if you're here to build something meaningful,\nDon’t let a generic template speak for your vision.\nBuild a brand that actually feels like you.\n\nI help entrepreneurs and creators craft memorable visual identities.\n\nIf you’re done with DIY and ready to be seen—\n\nDM me “BRAND” and let’s talk.",
        #   "postedDate": "2025-07-03 03:13:19.176 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 11,
        #   "totalReactionCount": 32,
        #   "postedDateTimestamp": 1751457610649,
        #   "urn": "7346145662176043008",
        #   "repostsCount": 1,
        #   "text": "I just saw another entrepreneur trying to DIY their brand \nwith ChatGPT and Canva… and calling it branding.\n\nAnd I couldn’t help but smile.\nBecause I get it. We’ve all been there.\nDoing everything alone. Keeping costs low.\n\nTrying to make it work with tools that feel easy and accessible.\n\n✋🏼 But let’s get real for a sec.\n\nCanva? Love it.\nChatGPT? Big fan.\nBut if you think branding = logo + colors + pretty templates…\nYou’re missing the soul of it.\n\nA brand is not a Canva template.\n\nIt’s not pastel shades or a catchy tagline.\nIt’s the memory you leave behind.\n\nThe emotion someone feels when they land on your page.\nThe vibe. The voice. The energy.\n\nThat’s not something AI can fully create.\nIt can only mimic it. Never feel it.\n\nSo if you're here to build something meaningful,\nDon’t let a generic template speak for your vision.\nBuild a brand that actually feels like you.\n\nI help entrepreneurs and creators craft memorable visual identities.\n\nIf you’re done with DIY and ready to be seen—\n\nDM me “BRAND” and let’s talk.",
        #   "postedDate": "2025-07-02 12:00:10.649 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 16,
        #   "totalReactionCount": 29,
        #   "postedDateTimestamp": 1751338522289,
        #   "urn": "7345646169391251456",
        #   "reposted": True,
        #   "repostsCount": 3,
        #   "text": "Think AI will replace designers?  \nHere’s what no one’s saying out loud.\n\nAI is fast. Smart. Accessible.  \nBut design—real design—is emotional intelligence in pixels.\n\nAs a designer, you don’t just decorate.  \nYou decode what a brand *feels like*  \nAnd translate it into visual identity.\n\nThis is your edge.  \nThis is why you’re irreplaceable.\n\nRead the carousel to discover the mindset shift you need.\n\nAnd if you’re serious about designing with depth in this AI age,  \nDM me “Design” \nI’ve got something for you.",
        #   "postedDate": "2025-07-01 02:55:22.289 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 16,
        #   "totalReactionCount": 29,
        #   "postedDateTimestamp": 1751284812478,
        #   "urn": "7345420894116245504",
        #   "repostsCount": 3,
        #   "text": "Think AI will replace designers?  \nHere’s what no one’s saying out loud.\n\nAI is fast. Smart. Accessible.  \nBut design—real design—is emotional intelligence in pixels.\n\nAs a designer, you don’t just decorate.  \nYou decode what a brand *feels like*  \nAnd translate it into visual identity.\n\nThis is your edge.  \nThis is why you’re irreplaceable.\n\nRead the carousel to discover the mindset shift you need.\n\nAnd if you’re serious about designing with depth in this AI age,  \nDM me “Design” \nI’ve got something for you.",
        #   "postedDate": "2025-06-30 12:00:12.478 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 13,
        #   "totalReactionCount": 24,
        #   "postedDateTimestamp": 1750750663704,
        #   "urn": "7343180511776862208",
        #   "reposted": True,
        #   "repostsCount": 1,
        #   "text": "3 years ago, I was this close to quitting freelancing.\n\nAnd no, it wasn’t a dramatic moment.\nIt was just… another day with no clients, no leads, and too many people asking,\n“Why don’t you just get a job?”\n\nI still remember staring at my screen.\nPortfolio open.\nInbox empty.\nMy mind full of doubts.\n\nI started freelancing because I loved designing.\nI loved the freedom, the creativity, the idea of working for myself.\nBut at that moment, it felt like nothing was working for me.\n\nNo one told me how lonely it would feel.\nHow hard it would be to prove my worth.\nHow often I’d question myself.\n\nAnd the worst part?\nI was doing everything I was “supposed to.”\nI had decent work.\nI was showing up online.\nI was learning new tools.\nStill, no one was seeing me.\n\nBut then something shifted.\n\nI stopped trying to look like a freelancer.\nAnd started thinking like a brand.\n\n➡️ I focused on who I wanted to serve.\n➡️ I cleaned up my LinkedIn.\n➡️ I worked on how I present my story, my visuals, my voice.\n➡️ I stopped chasing gigs and started building trust.\n\nIt didn’t happen overnight.\nBut slowly, things changed.\n\nPeople started noticing.\nI got my first inbound client.\nThen my first international project.\nThen came students who wanted to learn what I was doing.\n\nI didn’t quit.\nAnd I’m so glad I didn’t.\n\nBecause now, I wake up to DMs from people who say,\n“Your story made me feel seen.”\n“Your content helped me take the next step.”\n“Can we work together?”\n\n\nSo if you’re in that place where nothing seems to be working,\njust know you’re not alone.\nAnd no, you don’t need to quit.\nYou just need to realign.\n\nIf this felt like I was reading your diary out loud…\nmaybe it’s time we turned the page together.\n\nStick around.\nI’m not just sharing tips \nI’m building a space for creatives who are ready to make this work, without losing themselves in the noise.\n\nYou in?",
        #   "postedDate": "2025-06-24 07:37:43.704 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 13,
        #   "totalReactionCount": 24,
        #   "postedDateTimestamp": 1750680007268,
        #   "urn": "7342884157204701184",
        #   "repostsCount": 1,
        #   "text": "3 years ago, I was this close to quitting freelancing.\n\nAnd no, it wasn’t a dramatic moment.\nIt was just… another day with no clients, no leads, and too many people asking,\n“Why don’t you just get a job?”\n\nI still remember staring at my screen.\nPortfolio open.\nInbox empty.\nMy mind full of doubts.\n\nI started freelancing because I loved designing.\nI loved the freedom, the creativity, the idea of working for myself.\nBut at that moment, it felt like nothing was working for me.\n\nNo one told me how lonely it would feel.\nHow hard it would be to prove my worth.\nHow often I’d question myself.\n\nAnd the worst part?\nI was doing everything I was “supposed to.”\nI had decent work.\nI was showing up online.\nI was learning new tools.\nStill, no one was seeing me.\n\nBut then something shifted.\n\nI stopped trying to look like a freelancer.\nAnd started thinking like a brand.\n\n➡️ I focused on who I wanted to serve.\n➡️ I cleaned up my LinkedIn.\n➡️ I worked on how I present my story, my visuals, my voice.\n➡️ I stopped chasing gigs and started building trust.\n\nIt didn’t happen overnight.\nBut slowly, things changed.\n\nPeople started noticing.\nI got my first inbound client.\nThen my first international project.\nThen came students who wanted to learn what I was doing.\n\nI didn’t quit.\nAnd I’m so glad I didn’t.\n\nBecause now, I wake up to DMs from people who say,\n“Your story made me feel seen.”\n“Your content helped me take the next step.”\n“Can we work together?”\n\n\nSo if you’re in that place where nothing seems to be working,\njust know you’re not alone.\nAnd no, you don’t need to quit.\nYou just need to realign.\n\nIf this felt like I was reading your diary out loud…\nmaybe it’s time we turned the page together.\n\nStick around.\nI’m not just sharing tips \nI’m building a space for creatives who are ready to make this work, without losing themselves in the noise.\n\nYou in?",
        #   "postedDate": "2025-06-23 12:00:07.268 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 15,
        #   "totalReactionCount": 38,
        #   "postedDateTimestamp": 1750420814311,
        #   "urn": "7341797023148371968",
        #   "repostsCount": 1,
        #   "text": "Somewhere between choosing a trendy font\nand writing a “killer” bio…\nyou forgot to be you.\nI’ve worked with founders, coaches, and creators\nwho felt this exact thing:\n“I’m posting consistently… but something’s not clicking.”\nTheir content was solid.\n\nAesthetics? On point.\nEven thousands of followers.\nBut still — no real growth.\nNo real connection.\nNo real clients.\n\nHere’s the truth no one says loud enough:\nYour personal brand isn’t what you post.\nIt’s what people remember after they see you once.\n\nAnd most people?\nThey’re blending in, not standing out.\n\nIf your design looks good\nbut your message feels hollow…\nYou don’t need to start over.\nYou just need to realign.\n\nI help founders and personal brands grow an intentional presence online\nthat connects, converts, and creates a real audience.\n\nIf you’re building something meaningful let’s talk.\n\nThe full breakdown is in the carousel.\nIt’s worth a swipe if you’ve been showing up…\nbut still feel unseen.",
        #   "postedDate": "2025-06-20 12:00:14.311 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 36,
        #   "totalReactionCount": 64,
        #   "postedDateTimestamp": 1750316403439,
        #   "urn": "7341359092210290689",
        #   "reposted": True,
        #   "repostsCount": 2,
        #   "text": "5 carousels. 0 leads. 0 DMs. 0 clients.\nIf that’s your current content situation… this one’s for you.\nWe’re told:\n “Just post consistently.”\n “Make it aesthetic.”\n “Add value.”\n\nBut no one talks about the gap between effort and outcome.\nYour designs might look good.\nBut do they actually work?\n\nI used to obsess over colors, fonts, layouts.\nBut my best-performing post?\nThe simplest one.\n\nIt got 43 reposts and 3 leads — not because it was pretty,\nbut because it spoke to the right person.\nThat changed everything.\n\nNot just for me, but for my clients too.\nCoaches. Founders. Creators.\n\nPeople just like you showing up consistently but still not seeing results.\nSo I stopped designing for likes.\n\nAnd started designing for clarity. connection. conversion.\n\nIf you feel like your content is being ignored,\nplease swipe through this carousel.\n\nIt’ll help you see where the disconnect actually is —\nand how you can fix it without “doing more.”\n\nLet your slides speak with purpose, not just presence.\nIf this resonates and you're tired of guessing what’s not working \nYou can always DM me “Clarity”\nI'll take a look and offer honest, specific feedback. \nNo pitch. Just help.",
        #   "postedDate": "2025-06-19 07:00:03.439 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 36,
        #   "totalReactionCount": 64,
        #   "postedDateTimestamp": 1750248006891,
        #   "urn": "7341072216295395328",
        #   "repostsCount": 2,
        #   "text": "5 carousels. 0 leads. 0 DMs. 0 clients.\nIf that’s your current content situation… this one’s for you.\nWe’re told:\n “Just post consistently.”\n “Make it aesthetic.”\n “Add value.”\n\nBut no one talks about the gap between effort and outcome.\nYour designs might look good.\nBut do they actually work?\n\nI used to obsess over colors, fonts, layouts.\nBut my best-performing post?\nThe simplest one.\n\nIt got 43 reposts and 3 leads — not because it was pretty,\nbut because it spoke to the right person.\nThat changed everything.\n\nNot just for me, but for my clients too.\nCoaches. Founders. Creators.\n\nPeople just like you showing up consistently but still not seeing results.\nSo I stopped designing for likes.\n\nAnd started designing for clarity. connection. conversion.\n\nIf you feel like your content is being ignored,\nplease swipe through this carousel.\n\nIt’ll help you see where the disconnect actually is —\nand how you can fix it without “doing more.”\n\nLet your slides speak with purpose, not just presence.\nIf this resonates and you're tired of guessing what’s not working \nYou can always DM me “Clarity”\nI'll take a look and offer honest, specific feedback. \nNo pitch. Just help.",
        #   "postedDate": "2025-06-18 12:00:06.891 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 26,
        #   "totalReactionCount": 38,
        #   "postedDateTimestamp": 1750161612880,
        #   "urn": "7340709853549469696",
        #   "text": "I gained 100+ followers in a single day.\nNo ads. No viral tricks.\n\nJust one clear LinkedIn strategy\nbuilt around me and my people.\nAnd it didn’t just bring numbers.\n\nIt brought real conversations and client inquiries.\n\nStill posting every day, but no leads?\nYou’re consistent. You show up.\nBut your growth feels slow.\nAnd your DMs? Quiet.\n\nIt’s not that you’re not good enough.\nYou’re just not using a plan that fits you.\nWhat you need isn’t more content.\nIt’s a direction.\n\nSomething that reflects your voice, your vision, your people.\n\nHere’s what I did differently (and what I do for my clients, too):\n→ I simplified my content pillars.\n I stopped talking about everything and focused on three areas:\n one to attract, one to connect, one to convert.\n→ I updated my profile to speak for me.\n Not a bio that introduces me—\n But one that shows how I can help the person reading it.\n→ I used what I call the “Reverse Mirror” content format.\n It’s not storytelling.\n It’s showing your people their own thoughts before they say them.\n That’s what builds trust.\n→ I made my CTA super clear.\n Not “DM me to work together.”\n Instead, I made it easy. Simple.\n DM me a word. No pressure. No awkwardness.\n\nWant a strategy that finally feels right for you?\nDM me “strategy”\n\nAnd I’ll walk you through the exact steps I used—\nNo pressure, no fluff.\n\nP.S.\nThe right people are watching.\nThey just need to see the real you, clearly.",
        #   "postedDate": "2025-06-17 12:00:12.88 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 31,
        #   "totalReactionCount": 48,
        #   "postedDateTimestamp": 1749968101118,
        #   "urn": "7339898206392152064",
        #   "repostsCount": 2,
        #   "text": "I don’t use AI to pick colors for my designs  \nhere’s why that’s a game-changer\n\nAnd how that choice led to \n43 reposts and 200+ reactions on just one post\n\nIn a world flooded with AI tools suggesting “perfect” palettes \nI still go back to the basics: emotion, psychology, storytelling.\nBecause no matter how smart AI gets, it still can’t feel color.\n\nLast week, \nI posted a fun and educational breakdown of color theory —\nAnd it worked.\nWhy?\nI solved one real, everyday problem:\nChoosing the right color.\n\nEven experienced designers struggle with it —\nBecause colors speak emotions, and emotions need context.\nThat’s where the human eye still wins.\n\nIn today’s carousel, I’m decoding the psychology behind:\n – Monochromatic reds (from flirty to fierce)\n – Blues (from soft to boss mode)\n – Yellows (from bright to bold)\n\nYou’ll see:\n • What these tones really communicate\n • Real-life brand examples that nailed it\n • Fun facts AI tools won’t teach you\n\nRead till the end \nit’s designed to help you rethink your colors with confidence.\n\nAnd if you want a custom palette that actually \nreflects your brand’s vibe \nComment “COLOR GEEK” and I’ll send something your way.",
        #   "postedDate": "2025-06-15 06:15:01.118 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 18,
        #   "totalReactionCount": 30,
        #   "postedDateTimestamp": 1749644731231,
        #   "urn": "7338541894781542420",
        #   "text": "I never thought I’d write this.\n\nBut today, I have to \nfor every freelancer who got ghosted after giving their best.\n\nA client hired me to manage their LinkedIn for 3 months.\nContent strategy, writing, commenting, growth…\nI was all in.\n\nI created consistent posts \nSometimes 4, sometimes 6 \nWhatever felt right to get results.\n\nAnd suddenly…\nHe changed the password.\nI got logged out.\nAnd he said,\n“You don’t need to continue anymore.”\n\nNo warning. No proper closure. Just like that.\n\nI asked for my payment.\nHe said — “Wait a few days. I’ll pay when I get my money.”\n\nAnd then this:\n“My money is stuck, even 10x more than yours.”\n\nWait… how do you even know how much I earn?\nWhy compare?\nWhy make me feel guilty for asking what’s mine?\n\nThis is not just about money.\nIt’s about respect.\n\n🛑 So how can we, as freelancers, protect ourselves?\n\n1️⃣ Sign a contract.\nWrite everything.\nScope, timeline, payment terms, exand it clause.\n\n2️⃣ Don’t work on just words.\nIf it’s not written, it doesn’t exist.\n\n3️⃣ If they say “I’ll pay later,” politely walk away.\nYou deserve better. There are better clients out there.\n\nAnd now, to the kind, humble clients reading this:\n\n💛 If you want quality work, pay fairly — and on time.\n💛 Treat freelancers as equals, not employees.\n💛 Freelancing means we choose to work with you, not under you.\n\nWe don’t just work for money.\nWe work for meaning.\nBut that doesn’t mean we work for free.\n\nThis story may sound personal — because it is.\nBut it’s also a shared experience.\n\nLet’s build a world where freelancers feel safe, valued, and respected.\n\nBecause when we thrive, you thrive.",
        #   "postedDate": "2025-06-11 12:25:31.231 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 15,
        #   "totalReactionCount": 24,
        #   "postedDateTimestamp": 1749558606230,
        #   "urn": "7338180660345323523",
        #   "repostsCount": 1,
        #   "text": "You’re working way too hard as a freelancer.\nAnd it’s not even your fault.\nNobody told us there’s a faster way to do things.\n\nUntil AI walked in.\nNot to replace us.\nBut to save us time.\nHours of time.\n\nThis carousel walks you through 4 AI tools I’ve seen \nfreelancers, designers, and solopreneurs use to work faster, \ndeliver better, and actually breathe in between client projects.\n\nEach tool comes with:\nWhat it does\nHow to use it\nReal-life client use-cases\n\nAnd yes, \nI kept it simple. Because learning AI should feel exciting, \nnot exhausting.\n\nSave it.\nShare it with your freelancer friends.\n\nAnd if you’ve already tried any of these tools, \ntell me your go-to trick in the comments.\n\nLet’s make work easier in 2025. Not harder.",
        #   "postedDate": "2025-06-10 12:30:06.23 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 65,
        #   "totalReactionCount": 137,
        #   "postedDateTimestamp": 1749389403992,
        #   "urn": "7337470974721724416",
        #   "repostsCount": 6,
        #   "text": "Most people pick fonts like they pick snacks\nwhatever looks good at that moment.\n\nBut what if I told you…\nyour font choice is silently shaping your brand’s entire vibe?\n\n📌 This carousel breaks down typography like your chillest friend would:\n📌 What typography actually is (not what they taught in school)\n📌 Why “Playfair Display” and “Comic Sans” are not the same species\n📌 What makes a typeface feel bold, elegant, or trustworthy\n📌 Real-life font examples from brands you already know\n📌 One golden rule most designers break (that ruins everything)\n\nAnd no, it’s not a lecture.\nIt’s fun.  \nIt’s the type of post you’ll save, use, and remember.\nSwipe till the end — \nI’ve left a small surprise for those who \nalways struggle with font pairing.\n\nWant your brand to stop looking “almost there” \nand start feeling unforgettable?\n\nSend me a message with “TYPO” \nI’ll help you pick font combos that fit your energy, \nnot just your feed.",
        #   "postedDate": "2025-06-08 13:30:03.992 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        {
          "commentsCount": 60,
          "totalReactionCount": 232,
          "postedDateTimestamp": 1749211207700,
          "urn": "7336723565301374977",
          "repostsCount": 45,
          "text": "Here’s a fun, visual breakdown of color theory \nnot the boring kind you snoozed through in school, \nbut the kind that makes your \ncontent pop, sell, and look like you know what you’re doing.\n\nI covered:\nThe color wheel (finally makes sense)\n\nReal brand examples (McDonald’s was no accident)\n\nWhat colors feel like and why that matters\n\nThe 60-30-10 rule designers swear by\n\nSwipe through this carousel \nto finally understand what makes colors work  \nand how to use them without looking like you threw paint on the wall and prayed.\n\nCreating a brand? \nDesigning for yourself?\n\nDM me “COLORS” and I’ll help you build a palette that sells.\n\nSave this post if you never want to panic-choose colors again.",
          "postedDate": "2025-06-06 12:00:07.7 +0000 UTC",
          "isBrandPartnership": False,
          "contentType": "document"
        },
        {
          "commentsCount": 19,
          "totalReactionCount": 35,
          "postedDateTimestamp": 1748964685797,
          "urn": "7335689577497591808",
          "text": "Turn 1 Project into 30 Days of LinkedIn Posts\nCollab with the amazing MAIMOONA GHANI 🤍\nA Web Strategist I truly admire!\n\nWe broke it down into 5 practical rules + 1 powerful bonus tip to help you never run out of content again \n📌 Rule #1 – Make It Emotionally Relatable\n 📌 Rule #2 – Frame It Like a Roadmap\n 📌 Rule #3 – Share a Lesson from a Mistake\n 📌 Rule #4 – Repurpose Like a Pro\n 📌 Rule #5 – Use CTAs That Spark Conversation\n ➕ a humble bonus at the end just for you \n\nWhether you're a designer, coach, creator, or founder\nthis will help you turn your client wins into daily content gold.\n\nRead till the end, save it for later & tell us—\nWhich rule hit you the most?",
          "postedDate": "2025-06-03 15:31:25.797 +0000 UTC",
          "isBrandPartnership": False,
          "contentType": "document"
        },
        # {
        #   "commentsCount": 12,
        #   "totalReactionCount": 28,
        #   "postedDateTimestamp": 1748433601222,
        #   "urn": "7333462047340277760",
        #   "text": "Most creators don't have a content problem.\nThey have a content design problem.\n\nYou post valuable insights—but the wrong visual flow is costing you attention, saves, and leads.\n\nI recently helped a solo coach 2.4x her \ncontent saves with one shift in visual hierarchy.\n\nNo trendy templates.\nNo clickbait.\nJust strategy that actually converts.\n\nI broke down the exact move in this carousel.\nSwipe through to learn it. \nRead till the end your next post might thank you.\n\nAnd if you want me to take a look at your current content?\nDM me \"DESIGN\" and I’ll show you what to tweak first.",
        #   "postedDate": "2025-05-28 12:00:01.222 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 21,
        #   "totalReactionCount": 25,
        #   "postedDateTimestamp": 1748326030815,
        #   "urn": "7333010864351940608",
        #   "text": "WE ARE HIRING! \nVIDEO EDITORS — YES, YOU! 🔥\n\n\nAre you the type who gets weirdly excited about transitions?\n\nDo you vibe with audio beats harder than your playlist does?\n\nDo you want to grow, learn, and laugh while working on awesome content?\n\nWell then... slide into our DMs (or inbox) because we're looking for YOU. 😄\n\n📌Here’s the deal:\nGrowth mindset is our jam.\nWe’re not just editing videos. We’re building futures here  yours, ours, and our clients'.\n\nFriendly human beings only.\nNo ego, no drama. Just good vibes, memes, feedback loops, and “Did you try this effect?” convos.\n\nFreelancing basis.\nThis isn’t your boring 9–5. It's project-based, flexible, and remote.\n\nPerfect for you if you're starting out but SERIOUS about showing up and making epic stuff.\n\nWe want you to enjoy the work.\n\nLike actually enjoy it. Not “ugh another clip to trim” but “ooo can’t wait to spice this up!”\nThink this sounds like your tribe?\n\nDrop your portfolio (even if it’s small), a fun intro about you, and why you love editing! \n\nLet’s grow together, creatively and professionally.😊\n\n📌Share this post with your friends who need this!! 🍀",
        #   "postedDate": "2025-05-27 06:07:10.815 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 21,
        #   "totalReactionCount": 45,
        #   "postedDateTimestamp": 1748242802748,
        #   "urn": "7332661780537581569",
        #   "text": "You spent hours recording, editing, and publishing it…\nAnd all it gets is “New episode is live!” and one sad LinkedIn post?\n\nC’mon. \nYou’re leaving 90% of your content potential untouched.\nSwipe through this carousel 👉\n\nAnd I’ll show you \nhow to turn 1 podcast episode into 10+ content assets \nthat actually grow your audience, build authority, \nand create leads.\n\nNo AI hacks. No fluff.\n\nJust smart, organic repurposing that works like a content machine.\n\nBonus: Want me to personally review your last \npodcast episode and tell you what assets you can create from it?\n\nComment “REPURPOSE GOLD” a\nnd I’ll DM you a quick breakdown (free).\n\nSave this for your next content day.\nLet your podcast work harder—so you don’t have to.",
        #   "postedDate": "2025-05-26 07:00:02.748 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 15,
        #   "totalReactionCount": 30,
        #   "postedDateTimestamp": 1748089802559,
        #   "urn": "7332020051232862209",
        #   "text": "Slow growth. Steady progress. Long-term vision.\nThat’s how I’m building my design business.\n\nNot in a rush.\nNot comparing my journey to others.\nJust focused on showing up every single day with intention.\n\nLately, I’ve been investing deeply in myself—\nBecause I believe growth starts from within.\n\nHere’s what I’m actively working on:\n– Sharpening my design skills to deliver more clarity and impact\n – Learning video editing—because I truly believe it's an essential skill for today’s content creators\n\n – Writing better scripts and captions that engage and connect\n – Documenting my journey and lessons every step of the way\n – Celebrating every win, no matter how small, because it all adds up\nThe shift in mindset has been powerful.\n\nI’ve stopped thinking like a freelancer and started thinking like a creative entrepreneur.\n\nI don’t just deliver designs—I create systems, experiences, and strategies for my clients.\n And it’s working.\n– I’m attracting better-fit clients\n – I’m getting inbound leads through my content\n – I’m having conversations that go beyond price and center around value\n – Most importantly, I’m becoming the kind of designer I once looked up to\nThis is not a highlight reel.\n\n It’s the quiet, consistent work behind the scenes that no one claps for.\n But it’s exactly what’s moving me forward.\n\nIf you're building slow and steady too—don’t underestimate it.\n You're laying a foundation that won’t break under pressure.\n\nWe’re not here for quick wins.\nWe’re here to build something real.",
        #   "postedDate": "2025-05-24 12:30:02.559 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 19,
        #   "totalReactionCount": 33,
        #   "postedDateTimestamp": 1748072101638,
        #   "urn": "7331945808189169666",
        #   "reposted": True,
        #   "repostsCount": 1,
        #   "text": "Most coaches don’t have a content problem.\nThey have a repurposing problem.\n\nI see people sharing valuable stories, client wins, and insights—\nand then never using them again.\n\nThat’s where visibility dies.\nGood content doesn’t stop working after one post.\nIf you said something powerful once, it deserves to be said again—\nacross formats, in new ways, to reach people who missed it the first time.\n\nYou don’t need to constantly create from scratch.\nYou need a system that helps you stretch one \nstrong idea into many.\n\nThis post breaks that down.\nIf you’re tired of always trying to “keep up” with content, read this.\nIt’ll save your time, energy, and attention.",
        #   "postedDate": "2025-05-24 07:35:01.638 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 19,
        #   "totalReactionCount": 33,
        #   "postedDateTimestamp": 1747830603101,
        #   "urn": "7330932889909448705",
        #   "repostsCount": 1,
        #   "text": "Most coaches don’t have a content problem.\nThey have a repurposing problem.\n\nI see people sharing valuable stories, client wins, and insights—\nand then never using them again.\n\nThat’s where visibility dies.\nGood content doesn’t stop working after one post.\nIf you said something powerful once, it deserves to be said again—\nacross formats, in new ways, to reach people who missed it the first time.\n\nYou don’t need to constantly create from scratch.\nYou need a system that helps you stretch one \nstrong idea into many.\n\nThis post breaks that down.\nIf you’re tired of always trying to “keep up” with content, read this.\nIt’ll save your time, energy, and attention.",
        #   "postedDate": "2025-05-21 12:30:03.101 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 17,
        #   "totalReactionCount": 19,
        #   "postedDateTimestamp": 1747656006581,
        #   "urn": "7330200579027148800",
        #   "text": "I left the traditional path to build my creative studio. Here’s why…\n\nBack in 2021, I designed my first poster for ₹400.\nAt the time, I didn’t care.\nI just wanted to create — \nto get paid something for doing what I loved.\n\nBut I also didn’t know how to price, position, or protect my work.\nI was winging it.\nSaying yes to everything.\nBurning out fast, and earning slow\n.\nBy 2023, I started learning the business side —\n how to price, pitch, and partner with intention.\n\nI wasn’t making huge money, but it was enough to cover my bills.\nThat mattered.\n\nThen came 2025.\nAnd something finally clicked.\nIn just 5 months, I made over ₹80,000 — not from “just design,” but from building a creative system around what I know:\n ✔ Strategy\n ✔ Repurposing content\n ✔ Freelance projects with structure, not chaos\n\nI realized I didn’t just want to do the work —\nI wanted to own the direction of it.\n\nThat’s why I built my studio.\nNot just to create for others, but to create a space where:\n → Brand stories evolve\n → Content gets reused, not wasted\n → Clients grow with clarity, not confusion\nI’m not chasing “big agency” life.\n\nI’m building something that fits who I am now — \nand who I’m becoming.\n\nIf you’re standing at the edge of doing your own thing…\nI’ve been there.\n\nNo fancy blueprint. \nNo big break. \nJust momentum, built slowly.",
        #   "postedDate": "2025-05-19 12:00:06.581 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 25,
        #   "totalReactionCount": 42,
        #   "postedDateTimestamp": 1747286779312,
        #   "urn": "7328651927615954944",
        #   "reposted": True,
        #   "repostsCount": 1,
        #   "text": "At first, I thought ChatGPT would save my time.\n\nBut it made me sound like a tech blog from 2012 \nNo soul. No vibe. No replies.\n\nThen I changed how I used it —\n ➡️ Shared my messy thoughts\n ➡️ Gave it my tone\n ➡️ Treated it like a creative buddy, not a magic wand\n\nAnd boom —\nContent that feels like me and connects with real people\n(and yes, real clients too).\n\nI just dropped the exact steps I follow in a carousel 💛\n\nGo swipe through it now!\nComment “VOICE” and I’ll send you the prompts I actually use.\n\nTag your creative buddy who needs this!\nAnd save it if you ever felt robotic too",
        #   "postedDate": "2025-05-15 05:26:19.312 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 25,
        #   "totalReactionCount": 42,
        #   "postedDateTimestamp": 1747204201092,
        #   "urn": "7328305569457487872",
        #   "repostsCount": 1,
        #   "text": "At first, I thought ChatGPT would save my time.\n\nBut it made me sound like a tech blog from 2012 \nNo soul. No vibe. No replies.\n\nThen I changed how I used it —\n ➡️ Shared my messy thoughts\n ➡️ Gave it my tone\n ➡️ Treated it like a creative buddy, not a magic wand\n\nAnd boom —\nContent that feels like me and connects with real people\n(and yes, real clients too).\n\nI just dropped the exact steps I follow in a carousel 💛\n\nGo swipe through it now!\nComment “VOICE” and I’ll send you the prompts I actually use.\n\nTag your creative buddy who needs this!\nAnd save it if you ever felt robotic too",
        #   "postedDate": "2025-05-14 06:30:01.092 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 22,
        #   "totalReactionCount": 37,
        #   "postedDateTimestamp": 1747137612323,
        #   "urn": "7328026275917238272",
        #   "text": "Too many people still think design = colors and fonts.\nBut here’s the truth:\nIf your design isn’t supporting your message, \nit’s getting in the way of it.\n\nDesign isn’t about being pretty.\n\nIt’s about making things perform.\n→ Does it stop the scroll?\n → Does it guide the reader?\n → Does it lead to action?\n\nIf not, it’s decoration. Not design.\nIn this post, I’m breaking the myth that’s\nsilently tanking your content performance—\nand showing what actually makes design convert.\n\nSlide 3 reframes it.\n Slide 5 shows the real business impact.\n Slide 6 gives you what to focus on next.\n\nSave this to gut-check your next piece of content.\n\n And if you want someone who designs for clarity over fluff—\n you know where to find me.",
        #   "postedDate": "2025-05-13 12:00:12.323 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 13,
        #   "totalReactionCount": 32,
        #   "postedDateTimestamp": 1747056617546,
        #   "urn": "7327686559200137216",
        #   "text": "You won't survive as a designer with design only\nEven after 4 years as a graphic designer,\nI can confidently say—\ndesign was just the beginning.\nThe real growth?\nIt came when I started learning the skills around design.\n\nHere’s what no one tells you:\n📌 You can be amazing at your core skill,\n but if you don’t know how to sell it,\n you’ll keep struggling for clients.\n📌 You can post great work online,\n but without content writing, it won’t connect.\n📌 You can design daily,\n but if you don’t build personal branding,\n you’ll stay invisible.\n\nWhen I started freelancing,\nI only focused on getting better at design.\nFonts, colors, layouts—I practiced them day and night.\nBut something felt off.\n\nGood work wasn’t bringing good clients.\nThat’s when I realized…\nBeing a designer is also being a marketer,\na storyteller, a brand, and a learner.\n\nToday, I use content to attract leads.\nI know how to communicate my value.\nAnd I help entrepreneurs and coaches do \nthe same through powerful visuals.\n\n\nIf you're a fellow creative stuck in the \n\"why am I not getting clients?\" loop,\njust remember—\ndesign is the skill, but these other skills build the business.\n\nWould you like a post on which exact skills helped me the most?\nLet me know, I’d love to create it for you!",
        #   "postedDate": "2025-05-12 13:30:17.546 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "image"
        # },
        # {
        #   "commentsCount": 20,
        #   "totalReactionCount": 45,
        #   "postedDateTimestamp": 1746794701076,
        #   "urn": "7326588001902301184",
        #   "text": "Why your content isn’t bringing actual leads\n\nYou’re posting. You’re showing up.\nYou’re sharing real value.\nBut no one’s biting.\n\nNo leads. No calls. No traction.\n\nTruth?\nMost content doesn’t convert because it’s trying to:\nSpeak to everyone\nTeach without connecting\nShare tips instead of creating movement\n\nIn this carousel, I’m breaking down exactly what to shift\nso your posts start doing what they’re supposed to:\nbuild trust and bring the right people in.\nNo fluff. No hacks.\nJust what’s actually working with my clients\n\n(who went from silence to “just booked another call”)\n\nSlide 1 gives it to you straight.\nSlide 4–6 show what to fix.\nSlide 8 is your next move.\n\nSave this to audit your next few posts.\nAnd if you want honest feedback—DM me “AUDIT.”\n\nI’ll take a look. No pitch, just real help. 🙂",
        #   "postedDate": "2025-05-09 12:45:01.076 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 19,
        #   "totalReactionCount": 38,
        #   "postedDateTimestamp": 1746763068762,
        #   "urn": "7326455326361157632",
        #   "reposted": True,
        #   "repostsCount": 1,
        #   "text": "Steal this post format if you're a coach\nLet’s be real—\n\nYou’re posting great advice…\nbut it’s not getting the love it deserves.\nNo saves. No comments. Just silence.\nIt’s not that your content is bad.\n\nIt’s that the format isn’t doing it justice.\nSo I’m giving you\na simple, repeatable post structure\nthat actually gets shared and starts conversations.\n\nYou’ll see:\n📌 What to say\n📌 How to break it down\n📌 A real example you can swipe\n📌 And how to reuse it again and again\n\nStart using this and watch your posts\ngo from “cool, scroll” to “wait—I need this.”\n\nSlide 4 is the format.\nSlide 5 is the example.\nSlide 8? That’s where you get more.\nSave it. Repost it.\nYour future self will thank you.",
        #   "postedDate": "2025-05-09 03:57:48.762 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 19,
        #   "totalReactionCount": 38,
        #   "postedDateTimestamp": 1746705613962,
        #   "urn": "7326214343463698434",
        #   "repostsCount": 1,
        #   "text": "Steal this post format if you're a coach\nLet’s be real—\n\nYou’re posting great advice…\nbut it’s not getting the love it deserves.\nNo saves. No comments. Just silence.\nIt’s not that your content is bad.\n\nIt’s that the format isn’t doing it justice.\nSo I’m giving you\na simple, repeatable post structure\nthat actually gets shared and starts conversations.\n\nYou’ll see:\n📌 What to say\n📌 How to break it down\n📌 A real example you can swipe\n📌 And how to reuse it again and again\n\nStart using this and watch your posts\ngo from “cool, scroll” to “wait—I need this.”\n\nSlide 4 is the format.\nSlide 5 is the example.\nSlide 8? That’s where you get more.\nSave it. Repost it.\nYour future self will thank you.",
        #   "postedDate": "2025-05-08 12:00:13.962 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        # {
        #   "commentsCount": 30,
        #   "totalReactionCount": 39,
        #   "postedDateTimestamp": 1746584323752,
        #   "urn": "7325705615450746882",
        #   "reposted": True,
        #   "repostsCount": 1,
        #   "text": "Ever wondered what a designer sees \nwhen they open your LinkedIn profile?\n\nIt’s more than just a banner or a profile picture.\n\nWe scan your layout, visual hierarchy, typography, brand consistency — \nand check whether you’re building trust visually.\n\nBecause here’s the truth:\nGood content with poor design gets ignored\nGood design with good content = trust, leads & authority.\nI created this carousel to show you exactly what I \nlook for when reviewing a profile — \n\nas a designer who works with coaches, founders & creators every week.\n\nIf you want a quick tip on improving yours,\nDrop a “Profile Audit” below or DM me privately.",
        #   "postedDate": "2025-05-07 02:18:43.752 +0000 UTC",
        #   "isBrandPartnership": False,
        #   "contentType": "document"
        # },
        {
          "commentsCount": 30,
          "totalReactionCount": 39,
          "postedDateTimestamp": 1746536413748,
          "urn": "7325504666329370625",
          "repostsCount": 1,
          "text": "Ever wondered what a designer sees \nwhen they open your LinkedIn profile?\n\nIt’s more than just a banner or a profile picture.\n\nWe scan your layout, visual hierarchy, typography, brand consistency — \nand check whether you’re building trust visually.\n\nBecause here’s the truth:\nGood content with poor design gets ignored\nGood design with good content = trust, leads & authority.\nI created this carousel to show you exactly what I \nlook for when reviewing a profile — \n\nas a designer who works with coaches, founders & creators every week.\n\nIf you want a quick tip on improving yours,\nDrop a “Profile Audit” below or DM me privately.",
          "postedDate": "2025-05-06 13:00:13.748 +0000 UTC",
          "isBrandPartnership": False,
          "contentType": "document"
        },
        {
          "commentsCount": 44,
          "totalReactionCount": 70,
          "postedDateTimestamp": 1746444600053,
          "urn": "7325119571781201922",
          "text": "I got my first client without a single cold DM.\n\nHere’s exactly how it happened:\nI opened my inbox to this:\n “Hey, did you design that carousel about content mistakes?”\nI braced for criticism.\nInstead, they said:\n“I’ve been struggling to make my posts look that clean. Do you offer design services?”\nI didn’t.\nBut I replied:\n “Yeah, I do now.”\nFirst client.\n\nNo pitch. No funnel. No outreach.\nHere’s what I learned:\n→ Your work is your outreach.\n → If you post what you want to get paid for — clients come to you.\n\nThe simple framework I’ve followed since:\nShow what you can actually do\n Not theory. Not concepts.\n\nMake your output the portfolio.\nShare how you think\nPeople don’t just buy design — they buy your brain.\nBreak down your decisions. Make it make sense.\n\nStay consistent\nI wasn’t viral. I was visible.\nFour posts a week. No excuses.\nMake it easy to reach you\nNo vague bios.\n\nJust add: “DM me ‘design’ if you need help.”\n (It works.)\nThat one client became two.\nThen three.\nThen a system — without chasing.\n\nYou don’t have to shout.\nYou just have to show up in a way that builds trust.\nIf you're offering a creative service and building your brand — \n\ntry this for 30 days.\n→ No gimmicks\n → Just clarity, consistency, and value\n\nI write for creatives who want clients without the cringe.\nStick around if that’s you.\n\nP.S.: If you’re seeing this on a Monday...\nYes, I’m judging you for “starting fresh tomorrow” again.\nStart now.\nYour client’s already watching.",
          "postedDate": "2025-05-05 11:30:00.053 +0000 UTC",
          "isBrandPartnership": False,
          "contentType": "image"
        }
    ]
    setup_docs: List[SetupDocInfo] = [
        {
            'namespace': test_scraping_namespace, 'docname': LITE_LINKEDIN_SCRAPED_POSTS_DOCNAME, 'is_versioned': False,
            'initial_data': example_posts_data, # Store the list directly
            'is_shared': False, 'is_system_entity': False,
        }
    ]

    # # Cleanup: Remove the input posts doc and the generated analysis doc
    test_analysis_namespace = LITE_LINKEDIN_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE.format(item=entity_username)
    cleanup_docs: List[CleanupDocInfo] = [
        {'namespace': test_scraping_namespace, 
         'docname': LITE_LINKEDIN_SCRAPED_POSTS_DOCNAME, 
         'is_versioned': False, 
         'is_shared': False},
        {'namespace': test_analysis_namespace, 
         'docname': LITE_LINKEDIN_CONTENT_ANALYSIS_DOCNAME, 
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
