"""Knowledge pack snippet selector and deduplicator.

[INPUT]
- app.services.wiki.knowledge_pack.schemas::KnowledgePackConfig, RelevantSnippet, ProactiveKnowledgeResult
- app.services.wiki.knowledge_pack.query_terms::MAX_QUERY_CHARS, search_terms, carried_terms, paragraph_relevance, tokenize_text (POS: the question's terms and the relevance floor)
- myrm_agent_harness.api::search_published_index (POS: read-only published-pages-only FTS search)
- myrm_agent_harness.toolkits.wiki.core.frontmatter_contract::WikiPublishStatus, resolve_publish_status (POS: wiki publish gate SSOT)
- myrm_agent_harness.utils.markdown_frontmatter::parse_frontmatter (POS: BOM-tolerant frontmatter parse SSOT)

[OUTPUT]
- calculate_jaccard_similarity: Fast character-ngram / word overlap for semantic dedup.
- truncate_snippet_text: Cut a snippet to a character budget at a sentence or word boundary.
- KnowledgePackSelector: Select, dedup, and enforce strict token/character budget on snippets.
- resolve_proactive_snippets_from_vaults: Retrieve and budget snippets from the shared vaults within a timeout.

[POS]
High-performance snippet selection pipeline for pre-turn proactive injection. Tier 1 asks the vault's FTS index for
its best published pages (the harness applies the publish gate inside the query, so drafts cannot crowd them out)
with an OR query of the question's search terms; tier 2 scans the markdown files of a vault that has no readable
index, because listing thousands of pages to read fifteen of them would cost more than it finds. Both tiers keep a
paragraph only when ``paragraph_relevance`` says the page answers the question, and rank it by that score, so a
question the vault does not answer injects nothing and the order of the mounted vaults never decides which page
wins. Every page file it reads goes through the wiki publish gate again, so a draft or blocked page never reaches
the injected context, and snippets never lead with the page's frontmatter.
"""

from __future__ import annotations

import asyncio
import heapq
import logging
import time
from collections.abc import Sequence
from pathlib import Path

from myrm_agent_harness.api import search_published_index
from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import WikiPublishStatus, resolve_publish_status
from myrm_agent_harness.utils.markdown_frontmatter import parse_frontmatter

from app.services.wiki.knowledge_pack.query_terms import (
    MAX_QUERY_CHARS,
    carried_terms,
    paragraph_relevance,
    search_terms,
    tokenize_text,
)
from app.services.wiki.knowledge_pack.schemas import (
    KnowledgePackConfig,
    ProactiveKnowledgeResult,
    RelevantSnippet,
)

logger = logging.getLogger(__name__)

_MAX_INDEXED_SNIPPETS = 5
_MAX_SCANNED_FILES = 15
_MAX_SCANNED_SNIPPETS = 5


def calculate_jaccard_similarity(text_a: str, text_b: str) -> float:
    """Calculate token-level Jaccard similarity for content deduplication."""
    if not text_a or not text_b:
        return 0.0
    words_a = tokenize_text(text_a)
    words_b = tokenize_text(text_b)
    if not words_a or not words_b:
        return 0.0
    intersection = words_a.intersection(words_b)
    union = words_a.union(words_b)
    return len(intersection) / len(union)


def _published_page_body(page_file: Path) -> str:
    """Body of a page that passes the wiki publish gate, without its frontmatter.

    Empty for a draft or blocked page and for a file that cannot be read: an unverifiable page is held back.
    """
    try:
        text = page_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if resolve_publish_status(text) is not WikiPublishStatus.PUBLISHED:
        return ""
    return parse_frontmatter(text)[1]


def truncate_snippet_text(text: str, max_chars: int = 200) -> str:
    """Cleanly truncate snippet text without breaking sentences abruptly."""
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    truncated = cleaned[:max_chars].strip()
    # Try to break at a sentence boundary or space
    for punct in ("。", "！", "？", "；", ". ", "! ", "? ", "; "):
        last_idx = truncated.rfind(punct)
        if last_idx > max_chars // 2:
            return truncated[: last_idx + len(punct)].strip()
    return truncated + "…"


