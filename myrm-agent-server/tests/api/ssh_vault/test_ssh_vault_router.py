"""API integration tests for SSH Vault routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.ssh_vault.router import router as ssh_vault_router
from app.services.ssh_vault.models import (
    SSHCommandResult,
    SSHHostConfig,
    SSHProbeResult,
)
from app.services.ssh_vault.service import SSHAssetService


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(ssh_vault_router, prefix="/api/v1")
    return test_app


@pytest.fixture
def mock_service() -> SSHAssetService:
    service = SSHAssetService()
    service.register_host(
        SSHHostConfig(
            host_alias="prod-node-01",
            hostname="10.0.0.1",
            user="root",
            port=22,
            is_read_only=True,
            environment_tier="production",
            require_confirm_on_write=True,
        )
    )
    return service


@pytest.mark.asyncio
async def test_get_summary_success(app: FastAPI, mock_service: SSHAssetService) -> None:
    with patch("app.api.ssh_vault.router.get_ssh_asset_service", return_value=mock_service):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/ssh-vault/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_hosts"] >= 1
            assert any(h["host_alias"] == "prod-node-01" for h in data["hosts"])


@pytest.mark.asyncio
async def test_get_summary_failure_returns_500(app: FastAPI, mock_service: SSHAssetService) -> None:
    mock_service.get_summary = MagicMock(side_effect=RuntimeError("DB unreachable"))  # type: ignore[method-assign]
    with patch(
        "app.api.ssh_vault.router.get_ssh_asset_service",
        return_value=mock_service,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/ssh-vault/summary")
            assert resp.status_code == 500


@pytest.mark.asyncio
async def test_probe_host_success(app: FastAPI, mock_service: SSHAssetService) -> None:
    mock_service.probe_host = AsyncMock(  # type: ignore[method-assign]
        return_value=SSHProbeResult(
            host_alias="prod-node-01",
            is_reachable=True,
            latency_ms=12.5,
        )
    )
    with patch("app.api.ssh_vault.router.get_ssh_asset_service", return_value=mock_service):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/ssh-vault/probe/prod-node-01?timeout=2.0")
            assert resp.status_code == 200
            data = resp.json()
            assert data["is_reachable"] is True
            assert data["latency_ms"] == 12.5


@pytest.mark.asyncio
async def test_probe_host_failure_returns_500(app: FastAPI, mock_service: SSHAssetService) -> None:
    mock_service.probe_host = AsyncMock(side_effect=RuntimeError("Socket error"))  # type: ignore[method-assign]
    with patch("app.api.ssh_vault.router.get_ssh_asset_service", return_value=mock_service):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/ssh-vault/probe/prod-node-01")
            assert resp.status_code == 500


@pytest.mark.asyncio
async def test_execute_ssh_command_success(app: FastAPI, mock_service: SSHAssetService) -> None:
    mock_service.execute_remote_command = AsyncMock(  # type: ignore[method-assign]
        return_value=SSHCommandResult(
            host_alias="prod-node-01",
            command="uptime",
            exit_code=0,
            stdout="load average: 0.05",
            stderr="",
        )
    )
    with patch("app.api.ssh_vault.router.get_ssh_asset_service", return_value=mock_service):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/ssh-vault/execute",
                json={"host_alias": "prod-node-01", "command": "uptime"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["exit_code"] == 0
            assert "load average" in data["stdout"]


@pytest.mark.asyncio
async def test_execute_ssh_command_error_returns_500(
    app: FastAPI, mock_service: SSHAssetService
) -> None:
    mock_service.execute_remote_command = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("Subprocess failed")
    )
    with patch("app.api.ssh_vault.router.get_ssh_asset_service", return_value=mock_service):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/ssh-vault/execute",
                json={"host_alias": "prod-node-01", "command": "uptime"},
            )
            assert resp.status_code == 500


@pytest.mark.asyncio
async def test_request_break_glass_token_success(
    app: FastAPI, mock_service: SSHAssetService
) -> None:
    with patch("app.api.ssh_vault.router.get_ssh_asset_service", return_value=mock_service):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/ssh-vault/break-glass/request",
                json={
                    "host_alias": "prod-node-01",
                    "command": "systemctl restart nginx",
                    "reason": "Emergency fix for outage",
                    "ttl_seconds": 300,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "token" in data
            assert data["host_alias"] == "prod-node-01"
            assert data["reason"] == "Emergency fix for outage"


@pytest.mark.asyncio
async def test_request_break_glass_token_host_not_found(
    app: FastAPI, mock_service: SSHAssetService
) -> None:
    with patch("app.api.ssh_vault.router.get_ssh_asset_service", return_value=mock_service):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/ssh-vault/break-glass/request",
                json={
                    "host_alias": "unknown-host",
                    "command": "echo test",
                    "reason": "Testing",
                },
            )
            assert resp.status_code == 404


@pytest.mark.asyncio
async def test_request_break_glass_token_exception_returns_500(
    app: FastAPI, mock_service: SSHAssetService
) -> None:
    mock_service.change_window.issue_break_glass_token = MagicMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("Token generation failed")
    )
    with patch("app.api.ssh_vault.router.get_ssh_asset_service", return_value=mock_service):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/ssh-vault/break-glass/request",
                json={
                    "host_alias": "prod-node-01",
                    "command": "echo test",
                    "reason": "Testing",
                },
            )
            assert resp.status_code == 500


@pytest.mark.asyncio
async def test_update_host_policy_success(
    app: FastAPI, mock_service: SSHAssetService
) -> None:
    with patch("app.api.ssh_vault.router.get_ssh_asset_service", return_value=mock_service):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.patch(
                "/api/v1/ssh-vault/host/prod-node-01/policy",
                json={
                    "is_read_only": False,
                    "environment_tier": "staging",
                    "require_confirm_on_write": False,
                },
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

            host = mock_service.get_host("prod-node-01")
            assert host is not None
            assert host.is_read_only is False
            assert host.environment_tier == "staging"


@pytest.mark.asyncio
async def test_update_host_policy_host_not_found(
    app: FastAPI, mock_service: SSHAssetService
) -> None:
    with patch("app.api.ssh_vault.router.get_ssh_asset_service", return_value=mock_service):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.patch(
                "/api/v1/ssh-vault/host/non-existent/policy",
                json={"is_read_only": False},
            )
            assert resp.status_code == 404
