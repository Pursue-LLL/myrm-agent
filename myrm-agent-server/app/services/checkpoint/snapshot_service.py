"""Workspace snapshot interceptor for destructive action protection.

[INPUT]
myrm_agent_harness.agent.file_snapshot::create_file_snapshot_store (POS: Factory for snapshot store.)
myrm_agent_harness.agent.file_snapshot::FileSnapshotProtocol (POS: Protocol for snapshot operations.)
myrm_agent_harness.agent.file_snapshot.types::SnapshotTrigger (POS: Snapshot trigger enum.)
myrm_agent_harness.toolkits.code_execution.interceptor::ExecutionInterceptor (POS: Protocol for intercepting code execution actions.)

[OUTPUT]
SnapshotInterceptor: Server-layer business orchestration for workspace snapshots.

[POS]
Server-layer snapshot interceptor. Handles per-turn dedup, SSE events,
and multi-agent metadata binding. Delegates actual storage to harness-layer
FileSnapshotProtocol implementations (ShadowGit or LocalFile) via factory.
"""

import asyncio
import logging
from collections import defaultdict

from myrm_agent_harness.agent.file_snapshot import create_file_snapshot_store
from myrm_agent_harness.agent.file_snapshot.external_effect_detector import detect_external_effects
from myrm_agent_harness.agent.file_snapshot.protocols import FileSnapshotProtocol
from myrm_agent_harness.agent.file_snapshot.types import SnapshotTrigger
from myrm_agent_harness.toolkits.code_execution.interceptor import ExecutionInterceptor

logger = logging.getLogger(__name__)

_workspace_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

_TRIGGER_MAP: dict[str, SnapshotTrigger] = {
    "bash": SnapshotTrigger.EXECUTE_TERMINAL,
    "file_write": SnapshotTrigger.WRITE_FILE,
    "file_append": SnapshotTrigger.WRITE_FILE,
    "file_delete": SnapshotTrigger.DELETE_FILE,
    "patch_file": SnapshotTrigger.PATCH_FILE,
}


class SnapshotInterceptor(ExecutionInterceptor):
    """Intercepts destructive actions to create workspace snapshots.

    Business orchestration only — storage is delegated to harness-layer
    FileSnapshotProtocol implementations via create_file_snapshot_store().
    """

    def __init__(self) -> None:
        self._snapshotted_turns: dict[tuple[str, str], bool] = {}
        self._store: FileSnapshotProtocol | None = None

    async def _get_store(self) -> FileSnapshotProtocol:
        if self._store is None:
            self._store = await create_file_snapshot_store()
        return self._store

    async def before_destructive_action(self, workspace_path: str, action_type: str, payload: dict) -> None:
        """Called by Harness before a destructive action is executed."""
        session_id = payload.get("session_id")
        if not session_id:
            return

        from app.ai_agents.general_agent.context import get_current_agent_id, get_current_chat_id, get_current_turn_id

        turn_id = get_current_turn_id() or "unknown_turn"
        chat_id = get_current_chat_id() or "unknown_chat"
        agent_id = get_current_agent_id() or "unknown_agent"

        cache_key = (workspace_path, turn_id)

        if self._snapshotted_turns.get(cache_key):
            return

        metadata: dict[str, object] | None = None
        if action_type == "bash":
            command = payload.get("command", "")
            effects = detect_external_effects(command)
            if effects:
                metadata = {"external_effects": effects}

        snapshot_task = asyncio.create_task(
            self._safe_snapshot_with_lock(workspace_path, action_type, chat_id, agent_id, turn_id, cache_key, metadata)
        )

        try:
            await asyncio.wait_for(asyncio.shield(snapshot_task), timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning("Snapshot creation for %s exceeded 3s timeout, continuing in background", workspace_path)
        except Exception as e:
            logger.warning("Snapshot creation error: %s", e)

    async def _safe_snapshot_with_lock(
        self,
        workspace_path: str,
        action_type: str,
        chat_id: str,
        agent_id: str,
        turn_id: str,
        cache_key: tuple[str, str],
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Acquire lock and perform snapshot safely."""
        lock = _workspace_locks[workspace_path]
        async with lock:
            if self._snapshotted_turns.get(cache_key):
                return

            try:
                await self._emit_snapshot_event(chat_id, action_type)

                store = await self._get_store()
                trigger = _TRIGGER_MAP.get(action_type, SnapshotTrigger.MANUAL)
                description = f"Before {action_type} (chat:{chat_id[:8]} agent:{agent_id[:8]} turn:{turn_id[:8]})"

                await store.take_snapshot(
                    working_dir=workspace_path,
                    trigger=trigger,
                    description=description,
                    metadata=metadata,
                )

                self._snapshotted_turns[cache_key] = True
            except Exception as e:
                logger.error("Failed to create snapshot for %s: %s", workspace_path, e)

    async def _emit_snapshot_event(self, chat_id: str, action_type: str) -> None:
        """Emit an SSE event to the frontend to show the Snapshotting UI indicator."""
        try:
            from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.SYSTEM_NOTIFICATION,
                    data={
                        "title": "系统保护",
                        "message": "正在创建系统快照，保护您的代码",
                        "meta_data": {
                            "type": "snapshot_created",
                            "action": action_type,
                            "chat_id": chat_id,
                        },
                    },
                )
            )
        except Exception as e:
            logger.debug("Failed to emit snapshot event: %s", e)
