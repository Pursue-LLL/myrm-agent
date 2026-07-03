"""Stream Pipeline for GeneralAgent.

This module extracts the complex process_stream logic from GeneralAgent,
keeping the facade class clean.

[INPUT]
- app.core.utils.delivery_provenance::resolve_general_agent_pipeline_labels, apply_delivery_banner (POS: Human ingress banner + structured log labels keyed by channel_name.)
- app.ai_agents.general_agent.agent_middlewares.tool_selection_middleware::reset_answer_tool_convergence (POS: 工具约束中间件的收敛状态重置)

[OUTPUT]
- execute_stream_pipeline: Primary LangGraph execution loop for streamed general agent runs.
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


async def execute_stream_pipeline(
    agent_wrapper: "GeneralAgent",
    query: object,
    chat_history: list[list[str]] | list[list[str | object]] | None = None,
    message_id: str | None = None,
    chat_id: str | None = None,
    cancel_token: "CancellationToken | None" = None,
    steering_token: "SteeringToken | None" = None,
    timezone: str | None = None,
    force_delegate_agent: str | None = None,
    extra_context: dict[str, object] | None = None,
) -> AsyncGenerator[dict[str, object], None]:
    """Process query and stream results.

    Args:
        force_delegate_agent: If set, bypass the LLM and route the query
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

    if force_delegate_agent and agent_wrapper._runtime_pool is None:
        await agent_wrapper._ensure_runtime_pool()

    if force_delegate_agent and agent_wrapper._runtime_pool is not None:
        if force_delegate_agent in agent_wrapper._runtime_pool.available_backends:
            logger.warning(
                "🔗 Direct routing to external agent: %s query='%s'",
                force_delegate_agent,
                query_preview,
            )
            for attempt in range(2):
                started_streaming = False
                try:
                    async for event in agent_wrapper._direct_delegate_stream(
                        force_delegate_agent,
                        query,
                        cancel_token=cancel_token,
                        chat_id=chat_id,
                    ):
                        started_streaming = True
                        yield event
                    return
                except Exception:
                    if started_streaming or attempt > 0:
                        logger.error("Direct delegate failed: %s", force_delegate_agent, exc_info=True)
                        yield {
                            "type": "error",
                            "data": f"External agent '{force_delegate_agent}' execution failed",
                        }
                        return
                    logger.warning("Direct delegate connection failed, retrying: %s", force_delegate_agent)
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

    if agent_wrapper.agent is None:
        from .factory import build_general_agent

        user_id = extra_context.get("user_id") if extra_context else None
        agent_wrapper.agent = await build_general_agent(agent_wrapper, effective_chat_id, user_id=user_id)
    else:
        await agent_wrapper._check_skill_config_staleness(effective_chat_id)

    assert agent_wrapper.agent is not None
    artifact_processor = get_artifact_processor(
        user_id="sandbox",
        chat_id=effective_chat_id,
        api_prefix=settings.api_prefix,
    )
    agent_wrapper.agent.on_artifacts_ready = artifact_processor.process_artifacts_ready

    context = agent_wrapper._build_runtime_context(
        query=query,
        chat_history=chat_history,
        effective_chat_id=effective_chat_id,
    )
    if extra_context:
        context.update(extra_context)

    # Inject goal terminal callback for learnings extraction
    if context.get("goal_provider") and agent_wrapper.agent.memory_manager:
        from app.ai_agents.general_agent.goal_learnings import (
            build_goal_terminal_callback,
            build_loop_restart_callback,
            retrieve_relevant_learnings,
        )

        context["on_goal_terminal"] = build_goal_terminal_callback(
            memory_manager=agent_wrapper.agent.memory_manager,
            llm=agent_wrapper.agent._extraction_llm or agent_wrapper.agent.llm,
        )
        context["on_loop_restart"] = build_loop_restart_callback()

        # Enrich active goal with relevant historical learnings
        goal_provider = context["goal_provider"]
        active_goal = await goal_provider.get_active_goal(effective_chat_id)
        if active_goal and not active_goal.metadata.get("relevant_learnings"):
            learnings = await retrieve_relevant_learnings(
                agent_wrapper.agent.memory_manager,
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

    from myrm_agent_harness.backends.skills.decorators.version_aware import session_id_var
    from myrm_agent_harness.backends.skills.protocols import resolved_skill_versions_var

    from app.ai_agents.general_agent.agent_middlewares.tool_selection_middleware import (
        reset_answer_tool_convergence,
    )

    reset_answer_tool_convergence()
    token = session_id_var.set(str(context["session_id"]))
    version_token = resolved_skill_versions_var.set({})

    from app.services.infra.sleep_inhibitor import SleepInhibitor

    task_completed = False
    async with SleepInhibitor.hold():
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
            try:
                session_id_var.reset(token)
            except ValueError:
                pass

            try:
                resolved_skill_versions_var.reset(version_token)
            except ValueError:
                pass

            if task_completed and agent_wrapper._checkpoint_helper and agent_wrapper._current_thread_id:
                await mark_thread_completed(agent_wrapper._current_thread_id)
