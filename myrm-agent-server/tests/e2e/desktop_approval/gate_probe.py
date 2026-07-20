"""Desktop interact gate probing for approval Chrome E2E."""

from __future__ import annotations

import asyncio

from mcp_chat_ui import McpChatSession

from tests.e2e.desktop_approval.constants import APPROVAL_WAIT_SEC, E2E_NUDGE_PROMPT, progress
from tests.e2e.desktop_approval.trust_api import server_pending_approval_count
from tests.support.e2e_runtime_guard import heartbeat_e2e_lease


def require_approval_gate_triggered(
    *,
    last_tool: str,
    server_pending: int,
    ui_pending: bool,
) -> None:
    """Fail fast when the model never opened a pending desktop approval request."""
    if server_pending > 0 or ui_pending:
        return
    raise AssertionError(
        "Model never triggered desktop approval gate "
        f"(lastTool={last_tool!r}, server_pending={server_pending}). "
        "Expected desktop_interact_tool or desktop_vision_tool(scroll) with pending approval."
    )


async def probe_desktop_tool_progress(chat: McpChatSession) -> dict[str, object]:
    probe = await chat.evaluate(
        """(() => window.__MYRM_E2E_CHAT__?.getDesktopToolProgress?.() ?? {})()""",
        await_promise=False,
    )
    return probe if isinstance(probe, dict) else {"active": False}


async def wait_for_interact_or_approval(
    chat: McpChatSession,
    *,
    timeout_sec: float = 90.0,
) -> tuple[dict[str, object], str, int, bool]:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    tool_activity: dict[str, object] = {"active": False}
    last_tool = ""
    server_pending = 0
    ui_pending = False
    while asyncio.get_event_loop().time() < deadline:
        heartbeat_e2e_lease()
        tool_activity = await probe_desktop_tool_progress(chat)
        last_tool = str(tool_activity.get("lastTool") or "")
        server_pending = await asyncio.to_thread(server_pending_approval_count)
        ui_pending = bool(tool_activity.get("pending"))
        if ui_pending or server_pending > 0 or last_tool.endswith("desktop_interact_tool"):
            return tool_activity, last_tool, server_pending, ui_pending
        await asyncio.sleep(1.0)
    return tool_activity, last_tool, server_pending, ui_pending


async def ensure_interact_gate(
    chat: McpChatSession,
) -> tuple[dict[str, object], str, int, bool]:
    tool_activity = await chat.wait_desktop_tool_activity(timeout_sec=APPROVAL_WAIT_SEC)
    progress(
        f"desktop tool activity result active={tool_activity.get('active')} "
        f"pending={tool_activity.get('pending')} lastTool={tool_activity.get('lastTool')} "
        f"err={tool_activity.get('err')}"
    )
    assert tool_activity.get("active") or tool_activity.get("pending"), (
        f"Model did not start desktop tools: {tool_activity}"
    )

    last_tool = str(tool_activity.get("lastTool") or "")
    server_pending = await asyncio.to_thread(server_pending_approval_count)
    ui_pending = bool(tool_activity.get("pending"))
    snapshot_only = last_tool.endswith("desktop_snapshot_tool") or last_tool.endswith(
        "desktop_vision_tool"
    )
    if snapshot_only and not (ui_pending or server_pending > 0):
        progress("snapshot-only detected; nudge interact immediately")
        try:
            await chat.send_message(E2E_NUDGE_PROMPT, E2E_NUDGE_PROMPT)
        except (RuntimeError, TimeoutError, OSError) as exc:
            raise AssertionError(f"Nudge send failed (Chrome mux): {exc}") from exc
        heartbeat_e2e_lease()
        tool_activity, last_tool, server_pending, ui_pending = await wait_for_interact_or_approval(
            chat,
            timeout_sec=120.0,
        )
    elif not (ui_pending or server_pending > 0 or last_tool.endswith("desktop_interact_tool")):
        tool_activity, last_tool, server_pending, ui_pending = await wait_for_interact_or_approval(
            chat,
            timeout_sec=45.0,
        )

    if not (ui_pending or server_pending > 0 or last_tool.endswith("desktop_interact_tool")):
        progress("nudge model to call desktop_interact_tool")
        try:
            await chat.send_message(E2E_NUDGE_PROMPT, E2E_NUDGE_PROMPT)
        except (RuntimeError, TimeoutError, OSError) as exc:
            raise AssertionError(f"Nudge send failed (Chrome mux): {exc}") from exc
        heartbeat_e2e_lease()
        tool_activity, last_tool, server_pending, ui_pending = await wait_for_interact_or_approval(
            chat,
            timeout_sec=120.0,
        )

    return tool_activity, last_tool, server_pending, ui_pending
