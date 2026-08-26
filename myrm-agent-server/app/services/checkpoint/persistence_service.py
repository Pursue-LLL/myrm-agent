"""Event-driven cloud sandbox incremental persistence service with 3-level fail-closed privacy ladder.

[INPUT]
- myrm_agent_harness.api::PrivacyLadderValidator (POS: 3-level fail-closed privacy validator)
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

from myrm_agent_harness.api import (
    SEAL_FILENAME,
    IntegritySealer,
    IntegrityStatus,
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
    is_sealed: bool = False
    manifest_file: str | None = None


@dataclass(frozen=True)
class RestoreVerificationReport:
    session_id: str
    is_valid: bool
    status: IntegrityStatus
    corrupted_files: list[str]
    missing_files: list[str]
    quarantined: bool
    reason: str = ""


class SandboxPersistenceService:
    """Manages event-driven incremental persistence for sandbox sessions."""

    def __init__(self, storage_backend: "S3StorageBackend | None" = None) -> None:
        self._storage_backend = storage_backend
        self._session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._is_subscribed: bool = False
        self._queue: asyncio.Queue[AppEvent] | None = None
        self._listener_task: asyncio.Task[None] | None = None

    def bind_storage_backend(self, backend: "S3StorageBackend") -> None:
        """Bind or update the cloud storage backend."""
        self._storage_backend = backend

    def subscribe_to_event_bus(self) -> None:
        """Subscribe to global event bus for turn-completion persistence triggers."""
        if self._is_subscribed:
            return
        bus = get_event_bus()
        self._queue = bus.subscribe()
        self._is_subscribed = True
        self._listener_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self) -> None:
        while True:
            try:
                event = await self._queue.get()
                await self._handle_app_event(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in sandbox persistence event listener: %s", e)

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
            synced_payloads: dict[str, bytes] = {}

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
                        synced_payloads[rel_path] = content
                    except Exception as e:
                        logger.error("Failed to persist file '%s' to storage: %s", rel_path, e)

            # --- ATOMIC INTEGRITY SEALING ---
            is_sealed = False
            manifest_key: str | None = None
            if self._storage_backend and synced_payloads:
                try:
                    manifest = IntegritySealer.create_seal_manifest(
                        session_id=session_id,
                        files_data=synced_payloads,
                    )
                    manifest_key = f"sessions/{session_id}/{SEAL_FILENAME}"
                    await self._storage_backend.write(
                        manifest_key,
                        manifest.to_json().encode("utf-8"),
                    )
                    is_sealed = True
                    logger.info("Sandbox checkpoint successfully sealed for session '%s'", session_id)
                except Exception as e:
                    logger.error("Failed to write seal manifest for session '%s': %s", session_id, e)

            report = PersistenceSyncReport(
                session_id=session_id,
                synced_files=synced,
                blocked_files=blocked,
                ignored_files=ignored,
                is_sealed=is_sealed,
                manifest_file=manifest_key,
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
                        "is_sealed": is_sealed,
                    },
                )
            )

            return report

    async def verify_and_quarantine_session(
        self,
        session_id: str,
        workspace_root: Path,
    ) -> RestoreVerificationReport:
        """Verify the integrity of a restored session workspace and quarantine corrupted artifacts."""
        if not self._storage_backend:
            return RestoreVerificationReport(
                session_id=session_id,
                is_valid=True,
                status=IntegrityStatus.VALID,
                corrupted_files=[],
                missing_files=[],
                quarantined=False,
                reason="No storage backend configured; skipped integrity verification",
            )

        manifest_key = f"sessions/{session_id}/{SEAL_FILENAME}"
        manifest_data: bytes | None = None
        try:
            if await self._storage_backend.exists(manifest_key):
                manifest_data = await self._storage_backend.read(manifest_key)
        except Exception as e:
            logger.warning("Error reading seal manifest for session '%s': %s", session_id, e)

        if manifest_data is None:
            return RestoreVerificationReport(
                session_id=session_id,
                is_valid=False,
                status=IntegrityStatus.MISSING_MANIFEST,
                corrupted_files=[],
                missing_files=[],
                quarantined=False,
                reason="No seal manifest found (torn write or unsealed persistence)",
            )

        # Collect local workspace files matching candidate paths
        local_files: dict[str, bytes] = {}
        if workspace_root.exists() and workspace_root.is_dir():
            for item in workspace_root.rglob("*"):
                if item.is_file():
                    try:
                        rel = str(item.relative_to(workspace_root))
                        if rel != SEAL_FILENAME:
                            local_files[rel] = item.read_bytes()
                    except Exception as e:
                        logger.warning("Error reading local workspace file '%s': %s", item, e)

        verify_res = IntegritySealer.verify_manifest_and_files(
            manifest_json=manifest_data.decode("utf-8"),
            files_data=local_files,
        )

        quarantined = False
        if not verify_res.is_valid:
            # Trigger quarantine: move corrupted files to quarantine/
            quarantine_dir = workspace_root / "quarantine" / f"corrupted_{session_id}"
            try:
                quarantine_dir.mkdir(parents=True, exist_ok=True)
                for cf in verify_res.corrupted_files:
                    corrupted_path = workspace_root / cf
                    if corrupted_path.exists():
                        target_dst = quarantine_dir / cf
                        target_dst.parent.mkdir(parents=True, exist_ok=True)
                        corrupted_path.rename(target_dst)
                quarantined = True
                logger.warning(
                    "Quarantined corrupted files for session '%s' to '%s'",
                    session_id,
                    quarantine_dir,
                )
            except Exception as e:
                logger.error("Failed to quarantine corrupted session files: %s", e)

        return RestoreVerificationReport(
            session_id=session_id,
            is_valid=verify_res.is_valid,
            status=verify_res.status,
            corrupted_files=verify_res.corrupted_files,
            missing_files=verify_res.missing_files,
            quarantined=quarantined,
            reason=verify_res.reason,
        )


_persistence_singleton: SandboxPersistenceService | None = None


def get_sandbox_persistence_service() -> SandboxPersistenceService:
    global _persistence_singleton
    if _persistence_singleton is None:
        _persistence_singleton = SandboxPersistenceService()
        _persistence_singleton.subscribe_to_event_bus()
    return _persistence_singleton
