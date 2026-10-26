"""Chat-scoped RuntimePool registry for external CLI delegation.

[INPUT]
- myrm_agent_harness.toolkits.acp.runtime.pool::RuntimePool (POS: runtime pool management layer)

[OUTPUT]
- ChatRuntimePoolRegistry: reuse RuntimePool per conversation for CLI --resume across messages
- ChatScopedRuntimePoolFacade: per-chat single-flight guard around pool.run_turn (cancel lock-exempt); keeps its pool registered
- get_chat_runtime_pool_registry(): process-wide singleton accessor
- close_runtime_pool_bounded(): close a RuntimePool within a hard time limit, never raising

[POS]
Server 业务层外部 Agent 运行时池生命周期。按 chat 复用 harness RuntimePool，
支持 per-chat turn lock 串行化 CLI run_turn；cancel 为 lock-exempt 中断语义。
idle 计时在 acquire / release / 每次委托 turn 结束时刷新；持 turn lock 的在途委托不参与 idle 驱逐。
配置变更或 idle 超时再 close；服务关闭时由 close_all 统一收尾。
执行单元缓存（1800s）比 idle 驱逐（600s）活得久：缓存命中的旧 facade 在池被驱逐后再委托时，
已关闭的 RuntimePool 会懒重建后端；facade 每个委托 turn 先 ensure_tracked 把池重新登记，
这些后端才会被 close_chat / close_all 收尾而不是变成孤儿进程。
所有 pool 关闭都带上限（close_runtime_pool_bounded），失联的外部 agent 不会拖死持锁的 registry。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
    from myrm_agent_harness.toolkits.acp.types import McpServerConfig, RuntimeConfig, RuntimeEvent

logger = logging.getLogger(__name__)

_DEFAULT_IDLE_SECONDS = 600.0
# Slowest legitimate close is a CLI backend waiting 5s for SIGTERM before SIGKILL; backends close concurrently.
_POOL_CLOSE_TIMEOUT_SECONDS = 10.0

BuildPoolFn: TypeAlias = Callable[[], Awaitable["RuntimePool"]]


@dataclass
class _ChatPoolEntry:
    pool: RuntimePool
    config_fingerprint: str
    last_used: float


async def close_runtime_pool_bounded(pool: RuntimePool, *, scope: str) -> None:
    """Close a pool without letting an unresponsive backend wedge the caller.

    ``RuntimePool.close_all`` has no upper bound of its own, and the registry closes pools while
    holding its lock, so one backend that never finishes closing would freeze every chat. This is the
    safety net above the per-backend limits (``AcpRuntime`` bounds ``session/close`` itself).
    Timeouts and failures are logged, never raised; cancellation still propagates.
    """
    try:
        async with asyncio.timeout(_POOL_CLOSE_TIMEOUT_SECONDS):
            await pool.close_all()
    except TimeoutError:
        logger.warning("runtime_pool_close_timeout scope=%s timeout_s=%.0f", scope, _POOL_CLOSE_TIMEOUT_SECONDS)
    except Exception:
        logger.warning("runtime_pool_close_failed scope=%s", scope, exc_info=True)


async def _close_entries(entries: list[tuple[str, _ChatPoolEntry]]) -> None:
    """Close several chat pools concurrently so the worst case stays one timeout, not one per pool."""
    await asyncio.gather(*(close_runtime_pool_bounded(entry.pool, scope=chat) for chat, entry in entries))


class ChatRuntimePoolRegistry:
    """Keeps one RuntimePool per chat while the conversation stays active."""

    def __init__(self, *, idle_seconds: float = _DEFAULT_IDLE_SECONDS) -> None:
        self._idle_seconds = idle_seconds
        self._entries: dict[str, _ChatPoolEntry] = {}
        self._turn_locks: dict[str, asyncio.Lock] = {}
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def guard_turn(self, chat_scope_id: str | None) -> AsyncGenerator[None, None]:
        """Serialize external CLI turns for one chat (one CliRuntime subprocess).

        The idle clock restarts when the turn ends, so a delegation that outlived the
        idle window is not evicted the moment it finishes (which would drop the CLI
        session id used for ``--resume``).
        """
        if not chat_scope_id:
            yield
            return
        turn_lock = self._turn_locks.setdefault(chat_scope_id, asyncio.Lock())
        async with turn_lock:
            try:
                yield
            finally:
                self._touch(chat_scope_id)

    async def acquire(
        self,
        chat_scope_id: str,
        config_fingerprint: str,
        build_pool: BuildPoolFn,
    ) -> RuntimePool:
        """Return an existing pool for the chat or create one with ``build_pool``."""
        async with self._lock:
            await self._evict_idle_unlocked()
            entry = self._entries.get(chat_scope_id)
            if entry is not None and entry.config_fingerprint == config_fingerprint:
                entry.last_used = time.monotonic()
                logger.debug("runtime_pool_reuse chat=%s", chat_scope_id)
                return entry.pool

            if entry is not None:
                # The matching-fingerprint case returned above, so reaching here means the config changed.
                if self._is_turn_active(chat_scope_id):
                    logger.warning(
                        "runtime_pool_replace_deferred chat=%s reason=config_changed_active_turn",
                        chat_scope_id,
                    )
                    entry.last_used = time.monotonic()
                    return entry.pool

                logger.info("runtime_pool_replace chat=%s reason=config_changed", chat_scope_id)
                await close_runtime_pool_bounded(entry.pool, scope=chat_scope_id)

            pool = await build_pool()
            self._entries[chat_scope_id] = _ChatPoolEntry(
                pool=pool,
                config_fingerprint=config_fingerprint,
                last_used=time.monotonic(),
            )
            logger.info("runtime_pool_created chat=%s backends=%d", chat_scope_id, len(pool.available_backends))
            return pool

    async def release(self, chat_scope_id: str) -> None:
        """Mark a chat pool idle after a message completes (does not close CLI)."""
        async with self._lock:
            self._touch(chat_scope_id)

    async def ensure_tracked(
        self,
        chat_scope_id: str,
        config_fingerprint: str,
        pool: RuntimePool,
    ) -> RuntimePool:
        """Return the pool a delegation turn must run on, re-registering ``pool`` if eviction dropped it.

        A closed ``RuntimePool`` stays usable and re-spawns its backends on the next turn. Running on one
        that is no longer registered would leave those processes invisible to ``close_chat`` / ``close_all``.
        The registry is the source of truth: when it already holds a different pool for the chat, use that.
        """
        entry = self._entries.get(chat_scope_id)
        if entry is not None and entry.pool is pool:
            # Lock-free: a turn must not wait behind another chat's slow pool close. The caller holds the
            # chat's turn lock, so idle eviction cannot drop this entry between the check and the turn.
            return pool
        async with self._lock:
            entry = self._entries.get(chat_scope_id)
            if entry is not None:
                return entry.pool
            self._entries[chat_scope_id] = _ChatPoolEntry(
                pool=pool,
                config_fingerprint=config_fingerprint,
                last_used=time.monotonic(),
            )
            # close_all stopped the pool's health monitor; resume supervising the backends it re-spawns.
            await pool.start_monitoring()
            logger.info("runtime_pool_readopted chat=%s", chat_scope_id)
            return pool

    async def close_chat(self, chat_scope_id: str) -> None:
        """Explicitly tear down a chat pool (e.g. conversation deleted)."""
        async with self._lock:
            entry = self._entries.pop(chat_scope_id, None)
            self._turn_locks.pop(chat_scope_id, None)
            if entry is not None:
                await close_runtime_pool_bounded(entry.pool, scope=chat_scope_id)
                logger.info("runtime_pool_closed chat=%s", chat_scope_id)

    async def close_all(self) -> None:
        """Shut down every pooled RuntimePool."""
        async with self._lock:
            entries = list(self._entries.items())
            self._entries.clear()
            self._turn_locks.clear()
            await _close_entries(entries)

    def _is_turn_active(self, chat_scope_id: str) -> bool:
        """True while a delegation turn holds the chat's turn lock."""
        turn_lock = self._turn_locks.get(chat_scope_id)
        return turn_lock is not None and turn_lock.locked()

    def _touch(self, chat_scope_id: str) -> None:
        """Restart the idle clock of a chat pool (no-op once the pool is gone)."""
        entry = self._entries.get(chat_scope_id)
        if entry is not None:
            entry.last_used = time.monotonic()

    async def _evict_idle_unlocked(self) -> None:
        """Close pools idle past the window; a pool with an in-flight turn is never idle."""
        now = time.monotonic()
        stale = [
            chat_scope_id
            for chat_scope_id, entry in self._entries.items()
            if now - entry.last_used > self._idle_seconds and not self._is_turn_active(chat_scope_id)
        ]
        if not stale:
            return
        evicted: list[tuple[str, _ChatPoolEntry]] = []
        for chat_scope_id in stale:
            evicted.append((chat_scope_id, self._entries.pop(chat_scope_id)))
            self._turn_locks.pop(chat_scope_id, None)
        await _close_entries(evicted)
        for chat_scope_id, _ in evicted:
            logger.info("runtime_pool_evicted_idle chat=%s idle_s=%.0f", chat_scope_id, self._idle_seconds)


