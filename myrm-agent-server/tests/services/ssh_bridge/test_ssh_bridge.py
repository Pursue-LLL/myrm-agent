"""Unit tests for Multi-Host SSH Operations, SFTP Explorer, and Agent Asset Bridge.

[INPUT]
- pytest
- app.services.ssh_bridge::*

[OUTPUT]
- Test cases covering OpenSSH parser, asset manager, bridge executor, SFTP engine, and agent bridge distillation.

[POS]
Unit tests in tests/services/ssh_bridge/.
"""

from __future__ import annotations

import pytest

from app.services.ssh_bridge import (
    OpenSSHConfigParser,
    SFTPBridgeEngine,
    SSHAgentBridge,
    SSHAssetManager,
    SSHAuthMethod,
    SSHBridgeExecutor,
    SSHHostAsset,
)


@pytest.fixture
def asset_manager() -> SSHAssetManager:
    manager = SSHAssetManager()
    host = SSHHostAsset(
        asset_id="asset_gpu_01",
        alias="gpu-node-01",
        host_name="192.168.1.100",
        port=2222,
        user="ubuntu",
        auth_method=SSHAuthMethod.KEY_FILE,
        identity_file_path="~/.ssh/id_ed25519",
        tags=("gpu", "training"),
        description="Primary GPU node for deep learning",
    )
    manager.register_asset(host)
    return manager


def test_ssh_config_parser() -> None:
    sample_config = """
    # Developer test config
    Host bastion-jump
        HostName 10.0.0.1
        User admin
        Port 2200
        IdentityFile ~/.ssh/bastion_rsa

    Host worker-a worker-b
        HostName 10.0.0.50
        User deploy
        Port 22

    Host *
        ServerAliveInterval 60
    """
    hosts = OpenSSHConfigParser.parse_text(sample_config)
    assert len(hosts) == 3

    bastion = next(h for h in hosts if h.pattern == "bastion-jump")
    assert bastion.host_name == "10.0.0.1"
    assert bastion.user == "admin"
    assert bastion.port == 2200

    workers = [h for h in hosts if h.pattern in ("worker-a", "worker-b")]
    assert len(workers) == 2


def test_asset_manager_crud_and_import(asset_manager: SSHAssetManager) -> None:
    # 1. Retrieve registered host
    asset = asset_manager.get_by_alias("gpu-node-01")
    assert asset is not None
    assert asset.asset_id == "asset_gpu_01"

    # 2. Duplicate alias rejection
    dup = SSHHostAsset(
        asset_id="asset_dup",
        alias="gpu-node-01",
        host_name="10.0.0.2",
    )
    with pytest.raises(ValueError, match="already registered"):
        asset_manager.register_asset(dup)

    # 3. List by tag
    gpu_list = asset_manager.list_assets(tag="gpu")
    assert len(gpu_list) == 1
    assert len(asset_manager.list_assets(tag="non_existent")) == 0

    # 4. Import from config text
    imported_assets = asset_manager.import_from_ssh_config("""
    Host imported-box
        HostName 10.20.30.40
        User appuser
    """)
    assert len(imported_assets) == 1
    assert asset_manager.get_by_alias("imported-box") is not None

    # 5. Delete asset
    assert asset_manager.delete_asset("gpu-node-01") is True
    assert asset_manager.get_by_alias("gpu-node-01") is None


def test_executor_simulation_and_destructive_gate(asset_manager: SSHAssetManager) -> None:
    executor = SSHBridgeExecutor(asset_manager)

    # 1. Diagnostic simulated command
    uname_res = executor.execute_command("gpu-node-01", "uname -a")
    assert uname_res.exit_code == 0
    assert "Linux" in uname_res.stdout
    assert uname_res.is_blocked is False

    # 2. NVIDIA SMI simulated diagnostic
    gpu_res = executor.execute_command("gpu-node-01", "nvidia-smi")
    assert gpu_res.exit_code == 0
    assert "NVIDIA A100" in gpu_res.stdout

    # 3. High-risk destructive command gate
    blocked_res = executor.execute_command("gpu-node-01", "rm -rf /")
    assert blocked_res.is_blocked is True
    assert blocked_res.exit_code == 126
    assert "Security Gate Blocked" in blocked_res.stderr

    # 4. Host not found
    nf_res = executor.execute_command("unknown-alias", "ls -la")
    assert nf_res.is_blocked is True
    assert nf_res.exit_code == 127


def test_sftp_bridge_engine(asset_manager: SSHAssetManager) -> None:
    sftp = SFTPBridgeEngine(asset_manager)

    # 1. List directory
    items = sftp.list_directory("gpu-node-01", "/var/log")
    assert len(items) == 3
    names = [it.filename for it in items]
    assert "app.log" in names

    # 2. Transfer file
    result = sftp.transfer_file(
        host_alias="gpu-node-01",
        direction="upload",
        local_path="/tmp/test.txt",
        remote_path="/var/log/test.txt",
        content_override=b"hello sftp world",
    )
    assert result.success is True
    assert result.bytes_transferred == len(b"hello sftp world")
    assert result.sha256_checksum is not None


def test_agent_bridge_facade_and_distillation(asset_manager: SSHAssetManager) -> None:
    bridge = SSHAgentBridge(asset_manager)

    # 1. Command with distillation
    res, distilled = bridge.execute_remote("gpu-node-01", "df -h")
    assert res.exit_code == 0
    assert "Filesystem" in distilled

    # 2. Remote file listing
    files = bridge.list_remote_files("gpu-node-01", "/home/ubuntu")
    assert len(files) > 0

    # 3. Summary query
    meta = bridge.get_host_summary("gpu-node-01")
    assert meta is not None
    assert meta.host_name == "192.168.1.100"
