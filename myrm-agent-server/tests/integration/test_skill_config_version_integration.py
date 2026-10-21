"""Integration: server re-export uses harness Volume-backed skill config version."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.skills.config_version import (
    bump_skill_config_version,
    get_skill_config_version,
)

_VERSION_FILENAME = ".skill_config_version"


@pytest.fixture
def version_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path))
    return tmp_path


def test_server_reexport_bump_and_get_share_volume_file(version_dir: Path) -> None:
    assert get_skill_config_version() == 0.0
    bump_skill_config_version()
    first = get_skill_config_version()
    assert first > 0.0

    version_file = version_dir / _VERSION_FILENAME
    assert version_file.is_file()

    bump_skill_config_version()
    second = get_skill_config_version()
    assert second >= first


def _load_config_router():
    module_path = Path(__file__).resolve().parents[2] / "app" / "api" / "skills" / "config.py"
    spec = importlib.util.spec_from_file_location("app.api.skills.config", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load config router from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.router


def test_config_version_http_endpoint_reflects_volume_bump(version_dir: Path) -> None:
    app = FastAPI()
    app.include_router(_load_config_router(), prefix="/api/v1/skills")
    client = TestClient(app)

    initial = client.get("/api/v1/skills/config-version")
    assert initial.status_code == 200
    assert initial.json()["version"] == 0.0

    bump_skill_config_version()
    bumped = client.get("/api/v1/skills/config-version")
    assert bumped.status_code == 200
    assert bumped.json()["version"] > 0.0
