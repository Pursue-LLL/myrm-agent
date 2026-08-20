"""Chat-scoped execution cache for built SkillAgent units.

[INPUT]
- myrm_agent_harness.api::SkillAgent (POS: harness agent 实例)

[OUTPUT]
- ChatAgentExecutionCache: reuse BuiltExecutionUnit per chat+agent scope
- get_execution_cache(): process-wide singleton
- close_execution_cache_for_chat(): chat delete hook

[POS]
execution_cache 缓存注册表。维护 chat+agent 作用域的 BuiltExecutionUnit 池
（acquire/release/refresh/guard_turn/idle-evict），进程级 singleton。
"""

from __future__ import annotations

import asyncio
import contextlib
import gc
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TypeAlias

from app.config.settings import settings
from app.services.agent.execution_cache.types import BuiltExecutionUnit

logger = logging.getLogger(__name__)

_DEFAULT_IDLE_SECONDS = 1800.0
_IDLE_REAPER_MAX_INTERVAL_SECONDS = 60.0

BuildUnitFn: TypeAlias = Callable[[], Awaitable[BuiltExecutionUnit]]


@dataclass
class _CacheEntry:
    unit: BuiltExecutionUnit
    config_fingerprint: str
    last_used: float


class ChatAgentExecutionCache:
    """Keeps one BuiltExecutionUnit per chat scope while the conversation stays active."""

    def __init__(self, *, idle_seconds: float | None = None) -> None:
        self._idle_seconds = (
            idle_seconds
            if idle_seconds is not None
            else getattr(
                getattr(settings, "execution_cache", None),
                "idle_reclaim_timeout_seconds",
                _DEFAULT_IDLE_SECONDS,
            )
        )
        self._entries: dict[str, _CacheEntry] = {}
        self._turn_locks: dict[str, asyncio.Lock] = {}
        self._lock = asyncio.Lock()
        self._idle_reaper_task: asyncio.Task[None] | None = None
        self._reclaimed_count = 0

    @property
    def idle_seconds(self) -> float:
        return self._idle_seconds

    @property
    def warm_entry_count(self) -> int:
        return len(self._entries)

    @property
    def reclaimed_count(self) -> int:
        return self._reclaimed_count

    def _ensure_idle_reaper(self) -> None:
        if self._idle_seconds <= 0:
            return
        if self._idle_reaper_task is not None and not self._idle_reaper_task.done():
            return
        self._idle_reaper_task = asyncio.create_task(
            self._idle_reaper_loop(),
            name="execution-cache-idle-reaper",
        )

    async def _idle_reaper_loop(self) -> None:
        interval = min(
            _IDLE_REAPER_MAX_INTERVAL_SECONDS,
            max(0.01, self._idle_seconds / 2),
        )
        try:
            while True:
                await asyncio.sleep(interval)
                async with self._lock:
                    await self._evict_idle_unlocked()
        except asyncio.CancelledError:
            return

    @asynccontextmanager
    async def guard_turn(self, scope_key: str | None) -> AsyncGenerator[None, None]:
        if not scope_key:
            yield
            return
        turn_lock = self._turn_locks.setdefault(scope_key, asyncio.Lock())
        async with turn_lock:
            yield

    async def acquire(
        self,
        scope_key: str,
        config_fingerprint: str,
        build_unit: BuildUnitFn,
    ) -> BuiltExecutionUnit:
        self._ensure_idle_reaper()
        async with self._lock:
            await self._evict_idle_unlocked()
            entry = self._entries.get(scope_key)
            if entry is not None and entry.config_fingerprint == config_fingerprint:
                entry.last_used = time.monotonic()
                logger.warning("execution_cache_reuse scope=%s", scope_key)
                return entry.unit

            if entry is not None:
                turn_lock = self._turn_locks.get(scope_key)
                if entry.config_fingerprint != config_fingerprint and turn_lock is not None and turn_lock.locked():
                    logger.warning(
                        "execution_cache_replace_deferred scope=%s reason=config_changed_active_turn",
                        scope_key,
                    )
                    entry.last_used = time.monotonic()
                    logger.warning("execution_cache_reuse scope=%s", scope_key)
                    return entry.unit

                logger.info(
                    "execution_cache_replace scope=%s reason=%s",
                    scope_key,
                    "config_changed" if entry.config_fingerprint != config_fingerprint else "missing",
                )
                await entry.unit.teardown()

            unit = await build_unit()
            self._entries[scope_key] = _CacheEntry(
                unit=unit,
                config_fingerprint=config_fingerprint,
                last_used=time.monotonic(),
            )
            logger.warning("execution_cache_created scope=%s", scope_key)
            return unit

    async def is_warm(self, scope_key: str, config_fingerprint: str) -> bool:
        async with self._lock:
            entry = self._entries.get(scope_key)
            return entry is not None and entry.config_fingerprint == config_fingerprint

    async def release(self, scope_key: str) -> None:
        async with self._lock:
            entry = self._entries.get(scope_key)
            if entry is not None:
                entry.last_used = time.monotonic()

    async def refresh_unit(self, scope_key: str, unit: BuiltExecutionUnit) -> None:
        """Persist wrapper mutations (browser checkpoint, thread id) into the cache entry."""
        async with self._lock:
            entry = self._entries.get(scope_key)
            if entry is not None:
                entry.unit = unit
                entry.last_used = time.monotonic()

    async def snapshot_warm_units(self) -> list[tuple[str, BuiltExecutionUnit]]:
        """Return a snapshot of all warm scope keys and their execution units."""
        async with self._lock:
            return [(scope_key, entry.unit) for scope_key, entry in self._entries.items()]

    async def is_scope_turn_active(self, scope_key: str) -> bool:
        """True when a turn is actively holding the per-scope turn lock."""
        turn_lock = self._turn_locks.get(scope_key)
        return turn_lock is not None and turn_lock.locked()

    async def close_scope(self, scope_key: str) -> None:
        async with self._lock:
            entry = self._entries.pop(scope_key, None)
            self._turn_locks.pop(scope_key, None)
            if entry is not None:
                await entry.unit.teardown()
                logger.info("execution_cache_closed scope=%s", scope_key)

    async def close_scopes_for_chat(self, chat_id: str) -> None:
        """Close every cached scope for one chat (all agent profiles)."""
        prefix = f"{chat_id.strip()}:"
        async with self._lock:
            keys = [key for key in self._entries if key.startswith(prefix)]
        for key in keys:
            await self.close_scope(key)

    async def close_all(self) -> None:
        async with self._lock:
            for scope_key, entry in list(self._entries.items()):
                try:
                    await entry.unit.teardown()
                except Exception:
                    logger.warning("execution_cache_close_all_failed scope=%s", scope_key, exc_info=True)
            self._entries.clear()
            self._turn_locks.clear()
        reaper = self._idle_reaper_task
        self._idle_reaper_task = None
        if reaper is not None and not reaper.done():
            reaper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reaper

    async def _evict_idle_unlocked(self) -> None:
        if self._idle_seconds <= 0:
            return
        now = time.monotonic()
        stale_keys = [
            scope_key
            for scope_key, entry in self._entries.items()
            if now - entry.last_used > self._idle_seconds
            and not ((turn_lock := self._turn_locks.get(scope_key)) is not None and turn_lock.locked())
        ]
        evicted_entries: list[tuple[str, _CacheEntry]] = []
        for scope_key in stale_keys:
            entry = self._entries.pop(scope_key, None)
            if entry is not None:
                self._turn_locks.pop(scope_key, None)
                evicted_entries.append((scope_key, entry))

        if not evicted_entries:
            return

        for scope_key, entry in evicted_entries:
            try:
                await entry.unit.teardown()
                self._reclaimed_count += 1
                logger.info(
                    "execution_cache_evicted_idle scope=%s idle_s=%.0f",
                    scope_key,
                    self._idle_seconds,
                )
            except Exception:
                logger.warning(
                    "execution_cache_evict_teardown_failed scope=%s",
                    scope_key,
                    exc_info=True,
                )

        # Trigger garbage collection to reclaim memory back to OS
        gc.collect()


_registry: ChatAgentExecutionCache | None = None


def get_execution_cache() -> ChatAgentExecutionCache:
    global _registry
    if _registry is None:
        _registry = ChatAgentExecutionCache()
    return _registry


def _reset_execution_cache_for_testing() -> None:
    """Drop process singleton so the next access binds asyncio locks to the active loop."""
    global _registry
    _registry = None


async def close_execution_cache_for_chat(chat_id: str | None, *, agent_id: str | None = None) -> None:
    if not chat_id or not chat_id.strip():
        return
    from app.services.agent.execution_cache.fingerprint import build_execution_scope_key

    scope = build_execution_scope_key(chat_id, agent_id)
    if scope is None:
        return
    try:
        await get_execution_cache().close_scope(scope)
    except Exception:
        logger.warning("execution_cache_close_chat_failed scope=%s", scope, exc_info=True)


async def close_execution_cache_for_chat_all_agents(chat_id: str | None) -> None:
    """Close every cached scope whose key starts with ``chat_id:``."""
    if not chat_id or not chat_id.strip():
        return
    try:
        await get_execution_cache().close_scopes_for_chat(chat_id.strip())
    except Exception:
        logger.warning("execution_cache_close_chat_failed chat=%s", chat_id, exc_info=True)
