"""CronManager wrapper — enforces sandbox cron entitlements on job mutations.

[INPUT]
- myrm_agent_harness.toolkits.cron.manager::CronManager (POS: cron CRUD orchestration)
- platform_utils.sandbox.entitlements.entitlement_guard::require_cron_slot (POS: CP plan gate)

[OUTPUT]
- EntitlementGuardedCronManager: wraps create/duplicate with slot checks for REST + agent tools

[POS]
Server business-layer gate on harness CronManager mutations. All callers use ``get_cron_manager()``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.incremental.types import MonitorConfig
from myrm_agent_harness.toolkits.cron.triggers import TriggerConfig
from myrm_agent_harness.toolkits.cron.types import (
    ActiveHours,
    CronJob,
    CronJobPatch,
    DeliveryConfig,
    FailureAlertConfig,
    JobType,
    Schedule,
    SessionTarget,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.manager import CronManager


class EntitlementGuardedCronManager:
    """Delegates to harness ``CronManager``; gates ``create_job`` / ``duplicate_job``."""

    def __init__(self, inner: CronManager) -> None:
        self._inner = inner

    async def _enforce_slot(self, user_id: str) -> None:
        from app.platform_utils.sandbox.entitlements.entitlement_guard import (
            EntitlementGuardError,
            require_cron_slot,
        )

        try:
            current_count = await self._inner.count_jobs(user_id)
            require_cron_slot(current_count)
        except EntitlementGuardError as exc:
            raise ValueError(str(exc)) from exc

    async def create_job(
        self,
        user_id: str,
        name: str,
        job_type: JobType,
        schedule: Schedule,
        *,
        prompt: str | None = None,
        model: str | None = None,
        chat_id: str | None = None,
        agent_id: str | None = None,
        command: str | None = None,
        delivery: DeliveryConfig | None = None,
        failure_delivery: DeliveryConfig | None = None,
        failure_alert: FailureAlertConfig | bool | None = None,
        active_hours: ActiveHours | None = None,
        required_capabilities: tuple[str, ...] = (),
        tools_allowed: tuple[str, ...] | None = None,
        allowed_roots: tuple[str, ...] = (),
        max_retries: int = 2,
        retry_backoff_ms: int = 30_000,
        timeout_seconds: int = 300,
        misfire_grace_seconds: int = 300,
        cooldown_seconds: int = 0,
        max_fires: int | None = None,
        expires_at: datetime | None = None,
        session_target: SessionTarget = SessionTarget.ISOLATED,
        delete_after_run: bool | None = None,
        run_retention_days: int = 30,
        deduplicate: bool = False,
        monitor_config: MonitorConfig | None = None,
        triggers: TriggerConfig | None = None,
        context_from: tuple[str, ...] = (),
        pre_condition_script: str | None = None,
    ) -> CronJob:
        from app.core.cron.adapters.lifecycle_guard import assert_cron_job_lifecycle_safe
        from app.core.cron.adapters.tools_policy import normalize_cron_tools_allowed

        assert_cron_job_lifecycle_safe(prompt=prompt, command=command)
        await self._enforce_slot(user_id)
        normalized_tools = normalize_cron_tools_allowed(tools_allowed) if tools_allowed else None
        return await self._inner.create_job(
            user_id,
            name,
            job_type,
            schedule,
            prompt=prompt,
            model=model,
            chat_id=chat_id,
            agent_id=agent_id,
            command=command,
            delivery=delivery,
            failure_delivery=failure_delivery,
            failure_alert=failure_alert,
            active_hours=active_hours,
            required_capabilities=required_capabilities,
            tools_allowed=normalized_tools,
            allowed_roots=allowed_roots,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
            timeout_seconds=timeout_seconds,
            misfire_grace_seconds=misfire_grace_seconds,
            cooldown_seconds=cooldown_seconds,
            max_fires=max_fires,
            expires_at=expires_at,
            session_target=session_target,
            delete_after_run=delete_after_run,
            run_retention_days=run_retention_days,
            deduplicate=deduplicate,
            monitor_config=monitor_config,
            triggers=triggers,
            context_from=context_from,
            pre_condition_script=pre_condition_script,
        )

    async def update_job(self, job_id: str, user_id: str, patch: CronJobPatch) -> CronJob | None:
        from app.core.cron.adapters.lifecycle_guard import assert_cron_job_lifecycle_safe
        from app.core.cron.adapters.tools_policy import normalize_cron_tools_allowed

        existing = await self._inner.get_job(job_id, user_id)
        if existing:
            next_prompt = existing.prompt if patch.prompt is None else patch.prompt
            next_command = existing.command if patch.command is None else patch.command
            assert_cron_job_lifecycle_safe(prompt=next_prompt, command=next_command)

        if patch.clear_tools_allowed:
            patch = replace(patch, tools_allowed=None)
        elif patch.tools_allowed is not None:
            normalized = normalize_cron_tools_allowed(list(patch.tools_allowed))
            patch = replace(patch, tools_allowed=normalized)

        return await self._inner.update_job(job_id, user_id, patch)

    async def duplicate_job(self, job_id: str, user_id: str) -> CronJob | None:
        await self._enforce_slot(user_id)
        return await self._inner.duplicate_job(job_id, user_id)

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)
