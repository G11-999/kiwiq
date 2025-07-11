"""
Workflow definition for analyzing bucket-tagged documents and extracting
structured knowledge based on configurable focus areas.

Steps:
1. Input: Analysis focus areas, usage description, entity username, target document name, and tagged documents
2. Load Documents: Load all bucket-tagged documents using LoadCustomerDataNode
3. Map Documents: Iterate over loaded documents using MapListRouterNode
4. Construct Analysis Prompt: Build bucket-specific analysis prompts based on focus areas
5. Extract Knowledge: Use LLM for structured knowledge extraction
6. Aggregate Extractions: Collect individual extraction results using a reducer
7. Merge Extractions: Combine collected results using MergeAggregateNode
8. Store Analysis: Save results directly to target bucket-specific document
9. Output: Return analysis summary and storage confirmation
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Union
import json

# Internal dependencies
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

from kiwi_client.workflows.document_models.customer_docs import (
    UPLOADED_FILES_NAMESPACE_TEMPLATE,
    USER_KNOWLEDGE_BASE_ANALYSIS_DOCNAME_TEMPLATE,
    USER_KNOWLEDGE_BASE_ANALYSIS_NAMESPACE_TEMPLATE,
    USER_KNOWLEDGE_BASE_ANALYSIS_IS_VERSIONED,
)

from kiwi_client.workflows.llm_inputs.knowledge_base_analysis import (
    KNOWLEDGE_BASE_ANALYSIS_JSON_SCHEMA,
    KNOWLEDGE_BASE_ANALYSIS_SYSTEM_PROMPT,
    KNOWLEDGE_BASE_ANALYSIS_USER_PROMPT,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Workflow Configuration ---
LLM_PROVIDER = "openai"
ANALYSIS_MODEL_NAME = "gpt-4.1"
LLM_TEMPERATURE = 0.1
LLM_MAX_TOKENS = 12000

ANALYSIS_SAVE_OPERATION = "upsert_versioned"

# Merge Strategy for Knowledge Base Analysis
MERGE_STRATEGY_CONFIG = {
    "map_phase": {
        "unspecified_keys_strategy": "auto_merge",
        "key_mappings": []
    },
    "reduce_phase": {
        "default_reducer": "nested_merge_aggregate",
        "reducers": {
            # "summary": "combine_in_list",     # Collect all summaries into a list
            # "key_points": "append",          # Append key points from all documents into one list
            # "entities": "nested_merge_replace" # Merge entity dictionaries (last one wins for conflicting keys)
        },
        "error_strategy": "coalesce_keep_non_empty"
    },
    "transformation_error_strategy": "skip_operation"
}

# --- Workflow Graph Schema Definition ---
"""
Workflow definition for extracting structured information from multiple documents,
merging the results, and saving them.

