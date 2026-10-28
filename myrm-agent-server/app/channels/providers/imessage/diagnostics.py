"""iMessage channel diagnostics: what is missing or wrong with the configuration and the BlueBubbles connection.

[INPUT]
- channels.types::ChannelIssue, ChannelStatus, IssueKind, IssueSeverity (POS: structured channel diagnostics)

[OUTPUT]
- collect_imessage_issues: the issues an iMessage channel in this configuration and state reports

[POS]
Pure diagnosis for ``IMessageChannel.collect_issues``: it reads the channel's settings and state, never the network.
"""

from __future__ import annotations

from app.channels.types import ChannelIssue, ChannelStatus, IssueKind, IssueSeverity


def collect_imessage_issues(
    *,
    api_url: str,
    password: str,
    status: ChannelStatus,
    last_error: str,
    private_api_available: bool,
    helper_connected: bool,
) -> list[ChannelIssue]:
    """The issues a channel with these settings and this connection state reports, most fundamental first."""
    issues: list[ChannelIssue] = []
    if not api_url:
        issues.append(
            ChannelIssue(
                kind=IssueKind.CONFIG,
                severity=IssueSeverity.ERROR,
                message="BlueBubbles API URL not configured",
            )
        )
    if not password:
        issues.append(
            ChannelIssue(
                kind=IssueKind.CONFIG,
                severity=IssueSeverity.WARNING,
                message="BlueBubbles password not set; webhook authentication disabled",
            )
        )
    if status == ChannelStatus.ERROR:
        issues.append(
            ChannelIssue(
                kind=IssueKind.RUNTIME,
                severity=IssueSeverity.ERROR,
                message="Channel in ERROR state; check BlueBubbles server connectivity",
            )
        )
    if last_error:
        issues.append(ChannelIssue(kind=IssueKind.RUNTIME, severity=IssueSeverity.WARNING, message=last_error))
    if status == ChannelStatus.RUNNING:
        if not private_api_available:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message="BlueBubbles Private API is disabled; reactions, typing, and read receipts are unavailable",
                )
            )
        elif not helper_connected:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.WARNING,
                    message="BlueBubbles Private API Helper is disconnected; advanced messaging features may be limited",
                )
            )
    return issues
