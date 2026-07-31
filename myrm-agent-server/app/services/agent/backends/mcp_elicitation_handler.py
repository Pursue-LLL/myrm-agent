"""MCP elicitation handler — bridges SDK ElicitRequest to ApprovalRegistry.

When an MCP server returns ``InputRequiredResult`` with an ``ElicitRequest``,
the SDK invokes the ``elicitation_callback`` registered on ``Client``. This
module provides a factory that creates async handler callables for injection
into ``MCPServerConfig.elicitation_handler``.

The handler creates a pending approval via ``ApprovalRegistry``, pushes an SSE
event to the frontend, and suspends on an ``asyncio.Event`` until the user
resolves the approval via the standard ``POST /approvals/{id}/resolve`` API.

Implements the harness-level ``elicitation_handler`` protocol:
``async (server_name: str, message: str, schema: dict) -> "accept"|"decline"|"cancel"``

[INPUT]
- app.services.approvals.registry::ApprovalRegistry (POS: unified approval center)

[OUTPUT]
- build_mcp_elicitation_handler: factory returning an async handler callable
- resolve_pending_elicitation: called by the approval resolve path to wake the handler

[POS]
Bridges MCP protocol-level elicitation to the product's approval UI. One handler
per MCP server config, shared across sessions.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_ELICITATION_TIMEOUT_SECONDS = 300

_pending_elicitations: dict[str, tuple[asyncio.Event, str]] = {}


def resolve_pending_elicitation(approval_id: str, decision: str) -> bool:
    """Wake a suspended elicitation handler with the user's decision.

    Called from the approval resolve path when ``action_type == "mcp_elicitation"``.
    Returns True if the elicitation was found and resolved.
    """
    entry = _pending_elicitations.get(approval_id)
    if entry is None:
        return False
    event, _ = entry
    _pending_elicitations[approval_id] = (event, decision)
    event.set()
    return True


def build_mcp_elicitation_handler(
    agent_id: str,
    chat_id: str | None = None,
    thread_id: str | None = None,
) -> object:
    """Build an async elicitation handler for MCP server configs.

    The returned callable conforms to the harness protocol:
    ``async (server_name, message, schema) -> "accept"|"decline"|"cancel"``
    """

    async def handler(
        server_name: str,
        message: str,
        schema: dict[str, object],
    ) -> str:
        from app.services.approvals.registry import ApprovalRegistry

        payload = {
            "server_name": server_name,
            "message": message,
            "requested_schema": schema,
            "action_type": "mcp_elicitation",
        }
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=_ELICITATION_TIMEOUT_SECONDS)

        record = await ApprovalRegistry.create_approval(
            agent_id=agent_id,
            action_type="mcp_elicitation",
            payload=payload,
            reason=message,
            severity="warning",
            chat_id=chat_id,
            thread_id=thread_id,
            expires_at=expires_at,
        )

        event = asyncio.Event()
        _pending_elicitations[record.id] = (event, "decline")

        try:
            await asyncio.wait_for(
                event.wait(),
                timeout=_ELICITATION_TIMEOUT_SECONDS,
            )
            _, decision = _pending_elicitations.get(record.id, (event, "decline"))
            return _normalize_decision(decision)
        except TimeoutError:
            logger.warning(
                "MCP elicitation for server '%s' timed out (approval_id=%s)",
                server_name,
                record.id,
            )
            return "cancel"
        finally:
            _pending_elicitations.pop(record.id, None)

    return handler


def _normalize_decision(decision: str) -> str:
    """Map approval decisions to MCP elicitation actions (accept/decline/cancel)."""
    if decision in ("approve", "approved"):
        return "accept"
    if decision in ("deny", "denied", "reject", "rejected"):
        return "decline"
    if decision in ("cancel", "cancelled", "timeout"):
        return "cancel"
    return "decline"
