"""Wiki 响应的领域映射。

[POS]
把服务层结果转换成 API 响应模型；只做转换，不读写磁盘、不发请求。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.wiki.core.types import WikiRetrievalTrace

from app.api.wiki.routes.schemas import (
    CompileRunResponse,
    WikiClaimEvidenceItem,
    WikiClaimItem,
    WikiEditorSectionsResponse,
    WikiRetrievalSeedTraceItem,
    WikiRetrievalTraceIndexHit,
    WikiRetrievalTraceResponse,
    WikiSourceSnippet,
)
from app.services.wiki import MemoryToWikiArchiver

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure


def _compile_run_response(archiver: MemoryToWikiArchiver) -> CompileRunResponse:
    snapshot = archiver._queue.get_compile_run()
    return CompileRunResponse(
        state=snapshot.state,
        pause_reason=snapshot.pause_reason,
        primary_error_kind=snapshot.primary_error_kind,
        phase=snapshot.phase,
        facet_count=snapshot.facet_count,
        warning_count=snapshot.warning_count,
        survey_skipped=snapshot.survey_skipped,
    )


def _claims_to_response_items(
    content: str,
    structure: "WikiStructure | None" = None,
) -> list[WikiClaimItem]:
    from myrm_agent_harness.toolkits.wiki.core.claims_contract import (
        build_evidence_resource_uri,
        lookup_raw_supersede_uri,
        parse_claims_from_content,
        resolve_evidence_snapshot_status,
    )

    items: list[WikiClaimItem] = []
    for claim in parse_claims_from_content(content):
        evidence_items: list[WikiClaimEvidenceItem] = []
        for evidence in claim.evidence:
            snapshot_status = resolve_evidence_snapshot_status(
                evidence.path,
                evidence.content_sha256,
                structure,
            )
            superseded_from_uri = ""
            if snapshot_status == "stale":
                superseded_from_uri = lookup_raw_supersede_uri(structure, evidence.path)
            evidence_items.append(
                WikiClaimEvidenceItem(
                    kind=evidence.kind,
                    source_id=evidence.source_id,
                    path=evidence.path,
                    lines=evidence.lines,
                    weight=evidence.weight,
                    confidence=evidence.confidence,
                    note=evidence.note,
                    content_sha256=evidence.content_sha256,
                    updated_at=evidence.updated_at,
                    snapshot_status=snapshot_status,
                    resource_uri=build_evidence_resource_uri(
                        evidence.path,
                        evidence.content_sha256,
                        structure=structure,
                    ),
                    superseded_from_uri=superseded_from_uri,
                )
            )
        items.append(
            WikiClaimItem(
                id=claim.id,
                text=claim.text,
                status=claim.status,
                confidence=claim.confidence,
                updated_at=claim.updated_at,
                evidence=evidence_items,
            )
        )
    return items


def _str_or_none(value: object) -> str | None:
    """Return a trimmed string, or None when empty/missing."""
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _editor_sections_to_response(content: str) -> WikiEditorSectionsResponse:
    from myrm_agent_harness.toolkits.wiki.core.section_contract import (
        parse_editor_sections,
    )

    sections = parse_editor_sections(content)
    return WikiEditorSectionsResponse(
        compiled_truth=sections.compiled_truth,
        timeline=sections.timeline,
        tags=list(sections.tags),
        aliases=list(sections.aliases),
    )


def _citation_sources_to_snippets(
    sources: list[dict[str, object]],
) -> list[WikiSourceSnippet]:
    """Map harness citation SSOT dicts to REST response models."""
    snippets: list[WikiSourceSnippet] = []
    for entry in sources:
        confidence = entry.get("claim_confidence") or 0.0
        snippets.append(
            WikiSourceSnippet(
                path=str(entry.get("path", "")),
                name=str(entry.get("filename", "")),
                snippet=str(entry.get("snippet", "")),
                section=str(entry.get("section", "")),
                level=str(entry.get("level", "L2")),
                claim_id=str(entry.get("claim_id", "")),
                claim_text=str(entry.get("claim_text", "")),
                evidence_path=str(entry.get("evidence_path", "")),
                line_range=str(entry.get("line_range", "")),
                claim_status=str(entry.get("claim_status", "")),
                claim_confidence=float(confidence) if isinstance(confidence, (int, float, str)) else 0.0,
                snapshot_status=str(entry.get("snapshot_status", "")),
                resource_uri=str(entry.get("resource_uri", "")),
                superseded_from_uri=str(entry.get("superseded_from_uri", "")),
                hit_kind=str(entry.get("hit_kind", "concept")),
                asset_filename=str(entry.get("asset_filename", "")),
            )
        )
    return snippets


def _retrieval_trace_to_response(
    trace: WikiRetrievalTrace | None,
) -> WikiRetrievalTraceResponse | None:
    if trace is None:
        return None
    index_hits = [
        WikiRetrievalTraceIndexHit(
            link_name=hit.link_name,
            summary=hit.summary,
            score=hit.score,
            page_type=hit.page_type,
        )
        for hit in trace.index_hits
    ]
    seeds = [
        WikiRetrievalSeedTraceItem(
            concept_name=seed.concept_name,
            score=seed.score,
            source=seed.source,
        )
        for seed in trace.seeds
    ]
    sidecar_directories = list(trace.sidecar_directories)
    selected_concepts = list(trace.selected_concepts)
    if not index_hits and not seeds and not sidecar_directories and not selected_concepts:
        return None
    return WikiRetrievalTraceResponse(
        index_hits=index_hits,
        seeds=seeds,
        sidecar_directories=sidecar_directories,
        selected_concepts=selected_concepts,
    )
