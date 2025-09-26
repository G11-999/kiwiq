"""
Utilities to execute workflows from Streamlit synchronously, with JSON parsing
and basic validation. Wraps the async `run_workflow_test` into sync functions.

Run-time notes:
- Uses the workflow graph schema from the selected workflow's JSON file.
- Optionally sets the workflow name to ingest-as for testing if available.
- Supports optional HITL inputs provided up-front (validated if jsonschema
  is available and response schema is provided by user).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import asyncio
import json

try:
    from jsonschema import validate as jsonschema_validate  # type: ignore
    from jsonschema.exceptions import ValidationError as JSONSchemaValidationError  # type: ignore
    _HAS_JSONSCHEMA = True
except Exception:
    _HAS_JSONSCHEMA = False

# Import the shared test runner
from kiwi_client.test_run_workflow_client import run_workflow_test

# Lightweight, stepwise runner utilities for Streamlit interactive UI
from kiwi_client.auth_client import AuthenticatedClient
from kiwi_client.run_client import WorkflowRunTestClient as BaseWorkflowRunTestClient
from kiwi_client.notification_hitl_client import HITLTestClient
from kiwi_client.workflow_client import WorkflowTestClient
from kiwi_client.schemas import workflow_api_schemas as wf_schemas
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus
from kiwi_client.customer_data_client import CustomerDataTestClient
import uuid


@dataclass
class RunResult:
    """Captures the essential results of a workflow run for Streamlit rendering."""
    status: Optional[str]
    outputs: Optional[Dict[str, Any]]
    run_folder: Optional[str]
    error: Optional[str]


def _ensure_event_loop() -> asyncio.AbstractEventLoop:
    """Get or create an event loop suitable for calling from Streamlit."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
        return loop
    except Exception:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def _compute_runs_folder_from_json_path(json_path: Path) -> Path:
    """Given a workflow JSON file path, return its wf_testing/runs folder path."""
    # Expected structure: .../workflows/active/<category>/<workflow_name>/<file>
    wf_dir = json_path.parent
    runs_dir = wf_dir / "wf_testing" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    return runs_dir


def validate_hitl_inputs_against_schema_if_available(
    hitl_inputs: Optional[List[Dict[str, Any]]], response_schema: Optional[Dict[str, Any]]
) -> Tuple[bool, Optional[str]]:
    """Optionally validate pre-provided HITL inputs against a JSON schema.

    Returns (ok, error_message).
    """
    if not hitl_inputs or not response_schema:
        return True, None
    if not _HAS_JSONSCHEMA:
        return False, "jsonschema not installed; cannot validate HITL inputs"

    try:
        for idx, item in enumerate(hitl_inputs):
            jsonschema_validate(instance=item, schema=response_schema)
        return True, None
    except JSONSchemaValidationError as e:  # type: ignore
        return False, f"HITL input validation failed: {e.message}"
    except Exception as e:
        return False, f"HITL input validation error: {e}"