def _paragraphs(text: str) -> list[str]:
    """The blank-line separated paragraphs of ``text``, each on one line, with markdown heading lines dropped."""
    paragraphs: list[str] = []
    for block in text.split("\n\n"):
        lines = [line.strip() for line in block.split("\n") if line.strip() and not line.strip().startswith("#")]
        if lines:
            paragraphs.append(" ".join(lines))
    return paragraphs


def _best_paragraph(text: str, terms: Sequence[str]) -> str:
    """The paragraph that carries the most search terms, the first of them on a tie.

    A text made of headings only, such as the one flat line an index row stores for a page that has no file, falls
    back to its first block as it is.
    """

    paragraphs = _paragraphs(text)
    if paragraphs:
        return max(paragraphs, key=lambda paragraph: carried_terms(terms, paragraph.lower()))
    return next((block.strip() for block in text.split("\n\n") if block.strip()), "")


def _indexed_snippets(vault_path: Path, label: str, terms: Sequence[str]) -> list[RelevantSnippet]:
    """Tier 1: the best paragraph of each published page the vault's FTS index ranks first for the question."""
    db_path = vault_path / ".wiki_index.db"
    fts_query = " OR ".join(f'"{t}"' for t in terms)
    found: list[RelevantSnippet] = []
    for concept_name, indexed_text in search_published_index(db_path, fts_query, limit=_MAX_INDEXED_SNIPPETS):
        concept_file = vault_path / "wiki" / "concepts" / f"{concept_name}.md"
        if not concept_file.is_file():
            concept_file = vault_path / f"{concept_name}.md"
        # The page file is the source of truth for its publish status; the index row's text stands in only for
        # rows that have no page file (e.g. raw sources).
        raw_content = _published_page_body(concept_file) if concept_file.is_file() else indexed_text
        best_para = _best_paragraph(raw_content, terms)
        confidence = paragraph_relevance(terms, concept_name, best_para) if best_para else 0.0
        if confidence > 0.0:
            found.append(
                RelevantSnippet(
                    kb_name=label,
                    article_title=concept_name,
                    snippet=best_para,
                    confidence=confidence,
                    source_path=str(db_path),
                )
            )
    return found


def _markdown_snippets(vault_path: Path, label: str, terms: Sequence[str]) -> list[RelevantSnippet]:
    """Tier 2: the paragraphs that answer the question in the first markdown pages of the vault, in name order."""
    concepts_dir = vault_path / "wiki" / "concepts"
    search_dir = concepts_dir if concepts_dir.is_dir() else vault_path
    # The first files by name, picked without sorting the whole listing: a vault can hold thousands of pages.
    md_files = heapq.nsmallest(_MAX_SCANNED_FILES, search_dir.glob("*.md")) or heapq.nsmallest(
        _MAX_SCANNED_FILES, vault_path.glob("*.md")
    )
    found: list[RelevantSnippet] = []
    for md_file in md_files:
        for paragraph in _paragraphs(_published_page_body(md_file)):
            confidence = paragraph_relevance(terms, md_file.stem, paragraph)
            if confidence > 0.0:
                found.append(
                    RelevantSnippet(
                        kb_name=label,
                        article_title=md_file.stem,
                        snippet=paragraph,
                        confidence=confidence,
                        source_path=str(md_file),
                    )
                )
                if len(found) >= _MAX_SCANNED_SNIPPETS:
                    break
    return found


