"""The channels that deliver nowhere outside are one set, and each place that cares reads it.

[INPUT]
- app.core.cron.adapters.delivery_resolver::NON_OUTBOUND_CHANNELS (POS: business-layer cron delivery rules; the channels that deliver nowhere outside)
- app.api.cron.routes::actions_router, helpers (POS: the test-delivery endpoint and the delivery request conversion)
- app.core.cron.adapters.channel_delivery::ChannelResultDelivery (POS: ResultDelivery implementation via the Channel Gateway)

[OUTPUT]
- The set is chat, silent and none
- Each member needs no address when a delivery is saved, takes no test delivery and sends nothing when a result is
  delivered; a channel outside the set needs an address

[POS]
Saving a delivery, test-delivering it and delivering a result each apply the set; every member goes through each of
them here, so a channel added to the set cannot be missed by one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron import CronJob, DeliveryConfig, JobResult, JobType, Schedule, ScheduleKind
from myrm_agent_harness.toolkits.cron.delivery import WebhookDelivery

from app.api.cron.routes import actions_router, helpers
from app.api.cron.schemas import DeliveryCreate
from app.core.cron.adapters.channel_delivery import ChannelResultDelivery
from app.core.cron.adapters.delivery_resolver import NON_OUTBOUND_CHANNELS

_ADDRESS = "https://hooks.example.com/notify"


def _job(channel: str) -> CronJob:
    return CronJob(
        id="job-1",
        name="report",
        job_type=JobType.ROUTER,
        schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000),
        command="__probe__",
        delivery=DeliveryConfig(channel=channel, target=_ADDRESS),
    )


def test_the_set_is_chat_silent_and_none() -> None:
    assert NON_OUTBOUND_CHANNELS == {"chat", "silent", "none"}


@pytest.mark.parametrize("channel", sorted(NON_OUTBOUND_CHANNELS))
def test_a_delivery_that_stays_inside_needs_no_address(channel: str) -> None:
    config = helpers._delivery_from_request(DeliveryCreate(channel=channel))

    assert (config.channel, config.target) == (channel, None)


def test_a_channel_outside_the_set_needs_an_address() -> None:
    with pytest.raises(ValueError, match="Delivery target is required"):
        helpers._delivery_from_request(DeliveryCreate(channel="telegram"))


@pytest.mark.parametrize("channel", sorted(NON_OUTBOUND_CHANNELS))
def test_a_delivery_that_stays_inside_takes_no_test_delivery(monkeypatch: pytest.MonkeyPatch, channel: str) -> None:
    manager = MagicMock()
    manager.get_job = AsyncMock(return_value=_job(channel))
    monkeypatch.setattr(helpers, "_get_manager", lambda: manager)
    app = FastAPI()
    app.include_router(actions_router, prefix="/cron")

    response = TestClient(app).post("/cron/job-1/test-delivery")

    assert response.status_code == 400
    assert channel in response.json()["detail"]


@pytest.mark.parametrize("channel", sorted(NON_OUTBOUND_CHANNELS))
async def test_a_delivery_that_stays_inside_sends_nothing(channel: str) -> None:
    webhook = AsyncMock(spec=WebhookDelivery)

    with patch.object(ChannelResultDelivery, "_deliver_channel", new=AsyncMock()) as deliver_channel:
        await ChannelResultDelivery(webhook_delivery=webhook).deliver(_job(channel), JobResult(success=True, output="report"))

    webhook.deliver.assert_not_awaited()
    deliver_channel.assert_not_awaited()
