"""Knowledge pack snippet selector and deduplicator.

[INPUT]
- app.services.wiki.knowledge_pack.schemas::KnowledgePackConfig, RelevantSnippet, ProactiveKnowledgeResult
- app.services.wiki.vault::resolve_shared_wiki_vault_paths, resolve_shared_wiki_vault_labels

[OUTPUT]
- calculate_jaccard_similarity: Fast character-ngram / word overlap for semantic dedup.
- KnowledgePackSelector: Select, dedup, and enforce strict token/character budget on snippets.

[POS]
High-performance snippet selection pipeline for pre-turn proactive injection.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from app.services.wiki.knowledge_pack.schemas import (
    KnowledgePackConfig,
    ProactiveKnowledgeResult,
    RelevantSnippet,
)

logger = logging.getLogger(__name__)

_EN_NUM_PATTERN = re.compile(r"[a-z0-9]+", re.ASCII)


def tokenize_text(text: str) -> set[str]:
    """Tokenize text into alphanumeric words and CJK unigrams + bigrams."""
    if not text:
        return set()
    cleaned = text.lower()
    tokens: set[str] = set()

    # 1. Alphanumeric tokens (words/numbers)
    for match in _EN_NUM_PATTERN.finditer(cleaned):
        tokens.add(match.group(0))

    # 2. CJK characters + 2-grams
    cjk_chars = [c for c in cleaned if "\u4e00" <= c <= "\u9fa5"]
    tokens.update(cjk_chars)
    for i in range(len(cjk_chars) - 1):
        tokens.add(cjk_chars[i] + cjk_chars[i + 1])

    return tokens


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
    import asyncio

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

        # Quick match on concept markdown files
        terms = tokenize_text(trimmed_query)
        if not terms:
            return found

        # Prefer multi-char tokens for meaningful matching
        match_terms = {t for t in terms if len(t) >= 2} or terms

        try:
            # Shallow traversal of top markdown files to keep retrieval well under 50ms
            md_files = list(vault_path.glob("*.md"))[:20]
            for md_file in md_files:
                title = md_file.stem.lower()
                title_matches = sum(1 for t in match_terms if t in title)
                try:
                    content = md_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                raw_paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
                for p in raw_paragraphs:
                    # Strip markdown heading lines from the paragraph to avoid discarding text with single newline
                    content_lines = [
                        line.strip()
                        for line in p.split("\n")
                        if line.strip() and not line.strip().startswith("#")
                    ]
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
            logger.debug("Vault scan skipped for %s: %s", vault_path, exc)
        return found

    try:
        tasks = [
            _scan_vault(p, vault_labels.get(str(p), vault_labels.get(p.name, p.name)))
            for p in vault_paths
        ]
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
