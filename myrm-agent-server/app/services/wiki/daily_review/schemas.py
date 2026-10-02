"""Daily review domain DTOs.

[INPUT]
- (pure dataclasses)

[OUTPUT]
- DailyReviewIngestResult / WikiDailyReviewCompoundResult

[POS]
DTOs for the daily-review ingest path (REST) and the compounding cron summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DailyReviewIngestResult:
    """Outcome of ingesting one daily-review journal entry into raw/."""

    success: bool
    raw_relative_path: str = ""
    skipped: bool = False
    security_blocked: bool = False
    enqueued: bool = False
    message: str = ""


@dataclass(frozen=True, slots=True)
class WikiDailyReviewCompoundResult:
    """Summary of the daily-review compounding cron run (24h window semantics)."""

    summary_text: str
    recent_review_files: int = 0
    pending_compiles: int = 0
    processing_compiles: int = 0
    window_drafts: int = 0
    dimension_counts: dict[str, int] = field(default_factory=dict)
    total_pending_drafts: int = 0
    compiles_forced: bool = False


__all__ = [
    "DailyReviewIngestResult",
    "WikiDailyReviewCompoundResult",
]
