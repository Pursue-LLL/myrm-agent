"""Tests for WeCom group bot webhook cron delivery."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.cron.adapters.wecom_bot_webhook import (
    _build_wecom_markdown,
    deliver_wecom_bot_webhook,
    is_wecom_bot_hook_url,
)
from myrm_agent_harness.toolkits.cron.types import CronJob, DeliveryConfig, JobResult, JobType, Schedule


def _make_job(
    *,
    name: str = "weekly-report",
    target: str = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
    channel: str = "webhook",
    job_id: str = "job-w1",
) -> CronJob:
    return CronJob(
        id=job_id,
        user_id="user-1",
        name=name,
        job_type=JobType.AGENT,
        prompt="提醒",
        schedule=Schedule(kind="cron", expr="0 18 * * 5"),
        delivery=DeliveryConfig(channel=channel, target=target),
    )


def _mock_httpx_success(response_json: dict | None = None) -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = response_json or {"errcode": 0, "errmsg": "ok"}
    mock_response.text = json.dumps(response_json or {"errcode": 0})
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


# --- is_wecom_bot_hook_url ---


class TestIsWecomBotHookUrl:
    def test_standard_url(self) -> None:
        assert is_wecom_bot_hook_url(
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc123"
        )

    def test_uppercase_url(self) -> None:
        assert is_wecom_bot_hook_url(
            "https://QYAPI.WEIXIN.QQ.COM/cgi-bin/webhook/send?key=xyz"
        )

    def test_mixed_case_url(self) -> None:
        assert is_wecom_bot_hook_url(
            "https://QyApi.Weixin.QQ.com/CGI-BIN/webhook/send?key=k1"
        )

    def test_feishu_url_rejected(self) -> None:
        assert not is_wecom_bot_hook_url(
            "https://open.feishu.cn/open-apis/bot/v2/hook/abc"
        )

    def test_slack_url_rejected(self) -> None:
        assert not is_wecom_bot_hook_url("https://hooks.slack.com/services/T/B/X")

    def test_dingtalk_url_rejected(self) -> None:
        assert not is_wecom_bot_hook_url(
            "https://oapi.dingtalk.com/robot/send?access_token=abc"
        )

    def test_empty_string(self) -> None:
        assert not is_wecom_bot_hook_url("")

    def test_arbitrary_string(self) -> None:
        assert not is_wecom_bot_hook_url("not-a-url-at-all")


# --- _build_wecom_markdown ---


class TestBuildWecomMarkdown:
    def test_success_with_output(self) -> None:
        job = _make_job(name="weekly")
        result = JobResult(success=True, output="请提交周报")
        md = _build_wecom_markdown(job, result)
        assert "**[weekly]**" in md
        assert "✓ 成功" in md
        assert "请提交周报" in md

    def test_failure_with_error(self) -> None:
        job = _make_job(name="monitor")
        result = JobResult(success=False, output="", error="Connection timeout")
        md = _build_wecom_markdown(job, result)
        assert "✗ 失败" in md
        assert "Connection timeout" in md

    def test_fallback_to_job_id_when_name_empty(self) -> None:
        job = _make_job(name="", job_id="cron-12345")
        result = JobResult(success=True, output="done")
        md = _build_wecom_markdown(job, result)
        assert "**[cron-12345]**" in md

    def test_fallback_to_job_id_when_name_whitespace(self) -> None:
        job = _make_job(name="   ", job_id="cron-99")
        result = JobResult(success=True, output="done")
        md = _build_wecom_markdown(job, result)
        assert "**[cron-99]**" in md

    def test_default_success_text_when_no_output_no_error(self) -> None:
        job = _make_job(name="task")
        result = JobResult(success=True, output="")
        md = _build_wecom_markdown(job, result)
        assert "定时任务已完成。" in md

    def test_default_failure_text_when_no_output_no_error(self) -> None:
        job = _make_job(name="task")
        result = JobResult(success=False, output="")
        md = _build_wecom_markdown(job, result)
        assert "定时任务执行失败。" in md

    def test_output_combined_with_error(self) -> None:
        job = _make_job(name="check")
        result = JobResult(success=False, output="部分完成", error="步骤3超时")
        md = _build_wecom_markdown(job, result)
        assert "部分完成" in md
        assert "步骤3超时" in md
        assert "> Error:" in md

    def test_content_truncated_at_4000_chars(self) -> None:
        job = _make_job(name="big")
        long_output = "A" * 5000
        result = JobResult(success=True, output=long_output)
        md = _build_wecom_markdown(job, result)
        assert len(md) == 4000

    def test_error_truncated_at_500_chars(self) -> None:
        job = _make_job(name="err")
        long_error = "E" * 1000
        result = JobResult(success=False, output="", error=long_error)
        md = _build_wecom_markdown(job, result)
        # error[:500] is used, so only first 500 chars of error appear
        assert "E" * 500 in md
        assert "E" * 501 not in md

    def test_whitespace_only_output_treated_as_empty(self) -> None:
        job = _make_job(name="ws")
        result = JobResult(success=True, output="   \n\t  ")
        md = _build_wecom_markdown(job, result)
        assert "定时任务已完成。" in md

    def test_none_output_treated_as_empty(self) -> None:
        job = _make_job(name="n")
        result = JobResult(success=True, output=None)
        md = _build_wecom_markdown(job, result)
        assert "定时任务已完成。" in md


# --- deliver_wecom_bot_webhook ---


class TestDeliverWecomBotWebhook:
    @pytest.mark.asyncio
    async def test_posts_markdown_payload(self) -> None:
        job = _make_job()
        result = JobResult(success=True, output="请大家提交本周工作周报")
        mock_client = _mock_httpx_success()

        with patch(
            "app.core.cron.adapters.wecom_bot_webhook.httpx.AsyncClient",
            return_value=mock_client,
        ):
            await deliver_wecom_bot_webhook(job, result)

        mock_client.post.assert_awaited_once()
        call_kwargs = mock_client.post.await_args.kwargs
        body = json.loads(call_kwargs["content"])
        assert body["msgtype"] == "markdown"
        assert "请大家提交本周工作周报" in body["markdown"]["content"]
        assert "weekly-report" in body["markdown"]["content"]

    @pytest.mark.asyncio
    async def test_error_result(self) -> None:
        job = _make_job(name="monitor")
        result = JobResult(success=False, output="", error="Connection timeout")
        mock_client = _mock_httpx_success()

        with patch(
            "app.core.cron.adapters.wecom_bot_webhook.httpx.AsyncClient",
            return_value=mock_client,
        ):
            await deliver_wecom_bot_webhook(job, result)

        call_kwargs = mock_client.post.await_args.kwargs
        body = json.loads(call_kwargs["content"])
        assert "Connection timeout" in body["markdown"]["content"]
        assert "失败" in body["markdown"]["content"]

    @pytest.mark.asyncio
    async def test_raises_value_error_on_empty_url(self) -> None:
        job = _make_job(target="")
        result = JobResult(success=True, output="test")
        with pytest.raises(ValueError, match="URL missing"):
            await deliver_wecom_bot_webhook(job, result)

    @pytest.mark.asyncio
    async def test_raises_value_error_on_whitespace_url(self) -> None:
        job = _make_job(target="   ")
        result = JobResult(success=True, output="test")
        with pytest.raises(ValueError, match="URL missing"):
            await deliver_wecom_bot_webhook(job, result)

    @pytest.mark.asyncio
    async def test_raises_on_http_4xx(self) -> None:
        job = _make_job()
        result = JobResult(success=True, output="test")

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "app.core.cron.adapters.wecom_bot_webhook.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("app.core.cron.adapters.wecom_bot_webhook.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(RuntimeError, match="returned 403"),
        ):
            await deliver_wecom_bot_webhook(job, result)

    @pytest.mark.asyncio
    async def test_raises_on_wecom_errcode_nonzero(self) -> None:
        job = _make_job()
        result = JobResult(success=True, output="test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errcode": 93000, "errmsg": "invalid webhook url"}
        mock_response.text = '{"errcode": 93000}'
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "app.core.cron.adapters.wecom_bot_webhook.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("app.core.cron.adapters.wecom_bot_webhook.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(RuntimeError, match="errcode=93000"),
        ):
            await deliver_wecom_bot_webhook(job, result)

    @pytest.mark.asyncio
    async def test_non_json_response_succeeds(self) -> None:
        job = _make_job()
        result = JobResult(success=True, output="test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("", "", 0)
        mock_response.text = "OK"
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.core.cron.adapters.wecom_bot_webhook.httpx.AsyncClient",
            return_value=mock_client,
        ):
            await deliver_wecom_bot_webhook(job, result)

    @pytest.mark.asyncio
    async def test_retry_on_transient_error_then_success(self) -> None:
        job = _make_job()
        result = JobResult(success=True, output="test")

        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {"errcode": 0, "errmsg": "ok"}
        mock_response_ok.text = '{"errcode":0}'

        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        mock_response_500.text = "Internal Server Error"

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=[mock_response_500, mock_response_ok])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "app.core.cron.adapters.wecom_bot_webhook.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("app.core.cron.adapters.wecom_bot_webhook.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await deliver_wecom_bot_webhook(job, result)

        assert mock_client.post.await_count == 2
        mock_sleep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_last_error(self) -> None:
        job = _make_job()
        result = JobResult(success=True, output="test")

        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        mock_response_500.text = "Internal Server Error"
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response_500)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "app.core.cron.adapters.wecom_bot_webhook.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("app.core.cron.adapters.wecom_bot_webhook.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(RuntimeError, match="returned 500"),
        ):
            await deliver_wecom_bot_webhook(job, result)

        # 1 initial + 2 retries = 3 attempts
        assert mock_client.post.await_count == 3

    @pytest.mark.asyncio
    async def test_content_type_header_is_json_utf8(self) -> None:
        job = _make_job()
        result = JobResult(success=True, output="中文内容")
        mock_client = _mock_httpx_success()

        with patch(
            "app.core.cron.adapters.wecom_bot_webhook.httpx.AsyncClient",
            return_value=mock_client,
        ):
            await deliver_wecom_bot_webhook(job, result)

        call_kwargs = mock_client.post.await_args.kwargs
        assert call_kwargs["headers"]["Content-Type"] == "application/json; charset=utf-8"

    @pytest.mark.asyncio
    async def test_json_body_not_ascii_escaped(self) -> None:
        job = _make_job(name="中文任务")
        result = JobResult(success=True, output="中文输出")
        mock_client = _mock_httpx_success()

        with patch(
            "app.core.cron.adapters.wecom_bot_webhook.httpx.AsyncClient",
            return_value=mock_client,
        ):
            await deliver_wecom_bot_webhook(job, result)

        call_kwargs = mock_client.post.await_args.kwargs
        body_str = call_kwargs["content"]
        assert "中文任务" in body_str
        assert "\\u" not in body_str


# --- channel_delivery routing ---


class TestChannelDeliveryRouting:
    @pytest.mark.asyncio
    async def test_routes_webhook_channel_with_wecom_url(self) -> None:
        from app.core.cron.adapters.channel_delivery import ChannelResultDelivery

        job = _make_job(channel="webhook")
        result = JobResult(success=True, output="晨会提醒")

        delivery = ChannelResultDelivery()
        with patch(
            "app.core.cron.adapters.channel_delivery.deliver_wecom_bot_webhook",
            new_callable=AsyncMock,
        ) as mock_deliver:
            await delivery.deliver(job, result)
            mock_deliver.assert_awaited_once_with(job, result)

    @pytest.mark.asyncio
    async def test_routes_wecom_channel_with_wecom_url(self) -> None:
        """Bug fix: channel='wecom' + wecom bot URL should route to bot webhook."""
        from app.core.cron.adapters.channel_delivery import ChannelResultDelivery

        job = _make_job(channel="wecom")
        result = JobResult(success=True, output="提醒")

        delivery = ChannelResultDelivery()
        with patch(
            "app.core.cron.adapters.channel_delivery.deliver_wecom_bot_webhook",
            new_callable=AsyncMock,
        ) as mock_deliver:
            await delivery.deliver(job, result)
            mock_deliver.assert_awaited_once_with(job, result)

    @pytest.mark.asyncio
    async def test_webhook_channel_with_non_wecom_url_uses_generic(self) -> None:
        from app.core.cron.adapters.channel_delivery import ChannelResultDelivery

        job = _make_job(channel="webhook", target="https://example.com/hook")
        result = JobResult(success=True, output="data")

        delivery = ChannelResultDelivery()
        with patch(
            "app.core.cron.adapters.channel_delivery._webhook_delivery",
        ) as mock_wd:
            mock_wd.deliver = AsyncMock()
            await delivery.deliver(job, result)
            mock_wd.deliver.assert_awaited_once_with(job, result)

    @pytest.mark.asyncio
    async def test_silent_channel_does_nothing(self) -> None:
        from app.core.cron.adapters.channel_delivery import ChannelResultDelivery

        job = _make_job(channel="silent")
        result = JobResult(success=True, output="ignored")

        delivery = ChannelResultDelivery()
        with patch(
            "app.core.cron.adapters.channel_delivery.deliver_wecom_bot_webhook",
            new_callable=AsyncMock,
        ) as mock_deliver:
            await delivery.deliver(job, result)
            mock_deliver.assert_not_awaited()
