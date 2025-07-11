from kiwi_client.workflows.document_models.customer_docs import (
    # User DNA
    USER_DNA_DOCNAME,
    USER_DNA_NAMESPACE_TEMPLATE,
    USER_DNA_IS_VERSIONED,
    # Content Drafts
    CONTENT_DRAFT_DOCNAME,
    CONTENT_DRAFT_NAMESPACE_TEMPLATE,
    CONTENT_DRAFT_IS_VERSIONED,
    # Content Brief
    CONTENT_BRIEF_DOCNAME,
    CONTENT_BRIEF_NAMESPACE_TEMPLATE,
    CONTENT_BRIEF_IS_VERSIONED,
    CONTENT_BRIEF_DEFAULT_VERSION,
    CONTENT_BRIEF_FINAL_VERSION,
    # Knowledge Base Analysis
    USER_KNOWLEDGE_BASE_ANALYSIS_DOCNAME_TEMPLATE,
    USER_KNOWLEDGE_BASE_ANALYSIS_NAMESPACE_TEMPLATE,
    USER_KNOWLEDGE_BASE_ANALYSIS_IS_VERSIONED,
)
from kiwi_client.workflows.llm_inputs.content_generation import (
    POST_CREATION_FEEDBACK_USER_PROMPT,
    POST_CREATION_INITIAL_USER_PROMPT,
    POST_CREATION_SYSTEM_PROMPT,
    USER_FEEDBACK_INITIAL_USER_PROMPT,
    USER_FEEDBACK_SYSTEM_PROMPT,
    USER_FEEDBACK_ADDITIONAL_USER_PROMPT,
    POST_LLM_OUTPUT_SCHEMA
)

