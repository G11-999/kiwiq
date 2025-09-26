"""
Setup Docs Editor: edit wf_testing/sandbox_setup_docs.py for the selected workflow.
Appears before the workflow runner page.
"""

from typing import Any, Dict, Optional
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Setup Docs Editor", page_icon="🗂️")

from kiwi_client.workflow_exec_ui.utils.workflow_utils import (
    get_workflow_json_content,
    refresh_workflow_data,
    custom_btns,
    get_workflow_setup_docs,
    get_workflow_cleanup_docs,
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


def main() -> None:
    st.title("Setup Docs Editor")
    workflow = _require_selection()
    if not workflow:
        return

    # Resolve file path to sandbox_setup_docs.py
    json_path: Path = workflow["metadata"]["file_path"]
    setup_file_path = json_path.parent / "wf_testing" / "sandbox_setup_docs.py"

    if not setup_file_path.exists():
        st.info("No sandbox_setup_docs.py found for this workflow.")
        return

    try:
        current_content = setup_file_path.read_text(encoding="utf-8")
    except Exception as e:
        st.error(f"Failed to read setup docs file: {e}")
        return

    # Show summary (counts)
    setup_docs = get_workflow_setup_docs(workflow)
    cleanup_docs = get_workflow_cleanup_docs(workflow)
    st.caption(f"Setup docs entries: {len(setup_docs)} | Cleanup entries: {len(cleanup_docs)}")

    # Editor
    use_syntax = st.checkbox("Use syntax highlighting", value=True, key="setup_docs_use_syntax")
    editor_key = f"setup_docs_editor__{workflow['metadata']['workflow_name']}"
    if use_syntax:
        resp = code_editor(
            code=current_content,
            lang="python",
            theme="default",
            height=520,
            response_mode="blur",
            allow_reset=True,
            buttons=custom_btns,
            key=editor_key,
        )
        new_code = resp.get("text", current_content)
    else:
        lines = current_content.count('\n') + 1
        height = 500 if lines < 150 else 800
        new_code = st.text_area(
            "sandbox_setup_docs.py",
            value=current_content,
            height=height,
            key=editor_key,
        )

    cols = st.columns([1,1])
    with cols[0]:
        if st.button("Save Setup Docs", type="primary"):
            try:
                setup_file_path.write_text(new_code, encoding="utf-8")
                # Refresh workflow data so counts & modules update
                refresh_workflow_data(workflow)
                
                # Also refresh the selected workflow in session state
                if st.session_state.get("selected_workflow"):
                    refresh_workflow_data(st.session_state["selected_workflow"])
                
                st.success("✅ Setup docs saved and workflow data refreshed.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save: {e}")

    with cols[1]:
        if st.button("Reload from Disk"):
            st.rerun()


if __name__ == "__main__":
    main()


