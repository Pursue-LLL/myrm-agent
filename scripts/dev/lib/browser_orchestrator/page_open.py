"""Page-Open Orchestrator (POO) — Dev Gate SSOT for owned mux page open (Phase 3).

Transport queue routes through browser orchestrator operation credits (P0-B).
"""

from __future__ import annotations

from browser_orchestrator.core import wait_for_operation_credit
from e2e_mux_transport_queue import (
    MUX_TRANSPORT_QUEUE_OK_TOKEN,
    MUX_TRANSPORT_QUEUE_TIMEOUT_TOKEN,
    MUX_TRANSPORT_QUEUE_WAIT_TOKEN,
    _FORCE_CHAT_SHELL_BLOCKING_NODE,
    _OPEN_MCP_PAGE_BLOCKING_NODE,
    format_transport_queue_human,
    transport_queue_snapshot,
)

__all__ = [
    "MUX_TRANSPORT_QUEUE_OK_TOKEN",
    "MUX_TRANSPORT_QUEUE_TIMEOUT_TOKEN",
    "MUX_TRANSPORT_QUEUE_WAIT_TOKEN",
    "_FORCE_CHAT_SHELL_BLOCKING_NODE",
    "_OPEN_MCP_PAGE_BLOCKING_NODE",
    "format_transport_queue_human",
    "transport_queue_snapshot",
    "wait_for_operation_credit",
    "wait_force_chat_shell_transport_turn",
    "wait_open_mcp_page_transport_turn",
]


def wait_open_mcp_page_transport_turn(*, budget_sec: float) -> None:
    wait_for_operation_credit(
        budget_sec=budget_sec,
        current_node=_OPEN_MCP_PAGE_BLOCKING_NODE,
    )


def wait_force_chat_shell_transport_turn(*, budget_sec: float) -> None:
    wait_for_operation_credit(
        budget_sec=budget_sec,
        current_node=_FORCE_CHAT_SHELL_BLOCKING_NODE,
    )
