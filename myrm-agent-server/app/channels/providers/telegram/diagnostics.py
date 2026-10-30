"""Telegram channel diagnostics — configuration and runtime issues for the channel status page.

Mixin providing ``collect_issues`` used by TelegramChannel. The WebUI matches these English messages by pattern to
show localized copy, so a reworded message needs its pattern updated there.

[INPUT]
- channels.types::ChannelIssue, ChannelStatus, IssueKind, IssueSeverity

[OUTPUT]
- TelegramDiagnosticsMixin: collect_issues

[POS]
Telegram diagnostics mixin. Turns the bot token, webhook URL, channel status and the last health error into the
issues the status page lists, each with a kind, a severity and, where one exists, a fix.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.channels.types import ChannelIssue, ChannelStatus, IssueKind, IssueSeverity

if TYPE_CHECKING:
    from app.channels.types import ChannelHealth


class TelegramDiagnosticsMixin:
    """Mixin providing Telegram channel diagnostics.

    Requires the host class to have:
    - self._token, self._webhook_url, self._status: ChannelStatus
    - self.health, self.is_webhook_mode, self._redact(text)
    """

    _token: str
    _webhook_url: str
    _status: ChannelStatus

    if TYPE_CHECKING:
        # Provided by BaseChannel and the host channel; declared with their signatures for the type checker.
        health: ChannelHealth

        @property
        def is_webhook_mode(self) -> bool: ...
        def _redact(self, text: str) -> str: ...

    def collect_issues(self) -> list[ChannelIssue]:
        """Diagnostics for Telegram channel configuration and runtime health."""
        issues: list[ChannelIssue] = []
        if not self._token:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="No bot token configured.",
                    fix="Set TELEGRAM_BOT_TOKEN environment variable or configure in Settings → Channels → Telegram.",
                )
            )
            return issues
        if self._webhook_url and not self._webhook_url.startswith("https://"):
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message="Webhook URL must use HTTPS. Telegram rejects non-HTTPS URLs.",
                    fix="Update TELEGRAM_WEBHOOK_URL to use https://.",
                )
            )
        if self._status == ChannelStatus.ERROR and not self.health.last_error:
            # A failed start records no health error; when one exists, the runtime issue below names the cause.
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message="Channel in ERROR state; check credentials and network",
                )
            )
        if self._status == ChannelStatus.DEGRADED:
            if self.is_webhook_mode:
                issues.append(
                    ChannelIssue(
                        kind=IssueKind.CONFIG,
                        severity=IssueSeverity.WARNING,
                        message="Webhook setup failed. Channel running in degraded mode.",
                        fix="Check TELEGRAM_WEBHOOK_URL is reachable and retry, or switch to polling mode.",
                    )
                )
            else:
                issues.append(
                    ChannelIssue(
                        kind=IssueKind.RUNTIME,
                        severity=IssueSeverity.WARNING,
                        message="Channel running in degraded mode: polling keeps failing.",
                    )
                )
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message=self._redact(self.health.last_error),
                )
            )
        return issues
