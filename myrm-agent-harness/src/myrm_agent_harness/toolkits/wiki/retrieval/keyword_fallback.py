"""Keyword fallback for wiki query - published pages only.

[INPUT]
- ..core.frontmatter_contract::WikiPublishStatus, resolve_publish_status (POS: publish_status SSOT)
- .tokenizer::extract_query_terms (POS: normalized query terms shared with index routing)
- myrm_agent_harness.utils.logger_utils::get_agent_logger (POS: logger)

[OUTPUT]
- is_published_article: Whether a page is readable and published
- keyword_search: Rank published pages by query-term overlap

[POS]
Retrieval paths that do not go through the FTS5 index (keyword matching when semantic retrieval
returns nothing, graph expansion) read page files directly. Draft and blocked pages stay out of an
answer there exactly as they stay out of the FTS5 index; a page without a publish_status counts as
published.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.utils.logger_utils import get_agent_logger

from ..core.frontmatter_contract import WikiPublishStatus, resolve_publish_status
from .tokenizer import extract_query_terms

logger = get_agent_logger(__name__)


def is_published_article(path: Path) -> bool:
    """Whether the page is readable and published."""
    try:
        return resolve_publish_status(path.read_text(encoding="utf-8")) is WikiPublishStatus.PUBLISHED
    except OSError:
        return False


def keyword_search(query: str, concepts: list[Path], top_n: int) -> list[Path]:
    """Score published concepts by keyword overlap with query."""
    query_keywords = extract_query_terms(query)
    scored: list[tuple[Path, float]] = []

    for concept_path in concepts:
        try:
            content = concept_path.read_text(encoding="utf-8")
            if resolve_publish_status(content) is not WikiPublishStatus.PUBLISHED:
                continue
            content_keywords = extract_query_terms(content)
            overlap = len(query_keywords & content_keywords)
            score = overlap / max(len(query_keywords), 1)
            if score > 0:
                scored.append((concept_path, score))
        except Exception as e:
            logger.warning("Failed to read %s: %s", concept_path, e)

    scored.sort(key=lambda x: x[1], reverse=True)
    return [path for path, _ in scored[:top_n]]
