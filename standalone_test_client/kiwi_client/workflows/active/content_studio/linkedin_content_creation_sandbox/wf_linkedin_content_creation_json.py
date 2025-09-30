from kiwi_client.workflows.active.document_models.customer_docs import (
    # LinkedIn User Profile (replaces User DNA)
    LINKEDIN_USER_PROFILE_DOCNAME,
    LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
    LINKEDIN_USER_PROFILE_IS_VERSIONED,
    # LinkedIn Content Drafts (replaces Content Drafts)
    LINKEDIN_DRAFT_DOCNAME,
    LINKEDIN_DRAFT_NAMESPACE_TEMPLATE,
    LINKEDIN_DRAFT_IS_VERSIONED,

    # LinkedIn Content Brief (replaces Content Brief)
    LINKEDIN_BRIEF_NAMESPACE_TEMPLATE,
    LINKEDIN_BRIEF_IS_VERSIONED,

    # LinkedIn Content Strategy
    LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
    LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE,
    LINKEDIN_CONTENT_PLAYBOOK_IS_VERSIONED,
)
# Import LLM configurations from local wf_llm_inputs
from kiwi_client.workflows.active.content_studio.linkedin_content_creation_sandbox.wf_llm_inputs import (
    # LLM Model Configuration
    TEMPERATURE,
    MAX_TOKENS,
    MAX_LLM_ITERATIONS,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LLM_MODEL,
    MAX_ITERATIONS,
    # Prompts
    POST_CREATION_FEEDBACK_USER_PROMPT,
    POST_CREATION_INITIAL_USER_PROMPT,
    POST_CREATION_SYSTEM_PROMPT,
    USER_FEEDBACK_INITIAL_USER_PROMPT,
    USER_FEEDBACK_SYSTEM_PROMPT,
    USER_FEEDBACK_ADDITIONAL_USER_PROMPT,
    # Schema
    POST_LLM_OUTPUT_SCHEMA
)

