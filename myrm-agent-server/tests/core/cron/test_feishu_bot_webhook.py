"""Tests for Feishu/Lark custom bot webhook cron delivery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.types import CronJob, DeliveryConfig, JobResult, JobType, Schedule

from app.core.cron.adapters.feishu_bot_webhook import (
    deliver_feishu_bot_webhook,
    is_feishu_bot_hook_url,
)


def test_is_feishu_bot_hook_url() -> None:
    assert is_feishu_bot_hook_url("https://open.feishu.cn/open-apis/bot/v2/hook/abc")
    assert is_feishu_bot_hook_url("https://open.larksuite.com/open-apis/bot/v2/hook/abc")
    assert not is_feishu_bot_hook_url("https://hooks.slack.com/services/T/B/X")


@pytest.mark.asyncio
async def test_deliver_feishu_bot_webhook_posts_text_payload() -> None:
    job = CronJob(
        id="job-1",
        user_id="user-1",
        name="daily",
        job_type=JobType.AGENT,
        prompt="brief",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
        delivery=DeliveryConfig(
            channel="webhook",
            target="https://open.feishu.cn/open-apis/bot/v2/hook/test",
        ),
    )
    result = JobResult(success=True, output="Hello from cron")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": 0, "msg": "success"}
    mock_response.text = '{"code":0}'

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.core.cron.adapters.feishu_bot_webhook.httpx.AsyncClient", return_value=mock_client):
        await deliver_feishu_bot_webhook(job, result)

    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.await_args.kwargs
    body = call_kwargs["content"]
    assert '"msg_type": "text"' in body
    assert "Hello from cron" in body


@pytest.mark.asyncio
async def test_channel_delivery_routes_feishu_hook_via_bot_webhook() -> None:
    from app.core.cron.adapters.channel_delivery import ChannelResultDelivery

    job = CronJob(
        id="job-2",
        user_id="user-1",
        name="daily",
        job_type=JobType.AGENT,
        prompt="brief",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
        delivery=DeliveryConfig(
            channel="webhook",
            target="https://open.feishu.cn/open-apis/bot/v2/hook/test",
        ),
    )
    result = JobResult(success=True, output="ok")

    delivery = ChannelResultDelivery()
    with patch(
        "app.core.cron.adapters.channel_delivery.deliver_feishu_bot_webhook",
        new_callable=AsyncMock,
    ) as mock_deliver:
        await delivery.deliver(job, result)
        mock_deliver.assert_awaited_once_with(job, result)
