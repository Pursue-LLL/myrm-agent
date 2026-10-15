"""Curator config PATCH rejects values at which a sweep would treat every eligible skill as due."""

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.core.skills.curator.service as curator_service

_CONFIG_URL = "/api/v1/skills/curator/config"
_CONFIG_FILENAME = "curator_config.json"


@pytest.fixture
def isolated_config(tmp_path: Path) -> Iterator[Path]:
    """Point the curator config at a temp dir and restore the cached config afterwards."""
    previous = curator_service._curator_config
    curator_service._curator_config = None
    with patch.object(curator_service, "_get_data_dir", return_value=tmp_path):
        yield tmp_path
    curator_service._curator_config = previous


@pytest.mark.parametrize(
    "payload",
    [
        {"max_skills": 0},
        {"max_skills": -3},
        {"stale_after_days": 0},
        {"archive_after_days": 0},
        {"interval_hours": 0},
        {"consolidation_similarity_threshold": 1.5},
        {"min_success_rate": -0.1},
    ],
)
def test_out_of_range_value_is_rejected_and_nothing_is_stored(
    client: TestClient, isolated_config: Path, payload: dict[str, float]
) -> None:
    response = client.patch(_CONFIG_URL, json=payload)

    assert response.status_code == 422
    assert "CuratorConfig" in response.json()["detail"]
    assert not (isolated_config / _CONFIG_FILENAME).exists()
    assert client.get(_CONFIG_URL).json()["max_skills"] == 50


def test_rejected_update_keeps_the_previously_stored_config(client: TestClient, isolated_config: Path) -> None:
    assert client.patch(_CONFIG_URL, json={"max_skills": 80}).status_code == 200
    stored = (isolated_config / _CONFIG_FILENAME).read_text()

    assert client.patch(_CONFIG_URL, json={"max_skills": 0}).status_code == 422

    assert (isolated_config / _CONFIG_FILENAME).read_text() == stored
    assert client.get(_CONFIG_URL).json()["max_skills"] == 80


def test_boundary_values_are_accepted(client: TestClient, isolated_config: Path) -> None:
    response = client.patch(
        _CONFIG_URL,
        json={"stale_after_days": 1, "archive_after_days": 1, "interval_hours": 1, "grace_period_days": 0},
    )

    assert response.status_code == 200
    assert json.loads((isolated_config / _CONFIG_FILENAME).read_text())["stale_after_days"] == 1


def test_persisted_invalid_config_falls_back_to_defaults(client: TestClient, isolated_config: Path) -> None:
    (isolated_config / _CONFIG_FILENAME).write_text(json.dumps({"max_skills": 0, "stale_after_days": 0}))

    body = client.get(_CONFIG_URL).json()

    assert body["max_skills"] == 50
    assert body["stale_after_days"] == 30


def test_persisted_invalid_threshold_keeps_the_disabled_master_switch(client: TestClient, isolated_config: Path) -> None:
    (isolated_config / _CONFIG_FILENAME).write_text(json.dumps({"enabled": False, "max_skills": 0, "stale_after_days": 45}))

    body = client.get(_CONFIG_URL).json()

    assert body["enabled"] is False
    assert body["max_skills"] == 50
    assert body["stale_after_days"] == 30


def test_non_finite_persisted_threshold_keeps_the_disabled_master_switch(client: TestClient, isolated_config: Path) -> None:
    (isolated_config / _CONFIG_FILENAME).write_text('{"enabled": false, "stale_after_days": Infinity}')

    body = client.get(_CONFIG_URL).json()

    assert body["enabled"] is False
    assert body["stale_after_days"] == 30


def test_unreadable_persisted_config_falls_back_to_defaults(client: TestClient, isolated_config: Path) -> None:
    (isolated_config / _CONFIG_FILENAME).write_text("{not json")

    body = client.get(_CONFIG_URL).json()

    assert body["enabled"] is True
    assert body["max_skills"] == 50
