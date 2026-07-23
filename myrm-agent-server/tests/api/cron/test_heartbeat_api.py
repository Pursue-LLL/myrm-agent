"""Integration tests for heartbeat REST API endpoints.

Validates enable/disable/status lifecycle with agent_id binding,
using InMemoryCronStore (no DB) and FastAPI TestClient.
"""

from __future__ import annotations

from typing import Generator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron import (
    CronConfig,
    CronManager,
    CronScheduler,
)
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore


class _FakeDelivery:
    async def deliver(self, job, result):  # noqa: ANN001
        pass


@pytest.fixture
def cron_manager() -> CronManager:
    store = InMemoryCronStore()
    scheduler = CronScheduler(
        store=store,
        runners={},
        delivery=_FakeDelivery(),
        config=CronConfig(),
    )
    return CronManager(store, scheduler, shell_enabled=True)


@pytest.fixture
def app(cron_manager: CronManager) -> Generator[FastAPI, None, None]:
    from app.api.cron.routes import heartbeat as hb_mod
    from app.api.cron.routes import helpers

    test_app = FastAPI()
    test_app.include_router(hb_mod.router, prefix="/cron")

    with patch.object(helpers, "_get_manager", return_value=cron_manager):
        yield test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestHeartbeatLifecycle:
    """Enable → status → disable round-trip."""

    def test_status_when_disabled(self, client: TestClient) -> None:
        resp = client.get("/cron/heartbeat/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["agent_id"] is None

    def test_enable_default(self, client: TestClient) -> None:
        resp = client.post("/cron/heartbeat/enable", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["agent_id"] is None

    def test_enable_disable_roundtrip(self, client: TestClient) -> None:
        client.post("/cron/heartbeat/enable", json={})
        resp = client.post("/cron/heartbeat/disable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

        resp = client.get("/cron/heartbeat/status")
        assert resp.json()["enabled"] is False


class TestHeartbeatAgentIdBinding:
    """agent_id binding through heartbeat API."""

    def test_enable_with_agent_id(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/heartbeat/enable",
            json={"agent_id": "scout-agent"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "scout-agent"

    def test_status_reflects_agent_id(self, client: TestClient) -> None:
        client.post(
            "/cron/heartbeat/enable",
            json={"agent_id": "patrol-agent"},
        )
        resp = client.get("/cron/heartbeat/status")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "patrol-agent"

    def test_update_agent_id(self, client: TestClient) -> None:
        client.post(
            "/cron/heartbeat/enable",
            json={"agent_id": "old-agent"},
        )
        resp = client.post(
            "/cron/heartbeat/enable",
            json={"agent_id": "new-agent"},
        )
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "new-agent"

    def test_unbind_agent_id(self, client: TestClient) -> None:
        client.post(
            "/cron/heartbeat/enable",
            json={"agent_id": "bound-agent"},
        )
        resp = client.post("/cron/heartbeat/enable", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert not data["agent_id"]

    def test_disable_preserves_agent_id_in_status(self, client: TestClient) -> None:
        client.post(
            "/cron/heartbeat/enable",
            json={"agent_id": "persist-agent"},
        )
        resp = client.post("/cron/heartbeat/disable")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["agent_id"] == "persist-agent"


class TestHeartbeatCronSchedule:
    """Heartbeat with cron schedule through API."""

    def test_enable_cron_schedule(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/heartbeat/enable",
            json={
                "schedule_kind": "cron",
                "cron_expr": "0 9 * * *",
                "timezone": "Asia/Shanghai",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["schedule_kind"] == "cron"
        assert data["cron_expr"] == "0 9 * * *"
        assert data["timezone"] == "Asia/Shanghai"

    def test_cron_without_expr_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/heartbeat/enable",
            json={"schedule_kind": "cron"},
        )
        assert resp.status_code == 400

    def test_invalid_cron_expr_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/heartbeat/enable",
            json={"schedule_kind": "cron", "cron_expr": "not-valid"},
        )
        assert resp.status_code == 400

    def test_invalid_timezone_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/heartbeat/enable",
            json={
                "schedule_kind": "cron",
                "cron_expr": "0 9 * * *",
                "timezone": "Invalid/Zone",
            },
        )
        assert resp.status_code == 400
