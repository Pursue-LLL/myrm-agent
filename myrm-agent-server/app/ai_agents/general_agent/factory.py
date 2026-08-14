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
    from collections.abc import Awaitable, Callable, Sequence

    from myrm_agent_harness.agent.extensions.protocols import AgentExtension
    from myrm_agent_harness.api import SkillAgent

    from app.ai_agents.general_agent.agent import GeneralAgent
    from app.services.agent.params.models import MCPConfig

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

    from typing import cast

    from langchain.agents.middleware.types import AgentMiddleware
    from myrm_agent_harness.agent.context_management.infra.cache_policy import (
        resolve_cache_ttl_prune_policy,
    )
    from myrm_agent_harness.agent.middlewares import (
        create_context_pipeline_middleware,
    )
    from myrm_agent_harness.agent.workspace_rules import (
        workspace_rules_middleware,
    )
    from myrm_agent_harness.api import create_skill_agent

    from app.ai_agents.agent_middlewares import (
        memory_context_middleware,
        project_roadmap_middleware,
        user_instructions_middleware,
        widget_capability_middleware,
    )
    from app.ai_agents.prompts.general_agent_prompt import get_core_system_prompt
    from app.core.skills.effective_skill_ids import resolve_runtime_skill_ids
    from app.core.skills.loader import create_skill_backend
    from app.core.utils.media_file_reader import read_uploaded_media_file_content

    from .agent_middlewares.citation_rules_middleware import citation_rules_middleware
    from .agent_middlewares.tool_selection_middleware import tool_selection_middleware
    from .callbacks import (
        make_loaded_skills_persist_callback,
        make_notes_load,
        make_notes_persist,
        make_skill_review_callback,
        make_summary_persist_with_wiki_archive,
    )
    from .config_builders import (
        build_execution_config,
        build_privacy_routing_config,
        resolve_skill_env_map,
        wrap_with_privacy_routing,
    )
    from .llm_factory import apply_lite_managed_fallback, create_agent_llms

    llm, agent_wrapper._lite_llm, fallback_llm, safety_fallback_llm = (
        await create_agent_llms(
            agent_wrapper.model_cfg,
            agent_wrapper.lite_model_cfg,
            agent_wrapper.fallback_model_cfg,
            agent_wrapper.safety_fallback_model_cfg,
        )
    )

    privacy_routing_cfg = build_privacy_routing_config(
        agent_wrapper.privacy_routing_raw
    )
    if agent_wrapper._lite_llm is not None:
        from app.ai_agents.general_agent.llm_factory import (
            apply_lite_context_downgrade,
        )

        agent_wrapper._lite_llm, lite_cfg_for_fallback = (
            await apply_lite_context_downgrade(
                llm,
                agent_wrapper._lite_llm,
                agent_wrapper.model_cfg,
                agent_wrapper.lite_model_cfg,
            )
        )
        agent_wrapper._lite_llm = await apply_lite_managed_fallback(
            agent_wrapper._lite_llm,
            lite_cfg_for_fallback,
            agent_wrapper.fallback_lite_model_cfg,
        )

    escalation_target_llm = None
    if agent_wrapper.reasoning_model_cfg is not None:
        reasoning_model_name = agent_wrapper.reasoning_model_cfg.model
        main_model_name = agent_wrapper.model_cfg.model
        if reasoning_model_name != main_model_name:
            try:
                reasoning_api_keys = getattr(
                    agent_wrapper.reasoning_model_cfg, "api_keys", None
                )
                from myrm_agent_harness.toolkits.llms import llm_manager

                escalation_target_llm = await llm_manager.get_llm_from_config(
                    agent_wrapper.reasoning_model_cfg, api_keys=reasoning_api_keys
                )
                logger.warning(
                    "Escalation target model: %s (auto-upgrade from %s)",
                    reasoning_model_name,
                    main_model_name,
                )
            except Exception as e:
                logger.warning(
                    "Failed to create escalation target LLM: %s, auto-escalation disabled",
                    e,
                )

    if privacy_routing_cfg is not None and agent_wrapper._lite_llm is not None:
        agent_wrapper._lite_llm = wrap_with_privacy_routing(
            agent_wrapper._lite_llm, privacy_routing_cfg
        )

    from app.services.org_model_policy.enforce import enforce_org_model_policy

    await enforce_org_model_policy(agent_wrapper)

    # 2. Storage backend (adapts to DEPLOY_MODE)
    from app.platform_utils import get_storage_provider

    storage_backend = get_storage_provider()

    # 3. Load Skills (with prebuilt whitelist from Agent Profile)
    workspace_root = (
        agent_wrapper.declared_allowed_roots[0]
        if agent_wrapper.declared_allowed_roots
        else None
    )

    from app.core.skills.store.user_config import UserSkillConfigManager

    _user_skill_cfg = await UserSkillConfigManager(storage_backend).get_config()
    allowed_prebuilt = frozenset(_user_skill_cfg.enabled_prebuilt_ids)
    runtime_skill_ids = await resolve_runtime_skill_ids(agent_wrapper.skill_ids)

    skill_backend = await create_skill_backend(
        storage=storage_backend,
        skill_ids=runtime_skill_ids or None,
        user_id=user_id,
        workspace_path=workspace_root,
        allowed_prebuilt_ids=allowed_prebuilt,
    )

    # 4. Create tools (delegated to ToolSetupMixin)
    tools: list[object] = []
    agent_wrapper._task_user_id = user_id or "default"
    agent_wrapper._setup_search_and_basic_tools(tools)
    agent_wrapper._setup_clarification_tools(tools)
    agent_wrapper._setup_session_access_tools(tools)

    from app.services.context.context_assembly import ContextAssemblyService

    session_memory_enabled = (
        agent_wrapper.enable_memory and not agent_wrapper.incognito_mode
    )

    context_assembly = ContextAssemblyService.resolve_for_agent(
        agent_wrapper,
        effective_chat_id,
        enable_memory=session_memory_enabled,
    )

    memory_manager = None
    memory_binding = context_assembly.binding
    if session_memory_enabled and memory_binding is not None:
        memory_manager = await agent_wrapper._create_memory_tools(tools, memory_binding)

    if agent_wrapper.enable_cron_eager and _should_enable_cron_tools():
        await agent_wrapper._setup_cron_tools(tools, user_id=user_id)

    if agent_wrapper.enable_browser:
        await agent_wrapper._setup_browser_tools(
            tools, effective_chat_id, vision_llm=llm, memory_manager=memory_manager
        )

    if _should_setup_computer_use_tools(agent_wrapper.enable_computer_use):
        agent_wrapper._setup_computer_use_tools(tools)

    if runtime_skill_ids and "vision-toolkit" in runtime_skill_ids:
        agent_wrapper._setup_vision_toolkit_tools(tools)

    if agent_wrapper.enable_kanban:
        await _setup_kanban_tools(agent_wrapper, tools)

    await agent_wrapper._setup_artifact_publish_tool(tools)

    from app.ai_agents.general_agent.external_agents import (
        needs_runtime_pool,
        should_mount_delegate_tool,
    )

    mount_delegate_tool = (
        agent_wrapper.enable_external_cli
        and should_mount_delegate_tool(
            agent_id=agent_wrapper.agent_id,
            force_delegate_agent=agent_wrapper.force_delegate_agent,
        )
    )
    agent_wrapper._runtime_pool_scope_id = effective_chat_id
    if needs_runtime_pool(
        enable_external_cli=agent_wrapper.enable_external_cli,
        agent_id=agent_wrapper.agent_id,
        force_delegate_agent=agent_wrapper.force_delegate_agent,
    ):
        await agent_wrapper._setup_external_agents(
            tools,
            mount_delegate_tool=mount_delegate_tool,
            delegate_cwd=str(workspace_root) if workspace_root else None,
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
    channel_notify_tool_loaded = False
    try:
        from app.services.agent.outbound_notify.factory_wiring import (
            append_channel_notify_tool,
        )

        target_count = append_channel_notify_tool(
            agent_wrapper.notify_targets,
            tools,
            allowed_roots=agent_wrapper.declared_allowed_roots,
        )
        if target_count:
            channel_notify_tool_loaded = True
            logger.info(
                "Loaded channel_notify_tool (%d targets) [Turn1]",
                target_count,
            )
    except Exception as e:
        logger.warning("channel_notify_tool load failed (degraded): %s", e)

    # 5. Create sandbox executor
    from myrm_agent_harness.toolkits.code_execution.factory import create_executor

    exec_config = build_execution_config(agent_wrapper.code_execution_allow_network)
    executor = create_executor(exec_config)
    if workspace_root:
        executor.bind_workspace(workspace_root)

    logger.info(f"创建沙箱执行器: {executor.get_executor_name()}")
    agent_wrapper._executor = executor

    # Register the workspace snapshot interceptor for WebUI main conversations.
    # ChannelExecutor already registers it via app.core.channel_bridge.agent_executor;
    # this idempotent call covers the main-conversation path so FileSnapshotPanel
    # shows turn-level snapshots for WebUI users too.
    try:
        from myrm_agent_harness.toolkits.code_execution.interceptor import (
            set_execution_interceptor,
        )

        from app.services.checkpoint.snapshot_service import (
            get_snapshot_interceptor,
        )

        set_execution_interceptor(get_snapshot_interceptor())
    except Exception as e:
        logger.warning("Failed to register snapshot interceptor: %s", e)

    from myrm_agent_harness.runtime.context.offload import (
        create_compress_offload_callback,
        create_context_snapshot_callback,
    )

    from app.platform_utils import get_quota_manager

    quota_manager = await get_quota_manager()
    compress_offload_cb = create_compress_offload_callback(
        executor,
        quota_checker=quota_manager,
    )
    context_snapshot_cb = create_context_snapshot_callback(
        executor,
        quota_checker=quota_manager,
    )

    from app.ai_agents.extensions import (
        ArchiveCheckpointMemoryExtension,
        PreCompactMemoryExtension,
        SecurityPolicyExtension,
        SubagentManagementExtension,
        ZeroCostMemoryExtension,
    )

    extraction_preset = agent_wrapper.memory_extraction_preset
    if extraction_preset == "auto":
        from myrm_agent_harness.toolkits.memory.strategies.extraction_domain import (
            auto_detect_preset,
        )

        extraction_preset = auto_detect_preset(
            agent_wrapper.user_instructions or ""
        ).value

    memory_ext = ZeroCostMemoryExtension(
        enable_memory_auto_extraction=agent_wrapper.enable_memory_auto_extraction,
        is_subagent=getattr(agent_wrapper, "is_subagent", False),
        channel_name=agent_wrapper.channel_name,
        memory_manager=memory_manager,
        effective_chat_id=effective_chat_id,
        extractor_llm=agent_wrapper._lite_llm or llm,
        memory_extraction_preset=extraction_preset,
    )
    compress_eviction_cb = memory_ext.build_eviction_callback()

    pre_compact_ext = PreCompactMemoryExtension(
        enabled=agent_wrapper.enable_memory,
        is_subagent=getattr(agent_wrapper, "is_subagent", False),
        channel_name=agent_wrapper.channel_name,
        memory_manager=memory_manager,
        effective_chat_id=effective_chat_id,
    )
    pre_compact_cb = pre_compact_ext.build_pre_compact_callback()

    archive_checkpoint_ext = ArchiveCheckpointMemoryExtension(
        enabled=agent_wrapper.enable_memory and not agent_wrapper.incognito_mode,
        is_subagent=getattr(agent_wrapper, "is_subagent", False),
        channel_name=agent_wrapper.channel_name,
        memory_manager=memory_manager,
        effective_chat_id=effective_chat_id,
    )
    archive_checkpoint_store = archive_checkpoint_ext.build_archive_checkpoint_store()
    archive_checkpoint_notifier = (
        archive_checkpoint_ext.build_archive_checkpoint_notifier()
    )

    # 6. Create middlewares
    from myrm_agent_harness.agent.middlewares import (
        FilesystemFileSearchMiddleware,
        PlanConfirmMiddleware,
        RateLimitMiddleware,
    )
    from myrm_agent_harness.agent.middlewares.guardrails import (
        GuardrailMiddleware,
        SkillBoundaryProvider,
    )
    from myrm_agent_harness.api.hooks import (
        set_permission_invalidation_callback,
    )

    from app.services.skills.permission_service import (
        clear_permission_cache,
        create_async_permission_checker,
    )

    permission_checker = await create_async_permission_checker()

    guardrail_providers = [
        SkillBoundaryProvider(permission_checker=permission_checker),
    ]

    try:
        from app.services.security.tenant_guardrail import TenantPolicyProvider

        guardrail_providers.append(TenantPolicyProvider())
    except ImportError:
        pass

    guardrail_middleware = GuardrailMiddleware(
        providers=guardrail_providers,
        agent_id=agent_wrapper.agent_id,
        session_id=effective_chat_id,
    )

    set_permission_invalidation_callback(clear_permission_cache)

    logger.info(
        f"Skill permission checker enabled for user: {'sandbox'}, real-time revocation registered"
    )

    time_decay_half_life_days = 90.0
    if agent_wrapper.memory_decay_profile == "permanent":
        time_decay_half_life_days = 3650.0
    elif agent_wrapper.memory_decay_profile == "fast":
        time_decay_half_life_days = 7.0

    middlewares_list = [
        RateLimitMiddleware(warning_threshold_pct=0.8, debounce_seconds=300.0),
        PlanConfirmMiddleware(),
        user_instructions_middleware,
        workspace_rules_middleware,
        project_roadmap_middleware,
        memory_context_middleware,
        widget_capability_middleware,
        citation_rules_middleware,
        tool_selection_middleware,
        create_context_pipeline_middleware(
            llm=agent_wrapper._lite_llm,
            summarizer_llm=agent_wrapper._lite_llm,
            tail_budget_ratio=agent_wrapper.tail_budget_ratio,
            on_summary_persist=make_summary_persist_with_wiki_archive(
                enable_wiki=agent_wrapper.enable_wiki,
                wiki_archive_llm=(
                    agent_wrapper._lite_llm if agent_wrapper.enable_wiki else None
                ),
            ),
            on_compress_offload=compress_offload_cb,
            on_compress_eviction=compress_eviction_cb,
            on_context_snapshot=context_snapshot_cb,
            on_pre_compact=pre_compact_cb,
            archive_checkpoint_store=archive_checkpoint_store,
            on_archive_checkpoint=archive_checkpoint_notifier,
            session_notes_llm=agent_wrapper._lite_llm,
            on_notes_persist=make_notes_persist(effective_chat_id),
            on_notes_load=make_notes_load(effective_chat_id),
            budget_pressure_fn=_get_budget_pressure_fn(),
            time_decay_half_life_days=time_decay_half_life_days,
            cache_ttl_prune_config=resolve_cache_ttl_prune_policy(
                agent_wrapper.model_cfg.model
            ).config,
            file_content_reader=read_uploaded_media_file_content,
        ),
    ]

    from app.services.agent.stream_session.moa_overlay_setup import (
        build_moa_overlay_middleware,
    )

    moa_middleware = await build_moa_overlay_middleware(
        agent_wrapper.engine_params,
        unattended=bool(getattr(agent_wrapper, "unattended_mode", False)),
    )
    if moa_middleware is not None:
        middlewares_list.append(moa_middleware)
        agent_wrapper.moa_overlay_skip_reason = None
        logger.info(
            "MoA advisor overlay middleware mounted (chat_id=%s)", effective_chat_id
        )
    else:
        from app.services.agent.stream_session.moa_overlay_setup import (
            resolve_moa_overlay_skip_reason,
        )

        agent_wrapper.moa_overlay_skip_reason = await resolve_moa_overlay_skip_reason(
            agent_wrapper.engine_params,
        )

    if guardrail_middleware:
        middlewares_list.insert(0, guardrail_middleware)

    if workspace_root:
        middlewares_list.append(
            FilesystemFileSearchMiddleware(root_path=workspace_root)
        )

    middlewares = cast(list[AgentMiddleware], middlewares_list)

    # 7. Checkpointer
    from app.platform_utils import get_checkpointer

    checkpointer = get_checkpointer()
    logger.info(f"使用 checkpointer: {type(checkpointer).__name__}")

    # 7.5 Auto-tune for small models (zero-config compatibility mode)
    _apply_small_model_tuning(agent_wrapper)

    # 8. System prompt (core + CLI tool awareness)
    system_prompt = get_core_system_prompt(
        mode=agent_wrapper.prompt_mode,
        enable_answer_tool=agent_wrapper.enable_answer_tool,
        enable_memory=agent_wrapper.enable_memory and not agent_wrapper.incognito_mode,
    )

    if (
        agent_wrapper.prompt_mode == "search"
        and getattr(agent_wrapper, "search_depth", "normal") == "deep"
    ):
        from app.ai_agents.prompts.general_agent_prompt import SEARCH_DEEP_SUFFIX

        system_prompt += SEARCH_DEEP_SUFFIX

    if getattr(agent_wrapper, "unattended_mode", False):
        system_prompt += (
            "\n\n[Unattended Mode] You are running without human supervision. "
            "Do not ask the user for clarification or approval. "
            "Make reasonable decisions independently and proceed to completion."
        )

    from app.ai_agents.general_agent.kanban_tool_mode import resolve_kanban_tool_mode

    if (
        resolve_kanban_tool_mode(
            kanban_tool_mode=getattr(agent_wrapper, "kanban_tool_mode", None),
            kanban_current_task_id=getattr(
                agent_wrapper, "kanban_current_task_id", None
            ),
        )
        == "worker"
    ):
        from myrm_agent_harness.toolkits.kanban import get_worker_lifecycle_guidance

        system_prompt += get_worker_lifecycle_guidance(
            zombie_timeout_seconds=getattr(
                agent_wrapper, "kanban_zombie_timeout_seconds", 120
            ),
            max_runtime_seconds=getattr(
                agent_wrapper, "kanban_max_runtime_seconds", None
            ),
        )

    if _should_setup_computer_use_tools(agent_wrapper.enable_computer_use):
        from app.ai_agents.prompts.shared_rules import DESKTOP_CONTROL_RULES

        system_prompt += DESKTOP_CONTROL_RULES

    if executor is not None:
        try:
            from myrm_agent_harness.toolkits.code_execution.tool_discovery import (
                get_cli_tools_context,
            )

            cli_ctx = get_cli_tools_context()
            if cli_ctx:
                system_prompt += cli_ctx
        except Exception as e:
            logger.warning("CLI tool discovery failed (degraded): %s", e)

    if channel_notify_tool_loaded:
        from app.services.agent.outbound_notify.types import (
            CHANNEL_NOTIFY_SYSTEM_APPENDIX,
        )

        system_prompt += CHANNEL_NOTIFY_SYSTEM_APPENDIX

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
        resolved_env_map = await resolve_skill_env_map(
            skill_backend, _user_skill_cfg.skill_env_vars
        )

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

    workspace_root = (
        agent_wrapper.declared_allowed_roots[0]
        if agent_wrapper.declared_allowed_roots
        else None
    )

    if workspace_root and agent_wrapper.mcp_config:
        from app.ai_agents.general_agent.mcp_vault_handler import (
            build_mcp_vault_handler,
        )

        vault_handler = build_mcp_vault_handler(workspace_root)
        agent_wrapper.mcp_config = [
            cfg.model_copy(update={"oversized_result_handler": vault_handler})
            for cfg in agent_wrapper.mcp_config
        ]

    if agent_wrapper.mcp_config:
        from app.services.agent.backends.mcp_elicitation_handler import (
            build_mcp_elicitation_handler,
        )

        elicitation_handler = build_mcp_elicitation_handler(
            agent_id=agent_wrapper.agent_id,
            chat_id=effective_chat_id,
        )
        agent_wrapper.mcp_config = [
            cfg.model_copy(update={"elicitation_handler": elicitation_handler})
            for cfg in agent_wrapper.mcp_config
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

    active_tool_groups = derive_active_tool_groups(
        agent_wrapper, enable_planning=enable_planning
    )

    from app.services.agent.mcp_surface_mode import normalize_mcp_surface_engine_params

    mcp_surface_mode, normalized_engine_params = normalize_mcp_surface_engine_params(
        agent_wrapper.engine_params
    )

    spec = AgentRuntimeSpec(
        agent_id=agent_wrapper.agent_id,
        name=agent_wrapper.agent_id or "default",
        system_prompt=system_prompt,
        allowed_tools=allowed_tool_names,
        tool_groups=active_tool_groups,
        skill_ids=runtime_skill_ids,
        skill_configs=agent_wrapper.skill_configs,
        mcp_servers=agent_wrapper.mcp_config or [],
        openapi_services=agent_wrapper.openapi_services or [],
        memory_namespaces=memory_namespaces,
        workspace_binding=workspace_binding,
        max_iterations=agent_wrapper.max_iterations or 100,
        unattended=getattr(agent_wrapper, "unattended_mode", False),
        locale=agent_wrapper.locale,
        channel_name=agent_wrapper.channel_name,
        security_config=None,
        engine_params=normalized_engine_params,
        mcp_surface_mode=mcp_surface_mode,
    )
    # Build similarity checker (for anti-entropy dedup in skill_manage_tool + growth_lifecycle)
    sim_checker = None
    if skill_backend and agent_wrapper.embedding_config:
        try:
            from myrm_agent_harness.agent.meta_tools.skills.search.hybrid_engine import (
                HybridSkillSearchEngine,
            )

            from app.services.skills.similarity_checker import HybridSimilarityChecker

            all_backend_skills = await skill_backend.list_skills()
            if all_backend_skills:
                engine = HybridSkillSearchEngine(
                    all_backend_skills, agent_wrapper.embedding_config
                )
                sim_checker = HybridSimilarityChecker(engine)
                logger.info(
                    "Skill similarity checker enabled (%d skills indexed)",
                    len(all_backend_skills),
                )
        except Exception as e:
            logger.warning("Failed to build similarity checker (non-blocking): %s", e)

    # Also inject into growth_lifecycle for backend auto-review dedup
    from app.services.skills.growth.lifecycle import set_similarity_checker

    set_similarity_checker(sim_checker)

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

    from app.core.subagents.resolver import SubagentModelResolver

    subagent_model_resolver = SubagentModelResolver(
        providers_dict=agent_wrapper.providers_dict,
        task_description="",  # Will be populated by the builder per task
        standard_model_cfg=agent_wrapper.model_cfg,
        light_model_cfg=agent_wrapper.light_model_cfg,
        reasoning_model_cfg=agent_wrapper.reasoning_model_cfg,
    )

    # PTC dependency auto-injection: MCP/PTC skills require bash + file_read
    from app.services.agent.tool_mount import apply_ptc_meta_mount

    effective_file_access, effective_enable_shell = apply_ptc_meta_mount(
        agent_wrapper.file_access_mode,
        agent_wrapper.enable_shell_tools,
        has_mcp=bool(agent_wrapper.mcp_config),
    )

    mount_skill_market = getattr(agent_wrapper, "enable_skill_market", False)
    mount_skill_manage = getattr(
        agent_wrapper, "enable_skill_manage", False
    ) or getattr(agent_wrapper, "force_skill_manage", False)

    if mount_skill_market:
        agent_wrapper._setup_skill_market_tool(tools, market_service)
    if mount_skill_manage:
        agent_wrapper._setup_skill_manage_tool(
            tools,
            skill_creation_service,
            skill_backend,
            sim_checker,
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
        enable_memory_auto_extraction=agent_wrapper.enable_memory
        and agent_wrapper.enable_memory_auto_extraction,
        extraction_llm=agent_wrapper._lite_llm,
        middlewares=middlewares,
        tools=tools,
        collect_artifacts=True,
        fallback_llm=fallback_llm,
        safety_fallback_llm=safety_fallback_llm,
        escalation_target_llm=escalation_target_llm,
        embedding_config=agent_wrapper.embedding_config,
        checkpointer=checkpointer,
        privacy_routing_config=privacy_routing_cfg,
        event_log_backend=agent_wrapper.event_log_backend,
        trusted_skill_ids=trusted_ids,
        skill_env_map=resolved_env_map,
        state_manager=state_manager,
        default_skill_instances=(
            default_skill_instances if default_skill_instances else None
        ),
        global_env=global_env,
        on_skill_review_ready=make_skill_review_callback(),
        on_session_cleanup=_build_session_cleanup_callback(
            agent_wrapper, user_id or "default"
        ),
        on_loaded_skills_persist=(
            None
            if agent_wrapper.incognito_mode
            else make_loaded_skills_persist_callback()
        ),
        extraction_lifecycle_observer=(
            make_extraction_lifecycle_observer(effective_chat_id)
            if agent_wrapper.enable_memory
            and agent_wrapper.enable_memory_auto_extraction
            and not agent_wrapper.incognito_mode
            else None
        ),
        wiki_base_dir=(
            agent_wrapper._resolve_wiki_base_dir()
            if agent_wrapper.enable_wiki
            else None
        ),
        wiki_public_dirs=(
            agent_wrapper._resolve_wiki_public_dirs()
            if agent_wrapper.enable_wiki
            else None
        ),
        wiki_search_fn=(
            agent_wrapper._build_wiki_search_fn() if agent_wrapper.enable_wiki else None
        ),
        wiki_scope_id=agent_wrapper.agent_id,
        similarity_checker=sim_checker,
        model_resolver=subagent_model_resolver,
        file_access_mode=effective_file_access,
        enable_shell_tools=effective_enable_shell,
        enable_answer_tool=agent_wrapper.enable_answer_tool,
        enable_planning=enable_planning,
        task_workspace_root=workspace_root,
        library_skill_names=library_skill_names,
    )

    # 9.5 Register extensions (subagent tools, security, memory)
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
    extensions: list[AgentExtension] = [
        memory_ext,
        pre_compact_ext,
        archive_checkpoint_ext,
        security_ext,
    ]

    if _should_enable_subagent_tools():
        logger.warning(
            "Subagent tools are enabled. Adding SubagentManagementExtension."
        )
        subagent_ext = SubagentManagementExtension(
            jit_subagents=agent_wrapper.jit_subagents,
            subagent_ids=agent_wrapper.subagent_ids or [],
        )
        extensions.insert(-1, subagent_ext)
    else:
        logger.warning(
            "Subagent tools are NOT enabled. Skipping SubagentManagementExtension."
        )

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


async def _try_inject_mcp_oauth(cfg: "MCPConfig") -> "MCPConfig":
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
    store: object,
    *,
    preferred_board_id: str | None,
) -> str | None:
    """Pick default board for kanban tools: preferred id when valid, else newest when unset."""
    boards = await store.list_boards()  # type: ignore[attr-defined]
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
    tools: list,
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
        attach_task_file=(
            create_kanban_attach_handler(store) if mode == "worker" else None
        ),
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


def _build_session_cleanup_callback(
    agent_wrapper: "GeneralAgent",
    user_id: str,
) -> "Callable[[Sequence[dict[str, str]], str | None], Awaitable[None]] | None":
    """Build a composite session cleanup callback (follow-up extraction + correction propagation)."""
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

    from .callbacks import (
        make_commitment_extraction_callback,
        make_correction_propagation_callback,
    )
    from .frustration_routing import make_frustration_skill_routing_callback

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
        ),
        make_frustration_skill_routing_callback(
            agent_id=agent_id,
            profile_skill_ids=list(agent_wrapper.skill_ids or []),
            llm_func=llm_func,
        ),
    ]

    async def _composite(
        messages: "Sequence[dict[str, str]]", chat_id: str | None
    ) -> None:
        await run_session_post_process(tasks, messages, chat_id)

    return _composite


