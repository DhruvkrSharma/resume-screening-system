"""
Shared pytest fixtures for the Production IDE backend tests.
"""

import sys

import pytest
from fastapi.testclient import TestClient

# Ensure the backend package root is importable regardless of where pytest runs
sys.path.insert(0, __file__.rsplit("/tests", 1)[0])

from main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    """Return a synchronous TestClient for the FastAPI app."""
    return TestClient(app)
