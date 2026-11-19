"""Serves MCP tool tables from the local cache while the servers' sessions start in the background.

[INPUT]
- toolkits.mcp.client::MCPServerConfigProtocol (POS: MCP client management layer)
- toolkits.mcp.tool_table::ServerSurface, ToolTable, capture_table, encode_table, restore_surface, tools_of_server (POS: Serializable snapshot of the tools one MCP server exposes)
- toolkits.mcp.tool_table_store::ToolTableStore (POS: Local file store of MCP tool tables)
- utils.token_estimation::estimate_tools_schema_tokens (POS: Token estimation infrastructure)

[OUTPUT]
- McpWarmup: Serves cached tool tables of cold servers, starts their sessions on demand, remembers live tool tables
- ConnectionPool: the part of the MCP connection pool the warm-up asks for

[POS]
Lets the first model request leave without waiting for MCP discovery. Routing builds the Skill surface of a server it
has a cached table for from that table; the session then starts in the background and, once up, is compared with the
table: a changed surface replaces the cached one (the current run keeps what its prompt already showed, so a prompt
never changes mid-run), and a server that cannot be reached loses its entry. Nothing may run a served server's tools
before its live session has registered the tool safety metadata that approval and the IPC policy gates read: ``settle``
is the barrier for that.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Coroutine, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from myrm_agent_harness.toolkits.mcp.tool_table import (
    ServerSurface,
    ToolTable,
    capture_table,
    encode_table,
    restore_surface,
    tools_of_server,
)
from myrm_agent_harness.utils.token_estimation import estimate_tools_schema_tokens

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from myrm_agent_harness.toolkits.mcp.client import MCPServerConfigProtocol
    from myrm_agent_harness.toolkits.mcp.config import MCPConfig
    from myrm_agent_harness.toolkits.mcp.tool_table_store import ToolTableStore

logger = logging.getLogger(__name__)


class _LiveSurfaces(Protocol):
    """What a live connection exposes of the servers behind it."""

    @property
    def tools_by_server(self) -> Mapping[str, Sequence[BaseTool]]: ...

    @property
    def instructions_by_server(self) -> Mapping[str, str | None]: ...


class ConnectionPool(Protocol):
    """The part of the MCP connection pool the warm-up asks for."""

    def config_hash(self, config: Sequence[MCPServerConfigProtocol]) -> str: ...

    def is_pooled(self, config: Sequence[MCPServerConfigProtocol]) -> bool: ...

    async def get_connection(self, config: Sequence[MCPServerConfigProtocol]) -> _LiveSurfaces: ...


@dataclass(frozen=True, slots=True)
class _Job:
    """A server whose surface was served from its cached table and whose session still has to start."""

    manager: ConnectionPool
    config: MCPConfig
    key: str
    served: ToolTable


class McpWarmup:
    """The cached tool tables served to one agent assembly, the sessions that verify them and the writes in flight."""

    def __init__(self, store: ToolTableStore) -> None:
        self._store = store
        self._jobs: list[_Job] = []
        self._started = False
        self._inflight: set[asyncio.Task[None]] = set()

    @property
    def has_jobs(self) -> bool:
        """Whether any server was served from its cache, so a session is still to be started and awaited."""
        return bool(self._jobs)

    async def serve(
        self,
        manager: ConnectionPool,
        configs: Sequence[MCPConfig],
        *,
        threshold: int,
    ) -> dict[str, ServerSurface]:
        """Surfaces, by server name, of the servers whose session is not up yet and whose cached table is usable.

        Only a server routed to the Skill path (schema tokens above ``threshold``) is served: one the model gets as
        direct tools needs its live tool objects. A server the pool already holds is not served either: asking the pool
        is as fast as reading the cache and returns the authoritative surface.
        """
        cold = [cfg for cfg in configs if not manager.is_pooled([cfg])]
        keys = [manager.config_hash([cfg]) for cfg in cold]
        tables = await asyncio.to_thread(self._load_all, keys)
        served: dict[str, ServerSurface] = {}
        for cfg, key, table in zip(cold, keys, tables, strict=True):
            if table is None:
                continue
            surface = restore_surface(table)
            if estimate_tools_schema_tokens(surface.tools) <= threshold:
                continue
            served[cfg.name] = surface
            self._jobs.append(_Job(manager=manager, config=cfg, key=key, served=table))
            logger.info(
                "MCP server '%s': surface served from the cached tool table (%d tools)", cfg.name, len(table.tools)
            )
        return served

    def remember(self, manager: ConnectionPool, config: MCPConfig, surface: ServerSurface) -> None:
        """Keep the live *surface* of ``config`` for the next cold start, without making the caller wait for the disk."""
        self._spawn(self._remember(manager.config_hash([config]), surface, config.name), f"mcp-cache-{config.name}")

    def start(self) -> None:
        """Start the served servers' sessions in the background; a second call does nothing."""
        if self._started:
            return
        self._started = True
        for job in self._jobs:
            self._spawn(self._verify(job), f"mcp-warm-up-{job.config.name}")

    async def settle(self) -> None:
        """Wait until every started session is up or has failed, and every cache write has landed.

        Cancelling the caller does not cancel them. Work bound to another event loop is not waited for.
        """
        loop = asyncio.get_running_loop()
        waiting = {task for task in self._inflight if task.get_loop() is loop}
        if waiting:
            await asyncio.wait(waiting)

    def _spawn(self, work: Coroutine[object, object, None], name: str) -> None:
        task = asyncio.create_task(work, name=name)
        self._inflight.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task[None]) -> None:
        """Forget a finished task; whatever it failed with is cache upkeep, so it is logged and goes no further."""
        self._inflight.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.warning("MCP warm-up task '%s' failed: %s", task.get_name(), error)

    def _load_all(self, keys: list[str]) -> list[ToolTable | None]:
        return [self._store.load(key) for key in keys]

    async def _remember(self, key: str, surface: ServerSurface, server: str) -> None:
        table = await asyncio.to_thread(capture_table, surface)
        if table is None:
            logger.info("MCP server '%s': tool surface cannot be cached", server)
            return
        await self._save(key, table, server)

    async def _verify(self, job: _Job) -> None:
        """Start the session of a served server and bring the cache in line with what it exposes."""
        name = job.config.name
        try:
            # The SDK import is hundreds of milliseconds of CPU: on the event loop it would hold up the model request
            # that is being sent while this session starts.
            await asyncio.to_thread(importlib.import_module, "mcp")
            conn = await job.manager.get_connection([job.config])
        except Exception as exc:
            logger.warning("MCP server '%s' failed to start after its cached tool table was served: %s", name, exc)
            await self._discard(job.key, name)
            return
        surface = ServerSurface(
            tools=tuple(tools_of_server(conn.tools_by_server, name)),
            instructions=conn.instructions_by_server.get(name),
        )
        live = await asyncio.to_thread(capture_table, surface)
        if live is None:
            await self._discard(job.key, name)
        elif encode_table(live) != encode_table(job.served):
            logger.warning(
                "MCP server '%s': its tools changed since they were cached; this run keeps the cached surface", name
            )
            await self._save(job.key, live, name)

    async def _save(self, key: str, table: ToolTable, server: str) -> None:
        try:
            await asyncio.to_thread(self._store.save, key, table)
        except OSError as exc:
            logger.warning("MCP server '%s': tool table could not be cached: %s", server, exc)

    async def _discard(self, key: str, server: str) -> None:
        try:
            await asyncio.to_thread(self._store.discard, key)
        except OSError as exc:
            logger.warning("MCP server '%s': cached tool table could not be dropped: %s", server, exc)


__all__ = ["ConnectionPool", "McpWarmup"]
