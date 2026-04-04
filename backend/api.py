"""
FastAPI control-plane API for cloud notebook runtime execution.

Endpoints
---------
POST   /session/create          – create a provider session
POST   /execute                 – submit code for async execution
GET    /status/{execution_id}   – poll execution state
POST   /cancel/{execution_id}   – cancel a queued/running execution
GET    /health                  – liveness / provider info
WS     /ws/{client_id}          – live status/log streaming

Configuration (environment variables)
--------------------------------------
RUNTIME_PROVIDER   kaggle (default)
API_HOST           0.0.0.0
API_PORT           8000
API_TOKEN          optional bearer token (auth disabled when empty)
KAGGLE_USERNAME    Kaggle account username  (for real Kaggle integration)
KAGGLE_KEY         Kaggle API key           (for real Kaggle integration)
LOG_LEVEL          INFO (default)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.auth import APIKeyMiddleware
from backend.models import (
    CancelResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    ExecuteRequest,
    ExecuteResponse,
    HealthResponse,
    StatusResponse,
)
from runtime.adapter import ExecutionStatus
from runtime.kaggle_adapter import KaggleRuntimeAdapter
from runtime.store import ExecutionStore

# ------------------------------------------------------------------ #
# Logging setup
# ------------------------------------------------------------------ #
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Provider factory
# ------------------------------------------------------------------ #
_store = ExecutionStore()

_PROVIDERS: Dict[str, Any] = {
    "kaggle": lambda: KaggleRuntimeAdapter(_store),
}


def _get_adapter():
    provider = os.getenv("RUNTIME_PROVIDER", "kaggle").lower()
    factory = _PROVIDERS.get(provider)
    if factory is None:
        raise ValueError(
            f"Unknown RUNTIME_PROVIDER={provider!r}. "
            f"Available: {list(_PROVIDERS)}"
        )
    return factory()


# ------------------------------------------------------------------ #
# WebSocket connection manager
# ------------------------------------------------------------------ #
class _ConnectionManager:
    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}

    async def connect(self, client_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[client_id] = ws
        logger.info("ws_connected client_id=%s", client_id)

    def disconnect(self, client_id: str) -> None:
        self._connections.pop(client_id, None)
        logger.info("ws_disconnected client_id=%s", client_id)

    async def send(self, client_id: str, payload: dict) -> None:
        ws = self._connections.get(client_id)
        if ws:
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:  # noqa: BLE001
                self.disconnect(client_id)

    async def broadcast(self, payload: dict) -> None:
        for client_id in list(self._connections):
            await self.send(client_id, payload)


_manager = _ConnectionManager()

# ------------------------------------------------------------------ #
# App lifecycle
# ------------------------------------------------------------------ #


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup provider=%s", os.getenv("RUNTIME_PROVIDER", "kaggle"))
    yield
    logger.info("shutdown")


# ------------------------------------------------------------------ #
# FastAPI application
# ------------------------------------------------------------------ #
app = FastAPI(
    title="Cloud Notebook Runtime API",
    description=(
        "Control-plane API that enables VSCode local development to execute "
        "code on a cloud notebook runtime (default: Kaggle stub)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(APIKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #
def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _iso(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.isoformat() + "Z"


# ------------------------------------------------------------------ #
# Endpoints
# ------------------------------------------------------------------ #


@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health():
    """Liveness check – no auth required."""
    return HealthResponse(
        status="healthy",
        provider=os.getenv("RUNTIME_PROVIDER", "kaggle"),
    )


@app.post("/session/create", response_model=CreateSessionResponse, tags=["session"])
async def create_session(body: CreateSessionRequest):
    """Create a new provider session."""
    rid = _request_id()
    adapter = _get_adapter()
    session = await adapter.create_session(metadata=body.metadata)
    logger.info("request_id=%s session_created session_id=%s", rid, session.session_id)
    return CreateSessionResponse(
        session_id=session.session_id,
        provider=session.provider,
        created_at=_iso(session.created_at),
    )


@app.post("/execute", response_model=ExecuteResponse, tags=["execution"])
async def execute(body: ExecuteRequest):
    """Submit code for async execution on the cloud runtime."""
    rid = _request_id()
    execution_id = f"exec-{uuid.uuid4().hex}"
    adapter = _get_adapter()

    result = await adapter.execute(
        session_id=body.session_id,
        code=body.code,
        execution_id=execution_id,
        metadata=body.metadata,
    )
    logger.info(
        "request_id=%s execution_queued execution_id=%s session_id=%s",
        rid,
        execution_id,
        body.session_id,
    )

    # Push initial status to all WebSocket clients
    asyncio.create_task(
        _manager.broadcast(
            {
                "event": "status_update",
                "execution_id": execution_id,
                "status": result.status.value,
            }
        )
    )

    # Background task: push status updates as the execution progresses
    asyncio.create_task(_poll_and_push(adapter, execution_id))

    return ExecuteResponse(
        execution_id=result.execution_id,
        session_id=result.session_id,
        status=result.status.value,
    )


@app.get("/status/{execution_id}", response_model=StatusResponse, tags=["execution"])
async def get_status(execution_id: str):
    """Poll the current state of an execution."""
    result = _store.get_execution(execution_id)
    if result is None:
        return JSONResponse({"detail": "execution not found"}, status_code=404)
    return StatusResponse(
        execution_id=result.execution_id,
        session_id=result.session_id,
        status=result.status.value,
        output=result.output,
        error=result.error,
        created_at=_iso(result.created_at),
        updated_at=_iso(result.updated_at),
    )


@app.post("/cancel/{execution_id}", response_model=CancelResponse, tags=["execution"])
async def cancel_execution(execution_id: str):
    """Cancel a queued or running execution."""
    rid = _request_id()
    result = _store.get_execution(execution_id)
    if result is None:
        return JSONResponse({"detail": "execution not found"}, status_code=404)

    adapter = _get_adapter()
    try:
        updated = await adapter.cancel(execution_id)
    except KeyError:
        return JSONResponse({"detail": "execution not found"}, status_code=404)

    logger.info(
        "request_id=%s execution_cancelled execution_id=%s status=%s",
        rid,
        execution_id,
        updated.status,
    )
    await _manager.broadcast(
        {"event": "status_update", "execution_id": execution_id, "status": updated.status.value}
    )
    return CancelResponse(execution_id=updated.execution_id, status=updated.status.value)


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    WebSocket endpoint for live execution status/log streaming.

    Connect: ws://host:port/ws/<client_id>[?token=<API_TOKEN>]

    Server pushes JSON messages:
      {"event": "status_update", "execution_id": "...", "status": "..."}
      {"event": "pong"}

    Client can send:
      {"type": "ping"}
    """
    await _manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        _manager.disconnect(client_id)


# ------------------------------------------------------------------ #
# Background helpers
# ------------------------------------------------------------------ #


async def _poll_and_push(adapter, execution_id: str) -> None:
    """
    Poll execution state every second and push updates to WebSocket clients
    until the execution reaches a terminal state.
    """
    terminal = {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
    while True:
        await asyncio.sleep(1)
        try:
            result = await adapter.get_status(execution_id)
        except KeyError:
            break

        await _manager.broadcast(
            {
                "event": "status_update",
                "execution_id": execution_id,
                "status": result.status.value,
                "output": result.output,
                "error": result.error,
            }
        )
        if result.status in terminal:
            break


# ------------------------------------------------------------------ #
# Entry point
# ------------------------------------------------------------------ #
if __name__ == "__main__":
    uvicorn.run(
        "backend.api:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=True,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
