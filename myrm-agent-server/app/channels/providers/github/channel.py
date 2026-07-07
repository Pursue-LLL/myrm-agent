"""GitHub Channel — webhook inbound + REST API comment outbound.

Inbound: receives GitHub webhook POSTs, verifies X-Hub-Signature-256,
         parses event payload, emits InboundMessage to Router.
Outbound: posts comments to GitHub issues/PRs via REST API.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.providers.github.event_parser (POS: Structured event parsing)
- channels.providers.github.helpers (POS: Signature verification + API)

[OUTPUT]
- GitHubChannel: GitHub webhook bidirectional Channel

[POS]
GitHub integration: webhook inbound for Issue/PR/Push/Review events,
REST API outbound for comment delivery. Supports PAT authentication.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.providers.github.event_parser import (
    format_event_as_markdown,
    parse_github_event,
)
from app.channels.providers.github.helpers import (
    post_issue_comment,
    verify_github_signature,
)
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    InboundMessage,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
    RenderStyle,
    ToolSummaryDisplay,
)

logger = logging.getLogger(__name__)

_MAX_COMMENT_LENGTH = 65536


class GitHubChannel(BaseChannel):
    """GitHub webhook-based channel for Issue/PR/Push event triggers.

    Inbound: GitHub Webhook → verify signature → parse event → emit to Router.
    Outbound: Agent response → post as GitHub comment on the originating issue/PR.
    """

    name = "github"
    credential_spec = credential_spec(
        "githubCredentials",
        personal_access_token=credential_field(
            "personalAccessToken",
            "GITHUB_TOKEN",
            help_text="Personal Access Token with repo scope for posting comments",
        ),
        webhook_secret=credential_field(
            "webhookSecret",
            "GITHUB_WEBHOOK_SECRET",
            help_text="Webhook secret for verifying incoming event signatures",
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

    def __init__(self) -> None:
        super().__init__()
        self._token: str = ""
        self._secret: str = ""
        self._webhook_verified: bool = False

    @classmethod
    def from_credentials(
        cls,
        personal_access_token: str = "",
        webhook_secret: str = "",
        **kwargs: Any,
    ) -> "GitHubChannel":
        """Factory method for credential-based instantiation."""
        instance = cls()
        instance._token = personal_access_token
        instance._secret = webhook_secret
        return instance

    async def start(self) -> None:
        """GitHub channel is passive (webhook-driven), no active connection needed."""
        if not self._secret:
            logger.warning("GitHubChannel: no webhook_secret configured, signature verification disabled")
        self._set_connected(True)
        logger.info("GitHubChannel: started (webhook mode)")

    async def stop(self) -> None:
        self._set_connected(False)
        logger.info("GitHubChannel: stopped")

    # -- Inbound: Webhook handling -------------------------------------------

    def register_routes(self, registrar: object) -> None:
        """Register POST /webhook for GitHub webhook events."""
        from app.channels.protocols.route_registrar import (
            HttpMethod,
            RouteMetadata,
        )

        async def github_webhook_handler(request: object) -> object:
            """Handle inbound GitHub webhook POST."""
            from app.channels.protocols.route_registrar import GenericResponse

            raw_body: bytes = await request.body()  # type: ignore[attr-defined]
            headers = getattr(request, "headers", {})

            sig = headers.get("x-hub-signature-256", "") if hasattr(headers, "get") else ""
            event_type = headers.get("x-github-event", "") if hasattr(headers, "get") else ""

            if self._secret and sig:
                if not verify_github_signature(raw_body, sig, self._secret):
                    logger.warning("GitHubChannel: signature verification failed")
                    return GenericResponse(status_code=401, body={"error": "Invalid signature"})
                self._webhook_verified = True
            elif self._secret and not sig:
                logger.warning("GitHubChannel: missing signature header")
                return GenericResponse(status_code=401, body={"error": "Missing signature"})

            try:
                payload = json.loads(raw_body)
            except (json.JSONDecodeError, ValueError):
                return GenericResponse(status_code=400, body={"error": "Invalid JSON"})

            await self._handle_event(event_type, payload)
            return GenericResponse(status_code=200, body={"ok": True})

        registrar.add_route(  # type: ignore[attr-defined]
            HttpMethod.POST,
            "webhook",
            github_webhook_handler,
            RouteMetadata(
                description="GitHub webhook endpoint",
                requires_auth=False,
            ),
        )

    async def _handle_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Parse and dispatch a GitHub webhook event."""
        if not event_type:
            return

        ctx = parse_github_event(event_type, payload)
        if ctx is None:
            logger.debug("GitHubChannel: unsupported event type '%s', ignoring", event_type)
            return

        content = format_event_as_markdown(ctx)

        chat_id = ctx.repo_full_name
        if ctx.number is not None:
            chat_id = f"{ctx.repo_full_name}#{ctx.number}"

        action_part = ctx.action.replace(" ", "_") if ctx.action else "unknown"
        msg = InboundMessage(
            channel="github",
            chat_id=chat_id,
            sender_id=ctx.sender,
            text=content,
            message_id=f"gh-{event_type}-{action_part}-{chat_id}",
            mentioned=True,
            metadata={
                "github_event": event_type,
                "github_action": ctx.action,
                "github_repo": ctx.repo_full_name,
                "github_number": ctx.number,
                "github_url": ctx.url,
            },
        )
        await self._emit_inbound(msg)

    # -- Outbound: Post comment ----------------------------------------------

    async def send(self, msg: OutboundMessage) -> str | None:
        """Post Agent response as a comment on the originating GitHub issue/PR."""
        if not self._token:
            logger.warning("GitHubChannel: no token configured, cannot send")
            self.health.record_failure("No token")
            return None

        recipient = msg.recipient_id or ""
        repo, number = self._parse_recipient(recipient)
        if not repo or number is None:
            logger.warning("GitHubChannel: invalid recipient_id '%s'", recipient)
            self.health.record_failure("Invalid recipient")
            return None

        content = render(msg, self.render_style)

        success = await post_issue_comment(self._token, repo, number, content)
        if success:
            self.health.record_success()
            return f"gh-comment-{repo}-{number}"
        self.health.record_failure("API error")
        return None

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
        """Check if webhook has been successfully verified at least once."""
        return self._status in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED)

    def collect_issues(self) -> list[ChannelIssue]:
        """Report configuration and connectivity issues."""
        issues: list[ChannelIssue] = []
        if not self._secret:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message="Webhook secret not configured — signature verification is disabled",
                    fix="Set webhookSecret in GitHub channel credentials",
                )
            )
        if not self._token:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message="Personal Access Token not configured — cannot post comments",
                    fix="Set personalAccessToken in GitHub channel credentials",
                )
            )
        if not self._webhook_verified and self._status == ChannelStatus.RUNNING:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.INFO,
                    message="No webhook events received yet — verify webhook URL in GitHub settings",
                )
            )
        return issues
