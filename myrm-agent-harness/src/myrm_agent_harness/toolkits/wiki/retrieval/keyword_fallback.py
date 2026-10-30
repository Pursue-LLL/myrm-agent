"""Keyword fallback for wiki query - published pages only.

[INPUT]
- ..core.frontmatter_contract::read_published_text (POS: published-page reader, the publish_status gate)
- .tokenizer::extract_query_terms (POS: normalized query terms shared with index routing)

[OUTPUT]
- keyword_search: Rank published pages by query-term overlap

[POS]
Keyword matching for when semantic retrieval returns nothing. It reads page files directly, so it goes
through the published-page reader: draft, blocked and unreadable pages stay out of an answer exactly as they
stay out of the FTS5 index, and a page without a publish_status counts as published.
"""

from __future__ import annotations

from pathlib import Path

from ..core.frontmatter_contract import read_published_text
from .tokenizer import extract_query_terms


def keyword_search(query: str, concepts: list[Path], top_n: int) -> list[Path]:
    """Score published concepts by keyword overlap with query."""
    query_keywords = extract_query_terms(query)
    scored: list[tuple[Path, float]] = []

    for concept_path in concepts:
        content = read_published_text(concept_path)
        if content is None:
            continue
        overlap = len(query_keywords & extract_query_terms(content))
        score = overlap / max(len(query_keywords), 1)
        if score > 0:
            scored.append((concept_path, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [path for path, _ in scored[:top_n]]
