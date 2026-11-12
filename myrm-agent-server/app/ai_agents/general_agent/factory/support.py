"""[INPUT]
- myrm_agent_harness.toolkits.kanban::KanbanStore / create_kanban_tools (POS: Kanban toolkit entry point. Aggregates dispatcher, protocols, built-in implementations, and data models for the protocol-first kanban framework.)
- myrm_agent_harness.toolkits.mcp.config::MCPConfig (POS: MCP Configuration)
- myrm_agent_harness.toolkits.memory.manager::MemoryManager (POS: Stable public import path for the memory toolkit façade.)
- app.ai_agents.general_agent.agent::GeneralAgent (POS: 通用 Agent 核心实现。管理 Agent 生命周期（初始化、流式执行、资源释放）， 工具创建委托给 ToolSetupMixin。)
- app.core.types::MCPServerConfig (POS: Core types package)
- app.config.computer_use_deploy::is_computer_use_deploy_supported (POS: Deploy-mode gates for computer_use (Semantic Desktop Control).)
- app.platform_utils.deployment_capabilities::get_deployment_capabilities / get_deployment_capabilities (POS: 部署能力语义注册表。启动时一次性计算并缓存当前部署环境支持的语义能力位。)
- app.ai_agents.general_agent.kanban_tool_mode::resolve_kanban_tool_mode (POS: GeneralAgent factory 的 Kanban 工具 bind 解析辅助模块；TaskRunner 强制 worker，chat 默认 orchestrator。)
- app.services.kanban.kanban_attach_handler::create_kanban_attach_handler (POS: Server-side implementation for kanban_attach LLM tool (SSRF-safe URL fetch + worktree-aware path ingest).)
- app.services.kanban.service::KanbanService (POS: Kanban business service facade; domain logic lives in sibling orchestrator modules.)
- app.ai_agents.general_agent.callbacks::make_skill_review_callback / make_commitment_extraction_callback (POS: Callbacks for General Agent)
- myrm_agent_harness.api.hooks::create_extraction_llm_func (POS: Public re-export facade. Product code imports hooks here instead of private ``agent._*`` modules.)
- myrm_agent_harness.toolkits.memory.session_post_process::run_session_post_process (POS: Single entry point for memory-domain background work after a conversation session ends (proactive extraction, implicit feedback detection, etc.).)
- app.ai_agents.general_agent.correction_propagation::make_correction_propagation_callback (POS: 会话结束时的隐式纠错传播。两阶段检测用户纠正信号，产出结构化纠错提案，分别路由到 Harness 审批队列（个人记忆，HITL）与绑定的 SharedContext 写入提案。)
- app.ai_agents.general_agent.frustration_routing::make_frustration_skill_routing_callback (POS: Frustration signal → Skill evolution routing callback.)
- app.services.agent.backends.mcp_oauth_store::get_mcp_oauth_token_store (POS: MCP OAuth token encrypted persistence. Implements framework MCPOAuthTokenStore protocol with AES-256-GCM encryption, stampede-safe token refresh, and cross-server atomic writes.)
- myrm_agent_harness.toolkits.mcp.oauth::MCPOAuthProvider (POS: MCP OAuth 2.0 + PKCE authentication. Framework-level provider implementing MCPAuthProvider, delegating token storage to the business layer.)
- app.platform_utils.sandbox.entitlements.entitlement_guard::fetch_sandbox_entitlements / fetch_sandbox_entitlements (POS: Sandbox entitlement guard — resolves CP internal entitlements for SaaS sandbox mode.)
- app.services.budget.enforcer::is_eco_mode_active (POS: Budget enforcement service. Bridges harness MultidimensionalBudgetGuard with server-side persistence and SSE alerts.)

[OUTPUT]
- _try_inject_mcp_oauth: Inject MCPOAuthProvider if the server has stored OAuth tokens.
- _should_setup_computer_use_tools: Return False when deploy mode or sandbox entitlements cannot run desktop control.
- _should_enable_cron_tools: Return False in SaaS sandbox when the plan does not include cron.
- _should_enable_subagent_tools: Return False only when SaaS sandbox cannot reach Control Plane entitlements.
- _resolve_kanban_default_board_id: Pick default board for kanban tools: preferred id when valid, else newest when unset.
- _setup_kanban_tools: Load kanban tools according to agent_wrapper.kanban_tool_mode.
- _get_budget_pressure_fn: Create budget pressure callback for eco mode, or None if budget module unavailable.
- _build_skill_review_callback: Background skill review writes skills and approval records, so an incognito session never wires it.
- _build_session_cleanup_callback: Build a composite session cleanup callback (follow-up extraction + correction propagation + skill routing).

[POS]
与装配主流程分离的工具/Kanban/回调构造；只被 factory 包内部调用。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from myrm_agent_harness.toolkits.kanban import KanbanStore
    from myrm_agent_harness.toolkits.mcp.config import MCPConfig
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

    from app.ai_agents.general_agent.agent import GeneralAgent
    from app.core.types import MCPServerConfig


async def _try_inject_mcp_oauth[Config: (MCPConfig, MCPServerConfig)](cfg: Config) -> Config:
    """Inject MCPOAuthProvider if the server has stored OAuth tokens."""
    if cfg.type not in ("sse", "streamable_http"):
        return cfg
    if getattr(cfg, "auth_provider", None) is not None:
        return cfg

    try:
        from app.services.agent.backends.mcp_oauth_store import (
            get_mcp_oauth_token_store,
        )

        store = get_mcp_oauth_token_store()
        token = await store.get_token(cfg.name)
        if token is None:
            return cfg

        oauth_config = await store.get_oauth_config(cfg.name)
        if oauth_config is None:
            return cfg

        from myrm_agent_harness.toolkits.mcp.oauth import MCPOAuthProvider

        provider = MCPOAuthProvider(
            server_name=cfg.name,
            oauth_config=oauth_config,
            token_store=store,
        )
        return cfg.model_copy(update={"auth_provider": provider})
    except Exception:
        logger.debug("MCP OAuth injection skipped for '%s'", cfg.name, exc_info=True)
        return cfg


def _should_setup_computer_use_tools(enable_flag: bool) -> bool:
    """Return False when deploy mode or sandbox entitlements cannot run desktop control."""
    if not enable_flag:
        return False

    from app.config.computer_use_deploy import is_computer_use_deploy_supported

    return is_computer_use_deploy_supported()


def _should_enable_cron_tools() -> bool:
    """Return False in SaaS sandbox when the plan does not include cron."""
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    if not get_deployment_capabilities().uses_cp_entitlements:
        return True

    try:
        from app.platform_utils.sandbox.entitlements.entitlement_guard import (
            fetch_sandbox_entitlements,
        )

        entitlements = fetch_sandbox_entitlements()
        if entitlements is None:
            return False
        return entitlements.enable_cron
    except Exception as exc:
        logger.warning("Cron entitlement check failed (disabling tools): %s", exc)
        return False


def _should_enable_subagent_tools() -> bool:
    """Return False only when SaaS sandbox cannot reach Control Plane entitlements.

    Subagent delegation is a base capability on all plans; Work Unit balance gates consumption.
    """
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    if not get_deployment_capabilities().uses_cp_entitlements:
        return True

    try:
        from app.platform_utils.sandbox.entitlements.entitlement_guard import (
            fetch_sandbox_entitlements,
        )

        entitlements = fetch_sandbox_entitlements()
        if entitlements is None:
            return False
        return True
    except Exception as exc:
        logger.warning("Sub-agent entitlement check failed (disabling tools): %s", exc)
        return False


async def _resolve_kanban_default_board_id(
    store: "KanbanStore",
    *,
    preferred_board_id: str | None,
) -> str | None:
    """Pick default board for kanban tools: preferred id when valid, else newest when unset."""
    boards = await store.list_boards()
    if not boards:
        return None

    board_ids = {b.board_id for b in boards}
    if preferred_board_id and preferred_board_id in board_ids:
        return preferred_board_id
    if preferred_board_id:
        return None
    return boards[0].board_id


async def _setup_kanban_tools(
    agent_wrapper: "GeneralAgent",
    tools: list[object],
) -> None:
    """Load kanban tools according to agent_wrapper.kanban_tool_mode."""
    from myrm_agent_harness.toolkits.kanban import create_kanban_tools

    from app.ai_agents.general_agent.kanban_tool_mode import resolve_kanban_tool_mode
    from app.services.kanban.kanban_attach_handler import create_kanban_attach_handler
    from app.services.kanban.service import KanbanService

    kanban_svc = KanbanService.get_instance()
    store = kanban_svc.store

    mode = resolve_kanban_tool_mode(
        kanban_tool_mode=agent_wrapper.kanban_tool_mode,
        kanban_current_task_id=agent_wrapper.kanban_current_task_id,
    )
    chat_id = getattr(agent_wrapper, "chat_id", None)

    # Resolve default board and active dispatcher for wake signals
    default_board_id: str | None = None
    dispatcher = None

    # For worker mode, resolve board from the task itself
    if agent_wrapper.kanban_current_task_id:
        task = await store.get_task(agent_wrapper.kanban_current_task_id)
        if task:
            default_board_id = task.board_id
            dispatcher = kanban_svc._dispatchers.get(task.board_id)
    else:
        preferred = getattr(agent_wrapper, "kanban_default_board_id", None)
        default_board_id = await _resolve_kanban_default_board_id(
            store,
            preferred_board_id=preferred,
        )
        if default_board_id:
            dispatcher = kanban_svc._dispatchers.get(default_board_id)

    kanban_tools = create_kanban_tools(
        store,
        dispatcher,
        mode=mode,
        default_board_id=default_board_id,
        agent_id=agent_wrapper.agent_id,
        current_task_id=agent_wrapper.kanban_current_task_id,
        attach_task_file=(create_kanban_attach_handler(store) if mode == "worker" else None),
        source_chat_id=(chat_id if mode == "orchestrator" and chat_id else None),
    )
    tools.extend(kanban_tools)
    tool_names = ", ".join(t.name for t in kanban_tools)
    logger.info("Loaded kanban tools (mode=%s): %s", mode, tool_names)


def _get_budget_pressure_fn() -> "Callable[[], bool] | None":
    """Create budget pressure callback for eco mode, or None if budget module unavailable."""
    try:
        from app.services.budget.enforcer import is_eco_mode_active

        return is_eco_mode_active
    except Exception:
        return None


def _build_skill_review_callback(agent_wrapper: "GeneralAgent") -> "Callable[[dict[str, object]], None] | None":
    """Background skill review writes skills and approval records, so an incognito session never wires it."""
    if agent_wrapper.incognito_mode:
        return None

    from ..callbacks import make_skill_review_callback

    return make_skill_review_callback(memory_enabled=agent_wrapper.enable_memory)


def _build_session_cleanup_callback(
    agent_wrapper: "GeneralAgent",
    user_id: str,
    memory_manager: "MemoryManager | None" = None,
) -> "Callable[[Sequence[dict[str, str]], str | None], Awaitable[None]] | None":
    """Build a composite session cleanup callback (follow-up extraction + correction propagation + skill routing)."""
    if not agent_wrapper.enable_memory or agent_wrapper.incognito_mode:
        return None

    lite_llm = agent_wrapper._lite_llm
    if lite_llm is None:
        return None

    from myrm_agent_harness.api.hooks import (
        create_extraction_llm_func,
    )
    from myrm_agent_harness.toolkits.memory.session_post_process import (
        run_session_post_process,
    )

    from ..callbacks import make_commitment_extraction_callback
    from ..correction_propagation import make_correction_propagation_callback
    from ..frustration_routing import make_frustration_skill_routing_callback

    llm_func = create_extraction_llm_func(lite_llm)
    agent_id = agent_wrapper.agent_id or "default"
    channel = agent_wrapper.channel_name or "web"

    tasks = [
        make_commitment_extraction_callback(
            agent_id=agent_id,
            user_id=user_id,
            channel=channel,
            llm_func=llm_func,
        ),
        make_correction_propagation_callback(
            agent_id=agent_id,
            llm_func=llm_func,
            memory_manager=memory_manager,
        ),
        make_frustration_skill_routing_callback(
            agent_id=agent_id,
            profile_skill_ids=list(agent_wrapper.skill_ids or []),
            llm_func=llm_func,
        ),
    ]

    async def _composite(messages: "Sequence[dict[str, str]]", chat_id: str | None) -> None:
        await run_session_post_process(tasks, messages, chat_id)

    return _composite
