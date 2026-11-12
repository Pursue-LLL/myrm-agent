"""[INPUT]
- myrm_agent_harness.toolkits.cron.heartbeat::HEARTBEAT_JOB_NAME (POS: Heartbeat — convenience layer over CronManager for periodic agent self-checks.)
- myrm_agent_harness.toolkits.cron.types::CronJob / JobResult / ScheduleKind (POS: Cron job domain types.)
- app.core.agent.stop_reason::step_item_text (POS: The chat stream collector (services), the cron runner (core) and the Runs Hub (api) all store and read the same ``stopReason`` shape; this is the one definition they share.)

[OUTPUT]
- _heartbeat_follow_up_delivered: Return True when heartbeat output counts as a successful follow-up delivery ack.
- _finalize_heartbeat_follow_up_delivery: Confirm or reset follow-up delivery state after a heartbeat agent run.
- _scan_stalled_group_threads: Run one lazy stall scan from the heartbeat path (no new daemon).
- _source_sort_key: _source_sort_key
- _coerce_usage_int: _coerce_usage_int
- _derive_stop_reason_from_event: _derive_stop_reason_from_event
- _resolve_effective_allowed_roots: The folders a run may work in: the job's own roots, else its project's workspace.
- _build_effective_prompt: Append [SILENT] instruction for recurring jobs.
- resolve_trusted_desktop_keys: Resolve pre-trusted desktop app entries to canonical trust keys.
- _resolve_cron_enable_memory: Enable memory for cron only when all gates pass.
- _resolve_cron_enable_web_search: Enable web_search for cron when policy allows it and search is configured.
- _build_daily_context: Build injected context for DAILY session-target jobs.
- _memory_overload_reason: Return a skip reason when memory is critical, else None.
- _budget_skip_reason: Skip code of a budget-blocked run: a hosted deployment is out of plan credit, a local one over its daily budget.

[POS]
agent_runner 的支撑层；不持有执行器状态。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.heartbeat import HEARTBEAT_JOB_NAME
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    JobResult,
    ScheduleKind,
)

from app.core.agent.stop_reason import step_item_text

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

logger = logging.getLogger(__name__)

def _heartbeat_follow_up_delivered(job_output: str | None) -> bool:
    """Return True when heartbeat output counts as a successful follow-up delivery ack."""
    text = (job_output or "").strip()
    return bool(text) and not text.startswith("[SILENT]")


async def _finalize_heartbeat_follow_up_delivery(job: CronJob, result: JobResult) -> None:
    """Confirm or reset follow-up delivery state after a heartbeat agent run."""
    if job.name != HEARTBEAT_JOB_NAME:
        return

    from app.core.memory.proactive.delivery_tracker import (
        confirm_follow_up_delivery,
        reset_follow_up_delivery,
    )

    if result.success and not result.skipped:
        await confirm_follow_up_delivery(delivered=_heartbeat_follow_up_delivered(result.output))
    else:
        reset_follow_up_delivery()
    await _scan_stalled_group_threads()


async def _scan_stalled_group_threads() -> int:
    """Run one lazy stall scan from the heartbeat path (no new daemon).

    Covers fully silent groups that inbound traffic would never trigger.
    Best-effort: failures never propagate to the cron run.
    """
    try:
        from app.channels.routing.channel_data_plane import ChannelDataPlaneService
        from app.channels.routing.follow_up import scan_stalled_threads
        from app.core.channel_bridge import channel_gateway
        from app.core.channel_bridge.topic_config import SqlTopicManager

        return await scan_stalled_threads(
            bus=channel_gateway.bus,
            resolve_topic=SqlTopicManager().resolve_topic,
            record_outbound=ChannelDataPlaneService.record_outbound,
        )
    except Exception:
        logger.warning("Heartbeat stall scan skipped", exc_info=True)
        return 0


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


def _derive_stop_reason_from_event(
    event: dict[str, object],
) -> dict[str, object] | None:
    event_type = event.get("type")
    if not isinstance(event_type, str):
        return None

    data = event.get("data")
    detail = data if isinstance(data, dict) else None

    if event_type == "iteration_limit_reached":
        message = "Iteration limit reached"
        if detail is not None:
            limit = detail.get("limit")
            nodes = detail.get("nodes_completed")
            if limit is not None and nodes is not None:
                message = f"Iteration limit reached ({limit} iterations / {nodes} nodes)"
            elif limit is not None:
                message = f"Iteration limit reached ({limit} iterations)"
        payload: dict[str, object] = {
            "code": "iteration_limit_reached",
            "category": "limit",
            "message": message,
        }
        if detail is not None:
            payload["detail"] = detail
        return payload

    if event_type == "engine_limit_reached":
        message = "Engine limit reached"
        if detail is not None:
            raw_message = detail.get("message")
            if isinstance(raw_message, str) and raw_message.strip():
                message = raw_message.strip()
        payload_2: dict[str, object] = {
            "code": "engine_limit_reached",
            "category": "limit",
            "message": message,
        }
        if detail is not None:
            payload_2["detail"] = detail
        return payload_2

    if event_type == "agent_cancelled":
        reason = detail.get("reason") if detail else None
        payload_3: dict[str, object] = {
            "code": "agent_cancelled",
            "category": "cancelled",
            "message": ("Cancelled by user" if reason == "user_cancelled" else "Run cancelled"),
        }
        if detail is not None:
            payload_3["detail"] = detail
        return payload_3

    if event_type == "tasks_steps":
        step_key = event.get("step_key")
        if step_key == "iteration_limit_reached":
            text = step_item_text(event.get("data"))
            message = "Iteration limit reached"
            if text:
                message = f"Iteration limit reached ({text})"
            return {
                "code": "iteration_limit_reached",
                "category": "limit",
                "message": message,
            }
        if event.get("status") == "error":
            error_text = event.get("error")
            if isinstance(error_text, str) and "Tool call limit exceeded" in error_text:
                return {
                    "code": "engine_limit_reached",
                    "category": "limit",
                    "message": error_text.strip() or "Engine limit reached",
                }

    if event_type == "error":
        error_text = event.get("error")
        if isinstance(error_text, str) and error_text.strip():
            payload_4: dict[str, object] = {
                "code": "error",
                "category": "error",
                "message": error_text.strip(),
            }
            error_type = event.get("error_type")
            if isinstance(error_type, str) and error_type.strip():
                payload_4["detail"] = {"error_type": error_type.strip()}
            return payload_4

    return None


_SILENT_SUFFIX = (
    "\n\n---\n"
    "[Scheduler] This is a recurring scheduled task. "
    "If there is nothing actionable or noteworthy to report, "
    "respond with exactly `[SILENT]` (no other text) to skip notification delivery."
)


_DAILY_MAX_HISTORY_ENTRIES = 5
_DAILY_OUTPUT_TRUNCATE_CHARS = 500
_DAILY_CROSSDAY_SUMMARY_CHARS = 300
_ONE_DAY = timedelta(days=1)
_OVERLOAD_RETRY_DELAY = timedelta(seconds=60)


async def _resolve_effective_allowed_roots(job: CronJob) -> list[str]:
    """The folders a run may work in: the job's own roots, else its project's workspace.

    Stored roots are judged again here, so a root that is, or contains, a protected location fails the run with
    its reason instead of being granted.
    """
    from app.services.workspace.workspace_path_policy import require_grantable_roots

    roots = list(job.allowed_roots)
    if job.project_id and not roots:
        try:
            from app.services.project.project_service import ProjectService

            project_model = await ProjectService.get_project(job.project_id)
            if project_model and project_model.workspace_path:
                roots.append(project_model.workspace_path)
        except Exception as exc:
            logger.warning("Failed to resolve project workspace for cron job %s: %s", job.id, exc)
    require_grantable_roots(roots, subject=f"Cron job {job.id}")
    return roots


def _build_effective_prompt(job: CronJob) -> str:
    """Append [SILENT] instruction for recurring jobs."""
    prompt = job.prompt or ""
    if job.schedule.kind in (ScheduleKind.CRON, ScheduleKind.INTERVAL):
        return prompt + _SILENT_SUFFIX
    return prompt


def resolve_trusted_desktop_keys(
    entries: tuple[dict[str, str], ...] | list[dict[str, str]],
) -> tuple[str, ...]:
    """Resolve pre-trusted desktop app entries to canonical trust keys.

    Unresolvable entries are skipped (caller logs the count gap).
    """
    from myrm_agent_harness.toolkits.computer_use.app_identity import (
        resolve_trust_key,
    )

    return tuple(
        key
        for key in (
            resolve_trust_key(
                app_name=app.get("name", ""),
                app_id=app.get("app_id", ""),
            )
            for app in entries
        )
        if key
    )


def _resolve_cron_enable_memory(
    enabled_builtin_tools: list[str],
    memory_settings: dict[str, object] | None,
    *,
    untrusted: bool,
) -> bool:
    """Enable memory for cron only when all gates pass.

    1. The intersected tool set allows memory (``tools_allowed`` per-job
       allow-list, parallel to web_search/file/shell handling).
    2. The user-level memory master switch is on (``enableMemory`` personal
       setting), keeping cron consistent with channel/voice entry points.
    3. The run was not started by an untrusted sender: memory here is the owner's,
       so a stranger's run neither reads nor writes it.
    """
    from app.core.memory.proactive.settings import resolve_memory_enabled

    return not untrusted and "memory" in enabled_builtin_tools and resolve_memory_enabled(memory_settings)


async def _resolve_cron_enable_web_search(
    *,
    enabled_builtin_tools: list[str],
    job: CronJob,
    search_is_user_configured: bool,
    search_cfg: SearchServiceConfig | None,
) -> bool:
    """Enable web_search for cron when policy allows it and search is configured."""
    if "web_search" not in enabled_builtin_tools or not search_is_user_configured:
        return False
    if job.tools_allowed is not None and "web_search" in job.tools_allowed:
        return True
    from app.core.channel_bridge.config_parsers import verify_search_service_available

    return await verify_search_service_available(search_cfg)


async def _build_daily_context(job: CronJob) -> str:
    """Build injected context for DAILY session-target jobs.

    Queries same-day CronRunRecords for this job and formats recent
    outputs as context.  On cross-day boundary (first run of the day),
    injects the previous day's last output as a summary.

    Returns an empty string when there is no history to inject.
    """
    from ..setup import get_cron_store

    store = get_cron_store()
    today_utc = datetime.now(timezone.utc).date()

    runs = await store.list_runs(
        job_id=job.id,
        limit=_DAILY_MAX_HISTORY_ENTRIES + 5,
        status="ok",
    )
    if not runs:
        return ""

    def _utc_date(dt: datetime) -> date:
        if dt.tzinfo is None:
            return dt.date()
        return dt.astimezone(timezone.utc).date()

    today_runs = [r for r in runs if _utc_date(r.finished_at) == today_utc]
    yesterday_utc = today_utc - _ONE_DAY
    yesterday_runs = [r for r in runs if _utc_date(r.finished_at) == yesterday_utc]

    fragments: list[str] = []

    if not today_runs and yesterday_runs:
        prev = yesterday_runs[0]
        output = (prev.output or "")[:_DAILY_CROSSDAY_SUMMARY_CHARS]
        if output:
            fragments.append(f"[Yesterday's last output]\n{output}")

    for run in reversed(today_runs[:_DAILY_MAX_HISTORY_ENTRIES]):
        time_label = run.finished_at.strftime("%H:%M")
        output = (run.output or "")[:_DAILY_OUTPUT_TRUNCATE_CHARS]
        if output:
            fragments.append(f"[Previous run at {time_label}]\n{output}")

    if not fragments:
        return ""

    logger.debug("Daily context for job %s: %d fragments injected", job.id, len(fragments))
    return "<daily_context>\n" + "\n---\n".join(fragments) + "\n</daily_context>"


def _memory_overload_reason() -> str | None:
    """Return a skip reason when memory is critical, else None.

    Fail-open by design: any probe failure proceeds with execution rather
    than blocking scheduled work on a broken sensor.
    """
    try:
        from app.lifecycle.monitors import get_memory_pressure_monitor_instance

        monitor = get_memory_pressure_monitor_instance()
        if monitor is None:
            return None
        level = monitor.current_level.name
        if level in ("CRITICAL", "EMERGENCY"):
            return f"memory_pressure:{level.lower()}"
        return None
    except Exception:
        return None


def _budget_skip_reason() -> str:
    """Skip code of a budget-blocked run: a hosted deployment is out of plan credit, a local one over its daily budget."""
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    return "credit_exhausted" if get_deployment_capabilities().uses_platform_budget else "budget_blocked"
