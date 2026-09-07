"""Unit tests for Server Remote Host Asset Management Service."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.services.remote_host.manager import RemoteHostManager
from app.services.remote_host.models import RemoteHostConfig


def test_host_registration_and_listing() -> None:
    manager = RemoteHostManager()
    cfg = RemoteHostConfig(
        alias="prod-api",
        hostname="api.example.com",
        port=22,
        username="ubuntu",
        auth_type="agent",
        tags=["prod", "api"],
    )
    manager.register_host(cfg)

    retrieved = manager.get_host("prod-api")
    assert retrieved is not None
    assert retrieved.hostname == "api.example.com"
    assert retrieved.username == "ubuntu"

    summaries = manager.list_hosts()
    assert len(summaries) == 1
    assert summaries[0].alias == "prod-api"
    assert summaries[0].tags == ["prod", "api"]


def test_ssh_config_file_parsing() -> None:
    manager = RemoteHostManager()

    ssh_config_sample = """
Host gpu-node
    HostName 10.200.0.15
    User cuda
    Port 2200
    IdentityFile ~/.ssh/gpu_rsa

Host test-server
    HostName 10.200.0.16
    User testuser

Host *
    ServerAliveInterval 60
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write(ssh_config_sample)
        temp_path = f.name

    try:
        res = manager.import_from_ssh_config(config_path=temp_path)
        assert res.total_discovered == 2
        assert "gpu-node" in res.imported
        assert "test-server" in res.imported

        gpu = manager.get_host("gpu-node")
        assert gpu is not None
        assert gpu.hostname == "10.200.0.15"
        assert gpu.port == 2200
        assert gpu.username == "cuda"
        assert gpu.auth_type == "key"

        srv = manager.get_host("test-server")
        assert srv is not None
        assert srv.hostname == "10.200.0.16"
        assert srv.port == 22
        assert srv.auth_type == "agent"
    finally:
        Path(temp_path).unlink(missing_ok=True)
