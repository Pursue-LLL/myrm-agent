"""Domain-level learning metrics manager.

Responsibilities:
- Unified management of all domain learning metrics (web_fetch + browser)
- Provides domain-level failure decay and wait strategy data
- JSON serialization persistence (with file lock support), saved and cleaned up on a schedule as the store is used

Architecture:
- Framework layer adapts to deployment scenarios via parameter injection
- Default state file: <state root>/domain_metrics.json, with the state root from ``resolve_workspace_state_dir()``

[INPUT]
- infra.delivery.storage_metrics::MonitoredStorageCallback (POS: StorageProvider)
- toolkits.storage.base::StorageProvider (POS: Storage provider abstract base class. Defines the unified storage interface contract for all storage backends. Supports file read/write, delete, list, and info query. Method names use read/write (not get/put).)
- infra.data_dir::resolve_workspace_state_dir (POS: Single entry point for the Myrm state root; harness and server code derive every state path from it)

[OUTPUT]
- DomainMetricsManager: Domain-level learning metrics manager.
- get_global_domain_metrics_manager: Get the global domain metrics manager (singleton).

[POS]
Domain-level learning metrics manager.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.data_dir import resolve_workspace_state_dir
from myrm_agent_harness.utils import os_compat as fcntl

from ..fetchers.protocols import FetcherType
from .models import DomainMetrics

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.storage.base import StorageProvider

logger = logging.getLogger(__name__)

_CLEANUP_INTERVAL_SECONDS = 3600

_global_domain_metrics_manager: DomainMetricsManager | None = None


def get_global_domain_metrics_manager() -> DomainMetricsManager:
    """Get the global domain metrics manager (singleton)."""
    global _global_domain_metrics_manager
    if _global_domain_metrics_manager is None:
        _global_domain_metrics_manager = DomainMetricsManager()
    return _global_domain_metrics_manager


class DomainMetricsManager:
    """Domain-level learning metrics manager.

    Core capabilities:
    - Domain-level metric storage and retrieval
    - Async background persistence, scheduled lazily whenever the store is used
    - StorageProvider support (cloud storage S3/R2/GCS)
    - File lock support (local filesystem multi-process scenarios)
    - Auto-cleanup of expired domains (7 days inactive)

    Two storage modes:
    1. StorageProvider mode: abstract interface, supports cloud storage (S3/R2/GCS)
    2. Local file mode: direct Path operations, with file lock (fcntl)

    Note: StorageProvider mode does not load data in __init__ (async lazy load);
          local file mode loads synchronously in __init__.

    Concurrency model:
    - Re-entrant lock protects in-memory data structures
    - File lock protects local JSON file (multi-process scenarios)
    """

    def __init__(
        self,
        *,
        storage_path: str | Path | None = None,
        storage_provider: StorageProvider | None = None,
        storage_key: str = "web_fetch/domain_metrics.json",
        use_file_lock: bool = False,
        max_domains: int = 10000,
        save_interval_minutes: int = 5,
        inactive_days: int = 7,
    ):
        """Initialize domain metrics manager.

        Args:
            storage_path: Storage file path (local mode, None uses default path)
            storage_provider: Storage provider (cloud storage mode, optional)
            storage_key: Storage key (StorageProvider mode, default: "web_fetch/domain_metrics.json")
            use_file_lock: Whether to enable file lock (local mode, multi-process scenarios)
            max_domains: Maximum domain count (LRU eviction)
            save_interval_minutes: Auto-save interval (minutes)
            inactive_days: Inactive domain cleanup threshold (days)
        """
        self._storage_path = self._resolve_storage_path(storage_path) if not storage_provider else None
        self._storage_provider = storage_provider
        self._storage_key = storage_key
        self._use_file_lock = use_file_lock
        self._max_domains = max_domains
        self._save_interval_minutes = save_interval_minutes
        self._inactive_days = inactive_days

        self._lock = threading.RLock()
        self._metrics: dict[str, DomainMetrics] = {}

        self._save_pending = False
        self._saver_task: asyncio.Task[None] | None = None
        self._shutdown_event = threading.Event()
        self._last_save_time = time.time()
        self._last_cleanup_time = time.time()

        # Local file mode: synchronous load
        # StorageProvider mode: deferred async load (cache nature)
        if self._storage_path:
            self._load_metrics()

        logger.info(
            f"DomainMetricsManager initialized: {len(self._metrics)} domains, "
            f"file_lock={self._use_file_lock}, "
            f"storage={'StorageProvider' if self._storage_provider else str(self._storage_path)}"
        )

    @staticmethod
    def _resolve_storage_path(path: str | Path | None) -> Path:
        """Resolve storage path.

        Path selection priority:
        1. Explicit path parameter
        2. ``MYRM_DATA_DIR``, then the cloud sandbox's ``/workspace/.myrm/``, then ``~/.myrm/``
        """
        if path is not None:
            return Path(path)

        return resolve_workspace_state_dir() / "domain_metrics.json"

    def _load_metrics(self) -> None:
        """Load domain metrics from JSON file (local file mode).

        Uses fcntl file lock (synchronous), for multi-process concurrent scenarios.
        """
        assert self._storage_path is not None

        if not self._storage_path.exists():
            logger.info(f"Metrics file not found, starting fresh: {self._storage_path}")
            return

        try:
            with open(self._storage_path, encoding="utf-8") as f:
                if self._use_file_lock:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)

                try:
                    data = json.load(f)
                    loaded_metrics = {
                        domain: DomainMetrics.from_dict(metrics_data) for domain, metrics_data in data.items()
                    }
                finally:
                    if self._use_file_lock:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            self._metrics = loaded_metrics
            logger.info(f"Loaded {len(self._metrics)} domain metrics from {self._storage_path}")

        except Exception:
            logger.error(f"Failed to load metrics from {self._storage_path}", exc_info=True)
            self._metrics = {}

    async def load_metrics_async(self) -> None:
        """Async-load domain metrics (StorageProvider mode)."""
        storage = self._storage_provider
        if storage is None:
            raise RuntimeError("load_metrics_async requires StorageProvider mode")
        from myrm_agent_harness.infra.delivery.storage_metrics import (
            MonitoredStorageCallback,
            get_global_storage_metrics,
        )
        from myrm_agent_harness.infra.delivery.storage_resilience import resilient_storage_operation

        async def _load() -> dict[str, DomainMetrics]:
            data_bytes = await storage.read(self._storage_key)
            data = json.loads(data_bytes.decode("utf-8"))
            return {domain: DomainMetrics.from_dict(metrics_data) for domain, metrics_data in data.items()}

        callback = MonitoredStorageCallback(get_global_storage_metrics())
        try:
            loaded_metrics = await resilient_storage_operation("read", _load, max_retries=2, callback=callback)

            with self._lock:
                self._metrics = loaded_metrics

            logger.info(f"Loaded {len(self._metrics)} domain metrics from StorageProvider")

        except FileNotFoundError:
            logger.info(f"Metrics not found in StorageProvider, starting fresh: {self._storage_key}")
        except Exception:
            logger.error(
                f"Failed to load metrics from StorageProvider after retries: {self._storage_key}", exc_info=True
            )

    def _save_metrics(self) -> None:
        """Save domain metrics to JSON file (local file mode, snapshot copy avoids data races)."""
        assert self._storage_path is not None

        try:
            from myrm_agent_harness.infra.atomic_write import atomic_write

            with self._lock:
                snapshot = {domain: metrics.to_dict() for domain, metrics in self._metrics.items()}

            atomic_write(self._storage_path, json.dumps(snapshot, indent=2))
            logger.info(f"Saved {len(snapshot)} domain metrics to {self._storage_path}")

        except Exception:
            logger.error(f"Failed to save metrics to {self._storage_path}", exc_info=True)

    async def _save_metrics_async(self) -> None:
        """Async-save domain metrics to StorageProvider."""
        storage = self._storage_provider
        assert storage is not None
        from myrm_agent_harness.infra.delivery.storage_metrics import (
            MonitoredStorageCallback,
            get_global_storage_metrics,
        )
        from myrm_agent_harness.infra.delivery.storage_resilience import resilient_storage_operation

        with self._lock:
            snapshot = {domain: metrics.to_dict() for domain, metrics in self._metrics.items()}

        async def _write() -> None:
            data_bytes = json.dumps(snapshot, indent=2).encode("utf-8")
            await storage.write(self._storage_key, data_bytes)

        callback = MonitoredStorageCallback(get_global_storage_metrics())
        try:
            await resilient_storage_operation("write", _write, max_retries=3, callback=callback)
            logger.info(f"Saved {len(snapshot)} domain metrics to StorageProvider")
        except Exception:
            logger.error(f"Failed to save metrics to StorageProvider after retries: {self._storage_key}", exc_info=True)

    def get_or_create(self, domain: str) -> DomainMetrics:
        """Get or create domain metrics (thread-safe); also runs the scheduled save and cleanup."""
        self._maintain()
        with self._lock:
            if domain not in self._metrics:
                self._metrics[domain] = DomainMetrics(domain=domain)

                if len(self._metrics) > self._max_domains:
                    self._evict_lru()

            return self._metrics[domain]

    def record_failure(self, domain: str, fetcher_type: FetcherType) -> None:
        """Record a failed fetch attempt of a tier on a domain."""
        self.get_or_create(domain).record_failure(fetcher_type)

    def _maintain(self) -> None:
        """Run the scheduled save (every ``save_interval_minutes``) and cleanup (hourly).

        Nothing else drives them, so they are checked whenever the store is used.
        """
        now = time.time()
        with self._lock:
            save_due = now - self._last_save_time >= self._save_interval_minutes * 60
            cleanup_due = now - self._last_cleanup_time >= _CLEANUP_INTERVAL_SECONDS
            if save_due:
                self._last_save_time = now
            if cleanup_due:
                self._last_cleanup_time = now
        if save_due:
            self.request_save()
        if cleanup_due:
            self.cleanup_inactive_domains()

    def get(self, domain: str) -> DomainMetrics | None:
        """Get domain metrics (read-only, thread-safe)."""
        with self._lock:
            return self._metrics.get(domain)

    def _evict_lru(self) -> None:
        """Evict the least recently accessed domain (LRU)."""
        if not self._metrics:
            return

        lru_domain = min(self._metrics.items(), key=lambda x: x[1].last_access)[0]
        del self._metrics[lru_domain]
        logger.info(f"Evicted LRU domain: {lru_domain}")

    def request_save(self) -> None:
        """Request async save."""
        self._save_pending = True
        if self._saver_task is None or self._saver_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._saver_task = loop.create_task(self._background_saver())
            except RuntimeError:
                # No event loop: synchronous save (local file mode only)
                if self._storage_path:
                    self._save_metrics()
                # StorageProvider mode cannot save synchronously, skip

    async def _background_saver(self) -> None:
        """Background save task."""
        while not self._shutdown_event.is_set():
            await asyncio.sleep(1.0)
            if self._save_pending:
                self._save_pending = False
                if self._storage_provider:
                    await self._save_metrics_async()
                else:
                    await asyncio.to_thread(self._save_metrics)

    def cleanup_inactive_domains(self) -> None:
        """Clean up long-inactive domains."""
        now = time.time()
        cutoff = now - self._inactive_days * 86400

        with self._lock:
            inactive = [domain for domain, metrics in self._metrics.items() if metrics.last_access < cutoff]

            for domain in inactive:
                del self._metrics[domain]

            if inactive:
                logger.info(f"Cleaned up {len(inactive)} inactive domains")

    def shutdown(self) -> None:
        """Save state on close (synchronous, reliable only for local file mode)."""
        self._shutdown_event.set()

        # Local file mode: synchronous save
        if self._storage_path:
            self._save_metrics()
        # StorageProvider mode: cannot save synchronously, relies on background task

    async def shutdown_async(self) -> None:
        """Async close and save state (recommended for StorageProvider mode)."""
        self._shutdown_event.set()
        if self._saver_task and not self._saver_task.done():
            await self._saver_task

        # Final save
        if self._storage_provider:
            await self._save_metrics_async()
        else:
            await asyncio.to_thread(self._save_metrics)
