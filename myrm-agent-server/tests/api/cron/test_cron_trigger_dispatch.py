"""Tests for trigger dispatch API endpoints and TriggerProvider matching logic.

Uses InMemoryCronStore with mock TriggerProvider to test:
- POST /cron/trigger/event (body-based)
- POST /cron/trigger/system-event (body-based)
- POST /cron/trigger/webhook/{path}
- Trigger matching logic (extracted, no DB)
"""

from __future__ import annotations

from typing import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron import (
    CronConfig,
    CronManager,
    CronScheduler,
)
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.triggers import (
    EventTrigger,
    SystemEventTrigger,
    WebhookTrigger,
)
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

USER_ID = "test-user"


class FakeDelivery:
    async def deliver(self, job: CronJob, result: object) -> None:
        pass


def _make_job(**overrides: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "job-trigger-1",
        "user_id": USER_ID,
        "name": "Trigger Test",
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
        "status": JobStatus.ACTIVE,
        "prompt": "test prompt",
        "delivery": DeliveryConfig(channel="chat"),
    }
    defaults.update(overrides)
    return CronJob(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def trigger_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.check_event_triggers = AsyncMock(return_value=[])
    provider.check_system_event = AsyncMock(return_value=[])
    provider.handle_webhook = AsyncMock(return_value=None)
    return provider


@pytest.fixture
def scheduler(trigger_provider: AsyncMock) -> CronScheduler:
    store = InMemoryCronStore()
    return CronScheduler(
        store=store,
        runners={},
        delivery=FakeDelivery(),
        config=CronConfig(),
        trigger_provider=trigger_provider,
    )


@pytest.fixture
def app(scheduler: CronScheduler) -> Generator[FastAPI, None, None]:
    from app.api.cron.routes import helpers, router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/cron")

    manager = CronManager(scheduler._store, scheduler, shell_enabled=True)

    with (
        patch.object(helpers, "_get_manager", return_value=manager),
        patch.object(helpers, "_get_scheduler", return_value=scheduler),
    ):
        yield test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /cron/trigger/event — body-based
# ---------------------------------------------------------------------------


class TestEventTriggerEndpoint:
    def test_event_trigger_with_body(self, client: TestClient, trigger_provider: AsyncMock) -> None:
        job = _make_job()
        trigger_provider.check_event_triggers = AsyncMock(return_value=[job])

        resp = client.post(
            "/cron/trigger/event",
            json={"message": "Error: connection failed $AAPL&timeout=30", "channel": "slack"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["triggered"] == 1
        trigger_provider.check_event_triggers.assert_awaited_once()
        call_args = trigger_provider.check_event_triggers.call_args[0]
        assert call_args[0] == "Error: connection failed $AAPL&timeout=30"
        assert call_args[1] == "slack"

    def test_event_trigger_empty_message_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/trigger/event",
            json={"message": ""},
        )
        assert resp.status_code == 422

    def test_event_trigger_no_match(self, client: TestClient, trigger_provider: AsyncMock) -> None:
        trigger_provider.check_event_triggers = AsyncMock(return_value=[])
        resp = client.post(
            "/cron/trigger/event",
            json={"message": "hello world"},
        )
        assert resp.status_code == 200
        assert resp.json()["triggered"] == 0

    def test_event_trigger_special_chars_in_body(self, client: TestClient, trigger_provider: AsyncMock) -> None:
        trigger_provider.check_event_triggers = AsyncMock(return_value=[])
        msg = "告警: db&host=internal:5432 错误率>50%"
        resp = client.post(
            "/cron/trigger/event",
            json={"message": msg, "channel": "wechat"},
        )
        assert resp.status_code == 200
        call_args = trigger_provider.check_event_triggers.call_args[0]
        assert call_args[0] == msg


# ---------------------------------------------------------------------------
# POST /cron/trigger/system-event — body-based
# ---------------------------------------------------------------------------


class TestSystemEventTriggerEndpoint:
    def test_system_event_with_body(self, client: TestClient, trigger_provider: AsyncMock) -> None:
        job = _make_job()
        trigger_provider.check_system_event = AsyncMock(return_value=[job])

        resp = client.post(
            "/cron/trigger/system-event",
            json={
                "source": "github",
                "event_type": "push",
                "payload": {"ref": "refs/heads/main"},
            },
        )

        assert resp.status_code == 200
        assert resp.json()["triggered"] == 1
        trigger_provider.check_system_event.assert_awaited_once_with("github", "push", {"ref": "refs/heads/main"})

    def test_system_event_empty_source_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/trigger/system-event",
            json={"source": "", "event_type": "push"},
        )
        assert resp.status_code == 422

    def test_system_event_default_payload(self, client: TestClient, trigger_provider: AsyncMock) -> None:
        trigger_provider.check_system_event = AsyncMock(return_value=[])
        resp = client.post(
            "/cron/trigger/system-event",
            json={"source": "sentry", "event_type": "alert"},
        )
        assert resp.status_code == 200
        call_args = trigger_provider.check_system_event.call_args
        assert call_args[0][2] == {}


# ---------------------------------------------------------------------------
# POST /cron/trigger/webhook/{path}
# ---------------------------------------------------------------------------


class TestWebhookTriggerEndpoint:
    def test_webhook_match(self, client: TestClient, trigger_provider: AsyncMock) -> None:
        job = _make_job()
        trigger_provider.handle_webhook = AsyncMock(return_value=job)

        resp = client.post(
            "/cron/trigger/webhook/abc123",
            json={"event": "deployment"},
            headers={"x-webhook-secret": "my-secret"},
        )

        assert resp.status_code == 200
        assert resp.json()["triggered"] is True

    def test_webhook_no_match(self, client: TestClient, trigger_provider: AsyncMock) -> None:
        trigger_provider.handle_webhook = AsyncMock(return_value=None)
        resp = client.post(
            "/cron/trigger/webhook/unknown",
            json={},
            headers={"x-webhook-secret": "some-secret"},
        )
        assert resp.status_code == 404

    def test_webhook_missing_secret(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/trigger/webhook/abc123",
            json={"event": "deploy"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Trigger matching logic (unit tests, no DB)
# ---------------------------------------------------------------------------


class TestEventTriggerMatching:
    """Test regex matching logic as used by TriggerProvider."""

    def test_simple_match(self) -> None:
        import re

        et = EventTrigger(pattern=r"error|warn")
        assert re.search(et.pattern, "server error occurred")
        assert not re.search(et.pattern, "info: started")

    def test_channel_filter(self) -> None:
        et = EventTrigger(pattern=r"alert", channel="telegram")
        assert et.channel == "telegram"
        assert et.channel != "slack"

    def test_unicode_pattern(self) -> None:
        import re

        et = EventTrigger(pattern=r"告警.*\d+")
        assert re.search(et.pattern, "系统告警编号123")
        assert not re.search(et.pattern, "正常运行")

    def test_special_chars_preserved(self) -> None:
        import re

        et = EventTrigger(pattern=r"\$[A-Z]+")
        assert re.search(et.pattern, "Stock $AAPL dropped")


class TestSystemEventTriggerMatching:
    def test_exact_match(self) -> None:
        se = SystemEventTrigger(
            source="github",
            event_type="push",
            filters={"ref": "refs/heads/main"},
        )
        payload: dict[str, object] = {"ref": "refs/heads/main", "commits": []}
        assert all(str(payload.get(k)) == v for k, v in se.filters.items())

    def test_filter_mismatch(self) -> None:
        se = SystemEventTrigger(
            source="github",
            event_type="push",
            filters={"ref": "refs/heads/main"},
        )
        payload: dict[str, object] = {"ref": "refs/heads/dev"}
        assert not all(str(payload.get(k)) == v for k, v in se.filters.items())

    def test_empty_filters_match_all(self) -> None:
        se = SystemEventTrigger(source="sentry", event_type="alert", filters={})
        assert all(str({}.get(k)) == v for k, v in se.filters.items())


class TestWebhookTriggerMatching:
    def test_path_match(self) -> None:
        wh = WebhookTrigger(path="abc123", secret="s1")
        assert wh.path == "abc123"

    def test_secret_validation(self) -> None:
        from myrm_agent_harness.toolkits.cron.triggers import validate_webhook_secret

        assert validate_webhook_secret("s1", "s1") is True
        assert validate_webhook_secret("s1", "s2") is False
