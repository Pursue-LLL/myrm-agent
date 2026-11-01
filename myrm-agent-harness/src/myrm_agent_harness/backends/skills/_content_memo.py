"""Content-addressed memo for pure derivations of skill text.

[INPUT]
- utils.lru_cache::LRUCache (POS: OrderedDict LRU used as the bounded store)

[OUTPUT]
- ContentMemo: bounded, thread-safe memo keyed by a digest of the exact text
- clear_content_memos(): empty every memo (test isolation)

[POS]
Listing skills re-derives the same facts (frontmatter, security scan, token count) from unchanged SKILL.md text on
every agent turn. Each derivation is a pure function of the text, so the digest of the text is a complete cache key:
an edit changes the digest and can never be answered from a stale entry, so nothing needs invalidation or a watcher.
Only the digest is kept, never the text. Oversized text and results a caller declines to keep bypass the memo, which
bounds memory whatever a skill contains.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable

from myrm_agent_harness.utils.lru_cache import LRUCache

# SKILL.md files run a few KB (largest in this repo: 30 KB); anything beyond this is recomputed each time.
_MAX_MEMOIZED_CHARS = 64 * 1024
# Entries are content-addressed and never go stale; the LRU bound is the only eviction.
_NEVER_EXPIRES_S = 10 * 365 * 24 * 3600

_clearers: list[Callable[[], None]] = []


class ContentMemo[V]:
    """Bounded LRU memo of ``compute()`` results, keyed by ``(scope, digest of content)``.

    Stored values are shared between callers, so a value that callers may mutate must be copied by the caller.
    """

    def __init__(self, name: str, *, maxsize: int = 512) -> None:
        self._cache = LRUCache[V](maxsize=maxsize, ttl=_NEVER_EXPIRES_S, id=name)
        # LRUCache is only safe on a single thread; skill listing also runs on worker threads.
        self._lock = threading.Lock()
        _clearers.append(self.clear)

    def get_or_compute(
        self,
        content: str,
        compute: Callable[[], V],
        *,
        scope: str = "",
        keep: Callable[[V], bool] | None = None,
    ) -> V:
        """Return the memoized value for ``content``, computing it on a miss.

        Args:
            content: Text the value is derived from (the only input besides ``scope``).
            compute: Pure derivation of ``content`` and ``scope``; an exception propagates and is not memoized.
            scope: Any other input of the derivation (e.g. the skill name), so equal text under another scope misses.
            keep: Return False for a value too large to pin; it is still returned, just not stored.
        """
        if len(content) > _MAX_MEMOIZED_CHARS:
            return compute()
        # surrogatepass: lone surrogates must still hash (strict UTF-8 would raise where the derivation itself works).
        digest = hashlib.sha256(content.encode("utf-8", "surrogatepass")).hexdigest()
        key = f"{scope}\x00{digest}"
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached
        value = compute()
        if keep is None or keep(value):
            with self._lock:
                self._cache.set(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


def clear_content_memos() -> None:
    """Empty every memo, so a test never observes another test's derivations."""
    for clear in _clearers:
        clear()
