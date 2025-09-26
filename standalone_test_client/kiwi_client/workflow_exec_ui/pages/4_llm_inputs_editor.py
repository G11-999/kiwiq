"""
LLM Inputs Editor: edit workflow LLM input variables for the selected workflow.
"""

from typing import Any, Dict
import ast
from pathlib import Path
import json

import streamlit as st

st.set_page_config(page_title="LLM Inputs Editor", page_icon="🛠️")

from kiwi_client.workflow_exec_ui.utils.workflow_utils import (
    list_workflow_variables,
    update_workflow_variable,
    get_workflows_root_path,
    refresh_workflow_data,
    custom_btns,
)

from code_editor import code_editor



def _require_selection() -> Dict[str, Any] | None:
    if not (st.session_state.get("selected_category") and st.session_state.get("selected_workflow_name") and st.session_state.get("selected_workflow")):
        st.warning("Select a workflow in the Workflows page first.")
        return None
    st.success(
        f"Selected: {st.session_state['selected_category']}/{st.session_state['selected_workflow_name']}"
    )
    return st.session_state["selected_workflow"]


def _maybe_show_json_preview(value: Any) -> None:
    try:
        if isinstance(value, (dict, list)):
            st.json(value, expanded=2)
        elif isinstance(value, str):
            parsed = json.loads(value)
            st.json(parsed, expanded=2)
    except Exception:
        pass


def main() -> None:
    st.title("LLM Inputs Editor")
    workflow = _require_selection()
    if not workflow:
        return

    mode = st.radio("Mode", ["Variable-by-variable", "Full file"], index=0, horizontal=True, key="llm_mode")

    if mode == "Variable-by-variable":
        vars_dict = list_workflow_variables(workflow, "llm_inputs")
        if not vars_dict:
            st.info("No LLM input variables found.")
            return

        var_name = st.selectbox("Variable (llm_inputs)", sorted(vars_dict.keys()), key="sel_llm")
        current_val = vars_dict.get(var_name)
        st.caption(f"Type: {type(current_val).__name__}")

        _maybe_show_json_preview(current_val)

        is_primitive = isinstance(current_val, (str, int, float, bool)) or current_val is None
        if is_primitive:
            display_value = current_val if isinstance(current_val, str) else ("" if current_val is None else str(current_val))
            # dynamic height by size
            length = len(display_value) if isinstance(display_value, str) else len(str(display_value))
            height = 200 if length < 200 else (320 if length < 1000 else 520)
            new_val_str = st.text_area("New Value", value=display_value, height=height, key=f"txt_llm_{var_name}")
        else:
            editor_key = f"code_llm_{var_name}"
            edited = code_editor(
                code=str(repr(current_val)),
                lang="python",
                theme="default",
                height=320,
                response_mode="blur",
                allow_reset=True,
                buttons=custom_btns,
                key=editor_key,
            )
            new_val_str = edited.get("text", str(repr(current_val)))

        if st.button("Update", key=f"btn_llm_{var_name}"):
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
            ok = update_workflow_variable(workflow, "llm_inputs", var_name, new_value)
            if ok:
                st.success(f"Updated {var_name}")
                st.rerun()
            else:
                st.error("Update failed; check logs")
    else:
        meta = workflow.get("metadata", {})
        category = meta.get("category")
        workflow_name = meta.get("workflow_name")
        try:
            workflows_root = get_workflows_root_path()
            file_path: Path = workflows_root / category / workflow_name / "wf_llm_inputs.py"
            if not file_path.exists():
                st.error(f"File not found: {file_path}")
                return
            original = file_path.read_text(encoding="utf-8")
        except Exception as e:
            st.error(f"Failed to load file: {e}")
            return

        # Initialize session state for content
        content_key = f"llm_full_content__{category}__{workflow_name}"
        if content_key not in st.session_state:
            st.session_state[content_key] = original

        # Syntax highlighting toggle
        use_syntax_highlight = st.checkbox(
            "Use syntax highlighting", 
            value=True, 
            key=f"llm_syntax_highlight__{category}__{workflow_name}"
        )

        if use_syntax_highlight:
            # Code editor with syntax highlighting
            st.subheader("Code Editor (with syntax highlighting)")
            
            response = code_editor(
                code=st.session_state.get(content_key, ""),
                lang="python",
                theme="default",
                height=600,
                response_mode="blur",
                key=f"llm_code_editor__{category}__{workflow_name}",
                allow_reset=True,
                buttons=custom_btns,
            )
            
            # Update content when editor changes
            new_content = response.get("text", "")
            if response.get("id") and new_content != st.session_state[content_key]:
                st.session_state[content_key] = new_content
                st.rerun()
        else:
            # Plain text editor
            st.subheader("Text Editor (plain text)")
            lines = st.session_state[content_key].count('\n') + 1
            height = 500 if lines < 40 else (700 if lines < 120 else 900)
            
            new_text = st.text_area(
                "LLM Inputs (full file)",
                value=st.session_state[content_key],
                height=height,
                key=f"llm_text_area__{category}__{workflow_name}",
            )
            
            # Update content when text area changes
            if new_text != st.session_state[content_key]:
                st.session_state[content_key] = new_text
                st.rerun()

        # Save button
        if st.button("Save LLM file", type="primary"):
            try:
                content_to_save = st.session_state[content_key]
                if len(content_to_save.strip()) == 0:
                    st.error("Cannot save empty content. Please add some content first.")
                    return
                
                file_path.write_text(content_to_save, encoding="utf-8")
                refresh_workflow_data(workflow)
                st.success("LLM inputs file saved successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")

if __name__ == "__main__":
    main()
