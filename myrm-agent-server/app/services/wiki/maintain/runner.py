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
from app.services.wiki.maintain.schemas import WikiMaintainRunResult
from app.services.wiki.maintain.state_store import (
    save_wiki_maintain_state,
    state_from_run_result,
)

logger = logging.getLogger(__name__)

_COMPILE_BUSY_REASON = "compile_in_progress"
_NO_LLM_REASON = "no_llm_configured"


def _build_summary_text(*, result: WikiMaintainRunResult) -> str:
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
    mode: MaintainMode = MaintainMode.STRUCTURAL,
) -> WikiMaintainRunResult:
    mode_literal = "structural" if mode == MaintainMode.STRUCTURAL else "full"

    if llm is None:
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
        lint_result = await archiver._linter.lint_and_maintain(mode=mode)
        await run_wiki_asset_index(archiver)
        await after_wiki_vault_mutation(archiver, "maintain")

        from myrm_agent_harness.toolkits.wiki.maintenance.issue_kind import (
            count_open_actions,
        )

        from app.services.wiki.dedup_runner import get_wiki_dedup_stats
        from app.services.wiki.health_report_service import (
            persist_wiki_health_snapshot,
            report_from_lint_issues,
        )

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
