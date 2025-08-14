"""
Blog Monthly Topic Calendar Workflow

Generates X slots for a given month, where each slot contains 4 topic ideas around one theme aligned to a play from the blog playbook.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import json
from datetime import datetime, date

from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

from kiwi_client.workflows.active.document_models.customer_docs import (
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    BLOG_COMPANY_IS_SHARED,
    BLOG_COMPANY_IS_VERSIONED,
    BLOG_COMPANY_IS_SYSTEM_ENTITY,
    BLOG_CONTENT_STRATEGY_DOCNAME,
    BLOG_CONTENT_STRATEGY_NAMESPACE_TEMPLATE,
    BLOG_CONTENT_STRATEGY_IS_VERSIONED,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_VERSIONED,
    BLOG_SCRAPED_POSTS_DOCNAME,
    BLOG_SCRAPED_POSTS_NAMESPACE_TEMPLATE,
    # BLOG_CLASSIFIED_POSTS_DOCNAME,
    # BLOG_CLASSIFIED_POSTS_NAMESPACE_TEMPLATE,
    BLOG_USER_SCHEDULE_CONFIG_DOCNAME,
    BLOG_USER_SCHEDULE_CONFIG_NAMESPACE_TEMPLATE,
    BLOG_TOPIC_IDEAS_CARD_DOCNAME,
    BLOG_TOPIC_IDEAS_CARD_NAMESPACE_TEMPLATE,
)

from kiwi_client.workflows.active.content_studio.llm_inputs.blog_monthly_calendar_topic_ideas import (
    BLOG_MONTHLY_USER_PROMPT_TEMPLATE,
    BLOG_MONTHLY_SYSTEM_PROMPT_TEMPLATE,
    BLOG_MONTHLY_ADDITIONAL_USER_PROMPT_TEMPLATE,
    BLOG_MONTHLY_OUTPUT_SCHEMA,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LLM_PROVIDER = "openai"
GENERATION_MODEL = "gpt-4.1"
LLM_TEMPERATURE = 0.9
LLM_MAX_TOKENS = 4500

DEFAULT_PAST_CONTEXT_POSTS_LIMIT = 10

workflow_graph_schema: Dict[str, Any] = {
    "nodes": {
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "company_name": {"type": "str", "required": True},
                    "month_start": {"type": "str", "required": False, "description": "ISO date YYYY-MM-01; defaults to next month start if absent"},
                    "posts_per_month": {"type": "int", "required": False, "description": "Overrides schedule config if provided"},
                    "past_context_posts_limit": {"type": "int", "required": False, "default": DEFAULT_PAST_CONTEXT_POSTS_LIMIT}
                }
            }
        },

        # Load company, playbook, diagnostics, scraped/classified posts, and schedule
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
                            "input_namespace_field_pattern": BLOG_SCRAPED_POSTS_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_SCRAPED_POSTS_DOCNAME,
                        },
                        "output_field_name": "scraped_posts"
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_CLASSIFIED_POSTS_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_CLASSIFIED_POSTS_DOCNAME,
                        },
                        "output_field_name": "classified_posts"
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
            }
        },

        # Merge recent posts and compute control values
        "prepare_generation_context": {
            "node_id": "prepare_generation_context",
            "node_name": "merge_aggregate",
            "enable_node_fan_in": True,
            "node_config": {
                "operations": [
                    {
                        "output_field_name": "recent_posts_context",
                        "select_paths": ["classified_posts", "scraped_posts"],
                        "merge_strategy": {
                            "map_phase": {"unspecified_keys_strategy": "ignore"},
                            "reduce_phase": {"default_reducer": "extend", "error_strategy": "fail_node"},
                            "post_merge_transformations": {
                                "recent_posts_context": {
                                    "operation_type": "limit_list",
                                    "operand_path": "past_context_posts_limit"
                                }
                            },
                            "transformation_error_strategy": "skip_operation"
                        },
                        "merge_each_object_in_selected_list": False
                    },
                    {
                        "output_field_name": "preferred_days",
                        "select_paths": ["schedule_config.posting_days"],
                        "merge_strategy": {
                            "map_phase": {"unspecified_keys_strategy": "ignore"},
                            "reduce_phase": {"default_reducer": "replace_right", "error_strategy": "skip_operation"}
                        },
                        "merge_each_object_in_selected_list": False
                    },
                    {
                        "output_field_name": "total_slots_needed",
                        "select_paths": ["posts_per_month", "schedule_config.posts_per_month"],
                        "merge_strategy": {
                            "map_phase": {"unspecified_keys_strategy": "ignore"},
                            "reduce_phase": {"default_reducer": "coalesce", "error_strategy": "fail_node"}
                        },
                        "merge_each_object_in_selected_list": False
                    }
                ]
            }
        },

        # Construct prompts per slot
        "construct_slot_prompt": {
            "node_id": "construct_slot_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "slot_user_prompt": {
                        "id": "slot_user_prompt",
                        "template": BLOG_MONTHLY_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "company_doc": None,
                            "playbook": None,
                            "diagnostic_report": None,
                            "recent_posts_context": None,
                            "schedule_config": None,
                            "month_start": None,
                            "total_slots_needed": None,
                            "current_datetime": "$current_date"
                        },
                        "construct_options": {
                            "company_doc": "company_doc",
                            "playbook": "playbook",
                            "diagnostic_report": "diagnostic_report",
                            "recent_posts_context": "merged_data.recent_posts_context",
                            "schedule_config": "schedule_config",
                            "month_start": "month_start",
                            "total_slots_needed": "merged_data.total_slots_needed"
                        }
                    },
                    "slot_system_prompt": {
                        "id": "slot_system_prompt",
                        "template": BLOG_MONTHLY_SYSTEM_PROMPT_TEMPLATE,
                        "variables": {
                            "schema": json.dumps(BLOG_MONTHLY_OUTPUT_SCHEMA, indent=2),
                            "current_datetime": "$current_date"
                        },
                        "construct_options": {}
                    }
                }
            }
        },

        # LLM to generate one slot per iteration
        "generate_slot": {
            "node_id": "generate_slot",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": GENERATION_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": BLOG_MONTHLY_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # Check if more slots are needed
        "check_slot_count": {
            "node_id": "check_slot_count",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "more_slots_needed",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "metadata.iteration_count",
                                "operator": "less_than",
                                "value_path": "merged_data.total_slots_needed"
                            }]
                        }]
                    }
                ],
                "branch_logic_operator": "and"
            }
        },

        # Route: generate additional slot or store
        "route_on_slot_count": {
            "node_id": "route_on_slot_count",
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_additional_slot_prompt", "store_all_slots"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {"choice_id": "construct_additional_slot_prompt", "input_path": "if_else_condition_tag_results.more_slots_needed", "target_value": True},
                    {"choice_id": "store_all_slots", "input_path": "if_else_condition_tag_results.more_slots_needed", "target_value": False}
                ]
            }
        },

        "construct_additional_slot_prompt": {
            "node_id": "construct_additional_slot_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "additional_slot_prompt": {
                        "id": "additional_slot_prompt",
                        "template": BLOG_MONTHLY_ADDITIONAL_USER_PROMPT_TEMPLATE
                    }
                }
            }
        },

        # Store each slot as a topic ideas card
        "store_all_slots": {
            "node_id": "store_all_slots",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {"is_versioned": True, "operation": "upsert_versioned"},
                "global_is_shared": False,
                "store_configs": [
                    {
                        "input_field_path": "all_generated_slots",
                        "process_list_items_separately": True,
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_TOPIC_IDEAS_CARD_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": BLOG_TOPIC_IDEAS_CARD_DOCNAME,
                            }
                        },
                        "generate_uuid": True
                    }
                ]
            }
        },

        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {}
        }
    },

    "edges": [
        {"src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
            {"src_field": "month_start", "dst_field": "month_start"},
            {"src_field": "posts_per_month", "dst_field": "posts_per_month"},
            {"src_field": "past_context_posts_limit", "dst_field": "past_context_posts_limit"}
        ]},

        {"src_node_id": "input_node", "dst_node_id": "load_all_context_docs", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},

        {"src_node_id": "load_all_context_docs", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "company_doc", "dst_field": "company_doc"},
            {"src_field": "playbook", "dst_field": "playbook"},
            {"src_field": "diagnostic_report", "dst_field": "diagnostic_report"},
            {"src_field": "scraped_posts", "dst_field": "scraped_posts"},
            {"src_field": "classified_posts", "dst_field": "classified_posts"},
            {"src_field": "schedule_config", "dst_field": "schedule_config"}
        ]},

        {"src_node_id": "load_all_context_docs", "dst_node_id": "prepare_generation_context"},

        {"src_node_id": "$graph_state", "dst_node_id": "prepare_generation_context", "mappings": [
            {"src_field": "past_context_posts_limit", "dst_field": "past_context_posts_limit"},
            {"src_field": "posts_per_month", "dst_field": "posts_per_month"},
            {"src_field": "schedule_config", "dst_field": "schedule_config"}
        ]},

        {"src_node_id": "prepare_generation_context", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "recent_posts_context", "dst_field": "recent_posts_context"},
            {"src_field": "preferred_days", "dst_field": "preferred_days"},
            {"src_field": "total_slots_needed", "dst_field": "total_slots_needed"}
        ]},

        {"src_node_id": "prepare_generation_context", "dst_node_id": "construct_slot_prompt"},

        {"src_node_id": "$graph_state", "dst_node_id": "construct_slot_prompt", "mappings": [
            {"src_field": "company_doc", "dst_field": "company_doc"},
            {"src_field": "playbook", "dst_field": "playbook"},
            {"src_field": "diagnostic_report", "dst_field": "diagnostic_report"},
            {"src_field": "recent_posts_context", "dst_field": "recent_posts_context"},
            {"src_field": "schedule_config", "dst_field": "schedule_config"},
            {"src_field": "month_start", "dst_field": "month_start"},
            {"src_field": "total_slots_needed", "dst_field": "total_slots_needed"}
        ]},

        {"src_node_id": "construct_slot_prompt", "dst_node_id": "generate_slot", "mappings": [
            {"src_field": "slot_user_prompt", "dst_field": "user_prompt"},
            {"src_field": "slot_system_prompt", "dst_field": "system_prompt"}
        ]},

        {"src_node_id": "generate_slot", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "all_generated_slots"},
            {"src_field": "current_messages", "dst_field": "generation_messages"}
        ]},

        # Collect the slot and check count
        {"src_node_id": "$graph_state", "dst_node_id": "check_slot_count", "mappings": [
            {"src_field": "iteration_branch_result", "dst_field": "iteration_branch_result"},
            {"src_field": "total_slots_needed", "dst_field": "merged_data.total_slots_needed"}
        ]},
        {"src_node_id": "check_slot_count", "dst_node_id": "route_on_slot_count", "mappings": [
            {"src_field": "tag_results", "dst_field": "if_else_condition_tag_results"}
        ]},

        # Additional prompt loop
        {"src_node_id": "route_on_slot_count", "dst_node_id": "construct_additional_slot_prompt"},
        {"src_node_id": "construct_additional_slot_prompt", "dst_node_id": "generate_slot", "mappings": [
            {"src_field": "additional_slot_prompt", "dst_field": "user_prompt"}
        ]},

        # Store and output
        {"src_node_id": "route_on_slot_count", "dst_node_id": "store_all_slots"},
        {"src_node_id": "$graph_state", "dst_node_id": "store_all_slots", "mappings": [
            {"src_field": "all_generated_slots", "dst_field": "all_generated_slots"},
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},

        {"src_node_id": "store_all_slots", "dst_node_id": "output_node", "mappings": [
            {"src_field": "paths_processed", "dst_field": "stored_paths"}
        ]},

        {"src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
            {"src_field": "all_generated_slots", "dst_field": "final_monthly_slots"}
        ]}
    ],

    "input_node_id": "input_node",
    "output_node_id": "output_node",

    "metadata": {
        "$graph_state": {
            "reducer": {
                "all_generated_slots": "collect_values",
                "generation_messages": "add_messages"
            }
        }
    }
}


async def validate_monthly_calendar_output(outputs: Optional[Dict[str, Any]]) -> bool:
    assert outputs is not None, "Workflow returned no outputs."
    assert "final_monthly_slots" in outputs, "Missing final_monthly_slots."
    slots = outputs["final_monthly_slots"]
    assert isinstance(slots, list) and len(slots) > 0, "Expected non-empty list of slots."
    for slot in slots:
        assert "suggested_topics" in slot and len(slot["suggested_topics"]) == 4, "Each slot must have exactly 4 topics."
        assert "theme" in slot and slot["theme"], "Each slot must have a theme."
        assert "play_aligned" in slot and slot["play_aligned"], "Each slot must align to a play."
        assert "scheduled_date" in slot, "Each slot must have scheduled_date."
    return True


async def main_test_blog_monthly_calendar():
    test_name = "Blog Monthly Topic Calendar Workflow Test"
    print(f"--- Starting {test_name} ---")

    company_name = "test_blog_company"

    # Minimal setup docs
    setup_docs: List[SetupDocInfo] = [
        {
            'namespace': BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': BLOG_COMPANY_DOCNAME,
            'initial_data': {"company_name": company_name, "industry": "B2B SaaS"},
            'is_shared': BLOG_COMPANY_IS_SHARED,
            'is_versioned': BLOG_COMPANY_IS_VERSIONED,
            'initial_version': None,
            'is_system_entity': BLOG_COMPANY_IS_SYSTEM_ENTITY
        },
        {
            'namespace': BLOG_CONTENT_STRATEGY_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': BLOG_CONTENT_STRATEGY_DOCNAME,
            'initial_data': {
                "playbook_title": "Sample Playbook",
                "content_plays": [
                    {"play_name": "Problem Authority Stack", "implementation_strategy": "..."},
                    {"play_name": "Practitioner's Handbook", "implementation_strategy": "..."}
                ]
            },
            'is_shared': False,
            'is_versioned': BLOG_CONTENT_STRATEGY_IS_VERSIONED,
            'initial_version': "default",
            'is_system_entity': False
        },
        {
            'namespace': BLOG_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
            'initial_data': {
                "immediate_opportunities": {"top_content_opportunities": [{"title": "Executive Leadership Series"}]},
                "content_audit_summary": {"content_gaps": ["Integration Challenges"]}
            },
            'is_shared': False,
            'is_versioned': BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_VERSIONED,
            'initial_version': None,
            'is_system_entity': False
        }
    ]

    cleanup_docs: List[CleanupDocInfo] = [
        {
            'namespace': BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': BLOG_COMPANY_DOCNAME,
            'is_shared': BLOG_COMPANY_IS_SHARED,
            'is_versioned': BLOG_COMPANY_IS_VERSIONED,
            'is_system_entity': BLOG_COMPANY_IS_SYSTEM_ENTITY
        },
        {
            'namespace': BLOG_CONTENT_STRATEGY_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': BLOG_CONTENT_STRATEGY_DOCNAME,
            'is_shared': False,
            'is_versioned': BLOG_CONTENT_STRATEGY_IS_VERSIONED,
            'is_system_entity': False
        },
        {
            'namespace': BLOG_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
            'is_shared': False,
            'is_versioned': BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_VERSIONED,
            'is_system_entity': False
        }
    ]

    test_inputs = {
        "company_name": company_name,
        "posts_per_month": 6,
        "past_context_posts_limit": 5
    }

    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=[],
        setup_docs=setup_docs,
        cleanup_docs=cleanup_docs,
        cleanup_docs_created_by_setup=False,
        validate_output_func=validate_monthly_calendar_output,
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=900
    )

    print(f"--- {test_name} Finished ---")
    if final_run_outputs:
        print(f"Slots generated: {len(final_run_outputs.get('final_monthly_slots', []))}")


if __name__ == "__main__":
    try:
        asyncio.run(main_test_blog_monthly_calendar())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")
        logger.exception("Test execution failed") 