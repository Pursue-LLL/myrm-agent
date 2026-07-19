"""@input: dropped-state file path under MYRM_DATA_DIR
@output: MemoryBriefStatusDroppedStore — in-memory dropped aggregates + throttled disk persistence
@pos: Backpressure dropped-event persistence for memory brief status telemetry (cross-process file lock).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from app.schemas.control_plane import MemoryBriefStatusDroppedAggregate

logger = logging.getLogger(__name__)

try:
    import fcntl as _fcntl
except Exception:  # pragma: no cover - non-POSIX runtimes
    _fcntl = None

_DROPPED_STATE_LOCK_SUFFIX: str = ".lock"
_DROPPED_STATE_MAX_BYTES: int = 128 * 1024
_DROPPED_STATE_PERSIST_INTERVAL_SECONDS: float = 1.0
_DROPPED_STATE_PERSIST_MAX_PENDING_UPDATES: int = 32
_DROPPED_STATE_PERSIST_FAILURE_BASE_BACKOFF_SECONDS: float = 1.0
_DROPPED_STATE_PERSIST_FAILURE_MAX_BACKOFF_SECONDS: float = 30.0


class MemoryBriefStatusDroppedStore:
    """Tracks dropped telemetry events and persists aggregates for restart recovery."""

    def __init__(self, state_path: Path | None) -> None:
        self._path = state_path
        self._counts: dict[tuple[str, str], int] = self.load()
        self._dirty = False
        self._pending_updates = 0
        self._last_persist_monotonic = 0.0
        self._next_retry_monotonic = 0.0
        self._persist_failure_count = 0

    @property
    def counts(self) -> dict[tuple[str, str], int]:
        return self._counts

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def pending_updates(self) -> int:
        return self._pending_updates

    @property
    def next_retry_monotonic(self) -> float:
        return self._next_retry_monotonic

    @property
    def persist_failure_count(self) -> int:
        return self._persist_failure_count

    def record_drop(self, *, dropped_phase: str, incoming_phase: str) -> None:
        key = (dropped_phase, incoming_phase)
        self._counts[key] = self._counts.get(key, 0) + 1
        self._mark_dirty()
        self.persist_if_needed()

    def snapshot(self) -> dict[tuple[str, str], int]:
        return dict(self._counts)

    def ack(self, sent: dict[tuple[str, str], int]) -> None:
        if not sent:
            return
        changed = False
        for key, count in sent.items():
            if count <= 0:
                continue
            current = self._counts.get(key, 0)
            remaining = current - count
            if remaining > 0:
                self._counts[key] = remaining
                if remaining != current:
                    changed = True
            elif key in self._counts:
                del self._counts[key]
                changed = True
        if changed:
            self._mark_dirty()
            self.persist_if_needed(force=True)

    def has_pending(self) -> bool:
        return any(count > 0 for count in self._counts.values())

    def pending_event_count(self) -> int:
        return sum(count for count in self._counts.values() if count > 0)

    def persist_if_needed(self, *, force: bool = False) -> None:
        if not self._dirty:
            return
        now = time.monotonic()
        if not force and now < self._next_retry_monotonic:
            return
        should_persist = force or self._last_persist_monotonic == 0.0
        if not should_persist:
            if self._pending_updates >= _DROPPED_STATE_PERSIST_MAX_PENDING_UPDATES:
                should_persist = True
            elif (now - self._last_persist_monotonic) >= _DROPPED_STATE_PERSIST_INTERVAL_SECONDS:
                should_persist = True
        if not should_persist:
            return
        persisted = self.persist_with_state(self._counts)
        if persisted:
            self._dirty = False
            self._pending_updates = 0
            self._last_persist_monotonic = now
            self._next_retry_monotonic = 0.0
            self._persist_failure_count = 0
            return
        self._persist_failure_count += 1
        self._pending_updates = min(
            self._pending_updates,
            max(_DROPPED_STATE_PERSIST_MAX_PENDING_UPDATES - 1, 0),
        )
        self._last_persist_monotonic = now
        self._next_retry_monotonic = now + _compute_failure_backoff_seconds(
            self._persist_failure_count
        )

    def load(self) -> dict[tuple[str, str], int]:
        path = self._path
        if path is None or not path.exists():
            return {}
        _, lock_handle = self._acquire_lock()
        try:
            if not path.exists():
                return {}
            if path.stat().st_size > _DROPPED_STATE_MAX_BYTES:
                logger.warning(
                    "Memory brief status telemetry dropped-state file too large; ignoring persisted state: path=%s",
                    path,
                )
                self._clear_unlocked(path)
                return {}
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning(
                "Failed to load memory brief status telemetry dropped-state file: path=%s",
                path,
                exc_info=True,
            )
            try:
                self._clear_unlocked(path)
            except Exception:
                logger.warning(
                    "Failed to clear malformed memory brief telemetry dropped-state file: path=%s",
                    path,
                    exc_info=True,
                )
            return {}
        finally:
            self._release_lock(lock_handle)

        raw_rows: object
        if isinstance(raw, dict):
            raw_rows = raw.get("dropped_aggregates", [])
        else:
            raw_rows = raw
        if not isinstance(raw_rows, list):
            logger.warning(
                "Memory brief status telemetry dropped-state file has invalid format; expected list rows: path=%s",
                path,
            )
            self.clear_persisted()
            return {}

        recovered: dict[tuple[str, str], int] = {}
        for row in raw_rows:
            try:
                parsed = MemoryBriefStatusDroppedAggregate.model_validate(row)
            except Exception:
                logger.warning(
                    "Memory brief status telemetry dropped-state file contains invalid row; dropping all persisted rows: path=%s",
                    path,
                    exc_info=True,
                )
                self.clear_persisted()
                return {}
            if parsed.count <= 0:
                continue
            key = (parsed.dropped_phase, parsed.incoming_phase)
            recovered[key] = recovered.get(key, 0) + parsed.count
        if recovered:
            logger.info(
                "Recovered memory brief telemetry dropped aggregates from persisted state: pairs=%d dropped_events=%d",
                len(recovered),
                sum(recovered.values()),
            )
        else:
            self.clear_persisted()
        return recovered

    def persist_with_state(self, state: dict[tuple[str, str], int]) -> bool:
        path = self._path
        if path is None:
            return True
        _, lock_handle = self._acquire_lock()
        try:
            if not state:
                self._clear_unlocked(path)
                return True
            payload = {
                "dropped_aggregates": [
                    row.model_dump()
                    for row in serialize_dropped_aggregates(state)
                ]
            }
            serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
            if len(serialized.encode("utf-8")) > _DROPPED_STATE_MAX_BYTES:
                logger.warning(
                    "Memory brief status telemetry dropped-state payload exceeded limit; skipping persist: path=%s",
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
                "Failed to persist memory brief telemetry dropped aggregates: path=%s",
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
                "Failed to clear memory brief telemetry dropped-state file: path=%s",
                path,
                exc_info=True,
            )
        finally:
            self._release_lock(lock_handle)

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._pending_updates += 1

    def _lock_path(self) -> Path | None:
        if self._path is None:
            return None
        return self._path.with_name(f"{self._path.name}{_DROPPED_STATE_LOCK_SUFFIX}")

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


def _compute_failure_backoff_seconds(failure_count: int) -> float:
    if failure_count <= 0:
        return 0.0
    exponent = min(failure_count - 1, 8)
    candidate = _DROPPED_STATE_PERSIST_FAILURE_BASE_BACKOFF_SECONDS * (2 ** exponent)
    return min(candidate, _DROPPED_STATE_PERSIST_FAILURE_MAX_BACKOFF_SECONDS)


def serialize_dropped_aggregates(
    aggregates: dict[tuple[str, str], int],
) -> list[MemoryBriefStatusDroppedAggregate]:
    rows: list[MemoryBriefStatusDroppedAggregate] = []
    for (dropped_phase, incoming_phase), count in sorted(aggregates.items()):
        if count <= 0:
            continue
        rows.append(
            MemoryBriefStatusDroppedAggregate(
                dropped_phase=dropped_phase,
                incoming_phase=incoming_phase,
                count=count,
            )
        )
    return rows
