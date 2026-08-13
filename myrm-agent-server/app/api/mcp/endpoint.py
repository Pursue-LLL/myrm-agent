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
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

if TYPE_CHECKING:
    from fastapi import FastAPI
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

logger = logging.getLogger(__name__)

_session_manager_task: asyncio.Task[None] | None = None
_session_manager_ready = asyncio.Event()
_embedding_cfg: EmbeddingConfig | None = None


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


async def _memory_manager_for_agent(agent_id: str) -> MemoryManager:
    from app.core.memory.adapters.setup import (
        create_memory_manager,
        resolve_context_binding,
    )
    from app.services.memory.shared_context import resolve_shared_context_ids

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
        try:
            manager = await _memory_manager_for_agent(resolved.agent_id)
            ctx_token = set_request_memory_manager(manager)
            wiki_token = set_request_wiki_boundary_enabled(
                await _wiki_boundary_enabled_for_agent(resolved.agent_id)
            )
            service.mark_ready(resolved.profile_id)
            await self.app(scope, receive, send)
        except Exception:
            logger.exception(
                "MCP memory scope resolution failed for profile=%s agent=%s",
                resolved.profile_id,
                resolved.agent_id,
            )
            response = JSONResponse(
                {"error": "Memory scope unavailable"},
                status_code=503,
            )
            await response(scope, receive, send)
        finally:
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

        mcp_server = MemoryMCPServer(memory_manager)
        mcp_asgi_app = mcp_server.get_streamable_http_app(stateless=True)

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
    if _session_manager_task is not None:
        _session_manager_task.cancel()
        try:
            await _session_manager_task
        except asyncio.CancelledError:
            pass
        _session_manager_task = None
        logger.info("MCP session manager stopped")
