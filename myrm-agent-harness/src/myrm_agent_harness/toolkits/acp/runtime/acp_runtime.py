"""ACP protocol runtime backend.

Spawns an external ACP-compatible agent process (Claude Code, Codex CLI, etc.)
and communicates via the standard ACP JSON-RPC protocol over stdin/stdout.

[INPUT]
- toolkits.acp.types::AcpError, AcpErrorCode, BackendCapabilities, BackendStatus, McpServerConfig, images_not_sent_event (POS: ACP runtime type definitions layer. Provides all ACP-related core abstractions and data structures, serving as the foundation for the entire ACP module.)
- toolkits.acp.core.event_bus::EventBus (POS: ACP event bus layer. Provides decoupled event dispatch mechanism for the Runtime system with session isolation and type filtering.)
- toolkits.acp.runtime._base::KEEPALIVE_SECONDS, BaseRuntime, build_safe_env, working_status (POS: Base class for RuntimeBackend implementations.)
- toolkits.acp.runtime.acp_callback::AcpCallbackHandler (POS: ACP callback handler for the AcpRuntime backend.)
- toolkits.acp.runtime.image_blocks::ImageBlock, load_image_blocks (POS: Image input shared by CliRuntime and AcpRuntime)
- toolkits.acp.runtime.stalled_agent::cancel_session, leave_transport (POS: Bounded stop of an ACP agent that has stopped reading its stdin)
- toolkits.code_execution.utils.workspace_path::WorkspacePathResolver (POS: Workspace path resolver with intelligent auto-detection.)

[OUTPUT]
- AcpRuntime: RuntimeBackend implementation using the ACP protocol (std...

[POS]
ACP protocol runtime backend. Sends `session/close` only when the agent advertises it (ACP capability
negotiation) and bounds it, so a silent agent cannot skip the transport teardown that terminates its process.
A silent agent (one long tool call) is reported as still working at a fixed interval, as ``CliRuntime`` does, and a
missing ACP SDK (the optional ``acp`` extra) ends the turn with a ``BACKEND_NOT_FOUND`` error that says how to install it.

The images of a turn travel as image content blocks after the text, only to an agent that advertised
``promptCapabilities.image`` in ``initialize``; for any other agent the turn opens with an ``images_not_sent`` status
update and carries the text alone. Cancel and transport exit are bounded (``stalled_agent``), so an agent that has
stopped reading a prompt of several MiB cannot hold up a stop. A prompt failure surfaces as an error event only
once the events have been consumed to the end; when the consumer closed the turn first (the stop ended the agent) it
is logged at INFO, so closing is never replaced by that failure.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.acp.core.event_bus import EventBus
from myrm_agent_harness.toolkits.acp.runtime._base import (
    KEEPALIVE_SECONDS,
    BaseRuntime,
    build_safe_env,
    working_status,
)
from myrm_agent_harness.toolkits.acp.runtime.acp_callback import AcpCallbackHandler
from myrm_agent_harness.toolkits.acp.runtime.image_blocks import ImageBlock, load_image_blocks
from myrm_agent_harness.toolkits.acp.runtime.stalled_agent import cancel_session, leave_transport
from myrm_agent_harness.toolkits.acp.types import (
    AcpError,
    AcpErrorCode,
    BackendCapabilities,
    BackendStatus,
    McpServerConfig,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    create_event,
    images_not_sent_event,
)

if TYPE_CHECKING:
    from asyncio.subprocess import Process

    from acp import ClientSideConnection

logger = logging.getLogger(__name__)

# `session/close` is advisory. Bounded so an agent that advertises it but never answers still reaches the
# transport teardown (SDK-bounded terminate/kill) that actually stops the process.
_CLOSE_SESSION_TIMEOUT_SECONDS = 4.0


class _AcpSdkMissingError(Exception):
    """The ACP SDK (the optional ``acp`` extra of the harness) is not installed."""


def _require_acp_sdk() -> None:
    try:
        import acp  # noqa: F401
    except ModuleNotFoundError as exc:
        if exc.name != "acp":
            raise
        msg = "The ACP SDK is not installed; install it with: pip install 'myrm-agent-harness[acp]'"
        raise _AcpSdkMissingError(msg) from exc


class AcpRuntime(BaseRuntime):
    """RuntimeBackend implementation using the ACP protocol (stdin/stdout JSON-RPC).

    Spawns an external agent process and communicates via the official ACP SDK.
    Supports session reuse, cancel, and resume.
    """

    def __init__(
        self,
        runtime_name: str,
        config: RuntimeConfig,
        *,
        event_bus: EventBus | None = None,
    ) -> None:
        super().__init__(runtime_name, config, backend_type="acp")
        self._conn: ClientSideConnection | None = None
        self._process: Process | None = None
        self._session_id: str | None = None
        self._ctx_manager: AbstractAsyncContextManager[tuple[ClientSideConnection, Process]] | None = None
        self._handler: AcpCallbackHandler | None = None
        self._supports_session_close = False
        self._prompt_images = False
        self._event_bus = event_bus

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_resume=True,
            supports_mcp=True,
            supports_streaming=True,
            supports_tools=True,
            supports_images=True,
        )

    @property
    def is_alive(self) -> bool:
        if self._process is None:
            return False
        return self._process.returncode is None

    async def _do_run_turn(
        self,
        prompt: str,
        session_id: str,
        *,
        mcp_servers: list[McpServerConfig] | None = None,
        images: list[str] | None = None,
    ) -> AsyncGenerator[RuntimeEvent]:
        if not self.is_alive:
            yield create_event(
                RuntimeEventType.STATUS_UPDATE,
                session_id,
                status="starting",
                message="Spawning ACP agent process",
            )
            try:
                await self._ensure_connection()
            except _AcpSdkMissingError as exc:
                logger.warning("acp_sdk_missing name=%s", self._name)
                yield create_event(
                    RuntimeEventType.ERROR,
                    session_id,
                    error=AcpError(AcpErrorCode.BACKEND_NOT_FOUND, str(exc)),
                )
                return

        if self._session_id is None:
            await self._create_session(mcp_servers=mcp_servers)

        handler = self._handler
        if handler is None:
            msg = "Handler not initialized"
            raise RuntimeError(msg)
        handler.reset()

        blocks: list[ImageBlock] = []
        if images and self._prompt_images:
            blocks = await asyncio.to_thread(load_image_blocks, images)
        elif images:
            logger.info(
                "acp_runtime_images_skipped backend=%s images=%d reason=agent_without_image_prompt",
                self._name,
                len(images),
            )
            yield images_not_sent_event(session_id, len(images))
        prompt_task = asyncio.create_task(self._run_prompt(prompt, blocks, handler))

        drained = False
        try:
            async for event in self._consume_events(handler, session_id):
                yield event
            drained = True
        finally:
            if not prompt_task.done():
                prompt_task.cancel()
            try:
                await prompt_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                if not drained:
                    # The turn is closed or cancelled while events still flow (a stop that ended the agent): the
                    # caller is gone, and raising here would replace that close, so the base runtime would yield
                    # an error event from a generator that is being closed.
                    logger.info("acp_prompt_task_failed_after_close name=%s error=%s", self._name, exc)
                else:
                    logger.error("acp_prompt_task_failed name=%s", self._name, exc_info=True)
                    # Re-raise so the failure surfaces as an ERROR event and the
                    # BaseRuntime cleans up the process, matching CliRuntime
                    # behavior instead of degrading to a silent DONE.
                    raise

    async def _run_prompt(self, prompt: str, blocks: list[ImageBlock], handler: AcpCallbackHandler) -> None:
        """Run the ACP prompt (the text, then its images) and signal completion via the handler's queue."""
        from acp.schema import ImageContentBlock, TextContentBlock

        content: list[TextContentBlock | ImageContentBlock] = [TextContentBlock(type="text", text=prompt)]
        content.extend(ImageContentBlock(type="image", data=block.data, mime_type=block.media_type) for block in blocks)
        try:
            response = await self._conn.prompt(  # type: ignore[union-attr]
                prompt=content,
                session_id=self._session_id,
            )
            handler.mark_done(response.stop_reason)
        except Exception as exc:
            handler.mark_done(f"error:{type(exc).__name__}")
            raise

    @staticmethod
    async def _consume_events(
        handler: AcpCallbackHandler,
        session_id: str,
        *,
        silence_seconds: float = KEEPALIVE_SECONDS,
    ) -> AsyncGenerator[RuntimeEvent]:
        """Consume RuntimeEvents from the handler's queue in real-time.

        An agent that says nothing for ``silence_seconds`` (one long tool call) is reported as still working, so a
        host that watches for activity does not take the quiet for a hang.
        """
        started = time.monotonic()
        while True:
            try:
                event = await asyncio.wait_for(handler.event_queue.get(), timeout=silence_seconds)
            except TimeoutError:
                yield working_status(session_id, time.monotonic() - started)
                continue
            if event is None:
                break
            yield event

    async def _do_cancel(self, session_id: str) -> None:
        if self._conn is None or self._session_id is None:
            return
        await cancel_session(self._conn, self._session_id, self._process, self._name)

    async def _do_resume(self, session_id: str) -> bool:
        return self._session_id is not None and self.is_alive

    async def _do_close(self) -> None:
        # ACP: a client MUST NOT call `session/close` unless the agent advertised sessionCapabilities.close.
        if self._conn is not None and self._session_id is not None and self._supports_session_close:
            try:
                async with asyncio.timeout(_CLOSE_SESSION_TIMEOUT_SECONDS):
                    await self._conn.close_session(session_id=self._session_id)
            except TimeoutError:
                logger.warning(
                    "acp_close_session_timeout name=%s timeout_s=%.0f", self._name, _CLOSE_SESSION_TIMEOUT_SECONDS
                )
            except Exception:
                logger.debug("acp_close_session_failed name=%s", self._name, exc_info=True)

        if self._ctx_manager is not None:
            try:
                await leave_transport(self._ctx_manager, self._process, self._name)
            except Exception:
                logger.debug("acp_ctx_exit_failed name=%s", self._name, exc_info=True)

        self._conn = None
        self._process = None
        self._session_id = None
        self._ctx_manager = None
        self._handler = None
        self._supports_session_close = False
        self._prompt_images = False

    async def _do_get_status(self) -> BackendStatus:
        if self.is_alive:
            return "ready"
        if self._process is not None and self._process.returncode is not None:
            return "error"
        return "stopped"

    # -- Internal --

    async def _ensure_connection(self) -> None:
        """Spawn the external agent process and establish ACP connection."""
        _require_acp_sdk()
        await self._do_close()

        from acp import PROTOCOL_VERSION, spawn_agent_process
        from acp.schema import (
            ClientCapabilities,
            FileSystemCapabilities,
            Implementation,
        )

        self._handler = AcpCallbackHandler(
            self._config,
            session_id="",
            event_bus=self._event_bus,
        )
        safe_env = build_safe_env(self._config)
        from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import (
            WorkspacePathResolver,
        )

        cwd = self._config.cwd or str(WorkspacePathResolver.resolve_workspace_root())

        command = self._config.command
        if command is None:
            msg = "AcpRuntime requires 'command' in RuntimeConfig"
            raise ValueError(msg)

        # AcpCallbackHandler implements the acp.Client callbacks used here
        # (permission/session/file); terminal & elicitation callbacks are never
        # invoked because the connection declares terminal=False.
        ctx = spawn_agent_process(
            self._handler,  # type: ignore[arg-type]
            command,
            *self._config.args,
            env=safe_env,
            cwd=cwd,
        )
        self._ctx_manager = ctx
        conn, process = await ctx.__aenter__()
        self._conn = conn
        self._process = process
        self._alive = True

        init_response = await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(
                fs=FileSystemCapabilities(read_text_file=True, write_text_file=True),
                terminal=False,
            ),
            client_info=Implementation(name="myrm-acp-client", version="1.0.0"),
        )
        agent_caps = init_response.agent_capabilities
        session_caps = agent_caps.session_capabilities if agent_caps is not None else None
        self._supports_session_close = session_caps is not None and session_caps.close is not None
        prompt_caps = agent_caps.prompt_capabilities if agent_caps is not None else None
        self._prompt_images = prompt_caps is not None and bool(prompt_caps.image)
        logger.info("acp_runtime_connected name=%s pid=%s", self._name, process.pid)

    async def _create_session(self, *, mcp_servers: list[McpServerConfig] | None = None) -> None:
        """Create a new ACP session."""
        if self._conn is None:
            msg = "Cannot create session: connection not established"
            raise RuntimeError(msg)

        from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import (
            WorkspacePathResolver,
        )

        cwd = self._config.cwd or str(WorkspacePathResolver.resolve_workspace_root())
        acp_mcp = _mcp_configs_to_acp_stdio(mcp_servers)
        if acp_mcp:
            response = await self._conn.new_session(cwd=cwd, mcp_servers=acp_mcp)
        else:
            response = await self._conn.new_session(cwd=cwd)
        session_id = response.session_id
        self._session_id = session_id
        if self._handler is not None:
            self._handler.session_id = session_id
        logger.info("acp_runtime_session_created name=%s session_id=%s", self._name, session_id)


def _mcp_configs_to_acp_stdio(
    mcp_servers: list[McpServerConfig] | None,
) -> list[object] | None:
    if not mcp_servers:
        return None
    from acp.schema import EnvVariable, McpServerStdio

    return [
        McpServerStdio(
            name=server.name,
            command=server.command,
            args=list(server.args),
            env=[EnvVariable(name=key, value=value) for key, value in sorted((server.env or {}).items())],
        )
        for server in mcp_servers
    ]
