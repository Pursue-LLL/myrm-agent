"""End-to-end test: issues flow from Channel → Gateway → API schema shape."""

from __future__ import annotations

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.types import (
    ChannelIssue,
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
)


class NoTokenChannel(BaseChannel):
    """Simulates a channel with missing credentials."""

    name = "no_token"

    def __init__(self) -> None:
        super().__init__()
        self._token = ""

    async def send(self, msg: OutboundMessage) -> str | None:
        pass

    def collect_issues(self) -> list[ChannelIssue]:
        if not self._token:
            return [
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="Token not configured.",
                    fix="Set TOKEN env var.",
                )
            ]
        return []


class DegradedChannel(BaseChannel):
    """Simulates a channel with auth failure + runtime error."""

    name = "degraded"

    def __init__(self) -> None:
        super().__init__()
        self._status = ChannelStatus.DEGRADED
        self.health.record_failure("auth handshake failed")

    async def send(self, msg: OutboundMessage) -> str | None:
        pass

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if self._status == ChannelStatus.DEGRADED:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.AUTH,
                    severity=IssueSeverity.ERROR,
                    message="Auth handshake failed.",
                    fix="Re-authenticate.",
                )
            )
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.WARNING,
                    message=self.health.last_error,
                )
            )
        return issues


class HealthyChannel(BaseChannel):
    name = "healthy"

    async def send(self, msg: OutboundMessage) -> str | None:
        pass


class TestIssuesE2E:
    def test_gateway_aggregates_issues_from_multiple_channels(self) -> None:
        gw = ChannelGateway()
        gw.register(HealthyChannel())
        gw.register(NoTokenChannel())
        gw.register(DegradedChannel())

        all_issues = gw.collect_all_issues()

        assert "healthy" not in all_issues
        assert "no_token" in all_issues
        assert "degraded" in all_issues

        no_token_issues = all_issues["no_token"]
        assert len(no_token_issues) == 1
        assert no_token_issues[0].kind == IssueKind.CONFIG
        assert no_token_issues[0].severity == IssueSeverity.ERROR
        assert no_token_issues[0].fix == "Set TOKEN env var."

        degraded_issues = all_issues["degraded"]
        assert len(degraded_issues) == 2
        kinds = {i.kind for i in degraded_issues}
        assert kinds == {IssueKind.AUTH, IssueKind.RUNTIME}

    def test_gateway_status_and_issues_aligned(self) -> None:
        """Status map and issues map should reference the same channel names."""
        gw = ChannelGateway()
        gw.register(HealthyChannel())
        gw.register(DegradedChannel())

        statuses = gw.get_status()
        all_issues = gw.collect_all_issues()

        for channel_name in all_issues:
            assert channel_name in statuses

    def test_issue_immutability(self) -> None:
        """Issues are frozen — verify they can't be tampered with after collection."""
        gw = ChannelGateway()
        gw.register(NoTokenChannel())
        all_issues = gw.collect_all_issues()
        issue = all_issues["no_token"][0]

        with pytest.raises(AttributeError):
            issue.message = "hacked"  # type: ignore[misc]

    def test_default_collect_issues_with_health_error(self) -> None:
        """BaseChannel default uses health.last_error."""
        ch = HealthyChannel()
        assert ch.collect_issues() == []

        ch.health.record_failure("timeout")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.RUNTIME
        assert "timeout" in issues[0].message

    def test_default_collect_issues_clears_after_recovery(self) -> None:
        """After health recovery, default collect_issues returns empty."""
        ch = HealthyChannel()
        ch.health.record_failure("timeout")
        assert len(ch.collect_issues()) == 1

        ch.health.record_success()
        assert ch.collect_issues() == []

    def test_api_schema_shape(self) -> None:
        """Verify issues can be serialized to dict matching API schema."""
        issue = ChannelIssue(
            kind=IssueKind.AUTH,
            severity=IssueSeverity.ERROR,
            message="Token expired.",
            fix="Refresh token.",
        )
        as_dict = {
            "kind": issue.kind.value,
            "severity": issue.severity.value,
            "message": issue.message,
            "fix": issue.fix,
        }
        assert as_dict == {
            "kind": "auth",
            "severity": "error",
            "message": "Token expired.",
            "fix": "Refresh token.",
        }
