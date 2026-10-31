"""Knowledge pack snippet selector and deduplicator.

[INPUT]
- app.services.wiki.knowledge_pack.schemas::KnowledgePackConfig, RelevantSnippet, ProactiveKnowledgeResult
- app.services.wiki.knowledge_pack.query_terms::MAX_QUERY_CHARS, search_terms, paragraph_relevance, tokenize_text (POS: the question's terms and the relevance floor)
- myrm_agent_harness.api::search_published_index, index_has_pages (POS: read-only published-pages-only FTS search, and whether an index file holds any concept page row)
- myrm_agent_harness.api::is_within_boundary (POS: resolved-path containment check that follows symlinks)
- myrm_agent_harness.toolkits.wiki.core.frontmatter_contract::WikiPublishStatus, resolve_publish_status (POS: wiki publish gate SSOT)
- myrm_agent_harness.utils.markdown_frontmatter::parse_frontmatter (POS: BOM-tolerant frontmatter parse SSOT)

[OUTPUT]
- calculate_jaccard_similarity: Fast character-ngram / word overlap for semantic dedup.
- truncate_snippet_text: Cut a snippet to a character budget at a sentence or word boundary.
- KnowledgePackSelector: Select, dedup, and enforce strict token/character budget on snippets.
- resolve_proactive_snippets_from_vaults: Retrieve and budget snippets from the shared vaults; the vaults are scanned in one thread of a small pool of its own so the timeout can fire.

[POS]
High-performance snippet selection pipeline for pre-turn proactive injection. Tier 1 asks the vault's FTS index for
its best published pages (the harness applies the publish gate inside the query, so drafts cannot crowd them out)
with an OR query of the question's search terms; tier 2 scans the markdown files of a vault whose index is missing,
unreadable or holds no concept page rows (an index file alone says nothing: any ``WikiIndexer`` creates it on
construction), because
listing thousands of pages to read fifteen of them would cost more than it finds in a vault the index already
covers. Both tiers give each page its one best paragraph by ``paragraph_relevance`` and keep it only when
the page answers the question, ranked by that score, so most questions the vault does not answer inject nothing, one
long page cannot take every slot, and the order of the mounted vaults never decides which page wins. Every page file
it reads goes through the wiki publish gate again, so a draft or blocked page never reaches the injected context,
and snippets never lead with the page's frontmatter. A shared vault is written by another process, so its index
file and its page files are read only when they lie inside the vault, whatever the index or a symlink says: an indexed
page whose file lies outside is held back and logged, while a page with no file at all (a raw interim entry, or a link
that points at nothing) stands on its index row. The scan blocks on file and database reads, so each turn scans all
vaults in one thread, one after the other, of a small pool of its own, in a copy of the turn's context so what the scan
logs still carries the turn's trace and session ids: the timeout fires on time, a slow mount does not stall the loop,
and a mount that never answers pins at most that pool's threads instead of the default pool every other
``asyncio.to_thread`` caller shares.
"""

from __future__ import annotations

import asyncio
import contextvars
import heapq
import logging
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

from myrm_agent_harness.api import index_has_pages, is_within_boundary, search_published_index
from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import WikiPublishStatus, resolve_publish_status
from myrm_agent_harness.utils.markdown_frontmatter import parse_frontmatter

from app.services.wiki.knowledge_pack.query_terms import (
    MAX_QUERY_CHARS,
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
# A scan that never returns (a mount that does not answer) pins its thread for good; this bounds what it can pin.
_SCAN_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="knowledge-pack-scan")


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


def _best_paragraph(title: str, text: str, terms: Sequence[str]) -> tuple[str, float]:
    """The paragraph of a page that answers the question best, with its relevance; ``("", 0.0)`` when none does.

    The first of equally relevant paragraphs wins. A text made of headings only, such as the one flat line an index
    row stores for a page that has no file, is read as its first block as it is.
    """
    paragraphs = _paragraphs(text) or [block.strip() for block in text.split("\n\n") if block.strip()][:1]
    best, best_score = "", 0.0
    for paragraph in paragraphs:
        score = paragraph_relevance(terms, title, paragraph)
        if score > best_score:
            best, best_score = paragraph, score
    return best, best_score


def _page_snippet(label: str, title: str, body: str, terms: Sequence[str], source_path: Path) -> RelevantSnippet | None:
    """The snippet a page gives: its best paragraph, or None when no paragraph of it answers the question."""
    paragraph, confidence = _best_paragraph(title, body, terms)
    if not paragraph:
        return None
    return RelevantSnippet(
        kb_name=label,
        article_title=title,
        snippet=paragraph,
        confidence=confidence,
        source_path=str(source_path),
    )


def _inside_vault(path: Path, vault_path: Path) -> bool:
    """Whether ``path`` resolves inside the vault; a path that does not is refused and logged."""
    if is_within_boundary(path, vault_path):
        return True
    logger.warning("Shared vault %s refused %r: it resolves outside the vault", vault_path, path)
    return False


