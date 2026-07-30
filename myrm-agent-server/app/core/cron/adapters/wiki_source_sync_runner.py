"""Wiki source sync cron runner — zero-LLM router jobs.

[INPUT]
- app.services.wiki.source_sync.runner::run_wiki_source_sync (POS: wiki pull orchestration)

[OUTPUT]
- WikiSourceSyncJobRunner: cron adapter for __wiki_source_sync__ router command

[POS]
Cron adapter bridging harness RouterJobRunner to deterministic wiki source sync.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.cron.runners import RouterJobRunner
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult

logger = logging.getLogger(__name__)

WIKI_SOURCE_SYNC_COMMAND = "__wiki_source_sync__"


class WikiSourceSyncJobRunner:
    """Runs deterministic wiki source sync for router cron jobs."""

    def __init__(self) -> None:
        self._passthrough = RouterJobRunner()

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        if job.command != WIKI_SOURCE_SYNC_COMMAND:
            return await self._passthrough.run(job, context=context)

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
