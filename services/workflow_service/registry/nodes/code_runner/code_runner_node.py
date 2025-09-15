import logging
from prefect import task, flow
import tempfile, pathlib, subprocess, json, os, shutil, hashlib, uuid
import copy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union, Type, ClassVar
from enum import Enum

from pydantic import Field, BaseModel, model_validator
from bson.binary import Binary

# Internal dependencies
from kiwi_app.workflow_app.constants import LaunchStatus
from kiwi_app.auth.models import User
from kiwi_app.workflow_app.schemas import WorkflowRunJobCreate
from kiwi_app.workflow_app.service_customer_data import CustomerDataService
from sqlmodel.ext.asyncio.session import AsyncSession
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY,
)
from db.session import get_async_db_as_manager
from global_utils.utils import datetime_now_utc

# Base node/schema types
from workflow_service.registry.schemas.base import BaseSchema, BaseNodeConfig
from workflow_service.registry.nodes.core.base import BaseNode
from workflow_service.registry.nodes.db.customer_data import (
    LoadCustomerDataConfig, LoadCustomerDataNode, LoadCustomerDataOutput,
    FilenameConfig, _resolve_single_doc_path, _get_nested_obj
)

RUNNER_IMAGE = "py-runner:3.12"

# --- Save Configuration Schemas ---

class SaveFileConfig(BaseNodeConfig):
    """Configuration for saving a single output file as customer data."""
    namespace: str = Field(
        description="Exact namespace where the file should be saved."
    )
    docname: str = Field(
        description="Exact document name for the file."
    )
    is_shared: bool = Field(
        False,
        description="Whether to save the file as shared data."
    )

class SaveFileOverrides(BaseNodeConfig):
    """Output from code execution that can override default save configurations."""
    save_configs: Optional[Dict[str, SaveFileConfig]] = Field(
        None,
        description="Mapping of filenames to exact save configurations. "
                   "Keys are exact filenames, values are SaveFileConfig objects."
    )
    default_save_config: Optional[SaveFileConfig] = Field(
        None,
        description="Default save configuration to use for files not specifically configured."
    )

# --- Main Node Schemas ---

class CodeRunnerInputSchema(BaseSchema):
    """Input schema for the CodeRunner node."""
    code: Optional[str] = Field(
        None,
        description="Python code to execute. If not provided, uses default_code from config."
    )
    input_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Data to be made available to the code as the INPUT global variable."
    )
    load_data_inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input data for loading customer data files. "
                   "This will be passed to the LoadCustomerDataNode to load files."
    )

class SavedFileInfo(BaseNodeConfig):
    """Information about a file that was saved as customer data."""
    filename: str = Field(description="Original filename from code output")
    namespace: str = Field(description="Namespace where the file was saved")
    docname: str = Field(description="Document name used for saving")
    operation: str = Field(description="Save operation performed (e.g., 'create', 'upsert')")
    size_bytes: int = Field(description="Size of the saved file in bytes")
    document_path: str = Field(description="Full path identifier for the saved document")
    is_shared: bool = Field(description="Whether the file was saved as shared data")

class CodeRunnerOutputSchema(BaseSchema):
    """Output schema for the CodeRunner node."""
    success: bool = Field(description="Whether the code execution was successful")
    result: Optional[Any] = Field(
        None,
        description="The result returned by the code (value of RESULT global variable)"
    )
    logs: str = Field(default="", description="Execution logs from the code")
    error_message: Optional[str] = Field(None, description="Error message if execution failed")
    traceback: Optional[str] = Field(None, description="Python traceback if execution failed")
    
    # File handling results
    loaded_files_info: Optional[Dict[str, Any]] = Field(
        None,
        description="Information about customer data files that were loaded and made available to code"
    )
    saved_files: List[SavedFileInfo] = Field(
        default_factory=list,
        description="List of files that were saved as customer data from code output"
    )
    
    # Execution metadata
    execution_time_seconds: float = Field(description="Total execution time in seconds")
    artifacts_count: int = Field(description="Number of output artifacts created by the code")

class CodeRunnerConfigSchema(BaseNodeConfig):
    """Configuration schema for the CodeRunner node."""
    timeout_seconds: int = Field(
        30,
        description="Maximum time in seconds for code execution"
    )
    memory_mb: int = Field(
        256,
        description="Memory limit for code execution in MB"
    )
    cpus: float = Field(
        0.5,
        description="CPU limit for code execution"
    )
    default_code: Optional[str] = Field(
        None,
        description="Default Python code to execute if none provided in input"
    )
    load_data_config: Optional[LoadCustomerDataConfig] = Field(
        None,
        description="Configuration for loading customer data files. "
                   "If provided, files will be loaded and made available to code execution."
    )
    default_save_namespace: str = Field(
        "workflow_outputs_{run_id}",
        description="Default namespace pattern for saving output files. {run_id} will be replaced with actual run ID."
    )
    default_save_is_shared: bool = Field(
        False,
        description="Default value for is_shared when saving output files"
    )
    enable_network: bool = Field(
        False,
        description="Whether to allow network access during code execution"
    )
    persist_artifacts: bool = Field(
        True,
        description="Whether to persist code output artifacts and save them as customer data"
    )
    fail_node_on_code_error: bool = Field(
        False,
        description="Whether to raise an exception and fail the node when code execution fails"
    )