# Full GraphSchema Structure
workflow_graph_schema = {
  "nodes": {
    # --- 1. Input Node ---
    "input_node": {
      "node_id": "input_node",
      "node_name": "input_node",
      "node_config": {
      },
      "dynamic_output_schema": {
          "fields": {
              "post_uuid": { "type": "str", "required": True, "description": "UUID of the post being drafted for saving." },
              "brief_docname": { "type": "str", "required": True, "description": "Docname of the brief being used for drafting." },
              "entity_username": { "type": "str", "required": True, "description": "Username of the entity for which the post is being drafted." },
              "initial_status": { "type": "str", "required": False, "default": "draft", "description": "Initial status used when saving drafts." },
              "load_additional_user_files": {
                  "type": "list",
                  "required": False,
                  "default": [],
                  "description": "Optional list of additional user files to load. Each item should have 'namespace', 'docname', and 'is_shared' fields."
              }
          }
        }
    },

    # --- 2. Transform Additional Files Config ---
    "transform_additional_files_config": {
        "node_id": "transform_additional_files_config",
        "node_name": "transform_data",
        "node_config": {
            "apply_transform_to_each_item_in_list_at_path": "load_additional_user_files",
            "base_object": {
                "output_field_name": "additional_user_files"
            },
            "mappings": [
                {"source_path": "namespace", "destination_path": "filename_config.static_namespace"},
                {"source_path": "docname", "destination_path": "filename_config.static_docname"},
                {"source_path": "is_shared", "destination_path": "is_shared"}
            ]
        }
    },

    # --- 3. Load Additional User Files (conditional) ---
    "load_additional_user_files_node": {
        "node_id": "load_additional_user_files_node",
        "node_name": "load_customer_data",
        "node_config": {
            "load_configs_input_path": "transformed_data"
        }
    },

    # --- 4. Load Customer Context Documents and Scraped Posts (Single Node) ---
    "load_all_context_docs": {
        "node_id": "load_all_context_docs",
        "node_name": "load_customer_data",
        "node_config": {
            "load_paths": [
                {
                    "filename_config": {
                        "input_namespace_field_pattern": LINKEDIN_BRIEF_NAMESPACE_TEMPLATE, 
                        "input_namespace_field": "entity_username",
                        "input_docname_field": "brief_docname",
                    },
                    "output_field_name": "content_brief"
                },
                {
                    "filename_config": {
                        "input_namespace_field_pattern": LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
                        "input_namespace_field": "entity_username",
                        "static_docname": LINKEDIN_USER_PROFILE_DOCNAME,
                    },
                    "output_field_name": "linkedin_user_profile"
                },
                {
                    "filename_config": {
                        "input_namespace_field_pattern": LINKEDIN_CONTENT_PLAYBOOK_NAMESPACE_TEMPLATE,
                        "input_namespace_field": "entity_username",
                        "static_docname": LINKEDIN_CONTENT_PLAYBOOK_DOCNAME,
                    },
                    "output_field_name": "linkedin_content_playbook"
                }
            ],
            "global_is_shared": False,
            "global_is_system_entity": False,
            "global_schema_options": {"load_schema": False}
        },
    },

    # --- 5. Construct Initial Prompt ---
    "construct_initial_prompt": {
      "node_id": "construct_initial_prompt",
      "node_name": "prompt_constructor",
      "enable_node_fan_in": True, # Wait for all inputs before running
      "node_config": {
        "prompt_templates": {
          "initial_generation_prompt": {
            "id": "initial_generation_prompt",
            "template": POST_CREATION_INITIAL_USER_PROMPT,
            "variables": {
              "brief": None, # Required from input_node via edge mapping
              "linkedin_user_profile": None,
              "linkedin_content_playbook": None,
              "additional_user_files": "", # Additional user-provided context files
              # Default if not found via construct_options
            },
            "construct_options": { # P1 Sourcing: Map variables to paths within node's input fields
               "linkedin_user_profile": "linkedin_user_profile", # Look inside the mapped 'linkedin_user_profile' input field
               "brief": "content_brief", # Look inside the mapped 'content_brief' input field (corrected from 'brief_docname')
               "linkedin_content_playbook": "linkedin_content_playbook", # Look inside the mapped 'linkedin_content_playbook' input field
               "additional_user_files": "additional_user_files", # Additional context files from user
            }
          },
          "system_prompt": {  # NOTE: this can directly be set in the LLM node too! But putting it here for using template variables!
            "id": "system_prompt",
            "template": POST_CREATION_SYSTEM_PROMPT,
            "variables": {},
            "construct_options": {}
          }
        }
      }
      # Reads: brief_docname (from $graph_state), linkedin_user_profile (from `load_all_context_docs`)
      # Waits for all inputs due to enable_node_fan_in=True
      # Outgoing edges
      #   - Sends: initial_generation_prompt -> to user_prompt ; system_prompt -> system_prompt in LLM Node
    },

    # --- 4. Generate Content (Structured) ---
    "generate_content": {
      "node_id": "generate_content",
      "node_name": "llm",
      "node_config": {
        "llm_config": {
          "model_spec": {
            "provider": DEFAULT_LLM_PROVIDER,
            "model": DEFAULT_LLM_MODEL
          },
          "temperature": TEMPERATURE,
          "max_tokens": MAX_TOKENS
        },
        "output_schema": {
          "schema_definition": POST_LLM_OUTPUT_SCHEMA,
          "convert_loaded_schema_to_pydantic": False
        }
      }
    },

    # --- 5. Store Draft ---
    "store_draft": {  
      "node_id": "store_draft",
      "node_name": "store_customer_data",
      "node_config": {
        "global_versioning": {
          "is_versioned": True,
          "operation": "initialize", # Must not exist yet
          "version": None # Name the initial version
        },
        "store_configs": [
            
            {
                # Also store the selected concepts that were used
                "input_field_path": "structured_output", # Mapped from filter_selected_concepts
                "target_path": {
                    "filename_config": {
                        "input_namespace_field_pattern": LINKEDIN_DRAFT_NAMESPACE_TEMPLATE, 
                        "input_namespace_field": "entity_username",
                        "input_docname_field_pattern": LINKEDIN_DRAFT_DOCNAME, 
                        "input_docname_field": "post_uuid",
                    }
                },
                "versioning": {
                    "is_versioned": LINKEDIN_DRAFT_IS_VERSIONED,
                    "operation": "upsert_versioned",
                },
                "extra_fields": [
                    {
                        "src_path": "initial_status",
                        "dst_path": "status"
                    },
                    {
                        "src_path": "post_uuid",
                        "dst_path": "uuid"
                    }
                ]
            }
        ]
      }
    },

    # --- 5b. Save Draft (manual save similar to save_brief) ---
    "save_draft": {
      "node_id": "save_draft",
      "node_name": "store_customer_data",
      "node_config": {
        "global_versioning": {
          "is_versioned": LINKEDIN_DRAFT_IS_VERSIONED,
          "operation": "upsert_versioned"
        },
        "global_is_shared": False,
        "store_configs": [
          {
            "input_field_path": "current_post_draft",
            "target_path": {
              "filename_config": {
                "input_namespace_field_pattern": LINKEDIN_DRAFT_NAMESPACE_TEMPLATE,
                "input_namespace_field": "entity_username",
                "input_docname_field_pattern": LINKEDIN_DRAFT_DOCNAME,
                "input_docname_field": "post_uuid"
              }
            },
            "extra_fields": [
              {
                "src_path": "initial_status",
                "dst_path": "status"
              },
              {
                "src_path": "post_uuid",
                "dst_path": "uuid"
              }
            ],
            "versioning": {
              "is_versioned": LINKEDIN_DRAFT_IS_VERSIONED,
              "operation": "upsert_versioned"
            }
          }
        ]
      }
    },

    # --- 5c. Save Final Draft (similar to save_final_brief) ---
    "save_final_draft": {
      "node_id": "save_final_draft",
      "node_name": "store_customer_data",
      "node_config": {
        "global_versioning": {
          "is_versioned": LINKEDIN_DRAFT_IS_VERSIONED,
          "operation": "upsert_versioned"
        },
        "global_is_shared": False,
        "store_configs": [
          {
            "input_field_path": "current_post_draft",
            "target_path": {
              "filename_config": {
                "input_namespace_field_pattern": LINKEDIN_DRAFT_NAMESPACE_TEMPLATE,
                "input_namespace_field": "entity_username",
                "input_docname_field_pattern": LINKEDIN_DRAFT_DOCNAME,
                "input_docname_field": "post_uuid"
              }
            },
            "versioning": {
              "is_versioned": LINKEDIN_DRAFT_IS_VERSIONED,
              "operation": "upsert_versioned"
            },
            "extra_fields": [
              {
                "src_path": "user_action",
                "dst_path": "status"
              },
              {
                "src_path": "post_uuid",
                "dst_path": "uuid"
              }
            ]
          }
        ]
      }
    },

    # --- 6. Human Review ---
    "capture_approval": {  
      "node_id": "capture_approval",
      "node_name": "hitl_node__default",
      "node_config": {},
      "dynamic_output_schema": {
          "fields": {
              "user_action": { "type": "enum", "enum_values": ["complete", "provide_feedback", "cancel_workflow", "draft"], "required": True, "description": "User's decision on draft approval." },
              "revision_feedback": { "type": "str", "required": False, "description": "Feedback for revision (required if provide_feedback)." },
              "updated_content_draft": { "type": "dict", "required": True, "description": "Updated post draft with any manual edits." },
              "load_additional_user_files": {
                  "type": "list",
                  "required": False,
                  "default": [],
                  "description": "Optional list of additional user files to load. Each item should have 'namespace', 'docname', and 'is_shared' fields."
              }
          }
      },
    },

    # --- 7. Route Based on Approval ---
    "route_on_approval": {
      "node_id": "route_on_approval",
      "node_name": "router_node",
      "node_config": {
        "choices": ["check_iteration_limit", "delete_draft_on_cancel", "save_draft", "save_final_draft"], # Node IDs to route to
        "allow_multiple": False,
        "choices_with_conditions": [
          {
            "choice_id": "check_iteration_limit", # Route to feedback loop (needs iteration check first)
            "input_path": "user_action_from_hitl", # Path WITHIN the node's input data
            "target_value": "provide_feedback"
          },
          {
            "choice_id": "save_final_draft", # Final save
            "input_path": "user_action_from_hitl",
            "target_value": "complete"
          },
          {
            "choice_id": "save_draft", # Save as draft/intermediate
            "input_path": "user_action_from_hitl",
            "target_value": "draft"
          },
          {
            "choice_id": "delete_draft_on_cancel", # Delete draft and cancel
            "input_path": "user_action_from_hitl",
            "target_value": "cancel_workflow"
          }
        ]
      }

    },

    # --- 7b. Delete Draft on Cancel ---
    "delete_draft_on_cancel": {
        "node_id": "delete_draft_on_cancel",
        "node_name": "delete_customer_data",
        "node_config": {
            "search_params": {
                "input_namespace_field": "entity_username",
                "input_namespace_field_pattern": LINKEDIN_DRAFT_NAMESPACE_TEMPLATE,
                "input_docname_field": "post_uuid",
                "input_docname_field_pattern": LINKEDIN_DRAFT_DOCNAME
            }
        }
    },

    # --- 8. Check Iteration Limit ---
    "check_iteration_limit": {
        "node_id": "check_iteration_limit",
        "node_name": "if_else_condition",
        "node_config": {
            "tagged_conditions": [
                {
                    "tag": "iteration_limit_check", # Identifier for the condition group
                    "condition_groups": [ {
                        "logical_operator": "and", # Operator within the group
                        "conditions": [ {
                            "field": "generation_metadata.iteration_count", # Field name expected in the node's input data
                            "operator": "less_than",
                            "value": MAX_ITERATIONS
                        } ]
                    } ],
                    "group_logical_operator": "and" # Operator between groups (only one group here)
                }
            ],
            "branch_logic_operator": "and"
        }
    },

    # --- 8b. Route Based on Iteration Limit Check ---
    "route_on_limit_check": {  # NOTE: this demonstrates 3 diff ways of checking IFElse outputs to perform routing -> check tag or check overall result (via condition or branch name) across all tags!
        "node_id": "route_on_limit_check",
        "node_name": "router_node",
        "node_config": {
            "choices": ["route_to_initial_or_additional_prompt", "output_node"], # Node IDs to route to
            "allow_multiple": False,
            "choices_with_conditions": [
                {
                    "choice_id": "route_to_initial_or_additional_prompt", # Continue loop
                    "input_path": "if_else_condition_tag_results.iteration_limit_check", # Path WITHIN the node's input data
                    "target_value": True # Value output by check_iteration_limit
                },
                {
                    "choice_id": "output_node", # Limit reached, finalize
                    "input_path": "iteration_branch_result", # Path WITHIN the node's input data
                    "target_value": "false_branch" # Value output by check_iteration_limit
                },
            ]
        }
    },

    # --- 7. Route Based on Approval ---
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
              },
            ],
            "default_choice": "construct_user_feedback_additional_prompt"
        }
    },

    # --- Transform HITL Additional Files Config ---
    "transform_hitl_additional_files_config": {
        "node_id": "transform_hitl_additional_files_config",
        "node_name": "transform_data",
        "node_config": {
            "apply_transform_to_each_item_in_list_at_path": "load_additional_user_files",
            "base_object": {
                "output_field_name": "hitl_additional_user_files"
            },
            "mappings": [
                {"source_path": "namespace", "destination_path": "filename_config.static_namespace"},
                {"source_path": "docname", "destination_path": "filename_config.static_docname"},
                {"source_path": "is_shared", "destination_path": "is_shared"}
            ]
        }
    },

    # --- Load HITL Additional User Files ---
    "load_hitl_additional_user_files_node": {
        "node_id": "load_hitl_additional_user_files_node",
        "node_name": "load_customer_data",
        "node_config": {
            "load_configs_input_path": "transformed_data"
        }
    },

    # --- Construct Initial Feedback Prompt ---
    "construct_user_feedback_initial_prompt": {
        "node_id": "construct_user_feedback_initial_prompt",
        "node_name": "prompt_constructor",
        "node_config": {
            "prompt_templates": {
            "interpret_feedback_prompt": {
                "id": "interpret_feedback_prompt",
                "template": USER_FEEDBACK_INITIAL_USER_PROMPT,
                "variables": {
                    "current_feedback_text": None,
                    "current_post_draft": None,
                    "user_profile": None,
                    "hitl_additional_user_files": ""
                },
                "construct_options": {
                    "current_feedback_text": "current_feedback_text",
                    "current_post_draft": "current_post_draft",
                    "user_profile": "linkedin_user_profile",
                    "hitl_additional_user_files": "hitl_additional_user_files"
                }
            },
            "system_prompt": {
                "id": "system_prompt",
                "template": USER_FEEDBACK_SYSTEM_PROMPT,
                "variables": {},
                "construct_options": {}
            }
            }
        }
        # Reads: updated_brief from state
        # Writes: additional_brief_prompt, system_prompt
    },

    # --- Construct Additional Brief Prompt ---
    "construct_user_feedback_additional_prompt": {
        "node_id": "construct_user_feedback_additional_prompt",
        "node_name": "prompt_constructor",
        "node_config": {
            "prompt_templates": {
            "interpret_feedback_prompt": {
                "id": "interpret_feedback_prompt",
                "template": USER_FEEDBACK_ADDITIONAL_USER_PROMPT,
                "variables": {
                    "current_feedback_text": None,
                    "current_post_draft": None,
                    "hitl_additional_user_files": ""
                },
                "construct_options": {
                    "current_feedback_text": "current_feedback_text",
                    "current_post_draft": "current_post_draft",
                    "hitl_additional_user_files": "hitl_additional_user_files"
                }
            },
            }
        }
        # Reads: updated_brief from state
        # Writes: additional_brief_prompt, system_prompt
    },

    # --- 9. Interpret Feedback (Structured) ---
    "interpret_feedback": {
        "node_id": "interpret_feedback",
        "node_name": "llm",
        "node_config": {
            "llm_config": {
              "model_spec": {
                "provider": DEFAULT_LLM_PROVIDER,
                "model": DEFAULT_LLM_MODEL
              },
              "temperature": TEMPERATURE,
              "max_tokens": MAX_TOKENS
            },
            "output_schema": { # Define structured output for both rewrite instructions and change summary
                "dynamic_schema_spec": {
                    "schema_name": "FeedbackAnalysis",
                    "fields": {
                        "rewrite_instructions": { "type": "str", "required": True, "description": "Specific instructions for rewriting the content." },
                        "change_summary": { "type": "str", "required": True, "description": "Short, conversational message acknowledging the user's feedback and what will be improved." }
                    }
                }
            }
        }
    },

    # --- 10. Construct Rewrite Prompt ---
    "construct_rewrite_prompt": {  # NOTE: we don't need a system prompt since LLM will have access to message history with preexisting system prompt!
      "node_id": "construct_rewrite_prompt",
      "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
          "rewrite_prompt": {
            "id": "rewrite_prompt",
            "template": POST_CREATION_FEEDBACK_USER_PROMPT,
            "variables": {
                "current_feedback_text": None, # Required from transform_feedback_output
                "rewrite_instructions": None, # Required from transform_feedback_output
                "current_post_draft": None, # Required from transform_feedback_output
                "user_profile": None, # Required for factual context
            },
            "construct_options": { # P1 Sourcing: Map variables to paths within node's input fields
                "rewrite_instructions": "feedback_analysis.rewrite_instructions", # Look inside the mapped 'feedback_analysis' input field
                "current_feedback_text": "current_feedback_text", # Look inside the mapped 'feedback_directives' input field
                "current_post_draft": "current_post_draft", # Look inside the mapped 'feedback_directives' input field
                "user_profile": "linkedin_user_profile", # Use user profile as knowledge base
            }
          }
        }
      }
    },

    # --- 12. Output Node ---
    "output_node": {
      "node_id": "output_node",
      "node_name": "output_node",
      "node_config": {}
    }
  },

  # --- Edges Defining Data Flow ---
  "edges": [
    # --- Initial Setup ---
    # Input -> State: Store initial inputs globally
    { "src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "post_uuid", "dst_field": "post_uuid", "description": "Store the draft name for later use (e.g., saving)."},
        { "src_field": "brief_docname", "dst_field": "brief_docname", "description": "Store the initial brief globally."},
        { "src_field": "entity_username", "dst_field": "entity_username", "description": "Pass the LinkedIn username for scraping."},
        { "src_field": "initial_status", "dst_field": "initial_status", "description": "Initial status for saving drafts."},
        { "src_field": "load_additional_user_files", "dst_field": "load_additional_user_files", "description": "Store additional user files configuration."}
      ]
    },
    # Input -> Transform Additional Files: Pass files to transform
    { "src_node_id": "input_node", "dst_node_id": "transform_additional_files_config", "mappings": [
        { "src_field": "load_additional_user_files", "dst_field": "load_additional_user_files"}
      ]
    },
    # Transform -> Load Additional Files: Pass transformed data
    { "src_node_id": "transform_additional_files_config", "dst_node_id": "load_additional_user_files_node", "mappings": [
        { "src_field": "transformed_data", "dst_field": "transformed_data"}
      ]
    },
    # Load Additional Files -> Construct Initial Prompt: Data-only edge
    { "src_node_id": "load_additional_user_files_node", "dst_node_id": "construct_initial_prompt",
      "data_only_edge": True,
      "mappings": [
        { "src_field": "additional_user_files", "dst_field": "additional_user_files"}
      ]
    },
    # Input -> Load All Context Docs: Explicit mappings
    { "src_node_id": "input_node", "dst_node_id": "load_all_context_docs", "description": "Trigger loading user data after input.",
     "mappings": [
        { "src_field": "post_uuid", "dst_field": "post_uuid"},
        { "src_field": "brief_docname", "dst_field": "brief_docname"},
        { "src_field": "entity_username", "dst_field": "entity_username"},
      ]
     },

    # Load LinkedIn User Profile -> State: Store loaded user data
    { "src_node_id": "load_all_context_docs", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "linkedin_user_profile", "dst_field": "linkedin_user_profile", "description": "Store the loaded LinkedIn user profile document globally."},
        { "src_field": "content_brief", "dst_field": "content_brief", "description": "Store the loaded content brief globally."},
        { "src_field": "linkedin_content_playbook", "dst_field": "linkedin_content_playbook", "description": "Store the loaded LinkedIn content playbook document globally."}
      ]
    },
    # Load LinkedIn User Profile -> Construct Initial Prompt: Provide user data for prompt construction
    { "src_node_id": "load_all_context_docs", "dst_node_id": "construct_initial_prompt", "mappings": [
        { "src_field": "linkedin_user_profile", "dst_field": "linkedin_user_profile", "description": "Pass LinkedIn user profile for extracting style preference."},
        { "src_field": "content_brief", "dst_field": "content_brief", "description": "Pass the content brief for prompt construction."},
        { "src_field": "linkedin_content_playbook", "dst_field": "linkedin_content_playbook", "description": "Pass the LinkedIn content playbook document for prompt construction."}
    ]},

    # --- First Generation Path ---
    # Construct Initial Prompt -> Generate Content: Provide the user and system prompts
    { "src_node_id": "construct_initial_prompt", "dst_node_id": "generate_content", "mappings": [
        { "src_field": "initial_generation_prompt", "dst_field": "user_prompt", "description": "Pass the main generation prompt to the LLM."},
        { "src_field": "system_prompt", "dst_field": "system_prompt", "description": "Pass the system prompt/instructions to the LLM."}
      ]
    },
    # State (Messages) -> Generate Content: Provide conversation history if any (unlikely on first run)
    { "src_node_id": "$graph_state", "dst_node_id": "generate_content", "mappings": [
        { "src_field": "generate_content_messages_history", "dst_field": "messages_history", "description": "Pass existing message history for context."}
      ]
    },

    # --- Parallel Branches Post-Generation ---
    # Generate Content -> Store Draft: Send generated content for initial draft storage
    { "src_node_id": "generate_content", "dst_node_id": "store_draft", "mappings": [
        { "src_field": "structured_output", "dst_field": "structured_output", "description": "Pass the generated post content for saving as a draft. (Parallel Branch 1)"}
      ]
    },
    # State -> Store Draft: Provide draft name for saving
    { "src_node_id": "$graph_state", "dst_node_id": "store_draft", "mappings": [
        { "src_field": "post_uuid", "dst_field": "post_uuid", "description": "Pass the draft name needed by the node's target_path config."},
        { "src_field": "entity_username", "dst_field": "entity_username"},
        { "src_field": "initial_status", "dst_field": "initial_status"}
      ]
    },

    { "src_node_id": "generate_content", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "current_messages", "dst_field": "generate_content_messages_history", "description": "Update message history with the latest interaction."},
        { "src_field": "metadata", "dst_field": "generation_metadata", "description": "Store LLM metadata (e.g., token usage, iteration count)."},
        { "src_field": "structured_output", "dst_field": "current_post_draft", "description": "Store the latest generated post draft globally."}
      ]
    },

    # Generate Content -> Capture Approval: Send generated content for human review
    { "src_node_id": "store_draft", "dst_node_id": "capture_approval", "mappings": [
      ]
    },

    { "src_node_id": "$graph_state", "dst_node_id": "capture_approval", "mappings": [
        { "src_field": "current_post_draft", "dst_field": "draft_for_review", "description": "Pass the generated post content for HITL review. (Parallel Branch 2)"}
      ]
    },

    # --- Approval and Routing ---
    # Capture Approval -> Route on Approval: Send approval status for routing decision
    { "src_node_id": "capture_approval", "dst_node_id": "route_on_approval", "mappings": [
        { "src_field": "user_action", "dst_field": "user_action_from_hitl", "description": "Pass the user's decision ('complete' or 'provide_feedback' or others)."}
      ]
    },
    # Capture Approval -> State: Store user feedback and updated draft
    { "src_node_id": "capture_approval", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "revision_feedback", "dst_field": "current_revision_feedback", "description": "Store the user's feedback text globally."},
        { "src_field": "updated_content_draft", "dst_field": "current_post_draft", "description": "Store the user's updated post draft globally."},
        { "src_field": "user_action", "dst_field": "user_action", "description": "Store the user's approval action."},
        { "src_field": "load_additional_user_files", "dst_field": "hitl_load_additional_user_files", "description": "Store HITL additional user files."}
      ]
    },
    # Capture Approval -> Transform HITL Additional Files: Process HITL additional files
    { "src_node_id": "capture_approval", "dst_node_id": "transform_hitl_additional_files_config", "mappings": [
        { "src_field": "load_additional_user_files", "dst_field": "load_additional_user_files"}
      ]
    },
    # Transform HITL -> Load HITL Additional Files: Pass transformed data
    { "src_node_id": "transform_hitl_additional_files_config", "dst_node_id": "load_hitl_additional_user_files_node", "mappings": [
        { "src_field": "transformed_data", "dst_field": "transformed_data"}
      ]
    },
    # Load HITL Additional Files -> Route on Approval: Provide additional context
    { "src_node_id": "load_hitl_additional_user_files_node", "dst_node_id": "route_on_approval",
      "data_only_edge": True,
      "mappings": [
        { "src_field": "hitl_additional_user_files", "dst_field": "hitl_additional_user_files"}
      ]
    },
    # Route on Approval -> Check Iteration Limit: Control flow if 'provide_feedback'
    { "src_node_id": "route_on_approval", "dst_node_id": "check_iteration_limit", "description": "Trigger iteration check if feedback provided (Control Flow: 'provide_feedback')." },
    # Route on Approval -> Delete Draft on Cancel: Control flow if 'cancel_workflow'
    { "src_node_id": "route_on_approval", "dst_node_id": "delete_draft_on_cancel", "description": "Delete draft and cancel workflow if user cancels (Control Flow: 'cancel_workflow')." },
    # Route on Approval -> Save Final Draft: Control flow if 'save_content'
    { "src_node_id": "route_on_approval", "dst_node_id": "save_final_draft", "description": "Save final draft if approved (Control Flow: 'save_content')." },
    # Route on Approval -> Save Draft: Control flow if 'draft'
    { "src_node_id": "route_on_approval", "dst_node_id": "save_draft", "description": "Save interim draft (Control Flow: 'draft')." },

    # State -> Delete Draft on Cancel: Provide required fields for deletion
    { "src_node_id": "$graph_state", "dst_node_id": "delete_draft_on_cancel", "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username", "description": "Pass entity username for namespace pattern."},
        { "src_field": "post_uuid", "dst_field": "post_uuid", "description": "Pass post UUID for docname pattern."}
      ]
    },
    # Delete Draft on Cancel -> Output: Finalize after deletion
    { "src_node_id": "delete_draft_on_cancel", "dst_node_id": "output_node", "description": "Finalize workflow after deleting draft.", "mappings": [
        { "src_field": "deleted_count", "dst_field": "draft_deleted_count", "description": "Pass count of deleted drafts."}
      ]
    },

    # State -> Save Draft: Provide required fields
    { "src_node_id": "$graph_state", "dst_node_id": "save_draft", "mappings": [
        { "src_field": "current_post_draft", "dst_field": "current_post_draft"},
        { "src_field": "post_uuid", "dst_field": "post_uuid"},
        { "src_field": "entity_username", "dst_field": "entity_username"},
        { "src_field": "initial_status", "dst_field": "initial_status"}
      ]
    },
    # Save Draft -> Back to HITL for further review
    { "src_node_id": "save_draft", "dst_node_id": "capture_approval" },

    # State -> Save Final Draft: Provide required fields
    { "src_node_id": "$graph_state", "dst_node_id": "save_final_draft", "mappings": [
        { "src_field": "current_post_draft", "dst_field": "current_post_draft"},
        { "src_field": "post_uuid", "dst_field": "post_uuid"},
        { "src_field": "entity_username", "dst_field": "entity_username"},
        { "src_field": "user_action", "dst_field": "user_action"}
      ]
    },
 
    # Save Final Draft -> Output: finalize after save
    { "src_node_id": "save_final_draft", "dst_node_id": "output_node", "description": "Finalize workflow after saving final draft.", "mappings": [
        { "src_field": "paths_processed", "dst_field": "final_post_paths", "description": "Pass the paths where the post was saved."}
      ]
    },

    # --- Feedback Loop ---
    # State -> Check Iteration Limit: Provide metadata needed for the check
    { "src_node_id": "$graph_state", "dst_node_id": "check_iteration_limit", "mappings": [
        { "src_field": "generation_metadata", "dst_field": "generation_metadata", "description": "Pass LLM metadata containing iteration count."}
      ]
    },
    # Check Iteration Limit -> Route on Limit Check: Send check results for routing
    { "src_node_id": "check_iteration_limit", "dst_node_id": "route_on_limit_check", "mappings": [
        { "src_field": "branch", "dst_field": "iteration_branch_result", "description": "Pass the branch taken ('true_branch' if limit not reached, 'false_branch' if reached)."},
        { "src_field": "tag_results", "dst_field": "if_else_condition_tag_results", "description": "Pass detailed results per condition tag."},
        { "src_field": "condition_result", "dst_field": "if_else_overall_condition_result", "description": "Pass the overall boolean result of the check."}
      ]
    },
    # Route on Limit Check -> Interpret Feedback: Control flow if iteration limit NOT reached
    { "src_node_id": "route_on_limit_check", "dst_node_id": "route_to_initial_or_additional_prompt", "description": "Trigger feedback interpretation if iterations remain (Control Flow: 'true_branch')." },
    # Route on Limit Check -> Finalize Post: Control flow if iteration limit REACHED
    { "src_node_id": "route_on_limit_check", "dst_node_id": "output_node", "description": "Trigger finalization if iteration limit reached (Control Flow: 'false_branch')." },
    # State -> Output (via iteration limit): Include current draft in final outputs when limit is reached
    { "src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
        { "src_field": "current_post_draft", "dst_field": "final_post_content", "description": "Include the latest post draft in final outputs when iteration limit is reached."}
      ]
    },


    # --- Edges for router to appropriate prompt constructor ---
    # State -> Router: Provide metadata for routing decision
    { "src_node_id": "$graph_state", "dst_node_id": "route_to_initial_or_additional_prompt", "mappings": [
        { "src_field": "generation_metadata", "dst_field": "generation_metadata", 
          "description": "Pass iteration count for routing decision."}
      ]
    },
    # Router -> Initial Prompt Constructor: Control flow for first iteration
    { "src_node_id": "route_to_initial_or_additional_prompt", "dst_node_id": "construct_user_feedback_initial_prompt", 
      "description": "Route to initial prompt constructor if first iteration."
    },
    # Router -> Additional Prompt Constructor: Control flow for subsequent iterations
    { "src_node_id": "route_to_initial_or_additional_prompt", "dst_node_id": "construct_user_feedback_additional_prompt", 
      "description": "Route to additional prompt constructor if not first iteration."
    },

    # --- Edges for initial feedback prompt constructor ---
    # State -> Initial Prompt Constructor: Provide necessary context
    { "src_node_id": "$graph_state", "dst_node_id": "construct_user_feedback_initial_prompt", "mappings": [
        { "src_field": "current_revision_feedback", "dst_field": "current_feedback_text",
          "description": "Pass feedback for prompt construction."},
        { "src_field": "current_post_draft", "dst_field": "current_post_draft",
          "description": "Pass latest draft for context."},
        { "src_field": "linkedin_user_profile", "dst_field": "linkedin_user_profile",
          "description": "Pass LinkedIn user profile for knowledge base context."}
      ]
    },
    # Load HITL Additional Files -> Initial Feedback Prompt: Data-only edge
    { "src_node_id": "load_hitl_additional_user_files_node", "dst_node_id": "construct_user_feedback_initial_prompt",
      "data_only_edge": True,
      "mappings": [
        { "src_field": "hitl_additional_user_files", "dst_field": "hitl_additional_user_files"}
      ]
    },
    # Initial Prompt Constructor -> Interpret Feedback: Send constructed prompt
    { "src_node_id": "construct_user_feedback_initial_prompt", "dst_node_id": "interpret_feedback", "mappings": [
        { "src_field": "interpret_feedback_prompt", "dst_field": "user_prompt", 
          "description": "Pass the constructed initial prompt for feedback interpretation."},
        { "src_field": "system_prompt", "dst_field": "system_prompt", 
          "description": "Pass the system prompt for feedback analysis."}
      ]
    },

    # --- Edges for additional feedback prompt constructor ---
    # State -> Additional Prompt Constructor: Provide necessary context
    { "src_node_id": "$graph_state", "dst_node_id": "construct_user_feedback_additional_prompt", "mappings": [
        { "src_field": "current_revision_feedback", "dst_field": "current_feedback_text",
          "description": "Pass feedback for prompt construction."},
        { "src_field": "current_post_draft", "dst_field": "current_post_draft",
          "description": "Pass the current post draft for context."}
      ]
    },
    # Load HITL Additional Files -> Additional Feedback Prompt: Data-only edge
    { "src_node_id": "load_hitl_additional_user_files_node", "dst_node_id": "construct_user_feedback_additional_prompt",
      "data_only_edge": True,
      "mappings": [
        { "src_field": "hitl_additional_user_files", "dst_field": "hitl_additional_user_files"}
      ]
    },
    
    # Additional Prompt Constructor -> Interpret Feedback: Send constructed prompt
    { "src_node_id": "construct_user_feedback_additional_prompt", "dst_node_id": "interpret_feedback", "mappings": [
        { "src_field": "interpret_feedback_prompt", "dst_field": "user_prompt", 
          "description": "Pass the constructed additional prompt for feedback interpretation."}
      ]
    },

    # State -> Interpret Feedback: Provide necessary context for feedback analysis
    { "src_node_id": "$graph_state", "dst_node_id": "interpret_feedback", "mappings": [
        { "src_field": "interpret_feedback_messages_history", "dst_field": "messages_history", "description": "Pass message history for LLM context."},
        # { "src_field": "current_feedback_text", "dst_field": "user_prompt", "description": "Pass the user's feedback as the main input user_prompt for analysis."} # Assuming the LLM node expects 'prompt_for_feedback_analysis' based on its config comments
      ]
    },
    # Interpret Feedback -> Construct Rewrite Prompt: Send structured feedback interpretation
    { "src_node_id": "interpret_feedback", "dst_node_id": "construct_rewrite_prompt", "mappings": [
        { "src_field": "structured_output", "dst_field": "feedback_analysis", "description": "Pass the complete feedback analysis for accessing rewrite instructions."}
      ]
    },
     # State -> Additional Prompt Constructor: Provide necessary context
    { "src_node_id": "$graph_state", "dst_node_id": "construct_rewrite_prompt", "mappings": [
        { "src_field": "current_revision_feedback", "dst_field": "current_feedback_text", 
          "description": "Pass feedback for prompt construction."},
        { "src_field": "current_post_draft", "dst_field": "current_post_draft",
          "description": "Pass the current post draft for context."},
        { "src_field": "feedback_analysis", "dst_field": "feedback_analysis",
          "description": "Pass the feedback analysis containing rewrite instructions."},
        { "src_field": "linkedin_user_profile", "dst_field": "linkedin_user_profile",
          "description": "Pass LinkedIn user profile for knowledge base context."}
      ]
    },
    # Interpret Feedback -> State: Store the change summary for HITL display and update message history
    { "src_node_id": "interpret_feedback", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "structured_output", "dst_field": "feedback_analysis", "description": "Store the complete feedback analysis including change summary."},
        { "src_field": "current_messages", "dst_field": "interpret_feedback_messages_history", "description": "Update message history with the feedback analysis interaction."}
      ]
    },
    # Construct Rewrite Prompt -> Generate Content: Send the new prompt for regeneration
    { "src_node_id": "construct_rewrite_prompt", "dst_node_id": "generate_content", "mappings": [
        { "src_field": "rewrite_prompt", "dst_field": "user_prompt", "description": "Pass the rewrite prompt back to the main LLM node to generate a revised post."}
      ]
    }, # This completes the feedback loop, flowing back to Generate Content
  ],

  # --- Define Start and End ---
  "input_node_id": "input_node",
  "output_node_id": "output_node",

  "metadata": {
      "$graph_state": {
          "reducer": {
              "generate_content_messages_history": "add_messages",
              "interpret_feedback_messages_history": "add_messages",
              "load_additional_user_files": "replace",
              "hitl_load_additional_user_files": "replace"
          }
      }
  }
}