"""[INPUT]
- myrm_agent_harness.agent.streaming.zero_replay: ZeroReplayProtocolEngine, SessionAtomicSnapshot, LiveStreamFilterConfig

[OUTPUT]
- ZeroReplaySnapshotService: Server-side business service managing zero-replay atomic snapshots and live event stream gating

[POS]
Server-side business service for Zero-Replay reconnect protocol (Item 36 P0).
Provides atomic state snapshot compilation, handshake verification, and live SSE event filtering.
"""

from __future__ import annotations

import threading
from typing import ClassVar, Literal

from myrm_agent_harness.agent.streaming.zero_replay import (
    LiveStreamFilterConfig,
    SessionAtomicSnapshot,
    ZeroReplayProtocolEngine,
)


class ZeroReplaySnapshotService:
    """Server-side business service governing zero-replay reconnect state and live stream filtering."""

    _instance: ClassVar[ZeroReplaySnapshotService | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._engine = ZeroReplayProtocolEngine()

    @classmethod
    def get_instance(cls) -> ZeroReplaySnapshotService:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def get_atomic_snapshot(self, session_id: str) -> SessionAtomicSnapshot:
        """Compiles a fresh immutable atomic state snapshot for the requested session.

        Nothing in the product reports session state to this service, so the snapshot carries the idle defaults;
        only the epoch and the state version come from the engine.
        """
        return self._engine.compile_atomic_snapshot(
            session_id=session_id,
            status="idle",
            leaf_entry_id=None,
            active_tool_calls=[],
            message_count=0,
            latest_turn_summary=None,
            artifacts_summary=[],
            metadata={},
        )

    def evaluate_handshake(
        self,
        session_id: str,
        client_epoch_id: str,
        client_version: int,
    ) -> Literal["continue_live", "require_full_snapshot_reload"]:
        """Evaluates reconnecting client handshake against the current server snapshot."""
        current_snapshot = self.get_atomic_snapshot(session_id)
        return self._engine.evaluate_handshake(
            client_epoch_id=client_epoch_id,
            client_version=client_version,
            server_snapshot=current_snapshot,
        )

    def create_live_filter_config(
        self,
        client_snapshot_timestamp_ms: float,
        client_state_version: int,
        allow_equal_timestamp: bool = False,
    ) -> LiveStreamFilterConfig:
        return LiveStreamFilterConfig(
            client_snapshot_timestamp_ms=client_snapshot_timestamp_ms,
            client_state_version=client_state_version,
            allow_equal_timestamp=allow_equal_timestamp,
        )

    def is_event_eligible(
        self,
        event_timestamp_ms: float,
        event_version: int,
        filter_config: LiveStreamFilterConfig,
    ) -> bool:
        return self._engine.is_event_eligible_for_live_stream(
            event_timestamp_ms=event_timestamp_ms,
            event_version=event_version,
            filter_config=filter_config,
        )

    def serialize_snapshot(self, snapshot: SessionAtomicSnapshot) -> dict[str, object]:
        """Serializes SessionAtomicSnapshot to a JSON-compatible dictionary."""
        return {
            "session_id": snapshot.session_id,
            "epoch_id": snapshot.epoch_id,
            "state_version": snapshot.state_version,
            "snapshot_timestamp_ms": snapshot.snapshot_timestamp_ms,
            "status": snapshot.status,
            "leaf_entry_id": snapshot.leaf_entry_id,
            "active_tool_calls": snapshot.active_tool_calls,
            "message_count": snapshot.message_count,
            "latest_turn_summary": snapshot.latest_turn_summary,
            "artifacts_summary": snapshot.artifacts_summary,
            "metadata": snapshot.metadata,
        }
