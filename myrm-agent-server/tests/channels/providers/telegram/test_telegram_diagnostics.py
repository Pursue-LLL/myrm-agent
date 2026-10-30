"""TelegramChannel diagnostics: the issues the status page lists for configuration and runtime health."""

from __future__ import annotations

from app.channels.providers.telegram import TelegramChannel
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
