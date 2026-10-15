"""Wiki maintain orchestration SSOT for REST and cron.

[INPUT]
- app.services.wiki.vault::get_wiki_archiver (POS: shared archiver accessor)
- app.services.wiki.maintain.state_store (POS: wikiMaintainState persistence)
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
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.wiki.core.types import LintIssue
from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode
from myrm_agent_harness.toolkits.wiki.maintenance.progress import MaintainProgressCallback

from app.database.connection import get_session
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
# Issues listed in a run result; the counters still cover all of them.
_MAX_REPORTED_ISSUES = 200


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


def _lint_issue_payloads(issues: Sequence[LintIssue]) -> list[dict[str, object]]:
    return [
        {
            "issue_type": item.issue_type,
            "severity": item.severity,
            "location": item.location,
            "description": item.description,
            "action_kind": item.action_kind,
            "suggested_fix": item.suggested_fix,
        }
        for item in issues[:_MAX_REPORTED_ISSUES]
    ]


def _build_list_only_report(*, issues: Sequence[object]) -> str:
    lint_issues: list[LintIssue] = [item for item in issues if isinstance(item, LintIssue)]
    if not lint_issues:
        return (
            "## 📋 Wiki 知识库健康周检报告\n\n"
            "✅ **全库状态极佳**：未发现断链、陈旧事实或格式异常。\n\n"
            "— [在知识库治理面板中查看详情](/settings/wiki)"
        )

    broken_links = [i for i in lint_issues if i.issue_type in ("broken_link", "broken_wikilink")]
    stale_files = [i for i in lint_issues if i.issue_type == "stale"]
    invalid_types = [i for i in lint_issues if i.issue_type == "invalid_frontmatter_type"]
    provenance_gaps = [i for i in lint_issues if i.issue_type == "provenance_gap"]
    incomplete = [i for i in lint_issues if i.issue_type == "incomplete"]
    other_issues = [
        i
        for i in lint_issues
        if i.issue_type
        not in (
            "broken_link",
            "broken_wikilink",
            "stale",
            "invalid_frontmatter_type",
            "provenance_gap",
            "incomplete",
        )
    ]

    summary_counts: list[str] = []
    if broken_links:
        summary_counts.append(f"🔴 严重断链: {len(broken_links)} 处")
    if stale_files:
        summary_counts.append(f"🟡 事实陈旧: {len(stale_files)} 篇")
    if invalid_types:
        summary_counts.append(f"🟠 元数据异常: {len(invalid_types)} 篇")
    if provenance_gaps:
        summary_counts.append(f"⚪ 溯源缺失: {len(provenance_gaps)} 篇")
    if incomplete:
        summary_counts.append(f"⚪ 草稿/未完: {len(incomplete)} 篇")
    if other_issues:
        summary_counts.append(f"⚪ 其他项: {len(other_issues)} 篇")

    lines = [
        "## 📋 Wiki 知识库健康周检报告\n",
        f"**总计发现 {len(lint_issues)} 项待优化项**（{' · '.join(summary_counts)}）\n",
        "### 重点关注清单（Top 10）",
    ]

    for item in lint_issues[:10]:
        icon = "🔴" if item.severity == "high" else ("🟡" if item.severity == "medium" else "⚪")
        desc = item.description or item.issue_type
        lines.append(f"- {icon} `{item.location}`: {desc}")

    if len(lint_issues) > 10:
        lines.append(f"\n*(其余 {len(lint_issues) - 10} 项已收拢)*")

    lines.append("\n👉 [在知识库设置中查看全量诊断与治理](/settings/wiki)")
    return "\n".join(lines)


def _build_summary_text(*, result: WikiMaintainRunResult) -> str:
    if result.mode == "list_only":
        return result.summary_text

    if result.skipped:
        if result.skipped_reason == _COMPILE_BUSY_REASON:
            return "[SILENT]"
        return f"Wiki maintain skipped: {result.skipped_reason}"

    changed = result.issues_fixed > 0 or result.connections_discovered > 0 or result.raw_security_removed > 0
    if not changed and not result.ai_unavailable:
        return "[SILENT]"

    parts = [
        f"Wiki maintain ({result.mode}): {result.issues_found} issue(s)",
        f"{result.issues_fixed} fixed",
    ]
    if result.connections_discovered > 0:
        parts.append(f"{result.connections_discovered} new link(s)")
    if result.raw_security_removed > 0:
        parts.append(f"{result.raw_security_removed} raw file(s) removed")
    if result.ai_unavailable:
        parts.append("the AI model did not respond, so page review and link discovery were skipped")
    return ", ".join(parts)


async def _run_maintain_pipeline(
    *,
    llm: BaseChatModel | None,
    agent_id: str | None = None,
    mode: MaintainMode | str = MaintainMode.STRUCTURAL,
    on_progress: MaintainProgressCallback | None = None,
) -> WikiMaintainRunResult:
    mode_literal = _mode_literal(mode)

    from app.services.wiki.asset_index_service import run_wiki_asset_index
    from app.services.wiki.vault import after_wiki_vault_mutation, get_wiki_archiver

    # The read-only listing needs no model, so ``llm`` may be None here.
    archiver = get_wiki_archiver(llm, agent_id=agent_id)  # type: ignore[arg-type]
    if _compile_is_busy(archiver):
        skipped = WikiMaintainRunResult(
            skipped=True,
            skipped_reason=_COMPILE_BUSY_REASON,
            mode=mode_literal,
            summary_text="[SILENT]",
        )
        async with get_session() as db:
            await save_wiki_maintain_state(db, state_from_run_result(skipped), agent_id=agent_id)
        return skipped

    try:
        from myrm_agent_harness.toolkits.wiki.maintenance.issue_kind import (
            count_open_actions,
        )

        from app.services.wiki.dedup_runner import get_wiki_dedup_stats
        from app.services.wiki.health_report_service import (
            persist_wiki_health_snapshot,
            report_from_lint_issues,
        )

        if mode_literal == "list_only":
            start_t = time.perf_counter()
            scanned_issues, _ = await archiver._linter.scan(
                mode=MaintainMode.STRUCTURAL,
                include_raw_security=False,
            )
            duration_ms = int((time.perf_counter() - start_t) * 1000)

            dedup = get_wiki_dedup_stats(agent_id=agent_id)
            health_report = report_from_lint_issues(
                mode="structural",
                issues=list(scanned_issues),
                duplicate_groups_pending=dedup.duplicate_groups_pending,
                synthesis_pending=archiver._pending_mgr.count_synthesis_pending(),
            )
            persist_wiki_health_snapshot(archiver._structure, health_report)

            summary_text = _build_list_only_report(issues=scanned_issues)

            result = WikiMaintainRunResult(
                mode="list_only",
                issues_found=len(scanned_issues),
                issues_fixed=0,
                connections_discovered=0,
                duration_ms=duration_ms,
                open_actions_count=count_open_actions(scanned_issues),
                raw_security_removed=0,
                raw_security_removed_paths=[],
                lint_issues=_lint_issue_payloads(scanned_issues),
                summary_text=summary_text,
            )
            async with get_session() as db:
                await save_wiki_maintain_state(db, state_from_run_result(result), agent_id=agent_id)
            return result

        maintain_enum = MaintainMode.FULL if mode_literal == "full" else MaintainMode.STRUCTURAL
        lint_result = await archiver._linter.lint_and_maintain(mode=maintain_enum, on_progress=on_progress)
        await run_wiki_asset_index(archiver)
        await after_wiki_vault_mutation(archiver, "maintain")

        dedup = get_wiki_dedup_stats(agent_id=agent_id)
        health_report = report_from_lint_issues(
            mode="full" if mode_literal == "full" else "structural",
            issues=list(lint_result.issues),
            duplicate_groups_pending=dedup.duplicate_groups_pending,
            synthesis_pending=archiver._pending_mgr.count_synthesis_pending(),
        )
        persist_wiki_health_snapshot(archiver._structure, health_report)

        result = WikiMaintainRunResult(
            mode=mode_literal,
            issues_found=lint_result.issues_found,
            issues_fixed=lint_result.issues_fixed,
            connections_discovered=lint_result.connections_discovered,
            duration_ms=lint_result.duration_ms,
            open_actions_count=count_open_actions(lint_result.issues),
            raw_security_removed=lint_result.raw_security_removed,
            raw_security_removed_paths=list(lint_result.raw_security_removed_paths),
            lint_issues=_lint_issue_payloads(lint_result.issues),
            ai_unavailable=lint_result.ai_unavailable,
        )
        result.summary_text = _build_summary_text(result=result)
        async with get_session() as db:
            await save_wiki_maintain_state(db, state_from_run_result(result), agent_id=agent_id)
        return result
    except Exception as exc:
        logger.error("Wiki maintain job failed for agent %s: %s", agent_id, exc)
        failed = WikiMaintainRunResult(
            skipped=True,
            skipped_reason=str(exc),
            mode=mode_literal,
            summary_text=f"Wiki maintain failed: {exc}",
        )
        async with get_session() as db:
            await save_wiki_maintain_state(db, state_from_run_result(failed), agent_id=agent_id)
        raise


async def _execute_run(
    run: MaintainRun,
    *,
    llm: BaseChatModel | None,
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
        run.succeed(result)
    return result


async def _run_in_background(run: MaintainRun, *, llm: BaseChatModel | None, agent_id: str | None) -> None:
    # Nobody awaits this task: the outcome is on the run, and the pipeline has already logged a failure.
    with contextlib.suppress(Exception):
        await _execute_run(run, llm=llm, agent_id=agent_id)


async def run_wiki_maintain_job(
    *,
    llm: BaseChatModel | None,
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
        return WikiMaintainRunResult(
            skipped=True,
            skipped_reason=_MAINTAIN_BUSY_REASON,
            mode=mode_literal,
            summary_text="[SILENT]",
        )
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
