"""
KaggleRuntimeAdapter – Kaggle Kernels API integration.

When KAGGLE_USERNAME and KAGGLE_KEY environment variables are set the adapter
uses the real Kaggle Kernels API.  When they are absent (or the ``kaggle``
package is not installed) it falls back to a local simulation that is safe for
tests and development without credentials.

Real-API behaviour
------------------
* create_session – allocates a session with a unique kernel slug.
* execute        – pushes a notebook kernel via kaggle.api.kernels_push(),
                   then background-polls kernels_status() every _POLL_INTERVAL s.
* get_status     – reads from the shared ExecutionStore (updated by the background task).
* cancel         – marks CANCELLED in the store; the poll loop respects the flag.

Known Kaggle limitations
------------------------
* Cold-start times are typically 30–120 s; _POLL_INTERVAL is set to 10 s.
* Kaggle's public API does not provide a mid-run cancel endpoint; the adapter
  marks the execution CANCELLED locally but cannot stop a kernel mid-flight.
* Kernels require a unique slug per user; re-pushing the same slug re-runs it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import textwrap
import uuid
from datetime import datetime, timezone
from typing import Optional

from .adapter import ExecutionResult, ExecutionStatus, RuntimeAdapter, SessionInfo
from .store import ExecutionStore

try:
    import kaggle
    from kagglesdk.kernels.types.kernels_enums import KernelWorkerStatus
    _KAGGLE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _KAGGLE_AVAILABLE = False
    KernelWorkerStatus = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# Timings for stub/simulation mode (no credentials)
_QUEUE_DELAY = 1.0
_RUN_DURATION = 3.0

# Poll interval when using the real Kaggle API (kernels have slow cold starts)
_POLL_INTERVAL = 10.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_notebook(code: str) -> dict:
    """Wrap Python code in a minimal Jupyter notebook structure."""
    return {
        "nbformat": 4,
        "nbformat_minor": 4,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.10.0"},
        },
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": textwrap.dedent(code),
            }
        ],
    }


class KaggleRuntimeAdapter(RuntimeAdapter):
    """
    Kaggle notebook runtime adapter.

    Uses real Kaggle API when KAGGLE_USERNAME + KAGGLE_KEY env vars are set,
    otherwise falls back to a local simulation (safe for tests / local dev).

    Environment variables:
      KAGGLE_USERNAME – Kaggle account username
      KAGGLE_KEY      – Kaggle API key
    """

    def __init__(self, store: ExecutionStore) -> None:
        self._store = store

    @property
    def provider_name(self) -> str:
        return "kaggle"

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _credentials_available() -> bool:
        """Return True when both the kaggle package and API credentials are present."""
        return bool(
            _KAGGLE_AVAILABLE
            and os.getenv("KAGGLE_USERNAME")
            and os.getenv("KAGGLE_KEY")
        )

    @staticmethod
    def _get_api():
        """Authenticate and return the global Kaggle API client."""
        kaggle.api.authenticate()
        return kaggle.api

    # ------------------------------------------------------------------ #
    # Interface implementation
    # ------------------------------------------------------------------ #

    async def create_session(self, metadata: Optional[dict] = None) -> SessionInfo:
        """
        Allocate a session.

        Stores the Kaggle username and a unique kernel slug so that
        execute() can push to the correct kernel.
        """
        username = os.getenv("KAGGLE_USERNAME", "local")
        kernel_slug = f"runtime-{uuid.uuid4().hex[:8]}"
        session_id = f"kaggle-session-{uuid.uuid4().hex[:8]}"
        session = SessionInfo(
            session_id=session_id,
            provider=self.provider_name,
            created_at=_utcnow(),
            metadata={
                **(metadata or {}),
                "username": username,
                "kernel_slug": kernel_slug,
                "kernel_ref": f"{username}/{kernel_slug}",
            },
        )
        self._store.save_session(session)
        logger.info(
            "session_created session_id=%s kernel_ref=%s",
            session_id,
            session.metadata["kernel_ref"],
        )
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
        advances the state through RUNNING → COMPLETED/FAILED.
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

        if self._credentials_available():
            session = self._store.get_session(session_id)
            if session is None:
                result.status = ExecutionStatus.FAILED
                result.error = f"Session {session_id!r} not found."
                result.updated_at = _utcnow()
                self._store.save_execution(result)
            else:
                asyncio.create_task(self._push_and_poll(session, execution_id, code))
        else:
            asyncio.create_task(self._stub_run(execution_id, code))

        return result

    async def get_status(self, execution_id: str) -> ExecutionResult:
        """Return current execution state from the store."""
        result = self._store.get_execution(execution_id)
        if result is None:
            raise KeyError(f"execution_id {execution_id!r} not found")
        return result

    async def cancel(self, execution_id: str) -> ExecutionResult:
        """
        Cancel a queued or running execution.

        Note: Kaggle's public API does not expose a kernel-stop endpoint.
        The execution is marked CANCELLED locally; the background poll loop
        will exit on its next iteration.
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
    # Real Kaggle path
    # ------------------------------------------------------------------ #

    async def _push_and_poll(
        self, session: SessionInfo, execution_id: str, code: str
    ) -> None:
        """Push code as a Kaggle kernel then poll until completion."""
        loop = asyncio.get_running_loop()
        api = await loop.run_in_executor(None, self._get_api)
        kernel_ref = session.metadata["kernel_ref"]

        # Push notebook to Kaggle
        try:
            await loop.run_in_executor(None, self._push_kernel, api, session, code)
        except Exception as exc:
            logger.exception("kernel_push_failed execution_id=%s", execution_id)
            result = self._store.get_execution(execution_id)
            if result:
                result.status = ExecutionStatus.FAILED
                result.error = f"Failed to push kernel: {exc}"
                result.updated_at = _utcnow()
                self._store.save_execution(result)
            return

        # Transition to RUNNING
        result = self._store.get_execution(execution_id)
        if result is None or result.status == ExecutionStatus.CANCELLED:
            return
        result.status = ExecutionStatus.RUNNING
        result.updated_at = _utcnow()
        self._store.save_execution(result)
        logger.info(
            "execution_running execution_id=%s kernel_ref=%s", execution_id, kernel_ref
        )

        # Poll until terminal status
        while True:
            await asyncio.sleep(_POLL_INTERVAL)

            result = self._store.get_execution(execution_id)
            if result is None or result.status == ExecutionStatus.CANCELLED:
                return

            try:
                status_resp = await loop.run_in_executor(
                    None, api.kernels_status, kernel_ref
                )
            except Exception as exc:
                logger.warning(
                    "kernels_status_error execution_id=%s: %s", execution_id, exc
                )
                continue

            worker_status = status_resp.status
            failure_msg = status_resp.failure_message

            if worker_status == KernelWorkerStatus.COMPLETE:
                output = await loop.run_in_executor(
                    None, self._fetch_output, api, kernel_ref
                )
                result.status = ExecutionStatus.COMPLETED
                result.output = output
                result.updated_at = _utcnow()
                self._store.save_execution(result)
                logger.info("execution_completed execution_id=%s", execution_id)
                break

            elif worker_status == KernelWorkerStatus.ERROR:
                result.status = ExecutionStatus.FAILED
                result.error = failure_msg or "Kernel execution failed."
                result.updated_at = _utcnow()
                self._store.save_execution(result)
                logger.info(
                    "execution_failed execution_id=%s error=%s", execution_id, result.error
                )
                break

            elif worker_status in (
                KernelWorkerStatus.CANCEL_REQUESTED,
                KernelWorkerStatus.CANCEL_ACKNOWLEDGED,
            ):
                result.status = ExecutionStatus.CANCELLED
                result.error = "Kernel cancelled on Kaggle."
                result.updated_at = _utcnow()
                self._store.save_execution(result)
                logger.info("execution_cancelled_by_kaggle execution_id=%s", execution_id)
                break
            # KernelWorkerStatus.QUEUED or RUNNING → keep polling

    @staticmethod
    def _push_kernel(api, session: SessionInfo, code: str) -> None:
        """Write a temp folder with kernel-metadata.json + notebook and push to Kaggle."""
        username = session.metadata["username"]
        kernel_slug = session.metadata["kernel_slug"]

        with tempfile.TemporaryDirectory() as tmpdir:
            notebook_path = os.path.join(tmpdir, "kernel.ipynb")
            with open(notebook_path, "w") as fh:
                json.dump(_make_notebook(code), fh)

            meta = {
                "id": f"{username}/{kernel_slug}",
                "title": f"Runtime {kernel_slug}",
                "code_file": "kernel.ipynb",
                "language": "python",
                "kernel_type": "notebook",
                "is_private": True,
                "enable_gpu": False,
                "enable_internet": False,
                "dataset_sources": [],
                "competition_sources": [],
                "kernel_sources": [],
            }
            meta_path = os.path.join(tmpdir, "kernel-metadata.json")
            with open(meta_path, "w") as fh:
                json.dump(meta, fh)

            api.kernels_push(tmpdir)
            logger.info("kernel_pushed kernel_ref=%s/%s", username, kernel_slug)

    @staticmethod
    def _fetch_output(api, kernel_ref: str) -> str:
        """Download kernel output files and return the captured log content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files, _ = api.kernels_output(kernel_ref, tmpdir, quiet=True)
            # Prefer the .log file Kaggle produces; fall back to any text file
            for path in files:
                if path.endswith(".log"):
                    with open(path) as fh:
                        return fh.read() or "(no output)"
            for path in files:
                try:
                    with open(path) as fh:
                        return fh.read() or "(no output)"
                except Exception:  # noqa: BLE001
                    pass
        return "(no output)"

    # ------------------------------------------------------------------ #
    # Stub / simulation path (no credentials)
    # ------------------------------------------------------------------ #

    async def _stub_run(self, execution_id: str, code: str) -> None:
        """Simulate QUEUED → RUNNING → COMPLETED/FAILED without Kaggle API."""
        await asyncio.sleep(_QUEUE_DELAY)

        result = self._store.get_execution(execution_id)
        if result is None or result.status == ExecutionStatus.CANCELLED:
            return

        result.status = ExecutionStatus.RUNNING
        result.updated_at = _utcnow()
        self._store.save_execution(result)
        logger.info("execution_running execution_id=%s (stub mode)", execution_id)

        await asyncio.sleep(_RUN_DURATION)

        result = self._store.get_execution(execution_id)
        if result is None or result.status == ExecutionStatus.CANCELLED:
            return

        output, error = _safe_exec(code)
        result.status = ExecutionStatus.COMPLETED if error is None else ExecutionStatus.FAILED
        result.output = output
        result.error = error
        result.updated_at = _utcnow()
        self._store.save_execution(result)
        logger.info(
            "execution_finished execution_id=%s status=%s (stub mode)",
            execution_id,
            result.status,
        )


def _safe_exec(code: str) -> tuple[Optional[str], Optional[str]]:
    """
    Execute Python code in a restricted namespace and capture stdout.

    Used only in stub/development mode when KAGGLE_USERNAME / KAGGLE_KEY are
    not set.  Never call with untrusted input.
    """
    import io
    import sys

    logger.warning(
        "STUB: executing code locally via exec() – "
        "set KAGGLE_USERNAME and KAGGLE_KEY to use the real Kaggle API."
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
