"""MCP server endpoint for external agent memory access.

[INPUT]
- myrm_agent_harness.toolkits.memory.mcp_server::MemoryMCPServer (POS: MCP server adapter that lets external AI agents access the memory system via standard MCP protocol)
- app.services.connect::get_connect_service (POS: Token verification)
- app.core.memory.adapters.setup::create_memory_manager, resolve_context_binding (POS: MemoryManager factory)

[OUTPUT]
- setup_mcp_endpoint: async init + mount on FastAPI app
- shutdown_mcp_endpoint: cancel session manager task group

[POS]
Exposes the memory system as a stateless Streamable HTTP MCP endpoint that
external agents (Claude Code, Cursor, etc.) can connect to. Each Bearer
token carries an agent_id; middleware dynamically binds the MemoryManager to
the target Agent Profile + SharedContext via ContextVar, and sets wiki boundary
rejection for memory_store when the agent profile enables wiki. Mounted at /mcp on the FastAPI application during startup.

Stateless mode (no Mcp-Session-Id tracking) is used because all four memory
tools are inherently per-request — auth and agent scoping are handled
entirely by the Bearer token middleware, not by MCP session state.

FastAPI's mount() does not propagate lifespan events to sub-apps, so we
manually start the MCP session manager's task group via a background task
and cancel it on shutdown (the SDK requires the task group even in stateless
mode for per-request transport lifecycle).
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

if TYPE_CHECKING:
    from fastapi import FastAPI
    from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

logger = logging.getLogger(__name__)

_session_manager_task: asyncio.Task[None] | None = None
_session_manager_ready = asyncio.Event()
_embedding_cfg: EmbeddingConfig | None = None
_mcp_desktop_sessions: dict[str, DesktopSession] = {}

_request_desktop_enabled: ContextVar[bool] = ContextVar(
    "myrm_mcp_request_desktop_enabled",
    default=False,
)


def set_request_desktop_enabled(enabled: bool) -> Token[bool]:
    """Bind whether desktop tools are exposed for the current MCP request."""
    return _request_desktop_enabled.set(enabled)


def reset_request_desktop_enabled(token: Token[bool]) -> None:
    """Restore previous desktop tools exposed flag."""
    _request_desktop_enabled.reset(token)


def get_request_desktop_enabled() -> bool:
    """Return whether desktop tools are exposed for the current MCP request."""
    return _request_desktop_enabled.get()


def clear_mcp_desktop_sessions() -> None:
    """Clear cached external MCP desktop sessions (used in testing and shutdown)."""
    global _mcp_desktop_sessions
    _mcp_desktop_sessions.clear()


async def _require_embedding_config() -> EmbeddingConfig:
    global _embedding_cfg
    if _embedding_cfg is None:
        from app.services.agent.platform_config import require_platform_embedding_config

        _embedding_cfg = await require_platform_embedding_config()
    return _embedding_cfg


async def _wiki_boundary_enabled_for_agent(agent_id: str) -> bool:
    from app.services.agent.profile.profile_resolver import (
        get_agent_profile_resolver,
        resolve_builtin_tool_flags,
    )

    resolved = await get_agent_profile_resolver().resolve(agent_id)
    if resolved is None:
        return False
    flags = resolve_builtin_tool_flags(resolved.enabled_builtin_tools)
    return bool(flags["enable_wiki"])


async def _is_desktop_control_enabled_for_agent(agent_id: str) -> bool:
    try:
        from app.config.computer_use_deploy import is_computer_use_deploy_supported

        if not is_computer_use_deploy_supported():
            return False
        from app.services.agent.profile.profile_resolver import (
            get_agent_profile_resolver,
            resolve_builtin_tool_flags,
        )

        resolved = await get_agent_profile_resolver().resolve(agent_id)
        if resolved is None:
            return False
        flags = resolve_builtin_tool_flags(resolved.enabled_builtin_tools)
        return bool(flags.get("enable_computer_use"))
    except Exception as exc:
        logger.debug("Desktop control check failed for agent=%s: %s", agent_id, exc)
        return False


def _desktop_session_for_agent(agent_id: str) -> DesktopSession | None:
    try:
        from app.services.agent.gateway import get_agent_gateway

        gateway = get_agent_gateway()
        active_session = gateway.get_active_desktop_session()
        if active_session is not None and hasattr(active_session, "desktop_snapshot"):
            return active_session  # type: ignore[return-value]
    except Exception:
        pass

    global _mcp_desktop_sessions
    if agent_id not in _mcp_desktop_sessions:
        try:
            from myrm_agent_harness.toolkits.computer_use import create_desktop_session
            from myrm_agent_harness.toolkits.computer_use.types import (
                ComputerUseConfig,
                ExecutionMode,
            )

            from app.ai_agents.desktop_control.gate import DesktopControlGate
            from app.config.computer_use_deploy import is_computer_use_deploy_supported
            from app.config.deploy_mode import is_local_mode, is_sandbox

            auto_grant = (
                is_sandbox()
                and is_computer_use_deploy_supported()
                and not is_local_mode()
            )
            execution_mode = (
                ExecutionMode.background_strict
                if is_local_mode()
                else ExecutionMode.background_best_effort
            )
            gate = DesktopControlGate(workspace_root=None, auto_grant=auto_grant)
            config = ComputerUseConfig(execution_mode=execution_mode)
            _mcp_desktop_sessions[agent_id] = create_desktop_session(
                config=config, permission_callback=gate
            )
        except Exception as exc:
            logger.warning(
                "Failed to create MCP desktop session for agent=%s: %s", agent_id, exc
            )
            return None
    return _mcp_desktop_sessions.get(agent_id)


async def _memory_manager_for_agent(agent_id: str) -> MemoryManager:
    from app.core.memory.adapters.setup import (
        create_memory_manager,
        resolve_context_binding,
    )
    from app.services.memory.shared_context.shared_context import (
        resolve_shared_context_ids,
    )

    shared_context_ids = await resolve_shared_context_ids(agent_id=agent_id)
    binding = resolve_context_binding(
        namespaces=None,
        agent_id=agent_id,
        channel_id=None,
        conversation_id=None,
        task_id=None,
        shared_context_ids=shared_context_ids,
    )
    embedding_cfg = await _require_embedding_config()
    return await create_memory_manager(
        binding,
        embedding_cfg,
        approval_required=False,
    )


class _MCPTokenAuthMiddleware:
    """ASGI middleware validating Bearer tokens for MCP requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        auth_header = request.headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            response = JSONResponse(
                {"error": "Missing or invalid Authorization header"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        token = auth_header[7:]
        from app.services.connect import get_connect_service

        service = get_connect_service()
        resolved = service.resolve_token(token)
        if resolved is None:
            response = JSONResponse(
                {"error": "Invalid or revoked token"},
                status_code=403,
            )
            await response(scope, receive, send)
            return

        from myrm_agent_harness.toolkits.memory.mcp_server import (
            reset_request_memory_manager,
            reset_request_wiki_boundary_enabled,
            set_request_memory_manager,
            set_request_wiki_boundary_enabled,
        )

        scope["state"] = scope.get("state", {})
        scope["state"]["mcp_profile_id"] = resolved.profile_id
        scope["state"]["mcp_agent_id"] = resolved.agent_id

        ctx_token = None
        wiki_token = None
        desktop_token = None
        desktop_enabled_token = None
        try:
            manager = await _memory_manager_for_agent(resolved.agent_id)
            ctx_token = set_request_memory_manager(manager)
            wiki_token = set_request_wiki_boundary_enabled(
                await _wiki_boundary_enabled_for_agent(resolved.agent_id)
            )

            from myrm_agent_harness.toolkits.computer_use.mcp_server import (
                reset_request_desktop_session,
                set_request_desktop_session,
            )

            desktop_eligible = await _is_desktop_control_enabled_for_agent(
                resolved.agent_id
            )
            allow_desktop = desktop_eligible and getattr(
                resolved, "expose_desktop", False
            )
            desktop_enabled_token = set_request_desktop_enabled(allow_desktop)
            if allow_desktop:
                desktop_session = _desktop_session_for_agent(resolved.agent_id)
                desktop_token = set_request_desktop_session(desktop_session)

            service.mark_ready(resolved.profile_id)
            await self.app(scope, receive, send)
        except Exception:
            logger.exception(
                "MCP scope resolution failed for profile=%s agent=%s",
                resolved.profile_id,
                resolved.agent_id,
            )
            response = JSONResponse(
                {"error": "Memory scope unavailable"},
                status_code=503,
            )
            await response(scope, receive, send)
        finally:
            if desktop_token is not None:
                reset_request_desktop_session(desktop_token)
            if desktop_enabled_token is not None:
                reset_request_desktop_enabled(desktop_enabled_token)
            if wiki_token is not None:
                reset_request_wiki_boundary_enabled(wiki_token)
            if ctx_token is not None:
                reset_request_memory_manager(ctx_token)


async def setup_mcp_endpoint(app: FastAPI) -> None:
    """Create and mount the MCP memory endpoint at /mcp.

    Should be called during application startup (Phase 2 or later).
    Gracefully skips if memory system is not available.
    """
    global _session_manager_task

    try:
        from myrm_agent_harness.toolkits.memory.mcp_server import MemoryMCPServer

        from app.core.memory.adapters.setup import (
            create_memory_manager,
            resolve_context_binding,
        )

        embedding_cfg = await _require_embedding_config()

        binding = resolve_context_binding(
            namespaces=None,
            agent_id="default",
            channel_id=None,
            conversation_id=None,
            task_id=None,
        )
        memory_manager = await create_memory_manager(
            binding,
            embedding_cfg,
            approval_required=False,
        )

        mcp_server = MemoryMCPServer(memory_manager, stateless_http=True)

        from myrm_agent_harness.toolkits.computer_use.mcp_server import (
            get_request_desktop_session,
            register_desktop_mcp_tools,
        )

        register_desktop_mcp_tools(mcp_server.mcp, get_request_desktop_session)

        orig_list_tools = mcp_server.mcp.list_tools

        async def _filtered_list_tools() -> list[object]:
            tools = await orig_list_tools()
            if not get_request_desktop_enabled():
                return [
                    t
                    for t in tools
                    if not getattr(t, "name", "").startswith("desktop_")
                ]
            return tools

        from mcp.server.transport_security import TransportSecuritySettings

        mcp_server.mcp.list_tools = _filtered_list_tools  # type: ignore[method-assign]
        mcp_asgi_app = mcp_server.get_streamable_http_app(
            streamable_http_path="/",
            transport_security=TransportSecuritySettings(
                allowed_hosts=[
                    "localhost:*",
                    "127.0.0.1:*",
                    "testserver",
                    "testserver:*",
                ]
            ),
        )

        # FastAPI mount() does not propagate lifespan to sub-apps, so the
        # Starlette sub-app's lifespan (which calls session_manager.run())
        # never fires. We start the session manager manually via a background
        # task that keeps the anyio TaskGroup alive for the server lifetime.
        sm = mcp_server.mcp.session_manager
        if sm is not None:

            async def _run_session_manager() -> None:
                async with sm.run():
                    _session_manager_ready.set()
                    # Block until cancelled on shutdown
                    await asyncio.Event().wait()

            _session_manager_task = asyncio.create_task(_run_session_manager())
            await asyncio.wait_for(_session_manager_ready.wait(), timeout=5.0)

        authed_app = _MCPTokenAuthMiddleware(mcp_asgi_app)
        app.mount("/mcp", authed_app)
        logger.info("MCP memory endpoint mounted at /mcp")

    except Exception as e:
        logger.warning("MCP endpoint not mounted (memory system unavailable): %s", e)


async def shutdown_mcp_endpoint() -> None:
    """Cancel the MCP session manager background task on shutdown."""
    global _session_manager_task
    clear_mcp_desktop_sessions()
    if _session_manager_task is not None:
        _session_manager_task.cancel()
        try:
            await _session_manager_task
        except asyncio.CancelledError:
            pass
        _session_manager_task = None
        logger.info("MCP session manager stopped")
