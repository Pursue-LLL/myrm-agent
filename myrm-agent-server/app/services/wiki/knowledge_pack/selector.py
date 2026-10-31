"""Knowledge pack snippet selector and deduplicator.

[INPUT]
- app.services.wiki.knowledge_pack.schemas::KnowledgePackConfig, RelevantSnippet, ProactiveKnowledgeResult
- myrm_agent_harness.api::search_published_index, tokenize_for_fts (POS: read-only published-pages-only FTS search; query tokenizer)
- myrm_agent_harness.toolkits.wiki.core.frontmatter_contract::WikiPublishStatus, resolve_publish_status (POS: wiki publish gate SSOT)
- myrm_agent_harness.utils.markdown_frontmatter::parse_frontmatter (POS: BOM-tolerant frontmatter parse SSOT)

[OUTPUT]
- tokenize_text: Alphanumeric words plus CJK unigrams and bigrams of a text.
- calculate_jaccard_similarity: Fast character-ngram / word overlap for semantic dedup.
- truncate_snippet_text: Cut a snippet to a character budget at a sentence or word boundary.
- KnowledgePackSelector: Select, dedup, and enforce strict token/character budget on snippets.
- resolve_proactive_snippets_from_vaults: Retrieve and budget snippets from the shared vaults within a timeout.

[POS]
High-performance snippet selection pipeline for pre-turn proactive injection. Tier 1 asks the vault's FTS index for
its best published pages (the harness applies the publish gate inside the query, so drafts cannot crowd them out)
with an OR query of the question's first eight terms in the order they appear, so one question always becomes one
query; tier 2 scans markdown files. Every page file it reads goes through the wiki publish gate again, so a draft or
blocked page never reaches the injected context, and snippets never lead with the page's frontmatter.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path

from myrm_agent_harness.api import search_published_index, tokenize_for_fts
from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import WikiPublishStatus, resolve_publish_status
from myrm_agent_harness.utils.markdown_frontmatter import parse_frontmatter

from app.services.wiki.knowledge_pack.schemas import (
    KnowledgePackConfig,
    ProactiveKnowledgeResult,
    RelevantSnippet,
)

logger = logging.getLogger(__name__)

_EN_NUM_PATTERN = re.compile(r"[a-z0-9]+", re.ASCII)
_MAX_INDEXED_SNIPPETS = 5
_MAX_FTS_TERMS = 8


def _ordered_terms(text: str) -> list[str]:
    """Alphanumeric words plus CJK unigrams and bigrams, each once, in the order they appear in ``text``."""
    cleaned = text.lower()
    found: list[tuple[int, int, str]] = [(m.start(), 0, m.group(0)) for m in _EN_NUM_PATTERN.finditer(cleaned)]
    cjk_chars = [(i, c) for i, c in enumerate(cleaned) if "\u4e00" <= c <= "\u9fa5"]
    found.extend((i, 1, c) for i, c in cjk_chars)
    found.extend((i, 2, a + b) for (i, a), (_, b) in zip(cjk_chars, cjk_chars[1:], strict=False))
    return list(dict.fromkeys(term for _, _, term in sorted(found)))


def tokenize_text(text: str) -> set[str]:
    """Tokenize text into alphanumeric words and CJK unigrams + bigrams."""
    return set(_ordered_terms(text))


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


def _fts_match_query(query: str, terms: list[str]) -> str:
    """Tolerant FTS5 query: OR of the first ``_MAX_FTS_TERMS`` alphanumeric terms and CJK bigrams of ``terms``
    (in the order they appear in the query, so one query always gives one match expression), else the harness
    tokenizer's output."""
    safe_terms = [t for t in terms if len(t) >= 2 and (t.isalnum() or all("\u4e00" <= c <= "\u9fa5" for c in t))]
    if safe_terms:
        return " OR ".join(f'"{t}"' for t in safe_terms[:_MAX_FTS_TERMS])
    return tokenize_for_fts(query)


