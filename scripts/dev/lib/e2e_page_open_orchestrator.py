"""Page-Open Orchestrator (POO) — Dev Gate SSOT for owned mux page open (Phase 3).

Transport queue (TQ) is live SSOT for open_mcp_page and force chat shell paths.
"""

from __future__ import annotations

from e2e_mux_transport_queue import (
    MUX_TRANSPORT_QUEUE_OK_TOKEN,
    MUX_TRANSPORT_QUEUE_TIMEOUT_TOKEN,
    MUX_TRANSPORT_QUEUE_WAIT_TOKEN,
    _FORCE_CHAT_SHELL_BLOCKING_NODE,
    _OPEN_MCP_PAGE_BLOCKING_NODE,
    format_transport_queue_human,
    transport_queue_snapshot,
    wait_mux_transport_turn,
)

__all__ = [
    "MUX_TRANSPORT_QUEUE_OK_TOKEN",
    "MUX_TRANSPORT_QUEUE_TIMEOUT_TOKEN",
    "MUX_TRANSPORT_QUEUE_WAIT_TOKEN",
    "_FORCE_CHAT_SHELL_BLOCKING_NODE",
    "_OPEN_MCP_PAGE_BLOCKING_NODE",
    "format_transport_queue_human",
    "transport_queue_snapshot",
    "wait_force_chat_shell_transport_turn",
    "wait_mux_transport_turn",
    "wait_open_mcp_page_transport_turn",
]


def wait_open_mcp_page_transport_turn(*, budget_sec: float) -> None:
    wait_mux_transport_turn(
        budget_sec=budget_sec,
        current_node=_OPEN_MCP_PAGE_BLOCKING_NODE,
    )


def wait_force_chat_shell_transport_turn(*, budget_sec: float) -> None:
    wait_mux_transport_turn(
        budget_sec=budget_sec,
        current_node=_FORCE_CHAT_SHELL_BLOCKING_NODE,
    )
