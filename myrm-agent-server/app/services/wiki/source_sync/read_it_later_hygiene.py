"""Migrate legacy agent-type read-it-later cron jobs to wiki source sync router jobs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from myrm_agent_harness.toolkits.cron.types import CronJob, JobType, SessionTarget

from app.core.cron.adapters.setup import get_cron_manager
from app.core.cron.adapters.wiki_source_sync_runner import WIKI_SOURCE_SYNC_COMMAND
from app.core.cron.blueprints import fill_blueprint

logger = logging.getLogger(__name__)

_DEFAULT_USER_ID = "default"
_READ_IT_LATER_BLUEPRINT = "read_it_later"

_LEGACY_PROMPT_MARKERS: tuple[str, ...] = (
    "read-it-later ingestion",
    "read-it-later ingestion pipeline",
    "pull unprocessed items, ingest into wiki",
    "稍后读内化",
    "拉取未处理条目，写入知识库",
    "执行稍后读内化流程",
)

_SECOND_BRAIN_NAME_PREFIX = "Second Brain · Read-it-Later"
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(slots=True)
class ReadItLaterHygieneResult:
    migrated_count: int = 0
    id_remaps: dict[str, str] = field(default_factory=dict)


def _locale_for_job(job: CronJob) -> str:
    prompt = job.prompt or ""
    return "zh" if _CJK_RE.search(prompt) else "en"


def is_stale_read_it_later_job(job: CronJob) -> bool:
    if job.command == WIKI_SOURCE_SYNC_COMMAND and job.job_type == JobType.ROUTER:
        return False

    if job.name.startswith(_SECOND_BRAIN_NAME_PREFIX):
        return True

    prompt_lower = (job.prompt or "").lower()
    for marker in _LEGACY_PROMPT_MARKERS:
        if marker.lower() in prompt_lower:
            return True

    return False


async def migrate_stale_read_it_later_jobs(*, user_id: str = _DEFAULT_USER_ID) -> ReadItLaterHygieneResult:
    mgr = get_cron_manager()
    jobs = await mgr.list_jobs(user_id)
    result = ReadItLaterHygieneResult()

    for job in jobs:
        if not is_stale_read_it_later_job(job):
            continue

        locale = _locale_for_job(job)
        fill = fill_blueprint(
            _READ_IT_LATER_BLUEPRINT,
            {"time": "06:00", "weekdays": "everyday"},
            locale=locale,
        )
        if fill is None:
            logger.warning("read_it_later blueprint unavailable; skipping cron hygiene for %s", job.id)
            continue

        old_id = job.id
        try:
            await mgr.delete_job(old_id, user_id)
            recreated = await mgr.create_job(
                user_id,
                job.name,
                JobType(fill.job_type),
                job.schedule,
                prompt=fill.prompt,
                agent_id=job.agent_id,
                required_capabilities=fill.required_capabilities,
                tools_allowed=fill.tools_allowed,
                session_target=SessionTarget(fill.session_target),
                deduplicate=fill.deduplicate,
                skip_if_active=fill.skip_if_active,
                timeout_seconds=fill.timeout_seconds or 120,
                pre_condition_script=fill.pre_condition_script,
                command=fill.command,
            )
        except Exception as exc:
            logger.warning("Failed to migrate stale read-it-later cron %s: %s", old_id, exc)
            continue

        result.migrated_count += 1
        result.id_remaps[old_id] = recreated.id
        logger.info(
            "Migrated stale read-it-later cron job %s → %s (router %s)",
            old_id,
            recreated.id,
            WIKI_SOURCE_SYNC_COMMAND,
        )

    return result
