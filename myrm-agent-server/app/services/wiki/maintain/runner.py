"""Wiki maintain orchestration SSOT for REST and cron.

[INPUT]
- app.services.wiki.vault::get_wiki_archiver (POS: shared archiver accessor)
- app.services.wiki.maintain.state_store (POS: wikiMaintainState persistence)
- myrm_agent_harness.toolkits.wiki.maintenance.modes::MaintainMode (POS: structural vs full)

[OUTPUT]
- run_wiki_maintain_job: deterministic maintain pipeline + state persistence + cron summary text

[POS]
Server SSOT bridging POST /wiki/maintain and router cron __wiki_maintain__ commands.
"""

from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode

from app.database.connection import get_session
from app.services.wiki.maintain.schemas import (
    WikiMaintainModeLiteral,
    WikiMaintainRunResult,
)
from app.services.wiki.maintain.state_store import (
    save_wiki_maintain_state,
    state_from_run_result,
)

logger = logging.getLogger(__name__)

_COMPILE_BUSY_REASON = "compile_in_progress"
_NO_LLM_REASON = "no_llm_configured"


def _build_list_only_report(*, issues: list[object]) -> str:
    from myrm_agent_harness.toolkits.wiki.core.types import LintIssue

    lint_issues: list[LintIssue] = [item for item in issues if isinstance(item, LintIssue)]
    if not lint_issues:
        return (
            "## 📋 Wiki 知识库健康周检报告\n\n"
            "✅ **全库状态极佳**：未发现断链、陈旧事实或格式异常。\n\n"
            "— [在知识库治理面板中查看详情](/settings/knowledge)"
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

    lines.append("\n👉 [在知识库设置中查看全量诊断与治理](/settings/knowledge)")
    return "\n".join(lines)


def _build_summary_text(*, result: WikiMaintainRunResult) -> str:
    if result.mode == "list_only":
        return result.summary_text

    if result.skipped:
        if result.skipped_reason == _COMPILE_BUSY_REASON:
            return "[SILENT]"
        if result.skipped_reason == _NO_LLM_REASON:
            return "[SILENT]"
        return f"Wiki maintain skipped: {result.skipped_reason}"

    changed = result.issues_fixed > 0 or result.connections_discovered > 0 or result.raw_security_removed > 0
    if not changed:
        return "[SILENT]"

    parts = [
        f"Wiki maintain ({result.mode}): {result.issues_found} issue(s)",
        f"{result.issues_fixed} fixed",
    ]
    if result.connections_discovered > 0:
        parts.append(f"{result.connections_discovered} new link(s)")
    if result.raw_security_removed > 0:
        parts.append(f"{result.raw_security_removed} raw file(s) removed")
    return ", ".join(parts)


async def run_wiki_maintain_job(
    *,
    llm: BaseChatModel | None,
    agent_id: str | None = None,
    mode: MaintainMode | str = MaintainMode.STRUCTURAL,
) -> WikiMaintainRunResult:
    if isinstance(mode, str) and mode == "list_only":
        mode_literal: WikiMaintainModeLiteral = "list_only"
    elif mode == MaintainMode.FULL or mode == "full":
        mode_literal = "full"
    else:
        mode_literal = "structural"

    if llm is None and mode_literal != "list_only":
        skipped = WikiMaintainRunResult(
            skipped=True,
            skipped_reason=_NO_LLM_REASON,
            mode=mode_literal,
            summary_text="[SILENT]",
        )
        async with get_session() as db:
            await save_wiki_maintain_state(db, state_from_run_result(skipped), agent_id=agent_id)
        return skipped

    from app.services.wiki.asset_index_service import run_wiki_asset_index
    from app.services.wiki.vault import after_wiki_vault_mutation, get_wiki_archiver

    archiver = get_wiki_archiver(llm, agent_id=agent_id)
    queue_stats = archiver._queue.get_stats()
    processing = queue_stats.get("processing", 0)
    if isinstance(processing, int) and processing > 0:
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
            import time

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

            lint_issue_payloads = [
                {
                    "issue_type": item.issue_type,
                    "severity": item.severity,
                    "location": item.location,
                    "description": item.description,
                    "action_kind": item.action_kind,
                    "suggested_fix": item.suggested_fix,
                }
                for item in scanned_issues[:200]
            ]

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
                lint_issues=lint_issue_payloads,
                summary_text=summary_text,
            )
            async with get_session() as db:
                await save_wiki_maintain_state(db, state_from_run_result(result), agent_id=agent_id)
            return result

        maintain_enum = MaintainMode.FULL if mode_literal == "full" else MaintainMode.STRUCTURAL
        lint_result = await archiver._linter.lint_and_maintain(mode=maintain_enum)
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

        lint_issue_payloads = [
            {
                "issue_type": item.issue_type,
                "severity": item.severity,
                "location": item.location,
                "description": item.description,
                "action_kind": item.action_kind,
                "suggested_fix": item.suggested_fix,
            }
            for item in lint_result.issues[:200]
        ]

        result = WikiMaintainRunResult(
            mode=mode_literal,
            issues_found=lint_result.issues_found,
            issues_fixed=lint_result.issues_fixed,
            connections_discovered=lint_result.connections_discovered,
            duration_ms=lint_result.duration_ms,
            open_actions_count=count_open_actions(lint_result.issues),
            raw_security_removed=lint_result.raw_security_removed,
            raw_security_removed_paths=list(lint_result.raw_security_removed_paths),
            lint_issues=lint_issue_payloads,
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