def run_workflow_sync(
    *,
    workflow_json_path: Path,
    workflow_graph_schema: Dict[str, Any],
    testing_workflow_name: Optional[str],
    initial_inputs: Dict[str, Any],
    hitl_inputs: Optional[List[Dict[str, Any]]] = None,
    response_schema_for_validation: Optional[Dict[str, Any]] = None,
    state_filter_mapping: Optional[Dict[str, Any]] = None,
    test_name: str = "Streamlit Run",
    timeout_sec: int = 600,
) -> RunResult:
    """Run a workflow synchronously for Streamlit.

    Args:
        workflow_json_path: Path to the workflow's *_json.py file.
        workflow_graph_schema: Parsed graph schema dict.
        testing_workflow_name: Optional name to ingest-as for testing.
        initial_inputs: Initial inputs dict.
        hitl_inputs: Optional list of pre-provided HITL inputs.
        response_schema_for_validation: Optional JSON schema to validate HITL inputs.
        state_filter_mapping: Optional mapping for state filtering on dump.
        test_name: Name to tag the run artifacts with.
        timeout_sec: Max total duration.

    Returns:
        RunResult containing status, outputs, artifact folder path, and error if any.
    """
    # Validate HITL inputs if schema provided and library available
    ok, err = validate_hitl_inputs_against_schema_if_available(hitl_inputs, response_schema_for_validation)
    if not ok:
        return RunResult(status=None, outputs=None, run_folder=None, error=err)

    runs_folder = _compute_runs_folder_from_json_path(workflow_json_path)

    async def _runner() -> RunResult:
        try:
            status_obj, outputs = await run_workflow_test(
                test_name=test_name,
                workflow_graph_schema=workflow_graph_schema,
                workflow_name_to_ingest_as_for_testing=testing_workflow_name,
                initial_inputs=initial_inputs,
                expected_final_status=None,  # We'll not assert expected here; allow any terminal
                hitl_inputs=hitl_inputs,
                runs_folder_path=str(runs_folder),
                state_filter_mapping=state_filter_mapping,
                stream_intermediate_results=True,
                dump_artifacts=True,
                timeout_sec=timeout_sec,
            )
            status = status_obj.status.name if status_obj and getattr(status_obj, "status", None) else None
            return RunResult(status=status, outputs=outputs, run_folder=str(runs_folder), error=None)
        except Exception as e:
            return RunResult(status=None, outputs=None, run_folder=str(runs_folder), error=str(e))

    loop = _ensure_event_loop()
    return loop.run_until_complete(_runner())


# ---------- Stepwise runner primitives for Streamlit chat UI ---------- #

@dataclass
class StepUpdate:
    """Represents a state transition update from the workflow engine."""
    run_id: Optional[str]
    status: Optional[str]
    is_waiting_hitl: bool
    hitl_request_details: Optional[Dict[str, Any]]
    hitl_response_schema: Optional[Dict[str, Any]]
    final_outputs: Optional[Dict[str, Any]]
    state_snapshot: Optional[Dict[str, Any]]
    error: Optional[str]


async def _resolve_workflow_id(
    *,
    workflow_id: Optional[str] = None,
    workflow_name: Optional[str] = None,
    workflow_version: Optional[str] = None,
) -> Optional[str]:
    """Resolve a workflow ID using provided ID or by searching by name/version."""
    if workflow_id:
        return str(workflow_id)
    if not workflow_name:
        return None
    async with AuthenticatedClient() as auth_client:
        wf_client = WorkflowTestClient(auth_client)
        results = await wf_client.search_workflows(
            name=workflow_name,
            version_tag=workflow_version,
            include_public=True,
            include_system_entities=True,
        )
        if results and len(results) > 0 and getattr(results[0], "id", None):
            return str(results[0].id)
    return None


async def _create_workflow_from_schema(
    *,
    workflow_name: str,
    graph_schema: Dict[str, Any],
) -> Optional[str]:
    """Create a temporary workflow from schema and return workflow_id."""
    async with AuthenticatedClient() as auth_client:
        wf_client = WorkflowTestClient(auth_client)
        # Validate schema first
        validation_result = await wf_client.validate_graph_api(graph_config=graph_schema)
        if not validation_result or not validation_result.is_valid:
            return None
        # Create workflow
        created = await wf_client.create_workflow(name=workflow_name, graph_config=graph_schema)
        return str(created.id) if created and getattr(created, "id", None) else None


async def _submit_initial_run(
    *,
    workflow_id: str,
    inputs: Dict[str, Any],
    on_behalf_of_user_id: Optional[str] = None,
    include_active_overrides: Optional[bool] = None,
    include_override_tags: Optional[List[str]] = None,
    reset_overrides_on_hitl_resume: Optional[bool] = None,
) -> Optional[str]:
    """Submit an initial run and return the run_id."""
    async with AuthenticatedClient() as auth_client:
        run_client = BaseWorkflowRunTestClient(auth_client)
        submitted = await run_client.submit_run(
            workflow_id=workflow_id,
            inputs=inputs,
            on_behalf_of_user_id=on_behalf_of_user_id,
            include_active_overrides=include_active_overrides,
            include_override_tags=include_override_tags,
            reset_overrides_on_hitl_resume=reset_overrides_on_hitl_resume,
            streaming_mode=False,
        )
        return str(submitted.id) if submitted and getattr(submitted, "id", None) else None


