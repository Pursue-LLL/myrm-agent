"""Daily review compounding domain — journal ingest, cron runner, templates, prompts.

[INPUT]
- app.services.wiki.daily_review.ingest (POS: verbatim raw ingest + compile enqueue)
- app.services.wiki.daily_review.prompts (POS: four-dimension extract prompt)
- app.services.wiki.daily_review.runner (POS: cron compounding summary SSOT)
- app.services.wiki.daily_review.schemas (POS: domain DTOs)
- app.services.wiki.daily_review.templates (POS: four standard template seeds)

[OUTPUT]
- Public facade re-exports for REST /wiki/daily-review, cron __wiki_daily_review_compound__,
  and standard template seeding.

[POS]
Domain subpackage for daily-review driven knowledge compounding. Review journals enter
verbatim via raw/DailyReview/, compile through the four-dimension routing prompt, and
always land in the HITL pending box (fail-closed publish gate).
"""

from __future__ import annotations

from app.services.wiki.daily_review.ingest import (
    DAILY_REVIEW_RAW_DIR,
    ingest_daily_review_text,
)
from app.services.wiki.daily_review.prompts import FOUR_DIMENSION_EXTRACT_PROMPT
from app.services.wiki.daily_review.runner import run_wiki_daily_review_compound_job
from app.services.wiki.daily_review.schemas import (
    DailyReviewIngestResult,
    WikiDailyReviewCompoundResult,
)
from app.services.wiki.daily_review.templates import (
    STANDARD_TEMPLATE_NAMES,
    seed_standard_templates,
    standard_templates,
)

__all__ = [
    "DAILY_REVIEW_RAW_DIR",
    "DailyReviewIngestResult",
    "FOUR_DIMENSION_EXTRACT_PROMPT",
    "STANDARD_TEMPLATE_NAMES",
    "WikiDailyReviewCompoundResult",
    "ingest_daily_review_text",
    "run_wiki_daily_review_compound_job",
    "seed_standard_templates",
    "standard_templates",
]
