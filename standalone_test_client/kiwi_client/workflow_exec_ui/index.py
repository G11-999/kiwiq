"""
poetry run streamlit run kiwi_client/workflow_exec_ui/index.py

Streamlit multipage app entry for Workflow Executor UI.

This file initializes global session state and provides a simple landing
message guiding users to the pages sidebar.

"""

from typing import Any, Dict, Optional

import streamlit as st


def _init_session_state() -> None:
    """Initialize global session state keys if missing.

    Keys:
        selected_category: Selected workflow category
        selected_workflow_name: Selected workflow name
        selected_workflow: Cached workflow info dict
        editing_buffers: Dict of filename->str for editors
        last_run: Dict with last execution metadata
    """
    defaults = {
        "selected_category": None,
        "selected_workflow_name": None,
        "selected_workflow": None,
        "editing_buffers": {},
        "last_run": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def main() -> None:
    """Render landing content and initialize session state."""
    st.set_page_config(page_title="Workflow Executor UI", layout="wide")
    _init_session_state()

    st.title("Workflow Executor UI")
    st.caption("Use the sidebar to navigate: Workflows, Sandbox, Config, Run")

    if st.session_state.get("selected_category") and st.session_state.get("selected_workflow_name"):
        st.markdown(
            f"**Selected:** `{st.session_state['selected_category']}/{st.session_state['selected_workflow_name']}`"
        )
    else:
        st.info("No workflow selected yet. Open the Workflows page to choose one.")


if __name__ == "__main__":
    main()
    # poetry run streamlit run kiwi_client/workflow_exec_ui/index.py

