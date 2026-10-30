"""TelegramChannel diagnostics: the issues the status page lists for configuration and runtime health."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api_core import TelegramApiError
from app.channels.types import ChannelStatus, IssueKind, IssueSeverity
from tests.channels.providers.telegram.telegram_channel_factories import make_channel


class TestTelegramDiagnostics:
    def test_collect_issues_no_token(self) -> None:
        ch = TelegramChannel(bot_token="")
        issues = ch.collect_issues()
        assert any("token" in i.message.lower() for i in issues)

    def test_collect_issues_http_webhook(self) -> None:
        ch = TelegramChannel(bot_token="tok", webhook_url="http://insecure.com/wh")
        issues = ch.collect_issues()
        assert any("HTTPS" in i.message for i in issues)

    def test_collect_issues_healthy(self) -> None:
        ch = make_channel()
        assert ch.collect_issues() == []

    def test_collect_issues_degraded(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.DEGRADED
        issues = ch.collect_issues()
        assert any("degraded" in i.message.lower() for i in issues)

    def test_collect_issues_degraded_polling_does_not_blame_the_webhook(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.DEGRADED
        issues = ch.collect_issues()
        assert [i.message for i in issues] == ["Channel running in degraded mode: polling keeps failing."]
        assert all("webhook" not in f"{i.message} {i.fix}".lower() for i in issues)

    def test_collect_issues_degraded_webhook_points_at_the_webhook(self) -> None:
        ch = TelegramChannel(bot_token="tok", webhook_url="https://example.com/wh")
        ch._status = ChannelStatus.DEGRADED
        issues = ch.collect_issues()
        assert [i.message for i in issues] == ["Webhook setup failed. Channel running in degraded mode."]
        assert "TELEGRAM_WEBHOOK_URL" in issues[0].fix

    def test_collect_issues_failed_start_is_visible(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.ERROR
        issues = ch.collect_issues()
        assert [(i.kind, i.severity, i.message) for i in issues] == [
            (IssueKind.RUNTIME, IssueSeverity.ERROR, "Channel in ERROR state; check credentials and network")
        ]

    def test_collect_issues_error_with_a_recorded_cause_reports_only_the_cause(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.ERROR
        ch.health.record_failure("Polling conflict: another process is polling this bot token.")
        issues = ch.collect_issues()
        assert [i.message for i in issues] == ["Polling conflict: another process is polling this bot token."]

    def test_collect_issues_health_error(self) -> None:
        ch = make_channel()
        ch.health.record_failure("Connection timeout")
        issues = ch.collect_issues()
        assert any("timeout" in i.message.lower() for i in issues)


class TestTelegramFailedStartCause:
    """A failed start keeps why it failed, so the status page can tell a revoked token from a network that is down."""

    @staticmethod
    async def _start_with_getme(ch: TelegramChannel, outcome: Exception | dict[str, object]) -> None:
        ch._client = MagicMock()
        ch._client.get_me = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
        with (
            patch.object(ch, "_register_commands", new_callable=AsyncMock),
            patch.object(ch, "_cleanup_webhook", new_callable=AsyncMock),
            patch.object(ch, "_poll_loop", new_callable=AsyncMock),
        ):
            await ch.start()
        if ch._poll_task is not None:
            ch._poll_task.cancel()
            try:
                await ch._poll_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_a_refused_token_is_named_with_a_fix_that_is_about_the_token(self) -> None:
        ch = make_channel()
        await self._start_with_getme(ch, TelegramApiError(401, "Unauthorized"))

        [issue] = ch.collect_issues()

        assert (issue.kind, issue.severity, issue.message) == (
            IssueKind.CONFIG,
            IssueSeverity.ERROR,
            "Telegram rejected the bot token.",
        )
        assert "BotFather" in issue.fix

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "failure",
        [
            httpx.ConnectError("All connection attempts failed"),
            httpx.ReadTimeout("timed out"),
            TelegramApiError(429, "Too Many Requests"),
        ],
    )
    async def test_an_unreachable_bot_api_is_named_with_a_fix_about_the_network_and_proxy(self, failure: Exception) -> None:
        ch = make_channel()
        await self._start_with_getme(ch, failure)

        [issue] = ch.collect_issues()

        assert (issue.kind, issue.severity, issue.message) == (
            IssueKind.RUNTIME,
            IssueSeverity.ERROR,
            "Telegram Bot API could not be reached.",
        )
        assert "proxy" in issue.fix.lower()

    @pytest.mark.asyncio
    async def test_the_cause_is_a_category_and_never_the_raw_error_text(self) -> None:
        ch = make_channel()
        token = ch._token
        await self._start_with_getme(ch, httpx.ConnectError(f"failed for https://api.telegram.org/bot{token}/getMe"))

        text = " ".join(f"{i.message} {i.fix}" for i in ch.collect_issues())

        assert token not in text
        assert "api.telegram.org" not in text

    @pytest.mark.asyncio
    async def test_a_later_successful_start_clears_the_cause(self) -> None:
        ch = make_channel()
        await self._start_with_getme(ch, httpx.ConnectError("All connection attempts failed"))
        assert ch._status == ChannelStatus.ERROR

        await self._start_with_getme(ch, {"id": 123, "username": "testbot"})

        assert ch._status == ChannelStatus.RUNNING
        assert ch.collect_issues() == []
        # An ERROR state that is not a failed start must not borrow the earlier cause.
        ch._status = ChannelStatus.ERROR
        assert [i.message for i in ch.collect_issues()] == ["Channel in ERROR state; check credentials and network"]

    @pytest.mark.asyncio
    async def test_a_later_failure_of_another_kind_replaces_the_cause(self) -> None:
        ch = make_channel()
        await self._start_with_getme(ch, httpx.ConnectError("All connection attempts failed"))
        await self._start_with_getme(ch, TelegramApiError(401, "Unauthorized"))

        assert [i.message for i in ch.collect_issues()] == ["Telegram rejected the bot token."]