class ChatScopedRuntimePoolFacade:
    """Wraps a RuntimePool with per-chat turn serialization for shared CliRuntime."""

    def __init__(
        self,
        pool: RuntimePool,
        chat_scope_id: str,
        registry: ChatRuntimePoolRegistry,
        config_fingerprint: str,
    ) -> None:
        self._pool = pool
        self._chat_scope_id = chat_scope_id
        self._registry = registry
        self._config_fingerprint = config_fingerprint

    @property
    def available_backends(self) -> list[str]:
        return self._pool.available_backends

    def get_config(self, name: str) -> RuntimeConfig | None:
        return self._pool.get_config(name)

    async def run_turn(
        self,
        name: str,
        prompt: str,
        session_id: str,
        *,
        mode: str = "persistent",
        mcp_servers: list[McpServerConfig] | None = None,
    ) -> AsyncIterator[RuntimeEvent]:
        async with self._registry.guard_turn(self._chat_scope_id):
            self._pool = await self._registry.ensure_tracked(self._chat_scope_id, self._config_fingerprint, self._pool)
            async for event in self._pool.run_turn(
                name,
                prompt,
                session_id,
                mode=mode,
                mcp_servers=mcp_servers,
            ):
                yield event

    async def cancel(self, name: str, session_id: str) -> None:
        # Lock-exempt: callers invoke cancel from inside an active run_turn loop.
        await self._pool.cancel(name, session_id)

    def __getattr__(self, name: str) -> object:
        return getattr(self._pool, name)


_registry: ChatRuntimePoolRegistry | None = None


def get_chat_runtime_pool_registry() -> ChatRuntimePoolRegistry:
    """Return the process-wide chat RuntimePool registry."""
    global _registry
    if _registry is None:
        _registry = ChatRuntimePoolRegistry()
    return _registry


async def close_external_agent_pool_for_chat(chat_scope_id: str | None) -> None:
    """Tear down pooled external CLI runtimes when a chat session ends."""
    if not chat_scope_id or not chat_scope_id.strip():
        return
    try:
        await get_chat_runtime_pool_registry().close_chat(chat_scope_id.strip())
    except Exception:
        logger.warning(
            "runtime_pool_close_chat_failed chat=%s",
            chat_scope_id,
            exc_info=True,
        )
