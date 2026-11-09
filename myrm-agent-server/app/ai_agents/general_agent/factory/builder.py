"""[INPUT]
- app.ai_agents.general_agent.agent::GeneralAgent (POS: 通用 Agent 核心实现)
- app.ai_agents.general_agent.llm_factory::create_agent_llms (POS: 创建 LLM 实例)
- myrm_agent_harness.api.create_skill_agent (POS: SkillAgent 组装入口)

[OUTPUT]
- build_general_agent(): 将已解析配置组装为可执行的 GeneralAgent SkillAgent

[POS]
GeneralAgent 装配层。负责把业务配置、工具、存储、中间件和 LLM 组装为最终的可执行 Agent；
尊重用户在 WebUI 选择的主模型，failover 由 harness `stream_recovery` 在 API 报错时触发。
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool
    from myrm_agent_harness.agent.extensions.protocols import AgentExtension
    from myrm_agent_harness.api import SkillAgent
    from myrm_agent_harness.toolkits.mcp.config import MCPConfig

    from app.ai_agents.general_agent.agent import GeneralAgent

from app.ai_agents.general_agent.factory.llms import initialize_agent_llms
from app.ai_agents.general_agent.factory.middlewares import build_agent_middlewares
from app.ai_agents.general_agent.factory.prompt import build_system_prompt
from app.ai_agents.general_agent.factory.runtime import build_sandbox_runtime, load_channel_notify_tool
from app.ai_agents.general_agent.factory.skills import load_skill_runtime
from app.ai_agents.general_agent.factory.support import (
    _apply_small_model_tuning,
    _build_session_cleanup_callback,
    _build_skill_review_callback,
    _setup_kanban_tools,
    _should_enable_cron_tools,
    _should_enable_subagent_tools,
)

logger = logging.getLogger(__name__)


async def build_general_agent(
    agent_wrapper: "GeneralAgent",
    effective_chat_id: str,
    user_id: str | None = None,
) -> "SkillAgent":
    """Initialize Agent: create LLMs, tools, middlewares, and call framework API."""
    # Single-tenant SSOT — matches cron REST ``USER_ID`` so discover/eager cron tools bind jobs.
    if not user_id:
        user_id = "default"

    workspace_root = agent_wrapper.declared_allowed_roots[0] if agent_wrapper.declared_allowed_roots else None
    effective_prompt_locale = getattr(agent_wrapper, "prompt_locale", None) or getattr(agent_wrapper, "locale", None)

    from typing import cast

    from myrm_agent_harness.api import create_skill_agent

    from ..callbacks import (
        make_loaded_skills_persist_callback,
    )
    from ..config_builders import (
        resolve_skill_env_map,
    )

    llm_bundle = await initialize_agent_llms(agent_wrapper)
    llm = llm_bundle.llm
    fallback_llm = llm_bundle.fallback_llm
    safety_fallback_llm = llm_bundle.safety_fallback_llm
    stream_fallback_llms = llm_bundle.stream_fallback_llms
    privacy_routing_cfg = llm_bundle.privacy_routing_cfg

    # 2. Storage backend + 3. Skills
    skill_runtime = await load_skill_runtime(agent_wrapper, user_id, workspace_root)
    storage_backend = skill_runtime.storage_backend
    _user_skill_cfg = skill_runtime.user_skill_cfg
    runtime_skill_ids = skill_runtime.runtime_skill_ids
    skill_backend = skill_runtime.skill_backend

    # 4. Create tools (delegated to ToolSetupMixin)
    tools: list[object] = []
    agent_wrapper._task_user_id = user_id or "default"
    agent_wrapper._setup_search_and_basic_tools(tools)
    agent_wrapper._setup_clarification_tools(tools)

    from app.services.context.context_assembly import ContextAssemblyService

    session_memory_enabled = agent_wrapper.enable_memory and not agent_wrapper.incognito_mode

    context_assembly = ContextAssemblyService.resolve_for_agent(
        agent_wrapper,
        effective_chat_id,
        enable_memory=session_memory_enabled,
    )

    from app.ai_agents.general_agent.mount_resolver import resolve_agent_mount

    mount_plan = resolve_agent_mount(
        channel_name=getattr(agent_wrapper, "channel_name", "web_chat"),
        agent_wrapper=agent_wrapper,
    )

    memory_manager = None
    memory_binding = context_assembly.binding
    if session_memory_enabled and memory_binding is not None:
        memory_manager = await agent_wrapper._create_memory_tools(tools, memory_binding)

    if agent_wrapper.enable_cron_eager and _should_enable_cron_tools():
        await agent_wrapper._setup_cron_tools(tools, user_id=user_id)

    if mount_plan.mount_browser:
        await agent_wrapper._setup_browser_tools(tools, effective_chat_id, vision_llm=llm, memory_manager=memory_manager)

    if mount_plan.mount_computer_use:
        agent_wrapper._setup_computer_use_tools(tools)

    if agent_wrapper.enable_kanban:
        await _setup_kanban_tools(agent_wrapper, tools)

    await agent_wrapper._setup_artifact_publish_tool(tools)

    from app.ai_agents.general_agent.external_agents import (
        needs_runtime_pool,
        should_mount_invoke_acp_agent_tool,
    )

    mount_invoke_acp_agent_tool = agent_wrapper.enable_external_cli and should_mount_invoke_acp_agent_tool(
        agent_id=agent_wrapper.agent_id,
        force_external_agent=agent_wrapper.force_external_agent,
    )
    agent_wrapper._runtime_pool_scope_id = effective_chat_id
    if needs_runtime_pool(
        enable_external_cli=agent_wrapper.enable_external_cli,
        agent_id=agent_wrapper.agent_id,
        force_external_agent=agent_wrapper.force_external_agent,
    ):
        await agent_wrapper._setup_external_agents(
            tools,
            mount_invoke_acp_agent_tool=mount_invoke_acp_agent_tool,
            external_agent_workdir=str(workspace_root) if workspace_root else None,
        )

    from app.services.agent.goals.goal_registry import GoalRegistry

    enable_planning = agent_wrapper.enable_planning
    goal_provider = GoalRegistry.get_provider(effective_chat_id)
    if goal_provider:
        active_goal = await goal_provider.get_active_goal(effective_chat_id)
        if active_goal:
            enable_planning = True
            from myrm_agent_harness.agent.meta_tools.goals.goal_agent_tools import (
                create_goal_tools,
            )

            goal_tools = create_goal_tools(goal_provider, effective_chat_id)
            tools.extend(goal_tools)
            logger.info("🎯 已加载目标导向工具: complete_goal_tool")

    # 4.5 Channel notification tool (Turn1 when notify_targets configured)
    channel_notify_tool_loaded = load_channel_notify_tool(agent_wrapper, tools)

    # 5. Create sandbox executor
    runtime = await build_sandbox_runtime(
        agent_wrapper,
        llm=llm,
        memory_manager=memory_manager,
        effective_chat_id=effective_chat_id,
        workspace_root=workspace_root,
    )
    executor = runtime.executor
    memory_ext = runtime.memory_ext
    pre_compact_ext = runtime.pre_compact_ext
    archive_checkpoint_ext = runtime.archive_checkpoint_ext

    # 6. Create middlewares
    middlewares = await build_agent_middlewares(
        agent_wrapper,
        effective_chat_id,
        runtime,
        lite_llm=llm_bundle.lite_llm,
        mount_plan=mount_plan,
    )

    # 7. Checkpointer
    from app.platform_utils import get_checkpointer

    checkpointer = get_checkpointer()
    logger.info(f"使用 checkpointer: {type(checkpointer).__name__}")

    # 7.5 Auto-tune for small models (zero-config compatibility mode)
    _apply_small_model_tuning(agent_wrapper)

    # 8. System prompt
    system_prompt = build_system_prompt(
        agent_wrapper,
        mount_plan=mount_plan,
        channel_notify_tool_loaded=channel_notify_tool_loaded,
        prompt_locale=effective_prompt_locale,
    )

    # 9. Call framework API
    from app.core.skills.creation.service import skill_creation_service
    from app.core.skills.marketplace.market_service import market_service
    from app.core.skills.state_manager_instance import get_state_manager

    trusted_ids: list[str] | None = None
    resolved_env_map: dict[str, dict[str, str]] | None = None
    global_env: dict[str, str] | None = None
    secret_store = None

    if _user_skill_cfg.trusted_skill_ids:
        trusted_ids = _user_skill_cfg.trusted_skill_ids
    if _user_skill_cfg.skill_env_vars:
        resolved_env_map = await resolve_skill_env_map(skill_backend, _user_skill_cfg.skill_env_vars)

    if agent_wrapper.agent_id and agent_wrapper.mcp_config:
        try:
            from app.services.agent.mcp_runtime_prepare import (
                prepare_mcp_configs_for_runtime,
            )

            agent_wrapper.mcp_config = await prepare_mcp_configs_for_runtime(
                agent_wrapper.agent_id,
                agent_wrapper.mcp_config,
            )
        except Exception as e:
            logger.warning(
                "Failed to prepare MCP configs for agent %s: %s",
                agent_wrapper.agent_id,
                e,
            )

    state_manager = None
    default_skill_instances: dict[str, str] = {}
    try:
        from app.services.agent.skill_instance_resolver import (
            resolve_runtime_skill_instance_bindings,
        )

        state_manager = get_state_manager()
        if skill_backend and state_manager:
            all_skills = await skill_backend.list_skills()
            skill_id_to_name: dict[str, str] = {}
            for skill in all_skills:
                skill_id_to_name[skill.name] = skill.name
                if skill.storage_skill_id:
                    skill_id_to_name[skill.storage_skill_id] = skill.name

            default_skill_instances = resolve_runtime_skill_instance_bindings(
                runtime_skill_ids=runtime_skill_ids or [],
                skill_configs=agent_wrapper.skill_configs,
                skill_id_to_name=skill_id_to_name,
                state_manager=state_manager,
            )
    except Exception as e:
        logger.warning(f"Failed to initialize SkillStateManager for agent: {e}")

    from myrm_agent_harness.agent.types import WorkspaceBinding
    from myrm_agent_harness.api import AgentRuntimeSpec

    workspace_root = agent_wrapper.declared_allowed_roots[0] if agent_wrapper.declared_allowed_roots else None

    if workspace_root and agent_wrapper.mcp_config:
        from app.ai_agents.general_agent.mcp_vault_handler import (
            build_mcp_vault_handler,
        )

        vault_handler = build_mcp_vault_handler(workspace_root)
        agent_wrapper.mcp_config = [
            cfg.model_copy(update={"oversized_result_handler": vault_handler}) for cfg in agent_wrapper.mcp_config
        ]

    if agent_wrapper.mcp_config:
        from app.services.agent.backends.mcp_elicitation_handler import (
            build_mcp_elicitation_handler,
        )

        elicitation_handler = build_mcp_elicitation_handler(
            agent_id=agent_wrapper.agent_id or "default",
            chat_id=effective_chat_id,
        )
        agent_wrapper.mcp_config = [
            cfg.model_copy(update={"elicitation_handler": elicitation_handler}) for cfg in agent_wrapper.mcp_config
        ]

    workspace_mode = "chat"
    workspace_binding = (
        WorkspaceBinding(
            mode=workspace_mode,
            root_path=workspace_root or "",
            chat_id=effective_chat_id,
        )
        if workspace_root
        else None
    )

    memory_binding = context_assembly.binding
    memory_namespaces = memory_binding.namespaces if memory_binding is not None else []

    allowed_tool_names: list[str] = []
    for t in tools:
        raw_name = getattr(t, "name", None)
        if isinstance(raw_name, str):
            allowed_tool_names.append(raw_name)

    from app.ai_agents.general_agent.active_tool_groups import derive_active_tool_groups

    active_tool_groups = derive_active_tool_groups(agent_wrapper, enable_planning=enable_planning)

    from app.services.agent.mcp_surface_mode import normalize_mcp_surface_engine_params

    mcp_surface_mode, normalized_engine_params = normalize_mcp_surface_engine_params(agent_wrapper.engine_params)

    from app.ai_agents.extensions import SecurityPolicyExtension, SubagentManagementExtension

    security_ext = SecurityPolicyExtension(
        privacy_enabled=agent_wrapper.privacy_enabled,
        privacy_s2_action=agent_wrapper.privacy_s2_action,
        privacy_s3_action=agent_wrapper.privacy_s3_action,
        privacy_custom_keywords_s2=agent_wrapper.privacy_custom_keywords_s2,
        privacy_custom_keywords_s3=agent_wrapper.privacy_custom_keywords_s3,
        privacy_custom_patterns_s2=agent_wrapper.privacy_custom_patterns_s2,
        privacy_custom_patterns_s3=agent_wrapper.privacy_custom_patterns_s3,
        privacy_sensitive_tools_s2=agent_wrapper.privacy_sensitive_tools_s2,
        privacy_sensitive_tools_s3=agent_wrapper.privacy_sensitive_tools_s3,
        privacy_deep_scan=agent_wrapper.privacy_deep_scan,
        plan_confirm_enabled=agent_wrapper.enable_plan_confirm,
        channel_name=agent_wrapper.channel_name,
        security_config_raw=agent_wrapper.security_config_raw,
        agent_security_raw=agent_wrapper.agent_security_raw,
        declared_capabilities=agent_wrapper.declared_capabilities,
        declared_allowed_roots=agent_wrapper.declared_allowed_roots,
    )

    spec = AgentRuntimeSpec(
        agent_id=agent_wrapper.agent_id,
        name=agent_wrapper.agent_id or "default",
        system_prompt=system_prompt,
        allowed_tools=allowed_tool_names,
        tool_groups=active_tool_groups,
        skill_ids=runtime_skill_ids,
        skill_configs=agent_wrapper.skill_configs,
        # The harness reads MCP configs by attribute and applies its own default where MCPServerConfig has no field (max_output_chars).
        mcp_servers=cast("list[MCPConfig]", agent_wrapper.mcp_config or []),
        openapi_services=agent_wrapper.openapi_services or [],
        memory_namespaces=memory_namespaces,
        workspace_binding=workspace_binding,
        max_iterations=agent_wrapper.max_iterations or 100,
        unattended=getattr(agent_wrapper, "unattended_mode", False),
        locale=agent_wrapper.locale,
        prompt_locale=effective_prompt_locale,
        channel_name=agent_wrapper.channel_name,
        security_config=security_ext._build_security_config(),
        engine_params=normalized_engine_params,
        mcp_surface_mode=mcp_surface_mode,
    )

    library_skill_names: frozenset[str] = frozenset()
    if skill_backend is not None:
        try:
            library_skills = await skill_backend.list_skills()
            library_skill_names = frozenset(skill.name for skill in library_skills)
        except Exception as e:
            logger.warning(
                "Failed to load skill library names for gap detection (non-blocking): %s",
                e,
            )

    # PTC dependency auto-injection: MCP/PTC skills require bash + file_read
    from app.services.agent.tool_mount import apply_ptc_meta_mount

    effective_file_access, effective_enable_shell = apply_ptc_meta_mount(
        agent_wrapper.file_access_mode,
        agent_wrapper.enable_shell_tools,
        has_mcp=bool(agent_wrapper.mcp_config),
    )

    mount_skill_market = getattr(agent_wrapper, "enable_skill_market", False)

    if mount_skill_market:
        agent_wrapper._setup_skill_market_tool(tools, market_service)
    if agent_wrapper.skill_manage_mounted:
        from app.core.skills.creation.version_persisting_backend import (
            VersionPersistingSkillWriteBackend,
        )

        versioned_write_backend = VersionPersistingSkillWriteBackend(skill_creation_service)
        agent_wrapper._setup_skill_manage_tool(
            tools,
            versioned_write_backend,
            skill_backend,
            auxiliary_llm=fallback_llm or llm,
        )

    from app.ai_agents.extensions.extraction_lifecycle import (
        make_extraction_lifecycle_observer,
    )

    agent = await create_skill_agent(
        spec=spec,
        llm=llm,
        executor=executor,
        storage_backend=storage_backend,
        skill_backend=skill_backend,
        market_backend=None,
        write_backend=None,
        secret_backend=secret_store if agent_wrapper.agent_id else None,
        memory_manager=memory_manager,
        enable_memory_auto_extraction=agent_wrapper.enable_memory and agent_wrapper.enable_memory_auto_extraction,
        extraction_llm=agent_wrapper._lite_llm,
        middlewares=middlewares,
        tools=cast("list[BaseTool]", tools),
        collect_artifacts=True,
        fallback_llm=fallback_llm,
        fallback_llms=stream_fallback_llms,
        safety_fallback_llm=safety_fallback_llm,
        checkpointer=checkpointer,
        privacy_routing_config=privacy_routing_cfg,
        event_log_backend=agent_wrapper.event_log_backend,
        trusted_skill_ids=trusted_ids,
        skill_env_map=resolved_env_map,
        state_manager=state_manager,
        default_skill_instances=(default_skill_instances if default_skill_instances else None),
        global_env=global_env,
        on_skill_review_ready=_build_skill_review_callback(agent_wrapper),
        on_session_cleanup=_build_session_cleanup_callback(
            agent_wrapper,
            user_id or "default",
            memory_manager=memory_manager,
        ),
        on_loaded_skills_persist=(None if agent_wrapper.incognito_mode else make_loaded_skills_persist_callback()),
        extraction_lifecycle_observer=(
            make_extraction_lifecycle_observer(effective_chat_id)
            if agent_wrapper.enable_memory and agent_wrapper.enable_memory_auto_extraction and not agent_wrapper.incognito_mode
            else None
        ),
        wiki_base_dir=(agent_wrapper._resolve_wiki_base_dir() if agent_wrapper.enable_wiki else None),
        wiki_public_dirs=(agent_wrapper._resolve_wiki_public_dirs() if agent_wrapper.enable_wiki else None),
        wiki_public_dir_labels=(agent_wrapper._resolve_wiki_public_dir_labels() if agent_wrapper.enable_wiki else None),
        wiki_scope_id=agent_wrapper.agent_id,
        file_access_mode=effective_file_access,
        enable_shell_tools=effective_enable_shell,
        enable_answer_tool=agent_wrapper.enable_answer_tool,
        enable_planning=enable_planning,
        task_workspace_root=workspace_root,
        library_skill_names=library_skill_names,
    )

    # 9.5 Register extensions (subagent tools, security, memory)
    extensions: list[AgentExtension] = [
        memory_ext,
        pre_compact_ext,
        archive_checkpoint_ext,
        security_ext,
    ]

    if _should_enable_subagent_tools():
        logger.warning("Subagent tools are enabled. Adding SubagentManagementExtension.")
        subagent_ext = SubagentManagementExtension(
            jit_subagents=agent_wrapper.jit_subagents,
            subagent_ids=agent_wrapper.subagent_ids or [],
            incognito_mode=agent_wrapper.incognito_mode,
        )
        extensions.insert(-1, subagent_ext)
    else:
        logger.warning("Subagent tools are NOT enabled. Skipping SubagentManagementExtension.")

    for ext in extensions:
        agent.register_extension(ext)

    try:
        from app.services.budget.enforcer import get_budget_guard

        budget_guard = await get_budget_guard()
        if budget_guard is not None:
            agent.budget_checker = budget_guard
            logger.info("Budget guard injected into agent")
    except Exception as e:
        logger.warning("Failed to load budget guard (non-blocking): %s", e)

    logger.info("GeneralAgent 初始化完成")
    return agent
