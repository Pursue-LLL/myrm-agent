"""Wiki maintain orchestration SSOT for REST and cron.

[INPUT]
- app.services.wiki.vault::get_wiki_archiver (POS: shared archiver accessor)
- app.services.wiki.maintain.state_store (POS: wikiMaintainState persistence)
- app.services.wiki.maintain.reporting (POS: issue payloads, cron summary and weekly report texts)
- app.services.wiki.maintain.run_registry (POS: single flight + live state of the run of a vault scope)
- myrm_agent_harness.toolkits.wiki.core.types::LintIssue (POS: maintenance issue DTO)
- myrm_agent_harness.toolkits.wiki.maintenance.modes::MaintainMode (POS: structural vs full)
- myrm_agent_harness.toolkits.wiki.maintenance.progress::MaintainProgressCallback (POS: LLM phase progress observer)

[OUTPUT]
- run_wiki_maintain_job: blocking maintain run for cron (one run per vault scope) + state persistence + summary text
- schedule_wiki_maintain: background maintain run for POST /wiki/maintain, or the run already in flight
- WikiMaintainScheduleResult: the run to watch, or why none was started

[POS]
Server SSOT bridging POST /wiki/maintain and router cron __wiki_maintain__ commands. Both go through one
single flight per vault scope: a full run takes minutes and two runs on the same vault only pay twice.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.wiki.core.types import LintIssue
from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode
from myrm_agent_harness.toolkits.wiki.maintenance.progress import MaintainProgressCallback

from app.database.connection import get_session
from app.services.wiki.maintain.reporting import build_list_only_report, build_summary_text, lint_issue_payloads
from app.services.wiki.maintain.run_registry import (
    MaintainRun,
    get_wiki_maintain_run,
    start_wiki_maintain_run,
)
from app.services.wiki.maintain.schemas import (
    WikiMaintainModeLiteral,
    WikiMaintainRunResult,
)
from app.services.wiki.maintain.state_store import (
    save_wiki_maintain_state,
    state_from_run_result,
)

if TYPE_CHECKING:
    from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)

_COMPILE_BUSY_REASON = "compile_in_progress"
_MAINTAIN_BUSY_REASON = "maintain_in_progress"

# A full run is up to 25 sequential model calls of 12-60s each; the cap only frees the vault when a provider hangs.
_RUN_TIMEOUT_SECONDS = 45 * 60


@dataclass(frozen=True, slots=True)
class WikiMaintainScheduleResult:
    """The run to watch, or why no run was started."""

    run: MaintainRun | None = None
    skipped_reason: str | None = None


def _mode_literal(mode: MaintainMode | str) -> WikiMaintainModeLiteral:
    if isinstance(mode, str) and mode == "list_only":
        return "list_only"
    if mode == MaintainMode.FULL or mode == "full":
        return "full"
    return "structural"


def _compile_is_busy(archiver: MemoryToWikiArchiver) -> bool:
    processing = archiver._queue.get_stats().get("processing", 0)
    return isinstance(processing, int) and processing > 0


async def _save_state(result: WikiMaintainRunResult, agent_id: str | None) -> None:
    async with get_session() as db:
        await save_wiki_maintain_state(db, state_from_run_result(result), agent_id=agent_id)


def _silent_skip(mode: WikiMaintainModeLiteral, reason: str) -> WikiMaintainRunResult:
    return WikiMaintainRunResult(skipped=True, skipped_reason=reason, mode=mode, summary_text="[SILENT]")


def _persist_health_snapshot(
    archiver: MemoryToWikiArchiver,
    agent_id: str | None,
    *,
    mode: Literal["structural", "full"],
    issues: Sequence[LintIssue],
) -> None:
    from app.services.wiki.dedup_runner import get_wiki_dedup_stats
    from app.services.wiki.health_report_service import persist_wiki_health_snapshot, report_from_lint_issues

    report = report_from_lint_issues(
        mode=mode,
        issues=list(issues),
        duplicate_groups_pending=get_wiki_dedup_stats(agent_id=agent_id).duplicate_groups_pending,
        synthesis_pending=archiver._pending_mgr.count_synthesis_pending(),
    )
    persist_wiki_health_snapshot(archiver._structure, report)


async def _list_issues(archiver: MemoryToWikiArchiver, agent_id: str | None) -> WikiMaintainRunResult:
    """Read-only structural listing: nothing is repaired and the model is not asked."""
    from myrm_agent_harness.toolkits.wiki.maintenance.issue_kind import count_open_actions

    start_t = time.perf_counter()
    issues, _ = await archiver._linter.scan(mode=MaintainMode.STRUCTURAL, include_raw_security=False)
    duration_ms = int((time.perf_counter() - start_t) * 1000)
    _persist_health_snapshot(archiver, agent_id, mode="structural", issues=issues)
    return WikiMaintainRunResult(
        mode="list_only",
        issues_found=len(issues),
        duration_ms=duration_ms,
        open_actions_count=count_open_actions(issues),
        lint_issues=lint_issue_payloads(issues),
        summary_text=build_list_only_report(issues),
    )


async def _lint_and_maintain(
    archiver: MemoryToWikiArchiver,
    agent_id: str | None,
    *,
    mode: Literal["structural", "full"],
    on_progress: MaintainProgressCallback | None,
    stop: asyncio.Event | None,
) -> WikiMaintainRunResult:
    from myrm_agent_harness.toolkits.wiki.maintenance.issue_kind import count_open_actions

    from app.services.wiki.asset_index_service import run_wiki_asset_index
    from app.services.wiki.vault import after_wiki_vault_mutation

    maintain_mode = MaintainMode.FULL if mode == "full" else MaintainMode.STRUCTURAL
    lint_result = await archiver._linter.lint_and_maintain(mode=maintain_mode, on_progress=on_progress, stop=stop)
    await run_wiki_asset_index(archiver)
    await after_wiki_vault_mutation(archiver, "maintain")
    _persist_health_snapshot(archiver, agent_id, mode=mode, issues=lint_result.issues)

    result = WikiMaintainRunResult(
        mode=mode,
        issues_found=lint_result.issues_found,
        issues_fixed=lint_result.issues_fixed,
        connections_discovered=lint_result.connections_discovered,
        duration_ms=lint_result.duration_ms,
        open_actions_count=count_open_actions(lint_result.issues),
        raw_security_removed=lint_result.raw_security_removed,
        raw_security_removed_paths=list(lint_result.raw_security_removed_paths),
        lint_issues=lint_issue_payloads(lint_result.issues),
        ai_unavailable=lint_result.ai_unavailable,
        cancelled=lint_result.stopped,
    )
    result.summary_text = build_summary_text(result)
    return result


async def _run_maintain_pipeline(
    *,
    llm: BaseChatModel,
    agent_id: str | None = None,
    mode: MaintainMode | str = MaintainMode.STRUCTURAL,
    on_progress: MaintainProgressCallback | None = None,
    stop: asyncio.Event | None = None,
) -> WikiMaintainRunResult:
    from app.services.wiki.vault import get_wiki_archiver

    mode_literal = _mode_literal(mode)
    archiver = get_wiki_archiver(llm, agent_id=agent_id)
    if _compile_is_busy(archiver):
        skipped = _silent_skip(mode_literal, _COMPILE_BUSY_REASON)
        await _save_state(skipped, agent_id)
        return skipped

    try:
        if mode_literal == "list_only":
            result = await _list_issues(archiver, agent_id)
        else:
            result = await _lint_and_maintain(archiver, agent_id, mode=mode_literal, on_progress=on_progress, stop=stop)
    except Exception as exc:
        logger.error("Wiki maintain job failed for agent %s: %s", agent_id, exc)
        failed = WikiMaintainRunResult(
            skipped=True,
            skipped_reason=str(exc),
            mode=mode_literal,
            summary_text=f"Wiki maintain failed: {exc}",
        )
        await _save_state(failed, agent_id)
        raise
    await _save_state(result, agent_id)
    return result


async def _execute_run(
    run: MaintainRun,
    *,
    llm: BaseChatModel,
    agent_id: str | None,
) -> WikiMaintainRunResult:
    """Run the pipeline under the time cap and record the outcome on ``run``; a failure is re-raised."""
    budget = asyncio.timeout(_RUN_TIMEOUT_SECONDS)
    try:
        async with budget:
            result = await _run_maintain_pipeline(
                llm=llm,
                agent_id=agent_id,
                mode=run.mode,
                on_progress=run.on_progress,
                stop=run.stop,
            )
    except TimeoutError:
        if budget.expired():
            logger.warning("Wiki maintain for agent %s stopped after %ss", agent_id, _RUN_TIMEOUT_SECONDS)
            run.fail("maintain_timeout")
        else:
            run.fail("maintain_failed")
        raise
    except BaseException:
        run.fail("maintain_failed")
        raise
    if result.skipped and result.skipped_reason == _COMPILE_BUSY_REASON:
        run.fail("compile_in_progress")
    else:
        run.finish(result)
    return result


async def _run_in_background(run: MaintainRun, *, llm: BaseChatModel, agent_id: str | None) -> None:
    # Nobody awaits this task: the outcome is on the run, and the pipeline has already logged a failure.
    with contextlib.suppress(Exception):
        await _execute_run(run, llm=llm, agent_id=agent_id)


async def run_wiki_maintain_job(
    *,
    llm: BaseChatModel,
    agent_id: str | None = None,
    mode: MaintainMode | str = MaintainMode.STRUCTURAL,
) -> WikiMaintainRunResult:
    """Run maintenance to the end (cron); skipped silently while another run holds the vault."""
    mode_literal = _mode_literal(mode)
    if mode_literal == "list_only":
        # Read-only health listing: it neither costs model calls nor competes with a running maintenance.
        return await _run_maintain_pipeline(llm=llm, agent_id=agent_id, mode=mode_literal)

    run = start_wiki_maintain_run(agent_id, mode_literal)
    if run is None:
        return _silent_skip(mode_literal, _MAINTAIN_BUSY_REASON)
    return await _execute_run(run, llm=llm, agent_id=agent_id)


def schedule_wiki_maintain(
    *,
    llm: BaseChatModel,
    agent_id: str | None = None,
    mode: MaintainMode = MaintainMode.STRUCTURAL,
) -> WikiMaintainScheduleResult:
    """Start a background run, or hand back the run already in flight for this vault."""
    from app.services.wiki.vault import get_wiki_archiver

    if _compile_is_busy(get_wiki_archiver(llm, agent_id=agent_id)):
        return WikiMaintainScheduleResult(skipped_reason=_COMPILE_BUSY_REASON)

    run = start_wiki_maintain_run(agent_id, "full" if mode == MaintainMode.FULL else "structural")
    if run is None:
        return WikiMaintainScheduleResult(run=get_wiki_maintain_run(agent_id))
    run.task = asyncio.create_task(_run_in_background(run, llm=llm, agent_id=agent_id))
    return WikiMaintainScheduleResult(run=run)
