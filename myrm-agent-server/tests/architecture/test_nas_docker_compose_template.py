"""Architecture contract test for NAS / HomeLab Docker Compose overlay template."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

_WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
_NAS_COMPOSE_PATH = _WORKSPACE_ROOT / "docker-compose.nas.yml"
_BASE_COMPOSE_PATH = _WORKSPACE_ROOT / "docker-compose.yml"


@pytest.mark.architecture
def test_nas_compose_overlay_file_exists() -> None:
    """Verify that docker-compose.nas.yml exists at workspace root."""
    assert _NAS_COMPOSE_PATH.is_file(), f"Expected {_NAS_COMPOSE_PATH} to exist"


@pytest.mark.architecture
def test_nas_compose_overlay_contract() -> None:
    """Validate NAS compose overlay YAML structure and persistence split contract."""
    assert _NAS_COMPOSE_PATH.is_file()
    raw_content: object = yaml.safe_load(_NAS_COMPOSE_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw_content, dict)

    services_raw = raw_content.get("services")
    assert isinstance(services_raw, dict)
    assert "myrm-server" in services_raw, "myrm-server service must be defined in nas overlay"
    assert "myrm-frontend" in services_raw, "myrm-frontend service must be defined in nas overlay"

    server_raw = services_raw["myrm-server"]
    assert isinstance(server_raw, dict)
    env_list: list[str] = [str(item) for item in server_raw.get("environment", []) if isinstance(item, str)]
    env_map = dict(item.split("=", 1) for item in env_list if "=" in item)

    assert env_map.get("MYRM_DATA_DIR") == "/state/data", "MYRM_DATA_DIR must map to /state/data"
    assert env_map.get("MEMORY_BASE_PATH") == "/state/memory", "MEMORY_BASE_PATH must map to /state/memory"
    assert env_map.get("EVENT_LOG_DIR") == "/state/logs", "EVENT_LOG_DIR must map to /state/logs"
    assert "OLLAMA_BASE_URL" in env_map, "OLLAMA_BASE_URL must be injected for host-side local model communication"
    assert "host.docker.internal:11434" in env_map["OLLAMA_BASE_URL"]

    volumes_mounted: list[str] = [str(item) for item in server_raw.get("volumes", []) if isinstance(item, str)]
    assert "myrm-nas-data:/state/data" in volumes_mounted
    assert "myrm-nas-memory:/state/memory" in volumes_mounted
    assert "myrm-nas-logs:/state/logs" in volumes_mounted

    volumes_declared = raw_content.get("volumes")
    assert isinstance(volumes_declared, dict)
    assert "myrm-nas-data" in volumes_declared
    assert "myrm-nas-memory" in volumes_declared
    assert "myrm-nas-logs" in volumes_declared

    frontend_raw = services_raw["myrm-frontend"]
    assert isinstance(frontend_raw, dict)
    ports: list[str] = [str(item) for item in frontend_raw.get("ports", []) if isinstance(item, str)]
    assert any(":3000" in p for p in ports), "Frontend must expose port 3000 for LAN ingress"


@pytest.mark.architecture
def test_nas_compose_merge_config_validity() -> None:
    """Validate that docker compose merge runs without config schema errors."""
    if not shutil.which("docker"):
        pytest.skip("Docker CLI is not installed in the execution environment")

    res = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(_BASE_COMPOSE_PATH),
            "-f",
            str(_NAS_COMPOSE_PATH),
            "--profile",
            "app",
            "config",
        ],
        cwd=str(_WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"docker compose config failed:\n{res.stderr}"
