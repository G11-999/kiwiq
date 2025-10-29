"""
Investor Personalization Line Generation Workflow

This workflow generates personalized outreach lines for investors based on their context data.

Input: List of investor rows with: row_index, context (markdown-formatted)
Output: List of personalized outputs with: row_index, personalization_line, personalization_reason

**Key Features:**
- Generic column handling (no hardcoded fields)
- Flexible allow/deny list for column filtering
- Markdown-formatted context generation
- High-quality personalization using GPT-4.1

Workflow Flow:
1. Map router distributes each investor row
2. LLM (GPT-4.1) generates personalized line based on context
3. Collect all results
4. Output

Cost Estimate: ~$0.01-0.02 per row (GPT-4.1 with structured output)
Time Estimate: ~10-15 seconds per batch of 20 rows
"""

from kiwi_client.workflows.active.investor.investor_lead_scoring_sandbox.wf_personalization_llm_inputs import (
    PERSONALIZATION_SYSTEM_PROMPT,
    PERSONALIZATION_USER_PROMPT,
    PersonalizationOutput,
    PERSONALIZATION_MODEL_CONFIG,
)

# ============================================================================
# WORKFLOW GRAPH SCHEMA
# ============================================================================

# Private mode passthrough keys - preserve row_index through the pipeline
passthrough_keys = ["row_index"]

workflow_graph_schema = {
    "nodes": {
        # --- 1. Input Node ---
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "investors_to_personalize": {
                        "type": "list",
                        "required": False,
                        "default": [],
                        "description": "List of investor rows to generate personalization for"
                    },
                    "founder_company_context": {
                        "type": "str",
                        "required": False,
                        "default": "",
                        "description": "Additional context about founders/company (e.g., recent traction, specific product details)"
                    }
                }
            }
        },

        # --- 2. Map List Router - Routes each investor to personalization ---
        "route_investors_to_personalization": {
            "node_id": "route_investors_to_personalization",
            "node_name": "map_list_router_node",
            "node_config": {
                "choices": ["generate_personalization_prompt"],
                "map_targets": [
                    {
                        "source_path": "investors_to_personalize",
                        "destinations": ["generate_personalization_prompt"],
                        "batch_size": 1
                    }
                ]
            }
        },

        # --- 3. Prompt Constructor for Personalization ---
        "generate_personalization_prompt": {
            "node_id": "generate_personalization_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": passthrough_keys,
            "node_config": {
                "prompt_templates": {
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": PERSONALIZATION_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    },
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": PERSONALIZATION_USER_PROMPT,
                        "variables": {
                            "row_index": "",
                            "context": "",
                            "founder_company_context": ""
                        },
                        "construct_options": {
                            "row_index": "row_index",
                            "context": "context",
                            "founder_company_context": "founder_company_context"
                        }
                    }
                }
            }
        },

        # --- 4. LLM Node - Generate personalization using GPT-4.1 ---
        "generate_personalization_llm": {
            "node_id": "generate_personalization_llm",
            "node_name": "llm",
            "private_input_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": passthrough_keys,
            "private_output_to_central_state_node_output_key": "personalization_result",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": PERSONALIZATION_MODEL_CONFIG["provider"],
                        "model": PERSONALIZATION_MODEL_CONFIG["model"]
                    },
                    "temperature": PERSONALIZATION_MODEL_CONFIG["temperature"],
                    "max_tokens": PERSONALIZATION_MODEL_CONFIG["max_tokens"],
                    "reasoning_tokens_budget": PERSONALIZATION_MODEL_CONFIG["reasoning_tokens_budget"],
                },
                "output_schema": {
                    "schema_definition": PersonalizationOutput.model_json_schema(),
                    "convert_loaded_schema_to_pydantic": False
                }
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
        # Start: Input to central state (store founder_company_context)
        {
            "src_node_id": "input_node",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "founder_company_context", "dst_field": "founder_company_context"}
            ]
        },

        # Input to map router
        {
            "src_node_id": "input_node",
            "dst_node_id": "route_investors_to_personalization",
            "mappings": [
                {"src_field": "investors_to_personalize", "dst_field": "investors_to_personalize"}
            ]
        },

        # Map router to prompt constructor
        {
            "src_node_id": "route_investors_to_personalization",
            "dst_node_id": "generate_personalization_prompt",
            "mappings": []
        },

        # Central state to prompt constructor (pass founder_company_context)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "generate_personalization_prompt",
            "mappings": [
                {"src_field": "founder_company_context", "dst_field": "founder_company_context"}
            ]
        },

        # Prompt constructor to LLM
        {
            "src_node_id": "generate_personalization_prompt",
            "dst_node_id": "generate_personalization_llm",
            "mappings": [
                {"src_field": "system_prompt", "dst_field": "system_prompt"},
                {"src_field": "user_prompt", "dst_field": "user_prompt"}
            ]
        },

        # LLM to state (collect results with passthrough data)
        {
            "src_node_id": "generate_personalization_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "personalization_results"}
            ]
        },

        # LLM to output node
        {
            "src_node_id": "generate_personalization_llm",
            "dst_node_id": "output_node",
            "mappings": []
        },

        # State to output
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "personalization_results", "dst_field": "personalized_investors"}
            ]
        }
    ],

    # Define start and end
    "input_node_id": "input_node",
    "output_node_id": "output_node",

    # Runtime configuration
    "runtime_config": {
        "db_concurrent_pool_tier": "xlarge"  # Large pool for parallel operations
    },

    # State reducers - collect all results
    "metadata": {
        "$graph_state": {
            "reducer": {
                "personalization_results": "collect_values",
                "founder_company_context": "replace"
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
    """Test the personalization workflow with sample data - generates both Founder A and Founder B perspectives."""
    
    sample_context = """# investor_name:
John Smith

# firm_name:
Acme Ventures

# recent_investments:
TechCo (AI-powered analytics), DataFlow (data infrastructure), CloudOps (DevOps automation)

# investment_thesis:
Seed-stage B2B SaaS focusing on developer tools and infrastructure

# linkedin_activity:
Recently posted: "The best AI tools execute, not just recommend"

# typical_check_size:
$1M-$3M at seed

# geographic_focus:
US, Canada

# founder_preferences:
Looks for technical founders from top tech companies
"""

    founder_company_context = """We just hit 10 active customers using our multi-agent workflows in production.
Our agents have coordinated 150+ marketing campaigns end-to-end with minimal human intervention.
Recent product launch: persistent context system that remembers brand voice across months."""

    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name="investor_personalization_test",
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs={
            "investors_to_personalize": [
                {
                    "row_index": "1",
                    "context": sample_context
                },
                {
                    "row_index": "2",
                    "context": sample_context
                }
            ],
            "founder_company_context": founder_company_context
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

