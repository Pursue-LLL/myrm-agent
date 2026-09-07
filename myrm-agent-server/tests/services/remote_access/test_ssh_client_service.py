"""Unit tests for SSH client service, host models, and ~/.ssh/config parser."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.remote_access.host_models import (
    RemoteHostConfig,
    SSHCommandExecutionResult,
    parse_ssh_config_text,
)
from app.services.remote_access.ssh_client_service import SSHRemoteClientService


def test_parse_ssh_config_text() -> None:
    sample_config = """
    # Sample SSH Config
    Host gpu-node-01
        HostName 192.168.1.50
        User ubuntu
        Port 2222
        IdentityFile ~/.ssh/id_ed25519

    Host prod-api
        HostName api.internal.corp
        User deploy

    Host *
        ServerAliveInterval 60
    """
    hosts = parse_ssh_config_text(sample_config)
    assert len(hosts) == 2

    h1 = next(h for h in hosts if h.alias == "gpu-node-01")
    assert h1.hostname == "192.168.1.50"
    assert h1.user == "ubuntu"
    assert h1.port == 2222
    assert h1.identity_file is not None and "id_ed25519" in h1.identity_file

    h2 = next(h for h in hosts if h.alias == "prod-api")
    assert h2.hostname == "api.internal.corp"
    assert h2.user == "deploy"
    assert h2.port == 22


def test_host_alias_validation() -> None:
    valid_host = RemoteHostConfig(alias="my-server_01.prod", hostname="10.0.0.1")
    assert valid_host.validate_alias() is True

    invalid_host = RemoteHostConfig(alias="host; rm -rf /", hostname="10.0.0.1")
    assert invalid_host.validate_alias() is False


@pytest.mark.asyncio
async def test_execute_unknown_host() -> None:
    service = SSHRemoteClientService()
    result = await service.execute_remote_command("non-existent-host", "uname -a")
    assert result.exit_code == 1
    assert "not found" in result.stderr


@pytest.mark.asyncio
async def test_execute_blocked_high_risk_command() -> None:
    service = SSHRemoteClientService()
    service.register_host(RemoteHostConfig(alias="test-box", hostname="127.0.0.1"))

    result = await service.execute_remote_command("test-box", "rm -rf /")
    assert result.is_blocked_high_risk is True
    assert result.exit_code == 126
    assert "blocked" in result.stderr.lower()


@pytest.mark.asyncio
async def test_execute_remote_command_mocked_success() -> None:
    service = SSHRemoteClientService()
    service.register_host(RemoteHostConfig(alias="test-box", hostname="127.0.0.1", port=22, user="test"))

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Linux test-box 5.15.0-generic\n", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await service.execute_remote_command("test-box", "uname -a")
        assert result.exit_code == 0
        assert "Linux test-box" in result.stdout
        assert result.is_timeout is False


@pytest.mark.asyncio
async def test_execute_remote_command_timeout() -> None:
    service = SSHRemoteClientService()
    service.register_host(RemoteHostConfig(alias="timeout-box", hostname="10.255.255.1"))

    mock_proc = AsyncMock()
    mock_proc.communicate.side_effect = asyncio.TimeoutError()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await service.execute_remote_command("timeout-box", "sleep 100", timeout_seconds=0.1)
        assert result.is_timeout is True
        assert result.exit_code == 124
        assert "timed out" in result.stderr.lower()
