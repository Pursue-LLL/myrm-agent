"""[INPUT]
- .base::WikiQueryBase (POS: 共享状态)
- wiki.core.types::SourceSnippet (POS: 检索结果片段)
- wiki.pipeline.cognitive_map.index_routing::IndexRouteEntry (POS: index-first 路由)

[OUTPUT]
- WikiLoadingMixin: 文章/目录 sidecar 加载与片段提取

[POS]
`wiki/retrieval/query/` 的加载阶段；把检索候选变成可注入上下文的片段。
"""

from __future__ import annotations

import re
from pathlib import Path

from myrm_agent_harness.utils.logger_utils import get_agent_logger

from ...core.config import WikiQueryConfig
from ...core.structure import WikiStructure
from ...core.types import SourceSnippet
from ...pipeline.cognitive_map.index_routing import (
    INDEX_ROUTING_SECTION,
    IndexRouteEntry,
    format_index_route_context,
)
from .base import WikiQueryBase

logger = get_agent_logger(__name__)


class WikiLoadingMixin(WikiQueryBase):
    """文章/目录 sidecar 加载与片段提取。"""

    async def _load_articles_context(
        self,
        article_paths: list[Path],
        index_matches: list[tuple[IndexRouteEntry, float]],
        query_config: WikiQueryConfig | None = None,
    ) -> tuple[str, list[SourceSnippet]]:
        """Load article content as context and extract citation snippets.

        Returns:
            Tuple of (context_string, list_of_source_snippets).
        """
        qc = query_config or self._query_config
        context_parts: list[str] = []
        snippets: list[SourceSnippet] = []
        remaining_chars = max(500, qc.max_context_chars)

        if index_matches:
            index_block = format_index_route_context(index_matches)
            if index_block:
                context_parts.append(index_block)
                remaining_chars = max(0, remaining_chars - len(index_block))
                top_entry, _score = index_matches[0]
                snippets.append(
                    SourceSnippet(
                        article_path=self._structure.get_index_catalog_relative_path(),
                        article_name="index",
                        snippet=f"[[{top_entry.link_name}]] — {top_entry.summary}",
                        section=INDEX_ROUTING_SECTION,
                        level="L0",
                    )
                )

        # Step 1: directory-level L0/L1 context
        if qc.sidecar_retrieval_enabled:
            sidecar_parts, sidecar_chars, sidecar_snippets = self._load_directory_sidecars(
                article_paths,
                query_config=qc,
            )
            if sidecar_parts:
                context_parts.extend(sidecar_parts)
                remaining_chars = max(0, remaining_chars - sidecar_chars)
            if sidecar_snippets:
                snippets.extend(sidecar_snippets)

        # Step 2: full article context (L2), bounded by count and hard char budget
        max_full_articles = max(1, min(len(article_paths), qc.max_full_articles))
        loaded_articles = 0
        for path in article_paths:
            if loaded_articles >= max_full_articles or remaining_chars <= 0:
                break
            try:
                content = path.read_text(encoding="utf-8")

                # Extract only YAML frontmatter and Compiled Truth section to protect prompt caching
                truth_content = ""

                # 1. Extract YAML Frontmatter if present
                yaml_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
                if yaml_match:
                    truth_content += f"---\n{yaml_match.group(1)}\n---\n\n"

                # 2. Extract Compiled Truth section
                truth_match = re.search(r"(## Compiled Truth\n.*?)(?=\n## |$)", content, re.DOTALL)
                if truth_match:
                    truth_content += truth_match.group(1).strip()
                else:
                    truth_content = content

                block = f"# {path.stem}\n\n{truth_content}".strip()
                if len(block) > remaining_chars:
                    clipped = block[:remaining_chars].rsplit(" ", 1)[0].strip()
                    if not clipped:
                        break
                    block = f"{clipped}\n\n[... truncated by context budget]"
                context_parts.append(block)
                remaining_chars -= len(block)
                loaded_articles += 1

                # 3. Extract snippet: first meaningful section or paragraph (≤500 chars)
                snippet_text, section_name = self._extract_snippet(truth_content)
                snippets.append(
                    SourceSnippet(
                        article_path=str(path),
                        article_name=path.stem,
                        snippet=snippet_text,
                        section=section_name,
                        level="L2",
                    )
                )
                snippets.extend(self._claim_snippets_from_content(content, path))
            except Exception as e:
                logger.warning(f"Failed to load {path}: {e}")

        return "\n\n---\n\n".join(context_parts), snippets

    def _load_directory_sidecars(
        self,
        article_paths: list[Path],
        query_config: WikiQueryConfig | None = None,
    ) -> tuple[list[str], int, list[SourceSnippet]]:
        qc = query_config or self._query_config
        parts: list[str] = []
        total_chars = 0
        snippets: list[SourceSnippet] = []
        seen: set[str] = set()
        max_dirs = max(0, qc.max_sidecar_directories)
        if max_dirs == 0:
            return parts, total_chars, snippets
        for article in article_paths:
            dir_path = ""
            try:
                rel = article.relative_to(self._structure.concepts_dir).with_suffix("")
                dir_path = "" if str(rel.parent) in (".", "") else str(rel.parent).replace("\\", "/")
            except ValueError:
                for p_dir in self._structure.public_dirs:
                    p_concepts = p_dir / "wiki" / "concepts"
                    try:
                        rel = article.relative_to(p_concepts).with_suffix("")
                        dir_path = "" if str(rel.parent) in (".", "") else str(rel.parent).replace("\\", "/")
                        break
                    except ValueError:
                        continue
            if dir_path in seen:
                continue
            seen.add(dir_path)
            if len(seen) > max_dirs:
                break
            abstract = self._indexer.get_sidecar_truth(dir_path, level=0)
            overview = self._indexer.get_sidecar_truth(dir_path, level=1)
            if abstract:
                block = f"# Directory {dir_path or '/'} (L0)\n\n{abstract.strip()}"
                parts.append(block)
                total_chars += len(block)
                abstract_snippet, abstract_section = self._extract_snippet(abstract, max_chars=300)
                snippets.append(
                    SourceSnippet(
                        article_path=self._sidecar_source_path(dir_path, level="L0"),
                        article_name=dir_path or "/",
                        snippet=abstract_snippet or abstract.strip()[:300],
                        section=abstract_section or "Directory Abstract",
                        level="L0",
                    )
                )
            if overview:
                block = f"# Directory {dir_path or '/'} (L1)\n\n{overview.strip()}"
                parts.append(block)
                total_chars += len(block)
                overview_snippet, overview_section = self._extract_snippet(overview, max_chars=300)
                snippets.append(
                    SourceSnippet(
                        article_path=self._sidecar_source_path(dir_path, level="L1"),
                        article_name=dir_path or "/",
                        snippet=overview_snippet or overview.strip()[:300],
                        section=overview_section or "Directory Overview",
                        level="L1",
                    )
                )
        return parts, total_chars, snippets

    def _collect_concepts_from_directory_scopes(
        self,
        dir_paths: list[str],
        concepts: list[Path],
    ) -> list[Path]:
        ordered: list[Path] = []
        seen_paths: set[Path] = set()

        for dir_path in dir_paths:
            normalized = dir_path.strip("/").replace("\\", "/")
            for concept in concepts:
                concept_name = self._concept_name_from_path(concept)
                if normalized and not concept_name.startswith(f"{normalized}/"):
                    continue
                if concept not in seen_paths:
                    seen_paths.add(concept)
                    ordered.append(concept)
        return ordered

    def _concept_name_from_path(self, path: Path) -> str:
        try:
            rel = path.relative_to(self._structure.concepts_dir).with_suffix("")
            return str(rel).replace("\\", "/")
        except ValueError:
            pass

        for p_dir in self._structure.public_dirs:
            p_concepts = p_dir / "wiki" / "concepts"
            try:
                rel = path.relative_to(p_concepts).with_suffix("")
                return str(rel).replace("\\", "/")
            except ValueError:
                continue

        return path.stem

    def _normalize_concept_name(self, name: str) -> str:
        """Map FTS/index aliases to the canonical on-disk concept relative path."""
        candidate = name.strip().replace("\\", "/")
        if not candidate:
            return ""
        path = self._structure.resolve_concept_file_path(candidate)
        if path and path.exists():
            return self._concept_name_from_path(path)
        return candidate

    @staticmethod
    def _sidecar_source_path(dir_path: str, *, level: str) -> str:
        filename = (
            WikiStructure.DIRECTORY_ABSTRACT_FILENAME if level == "L0" else WikiStructure.DIRECTORY_OVERVIEW_FILENAME
        )
        normalized = dir_path.strip("/")
        if not normalized:
            return f"/{filename}"
        return f"{normalized}/{filename}"

    def _claim_snippets_from_content(self, content: str, path: Path) -> list[SourceSnippet]:
        from ...core.claims_contract import (
            parse_claims_from_content,
            resolve_evidence_snapshot_and_excerpt,
        )

        claim_snippets: list[SourceSnippet] = []
        raw_bytes_cache: dict[str, bytes] = {}
        for claim in parse_claims_from_content(content):
            if claim.evidence:
                for evidence in claim.evidence:
                    snapshot_status, excerpt = resolve_evidence_snapshot_and_excerpt(
                        evidence.path,
                        evidence.lines,
                        evidence.content_sha256,
                        self._structure,
                        cache=raw_bytes_cache,
                    )
                    snippet_text = excerpt or claim.text
                    claim_snippets.append(
                        SourceSnippet(
                            article_path=str(path),
                            article_name=path.stem,
                            snippet=snippet_text,
                            section="Claim",
                            level="L2",
                            claim_id=claim.id,
                            claim_text=claim.text,
                            evidence_path=evidence.path,
                            line_range=evidence.lines,
                            claim_status=claim.status,
                            claim_confidence=claim.confidence,
                            evidence_content_sha256=evidence.content_sha256,
                            evidence_snapshot_status=snapshot_status,
                        )
                    )
            else:
                claim_snippets.append(
                    SourceSnippet(
                        article_path=str(path),
                        article_name=path.stem,
                        snippet=claim.text,
                        section="Claim",
                        level="L2",
                        claim_id=claim.id,
                        claim_text=claim.text,
                        claim_status=claim.status,
                        claim_confidence=claim.confidence,
                    )
                )
        return claim_snippets

    async def _search_asset_snippets(self, query: str) -> list[SourceSnippet]:
        if self._asset_indexer is None:
            return []
        hits = await self._asset_indexer.search(query, limit=3)
        snippets: list[SourceSnippet] = []
        for hit in hits:
            parent = hit.source_concepts[0] if hit.source_concepts else hit.filename
            snippets.append(
                SourceSnippet(
                    article_path=f"wiki/assets/{hit.filename}",
                    article_name=parent,
                    snippet=hit.caption,
                    section="Image",
                    level="L2",
                    hit_kind="asset",
                    asset_filename=hit.filename,
                )
            )
        return snippets

    @staticmethod
    def _extract_snippet(content: str, max_chars: int = 500) -> tuple[str, str]:
        """Extract the first meaningful paragraph as a citation snippet.

        Returns:
            Tuple of (snippet_text, section_heading).
        """
        section_name = ""

        # Strip YAML frontmatter
        stripped = re.sub(r"^---\n.*?\n---\n*", "", content, count=1, flags=re.DOTALL)

        # Find the first section heading (## ...)
        section_match = re.search(r"^(#{1,3})\s+(.+)$", stripped, re.MULTILINE)
        if section_match:
            section_name = section_match.group(2).strip()

        # Collect non-empty, non-heading lines as the snippet
        lines: list[str] = []
        total = 0
        for line in stripped.split("\n"):
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#"):
                if lines:
                    break
                continue
            lines.append(line_stripped)
            total += len(line_stripped)
            if total >= max_chars:
                break

        snippet = " ".join(lines)
        if len(snippet) > max_chars:
            snippet = snippet[:max_chars].rsplit(" ", 1)[0] + "…"

        return snippet, section_name
