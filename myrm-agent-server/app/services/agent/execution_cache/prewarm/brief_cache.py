"""In-memory memory-brief cache keyed by chat scope + execution fingerprint.

[INPUT]
- none (imports no other project module)

[OUTPUT]
- BriefCache get/take/put/invalidate for turn prewarm join

[POS]
execution_cache prewarm brief 缓存。简报是对存储的纯读取（毫秒级），缓存只把聚焦时的构建交给紧随其后的发送：
一份简报只服务一个回合（`take`），且存活很短，之后的回合都按存储的当前内容重建，上一回合写入的记忆下一回合就进块。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

# A prewarmed brief only bridges the build at composer focus to the send that follows; a longer life would hand the
# turn a memory block older than what the user changed in the meantime.
_DEFAULT_TTL_SECONDS = 10.0


@dataclass(frozen=True)
class CachedBriefBundle:
    preview: dict[str, object]
    snapshot: dict[str, object]
    stored_at: float


class BriefCache:
    def __init__(self, *, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
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

    def take(self, scope_key: str, fingerprint: str) -> CachedBriefBundle | None:
        """Hand out a live entry and drop it, so the next turn reads the store again."""
        entry = self.get(scope_key, fingerprint)
        if entry is not None:
            del self._entries[self._key(scope_key, fingerprint)]
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
