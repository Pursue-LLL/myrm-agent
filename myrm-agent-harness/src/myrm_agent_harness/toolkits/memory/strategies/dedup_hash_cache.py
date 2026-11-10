"""Layer 1 of deduplication: the namespace-scoped hash key, its metrics and its persistence on disk.

[INPUT]
- infra.atomic_write::atomic_write (POS: crash-safe file replacement)
- infra.data_dir::resolve_data_dir (POS: Single entry point for the Myrm state root; harness and server code derive every state path from it)
- strategies.dedup_types::DeduplicatableMemory (POS: the memory types deduplication compares and merges)

[OUTPUT]
- NAMESPACE_DELIMITER, hash_cache_key: the key that binds a normalized content hash to the memory's own namespaces
- HashCacheMetrics: performance metrics of hash-based deduplication
- default_hash_cache_path, load_hash_cache, save_hash_cache: where the keys live on disk, and reading and writing them

[POS]
The pieces of the hash layer that need no deduplicator state: how a key is built, what is counted, and how the
cache survives a restart. A key without a namespace part cannot have been written by ``hash_cache_key``, so loading
drops it; the file is replaced atomically, so a crash never leaves half a cache behind.
"""

from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict
from dataclasses import dataclass

from myrm_agent_harness.infra.data_dir import resolve_data_dir
from myrm_agent_harness.toolkits.memory.strategies.dedup_types import DeduplicatableMemory

logger = logging.getLogger(__name__)

NAMESPACE_DELIMITER = "|"


def hash_cache_key(memory: DeduplicatableMemory, content_hash: str) -> str:
    """Namespace-scoped hash cache key.

    Same content written into different scopes must not suppress each other,
    so the cache key binds the hash to the memory's own namespaces.
    """
    namespaces = ",".join(sorted(memory.scope.namespaces))
    return f"{namespaces}{NAMESPACE_DELIMITER}{content_hash}"


@dataclass
class HashCacheMetrics:
    """Performance metrics for hash-based deduplication.

    Attributes:
        total_checks: Total number of deduplication checks
        cache_hits: Duplicates caught by hash layer
        cache_misses: New content not in cache
        evictions: Number of FIFO evictions performed
    """

    total_checks: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        """Cache hit rate."""
        return self.cache_hits / self.total_checks if self.total_checks > 0 else 0.0


def default_hash_cache_path() -> str:
    """Get default hash cache persistence path."""
    cache_dir = resolve_data_dir() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return str(cache_dir / "hash_cache.json")


def load_hash_cache(path: str, max_size: int) -> OrderedDict[str, None]:
    """Load the newest ``max_size`` persisted keys; a missing or unreadable file yields what could be read."""
    cache: OrderedDict[str, None] = OrderedDict()
    if not os.path.exists(path):
        return cache

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            hashes = data.get("hashes", [])
            for h in hashes[-max_size:]:
                if NAMESPACE_DELIMITER not in h:
                    continue
                cache[h] = None
            logger.info("Loaded %d hashes from %s", len(cache), path)
    except Exception as e:
        logger.warning("Failed to load hash cache: %s", e)
    return cache


def save_hash_cache(path: str, cache: OrderedDict[str, None]) -> None:
    """Save hash cache to disk with atomic write."""
    try:
        from myrm_agent_harness.infra.atomic_write import atomic_write

        data = {"hashes": list(cache.keys())}
        atomic_write(path, json.dumps(data))
    except Exception as e:
        logger.warning("Failed to save hash cache: %s", e)
