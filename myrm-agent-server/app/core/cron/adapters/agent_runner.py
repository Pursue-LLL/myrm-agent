"""Agent job runner — executes cron jobs through the Agent pipeline.

1. agent/context_management/PROMPT_CACHE_PRACTICE.md §2.3 Cron 场景

Reads the user's latest configs from ConfigService at execution time
(no config snapshot). Model priority: agent profile model > CronJob.model
> user's default model. No implicit fallback to arbitrary providers.

When CronJob.agent_id is set, loads the agent's full profile via
AgentProfileResolver to inject system_prompt, skills, model,
subagent_ids, security overrides, max_iterations, and memory_policy
into GeneralAgentParams — identical to Web/Channel entry points.

For recurring jobs, a [SILENT] instruction is appended to the prompt
so the Agent can skip delivery when there's nothing actionable to report.

During execution, a ContextVar guard prevents the Agent from creating new
cron jobs (cron self-scheduling prevention).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from myrm_agent_harness.toolkits.cron.cron_agent_tools import (
    enter_cron_execution_context,
    exit_cron_execution_context,
)
from myrm_agent_harness.toolkits.cron.heartbeat import HEARTBEAT_JOB_NAME
from myrm_agent_harness.toolkits.cron.situation import SituationContext, SituationReportBuilder
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult, ScheduleKind

from .injection_scan import scan_cron_prompt

logger = logging.getLogger(__name__)


def _source_sort_key(s: dict[str, object]) -> int:
    v = s.get("index", 0)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v, 10)
        except ValueError:
            return 0
    return 0


def _coerce_usage_int(v: object) -> int:
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v, 10)
        except ValueError:
            return 0
    return 0


_SILENT_SUFFIX = (
    "\n\n---\n"
    "[Scheduler] This is a recurring scheduled task. "
    "If there is nothing actionable or noteworthy to report, "
    "respond with exactly `[SILENT]` (no other text) to skip notification delivery."
)


def _build_effective_prompt(job: CronJob) -> str:
    """Append [SILENT] instruction for recurring jobs."""
    prompt = job.prompt or ""
    if job.schedule.kind in (ScheduleKind.CRON, ScheduleKind.INTERVAL):
        return prompt + _SILENT_SUFFIX
    return prompt


class AgentJobRunner:
    """JobRunner implementation that delegates to AgentFactory.

    When a ``SituationReportBuilder`` is injected, heartbeat jobs receive
    a dynamically-built situation report prepended to their prompt,
    transforming blind self-checks into intelligence-driven actions.
    """

    def __init__(self, *, situation_builder: SituationReportBuilder | None = None) -> None:
        self._situation_builder = situation_builder

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        last_result = JobResult(success=False, error="never executed")

        for attempt in range(1 + job.max_retries):
            last_result = await self._run_once(job, context=context)
            if last_result.success:
                return last_result

            if attempt < job.max_retries:
                backoff = min(job.retry_backoff_ms * (2**attempt), 30_000)
                jitter = int(datetime.now(timezone.utc).microsecond % 250)
                await asyncio.sleep((backoff + jitter) / 1000)

        return last_result

    async def _inject_situation_report(self, job: CronJob, prompt: str) -> tuple[str, bool]:
        """Build and prepend a situation report for heartbeat jobs.

        Returns ``(effective_prompt, has_actionable_content)`` so the caller
        can skip the LLM call when no section produced useful data.
        """
        assert self._situation_builder is not None
        try:
            ctx = SituationContext(
                last_tick_at=job.last_run_at,
                agent_id=job.agent_id or "",
                user_id=job.user_id,
            )
            report = await self._situation_builder.build(ctx)
            if report:
                return f"<situation_report>\n{report}</situation_report>\n\n{prompt}", True
        except Exception:
            logger.warning("Situation report build failed for job %s", job.id, exc_info=True)
            return prompt, True
        return prompt, False

    async def _try_enqueue_if_goal_active(self, job: CronJob, *, context: str = "") -> bool:
        """If an active goal exists on this chat, enqueue the cron task as a queued goal.

        Returns True if the job was enqueued (caller should skip direct execution).
        """
        from app.services.agent.goal_registry import GoalRegistry

        chat_id = job.chat_id
        if not chat_id:
            return False

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return False

        active = await provider.get_active_goal(chat_id)
        if not active:
            return False

        effective_prompt = _build_effective_prompt(job)
        if context:
            effective_prompt = f"{effective_prompt}\n\n{context}"

        objective = f"[Cron: {job.name}] {effective_prompt[:200]}"
        await provider.create_goal(session_id=chat_id, objective=objective)
        logger.info(
            "Cron job %s enqueued as goal on chat %s (active goal: %s)",
            job.id,
            chat_id,
            active.goal_id,
        )
        return True

    async def _run_once(self, job: CronJob, *, context: str = "") -> JobResult:
        if not job.prompt:
            return JobResult(success=False, error="agent job requires a prompt")

        from app.services.budget.enforcer import should_block_execution

        if await should_block_execution():
            return JobResult(success=False, error="daily budget exceeded (block policy)")

        if job.chat_id:
            queued = await self._try_enqueue_if_goal_active(job, context=context)
            if queued:
                return JobResult(success=True, output="cron job enqueued as goal (active goal exists)")

        effective_prompt = _build_effective_prompt(job)

        injection_findings = scan_cron_prompt(effective_prompt)
        if injection_findings:
            logger.warning(
                "Cron job %s: prompt injection patterns detected — %s",
                job.id,
                "; ".join(injection_findings),
            )
            return JobResult(
                success=False,
                error=f"prompt injection detected: {injection_findings[0]}",
            )

        if self._situation_builder and job.name == HEARTBEAT_JOB_NAME:
            effective_prompt, has_content = await self._inject_situation_report(job, effective_prompt)
            if not has_content:
                logger.info("Heartbeat job %s: all sections empty, skipping LLM call", job.id)
                return JobResult(success=True, skipped=True, skip_reason="no-content")

        if context:
            effective_prompt = f"{effective_prompt}\n\n{context}"

        cron_ctx_token = enter_cron_execution_context()
        try:
            from app.ai_agents.agents import AgentFactory, GeneralAgentParams
            from app.core.channel_bridge.config_loader import load_user_configs
            from app.core.channel_bridge.config_parsers import (
                extract_fallback_model_configs,
                extract_retrieval_models,
                verify_search_service_available,
            )
            from app.core.channel_bridge.model_resolver import enrich_model_context_window, resolve_model_config

            user_cfgs = await load_user_configs()

            embedding_cfg, reranker_cfg = extract_retrieval_models(user_cfgs.retrieval_dict)
            fallback_model_cfg, fallback_lite_model_cfg = extract_fallback_model_configs(user_cfgs.providers_dict)

            from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
            from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

            GeneralAgentParams.model_rebuild(
                _types_namespace={
                    "EmbeddingConfig": EmbeddingConfig,
                    "RerankerConfig": RerankerConfig,
                }
            )

            security_config_raw = user_cfgs.security_config_dict or {}
            if not security_config_raw.get("yolo_mode_enabled", False):
                security_config_raw["yolo_mode_enabled"] = True
                security_config_raw["yolo_mode_enabled_at"] = time.time()
                security_config_raw["yolo_mode_timeout"] = None
                logger.info("Cron job %s: auto-enabled YOLO mode for unattended execution", job.id)

            agent_skill_ids: list[str] = []
            agent_subagent_ids: list[str] | None = None
            agent_security_raw: dict[str, object] | None = None
            agent_max_iterations: int | None = None
            agent_memory_policy = None
            agent_engine_params = None
            user_instructions: str | None = None
            agent_model_override: str | None = None
            from app.services.agent.profile_resolver import (
                DEFAULT_ENABLED_BUILTIN_TOOLS,
                resolve_builtin_tool_flags,
            )

            enabled_builtin_tools: list[str] = list(DEFAULT_ENABLED_BUILTIN_TOOLS)
            auto_restore_domains: list[str] = []
            memory_decay_profile: str | None = None

            if job.agent_id:
                from app.services.agent.profile_resolver import get_agent_profile_resolver

                resolved = await get_agent_profile_resolver().resolve(job.agent_id)
                if resolved:
                    if resolved.system_prompt:
                        user_instructions = resolved.system_prompt
                    agent_skill_ids = list(resolved.skill_ids)
                    agent_subagent_ids = list(resolved.subagent_ids) if resolved.subagent_ids else None
                    agent_security_raw = resolved.security_overrides
                    agent_max_iterations = resolved.max_iterations
                    agent_memory_policy = resolved.memory_policy
                    agent_engine_params = resolved.engine_params
                    agent_model_override = resolved.model
                    enabled_builtin_tools = list(resolved.enabled_builtin_tools)
                    auto_restore_domains = list(resolved.auto_restore_domains)
                    raw_decay = resolved.memory_decay_profile
                    memory_decay_profile = raw_decay if isinstance(raw_decay, str) else None

                    if resolved.agent_type == "team":
                        from app.ai_agents.team_protocol import (
                            build_leader_protocol_prompt,
                        )

                        leader_protocol = await build_leader_protocol_prompt(
                            agent_subagent_ids or [],
                            leader_id=job.agent_id,
                            dynamic_discovery=True,
                        )
                        user_instructions = f"{user_instructions}\n\n{leader_protocol}" if user_instructions else leader_protocol

            # Priority: agent profile model > job.model > global default
            model_override = agent_model_override or job.model
            model_cfg = resolve_model_config(
                user_cfgs.providers_dict,
                model_override=model_override,
            )
            model_cfg = enrich_model_context_window(model_cfg, user_cfgs.providers_dict)

            memory_shared_context_ids: list[str] = []
            try:
                from app.services.memory.shared_context import resolve_shared_context_ids

                memory_shared_context_ids = await resolve_shared_context_ids(
                    agent_id=job.agent_id,
                    channel_id="cron",
                    cron_id=job.id,
                    conversation_id=job.chat_id,
                    task_id=job.id,
                )
            except Exception as e:
                logger.warning("Cron job %s: failed to resolve shared memory contexts: %s", job.id, e)

            params = GeneralAgentParams(
                query=effective_prompt,
                model_cfg=model_cfg,
                fallback_model_cfg=fallback_model_cfg,
                fallback_lite_model_cfg=fallback_lite_model_cfg,
                search_service_cfg=user_cfgs.search_cfg,
                chat_id=job.chat_id,
                agent_id=job.agent_id,
                embedding_config=embedding_cfg,
                reranker_config=reranker_cfg,
                security_config_raw=security_config_raw,
                agent_security_raw=agent_security_raw,
                channel_name="cron",
                declared_capabilities=job.required_capabilities,
                declared_allowed_roots=job.allowed_roots,
                enable_web_search="web_search" in enabled_builtin_tools
                and user_cfgs.search_is_user_configured
                and await verify_search_service_available(user_cfgs.search_cfg),
                **resolve_builtin_tool_flags(enabled_builtin_tools),
                auto_restore_domains=auto_restore_domains,
                unattended_mode=True,
                user_instructions=user_instructions,
                agent_skill_ids=agent_skill_ids,
                subagent_ids=agent_subagent_ids,
                max_iterations=agent_max_iterations,
                memory_policy=agent_memory_policy,
                memory_decay_profile=memory_decay_profile,
                engine_params=agent_engine_params,
                memory_shared_context_ids=memory_shared_context_ids,
                notify_targets=(resolved.notify_targets if resolved else ()),
            )

            agent = AgentFactory.create_general_agent(params)
            agent.approval_session_key = f"cron:{job.id}"
            timeout = job.timeout_seconds or 300
            try:
                result = await asyncio.wait_for(
                    _consume_stream(agent, job, effective_prompt),
                    timeout=timeout,
                )
            finally:
                await agent.close()

            return result

        except asyncio.TimeoutError:
            logger.warning("Cron agent job %s timed out after %ds", job.id, job.timeout_seconds or 300)
            return JobResult(success=False, error=f"agent timed out after {job.timeout_seconds or 300}s")
        except Exception as exc:
            logger.warning("Cron agent job %s failed: %s", job.id, exc)
            return JobResult(success=False, error=str(exc))
        finally:
            exit_cron_execution_context(cron_ctx_token)


# ---------------------------------------------------------------------------
# Stream accumulation
# ---------------------------------------------------------------------------


@dataclass
class _StreamAccumulator:
    chunks: list[str] = field(default_factory=list)
    progress_steps: list[dict[str, object]] = field(default_factory=list)
    sources: list[dict[str, object]] = field(default_factory=list)
    usage: dict[str, int] | None = None
    error: str | None = None
    _seen_indices: set[int] = field(default_factory=set)

    def add_sources(self, items: list[dict[str, object]]) -> None:
        for src in items:
            idx = src.get("index")
            if isinstance(idx, int) and idx not in self._seen_indices:
                self._seen_indices.add(idx)
                self.sources.append(src)

    def to_result(self, model: str | None = None) -> JobResult:
        output = "".join(self.chunks)
        metadata: dict[str, object] = {}
        if self.progress_steps:
            metadata["progressSteps"] = self.progress_steps
        if self.sources:
            metadata["sources"] = sorted(self.sources, key=_source_sort_key)
        if model:
            metadata["model"] = model
        if self.usage:
            metadata["usage"] = self.usage

        from myrm_agent_harness.agent.security.audit import get_audit_entries

        audit = get_audit_entries()
        if audit:
            metadata["securityAudit"] = [e.to_dict() for e in audit]

        if self.error:
            return JobResult(
                success=False,
                output=output or None,
                error=self.error,
                metadata=metadata or None,
            )

        return JobResult(
            success=True,
            output=output or "agent completed",
            metadata=metadata or None,
        )


async def _consume_stream(agent: object, job: CronJob, effective_prompt: str) -> JobResult:
    from app.ai_agents.general_agent import GeneralAgent

    assert isinstance(agent, GeneralAgent)

    acc = _StreamAccumulator()
    model_name: str | None = getattr(agent.model_cfg, "model", None)

    async for event in agent.process_stream(
        query=effective_prompt,
        chat_history=None,
        chat_id=job.chat_id,
    ):
        event_type = event.get("type", "")

        if event_type == "message" and isinstance(event.get("data"), str):
            acc.chunks.append(str(event["data"]))
        elif event_type == "message_end" and isinstance(event.get("usage"), dict):
            raw_u = event.get("usage")
            assert isinstance(raw_u, dict)
            acc.usage = {str(k): _coerce_usage_int(v) for k, v in raw_u.items()}
        elif event_type == "error":
            error_msg = event.get("error", "unknown agent error")
            error_type = event.get("error_type", "")
            acc.error = f"{error_type}: {error_msg}" if error_type else str(error_msg)
        elif event_type == "tasks_steps":
            acc.progress_steps.append(
                {
                    "step_key": event.get("step_key"),
                    "tool_name": event.get("tool_name"),
                    "items": event.get("data"),
                    "count": event.get("count"),
                    "error": event.get("error") if event.get("status") == "error" else None,
                }
            )
        elif event_type == "sources" and isinstance(event.get("data"), list):
            raw_list = event.get("data")
            assert isinstance(raw_list, list)
            src_items: list[dict[str, object]] = []
            for el in raw_list:
                if isinstance(el, dict):
                    src_items.append({str(k): val for k, val in el.items()})
            acc.add_sources(src_items)

    return acc.to_result(model=model_name)
