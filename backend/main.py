"""
Production IDE – FastAPI backend (MVP)

Endpoints
---------
GET  /api/health          – liveness check
POST /api/execute         – run Python / C / C++ code and return output
WS   /ws/debug            – [STUB] step-debugger placeholder (not implemented)
"""

import logging
import os
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    import resource as _resource

    def _set_memory_limit() -> None:
        """Limit virtual address space of the child process to 256 MB."""
        limit = 256 * 1024 * 1024
        _resource.setrlimit(_resource.RLIMIT_AS, (limit, limit))

    _memory_limit_fn: Callable[[], None] | None = _set_memory_limit

except ImportError:
    # resource module is Unix-only; skip on other platforms
    _memory_limit_fn = None

logger = logging.getLogger(__name__)

app = FastAPI(title="Production IDE API", version="0.1.0")

# ---------------------------------------------------------------------------
# CORS – permissive for development; tighten to real origins in production
# ---------------------------------------------------------------------------
_CORS_DEFAULT = "http://localhost,http://localhost:5173,http://localhost:80"
_cors_raw = os.getenv("ALLOWED_ORIGINS", "")

if not _cors_raw:
    logger.warning(
        "ALLOWED_ORIGINS env var is not set. "
        "Falling back to development defaults (%s). "
        "Set ALLOWED_ORIGINS explicitly for production deployments.",
        _CORS_DEFAULT,
    )
    _cors_raw = _CORS_DEFAULT

ALLOWED_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Execution limits
# ---------------------------------------------------------------------------
MAX_CODE_LENGTH = 50_000          # characters
MAX_OUTPUT_LENGTH = 10_000        # characters
DEFAULT_TIMEOUT = 10              # seconds
MAX_TIMEOUT = 30                  # hard cap on requested timeout


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class ExecuteRequest(BaseModel):
    code: str
    language: str = "python"      # python | c | cpp
    timeout: int = DEFAULT_TIMEOUT
    stdin: str | None = None      # optional stdin to feed the running program


class ExecuteResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    error: str | None = None
    truncated: bool = False       # True when stdout/stderr was cut at MAX_OUTPUT_LENGTH


