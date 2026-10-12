"""Integration tests for Executable Capability Probing API endpoints.

[INPUT]
- HTTP requests to /api/v1/security/executable-probe/* endpoints.

[OUTPUT]
- Verified JSON responses for capable, incompatible, and broken probe classifications.

[POS]
- Server integration test suite for Claude-Mem #4167 shell-immune executable probing.
"""

from __future__ import annotations

import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.executable_probe_router import (
    get_executable_probe_service,
)
from app.api.security.executable_probe_router import (
    router as executable_probe_router,
)
from app.schemas.executable_probe import ExecutableProbeStatusDto
from app.services.security.executable_probe_service import (
    ExecutableProbeService,
)


@pytest.fixture(scope="function")
def isolated_service() -> ExecutableProbeService:
    """Fixture providing isolated service instance."""
    return ExecutableProbeService()


@pytest.fixture(scope="function")
def client(isolated_service: ExecutableProbeService) -> TestClient:
    """Fixture providing test client mounting executable_probe_router."""
    test_app = FastAPI(title="Executable Probe Test App")
    test_app.dependency_overrides[get_executable_probe_service] = (
        lambda: isolated_service
    )
    test_app.include_router(executable_probe_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_probe_capable_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/executable-probe/probe",
        json={
            "candidate_path": sys.executable,
            "capability_flags": ["--version"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == ExecutableProbeStatusDto.CAPABLE.value
    assert data["is_capable"] is True
    assert data["launch_failed"] is False
    assert "Python" in str(data["version"])


def test_probe_broken_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/executable-probe/probe",
        json={
            "candidate_path": "/invalid/bogus/executable/name",
            "capability_flags": ["--version"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == ExecutableProbeStatusDto.BROKEN.value
    assert data["is_capable"] is False
    assert data["launch_failed"] is True
