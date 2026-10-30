"""Complete job definition a blueprint hands to the cron agent tool.

A blueprint fills more than a prompt and a schedule: job type, session mode, dedup and overlap
policy, timeout, monitoring, failure alerting, a pre-condition script and a command. One typed
record carries all of them, so ``cron_manage_tool`` add forwards every field to ``create_job``.

[INPUT]
- infra.incremental.types::MonitorConfig (POS: Domain types for incremental monitoring.)
- toolkits.cron.types::FailureAlertConfig, JobType, Schedule, SessionTarget (POS: cron 数据模型)

[OUTPUT]
- DEFAULT_JOB_TIMEOUT_SECONDS: Timeout applied when a spec leaves ``timeout_seconds`` unset.
- BlueprintJobSpec: Frozen job definition produced by a blueprint filler.
- BlueprintFiller: (blueprint id, slot values, timezone) -> BlueprintJobSpec, or None for an unknown blueprint.

[POS]
Typed contract between a blueprint source and ``cron_manage_tool`` add.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from myrm_agent_harness.infra.incremental.types import MonitorConfig
from myrm_agent_harness.toolkits.cron.types import FailureAlertConfig, JobType, Schedule, SessionTarget

DEFAULT_JOB_TIMEOUT_SECONDS = 300


@dataclass(frozen=True, slots=True)
class BlueprintJobSpec:
    """Everything a blueprint decides about the job it creates."""

    schedule: Schedule
    prompt: str
    name: str
    required_capabilities: tuple[str, ...] = ()
    tools_allowed: tuple[str, ...] | None = None
    skill_ids: tuple[str, ...] = ()
    job_type: JobType = JobType.AGENT
    session_target: SessionTarget = SessionTarget.ISOLATED
    deduplicate: bool = False
    skip_if_active: bool = False
    timeout_seconds: int | None = None
    monitor_config: MonitorConfig | None = None
    failure_alert: FailureAlertConfig | None = None
    pre_condition_script: str | None = None
    command: str | None = None


BlueprintFiller = Callable[[str, dict[str, str], str | None], BlueprintJobSpec | None]