def _indexed_page_body(vault_path: Path, concept_name: str, indexed_text: str) -> str:
    """The text of an indexed page, from its file through the publish gate.

    The name comes from an index another process wrote. A page that has no file at all (a raw interim entry, or a link
    that points at nothing) stands on its index row; a page whose file lies outside the vault, by a name that climbs
    out of it or a link, is held back.
    """
    for candidate in (vault_path / "wiki" / "concepts" / f"{concept_name}.md", vault_path / f"{concept_name}.md"):
        if candidate.is_file():
            return _published_page_body(candidate) if _inside_vault(candidate, vault_path) else ""
    return indexed_text


def _indexed_snippets(db_path: Path, vault_path: Path, label: str, terms: Sequence[str]) -> list[RelevantSnippet]:
    """Tier 1: the best paragraph of each published page the vault's FTS index ranks first for the question."""
    fts_query = " OR ".join(f'"{t}"' for t in terms)
    found: list[RelevantSnippet] = []
    for concept_name, indexed_text in search_published_index(db_path, fts_query, limit=_MAX_INDEXED_SNIPPETS):
        body = _indexed_page_body(vault_path, concept_name, indexed_text)
        snippet = _page_snippet(label, concept_name, body, terms, db_path)
        if snippet:
            found.append(snippet)
    return found


def _markdown_snippets(vault_path: Path, label: str, terms: Sequence[str]) -> list[RelevantSnippet]:
    """Tier 2: the best paragraph of each of the vault's first markdown pages, in name order, that answers the question."""
    concepts_dir = vault_path / "wiki" / "concepts"
    search_dir = concepts_dir if concepts_dir.is_dir() else vault_path
    # The first files by name, picked without sorting the whole listing: a vault can hold thousands of pages.
    md_files = heapq.nsmallest(_MAX_SCANNED_FILES, search_dir.glob("*.md")) or heapq.nsmallest(
        _MAX_SCANNED_FILES, vault_path.glob("*.md")
    )
    found: list[RelevantSnippet] = []
    for md_file in md_files:
        if not _inside_vault(md_file, vault_path):
            continue
        snippet = _page_snippet(label, md_file.stem, _published_page_body(md_file), terms, md_file)
        if snippet:
            found.append(snippet)
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


def _scan_vault(vault_path: Path, label: str, terms: Sequence[str]) -> list[RelevantSnippet]:
    """The snippets one vault gives for the question."""
    if not vault_path.is_dir():
        return []

    # ── Tier 1: SQLite FTS5 index-first retrieval ──
    # An index that holds pages answers for its vault, an empty answer included. An index file without concept page
    # rows is no index (the file is created by any WikiIndexer, filled or not), so the vault goes to tier 2.
    db_path = vault_path / ".wiki_index.db"
    if db_path.is_file() and _inside_vault(db_path, vault_path):
        try:
            found = _indexed_snippets(db_path, vault_path, label, terms)
            if found or index_has_pages(db_path):
                return found
        except Exception as exc:
            logger.warning("FTS5 index scan failed for %s, falling back to markdown: %s", db_path, exc)

    # ── Tier 2: Concept markdown files (for vaults whose index is missing, unreadable or holds no pages) ──
    try:
        return _markdown_snippets(vault_path, label, terms)
    except Exception as exc:
        logger.warning("Vault markdown scan skipped for %s: %s", vault_path, exc)
        return []


def _scan_vaults(vaults: Sequence[tuple[Path, str]], terms: Sequence[str]) -> list[RelevantSnippet]:
    """The snippets the vaults give for the question, vault after vault. Blocking: it runs in a scan pool thread."""
    return [snippet for vault_path, label in vaults for snippet in _scan_vault(vault_path, label, terms)]


async def resolve_proactive_snippets_from_vaults(
    query: str,
    vault_paths: tuple[Path, ...],
    vault_labels: dict[str, str],
    *,
    config: KnowledgePackConfig | None = None,
    timeout_seconds: float = 0.150,
) -> ProactiveKnowledgeResult:
    """Asynchronously retrieve and budget proactive snippets within timeout guardrail.

    The vaults are scanned in one thread of a pool of their own, in a copy of the caller's context, so the timeout cuts
    the wait on time, a scan that never returns cannot starve the default pool, and the scan's log records keep the
    caller's trace and session ids; a scan that overruns the timeout finishes in the background and its result is
    dropped.
    """
    t0 = time.monotonic()
    selector = KnowledgePackSelector(config)

    terms = search_terms(query.strip()[:MAX_QUERY_CHARS])
    if not terms or not vault_paths:
        return ProactiveKnowledgeResult()

    vaults = [(p, vault_labels.get(str(p), vault_labels.get(p.name, p.name))) for p in vault_paths]

    scan = partial(_scan_vaults, vaults, terms)
    context = contextvars.copy_context()
    try:
        candidates = await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(_SCAN_EXECUTOR, partial(context.run, scan)),
            timeout=timeout_seconds,
        )
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
