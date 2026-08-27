"""Wiki router cron runner — dispatches zero-LLM router commands.

[INPUT]
- app.services.wiki.source_sync.runner::run_wiki_source_sync (POS: wiki pull orchestration)
- app.services.wiki.maintain::run_wiki_maintain_job (POS: wiki maintain SSOT)

[OUTPUT]
- WikiRouterJobRunner: cron adapter for __wiki_source_sync__ and __wiki_maintain__ commands

[POS]
Cron adapter bridging harness RouterJobRunner to deterministic wiki router jobs.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.cron.runners import RouterJobRunner
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult
from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode

logger = logging.getLogger(__name__)

WIKI_SOURCE_SYNC_COMMAND = "__wiki_source_sync__"
WIKI_MAINTAIN_COMMAND_PREFIX = "__wiki_maintain__"
WIKI_DEDUP_COMMAND = "__wiki_dedup__"


def parse_wiki_maintain_mode(command: str | None) -> MaintainMode | str | None:
    if command is None:
        return None
    if command == WIKI_MAINTAIN_COMMAND_PREFIX:
        return MaintainMode.STRUCTURAL
    if command == f"{WIKI_MAINTAIN_COMMAND_PREFIX}:structural":
        return MaintainMode.STRUCTURAL
    if command == f"{WIKI_MAINTAIN_COMMAND_PREFIX}:full":
        return MaintainMode.FULL
    if command == f"{WIKI_MAINTAIN_COMMAND_PREFIX}:list_only":
        return "list_only"
    return None


class WikiRouterJobRunner:
    """Runs deterministic wiki router cron jobs."""

    def __init__(self) -> None:
        self._passthrough = RouterJobRunner()

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        maintain_mode = parse_wiki_maintain_mode(job.command)
        if maintain_mode is not None:
            return await self._run_maintain(job, mode=maintain_mode, context=context)

        if job.command == WIKI_SOURCE_SYNC_COMMAND:
            return await self._run_source_sync(job, context=context)

        if job.command == WIKI_DEDUP_COMMAND:
            return await self._run_dedup(job, context=context)

        return await self._passthrough.run(job, context=context)

    async def _run_source_sync(self, job: CronJob, *, context: str = "") -> JobResult:
        try:
            from app.services.agent.llm_access import get_optional_llm_for_user
            from app.services.wiki.source_sync.runner import run_wiki_source_sync

            llm = await get_optional_llm_for_user()
            summary = await run_wiki_source_sync(llm=llm, agent_id=job.agent_id)
            output = summary.summary_text
            if context.strip() and output != "[SILENT]":
                output = f"{context.strip()}\n{output}"
            exit_code = 0 if output == "[SILENT]" else 1
            return JobResult(success=True, output=output, exit_code=exit_code)
        except Exception as exc:
            logger.error("Wiki source sync cron failed for job %s: %s", job.id, exc)
            return JobResult(success=False, error=str(exc), exit_code=1)

    async def _run_maintain(
        self,
        job: CronJob,
        *,
        mode: MaintainMode | str,
        context: str = "",
    ) -> JobResult:
        try:
            from app.services.agent.llm_access import get_optional_llm_for_user
            from app.services.wiki.maintain import run_wiki_maintain_job

            llm = await get_optional_llm_for_user()
            result = await run_wiki_maintain_job(llm=llm, agent_id=job.agent_id, mode=mode)
            output = result.summary_text
            if context.strip() and output != "[SILENT]":
                output = f"{context.strip()}\n{output}"
            exit_code = 0 if output == "[SILENT]" else 1
            return JobResult(success=True, output=output, exit_code=exit_code)
        except Exception as exc:
            logger.error("Wiki maintain cron failed for job %s: %s", job.id, exc)
            return JobResult(success=False, error=str(exc), exit_code=1)

    async def _run_dedup(self, job: CronJob, *, context: str = "") -> JobResult:
        try:
            from app.services.wiki.dedup_runner import run_wiki_dedup_scan_job

            result = await run_wiki_dedup_scan_job(agent_id=job.agent_id, incremental=False)
            output = result.summary_text
            if context.strip() and output != "[SILENT]":
                output = f"{context.strip()}\n{output}"
            exit_code = 0 if output == "[SILENT]" else 1
            return JobResult(success=True, output=output, exit_code=exit_code)
        except Exception as exc:
            logger.error("Wiki dedup cron failed for job %s: %s", job.id, exc)
            return JobResult(success=False, error=str(exc), exit_code=1)
