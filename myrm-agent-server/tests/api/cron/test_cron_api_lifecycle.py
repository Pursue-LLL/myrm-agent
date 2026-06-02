"""End-to-end lifecycle test for cron REST API.

Uses InMemoryCronStore (no DB) to validate the full API lifecycle:
create → get → pause → resume → update → list → delete.

Covers max_fires, expires_at, active_hours, and error scenarios.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


class FakeDelivery:
    async def deliver(self, job, result):  # noqa: ANN001
        pass


@pytest.fixture
def cron_manager() -> CronManager:
    store = InMemoryCronStore()
    scheduler = CronScheduler(
        store=store,
        runners={},
        delivery=FakeDelivery(),
        config=CronConfig(),
    )
    return CronManager(store, scheduler, shell_enabled=True)


@pytest.fixture
def app(cron_manager: CronManager) -> Generator[FastAPI, None, None]:
    from app.api.cron.routes import helpers, router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/cron")

    with patch.object(helpers, "_get_manager", return_value=cron_manager):
        yield test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestCronApiLifecycle:
    """Full lifecycle: create → get → pause → resume → update → list → delete."""

    def _create_job(self, client: TestClient) -> dict[str, object]:
        resp = client.post(
            "/cron",
            json={
                "name": "test-monitor",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check stock",
            },
        )
        assert resp.status_code == 201
        return resp.json()

    def test_create_job(self, client: TestClient) -> None:
        data = self._create_job(client)
        assert data["name"] == "test-monitor"
        assert data["status"] == "active"
        assert data["job_type"] == "agent"

    def test_get_job(self, client: TestClient) -> None:
        data = self._create_job(client)
        resp = client.get(f"/cron/{data['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == data["id"]

    def test_get_nonexistent_job(self, client: TestClient) -> None:
        resp = client.get("/cron/nonexistent")
        assert resp.status_code == 404

    def test_pause_job(self, client: TestClient) -> None:
        data = self._create_job(client)
        resp = client.post(f"/cron/{data['id']}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    def test_resume_job(self, client: TestClient) -> None:
        data = self._create_job(client)
        client.post(f"/cron/{data['id']}/pause")
        resp = client.post(f"/cron/{data['id']}/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_pause_nonexistent_job(self, client: TestClient) -> None:
        resp = client.post("/cron/nonexistent/pause")
        assert resp.status_code == 404

    def test_resume_nonexistent_job(self, client: TestClient) -> None:
        resp = client.post("/cron/nonexistent/resume")
        assert resp.status_code == 404

    def test_delete_job(self, client: TestClient) -> None:
        data = self._create_job(client)
        resp = client.delete(f"/cron/{data['id']}")
        assert resp.status_code == 204

        resp = client.get(f"/cron/{data['id']}")
        assert resp.status_code == 404

    def test_delete_nonexistent_job(self, client: TestClient) -> None:
        resp = client.delete("/cron/nonexistent")
        assert resp.status_code == 404

    def test_list_jobs(self, client: TestClient) -> None:
        self._create_job(client)
        resp = client.get("/cron")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/cron")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_update_job_name(self, client: TestClient) -> None:
        data = self._create_job(client)
        resp = client.patch(f"/cron/{data['id']}", json={"name": "renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "renamed"

    def test_update_nonexistent_job(self, client: TestClient) -> None:
        resp = client.patch("/cron/nonexistent", json={"name": "new"})
        assert resp.status_code == 404


class TestCronApiMaxFiresExpires:
    """Tests for max_fires and expires_at API fields."""

    def test_create_with_max_fires(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "limited-task",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "max_fires": 100,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["max_fires"] == 100

    def test_create_with_expires_at(self, client: TestClient) -> None:
        future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        resp = client.post(
            "/cron",
            json={
                "name": "expiring-task",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "expires_at": future,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["expires_at"] is not None

    def test_create_with_both(self, client: TestClient) -> None:
        future = (datetime.now(UTC) + timedelta(days=7)).isoformat()
        resp = client.post(
            "/cron",
            json={
                "name": "combo-task",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "max_fires": 50,
                "expires_at": future,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["max_fires"] == 50
        assert data["expires_at"] is not None

    def test_update_max_fires(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "test",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
            },
        )
        job_id = resp.json()["id"]
        resp = client.patch(f"/cron/{job_id}", json={"max_fires": 200})
        assert resp.status_code == 200
        assert resp.json()["max_fires"] == 200


class TestCronApiScheduleTypes:
    """Tests for different schedule types."""

    def test_cron_expr_schedule(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "daily",
                "job_type": "agent",
                "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                "prompt": "daily check",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["schedule"]["kind"] == "cron"

    def test_once_schedule(self, client: TestClient) -> None:
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        resp = client.post(
            "/cron",
            json={
                "name": "one-shot",
                "job_type": "agent",
                "schedule": {"kind": "once", "run_at": future},
                "prompt": "remind me",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["schedule"]["kind"] == "once"

    def test_interval_schedule(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "interval",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 600_000},
                "prompt": "check",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["schedule"]["kind"] == "interval"


class TestCronApiValidation:
    """Tests for input validation."""

    def test_reserved_name_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "__system-task",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
            },
        )
        assert resp.status_code == 422

    def test_empty_name_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "  ",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
            },
        )
        assert resp.status_code == 422


class TestCronApiPauseResumeRoundTrip:
    """Pause→resume preserves state."""

    def test_round_trip_preserves_config(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "persistent",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "max_fires": 50,
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["id"]

        client.post(f"/cron/{job_id}/pause")
        resp = client.post(f"/cron/{job_id}/resume")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["max_fires"] == 50
        assert data["next_run_at"] is not None


class TestCronApiAgentIdBinding:
    """Full lifecycle for agent_id binding on cron jobs."""

    def test_create_with_agent_id(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "agent-bound-task",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "analyse logs",
                "agent_id": "custom-agent-42",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_id"] == "custom-agent-42"

    def test_create_without_agent_id(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "default-task",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["agent_id"] is None

    def test_update_agent_id(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "rebindable",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
            },
        )
        job_id = resp.json()["id"]

        resp = client.patch(f"/cron/{job_id}", json={"agent_id": "new-agent"})
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "new-agent"

    def test_pause_resume_preserves_agent_id(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "agent-persistent",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "agent_id": "persist-agent",
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["id"]

        client.post(f"/cron/{job_id}/pause")
        resp = client.post(f"/cron/{job_id}/resume")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "persist-agent"


class TestCronApiSessionTargetChatId:
    """Tests for session_target and chat_id API fields."""

    def test_create_with_session_target_main_and_chat_id(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "thread-task",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check progress",
                "session_target": "main",
                "chat_id": "chat-abc-123",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["session_target"] == "main"
        assert data["chat_id"] == "chat-abc-123"

    def test_create_default_isolated(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "isolated-task",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["session_target"] == "isolated"
        assert data["chat_id"] is None

    def test_update_chat_id(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "rebind-chat",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "session_target": "main",
                "chat_id": "chat-old",
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["id"]

        resp = client.patch(f"/cron/{job_id}", json={"chat_id": "chat-new"})
        assert resp.status_code == 200
        assert resp.json()["chat_id"] == "chat-new"

    def test_clear_chat_id(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "clear-chat",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "session_target": "main",
                "chat_id": "chat-to-clear",
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["id"]

        resp = client.patch(f"/cron/{job_id}", json={"chat_id": None})
        assert resp.status_code == 200
        assert resp.json()["chat_id"] is None

    def test_switch_to_isolated_clears_chat_id(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "switch-mode",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "session_target": "main",
                "chat_id": "chat-bound",
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["id"]

        resp = client.patch(
            f"/cron/{job_id}",
            json={"session_target": "isolated", "chat_id": None},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_target"] == "isolated"
        assert data["chat_id"] is None

    def test_update_preserves_chat_id_when_not_sent(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "preserve-chat",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "session_target": "main",
                "chat_id": "chat-keep",
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["id"]

        resp = client.patch(f"/cron/{job_id}", json={"name": "renamed"})
        assert resp.status_code == 200
        assert resp.json()["chat_id"] == "chat-keep"