llm_provider = "anthropic"
generation_model_name = "claude-3-7-sonnet-20250219"
temperature = 0.5
max_tokens = 2000
max_iterations = 10
feedback_llm_provider = "anthropic"
feedback_analysis_model = "claude-3-7-sonnet-20250219"


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
              "customer_context_doc_configs": {
                  "type": "list",
                  "required": True,
                  "description": "List of document identifiers (namespace/docname pairs) for customer context like DNA, strategy docs."
              },
              "post_uuid": { "type": "str", "required": True, "description": "UUID of the post being drafted for saving." },
              "brief_docname": { "type": "str", "required": True, "description": "Docname of the brief being used for drafting." },
              "entity_username": { "type": "str", "required": True, "description": "Username of the entity for which the post is being drafted." },
          }
        }
    },
    # Defines workflow start inputs: post_uuid, brief_docname, entity_username
    # outgoing edges:
    #  - stores post_uuid to $graph_state
    #  - stores brief_docname to $graph_state

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
            # "global_version_config": {"version": "default"},
            "global_schema_options": {"load_schema": False},
        },
    },

    # --- 3. Construct Initial Prompt ---
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
              "user_dna": None, # Default if not found via construct_options
              "knowledge_base_analysis": None, # Added for factual context
            },
            "construct_options": { # P1 Sourcing: Map variables to paths within node's input fields
               "user_dna": "user_dna", # Look inside the mapped 'user_dna_doc' input field
               "brief": "content_brief", # Look inside the mapped 'brief_docname' input field
               "knowledge_base_analysis": "knowledge_base_analysis", # Added for factual context
            }
          },
          "system_prompt": {  # NOTE: this can directly be set in the LLM node too! But putting it here for using template variables!
            "id": "system_prompt",
            "template": POST_CREATION_SYSTEM_PROMPT,
            "variables": {
            }
          }
        }
      }
      # Reads: brief_docname (from $graph_state), user_dna_doc (from `load_all_context_docs`)
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
            "provider": f"{llm_provider}", # e.g., "openai"
            "model": f"{generation_model_name}" # e.g., "gpt-4-turbo"
          },
          "temperature": temperature, # Low temperature for deterministic interpretation
          "max_tokens": max_tokens,
        },
        # Define the structured output for the post
        "output_schema": {
          "schema_definition": POST_LLM_OUTPUT_SCHEMA,
          "convert_loaded_schema_to_pydantic": False
          # "dynamic_schema_spec": {
          #   "schema_name": "LinkedInPost",
          #   "fields": {
          #     # NOTE: Ensure these match the schema provided in linked_in_schema_string and used in prompts
          #     "post_text": { "type": "str", "required": True, "description": "The main body of the LinkedIn post." },
          #     "hashtags": { "type": "list", "items_type": "str", "required": True, "description": "Suggested hashtags." }
          #   }
          # }
        }
        # Input prompt field name will be 'user_prompt' , 'system_prompt'
        # Also expects 'messages_history' as input if available from $graph_state
      }
      # Reads: user_prompt, system_prompt (from construct_initial_prompt OR construct_rewrite_prompt), 
      # Reads: messages_history (from $graph_state)
      # Writes: structured_output (the post), content, metadata, current_messages
      # Outgoing edges
      #   - Sends: structured_output to store_draft
      #   - Sends: structured_output -> draft_for_review to capture_approval
      #   - Sends: messages_history -> to $graph_state
      #   - Sends: structured_output -> `current_post_draft` to $graph_state
      #   - Sends: metadata -> `generation_metadata` to $graph_state
    },

    # --- 5. Store Draft ---
    # TODO: CHECK if post is correctly saved given interrupt in parallel branch!
    "store_draft": {  # NOTE: this is demonstrating node parallism / branching for now and under what conditions it should be used! Store Branch post LLM generation
      "node_id": "store_draft",
      "node_name": "store_customer_data",
      "node_config": {
        "global_versioning": {
          "is_versioned": True,
          "operation": "initialize", # Must not exist yet
          "version": "draft_v1" # Name the initial version
        },
        "store_configs": [
            
            {
                # Also store the selected concepts that were used
                "input_field_path": "structured_output", # Mapped from filter_selected_concepts
                "target_path": {
                    "filename_config": {
                        "input_namespace_field_pattern": CONTENT_DRAFT_NAMESPACE_TEMPLATE, 
                        "input_namespace_field": "entity_username",
                        "input_docname_field_pattern": CONTENT_DRAFT_DOCNAME, 
                        "input_docname_field": "post_uuid",
                    }
                },
                "extra_fields": [
                    {
                        # Required: Path to value in input data
                        "src_path": "content_brief.uuid",
                        
                        # Optional: Path where value should be placed in stored object
                        # If not provided, defaults to last segment of src_path
                        "dst_path": "brief_id"
                    },
                    {
                        # Add scheduled_date from content_brief
                        "src_path": "content_brief.scheduled_date",
                        "dst_path": "scheduled_date"
                    }
                ],
                "versioning": {
                    "is_versioned": CONTENT_DRAFT_IS_VERSIONED,
                    "operation": "upsert_versioned",
                }
            }
          
        ]
      }
      # Reads: `post_uuid` from central State
      # Reads: structured_output (mapped from generate_content.structured_output)
    },

    # --- 6. Human Review ---
    "capture_approval": {  # NOTE: this is demonstrating node parallism / branching for now and under what conditions it should be used! HITL Branch post LLM generation
      "node_id": "capture_approval",
      "node_name": "hitl_node__default",
      "node_config": {}, # Config removed as base HITLNode ignores it
      "dynamic_output_schema": {
          "fields": {
              "approval_status": { "type": "enum", "enum_values": ["approved", "needs_work"], "required": True, "description": "User decision on the draft." },
              "feedback_text": { "type": "str", "required": False, "description": "Optional feedback text from the user." }
          }
      },
      # Reads: draft_for_review (mapped from generate_content.structured_output)
      # Writes: approval_status, feedback_text
      # Outgoing edges
      #   - Sends: approval_status -> approval_status_from_hitl to route_on_approval
      #   - Sends: feedback_text -> current_feedback_text to $graph_state
    },

    # --- 7. Route Based on Approval ---
    "route_on_approval": {
      "node_id": "route_on_approval",
      "node_name": "router_node",
      "node_config": {
        "choices": ["check_iteration_limit", "output_node"], # Node IDs to route to
        "allow_multiple": False,
        "choices_with_conditions": [
          {
            "choice_id": "check_iteration_limit", # Route to feedback loop (needs iteration check first)
            "input_path": "approval_status_from_hitl", # Path WITHIN the node's input data
            "target_value": "needs_work"
          },
          {
            "choice_id": "output_node", # Route to final storage
            "input_path": "approval_status_from_hitl", # Path WITHIN the node's input data
            "target_value": "approved"
          }
        ]
        # Removed default_choice (NOT SUPPORTED AS OF NOW!) - relies on the conditions covering expected values
      }
      # Reads: approval_status_from_hitl (mapped from capture_approval.approval_status)
      # Routes execution, passes state implicitly.
      # Outgoing edges (Routes execution)
      #   - Send: check_iteration_limit (no mapping)
      #   - Send: output_node (no mapping)
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
                            "value": max_iterations
                        } ]
                    } ],
                    "group_logical_operator": "and" # Operator between groups (only one group here)
                }
            ],
            "branch_logic_operator": "and"
        }
        # Reads: generation_metadata from $graph_state
        # Writes: branch ('true_branch' or 'false_branch') in `branch`; tag_results ; condition_result
        # Outgoing edges
        #   - route_on_limit_check:
        #     - Send: tag_results -> if_else_condition_tag_results to `route_on_limit_check`
        #     - Send: condition_result -> if_else_overall_condition_result to `route_on_limit_check`
        #     - Send: branch -> iteration_branch_result (no mapping) to `route_on_limit_check`
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
                # NOTE: this is the alternative way to check the overall condition result across all tags!
                # {
                #     "choice_id": "output_node", # Limit reached, finalize
                #     "input_path": "if_else_overall_condition_result", # Path WITHIN the node's input data
                #     "target_value": "False" # Value output by check_iteration_limit
                # }
            ]
        }
        # Reads: if_else_condition_tag_results, `route_on_limit_check`, iteration_branch_result from `check_iteration_limit`
        # Outgoing edges
        #   - Routes execution (no mapping in outgoing edges) to ["route_to_initial_or_additional_prompt", "output_node"].
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
                    "user_dna_doc": None,
                },
                "construct_options": {
                    "current_feedback_text": "current_feedback_text",
                    "current_post_draft": "current_post_draft",
                    "user_dna_doc": "user_dna",
                }
            },
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
                    "current_feedback_text": None
                },
                "construct_options": {
                    "current_feedback_text": "current_feedback_text",
                    "current_post_draft": "current_post_draft",
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
                "provider": feedback_llm_provider, # e.g., "openai"
                "model": feedback_analysis_model # e.g., "gpt-3.5-turbo"
              },
              "temperature": temperature, # Low temperature for deterministic interpretation
              "max_tokens": max_tokens,
            },
            "default_system_prompt": USER_FEEDBACK_SYSTEM_PROMPT, # Optional default if no system message in input
            "output_schema": { # Define structured output for both rewrite instructions and change summary
                "dynamic_schema_spec": {
                    "schema_name": "FeedbackAnalysis",
                    "fields": {
                        "rewrite_instructions": { "type": "str", "required": True, "description": "Specific instructions for rewriting the content." },
                        "change_summary": { "type": "str", "required": True, "description": "Short, conversational message acknowledging the user's feedback and what will be improved." }
                    }
                }
            }
            # Input prompt field name will be 'user_prompt'
            # Also expects 'messages_history' as input if available from $graph_state
        }
        # Reads: current_feedback_text, messages_history (from $graph_state)
        # Writes: structured_output (containing rewrite_instructions and change_summary)
        # Outgoing edges
        #   - Sends: structured_output.rewrite_instructions -> rewrite_instructions to `construct_rewrite_prompt`
        #   - Sends: structured_output.change_summary -> change_summary to $graph_state
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
                # Available from previous `message_history`!
                # "original_post": None, # Required from $graph_state.original_draft_content
                "current_feedback_text": None, # Required from transform_feedback_output
                "rewrite_instructions": None, # Required from transform_feedback_output
                "current_post_draft": None, # Required from transform_feedback_output
                "knowledge_base_analysis": None, # Added for factual context
                # "user_style": "default", # Default if not found via construct_options
                # "schema_definition": None # Required via construct_options
                # "schema_definition": f"{LinkedInPostSchemaDefinition}" # Required (placeholder for actual schema JSON string or loaded value)
            },
            "construct_options": { # P1 Sourcing: Map variables to paths within node's input fields
                "rewrite_instructions": "feedback_analysis.rewrite_instructions", # Look inside the mapped 'feedback_analysis' input field
                "current_feedback_text": "current_feedback_text", # Look inside the mapped 'feedback_directives' input field
                "current_post_draft": "current_post_draft", # Look inside the mapped 'feedback_directives' input field
                "knowledge_base_analysis": "knowledge_base_analysis", # Added for factual context
                # NOTE: user_style, brief not required here probably since they wil be available from previous `message_history`!
                # "user_style": "user_dna_doc.style_preference", # Look inside the mapped 'user_dna_doc' input field
                # "brief": "brief_docname", # Look inside the mapped 'brief_docname' input field
            }
          }
        }
      }
      # Reads: rewrite_interpretation (mapped from `interpret_feedback`)
      # Writes: rewrite_prompt
      # Outgoing edges
      #   - Sends: rewrite_prompt -> to user_prompt in LLM Node
    },

    # --- 12. Output Node ---
    "output_node": {
      "node_id": "output_node",
      "node_name": "output_node",
      "node_config": {}
    }
    # Reads: `paths_processed` from store_draft
    # Reads: `current_post_draft` from central State
  },

  # --- Edges Defining Data Flow ---
  "edges": [
    # --- Initial Setup ---
    # Input -> State: Store initial inputs globally
    { "src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "post_uuid", "dst_field": "post_uuid", "description": "Store the draft name for later use (e.g., saving)."},
        { "src_field": "brief_docname", "dst_field": "brief_docname", "description": "Store the initial brief globally."},
        { "src_field": "entity_username", "dst_field": "entity_username", "description": "Pass the LinkedIn username for scraping."},
        { "src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs", "description": "Store the context document configurations globally."}
      ]
    },
    # Input -> Load All Context Docs: Explicit mappings
    { "src_node_id": "input_node", "dst_node_id": "load_all_context_docs", "description": "Trigger loading user data after input." ,
     "mappings": [
        { "src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs"},
        { "src_field": "entity_username", "dst_field": "entity_username"},
        { "src_field": "brief_docname", "dst_field": "brief_docname"},
      ]
     
     },

    # Load User DNA -> State: Store loaded user data
    { "src_node_id": "load_all_context_docs", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "user_dna", "dst_field": "user_dna", "description": "Store the loaded user DNA document globally."},
        { "src_field": "content_brief", "dst_field": "content_brief", "description": "Store the loaded content brief globally."},
        { "src_field": "knowledge_base_analysis", "dst_field": "knowledge_base_analysis", "description": "Store the loaded knowledge base analysis globally."}
      ]
    },
    # Load User DNA -> Construct Initial Prompt: Provide user data for prompt construction
    { "src_node_id": "load_all_context_docs", "dst_node_id": "construct_initial_prompt", "mappings": [
        { "src_field": "user_dna", "dst_field": "user_dna", "description": "Pass user DNA for extracting style preference."},
        { "src_field": "content_brief", "dst_field": "content_brief", "description": "Pass the content brief for prompt construction."},
        { "src_field": "knowledge_base_analysis", "dst_field": "knowledge_base_analysis", "description": "Pass knowledge base analysis for factual context."}
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
        { "src_field": "content_brief", "dst_field": "content_brief"},
        { "src_field": "entity_username", "dst_field": "entity_username"}
      ]
    },
    { "src_node_id": "store_draft", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "paths_processed", "dst_field": "paths_processed", "description": "Pass the paths processed by the node."},
        { "src_field": "passthrough_data", "dst_field": "passthrough_data", "description": "Pass the passthrough data of the draft."}
      ]
    },
    # Generate Content -> Capture Approval: Send generated content for human review
    { "src_node_id": "generate_content", "dst_node_id": "capture_approval", "mappings": [
        { "src_field": "structured_output", "dst_field": "draft_for_review", "description": "Pass the generated post content for HITL review. (Parallel Branch 2)"}
      ]
    },

    { "src_node_id": "$graph_state", "dst_node_id": "capture_approval", "mappings": [
        { "src_field": "paths_processed", "dst_field": "draft_paths_processed"},
        { "src_field": "feedback_analysis", "dst_field": "feedback_analysis", "description": "Pass complete feedback analysis to extract change summary within the node"}
      ]
    },

    # --- Update State Post-Generation ---
    # Generate Content -> State: Update global state with results and context
    { "src_node_id": "generate_content", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "current_messages", "dst_field": "generate_content_messages_history", "description": "Update message history with the latest interaction."},
        { "src_field": "metadata", "dst_field": "generation_metadata", "description": "Store LLM metadata (e.g., token usage, iteration count)."},
        { "src_field": "structured_output", "dst_field": "current_post_draft", "description": "Store the latest generated post draft globally."}
      ]
    },

    # --- Approval and Routing ---
    # Capture Approval -> Route on Approval: Send approval status for routing decision
    { "src_node_id": "capture_approval", "dst_node_id": "route_on_approval", "mappings": [
        { "src_field": "approval_status", "dst_field": "approval_status_from_hitl", "description": "Pass the user's decision ('approved' or 'needs_work')."}
      ]
    },
    # Capture Approval -> State: Store user feedback and updated draft
    { "src_node_id": "capture_approval", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "feedback_text", "dst_field": "current_feedback_text", "description": "Store the user's feedback text globally."},
        { "src_field": "updated_post_draft", "dst_field": "current_post_draft", "description": "Store the updated post draft globally."}
      ]
    },
    # Route on Approval -> Check Iteration Limit: Control flow if 'needs_work'
    { "src_node_id": "route_on_approval", "dst_node_id": "check_iteration_limit", "description": "Trigger iteration check if feedback provided (Control Flow: 'needs_work')." },
    # Route on Approval -> Finalize Post: Control flow if 'approved'
    { "src_node_id": "route_on_approval", "dst_node_id": "output_node", "description": "Trigger finalization if post approved (Control Flow: 'approved')." },

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
        { "src_field": "current_feedback_text", "dst_field": "current_feedback_text", 
          "description": "Pass feedback for prompt construction."},
        { "src_field": "current_post_draft", "dst_field": "current_post_draft", 
          "description": "Pass latest draft for context."},
        { "src_field": "user_dna", "dst_field": "user_dna", 
          "description": "Pass user DNA for style context."},
        { "src_field": "knowledge_base_analysis", "dst_field": "knowledge_base_analysis", 
          "description": "Pass knowledge base analysis for factual context in feedback interpretation."}
      ]
    },
    # Initial Prompt Constructor -> Interpret Feedback: Send constructed prompt
    { "src_node_id": "construct_user_feedback_initial_prompt", "dst_node_id": "interpret_feedback", "mappings": [
        { "src_field": "interpret_feedback_prompt", "dst_field": "user_prompt", 
          "description": "Pass the constructed initial prompt for feedback interpretation."}
      ]
    },

    # --- Edges for additional feedback prompt constructor ---
    # State -> Additional Prompt Constructor: Provide necessary context
    { "src_node_id": "$graph_state", "dst_node_id": "construct_user_feedback_additional_prompt", "mappings": [
        { "src_field": "current_feedback_text", "dst_field": "current_feedback_text", 
          "description": "Pass feedback for prompt construction."},
        { "src_field": "current_post_draft", "dst_field": "current_post_draft",
          "description": "Pass the current post draft for context."},
        { "src_field": "knowledge_base_analysis", "dst_field": "knowledge_base_analysis", 
          "description": "Pass knowledge base analysis for factual context in feedback interpretation."}
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
        { "src_field": "current_feedback_text", "dst_field": "current_feedback_text", 
          "description": "Pass feedback for prompt construction."},
        { "src_field": "current_post_draft", "dst_field": "current_post_draft",
          "description": "Pass the current post draft for context."},
        { "src_field": "knowledge_base_analysis", "dst_field": "knowledge_base_analysis", 
          "description": "Pass knowledge base analysis for factual context in rewrite."},
        { "src_field": "feedback_analysis", "dst_field": "feedback_analysis",
          "description": "Pass the feedback analysis containing rewrite instructions."}
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

    # --- Finalization Path ---
    # State -> Finalize Post: Provide the final draft content and name for saving
    { "src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
        { "src_field": "current_post_draft", "dst_field": "final_post_content", "description": "Pass the final approved post content for saving."},
        { "src_field": "paths_processed", "dst_field": "final_post_paths", "description": "Pass the path(s) or ID(s) of the finalized stored document(s)."}, # Assuming Store node outputs 'paths_processed'
        { "src_field": "passthrough_data", "dst_field": "passthrough_data", "description": "Pass the passthrough data of the draft."}
      ]
    },
  ],

  # --- Define Start and End ---
  "input_node_id": "input_node",
  "output_node_id": "output_node",