Steps:
1. Input: List of documents to load, LLM config, extraction schema, merge strategy, save location.
2. Load Documents: Load all specified documents using LoadCustomerDataNode.
3. Map Documents: Iterate over loaded documents using MapListRouterNode.
4. Extract Data: For each document, call LLMNode for structured extraction.
5. Aggregate Extractions (State): Collect individual extraction results using a reducer.
6. Merge Extractions (Node): Combine collected results using MergeAggregateNode.
7. Store Output: Save the final merged data using StoreCustomerDataNode.
8. Output: Return the path/status of the saved output.
"""

workflow_graph_schema = {
  "nodes": {
    # --- 1. Input Node: Now accepts a list of documents to process ---
    "input_node": {
      "node_id": "input_node",
      "node_name": "input_node",
      "node_config": {},
      "dynamic_output_schema": {
          "fields": {
              "documents_to_process": {
                  "type": "list",
                  "required": True,
                  "description": "List of document identifiers (namespace/docname pairs) to load and process."
              },
              "entity_username": {
                  "type": "str",
                  "required": True,
                  "description": "Username of the entity to process."
              },
              "description": {
                  "type": "str",
                  "required": False,
                  "description": "Description of the knowledge base analysis to perform."
              }
          }
        }
    },

    # --- 3. Load Single Document (Inside Map Branch) ---
    "load_documents": {
      "node_id": "load_documents",
      "node_name": "load_customer_data",
      "node_config": {
          "global_is_shared": False,
          "global_is_system_entity": False,
          "global_version_config": {"version": "default"},
          "global_schema_options": {"load_schema": False},
          "load_configs_input_path": "documents_to_process"
      },
      "dynamic_output_schema": {
        "fields": {
          "loaded_documents": {
            "type": "any",
            "required": True,
            "description": "List or single document loaded from the input"
          }
        }
      }
    },


    # --- 2. Map Identifiers to Processing Branch ---
    "map_identifiers_to_process": { # Renamed from map_docs_to_extract
        "node_id": "map_identifiers_to_process",
        "node_name": "map_list_router_node",
        "node_config": {
            "choices": ["construct_prompt"], # Target the loader node first in the branch
            "map_targets": [
                {
                    # Source path points to the list of identifiers from the input node
                    "source_path": "loaded_documents",
                    "destinations": ["construct_prompt"] # Start the branch here
                }
            ]
        },
        # Reads: documents_to_process (from input_node)
        # Iterates over the list items (dicts containing namespace/docname).
        # Sends each item -> doc_identifier to load_documents
    },

    # --- 4. Construct Prompt (Inside Map Branch) ---
    "construct_prompt": {
      "node_id": "construct_prompt",
      "node_name": "prompt_constructor",
      "private_input_mode": True,  # Receives input directly from map_identifiers_to_process
      "private_output_mode": True,
      "enable_node_fan_in": True, # Sends output directly to extract_data
      "node_config": {
        "prompt_templates": {
          # User prompt template takes the document content from the loader
          "extraction_user_prompt": {
            "id": "extraction_user_prompt",
            # Updated template to reflect input source
            "template": KNOWLEDGE_BASE_ANALYSIS_USER_PROMPT,
            "variables": {
              "document_content": None, # Required, mapped from load_documents edge
              "usage_description": None # Required, mapped from input_node
            },
            "construct_options": {
               # Map from the input field provided by the edge from load_documents
               "document_content": "markdown_content",
               "usage_description": "description"
            }
          },
          # System prompt is static
          "extraction_system_prompt": {
            "id": "extraction_system_prompt",
            "template": KNOWLEDGE_BASE_ANALYSIS_SYSTEM_PROMPT,
            "variables": {
                "extraction_schema": KNOWLEDGE_BASE_ANALYSIS_JSON_SCHEMA,
                "usage_description": None # Required, mapped from input_node
            },
            "construct_options": {
                "usage_description": "description"
            }
          }
        }
      }
      # Reads: document_data_input (mapped from load_documents via private input)
      # Writes: user_prompt, system_prompt (via private output)
    },

    # --- 5. Extract Data (LLM - Inside Map Branch) ---
    "extract_data": {
      "node_id": "extract_data",
      "node_name": "llm",
      "private_input_mode": True, # Receives input directly from construct_prompt
      # Output goes to the graph state aggregator (no longer private output)
      "node_config": {
          "llm_config": {
              "model_spec": {"provider": LLM_PROVIDER, "model": ANALYSIS_MODEL_NAME},
              "temperature": LLM_TEMPERATURE,
              "max_tokens": LLM_MAX_TOKENS
          },
          "output_schema": {
              # Use the schema definition generated from Pydantic model
             "schema_definition": KNOWLEDGE_BASE_ANALYSIS_JSON_SCHEMA,
             "convert_loaded_schema_to_pydantic": False
          },
      }
      # Reads: user_prompt, system_prompt (from construct_prompt via private input)
      # Writes: structured_output (sent to $graph_state)
    },

    # --- 6. Merge Extractions (Outside Map Branch) ---
    # TODO: LLM DEDUPE! Try this graph without map reduce and process all docs together!
    "merge_extractions": {
      "node_id": "merge_extractions",
      "node_name": "merge_aggregate",
      "node_config": {
          "operations": [
              {
                  "output_field_name": "merged_result_field",
                  # Path to the list of extractions collected in the state
                  "select_paths": ["collected_extractions"], # Input field name, mapped from state
                  "merge_strategy": MERGE_STRATEGY_CONFIG
              }
          ]
      },
      "dynamic_input_schema": {
        "fields": {
          "collected_extractions": {
            "type": "any",
            "required": True,
            "description": "List or single extracted data"
          }
        }
      }
      # Reads: collected_extractions (mapped from $graph_state.all_extractions)
      # Writes: merged_data
    },

    # --- 7. Store Merged Output (Outside Map Branch) ---
    "save_merged_extraction": {
      "node_id": "save_merged_extraction",
      "node_name": "store_customer_data",
      "node_config": {
          "store_configs": [
              {
                  "input_field_path": "merged_data.merged_result_field",
                  "target_path": {
                      "filename_config": {
                          "input_namespace_field_pattern": USER_KNOWLEDGE_BASE_ANALYSIS_NAMESPACE_TEMPLATE, 
                          "input_namespace_field": "entity_username",
                          "static_docname": USER_KNOWLEDGE_BASE_ANALYSIS_DOCNAME_TEMPLATE,
                      }
                  },
              }
          ],
          "global_versioning": {"is_versioned": USER_KNOWLEDGE_BASE_ANALYSIS_IS_VERSIONED, "operation": ANALYSIS_SAVE_OPERATION},
          "global_schema_options": {}
      }
      # Reads: data_to_save_container (mapped from merge_extractions.merged_data)
      # Writes: paths_processed
    },

    # --- 8. Output Node (Outside Map Branch) ---
    "output_node": {
      "node_id": "output_node",
      "node_name": "output_node",
      "node_config": {},
      "dynamic_input_schema": {
        "fields": {
          "all_extractions": {
            "type": "any",
            "required": True,
            "description": "List or single extracted data"
          }
        }
      }
      # Reads: final_save_details (from save_merged_extraction)
    }
  },

  # --- Edges Defining Data Flow ---
  "edges": [
    # --- Input -> Map ---
    { "src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username" },
        { "src_field": "description", "dst_field": "description" }
      ],
      "description": "Pass the entity username and description to the graph state."
    },

    { "src_node_id": "input_node", "dst_node_id": "load_documents", "mappings": [
        # Pass the list of document identifiers to the mapper
        { "src_field": "documents_to_process", "dst_field": "documents_to_process" },
        { "src_field": "entity_username", "dst_field": "entity_username" }
      ],
      "description": "Pass the list of document identifiers and entity username to the load_documents node."
    },

    # --- Map -> Load (Private Branch Start) ---
    { "src_node_id": "load_documents", "dst_node_id": "map_identifiers_to_process", "mappings": [
        # Map the item being iterated (doc identifier dict) to the loader's expected input field
        { "src_field": "loaded_documents", "dst_field": "loaded_documents", "description": "Pass the documents to be processed."}
      ]
    },

    # --- Load -> Construct Prompt (Private Branch) ---
    { "src_node_id": "map_identifiers_to_process", "dst_node_id": "construct_prompt", "mappings": [
        # Map the loaded content to the prompt constructor's expected input field
        # { "src_field": "loaded_documents", "dst_field": "document_data_input" }
      ]
    },

    # --- State -> Construct Prompt ---
    { "src_node_id": "$graph_state", "dst_node_id": "construct_prompt", "mappings": [
        { "src_field": "description", "dst_field": "description" }
      ],
      "description": "Pass the description to the prompt constructor."
    },

    # --- Construct Prompt -> Extract (Private Branch) ---
    { "src_node_id": "construct_prompt", "dst_node_id": "extract_data", "mappings": [
        { "src_field": "extraction_user_prompt", "dst_field": "user_prompt"},
        { "src_field": "extraction_system_prompt", "dst_field": "system_prompt"}
      ]
    },

    # --- State -> Extract Data (Message History) ---
    { "src_node_id": "$graph_state", "dst_node_id": "extract_data", "mappings": [
        { "src_field": "extract_data_messages_history", "dst_field": "messages_history"}
      ]
    },

    # --- Extract -> State (Aggregate - Branch End) ---
    { "src_node_id": "extract_data", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "structured_output", "dst_field": "all_extractions", "description": "Collect the structured output from each extraction branch."},
        { "src_field": "current_messages", "dst_field": "extract_data_messages_history", "description": "Update message history with extraction interaction."}
      ]
    },

    { "src_node_id": "extract_data", "dst_node_id": "merge_extractions", "mappings": [
      ]
    },

    # --- State -> Merge (After Map/Reduce) ---
    { "src_node_id": "$graph_state", "dst_node_id": "merge_extractions", "mappings": [
        { "src_field": "all_extractions", "dst_field": "collected_extractions", "description": "Pass the list of all extracted data to the merge node."}
      ]
    },

    # --- Merge -> Store ---
    { "src_node_id": "merge_extractions", "dst_node_id": "save_merged_extraction", "mappings": [
        { "src_field": "merged_data", "dst_field": "merged_data", "description": "Pass the container holding the merged data."}
      ]
    },
    { "src_node_id": "$graph_state", "dst_node_id": "save_merged_extraction", "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username", "description": "Pass the entity username to the save_merged_extraction node."},
      ]
    },


    # --- Merge -> State ---
    { "src_node_id": "merge_extractions", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "merged_data", "dst_field": "merged_data", "description": "Pass the merged data to the graph state."}
      ]
    },

    # --- Store -> Output ---
    { "src_node_id": "save_merged_extraction", "dst_node_id": "output_node", "mappings": [
        { "src_field": "paths_processed", "dst_field": "final_save_details", "description": "Pass the details of the saved document(s)."}
      ]
    },

    # --- State -> Output ---
    { "src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
        { "src_field": "all_extractions", "dst_field": "all_extractions", "description": "Pass the list of all extracted data to the merge node."},
        { "src_field": "merged_data", "dst_field": "merged_data", "description": "Pass the merged data to the graph state."},
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
          "all_extractions": "collect_values",
          "extract_data_messages_history": "add_messages"
        }
      }
  }
}


# --- Test Execution Logic ---

async def validate_extraction_workflow_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Custom validation function for the extraction workflow outputs.
    (Remains largely the same, checks the final saved output details)
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating extraction workflow outputs...")
    assert 'final_save_details' in outputs, "Validation Failed: 'final_save_details' key missing."
    final_details = outputs.get('final_save_details')
    assert isinstance(final_details, list), f"Validation Failed: 'final_save_details' should be a list, got {type(final_details)}"
    assert len(final_details) > 0, "Validation Failed: 'final_save_details' list is empty."
    assert isinstance(final_details[0], list), f"Validation Failed: First item in 'final_save_details' should be a list, got {type(final_details[0])}"
    # assert len(final_details[0]) == 3, f"Validation Failed: Inner list in 'final_save_details' should have 3 elements (ns, dn, op), got {len(final_details[0])}"
    # saved_ns, saved_dn, saved_op = final_details[0]
    logger.info(f"   Found expected 'final_save_details': {final_details}")
    logger.info("✓ Output structure and content validation passed.")
    return True


async def main_test_extraction_workflow():
    """
    Tests the Knowledge Base Analysis Workflow using the run_workflow_test helper.
    Now provides a list of documents as input.
    """
    test_name = "Knowledge Base Analysis Workflow Test V5 (Map-Load-Extract)" # Updated test name
    print(f"--- Starting {test_name} --- ")

    DOC1_NAME = "Alejandra Vergara – Knowledge Base 1"
    DOC2_NAME = "Alejandra Vergara – Knowledge Base 2"

    # --- Define Input Data ---
    # Provide the list of document identifiers matching the input_node schema
    workflow_inputs: Dict[str, Any] = {
        "documents_to_process": [
            {
                "filename_config": {
                    "input_namespace_field_pattern": UPLOADED_FILES_NAMESPACE_TEMPLATE, 
                    "input_namespace_field": "entity_username",
                    "static_docname": DOC1_NAME
                },
                "output_field_name": "loaded_documents",
            },
            {
                "filename_config": {
                    "input_namespace_field_pattern": UPLOADED_FILES_NAMESPACE_TEMPLATE, 
                    "input_namespace_field": "entity_username",
                    "static_docname": DOC2_NAME
                },
                "output_field_name": "loaded_documents",
            }
        ],
        "entity_username": "example-user-4",
        "description": "Analyze these documents to extract key insights about content strategy and SEO practices. Focus on identifying best practices, common challenges, and specific techniques mentioned. This analysis will be used to inform our content creation strategy."
    }

    # --- Define Setup and Cleanup ---
    test_namespace = UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=workflow_inputs["entity_username"])
    setup_docs: List[SetupDocInfo] = [
        {
            'namespace': test_namespace, 'docname': DOC1_NAME, 'is_versioned': False,
            'initial_data': {
                "source_filename": DOC1_NAME,
                "markdown_content": "Content Strategy Overview: This document outlines key content strategy principles and best practices. Topics include audience targeting, content planning, SEO optimization, and performance measurement. Key focus areas are content quality, consistency, and engagement metrics."
            }, 'is_shared': False, 'is_system_entity': False,
        },
        {
            'namespace': test_namespace, 'docname': DOC2_NAME, 'is_versioned': False,
            'initial_data': {
                "source_filename": DOC2_NAME,
                "markdown_content": "SEO Best Practices: Comprehensive guide covering technical SEO, on-page optimization, link building strategies, and content optimization. Includes case studies and performance metrics. Emphasizes the importance of user experience and mobile optimization."
            }, 'is_shared': False, 'is_system_entity': False,
        }
    ]
    cleanup_docs: List[CleanupDocInfo] = [
        {'namespace': test_namespace, 'docname': DOC1_NAME, 'is_versioned': False, 'is_shared': False},
        {'namespace': test_namespace, 'docname': DOC2_NAME, 'is_versioned': False, 'is_shared': False},
    ]
    setup_schemas = None
    cleanup_created_schemas = False

    # --- Execute Test ---
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=workflow_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=[],
        setup_docs=setup_docs,
        cleanup_docs=cleanup_docs,
        setup_schemas=setup_schemas,
        cleanup_created_schemas=cleanup_created_schemas,
        validate_output_func=validate_extraction_workflow_output,
        stream_intermediate_results=False,
        poll_interval_sec=5,
        timeout_sec=900
    )

    print(f"\n--- {test_name} Finished --- ")
    if final_run_status_obj:
        print(f"Final Status: {final_run_status_obj.status}")
        if final_run_outputs:
            print(f"Final Save Details: {final_run_outputs.get('final_save_details')}")
        if final_run_status_obj.status != WorkflowRunStatus.COMPLETED:
             print(f"Error Message: {final_run_status_obj.error_message}")


# Standard Python entry point check.
if __name__ == "__main__":
    print("="*50)
    print("Executing Knowledge Base Analysis Workflow Test V5 (Map-Load-Extract)") # Updated print message
    print("="*50)
    try:
        asyncio.run(main_test_extraction_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.")
    except Exception as main_err:
        print(f"\nCritical error during script execution: {main_err}")
        logger.exception("Critical error running main")

    print("\nScript execution finished.")
