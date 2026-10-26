"""External agent delegation setup and direct-delegate streaming.

[INPUT]
- myrm_agent_harness.toolkits.acp (POS: 外部 Agent 委托协议框架)
- app.config.deploy_mode (POS: 部署模式检测)
- .external_agents_runtime_config (POS: 外部 Agent 配置归一化层)
- app.services.external_agents.cli_session_store::ChatCliSessionStore (POS: chat 行持久化的外部 CLI 会话 id，服务重启后续接同一外部对话) [lazy]
- app.services.external_agents.direct_delegate_stream::stream_direct_delegate (POS: 外部 Agent 回合 → 前端 SSE 事件流) [lazy]

[OUTPUT]
- ExternalAgentsMixin: 外部 Agent 初始化与直接委托流式执行的 Mixin
- should_mount_invoke_acp_agent_tool(): direct-only 路径是否跳过 invoke_acp_agent_tool 挂载
- needs_runtime_pool(): factory 是否 eager 初始化 RuntimePool（与 stream lazy path 对齐）
- BUILTIN_CLI_VISUAL_AGENT_ID: CLI Visual 内置 Agent 标识
- chat scope 路径：ChatRuntimePoolRegistry + ChatScopedRuntimePoolFacade 接线；池带 ChatCliSessionStore，CLI 会话 id 随 chat 落库

[POS]
外部 Agent 委托层。负责 RuntimePool 初始化、CLI/ACP 后端注册、
本地模式自动检测（请求热路径使用 path-only 探测，版本探测留给设置态），
以及绕过 LangChain 直接向前端流式转发外部 Agent 事件。
Settings auth/status 仅报告安装/登录态。
有 chat scope 时经 ChatRuntimePoolRegistry 跨消息复用 pool（CLI --resume，会话 id 落在 chat 行，服务重启后仍续接），
ChatScopedRuntimePoolFacade 对 run_turn 做 per-chat single-flight 串行化。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import external_agents_runtime_config as _runtime_cfg_helpers

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
    from myrm_agent_harness.toolkits.acp.types import DelegationPool
    from myrm_agent_harness.utils import CancellationToken

logger = logging.getLogger(__name__)

BUILTIN_CLI_VISUAL_AGENT_ID = "builtin-cli_visual"

_auth_mode = _runtime_cfg_helpers._auth_mode
_cfg_int = _runtime_cfg_helpers._cfg_int
_config_fingerprint = _runtime_cfg_helpers._config_fingerprint
_resolve_external_agent_cfgs = _runtime_cfg_helpers._resolve_external_agent_cfgs
_register_backends_on_pool = _runtime_cfg_helpers._register_backends_on_pool


def should_mount_invoke_acp_agent_tool(*, agent_id: str | None, force_external_agent: str | None) -> bool:
    """Return False when direct-delegate routing makes the LLM tool redundant."""
    if force_external_agent:
        return False
    if agent_id == BUILTIN_CLI_VISUAL_AGENT_ID:
        return False
    return True


def needs_runtime_pool(
    *,
    enable_external_cli: bool,
    agent_id: str | None,
    force_external_agent: str | None,
) -> bool:
    """Return True when factory should eagerly init RuntimePool (not lazy stream path)."""
    if force_external_agent:
        return True
    if agent_id == BUILTIN_CLI_VISUAL_AGENT_ID:
        return True
    return enable_external_cli


def _runtime_pool_scope_id(agent: object) -> str | None:
    scope = getattr(agent, "_runtime_pool_scope_id", None)
    if isinstance(scope, str) and scope.strip():
        return scope.strip()
    chat_id = getattr(agent, "chat_id", None)
    if isinstance(chat_id, str) and chat_id.strip():
        return chat_id.strip()
    return None


async def resolve_external_agent_backends(
    external_agents_config: list[dict[str, object]] | None,
) -> list[dict[str, object]] | None:
    """Return resolved external agent configs (explicit Settings or local auto-detect)."""
    return await _resolve_external_agent_cfgs(external_agents_config)


class ExternalAgentsMixin:
    """Mixin providing external agent delegation and direct-delegate streaming."""

    if TYPE_CHECKING:
        external_agents_config: list[dict[str, object]] | None
        _runtime_pool: DelegationPool | None
        _runtime_pool_scope_id: str | None
        _runtime_pool_from_registry: bool
        _owned_runtime_pool: RuntimePool | None
        chat_id: str | None
        agent_id: str | None
        force_external_agent: str | None
        locale: str | None

    async def _setup_external_agents(
        self,
        tools: list[object],
        *,
        mount_invoke_acp_agent_tool: bool | None = None,
        external_agent_workdir: str | None = None,
    ) -> None:
        """Set up external agent delegation via RuntimePool.

        Parses external_agents_config (from UserConfig 'externalAgents'),
        registers each enabled agent as a RuntimeBackend, and optionally adds the
        invoke_acp_agent_tool tool. In local mode, auto-discovers local CLI agents
        when no explicit config is provided.

        Failures are caught and logged — they never block Agent initialization.
        """
        if mount_invoke_acp_agent_tool is None:
            mount_invoke_acp_agent_tool = should_mount_invoke_acp_agent_tool(
                agent_id=getattr(self, "agent_id", None),
                force_external_agent=getattr(self, "force_external_agent", None),
            )
        try:
            await self._do_setup_external_agents(
                tools,
                mount_invoke_acp_agent_tool=mount_invoke_acp_agent_tool,
                external_agent_workdir=external_agent_workdir,
            )
        except Exception as e:
            logger.warning("External agent setup failed (degraded): %s", e)

    async def _do_setup_external_agents(
        self,
        tools: list[object],
        *,
        mount_invoke_acp_agent_tool: bool = True,
        external_agent_workdir: str | None = None,
    ) -> None:
        agent_cfgs = await _resolve_external_agent_cfgs(self.external_agents_config)
        if not agent_cfgs:
            return

        from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool

        from app.services.external_agents.cli_session_store import ChatCliSessionStore

        fingerprint = _config_fingerprint(agent_cfgs)
        chat_scope_id = _runtime_pool_scope_id(self)

        async def _build_pool() -> RuntimePool:
            session_store = ChatCliSessionStore(chat_scope_id) if chat_scope_id else None
            pool = RuntimePool(max_concurrent=4, cli_session_store=session_store)
            _register_backends_on_pool(pool, agent_cfgs)
            return pool

        pool: DelegationPool
        if chat_scope_id:
            from app.services.external_agents.runtime_pool_registry import (
                ChatScopedRuntimePoolFacade,
                get_chat_runtime_pool_registry,
            )

            registry = get_chat_runtime_pool_registry()
            raw_pool = await registry.acquire(
                chat_scope_id,
                fingerprint,
                _build_pool,
            )
            pool = ChatScopedRuntimePoolFacade(raw_pool, chat_scope_id, registry, fingerprint)
            self._runtime_pool_from_registry = True
            self._owned_runtime_pool = None
        else:
            owned_pool = await _build_pool()
            pool = owned_pool
            self._runtime_pool_from_registry = False
            self._owned_runtime_pool = owned_pool

        if pool.available_backends:
            self._runtime_pool = pool

            if mount_invoke_acp_agent_tool:
                from myrm_agent_harness.toolkits import create_invoke_acp_agent_tool

                chat_scope = _runtime_pool_scope_id(self)
                delegate_tool = create_invoke_acp_agent_tool(
                    pool,
                    cwd=external_agent_workdir,
                    session_scope=chat_scope,
                )
                tools.append(delegate_tool)
                logger.info(
                    "invoke_acp_agent loaded (%d backends) [Turn1]",
                    len(pool.available_backends),
                )
            else:
                logger.info(
                    "RuntimePool ready (%d backends), delegate tool skipped [direct-only]",
                    len(pool.available_backends),
                )

    async def _ensure_runtime_pool(self) -> None:
        """Initialize RuntimePool without creating the full LangChain Agent.

        Used by direct-delegate mode to set up external agent backends
        before the full Agent initialization.
        """
        if self._runtime_pool is not None:
            return
        try:
            tools: list[object] = []
            await self._do_setup_external_agents(tools, mount_invoke_acp_agent_tool=False)
        except Exception as e:
            logger.warning("RuntimePool init for direct delegate failed: %s", e)

    def _direct_delegate_stream(
        self,
        agent_name: str,
        query: object,
        *,
        cancel_token: CancellationToken | None = None,
        chat_id: str | None = None,
    ) -> AsyncGenerator[dict[str, object]]:
        """Stream one turn of an external agent straight to the frontend, bypassing the LangChain Agent."""
        from app.services.external_agents.direct_delegate_stream import stream_direct_delegate

        assert self._runtime_pool is not None
        return stream_direct_delegate(
            self._runtime_pool,
            agent_name,
            query if isinstance(query, str) else str(query),
            session_id=f"{agent_name}-{chat_id}" if chat_id else f"{agent_name}-default",
            cancel_token=cancel_token,
            locale=self.locale or "en",
        )
