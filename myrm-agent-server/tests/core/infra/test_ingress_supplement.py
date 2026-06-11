"""Tests for supplement_ingress_issues channel warning injection."""

from app.channels.types import ChannelIssue, IssueKind, IssueSeverity
from app.core.infra.ingress_requirement import (
    IngressRequirementSnapshot,
    supplement_ingress_issues,
)


def test_supplement_adds_warning_for_inbound_without_ingress() -> None:
    snapshot = IngressRequirementSnapshot(
        required=True,
        has_public_ingress=False,
        reasons=("channel:line",),
        channels={"line": "inbound"},
    )
    issues = supplement_ingress_issues("line", [], snapshot)
    assert len(issues) == 1
    assert issues[0].kind == IssueKind.CONFIG
    assert issues[0].severity == IssueSeverity.WARNING
    assert "Ingress" in issues[0].message


def test_supplement_skips_when_ingress_configured() -> None:
    snapshot = IngressRequirementSnapshot(
        required=False,
        has_public_ingress=True,
        channels={"line": "inbound"},
    )
    existing = [
        ChannelIssue(
            kind=IssueKind.CONFIG,
            severity=IssueSeverity.WARNING,
            message="Other issue",
        )
    ]
    assert supplement_ingress_issues("line", existing, snapshot) == existing


def test_supplement_skips_outbound_channel() -> None:
    snapshot = IngressRequirementSnapshot(
        required=False,
        has_public_ingress=False,
        channels={"feishu": "outbound"},
    )
    assert supplement_ingress_issues("feishu", [], snapshot) == []


def test_supplement_avoids_duplicate_ingress_warning() -> None:
    snapshot = IngressRequirementSnapshot(
        required=True,
        has_public_ingress=False,
        channels={"teams": "inbound"},
    )
    existing = [
        ChannelIssue(
            kind=IssueKind.CONFIG,
            severity=IssueSeverity.WARNING,
            message="Public Ingress is required for webhook",
        )
    ]
    assert supplement_ingress_issues("teams", existing, snapshot) == existing
