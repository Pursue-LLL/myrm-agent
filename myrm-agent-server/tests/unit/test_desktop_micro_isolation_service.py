"""Unit tests for DesktopMicroIsolationService."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.desktop_micro_isolation import (
    RouteToolExecutionRequest,
    SanitizeEnvironmentRequest,
)
from app.services.security.desktop_micro_isolation_service import (
    DesktopMicroIsolationService,
)


@pytest.fixture
def sample_service(tmp_path: Path) -> DesktopMicroIsolationService:
    workspace = tmp_path / "desktop_project"
    workspace.mkdir(parents=True, exist_ok=True)
    return DesktopMicroIsolationService(workspace_root=str(workspace), provider_available=True)


def test_sanitize_environment(sample_service: DesktopMicroIsolationService) -> None:
    host_env = {
        "OPENAI_API_KEY": "sk-secret-12345",
        "DATABASE_URL": "postgres://user:pwd@localhost:5432/db",
        "AWS_SECRET_ACCESS_KEY": "secret_key_abc",
        "USER": "developer",
        "PATH": "/usr/bin:/bin",
    }
    req = SanitizeEnvironmentRequest(host_env=host_env)
    res = sample_service.sanitize_env(req)

    assert "OPENAI_API_KEY" not in res.clean_env
    assert "DATABASE_URL" not in res.clean_env
    assert "AWS_SECRET_ACCESS_KEY" not in res.clean_env
    assert res.clean_env["USER"] == "developer"
    assert res.clean_env["PATH"] == "/usr/bin:/bin"
    assert "OPENAI_API_KEY" in res.stripped_keys
    assert "DATABASE_URL" in res.stripped_keys


def test_route_read_only_tool(sample_service: DesktopMicroIsolationService) -> None:
    req = RouteToolExecutionRequest(
        tool_name="read_file",
        arguments={"path": "README.md"},
        host_env={"ANTHROPIC_API_KEY": "sk-ant-123"},
    )
    res = sample_service.route_tool_execution(req)

    assert not res.is_blocked
    assert res.destination == "HOST_PROCESS"
    assert res.isolation_level == "MICRO_SANDBOX"
    assert "ANTHROPIC_API_KEY" in res.stripped_credential_keys


def test_route_dangerous_tool_to_micro_sandbox(sample_service: DesktopMicroIsolationService) -> None:
    req = RouteToolExecutionRequest(
        tool_name="bash",
        arguments={"command": "npm install"},
        host_env={"GITHUB_TOKEN": "ghp_123456789"},
    )
    res = sample_service.route_tool_execution(req)

    assert not res.is_blocked
    assert res.destination == "MICRO_ISOLATION_SANDBOX"
    assert res.isolation_level == "MICRO_SANDBOX"
    assert "GITHUB_TOKEN" in res.stripped_credential_keys


def test_fail_closed_contract_when_provider_unavailable(tmp_path: Path) -> None:
    workspace = tmp_path / "desktop_project"
    workspace.mkdir(parents=True, exist_ok=True)
    service = DesktopMicroIsolationService(workspace_root=str(workspace), provider_available=False)

    # 1. Dangerous tool without override is blocked
    req = RouteToolExecutionRequest(
        tool_name="python_exec",
        arguments={"code": "import os"},
        allow_unisolated_override=False,
    )
    res = service.route_tool_execution(req)
    assert res.is_blocked
    assert res.isolation_level == "FAIL_CLOSED_BLOCKED"
    assert res.error_message is not None
    assert "Fail-Closed" in res.error_message

    # 2. Dangerous tool with explicit override is allowed on host with override level
    req_override = RouteToolExecutionRequest(
        tool_name="python_exec",
        arguments={"code": "import os"},
        allow_unisolated_override=True,
    )
    res_override = service.route_tool_execution(req_override)
    assert not res_override.is_blocked
    assert res_override.destination == "HOST_PROCESS"
    assert res_override.isolation_level == "UNISOLATED_OVERRIDE"


def test_workspace_boundary_enforcement(sample_service: DesktopMicroIsolationService) -> None:
    # Attempting to access forbidden ~/.ssh directory
    req = RouteToolExecutionRequest(
        tool_name="file_write",
        arguments={"content": "malicious key"},
        target_path="/Users/developer/.ssh/id_rsa",
    )
    res = sample_service.route_tool_execution(req)
    assert res.is_blocked
    assert res.error_message is not None
    assert "forbidden system path" in res.error_message


def test_isolation_status_disclosure(sample_service: DesktopMicroIsolationService) -> None:
    status = sample_service.get_isolation_status()
    assert status.provider_available is True
    assert status.fail_closed_enforced is True
    assert "Micro-isolation sandbox is active" in status.disclosure_notice
