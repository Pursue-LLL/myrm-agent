"""External agent delegation setup and direct-delegate streaming.

[INPUT]
- myrm_agent_harness.toolkits.acp (POS: 外部 Agent 委托协议框架)
- myrm_agent_harness.agent.streaming.types (POS: 流式事件类型)
- app.config.deploy_mode (POS: 部署模式检测)
- .external_agents_runtime_config (POS: 外部 Agent 配置归一化层)

[OUTPUT]
- ExternalAgentsMixin: 外部 Agent 初始化与直接委托流式执行的 Mixin
- should_mount_delegate_tool(): direct-only 路径是否跳过 delegate_to_agent 挂载
- needs_runtime_pool(): factory 是否 eager 初始化 RuntimePool（与 stream lazy path 对齐）
- BUILTIN_CLI_VISUAL_AGENT_ID: CLI Visual 内置 Agent 标识
- chat scope 路径：ChatRuntimePoolRegistry + ChatScopedRuntimePoolFacade 接线

[POS]
外部 Agent 委托层。负责 RuntimePool 初始化、CLI/ACP/SDK 后端注册、
本地模式自动检测（请求热路径使用 path-only 探测，版本探测留给设置态），
以及绕过 LangChain 直接向前端流式转发外部 Agent 事件。
RuntimePool 启用会话内 HealthMonitor（活跃 chat 流内进程崩溃恢复）；
Settings auth/status 仅报告安装/登录态，不暴露 ephemeral pool metrics。
有 chat scope 时经 ChatRuntimePoolRegistry 跨消息复用 pool（CLI --resume），
ChatScopedRuntimePoolFacade 对 run_turn 做 per-chat single-flight 串行化。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import external_agents_runtime_config as _runtime_cfg_helpers

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
    from myrm_agent_harness.utils import CancellationToken

logger = logging.getLogger(__name__)

BUILTIN_CLI_VISUAL_AGENT_ID = "builtin-cli_visual"

_default_cli_args = _runtime_cfg_helpers._default_cli_args
_auth_mode = _runtime_cfg_helpers._auth_mode
_cfg_int = _runtime_cfg_helpers._cfg_int
_config_fingerprint = _runtime_cfg_helpers._config_fingerprint
_resolve_external_agent_cfgs = _runtime_cfg_helpers._resolve_external_agent_cfgs
_register_backends_on_pool = _runtime_cfg_helpers._register_backends_on_pool


def should_mount_delegate_tool(*, agent_id: str | None, force_delegate_agent: str | None) -> bool:
    """Return False when direct-delegate routing makes the LLM tool redundant."""
    if force_delegate_agent:
        return False
    if agent_id == BUILTIN_CLI_VISUAL_AGENT_ID:
        return False
    return True


def needs_runtime_pool(
    *,
    enable_external_cli: bool,
    agent_id: str | None,
    force_delegate_agent: str | None,
) -> bool:
    """Return True when factory should eagerly init RuntimePool (not lazy stream path)."""
    if force_delegate_agent:
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
        _runtime_pool: RuntimePool | None
        _runtime_pool_scope_id: str | None
        _runtime_pool_from_registry: bool
        _runtime_pool_ephemeral: bool
        chat_id: str | None
        agent_id: str | None
        force_delegate_agent: str | None

    async def _setup_external_agents(
        self,
        tools: list[object],
        *,
        mount_delegate_tool: bool | None = None,
        delegate_cwd: str | None = None,
    ) -> None:
        """Set up external agent delegation via RuntimePool.

        Parses external_agents_config (from UserConfig 'externalAgents'),
        registers each enabled agent as a RuntimeBackend, and optionally adds the
        delegate_to_agent tool. In local mode, auto-discovers local CLI agents
        when no explicit config is provided.

        Failures are caught and logged — they never block Agent initialization.
        """
        if mount_delegate_tool is None:
            mount_delegate_tool = should_mount_delegate_tool(
                agent_id=getattr(self, "agent_id", None),
                force_delegate_agent=getattr(self, "force_delegate_agent", None),
            )
        try:
            await self._do_setup_external_agents(
                tools,
                mount_delegate_tool=mount_delegate_tool,
                delegate_cwd=delegate_cwd,
            )
        except Exception as e:
            logger.warning("External agent setup failed (degraded): %s", e)

    async def _do_setup_external_agents(
        self,
        tools: list[object],
        *,
        mount_delegate_tool: bool = True,
        delegate_cwd: str | None = None,
    ) -> None:
        agent_cfgs = await _resolve_external_agent_cfgs(self.external_agents_config)
        if not agent_cfgs:
            return

        from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool

        fingerprint = _config_fingerprint(agent_cfgs)
        chat_scope_id = _runtime_pool_scope_id(self)

        async def _build_pool() -> RuntimePool:
            pool = RuntimePool(max_concurrent=4, enable_health_monitor=True)
            _register_backends_on_pool(pool, agent_cfgs)
            await pool.start_monitoring()
            return pool

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
            pool = ChatScopedRuntimePoolFacade(raw_pool, chat_scope_id, registry)
            self._runtime_pool_from_registry = True
            self._runtime_pool_ephemeral = False
        else:
            pool = await _build_pool()
            self._runtime_pool_from_registry = False
            self._runtime_pool_ephemeral = True

        if pool.available_backends:
            self._runtime_pool = pool

            if mount_delegate_tool:
                from myrm_agent_harness.toolkits import create_delegate_to_agent_tool

                chat_scope = _runtime_pool_scope_id(self)
                delegate_tool = create_delegate_to_agent_tool(
                    pool,
                    cwd=delegate_cwd,
                    session_scope=chat_scope,
                )
                tools.append(delegate_tool)
                logger.info(
                    "delegate_to_agent loaded (%d backends) [Turn1]",
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
            await self._do_setup_external_agents(tools, mount_delegate_tool=False)
        except Exception as e:
            logger.warning("RuntimePool init for direct delegate failed: %s", e)

    async def _direct_delegate_stream(
        self,
        agent_name: str,
        query: object,
        *,
        cancel_token: CancellationToken | None = None,
        chat_id: str | None = None,
    ) -> AsyncGenerator[dict[str, object], None]:
        """Stream events from an external agent directly to the frontend.

        Bypasses the LangChain Agent entirely. Converts RuntimeEvents to
        the frontend SSE event format (AgentEventType).
        """
        from myrm_agent_harness.api import AgentEventType
        from myrm_agent_harness.toolkits.acp.types import RuntimeEventType

        assert self._runtime_pool is not None

        text_query = query if isinstance(query, str) else str(query)
        session_id = f"{agent_name}-{chat_id}" if chat_id else f"{agent_name}-default"
        _cfg = self._runtime_pool.get_config(agent_name)
        auth_mode = _cfg.auth_mode if _cfg else "subscription"

        yield {
            "type": AgentEventType.TASKS_STEPS.value,
            "step_key": f"delegation_{agent_name}_status",
            "tool_name": f"delegate:{agent_name}",
            "data": [{"text": f"{agent_name}: connecting"}],
        }

        async for event in self._runtime_pool.run_turn(agent_name, text_query, session_id=session_id):
            if cancel_token and cancel_token.is_cancelled:
                await self._runtime_pool.cancel(agent_name, session_id)
                yield {"type": AgentEventType.CANCELLED.value}
                return

            if event.type == RuntimeEventType.TEXT_DELTA:
                content = event.data.get("content")
                if isinstance(content, str):
                    yield {"type": AgentEventType.MESSAGE.value, "data": content}

            elif event.type == RuntimeEventType.REASONING_DELTA:
                content = event.data.get("content")
                if isinstance(content, str):
                    yield {
                        "type": AgentEventType.REASONING.value,
                        "data": {
                            "content": content,
                            "source": f"delegate:{agent_name}",
                        },
                    }

            elif event.type == RuntimeEventType.TOOL_START:
                tool_name = event.data.get("tool_name", "unknown")
                yield {
                    "type": AgentEventType.TASKS_STEPS.value,
                    "step_key": f"delegation_{agent_name}_tool",
                    "tool_name": f"delegate:{agent_name}",
                    "data": [{"text": f"{agent_name}: {tool_name}"}],
                }

            elif event.type == RuntimeEventType.TOOL_RESULT:
                is_error = event.data.get("is_error", False)
                status_icon = "x" if is_error else "ok"
                yield {
                    "type": AgentEventType.TASKS_STEPS.value,
                    "step_key": f"delegation_{agent_name}_tool",
                    "tool_name": f"delegate:{agent_name}",
                    "data": [{"text": f"{status_icon} {agent_name}: tool completed"}],
                    "status": "error" if is_error else "completed",
                }

            elif event.type == RuntimeEventType.STATUS_UPDATE:
                status = event.data.get("status", "")
                message = event.data.get("message", "")
                yield {
                    "type": AgentEventType.TASKS_STEPS.value,
                    "step_key": f"delegation_{agent_name}_status",
                    "tool_name": f"delegate:{agent_name}",
                    "data": [{"text": f"{agent_name}: {status}" + (f" — {message}" if message else "")}],
                }

            elif event.type == RuntimeEventType.USAGE_UPDATE:
                input_tokens = int(event.data.get("input_tokens") or 0)
                output_tokens = int(event.data.get("output_tokens") or 0)
                total_tokens = input_tokens + output_tokens
                if total_tokens > 0:
                    yield {
                        "type": AgentEventType.TOKEN_USAGE.value,
                        "data": {
                            "source": f"delegate:{agent_name}",
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "total_tokens": total_tokens,
                            # Subscription runs on the user's own plan → no metered API cost.
                            "auth_mode": auth_mode,
                            "billable": auth_mode == "api_key",
                        },
                    }

            elif event.type == RuntimeEventType.ERROR:
                error_data = event.data.get("error")
                msg = getattr(error_data, "message", str(error_data)) if error_data else "Unknown error"
                yield {"type": AgentEventType.ERROR.value, "data": msg}

        yield {
            "type": AgentEventType.TASKS_STEPS.value,
            "step_key": f"delegation_{agent_name}_status",
            "tool_name": f"delegate:{agent_name}",
            "data": [{"text": f"{agent_name}: completed"}],
            "status": "completed",
        }
        yield {"type": AgentEventType.MESSAGE_END.value, "data": ""}
