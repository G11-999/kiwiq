
## Product Requirements: Streamlit Workflow Executor UI (v0.1)

### Goals
- Provide a Streamlit multipage app to:
  - Discover and list available workflows
  - Select a workflow and keep the selection in global session state
  - View and edit: sandbox identifiers, workflow LLM inputs, testing inputs
  - Execute workflows from UI with optional predefined HITL inputs
  - Display final outputs and link to saved artifacts; stream intermediate messages in a future iteration

### Scope (Phase 1)
- Pages
  - Workflows: list and select workflows (category/name). Selected workflow is persisted globally.
  - Sandbox Editor: list and edit variables from `sandbox_identifiers.py`.
  - Config Editor: edit selected workflow’s `wf_llm_inputs.py` and `wf_testing/wf_inputs.py` (and optionally `wf_runner.py`, `wf_state_filter_mapping.py`).
  - Run Workflow: configure `initial_inputs` JSON, optional `hitl_inputs` JSON list; run workflow; show status, outputs, and links to artifacts.

- Data model / Session State
  - `selected_category` (str), `selected_workflow_name` (str)
  - `selected_workflow` (dict from `workflow_utils.get_workflow_by_name`)
  - `editing_buffers` for code/JSON editors
  - `last_run` metadata: status, outputs, artifacts_path

- Editors
  - Use `streamlit-code-editor` when available; fallback to `st.text_area`.
  - For JSON inputs, present a code editor and a live JSON viewer (parsed) side-by-side.

- Execution
  - Reuse existing async clients via `run_workflow_test` (blocking call inside a utility wrapper).
  - Provide optional pre-defined HITL inputs (list of dict). No in-run interactive HITL in v0.1; streaming to be added later.
  - Validate `initial_inputs` and `hitl_inputs` are valid JSON before running.

- Artifacts & Visibility
  - Pass `runs_folder_path` pointing to the workflow’s `wf_testing/runs` dir.
  - After completion, display final status, outputs (JSON), and links to saved logs/state.

### Out of Scope (Phase 1)
- Live, in-run HITL prompt UI with response schema–driven dynamic forms
- Real-time event streaming in Streamlit (will be Phase 2)
- Authentication/login in Streamlit

### Phase 2 Preview
- Live event streaming to Streamlit during run.
- Dynamic HITL UI while run is paused: construct form from `response_schema` and validate before submission.
- Experiments: manage multiple runs, compare outputs over time; show past runs per workflow.

### Technical Notes
- Utilities: `utils/workflow_utils.py` for discovery, file edits, reload.
- Runner: new `utils/streamlit_runner.py` wrapper to call `run_workflow_test` from Streamlit, handle JSON parsing, error surfacing, and artifact path return.
- Keep all Python code typed with rich docstrings. Editors should preserve quote styles when writing back via `workflow_utils.update_*` functions.

### Open Questions
- Should workflow selection also be a small global dropdown on all pages? For v0.1, selection is performed on the Workflows page and reflected globally; pages show current selection and link back to change.
- How to expose HITL schema-guided forms without modifying the runner? Likely needs a small forked client in Phase 2.


# Phase 1: Run a workflow, edit configs
1. Separate page: configure sandbox identifiers (this will be applied for all workflows to be run); configure X workflow 
identifiers (eg: which brief to load -- this is specific to a workflow) -- This will be common across all workflows!
2. List of all workflows (fetch by path); choose a workflow and go to that workflow testing page
   1. Workflow testing page: see past runs of workflow tests; create new run
3. Separate page: configure setup docs; check if these should be deleted or not + any additional docs to be deleted?
4. Workflow inputs
5. TODO: connect workflow 
   
6. ingest workflows in test namespace; mega workflows ingests all dependencies before executing and runs those test 
namespace workflows after ingestion
7. single editable file per workflow iwth all configs to be changed, prompts ,schemas, model etc ; verbose variable name; 
comments etc; ALSO schema fields graph mappings if any mappings / config dependent on LLM output schema! Edit file, it gets 
overwritten and you're good!

8. Workflow Running: HITL data; intermediate outputs, node wise outputs??, final outputs; HITL interaction and validation

Session, multipage; potential login?

# Phase 2: Experiment configs, multiple runs belonging to experiment, eval runs and show evals (evals of specific workflow 
runs, between indices or dates)
Show past test runs of a worklfow in test key!