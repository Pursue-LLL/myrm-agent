"""Agent job runner — executes cron jobs through the Agent pipeline.

1. agent/context_management/PROMPT_CACHE_PRACTICE.md §2.3 Cron 场景

Reads the user's latest configs from ConfigService at execution time
(no config snapshot). Model priority: agent profile model > CronJob.model
> user's default model. No implicit fallback to arbitrary providers.

When CronJob.agent_id is set, loads the agent's full profile via
AgentProfileResolver to inject system_prompt, skills, model,
subagent_ids, security overrides, max_iterations, and memory_policy
into GeneralAgentParams — identical to Web/Channel entry points.

Session target modes:
- ISOLATED: each execution runs with a blank context (default).
- MAIN: reuses the bound web-chat session's history.
- DAILY: same-day executions share context via injected run-history;
  a fresh context starts each calendar day.  See §2.3 of
  PROMPT_CACHE_PRACTICE.md for cache-safety analysis.

For recurring jobs, a [SILENT] instruction is appended to the prompt
so the Agent can skip delivery when there's nothing actionable to report.

During execution, a ContextVar guard prevents the Agent from creating new
cron jobs (cron self-scheduling prevention).

[POS]
`agent_runner` 的执行核心：`AgentJobRunner` 编排一次 cron 任务的 Agent 执行；执行前检查、会话后置动作、事件流累积、profile 解析由同目录其余模块承担。
"""

from __future__ import annotations

import asyncio
import logging
import time

from myrm_agent_harness.api.security import is_untrusted_ingress_active
from myrm_agent_harness.toolkits.cron.cron_agent_tools import (
    enter_cron_execution_context,
    exit_cron_execution_context,
)
from myrm_agent_harness.toolkits.cron.heartbeat import HEARTBEAT_JOB_NAME
from myrm_agent_harness.toolkits.cron.situation import (
    SituationReportBuilder,
)
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    JobResult,
    ScheduleKind,
    SessionTarget,
)

from app.core.agent.run_activity import track_background_agent_run

from ..injection_scan import scan_cron_prompt
from ..research_lease import grant_run_lease, release_run_lease
from . import session
from .profile import resolve_cron_agent_profile
from .stream import (
    _consume_dynamic_workflow_stream,
    _consume_stream,
    _deterministic_failure,
    _failure_result,
    _StreamAccumulator,
    _timeout_result,
)
from .support import (
    _budget_skip_reason,
    _build_daily_context,
    _build_effective_prompt,
    _finalize_heartbeat_follow_up_delivery,
    _resolve_cron_enable_memory,
    _resolve_cron_enable_web_search,
    _resolve_effective_allowed_roots,
    resolve_trusted_desktop_keys,
)

logger = logging.getLogger(__name__)


