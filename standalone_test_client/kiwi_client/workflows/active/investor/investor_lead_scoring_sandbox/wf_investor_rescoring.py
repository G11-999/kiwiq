"""
Investor Check Size Rescoring Workflow

This workflow rescores investor check sizes based on updated scoring rules using GPT-4o.

Input: List of investor rows with: row_index, typical_check_size, check_size_points, total_score, score_tier, recommended_action, is_disqualified
Output: List of rescored investors with updated scores

**NEW SCORING RULES:**
- $500K-$2M = 10 pts
- $250K-$500K = 6 pts
- $2M-$10M = 2 pts
- >$10M or <$250K or N/A = 0 pts

**TIER ASSIGNMENT:**
- A: 85-100 points (Top Priority)
- B: 70-84 points (High Priority)
- C: 50-69 points (Medium Priority)
- D: <50 points (Low Priority)

Workflow Flow:
1. Map router distributes each row
2. LLM (GPT-4o) scores the check size string
3. Transform node recalculates total_score, tier, and recommended_action
4. Collect all results
5. Output

Cost Estimate: ~$0.001 per row (GPT-4o with short structured output)
Time Estimate: ~5-10 seconds per batch of 20 rows
"""

from kiwi_client.workflows.active.investor.investor_lead_scoring_sandbox.wf_rescoring_llm_inputs import (
    RESCORE_CHECK_SIZE_SYSTEM_PROMPT,
    RESCORE_CHECK_SIZE_USER_PROMPT,
    CheckSizeScore,
    RESCORE_MODEL_CONFIG,
)

# ============================================================================
# WORKFLOW GRAPH SCHEMA
# ============================================================================

# Private mode passthrough keys - data to preserve through the pipeline
passthrough_keys = [
    "row_index", "investor_name", "typical_check_size",
    "old_check_size_points", "old_total_score", "is_disqualified",
]

