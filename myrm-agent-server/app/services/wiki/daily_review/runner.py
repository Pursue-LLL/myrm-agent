"""Daily review compounding cron runner.

[INPUT]
- app.services.wiki.vault (POS: shared archiver + vault path SSOT)
- app.services.wiki.daily_review.ingest (POS: DAILY_REVIEW_RAW_DIR SSOT)
- myrm_agent_harness.toolkits.wiki::WikiStructure (POS: vault filesystem abstraction)

[OUTPUT]
- run_wiki_daily_review_compound_job(): today's review digest + stuck-queue rescue compile + HITL summary

[POS]
Router-mode cron entry for __wiki_daily_review_compound__. Reports today's daily-review
journals, rescues a stalled compile queue (compile_all when idle), and summarizes the
four-dimension drafts awaiting human review. Reply [SILENT] when no review was ingested.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.services.wiki.daily_review.ingest import DAILY_REVIEW_RAW_DIR
from app.services.wiki.daily_review.schemas import WikiDailyReviewCompoundResult

logger = logging.getLogger(__name__)

_DIMENSIONS = ("Projects", "Knowledge", "Methods", "Comparisons")
_SILENT = "[SILENT]"


def _today_prefix() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _list_today_review_files(structure: WikiStructure) -> list[str]:
    review_dir = structure.raw_dir / DAILY_REVIEW_RAW_DIR
    if not review_dir.is_dir():
        return []
    prefix = _today_prefix()
    return sorted(path.name for path in review_dir.glob("*.md") if path.name.startswith(prefix))


def _dimension_counts(archiver: object) -> tuple[dict[str, int], int, int]:
    """Count today's pending drafts per first-path dimension plus totals."""
    pending_mgr = getattr(archiver, "_pending_mgr", None)
    if pending_mgr is None:
        return {}, 0, 0
    today_prefix = _today_prefix()
    counts = {dimension: 0 for dimension in _DIMENSIONS}
    today_drafts = 0
    total_drafts = 0
    for edit in pending_mgr.get_pending_edits():
        total_drafts += 1
        if not str(edit.get("created_at", "")).startswith(today_prefix):
            continue
        today_drafts += 1
        first_segment = str(edit.get("concept_name", "")).split("/", 1)[0]
        if first_segment in counts:
            counts[first_segment] += 1
    return counts, today_drafts, total_drafts


async def run_wiki_daily_review_compound_job(
    *,
    llm: BaseChatModel | None,
    agent_id: str | None = None,
) -> WikiDailyReviewCompoundResult:
    """Summarize today's daily-review compounding; rescue a stalled compile queue."""
    from app.services.wiki.vault import get_wiki_archiver

    archiver = None
    if llm is not None:
        archiver = get_wiki_archiver(llm, agent_id=agent_id)
        structure = archiver._structure
    else:
        from app.services.wiki.vault import resolve_wiki_vault_path

        structure = WikiStructure(resolve_wiki_vault_path(agent_id))

    today_files = _list_today_review_files(structure)
    if not today_files:
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

    dimension_counts, today_drafts, total_drafts = (
        _dimension_counts(archiver) if archiver is not None else ({}, 0, 0)
    )

    dimension_parts = [f"{name} {count}" for name, count in dimension_counts.items() if count > 0]
    dimensions_text = " · ".join(dimension_parts) if dimension_parts else "no new drafts yet"

    if llm is None:
        summary_text = (
            f"今日复盘 {len(today_files)} 条已存为证据（未配置 LLM，编译暂缓，"
            "将在配置模型后自动编译）"
        )
    else:
        summary_text = (
            f"今日复盘 {len(today_files)} 条已入库并编译："
            f"新增 {today_drafts} 篇四维草稿待审（{dimensions_text}），"
            f"待审箱共 {total_drafts} 篇。"
        )
        if pending_compiles > 0 or processing_compiles > 0:
            summary_text += f" 队列尚有 {pending_compiles + processing_compiles} 项编译中。"
        summary_text += " [在知识库治理面板中审核](/settings/knowledge)"

    return WikiDailyReviewCompoundResult(
        summary_text=summary_text,
        today_review_files=len(today_files),
        pending_compiles=pending_compiles,
        processing_compiles=processing_compiles,
        today_pending_drafts=today_drafts,
        dimension_counts=dimension_counts,
        total_pending_drafts=total_drafts,
        compiles_forced=compiles_forced,
    )


__all__ = ["run_wiki_daily_review_compound_job"]
