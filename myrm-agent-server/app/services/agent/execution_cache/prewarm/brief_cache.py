"""In-memory memory-brief cache keyed by chat scope + execution fingerprint.

[INPUT]
- stream_session.memory_brief::build_memory_brief_snapshot (POS: 流式会话的记忆预检构建器)

[OUTPUT]
- BriefCache get/put/invalidate for turn prewarm join

[POS]
execution_cache prewarm brief 缓存。TTL 与 execution_cache 空闲淘汰对齐（~600s）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class CachedBriefBundle:
    preview: dict[str, object]
    snapshot: dict[str, object]
    stored_at: float


class BriefCache:
    def __init__(self, *, ttl_seconds: float = 600.0) -> None:
        self._ttl_seconds = ttl_seconds
        self._entries: dict[str, CachedBriefBundle] = {}

    @staticmethod
    def _key(scope_key: str, fingerprint: str) -> str:
        return f"{scope_key}:{fingerprint}"

    def put(
        self,
        scope_key: str,
        fingerprint: str,
        preview: dict[str, object],
        snapshot: dict[str, object],
    ) -> None:
        cache_key = self._key(scope_key, fingerprint)
        self._entries[cache_key] = CachedBriefBundle(
            preview=preview,
            snapshot=snapshot,
            stored_at=time.monotonic(),
        )

    def get(self, scope_key: str, fingerprint: str) -> CachedBriefBundle | None:
        cache_key = self._key(scope_key, fingerprint)
        entry = self._entries.get(cache_key)
        if entry is None:
            return None
        if time.monotonic() - entry.stored_at > self._ttl_seconds:
            del self._entries[cache_key]
            return None
        return entry

    def prune_expired(self) -> None:
        now = time.monotonic()
        stale = [key for key, entry in self._entries.items() if now - entry.stored_at > self._ttl_seconds]
        for key in stale:
            self._entries.pop(key, None)

    def invalidate_scope(self, scope_key: str) -> None:
        prefix = f"{scope_key}:"
        stale = [key for key in self._entries if key.startswith(prefix)]
        for key in stale:
            del self._entries[key]
