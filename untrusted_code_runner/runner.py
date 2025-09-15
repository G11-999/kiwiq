# Contract:
# - stdin JSON: {"input": {...}, "read_hints": ["inputs/data.csv", ...]}
# - mounts: /work/code.py (ro), /work/inputs (ro), /work/out (rw)
# - globals for user code: INPUT, FILES, OUT_DIR, RESULT
# - runner prints ONE JSON line to stdout:
#   {"ok": true/false, "result": ..., "logs": {"stdout": "...", "stderr": "..."}, "tb": "..."}
import sys, json, runpy, traceback, io, contextlib, pathlib

MAX_LOG = 200_000  # cap logs to keep IPC snappy

def _truncate(s: str, n: int = MAX_LOG) -> str:
    if s is None: return ""
    return s if len(s) <= n else (s[:n] + "…[truncated]")

def main():
    out_dir = pathlib.Path("/work/out")
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        stdin_raw = sys.stdin.read() or "{}"
        payload = json.loads(stdin_raw)
        input_data = payload.get("input", {})
        read_hints = payload.get("read_hints", [])  # e.g., ["inputs/data.csv"]
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"bad_stdin_json: {e}"}))
        return

    g = {
        "__name__": "__main__",
        "INPUT": input_data,
        "FILES": read_hints,      # purely informational convenience for plugin authors
        "OUT_DIR": str(out_dir),
        "RESULT": None,
    }

    # NOTE: we can debug like this:
    # print(f"DEBUG: INPUT received: {input_data}", file=sys.stderr)

    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        # Read the code file and execute it with our globals
        with open("/work/code.py", "r", encoding="utf-8") as f:
            code_content = f.read()
        
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            # NOTE: for multi-file and relative imports in custom code, runpy makes much more sense!
            # For your single-file plugin contract, exec(compile(...), g, g) is simpler, a bit faster, and (crucially) keeps RESULT in the same globals dict. runpy mainly helps when you want script-like semantics (e.g., relative imports from sibling files, proper __package__, sys.path[0] tweaks). You’re not allowing multi-file plugins or relative imports, so its benefits don’t apply.
            # runpy.run_path("/work/code.py", g)

            # compile(src, "/work/code.py", "exec") bakes the real path into the code object → your logs show /work/code.py:LINE, which is invaluable for users
            exec(compile(code_content, "/work/code.py", "exec"), g)
            # exec(code_content, g)
        
        # Get the final RESULT value
        result_value = g.get("RESULT")
        
        print(json.dumps({
            "ok": True,
            "result": result_value,
            "logs": {"stdout": _truncate(buf_out.getvalue()),
                     "stderr": _truncate(buf_err.getvalue())}
        }))
    except Exception:
        tb = traceback.format_exc()
        print(json.dumps({
            "ok": False,
            "error": "runtime_error",
            "tb": _truncate(tb),
            "logs": {"stdout": _truncate(buf_out.getvalue()),
                     "stderr": _truncate(buf_err.getvalue())}
        }))

if __name__ == "__main__":
    main()