#   # --- Optional Metadata ---
#   "metadata": {
#     # State reducers define how to merge data written to the same key in $graph_state.
#      "state_reducers": {
#        "messages_history": { "reducer_type": "add_messages", "description": "Append new messages to maintain conversation history."},
#        "generation_metadata": { "reducer_type": "replace", "description": "Replace with the latest LLM metadata (e.g., iteration count)."},
#        "current_post_draft": { "reducer_type": "replace", "description": "Replace with the latest generated/approved draft."},
#        "current_feedback_text": { "reducer_type": "replace", "description": "Replace with the latest feedback received."},
#        # Other state keys like post_uuid, brief_docname, user_dna_doc are typically written once, so default 'replace' is fine.
#      }
#   }

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

# --- Inputs for the Post Creation Workflow ---
# These inputs match the 'input_node' dynamic_output_schema



import asyncio
import logging
from typing import Dict, Any, Optional, List

# Configure logging
logging.basicConfig(level=logging.INFO) # Use INFO level for less verbose output
logger = logging.getLogger(__name__)

# Import the new helper function and necessary types
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
# CustomerDataTestClient is no longer directly needed in main, but keep for potential future use or reference
# from kiwi_client.customer_data_client import CustomerDataTestClient

# Schema imports
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

# Removed the ensure_user_dna_exists function as setup is handled by run_workflow_test


