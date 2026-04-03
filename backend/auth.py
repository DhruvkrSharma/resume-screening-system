"""
Simple API-key bearer-token middleware.

Configure the token via the API_TOKEN environment variable.
If API_TOKEN is not set, auth is disabled (useful for local dev / tests).
"""
from __future__ import annotations

import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Paths that do not require authentication
_PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validate Bearer token for non-public endpoints."""

    async def dispatch(self, request: Request, call_next):
        api_token = os.getenv("API_TOKEN", "")

        # Auth disabled when no token is configured
        if not api_token:
            return await call_next(request)

        # WebSocket upgrades carry the token as a query param
        if request.url.path.startswith("/ws"):
            token = request.query_params.get("token", "")
            if token != api_token:
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
            return await call_next(request)

        # Public paths bypass auth
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        token = auth_header[len("Bearer "):]
        if token != api_token:
            logger.warning("auth_failed path=%s", request.url.path)
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

        return await call_next(request)
