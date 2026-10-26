"""Browser snapshot collection shared by WebUI and mobile remote routes.

[INPUT]
- harness session.view_update_payload::capture_browser_view_update_data (POS: shared browser inspector payload builder)
- app.services.agent.gateway::get_agent_gateway (POS: active agent session registry)

[OUTPUT]
- collect_browser_snapshot_payload: chat-scoped browser inspector snapshot for REST consumers
- BrowserSnapshotUnavailableError: normalized unavailable errors (400/404)

[POS]
Server-side adapter for WebUI and mobile browser inspector manual refresh APIs.
"""

from __future__ import annotations


class BrowserSnapshotUnavailableError(Exception):
    """Normalized browser snapshot unavailable error for REST consumers."""

    __slots__ = ("status_code", "error", "message")

    def __init__(self, *, status_code: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message


async def collect_browser_snapshot_payload(
    *,
    chat_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, object]:
    """Collect browser inspector snapshot payload scoped to one chat/session."""
    resolved = (chat_id or session_id or "").strip()
    if not resolved:
        raise BrowserSnapshotUnavailableError(
            status_code=400,
            error="missing_chat_id",
            message="chat_id is required for browser snapshot",
        )

    from app.services.agent.gateway import get_agent_gateway

    gateway = get_agent_gateway()
    browser_session = gateway.get_active_browser_session(session_id=resolved)
    if browser_session is None:
        raise BrowserSnapshotUnavailableError(
            status_code=404,
            error="no_active_browser",
            message="No active browser session for this chat",
        )

    from myrm_agent_harness.toolkits.browser.session.view_update_payload import (
        capture_browser_view_update_data,
    )

    return await capture_browser_view_update_data(browser_session)