def _write_input_files(file_data_mapping: dict[str, tuple[str, bytes]], dst_root: pathlib.Path) -> list[str]:
    """Write file data directly into dst_root. DEPRECATED - kept for backward compatibility."""
    hints = []
    for filename, (content_type, file_bytes) in (file_data_mapping or {}).items():
        dst = (dst_root / filename).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        
        # Write the file data directly
        with open(dst, 'wb') as f:
            f.write(file_bytes)
        
        hints.append(f"inputs/{filename}")  # how the container will see it
    return hints

def _artifact_manifest(out_dir: pathlib.Path, base_dir: pathlib.Path,
                       max_artifacts=64, max_each_bytes=25*1024*1024):
    arts = []
    count = 0
    for p in out_dir.rglob("*"):
        if not p.is_file(): 
            continue
        count += 1
        if count > max_artifacts:
            arts.append({"warning": f"artifact_limit_exceeded>{max_artifacts}"})
            break
        size = p.stat().st_size
        if size > max_each_bytes:
            arts.append({"warning": f"artifact_too_large:{p.name}>{size}"})
            continue
        # sha256
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024*1024), b""):
                h.update(chunk)
        arts.append({
            # paths relative to the per-job base dir (so they stay stable if persisted)
            "relpath": str(p.relative_to(base_dir)),
            "size": size,
            "sha256": h.hexdigest(),
        })
    return arts


def run_untrusted_docker(
    code_str: str,
    inputs: dict,
    input_files: dict[str, str] | None = None,   # {"data.csv": "/abs/path/to/data.csv"} - DEPRECATED, use file_hints instead
    temp_dir: pathlib.Path | None = None,        # Optional temp directory to use
    host_temp_dir: pathlib.Path | None = None,    # Optional host temp directory to use
    file_hints: list[str] | None = None,         # File hints for files already written to inp_dir
    *,
    timeout_s: int = 20,
    mem_mb: int = 256,
    cpus: float = 0.5,
    allow_net: bool = False,                     # stretch goal toggle
    docker_network: str = "bridge",                # "none" or e.g. "bridge"/"runner_net"
    persist_root: str | None = None,             # e.g. "/srv/artifacts"; if set, we copy outputs here
    keep_temp: bool = False,                      # debug: keep tmp dir even if persisted
    logger = None,
):
    """
    Returns:
      {
        ok, result, logs, tb, rc,
        artifacts: [{relpath,size,sha256,...}],
        output_dir: <persisted_dir or temp_dir>,
        job_id
      }
    """
    logger = logger or logging.getLogger(__name__) 
    host_temp_dir = host_temp_dir or temp_dir
    job_id = f"job-{uuid.uuid4().hex[:10]}"
    if temp_dir:
        td = temp_dir
        tmpdir = str(td)
    else:
        tmpdir = tempfile.mkdtemp(prefix=job_id + "-")
    td = pathlib.Path(tmpdir)

    try:
        # lay out per-job dirs
        code_path = td / "code.py"
        inp_dir = td / "inputs"
        out_dir = td / "out"
        inp_dir.mkdir(exist_ok=True)
        out_dir.mkdir(exist_ok=True)
        
        # CRITICAL: Ensure proper permissions for Docker container user 10001 to write
        # The py-runner container runs as user 10001:10001 and needs write access to these dirs
        # This prevents PermissionError: [Errno 13] Permission denied: '/work/out' 
        try:
            os.chmod(inp_dir, 0o777)  # allow container user 10001 to read input files
            os.chmod(out_dir, 0o777)  # allow container user 10001 to write output files
            os.chmod(td, 0o755)       # parent directory must be accessible to user 10001
        except Exception as chmod_error:
            # Log but don't fail - permissions might already be set correctly in calling code
            logger.warning(f"Warning: Could not set directory permissions in run_untrusted_docker: {chmod_error}")

        # Validate code_str is not empty
        if not code_str or not code_str.strip():
            return {
                "ok": False, 
                "error": "empty_code", 
                "artifacts": [], 
                "output_dir": str(td), 
                "job_id": job_id,
                "logs": {"stdout": "", "stderr": "Code string is empty or None"}
            }
        
        # Ensure code_path is a file, not directory
        if code_path.exists() and code_path.is_dir():
            # Remove directory if it exists
            shutil.rmtree(code_path, ignore_errors=True)
        
        # Create parent directory if needed and write code file
        code_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            code_path.write_text(code_str, encoding="utf-8")
        except Exception as e:
            return {
                "ok": False, 
                "error": f"failed_to_write_code: {str(e)}", 
                "artifacts": [], 
                "output_dir": str(td), 
                "job_id": job_id,
                "logs": {"stdout": "", "stderr": f"Failed to write code file: {str(e)}"}
            }
        
        # Validate the code file was created successfully
        if not code_path.exists() or not code_path.is_file():
            return {
                "ok": False, 
                "error": "code_file_not_created", 
                "artifacts": [], 
                "output_dir": str(td), 
                "job_id": job_id,
                "logs": {"stdout": "", "stderr": f"Code file not created at {code_path}. Exists: {code_path.exists()}, Is file: {code_path.is_file() if code_path.exists() else 'N/A'}"}
            }
        
        # Handle input files - either write them or use provided hints
        if input_files:
            # Legacy path: write input files (deprecated)
            read_hints = _write_input_files(input_files, inp_dir)
        else:
            # New path: files already written, use provided hints
            read_hints = file_hints or []

        # Prepare payload for container stdin
        stdin_payload = {"input": inputs, "read_hints": read_hints}

        # Verify the file exists and is readable before mounting
        if not os.access(code_path, os.R_OK):
            return {
                "ok": False, 
                "error": "code_file_not_readable", 
                "artifacts": [], 
                "output_dir": str(td), 
                "job_id": job_id,
                "logs": {"stdout": "", "stderr": f"Code file not readable: {code_path}"}
            }

        # build docker run - mount the parent directory instead of individual files
        # This avoids the "Is a directory" issue with direct file mounting
        cmd = [
            "docker","run","--rm","-i",  # -i flag is essential for stdin input
            "--read-only",  # CRITICAL: Makes container filesystem read-only for security
            "--cap-drop=ALL",
            "--pids-limit","128",
            "--security-opt","no-new-privileges",
            "--user","10001:10001",
            "--cpus", str(cpus),
            "--memory", f"{mem_mb}m",
            "--memory-swap", f"{mem_mb}m",
            "--ulimit","nofile=64:64",
            "--tmpfs","/tmp:rw,size=32m,mode=1777",
            # Mount ONLY this job's temp directory to /work - maintains per-job isolation
            # Docker-in-Docker path conversion is handled by the caller
            "-v", f"{host_temp_dir}:/work",
        ]
        cmd += ["--network", docker_network if allow_net else "none"]
        cmd.append(RUNNER_IMAGE)
        
        # # Debug: Log the temp directory structure before running
        # print(f"DEBUG HOST: temp_dir contents before Docker:")
        # for root, dirs, files in os.walk(td):
        #     level = root.replace(str(td), '').count(os.sep)
        #     indent = ' ' * 2 * level
        #     print(f"DEBUG HOST: {indent}{os.path.basename(root)}/")
        #     subindent = ' ' * 2 * (level + 1)
        #     for file in files:
        #         file_path = os.path.join(root, file)
        #         size = os.path.getsize(file_path)
        #         print(f"DEBUG HOST: {subindent}{file} ({size} bytes)")

        # run with wall-time timeout
        try:
            proc = subprocess.run(
                cmd,
                input=json.dumps(stdin_payload),
                text=True, capture_output=True, timeout=timeout_s
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False, "error": f"timeout>{timeout_s}s",
                "artifacts": [], "output_dir": str(td), "job_id": job_id
            }

        # parse runner JSON line (stdout)
        stdout = proc.stdout or ""
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {
                "ok": False, "error": "non_json_stdout",
                "logs": {"stdout": stdout[:2000], "stderr": (proc.stderr or "")[:2000]},
            }
        payload.setdefault("rc", proc.returncode)

        # attach container stderr if entrypoint failed early
        if proc.stderr:
            payload.setdefault("container_stderr", proc.stderr[:4000])

        # manifest (based on temp dir layout)
        payload["artifacts"] = _artifact_manifest(out_dir, base_dir=td)

        # --- optional persistence ---
        persisted_dir = None
        if persist_root:
            pr = pathlib.Path(persist_root).expanduser().resolve()
            persisted_dir = pr / job_id
            # copy only the 'out' subtree to keep it small & intentional
            persisted_out = persisted_dir / "out"
            persisted_out.mkdir(parents=True, exist_ok=True)
            # safe copy: ignore symlinks
            for p in out_dir.rglob("*"):
                if p.is_symlink() or not p.is_file():
                    continue
                rel = p.relative_to(out_dir)
                dst = persisted_out / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
            payload["output_dir"] = str(persisted_dir)
        else:
            payload["output_dir"] = str(td)

        payload["job_id"] = job_id
        return payload

    finally:
        # cleanup temp dir unless explicitly kept or you persisted elsewhere already
        if persist_root and not keep_temp:
            shutil.rmtree(td, ignore_errors=True)
        elif not persist_root and not keep_temp:
            shutil.rmtree(td, ignore_errors=True)


