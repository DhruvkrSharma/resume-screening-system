"""
Tests for the RuntimeAdapter interface and KaggleRuntimeAdapter lifecycle.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest

from kagglesdk.kernels.types.kernels_enums import KernelWorkerStatus
from runtime.adapter import ExecutionStatus, RuntimeAdapter
from runtime.kaggle_adapter import KaggleRuntimeAdapter, _QUEUE_DELAY, _RUN_DURATION
from runtime.store import ExecutionStore

# A little margin on top of the simulated execution time
_EXEC_TIMEOUT = _QUEUE_DELAY + _RUN_DURATION + 1.5


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def store() -> ExecutionStore:
    return ExecutionStore()


@pytest.fixture
def adapter(store: ExecutionStore) -> KaggleRuntimeAdapter:
    return KaggleRuntimeAdapter(store)


# ------------------------------------------------------------------ #
# Interface contract tests
# ------------------------------------------------------------------ #


def test_kaggle_adapter_is_runtime_adapter(adapter):
    assert isinstance(adapter, RuntimeAdapter)


def test_provider_name(adapter):
    assert adapter.provider_name == "kaggle"


# ------------------------------------------------------------------ #
# Session tests
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_create_session_returns_session_info(adapter):
    session = await adapter.create_session()
    assert session.session_id.startswith("kaggle-session-")
    assert session.provider == "kaggle"


@pytest.mark.asyncio
async def test_create_session_persisted_in_store(adapter, store):
    session = await adapter.create_session()
    stored = store.get_session(session.session_id)
    assert stored is not None
    assert stored.session_id == session.session_id


# ------------------------------------------------------------------ #
# Execute tests
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_execute_returns_queued(adapter):
    session = await adapter.create_session()
    result = await adapter.execute(
        session_id=session.session_id,
        code="print('hello')",
        execution_id="exec-test-001",
    )
    assert result.execution_id == "exec-test-001"
    assert result.status == ExecutionStatus.QUEUED


@pytest.mark.asyncio
async def test_execute_transitions_to_completed(adapter):
    """Full lifecycle: QUEUED → RUNNING → COMPLETED."""
    session = await adapter.create_session()
    result = await adapter.execute(
        session_id=session.session_id,
        code="print('done')",
        execution_id="exec-lifecycle-001",
    )
    assert result.status == ExecutionStatus.QUEUED

    # Wait longer than _QUEUE_DELAY + _RUN_DURATION
    await asyncio.sleep(_EXEC_TIMEOUT)

    final = await adapter.get_status("exec-lifecycle-001")
    assert final.status == ExecutionStatus.COMPLETED
    assert final.output is not None


@pytest.mark.asyncio
async def test_execute_failed_on_bad_code(adapter):
    """Syntax error should result in FAILED status."""
    session = await adapter.create_session()
    await adapter.execute(
        session_id=session.session_id,
        code="raise ValueError('boom')",
        execution_id="exec-fail-001",
    )
    await asyncio.sleep(_EXEC_TIMEOUT)
    final = await adapter.get_status("exec-fail-001")
    assert final.status == ExecutionStatus.FAILED
    assert final.error is not None


# ------------------------------------------------------------------ #
# Cancel tests
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_cancel_queued_execution(adapter):
    session = await adapter.create_session()
    await adapter.execute(
        session_id=session.session_id,
        code="print('will be cancelled')",
        execution_id="exec-cancel-001",
    )
    cancelled = await adapter.cancel("exec-cancel-001")
    assert cancelled.status == ExecutionStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_unknown_execution_raises(adapter):
    with pytest.raises(KeyError):
        await adapter.cancel("does-not-exist")


@pytest.mark.asyncio
async def test_get_status_unknown_raises(adapter):
    with pytest.raises(KeyError):
        await adapter.get_status("does-not-exist")


# ------------------------------------------------------------------ #
# Store tests
# ------------------------------------------------------------------ #


def test_store_list_executions_by_session(store, adapter):
    """list_executions should filter by session_id."""
    from runtime.adapter import ExecutionResult, ExecutionStatus

    r1 = ExecutionResult(
        execution_id="e1", session_id="s1",
        status=ExecutionStatus.QUEUED, code="x"
    )
    r2 = ExecutionResult(
        execution_id="e2", session_id="s2",
        status=ExecutionStatus.QUEUED, code="y"
    )
    store.save_execution(r1)
    store.save_execution(r2)

    assert len(store.list_executions(session_id="s1")) == 1
    assert store.list_executions(session_id="s1")[0].execution_id == "e1"
    assert len(store.list_executions()) == 2


# ------------------------------------------------------------------ #
# Real Kaggle API path (kaggle.api mocked)
# ------------------------------------------------------------------ #


@pytest.fixture
def mock_kaggle_api() -> MagicMock:
    """A MagicMock that mimics the kaggle.api object with default success responses."""
    api = MagicMock()
    api.authenticate.return_value = None
    api.kernels_push.return_value = MagicMock()

    status_resp = MagicMock()
    status_resp.status = KernelWorkerStatus.COMPLETE
    status_resp.failure_message = ""
    api.kernels_status.return_value = status_resp

    # kernels_output returns an empty list of files (output → "(no output)")
    api.kernels_output.return_value = ([], None)

    return api


@pytest.mark.asyncio
async def test_create_session_stores_kernel_metadata():
    """create_session should embed username and kernel_ref in session metadata."""
    store = ExecutionStore()
    with patch.dict(os.environ, {"KAGGLE_USERNAME": "testuser", "KAGGLE_KEY": "testkey"}):
        adapter = KaggleRuntimeAdapter(store)
        session = await adapter.create_session()
    assert session.metadata["username"] == "testuser"
    assert session.metadata["kernel_ref"].startswith("testuser/runtime-")
    assert "kernel_slug" in session.metadata


@pytest.mark.asyncio
async def test_kaggle_api_push_and_complete(mock_kaggle_api):
    """Happy path: kernel pushed, polls COMPLETE, execution marked COMPLETED."""
    store = ExecutionStore()
    with (
        patch("runtime.kaggle_adapter._KAGGLE_AVAILABLE", True),
        patch("runtime.kaggle_adapter._POLL_INTERVAL", 0.05),
        patch("runtime.kaggle_adapter.kaggle") as mock_pkg,
        patch.dict(os.environ, {"KAGGLE_USERNAME": "testuser", "KAGGLE_KEY": "testkey"}),
    ):
        mock_pkg.api = mock_kaggle_api

        adapter = KaggleRuntimeAdapter(store)
        session = await adapter.create_session()
        result = await adapter.execute(
            session_id=session.session_id,
            code="print('hello from kaggle')",
            execution_id="exec-kg-001",
        )
        assert result.status == ExecutionStatus.QUEUED

        await asyncio.sleep(0.5)  # allow push + one poll cycle to complete

        final = await adapter.get_status("exec-kg-001")
        assert final.status == ExecutionStatus.COMPLETED
        assert final.output == "(no output)"
        mock_kaggle_api.kernels_push.assert_called_once()
        mock_kaggle_api.kernels_status.assert_called()


@pytest.mark.asyncio
async def test_kaggle_api_push_failure_marks_failed(mock_kaggle_api):
    """If kernels_push raises, the execution should be marked FAILED."""
    mock_kaggle_api.kernels_push.side_effect = RuntimeError("network error")

    store = ExecutionStore()
    with (
        patch("runtime.kaggle_adapter._KAGGLE_AVAILABLE", True),
        patch("runtime.kaggle_adapter.kaggle") as mock_pkg,
        patch.dict(os.environ, {"KAGGLE_USERNAME": "testuser", "KAGGLE_KEY": "testkey"}),
    ):
        mock_pkg.api = mock_kaggle_api

        adapter = KaggleRuntimeAdapter(store)
        session = await adapter.create_session()
        await adapter.execute(
            session_id=session.session_id,
            code="print('hi')",
            execution_id="exec-kg-002",
        )
        await asyncio.sleep(0.3)

        final = await adapter.get_status("exec-kg-002")
        assert final.status == ExecutionStatus.FAILED
        assert "Failed to push kernel" in (final.error or "")
        assert "network error" in (final.error or "")


@pytest.mark.asyncio
async def test_kaggle_api_error_status_marks_failed(mock_kaggle_api):
    """If Kaggle reports ERROR status, the execution should be marked FAILED."""
    error_resp = MagicMock()
    error_resp.status = KernelWorkerStatus.ERROR
    error_resp.failure_message = "Out of memory"
    mock_kaggle_api.kernels_status.return_value = error_resp

    store = ExecutionStore()
    with (
        patch("runtime.kaggle_adapter._KAGGLE_AVAILABLE", True),
        patch("runtime.kaggle_adapter._POLL_INTERVAL", 0.05),
        patch("runtime.kaggle_adapter.kaggle") as mock_pkg,
        patch.dict(os.environ, {"KAGGLE_USERNAME": "testuser", "KAGGLE_KEY": "testkey"}),
    ):
        mock_pkg.api = mock_kaggle_api

        adapter = KaggleRuntimeAdapter(store)
        session = await adapter.create_session()
        await adapter.execute(
            session_id=session.session_id,
            code="print('hi')",
            execution_id="exec-kg-003",
        )
        await asyncio.sleep(0.4)

        final = await adapter.get_status("exec-kg-003")
        assert final.status == ExecutionStatus.FAILED
        assert final.error == "Out of memory"


@pytest.mark.asyncio
async def test_kaggle_api_cancel_stops_poll_loop(mock_kaggle_api):
    """Cancelling while the poll loop is running should exit the loop cleanly."""
    running_resp = MagicMock()
    running_resp.status = KernelWorkerStatus.RUNNING
    running_resp.failure_message = ""
    mock_kaggle_api.kernels_status.return_value = running_resp

    store = ExecutionStore()
    with (
        patch("runtime.kaggle_adapter._KAGGLE_AVAILABLE", True),
        patch("runtime.kaggle_adapter._POLL_INTERVAL", 0.05),
        patch("runtime.kaggle_adapter.kaggle") as mock_pkg,
        patch.dict(os.environ, {"KAGGLE_USERNAME": "testuser", "KAGGLE_KEY": "testkey"}),
    ):
        mock_pkg.api = mock_kaggle_api

        adapter = KaggleRuntimeAdapter(store)
        session = await adapter.create_session()
        await adapter.execute(
            session_id=session.session_id,
            code="print('hi')",
            execution_id="exec-kg-004",
        )
        # Allow the background task to push and enter the poll loop
        await asyncio.sleep(0.15)

        cancelled = await adapter.cancel("exec-kg-004")
        assert cancelled.status == ExecutionStatus.CANCELLED

        # After cancel the loop exits; status must remain CANCELLED
        await asyncio.sleep(0.2)
        final = await adapter.get_status("exec-kg-004")
        assert final.status == ExecutionStatus.CANCELLED


@pytest.mark.asyncio
async def test_kaggle_api_output_with_log_file(mock_kaggle_api, tmp_path):
    """kernels_output log file content should become the execution output."""
    log_file = tmp_path / "runtime-abc.log"
    log_file.write_text("Hello from Kaggle!\n")
    mock_kaggle_api.kernels_output.return_value = ([str(log_file)], None)

    store = ExecutionStore()
    with (
        patch("runtime.kaggle_adapter._KAGGLE_AVAILABLE", True),
        patch("runtime.kaggle_adapter._POLL_INTERVAL", 0.05),
        patch("runtime.kaggle_adapter.kaggle") as mock_pkg,
        patch.dict(os.environ, {"KAGGLE_USERNAME": "testuser", "KAGGLE_KEY": "testkey"}),
    ):
        mock_pkg.api = mock_kaggle_api

        adapter = KaggleRuntimeAdapter(store)
        session = await adapter.create_session()
        await adapter.execute(
            session_id=session.session_id,
            code="print('hello')",
            execution_id="exec-kg-005",
        )
        await asyncio.sleep(0.5)

        final = await adapter.get_status("exec-kg-005")
        assert final.status == ExecutionStatus.COMPLETED
        assert final.output == "Hello from Kaggle!\n"
