"""Unit tests for Host Asset Vault, Remote SSH Ops Bridge, and SFTP Bridge.

[INPUT]
- app.services.host_assets.*

[OUTPUT]
- Pytest test cases

[POS]
Unit tests in myrm-agent/myrm-agent-server/tests/services/host_assets/test_host_assets.py.
"""

from app.services.host_assets import (
    AuthType,
    HostAssetCreate,
    HostAssetVault,
    RemoteSSHOpsBridge,
    SFTPBridge,
    SFTPTransferRequest,
    SSHCommandRequest,
)


def test_host_asset_vault_encryption_and_crud() -> None:
    vault = HostAssetVault()
    create_payload = HostAssetCreate(
        alias="gpu-node-1",
        hostname="192.168.1.100",
        port=2222,
        username="developer",
        auth_type=AuthType.PASSWORD,
        description="Main GPU Server",
        password="super_secret_password",
    )
    asset = vault.create_asset(create_payload)
    assert asset.alias == "gpu-node-1"
    assert asset.has_password is True
    assert asset.has_private_key is False
    assert asset.encrypted_secret != ""

    # Decrypt verification
    secrets = vault.get_decrypted_secrets(asset.id)
    assert secrets.get("password") == "super_secret_password"

    # Fetch by alias
    fetched = vault.get_asset("gpu-node-1")
    assert fetched is not None
    assert fetched.id == asset.id

    # List & Delete
    assert len(vault.list_assets()) == 1
    assert vault.delete_asset("gpu-node-1") is True
    assert len(vault.list_assets()) == 0


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
    imported = vault.import_from_ssh_config_content(sample_ssh_config)
    assert len(imported) == 2
    assert imported[0].alias == "test-vm"
    assert imported[0].port == 2200
    assert imported[1].alias == "dev-cluster"
    assert imported[1].username == "admin"


def test_remote_ssh_ops_bridge_security_and_execution() -> None:
    vault = HostAssetVault()
    asset = vault.create_asset(
        HostAssetCreate(
            alias="prod-server",
            hostname="1.2.3.4",
            username="root",
            auth_type=AuthType.PASSWORD,
            password="pwd",
        )
    )

    bridge = RemoteSSHOpsBridge(vault)

    # 1. Normal safe command
    req = SSHCommandRequest(
        host_id_or_alias="prod-server",
        command="nvidia-smi --query-gpu=utilization.gpu --format=csv",
    )
    res = bridge.execute_command(req)
    assert res.success is True
    assert "Executed" in res.stdout
    assert res.exit_code == 0

    # 2. Dangerous destructive command rejection
    dangerous_req = SSHCommandRequest(
        host_id_or_alias="prod-server",
        command="rm -rf / --no-preserve-root",
    )
    res_danger = bridge.execute_command(dangerous_req)
    assert res_danger.success is False
    assert res_danger.exit_code == 126
    assert "destructive" in (res_danger.error_message or "")


def test_sftp_bridge_explorer_and_transfer() -> None:
    vault = HostAssetVault()
    vault.create_asset(
        HostAssetCreate(
            alias="storage-node",
            hostname="10.0.0.10",
            username="backup",
            auth_type=AuthType.AGENT,
        )
    )

    sftp = SFTPBridge(vault)

    # 1. Directory explorer
    entries = sftp.list_remote_directory("storage-node", "/var/log")
    assert len(entries) == 2
    assert entries[0].filename == "logs"
    assert entries[0].is_dir is True

    # 2. Transfer upload
    upload_res = sftp.transfer_file(
        SFTPTransferRequest(
            host_id_or_alias="storage-node",
            direction="upload",
            local_path="/tmp/test.txt",
            remote_path="/var/log/test.txt",
        )
    )
    assert upload_res.success is True
    assert upload_res.bytes_transferred > 0
