"""The cron manager operations the ``cron_manage`` tool and the heartbeat call.

``CronManager`` is the harness implementation. An application that gates or audits job mutations
wraps it and hands the wrapper to the tool factory. The wrapper satisfies this port by shape: it
holds a manager rather than inheriting from one, so it carries none of the manager's state.

A rejected mutation (invalid configuration, a refused gate) raises ``ValueError`` carrying the reason.
Parameters written ``= ...`` have a default in the manager, which stays the only place that states it.

[INPUT]
- infra.incremental.types::MonitorConfig (POS: Domain types for incremental monitoring.)
- cron.triggers::TriggerConfig (POS: event trigger definitions)
- cron.types::CronJob, CronJobPatch, RunNowOutcome, Schedule and the job option types (POS: cron data models)

[OUTPUT]
- CronManagerPort: structural contract of the eight job operations the agent tool and the heartbeat use

[POS]
Typing seam between the cron agent tools and the object that manages jobs, the harness ``CronManager``
or an application wrapper around it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from myrm_agent_harness.infra.incremental.types import MonitorConfig
    from myrm_agent_harness.toolkits.cron.triggers import TriggerConfig
    from myrm_agent_harness.toolkits.cron.types import (
        ActiveHours,
        CronJob,
        CronJobPatch,
        DeliveryConfig,
        FailureAlertConfig,
        JobType,
        RunNowOutcome,
        Schedule,
        SessionTarget,
    )


class CronManagerPort(Protocol):
    """Job operations a caller may rely on; a manager may accept more options than listed here."""

    async def create_job(
        self,
        name: str,
        job_type: JobType,
        schedule: Schedule,
        *,
        prompt: str | None = ...,
        model: str | None = ...,
        chat_id: str | None = ...,
        agent_id: str | None = ...,
        command: str | None = ...,
        delivery: DeliveryConfig | None = ...,
        failure_delivery: DeliveryConfig | None = ...,
        failure_alert: FailureAlertConfig | bool | None = ...,
        active_hours: ActiveHours | None = ...,
        required_capabilities: tuple[str, ...] = ...,
        tools_allowed: tuple[str, ...] | None = ...,
        skill_ids: tuple[str, ...] = ...,
        timeout_seconds: int = ...,
        max_fires: int | None = ...,
        expires_at: datetime | None = ...,
        session_target: SessionTarget = ...,
        deduplicate: bool = ...,
        skip_if_active: bool = ...,
        monitor_config: MonitorConfig | None = ...,
        triggers: TriggerConfig | None = ...,
        context_from: tuple[str, ...] = ...,
        pre_condition_script: str | None = ...,
    ) -> CronJob: ...

    async def update_job(self, job_id: str, patch: CronJobPatch) -> CronJob | None: ...

    async def list_jobs(self, *, name_filter: str | None = ..., limit: int | None = ...) -> list[CronJob]: ...

    async def get_job(self, job_id: str) -> CronJob | None: ...

    async def delete_job(self, job_id: str) -> bool: ...

    async def pause_job(self, job_id: str) -> CronJob | None: ...

    async def resume_job(self, job_id: str) -> CronJob | None: ...

    async def run_now(self, job_id: str) -> RunNowOutcome: ...
