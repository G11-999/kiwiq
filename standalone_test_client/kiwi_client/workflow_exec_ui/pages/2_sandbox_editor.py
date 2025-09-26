"""
Sandbox Editor: view and edit variables from sandbox_identifiers.py
"""

from typing import Any, Dict
import ast

import streamlit as st

st.set_page_config(page_title="Sandbox Editor", page_icon="🧪")

from kiwi_client.workflow_exec_ui.utils.workflow_utils import (
    list_sandbox_variables,
    update_sandbox_identifiers_variable,
    custom_btns,
    refresh_workflow_data,
)

from code_editor import code_editor


def _render_header() -> None:
    st.title("Sandbox Editor")
    st.caption("Global variables used across workflows (sandbox_identifiers.py)")


def _render_variables_table(vars_dict: Dict[str, Any]) -> None:
    if not vars_dict:
        st.info("No variables found in sandbox_identifiers.py")
        return
    st.subheader("Current Variables")
    st.dataframe({"name": list(vars_dict.keys()), "value": [repr(v) for v in vars_dict.values()]})


def _render_edit_form(vars_dict: Dict[str, Any]) -> None:
    st.subheader("Edit Variable")
    var_name = st.selectbox("Variable", sorted(vars_dict.keys())) if vars_dict else None
    if not var_name:
        return
    current_val = vars_dict[var_name]
    is_primitive = isinstance(current_val, (str, int, float, bool)) or current_val is None
    if is_primitive:
        display_value = current_val if isinstance(current_val, str) else ("" if current_val is None else str(current_val))
        new_val_str = st.text_area("New Value", value=display_value, height=240, key=f"txt_sandbox_{var_name}")
    else:
        edited = code_editor(
            code=str(repr(current_val)),
            lang="python",
            theme="default",
            height=240,
            response_mode="blur",
            allow_reset=True,
            buttons=custom_btns,
            key=f"code_sandbox_{var_name}",
        )
        new_val_str = edited.get("text", str(repr(current_val)))

    if st.button("Update Variable"):
        if is_primitive:
            if isinstance(current_val, str):
                new_value = new_val_str
            elif new_val_str.strip() == "":
                new_value = None
            else:
                try:
                    new_value = ast.literal_eval(new_val_str)
                except Exception as e:
                    st.error(f"Invalid value: {e}")
                    return
        else:
            try:
                new_value = ast.literal_eval(new_val_str)
            except Exception as e:
                st.error(f"Invalid value: {e}")
                return
        ok = update_sandbox_identifiers_variable(var_name, new_value)
        if ok:
            st.success(f"Updated {var_name}")
            
            # Refresh selected workflow data since sandbox variables may be used by workflows
            if st.session_state.get("selected_workflow"):
                try:
                    refresh_workflow_data(st.session_state["selected_workflow"])
                    st.info("✅ Refreshed selected workflow data")
                except Exception as e:
                    st.warning(f"⚠️ Could not refresh selected workflow: {e}")
            
            st.rerun()
        else:
            st.error("Update failed; check logs")


def main() -> None:
    _render_header()
    vars_dict = list_sandbox_variables()
    _render_variables_table(vars_dict)
    st.divider()
    _render_edit_form(vars_dict)


if __name__ == "__main__":
    main()


