"""
Run Workflow (Interactive):
- Manage inputs/HITL/outputs via session state
- Start run, poll for status, handle HITL in chat UI
- Rebuild chat from session on refresh
"""

from typing import Any, Dict, Optional, List

import json
import time
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Run Workflow", page_icon="▶️")

from kiwi_client.workflow_exec_ui.utils.workflow_utils import (
    get_workflow_json_content,
    custom_btns,
    get_workflow_variable,
    get_workflow_setup_docs,
    get_workflow_cleanup_docs,
    refresh_workflow_data,
)
from kiwi_client.workflow_exec_ui.utils.streamlit_runner import (
    start_run_stepwise_sync,
    poll_next_step_sync,
    resume_with_hitl_sync,
    create_setup_docs_sync,
    cleanup_docs_sync,
)

from code_editor import code_editor


def _require_selection() -> Optional[Dict[str, Any]]:
    if not (st.session_state.get("selected_category") and st.session_state.get("selected_workflow_name") and st.session_state.get("selected_workflow")):
        st.warning("Select a workflow in the Workflows page first.")
        return None
    st.success(
        f"Selected: {st.session_state['selected_category']}/{st.session_state['selected_workflow_name']}"
    )
    return st.session_state["selected_workflow"]


def _json_editor(label: str, key: str, default_value: str) -> Optional[Dict[str, Any]]:
    edited = code_editor(
        code=str(default_value),
        lang="json",
        theme="default",
        height=280,
        response_mode="blur",
        allow_reset=True,
        buttons=custom_btns,
        key=f"ce_{key}",
    )
    text = edited.get("text", str(default_value))
    try:
        parsed = json.loads(text) if text.strip() else {}
        st.caption("Valid JSON")
        return parsed
    except Exception as e:
        st.error(f"Invalid JSON: {e}")
        return None