# ---------------------------------------------------------------------------
# Safe code executor
# ---------------------------------------------------------------------------
class SafeCodeExecutor:
    """
    Executes untrusted code in a subprocess with resource limits.

    This is resource-limited execution, **not** a hardened sandbox.
    For production use, run the backend container with --network none,
    add seccomp/AppArmor profiles, and isolate via a per-request runner
    container.
    """

    SUPPORTED_LANGUAGES = ("python", "c", "cpp")

    def execute(
        self,
        code: str,
        language: str,
        timeout: int,
        stdin_data: str | None = None,
    ) -> ExecuteResponse:
        if language not in self.SUPPORTED_LANGUAGES:
            return ExecuteResponse(
                stdout="",
                stderr="",
                exit_code=1,
                execution_time=0.0,
                error=f"Unsupported language: {language}. Choose from {self.SUPPORTED_LANGUAGES}",
            )

        if len(code) > MAX_CODE_LENGTH:
            return ExecuteResponse(
                stdout="",
                stderr="",
                exit_code=1,
                execution_time=0.0,
                error=f"Code exceeds maximum length of {MAX_CODE_LENGTH} characters",
            )

        timeout = min(timeout, MAX_TIMEOUT)

        if language == "python":
            return self._run_python(code, timeout, stdin_data)
        elif language == "c":
            return self._run_c(code, timeout, stdin_data)
        else:
            return self._run_cpp(code, timeout, stdin_data)

    # ------------------------------------------------------------------
    # Python execution
    # ------------------------------------------------------------------
    def _run_python(
        self, code: str, timeout: int, stdin_data: str | None
    ) -> ExecuteResponse:
        with tempfile.TemporaryDirectory() as tmpdir:
            script = os.path.join(tmpdir, f"{uuid.uuid4().hex}.py")
            with open(script, "w") as f:
                f.write(code)
            return self._subprocess_run(
                ["python3", script], timeout, cwd=tmpdir, stdin_data=stdin_data
            )

    # ------------------------------------------------------------------
    # C execution
    # ------------------------------------------------------------------
    def _run_c(
        self, code: str, timeout: int, stdin_data: str | None
    ) -> ExecuteResponse:
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "prog.c")
            out = os.path.join(tmpdir, "prog")
            with open(src, "w") as f:
                f.write(code)

            # Compilation does not need memory limits or stdin
            compile_result = self._subprocess_run(
                ["gcc", src, "-o", out, "-lm"],
                timeout=30,
                cwd=tmpdir,
                apply_limits=False,
            )
            if compile_result.exit_code != 0:
                compile_result.error = "Compilation failed"
                return compile_result

            return self._subprocess_run(
                [out], timeout, cwd=tmpdir, stdin_data=stdin_data
            )

    # ------------------------------------------------------------------
    # C++ execution
    # ------------------------------------------------------------------
    def _run_cpp(
        self, code: str, timeout: int, stdin_data: str | None
    ) -> ExecuteResponse:
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "prog.cpp")
            out = os.path.join(tmpdir, "prog")
            with open(src, "w") as f:
                f.write(code)

            # Compilation does not need memory limits or stdin
            compile_result = self._subprocess_run(
                ["g++", src, "-o", out, "-lm"],
                timeout=30,
                cwd=tmpdir,
                apply_limits=False,
            )
            if compile_result.exit_code != 0:
                compile_result.error = "Compilation failed"
                return compile_result

            return self._subprocess_run(
                [out], timeout, cwd=tmpdir, stdin_data=stdin_data
            )

    # ------------------------------------------------------------------
    # Shared subprocess runner
    # ------------------------------------------------------------------
    def _subprocess_run(
        self,
        cmd: list[str],
        timeout: int,
        cwd: str | None = None,
        stdin_data: str | None = None,
        apply_limits: bool = True,
    ) -> ExecuteResponse:
        preexec = _memory_limit_fn if apply_limits else None
        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                input=stdin_data,
                preexec_fn=preexec,
            )
            elapsed = time.monotonic() - start
            stdout_full = result.stdout
            stderr_full = result.stderr
            truncated = (
                len(stdout_full) > MAX_OUTPUT_LENGTH
                or len(stderr_full) > MAX_OUTPUT_LENGTH
            )
            return ExecuteResponse(
                stdout=stdout_full[:MAX_OUTPUT_LENGTH],
                stderr=stderr_full[:MAX_OUTPUT_LENGTH],
                exit_code=result.returncode,
                execution_time=round(elapsed, 3),
                truncated=truncated,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            return ExecuteResponse(
                stdout="",
                stderr="",
                exit_code=124,
                execution_time=round(elapsed, 3),
                error=f"Execution timed out after {timeout}s",
            )
        except FileNotFoundError as exc:
            elapsed = time.monotonic() - start
            return ExecuteResponse(
                stdout="",
                stderr="",
                exit_code=127,
                execution_time=round(elapsed, 3),
                error=f"Command not found: {exc.filename}",
            )


executor = SafeCodeExecutor()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/execute", response_model=ExecuteResponse)
async def execute_code(request: ExecuteRequest):
    return executor.execute(
        code=request.code,
        language=request.language,
        timeout=request.timeout,
        stdin_data=request.stdin,
    )


@app.websocket("/ws/debug")
async def debug_websocket(websocket: WebSocket):
    """
    [STUB] Step-debugger endpoint – not implemented in MVP v0.

    Connects and immediately tells the client this feature is not yet
    available, then closes cleanly.
    """
    await websocket.accept()
    await websocket.send_json(
        {
            "type": "info",
            "message": (
                "Step-by-step debugger is a stub in MVP v0. "
                "Full implementation is planned for MVP v1."
            ),
        }
    )
    await websocket.close()


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
