"""
Blog Content Calendar Entry Workflow

# Workflow Overview:
1. Generate content topic suggestions for next X weeks: (X) int input optional, default 2
2. Load customer context docs such as company profile, playbook, diagnostic report
3. NO loading of previous posts - generates fresh topics based on strategy
4. Compute total topics needed based on weeks and posting frequency
5. Generate structured topic suggestions (4 topics per slot around common theme)
6. Iterate until required number of topics generated
7. Store all topic suggestions

Key differences from LinkedIn workflow:
- No loading of previous posts (drafts or scraped)
- Uses blog-specific document models
- Includes SEO optimization considerations
- Simpler context preparation without post merging
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
    # Blog Company Profile
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    BLOG_COMPANY_IS_VERSIONED,
    # Blog Content Strategy/Playbook
    BLOG_CONTENT_STRATEGY_DOCNAME,
    BLOG_CONTENT_STRATEGY_NAMESPACE_TEMPLATE,
    BLOG_CONTENT_STRATEGY_IS_VERSIONED,
    # Blog Diagnostic Report (optional)
    BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_VERSIONED,
    # Blog Schedule Config
    BLOG_USER_SCHEDULE_CONFIG_DOCNAME,
    BLOG_USER_SCHEDULE_CONFIG_NAMESPACE_TEMPLATE,
    BLOG_USER_SCHEDULE_CONFIG_IS_VERSIONED,
    # Blog Topic Ideas Storage
    BLOG_TOPIC_IDEAS_CARD_DOCNAME,
    BLOG_TOPIC_IDEAS_CARD_NAMESPACE_TEMPLATE,
    BLOG_TOPIC_IDEAS_CARD_IS_VERSIONED,
)
from kiwi_client.workflows.active.content_studio.llm_inputs.blog_content_calendar_entry import (
    BRIEF_USER_PROMPT_TEMPLATE, 
    BRIEF_SYSTEM_PROMPT_TEMPLATE, 
    BRIEF_LLM_OUTPUT_SCHEMA, 
    BRIEF_ADDITIONAL_USER_PROMPT_TEMPLATE
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Workflow Configuration Constants ---

# LLM Configuration
LLM_PROVIDER = "openai"
GENERATION_MODEL = "gpt-4.1"
LLM_TEMPERATURE = 1
LLM_MAX_TOKENS = 5000

# Workflow Defaults
DEFAULT_WEEKS_TO_GENERATE = 2
DEFAULT_POSTS_PER_WEEK = 2  # Default if not specified in schedule config

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
              "weeks_to_generate": { 
                  "type": "int", 
                  "required": False, 
                  "default": DEFAULT_WEEKS_TO_GENERATE, 
                  "description": f"Number of weeks ahead to generate topic suggestions for (default: {DEFAULT_WEEKS_TO_GENERATE})." 
              },
              "company_name": {
                  "type": "str", 
                  "required": True,
                  "description": "Company name identifier for loading documents"
              },
          }
        }
    },
 
    # --- 2. Load Customer Context Documents ---
    "load_all_context_docs": {
        "node_id": "load_all_context_docs",
        "node_name": "load_customer_data",
        "node_config": {
            "load_paths": [
                {
                    "filename_config": {
                        "input_namespace_field_pattern": BLOG_COMPANY_NAMESPACE_TEMPLATE, 
                        "input_namespace_field": "company_name",
                        "static_docname": BLOG_COMPANY_DOCNAME,
                    },
                    "output_field_name": "company_doc"
                },
                {
                    "filename_config": {
                        "input_namespace_field_pattern": BLOG_CONTENT_STRATEGY_NAMESPACE_TEMPLATE, 
                        "input_namespace_field": "company_name",
                        "static_docname": BLOG_CONTENT_STRATEGY_DOCNAME,
                    },
                    "output_field_name": "playbook"
                },
                {
                    "filename_config": {
                        "input_namespace_field_pattern": BLOG_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE, 
                        "input_namespace_field": "company_name",
                        "static_docname": BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
                    },
                    "output_field_name": "diagnostic_report"
                },
                {
                    "filename_config": {
                        "input_namespace_field_pattern": BLOG_USER_SCHEDULE_CONFIG_NAMESPACE_TEMPLATE, 
                        "input_namespace_field": "company_name",
                        "static_docname": BLOG_USER_SCHEDULE_CONFIG_DOCNAME,
                    },
                    "output_field_name": "schedule_config"
                },
            ],
            "global_is_shared": False,
            "global_is_system_entity": False,
            "global_schema_options": {"load_schema": False}
        },
    },

    # --- 3. Prepare Generation Context (Simplified - No Post Merging) ---
    "prepare_generation_context": {
      "node_id": "prepare_generation_context",
      "node_name": "merge_aggregate",
      "enable_node_fan_in": True,
      "node_config": {
        "operations": [
          # Operation: Compute Total Topics Needed - weeks_to_generate * posts_per_week
          {
            "output_field_name": "total_topics_needed",
            "select_paths": ["schedule_config.posts_per_week"],
            "merge_strategy": {
                "map_phase": {"unspecified_keys_strategy": "ignore"},
                "reduce_phase": {
                    "default_reducer": "replace_right",
                    "error_strategy": "skip_operation"  # Use default if schedule not found
                },
                "post_merge_transformations": {
                     "total_topics_needed": {
                         "operation_type": "multiply",
                         "operand_path": "weeks_to_generate"
                     }
                },
                "transformation_error_strategy": "skip_operation"
            },
            "merge_each_object_in_selected_list": False
          }
        ]
      },
    },

    # --- 4. Construct Topic Prompt ---
    "construct_topic_prompt": {
      "node_id": "construct_topic_prompt",
      "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
          "topic_user_prompt": {
            "id": "topic_user_prompt",
            "template": BRIEF_USER_PROMPT_TEMPLATE,
            "variables": {
              "company_doc": None,
              "playbook": None,
              "diagnostic_report": None,
              "schedule_config": None,
              "current_datetime": "$current_date",
            },
            "construct_options": {
               "company_doc": "company_doc",
               "playbook": "playbook",
               "diagnostic_report": "diagnostic_report",
               "schedule_config": "schedule_config",
            }
          },
          "topic_system_prompt": {
            "id": "topic_system_prompt",
            "template": BRIEF_SYSTEM_PROMPT_TEMPLATE,
            "variables": { 
                "schema": json.dumps(BRIEF_LLM_OUTPUT_SCHEMA, indent=2), 
                "current_datetime": "$current_date" 
            },
            "construct_options": {}
          }
        }
      }
    },

    # --- 5. Generate Topics (LLM) ---
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
    },

    # --- 6. Check Topic Count ---
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
    },

    # --- 7. Router Based on Topic Count Check ---
    "route_on_topic_count": {
      "node_id": "route_on_topic_count",
      "node_name": "router_node",
      "node_config": {
        "choices": ["construct_additional_topic_prompt", "store_all_topics"],
        "allow_multiple": False,
        "choices_with_conditions": [
          {
            "choice_id": "construct_additional_topic_prompt",
            "input_path": "if_else_condition_tag_results.topic_count_check",
            "target_value": True
          },
          {
            "choice_id": "store_all_topics",
            "input_path": "if_else_condition_tag_results.topic_count_check",
            "target_value": False,
          }
        ]
      }
    },

    # --- 8. Construct Additional Topic Prompt ---
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

    # --- 9. Store All Generated Topics ---
    "store_all_topics": {
      "node_id": "store_all_topics",
      "node_name": "store_customer_data",
      "node_config": {
          "global_versioning": { 
              "is_versioned": BLOG_TOPIC_IDEAS_CARD_IS_VERSIONED, 
              "operation": "upsert_versioned"
          },
          "global_is_shared": False,
          "store_configs": [
              {
                  "input_field_path": "all_generated_topics",
                  "process_list_items_separately": True,
                  "target_path": {
                      "filename_config": {
                          "input_namespace_field_pattern": BLOG_TOPIC_IDEAS_CARD_NAMESPACE_TEMPLATE, 
                          "input_namespace_field": "company_name",
                          "static_docname": BLOG_TOPIC_IDEAS_CARD_DOCNAME,
                      }
                  },
                  "generate_uuid": True,
              }
          ],
      },
      "dynamic_input_schema": {
          "fields": {}
      }
    },

    # --- 10. Output Node ---
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
        { "src_field": "company_name", "dst_field": "company_name" },
      ]
    },

    # --- Input to Context Loader ---
    { "src_node_id": "input_node", "dst_node_id": "load_all_context_docs", "mappings": [
        { "src_field": "company_name", "dst_field": "company_name" },
      ], "description": "Trigger context docs loading."
    },

    # --- State Updates from Loaders ---
    { "src_node_id": "load_all_context_docs", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "company_doc", "dst_field": "company_doc"},
        { "src_field": "playbook", "dst_field": "playbook"},
        { "src_field": "diagnostic_report", "dst_field": "diagnostic_report"},
        { "src_field": "schedule_config", "dst_field": "schedule_config"}
      ]
    },

    # --- Trigger Context Preparation ---
    { "src_node_id": "load_all_context_docs", "dst_node_id": "prepare_generation_context"},

    # --- Mapping State to Context Prep Node ---
    { "src_node_id": "$graph_state", "dst_node_id": "prepare_generation_context", "mappings": [
        { "src_field": "schedule_config", "dst_field": "schedule_config"},
        { "src_field": "weeks_to_generate", "dst_field": "weeks_to_generate" },
      ]
    },

    # --- Context Prep to Prompt Construction ---
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

    # --- State to Construct Prompt ---
    { "src_node_id": "$graph_state", "dst_node_id": "construct_topic_prompt", "mappings": [
        { "src_field": "company_doc", "dst_field": "company_doc" },
        { "src_field": "playbook", "dst_field": "playbook"},
        { "src_field": "diagnostic_report", "dst_field": "diagnostic_report"},
        { "src_field": "schedule_config", "dst_field": "schedule_config"},
      ]
    },

    # --- Construct Prompt to Generate Topics ---
    { "src_node_id": "construct_topic_prompt", "dst_node_id": "generate_topics", "mappings": [
        { "src_field": "topic_user_prompt", "dst_field": "user_prompt"},
        { "src_field": "topic_system_prompt", "dst_field": "system_prompt"}
      ], "description": "Private edge: Sends prompts to LLM."
    },

    # --- State to Generate Topics (for history) ---
    { "src_node_id": "$graph_state", "dst_node_id": "generate_topics", "mappings": [
        { "src_field": "generate_topics_messages_history", "dst_field": "messages_history"}
      ]
    },

    # --- Generate Topics to State ---
    { "src_node_id": "generate_topics", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "structured_output", "dst_field": "all_generated_topics"},
        { "src_field": "current_messages", "dst_field": "generate_topics_messages_history"}
      ]
    },

    # --- Generate Topics to Check Topic Count ---
    { "src_node_id": "generate_topics", "dst_node_id": "check_topic_count", "mappings": [
        { "src_field": "metadata", "dst_field": "metadata"}
      ]},

    # --- State to Check Topic Count ---
    { "src_node_id": "$graph_state", "dst_node_id": "check_topic_count", "mappings": [
        { "src_field": "merged_data", "dst_field": "merged_data" }
      ]
    },

    # --- Check Topic Count to Router ---
    { "src_node_id": "check_topic_count", "dst_node_id": "route_on_topic_count", "mappings": [
        { "src_field": "tag_results", "dst_field": "if_else_condition_tag_results" },
        { "src_field": "condition_result", "dst_field": "if_else_overall_condition_result" }
      ]
    },

    # --- Router to Additional Prompt ---
    { "src_node_id": "route_on_topic_count", "dst_node_id": "construct_additional_topic_prompt" },

    # --- Router to Store ---
    { "src_node_id": "route_on_topic_count", "dst_node_id": "store_all_topics" },

    # --- State to Store ---
    { "src_node_id": "$graph_state", "dst_node_id": "store_all_topics", "mappings": [
        { "src_field": "all_generated_topics", "dst_field": "all_generated_topics"},
        { "src_field": "company_name", "dst_field": "company_name" }
      ]
    },

    # --- Additional Prompt to Generate Topics (loop) ---
    { "src_node_id": "construct_additional_topic_prompt", "dst_node_id": "generate_topics", "mappings": [
        { "src_field": "additional_topic_prompt", "dst_field": "user_prompt" },
      ]
    },

    # --- Store to Output ---
    { "src_node_id": "store_all_topics", "dst_node_id": "output_node", 
     "mappings": [
        { "src_field": "paths_processed", "dst_field": "topic_paths_processed"}
      ]
     },

    # --- State to Output ---
    { "src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
        { "src_field": "all_generated_topics", "dst_field": "final_topics_list"}
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
          "all_generated_topics": "collect_values",
          "generate_topics_messages_history": "add_messages"
        }
      }
  }
}


# --- Test Execution Logic ---

async def main_test_blog_content_calendar_workflow():
    """
    Test the Blog Content Calendar Entry Workflow.
    Sets up required test documents, runs the workflow, validates the output and cleans up after.
    """
    test_name = "Blog Content Calendar Entry Workflow Test"
    print(f"--- Starting {test_name} --- ")

    # Example Inputs 
    test_company_name = "acme-corp"
    
    # Define test inputs with realistic values
    test_inputs = {
        "company_name": test_company_name,
        "weeks_to_generate": 2,  # Generate for 2 weeks
    }

    # Create realistic test data for setup
    setup_docs: List[SetupDocInfo] = [
        # Company Profile Document
        {
            'namespace': BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item=test_company_name), 
            'docname': BLOG_COMPANY_DOCNAME,
            'initial_data': {
                "company_name": "Acme Corp",
                "company_description": "Leading B2B SaaS platform for enterprise resource planning",
                "industry": "Enterprise Software",
                "target_audience": {
                    "primary": "IT Directors and CTOs at mid-market companies",
                    "secondary": "Operations managers looking for efficiency tools",
                    "industries": ["Manufacturing", "Retail", "Healthcare"]
                },
                "value_proposition": "Streamline operations with AI-powered ERP that reduces manual work by 60%",
                "content_goals": {
                    "primary": "Establish thought leadership in enterprise automation",
                    "secondary": ["Generate qualified leads", "Improve SEO rankings for key terms"]
                },
                "expertise_areas": [
                    "Enterprise resource planning",
                    "AI and machine learning in operations",
                    "Supply chain optimization",
                    "Business process automation",
                    "Data analytics and reporting"
                ],
                "pain_points_addressed": [
                    "Manual data entry and errors",
                    "Lack of real-time visibility",
                    "Disconnected systems",
                    "Compliance and reporting challenges",
                    "Scaling operations efficiently"
                ]
            }, 
            'is_versioned': BLOG_COMPANY_IS_VERSIONED, 
            'is_shared': False,
        },
        # Content Strategy/Playbook Document
        {
            'namespace': BLOG_CONTENT_STRATEGY_NAMESPACE_TEMPLATE.format(item=test_company_name), 
            'docname': BLOG_CONTENT_STRATEGY_DOCNAME,
            'initial_data': {
                "title": "Acme Corp Blog Content Strategy",
                "content_pillars": [
                    {
                        "name": "Enterprise Automation Insights",
                        "description": "Deep dives into automation strategies and best practices",
                        "topics": [
                            "ROI of automation",
                            "Implementation roadmaps",
                            "Change management",
                            "Case studies and success stories"
                        ]
                    },
                    {
                        "name": "Industry Trends & Analysis",
                        "description": "Market trends and future of enterprise software",
                        "topics": [
                            "AI adoption in enterprises",
                            "Digital transformation trends",
                            "Regulatory updates",
                            "Market research and reports"
                        ]
                    },
                    {
                        "name": "Product Innovation & Features",
                        "description": "Product updates and feature deep-dives",
                        "topics": [
                            "New feature announcements",
                            "Product roadmap insights",
                            "Integration guides",
                            "Best practices for platform usage"
                        ]
                    },
                    {
                        "name": "Customer Success Stories",
                        "description": "Real-world implementations and results",
                        "topics": [
                            "Customer case studies",
                            "Implementation journeys",
                            "ROI achievements",
                            "Industry-specific solutions"
                        ]
                    }
                ],
                "seo_strategy": {
                    "primary_keywords": [
                        "enterprise resource planning",
                        "ERP software",
                        "business automation",
                        "supply chain management software"
                    ],
                    "long_tail_keywords": [
                        "best ERP for manufacturing companies",
                        "how to automate business processes",
                        "enterprise software implementation guide"
                    ]
                },
                "content_format_preferences": [
                    "Long-form guides (2000+ words)",
                    "Industry reports with data",
                    "How-to tutorials",
                    "Case studies with metrics",
                    "Thought leadership pieces"
                ]
            }, 
            'is_versioned': BLOG_CONTENT_STRATEGY_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': 'default'
        },
        # Schedule Configuration
        {
            'namespace': BLOG_USER_SCHEDULE_CONFIG_NAMESPACE_TEMPLATE.format(item=test_company_name), 
            'docname': BLOG_USER_SCHEDULE_CONFIG_DOCNAME,
            'initial_data': {
                "posts_per_week": 2,
                "posting_days": ["Tuesday", "Thursday"],
                "preferred_time": "10:00 AM EST",
                "content_mix": {
                    "thought_leadership": 40,
                    "product_focused": 20,
                    "customer_stories": 20,
                    "industry_insights": 20
                }
            }, 
            'is_versioned': BLOG_USER_SCHEDULE_CONFIG_IS_VERSIONED, 
            'is_shared': False,
            'initial_version': 'default'
        },
        # Optional: Diagnostic Report (can be empty or minimal)
        {
            'namespace': BLOG_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE.format(item=test_company_name), 
            'docname': BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
            'initial_data': {
                "report_date": "2024-01-15",
                "key_findings": [
                    "Need more bottom-funnel content",
                    "Lacking content for healthcare vertical",
                    "Strong performance on automation topics"
                ],
                "recommendations": [
                    "Increase case study production",
                    "Create healthcare-specific content series",
                    "Continue automation thought leadership"
                ]
            }, 
            'is_versioned': BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_VERSIONED, 
            'is_shared': False,
        },
    ]

    # Define cleanup docs to remove test artifacts after test completion
    cleanup_docs: List[CleanupDocInfo] = [
        {
            'namespace': BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item=test_company_name), 
            'docname': BLOG_COMPANY_DOCNAME, 
            'is_versioned': BLOG_COMPANY_IS_VERSIONED, 
            'is_shared': False
        },
        {
            'namespace': BLOG_CONTENT_STRATEGY_NAMESPACE_TEMPLATE.format(item=test_company_name), 
            'docname': BLOG_CONTENT_STRATEGY_DOCNAME, 
            'is_versioned': BLOG_CONTENT_STRATEGY_IS_VERSIONED, 
            'is_shared': False
        },
        {
            'namespace': BLOG_USER_SCHEDULE_CONFIG_NAMESPACE_TEMPLATE.format(item=test_company_name), 
            'docname': BLOG_USER_SCHEDULE_CONFIG_DOCNAME, 
            'is_versioned': BLOG_USER_SCHEDULE_CONFIG_IS_VERSIONED, 
            'is_shared': False
        },
        {
            'namespace': BLOG_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE.format(item=test_company_name), 
            'docname': BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME, 
            'is_versioned': BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_VERSIONED, 
            'is_shared': False
        },
    ]

    print("--- Setup/Cleanup Definitions (Complete) ---")
    print(f"Company Name: {test_company_name}")
    print(f"Setup Docs: {len(setup_docs)} documents prepared")
    print(f"Cleanup Docs: {len(cleanup_docs)} documents to be removed after test")
    print("------------------------------------------------")

    # --- Define Custom Output Validation ---
    async def validate_calendar_output(outputs: Optional[Dict[str, Any]]) -> bool:
        assert outputs is not None, "Validation Failed: Workflow returned no outputs."
        logger.info("Validating blog content topic suggestions workflow outputs...")
        assert 'final_topics_list' in outputs, "Validation Failed: 'final_topics_list' missing."
        
        # Handle both single object and list formats
        final_topics = outputs['final_topics_list']
        if isinstance(final_topics, dict):
            topic_suggestions_list = [final_topics]
            logger.info("Found single topic suggestion object instead of list. This indicates the workflow iteration didn't work properly.")
        elif isinstance(final_topics, list):
            topic_suggestions_list = final_topics
        else:
            assert False, f"Validation Failed: 'final_topics_list' must be a list or dict, got {type(final_topics)}"
        
        # Calculate expected number of topic suggestions
        posts_per_week = 2  # From our test data
        expected_count = test_inputs.get("weeks_to_generate", DEFAULT_WEEKS_TO_GENERATE) * posts_per_week
        
        # Validate topic suggestions count
        actual_count = len(topic_suggestions_list)
        
        if actual_count != expected_count:
            logger.warning(f"Expected {expected_count} topic suggestions, found {actual_count}.")
            logger.warning(f"Expected: {expected_count} = {test_inputs.get('weeks_to_generate', DEFAULT_WEEKS_TO_GENERATE)} weeks × {posts_per_week} posts per week")
        
        # Validate topic suggestion structure
        for idx, topic_output in enumerate(topic_suggestions_list, 1):
            logger.info(f"   Validating topic suggestion {idx}/{len(topic_suggestions_list)}...")
            
            # Check required fields
            assert 'suggested_topics' in topic_output, f"Topic suggestion {idx} missing: suggested_topics"
            assert isinstance(topic_output['suggested_topics'], list), f"suggested_topics in {idx} must be a list"
            assert len(topic_output['suggested_topics']) == 4, f"Topic suggestion {idx} must have exactly 4 topics"
            
            assert 'scheduled_date' in topic_output, f"Topic suggestion {idx} missing: scheduled_date"
            assert 'theme' in topic_output, f"Topic suggestion {idx} missing: theme"
            assert 'play_aligned' in topic_output, f"Topic suggestion {idx} missing: play_aligned"
            assert 'objective' in topic_output, f"Topic suggestion {idx} missing: objective"
            assert 'why_important' in topic_output, f"Topic suggestion {idx} missing: why_important"
            
            # Validate individual topics
            for i, topic in enumerate(topic_output['suggested_topics'], 1):
                assert 'title' in topic, f"Topic {idx}.{i} missing: title"
                assert 'description' in topic, f"Topic {idx}.{i} missing: description"
                assert isinstance(topic['title'], str) and len(topic['title'].strip()) > 0
                assert isinstance(topic['description'], str) and len(topic['description'].strip()) > 0
            
            # Validate objective enum
            valid_objectives = ["brand_awareness", "thought_leadership", "engagement", 
                              "education", "lead_generation", "seo_optimization", "product_awareness"]
            assert topic_output['objective'] in valid_objectives, f"Invalid objective: {topic_output['objective']}"
            
            # Validate scheduled_date format
            try:
                if isinstance(topic_output['scheduled_date'], str):
                    if topic_output['scheduled_date'].endswith('Z'):
                        datetime.strptime(topic_output['scheduled_date'], '%Y-%m-%dT%H:%M:%SZ')
                    else:
                        datetime.fromisoformat(topic_output['scheduled_date'].replace('Z', '+00:00'))
            except ValueError:
                assert False, f"Invalid scheduled_date format: {topic_output['scheduled_date']}"
        
        logger.info(f"Found {actual_count} topic suggestions, expected {expected_count}.")
        logger.info("Each topic suggestion contains exactly 4 topics around one theme.")
        logger.info("Output structure validation passed.")
        
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
    print("Blog Content Calendar Entry Workflow")
    print("="*50)
    logging.basicConfig(level=logging.INFO)

    try:
        asyncio.run(main_test_blog_content_calendar_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")
        logger.exception("Test execution failed")