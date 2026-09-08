"""Unit tests for SSH Vault and Host Discovery Service.

[INPUT]
- pytest, asyncio, pathlib::Path
- app.services.ssh_vault::SSHAssetService, SSHHostConfig, SSHProbeResult, SSHAssetSummary

[OUTPUT]
- TestSSHAssetService: Test cases for ssh config parsing, caching, and probing.

[POS]
Unit tests in tests/services/ssh_vault/.
"""

from __future__ import annotations

import pytest

from app.services.ssh_vault.models import SSHHostConfig
from app.services.ssh_vault.service import SSHAssetService

SAMPLE_SSH_CONFIG = """
# Test SSH Config
Host gpu-node-01
    HostName 192.168.1.100
    User ubuntu
    Port 2222
    IdentityFile ~/.ssh/id_ed25519

Host prod-api-01 prod-api-02
    HostName 10.0.0.50
    User deploy
    Port 22

Host *
    ServerAliveInterval 60
"""


def test_parse_ssh_config_text_content() -> None:
    service = SSHAssetService()
    hosts = service.parse_ssh_config(text_content=SAMPLE_SSH_CONFIG)

    assert len(hosts) == 2
    gpu_host = next(h for h in hosts if h.host_alias == "gpu-node-01")
    assert gpu_host.hostname == "192.168.1.100"
    assert gpu_host.user == "ubuntu"
    assert gpu_host.port == 2222
    assert "id_ed25519" in str(gpu_host.identity_file)

    prod_host = next(h for h in hosts if h.host_alias == "prod-api-01")
    assert prod_host.hostname == "10.0.0.50"
    assert prod_host.user == "deploy"
    assert prod_host.port == 22


def test_get_host_and_summary() -> None:
    service = SSHAssetService()
    service.parse_ssh_config(text_content=SAMPLE_SSH_CONFIG)

    host = service.get_host("gpu-node-01")
    assert host is not None
    assert host.host_alias == "gpu-node-01"

    non_exist = service.get_host("non-existent-alias")
    assert non_exist is None

    summary = service.get_summary()
    assert summary.total_hosts == 2
    assert len(summary.hosts) == 2


@pytest.mark.asyncio
async def test_probe_host_not_found() -> None:
    service = SSHAssetService()
    service.parse_ssh_config(text_content=SAMPLE_SSH_CONFIG)

    result = await service.probe_host("unknown-host", timeout_seconds=0.5)
    assert not result.is_reachable
    assert "not found" in (result.error_message or "")


@pytest.mark.asyncio
async def test_probe_host_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    service = SSHAssetService()
    service.parse_ssh_config(text_content=SAMPLE_SSH_CONFIG)

    service._hosts_cache["unreachable-test"] = SSHHostConfig(
        host_alias="unreachable-test",
        hostname="192.0.2.1",
        port=59999,
        user="test",
    )

    def mock_create_connection(*args: object, **kwargs: object) -> None:
        raise socket.timeout("Timed out")

    monkeypatch.setattr(socket, "create_connection", mock_create_connection)

    result = await service.probe_host("unreachable-test", timeout_seconds=0.5)
    assert not result.is_reachable
    assert result.error_message is not None
