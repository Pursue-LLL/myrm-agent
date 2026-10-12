"""GitHub Channel — posts agent messages as comments on issues and pull requests.

Outbound only: the recipient is ``owner/repo#number`` and the comment goes out through the REST API
(rendered as multiple chunks when it exceeds GitHub's comment limit). Nothing is received from GitHub.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.core.exceptions::ChannelSendError (POS: Channel exception hierarchy for precise retry and error handling.)
- channels.providers.github.helpers (POS: GitHub REST API comment client)

[OUTPUT]
- GitHubChannel: outbound-only GitHub Channel

[POS]
GitHub integration: REST API comment delivery, authenticated with a personal access token.
Because it receives nothing it needs no public Ingress.
"""

from __future__ import annotations

import logging

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.github.helpers import post_issue_comment
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
    RenderStyle,
    ToolSummaryDisplay,
)

logger = logging.getLogger(__name__)

_MAX_COMMENT_LENGTH = 65536


class GitHubChannel(BaseChannel):
    """Outbound-only channel: Agent output is posted as a GitHub comment on the target issue/PR."""

    name = "github"
    credential_spec = credential_spec(
        "githubCredentials",
        personal_access_token=credential_field(
            "personalAccessToken",
            "GITHUB_TOKEN",
            help_text="Personal Access Token with repo scope for posting comments",
        ),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=False,
        file_upload=False,
        max_text_length=_MAX_COMMENT_LENGTH,
    )
    render_style = RenderStyle(
        format="markdown",
        use_emoji=True,
        max_text_length=_MAX_COMMENT_LENGTH,
        supports_code_fence=True,
        supports_links=True,
        supports_tables=True,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    def __init__(self, personal_access_token: str = "") -> None:
        super().__init__()
        self._token = personal_access_token

    async def start(self) -> None:
        """No connection to hold: the REST API is only called when sending."""
        self._set_connected(True)
        logger.info("GitHubChannel: started")

    async def stop(self) -> None:
        self._set_connected(False)
        logger.info("GitHubChannel: stopped")

    # -- Outbound: Post comment ----------------------------------------------

    async def send(self, msg: OutboundMessage) -> str | None:
        """Post Agent response as a comment on the originating GitHub issue/PR."""
        if not self._token:
            self.health.record_failure("No token")
            raise ChannelSendError("GitHub token is not configured", channel=self.name, retriable=False)

        recipient = msg.recipient_id or ""
        repo, number = self._parse_recipient(recipient)
        if not repo or number is None:
            self.health.record_failure("Invalid recipient")
            raise ChannelSendError(f"GitHub recipient '{recipient}' is not owner/repo#number", channel=self.name, retriable=False)

        chunks = render(msg, self.render_style)
        if not chunks:
            return None

        last_id: str | None = None
        for chunk in chunks:
            try:
                await post_issue_comment(self._token, repo, number, chunk)
            except ChannelSendError as exc:
                self.health.record_failure(str(exc))
                raise
            last_id = f"gh-comment-{repo}-{number}"

        self.health.record_success()
        return last_id

    @staticmethod
    def _parse_recipient(recipient_id: str) -> tuple[str, int | None]:
        """Parse 'owner/repo#123' format into (repo, number)."""
        if "#" not in recipient_id:
            return "", None
        parts = recipient_id.rsplit("#", 1)
        if len(parts) != 2:
            return "", None
        repo = parts[0]
        try:
            number = int(parts[1])
        except ValueError:
            return "", None
        return repo, number

    # -- Diagnostics ---------------------------------------------------------

    async def health_check(self) -> bool:
        """Healthy while the channel is running, including when degraded."""
        return self._status in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED)

    def collect_issues(self) -> list[ChannelIssue]:
        """Report configuration issues."""
        if self._token:
            return []
        return [
            ChannelIssue(
                kind=IssueKind.CONFIG,
                severity=IssueSeverity.WARNING,
                message="Personal Access Token not configured — cannot post comments",
                fix="Set personalAccessToken in GitHub channel credentials",
            )
        ]
