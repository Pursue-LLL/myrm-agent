"""Architecture contract: the Docker data-volume target must match MYRM_DATA_DIR.

The local Docker stack and the native/desktop installers share one state
directory. A mismatch silently loses data when a container is recreated, so
this test locks the path in one place.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
_STATE_DIR = "/home/myrm/.myrm"


def _service_volume_targets(compose_path: Path, service: str) -> list[str]:
    raw = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = raw["services"]
    volumes = services[service].get("volumes", [])
    targets: list[str] = []
    for volume in volumes:
        if isinstance(volume, str) and ":" in volume:
            targets.append(volume.rsplit(":", 1)[1])
        elif isinstance(volume, dict) and volume.get("target"):
            targets.append(str(volume["target"]))
    return targets


def test_server_compose_mounts_state_dir() -> None:
    targets = _service_volume_targets(_SERVER_ROOT / "docker-compose.yaml", "backend")
    assert _STATE_DIR in targets
    assert all(".myrm-agent" not in target for target in targets)


def test_distribution_compose_mounts_state_dir() -> None:
    targets = _service_volume_targets(_WORKSPACE_ROOT / "docker-compose.yml", "myrm-server")
    assert _STATE_DIR in targets
    assert all(".myrm-agent" not in target for target in targets)


@pytest.mark.parametrize(
    "dockerfile",
    [
        _SERVER_ROOT / "Dockerfile",
        _SERVER_ROOT / "docker" / "Dockerfile.official",
    ],
)
def test_dockerfile_creates_state_dir(dockerfile: Path) -> None:
    content = dockerfile.read_text(encoding="utf-8")
    assert f"mkdir -p {_STATE_DIR}" in content
    assert ".myrm-agent" not in content


def test_default_state_dir_matches_volume_target() -> None:
    from app.config.settings import DatabaseSettings

    assert DatabaseSettings.model_fields["state_dir"].default == "~/.myrm"
