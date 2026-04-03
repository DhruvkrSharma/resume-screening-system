"""
KaggleRuntimeAdapter – MVP stub.

This adapter **simulates** the Kaggle notebook lifecycle
(queued → running → completed/failed) using asyncio tasks.

TODO: Replace the simulated execution blocks below with real Kaggle API
      calls once you have working credentials:

  1. Authenticate:
       import kaggle
       kaggle.api.authenticate()   # reads ~/.kaggle/kaggle.json or env vars

  2. Create kernel / notebook:
       kaggle.api.kernels_push(...)

  3. Poll kernel status:
       status = kaggle.api.kernels_status(kernel_slug)

  4. Pull output:
       kaggle.api.kernels_output(kernel_slug, path=...)

  Real Kaggle kernels have cold-start times of 30-120 s and cannot be
  cancelled mid-run through the public API – document this as a known
  limitation.
"""
from __future__ import annotations

import asyncio
import logging
import textwrap
import uuid
from datetime import datetime, timezone
from typing import Optional

from .adapter import ExecutionResult, ExecutionStatus, RuntimeAdapter, SessionInfo
from .store import ExecutionStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

logger = logging.getLogger(__name__)

# Simulated execution timings (seconds)
_QUEUE_DELAY = 1.0      # time in QUEUED state
_RUN_DURATION = 3.0     # simulated execution wall-time


class KaggleRuntimeAdapter(RuntimeAdapter):
    """
    Kaggle notebook runtime adapter.

    MVP behaviour
    -------------
    * create_session  – allocates a stub session (no real API call).
    * execute         – enqueues code, advances lifecycle via asyncio task.
    * get_status      – reads from the shared ExecutionStore.
    * cancel          – marks CANCELLED if still QUEUED/RUNNING.

    Environment variables consumed (set in .env / environment):
      KAGGLE_USERNAME – Kaggle account username
      KAGGLE_KEY      – Kaggle API key
    """

    def __init__(self, store: ExecutionStore) -> None:
        self._store = store

    @property
    def provider_name(self) -> str:
        return "kaggle"

    # ------------------------------------------------------------------ #
    # Interface implementation
    # ------------------------------------------------------------------ #

    async def create_session(self, metadata: Optional[dict] = None) -> SessionInfo:
        """
        Allocate a Kaggle session stub.

        TODO: Create a Kaggle kernel / dataset to host the session.
        """
        session_id = f"kaggle-session-{uuid.uuid4().hex[:8]}"
        session = SessionInfo(
            session_id=session_id,
            provider=self.provider_name,
            created_at=_utcnow(),
            metadata=metadata or {},
        )
        self._store.save_session(session)
        logger.info("session_created session_id=%s provider=%s", session_id, self.provider_name)
        return session

    async def execute(
        self,
        session_id: str,
        code: str,
        execution_id: str,
        metadata: Optional[dict] = None,
    ) -> ExecutionResult:
        """
        Submit code for async execution.

        Returns immediately with status=QUEUED; a background asyncio task
        advances the state to RUNNING → COMPLETED/FAILED.

        TODO: Push code to a Kaggle kernel via kaggle.api.kernels_push().
        """
        result = ExecutionResult(
            execution_id=execution_id,
            session_id=session_id,
            status=ExecutionStatus.QUEUED,
            code=code,
            created_at=_utcnow(),
            updated_at=_utcnow(),
            metadata=metadata or {},
        )
        self._store.save_execution(result)
        logger.info(
            "execution_queued execution_id=%s session_id=%s",
            execution_id,
            session_id,
        )

        # Fire-and-forget background task to simulate execution lifecycle
        asyncio.create_task(self._run_execution(execution_id, code))
        return result

    async def get_status(self, execution_id: str) -> ExecutionResult:
        """
        Return current execution state.

        TODO: Poll kaggle.api.kernels_status(kernel_slug) and map to
              ExecutionStatus enum.
        """
        result = self._store.get_execution(execution_id)
        if result is None:
            raise KeyError(f"execution_id {execution_id!r} not found")
        return result

    async def cancel(self, execution_id: str) -> ExecutionResult:
        """
        Cancel a queued or running execution.

        TODO: Kaggle's public API does not expose a kernel-stop endpoint.
              For real integration, set a flag that the polling loop checks
              and deletes the kernel if possible.
        """
        result = self._store.get_execution(execution_id)
        if result is None:
            raise KeyError(f"execution_id {execution_id!r} not found")

        if result.status in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING):
            result.status = ExecutionStatus.CANCELLED
            result.updated_at = _utcnow()
            result.error = "Cancelled by user request."
            self._store.save_execution(result)
            logger.info("execution_cancelled execution_id=%s", execution_id)

        return result

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    async def _run_execution(self, execution_id: str, code: str) -> None:
        """
        Simulate the QUEUED → RUNNING → COMPLETED/FAILED lifecycle.

        Replace with real Kaggle polling once credentials are wired up.
        """
        await asyncio.sleep(_QUEUE_DELAY)

        result = self._store.get_execution(execution_id)
        if result is None or result.status == ExecutionStatus.CANCELLED:
            return

        # Transition to RUNNING
        result.status = ExecutionStatus.RUNNING
        result.updated_at = _utcnow()
        self._store.save_execution(result)
        logger.info("execution_running execution_id=%s", execution_id)

        await asyncio.sleep(_RUN_DURATION)

        result = self._store.get_execution(execution_id)
        if result is None or result.status == ExecutionStatus.CANCELLED:
            return

        # Simulate code execution (safe sandbox)
        output, error = self._safe_exec(code)

        result.status = ExecutionStatus.COMPLETED if error is None else ExecutionStatus.FAILED
        result.output = output
        result.error = error
        result.updated_at = _utcnow()
        self._store.save_execution(result)
        logger.info(
            "execution_finished execution_id=%s status=%s",
            execution_id,
            result.status,
        )

    @staticmethod
    def _safe_exec(code: str) -> tuple[Optional[str], Optional[str]]:
        """
        Execute Python code in a restricted namespace and capture stdout.

        TODO: Replace with real Kaggle kernel output fetch.

        WARNING: This exec() call runs arbitrary code inside the API server
        process. It is intentionally limited to the MVP stub and MUST NOT
        be used with untrusted input. When integrating with real Kaggle,
        remove this method entirely and use kaggle.api.kernels_output().
        """
        import io
        import sys

        import logging as _logging
        _logging.getLogger(__name__).warning(
            "STUB: executing code locally via exec() – unsafe for untrusted input. "
            "Replace with real Kaggle API integration before production use."
        )

        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout_capture
        try:
            exec(  # noqa: S102
                textwrap.dedent(code),
                {"__builtins__": __builtins__},
            )
            output = stdout_capture.getvalue()
            return output or "(no output)", None
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)
        finally:
            sys.stdout = old_stdout
