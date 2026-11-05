"""Wiki API 子路由共享的响应转换、状态码映射与变更后副作用。

[POS]
Wiki API 的共享实现；由 routes/ 下的查询、去重、导入等路由复用。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.wiki.core.types import WikiRetrievalTrace
from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
    WikiCognitiveMapService,
    WikiMapEvent,
    WikiMapEventType,
)

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
    from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import RawPublishResult

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])


def _refresh_wiki_cognitive_map(
    archiver: MemoryToWikiArchiver,
    event_type: WikiMapEventType,
    summary: str,
    details: dict[str, object] | None = None,
) -> None:
    """Rebuild OKF index/log/hot after a wiki lifecycle event."""
    pending_stats = archiver._pending_mgr.get_stats()
    queue_stats = archiver._queue.get_stats()
    WikiCognitiveMapService(
        archiver._structure,
        get_pending_count=lambda: int(pending_stats.get("pending", 0)),
        get_queue_pending=lambda: int(queue_stats.get("pending", 0)),
    ).refresh(
        WikiMapEvent(
            event_type=event_type,
            summary=summary,
            details=details or {},
        )
    )


async def _after_wiki_vault_mutation(archiver: MemoryToWikiArchiver, reason: str) -> None:
    """Drop stats cache and commit vault git snapshot after wiki mutations."""
    from app.services.wiki.vault import after_wiki_vault_mutation

    await after_wiki_vault_mutation(archiver, reason)


# --- Request/Response Models ---


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


# --- Core RAG & Compilation Endpoints ---


async def _schedule_post_import_dedup_scan(agent_id: str | None) -> None:
    try:
        from app.services.wiki.dedup_runner import schedule_wiki_dedup_scan

        await schedule_wiki_dedup_scan(agent_id=agent_id, incremental=True)
    except Exception as exc:
        logger.warning("Post-import wiki dedup scan failed: %s", exc)


def _wiki_apply_http_status(code: str) -> int:
    mapping = {
        "concept_not_found": 404,
        "concept_exists": 409,
        "canonical_conflict": 409,
        "conflict": 409,
        "forbidden_for_caller": 403,
        "forbidden_for_agent": 403,
        "invalid_frontmatter": 422,
        "invalid_request": 422,
        "publish_blocked": 422,
        "timeline_rejected": 422,
    }
    return mapping.get(code, 400)


def _wiki_compound_http_status(code: str) -> int:
    mapping = {
        "already_staged": 409,
        "incognito_forbidden": 403,
        "invalid_request": 422,
        "invalid_role": 422,
        "message_not_found": 404,
    }
    return mapping.get(code, 400)


async def _publish_import_raw(
    structure: "WikiStructure",
    relative_path: str,
    content: str,
    *,
    on_conflict: Literal["skip", "supersede"],
    supersede_reason: str,
) -> RawPublishResult:
    from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import (
        RawConflictPolicy,
        RawGateError,
        RawPublishRequest,
        publish_raw,
    )

    policy = RawConflictPolicy.SUPERSEDE if on_conflict == "supersede" else RawConflictPolicy.SKIP
    try:
        return await publish_raw(
            structure,
            RawPublishRequest(
                relative_path=relative_path,
                content=content,
                conflict_policy=policy,
                supersede_reason=supersede_reason,
            ),
            caller="settings",
        )
    except RawGateError as exc:
        if exc.code == "invalid_request":
            raise HTTPException(
                status_code=422,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        raise


def _validate_import_conflict_options(
    on_conflict: Literal["skip", "supersede"],
    supersede_reason: str,
) -> None:
    if on_conflict == "supersede" and not supersede_reason.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_request",
                "message": "supersede_reason is required when on_conflict is supersede.",
            },
        )


def _track_import_publish_result(
    result: RawPublishResult,
    *,
    enqueued_paths: list[Path],
    conflict_paths: list[str],
    security_blocked_paths: list[str],
    security_redacted_paths: list[str],
) -> tuple[int, int]:
    """Returns (skipped_conflict_count, superseded_count) for one publish result."""
    if result.security_blocked:
        security_blocked_paths.append(result.relative_path)
        return 0, 0
    if result.written:
        enqueued_paths.append(result.absolute_path)
        if result.security_redacted:
            security_redacted_paths.append(result.relative_path)
    if result.conflict_skipped:
        conflict_paths.append(result.relative_path)
        return 1, 0
    if result.superseded:
        return 0, 1
    return 0, 0


def _build_import_message(
    *,
    enqueued: int,
    skipped_conflict: int,
    superseded: int,
    security_blocked: int,
    security_redacted: int,
    auto_compile: bool,
    source_label: str = "",
) -> str:
    parts = [f"Imported {enqueued} file(s){source_label}"]
    if skipped_conflict:
        parts.append(f"{skipped_conflict} conflict(s) skipped")
    if superseded:
        parts.append(f"{superseded} superseded")
    if security_blocked:
        parts.append(f"{security_blocked} blocked (sensitive content)")
    if security_redacted:
        parts.append(f"{security_redacted} redacted")
    parts.append("compilation started" if auto_compile else "queued without auto-compile")
    return ", ".join(parts)
