"""Unit tests for host asset depot in app/remote_access/host_depot.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

from myrm_agent_harness.toolkits.ssh_remote.models import SSHAuthType

from app.remote_access.host_depot import HostAssetDepot


def test_host_depot_save_and_decrypt() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        depot = HostAssetDepot(base_dir=Path(tmpdir))

        rec = depot.save_host(
            host_id="test-node-1",
            hostname="192.168.1.50",
            port=22,
            username="admin",
            auth_type=SSHAuthType.PASSWORD,
            secret="MySuperSecretPass123!",
            tags=["gpu", "cluster-a"],
            description="Test GPU worker",
        )

        assert rec.host_id == "test-node-1"
        assert rec.hostname == "192.168.1.50"
        assert rec.encrypted_secret != "MySuperSecretPass123!"

        spec = depot.get_host_spec("test-node-1")
        assert spec is not None
        assert spec.password == "MySuperSecretPass123!"
        assert spec.username == "admin"
        assert spec.tags == ["gpu", "cluster-a"]


def test_host_depot_ssh_config_import() -> None:
    config_sample = """
    Host lab-server
        HostName 10.0.0.15
        Port 2200
        User devops
        ProxyJump bastion.company.com

    Host cloud-vm
        HostName vm.cloud.provider.com
        User root
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        depot = HostAssetDepot(base_dir=Path(tmpdir))
        imported = depot.import_from_ssh_config(config_sample)

        assert len(imported) == 2
        host_map = {h.host_id: h for h in imported}

        assert "lab-server" in host_map
        assert host_map["lab-server"].port == 2200
        assert host_map["lab-server"].username == "devops"
        assert host_map["lab-server"].proxy_jump == "bastion.company.com"

        assert "cloud-vm" in host_map
        assert host_map["cloud-vm"].username == "root"


def test_host_depot_delete() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        depot = HostAssetDepot(base_dir=Path(tmpdir))
        depot.save_host(host_id="temp-host", hostname="1.1.1.1")
        assert len(depot.list_hosts()) == 1

        deleted = depot.delete_host("temp-host")
        assert deleted is True
        assert len(depot.list_hosts()) == 0