async def _get_status_and_optionally_state(
    *, run_id: str, fetch_state: bool = False
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Fetch current status and optionally a state snapshot."""
    async with AuthenticatedClient() as auth_client:
        run_client = BaseWorkflowRunTestClient(auth_client)
        status_obj = await run_client.get_run_status(run_id)
        status = status_obj.status.name if status_obj and getattr(status_obj, "status", None) else None
        state_snapshot = None
        if fetch_state:
            try:
                state_snapshot, _ = await run_client.get_run_state(run_id=run_id, save_to_file=False)
            except Exception:
                state_snapshot = None
        return status, state_snapshot


async def _get_pending_hitl_job(run_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Get request_details and response_schema for the latest pending HITL job for a run."""
    async with AuthenticatedClient() as auth_client:
        hitl_client = HITLTestClient(auth_client)
        job = await hitl_client.get_latest_pending_hitl_job(run_id=run_id)
        if not job:
            return None, None
        try:
            return job.request_details, job.response_schema
        except Exception:
            return None, None


async def _resume_with_hitl(
    *,
    run_id: str,
    inputs: Dict[str, Any],
    on_behalf_of_user_id: Optional[str] = None,
    reset_overrides_on_hitl_resume: Optional[bool] = None,
    hitl_include_active_overrides: Optional[bool] = None,
    hitl_include_override_tags: Optional[List[str]] = None,
) -> bool:
    """Submit a HITL response to resume a run."""
    async with AuthenticatedClient() as auth_client:
        run_client = BaseWorkflowRunTestClient(auth_client)
        resumed = await run_client.submit_run(
            resume_run_id=run_id,
            inputs=inputs,
            on_behalf_of_user_id=on_behalf_of_user_id,
            reset_overrides_on_hitl_resume=reset_overrides_on_hitl_resume,
            include_active_overrides=hitl_include_active_overrides,
            include_override_tags=hitl_include_override_tags,
        )
        return bool(resumed)


def start_run_stepwise_sync(
    *,
    workflow_name_to_ingest_as: str,
    graph_schema: Dict[str, Any],
    initial_inputs: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
    """Create workflow from schema and start a run. Return (run_id, status)."""
    async def _go() -> Tuple[Optional[str], Optional[str]]:
        # Create temporary workflow from schema
        wid = await _create_workflow_from_schema(workflow_name=workflow_name_to_ingest_as, graph_schema=graph_schema)
        if not wid:
            return None, None
        # Submit run
        rid = await _submit_initial_run(workflow_id=wid, inputs=initial_inputs)
        if not rid:
            return None, None
        # Get initial status
        status, _ = await _get_status_and_optionally_state(run_id=rid, fetch_state=False)
        return rid, status

    loop = _ensure_event_loop()
    return loop.run_until_complete(_go())


def poll_next_step_sync(
    *,
    run_id: str,
    fetch_state: bool = True,
) -> StepUpdate:
    """Poll the run and return a StepUpdate describing whether HITL is needed or run finished."""
    async def _go() -> StepUpdate:
        status, state = await _get_status_and_optionally_state(run_id=run_id, fetch_state=fetch_state)
        if status is None:
            return StepUpdate(run_id=run_id, status=None, is_waiting_hitl=False, hitl_request_details=None, hitl_response_schema=None, final_outputs=None, state_snapshot=state, error="Failed to get status")
        if status == WorkflowRunStatus.WAITING_HITL.name:
            req, schema = await _get_pending_hitl_job(run_id)
            return StepUpdate(run_id=run_id, status=status, is_waiting_hitl=True, hitl_request_details=req, hitl_response_schema=schema, final_outputs=None, state_snapshot=state, error=None)
        if status == WorkflowRunStatus.COMPLETED.name:
            # Attempt to fetch final outputs via status object
            final_outputs = None
            async with AuthenticatedClient() as auth_client:
                run_client = BaseWorkflowRunTestClient(auth_client)
                status_obj = await run_client.get_run_status(run_id)
                final_outputs = getattr(status_obj, "outputs", None) if status_obj else None
            return StepUpdate(run_id=run_id, status=status, is_waiting_hitl=False, hitl_request_details=None, hitl_response_schema=None, final_outputs=final_outputs, state_snapshot=state, error=None)
        if status in (WorkflowRunStatus.FAILED.name, WorkflowRunStatus.CANCELLED.name):
            err = None
            async with AuthenticatedClient() as auth_client:
                run_client = BaseWorkflowRunTestClient(auth_client)
                status_obj = await run_client.get_run_status(run_id)
                err = getattr(status_obj, "error_message", None)
            return StepUpdate(run_id=run_id, status=status, is_waiting_hitl=False, hitl_request_details=None, hitl_response_schema=None, final_outputs=None, state_snapshot=state, error=err)
        # Still running or other non-terminal
        return StepUpdate(run_id=run_id, status=status, is_waiting_hitl=False, hitl_request_details=None, hitl_response_schema=None, final_outputs=None, state_snapshot=state, error=None)

    loop = _ensure_event_loop()
    return loop.run_until_complete(_go())


def resume_with_hitl_sync(
    *,
    run_id: str,
    hitl_inputs: Dict[str, Any],
) -> bool:
    """Submit HITL inputs and return True if resume succeeded."""
    async def _go() -> bool:
        return await _resume_with_hitl(run_id=run_id, inputs=hitl_inputs)

    loop = _ensure_event_loop()
    return loop.run_until_complete(_go())


# ---------- Setup docs helpers ---------- #

async def _create_or_update_setup_doc(
    client: CustomerDataTestClient,
    doc: Dict[str, Any],
) -> bool:
    ns = doc.get('namespace')
    dn = doc.get('docname')
    is_shared = bool(doc.get('is_shared', False))
    is_versioned = bool(doc.get('is_versioned', False))
    is_system = bool(doc.get('is_system_entity', False))
    if is_versioned:
        init_version = doc.get('initial_version')
        payload = wf_schemas.CustomerDataVersionedInitialize(
            is_shared=is_shared,
            initial_data=doc.get('initial_data', {}),
            initial_version=init_version,
            is_system_entity=is_system,
            on_behalf_of_user_id=None,
        )
        return await client.initialize_versioned_document(ns, dn, payload)
    else:
        payload = wf_schemas.CustomerDataUnversionedCreateUpdate(
            is_shared=is_shared,
            data=doc.get('initial_data', {}),
            is_system_entity=is_system,
            on_behalf_of_user_id=None,
        )
        return await client.create_or_update_unversioned_document(ns, dn, payload)


def create_setup_docs_sync(setup_docs: List[Dict[str, Any]]) -> int:
    """Create/setup documents required for a test run. Returns number created/updated."""
    async def _go() -> int:
        if not setup_docs:
            return 0
        count = 0
        async with AuthenticatedClient() as auth:
            c = CustomerDataTestClient(auth)
            for d in setup_docs:
                try:
                    ok = await _create_or_update_setup_doc(c, d)
                    if ok:
                        count += 1
                except Exception:
                    # best-effort; continue
                    continue
        return count

    loop = _ensure_event_loop()
    return loop.run_until_complete(_go())


def cleanup_docs_sync(cleanup_docs: List[Dict[str, Any]]) -> int:
    """Delete documents created by setup if requested. Returns number deleted (best-effort)."""
    async def _go() -> int:
        if not cleanup_docs:
            return 0
        count = 0
        async with AuthenticatedClient() as auth:
            c = CustomerDataTestClient(auth)
            for d in cleanup_docs:
                try:
                    ns = d.get('namespace')
                    dn = d.get('docname')
                    is_shared = bool(d.get('is_shared', False))
                    is_versioned = bool(d.get('is_versioned', False))
                    is_system = bool(d.get('is_system_entity', False))
                    ok = False
                    if is_versioned:
                        ok = await c.delete_versioned_document(ns, dn, is_shared=is_shared, is_system_entity=is_system, on_behalf_of_user_id=None)
                    else:
                        ok = await c.delete_unversioned_document(ns, dn, is_shared=is_shared, is_system_entity=is_system, on_behalf_of_user_id=None)
                    if ok:
                        count += 1
                except Exception:
                    continue
        return count

    loop = _ensure_event_loop()
    return loop.run_until_complete(_go())


def get_customer_data_client_sync() -> CustomerDataTestClient:
    """
    Get an authenticated CustomerDataTestClient synchronously.
    
    Returns:
        CustomerDataTestClient: Ready-to-use client for document operations
    """
    import asyncio
    import threading
    
    async def _get_client():
        auth_client = AuthenticatedClient()
        await auth_client.login()
        return CustomerDataTestClient(auth_client)
    
    # Check if we're already in an async context (like Streamlit)
    try:
        # Try to get the current running loop
        asyncio.get_running_loop()
        # If we get here, we're in an async context, so run in a separate thread
        result = [None]
        exception = [None]
        
        def run_in_thread():
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result[0] = new_loop.run_until_complete(_get_client())
                new_loop.close()
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        
        if exception[0]:
            raise exception[0]
        return result[0]
        
    except RuntimeError:
        # No loop is running, so we can create our own
        loop = _ensure_event_loop()
        return loop.run_until_complete(_get_client())


def run_async_operation_sync(async_operation):
    """
    Run an async operation synchronously for Streamlit.
    
    Args:
        async_operation: The async operation to run
        
    Returns:
        The result of the async operation
    """
    loop = _ensure_event_loop()
    return loop.run_until_complete(async_operation)


def upload_files_sync(files, config_payload=None):
    """
    Upload files synchronously for Streamlit.
    
    Args:
        files: List of tuples containing (filename, file_content_bytes, content_type)
        config_payload: FileUploadRequestPayload or JSON string containing upload configuration
        
    Returns:
        List of upload results if successful, None otherwise
    """
    import asyncio
    import threading
    
    async def _upload():
        auth_client = AuthenticatedClient()
        await auth_client.login()
        client = CustomerDataTestClient(auth_client)
        return await client.upload_files(files, config_payload)
    
    # Check if we're already in an async context (like Streamlit)
    try:
        # Try to get the current running loop
        current_loop = asyncio.get_running_loop()
        # If we get here, we're in an async context, so run in a separate thread
        result = [None]
        exception = [None]
        
        def run_in_thread():
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result[0] = new_loop.run_until_complete(_upload())
                new_loop.close()
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        
        if exception[0]:
            raise exception[0]
        return result[0]
        
    except RuntimeError:
        # No loop is running, so we can create our own
        loop = _ensure_event_loop()
        return loop.run_until_complete(_upload())


def validate_upload_config_sync(config_payload):
    """
    Validate file upload configuration synchronously for Streamlit.
    
    Args:
        config_payload: FileUploadValidationRequest containing config and file list
        
    Returns:
        FileUploadValidationResult if successful, None otherwise
    """
    import asyncio
    import threading
    
    async def _validate():
        auth_client = AuthenticatedClient()
        await auth_client.login()
        client = CustomerDataTestClient(auth_client)
        return await client.validate_upload_config(config_payload)
    
    # Check if we're already in an async context (like Streamlit)
    try:
        # Try to get the current running loop
        current_loop = asyncio.get_running_loop()
        # If we get here, we're in an async context, so run in a separate thread
        result = [None]
        exception = [None]
        
        def run_in_thread():
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result[0] = new_loop.run_until_complete(_validate())
                new_loop.close()
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        
        if exception[0]:
            raise exception[0]
        return result[0]
        
    except RuntimeError:
        # No loop is running, so we can create our own
        loop = _ensure_event_loop()
        return loop.run_until_complete(_validate())

