"""Stable facade for Chrome chat UI E2E helpers."""

from __future__ import annotations

from cdp_chat_support import (
    API_URL,
    DISMISS_MODALS_JS,
    E2E_BRIDGE_INSTALL_JS,
    MODEL_PROBE_JS,
    PAGE_PROBE_JS,
    RESET_CHAT_JS,
    SELECT_FIRST_ENABLED_MODEL_JS,
    SELECT_MIMO_MODEL_JS,
    backend_log_path,
    chat_id_from_path,
    chat_messages_have_ok,
    chat_user_message_count,
    count_execution_cache_in_log,
    fetch_chat_messages,
    snapshot_backend_log_offset,
    warmup_frontend,
)
from cdp_chat_transport import CdpSocket
from cdp_chat_turn import CdpChatTurn


class CdpChatSession(CdpChatTurn):
    """Chat UI workflow shared by raw transport warmup and MCP-owned test pages."""


__all__ = [
    "API_URL",
    "CdpChatSession",
    "CdpSocket",
    "DISMISS_MODALS_JS",
    "E2E_BRIDGE_INSTALL_JS",
    "MODEL_PROBE_JS",
    "PAGE_PROBE_JS",
    "RESET_CHAT_JS",
    "SELECT_FIRST_ENABLED_MODEL_JS",
    "SELECT_MIMO_MODEL_JS",
    "backend_log_path",
    "chat_id_from_path",
    "chat_messages_have_ok",
    "chat_user_message_count",
    "count_execution_cache_in_log",
    "fetch_chat_messages",
    "snapshot_backend_log_offset",
    "warmup_frontend",
]