def _apply_small_model_tuning(agent_wrapper: "GeneralAgent") -> None:
    """Auto-tune agent parameters when a small/weak model is detected.

    Only applies when prompt_mode is still at default ("full") and user
    has not explicitly configured engine_params overrides.
    Preserves all user-explicit settings — auto-tuning is purely additive.
    """
    if agent_wrapper.prompt_mode != "full":
        return

    from myrm_agent_harness.core.config import ModelTier, infer_model_tier

    custom_def = getattr(agent_wrapper.model_cfg, "custom_model_def", None)
    max_ctx = getattr(agent_wrapper.model_cfg, "max_context_tokens", None)

    tier = infer_model_tier(
        model_name=agent_wrapper.model_cfg.model,
        custom_model_def=custom_def,
        max_context_tokens=max_ctx,
    )

    if tier == ModelTier.STRONG:
        return

    engine = agent_wrapper.engine_params or {}

    if tier == ModelTier.WEAK:
        agent_wrapper.prompt_mode = "lean"
        if engine.get("enable_parallel_tool_calls") is None:
            engine["enable_parallel_tool_calls"] = False
        if engine.get("compress_start_ratio") is None:
            engine["compress_start_ratio"] = 0.30
        if engine.get("max_tool_calls") is None:
            engine["max_tool_calls"] = 10
        logger.info(
            "Small model compatibility: tier=%s, model=%s → prompt_mode=lean, parallel=False, compress_ratio=0.30",
            tier,
            agent_wrapper.model_cfg.model,
        )
    elif tier == ModelTier.MEDIUM:
        agent_wrapper.prompt_mode = "lean"
        if engine.get("compress_start_ratio") is None:
            engine["compress_start_ratio"] = 0.50
        logger.info(
            "Medium model tuning: tier=%s, model=%s → prompt_mode=lean, compress_ratio=0.50",
            tier,
            agent_wrapper.model_cfg.model,
        )

    agent_wrapper.engine_params = engine
