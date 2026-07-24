"""Pin LITE_MODEL for desktop Chrome E2E (multi-step desktop tool chain).

Desktop approval requires reliable snapshot→interact sequencing; BASIC (mimo) often
stops after desktop_snapshot_tool. LITE (MiniMax-M3) matches clarify/API E2E SSOT.
"""

from __future__ import annotations

from tests.support.e2e_lite_model_pin import pin_lite_model_for_e2e

try:
    from mcp_chat_ui import McpChatSession
except ImportError:  # pragma: no cover - import path in pytest vs standalone
    McpChatSession = object  # type: ignore[misc,assignment]


async def pin_basic_model_for_desktop_e2e(
    chat: McpChatSession,
    *,
    recv_timeout: float = 30.0,
    max_attempts: int = 5,
    retry_sleep_sec: float = 3.0,
) -> dict[str, object]:
    """Pin LITE model for desktop E2E (tool-chain reliability)."""
    return await pin_lite_model_for_e2e(
        chat,
        recv_timeout=recv_timeout,
        max_attempts=max_attempts,
        retry_sleep_sec=retry_sleep_sec,
    )
