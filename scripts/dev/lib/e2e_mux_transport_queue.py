"""Mux transport queue — fair wait via browser operation credits (P0-B).

Peers holding upstream operation credits block newcomers until credits free or
budget expires. Replaces process-scan transport stall detection (roadmap P0-B).
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

MUX_TRANSPORT_QUEUE_WAIT_TOKEN: str = "E2E_MUX_TRANSPORT_QUEUE_WAIT"
MUX_TRANSPORT_QUEUE_OK_TOKEN: str = "E2E_MUX_TRANSPORT_QUEUE_OK"
MUX_TRANSPORT_QUEUE_TIMEOUT_TOKEN: str = "E2E_MUX_TRANSPORT_QUEUE_TIMEOUT"
MUX_TRANSPORT_QUEUE_WAIT_NODE: str = "parallel_mux_queue_wait"

_OPERATION_CREDIT_NODE: str = "mux_operation_credit"
_FORCE_CHAT_SHELL_BLOCKING_NODE: str = "force_chat_shell_blocking"
_OPEN_MCP_PAGE_BLOCKING_NODE: str = "open_mcp_page_blocking"

_POLL_INTERVAL_SEC: float = 2.0
_PROGRESS_EMIT_INTERVAL_SEC: float = 30.0


@dataclass(frozen=True, slots=True)
class TransportQueuePeer:
    pid: int
    node: str


@dataclass(frozen=True, slots=True)
class TransportQueueSnapshot:
    blocked: bool
    peers: tuple[TransportQueuePeer, ...]

    def format_peers(self) -> str:
        if not self.peers:
            return "0"
        return ",".join(f"{peer.pid}:{peer.node}" for peer in self.peers)


def _emit_stderr(token: str, *, peers: TransportQueueSnapshot | None = None) -> None:
    if peers is not None and peers.peers:
        sys.stderr.write(f"{token}: peers={peers.format_peers()}\n")
    else:
        sys.stderr.write(f"{token}\n")
    sys.stderr.flush()


def _resolve_peer_node(owner_pid: int) -> str:
    """Best-effort node label for observability; credit ownership is SSOT."""
    support_path = (
        Path(__file__).resolve().parents[3] / "myrm-agent-server" / "tests" / "support"
    )
    support_text = str(support_path)
    inserted = False
    if support_text not in sys.path:
        sys.path.insert(0, support_text)
        inserted = True
    try:
        from e2e_parallel_snapshot import (  # noqa: PLC0415
            parallel_snapshot_to_dict,
            snapshot_live_e2e_processes,
        )

        payload = parallel_snapshot_to_dict(snapshot_live_e2e_processes())
        active_raw = payload.get("active_tests")
        if isinstance(active_raw, list):
            for row in active_raw:
                if not isinstance(row, dict):
                    continue
                try:
                    pid = int(row.get("pid"))
                except (TypeError, ValueError):
                    continue
                if pid != owner_pid:
                    continue
                node = str(row.get("current_node") or "").strip()
                if node and node != MUX_TRANSPORT_QUEUE_WAIT_NODE:
                    return node
    except ImportError:
        pass
    finally:
        if inserted:
            sys.path.remove(support_text)
    return _OPERATION_CREDIT_NODE


def _transport_blocking_peers(
    *, exclude_pid: int | None = None
) -> tuple[TransportQueuePeer, ...]:
    from mux_upstream_admission import list_active_upstream_operations  # noqa: PLC0415

    owner = exclude_pid if exclude_pid is not None else os.getpid()
    peers: list[TransportQueuePeer] = []
    for operation in list_active_upstream_operations():
        if operation.owner_pid == owner:
            continue
        peers.append(
            TransportQueuePeer(
                pid=operation.owner_pid,
                node=_resolve_peer_node(operation.owner_pid),
            )
        )
    peers.sort(key=lambda item: item.pid)
    return tuple(peers)


def transport_queue_snapshot(
    *, exclude_pid: int | None = None
) -> TransportQueueSnapshot:
    peers = _transport_blocking_peers(exclude_pid=exclude_pid)
    return TransportQueueSnapshot(blocked=len(peers) > 0, peers=peers)


def format_transport_queue_human(*, exclude_pid: int | None = None) -> str:
    snap = transport_queue_snapshot(exclude_pid=exclude_pid)
    blocked = "yes" if snap.blocked else "no"
    return f"E2E_MUX_TRANSPORT_QUEUE: blocked={blocked} peers={snap.format_peers()}"


def wait_mux_transport_turn(
    *,
    budget_sec: float,
    current_node: str = MUX_TRANSPORT_QUEUE_WAIT_NODE,
) -> None:
    """Block until no peer holds an operation credit, then mark this session ready."""
    try:
        from e2e_session_lifecycle import touch_wall_progress  # noqa: PLC0415
    except ImportError:

        def touch_wall_progress(*, current_node: str | None = None) -> None:
            del current_node

    try:
        from e2e_lease_heartbeat import heartbeat_e2e_lease  # noqa: PLC0415
    except ImportError:

        def heartbeat_e2e_lease() -> None:
            return None

    touch_wall_progress(current_node=current_node)
    deadline = time.monotonic() + max(0.0, float(budget_sec))
    last_emit = 0.0
    owner = os.getpid()
    while True:
        snap = transport_queue_snapshot(exclude_pid=owner)
        if not snap.blocked:
            _emit_stderr(MUX_TRANSPORT_QUEUE_OK_TOKEN)
            touch_wall_progress(current_node=current_node)
            return
        now = time.monotonic()
        if now >= deadline:
            _emit_stderr(MUX_TRANSPORT_QUEUE_TIMEOUT_TOKEN, peers=snap)
            raise RuntimeError(
                f"{MUX_TRANSPORT_QUEUE_TIMEOUT_TOKEN}: budget={budget_sec:.0f}s "
                f"peers={snap.format_peers()}"
            )
        touch_wall_progress(current_node=current_node)
        heartbeat_e2e_lease()
        elapsed = now - (deadline - float(budget_sec))
        if elapsed - last_emit >= _PROGRESS_EMIT_INTERVAL_SEC:
            _emit_stderr(MUX_TRANSPORT_QUEUE_WAIT_TOKEN, peers=snap)
            last_emit = elapsed
        time.sleep(_POLL_INTERVAL_SEC)


__all__ = [
    "MUX_TRANSPORT_QUEUE_OK_TOKEN",
    "MUX_TRANSPORT_QUEUE_TIMEOUT_TOKEN",
    "MUX_TRANSPORT_QUEUE_WAIT_NODE",
    "MUX_TRANSPORT_QUEUE_WAIT_TOKEN",
    "TransportQueuePeer",
    "TransportQueueSnapshot",
    "_FORCE_CHAT_SHELL_BLOCKING_NODE",
    "_OPEN_MCP_PAGE_BLOCKING_NODE",
    "format_transport_queue_human",
    "transport_queue_snapshot",
    "wait_mux_transport_turn",
]
