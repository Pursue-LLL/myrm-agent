"""Stream Pipeline for GeneralAgent.

[INPUT]
- app.core.utils.delivery_provenance::resolve_general_agent_pipeline_labels, apply_delivery_banner (POS: Human ingress banner + structured log labels keyed by channel_name.)
- app.ai_agents.general_agent.agent_middlewares.tool_selection_middleware::reset_answer_tool_convergence (POS: 工具约束中间件的收敛状态重置)

[OUTPUT]
- execute_stream_pipeline: Primary LangGraph execution loop for streamed general agent runs.
- POOLED path: execution_cache acquire/apply + guard_turn per chat scope.
"""

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING
from uuid import uuid4

from app.ai_agents.general_agent.checkpoint_helpers import (
    mark_thread_completed,
    mark_thread_failed,
    update_checkpoint_counters,
)
from app.core.utils.delivery_provenance import (
    apply_delivery_banner,
    resolve_general_agent_pipeline_labels,
)

if TYPE_CHECKING:
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
    from myrm_agent_harness.utils.runtime.steering import SteeringToken

    from app.ai_agents.general_agent.agent import GeneralAgent

logger = logging.getLogger(__name__)


def _force_external_delegate_denial_reason(
    agent_wrapper: "GeneralAgent",
    force_external_agent: str,
) -> str | None:
    """Return denial reason when invoke_external_agent is blocked for direct delegate."""
    from myrm_agent_harness.agent.security.config import parse_security_config
    from myrm_agent_harness.agent.security.engine import evaluate_tool_call
    from myrm_agent_harness.agent.security.types import PermissionAction

    config = parse_security_config(agent_wrapper.security_config_raw)
    if config is None:
        return "invoke_external_agent denied: security config missing"
    action, reason = evaluate_tool_call(
        "invoke_external_agent",
        {"agent": force_external_agent},
        config,
    )
    if action != PermissionAction.ALLOW:
        return reason or f"invoke_external_agent {action.value} by security policy"
    return None


