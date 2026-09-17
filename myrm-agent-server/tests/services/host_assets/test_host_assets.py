"""Unit tests for Host Asset Vault, SSH Ops Bridge, and SFTP Bridge.

[INPUT]
- app.services.host_assets.*

[OUTPUT]
- Pytest test cases

[POS]
Unit tests in myrm-agent/myrm-agent-server/tests/services/host_assets/test_host_assets.py.
"""

from __future__ import annotations

import pytest

from app.services.host_assets import (
    HostAssetConfig,
    HostAssetVault,
    HostAuthType,
    SFTPBridge,
    SFTPReadRequest,
    SFTPWriteRequest,
    SSHCommandRequest,
    SSHOpsBridge,
)


def test_host_asset_vault_crud() -> None:
    vault = HostAssetVault()
    host = HostAssetConfig(
        host_id="gpu-node-1",
        name="Main GPU Server",
        hostname="192.168.1.100",
        port=2222,
        username="developer",
        auth_type=HostAuthType.PASSWORD,
        password="super_secret_password",
        description="Main GPU Server",
    )
    registered = vault.register_host(host)
    assert registered.host_id == "gpu-node-1"
    assert registered.auth_type == HostAuthType.PASSWORD
    assert registered.password == "super_secret_password"

    # Fetch by id
    fetched = vault.get_host("gpu-node-1")
    assert fetched is not None
    assert fetched.host_id == "gpu-node-1"
    assert fetched.name == "Main GPU Server"

    # List & Delete
    assert len(vault.list_hosts()) == 1
    assert vault.remove_host("gpu-node-1") is True
    assert len(vault.list_hosts()) == 0


def test_ssh_config_import() -> None:
    vault = HostAssetVault()
    sample_ssh_config = """
    Host test-vm
        HostName 10.0.0.50
        User ubuntu
        Port 2200

    Host dev-cluster
        HostName 10.0.0.51
        User admin
    """
    res = vault.import_from_ssh_config(config_text=sample_ssh_config)
    assert res.total_parsed == 2
    assert res.total_imported == 2
    vm = vault.get_host("host_test_vm")
    assert vm is not None
    assert vm.port == 2200
    cluster = vault.get_host("host_dev_cluster")
    assert cluster is not None
    assert cluster.username == "admin"


@pytest.mark.asyncio
async def test_ssh_ops_bridge_security_and_execution() -> None:
    vault = HostAssetVault()
    vault.register_host(
        HostAssetConfig(
            host_id="prod-server",
            name="prod-server",
            hostname="1.2.3.4",
            username="root",
            auth_type=HostAuthType.PASSWORD,
            password="pwd",
        )
    )

    bridge = SSHOpsBridge(vault)

    # 1. Normal safe command with mock_runner
    async def mock_runner(host: HostAssetConfig, cmd: str, timeout: float) -> tuple[int, str, str]:
        return (0, "nvidia-smi utilization: 42%", "")

    req = SSHCommandRequest(
        host_id="prod-server",
        command="nvidia-smi --query-gpu=utilization.gpu --format=csv",
    )
    res = await bridge.execute_command(req, mock_runner=mock_runner)
    assert res.success is True
    assert "nvidia-smi" in res.stdout
    assert res.exit_code == 0

    # 2. Dangerous destructive command rejection
    dangerous_req = SSHCommandRequest(
        host_id="prod-server",
        command="rm -rf / --no-preserve-root",
    )
    res_danger = await bridge.execute_command(dangerous_req, mock_runner=mock_runner)
    assert res_danger.success is False
    assert res_danger.exit_code == 126
    assert "destructive" in res_danger.stderr.lower()


@pytest.mark.asyncio
async def test_sftp_bridge_read_and_write() -> None:
    vault = HostAssetVault()
    vault.register_host(
        HostAssetConfig(
            host_id="storage-node",
            name="storage-node",
            hostname="10.0.0.10",
            username="backup",
            auth_type=HostAuthType.AGENT_FORWARD,
        )
    )

    sftp = SFTPBridge(vault)

    # 1. Mock read
    async def mock_reader(host: HostAssetConfig, path: str, max_bytes: int) -> tuple[bool, str | None, int, str | None]:
        data = "log line 1\nlog line 2"
        return (True, data, len(data), None)

    read_res = await sftp.read_remote_file(
        SFTPReadRequest(host_id="storage-node", remote_path="/var/log/syslog"),
        mock_reader=mock_reader,
    )
    assert read_res.success is True
    assert read_res.content == "log line 1\nlog line 2"
    assert read_res.bytes_transferred > 0

    # 2. Mock write
    async def mock_writer(host: HostAssetConfig, path: str, content: str, mode: str) -> tuple[bool, int, str | None]:
        return (True, len(content), None)

    write_res = await sftp.write_remote_file(
        SFTPWriteRequest(
            host_id="storage-node",
            remote_path="/var/log/test.txt",
            content="hello world",
        ),
        mock_writer=mock_writer,
    )
    assert write_res.success is True
    assert write_res.bytes_transferred == 11
