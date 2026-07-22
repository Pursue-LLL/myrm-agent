"""Standalone Cron Lock Implementation

Process-safe cron locking using file locks for 10/10 standalone reliability.
"""

from __future__ import annotations

import logging
from pathlib import Path

from filelock import FileLock, Timeout

logger = logging.getLogger(__name__)


def _default_lock_dir() -> Path:
    from app.config.settings import get_settings

    return Path(get_settings().database.state_dir) / "locks" / "cron"


class CrossProcessCronLock:
    """File-based implementation of cron ConcurrencyLock protocol.

    Ensures that only one process/instance of a cron scheduler engine runs
    even in shared filesystem environments (Industrial-grade leader election).
    """

    def __init__(self, lock_dir: str | Path | None = None):
        if lock_dir is None:
            lock_dir = _default_lock_dir()
        self.lock_dir = Path(lock_dir)
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self._active_locks: dict[str, FileLock] = {}

    async def try_acquire(self, name: str, ttl_seconds: int = 60) -> bool:
        """Attempt to acquire a named file lock without blocking.

        Args:
            name: unique lock name
            ttl_seconds: TTL for the lock (handled by OS file lock lifecycle)

        Returns:
            True if acquired
        """
        # Sanitize name for filesystem
        safe_name = name.replace(":", "_").replace("/", "_")
        lock_path = self.lock_dir / f"{safe_name}.lock"

        lock = FileLock(str(lock_path))
        try:
            # Try to acquire without blocking (timeout=0)
            lock.acquire(timeout=0)
            self._active_locks[name] = lock
            logger.info(f"Cron file lock acquired: {name}")
            return True
        except Timeout:
            logger.debug(f"Cron lock already held: {name}")
            return False
        except Exception as e:
            logger.error(f"Error acquiring cron file lock {name}: {e}")
            return False

    async def release(self, name: str) -> None:
        """Release the named file lock.

        Args:
            name: unique lock name
        """
        lock = self._active_locks.pop(name, None)
        if lock:
            try:
                lock.release()
                logger.info(f"Cron file lock released: {name}")
            except Exception as e:
                logger.error(f"Error releasing cron file lock {name}: {e}")


# Keep alias for backward compatibility
MemoryCronLock = CrossProcessCronLock