async def execute_stream_pipeline(
    agent_wrapper: "GeneralAgent",
    query: object,
    chat_history: list[list[str]] | list[list[str | object]] | None = None,
    message_id: str | None = None,
    chat_id: str | None = None,
    cancel_token: "CancellationToken | None" = None,
    steering_token: "SteeringToken | None" = None,
    timezone: str | None = None,
    force_external_agent: str | None = None,
    extra_context: dict[str, object] | None = None,
) -> AsyncGenerator[dict[str, object], None]:
    """Process query and stream results.

    Args:
        force_external_agent: If set, bypass the LLM and route the query
            directly to the named external agent via RuntimePool.
    """
    message_id = message_id or str(uuid4())
    ch_label, ingress_label = resolve_general_agent_pipeline_labels(agent_wrapper.channel_name)
    logger.info(
        "general_agent_delivery_labels channel_label=%s ingress_label=%s message_id=%s chat_id=%s",
        ch_label,
        ingress_label,
        message_id,
        chat_id or "",
    )
    query = apply_delivery_banner(query, channel_label=ch_label, ingress_label=ingress_label)
    query_preview = query if isinstance(query, str) else "[multimodal]"

    if chat_id:
        agent_wrapper._runtime_pool_scope_id = chat_id

    if force_external_agent:
        deny_reason = _force_external_delegate_denial_reason(
            agent_wrapper,
            force_external_agent,
        )
        if deny_reason:
            logger.warning(
                "Direct external delegate blocked by security policy: agent=%s reason=%s",
                force_external_agent,
                deny_reason,
            )
            yield {
                "type": "error",
                "data": f"External agent delegation denied: {deny_reason}",
            }
            return

    if force_external_agent and agent_wrapper._runtime_pool is None:
        await agent_wrapper._ensure_runtime_pool()

    if force_external_agent and agent_wrapper._runtime_pool is not None:
        if force_external_agent in agent_wrapper._runtime_pool.available_backends:
            logger.warning(
                "🔗 Direct routing to external agent: %s query='%s'",
                force_external_agent,
                query_preview,
            )
            for attempt in range(2):
                started_streaming = False
                try:
                    async for event in agent_wrapper._direct_delegate_stream(
                        force_external_agent,
                        query,
                        cancel_token=cancel_token,
                        chat_id=chat_id,
                    ):
                        started_streaming = True
                        yield event
                    return
                except Exception:
                    if started_streaming or attempt > 0:
                        logger.error(
                            "Direct delegate failed: %s",
                            force_external_agent,
                            exc_info=True,
                        )
                        yield {
                            "type": "error",
                            "data": f"External agent '{force_external_agent}' execution failed",
                        }
                        return
                    logger.warning(
                        "Direct delegate connection failed, retrying: %s",
                        force_external_agent,
                    )
            return

    if agent_wrapper.jit_subagents:
        roster_lines = [
            "\n<Available_Team_Roster>",
            "You have access to the following specialized subagents. You can delegate tasks to them using the `delegate_task` tool:",
        ]
        for type_id, cfg_data in agent_wrapper.jit_subagents.items():
            if isinstance(cfg_data, dict):
                label = cfg_data.get("display_name", type_id)
                desc = cfg_data.get("description") or str(cfg_data.get("system_prompt", ""))[:80]
                roster_lines.append(f"  - '{type_id}': [{label}] {desc}")
        roster_lines.append("</Available_Team_Roster>")
        roster_xml = "\n".join(roster_lines)

        if isinstance(query, str):
            query = f"{query}\n{roster_xml}"
        elif isinstance(query, list):
            query = list(query)
            query.append({"type": "text", "text": roster_xml})

    logger.info(f"Agent模式启动: 查询='{query_preview}'")

    from app.config.settings import settings
    from app.platform_utils import get_artifact_processor

    effective_chat_id = chat_id or agent_wrapper.chat_id or "default"
    agent_wrapper._current_chat_id = effective_chat_id

    from app.services.agent.execution_cache import (
        ExecutionMode,
        apply_built_unit,
        build_execution_scope_key,
        capture_built_unit,
        compute_execution_fingerprint,
        get_execution_cache,
        resolve_execution_mode,
    )

    execution_mode = resolve_execution_mode(extra_context)
    scope_key = build_execution_scope_key(effective_chat_id, agent_wrapper.agent_id)
    execution_cache = get_execution_cache()
    use_execution_pool = execution_mode == ExecutionMode.POOLED and scope_key is not None

    async def _core_stream() -> AsyncGenerator[dict[str, object], None]:
        if agent_wrapper.agent is None:
            from .factory import build_general_agent

            user_id = extra_context.get("user_id") if extra_context else None
            if use_execution_pool:
                assert scope_key is not None
                fingerprint = compute_execution_fingerprint(agent_wrapper)

                async def build_unit():
                    skill_agent = await build_general_agent(
                        agent_wrapper,
                        effective_chat_id,
                        user_id=user_id,
                    )
                    return capture_built_unit(agent_wrapper, skill_agent)

                from app.services.agent.execution_cache.prewarm.coordinator import (
                    get_turn_prewarm_coordinator,
                )

                unit = await get_turn_prewarm_coordinator().coalesced_acquire(
                    scope_key,
                    fingerprint,
                    build_unit,
                )
                apply_built_unit(agent_wrapper, unit)
                if isinstance(extra_context, dict):
                    if extra_context.get("turn_prewarm_still_warming"):
                        yield {
                            "type": "status",
                            "messageId": message_id,
                            "step_key": "turn_prewarm_agent_clear",
                            "status": "success",
                        }
                    brief_status = extra_context.get("memory_brief_status")
                    if isinstance(brief_status, dict) and brief_status.get("reason") == "brief_pending":
                        yield {
                            "type": "status",
                            "messageId": message_id,
                            "step_key": "turn_prewarm_memory_clear",
                            "status": "success",
                        }
            else:
                agent_wrapper.agent = await build_general_agent(
                    agent_wrapper,
                    effective_chat_id,
                    user_id=user_id,
                )

        assert agent_wrapper.agent is not None

        from app.services.agent.stream_session.moa_overlay_setup import (
            MOA_OVERLAY_SKIP_NO_REFERENCE_CONFIGS,
            MOA_OVERLAY_SKIP_NO_REFERENCE_LLMS,
            resolve_moa_overlay_models,
        )

        overlay_cfg, ref_cfgs = await resolve_moa_overlay_models(agent_wrapper.engine_params)
        moa_skip_reason: str | None = None
        if overlay_cfg is not None:
            if not ref_cfgs:
                moa_skip_reason = MOA_OVERLAY_SKIP_NO_REFERENCE_CONFIGS
            elif agent_wrapper.moa_overlay_skip_reason == MOA_OVERLAY_SKIP_NO_REFERENCE_LLMS:
                moa_skip_reason = MOA_OVERLAY_SKIP_NO_REFERENCE_LLMS
        if moa_skip_reason:
            yield {
                "type": "status",
                "messageId": message_id,
                "step_key": "moa_overlay_skipped",
                "status": "warning",
                "data": {"reason": moa_skip_reason},
            }

        from app.ai_agents.extensions.security_policy_extension import (
            refresh_wrapper_security_config,
            sync_wrapper_security_from_store,
        )

        if agent_wrapper.agent_id:
            from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

            resolved_profile = await get_agent_profile_resolver().resolve(agent_wrapper.agent_id)
            if resolved_profile is not None and resolved_profile.security_overrides:
                agent_wrapper.agent_security_raw = dict(resolved_profile.security_overrides)

        await sync_wrapper_security_from_store(agent_wrapper)
        refresh_wrapper_security_config(agent_wrapper)
        runtime_sec = agent_wrapper.agent.config.security_config
        if runtime_sec is None:
            raise RuntimeError(f"security_config is None after refresh (agent_id={agent_wrapper.agent_id})")
        logger.info(
            "stream_security_snapshot agent=%s yolo=%s auto_mode=%s",
            agent_wrapper.agent_id,
            runtime_sec.yolo_mode_enabled,
            runtime_sec.auto_mode_enabled,
        )
        from myrm_agent_harness.api.hooks import set_security_config

        set_security_config(runtime_sec)
        context = agent_wrapper._build_runtime_context(
            query=query,
            chat_history=chat_history,
            effective_chat_id=effective_chat_id,
        )
        if extra_context:
            context.update(extra_context)

        # Inject goal terminal callback for learnings extraction and queue advancement
        if context.get("goal_provider"):
            from app.ai_agents.general_agent.goal_learnings import (
                build_goal_terminal_callback,
                build_loop_restart_callback,
                retrieve_relevant_learnings,
            )

            memory_manager = agent_wrapper.agent.memory_manager
            context["on_goal_terminal"] = build_goal_terminal_callback(
                memory_manager=memory_manager,
                llm=agent_wrapper.agent._extraction_llm or agent_wrapper.agent.llm,
                deep_scan=agent_wrapper.privacy_deep_scan,
            )
            context["on_loop_restart"] = build_loop_restart_callback()

            # Enrich active goal with relevant historical learnings
            goal_provider = context["goal_provider"]
            active_goal = await goal_provider.get_active_goal(effective_chat_id)
            if active_goal and memory_manager is not None and not active_goal.metadata.get("relevant_learnings"):
                learnings = await retrieve_relevant_learnings(
                    memory_manager,
                    active_goal.objective,
                )
                if learnings:
                    active_goal.metadata["relevant_learnings"] = learnings

        if agent_wrapper.enable_browser and agent_wrapper._browser_session and agent_wrapper._session_vault:
            from myrm_agent_harness.toolkits.browser import BrowserCheckpointHelper

            expected_thread_id = agent_wrapper.approval_session_key or str(context["session_id"])
            if agent_wrapper._current_thread_id and agent_wrapper._current_thread_id != expected_thread_id:
                logger.warning(
                    f"Thread ID mismatch: init={agent_wrapper._current_thread_id}, runtime={expected_thread_id}. "
                    "Using init value (BrowserSession already bound)."
                )
            elif not agent_wrapper._current_thread_id:
                agent_wrapper._current_thread_id = expected_thread_id

            checkpoint_helper = BrowserCheckpointHelper(agent_wrapper._browser_session, agent_wrapper._session_vault)
            agent_wrapper._checkpoint_helper = checkpoint_helper
            checkpoint_context = checkpoint_helper.get_initial_context()
            context.update(checkpoint_context)
            logger.info(f"Checkpoint: initialized for thread_id={agent_wrapper._current_thread_id}")

        artifact_processor = get_artifact_processor(
            user_id="sandbox",
            chat_id=effective_chat_id,
            api_prefix=settings.api_prefix,
        )
        agent_wrapper.agent.on_artifacts_ready = artifact_processor.process_artifacts_ready

        from myrm_agent_harness.backends.skills.decorators.version_aware import (
            session_id_var,
        )
        from myrm_agent_harness.backends.skills.protocols import (
            resolved_skill_versions_var,
        )

        from app.ai_agents.general_agent.agent_middlewares.tool_selection_middleware import (
            reset_answer_tool_convergence,
        )

        reset_answer_tool_convergence()
        token = session_id_var.set(str(context["session_id"]))
        version_token = resolved_skill_versions_var.set({})

        from app.services.infra.sleep_inhibitor import SleepInhibitor

        task_completed = False
        async with SleepInhibitor.hold():
            from app.services.web_fetch.binding import open_web_fetch_escalation_context

            async with open_web_fetch_escalation_context(
                session_id=str(context["session_id"]),
                browser_source=getattr(agent_wrapper, "browser_source", None),
            ):
                try:
                    async for event in agent_wrapper.agent.run(
                        query,
                        chat_history=chat_history,
                        message_id=message_id,
                        context=context,
                        cancel_token=cancel_token,
                        steering_token=steering_token,
                        timezone=timezone,
                    ):
                        if cancel_token and cancel_token.is_cancelled:
                            logger.warning(f"🛑 GeneralAgent 被取消: chat_id={message_id}")
                            break

                        if agent_wrapper._checkpoint_helper:
                            should_update = await update_checkpoint_counters(agent_wrapper._checkpoint_helper, event)
                            if should_update:
                                await agent_wrapper._checkpoint_helper.update_context(context)

                        yield event

                    task_completed = True
                except Exception:
                    if agent_wrapper._checkpoint_helper and agent_wrapper._current_thread_id:
                        await mark_thread_failed(agent_wrapper._current_thread_id)
                    raise
                finally:
                    for _var, _tok in (
                        (session_id_var, token),
                        (resolved_skill_versions_var, version_token),
                    ):
                        try:
                            _var.reset(_tok)
                        except ValueError:
                            pass
                    if task_completed and agent_wrapper._checkpoint_helper and agent_wrapper._current_thread_id:
                        await mark_thread_completed(agent_wrapper._current_thread_id)

    if use_execution_pool:
        assert scope_key is not None
        async with execution_cache.guard_turn(scope_key):
            async for pipeline_event in _core_stream():
                yield pipeline_event
    else:
        async for pipeline_event in _core_stream():
            yield pipeline_event
