"""Chat-scoped execution cache for built SkillAgent units.

[INPUT]
- myrm_agent_harness.api::SkillAgent (POS: harness agent instance)

[OUTPUT]
- ChatAgentExecutionCache: reuse BuiltExecutionUnit per chat+agent scope
- get_execution_cache(): process-wide singleton
- close_execution_cache_for_chat(): chat delete hook

[POS]
Server business layer. Mirrors ChatRuntimePoolRegistry lifecycle semantics.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TypeAlias

from app.services.agent.execution_cache.types import BuiltExecutionUnit

logger = logging.getLogger(__name__)

_DEFAULT_IDLE_SECONDS = 600.0

BuildUnitFn: TypeAlias = Callable[[], Awaitable[BuiltExecutionUnit]]


@dataclass
class _CacheEntry:
    unit: BuiltExecutionUnit
    config_fingerprint: str
    last_used: float


class ChatAgentExecutionCache:
    """Keeps one BuiltExecutionUnit per chat scope while the conversation stays active."""

    def __init__(self, *, idle_seconds: float = _DEFAULT_IDLE_SECONDS) -> None:
        self._idle_seconds = idle_seconds
        self._entries: dict[str, _CacheEntry] = {}
        self._turn_locks: dict[str, asyncio.Lock] = {}
        self._lock = asyncio.Lock()

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
        async with self._lock:
            await self._evict_idle_unlocked()
            entry = self._entries.get(scope_key)
            if entry is not None and entry.config_fingerprint == config_fingerprint:
                entry.last_used = time.monotonic()
                logger.debug("execution_cache_reuse scope=%s", scope_key)
                return entry.unit

            if entry is not None:
                turn_lock = self._turn_locks.get(scope_key)
                if (
                    entry.config_fingerprint != config_fingerprint
                    and turn_lock is not None
                    and turn_lock.locked()
                ):
                    logger.warning(
                        "execution_cache_replace_deferred scope=%s reason=config_changed_active_turn",
                        scope_key,
                    )
                    entry.last_used = time.monotonic()
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
            logger.info("execution_cache_created scope=%s", scope_key)
            return unit

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

    async def _evict_idle_unlocked(self) -> None:
        now = time.monotonic()
        stale = [
            scope_key
            for scope_key, entry in self._entries.items()
            if now - entry.last_used > self._idle_seconds
        ]
        for scope_key in stale:
            entry = self._entries.pop(scope_key)
            self._turn_locks.pop(scope_key, None)
            await entry.unit.teardown()
            logger.info("execution_cache_evicted_idle scope=%s idle_s=%.0f", scope_key, self._idle_seconds)


_registry: ChatAgentExecutionCache | None = None


def get_execution_cache() -> ChatAgentExecutionCache:
    global _registry
    if _registry is None:
        _registry = ChatAgentExecutionCache()
    return _registry


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
