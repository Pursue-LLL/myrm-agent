"""Unit tests for skill discovery registry probe endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills import discovery


@pytest.fixture(scope="function")
def app() -> FastAPI:
    test_app = FastAPI(title="Skill Discovery Probe Test App")
    test_app.include_router(discovery.router, prefix="/api/v1/skills")
    return test_app


@pytest.fixture(scope="function")
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_registry_probe_cn_reachable(client: TestClient) -> None:
    with patch(
        "app.core.skills.clawhub_probe.probe_configured_cn_mirror",
        new=AsyncMock(return_value=(True, "reachable")),
    ):
        response = client.get("/api/v1/skills/discovery/registry-probe?mirror=cn")

    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is True
    assert body["error"] == "reachable"


def test_registry_probe_cn_unreachable(client: TestClient) -> None:
    with patch(
        "app.core.skills.clawhub_probe.probe_configured_cn_mirror",
        new=AsyncMock(return_value=(False, "not_clawhub_json")),
    ):
        response = client.get("/api/v1/skills/discovery/registry-probe?mirror=cn")

    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is False
    assert body["error"] == "not_clawhub_json"


def test_registry_probe_explicit_url(client: TestClient) -> None:
    with patch(
        "app.core.skills.clawhub_probe.probe_clawhub_registry",
        new=AsyncMock(return_value=(True, "reachable")),
    ) as probe:
        response = client.get(
            "/api/v1/skills/discovery/registry-probe?"
            "url=https%3A%2F%2Fskill.xfyun.cn",
        )

    assert response.status_code == 200
    probe.assert_awaited_once_with("https://skill.xfyun.cn")
    assert response.json()["reachable"] is True
