"""Daily review journal ingest into wiki raw/ (verbatim evidence + compile enqueue).

[INPUT]
- app.services.wiki.source_sync.publish_helpers (POS: publish_raw frontmatter + path sanitize)
- myrm_agent_harness.toolkits.wiki.pipeline.raw_gate (POS: raw publication gate)
- app.services.wiki.memory_to_wiki::MemoryToWikiArchiver (POS: vault + compiler)

[OUTPUT]
- ingest_daily_review_text(): verbatim raw publish + compile enqueue
- DAILY_REVIEW_RAW_DIR: raw subdirectory SSOT for daily review journals

[POS]
REST entry for POST /wiki/daily-review. The review text is stored verbatim as
raw evidence under raw/DailyReview/ and enqueued for four-dimension compilation;
generated articles always land in the HITL pending box (fail-closed publish gate).
Cache invalidation and the vault git snapshot are owned by the endpoint mutation hook.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import RawConflictPolicy, RawPublishRequest, publish_raw

from app.services.wiki.daily_review.schemas import DailyReviewIngestResult
from app.services.wiki.source_sync.publish_helpers import build_frontmatter, sanitize_path_segment

if TYPE_CHECKING:
    from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)

DAILY_REVIEW_RAW_DIR = "DailyReview"
_DEFAULT_SLUG = "review"


def _review_raw_relative_path(title: str) -> str:
    """Deterministic per-day path: same-day retry with the same title stays idempotent."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    slug = sanitize_path_segment(title) if title.strip() else _DEFAULT_SLUG
    return f"{DAILY_REVIEW_RAW_DIR}/{today}_{slug}.md"


async def ingest_daily_review_text(
    archiver: MemoryToWikiArchiver,
    *,
    text: str,
    title: str = "",
) -> DailyReviewIngestResult:
    """Store one daily-review entry verbatim into raw/DailyReview and enqueue compilation."""
    relative_path = _review_raw_relative_path(title)
    frontmatter = build_frontmatter(
        source="daily-review",
        title=title.strip() or "Daily Review",
        external_id=relative_path,
    )

    try:
        result = await publish_raw(
            archiver._structure,
            RawPublishRequest(
                relative_path=relative_path,
                content=f"{frontmatter}{text}",
                conflict_policy=RawConflictPolicy.SKIP,
            ),
            caller="settings",
        )
    except Exception as exc:
        logger.error("Daily review raw publish failed for %s: %s", relative_path, exc)
        return DailyReviewIngestResult(success=False, message=f"Raw publish failed: {exc}")

    if result.security_blocked:
        return DailyReviewIngestResult(
            success=False,
            raw_relative_path=relative_path,
            security_blocked=True,
            message="Daily review rejected by the raw security scan.",
        )
    if result.conflict_skipped or not result.written:
        return DailyReviewIngestResult(
            success=True,
            raw_relative_path=relative_path,
            skipped=True,
            message="Daily review already ingested today (skipped duplicate).",
        )

    archiver._compiler.enqueue_file(result.absolute_path)
    logger.info("Daily review ingested: %s (enqueued for compilation)", relative_path)
    return DailyReviewIngestResult(
        success=True,
        raw_relative_path=relative_path,
        enqueued=True,
        message="Daily review stored as verbatim evidence and enqueued for compilation.",
    )


__all__ = ["DAILY_REVIEW_RAW_DIR", "ingest_daily_review_text"]