def run_many(jobs: list[dict]):
    futures = []
    for j in jobs:
        futures.append(
            run_untrusted_docker.submit(
                j["code"], j.get("inputs", {}), j.get("input_files"),
                timeout_s=20, mem_mb=256, cpus=0.5,
                allow_net=False  # , docker_network="none",
                # persist_root="srv/artifacts"     # persisted for downstream tasks
            )
        )
    results = [f.result() for f in futures]
    # handle errors, logs, etc.
    return results


# --- CodeRunner Node Implementation ---

class CodeRunnerNode(BaseNode[CodeRunnerInputSchema, CodeRunnerOutputSchema, CodeRunnerConfigSchema]):
    """
    Node to execute Python code in a secure Docker environment with customer data integration.
    
    This node can:
    1. Load customer data files and make them available to code execution
    2. Execute Python code in a sandboxed Docker container
    3. Save any output files created by the code as customer data documents
    4. Return comprehensive execution results and file handling information
    
    Key features:
    - Secure code execution using Docker sandboxing
    - Integration with customer data loading and saving
    - Configurable resource limits (CPU, memory, timeout)
    - Support for dynamic save configurations from code output
    - Comprehensive error handling and logging
    """
    node_name: ClassVar[str] = "code_runner"
    node_version: ClassVar[str] = "1.0.0"
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT
    
    input_schema_cls: ClassVar[Type[CodeRunnerInputSchema]] = CodeRunnerInputSchema
    output_schema_cls: ClassVar[Type[CodeRunnerOutputSchema]] = CodeRunnerOutputSchema
    config_schema_cls: ClassVar[Type[CodeRunnerConfigSchema]] = CodeRunnerConfigSchema
    
    config: CodeRunnerConfigSchema

    async def process(
        self,
        input_data: Union[CodeRunnerInputSchema, Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any
    ) -> CodeRunnerOutputSchema:
        """
        Execute Python code with customer data integration.
        
        Args:
            input_data: Input containing code, input_data, and load_data_inputs
            runtime_config: Runtime configuration with context information
            
        Returns:
            CodeRunnerOutputSchema: Comprehensive execution results
        """
        if isinstance(input_data, dict):
            input_data = self.input_schema_cls(**input_data)
        
        if not runtime_config:
            self.error("Missing runtime_config.")
            return self._create_error_response("Missing runtime configuration")
        
        # Extract context
        configurable = runtime_config.get("configurable", {})
        app_context: Optional[Dict[str, Any]] = configurable.get(APPLICATION_CONTEXT_KEY)
        ext_context = configurable.get(EXTERNAL_CONTEXT_MANAGER_KEY)
        
        if not app_context or not ext_context:
            self.error(f"Missing required keys in runtime_config: {APPLICATION_CONTEXT_KEY} or {EXTERNAL_CONTEXT_MANAGER_KEY}")
            return self._create_error_response("Missing application context or external context")
        
        user: Optional[User] = app_context.get("user")
        run_job: Optional[WorkflowRunJobCreate] = app_context.get("workflow_run_job")
        if not user or not run_job:
            self.error("Missing 'user' or 'workflow_run_job' in application context")
            return self._create_error_response("Missing user or workflow run job information")
        
        org_id = run_job.owner_org_id
        run_id = str(run_job.id) if hasattr(run_job, 'id') else str(uuid.uuid4())
        
        self.info(f"Starting code execution for org {org_id}, run {run_id}")
        
        # try:
        # Step 1: Prepare code execution
        code_to_execute = input_data.code or self.config.default_code
        if not code_to_execute:
            return self._create_error_response("No code provided and no default_code configured")
        
        # Step 2: Execute code (this will handle file loading internally)
        execution_start_time = datetime.now(timezone.utc)
        execution_result, loaded_files_info = await self._execute_code(
            code_to_execute,
            input_data.input_data or {},
            input_data.load_data_inputs,
            runtime_config,
            org_id,
            user,
            run_job
        )
        execution_end_time = datetime.now(timezone.utc)
        execution_time = (execution_end_time - execution_start_time).total_seconds()
        
        # Check if we should fail the node on code execution error
        execution_success = execution_result.get("ok", False)
        if not execution_success and self.config.fail_node_on_code_error:
            error_details = self._format_code_execution_error(execution_result)
            self.error(f"Code execution failed: {error_details}")
            raise RuntimeError(f"CodeRunner execution failed: {error_details}")
        
        
        try:
            # Step 3: Process results and save files if execution was successful
            saved_files = []
            if execution_result.get("ok", False) and self.config.persist_artifacts:
                saved_files = await self._save_output_files(
                    execution_result,
                    org_id,
                    user,
                    run_id,
                    ext_context.customer_data_service
                )
        except Exception as e:
            raise e
        finally:    # cleanup temp directory regardless of success or failure
            self._cleanup_temp_directory(execution_result)
        
        # Step 4: Build response
        # Combine stdout and stderr logs into a single string
        logs_data = execution_result.get("logs", "")
        if isinstance(logs_data, dict):
            stdout = logs_data.get("stdout", "")
            stderr = logs_data.get("stderr", "")
            combined_logs = ""
            if stdout:
                combined_logs += f"STDOUT:\n{stdout}"
            if stderr:
                if combined_logs:
                    combined_logs += f"\n\nSTDERR:\n{stderr}"
                else:
                    combined_logs = f"STDERR:\n{stderr}"
            logs_str = combined_logs
        else:
            logs_str = str(logs_data) if logs_data else ""
        
        return CodeRunnerOutputSchema(
            success=execution_result.get("ok", False),
            result=execution_result.get("result"),
            logs=logs_str,
            error_message=execution_result.get("error") if not execution_result.get("ok", False) else None,
            traceback=execution_result.get("tb"),
            loaded_files_info=loaded_files_info,
            saved_files=saved_files,
            execution_time_seconds=execution_time,
            artifacts_count=len(execution_result.get("artifacts", []))
        )
            
        # except Exception as e:
        #     self.error(f"Unexpected error in code execution: {e}", exc_info=True)
        #     return self._create_error_response(f"Unexpected error: {str(e)}")

    async def _load_customer_data_files(
        self,
        load_data_inputs: Dict[str, Any],
        runtime_config: Dict[str, Any],
        org_id: str,
        user: User,
        run_job: WorkflowRunJobCreate,
        inp_dir: pathlib.Path
    ) -> tuple[Optional[Dict[str, Any]], List[str]]:
        """
        Load customer data files using LoadCustomerDataNode and write them directly to inp_dir.
        
        Args:
            inp_dir: Directory where input files should be written for Docker execution
        
        Returns:
            Tuple of (loaded_files_info, file_hints_list)
        """
        try:
            # Create and configure LoadCustomerDataNode

            data_loader_config = self.config.load_data_config.model_dump(exclude_unset=True) if self.config.load_data_config else {}
            if "force_add_missing_fields" not in data_loader_config:
                data_loader_config["force_add_missing_fields"] = True
            
            load_node = LoadCustomerDataNode(
                config=data_loader_config,
                node_id=f"{self.node_id}__data_loader",
                prefect_mode=self.prefect_mode, # Enable prefect mode for logging
                runtime_metadata=self.runtime_metadata,
            )
            
            # Execute data loading
            load_result = await load_node.process(
                input_data=load_data_inputs,
                runtime_config=runtime_config
            )
            
            # Process loaded data and write files directly to inp_dir
            file_hints = []
            loaded_info = {}
            
            # Convert loaded data and write files directly
            for field_name, field_value in load_result.model_dump().items():
                if field_name in ["loaded_fields", "output_metadata"]:
                    continue
                    
                if field_value is not None:
                    file_data = self._prepare_file_data_from_loaded_content(field_name, field_value)
                    if file_data:
                        filename, (content_type, file_bytes) = file_data
                        
                        # Write file directly to inp_dir
                        file_path = inp_dir / filename
                        with open(file_path, 'wb') as f:
                            f.write(file_bytes)
                        
                        file_hints.append(f"inputs/{filename}")
                        loaded_info[field_name] = {
                            "filename": filename,
                            "content_type": content_type,
                            "size_bytes": len(file_bytes),
                            "file_path": str(file_path)
                        }
            
            self.info(f"Loaded and wrote {len(file_hints)} customer data files directly to input directory")
            return loaded_info, file_hints
            
        except Exception as e:
            self.error(f"Failed to load customer data files: {e}", exc_info=True)
            return None, []

    def _prepare_file_data_from_loaded_content(self, field_name: str, data: Any) -> Optional[tuple[str, tuple[str, bytes]]]:
        """
        Prepare file data from loaded customer data content.
        
        Args:
            field_name: Name of the field
            data: The loaded data (can be dict with raw_content or regular data)
            
        Returns:
            Tuple of (filename, (content_type, file_bytes)) or None if failed
        """
        try:
            # Check if this is raw binary content (like uploaded files)
            if isinstance(data, dict) and "raw_content" in data and "source_filename" in data:
                # This is a file uploaded with raw content
                raw_content = data["raw_content"]
                source_filename = data["source_filename"]
                
                # Convert Binary to bytes if needed
                if hasattr(raw_content, '__bytes__'):
                    file_bytes = bytes(raw_content)
                elif isinstance(raw_content, bytes):
                    file_bytes = raw_content
                else:
                    self.warning(f"Raw content for {field_name} is not in binary format, converting to JSON")
                    file_bytes = json.dumps(data, indent=2, default=str).encode('utf-8')
                    source_filename = f"{field_name}.json"
                
                # Use original filename or construct one
                filename = source_filename or f"{field_name}.bin"
                content_type = "application/octet-stream"  # Default for binary
                
                # Try to determine content type from filename
                import mimetypes
                guessed_type, _ = mimetypes.guess_type(filename)
                if guessed_type:
                    content_type = guessed_type
                
                return filename, (content_type, file_bytes)
            
            else:
                # This is regular JSON data, convert to JSON file
                if isinstance(data, (dict, list)):
                    json_data = data
                else:
                    json_data = {"data": data}
                
                file_bytes = json.dumps(json_data, indent=2, default=str).encode('utf-8')
                filename = f"{field_name}.json"
                content_type = "application/json"
                
                return filename, (content_type, file_bytes)
                
        except Exception as e:
            self.error(f"Failed to prepare file data for {field_name}: {e}")
            return None

    async def _execute_code(
        self,
        code: str,
        input_data: Dict[str, Any],
        load_data_inputs: Optional[Dict[str, Any]],
        runtime_config: Dict[str, Any],
        org_id: str,
        user: User,
        run_job: WorkflowRunJobCreate
    ) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        Execute code using the existing run_untrusted_docker function.
        
        Args:
            code: Python code to execute
            input_data: Data to make available as INPUT global
            load_data_inputs: Optional data inputs for loading customer data files
            runtime_config: Runtime configuration for loading files
            org_id: Organization ID
            user: Current user
            run_job: Workflow run job
            
        Returns:
            Tuple of (execution_result, loaded_files_info)
        """
        try:
            self.info("Executing code in Docker container")
            
            # Create temporary directory for this execution
            import tempfile
            
            # Use /app/tmp for Docker-in-Docker compatibility when running in prefect-agent
            # /app is mounted from host in prefect-agent container, so nested containers can access it
            if os.path.exists("/app"):
                # Running inside prefect-agent container - use /app for Docker-in-Docker compatibility
                temp_base = "/app/tmp"
                os.makedirs(temp_base, exist_ok=True)
                temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="code_runner_", dir=temp_base))
            else:
                # Running directly on host - use system temp
                temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="code_runner_"))
            
            # Set up input directory
            inp_dir = temp_dir / "inputs"
            inp_dir.mkdir(exist_ok=True)
            
            # Set up output directory early and ensure proper permissions for Docker user 10001
            # The py-runner Docker container runs as user 10001:10001 and needs to be able to
            # create and write to the /work/out directory (which maps to our temp_dir/out)
            out_dir = temp_dir / "out"
            out_dir.mkdir(exist_ok=True)
            
            # CRITICAL: Set permissions for Docker container user 10001 to write to these directories
            # This fixes PermissionError: [Errno 13] Permission denied: '/work/out' in production
            # The Docker container mounts temp_dir to /work and runs as user 10001:10001
            try:
                os.chmod(temp_dir, 0o755)  # Parent directory needs to be accessible to user 10001
                os.chmod(inp_dir, 0o777)   # Input directory needs to be writable for file loading
                os.chmod(out_dir, 0o777)   # Output directory needs to be writable for artifacts
                self.debug(f"Set permissions on temp directories for Docker user 10001: {temp_dir}")
            except Exception as e:
                self.warning(f"Failed to set permissions on temp directories: {e}")
                # Continue execution - permissions might already be correct or container might handle it
            
            loaded_files_info = None
            file_hints = []
            
            # Load customer data files directly to inp_dir if needed
            if self.config.load_data_config:
                self.info("Loading customer data files directly to input directory")
                loaded_files_info, file_hints = await self._load_customer_data_files(
                    load_data_inputs,
                    runtime_config,
                    org_id,
                    user,
                    run_job,
                    inp_dir
                )
            
            # Convert temp_dir path for Docker-in-Docker compatibility
            host_temp_dir = pathlib.Path(self._get_host_path_for_docker_mount(str(temp_dir)))
            self.info(f"Executing code in Docker container, temp_dir: {temp_dir} -> host_path: {host_temp_dir}")
            
            try:
                result = run_untrusted_docker(
                    code_str=code,
                    inputs=input_data,
                    input_files=None,  # Files already written to inp_dir
                    temp_dir=temp_dir,
                    host_temp_dir=host_temp_dir,
                    file_hints=file_hints,  # Pass the file hints
                    timeout_s=self.config.timeout_seconds,
                    mem_mb=self.config.memory_mb,
                    cpus=self.config.cpus,
                    allow_net=self.config.enable_network,
                    persist_root=None,  # We'll handle persistence ourselves
                    keep_temp=True,  # Keep temp directory so we can access artifacts
                    logger=self,
                )
                
                self.info(f"Code execution completed. Success: {result.get('ok', False)}")
                
                # Store temp_dir path in result for cleanup after artifact saving
                result["_temp_dir_to_cleanup"] = str(temp_dir)
                
                return result, loaded_files_info
                
            except Exception as e:
                # Clean up temp directory on error
                try:
                    if temp_dir and temp_dir.exists():
                        import shutil
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        self.debug(f"Cleaned up temp directory on error: {temp_dir}")
                except Exception as cleanup_error:
                    self.warning(f"Failed to cleanup temp directory on error: {cleanup_error}")
                raise e
            
        except Exception as e:
            self.error(f"Code execution failed: {e}", exc_info=True)
            return {
                "ok": False,
                "error": f"Code execution failed: {str(e)}",
                "artifacts": [],
                "logs": {"stdout": "", "stderr": f"Code execution failed: {str(e)}"},
                "job_id": f"failed-{uuid.uuid4().hex[:8]}"
            }, None

    async def _save_output_files(
        self,
        execution_result: Dict[str, Any],
        org_id: str,
        user: User,
        run_id: str,
        customer_data_service: CustomerDataService
    ) -> List[SavedFileInfo]:
        """
        Save output artifacts as customer data files.
        
        Args:
            execution_result: Result from code execution
            org_id: Organization ID
            user: Current user
            run_id: Workflow run ID
            customer_data_service: Service for saving customer data
            
        Returns:
            List of information about saved files
        """
        saved_files = []
        artifacts = execution_result.get("artifacts", [])
        
        if not artifacts:
            self.info("No artifacts to save from code execution")
            return saved_files
        
        # Check if code provided save configuration overrides
        save_overrides = None
        result_data = execution_result.get("result")
        if isinstance(result_data, dict) and "save_file_config" in result_data:
            try:
                save_overrides = SaveFileOverrides.model_validate(result_data["save_file_config"])
                self.info("Found save configuration overrides from code output")
            except Exception as e:
                self.warning(f"Invalid save configuration from code output: {e}")
        
        self.info(f"Saving {len(artifacts)} output artifacts as customer data")
        
        for artifact in artifacts:
            try:
                saved_file = await self._save_single_artifact(
                    artifact,
                    execution_result,
                    org_id,
                    user,
                    run_id,
                    customer_data_service,
                    save_overrides
                )
                if saved_file:
                    saved_files.append(saved_file)
                    
            except Exception as e:
                self.error(f"Failed to save artifact {artifact.get('relpath', 'unknown')}: {e}", exc_info=True)
        
        self.info(f"Successfully saved {len(saved_files)} artifacts as customer data")
        return saved_files

    async def _save_single_artifact(
        self,
        artifact: Dict[str, Any],
        execution_result: Dict[str, Any],
        org_id: str,
        user: User,
        run_id: str,
        customer_data_service: CustomerDataService,
        save_overrides: Optional[SaveFileOverrides]
    ) -> Optional[SavedFileInfo]:
        """
        Save a single artifact as customer data.
        
        Args:
            artifact: Artifact information from code execution
            execution_result: Complete execution result containing output directory
            org_id: Organization ID
            user: Current user
            run_id: Workflow run ID
            customer_data_service: Service for saving customer data
            save_overrides: Optional save configuration overrides
            
        Returns:
            Information about the saved file or None if failed
        """
        try:
            # Extract artifact information
            rel_path = artifact.get("relpath", "")
            if not rel_path:
                self.warning("Artifact missing relative path, skipping")
                return None
            
            filename = os.path.basename(rel_path)
            size_bytes = artifact.get("size", 0)
            
            # Determine save configuration
            save_config = self._get_save_config_for_file(filename, save_overrides, run_id)
            
            # Use exact namespace and docname from configuration
            namespace = save_config.namespace
            docname = save_config.docname
            
            # Read the artifact file
            output_dir = execution_result.get("output_dir", "")
            artifact_path = os.path.join(output_dir, rel_path)
            
            if not os.path.exists(artifact_path):
                self.error(f"Artifact file not found: {artifact_path}")
                return None
            
            # Read file content
            with open(artifact_path, 'rb') as f:
                file_content = f.read()
            
            # Prepare data for storage (using raw binary format like file_processing.py)
            data_to_store = {
                "source_filename": filename,
                "raw_content": Binary(file_content),
                "created_by_code_execution": True,
                "execution_run_id": run_id,
                "created_at": datetime_now_utc().isoformat()
            }
            
            # Save as unversioned document (upsert mode)
            async with get_async_db_as_manager() as db:
                doc_id, created = await customer_data_service.create_or_update_unversioned_document(
                    db=db,
                    org_id=org_id if isinstance(org_id, uuid.UUID) else uuid.UUID(org_id),
                    namespace=namespace,
                    docname=docname,
                    is_shared=save_config.is_shared,
                    user=user,
                    data=data_to_store,
                    is_system_entity=False,  # Code execution files are never system entities
                    on_behalf_of_user_id=None,  # Code execution is always on behalf of current user
                    is_called_from_workflow=True
                )
            
            operation = "create" if created else "update"
            document_path = f"{org_id}/{namespace}/{docname}"
            
            self.info(f"Saved artifact {filename} as {document_path} ({operation})")
            
            return SavedFileInfo(
                filename=filename,
                namespace=namespace,
                docname=docname,
                operation=operation,
                size_bytes=size_bytes,
                document_path=document_path,
                is_shared=save_config.is_shared
            )
            
        except Exception as e:
            self.error(f"Error saving artifact {artifact.get('relpath', 'unknown')}: {e}", exc_info=True)
            return None

    def _get_save_config_for_file(
        self,
        filename: str,
        save_overrides: Optional[SaveFileOverrides],
        run_id: str
    ) -> SaveFileConfig:
        """
        Get the appropriate save configuration for a file.
        
        Args:
            filename: Name of the file
            save_overrides: Optional save configuration overrides from code
            run_id: Current workflow run ID
            
        Returns:
            Save configuration to use
        """
        # Check for specific override first
        if save_overrides and save_overrides.save_configs and filename in save_overrides.save_configs:
            return save_overrides.save_configs[filename]
        
        # Check for default override
        if save_overrides and save_overrides.default_save_config:
            return save_overrides.default_save_config
        
        # Use system defaults
        default_namespace = self.config.default_save_namespace.replace("{run_id}", run_id)
        return SaveFileConfig(
            namespace=default_namespace,
            docname=filename,  # Use filename as docname by default
            is_shared=self.config.default_save_is_shared
        )
    
    def _get_host_path_for_docker_mount(self, container_path: str) -> str:
        """
        Convert container path to host path for Docker-in-Docker compatibility.
        
        In Docker-in-Docker setups, the prefect-agent container mounts ./:/app,
        so /app inside the container corresponds to the project root on the host.
        This function converts container paths starting with /app to the correct host path.
        """
        if not container_path.startswith('/app/'):
            return container_path
        
        # Method 1: Use environment variable (recommended for production)
        host_project_path = os.environ.get('HOST_PROJECT_PATH')
        if host_project_path:
            self.debug(f"Using HOST_PROJECT_PATH: {host_project_path}")
            return container_path.replace('/app', host_project_path, 1)
        
        # Final fallback: return as-is
        self.warning(f"Could not convert container path {container_path} to host path - using as-is")
        return container_path

    def _format_code_execution_error(self, execution_result: Dict[str, Any]) -> str:
        """
        Format code execution error details for exception raising.
        
        Args:
            execution_result: The result from code execution
            
        Returns:
            Formatted error string with all relevant details
        """
        error_parts = []
        
        # Main error message
        error_msg = execution_result.get("error", "Unknown error")
        error_parts.append(f"Error: {error_msg}")
        
        # Traceback if available
        traceback = execution_result.get("tb")
        if traceback:
            error_parts.append(f"Traceback:\n{traceback}")
        
        # Container stderr if available
        container_stderr = execution_result.get("container_stderr")
        if container_stderr:
            error_parts.append(f"Container stderr:\n{container_stderr}")
        
        # Logs if available and structured
        logs_data = execution_result.get("logs", {})
        if isinstance(logs_data, dict):
            stdout = logs_data.get("stdout", "").strip()
            stderr = logs_data.get("stderr", "").strip()
            
            if stdout:
                error_parts.append(f"STDOUT:\n{stdout}")
            if stderr:
                error_parts.append(f"STDERR:\n{stderr}")
        elif logs_data:
            error_parts.append(f"Logs: {logs_data}")
        
        # Job ID for debugging
        job_id = execution_result.get("job_id")
        if job_id:
            error_parts.append(f"Job ID: {job_id}")
        
        return "\n\n".join(error_parts)

    async def _cleanup_temp_directory(self, execution_result: Dict[str, Any]) -> None:
        """
        Clean up the temporary directory used for code execution.
        
        Args:
            execution_result: Result from code execution containing temp directory path
        """
        temp_dir_path = execution_result.get("_temp_dir_to_cleanup")
        if not temp_dir_path:
            return
        
        try:
            import shutil
            temp_dir = pathlib.Path(temp_dir_path)
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
                self.debug(f"Successfully cleaned up temporary directory: {temp_dir_path}")
            else:
                self.debug(f"Temporary directory already cleaned up or doesn't exist: {temp_dir_path}")
        except Exception as e:
            self.warning(f"Failed to cleanup temporary directory {temp_dir_path}: {e}")

    def _create_error_response(self, error_message: str) -> CodeRunnerOutputSchema:
        """
        Create an error response.
        
        Args:
            error_message: Error message
            
        Returns:
            Error response
        """
        return CodeRunnerOutputSchema(
            success=False,
            error_message=error_message,
            logs="",
            execution_time_seconds=0.0,
            artifacts_count=0,
            saved_files=[]
        )


if __name__ == "__main__":
    # Example of how to use the CodeRunnerNode
    print("CodeRunnerNode Example")
    
    # Test code that creates some output files
    test_code = """
import json
import os
import pandas as pd

print("Hello from CodeRunnerNode!")
print(f"INPUT data received: {INPUT}")
print(f"Available files: {FILES}")

# Create a simple output file
output_file = os.path.join(OUT_DIR, 'test_output.json')
test_data = {
    "message": "This is a test output from CodeRunnerNode",
    "input_received": INPUT,
    "files_available": list(FILES) if FILES else [],
    "timestamp": "2024-01-01T12:00:00"
}

with open(output_file, 'w') as f:
    json.dump(test_data, f, indent=2)

print(f"Created output file: {output_file}")

# Create a CSV file as well
csv_file = os.path.join(OUT_DIR, 'sample_data.csv')
sample_df = pd.DataFrame({
    'name': ['Alice', 'Bob', 'Charlie'],
    'age': [25, 30, 35],
    'department': ['Engineering', 'Marketing', 'Sales']
})
sample_df.to_csv(csv_file, index=False)
print(f"Created CSV file: {csv_file}")

# Set result for the workflow system
RESULT = {
    "success": True,
    "files_created": ["test_output.json", "sample_data.csv"],
    "record_count": len(sample_df),
    # Example of providing save configuration overrides
    "save_file_config": {
        "default_save_config": {
            "namespace": f"code_outputs_custom_{run_id if 'run_id' in locals() else 'test_run'}",
            "docname": "custom_test_output.json",
            "is_shared": False
        },
        "save_configs": {
            "sample_data.csv": {
                "namespace": f"csv_outputs_{run_id if 'run_id' in locals() else 'test_run'}",
                "docname": "processed_sample_data.csv", 
                "is_shared": True
            }
        }
    }
}
"""
    
    # Example configuration for the node
    config = CodeRunnerConfigSchema(
        timeout_seconds=30,
        memory_mb=256,
        default_code=test_code,
        default_save_namespace="workflow_outputs_{run_id}",
        default_save_is_shared=False,
        persist_artifacts=True
    )
    
    # Example input data
    input_data = CodeRunnerInputSchema(
        code=test_code,  # Could be None to use default_code
        input_data={"test_message": "Hello from workflow!"},
        load_data_inputs=None  # Could contain data for loading customer files
    )
    
    print("Node configuration and input prepared.")
    print("To test this node, instantiate it in a proper workflow environment with:")
    print("- Proper runtime_config with APPLICATION_CONTEXT_KEY and EXTERNAL_CONTEXT_MANAGER_KEY")
    print("- Valid user and workflow_run_job context")
    print("- Customer data service available in external context")
    print("\nExample usage:")
    print("node = CodeRunnerNode(config=config, node_id='test_code_runner')")
    print("result = await node.process(input_data, runtime_config)")
    
    # Test the existing Docker execution function independently
    print("\n" + "="*60)
    print("Testing Docker execution function with simple code...")
    
    simple_test_code = """
import json
import os

print("Simple test from Docker container")
print(f"INPUT: {INPUT}")

# Create a simple output file
with open(os.path.join(OUT_DIR, 'simple_test.txt'), 'w') as f:
    f.write("Hello from Docker container!")

RESULT = {"message": "Docker test successful", "input_data": INPUT}
"""
    
    result = run_untrusted_docker(
        code_str=simple_test_code,
        inputs={"test": "data"},
        input_files=None,
        temp_dir=None,  # Let it create its own temp directory
        file_hints=None,  # No pre-loaded files
        timeout_s=10,
        mem_mb=128,
        cpus=0.25,
        allow_net=False,
        persist_root=None,
        keep_temp=False
    )
    
    print("Docker execution result:")
    print(json.dumps({k: v for k, v in result.items() if k != 'artifacts'}, indent=2))
    print(f"Artifacts created: {len(result.get('artifacts', []))}")
    for artifact in result.get('artifacts', []):
        print(f"  - {artifact.get('relpath', 'unknown')}: {artifact.get('size', 0)} bytes")
    
    # Show logs in structured format
    logs_data = result.get('logs', {})
    if isinstance(logs_data, dict):
        print(f"\nSTDOUT: {logs_data.get('stdout', 'none')}")
        print(f"STDERR: {logs_data.get('stderr', 'none')}")
    else:
        print(f"\nLogs: {logs_data}")
