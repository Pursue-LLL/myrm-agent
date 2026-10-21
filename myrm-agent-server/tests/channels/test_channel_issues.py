"""Tests for ChannelIssue types and BaseChannel.collect_issues() default."""

from __future__ import annotations

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.types import (
    ChannelIssue,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
)


class HealthyChannel(BaseChannel):
    name = "healthy"

    async def send(self, msg: OutboundMessage) -> str | None:
        pass


class FailingChannel(BaseChannel):
    name = "failing"

    def __init__(self) -> None:
        super().__init__()
        self.health.record_failure("connection timeout")

    async def send(self, msg: OutboundMessage) -> str | None:
        pass


class CustomIssueChannel(BaseChannel):
    name = "custom"

    def __init__(self, *, configured: bool = True) -> None:
        super().__init__()
        self._configured = configured

    async def send(self, msg: OutboundMessage) -> str | None:
        pass

    def collect_issues(self) -> list[ChannelIssue]:
        if not self._configured:
            return [
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="API key not set.",
                    fix="Configure in Settings → Channels.",
                )
            ]
        return []


class TestChannelIssueTypes:
    def test_frozen(self) -> None:
        issue = ChannelIssue(kind=IssueKind.AUTH, severity=IssueSeverity.ERROR, message="test")
        with pytest.raises(AttributeError):
            issue.message = "changed"  # type: ignore[misc]

    def test_default_fix(self) -> None:
        issue = ChannelIssue(kind=IssueKind.RUNTIME, severity=IssueSeverity.WARNING, message="x")
        assert issue.fix == ""

    def test_kind_values(self) -> None:
        assert IssueKind.AUTH == "auth"
        assert IssueKind.CONFIG == "config"
        assert IssueKind.PERMISSIONS == "permissions"
        assert IssueKind.RUNTIME == "runtime"

    def test_severity_values(self) -> None:
        assert IssueSeverity.ERROR == "error"
        assert IssueSeverity.WARNING == "warning"
        assert IssueSeverity.INFO == "info"


class TestBaseChannelCollectIssues:
    def test_healthy_returns_empty(self) -> None:
        ch = HealthyChannel()
        assert ch.collect_issues() == []

    def test_failing_returns_runtime_issue(self) -> None:
        ch = FailingChannel()
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.RUNTIME
        assert issues[0].severity == IssueSeverity.ERROR
        assert "connection timeout" in issues[0].message

    def test_custom_override(self) -> None:
        ch = CustomIssueChannel(configured=False)
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.CONFIG
        assert issues[0].fix == "Configure in Settings → Channels."

    def test_custom_healthy(self) -> None:
        ch = CustomIssueChannel(configured=True)
        assert ch.collect_issues() == []


class TestGatewayCollectAllIssues:
    def test_empty_when_all_healthy(self) -> None:
        gw = ChannelGateway()
        gw.register(HealthyChannel())
        result = gw.collect_all_issues()
        assert result == {}

    def test_returns_issues_for_failing(self) -> None:
        gw = ChannelGateway()
        gw.register(HealthyChannel())
        gw.register(FailingChannel())
        result = gw.collect_all_issues()
        assert "healthy" not in result
        assert "failing" in result
        assert len(result["failing"]) == 1

    def test_mixed_channels(self) -> None:
        gw = ChannelGateway()
        gw.register(HealthyChannel())
        gw.register(FailingChannel())
        gw.register(CustomIssueChannel(configured=False))
        result = gw.collect_all_issues()
        assert len(result) == 2
        assert "failing" in result
        assert "custom" in result
