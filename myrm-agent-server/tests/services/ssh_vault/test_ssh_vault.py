"""Unit tests for SSHAssetService and SSH configuration discovery.

Verifies ~/.ssh/config parsing, alias matching, and network reachability probing.

[INPUT]
- app.services.ssh_vault.models::SSHHostConfig, SSHProbeResult, SSHAssetSummary
- app.services.ssh_vault.service::SSHAssetService
- pytest, unittest.mock, pathlib::Path

[OUTPUT]
- Test cases for SSH Asset Vault service.

[POS]
Unit tests in myrm-agent/myrm-agent-server/tests/services/ssh_vault/.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from app.services.ssh_vault.service import SSHAssetService

SAMPLE_SSH_CONFIG = """
# Developer Bastion
Host bastion
    HostName 1.2.3.4
    Port 2222
    User devops
    IdentityFile ~/.ssh/bastion_rsa

# GPU Node
Host gpu-cluster
    HostName 10.0.0.88
    Port 22
    User ubuntu
    IdentityFile ~/.ssh/id_ed25519

Host *
    ServerAliveInterval 60
"""


def test_parse_ssh_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config"
    config_file.write_text(SAMPLE_SSH_CONFIG, encoding="utf-8")

    service = SSHAssetService(config_path=config_file)
    hosts = service.parse_ssh_config()

    assert len(hosts) == 2

    bastion = service.get_host("bastion")
    assert bastion is not None
    assert bastion.hostname == "1.2.3.4"
    assert bastion.port == 2222
    assert bastion.user == "devops"
    assert bastion.identity_file is not None

    gpu = service.get_host("gpu-cluster")
    assert gpu is not None
    assert gpu.hostname == "10.0.0.88"
    assert gpu.port == 22
    assert gpu.user == "ubuntu"

    summary = service.get_summary()
    assert summary.total_hosts == 2


@pytest.mark.asyncio
async def test_probe_host(tmp_path: Path) -> None:
    config_file = tmp_path / "config"
    config_file.write_text(SAMPLE_SSH_CONFIG, encoding="utf-8")

    service = SSHAssetService(config_path=config_file)

    # 1. Non-existent host
    res = await service.probe_host("non-existent")
    assert not res.is_reachable
    assert "not found" in (res.error_message or "")

    # 2. Mock reachable socket
    with patch("socket.create_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = None
        res_ok = await service.probe_host("bastion")
        assert res_ok.is_reachable
        assert res_ok.latency_ms is not None
        assert res_ok.latency_ms >= 0
