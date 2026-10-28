"""Matrix channel diagnostics: what is missing or wrong with the configuration, the dependencies and the login.

[INPUT]
- channels.providers.matrix.crypto::check_e2ee_deps (POS: whether the optional E2EE dependencies are installed)
- channels.types::ChannelIssue, ChannelStatus, IssueKind, IssueSeverity (POS: structured channel diagnostics)

[OUTPUT]
- collect_matrix_issues: the issues a Matrix channel in this configuration and state reports

[POS]
Pure diagnosis for ``MatrixChannel.collect_issues``: it reads the channel's settings and state, never the network.
"""

from __future__ import annotations

from app.channels.types import ChannelIssue, ChannelStatus, IssueKind, IssueSeverity


def collect_matrix_issues(
    *,
    homeserver: str,
    has_credentials: bool,
    mautrix_available: bool,
    encryption: bool,
    device_id: str,
    status: ChannelStatus,
) -> list[ChannelIssue]:
    """Issues for a Matrix channel; without a homeserver nothing else can be judged, so that one is reported alone."""
    if not homeserver:
        return [ChannelIssue(kind=IssueKind.CONFIG, severity=IssueSeverity.ERROR, message="homeserver URL not configured.")]

    issues: list[ChannelIssue] = []
    if not has_credentials:
        issues.append(
            ChannelIssue(
                kind=IssueKind.CONFIG,
                severity=IssueSeverity.ERROR,
                message="access_token or password not configured.",
            )
        )

    if not mautrix_available:
        issues.append(
            ChannelIssue(
                kind=IssueKind.DEPENDENCY,
                severity=IssueSeverity.ERROR,
                message="mautrix not installed. Run: uv sync --extra matrix",
                fix="uv sync --extra matrix",
            )
        )

    if encryption:
        from app.channels.providers.matrix.crypto import check_e2ee_deps

        if not check_e2ee_deps():
            issues.append(
                ChannelIssue(
                    kind=IssueKind.DEPENDENCY,
                    severity=IssueSeverity.ERROR,
                    message=(
                        "E2EE enabled but mautrix[encryption] not installed. "
                        "Run: uv sync --extra matrix --extra matrix-e2ee "
                        "(requires libolm C library)"
                    ),
                    fix="uv sync --extra matrix --extra matrix-e2ee",
                )
            )
        elif not device_id:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message=(
                        "device_id not set. E2EE sessions won't persist across "
                        "restarts. Set a stable device_id for key persistence."
                    ),
                )
            )

    if status == ChannelStatus.ERROR:
        issues.append(
            ChannelIssue(
                kind=IssueKind.AUTH,
                severity=IssueSeverity.ERROR,
                message="Matrix authentication failed. Check credentials.",
            )
        )
    return issues