def _best_paragraph(text: str, match_terms: set[str]) -> str:
    """The paragraph that matches the most query terms, else the first one; headings are dropped."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    best_para = ""
    best_matches = 0
    for p in paras:
        lines = [line.strip() for line in p.split("\n") if line.strip() and not line.strip().startswith("#")]
        if not lines:
            continue
        joined = " ".join(lines)
        joined_lower = joined.lower()
        matches = sum(1 for t in match_terms if t in joined_lower)
        if matches > best_matches:
            best_matches = matches
            best_para = joined
    if not best_para and paras:
        first_lines = [line.strip() for line in paras[0].split("\n") if line.strip() and not line.strip().startswith("#")]
        best_para = " ".join(first_lines) if first_lines else paras[0]
    return best_para


def _indexed_snippets(vault_path: Path, label: str, fts_query: str, match_terms: set[str]) -> list[RelevantSnippet]:
    """Tier 1: the best paragraph of each published page the vault's FTS index ranks first for the query."""
    db_path = vault_path / ".wiki_index.db"
    found: list[RelevantSnippet] = []
    for concept_name, indexed_text in search_published_index(db_path, fts_query, limit=_MAX_INDEXED_SNIPPETS):
        concept_file = vault_path / "wiki" / "concepts" / f"{concept_name}.md"
        if not concept_file.is_file():
            concept_file = vault_path / f"{concept_name}.md"
        # The page file is the source of truth for its publish status; the index row's text stands in only for
        # rows that have no page file (e.g. raw sources).
        raw_content = _published_page_body(concept_file) if concept_file.is_file() else indexed_text
        best_para = _best_paragraph(raw_content, match_terms)
        if best_para:
            found.append(
                RelevantSnippet(
                    kb_name=label,
                    article_title=concept_name,
                    snippet=best_para,
                    confidence=0.95,
                    source_path=str(db_path),
                )
            )
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

    trimmed_query = query.strip()
    if not trimmed_query or not vault_paths:
        return ProactiveKnowledgeResult()

    candidates: list[RelevantSnippet] = []

    async def _scan_vault(vault_path: Path, label: str) -> list[RelevantSnippet]:
        found: list[RelevantSnippet] = []
        if not vault_path.exists() or not vault_path.is_dir():
            return found

        terms = _ordered_terms(trimmed_query)
        if not terms:
            return found

        match_terms = {t for t in terms if len(t) >= 2} or set(terms)

        # ── Tier 1: SQLite FTS5 index-first retrieval (O(1) ms latency) ──
        db_path = vault_path / ".wiki_index.db"
        if db_path.is_file():
            try:
                fts_query = _fts_match_query(trimmed_query, terms)
                if fts_query.strip():
                    found = _indexed_snippets(vault_path, label, fts_query, match_terms)
                if found:
                    return found
            except Exception as exc:
                logger.debug("FTS5 index scan failed for %s, falling back to markdown: %s", db_path, exc)

        # ── Tier 2: Concept markdown files fallback (for newly created or uncompiled vaults) ──
        try:
            concepts_dir = vault_path / "wiki" / "concepts"
            search_dir = concepts_dir if concepts_dir.is_dir() else vault_path
            md_files = (list(search_dir.glob("*.md")) or list(vault_path.glob("*.md")))[:15]
            for md_file in md_files:
                title = md_file.stem.lower()
                title_matches = sum(1 for t in match_terms if t in title)
                content = _published_page_body(md_file)

                raw_paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
                for p in raw_paragraphs:
                    content_lines = [line.strip() for line in p.split("\n") if line.strip() and not line.strip().startswith("#")]
                    if not content_lines:
                        continue
                    body_text = " ".join(content_lines)
                    p_lower = body_text.lower()
                    content_matches = sum(1 for t in match_terms if t in p_lower)
                    if content_matches > 0 or title_matches > 0:
                        score = (title_matches * 2.0 + content_matches) / (len(match_terms) + 1.0)
                        found.append(
                            RelevantSnippet(
                                kb_name=label,
                                article_title=md_file.stem,
                                snippet=body_text,
                                confidence=min(1.0, score),
                                source_path=str(md_file),
                            )
                        )
                        if len(found) >= 5:
                            break
        except Exception as exc:
            logger.debug("Vault markdown scan skipped for %s: %s", vault_path, exc)
        return found

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