workflow_graph_schema = {
    "nodes": {
        # --- 1. Input Node ---
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "investors_to_rescore": {
                        "type": "list",
                        "required": False,
                        "default": [],
                        "description": "List of investor rows to rescore"
                    }
                }
            }
        },

        # --- 2. Map List Router - Routes each investor to rescoring ---
        "route_investors_to_rescoring": {
            "node_id": "route_investors_to_rescoring",
            "node_name": "map_list_router_node",
            "node_config": {
                "choices": ["score_check_size_prompt"],
                "map_targets": [
                    {
                        "source_path": "investors_to_rescore",
                        "destinations": ["score_check_size_prompt"],
                        "batch_size": 1
                    }
                ]
            }
        },

        # --- 3. Prompt Constructor for Check Size Scoring ---
        "score_check_size_prompt": {
            "node_id": "score_check_size_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": passthrough_keys,
            "node_config": {
                "prompt_templates": {
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": RESCORE_CHECK_SIZE_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    },
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": RESCORE_CHECK_SIZE_USER_PROMPT,
                        "variables": {
                            "row_index": "",
                            "investor_name": "",
                            "typical_check_size": "",
                            "current_score": ""
                        },
                        "construct_options": {
                            "row_index": "row_index",
                            "investor_name": "investor_name",
                            "typical_check_size": "typical_check_size",
                            "current_score": "old_check_size_points"
                        }
                    }
                }
            }
        },

        # --- 4. LLM Node - Score the check size using GPT-4o ---
        "score_check_size_llm": {
            "node_id": "score_check_size_llm",
            "node_name": "llm",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": passthrough_keys,
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": "openai",
                        "model": RESCORE_MODEL_CONFIG["model"]
                    },
                    "temperature": RESCORE_MODEL_CONFIG["temperature"],
                    "max_tokens": RESCORE_MODEL_CONFIG["max_tokens"],
                    "reasoning_effort_class": RESCORE_MODEL_CONFIG["reasoning_effort"],
                },
                "output_schema": {
                    "schema_definition": CheckSizeScore.model_json_schema(),
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 5. Code Runner Node - Recalculate scores and tier ---
        "recalculate_scores": {
            "node_id": "recalculate_scores",
            "node_name": "code_runner",
            "private_input_mode": True,
            # "output_private_output_to_central_state": True,
            # "private_output_passthrough_data_to_central_state_keys": passthrough_keys,
            # "write_to_private_output_passthrough_data_from_output_mappings": {
            #     "result": "rescoring_result"
            # },
            "read_private_input_passthrough_data_to_input_field_mappings": {
                "old_check_size_points": "input_data.old_check_size_points",
                "old_total_score": "input_data.old_total_score",
                "is_disqualified": "input_data.is_disqualified",
                "row_index": "input_data.row_index",
                "investor_name": "input_data.investor_name",
                "typical_check_size": "input_data.typical_check_size"
            },
            "node_config": {
                # "mappings": [],
                "timeout_seconds": 60,
                "memory_mb": 30,
                "cpus": 0.02,
                "enable_network": False,
                "persist_artifacts": False,
                "fail_node_on_code_error": True,

                "default_code": '''
# Recalculate scores based on new check size points

# Extract values from LLM output
new_check_size_points = INPUT['structured_output']['new_check_size_points']
old_check_size_points = INPUT['old_check_size_points']
old_total_score = INPUT['old_total_score']

# Calculate point difference
points_diff = new_check_size_points - old_check_size_points

# Recalculate total score (capped at 0-100)
new_total_score = max(0, min(100, old_total_score + points_diff))

# Recalculate tier
if new_total_score >= 85:
    new_tier = "A"
elif new_total_score >= 70:
    new_tier = "B"
elif new_total_score >= 50:
    new_tier = "C"
else:
    new_tier = "D"

# Recalculate recommended action
is_disqualified = INPUT.get('is_disqualified', False)
if isinstance(is_disqualified, str):
    is_disqualified = is_disqualified.lower() == 'true'

if new_tier == "A":
    recommended_action = "Top Priority - Pursue immediately"
elif new_tier == "B":
    recommended_action = "High Priority - Direct outreach"
elif new_tier == "C":
    recommended_action = "Medium Priority - Consider timing"
else:  # D
    recommended_action = "Low Priority - Backup list"

# Build output
output_data = {
    'row_index': INPUT['row_index'],
    'investor_name': INPUT['investor_name'],
    'typical_check_size': INPUT['typical_check_size'],
    'old_check_size_points': old_check_size_points,
    'new_check_size_points': new_check_size_points,
    'points_difference': points_diff,
    'old_total_score': old_total_score,
    'new_total_score': new_total_score,
    'new_score_tier': new_tier,
    'new_recommended_action': recommended_action,
    # 'scoring_reasoning': INPUT['structured_output']['reasoning'],
    'parsed_typical_amount': INPUT['structured_output'].get('parsed_typical_amount', 'N/A'),
}

# print(f"Output data: {output_data}")

# Set RESULT for code_runner node
RESULT = output_data
'''
            }
        },

        # --- 6. Output Node ---
        "output_node": {
            "enable_node_fan_in": True,
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {}
        }
    },

    # Edge definitions
    "edges": [
        # Start: Input to map router
        {"src_node_id": "input_node", "dst_node_id": "route_investors_to_rescoring", "mappings": [{"src_field": "investors_to_rescore", "dst_field": "investors_to_rescore"},]},

        # Map router to prompt constructor
        {"src_node_id": "route_investors_to_rescoring", "dst_node_id": "score_check_size_prompt", "mappings": []},

        # Prompt constructor to LLM
        {"src_node_id": "score_check_size_prompt", "dst_node_id": "score_check_size_llm", "mappings": [
            {"src_field": "system_prompt", "dst_field": "system_prompt"},
            {"src_field": "user_prompt", "dst_field": "user_prompt"}
        ]},

        # LLM to transform
        {"src_node_id": "score_check_size_llm", "dst_node_id": "recalculate_scores", "mappings": [
            {"src_field": "structured_output", "dst_field": "input_data.structured_output"},
        ]},

        # Map router to state (collect results)
        {"src_node_id": "recalculate_scores", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "result", "dst_field": "rescored_results"}
        ]},

        {"src_node_id": "recalculate_scores", "dst_node_id": "output_node", "mappings": [
        ]},

        # State to output
        {"src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
            {"src_field": "rescored_results", "dst_field": "rescored_investors"}
        ]}
    ],

    # Define start and end
    "input_node_id": "input_node",
    "output_node_id": "output_node",

    # Runtime configuration
    "runtime_config": {
        "db_concurrent_pool_tier": "xlarge"  # Medium pool for moderate parallel operations
    },

    # State reducers - collect all results
    "metadata": {
        "$graph_state": {
            "reducer": {
                "rescored_results": "collect_values"
            }
        }
    }
}


# ============================================================================
# TEST ENTRY POINT
# ============================================================================

import asyncio
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus
from kiwi_client.test_run_workflow_client import run_workflow_test

async def test():
    """Test the rescoring workflow with sample data."""
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name="investor_rescoring_test",
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs={
            "investors_to_rescore": [
                {
                    "row_index": "1",
                    "investor_name": "Test Investor",
                    "typical_check_size": "$1M-$3M at seed",
                    "old_check_size_points": 8,
                    "old_total_score": 75,
                    "is_disqualified": False
                },
                {
                    "row_index": "2",
                    "investor_name": "Test Investor 2",
                    "typical_check_size": "$1M-$3M at seed",
                    "old_check_size_points": 8,
                    "old_total_score": 75,
                    "is_disqualified": False
                },
            ]
        },
        expected_final_status=WorkflowRunStatus.COMPLETED,
        setup_docs=None,
        cleanup_docs=None,
        stream_intermediate_results=False,
        dump_artifacts=True,
        poll_interval_sec=5,
        timeout_sec=300  # 5 minutes timeout
    )

if __name__ == "__main__":
    asyncio.run(test())
