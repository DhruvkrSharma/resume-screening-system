"""
Pydantic models for request/response bodies.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    metadata: Optional[dict] = Field(default_factory=dict)


class CreateSessionResponse(BaseModel):
    session_id: str
    provider: str
    created_at: str


class ExecuteRequest(BaseModel):
    session_id: str
    code: str
    metadata: Optional[dict] = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    execution_id: str
    session_id: str
    status: str


class StatusResponse(BaseModel):
    execution_id: str
    session_id: str
    status: str
    output: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class CancelResponse(BaseModel):
    execution_id: str
    status: str


class HealthResponse(BaseModel):
    status: str
    provider: str
    version: str = "1.0.0"
