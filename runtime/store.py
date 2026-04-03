"""
In-memory execution store.

For MVP purposes all state lives in process memory.
Replace with Redis / a database for multi-process deployments.
"""
from __future__ import annotations

import threading
from typing import Dict, Optional

from .adapter import ExecutionResult, SessionInfo


class ExecutionStore:
    """Thread-safe in-memory store for sessions and executions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, SessionInfo] = {}
        self._executions: Dict[str, ExecutionResult] = {}

    # ------------------------------------------------------------------ #
    # Sessions
    # ------------------------------------------------------------------ #

    def save_session(self, session: SessionInfo) -> None:
        with self._lock:
            self._sessions[session.session_id] = session

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self) -> list[SessionInfo]:
        with self._lock:
            return list(self._sessions.values())

    # ------------------------------------------------------------------ #
    # Executions
    # ------------------------------------------------------------------ #

    def save_execution(self, result: ExecutionResult) -> None:
        with self._lock:
            self._executions[result.execution_id] = result

    def get_execution(self, execution_id: str) -> Optional[ExecutionResult]:
        with self._lock:
            return self._executions.get(execution_id)

    def list_executions(self, session_id: Optional[str] = None) -> list[ExecutionResult]:
        with self._lock:
            all_exec = list(self._executions.values())
        if session_id:
            return [e for e in all_exec if e.session_id == session_id]
        return all_exec
