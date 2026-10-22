"""[INPUT]
- myrm_agent_harness.agent.streaming.zero_replay: ZeroReplayProtocolEngine, SessionAtomicSnapshot, LiveStreamFilterConfig, SessionLifecycleStatus

[OUTPUT]
- ZeroReplaySnapshotService: Server-side business service managing zero-replay atomic snapshots and live event stream gating

[POS]
Server-side business service for Zero-Replay reconnect protocol (Item 36 P0).
Provides atomic state snapshot compilation, handshake verification, and live SSE event filtering.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import ClassVar, Literal

from myrm_agent_harness.agent.streaming.zero_replay import (
    LiveStreamFilterConfig,
    SessionAtomicSnapshot,
    SessionLifecycleStatus,
    ZeroReplayProtocolEngine,
)

logger = logging.getLogger(__name__)


class ZeroReplaySnapshotService:
    """Server-side business service governing zero-replay reconnect state and live stream filtering."""

    _instance: ClassVar[ZeroReplaySnapshotService | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._engine = ZeroReplayProtocolEngine()
        self._state_lock = threading.Lock()
        self._session_status: dict[str, SessionLifecycleStatus] = {}
        self._leaf_entries: dict[str, str] = {}
        self._active_tools: dict[str, list[dict[str, str]]] = {}
        self._message_counts: dict[str, int] = {}
        self._latest_summaries: dict[str, str] = {}
        self._artifacts_summaries: dict[str, list[dict[str, str]]] = {}
        self._session_metadata: dict[str, dict[str, str]] = {}

    @classmethod
    def get_instance(cls) -> ZeroReplaySnapshotService:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def update_session_state(
        self,
        session_id: str,
        status: SessionLifecycleStatus | None = None,
        leaf_entry_id: str | None = None,
        active_tool_calls: list[dict[str, str]] | None = None,
        message_count: int | None = None,
        latest_turn_summary: str | None = None,
        artifacts_summary: list[dict[str, str]] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> SessionAtomicSnapshot:
        """Updates internal snapshot components and increments state version."""
        with self._state_lock:
            if status is not None:
                self._session_status[session_id] = status
            if leaf_entry_id is not None:
                self._leaf_entries[session_id] = leaf_entry_id
            if active_tool_calls is not None:
                self._active_tools[session_id] = active_tool_calls
            if message_count is not None:
                self._message_counts[session_id] = message_count
            if latest_turn_summary is not None:
                self._latest_summaries[session_id] = latest_turn_summary
            if artifacts_summary is not None:
                self._artifacts_summaries[session_id] = artifacts_summary
            if metadata is not None:
                current_meta = self._session_metadata.setdefault(session_id, {})
                current_meta.update(metadata)

        # Increment version to mark atomic state change
        self._engine.increment_state_version(session_id)
        return self.get_atomic_snapshot(session_id)

    def get_atomic_snapshot(self, session_id: str) -> SessionAtomicSnapshot:
        """Compiles a fresh immutable atomic state snapshot for the requested session."""
        with self._state_lock:
            status = self._session_status.get(session_id, "idle")
            leaf_id = self._leaf_entries.get(session_id)
            active_tools = list(self._active_tools.get(session_id, []))
            msg_count = self._message_counts.get(session_id, 0)
            summary = self._latest_summaries.get(session_id)
            artifacts = list(self._artifacts_summaries.get(session_id, []))
            meta = dict(self._session_metadata.get(session_id, {}))

        return self._engine.compile_atomic_snapshot(
            session_id=session_id,
            status=status,
            leaf_entry_id=leaf_id,
            active_tool_calls=active_tools,
            message_count=msg_count,
            latest_turn_summary=summary,
            artifacts_summary=artifacts,
            metadata=meta,
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

    def create_live_event_payload(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        """Creates a stamped live stream event payload with incremental version and current timestamp."""
        new_version = self._engine.increment_state_version(session_id)
        now_ms = time.time() * 1000.0
        return {
            "session_id": session_id,
            "epoch_id": self._engine.get_or_create_epoch(session_id),
            "state_version": new_version,
            "event_timestamp_ms": now_ms,
            "event_type": event_type,
            "payload": payload,
        }

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
