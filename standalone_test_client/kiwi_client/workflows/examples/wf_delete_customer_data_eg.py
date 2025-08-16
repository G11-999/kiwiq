"""
Example Workflow: Delete Customer Data via System Search

This workflow demonstrates how to use the `delete_customer_data` node to:
- Perform a system-level search for customer data documents
- Delete the found documents (fail-fast by default)

Notes:
- Search parameters are provided as workflow inputs (graph input) and passed to the node via
  `search_params_input_path`, not hardcoded in node config.
- The node will raise on first deletion failure by default. For demonstration safety,
  you can manually modify the node config to enable `dry_run` if desired.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    CleanupDocInfo,
)
from kiwi_client.test_config import CLIENT_LOG_LEVEL
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus


logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)


# --- Workflow Graph Definition ---
workflow_graph_schema: Dict[str, Any] = {
    "nodes": {
        # 1) Input node: provides `search_params` to the delete node
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
        },

        # 2) Delete node: resolves search params from input via `search_params_input_path`
        "delete_node": {
            "node_id": "delete_node",
            "node_name": "delete_customer_data",
            "node_config": {
                # Pull search params dynamically from incoming input
                "search_params_input_path": "search_params",
                # If you need to override delete options dynamically, also set:
                # "delete_options_input_path": "delete_options",
                # Defaults: fail fast, not a dry run; see node config for details
            },
        },

        # 3) Output node: captures results from the delete node
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {},
        },
    },
    "edges": [
        # Input -> Delete: pass search params
        {
            "src_node_id": "input_node",
            "dst_node_id": "delete_node",
            "mappings": [
                {"src_field": "search_params", "dst_field": "search_params"},
                # If you provide delete options at runtime, also add:
                # {"src_field": "delete_options", "dst_field": "delete_options"},
            ],
        },

        # Delete -> Output: pass delete result fields
        {
            "src_node_id": "delete_node",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "found_count", "dst_field": "found_count"},
                {"src_field": "deleted_count", "dst_field": "deleted_count"},
                {"src_field": "dry_run", "dst_field": "dry_run"},
                {"src_field": "deleted_documents", "dst_field": "deleted_documents"},
                {"src_field": "failures", "dst_field": "failures"},
            ],
        },
    ],
    "input_node_id": "input_node",
    "output_node_id": "output_node",
}


async def main_test_delete_customer_data() -> None:
    """Run the Delete Customer Data workflow test with provided search params.

    The search parameters are injected as workflow inputs and consumed by the
    `delete_customer_data` node via `search_params_input_path`.
    """

    # Prepare workflow inputs per the request
    WORKFLOW_INPUTS: Dict[str, Any] = {
        "search_params": {
            "namespace_pattern": "content_briefs",
            "docname_pattern": "*",
            "value_filter": {
                "scheduled_date": {
                    "$gt": "2025-08-14T00:00:00Z",
                    "$lte": "2025-08-17T00:00:00Z",
                }
            },
            # Optional pagination/sorting if needed:
            # "skip": 0,
            # "limit": 1000,
            # "sort_by": "UPDATED_AT",  # if enums-as-strings supported in your setup
            # "sort_order": "DESC",
        },
        # If you want runtime delete options (optional), also provide:
        # "delete_options": {"dry_run": True, "continue_on_error": True, "max_deletes": 25},
    }

    test_name = "Delete Customer Data Test"
    logger.info("Starting Delete Customer Data workflow test...")

    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=WORKFLOW_INPUTS,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=None,
        setup_docs=[],
        cleanup_docs=[],
        stream_intermediate_results=True,
        poll_interval_sec=2,
        timeout_sec=120,
    )

    # Log a concise summary
    if final_run_outputs:
        found = final_run_outputs.get("found_count")
        deleted = final_run_outputs.get("deleted_count")
        dry_run = final_run_outputs.get("dry_run")
        logger.info(
            f"Delete results - found: {found}, deleted: {deleted}, dry_run: {dry_run}"
        )
        failures = final_run_outputs.get("failures") or []
        if failures:
            logger.warning(f"Failures encountered: {len(failures)}")
        deleted_docs = final_run_outputs.get("deleted_documents") or []
        if deleted_docs:
            logger.info(
                f"Sample deleted doc: {deleted_docs[0] if isinstance(deleted_docs, list) and deleted_docs else 'N/A'}"
            )


if __name__ == "__main__":
    print("=" * 60)
    print("Delete Customer Data Workflow Example")
    print("=" * 60)
    print("Running delete workflow with provided search parameters...")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        task = loop.create_task(main_test_delete_customer_data())
    else:
        asyncio.run(main_test_delete_customer_data())

    print("\n" + "-" * 60)
    print("Run this script from the project root using:")
    print(
        "PYTHONPATH=. python standalone_test_client/kiwi_client/workflows/examples/wf_delete_customer_data_eg.py"
    )
    print("-" * 60)


