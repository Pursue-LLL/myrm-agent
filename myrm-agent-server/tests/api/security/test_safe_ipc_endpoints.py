"""Integration tests for Safe IPC Pipeline API endpoints."""

from __future__ import annotations

import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.ipc_router import router as ipc_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing dedicated test client mounting ipc_router."""
    test_app = FastAPI(title="Safe IPC Security Test App")
    test_app.include_router(ipc_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_dispatch_ipc_command_query_file_endpoint(client: TestClient) -> None:
    worker_script = (
        "import sys, pathlib; "
        "idx = sys.argv.index('--query-file'); "
        "content = pathlib.Path(sys.argv[idx + 1]).read_text(); "
        "print('API_RESULT:', content, end='')"
    )

    payload = {
        "command": [sys.executable, "-c", worker_script],
        "payload": "Message with $VAR and 'quotes' and \"double\"",
        "transport": "query_file",
        "timeout_seconds": 15.0,
    }

    resp = client.post("/api/v1/security/ipc/dispatch", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    assert data["returncode"] == 0
    assert data["stdout"] == f"API_RESULT: {payload['payload']}"
    assert data["duration_seconds"] >= 0.0


def test_dispatch_ipc_command_stdin_endpoint(client: TestClient) -> None:
    worker_script = "import sys; print('STDIN_API:', sys.stdin.read(), end='')"
    payload = {
        "command": [sys.executable, "-c", worker_script],
        "payload": "Direct stream line 1\nDirect stream line 2",
        "transport": "stdin_stream",
        "timeout_seconds": 15.0,
    }

    resp = client.post("/api/v1/security/ipc/dispatch", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    assert data["returncode"] == 0
    assert data["stdout"] == f"STDIN_API: {payload['payload']}"


def test_dispatch_ipc_command_rejected_endpoint(client: TestClient) -> None:
    payload = {
        "command": ["sh", "-c", "echo 'pwned'"],
        "payload": "malicious injection",
        "transport": "query_file",
    }

    resp = client.post("/api/v1/security/ipc/dispatch", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "rejected"
    assert data["returncode"] == -1
    assert "strictly forbidden" in data["stderr"]
