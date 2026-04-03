"""
Integration tests for the FastAPI control-plane endpoints.
"""
from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api import app
from runtime.kaggle_adapter import _QUEUE_DELAY, _RUN_DURATION

_EXEC_TIMEOUT = _QUEUE_DELAY + _RUN_DURATION + 1.5


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ------------------------------------------------------------------ #
# Health
# ------------------------------------------------------------------ #


@pytest.mark.anyio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "provider" in data


# ------------------------------------------------------------------ #
# Session
# ------------------------------------------------------------------ #


@pytest.mark.anyio
async def test_create_session(client):
    resp = await client.post("/session/create", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["provider"] == "kaggle"


# ------------------------------------------------------------------ #
# Execute → Status lifecycle
# ------------------------------------------------------------------ #


@pytest.mark.anyio
async def test_execute_returns_queued(client):
    # Create session
    session_resp = await client.post("/session/create", json={})
    session_id = session_resp.json()["session_id"]

    exec_resp = await client.post(
        "/execute",
        json={"session_id": session_id, "code": "print('hi')"},
    )
    assert exec_resp.status_code == 200
    data = exec_resp.json()
    assert data["status"] == "queued"
    assert "execution_id" in data


@pytest.mark.anyio
async def test_status_unknown_execution(client):
    resp = await client.get("/status/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_execute_and_wait_for_completion(client):
    session_resp = await client.post("/session/create", json={})
    session_id = session_resp.json()["session_id"]

    exec_resp = await client.post(
        "/execute",
        json={"session_id": session_id, "code": "print('lifecycle test')"},
    )
    execution_id = exec_resp.json()["execution_id"]

    # Wait for execution to finish
    await asyncio.sleep(_EXEC_TIMEOUT)

    status_resp = await client.get(f"/status/{execution_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "completed"
    assert data["output"] is not None


# ------------------------------------------------------------------ #
# Cancel
# ------------------------------------------------------------------ #


@pytest.mark.anyio
async def test_cancel_queued_execution(client):
    session_resp = await client.post("/session/create", json={})
    session_id = session_resp.json()["session_id"]

    exec_resp = await client.post(
        "/execute",
        json={"session_id": session_id, "code": "print('cancel me')"},
    )
    execution_id = exec_resp.json()["execution_id"]

    cancel_resp = await client.post(f"/cancel/{execution_id}")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


@pytest.mark.anyio
async def test_cancel_unknown_execution(client):
    resp = await client.post("/cancel/does-not-exist")
    assert resp.status_code == 404
