"""Chat-scoped RuntimePool registry for external CLI delegation.

[INPUT]
- myrm_agent_harness.toolkits.acp.runtime.pool::RuntimePool (POS: runtime pool management layer)

[OUTPUT]
- ChatRuntimePoolRegistry: reuse RuntimePool per conversation for CLI --resume across messages
- ChatScopedRuntimePoolFacade: per-chat single-flight guard around pool.run_turn (cancel lock-exempt)
- get_chat_runtime_pool_registry(): process-wide singleton accessor

[POS]
Server 业务层外部 Agent 运行时池生命周期。按 chat 复用 harness RuntimePool，
支持 per-chat turn lock 串行化 CLI run_turn；cancel 为 lock-exempt 中断语义。
消息结束后刷新 idle 计时；配置变更或 idle 超时再 close。
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

BuildPoolFn: TypeAlias = Callable[[], Awaitable["RuntimePool"]]


@dataclass
class _ChatPoolEntry:
    pool: RuntimePool
    config_fingerprint: str
    last_used: float


class ChatRuntimePoolRegistry:
    """Keeps one RuntimePool per chat while the conversation stays active."""

    def __init__(self, *, idle_seconds: float = _DEFAULT_IDLE_SECONDS) -> None:
        self._idle_seconds = idle_seconds
        self._entries: dict[str, _ChatPoolEntry] = {}
        self._turn_locks: dict[str, asyncio.Lock] = {}
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def guard_turn(self, chat_scope_id: str | None) -> AsyncGenerator[None, None]:
        """Serialize external CLI turns for one chat (one CliRuntime subprocess)."""
        if not chat_scope_id:
            yield
            return
        turn_lock = self._turn_locks.setdefault(chat_scope_id, asyncio.Lock())
        async with turn_lock:
            yield

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
                turn_lock = self._turn_locks.get(chat_scope_id)
                if (
                    entry.config_fingerprint != config_fingerprint
                    and turn_lock is not None
                    and turn_lock.locked()
                ):
                    logger.warning(
                        "runtime_pool_replace_deferred chat=%s reason=config_changed_active_turn",
                        chat_scope_id,
                    )
                    entry.last_used = time.monotonic()
                    return entry.pool

                logger.info(
                    "runtime_pool_replace chat=%s reason=%s",
                    chat_scope_id,
                    "config_changed" if entry.config_fingerprint != config_fingerprint else "missing",
                )
                await entry.pool.close_all()

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
            entry = self._entries.get(chat_scope_id)
            if entry is not None:
                entry.last_used = time.monotonic()

    async def close_chat(self, chat_scope_id: str) -> None:
        """Explicitly tear down a chat pool (e.g. conversation deleted)."""
        async with self._lock:
            entry = self._entries.pop(chat_scope_id, None)
            self._turn_locks.pop(chat_scope_id, None)
            if entry is not None:
                await entry.pool.close_all()
                logger.info("runtime_pool_closed chat=%s", chat_scope_id)

    async def close_all(self) -> None:
        """Shut down every pooled RuntimePool."""
        async with self._lock:
            for chat_scope_id, entry in list(self._entries.items()):
                try:
                    await entry.pool.close_all()
                except Exception:
                    logger.warning("runtime_pool_close_all_failed chat=%s", chat_scope_id, exc_info=True)
            self._entries.clear()
            self._turn_locks.clear()

    async def _evict_idle_unlocked(self) -> None:
        now = time.monotonic()
        stale = [
            chat_scope_id
            for chat_scope_id, entry in self._entries.items()
            if now - entry.last_used > self._idle_seconds
        ]
        for chat_scope_id in stale:
            entry = self._entries.pop(chat_scope_id)
            self._turn_locks.pop(chat_scope_id, None)
            await entry.pool.close_all()
            logger.info("runtime_pool_evicted_idle chat=%s idle_s=%.0f", chat_scope_id, self._idle_seconds)


class ChatScopedRuntimePoolFacade:
    """Wraps a RuntimePool with per-chat turn serialization for shared CliRuntime."""

    def __init__(
        self,
        pool: RuntimePool,
        chat_scope_id: str,
        registry: ChatRuntimePoolRegistry,
    ) -> None:
        self._pool = pool
        self._chat_scope_id = chat_scope_id
        self._registry = registry

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