async def validate_content_workflow_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Custom validation function for the content creation workflow outputs.

    Args:
        outputs: The dictionary of final outputs from the workflow run.

    Returns:
        True if the outputs are valid, False otherwise.

    Raises:
        AssertionError: If the outputs are None or do not contain the expected keys.
    """
    # Ensure outputs exist
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating content workflow outputs...")

    # Check for expected keys in the output
    assert 'final_post_paths' in outputs, "Validation Failed: 'final_post_paths' key missing in outputs."
    assert 'final_post_content' in outputs, "Validation Failed: 'final_post_content' key missing in outputs."

    # Optional: Add more sophisticated checks here, e.g., check content format, path validity etc.
    logger.info(f"   Found 'final_post_paths': {outputs.get('final_post_paths')}")
    logger.info(f"   Found 'final_post_content' (snippet): {str(outputs.get('final_post_content'))[:100]}...")
    
    # Validate specific structure of the post content if needed
    if 'final_post_content' in outputs:
        post_content = outputs.get('final_post_content')
        assert 'post_text' in post_content, "Validation Failed: 'post_text' missing in content."
        assert 'hashtags' in post_content, "Validation Failed: 'hashtags' missing in content."
        assert isinstance(post_content['hashtags'], list), "Validation Failed: 'hashtags' should be a list."
        
        # Validate that the post text incorporates knowledge base analysis
        post_text = post_content['post_text']
        assert len(post_text) > 0, "Validation Failed: Post text is empty"
        # Check for factual information and company-specific details
        assert any(keyword in post_text.lower() for keyword in ['according to', 'research shows', 'studies indicate', 'data suggests']), \
            "Validation Failed: Post should include factual information from knowledge base"
    
    logger.info("✓ Output structure validation passed.")
    return True


async def main_test_content_workflow_with_client():
    """
    Tests the Post Creation Workflow using the run_workflow_test helper function.
    Includes setup for user DNA, content brief, and knowledge base analysis, handles HITL steps with pre-defined inputs,
    validates output, and performs cleanup.
    """
    test_name = "Content Workflow Test"
    print(f"--- Starting {test_name} --- ")

    # Define test parameters
    test_entity_username = "example-user"
    test_post_uuid = "test_post_uuid"
    brief_docname = "brief_docname"
    
    # Define user DNA namespace based on the template
    user_dna_namespace = USER_DNA_NAMESPACE_TEMPLATE.format(item=test_entity_username)
    user_dna_docname = USER_DNA_DOCNAME
    
    # Define content brief namespace based on the template
    content_brief_namespace = CONTENT_BRIEF_NAMESPACE_TEMPLATE.format(item=test_entity_username)
    
    # Define draft storage namespace based on the template
    draft_storage_namespace = CONTENT_DRAFT_NAMESPACE_TEMPLATE.format(item=test_entity_username)

    # Define knowledge base analysis namespace
    knowledge_base_namespace = USER_KNOWLEDGE_BASE_ANALYSIS_NAMESPACE_TEMPLATE.format(item=test_entity_username)
    knowledge_base_docname = USER_KNOWLEDGE_BASE_ANALYSIS_DOCNAME_TEMPLATE.format(item=test_entity_username)

    # Define test context document configurations
    test_context_docs = [{
            "filename_config": {
                "input_namespace_field_pattern": USER_DNA_NAMESPACE_TEMPLATE, 
                "input_namespace_field": "entity_username",
                "static_docname": USER_DNA_DOCNAME,
            },
            "output_field_name": "user_dna"  # Field where the loaded DNA doc will be stored
        },
        {
            "filename_config": {
                "input_namespace_field_pattern": CONTENT_BRIEF_NAMESPACE_TEMPLATE, 
                "input_namespace_field": "entity_username",
                "input_docname_field": "brief_docname",
            },
            "output_field_name": "content_brief"  # Field where the loaded brief will be stored
        },
        {
            "filename_config": {
                "input_namespace_field_pattern": USER_KNOWLEDGE_BASE_ANALYSIS_NAMESPACE_TEMPLATE,
                "input_namespace_field": "entity_username",
                "static_docname": USER_KNOWLEDGE_BASE_ANALYSIS_DOCNAME_TEMPLATE,
            },
            "output_field_name": "knowledge_base_analysis"  # Field where the loaded knowledge base analysis will be stored
        }
    ]

    # Define workflow input parameters
    POST_CREATION_WORKFLOW_INPUTS = {
        "post_uuid": test_post_uuid,
        "brief_docname": brief_docname,
        "customer_context_doc_configs": test_context_docs,
        "entity_username": test_entity_username
    }

    # Define the setup documents to be created before workflow execution
    setup_docs: List[SetupDocInfo] = [
        # User DNA Document
        {
            'namespace': user_dna_namespace,
            'docname': user_dna_docname,
            'initial_data': {
                "professional_background": "Digital marketing expert with 10+ years experience in B2B SaaS",
                "expertise_areas": ["Content Marketing", "Brand Development", "Social Media Strategy"],
                "target_audience": "Marketing directors and CMOs in technology companies",
                "content_goals": "Establish thought leadership and drive engagement on LinkedIn",
                "personal_style": "Professional with conversational elements",
                "personal_brand_statement": "Helping tech companies build authentic marketing narratives",
                "tone": "informative",
                "style_preference": "professional",
                "preferred_hashtags": ["#MarketingStrategy", "#ContentCreation", "#B2BTech", "#SaaS"]
            },
            'is_shared': False,
            'is_versioned': USER_DNA_IS_VERSIONED,
            'initial_version': "default",
            'is_system_entity': False
        },
        
        # Content Brief Document
        {
            'namespace': content_brief_namespace,
            'docname': brief_docname,
            'initial_data': {
                "uuid": brief_docname,
                "title": "Effective Content Strategy for B2B SaaS Companies",
                "core_perspective": "Content strategy should align with customer journey touchpoints",
                "key_messages": [
                    "Quality content drives better conversions than quantity",
                    "Technical content must be accessible to non-technical decision makers",
                    "Case studies with quantifiable results are the most effective B2B content"
                ],
                "target_audience": {
                    "primary": "B2B SaaS Marketing Directors",
                    "secondary": "Product Managers interested in go-to-market strategy"
                },
                "content_pillar": "B2B Content Strategy",
                "post_objectives": ["Educate audience", "Position as thought leader", "Generate discussion"],
                "tone_and_style": "Professional but approachable, data-backed with practical insights",
                "call_to_action": "Share your experience with B2B content strategy in the comments",
                "hashtags": ["#B2BMarketing", "#ContentStrategy", "#SaaS", "#MarketingROI"],
                "evidence_and_examples": ["Recent McKinsey report on B2B marketing", "HubSpot study on SaaS content"],
                "scheduled_date": "2025-05-26T10:00:00Z",
                "structure_outline": {
                    "opening_hook": "Most B2B companies treat content as a checkbox, not a conversion tool",
                    "core_perspective": "Effective B2B content aligns with specific stages of the customer journey",
                    "supporting_evidence": "Companies with documented content strategies have 3x higher conversion rates",
                    "practical_framework": "The 3T approach: Target, Tailor, Track",
                    "engagement_question": "What's your biggest challenge with B2B content development?"
                },
                "suggested_hook_options": [
                    "73% of B2B buyers don't read most of the content they download. Here's why...",
                    "If your content strategy doesn't segment by buying stage, you're leaving money on the table.",
                    "Tech companies consistently make one critical content mistake that costs them qualified leads."
                ],
                "post_length": {
                    "min": 400,
                    "max": 700
                }
            },
            'is_shared': False,
            'is_versioned': CONTENT_BRIEF_IS_VERSIONED,
            'initial_version': CONTENT_BRIEF_DEFAULT_VERSION,
            'is_system_entity': False
        },
        
        # Knowledge Base Analysis Document
        {
            'namespace': knowledge_base_namespace,
            'docname': knowledge_base_docname,
            'initial_data': {
                "company_facts": {
                    "industry": "B2B SaaS",
                    "specialization": "Content Marketing and Strategy",
                    "key_achievements": [
                        "Helped 50+ B2B SaaS companies improve content ROI",
                        "Developed content strategies resulting in 3x conversion rates",
                        "Created frameworks for technical content accessibility"
                    ]
                },
                "market_research": {
                    "key_statistics": [
                        "73% of B2B buyers don't read most downloaded content",
                        "Companies with documented content strategies show 3x higher conversion rates",
                        "Technical content accessibility increases C-suite engagement by 200%"
                    ],
                    "source_studies": [
                        "McKinsey B2B Marketing Report 2024",
                        "HubSpot SaaS Content Study 2024",
                        "Gartner Technical Content Accessibility Research"
                    ]
                },
                "best_practices": [
                    "Align content with specific customer journey stages",
                    "Make technical content accessible to non-technical decision makers",
                    "Use quantifiable results in case studies",
                    "Implement the 3T approach: Target, Tailor, Track"
                ]
            },
            'is_shared': False,
            'is_versioned': USER_KNOWLEDGE_BASE_ANALYSIS_IS_VERSIONED,
            'initial_version': "default",
            'is_system_entity': False
        }
    ]

    # Define the documents that should be cleaned up after workflow execution
    cleanup_docs: List[CleanupDocInfo] = [
        # Clean up User DNA document
        {
            'namespace': user_dna_namespace,
            'docname': user_dna_docname,
            'is_shared': False,
            'is_versioned': USER_DNA_IS_VERSIONED,
            'is_system_entity': False
        },
        # Clean up Content Brief document
        {
            'namespace': content_brief_namespace,
            'docname': brief_docname,
            'is_shared': False,
            'is_versioned': CONTENT_BRIEF_IS_VERSIONED,
            'is_system_entity': False
        },
        # Clean up Knowledge Base Analysis document
        {
            'namespace': knowledge_base_namespace,
            'docname': knowledge_base_docname,
            'is_shared': False,
            'is_versioned': USER_KNOWLEDGE_BASE_ANALYSIS_IS_VERSIONED,
            'is_system_entity': False
        },
        # Clean up Draft document that the workflow creates
        {
            'namespace': draft_storage_namespace,
            'docname': test_post_uuid,  # Using the post_uuid as docname
            'is_shared': False,
            'is_versioned': CONTENT_DRAFT_IS_VERSIONED,
            'is_system_entity': False
        }
    ]

    # Pre-defined HITL inputs for the two expected stops in this workflow
    # Configured to test multiple LLM iterations for message history:
    # 1st call: Initial content generation (generate_content_messages_history)
    # 2nd call: Feedback interpretation (interpret_feedback_messages_history) 
    # 3rd call: Content regeneration (generate_content_messages_history continues)
    # 4th call: Final approval after regeneration
    predefined_hitl_inputs: List[Dict[str, Any]] = [
        # Input for the first HITL stop (request revisions)
        {
            "approval_status": "needs_work",
            "feedback_text": "The content is good but needs to be more specific to SaaS companies. Also, can you add more statistics to back up the claims and make the call to action stronger?",
            "updated_post_draft": {
                "post_text": "73% of B2B buyers don't read most of the content they download. Here's why...\n\nAfter 10+ years in B2B SaaS marketing, I've seen this pattern repeatedly: companies invest heavily in content creation but treat it as a checkbox rather than a conversion tool.\n\nThe truth? Quality trumps quantity every time. And alignment with the customer journey is non-negotiable.\n\nHere's what I've learned works consistently:\n\n1️⃣ ALIGN WITH THE JOURNEY: Most B2B content fails because it doesn't match where prospects are in their decision process. Technical whitepapers don't work for awareness stage, and basic \"what is\" content frustrates those ready to buy.\n\n2️⃣ BRIDGE THE TECHNICAL DIVIDE: Your technical content must speak to non-technical decision makers. I've seen brilliant solutions rejected because the content only made sense to engineers, not the C-suite holding the budget.\n\n3️⃣ QUANTIFY RESULTS: The recent McKinsey report confirms what I've observed - case studies with specific, measurable outcomes convert 3x better than generic testimonials.\n\nThe framework I use with clients is what I call the 3T approach:\n• Target: Identify exactly which buying stage you're addressing\n• Tailor: Adapt complexity and focus to match that stage\n• Track: Measure engagement by stage, not just overall views\n\nCompanies with documented content strategies aligned to this approach have consistently shown 3x higher conversion rates according to HubSpot's latest SaaS content study.\n\nGaurav, you might want to personalize the ending a bit more with a stronger call-to-action or reference to your expertise—something that makes your voice unmistakable.\n\nWhat's your biggest challenge with B2B content development? I'd love to hear your experiences in the comments.\n\n(And if you're struggling with making technical content accessible to decision-makers, let's connect - that's my sweet spot.)",
                "hashtags": ["#B2BMarketing", "#ContentStrategy", "#SaaS", "#MarketingROI"]
            }
        },
        {
            "approval_status": "needs_work", 
            "feedback_text": "The statistics are helpful, but I'd like to see more concrete examples of successful B2B SaaS content strategies. Also, can you make the opening hook more attention-grabbing and include a specific mention of ROI?",
            "updated_post_draft": {
                "post_text": "73% of B2B buyers don't read most of the content they download. Here's why...\n\nAfter 10+ years in B2B SaaS marketing, I've seen this pattern repeatedly: companies invest heavily in content creation but treat it as a checkbox rather than a conversion tool.\n\nThe truth? Quality trumps quantity every time. And alignment with the customer journey is non-negotiable.\n\nHere's what I've learned works consistently:\n\n1️⃣ ALIGN WITH THE JOURNEY: Most B2B content fails because it doesn't match where prospects are in their decision process. Technical whitepapers don't work for awareness stage, and basic \"what is\" content frustrates those ready to buy.\n\n2️⃣ BRIDGE THE TECHNICAL DIVIDE: Your technical content must speak to non-technical decision makers. I've seen brilliant solutions rejected because the content only made sense to engineers, not the C-suite holding the budget.\n\n3️⃣ QUANTIFY RESULTS: The recent McKinsey report confirms what I've observed - case studies with specific, measurable outcomes convert 3x better than generic testimonials.\n\nThe framework I use with clients is what I call the 3T approach:\n• Target: Identify exactly which buying stage you're addressing\n• Tailor: Adapt complexity and focus to match that stage\n• Track: Measure engagement by stage, not just overall views\n\nCompanies with documented content strategies aligned to this approach have consistently shown 3x higher conversion rates according to HubSpot's latest SaaS content study.\n\nGaurav, you might want to personalize the ending a bit more with a stronger call-to-action or reference to your expertise—something that makes your voice unmistakable.\n\nWhat's your biggest challenge with B2B content development? I'd love to hear your experiences in the comments.\n\n(And if you're struggling with making technical content accessible to decision-makers, let's connect - that's my sweet spot.)",
                "hashtags": ["#B2BMarketing", "#ContentStrategy", "#SaaS", "#MarketingROI"]
            }
        },
        # Input for the final HITL stop (approve)
        {
            "approval_status": "approved",
            "feedback_text": "",
            "updated_post_draft": {
                "post_text": "73% of B2B buyers don't read most of the content they download. Here's why...\n\nAfter 10+ years in B2B SaaS marketing, I've seen this pattern repeatedly: companies invest heavily in content creation but treat it as a checkbox rather than a conversion tool.\n\nThe truth? Quality trumps quantity every time. And alignment with the customer journey is non-negotiable.\n\nHere's what I've learned works consistently:\n\n1️⃣ ALIGN WITH THE JOURNEY: Most B2B content fails because it doesn't match where prospects are in their decision process. Technical whitepapers don't work for awareness stage, and basic \"what is\" content frustrates those ready to buy.\n\n2️⃣ BRIDGE THE TECHNICAL DIVIDE: Your technical content must speak to non-technical decision makers. I've seen brilliant solutions rejected because the content only made sense to engineers, not the C-suite holding the budget.\n\n3️⃣ QUANTIFY RESULTS: The recent McKinsey report confirms what I've observed - case studies with specific, measurable outcomes convert 3x better than generic testimonials.\n\nThe framework I use with clients is what I call the 3T approach:\n• Target: Identify exactly which buying stage you're addressing\n• Tailor: Adapt complexity and focus to match that stage\n• Track: Measure engagement by stage, not just overall views\n\nCompanies with documented content strategies aligned to this approach have consistently shown 3x higher conversion rates according to HubSpot's latest SaaS content study.\n\nGaurav, you might want to personalize the ending a bit more with a stronger call-to-action or reference to your expertise—something that makes your voice unmistakable.\n\nWhat's your biggest challenge with B2B content development? I'd love to hear your experiences in the comments.\n\n(And if you're struggling with making technical content accessible to decision-makers, let's connect - that's my sweet spot.)",
                "hashtags": ["#B2BMarketing", "#ContentStrategy", "#SaaS", "#MarketingROI"]
            }
        }
    ]

    # Execute the test using the helper function
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=POST_CREATION_WORKFLOW_INPUTS,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=predefined_hitl_inputs,
        setup_docs=setup_docs,
        cleanup_docs=cleanup_docs,
        cleanup_docs_created_by_setup=True,
        validate_output_func=validate_content_workflow_output,
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=600
    )

    print(f"\n--- {test_name} Finished --- ")
    
    # Display final results if available
    if final_run_outputs and 'final_post_content' in final_run_outputs:
        post = final_run_outputs['final_post_content']
        print("\nGenerated LinkedIn Post:")
        print("-" * 50)
        print(post.get('post_text', 'No post text generated'))
        print("\nHashtags:")
        print(", ".join(post.get('hashtags', [])))
        print("-" * 50)


# Standard Python entry point
if __name__ == "__main__":
    print("="*50)
    print("Executing Content Workflow Test")
    print("="*50)
    try:
        asyncio.run(main_test_content_workflow_with_client())
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.")
    except Exception as main_err:
        print(f"\nCritical error during script execution: {main_err}")
        logger.exception("Critical error running main")

    print("\nScript execution finished.")
    print(f"Run this script from the project root directory using:")
    print(f"PYTHONPATH=. python standalone_test_client/kiwi_client/workflows/wf_content_generation.py")
