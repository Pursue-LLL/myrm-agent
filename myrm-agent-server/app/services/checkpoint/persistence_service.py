"""Event-driven cloud sandbox incremental persistence service with 3-level fail-closed privacy ladder.

[INPUT]
- myrm_agent_harness.core.security.privacy::PrivacyLadderValidator (POS: 3-level fail-closed privacy validator)
- app.services.event.app_event_bus::AppEvent, AppEventType, get_event_bus (POS: SSE & in-process event bus)
- app.platform_utils.sandbox.storage::S3StorageBackend (POS: S3/R2 storage backend)

[OUTPUT]
- SandboxPersistenceService: Singleton service coordinating turn-completion events, privacy ladder scans, and debounced persistence sync.
- get_sandbox_persistence_service: Factory accessor.

[POS]
Business orchestration service for sandbox persistence. Listens to turn completion events, validates
modified artifacts against the 3-level privacy ladder, and asynchronously persists safe state.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.core.security.privacy import (
    PrivacyLadderValidator,
    PrivacyScanVerdict,
)

from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

if TYPE_CHECKING:
    from app.platform_utils.sandbox.storage import S3StorageBackend

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PersistenceSyncReport:
    session_id: str
    synced_files: list[str]
    blocked_files: list[tuple[str, str]]
    ignored_files: list[str]


class SandboxPersistenceService:
    """Manages event-driven incremental persistence for sandbox sessions."""

    def __init__(self, storage_backend: "S3StorageBackend | None" = None) -> None:
        self._storage_backend = storage_backend
        self._session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._is_subscribed: bool = False

    def bind_storage_backend(self, backend: "S3StorageBackend") -> None:
        """Bind or update the cloud storage backend."""
        self._storage_backend = backend

    def subscribe_to_event_bus(self) -> None:
        """Subscribe to global event bus for turn-completion persistence triggers."""
        if self._is_subscribed:
            return
        bus = get_event_bus()
        bus.subscribe(self._handle_app_event)
        self._is_subscribed = True

    async def _handle_app_event(self, event: AppEvent) -> None:
        if event.event_type == AppEventType.SANDBOX_PERSIST_TRIGGERED:
            session_id = event.data.get("session_id", "default")
            workspace_root = event.data.get("workspace_root")
            if workspace_root:
                asyncio.create_task(
                    self.persist_session_turn(
                        session_id=str(session_id),
                        workspace_root=Path(workspace_root),
                    )
                )

    async def persist_session_turn(
        self,
        session_id: str,
        workspace_root: Path,
        candidate_paths: list[str | Path] | None = None,
    ) -> PersistenceSyncReport:
        """Validate candidate paths against 3-level privacy ladder and persist safe files asynchronously."""
        async with self._session_locks[session_id]:
            validator = PrivacyLadderValidator(
                workspace_root=workspace_root,
                session_id=session_id,
            )

            paths_to_evaluate: list[Path] = []
            if candidate_paths:
                for cp in candidate_paths:
                    p = Path(cp)
                    abs_p = (workspace_root / p).resolve() if not p.is_absolute() else p.resolve()
                    paths_to_evaluate.append(abs_p)
            else:
                # Scan modified files under workspace root
                if workspace_root.exists() and workspace_root.is_dir():
                    for item in workspace_root.rglob("*"):
                        if item.is_file():
                            paths_to_evaluate.append(item)

            synced: list[str] = []
            blocked: list[tuple[str, str]] = []
            ignored: list[str] = []

            for target in paths_to_evaluate:
                eval_res = validator.evaluate_path(target)
                target_str = str(target)
                if eval_res.verdict == PrivacyScanVerdict.IGNORED:
                    ignored.append(target_str)
                    continue

                if not eval_res.is_safe:
                    reasons = "; ".join(v.reason for v in eval_res.violations)
                    logger.warning(
                        "Sandbox privacy ladder BLOCKED persistence for '%s': %s",
                        target_str,
                        reasons,
                    )
                    blocked.append((target_str, reasons))
                    continue

                rel_path = eval_res.sanitized_rel_path or target.name
                if self._storage_backend and target.exists():
                    try:
                        content = target.read_bytes()
                        storage_key = f"sessions/{session_id}/{rel_path}"
                        await self._storage_backend.write(storage_key, content)
                        synced.append(rel_path)
                    except Exception as e:
                        logger.error("Failed to persist file '%s' to storage: %s", rel_path, e)

            report = PersistenceSyncReport(
                session_id=session_id,
                synced_files=synced,
                blocked_files=blocked,
                ignored_files=ignored,
            )

            # Emit completion event
            bus = get_event_bus()
            bus.publish(
                AppEvent(
                    event_type=AppEventType.SANDBOX_PERSIST_COMPLETED,
                    data={
                        "session_id": session_id,
                        "synced_count": len(synced),
                        "blocked_count": len(blocked),
                    },
                )
            )

            return report


_persistence_singleton: SandboxPersistenceService | None = None


def get_sandbox_persistence_service() -> SandboxPersistenceService:
    global _persistence_singleton
    if _persistence_singleton is None:
        _persistence_singleton = SandboxPersistenceService()
        _persistence_singleton.subscribe_to_event_bus()
    return _persistence_singleton
