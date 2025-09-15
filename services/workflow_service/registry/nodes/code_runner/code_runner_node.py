from prefect import task, flow
import tempfile, pathlib, subprocess, json, os, shutil, hashlib, uuid

RUNNER_IMAGE = "py-runner:3.12"

def _copy_host_inputs(mapping: dict[str, str], dst_root: pathlib.Path) -> list[str]:
    """Copy host files into dst_root, preserving relpaths."""
    hints = []
    for rel, src in (mapping or {}).items():
        dst = (dst_root / rel).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        hints.append(f"inputs/{rel}")  # how the container will see it
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

@task
def run_untrusted_docker(
    code_str: str,
    inputs: dict,
    input_files: dict[str, str] | None = None,   # {"data.csv": "/abs/path/to/data.csv"}
    *,
    timeout_s: int = 20,
    mem_mb: int = 256,
    cpus: float = 0.5,
    allow_net: bool = False,                     # stretch goal toggle
    docker_network: str = "bridge",                # "none" or e.g. "bridge"/"runner_net"
    persist_root: str | None = None,             # e.g. "/srv/artifacts"; if set, we copy outputs here
    keep_temp: bool = False                      # debug: keep tmp dir even if persisted
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
    job_id = f"job-{uuid.uuid4().hex[:10]}"
    tmpdir = tempfile.mkdtemp(prefix=job_id + "-")
    td = pathlib.Path(tmpdir)

    try:
        # lay out per-job dirs
        code_path = td / "code.py"
        inp_dir = td / "inputs"
        out_dir = td / "out"
        inp_dir.mkdir()
        out_dir.mkdir()
        os.chmod(out_dir, 0o777)  # allow container user 10001 to write

        code_path.write_text(code_str, encoding="utf-8")
        read_hints = _copy_host_inputs(input_files or {}, inp_dir)

        # Prepare payload for container stdin
        stdin_payload = {"input": inputs, "read_hints": read_hints}

        # build docker run
        cmd = [
            "docker","run","--rm","-i",  # -i flag is essential for stdin input
            "--read-only",
            "--cap-drop=ALL",
            "--pids-limit","128",
            "--security-opt","no-new-privileges",
            "--user","10001:10001",
            "--cpus", str(cpus),
            "--memory", f"{mem_mb}m",
            "--memory-swap", f"{mem_mb}m",
            "--ulimit","nofile=64:64",
            "--tmpfs","/tmp:rw,size=32m,mode=1777",
            "-v", f"{code_path}:/work/code.py:ro",
            "-v", f"{inp_dir}:/work/inputs:ro",
            "-v", f"{out_dir}:/work/out:rw",
        ]
        cmd += ["--network", docker_network if allow_net else "none"]
        cmd.append(RUNNER_IMAGE)

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
                "runner_stdout": stdout[:2000],
                "runner_stderr": (proc.stderr or "")[:2000],
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

@flow
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


if __name__ == "__main__":
    # Test with CSV file input and pandas processing
    # NOTE: \n character messes up with newline in the code string so be careful while using that!
    csv_processing_code = """
import pandas as pd
import json
import os


# Test network access by pinging YCombinator.com
import urllib.request
import urllib.error

try:
    print("Testing network access to ycombinator.com...")
    
    # Create a request with timeout
    req = urllib.request.Request("https://ycombinator.com")
    with urllib.request.urlopen(req, timeout=10) as response:
        status_code = response.getcode()
        print(f"Response status: {status_code}")
        
        # Get the response text and extract middle 500 characters
        content = response.read().decode('utf-8')
        content_length = len(content)
        
        if content_length >= 500:
            # Calculate the middle position and extract 500 characters around it
            middle_pos = content_length // 2
            start_pos = max(0, middle_pos - 250)
            end_pos = min(content_length, start_pos + 500)
            middle_content = content[start_pos:end_pos]
            
            print(f"Middle 500 characters from ycombinator.com (chars {start_pos}-{end_pos} of {content_length}):")
            print("-" * 60)
            print(middle_content)
            print("-" * 60)
        else:
            print(f"Content too short ({content_length} chars), showing all:")
            print(content)
            
except urllib.error.URLError as e:
    print(f"Network request failed: {e}")
except Exception as e:
    print(f"Unexpected error during network test: {e}")

print("Continuing with CSV processing...")

# Use the FILES global to discover available input files
print(f"Available input files: {FILES}")
print(f"INPUT data: {INPUT}")

# Check if we have any CSV files available
csv_files = [f for f in FILES if f.endswith('.csv')]
if not csv_files:
    print("No CSV files found in input files!")
    RESULT = {"error": "no_csv_files", "available_files": FILES}
else:
    # Use the first CSV file found
    csv_file = csv_files[0]
    print(f"Processing CSV file: {csv_file}")
    
    # Read the input CSV file using FILES global
    df = pd.read_csv(csv_file)
    
    # Output the data as JSON to stdout
    data_dict = df.to_dict('records')
    print("\\nCSV DATA AS JSON:")
    print(json.dumps(data_dict, indent=2))
    
    # Create aggregations
    dept_stats = df.groupby('department').agg({
        'age': ['mean', 'min', 'max'],
        'salary': ['mean', 'sum'],
        'years_experience': 'mean'
    }).round(2)
    
    # Flatten column names for easier reading
    dept_stats.columns = ['_'.join(col).strip() for col in dept_stats.columns]
    dept_stats = dept_stats.reset_index()
    
    # Write aggregations to output file
    output_path = os.path.join(OUT_DIR, 'department_stats.csv')
    dept_stats.to_csv(output_path, index=False)
    print(f"\\nWrote aggregations to: {output_path}")
    
    # Also output summary stats to stdout
    summary = {
        "total_employees": len(df),
        "average_age": float(df['age'].mean()),
        "average_salary": float(df['salary'].mean()),
        "departments": df['department'].unique().tolist()
    }
    # raise Exception("test")
    
    print("\\nSUMMARY STATS:")
    print(json.dumps(summary, indent=2))
    
    # Set RESULT for the workflow system
    RESULT = {
        "processed_records": len(df),
        "output_files": ["department_stats.csv"],
        "summary": summary,
        "input_files_used": csv_files
    }
"""

    outputs = run_many([{
        "code": csv_processing_code,
        "inputs": {"message": "Processing employee data"},
        "input_files": {"data.csv": "/path/to/project/test_data.csv"}
    }])
    print(json.dumps(outputs, indent=4))
