"""A job's chat binding and acceptance criteria round-trip through the cron REST API.

[INPUT] Job create/update payloads carrying session_target, chat_id and acceptance_criteria; a real CronManager over an in-memory store.
[OUTPUT] Verified create stores the binding and the criteria, update changes or clears them only when sent, pause and resume keep them, and the list filters by chat_id.
[POS] tests/api/cron/test_cron_api_chat_binding_and_criteria.py
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore

from app.api.cron.routes import actions_router, helpers, jobs_router


class _NoDelivery:
    async def deliver(self, job: object, result: object) -> None:
        pass


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    store = InMemoryCronStore()
    scheduler = CronScheduler(store=store, runners={}, delivery=_NoDelivery(), config=CronConfig())
    manager = CronManager(store, scheduler, shell_enabled=True)
    app = FastAPI()
    app.include_router(jobs_router, prefix="/cron")
    app.include_router(actions_router, prefix="/cron")
    with patch.object(helpers, "_get_manager", return_value=manager):
        yield TestClient(app)


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


class TestCronApiAcceptanceCriteria:
    """Tests for acceptance_criteria CRUD through the REST API."""

    def test_create_with_acceptance_criteria(self, client: TestClient) -> None:
        criteria = [
            {"type": "shell", "command": "echo ok"},
            {"type": "semantic", "description": "output must contain 'success'"},
        ]
        resp = client.post(
            "/cron",
            json={
                "name": "verified-task",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "do work",
                "acceptance_criteria": criteria,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["acceptance_criteria"] == criteria

    def test_create_without_acceptance_criteria(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "no-criteria",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["acceptance_criteria"] is None

    def test_update_acceptance_criteria(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "update-criteria",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["id"]

        new_criteria = [{"type": "shell", "command": "test -f /tmp/done"}]
        resp = client.patch(f"/cron/{job_id}", json={"acceptance_criteria": new_criteria})
        assert resp.status_code == 200
        assert resp.json()["acceptance_criteria"] == new_criteria

    def test_clear_acceptance_criteria(self, client: TestClient) -> None:
        criteria = [{"type": "shell", "command": "echo ok"}]
        resp = client.post(
            "/cron",
            json={
                "name": "clear-criteria",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "acceptance_criteria": criteria,
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["id"]
        assert resp.json()["acceptance_criteria"] == criteria

        resp = client.patch(f"/cron/{job_id}", json={"acceptance_criteria": None})
        assert resp.status_code == 200
        assert resp.json()["acceptance_criteria"] is None

    def test_get_preserves_acceptance_criteria(self, client: TestClient) -> None:
        criteria = [{"type": "semantic", "description": "must mention price"}]
        resp = client.post(
            "/cron",
            json={
                "name": "get-criteria",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "acceptance_criteria": criteria,
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["id"]

        resp = client.get(f"/cron/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["acceptance_criteria"] == criteria

    def test_pause_resume_preserves_acceptance_criteria(self, client: TestClient) -> None:
        criteria = [{"type": "shell", "command": "curl -s http://example.com"}]
        resp = client.post(
            "/cron",
            json={
                "name": "persist-criteria",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "acceptance_criteria": criteria,
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["id"]

        client.post(f"/cron/{job_id}/pause")
        resp = client.post(f"/cron/{job_id}/resume")
        assert resp.status_code == 200
        assert resp.json()["acceptance_criteria"] == criteria


class TestCronChatIdFilter:
    def test_list_jobs_filters_by_chat_id(self, client: TestClient) -> None:
        for chat_id, name in (("chat-a", "job-a"), ("chat-b", "job-b")):
            resp = client.post(
                "/cron",
                json={
                    "name": name,
                    "job_type": "agent",
                    "schedule": {"kind": "interval", "interval_ms": 300_000},
                    "prompt": "check",
                    "session_target": "main",
                    "chat_id": chat_id,
                },
            )
            assert resp.status_code == 201

        resp = client.get("/cron?chat_id=chat-a")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["chat_id"] == "chat-a"
        assert data["items"][0]["name"] == "job-a"
