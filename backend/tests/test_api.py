"""
Pytest test suite for the Production IDE backend (MVP).

Run from the backend/ directory:
    pip install -r requirements.txt pytest pytest-anyio httpx
    pytest tests/

Or from the repo root:
    cd backend && pytest tests/
"""

import shutil
import sys

import pytest
from fastapi.testclient import TestClient

# Make sure the backend package root is on the path when running from repo root
sys.path.insert(0, __file__.rsplit("/tests", 1)[0])

from main import app  # noqa: E402

client = TestClient(app)

# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


def test_health_returns_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


# ---------------------------------------------------------------------------
# Python execution
# ---------------------------------------------------------------------------


def test_execute_python_hello_world():
    response = client.post(
        "/api/execute",
        json={"code": 'print("Hello, World!")', "language": "python"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "Hello, World!" in body["stdout"]
    assert body["exit_code"] == 0
    assert body["execution_time"] >= 0


def test_execute_python_stderr():
    response = client.post(
        "/api/execute",
        json={"code": "import sys; sys.stderr.write('err\\n')", "language": "python"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "err" in body["stderr"]


def test_execute_python_syntax_error():
    response = client.post(
        "/api/execute",
        json={"code": "def broken(:", "language": "python"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] != 0


# ---------------------------------------------------------------------------
# C execution (skip if gcc not available)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")
def test_execute_c_hello_world():
    code = r"""
#include <stdio.h>
int main() {
    printf("Hello from C\n");
    return 0;
}
"""
    response = client.post(
        "/api/execute",
        json={"code": code, "language": "c"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "Hello from C" in body["stdout"]
    assert body["exit_code"] == 0


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")
def test_execute_c_compile_error():
    code = "int main() { bad syntax }"
    response = client.post(
        "/api/execute",
        json={"code": code, "language": "c"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] != 0


# ---------------------------------------------------------------------------
# C++ execution (skip if g++ not available)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not installed")
def test_execute_cpp_hello_world():
    code = r"""
#include <iostream>
int main() {
    std::cout << "Hello from C++" << std::endl;
    return 0;
}
"""
    response = client.post(
        "/api/execute",
        json={"code": code, "language": "cpp"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "Hello from C++" in body["stdout"]
    assert body["exit_code"] == 0


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not installed")
def test_execute_cpp_compile_error():
    code = "int main() { bad syntax }"
    response = client.post(
        "/api/execute",
        json={"code": code, "language": "cpp"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] != 0


# ---------------------------------------------------------------------------
# Timeout test
# ---------------------------------------------------------------------------


def test_execute_python_timeout():
    response = client.post(
        "/api/execute",
        json={
            "code": "import time; time.sleep(60)",
            "language": "python",
            "timeout": 2,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] == 124
    assert "timed out" in (body.get("error") or "").lower()


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_execute_unsupported_language():
    response = client.post(
        "/api/execute",
        json={"code": "print(1)", "language": "ruby"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] == 1
    assert "Unsupported" in (body.get("error") or "")


def test_execute_code_too_long():
    response = client.post(
        "/api/execute",
        json={"code": "x" * 60_000, "language": "python"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] == 1
    assert "exceeds" in (body.get("error") or "").lower()


def test_execute_timeout_capped():
    """Verify that a requested timeout above MAX_TIMEOUT is silently capped."""
    response = client.post(
        "/api/execute",
        json={
            "code": "import time; time.sleep(5)",
            "language": "python",
            "timeout": 9999,  # above MAX_TIMEOUT (30)
        },
    )
    # We only verify the response is well-formed; the code sleeps 5s which is
    # under the capped limit of 30s, so it should finish normally.
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] == 0
