"""Webhook delivery secret stability + test-delivery endpoint tests.

Secret lifecycle (api/cron/routes/helpers.py:_delivery_from_request):
- create webhook delivery → fresh secret generated
- update without touching delivery → secret preserved
- update target URL only → secret preserved
- switch away from webhook channel → secret cleared

Test-delivery endpoint (POST /{job_id}/test-delivery):
- 404 for unknown job, 400 for non-deliverable channels
- reuses the real ChannelResultDelivery pipeline for webhook channels
- supports not-yet-saved override configs
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


def _create_webhook_job(client: TestClient, url: str = "https://hooks.example.com/x") -> dict[str, object]:
    resp = client.post(
        "/cron",
        json={
            "name": "webhook-task",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 300_000},
            "prompt": "check",
            "delivery": {"channel": "webhook", "target": url},
        },
    )
    assert resp.status_code == 201
    return resp.json()


class TestWebhookSecretStability:
    def test_create_generates_secret(self, client: TestClient) -> None:
        data = _create_webhook_job(client)
        secret = data["delivery"]["secret"]
        assert secret is not None
        assert len(secret) == 64

    def test_update_unrelated_field_preserves_secret(self, client: TestClient) -> None:
        job = _create_webhook_job(client)
        original_secret = job["delivery"]["secret"]

        resp = client.patch(f"/cron/{job['id']}", json={"name": "renamed"})
        assert resp.status_code == 200
        assert resp.json()["delivery"]["secret"] == original_secret

    def test_update_webhook_url_preserves_secret(self, client: TestClient) -> None:
        job = _create_webhook_job(client)
        original_secret = job["delivery"]["secret"]

        resp = client.patch(
            f"/cron/{job['id']}",
            json={"delivery": {"channel": "webhook", "target": "https://hooks.example.com/new"}},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["delivery"]["target"] == "https://hooks.example.com/new"
        assert updated["delivery"]["secret"] == original_secret

    def test_switch_away_from_webhook_clears_secret(self, client: TestClient) -> None:
        job = _create_webhook_job(client)

        resp = client.patch(f"/cron/{job['id']}", json={"delivery": {"channel": "chat"}})
        assert resp.status_code == 200
        assert resp.json()["delivery"]["secret"] is None

    def test_update_failure_delivery_preserves_secret(self, client: TestClient) -> None:
        job = _create_webhook_job(client)
        resp = client.patch(
            f"/cron/{job['id']}",
            json={"failure_delivery": {"channel": "webhook", "target": "https://alerts.example.com/f"}},
        )
        assert resp.status_code == 200
        failure_secret = resp.json()["failure_delivery"]["secret"]
        assert failure_secret is not None

        resp = client.patch(
            f"/cron/{job['id']}",
            json={"failure_delivery": {"channel": "webhook", "target": "https://alerts.example.com/f2"}},
        )
        assert resp.status_code == 200
        assert resp.json()["failure_delivery"]["secret"] == failure_secret

    def test_update_failure_alert_delivery_preserves_secret(self, client: TestClient) -> None:
        job = _create_webhook_job(client)
        resp = client.patch(
            f"/cron/{job['id']}",
            json={
                "failure_alert": {
                    "enabled": True,
                    "after": 3,
                    "cooldown_seconds": 300,
                    "delivery": {"channel": "webhook", "target": "https://alerts.example.com/a"},
                }
            },
        )
        assert resp.status_code == 200
        alert_secret = resp.json()["failure_alert"]["delivery"]["secret"]
        assert alert_secret is not None

        resp = client.patch(
            f"/cron/{job['id']}",
            json={
                "failure_alert": {
                    "enabled": True,
                    "after": 5,
                    "cooldown_seconds": 600,
                    "delivery": {"channel": "webhook", "target": "https://alerts.example.com/a2"},
                }
            },
        )
        assert resp.status_code == 200
        assert resp.json()["failure_alert"]["delivery"]["secret"] == alert_secret


class TestTestDeliveryEndpoint:
    def test_nonexistent_job_404(self, client: TestClient) -> None:
        resp = client.post("/cron/nonexistent/test-delivery", json={})
        assert resp.status_code == 404

    def test_chat_channel_400(self, client: TestClient) -> None:
        resp = client.post(
            "/cron",
            json={
                "name": "chat-task",
                "job_type": "agent",
                "schedule": {"kind": "interval", "interval_ms": 300_000},
                "prompt": "check",
                "delivery": {"channel": "chat"},
            },
        )
        job_id = resp.json()["id"]
        resp = client.post(f"/cron/{job_id}/test-delivery", json={})
        assert resp.status_code == 400

    def test_success_uses_real_delivery_pipeline(self, client: TestClient) -> None:
        job = _create_webhook_job(client)
        mock_delivery = AsyncMock()
        with patch(
            "app.core.cron.adapters.channel_delivery.ChannelResultDelivery",
            return_value=mock_delivery,
        ):
            resp = client.post(f"/cron/{job['id']}/test-delivery", json={})
        assert resp.status_code == 200
        assert resp.json() == {"delivered": True}
        sent_job, sent_result = mock_delivery.deliver.await_args.args
        assert sent_job.delivery.target == "https://hooks.example.com/x"
        assert sent_job.delivery.secret == job["delivery"]["secret"]
        assert sent_result.success is True

    def test_override_config_tested(self, client: TestClient) -> None:
        job = _create_webhook_job(client)
        mock_delivery = AsyncMock()
        with patch(
            "app.core.cron.adapters.channel_delivery.ChannelResultDelivery",
            return_value=mock_delivery,
        ):
            resp = client.post(
                f"/cron/{job['id']}/test-delivery",
                json={"delivery": {"channel": "webhook", "target": "https://staging.example.com/h"}},
            )
        assert resp.status_code == 200
        sent_job = mock_delivery.deliver.await_args.args[0]
        assert sent_job.delivery.target == "https://staging.example.com/h"
        assert sent_job.delivery.secret == job["delivery"]["secret"]

    def test_failure_propagates_502(self, client: TestClient) -> None:
        job = _create_webhook_job(client)
        mock_delivery = AsyncMock()
        mock_delivery.deliver.side_effect = RuntimeError("Webhook returned 404: Not Found")
        with patch(
            "app.core.cron.adapters.channel_delivery.ChannelResultDelivery",
            return_value=mock_delivery,
        ):
            resp = client.post(f"/cron/{job['id']}/test-delivery", json={})
        assert resp.status_code == 502
        assert "Webhook returned 404" in resp.json()["detail"]

    def test_both_overrides_rejected(self, client: TestClient) -> None:
        job = _create_webhook_job(client)
        resp = client.post(
            f"/cron/{job['id']}/test-delivery",
            json={
                "delivery": {"channel": "webhook", "target": "https://a.example.com"},
                "failure_delivery": {"channel": "webhook", "target": "https://b.example.com"},
            },
        )
        assert resp.status_code == 422

    def test_failure_delivery_override_uses_failure_secret(self, client: TestClient) -> None:
        job = _create_webhook_job(client)
        client.patch(
            f"/cron/{job['id']}",
            json={"failure_delivery": {"channel": "webhook", "target": "https://alerts.example.com/f"}},
        )
        job = client.get(f"/cron/{job['id']}").json()
        failure_secret = job["failure_delivery"]["secret"]

        mock_delivery = AsyncMock()
        with patch(
            "app.core.cron.adapters.channel_delivery.ChannelResultDelivery",
            return_value=mock_delivery,
        ):
            resp = client.post(
                f"/cron/{job['id']}/test-delivery",
                json={"failure_delivery": {"channel": "webhook", "target": "https://alerts.example.com/f2"}},
            )
        assert resp.status_code == 200
        sent_job = mock_delivery.deliver.await_args.args[0]
        assert sent_job.delivery.target == "https://alerts.example.com/f2"
        assert sent_job.delivery.secret == failure_secret

    def test_test_to_heal_resets_consecutive_failures(self, client: TestClient, cron_manager: CronManager) -> None:
        """Successful test delivery on active degraded delivery immediately clears failure state."""
        job = _create_webhook_job(client)
        from myrm_agent_harness.toolkits.cron.types import CronJobPatch
        import asyncio
        asyncio.run(cron_manager.update_job(
            job["id"],
            "default",
            CronJobPatch(consecutive_failures=3, last_error="502 Bad Gateway"),
        ))
        degraded_job = client.get(f"/cron/{job['id']}").json()
        assert degraded_job["consecutive_failures"] == 3

        mock_delivery = AsyncMock()
        with patch(
            "app.core.cron.adapters.channel_delivery.ChannelResultDelivery",
            return_value=mock_delivery,
        ):
            resp = client.post(f"/cron/{job['id']}/test-delivery")
        assert resp.status_code == 200

        healed_job = client.get(f"/cron/{job['id']}").json()
        assert healed_job["consecutive_failures"] == 0
        assert healed_job["last_error"] is None

