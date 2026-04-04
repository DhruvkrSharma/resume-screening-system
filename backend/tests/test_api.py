"""
Pytest test suite for the Production IDE backend (MVP).

Run from the backend/ directory:
    pip install -r requirements.txt pytest httpx
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

# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


def test_health_returns_ok(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


# ---------------------------------------------------------------------------
# Python execution
# ---------------------------------------------------------------------------


def test_execute_python_hello_world(client: TestClient):
    response = client.post(
        "/api/execute",
        json={"code": 'print("Hello, World!")', "language": "python"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "Hello, World!" in body["stdout"]
    assert body["exit_code"] == 0
    assert body["execution_time"] >= 0


def test_execute_python_stderr(client: TestClient):
    response = client.post(
        "/api/execute",
        json={"code": "import sys; sys.stderr.write('err\\n')", "language": "python"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "err" in body["stderr"]


def test_execute_python_syntax_error(client: TestClient):
    response = client.post(
        "/api/execute",
        json={"code": "def broken(:", "language": "python"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] != 0


def test_execute_python_stdin(client: TestClient):
    """stdin passed in the request is piped to the running program."""
    code = "name = input()\nprint(f'Hello, {name}!')"
    response = client.post(
        "/api/execute",
        json={"code": code, "language": "python", "stdin": "Alice"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "Hello, Alice!" in body["stdout"]
    assert body["exit_code"] == 0


def test_execute_python_truncated_flag(client: TestClient):
    """Output longer than MAX_OUTPUT_LENGTH sets truncated=True."""
    code = "print('x' * 20_000)"
    response = client.post(
        "/api/execute",
        json={"code": code, "language": "python"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is True
    # The returned stdout is capped at 10 000 chars
    assert len(body["stdout"]) == 10_000


def test_execute_python_not_truncated(client: TestClient):
    """Short output must NOT set truncated=True."""
    response = client.post(
        "/api/execute",
        json={"code": 'print("short")', "language": "python"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is False


def test_execute_python_memory_limit(client: TestClient):
    """A process that allocates memory far beyond the 256 MB limit must fail."""
    # Attempt to allocate ~2 GB; the process should be killed by the OS
    code = "data = bytearray(2 * 1024 * 1024 * 1024)"
    response = client.post(
        "/api/execute",
        json={"code": code, "language": "python", "timeout": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] != 0


# ---------------------------------------------------------------------------
# C execution (skip if gcc not available)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")
def test_execute_c_hello_world(client: TestClient):
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
def test_execute_c_compile_error(client: TestClient):
    code = "int main() { bad syntax }"
    response = client.post(
        "/api/execute",
        json={"code": code, "language": "c"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] != 0


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")
def test_execute_c_stdin(client: TestClient):
    """C programs can read from stdin when the field is provided."""
    code = r"""
#include <stdio.h>
int main() {
    char name[64];
    scanf("%63s", name);
    printf("Hello, %s!\n", name);
    return 0;
}
"""
    response = client.post(
        "/api/execute",
        json={"code": code, "language": "c", "stdin": "Bob"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "Hello, Bob!" in body["stdout"]
    assert body["exit_code"] == 0


# ---------------------------------------------------------------------------
# C++ execution (skip if g++ not available)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not installed")
def test_execute_cpp_hello_world(client: TestClient):
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
def test_execute_cpp_compile_error(client: TestClient):
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


def test_execute_python_timeout(client: TestClient):
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


def test_execute_unsupported_language(client: TestClient):
    response = client.post(
        "/api/execute",
        json={"code": "print(1)", "language": "ruby"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] == 1
    assert "Unsupported" in (body.get("error") or "")


def test_execute_code_too_long(client: TestClient):
    response = client.post(
        "/api/execute",
        json={"code": "x" * 60_000, "language": "python"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] == 1
    assert "exceeds" in (body.get("error") or "").lower()


def test_execute_timeout_capped(client: TestClient):
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

