"""Unit tests for Multi-Host SSH Operations, SFTP Explorer, and Agent Asset Bridge."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.services.ssh_bridge.agent_bridge import SSHAgentBridge
from app.services.ssh_bridge.config_importer import SSHConfigImporter
from app.services.ssh_bridge.models import (
    HostAuthMethod,
    SFTPItemInfo,
    SSHExecResult,
    SSHHostAsset,
)
from app.services.ssh_bridge.pool import SSHConnectionPool
from app.services.ssh_bridge.sftp_manager import SFTPManager
from app.services.ssh_bridge.vault import SSHHostVault


@pytest.fixture
def temp_vault() -> SSHHostVault:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    vault = SSHHostVault(storage_path=path)
    return vault


def test_vault_crud_and_lookup(temp_vault: SSHHostVault) -> None:
    host = SSHHostAsset(
        host_id="host_gpu_1",
        alias="gpu-box",
        hostname="192.168.1.100",
        port=22,
        username="ubuntu",
        auth_method=HostAuthMethod.KEY_FILE,
        key_path="~/.ssh/id_rsa",
        tags=["gpu", "ml"],
    )
    temp_vault.register_host(host)

    assert temp_vault.get_host("host_gpu_1") is not None
    assert len(temp_vault.list_hosts("gpu")) == 1
    assert temp_vault.find_by_alias_or_hostname("gpu-box") is not None
    assert temp_vault.find_by_alias_or_hostname("192.168.1.100") is not None

    temp_vault.delete_host("host_gpu_1")
    assert temp_vault.get_host("host_gpu_1") is None


def test_ssh_config_importer_parser() -> None:
    sample_config = """
    # Comments should be ignored
    Host my-dev-server
        HostName dev.internal.corp
        User devuser
        Port 2222
        IdentityFile ~/.ssh/dev_rsa

    Host prod-worker
        HostName 10.0.0.5
        User root
        Port 22
    """
    hosts = SSHConfigImporter.parse_config_text(sample_config)
    assert len(hosts) == 2

    dev_host = next(h for h in hosts if h.alias == "my-dev-server")
    assert dev_host.hostname == "dev.internal.corp"
    assert dev_host.username == "devuser"
    assert dev_host.port == 2222
    assert dev_host.key_path is not None

    prod_host = next(h for h in hosts if h.alias == "prod-worker")
    assert prod_host.hostname == "10.0.0.5"
    assert prod_host.username == "root"


@pytest.mark.asyncio
async def test_agent_bridge_execution_and_distillation(temp_vault: SSHHostVault) -> None:
    host = SSHHostAsset(
        host_id="host_test_node",
        alias="test-node",
        hostname="127.0.0.1",
        port=22,
        username="testuser",
        is_trusted=False,
    )
    temp_vault.register_host(host)

    pool = SSHConnectionPool()
    # Mock driver for remote execution simulation
    def mock_driver(target_host: SSHHostAsset, command: str) -> SSHExecResult:
        if "nvidia-smi" in command:
            stdout = "\n".join([f"Processing batch {i}..." for i in range(100)]) + "\nGPU 0: NVIDIA A100 80GB (Temp: 45C)"
            return SSHExecResult(host_id=target_host.host_id, command=command, exit_code=0, stdout=stdout)
        return SSHExecResult(host_id=target_host.host_id, command=command, exit_code=0, stdout="OK")

    pool.set_mock_driver(mock_driver)
    sftp = SFTPManager(pool)
    bridge = SSHAgentBridge(temp_vault, pool, sftp)

    # 1. Normal execution with log distillation
    result = await bridge.execute_remote("test-node", "nvidia-smi")
    assert result.exit_code == 0
    assert result.distilled_summary is not None
    assert "NVIDIA A100" in (result.distilled_summary or "")

    # 2. Dangerous command interception gate
    dangerous_res = await bridge.execute_remote("test-node", "rm -rf /var/log")
    assert dangerous_res.exit_code == 126
    assert "Security Gate Intercept" in dangerous_res.stderr


@pytest.mark.asyncio
async def test_sftp_directory_listing(temp_vault: SSHHostVault) -> None:
    host = SSHHostAsset(
        host_id="host_sftp",
        alias="sftp-node",
        hostname="10.0.0.1",
        port=22,
        username="ubuntu",
    )
    temp_vault.register_host(host)

    pool = SSHConnectionPool()
    sftp = SFTPManager(pool)
    
    def mock_lister(target_host: SSHHostAsset, path: str) -> list[SFTPItemInfo]:
        return [
            SFTPItemInfo(filename="app.log", path=f"{path}/app.log", is_dir=False, size_bytes=1024),
            SFTPItemInfo(filename="data", path=f"{path}/data", is_dir=True),
        ]
    
    sftp.set_mock_lister(mock_lister)
    bridge = SSHAgentBridge(temp_vault, pool, sftp)

    items, status = await bridge.list_remote_files("sftp-node", "/var/www")
    assert status == "OK"
    assert items is not None
    assert len(items) == 2
    assert items[0].filename == "app.log"
    assert items[1].is_dir is True