class AgentJobRunner:
    """JobRunner implementation that delegates to AgentFactory.

    When a ``SituationReportBuilder`` is injected, heartbeat jobs receive
    a dynamically-built situation report prepended to their prompt,
    transforming blind self-checks into intelligence-driven actions.
    """

    def __init__(self, *, situation_builder: SituationReportBuilder | None = None) -> None:
        self._situation_builder = situation_builder

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        with track_background_agent_run():
            return await session.run_with_retries(job, context=context, run_once=self._run_once)

    async def _inject_situation_report(self, job: CronJob, prompt: str) -> tuple[str, bool]:
        """Build and prepend a situation report for heartbeat jobs."""
        return await session.inject_situation_report(job, prompt, self._situation_builder)

    async def _try_enqueue_if_goal_active(self, job: CronJob, *, context: str = "") -> bool:
        """Enqueue this run as a goal when the chat already has an active goal."""
        return await session.try_enqueue_if_goal_active(job, context=context)

    async def _run_once(self, job: CronJob, *, context: str = "") -> JobResult:
        if not job.prompt:
            return _deterministic_failure("agent job requires a prompt")

        from app.services.budget.enforcer import should_block_execution

        if await should_block_execution():
            if job.schedule.kind is ScheduleKind.ONCE:
                # A skipped one-shot job would be consumed as completed, so it fails instead.
                return _deterministic_failure("budget exhausted (block policy)")
            # The budget reopens on its own or through a top-up; a failure would pause the job for good.
            logger.warning("Cron agent job %s skipped: budget exhausted (block policy)", job.id)
            return JobResult(success=False, skipped=True, skip_reason=_budget_skip_reason())

        # A non-owner's message started this run, so its trigger context is a stranger's text: the run gets the
        # read-only lease and no memory or owner chat history (below), is never queued as a goal in the owner's
        # chat, where it would run unfenced, and cannot be a workflow template, whose agents the lease cannot reach.
        untrusted = is_untrusted_ingress_active()
        if untrusted and job.workflow_template_id:
            logger.info("Cron job %s: workflow template jobs do not run for a non-owner sender", job.id)
            return JobResult(success=True, skipped=True, skip_reason="untrusted-workflow")

        if job.chat_id and not untrusted:
            queued = await self._try_enqueue_if_goal_active(job, context=context)
            if queued:
                return JobResult(
                    success=True,
                    output="cron job enqueued as goal (active goal exists)",
                )

        effective_prompt = _build_effective_prompt(job)

        injection_findings = scan_cron_prompt(effective_prompt)
        if injection_findings:
            logger.warning(
                "Cron job %s: prompt injection patterns detected — %s",
                job.id,
                "; ".join(injection_findings),
            )
            return _deterministic_failure(f"prompt injection detected: {injection_findings[0]}")

        if self._situation_builder and job.name == HEARTBEAT_JOB_NAME:
            effective_prompt, has_content = await self._inject_situation_report(job, effective_prompt)
            if not has_content:
                logger.info("Heartbeat job %s: all sections empty, skipping LLM call", job.id)
                return JobResult(success=True, skipped=True, skip_reason="no-content")

        if job.session_target == SessionTarget.DAILY:
            daily_ctx = await _build_daily_context(job)
            if daily_ctx:
                effective_prompt = f"{daily_ctx}\n\n{effective_prompt}"

        if context:
            effective_prompt = f"{effective_prompt}\n\n{context}"

        cron_ctx_token = enter_cron_execution_context()
        lease_session_key: str | None = None
        # Owned here, not by the consumers, so a timeout or crash still knows whether the run used tools.
        acc = _StreamAccumulator()
        try:
            from app.ai_agents.agents import AgentFactory, GeneralAgentParams
            from app.core.channel_bridge.config_loader import load_user_configs
            from app.core.channel_bridge.config_parsers import (
                extract_fallback_model_configs,
                extract_retrieval_models,
                resolve_chat_fallback_chains_from_providers,
                resolve_vision_fallback_chain_for_agent,
            )
            from app.core.channel_bridge.model_resolver import (
                enrich_model_capabilities,
                enrich_model_context_window,
                resolve_model_config,
            )
            from app.core.security.privacy_settings import privacy_agent_params

            user_cfgs = await load_user_configs()

            embedding_cfg, reranker_cfg = extract_retrieval_models(user_cfgs.retrieval_dict)
            fallback_model_cfg, fallback_lite_model_cfg = extract_fallback_model_configs(user_cfgs.providers_dict)
            fallback_model_cfgs_list, fallback_lite_model_cfgs_list = resolve_chat_fallback_chains_from_providers(
                user_cfgs.providers_dict,
                require_tool_calling=True,
            )
            fallback_model_cfgs = fallback_model_cfgs_list or None
            fallback_lite_model_cfgs = fallback_lite_model_cfgs_list or None
            if fallback_model_cfgs and fallback_model_cfg is None:
                fallback_model_cfg = fallback_model_cfgs[0]
            if fallback_lite_model_cfgs and fallback_lite_model_cfg is None:
                fallback_lite_model_cfg = fallback_lite_model_cfgs[0]

            from myrm_agent_harness.toolkits.retriever.embedding.factory import (
                EmbeddingConfig,
            )
            from myrm_agent_harness.toolkits.retriever.reranker.factory import (
                RerankerConfig,
            )

            GeneralAgentParams.model_rebuild(
                _types_namespace={
                    "EmbeddingConfig": EmbeddingConfig,
                    "RerankerConfig": RerankerConfig,
                }
            )
            security_config_raw = user_cfgs.security_config_dict or {}
            profile = await resolve_cron_agent_profile(job)
            user_instructions = profile.user_instructions
            agent_skill_ids = profile.skill_ids
            agent_subagent_ids = profile.subagent_ids
            agent_security_raw = profile.security_raw
            agent_max_iterations = profile.max_iterations
            agent_memory_policy = profile.memory_policy
            agent_engine_params = profile.engine_params
            agent_model_override = profile.model_override
            enabled_builtin_tools = profile.enabled_builtin_tools
            auto_restore_domains = profile.auto_restore_domains
            memory_decay_profile = profile.memory_decay_profile
            memory_extraction_preset = profile.memory_extraction_preset
            cron_post_run_verify = profile.cron_post_run_verify
            trusted_desktop_apps = profile.trusted_desktop_apps
            resolved = profile.resolved

            from app.core.cron.adapters.tools_policy import (
                intersect_cron_enabled_builtin_tools,
            )

            enabled_builtin_tools = intersect_cron_enabled_builtin_tools(
                enabled_builtin_tools,
                job.tools_allowed,
            )

            from app.core.cron.adapters.tools_policy import (
                resolve_cron_runtime_tool_flags,
            )

            cron_tool_flags = resolve_cron_runtime_tool_flags(
                enabled_builtin_tools,
                job.tools_allowed,
            )

            # Priority: agent profile model > job.model > global default
            model_override = agent_model_override or job.model
            model_cfg = resolve_model_config(
                user_cfgs.providers_dict,
                model_override=model_override,
            )
            model_cfg = enrich_model_capabilities(model_cfg, user_cfgs.providers_dict)
            model_cfg = enrich_model_context_window(model_cfg, user_cfgs.providers_dict)
            vision_fallback_model_cfg, vision_fallback_model_cfgs = resolve_vision_fallback_chain_for_agent(
                user_cfgs.providers_dict,
                main_model_cfg=model_cfg if model_cfg.supports_vision else None,
            )

            memory_shared_context_ids: list[str] = []
            try:
                from app.services.memory.shared_context.shared_context import (
                    resolve_shared_context_ids,
                )

                memory_shared_context_ids = await resolve_shared_context_ids(
                    agent_id=job.agent_id,
                    channel_id="cron",
                    cron_id=job.id,
                    conversation_id=job.chat_id,
                    task_id=job.id,
                )
            except Exception as e:
                logger.warning(
                    "Cron job %s: failed to resolve shared memory contexts: %s",
                    job.id,
                    e,
                )

            memory_settings = user_cfgs.personal_settings_dict or {}
            cron_trusted_desktop_keys = resolve_trusted_desktop_keys(trusted_desktop_apps)
            if len(cron_trusted_desktop_keys) != len(trusted_desktop_apps):
                logger.warning(
                    "Cron job %s: %d/%d trusted desktop apps unresolvable, skipped",
                    job.id,
                    len(trusted_desktop_apps) - len(cron_trusted_desktop_keys),
                    len(trusted_desktop_apps),
                )
            from app.core.agent.tool_description_locale import (
                resolve_agent_params_locale,
            )
            from app.core.memory.proactive.settings import (
                resolve_conversation_search_enabled,
            )
            from app.services.agent.resolve_enable_web_fetch import (
                resolve_enable_web_fetch,
            )

            if job.chat_id and job.session_target != SessionTarget.MAIN:
                from app.services.chat.chat_crud import _ChatCrudMixin

                await _ChatCrudMixin.ensure_chat_source(job.chat_id, "cron")

            effective_allowed_roots = await _resolve_effective_allowed_roots(job)

            params = GeneralAgentParams(
                query=effective_prompt,
                model_cfg=model_cfg,
                fallback_model_cfg=fallback_model_cfg,
                fallback_model_cfgs=fallback_model_cfgs,
                fallback_lite_model_cfg=fallback_lite_model_cfg,
                fallback_lite_model_cfgs=fallback_lite_model_cfgs,
                vision_fallback_model_cfg=vision_fallback_model_cfg,
                vision_fallback_model_cfgs=vision_fallback_model_cfgs or None,
                search_service_cfg=user_cfgs.search_cfg,
                chat_id=job.chat_id,
                agent_id=job.agent_id,
                project_id=job.project_id,
                embedding_config=embedding_cfg,
                reranker_config=reranker_cfg,
                security_config_raw=security_config_raw,
                agent_security_raw=agent_security_raw,
                channel_name="cron",
                declared_capabilities=job.required_capabilities,
                declared_allowed_roots=tuple(effective_allowed_roots),
                **cron_tool_flags,
                enable_memory=_resolve_cron_enable_memory(enabled_builtin_tools, memory_settings, untrusted=untrusted),
                enable_web_search=await _resolve_cron_enable_web_search(
                    enabled_builtin_tools=enabled_builtin_tools,
                    job=job,
                    search_is_user_configured=user_cfgs.search_is_user_configured,
                    search_cfg=user_cfgs.search_cfg,
                ),
                enable_web_fetch=resolve_enable_web_fetch(agent_security_raw),
                auto_restore_domains=auto_restore_domains,
                unattended_mode=True,
                desktop_preapproved_trust_keys=cron_trusted_desktop_keys,
                desktop_unattended_fail_fast=True,
                user_instructions=user_instructions,
                agent_skill_ids=list(dict.fromkeys(agent_skill_ids + list(job.skill_ids))),
                subagent_ids=agent_subagent_ids,
                max_iterations=agent_max_iterations,
                memory_policy=agent_memory_policy,
                memory_decay_profile=memory_decay_profile,
                memory_extraction_preset=memory_extraction_preset,
                engine_params=agent_engine_params,
                memory_shared_context_ids=memory_shared_context_ids,
                enable_conversation_search=resolve_conversation_search_enabled(memory_settings),
                locale=resolve_agent_params_locale(
                    personal_settings=memory_settings,
                    channel="cron",
                ),
                notify_targets=(resolved.notify_targets if resolved else ()),
                **privacy_agent_params(memory_settings),
            )

            from app.ai_agents.event_log_injector import (
                inject_event_log_config,
                resolve_cron_event_log_session_id,
            )

            cron_event_log_sid = (
                job.chat_id
                if (job.session_target == SessionTarget.MAIN and job.chat_id)
                else resolve_cron_event_log_session_id(str(job.id))
            )
            inject_event_log_config(params, session_id_override=cron_event_log_sid)

            agent = AgentFactory.create_general_agent(params)
            agent.approval_session_key = f"cron:{job.id}"

            timeout = job.timeout_seconds or 300
            lease_session_key = grant_run_lease(agent, job, timeout_seconds=timeout, untrusted=untrusted)
            run_started_at = time.monotonic()
            model_name: str | None = getattr(agent.model_cfg, "model", None)

            from myrm_agent_harness.core.security.types import user_credentials_ctx

            from app.services.agent.execution_cache import (
                ExecutionMode,
                finalize_agent_session,
            )
            from app.services.agent.runtime_context import build_agent_runtime_context
            from app.services.agent.session_credential_assembler import (
                assemble_session_credentials,
            )

            runtime_context = await build_agent_runtime_context(
                execution_mode=ExecutionMode.EPHEMERAL,
            )

            session_credentials = await assemble_session_credentials(
                oauth_credentials_dict=user_cfgs.oauth_credentials_dict,
                providers_dict=user_cfgs.providers_dict,
            )
            cred_ctx = user_credentials_ctx.set(session_credentials)
            try:
                try:
                    if job.workflow_template_id:
                        import secrets

                        from app.services.agent.stream_session.stream_lane_factory import (
                            create_dynamic_workflow_stream,
                        )
                        from app.services.workflow_templates.validation import (
                            validate_cron_template_at_execution,
                        )

                        template_error = validate_cron_template_at_execution(
                            job.workflow_template_id,
                            job.workflow_template_args,
                        )
                        if template_error:
                            logger.warning(
                                "Cron agent job %s blocked by workflow template execution guard: %s",
                                job.id,
                                template_error,
                            )
                            return _deterministic_failure(template_error)

                        params.message_id = f"cron-{job.id}-{secrets.token_urlsafe(6)}"
                        dw_stream = create_dynamic_workflow_stream(
                            params,
                            cancel_token=None,
                            workflow_template_id=job.workflow_template_id,
                            workflow_template_args=job.workflow_template_args,
                            unattended=True,
                        )
                        result = await asyncio.wait_for(
                            _consume_dynamic_workflow_stream(dw_stream, job, model_name, acc),
                            timeout=timeout,
                        )
                    else:
                        result = await asyncio.wait_for(
                            _consume_stream(agent, job, effective_prompt, runtime_context, acc, untrusted=untrusted),
                            timeout=timeout,
                        )
                    if cron_post_run_verify:
                        from app.core.cron.adapters.post_run_verification import (
                            apply_cron_post_run_verification,
                        )

                        elapsed = time.monotonic() - run_started_at
                        remaining = max(0.0, float(timeout) - elapsed)
                        result = await apply_cron_post_run_verification(
                            agent,
                            job,
                            result,
                            enabled=True,
                            timeout_seconds=remaining,
                        )

                    if job.acceptance_criteria and result.success:
                        from app.core.cron.adapters.acceptance_verification import (
                            apply_acceptance_criteria_verification,
                        )

                        elapsed = time.monotonic() - run_started_at
                        remaining = max(0.0, float(timeout) - elapsed)
                        result = await apply_acceptance_criteria_verification(
                            job,
                            result,
                            timeout_seconds=remaining,
                        )
                finally:
                    await finalize_agent_session(
                        agent,
                        chat_id=job.chat_id,
                        agent_id=params.agent_id,
                        extra_context=runtime_context,
                    )

                await _finalize_heartbeat_follow_up_delivery(job, result)

                return result
            finally:
                user_credentials_ctx.reset(cred_ctx)

        except asyncio.TimeoutError:
            return _timeout_result(job)
        except Exception as exc:
            return _failure_result(job, exc, acc)
        finally:
            if lease_session_key:
                release_run_lease(lease_session_key)
            exit_cron_execution_context(cron_ctx_token)
