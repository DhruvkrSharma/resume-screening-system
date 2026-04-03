"""
Production IDE – FastAPI backend (MVP)

Endpoints
---------
GET  /api/health          – liveness check
POST /api/execute         – run Python / C / C++ code and return output
WS   /ws/debug            – [STUB] step-debugger placeholder (not implemented)
"""

import os
import subprocess
import tempfile
import time
import uuid

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Production IDE API", version="0.1.0")

# ---------------------------------------------------------------------------
# CORS – permissive for development; tighten to real origins in production
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost,http://localhost:5173,http://localhost:80",
).split(",")

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


class ExecuteResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    error: str | None = None


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

    def execute(self, code: str, language: str, timeout: int) -> ExecuteResponse:
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
            return self._run_python(code, timeout)
        elif language == "c":
            return self._run_c(code, timeout)
        else:
            return self._run_cpp(code, timeout)

    # ------------------------------------------------------------------
    # Python execution
    # ------------------------------------------------------------------
    def _run_python(self, code: str, timeout: int) -> ExecuteResponse:
        with tempfile.TemporaryDirectory() as tmpdir:
            script = os.path.join(tmpdir, f"{uuid.uuid4().hex}.py")
            with open(script, "w") as f:
                f.write(code)
            return self._subprocess_run(
                ["python3", script], timeout, cwd=tmpdir
            )

    # ------------------------------------------------------------------
    # C execution
    # ------------------------------------------------------------------
    def _run_c(self, code: str, timeout: int) -> ExecuteResponse:
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "prog.c")
            out = os.path.join(tmpdir, "prog")
            with open(src, "w") as f:
                f.write(code)

            compile_result = self._subprocess_run(
                ["gcc", src, "-o", out, "-lm"], timeout=30, cwd=tmpdir
            )
            if compile_result.exit_code != 0:
                compile_result.error = "Compilation failed"
                return compile_result

            return self._subprocess_run([out], timeout, cwd=tmpdir)

    # ------------------------------------------------------------------
    # C++ execution
    # ------------------------------------------------------------------
    def _run_cpp(self, code: str, timeout: int) -> ExecuteResponse:
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "prog.cpp")
            out = os.path.join(tmpdir, "prog")
            with open(src, "w") as f:
                f.write(code)

            compile_result = self._subprocess_run(
                ["g++", src, "-o", out, "-lm"], timeout=30, cwd=tmpdir
            )
            if compile_result.exit_code != 0:
                compile_result.error = "Compilation failed"
                return compile_result

            return self._subprocess_run([out], timeout, cwd=tmpdir)

    # ------------------------------------------------------------------
    # Shared subprocess runner
    # ------------------------------------------------------------------
    def _subprocess_run(
        self, cmd: list[str], timeout: int, cwd: str | None = None
    ) -> ExecuteResponse:
        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            elapsed = time.monotonic() - start
            return ExecuteResponse(
                stdout=result.stdout[:MAX_OUTPUT_LENGTH],
                stderr=result.stderr[:MAX_OUTPUT_LENGTH],
                exit_code=result.returncode,
                execution_time=round(elapsed, 3),
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
