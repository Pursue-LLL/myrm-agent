"""Unit tests for Multi-Host SSH Operations, SFTP Explorer, and Agent Asset Bridge."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from app.services.ssh_bridge import (
    HostAuthMethod,
    SFTPItemInfo,
    SFTPManager,
    SSHAgentBridge,
    SSHConfigImporter,
    SSHConnectionPool,
    SSHExecResult,
    SSHHostAsset,
    SSHHostVault,
)


@pytest.fixture
def temp_vault_file(tmp_path: Path) -> Path:
    return tmp_path / "ssh_hosts_test.json"


@pytest.fixture
def sample_host() -> SSHHostAsset:
    return SSHHostAsset(
        host_id="host_gpu_1",
        alias="gpu-node",
        hostname="192.168.1.100",
        port=22,
        username="ubuntu",
        auth_method=HostAuthMethod.KEY_FILE,
        key_path="~/.ssh/id_rsa",
        tags=["gpu", "ml"],
        description="Primary ML Training Node",
        is_trusted=False,
    )


def test_ssh_host_vault_crud(temp_vault_file: Path, sample_host: SSHHostAsset) -> None:
    vault = SSHHostVault(storage_path=temp_vault_file)
    assert len(vault.list_hosts()) == 0

    # Register host
    vault.register_host(sample_host)
    assert len(vault.list_hosts()) == 1

    # Query by ID
    h = vault.get_host("host_gpu_1")
    assert h is not None
    assert h.alias == "gpu-node"

    # Query by alias or hostname
    found_alias = vault.find_by_alias_or_hostname("gpu-node")
    assert found_alias is not None
    assert found_alias.host_id == "host_gpu_1"

    found_ip = vault.find_by_alias_or_hostname("192.168.1.100")
    assert found_ip is not None
    assert found_ip.host_id == "host_gpu_1"

    # Filter by tag
    ml_hosts = vault.list_hosts(tag="ml")
    assert len(ml_hosts) == 1
    web_hosts = vault.list_hosts(tag="web")
    assert len(web_hosts) == 0

    # Persistence verification
    new_vault = SSHHostVault(storage_path=temp_vault_file)
    assert len(new_vault.list_hosts()) == 1

    # Delete
    deleted = vault.delete_host("host_gpu_1")
    assert deleted is True
    assert len(vault.list_hosts()) == 0


def test_ssh_config_importer_text_parsing() -> None:
    sample_config = """
    # Global default
    Host *
        ServerAliveInterval 60

    Host dev-bastion
        HostName bastion.internal.net
        User ops_admin
        Port 2222
        IdentityFile ~/.ssh/id_bastion

    Host ai-runner
        HostName 10.0.4.12
        User root
    """
    hosts = SSHConfigImporter.parse_config_text(sample_config)
    assert len(hosts) == 2

    bastion = next((h for h in hosts if h.alias == "dev-bastion"), None)
    assert bastion is not None
    assert bastion.hostname == "bastion.internal.net"
    assert bastion.port == 2222
    assert bastion.username == "ops_admin"
    assert bastion.auth_method == HostAuthMethod.KEY_FILE

    runner = next((h for h in hosts if h.alias == "ai-runner"), None)
    assert runner is not None
    assert runner.hostname == "10.0.4.12"
    assert runner.port == 22
    assert runner.username == "root"


@pytest.mark.asyncio
async def test_ssh_pool_and_health_probe(sample_host: SSHHostAsset) -> None:
    pool = SSHConnectionPool()

    # Mock execution driver
    def mock_driver(host: SSHHostAsset, cmd: str) -> SSHExecResult:
        if cmd == "nvidia-smi":
            return SSHExecResult(
                host_id=host.host_id,
                command=cmd,
                exit_code=0,
                stdout="NVIDIA-SMI 535.129.03  Driver Version: 535.129.03  CUDA Version: 12.2\nGPU 0: NVIDIA A100-SXM4-80GB",
                stderr="",
            )
        return SSHExecResult(host_id=host.host_id, command=cmd, exit_code=0, stdout="ok", stderr="")

    pool.set_mock_driver(mock_driver)

    # Test health probe
    status = await pool.probe_host_health(sample_host)
    assert status.is_online is True
    assert status.latency_ms is not None
    assert status.latency_ms > 0

    # Test command execution
    res = await pool.execute_command(sample_host, "nvidia-smi")
    assert res.exit_code == 0
    assert "NVIDIA A100" in res.stdout


@pytest.mark.asyncio
async def test_sftp_manager_directory_listing(sample_host: SSHHostAsset) -> None:
    pool = SSHConnectionPool()

    # Mock `ls -la` response
    ls_output = (
        "total 64\n"
        "drwxr-xr-x 5 root root 4096 1725732100 .\n"
        "drwxr-xr-x 3 root root 4096 1725732000 ..\n"
        "drwxr-xr-x 2 root root 4096 1725732100 models\n"
        "-rw-r--r-- 1 root root 1048576 1725732200 weights.bin\n"
        "-rwxr-xr-x 1 root root 512 1725732300 train.sh\n"
    )

    def mock_driver(host: SSHHostAsset, cmd: str) -> SSHExecResult:
        if "ls -la" in cmd:
            return SSHExecResult(host_id=host.host_id, command=cmd, exit_code=0, stdout=ls_output, stderr="")
        if "tail -n" in cmd:
            return SSHExecResult(host_id=host.host_id, command=cmd, exit_code=0, stdout="epoch 10 loss: 0.012\n", stderr="")
        return SSHExecResult(host_id=host.host_id, command=cmd, exit_code=1, stdout="", stderr="unknown")

    pool.set_mock_driver(mock_driver)
    sftp = SFTPManager(pool)

    items = await sftp.list_directory(sample_host, "/workspace")
    assert len(items) == 3
    assert any(i.filename == "models" and i.is_dir for i in items)
    assert any(i.filename == "weights.bin" and not i.is_dir and i.size_bytes == 1048576 for i in items)

    # Test file read
    tail_content = await sftp.read_remote_file_tail(sample_host, "/workspace/log.txt", lines=5)
    assert "epoch 10 loss" in tail_content


@pytest.mark.asyncio
async def test_agent_bridge_safety_and_distillation(temp_vault_file: Path, sample_host: SSHHostAsset) -> None:
    vault = SSHHostVault(storage_path=temp_vault_file)
    vault.register_host(sample_host)

    pool = SSHConnectionPool()

    def mock_driver(host: SSHHostAsset, cmd: str) -> SSHExecResult:
        # Generate noisy log with error
        noisy_output = (
            "[ 10% ] downloading weights...\n"
            "[ 50% ] downloading weights...\n"
            "HTTP 403 Forbidden: access to checkpoint denied\n"
            "Traceback (most recent call last):\n"
            "  File 'train.py', line 45, in <module>\n"
            "    raise PermissionError('Access denied')\n"
            "PermissionError: Access denied\n"
        )
        return SSHExecResult(host_id=host.host_id, command=cmd, exit_code=1, stdout=noisy_output, stderr="")

    pool.set_mock_driver(mock_driver)
    sftp = SFTPManager(pool)
    bridge = SSHAgentBridge(vault=vault, pool=pool, sftp=sftp)

    # 1. Test safety gate on untrusted host
    blocked_res = await bridge.execute_remote_tool("gpu-node", "rm -rf /data/checkpoints")
    assert blocked_res.exit_code == 126
    assert "Execution blocked by safety policy" in blocked_res.stderr

    # 2. Test safe execution + log distillation
    run_res = await bridge.execute_remote_tool("gpu-node", "python3 train.py")
    assert run_res.exit_code == 1
    assert run_res.distilled_summary is not None
    assert "HTTP_403_FORBIDDEN" in run_res.distilled_summary or "Traceback" in run_res.distilled_summary

    # 3. Test list remote files tool
    files_result = await bridge.list_remote_files_tool("gpu-node", "/workspace")
    assert files_result.get("host_id") == "host_gpu_1"
    assert "items" in files_result
