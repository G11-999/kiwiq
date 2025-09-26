"""
Workflows page: list discovered workflows and allow selection.
"""

from typing import Any, Dict, List, Tuple

import streamlit as st

st.set_page_config(page_title="Workflows", page_icon="🧩")

from kiwi_client.workflow_exec_ui.utils.workflow_utils import (
    list_available_workflows,
    get_workflow_by_name,
)


def _ensure_selection_defaults() -> None:
    if "selected_category" not in st.session_state:
        st.session_state.selected_category = None
    if "selected_workflow_name" not in st.session_state:
        st.session_state.selected_workflow_name = None
    if "selected_workflow" not in st.session_state:
        st.session_state.selected_workflow = None


def _render_current_selection() -> None:
    if st.session_state.selected_category and st.session_state.selected_workflow_name:
        st.markdown(
            f"**Selected:** `{st.session_state.selected_category}/{st.session_state.selected_workflow_name}`"
        )
    else:
        st.info("No workflow selected.")


def main() -> None:
    st.title("Workflows")
    _ensure_selection_defaults()
    _render_current_selection()

    st.divider()
    st.subheader("Available Workflows")

    workflows: List[Tuple[str, str]] = list_available_workflows()
    if not workflows:
        st.warning("No workflows found.")
        return

    # Simple table with select buttons
    for category, name in sorted(workflows):
        cols = st.columns([3, 5, 2])
        cols[0].write(category)
        cols[1].write(name)
        if cols[2].button("Select", key=f"select__{category}__{name}"):
            st.session_state.selected_category = category
            st.session_state.selected_workflow_name = name
            st.session_state.selected_workflow = get_workflow_by_name(category, name)
            st.success(f"Selected {category}/{name}")
            st.rerun()


if __name__ == "__main__":
    main()