class KnowledgePackSelector:
    """Selector that deduplicates and enforces hard budget on proactive snippets."""

    def __init__(self, config: KnowledgePackConfig | None = None) -> None:
        self._config = config or KnowledgePackConfig(
            pack_id="default",
            name="Default Knowledge Pack",
        )

    def select(
        self,
        candidates: list[RelevantSnippet],
        *,
        start_time: float | None = None,
    ) -> ProactiveKnowledgeResult:
        """Filter candidates with Jaccard deduplication and hard character budget."""
        t0 = start_time if start_time is not None else time.monotonic()
        accepted: list[RelevantSnippet] = []
        current_total_chars = 0
        is_truncated = False
        seen_texts: list[str] = []

        # Sort candidates descending by confidence
        sorted_candidates = sorted(candidates, key=lambda s: s.confidence, reverse=True)

        for candidate in sorted_candidates:
            if len(accepted) >= self._config.max_snippets:
                is_truncated = True
                break

            truncated_text = truncate_snippet_text(
                candidate.snippet,
                max_chars=self._config.max_chars_per_snippet,
            )
            if not truncated_text:
                continue

            # Check cross-source semantic duplication
            is_duplicate = False
            for seen in seen_texts:
                sim = calculate_jaccard_similarity(truncated_text, seen)
                if sim >= self._config.dedup_threshold:
                    is_duplicate = True
                    break

            if is_duplicate:
                continue

            char_cost = len(truncated_text)
            if current_total_chars + char_cost > self._config.max_total_chars:
                is_truncated = True
                break

            seen_texts.append(truncated_text)
            current_total_chars += char_cost
            accepted.append(
                RelevantSnippet(
                    kb_name=candidate.kb_name,
                    article_title=candidate.article_title,
                    snippet=truncated_text,
                    confidence=candidate.confidence,
                    source_path=candidate.source_path,
                )
            )

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        unique_kbs = {s.kb_name for s in accepted}
        return ProactiveKnowledgeResult(
            snippets=accepted,
            total_chars=current_total_chars,
            latency_ms=elapsed_ms,
            is_truncated=is_truncated,
            source_count=len(unique_kbs),
        )


async def resolve_proactive_snippets_from_vaults(
    query: str,
    vault_paths: tuple[Path, ...],
    vault_labels: dict[str, str],
    *,
    config: KnowledgePackConfig | None = None,
    timeout_seconds: float = 0.150,
) -> ProactiveKnowledgeResult:
    """Asynchronously retrieve and budget proactive snippets within timeout guardrail."""
    t0 = time.monotonic()
    selector = KnowledgePackSelector(config)

    terms = search_terms(query.strip()[:MAX_QUERY_CHARS])
    if not terms or not vault_paths:
        return ProactiveKnowledgeResult()

    candidates: list[RelevantSnippet] = []

    async def _scan_vault(vault_path: Path, label: str) -> list[RelevantSnippet]:
        if not vault_path.is_dir():
            return []

        # ── Tier 1: SQLite FTS5 index-first retrieval (O(1) ms latency) ──
        # An index answers for its vault, an empty answer included.
        db_path = vault_path / ".wiki_index.db"
        if db_path.is_file():
            try:
                return _indexed_snippets(vault_path, label, terms)
            except Exception as exc:
                logger.debug("FTS5 index scan failed for %s, falling back to markdown: %s", db_path, exc)

        # ── Tier 2: Concept markdown files fallback (for uncompiled vaults and unreadable indexes) ──
        try:
            return _markdown_snippets(vault_path, label, terms)
        except Exception as exc:
            logger.debug("Vault markdown scan skipped for %s: %s", vault_path, exc)
            return []

    try:
        tasks = [_scan_vault(p, vault_labels.get(str(p), vault_labels.get(p.name, p.name))) for p in vault_paths]
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout_seconds,
        )
        for res in results:
            if isinstance(res, list):
                candidates.extend(res)
    except asyncio.TimeoutError:
        logger.warning(
            "Proactive knowledge retrieval timed out after %.3fs, degrading gracefully",
            timeout_seconds,
        )
        return ProactiveKnowledgeResult(latency_ms=(time.monotonic() - t0) * 1000.0)
    except Exception as exc:
        logger.warning("Proactive knowledge retrieval failed: %s", exc)
        return ProactiveKnowledgeResult(latency_ms=(time.monotonic() - t0) * 1000.0)

    return selector.select(candidates, start_time=t0)
