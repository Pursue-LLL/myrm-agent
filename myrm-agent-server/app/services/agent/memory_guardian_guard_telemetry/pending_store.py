"""@input: pending-envelope state path under MYRM_DATA_DIR
@output: MemoryGuardianGuardPendingStore — persisted guardian telemetry envelope queue
@pos: Restart recovery for unsent memory guardian guard telemetry envelopes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Sequence

from app.schemas.control_plane import MemoryGuardianGuardTelemetryEnvelope

logger = logging.getLogger(__name__)

try:
    import fcntl as _fcntl
except Exception:  # pragma: no cover - non-POSIX runtimes
    _fcntl = None

_PENDING_STATE_LOCK_SUFFIX: str = ".lock"
_PENDING_STATE_MAX_BYTES: int = 256 * 1024


class MemoryGuardianGuardPendingStore:
    """Persist and recover unsent guardian telemetry envelopes."""

    def __init__(self, state_path: Path | None) -> None:
        self._path = state_path

    def load(self) -> list[MemoryGuardianGuardTelemetryEnvelope]:
        path = self._path
        if path is None or not path.exists():
            return []

        _, lock_handle = self._acquire_lock()
        try:
            if not path.exists():
                return []
            if path.stat().st_size > _PENDING_STATE_MAX_BYTES:
                logger.warning(
                    "Guardian telemetry pending-state file too large; clearing persisted state: path=%s",
                    path,
                )
                self._clear_unlocked(path)
                return []
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning(
                "Failed to load guardian telemetry pending-state file: path=%s",
                path,
                exc_info=True,
            )
            try:
                self._clear_unlocked(path)
            except Exception:
                logger.warning(
                    "Failed to clear malformed guardian telemetry pending-state file: path=%s",
                    path,
                    exc_info=True,
                )
            return []
        finally:
            self._release_lock(lock_handle)

        raw_events = payload.get("events", []) if isinstance(payload, dict) else []
        if not isinstance(raw_events, list):
            logger.warning(
                "Guardian telemetry pending-state file has invalid format; clearing file: path=%s",
                path,
            )
            self.clear_persisted()
            return []

        recovered: list[MemoryGuardianGuardTelemetryEnvelope] = []
        for raw_event in raw_events:
            try:
                recovered.append(MemoryGuardianGuardTelemetryEnvelope.model_validate(raw_event))
            except Exception:
                logger.warning(
                    "Guardian telemetry pending-state row is invalid; clearing file: path=%s",
                    path,
                    exc_info=True,
                )
                self.clear_persisted()
                return []

        if recovered:
            logger.info(
                "Recovered guardian telemetry pending envelopes: envelopes=%d",
                len(recovered),
            )
        else:
            self.clear_persisted()
        return recovered

    def persist(self, envelopes: Sequence[MemoryGuardianGuardTelemetryEnvelope]) -> bool:
        path = self._path
        if path is None:
            return True

        _, lock_handle = self._acquire_lock()
        try:
            if not envelopes:
                self._clear_unlocked(path)
                return True
            payload = {
                "events": [envelope.model_dump() for envelope in envelopes],
            }
            serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
            if len(serialized.encode("utf-8")) > _PENDING_STATE_MAX_BYTES:
                logger.warning(
                    "Guardian telemetry pending payload exceeded limit; refusing persist: path=%s",
                    path,
                )
                return False
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_suffix(f"{path.suffix}.tmp")
            temp_path.write_text(serialized, encoding="utf-8")
            temp_path.replace(path)
            return True
        except Exception:
            logger.warning(
                "Failed to persist guardian telemetry pending envelopes: path=%s",
                path,
                exc_info=True,
            )
            return False
        finally:
            self._release_lock(lock_handle)

    def clear_persisted(self) -> None:
        path = self._path
        if path is None or not path.exists():
            return
        _, lock_handle = self._acquire_lock()
        try:
            self._clear_unlocked(path)
        except Exception:
            logger.warning(
                "Failed to clear guardian telemetry pending-state file: path=%s",
                path,
                exc_info=True,
            )
        finally:
            self._release_lock(lock_handle)

    def _lock_path(self) -> Path | None:
        if self._path is None:
            return None
        return self._path.with_name(f"{self._path.name}{_PENDING_STATE_LOCK_SUFFIX}")

    def _acquire_lock(self) -> tuple[Path | None, object | None]:
        lock_path = self._lock_path()
        if lock_path is None:
            return None, None
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_handle = lock_path.open("a+")
        if _fcntl is not None:
            _fcntl.flock(lock_handle.fileno(), _fcntl.LOCK_EX)
        return lock_path, lock_handle

    @staticmethod
    def _release_lock(lock_handle: object | None) -> None:
        if lock_handle is None:
            return
        try:
            if _fcntl is not None and hasattr(lock_handle, "fileno"):
                _fcntl.flock(lock_handle.fileno(), _fcntl.LOCK_UN)
        finally:
            if hasattr(lock_handle, "close"):
                lock_handle.close()

    @staticmethod
    def _clear_unlocked(path: Path) -> None:
        if not path.exists():
            return
        path.unlink()
