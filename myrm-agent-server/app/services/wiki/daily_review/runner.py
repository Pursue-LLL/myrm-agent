"""Daily review compounding cron runner.

[INPUT]
- app.services.wiki.vault (POS: shared archiver + vault path SSOT)
- app.services.wiki.daily_review.ingest (POS: DAILY_REVIEW_RAW_DIR SSOT)
- myrm_agent_harness.toolkits.wiki::WikiStructure (POS: vault filesystem abstraction)
- myrm_agent_harness.toolkits.wiki::WikiPendingEditsManager (POS: HITL pending review draft manager)

[OUTPUT]
- run_wiki_daily_review_compound_job(): 24h-window review digest + stuck-queue rescue compile + HITL summary

[POS]
Router-mode cron entry for __wiki_daily_review_compound__. Reports review journals ingested
within the last 24h so evening and overnight writers are always covered, rescues a
stalled compile queue (compile_all when idle), and summarizes the drafts the window
produced regardless of review status (approved/rejected drafts keep counting so numbers
reflect real output, not just what is still queued). Reply [SILENT] when no review was
ingested within the window.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.services.wiki.daily_review.ingest import DAILY_REVIEW_RAW_DIR
from app.services.wiki.daily_review.schemas import WikiDailyReviewCompoundResult

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki import WikiPendingEditsManager
    from myrm_agent_harness.toolkits.wiki.pipeline.pending import PendingWikiEdit

logger = logging.getLogger(__name__)

_DIMENSIONS = ("Projects", "Knowledge", "Methods", "Comparisons")
_SILENT = "[SILENT]"
# One daily cron cycle: anything ingested since the previous run is reported by the
# next run exactly once, independent of calendar-day or timezone boundaries.
_REPORT_WINDOW = timedelta(hours=24)
# Window-stat page size; exhausting pages keeps the breakdown exact at any volume.
_STATS_PAGE_SIZE = 500


def _window_cutoffs() -> tuple[float, str]:
    """(epoch cutoff for file mtime, SQLite UTC timestamp cutoff for created_at)."""
    now = datetime.now(UTC)
    return (
        now.timestamp() - _REPORT_WINDOW.total_seconds(),
        (now - _REPORT_WINDOW).strftime("%Y-%m-%d %H:%M:%S"),
    )


def _list_window_review_files(structure: WikiStructure, epoch_cutoff: float) -> list[str]:
    """Review files ingested within the window (mtime), from any calendar day."""
    review_dir = structure.raw_dir / DAILY_REVIEW_RAW_DIR
    if not review_dir.is_dir():
        return []
    return sorted(
        path.name
        for path in review_dir.glob("*.md")
        if path.stat().st_mtime >= epoch_cutoff
    )


def _window_draft_stats(
    pending_mgr: WikiPendingEditsManager, iso_cutoff: str
) -> tuple[dict[str, int], int, int]:
    """Count window-produced drafts per dimension plus out-of-dimension and box totals.

    Status-agnostic (approved/rejected drafts keep counting) and deduped per concept:
    add_pending_edit replaces same-concept drafts, so a recompiled concept must not be
    counted twice within one window. Pages are exhausted so the breakdown always
    matches the exact box total, even in bulk-compile storms.
    """
    # Rows arrive newest-first; keep the newest draft per concept name.
    latest_per_concept: dict[str, PendingWikiEdit] = {}
    page_offset = 0
    while True:
        page = pending_mgr.get_edits_created_since(iso_cutoff, limit=_STATS_PAGE_SIZE, offset=page_offset)
        for edit in page:
            latest_per_concept.setdefault(edit["concept_name"], edit)
        if len(page) < _STATS_PAGE_SIZE:
            break
        page_offset += _STATS_PAGE_SIZE
    counts = {dimension: 0 for dimension in _DIMENSIONS}
    other_drafts = 0
    for edit in latest_per_concept.values():
        first_segment = edit["concept_name"].split("/", 1)[0]
        if first_segment in counts:
            counts[first_segment] += 1
        else:
            other_drafts += 1
    # Exact box size: get_pending_edits caps at 50 rows, get_stats does not.
    total_drafts = pending_mgr.get_stats().get("pending", 0)
    return counts, other_drafts, total_drafts


async def run_wiki_daily_review_compound_job(
    *,
    llm: BaseChatModel | None,
    agent_id: str | None = None,
) -> WikiDailyReviewCompoundResult:
    """Summarize the window's daily-review compounding; rescue a stalled compile queue."""
    from app.services.wiki.vault import get_wiki_archiver

    archiver = None
    if llm is not None:
        archiver = get_wiki_archiver(llm, agent_id=agent_id)
        structure = archiver._structure
    else:
        from app.services.wiki.vault import resolve_wiki_vault_path

        structure = WikiStructure(resolve_wiki_vault_path(agent_id))

    epoch_cutoff, iso_cutoff = _window_cutoffs()
    window_files = _list_window_review_files(structure, epoch_cutoff)
    if not window_files:
        return WikiDailyReviewCompoundResult(summary_text=_SILENT)

    queue_stats = archiver._queue.get_stats() if archiver is not None else {}
    pending_compiles = int(queue_stats.get("pending", 0))
    processing_compiles = int(queue_stats.get("processing", 0))

    compiles_forced = False
    if (
        archiver is not None
        and llm is not None
        and pending_compiles > 0
        and processing_compiles == 0
    ):
        # Stalled-queue rescue: the background worker is idle while items remain queued.
        logger.info("Daily review compounding: rescuing %d stalled compile item(s)", pending_compiles)
        await archiver._compiler.compile_all()
        compiles_forced = True
        queue_stats = archiver._queue.get_stats()
        pending_compiles = int(queue_stats.get("pending", 0))
        processing_compiles = int(queue_stats.get("processing", 0))

    if archiver is None:
        dimension_counts, other_drafts, total_drafts = {}, 0, 0
    else:
        dimension_counts, other_drafts, total_drafts = _window_draft_stats(
            archiver._pending_mgr, iso_cutoff
        )
    window_drafts = sum(dimension_counts.values()) + other_drafts

    dimension_parts = [f"{name} {count}" for name, count in dimension_counts.items() if count > 0]
    if other_drafts > 0:
        dimension_parts.append(f"other {other_drafts}")
    dimensions_text = ", ".join(dimension_parts) if dimension_parts else "none"

    if llm is None:
        summary_text = (
            f"Daily review compounding: {len(window_files)} journal(s) stored as evidence in the "
            "last 24h (no LLM configured; compilation deferred until a model is available)"
        )
    else:
        summary_text = (
            f"Daily review compounding: {len(window_files)} journal(s) ingested in the last 24h; "
            f"{window_drafts} draft(s) produced ({dimensions_text}); "
            f"{total_drafts} draft(s) currently awaiting review."
        )
        if pending_compiles > 0 or processing_compiles > 0:
            summary_text += f" {pending_compiles + processing_compiles} compile(s) still queued."
        # Cron output renders as plain text in every surface (run history, push feed),
        # so the pending panel is referenced by URL only, never as a markdown link.
        summary_text += " Review them at /settings/knowledge?wikiTab=pendingEdits."

    return WikiDailyReviewCompoundResult(
        summary_text=summary_text,
        recent_review_files=len(window_files),
        pending_compiles=pending_compiles,
        processing_compiles=processing_compiles,
        window_drafts=window_drafts,
        dimension_counts=dimension_counts,
        total_pending_drafts=total_drafts,
        compiles_forced=compiles_forced,
    )


__all__ = ["run_wiki_daily_review_compound_job"]
