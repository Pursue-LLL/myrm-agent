"""RuntimePool — unified pool for managing arbitrary RuntimeBackend instances.

Supports ACP and CLI backends with config-driven registration and
concurrency control via a global asyncio.Semaphore plus per-backend
serialization locks. Backends are created lazily on first use, and a resident
ACP process that has exited is reconnected by its next ``run_turn``. A ``oneshot``
turn runs on a private backend (fresh session, closed afterwards) so it never
disturbs the shared backend's persistent session. ``release_resident`` frees the
resident ACP processes of an idle pool while CLI backends keep their resume state. An optional
``CliSessionStore`` lets the persistent CLI backends resume their sessions after the host restarts.


[INPUT]
- myrm_agent_harness.toolkits.acp.core.event_bus::EventBus (POS: ACP event bus layer)
- myrm_agent_harness.toolkits.acp.types::RuntimeBackend, RuntimeConfig, RuntimeEvent, CliSessionStore (POS: ACP runtime type definitions)
- myrm_agent_harness.toolkits.acp.runtime.*::AcpRuntime, CliRuntime (POS: runtime backend implementations)

[OUTPUT]
- RuntimePool: unified runtime instance pool managing multiple backend types

[POS]
Runtime pool management layer. Provides multi-backend unified management, concurrency control,
and config-driven registration — the central dispatcher of the runtime system.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import aclosing
from uuid import uuid4

from myrm_agent_harness.toolkits.acp.core.event_bus import EventBus
from myrm_agent_harness.toolkits.acp.types import (
    CliSessionStore,
    McpServerConfig,
    RuntimeBackend,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
)

logger = logging.getLogger(__name__)


def _create_runtime(
    name: str,
    config: RuntimeConfig,
    *,
    event_bus: EventBus | None = None,
    cli_session_store: CliSessionStore | None = None,
) -> RuntimeBackend:
    """Factory: create the appropriate RuntimeBackend based on config.backend_type."""
    if config.backend_type == "acp":
        from myrm_agent_harness.toolkits.acp.runtime.acp_runtime import AcpRuntime

        return AcpRuntime(name, config, event_bus=event_bus)

    if config.backend_type == "cli":
        from myrm_agent_harness.toolkits.acp.runtime.cli.runtime import CliRuntime

        return CliRuntime(name, config, session_store=cli_session_store)

    msg = f"Unknown backend_type: {config.backend_type!r}"
    raise ValueError(msg)


async def _safe_close(name: str, backend: RuntimeBackend) -> None:
    """Close a backend, logging instead of raising so one failure cannot strand the others."""
    try:
        await backend.close()
    except Exception:
        logger.warning("pool_close_failed backend=%s", name, exc_info=True)


class RuntimePool:
    """Manages multiple RuntimeBackend instances with concurrency control.

    Usage::

        pool = RuntimePool(max_concurrent=4)
        pool.register("claude", RuntimeConfig(backend_type="acp", command="claude"))
        response = await pool.prompt("claude", "Fix the bug in main.py")
    """

    def __init__(
        self,
        *,
        max_concurrent: int = 4,
        event_bus: EventBus | None = None,
        cli_session_store: CliSessionStore | None = None,
    ) -> None:
        self._configs: dict[str, RuntimeConfig] = {}
        self._backends: dict[str, RuntimeBackend] = {}
        # Private backends of in-flight oneshot turns, keyed by (backend name, session id).
        self._oneshot_backends: dict[tuple[str, str], RuntimeBackend] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._backend_locks: dict[str, asyncio.Lock] = {}
        self._event_bus = event_bus
        self._cli_session_store = cli_session_store

    @property
    def available_backends(self) -> list[str]:
        """List all registered backend names."""
        return list(self._configs)

    def register(self, name: str, config: RuntimeConfig) -> None:
        """Register a backend configuration. Creates the backend lazily on first use."""
        self._configs[name] = config

    def get_config(self, name: str) -> RuntimeConfig | None:
        """Return the RuntimeConfig for a registered backend, or None if not found."""
        return self._configs.get(name)

    def _new_backend(self, name: str, *, cli_session_store: CliSessionStore | None = None) -> RuntimeBackend:
        """Create a backend for ``name`` that the pool does not keep.

        Only the shared persistent backend is given the session store: a private oneshot backend
        is a fresh session that ends with its turn, so it has nothing to resume or to persist.

        Raises:
            KeyError: If the name is not registered.
        """
        config = self._configs.get(name)
        if config is None:
            available = ", ".join(self._configs) or "(none)"
            msg = f"Unknown backend '{name}'. Available: {available}"
            raise KeyError(msg)
        return _create_runtime(name, config, event_bus=self._event_bus, cli_session_store=cli_session_store)

    def get(self, name: str) -> RuntimeBackend:
        """Get or lazily create the shared (persistent) RuntimeBackend by name.

        Raises:
            KeyError: If the name is not registered.
        """
        backend = self._backends.get(name)
        if backend is None:
            backend = self._backends[name] = self._new_backend(name, cli_session_store=self._cli_session_store)
        return backend

    async def prompt(self, name: str, task: str, *, mode: str = "persistent") -> str:
        """Send a task to the named backend with concurrency control.

        Collects all text_delta events and returns the concatenated response.
        """
        if mode == "oneshot":
            session_id = f"{name}-oneshot-{uuid4().hex}"
        elif mode == "persistent":
            session_id = f"{name}-default"
        else:
            msg = f"Invalid mode: {mode}"
            raise ValueError(msg)

        text_parts: list[str] = []
        async for event in self.run_turn(name, task, session_id=session_id, mode=mode):
            if event.type == RuntimeEventType.TEXT_DELTA:
                content = event.data.get("content")
                if isinstance(content, str):
                    text_parts.append(content)

        return "".join(text_parts)

    async def run_turn(
        self,
        name: str,
        prompt: str,
        session_id: str,
        *,
        mode: str = "persistent",
        mcp_servers: list[McpServerConfig] | None = None,
    ) -> AsyncGenerator[RuntimeEvent]:
        """Stream events from a backend turn with concurrency control.

        Use this instead of ``prompt()`` when you need the full event stream.

        ``persistent`` turns share one backend per name, so the session carries over between turns.
        A ``oneshot`` turn runs on a private backend that is closed when the turn ends: it always
        starts a fresh session and never touches the persistent backend's session or process.
        """
        if mode not in {"persistent", "oneshot"}:
            msg = f"Invalid mode: {mode}"
            raise ValueError(msg)

        config = self._configs.get(name)
        effective_mcp: list[McpServerConfig] | None = (
            mcp_servers if mcp_servers is not None else (list(config.mcp_servers) if config is not None else [])
        )

        oneshot = mode == "oneshot"
        async with self._semaphore:
            backend = self._new_backend(name) if oneshot else self.get(name)
            # MCP 注入前能力断言：仅向声明支持的后端注入。静默忽略会让调用方
            # 误以为 MCP 已生效，必须显式告警。
            if effective_mcp and not backend.capabilities.supports_mcp:
                logger.warning(
                    "pool_mcp_skipped backend=%s type=%s mcp_servers=%d reason=unsupported",
                    name,
                    type(backend).__name__,
                    len(effective_mcp),
                )
                effective_mcp = None
            # Serialize turns per backend: a backend instance (e.g. CliRuntime)
            # holds mutable per-turn state (active process handle) that cannot
            # be safely shared across concurrent turns.
            backend_lock = self._backend_locks.setdefault(name, asyncio.Lock())
            async with backend_lock:
                if oneshot:
                    self._oneshot_backends[(name, session_id)] = backend
                try:
                    async with aclosing(
                        backend.run_turn(prompt, session_id, mcp_servers=effective_mcp or None)
                    ) as events:
                        async for event in events:
                            if self._event_bus is not None:
                                await self._event_bus.emit(event)
                            yield event
                finally:
                    if oneshot:
                        self._oneshot_backends.pop((name, session_id), None)
                        await _safe_close(name, backend)

    async def cancel(self, name: str, session_id: str) -> None:
        """Cancel a running turn for the named backend.

        Delegates to ``backend.cancel(session_id)`` which terminates the
        external process (e.g., SIGTERM → SIGKILL for CliRuntime). A running
        oneshot turn is cancelled on its own private backend.
        No-op if no backend for ``name`` has been instantiated yet.
        """
        backend = self._oneshot_backends.get((name, session_id))
        if backend is None:
            backend = self._backends.get(name)
        if backend is not None:
            await backend.cancel(session_id)
            logger.info("pool_cancel backend=%s session=%s", name, session_id)

    async def release_resident(self) -> None:
        """Stop the backends that keep an OS process between turns (ACP) and keep the rest.

        A CLI backend runs one process per turn, so between turns it holds nothing but the session id
        behind ``--resume``; that stays. A released ACP backend is recreated by its next turn.
        Call it only while no turn is running on this pool.
        """
        resident = {
            name: backend
            for name, backend in self._backends.items()
            if (config := self._configs.get(name)) is not None and config.backend_type == "acp"
        }
        if not resident:
            return
        for name in resident:
            del self._backends[name]
        await asyncio.gather(*[_safe_close(name, backend) for name, backend in resident.items()])
        logger.info("runtime_pool_released_resident backends=%s", ",".join(resident))

    async def close_all(self) -> None:
        """Close all active backend connections, including in-flight oneshot turns."""
        backends = [*self._backends.items(), *((n, b) for (n, _), b in self._oneshot_backends.items())]
        if backends:
            await asyncio.gather(*[_safe_close(n, b) for n, b in backends])
        self._backends.clear()
        logger.info("runtime_pool_closed")
