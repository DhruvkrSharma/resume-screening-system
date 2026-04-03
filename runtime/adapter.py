"""
Abstract RuntimeAdapter interface.

Any new provider (e.g. Google Colab, SageMaker) only needs to subclass
RuntimeAdapter and implement the four abstract methods below.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExecutionStatus(str, Enum):
    """Lifecycle states for a single code-execution request."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SessionInfo:
    """Lightweight descriptor for a provider session."""
    session_id: str
    provider: str
    created_at: datetime = field(default_factory=_utcnow)
    metadata: dict = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Result/state snapshot for one execution request."""
    execution_id: str
    session_id: str
    status: ExecutionStatus
    code: str
    output: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    metadata: dict = field(default_factory=dict)


class RuntimeAdapter(abc.ABC):
    """
    Provider-agnostic interface for cloud notebook runtimes.

    Implementing a new provider requires only:
      1. Subclass RuntimeAdapter.
      2. Implement the four abstract methods.
      3. Register it in backend/api.py's provider factory.
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the provider (e.g. 'kaggle')."""

    @abc.abstractmethod
    async def create_session(self, metadata: Optional[dict] = None) -> SessionInfo:
        """
        Allocate / open a new runtime session with the provider.

        Returns a SessionInfo describing the session.
        """

    @abc.abstractmethod
    async def execute(
        self,
        session_id: str,
        code: str,
        execution_id: str,
        metadata: Optional[dict] = None,
    ) -> ExecutionResult:
        """
        Submit *code* for asynchronous execution on the provider.

        Must return immediately with status QUEUED or RUNNING.
        Actual completion is polled via get_status() or pushed via events.
        """

    @abc.abstractmethod
    async def get_status(self, execution_id: str) -> ExecutionResult:
        """Return the current ExecutionResult for the given execution_id."""

    @abc.abstractmethod
    async def cancel(self, execution_id: str) -> ExecutionResult:
        """
        Request cancellation of a running or queued execution.

        Returns the updated ExecutionResult (status may be CANCELLED or
        RUNNING if cancellation is asynchronous).
        """