def main() -> None:
    st.title("Run Workflow (Interactive)")
    workflow = _require_selection()
    if not workflow:
        return

    schema = workflow.get("json_schema") or get_workflow_json_content(workflow)
    if not schema:
        st.error("Workflow JSON schema could not be loaded.")
        return

    # Session state keys
    cat = workflow["metadata"]["category"]
    name = workflow["metadata"]["workflow_name"]
    ss_prefix = f"run_{cat}__{name}"
    run_id_key = f"{ss_prefix}__run_id"
    chat_key = f"{ss_prefix}__chat"
    status_key = f"{ss_prefix}__status"
    hitl_pending_key = f"{ss_prefix}__hitl_pending"
    hitl_schema_key = f"{ss_prefix}__hitl_schema"
    init_inputs_key = f"{ss_prefix}__initial_inputs"
    hitl_editor_key = f"{ss_prefix}__hitl_editor"

    # Initialize session containers
    if chat_key not in st.session_state:
        st.session_state[chat_key]: List[Dict[str, Any]] = []
    if run_id_key not in st.session_state:
        st.session_state[run_id_key] = None
    if status_key not in st.session_state:
        st.session_state[status_key] = None
    if hitl_pending_key not in st.session_state:
        st.session_state[hitl_pending_key] = False
    if hitl_schema_key not in st.session_state:
        st.session_state[hitl_schema_key] = None

    # Display inputs info (read-only)
    st.subheader("Inputs")
    # Prefer testing file variable `test_scenario.initial_inputs` if available
    test_scenario = get_workflow_variable(workflow, 'testing_inputs', 'test_scenario')
    initial_inputs_from_testing = {}
    if isinstance(test_scenario, dict) and isinstance(test_scenario.get('initial_inputs'), dict):
        initial_inputs_from_testing = test_scenario['initial_inputs']
        st.json(initial_inputs_from_testing)
        if test_scenario.get('name'):
            st.caption(f"From test_scenario: {test_scenario.get('name')}")
    else:
        fallback_inputs = schema.get("input_schema", {}) if isinstance(schema, dict) else {}
        st.json(fallback_inputs)
        st.caption("From workflow input_schema (no test_scenario found)")
    st.caption("These inputs will be loaded fresh from the testing file when starting a new run.")

    # Setup docs summary and cleanup toggle
    setup_docs = get_workflow_setup_docs(workflow)
    cleanup_docs = get_workflow_cleanup_docs(workflow)
    st.info(f"Setup Docs: {len(setup_docs)} will be created before run. | Cleanup Docs: {len(cleanup_docs)}")
    cleanup_toggle_key = f"{ss_prefix}__cleanup_toggle"
    cleanup_after_run = st.checkbox("Cleanup created setup docs after run", value=True, key=cleanup_toggle_key)

    # Tables for setup and cleanup docs
    def _docs_rows(docs: List[Dict[str, Any]]):
        return [{"namespace": d.get("namespace"), "docname": d.get("docname")} for d in (docs or [])]

    st.write("Setup Docs")
    st.dataframe(_docs_rows(setup_docs))
    st.write("Cleanup Docs")
    st.dataframe(_docs_rows(cleanup_docs))

    cols = st.columns([1,1,1])
    with cols[0]:
        if st.button("Start New Run", type="primary"):
            # Reload workflow data from scratch to get latest inputs, schema, etc.
            refresh_workflow_data(workflow)
            
            # Reset session run state
            st.session_state[run_id_key] = None
            st.session_state[status_key] = None
            st.session_state[hitl_pending_key] = False
            st.session_state[hitl_schema_key] = None
            st.session_state[chat_key] = []
            
            # Get fresh inputs from test_scenario after refresh
            test_scenario = get_workflow_variable(workflow, 'testing_inputs', 'test_scenario')
            fresh_initial_inputs = {}
            if isinstance(test_scenario, dict) and isinstance(test_scenario.get('initial_inputs'), dict):
                fresh_initial_inputs = test_scenario['initial_inputs']
            else:
                # Fallback to input_schema from JSON
                fresh_schema = get_workflow_json_content(workflow)
                if fresh_schema and 'input_schema' in fresh_schema:
                    fresh_initial_inputs = fresh_schema['input_schema']
            
            # Submit the run
            if not fresh_initial_inputs:
                st.error("No initial inputs found in test_scenario or input_schema.")
            else:
                # Create setup docs first
                created_ct = 0
                if setup_docs:
                    with st.spinner("Creating setup docs..."):
                        created_ct = create_setup_docs_sync(setup_docs)
                    st.success(f"Setup docs created/updated: {created_ct}")
                
                # Get workflow name to ingest as and fresh graph schema
                workflow_name_to_ingest_as = get_workflow_variable(workflow, 'wf_runner', 'WORKFLOW_NAME_TO_INGEST_AS_FOR_TESTING')
                if not workflow_name_to_ingest_as:
                    workflow_name_to_ingest_as = f"test_{workflow['metadata']['workflow_name']}"
                
                fresh_graph_schema = get_workflow_json_content(workflow)
                if not fresh_graph_schema:
                    st.error("No workflow graph schema found")
                    return
                
                with st.spinner("Creating workflow and submitting run..."):
                    rid, status = start_run_stepwise_sync(
                        workflow_name_to_ingest_as=workflow_name_to_ingest_as,
                        graph_schema=fresh_graph_schema,
                        initial_inputs=fresh_initial_inputs,
                    )
                st.session_state[run_id_key] = rid
                st.session_state[status_key] = status
                if rid:
                    # Only add chat messages after successful submission
                    st.session_state[chat_key].append({"role": "user", "type": "inputs", "content": fresh_initial_inputs})
                    st.session_state[chat_key].append({"role": "assistant", "type": "status", "content": {"run_id": rid, "status": status}})
                    st.success(f"Run started: {rid}")
                else:
                    st.error("Failed to create workflow or submit run.")
                st.rerun()

    with cols[1]:
        st.empty()  # placeholder to keep layout; auto-polling enabled below

    with cols[2]:
        if st.button("Reset Session"):
            st.session_state[run_id_key] = None
            st.session_state[status_key] = None
            st.session_state[hitl_pending_key] = False
            st.session_state[hitl_schema_key] = None
            st.session_state[chat_key] = []
            st.success("Session reset.")
            st.rerun()

    st.divider()
    st.subheader("Interactive Session")

    # Render chat history
    for msg in st.session_state[chat_key]:
        role = msg.get("role", "assistant")
        with st.chat_message("user" if role == "user" else "assistant"):
            mtype = msg.get("type")
            if mtype == "inputs":
                st.write("**Initial Inputs**")
                st.json(msg.get("content", {}))
            elif mtype == "status":
                st.write("**Run Status Update**")
                content = msg.get("content", {})
                st.write(f"Run ID: {content.get('run_id')}")
                st.write(f"Status: {content.get('status')}")
            elif mtype == "state":
                st.write("**Intermediate State Snapshot**")
                st.json(msg.get("content", {}))
            elif mtype == "hitl_request":
                st.write("**HITL Request**")
                st.json(msg.get("content", {}))
            elif mtype == "hitl_response":
                st.write("**HITL Response**")
                st.json(msg.get("content", {}))
            elif mtype == "final_outputs":
                st.write("**Final Outputs**")
                st.json(msg.get("content", {}))
            elif mtype == "error":
                st.error(f"**Error:** {msg.get('content', {})}")
            else:
                st.write(msg.get("content"))

    # If waiting HITL, show editor to collect inputs
    if st.session_state.get(hitl_pending_key):
        st.info("Workflow is waiting for HITL. Provide a response to resume.")
        schema_preview = st.session_state.get(hitl_schema_key)
        if schema_preview:
            with st.expander("Expected Response Schema"):
                st.json(schema_preview)

        # HITL editor using code_editor for JSON
        hitl_resp = code_editor(
            code="{}",
            lang="json",
            theme="default",
            height=220,
            response_mode="blur",
            allow_reset=True,
            buttons=custom_btns,
            key=hitl_editor_key,
        )
        hitl_text = hitl_resp.get("text", "{}")

        if st.button("Submit HITL Response", type="primary"):
            # Parse and submit
            try:
                parsed = json.loads(hitl_text) if hitl_text.strip() else {}
            except Exception as e:
                st.error(f"Invalid JSON: {e}")
                return
            rid = st.session_state.get(run_id_key)
            if not rid:
                st.error("No active run.")
                return
            with st.spinner("Submitting HITL response..."):
                ok = resume_with_hitl_sync(run_id=rid, hitl_inputs=parsed)
            if ok:
                st.session_state[chat_key].append({"role": "user", "type": "hitl_response", "content": parsed})
                st.session_state[hitl_pending_key] = False
                st.session_state[hitl_schema_key] = None
                st.success("HITL submitted. Poll next step.")
                st.rerun()
            else:
                st.error("Failed to submit HITL response.")

    # Auto-polling while run is active and not waiting for HITL
    rid = st.session_state.get(run_id_key)
    status = st.session_state.get(status_key)
    if rid and status and status not in ("COMPLETED", "FAILED", "CANCELLED") and not st.session_state.get(hitl_pending_key):
        with st.spinner("Polling run status...", show_time=True):
            upd = poll_next_step_sync(run_id=rid, fetch_state=True)
        st.session_state[status_key] = upd.status
        
        # Only show intermediate state snapshots for HITL, FAILED, or CANCELLED states
        # Skip for COMPLETED (we'll show final outputs instead)
        if upd.state_snapshot is not None and upd.status in ("WAITING_HITL", "FAILED", "CANCELLED"):
            st.session_state[chat_key].append({"role": "assistant", "type": "state", "content": upd.state_snapshot})
        
        if upd.is_waiting_hitl:
            st.session_state[hitl_pending_key] = True
            st.session_state[hitl_schema_key] = upd.hitl_response_schema
            st.session_state[chat_key].append({"role": "assistant", "type": "hitl_request", "content": upd.hitl_request_details or {}})
        elif upd.final_outputs is not None:
            # For completed workflows, show final outputs directly (no intermediate state)
            st.session_state[chat_key].append({"role": "assistant", "type": "final_outputs", "content": upd.final_outputs})
            if cleanup_after_run and cleanup_docs:
                with st.spinner("Cleaning up setup docs..."):
                    deleted_ct = cleanup_docs_sync(cleanup_docs)
                st.success(f"Cleanup complete: deleted {deleted_ct}")
        elif upd.error:
            st.session_state[chat_key].append({"role": "assistant", "type": "error", "content": {"message": upd.error}})
        st.rerun()



if __name__ == "__main__":
    main()

# ... existing code ...

