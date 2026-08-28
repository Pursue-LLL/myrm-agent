"""Wiki Knowledge Base API router.

[INPUT]
fastapi::APIRouter, Depends, HTTPException, Query (POS: FastAPI 路由与依赖注入)
pydantic::BaseModel, Field (POS: 数据验证与序列化)
app.api.dependencies::get_optional_llm_for_user, get_workspace_root (POS: 依赖注入函数)
app.services.wiki::MemoryToWikiArchiver (POS: Memory→Wiki 自动归档服务)
langchain_core.language_models::BaseChatModel (POS: LangChain LLM 基类)
myrm_agent_harness.agent.artifacts.vault::ArtifactVault (POS: Artifact 存储金库，ingest 端点延迟导入)
app.database.models.artifact::Artifact (POS: Artifact 数据库模型，ingest 端点延迟导入)

[OUTPUT]
router: Wiki API 路由器（完整增删改查、后台队列审核、批量导入、artifact 内容写入接口）
Wiki概念 CRUD 接口
Wiki队列与审核状态接口
批量导入接口（folder/zip/obsidian；`on_conflict` skip|supersede + `conflict_paths`）
Artifact 内容写入接口

[POS]
业务层 Wiki API 路由。提供全量 REST 端点供前端 Brain Console 调用：
查询/编译/维护/ingest wiki。/concepts (CRUD)、/queue (状态控制)、/pending (人工审核)、
/import/* (批量导入经 harness raw_gate)、/ingest (artifact 内容写入)。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.wiki.core.types import WikiRetrievalTrace
from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
    WikiCognitiveMapService,
    WikiMapEvent,
    WikiMapEventType,
)
from pydantic import BaseModel, Field

from app.api.dependencies import get_optional_llm_for_user
from app.api.memory.utils import get_optional_memory_manager
from app.services.wiki import MemoryToWikiArchiver

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

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


class WikiQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question to ask the wiki")
    mode: Literal["auto", "raw_claim"] = Field(
        default="auto",
        description="Retrieval mode: auto (default) or raw_claim (prioritize frontmatter claims)",
    )


class WikiSourceSnippet(BaseModel):
    path: str
    name: str
    snippet: str = ""
    section: str = ""
    level: str = "L2"
    claim_id: str = ""
    claim_text: str = ""
    evidence_path: str = ""
    line_range: str = ""
    claim_status: str = ""
    claim_confidence: float = 0.0
    snapshot_status: str = ""
    resource_uri: str = ""
    superseded_from_uri: str = ""
    hit_kind: str = "concept"
    asset_filename: str = ""


class WikiClaimEvidenceItem(BaseModel):
    kind: str = ""
    source_id: str = ""
    path: str = ""
    lines: str = ""
    weight: float = 1.0
    confidence: float = 0.0
    note: str = ""
    content_sha256: str = ""
    updated_at: str = ""
    snapshot_status: str = "missing"
    resource_uri: str = ""
    superseded_from_uri: str = ""


class WikiClaimItem(BaseModel):
    id: str
    text: str
    status: str = "unknown"
    confidence: float = 0.0
    updated_at: str = ""
    evidence: list[WikiClaimEvidenceItem] = Field(default_factory=list)


class WikiRetrievalTraceIndexHit(BaseModel):
    link_name: str
    summary: str
    score: float
    page_type: str = ""


class WikiRetrievalSeedTraceItem(BaseModel):
    concept_name: str
    score: float
    source: str


class WikiRetrievalTraceResponse(BaseModel):
    index_hits: list[WikiRetrievalTraceIndexHit] = Field(default_factory=list)
    seeds: list[WikiRetrievalSeedTraceItem] = Field(default_factory=list)
    sidecar_directories: list[str] = Field(default_factory=list)
    selected_concepts: list[str] = Field(default_factory=list)


class WikiQueryResponse(BaseModel):
    answer: str
    related_articles: list[str] = Field(default_factory=list)
    source_snippets: list[WikiSourceSnippet] = Field(default_factory=list)
    confidence_score: float = 0.0
    retrieval_trace: WikiRetrievalTraceResponse | None = None


class WikiCompileResponse(BaseModel):
    concepts_count: int
    articles_generated: int
    backlinks_created: int
    duration_ms: int
    articles_pending: int = 0
    articles_published: int = 0
    articles_blocked: int = 0
    synthesis_pending: int = 0
    compile_run: "CompileRunResponse | None" = None


class CompileRunResponse(BaseModel):
    state: Literal["running", "paused"]
    pause_reason: str = ""
    primary_error_kind: str = ""
    phase: Literal["idle", "structure_survey", "semantic_compile", "postprocess"] = "idle"
    facet_count: int = 0
    warning_count: int = 0
    survey_skipped: bool = False


class WikiHealthIssueResponse(BaseModel):
    issue_type: str
    severity: str
    location: str
    description: str
    action_kind: str
    suggested_fix: str | None = None


class WikiMaintenanceResponse(BaseModel):
    issues_found: int
    issues_fixed: int
    connections_discovered: int
    duration_ms: int
    open_actions_count: int = 0
    raw_security_removed: int = 0
    raw_security_removed_paths: list[str] = Field(default_factory=list)
    issues: list[WikiHealthIssueResponse] = Field(default_factory=list)


class WikiHealthReportResponse(BaseModel):
    mode: Literal["structural", "full"]
    generated_at: str
    open_actions_count: int
    issues_found: int
    issues: list[WikiHealthIssueResponse] = Field(default_factory=list)
    drift_sampled: bool = False
    drift_checked_at: str | None = None
    duplicate_groups_pending: int = 0
    synthesis_pending: int = 0


class WikiStructuralIssuesResponse(BaseModel):
    broken_links: int = 0
    invalid_frontmatter_types: int = 0
    provenance_gaps: int = 0
    scanned_concepts: int = 0


class WikiDedupStatsResponse(BaseModel):
    duplicate_groups_pending: int = 0
    compile_jobs_prevented: int = 0
    eligible_raw_count: int = 0
    excluded_raw_count: int = 0
    trashed_raw_count: int = 0
    blocks_compile: bool = False


class WikiAssetIndexStatsResponse(BaseModel):
    indexed: int = 0
    pending: int = 0
    failed: int = 0
    total_files: int = 0
    enabled: bool = False


class WikiMaintainStateResponse(BaseModel):
    last_run_at: str | None = None
    last_mode: str | None = None
    last_issues_found: int = 0
    last_issues_fixed: int = 0
    last_connections_discovered: int = 0
    last_duration_ms: int = 0
    last_skipped_reason: str | None = None


class WikiStatsResponse(BaseModel):
    total_concepts: int
    total_articles: int
    total_raw_files: int
    wiki_path: str
    vault_ready: bool
    legacy_migrated: bool
    cognitive_index_ready: bool = False
    cognitive_log_entries: int = 0
    cognitive_hot_updated_at: str | None = None
    synthesis_pending: int = 0
    obsidian_launch_available: bool = False
    vault_git_enabled: bool = False
    vault_git_initialized: bool = False
    vault_git_last_commit: str | None = None
    structural_issues: WikiStructuralIssuesResponse = Field(default_factory=WikiStructuralIssuesResponse)
    dedup_stats: WikiDedupStatsResponse = Field(default_factory=WikiDedupStatsResponse)
    maintain_state: WikiMaintainStateResponse = Field(default_factory=WikiMaintainStateResponse)
    asset_index: WikiAssetIndexStatsResponse = Field(default_factory=WikiAssetIndexStatsResponse)


class GraphNodeItem(BaseModel):
    id: str
    name: str
    group: int
    val: int = 1


class GraphEdgeItem(BaseModel):
    source: str
    target: str
    weight: float = 1.0


class WikiGraphResponse(BaseModel):
    nodes: list[GraphNodeItem]
    edges: list[GraphEdgeItem]


class WikiEditorSectionsResponse(BaseModel):
    compiled_truth: str = ""
    timeline: str = ""
    tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


class ConceptResponse(BaseModel):
    name: str
    content: str
    content_hash: str = ""
    provenance: str | None = None
    source_chat: str | None = None
    source_message: str | None = None
    claims: list[WikiClaimItem] = Field(default_factory=list)
    editor_sections: WikiEditorSectionsResponse = Field(default_factory=WikiEditorSectionsResponse)


class ConceptListResponse(BaseModel):
    concepts: list[str]
    total: int
    has_more: bool


class TreeNode(BaseModel):
    id: str
    name: str
    is_dir: bool
    ingest_status: str | None = None
    children: list["TreeNode"] | None = None


class CreateFolderRequest(BaseModel):
    path: str = Field(..., min_length=1)


class MoveNodeRequest(BaseModel):
    source_path: str = Field(..., min_length=1)
    target_path: str = Field(..., min_length=1)


class DeleteFolderRequest(BaseModel):
    path: str = Field(..., min_length=1)


class WikiApplyClaimPatch(BaseModel):
    id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    status: str = "unknown"
    confidence: float = 0.0
    updated_at: str = ""
    evidence: list[dict[str, object]] = Field(default_factory=list)


class WikiApplyRequestBody(BaseModel):
    op: Literal[
        "update_metadata",
        "patch_compiled_truth",
        "append_timeline",
        "create_note",
        "replace_full_document",
    ]
    concept_name: str = Field(..., min_length=1)
    compiled_truth: str = ""
    timeline_entry: str = ""
    content: str = ""
    body: str = ""
    tags: list[str] | None = None
    aliases: list[str] | None = None
    sources: list[str] | None = None
    claims: list[WikiApplyClaimPatch] = Field(default_factory=list)
    clear_confidence: bool = False
    page_type: str = "session"
    provenance: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    canonical_id: str | None = None
    if_match: str | None = None


class WikiApplyResponse(BaseModel):
    success: bool
    op: str
    concept_name: str
    message: str
    created: bool = False
    appended: bool = False
    content_hash: str = ""


class WikiCompoundRequestBody(BaseModel):
    concept_name: str = Field(..., min_length=1)
    source_chat: str = Field(..., min_length=1)
    source_message: str = Field(..., min_length=1)


class WikiCompoundResponse(BaseModel):
    success: bool
    pending_edit_id: int
    concept_name: str
    message: str


class QueueStatusResponse(BaseModel):
    stats: dict[str, int]
    pending_items: list[dict[str, object]]
    failed_items: list[dict[str, object]] = Field(default_factory=list)
    compile_run: CompileRunResponse | None = None


class PendingEditsResponse(BaseModel):
    stats: dict[str, int]
    pending_edits: list[dict[str, object]]


class OperationResult(BaseModel):
    success: bool
    message: str


class ApprovePendingEditRequest(BaseModel):
    modified_content: str | None = None


class RepairTypesResponse(BaseModel):
    success: bool
    files_scanned: int
    files_repaired: int
    files_skipped: int
    message: str


class RepairPublicationResponse(BaseModel):
    success: bool
    files_scanned: int
    files_repaired: int
    files_skipped: int
    files_skipped_intentional_drafts: int = 0
    reindexed: int
    message: str


class ReindexVectorsResponse(BaseModel):
    success: bool
    scanned: int
    reindexed: int
    concepts_reindexed: int
    sidecars_reindexed: int
    assets_indexed: int
    skipped_drafts: int
    failed: int
    errors: list[str] = Field(default_factory=list)
    message: str


async def _get_wiki_archiver(
    llm: Annotated[BaseChatModel, Depends(get_optional_llm_for_user)],
    manager: Annotated[MemoryManager | None, Depends(get_optional_memory_manager)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> MemoryToWikiArchiver:
    """Get wiki archiver bound to an agent-scoped vault path."""
    from app.services.wiki.vault import get_wiki_archiver

    return get_wiki_archiver(llm, manager, agent_id=agent_id)


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
                claim_confidence=float(entry.get("claim_confidence", 0.0) or 0.0),
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


@router.post("/query", response_model=WikiQueryResponse)
async def query_wiki(
    request: WikiQueryRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiQueryResponse:
    try:
        from app.services.wiki.knowledge_query_service import (
            execute_wiki_knowledge_query,
        )

        query_result = await execute_wiki_knowledge_query(
            agent_id=agent_id,
            question=request.question,
            query_mode=request.mode,
            archiver=archiver,
        )
        source_snippets = _citation_sources_to_snippets(query_result.sources)
        return WikiQueryResponse(
            answer=query_result.answer,
            related_articles=query_result.related_articles,
            source_snippets=source_snippets,
            confidence_score=query_result.confidence_score,
            retrieval_trace=_retrieval_trace_to_response(
                query_result.retrieval_result.retrieval_trace,
            ),
        )
    except Exception as e:
        logger.error(f"Wiki query failed: {e}")
        raise HTTPException(status_code=500, detail="Wiki query failed") from e


@router.get("/assets/{filename}")
async def serve_wiki_asset(
    filename: str,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> FileResponse:
    from myrm_agent_harness.core.security.path_security import safe_join_path

    assets_dir = archiver._structure.wiki_dir / "assets"
    try:
        asset_path = safe_join_path(assets_dir, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset path") from exc

    if not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")

    media_type = "application/octet-stream"
    headers: dict[str, str] = {"Content-Disposition": f'inline; filename="{filename}"'}
    if filename.lower().endswith(".svg"):
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    return FileResponse(
        path=asset_path,
        media_type=media_type,
        filename=filename,
        headers=headers,
    )


@router.post("/compile", response_model=WikiCompileResponse)
async def compile_wiki(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiCompileResponse:
    from app.services.wiki.ingest_events import publish_wiki_ingest_snapshot

    try:
        from app.services.wiki.dedup_runner import wiki_dedup_blocks_compile

        if wiki_dedup_blocks_compile(agent_id=agent_id):
            raise HTTPException(
                status_code=409,
                detail="Duplicate review required: resolve exact/normalized groups before compiling",
            )
        result = await archiver._compiler.compile_all()
        from app.services.wiki.asset_index_service import run_wiki_asset_index

        await run_wiki_asset_index(archiver)
        await publish_wiki_ingest_snapshot(archiver, agent_id=agent_id)
        await _after_wiki_vault_mutation(archiver, "compile")
        return WikiCompileResponse(
            concepts_count=result.concepts_count,
            articles_generated=result.articles_generated,
            backlinks_created=result.backlinks_created,
            duration_ms=result.duration_ms,
            articles_pending=result.articles_pending,
            articles_published=result.articles_published,
            articles_blocked=result.articles_blocked,
            synthesis_pending=result.synthesis_pending,
            compile_run=_compile_run_response(archiver),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Wiki compilation failed: {e}")
        raise HTTPException(status_code=500, detail="Wiki compilation failed") from e


@router.post("/maintain", response_model=WikiMaintenanceResponse)
async def maintain_wiki(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
    mode: Annotated[
        Literal["structural", "full"],
        Query(description="Maintenance intensity: structural (default) or full"),
    ] = "structural",
) -> WikiMaintenanceResponse:
    try:
        from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode

        from app.services.wiki.maintain import run_wiki_maintain_job

        maintain_mode = MaintainMode.FULL if mode == "full" else MaintainMode.STRUCTURAL
        result = await run_wiki_maintain_job(
            llm=archiver._llm,
            agent_id=agent_id,
            mode=maintain_mode,
        )
        if result.skipped and result.skipped_reason == "compile_in_progress":
            raise HTTPException(
                status_code=409,
                detail="Wiki compilation is in progress; maintain skipped",
            )
        return WikiMaintenanceResponse(
            issues_found=result.issues_found,
            issues_fixed=result.issues_fixed,
            connections_discovered=result.connections_discovered,
            duration_ms=result.duration_ms,
            open_actions_count=result.open_actions_count,
            raw_security_removed=result.raw_security_removed,
            raw_security_removed_paths=list(result.raw_security_removed_paths),
            issues=[
                WikiHealthIssueResponse(
                    issue_type=str(item["issue_type"]),
                    severity=str(item["severity"]),
                    location=str(item["location"]),
                    description=str(item["description"]),
                    action_kind=str(item["action_kind"]),
                    suggested_fix=(str(item["suggested_fix"]) if item.get("suggested_fix") is not None else None),
                )
                for item in result.lint_issues
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Wiki maintenance failed: {e}")
        raise HTTPException(status_code=500, detail="Wiki maintenance failed") from e


@router.get("/health-report", response_model=WikiHealthReportResponse)
async def get_wiki_health_report(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiHealthReportResponse:
    """Return a zero-LLM structural health report with actionable lint issues."""
    try:
        from app.services.wiki.dedup_runner import get_wiki_dedup_stats
        from app.services.wiki.health_report_service import build_wiki_health_report

        dedup = get_wiki_dedup_stats(agent_id=agent_id)
        return await build_wiki_health_report(
            linter=archiver._linter,
            structure=archiver._structure,
            mode="structural",
            duplicate_groups_pending=dedup.duplicate_groups_pending,
            synthesis_pending=archiver._pending_mgr.count_synthesis_pending(),
        )
    except Exception as e:
        logger.error(f"Wiki health report failed: {e}")
        raise HTTPException(status_code=500, detail="Wiki health report failed") from e


class WikiDedupMemberResponse(BaseModel):
    relative_path: str
    size_bytes: int
    mtime_ns: int


class WikiDedupMemberSnippetResponse(BaseModel):
    relative_path: str
    snippet: str


class WikiDedupGroupResponse(BaseModel):
    group_id: int
    tier: Literal["exact", "normalized", "near"]
    fingerprint: str
    recommended_keep_path: str
    status: Literal["open", "deferred", "resolved"]
    members: list[WikiDedupMemberResponse]


class WikiDedupScanResponse(BaseModel):
    accepted: bool = False
    skipped: bool = False
    skipped_reason: str | None = None
    files_scanned: int = 0
    groups_found: int = 0
    open_groups: int = 0
    exact_groups: int = 0
    normalized_groups: int = 0
    near_groups: int = 0
    duration_ms: int = 0


class WikiDedupDispositionRequest(BaseModel):
    action: Literal["trash", "exclude", "dismiss", "defer"]
    reason: str = Field(default="", max_length=500)


class WikiDedupDispositionResponse(BaseModel):
    group_id: int
    action: Literal["trash", "exclude", "dismiss", "defer"]
    affected_paths: list[str] = Field(default_factory=list)
    compile_jobs_prevented: int = 0


class WikiDedupProgressResponse(BaseModel):
    phase: Literal["idle", "scanning", "grouping", "done", "failed"] = "idle"
    files_scanned: int = 0
    files_total: int = 0
    groups_found: int = 0
    message: str = ""


class WikiDedupTrashedEntryResponse(BaseModel):
    relative_path: str
    trash_relpath: str
    content_hash: str
    created_at: str


class WikiDedupExcludedEntryResponse(BaseModel):
    relative_path: str
    reason: str
    created_at: str


class WikiDedupVaultHygieneResponse(BaseModel):
    trashed: list[WikiDedupTrashedEntryResponse] = Field(default_factory=list)
    excluded: list[WikiDedupExcludedEntryResponse] = Field(default_factory=list)


class WikiDedupPathActionRequest(BaseModel):
    relative_path: str = Field(min_length=1, max_length=2048)


async def _schedule_post_import_dedup_scan(agent_id: str | None) -> None:
    try:
        from app.services.wiki.dedup_runner import schedule_wiki_dedup_scan

        await schedule_wiki_dedup_scan(agent_id=agent_id, incremental=True)
    except Exception as exc:
        logger.warning("Post-import wiki dedup scan failed: %s", exc)


@router.post("/dedup/scan", response_model=WikiDedupScanResponse, status_code=202)
async def scan_wiki_duplicates(
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
    incremental: Annotated[bool, Query(description="Incremental scan mode")] = True,
) -> WikiDedupScanResponse:
    from app.services.wiki.dedup_runner import schedule_wiki_dedup_scan

    result = await schedule_wiki_dedup_scan(agent_id=agent_id, incremental=incremental)
    if result.skipped and result.skipped_reason == "compile_in_progress":
        raise HTTPException(
            status_code=409,
            detail="Wiki compilation is in progress; dedup scan skipped",
        )
    if result.skipped and result.skipped_reason == "scan_in_progress":
        return WikiDedupScanResponse(skipped=True, skipped_reason=result.skipped_reason)
    if not result.accepted:
        return WikiDedupScanResponse(skipped=True, skipped_reason=result.skipped_reason)
    return WikiDedupScanResponse(accepted=True)


@router.get("/dedup/groups", response_model=list[WikiDedupGroupResponse])
async def list_wiki_duplicate_groups(
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> list[WikiDedupGroupResponse]:
    from app.services.wiki.dedup_runner import list_wiki_dedup_groups

    groups = list_wiki_dedup_groups(agent_id=agent_id)
    return [
        WikiDedupGroupResponse(
            group_id=group.group_id,
            tier=group.tier.value,
            fingerprint=group.fingerprint,
            recommended_keep_path=group.recommended_keep_path,
            status=group.status.value,
            members=[
                WikiDedupMemberResponse(
                    relative_path=member.relative_path,
                    size_bytes=member.size_bytes,
                    mtime_ns=member.mtime_ns,
                )
                for member in group.members
            ],
        )
        for group in groups
    ]


@router.get(
    "/dedup/groups/{group_id}/snippets",
    response_model=list[WikiDedupMemberSnippetResponse],
)
async def get_wiki_dedup_group_snippets(
    group_id: int,
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> list[WikiDedupMemberSnippetResponse]:
    from app.services.wiki.dedup_runner import get_wiki_dedup_group_snippets

    try:
        snippets = get_wiki_dedup_group_snippets(agent_id=agent_id, group_id=group_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [WikiDedupMemberSnippetResponse(relative_path=item.relative_path, snippet=item.snippet) for item in snippets]


@router.post("/dedup/groups/{group_id}/disposition", response_model=WikiDedupDispositionResponse)
async def apply_wiki_duplicate_disposition(
    group_id: int,
    request: WikiDedupDispositionRequest,
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiDedupDispositionResponse:
    from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import DispositionAction

    from app.services.wiki.dedup_runner import apply_wiki_dedup_disposition

    action = DispositionAction(request.action)
    if action in {DispositionAction.TRASH, DispositionAction.EXCLUDE} and not request.reason.strip():
        raise HTTPException(status_code=422, detail="reason is required for trash/exclude dispositions")
    try:
        result = await apply_wiki_dedup_disposition(
            agent_id=agent_id,
            group_id=group_id,
            action=action,
            reason=request.reason.strip() or "Duplicate review disposition",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WikiDedupDispositionResponse(
        group_id=result.group_id,
        action=result.action.value,
        affected_paths=list(result.affected_paths),
        compile_jobs_prevented=result.compile_jobs_prevented,
    )


@router.get("/dedup/progress", response_model=WikiDedupProgressResponse)
async def get_wiki_dedup_progress(
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiDedupProgressResponse:
    from app.services.wiki.dedup_runner import get_wiki_dedup_progress

    progress = get_wiki_dedup_progress(agent_id=agent_id)
    return WikiDedupProgressResponse(
        phase=progress.phase,
        files_scanned=progress.files_scanned,
        files_total=progress.files_total,
        groups_found=progress.groups_found,
        message=progress.message,
    )


@router.get("/dedup/vault-hygiene", response_model=WikiDedupVaultHygieneResponse)
async def get_wiki_dedup_vault_hygiene(
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiDedupVaultHygieneResponse:
    from app.services.wiki.dedup_runner import get_wiki_dedup_vault_hygiene

    snapshot = get_wiki_dedup_vault_hygiene(agent_id=agent_id)
    return WikiDedupVaultHygieneResponse(
        trashed=[
            WikiDedupTrashedEntryResponse(
                relative_path=entry.relative_path,
                trash_relpath=entry.trash_relpath,
                content_hash=entry.content_hash,
                created_at=entry.created_at,
            )
            for entry in snapshot.trashed
        ],
        excluded=[
            WikiDedupExcludedEntryResponse(
                relative_path=entry.relative_path,
                reason=entry.reason,
                created_at=entry.created_at,
            )
            for entry in snapshot.excluded
        ],
    )


@router.post("/dedup/trash/restore", response_model=WikiDedupTrashedEntryResponse)
async def restore_wiki_dedup_trashed_raw(
    request: WikiDedupPathActionRequest,
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiDedupTrashedEntryResponse:
    from app.services.wiki.dedup_runner import restore_wiki_dedup_trashed

    try:
        restored = await restore_wiki_dedup_trashed(agent_id=agent_id, relative_path=request.relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WikiDedupTrashedEntryResponse(
        relative_path=restored.relative_path,
        trash_relpath=restored.trash_relpath,
        content_hash=restored.content_hash,
        created_at=restored.created_at,
    )


@router.post("/dedup/excluded/undo", response_model=WikiDedupExcludedEntryResponse)
async def undo_wiki_dedup_excluded_raw(
    request: WikiDedupPathActionRequest,
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiDedupExcludedEntryResponse:
    from app.services.wiki.dedup_runner import undo_wiki_dedup_excluded

    try:
        restored = await undo_wiki_dedup_excluded(agent_id=agent_id, relative_path=request.relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WikiDedupExcludedEntryResponse(
        relative_path=restored.relative_path,
        reason=restored.reason,
        created_at=restored.created_at,
    )


@router.get("/stats", response_model=WikiStatsResponse)
async def get_wiki_stats(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiStatsResponse:
    try:
        from app.services.wiki.vault import (
            is_legacy_migration_complete,
            is_vault_ready,
        )

        concepts = archiver._structure.list_concepts()
        raw_files = archiver._structure.list_raw_files()
        from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
            count_log_entries,
            hot_updated_at_iso,
        )

        index_path = archiver._structure.get_index_file_path()
        from app.services.files.reveal_utils import is_obsidian_direct_launch_available
        from app.services.wiki.structural_stats_cache import (
            get_structural_lint_snapshot_cached,
        )

        structural_cached = get_structural_lint_snapshot_cached(archiver._structure)
        structural = structural_cached.snapshot
        from app.services.wiki.asset_index_service import (
            ensure_archiver_asset_indexer,
            wiki_asset_index_enabled,
        )
        from app.services.wiki.vault import read_vault_git_status

        await ensure_archiver_asset_indexer(archiver)
        asset_enabled = await wiki_asset_index_enabled()
        if archiver._asset_indexer is not None:
            asset_stats = archiver._asset_indexer.get_stats()
            asset_index = WikiAssetIndexStatsResponse(
                indexed=asset_stats.indexed,
                pending=asset_stats.pending,
                failed=asset_stats.failed,
                total_files=asset_stats.total_files,
                enabled=True,
            )
        else:
            assets_dir = archiver._structure.wiki_dir / "assets"
            total_files = len([p for p in assets_dir.iterdir() if p.is_file()]) if assets_dir.is_dir() else 0
            asset_index = WikiAssetIndexStatsResponse(
                total_files=total_files,
                pending=total_files,
                enabled=asset_enabled,
            )
        git_status = read_vault_git_status(archiver._structure, archiver._config)
        from app.database.connection import get_session
        from app.services.wiki.maintain import load_wiki_maintain_state

        async with get_session() as db:
            maintain = await load_wiki_maintain_state(db, agent_id=agent_id)
        maintain_state = WikiMaintainStateResponse(
            last_run_at=(maintain.last_run_at.isoformat() if maintain.last_run_at else None),
            last_mode=maintain.last_mode,
            last_issues_found=maintain.last_issues_found,
            last_issues_fixed=maintain.last_issues_fixed,
            last_connections_discovered=maintain.last_connections_discovered,
            last_duration_ms=maintain.last_duration_ms,
            last_skipped_reason=maintain.last_skipped_reason,
        )
        from app.services.wiki.dedup_runner import (
            get_wiki_dedup_stats,
            wiki_dedup_blocks_compile,
        )

        dedup = get_wiki_dedup_stats(agent_id=agent_id)
        dedup_stats = WikiDedupStatsResponse(
            duplicate_groups_pending=dedup.duplicate_groups_pending,
            compile_jobs_prevented=dedup.compile_jobs_prevented,
            eligible_raw_count=dedup.eligible_raw_count,
            excluded_raw_count=dedup.excluded_raw_count,
            trashed_raw_count=dedup.trashed_raw_count,
            blocks_compile=wiki_dedup_blocks_compile(agent_id=agent_id),
        )
        return WikiStatsResponse(
            total_concepts=len(concepts),
            total_articles=len(concepts),
            total_raw_files=len(raw_files),
            wiki_path=str(archiver.get_wiki_path()),
            vault_ready=is_vault_ready(agent_id),
            legacy_migrated=is_legacy_migration_complete(),
            cognitive_index_ready=index_path.exists(),
            cognitive_log_entries=count_log_entries(archiver._structure),
            cognitive_hot_updated_at=hot_updated_at_iso(archiver._structure),
            synthesis_pending=archiver._pending_mgr.count_synthesis_pending(),
            obsidian_launch_available=is_obsidian_direct_launch_available(),
            vault_git_enabled=git_status.enabled,
            vault_git_initialized=git_status.initialized,
            vault_git_last_commit=git_status.last_commit,
            structural_issues=WikiStructuralIssuesResponse(
                broken_links=structural.broken_links,
                invalid_frontmatter_types=structural.invalid_frontmatter_types,
                provenance_gaps=structural.provenance_gaps,
                scanned_concepts=structural.scanned_concepts,
            ),
            dedup_stats=dedup_stats,
            maintain_state=maintain_state,
            asset_index=asset_index,
        )
    except Exception as e:
        logger.error("Wiki full state retrieval failed: %s", e)
        raise HTTPException(status_code=500, detail="Wiki state retrieval failed") from e


# --- Concepts CRUD Endpoints ---


@router.get("/concepts", response_model=ConceptListResponse)
async def list_concepts(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> ConceptListResponse:
    """List or search concept names with pagination."""
    if query:
        # Use FTS5 indexer for fast search
        results = await archiver._query_engine._indexer.search(query, limit=limit + 1, offset=offset)
        concept_names = [name for name, _ in results]

        has_more = len(concept_names) > limit
        if has_more:
            concept_names = concept_names[:limit]

        return ConceptListResponse(concepts=concept_names, total=len(concept_names), has_more=has_more)
    else:
        paths = archiver._structure.list_concepts()
        concept_names = []
        for p in paths:
            try:
                rel = p.relative_to(archiver._structure.concepts_dir)
                concept_names.append(str(rel.with_suffix("")).replace("\\", "/"))
            except ValueError:
                concept_names.append(p.stem)

        total = len(concept_names)

        sliced = concept_names[offset : offset + limit]
        has_more = offset + limit < total

        return ConceptListResponse(concepts=sliced, total=total, has_more=has_more)


@router.get("/tree", response_model=list[TreeNode])
async def get_wiki_tree(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> list[TreeNode]:
    """Get the full directory tree of the wiki concepts."""
    from myrm_agent_harness.toolkits.wiki.maintenance.stale_summary import (
        collect_stale_raw_path_set,
        concept_uses_stale_sources,
    )

    concepts_dir = archiver._structure.concepts_dir
    stale_paths = collect_stale_raw_path_set(archiver._structure)

    def build_tree(dir_path: Path, rel_base: Path) -> list[TreeNode]:
        nodes: list[TreeNode] = []
        if not dir_path.exists():
            return nodes

        for item in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
            if item.is_dir():
                rel_id = str(item.relative_to(rel_base)).replace("\\", "/")
                children = build_tree(item, rel_base)
                child_statuses = [child.ingest_status for child in children if child.ingest_status]
                folder_status: str | None = None
                if any(status == "tracked-modified" for status in child_statuses):
                    folder_status = "tracked-modified"
                elif child_statuses:
                    folder_status = "tracked-clean"
                nodes.append(
                    TreeNode(
                        id=rel_id,
                        name=item.name,
                        is_dir=True,
                        ingest_status=folder_status,
                        children=children,
                    )
                )
            elif item.suffix == ".md":
                rel_id = str(item.relative_to(rel_base).with_suffix("")).replace("\\", "/")
                ingest_status: str | None = None
                if stale_paths:
                    try:
                        concept_content = item.read_text(encoding="utf-8")
                        ingest_status = (
                            "tracked-modified" if concept_uses_stale_sources(concept_content, stale_paths) else "tracked-clean"
                        )
                    except OSError:
                        ingest_status = None
                nodes.append(
                    TreeNode(
                        id=rel_id,
                        name=item.stem,
                        is_dir=False,
                        ingest_status=ingest_status,
                    )
                )
        return nodes

    return build_tree(concepts_dir, concepts_dir)


@router.get("/raw/tree", response_model=list[TreeNode])
async def get_wiki_raw_tree(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> list[TreeNode]:
    """Get the directory tree of raw source files with ingest status annotations."""
    from myrm_agent_harness.toolkits.wiki.maintenance.stale_summary import (
        collect_stale_raw_files,
        collect_stale_raw_path_set,
        resolve_raw_file_ingest_status,
    )

    raw_dir = archiver._structure.raw_dir
    summary = collect_stale_raw_files(archiver._structure)
    stale_paths = collect_stale_raw_path_set(archiver._structure)
    last_compile_time = summary.last_compile_time

    def build_raw_tree(dir_path: Path, rel_base: Path) -> list[TreeNode]:
        nodes: list[TreeNode] = []
        if not dir_path.exists():
            return nodes

        for item in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
            rel_path = item.relative_to(rel_base)
            rel_id = str(rel_path).replace("\\", "/")
            if item.is_dir():
                children = build_raw_tree(item, rel_base)
                child_statuses = [child.ingest_status for child in children if child.ingest_status]
                folder_status: str | None = None
                if any(status == "tracked-modified" for status in child_statuses):
                    folder_status = "tracked-modified"
                elif child_statuses:
                    folder_status = "tracked-clean"
                nodes.append(
                    TreeNode(
                        id=rel_id,
                        name=item.name,
                        is_dir=True,
                        ingest_status=folder_status,
                        children=children,
                    )
                )
            elif item.suffix == ".md":
                rel_id = str(rel_path.with_suffix("")).replace("\\", "/")
                stale_key = f"raw/{rel_id}.md"
                ingest_status = resolve_raw_file_ingest_status(
                    stale_key,
                    stale_paths=stale_paths,
                    last_compile_time=last_compile_time,
                )
                nodes.append(
                    TreeNode(
                        id=rel_id,
                        name=item.stem,
                        is_dir=False,
                        ingest_status=ingest_status,
                    )
                )
        return nodes

    return build_raw_tree(raw_dir, raw_dir)


@router.post("/tree/folder", response_model=OperationResult)
async def create_wiki_folder(
    request: CreateFolderRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> OperationResult:
    """Create a new folder in the wiki concepts directory."""
    safe_path = archiver._structure._sanitize_path(request.path)
    folder_path = archiver._structure.concepts_dir / safe_path
    try:
        folder_path.mkdir(parents=True, exist_ok=True)
        return OperationResult(success=True, message=f"Folder {safe_path} created")
    except Exception as e:
        logger.error("Wiki folder creation failed: %s", e)
        raise HTTPException(status_code=500, detail="Folder creation failed") from e


@router.put("/tree/move", response_model=OperationResult)
async def move_wiki_node(
    request: MoveNodeRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> OperationResult:
    """Move a file or folder and update relative links."""
    safe_source = archiver._structure._sanitize_path(request.source_path)
    safe_target = archiver._structure._sanitize_path(request.target_path)

    concepts_dir = archiver._structure.concepts_dir

    # Check if source is a file or dir
    source_file = concepts_dir / f"{safe_source}.md"
    source_dir = concepts_dir / safe_source

    if source_file.exists():
        old_path = source_file
        new_path = concepts_dir / f"{safe_target}.md"
    elif source_dir.exists() and source_dir.is_dir():
        old_path = source_dir
        new_path = concepts_dir / safe_target
    else:
        raise HTTPException(status_code=404, detail="Source not found")

    if new_path.exists():
        raise HTTPException(status_code=400, detail="Target already exists")

    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.rename(new_path)

        # Refactor links
        from myrm_agent_harness.toolkits.wiki.core.refactor import LinkRefactorEngine

        engine = LinkRefactorEngine(concepts_dir)
        updated_count = engine.refactor_links(old_path, new_path)

        from myrm_agent_harness.toolkits.wiki.pipeline.publication import (
            ConceptPathMapping,
            reindex_concepts_after_move,
        )

        mappings: list[ConceptPathMapping] = []
        if old_path.is_file():
            mappings.append(ConceptPathMapping(old_concept=safe_source, new_concept=safe_target))
        else:
            for md_file in new_path.rglob("*.md"):
                rel_new = md_file.relative_to(concepts_dir)
                concept_new = str(rel_new.with_suffix("")).replace("\\", "/")
                rel_to_new_dir = md_file.relative_to(new_path)
                old_md_file = old_path / rel_to_new_dir
                rel_old = old_md_file.relative_to(concepts_dir)
                concept_old = str(rel_old.with_suffix("")).replace("\\", "/")
                mappings.append(ConceptPathMapping(old_concept=concept_old, new_concept=concept_new))

        await reindex_concepts_after_move(
            archiver._structure,
            archiver._query_engine._indexer,
            mappings,
        )

        await _after_wiki_vault_mutation(archiver, "move concept")
        return OperationResult(success=True, message=f"Moved successfully. Updated {updated_count} files.")
    except Exception as e:
        logger.error("Wiki node move failed: %s", e)
        raise HTTPException(status_code=500, detail="Move operation failed") from e


@router.delete("/tree/folder", response_model=OperationResult)
async def delete_wiki_folder(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    path: str = Query(..., min_length=1),
) -> OperationResult:
    """Safely delete a folder and clear all its files from the indexer."""
    try:
        deleted_count = await archiver._structure.delete_folder_safe(path, archiver._query_engine._indexer)
        await _after_wiki_vault_mutation(archiver, "delete folder")
        return OperationResult(success=True, message=f"Folder deleted. Unindexed {deleted_count} files.")
    except Exception as e:
        logger.error("Wiki folder deletion failed: %s", e)
        raise HTTPException(status_code=500, detail="Folder deletion failed") from e


@router.get("/concepts/{name:path}", response_model=ConceptResponse)
async def get_concept(name: str, archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]) -> ConceptResponse:
    """Get content of a specific concept."""
    path = archiver._structure.resolve_concept_file_path(name)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Concept not found")
    content = path.read_text(encoding="utf-8")
    from myrm_agent_harness.toolkits.wiki.core.canonical_registry import (
        compute_page_lease_hash,
    )
    from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import (
        load_frontmatter_metadata,
    )

    metadata, _body = load_frontmatter_metadata(content)
    return ConceptResponse(
        name=name,
        content=content,
        content_hash=compute_page_lease_hash(content),
        provenance=str(metadata["provenance"]) if metadata.get("provenance") else None,
        source_chat=_str_or_none(metadata.get("source_chat")),
        source_message=_str_or_none(metadata.get("source_message")),
        claims=_claims_to_response_items(content, archiver._structure),
        editor_sections=_editor_sections_to_response(content),
    )


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
        "timeline_rejected": 422,
    }
    return mapping.get(code, 400)


@router.post("/apply", response_model=WikiApplyResponse)
async def apply_wiki_mutation_endpoint(
    request: WikiApplyRequestBody,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    caller: Annotated[
        Literal["agent", "settings", "chat"],
        Query(description="Apply caller surface; full-document replace is settings-only"),
    ] = "settings",
) -> WikiApplyResponse:
    """Apply a narrow wiki mutation through the WPG publish gate."""
    from myrm_agent_harness.toolkits.wiki.pipeline.apply import (
        WikiApplyError,
        WikiApplyOp,
        WikiApplyRequest,
        apply_wiki_mutation,
    )

    claim_payloads: tuple[dict[str, object], ...] = tuple(
        {
            "id": claim.id,
            "text": claim.text,
            "status": claim.status,
            "confidence": claim.confidence,
            "updatedAt": claim.updated_at,
            "evidence": claim.evidence,
        }
        for claim in request.claims
    )
    apply_request = WikiApplyRequest(
        op=WikiApplyOp(request.op),
        concept_name=request.concept_name,
        compiled_truth=request.compiled_truth,
        timeline_entry=request.timeline_entry,
        content=request.content,
        body=request.body,
        tags=tuple(request.tags) if request.tags is not None else None,
        aliases=tuple(request.aliases) if request.aliases is not None else None,
        sources=tuple(request.sources) if request.sources is not None else None,
        claims=claim_payloads,
        clear_confidence=request.clear_confidence,
        page_type=request.page_type,
        provenance=request.provenance,
        metadata=dict(request.metadata),
        canonical_id=request.canonical_id,
        if_match=request.if_match,
    )
    try:
        result = await apply_wiki_mutation(
            archiver._structure,
            archiver._query_engine._indexer,
            apply_request,
            caller=caller,
        )
    except WikiApplyError as exc:
        raise HTTPException(
            status_code=_wiki_apply_http_status(exc.code),
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except Exception as exc:
        logger.error("Wiki mutation apply failed: %s", exc)
        raise HTTPException(status_code=500, detail="Wiki mutation failed") from exc

    await _after_wiki_vault_mutation(archiver, "apply mutation")
    return WikiApplyResponse(
        success=result.success,
        op=result.op.value,
        concept_name=result.concept_name,
        message=result.message,
        created=result.created,
        appended=result.appended,
        content_hash=result.content_hash,
    )


def _wiki_compound_http_status(code: str) -> int:
    mapping = {
        "already_staged": 409,
        "incognito_forbidden": 403,
        "invalid_request": 422,
        "invalid_role": 422,
        "message_not_found": 404,
    }
    return mapping.get(code, 400)


@router.post("/compound", response_model=WikiCompoundResponse)
async def compound_chat_message_to_wiki(
    request: WikiCompoundRequestBody,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> WikiCompoundResponse:
    """Stage a chat Q&A pair as a pending wiki edit (HITL; zero LLM)."""
    from app.services.wiki.chat_compound_service import (
        ChatCompoundServiceError,
        stage_chat_compound_from_message,
    )

    try:
        result = await stage_chat_compound_from_message(
            archiver,
            concept_name=request.concept_name,
            source_chat=request.source_chat,
            source_message=request.source_message,
        )
    except ChatCompoundServiceError as exc:
        raise HTTPException(
            status_code=_wiki_compound_http_status(exc.code),
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except Exception as exc:
        logger.error("Wiki chat compound failed: %s", exc)
        raise HTTPException(status_code=500, detail="Wiki chat compound failed") from exc

    return WikiCompoundResponse(
        success=True,
        pending_edit_id=result.pending_edit_id,
        concept_name=result.concept_name,
        message="Chat Q&A staged for wiki review",
    )


@router.delete("/concepts/{name:path}", response_model=OperationResult)
async def delete_concept(name: str, archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]) -> OperationResult:
    """Delete a concept file manually."""
    path = archiver._structure.get_concept_file_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Concept not found")
    try:
        path.unlink()
        await archiver._query_engine._indexer.delete(name)
        await _after_wiki_vault_mutation(archiver, "delete concept")
        return OperationResult(success=True, message=f"Concept {name} deleted")
    except Exception as e:
        logger.error("Wiki concept deletion failed: %s", e)
        raise HTTPException(status_code=500, detail="Concept deletion failed") from e


class DeleteRawRequest(BaseModel):
    forget_reason: str = Field(..., min_length=1, description="Why this raw evidence is being removed")


@router.delete("/raw/{path:path}", response_model=OperationResult)
async def delete_raw_source(
    path: str,
    body: DeleteRawRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> OperationResult:
    """Forget a raw source file and re-anchor dependent compiled pages."""
    from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import (
        RawGateError,
        forget_evidence,
    )

    try:
        result = await forget_evidence(
            archiver._structure,
            path,
            reason=body.forget_reason,
            caller="settings",
            compiler=archiver._compiler,
            indexer=archiver._query_engine._indexer,
        )
    except RawGateError as exc:
        if exc.code == "not_found":
            raise HTTPException(status_code=404, detail=exc.message) from exc
        if exc.code in {"invalid_request", "forbidden_for_caller"}:
            raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
        raise HTTPException(status_code=500, detail=exc.message) from exc

    affected = len(result.affected_concepts)
    republished = len(result.republished_concepts)
    await _after_wiki_vault_mutation(archiver, "forget raw source")
    return OperationResult(
        success=True,
        message=f"Forgot raw source {result.relative_path} ({affected} affected, {republished} republished)",
    )


# --- Queue Management Endpoints ---


@router.get("/queue", response_model=QueueStatusResponse)
async def get_queue_status(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> QueueStatusResponse:
    """Get ingestion queue statistics and pending items."""
    stats = archiver._queue.get_stats()
    items = archiver._queue.get_pending_items(limit=20)
    failed_items = archiver._queue.get_failed_items(limit=20)
    return QueueStatusResponse(
        stats=stats,
        pending_items=items,
        failed_items=failed_items,
        compile_run=_compile_run_response(archiver),
    )


@router.post("/queue/cancel", response_model=OperationResult)
async def cancel_queue(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> OperationResult:
    """Cancel all pending ingestion jobs."""
    from app.services.wiki.ingest_events import publish_wiki_ingest_snapshot

    count = archiver._queue.cancel_pending()
    await publish_wiki_ingest_snapshot(archiver, agent_id=agent_id)
    return OperationResult(success=True, message=f"Cancelled {count} jobs")


@router.post("/queue/retry", response_model=OperationResult)
async def retry_queue_failed(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> OperationResult:
    """Reset transient failed jobs back to pending."""
    from app.services.wiki.ingest_events import publish_wiki_ingest_snapshot

    count = archiver._queue.reset_transient_failed()
    await publish_wiki_ingest_snapshot(archiver, agent_id=agent_id)
    return OperationResult(success=True, message=f"Reset {count} transient failed jobs to pending")


@router.post("/queue/retry-all", response_model=OperationResult)
async def retry_queue_failed_all(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> OperationResult:
    """Reset all failed jobs back to pending."""
    from app.services.wiki.ingest_events import publish_wiki_ingest_snapshot

    count = archiver._queue.reset_failed()
    archiver._compiler.resume_compile_worker()
    await publish_wiki_ingest_snapshot(archiver, agent_id=agent_id)
    return OperationResult(success=True, message=f"Reset {count} failed jobs to pending")


@router.post("/queue/resume-circuit", response_model=OperationResult)
async def resume_compile_circuit(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> OperationResult:
    """Resume compile worker after a circuit pause."""
    from app.services.wiki.ingest_events import publish_wiki_ingest_snapshot

    archiver._compiler.resume_compile_worker()
    await publish_wiki_ingest_snapshot(archiver, agent_id=agent_id)
    return OperationResult(success=True, message="Compile worker resumed")


# --- HITL Pending Edits Endpoints ---


@router.get("/pending", response_model=PendingEditsResponse)
async def get_pending_edits(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> PendingEditsResponse:
    """Get stats and list of pending Wiki edits (HITL)."""
    stats = archiver._pending_mgr.get_stats()
    stats["synthesis_pending"] = archiver._pending_mgr.count_synthesis_pending()
    edits = archiver._pending_mgr.get_pending_edits(limit=50)
    return PendingEditsResponse(stats=stats, pending_edits=edits)


@router.post("/pending/{edit_id}/approve", response_model=OperationResult)
async def approve_pending_edit(
    edit_id: int,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    request: ApprovePendingEditRequest = ApprovePendingEditRequest(),
) -> OperationResult:
    """Approve a pending edit and merge it to the wiki."""
    from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import (
        FrontmatterValidationError,
    )
    from myrm_agent_harness.toolkits.wiki.pipeline.publication import (
        StalePendingApprovalError,
    )

    try:
        success = await archiver._pending_mgr.approve_edit(edit_id, request.modified_content)
    except FrontmatterValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_frontmatter",
                "message": "Page metadata is incomplete. Add a valid page type before approving.",
                "errors": list(exc.errors),
            },
        ) from exc
    except StalePendingApprovalError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "stale_pending",
                "message": str(exc),
            },
        ) from exc
    if not success:
        raise HTTPException(status_code=400, detail="Edit not found or already processed")
    _refresh_wiki_cognitive_map(
        archiver,
        WikiMapEventType.PENDING_APPROVE,
        f"Approved pending edit {edit_id}",
        {"edit_id": edit_id},
    )
    await _after_wiki_vault_mutation(archiver, f"approve pending edit {edit_id}")
    return OperationResult(success=True, message=f"Approved edit {edit_id}")


@router.post("/pending/{edit_id}/reject", response_model=OperationResult)
async def reject_pending_edit(
    edit_id: int, archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]
) -> OperationResult:
    """Reject a pending edit."""
    success = archiver._pending_mgr.reject_edit(edit_id)
    if not success:
        raise HTTPException(status_code=400, detail="Edit not found or already processed")
    return OperationResult(success=True, message=f"Rejected edit {edit_id}")


@router.post("/repair-types", response_model=RepairTypesResponse)
async def repair_wiki_frontmatter_types(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> RepairTypesResponse:
    """Repair missing or invalid frontmatter `type` across concept and raw markdown files."""
    from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import (
        repair_missing_types,
    )

    result = repair_missing_types(archiver._structure)
    message = f"Repaired {result.files_repaired} of {result.files_scanned} scanned files"
    if result.errors:
        message = f"{message}; {len(result.errors)} errors"
    if result.files_repaired > 0:
        _refresh_wiki_cognitive_map(
            archiver,
            WikiMapEventType.REPAIR_TYPES,
            message,
            {
                "files_scanned": result.files_scanned,
                "files_repaired": result.files_repaired,
                "files_skipped": result.files_skipped,
            },
        )
        await _after_wiki_vault_mutation(archiver, "repair frontmatter types")
    return RepairTypesResponse(
        success=len(result.errors) == 0,
        files_scanned=result.files_scanned,
        files_repaired=result.files_repaired,
        files_skipped=result.files_skipped,
        message=message,
    )


@router.post("/repair-publication", response_model=RepairPublicationResponse)
async def repair_wiki_publication(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> RepairPublicationResponse:
    """Grandfather missing publish_status; preserve intentional draft/blocked pages and reindex."""
    from myrm_agent_harness.toolkits.wiki.pipeline.publication import (
        repair_publication_status,
    )

    result = await repair_publication_status(archiver._structure, archiver._query_engine._indexer)
    message = f"Repaired {result.files_repaired} of {result.files_scanned} scanned files; reindexed {result.reindexed}"
    if result.files_skipped_intentional_drafts > 0:
        message = f"{message}; skipped {result.files_skipped_intentional_drafts} intentional draft pages"
    if result.errors:
        message = f"{message}; {len(result.errors)} errors"
    if result.files_repaired > 0 or result.reindexed > 0:
        _refresh_wiki_cognitive_map(
            archiver,
            WikiMapEventType.REPAIR_TYPES,
            message,
            {
                "files_scanned": result.files_scanned,
                "files_repaired": result.files_repaired,
                "files_skipped": result.files_skipped,
                "files_skipped_intentional_drafts": result.files_skipped_intentional_drafts,
                "reindexed": result.reindexed,
            },
        )
        await _after_wiki_vault_mutation(archiver, "repair publication status")
    return RepairPublicationResponse(
        success=len(result.errors) == 0,
        files_scanned=result.files_scanned,
        files_repaired=result.files_repaired,
        files_skipped=result.files_skipped,
        files_skipped_intentional_drafts=result.files_skipped_intentional_drafts,
        reindexed=result.reindexed,
        message=message,
    )


@router.post("/reindex-vectors", response_model=ReindexVectorsResponse)
async def reindex_wiki_vectors(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> ReindexVectorsResponse:
    """Rebuild published concept, sidecar, and optional asset vectors with the current embedding model."""
    from myrm_agent_harness.toolkits.wiki.retrieval.reindex_vectors import (
        reindex_published_vectors,
    )

    from app.services.wiki.asset_index_service import ensure_archiver_asset_indexer
    from app.services.wiki.ingest_events import publish_wiki_ingest_snapshot

    await ensure_archiver_asset_indexer(archiver)
    result = await reindex_published_vectors(
        archiver._structure,
        archiver._query_engine._indexer,
        asset_indexer=archiver._asset_indexer,
    )
    message = (
        f"Reindexed {result.concepts_reindexed} concepts, "
        f"{result.sidecars_reindexed} sidecars, {result.assets_indexed} assets "
        f"({result.scanned} concepts scanned"
    )
    if result.skipped_drafts:
        message = f"{message}; {result.skipped_drafts} drafts skipped"
    message = f"{message})"
    if result.failed:
        message = f"{message}; {result.failed} failed"
    if result.reindexed > 0 or result.failed > 0:
        await _after_wiki_vault_mutation(archiver, "reindex wiki vectors")
    await publish_wiki_ingest_snapshot(archiver, agent_id=agent_id)
    return ReindexVectorsResponse(
        success=result.failed == 0,
        scanned=result.scanned,
        reindexed=result.reindexed,
        concepts_reindexed=result.concepts_reindexed,
        sidecars_reindexed=result.sidecars_reindexed,
        assets_indexed=result.assets_indexed,
        skipped_drafts=result.skipped_drafts,
        failed=result.failed,
        errors=list(result.errors),
        message=message,
    )


# --- Purpose Endpoint ---


class PurposeResponse(BaseModel):
    purpose: str


class PurposeUpdateRequest(BaseModel):
    purpose: str = Field(..., max_length=2000, description="Knowledge base direction/scope")


@router.get("/purpose", response_model=PurposeResponse)
def get_wiki_purpose(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> PurposeResponse:
    """Get the knowledge base purpose/direction."""
    purpose_path = archiver._structure.get_purpose_path()
    if purpose_path.exists():
        return PurposeResponse(purpose=purpose_path.read_text(encoding="utf-8"))
    return PurposeResponse(purpose="")


@router.put("/purpose", response_model=OperationResult)
def update_wiki_purpose(
    request: PurposeUpdateRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> OperationResult:
    """Update the knowledge base purpose/direction."""
    purpose_path = archiver._structure.get_purpose_path()
    purpose_path.parent.mkdir(parents=True, exist_ok=True)
    purpose_path.write_text(request.purpose, encoding="utf-8")
    return OperationResult(success=True, message="Purpose updated")


# --- Graph Endpoints ---


class GraphInsightsResponse(BaseModel):
    unexpected_connections: list[dict[str, object]]
    knowledge_gaps: list[dict[str, object]]
    communities: list[dict[str, object]]


@router.get("/graph/insights", response_model=GraphInsightsResponse)
def get_graph_insights(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> GraphInsightsResponse:
    """Get graph structure insights: unexpected connections, knowledge gaps, communities."""
    try:
        insights = archiver._query_engine._indexer.graph_insights()
        return GraphInsightsResponse(**insights)
    except Exception as e:
        logger.error(f"Graph insights failed: {e}")
        raise HTTPException(status_code=500, detail="Graph insights failed") from e


class DeepResearchRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="Topic to research and add to wiki")
    search_queries: list[str] = Field(default_factory=list, description="Optional custom search queries")


@router.post("/research", response_model=OperationResult)
async def deep_research(
    request: DeepResearchRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> OperationResult:
    """Research a topic via web search and ingest results into the wiki."""
    try:
        from myrm_agent_harness.toolkits.web_search.providers.web_searcher import WebSearcher

        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.config_parsers import (
            verify_search_service_available,
        )

        configs = await load_user_configs()
        if not configs.search_is_user_configured or configs.search_cfg is None:
            raise HTTPException(
                status_code=400,
                detail="Search service is not configured in WebUI Settings",
            )
        if not await verify_search_service_available(configs.search_cfg):
            raise HTTPException(
                status_code=503,
                detail="Configured search service is unavailable",
            )

        searcher = WebSearcher(configs.search_cfg)

        queries = request.search_queries or [request.topic]
        all_content: list[str] = []

        for query in queries[:3]:
            try:
                summary, _docs, _err = await searcher.search_and_process(query, num_results=5)
                if summary:
                    all_content.append(f"# Research: {query}\n\n{summary}")
            except Exception as e:
                logger.warning(f"Search failed for '{query}': {e}")

        if not all_content:
            return OperationResult(success=False, message="No search results found")

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        safe_topic = request.topic.replace(" ", "_").replace("/", "_")[:50]
        raw_file = archiver._structure.raw_dir / f"research_{safe_topic}_{timestamp}.md"
        raw_file.write_text("\n\n---\n\n".join(all_content), encoding="utf-8")

        archiver._compiler.enqueue_file(raw_file)

        return OperationResult(
            success=True,
            message=f"Research on '{request.topic}' ingested, compilation started",
        )
    except ImportError:
        return OperationResult(success=False, message="Web search toolkit not configured")
    except Exception as e:
        logger.error(f"Deep research failed: {e}")
        raise HTTPException(status_code=500, detail="Deep research failed") from e


class IngestArtifactRequest(BaseModel):
    artifact_id: str = Field(..., min_length=1, description="Artifact ID to ingest into wiki")


@router.post("/ingest", response_model=OperationResult)
async def ingest_artifact(
    request: IngestArtifactRequest,
    llm: Annotated[BaseChatModel, Depends(get_optional_llm_for_user)],
    manager: Annotated[MemoryManager | None, Depends(get_optional_memory_manager)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> OperationResult:
    """Ingest an artifact's content into the wiki knowledge base."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.api.dependencies import get_workspace_root
    from app.database.connection import get_session
    from app.database.models.artifact import Artifact
    from app.services.wiki.agent_scope import resolve_chat_agent_id
    from app.services.wiki.vault import get_wiki_archiver

    workspace_root = get_workspace_root()
    try:
        async with get_session() as db:
            stmt = (
                select(Artifact)
                .options(selectinload(Artifact.versions))
                .where(Artifact.id == request.artifact_id, Artifact.is_deleted.is_(False))
            )
            result = await db.execute(stmt)
            artifact = result.scalars().first()

        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        if not artifact.versions:
            raise HTTPException(status_code=400, detail="Artifact has no versions")

        effective_agent_id = agent_id or await resolve_chat_agent_id(artifact.chat_id)
        archiver = get_wiki_archiver(llm, manager, agent_id=effective_agent_id)

        latest_version = sorted(artifact.versions, key=lambda v: v.created_at, reverse=True)[0]
        vault = ArtifactVault(workspace_root)
        vault_uri = latest_version.vault_uri
        obj_id = vault_uri[len("vault://") :] if vault_uri.startswith("vault://") else vault_uri
        obj_path = vault.get_object_path(obj_id)

        if not obj_path.exists():
            raise HTTPException(status_code=404, detail="Artifact content not found on disk")

        content = obj_path.read_text(encoding="utf-8")
        if not content.strip():
            return OperationResult(success=False, message="Artifact content is empty")

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        safe_name = artifact.name.replace(" ", "_").replace("/", "_")[:80]
        raw_file = archiver._structure.raw_dir / f"artifact_{safe_name}_{timestamp}.md"
        raw_file.write_text(content, encoding="utf-8")

        archiver._compiler.enqueue_file(raw_file)

        return OperationResult(
            success=True,
            message=f"Artifact '{artifact.name}' ingested, compilation started",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Artifact ingest failed: {e}")
        raise HTTPException(status_code=500, detail="Artifact ingest failed") from e


@router.get("/graph", response_model=WikiGraphResponse)
def get_wiki_graph(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    center_node: str | None = Query(None, description="Center node for progressive loading"),
    depth: int = Query(1, description="Depth of neighborhood to load"),
    limit: int = Query(500, description="Max nodes to return"),
) -> WikiGraphResponse:
    """Fetch the full or progressive topology graph in O(1) DB read time."""
    try:
        # Note: get_knowledge_graph is synchronous. By making this route `def` instead of `async def`,
        # FastAPI will automatically run it in a threadpool, preventing event loop blocking.
        graph = archiver._query_engine._indexer.get_knowledge_graph(center_node, depth, limit)
        return WikiGraphResponse(nodes=graph["nodes"], edges=graph["edges"])
    except Exception as e:
        logger.error(f"Wiki graph retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Wiki graph retrieval failed") from e


# --- Batch Import Endpoints ---


class ImportFolderRequest(BaseModel):
    folder_path: str = Field(..., min_length=1, description="Absolute path to local folder")
    extensions: list[str] = Field(
        default=[".md", ".txt", ".org"],
        description="File extensions to include",
    )
    auto_compile: bool = Field(default=True, description="Start compilation after import")
    on_conflict: Literal["skip", "supersede"] = Field(
        default="skip",
        description="When a raw file already exists with different content",
    )
    supersede_reason: str = Field(default="", description="Required when on_conflict is supersede")


class ImportResultResponse(BaseModel):
    success: bool
    files_scanned: int
    files_enqueued: int
    files_skipped_conflict: int = 0
    files_superseded: int = 0
    files_security_blocked: int = 0
    files_security_redacted: int = 0
    conflict_paths: list[str] = Field(default_factory=list)
    security_blocked_paths: list[str] = Field(default_factory=list)
    security_redacted_paths: list[str] = Field(default_factory=list)
    message: str


class ObsidianImportRequest(BaseModel):
    vault_path: str = Field(..., min_length=1, description="Absolute path to Obsidian vault folder")
    auto_compile: bool = Field(default=True, description="Start compilation after import")
    on_conflict: Literal["skip", "supersede"] = Field(default="skip")
    supersede_reason: str = Field(default="")


class ObsidianImportResultResponse(BaseModel):
    success: bool
    files_scanned: int
    files_processed: int
    files_skipped: int
    files_skipped_conflict: int = 0
    files_superseded: int = 0
    files_security_blocked: int = 0
    files_security_redacted: int = 0
    conflict_paths: list[str] = Field(default_factory=list)
    security_blocked_paths: list[str] = Field(default_factory=list)
    security_redacted_paths: list[str] = Field(default_factory=list)
    tags_extracted: int
    images_copied: int
    message: str


async def _publish_import_raw(
    structure: "WikiStructure",
    relative_path: str,
    content: str,
    *,
    on_conflict: Literal["skip", "supersede"],
    supersede_reason: str,
):
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
    result,
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


@router.post("/import/folder", response_model=ImportResultResponse)
async def import_folder(
    request: ImportFolderRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> ImportResultResponse:
    """Batch import all text documents from a local folder into the wiki raw/ directory."""
    _validate_import_conflict_options(request.on_conflict, request.supersede_reason)
    try:
        source_dir = Path(request.folder_path)
        scanned_files = archiver._structure.scan_folder(source_dir, request.extensions)

        if not scanned_files:
            return ImportResultResponse(
                success=True,
                files_scanned=0,
                files_enqueued=0,
                message="No matching files found",
            )

        enqueued_paths: list[Path] = []
        conflict_paths: list[str] = []
        security_blocked_paths: list[str] = []
        security_redacted_paths: list[str] = []
        files_skipped_conflict = 0
        files_superseded = 0

        for src_file in scanned_files:
            try:
                content = src_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    content = src_file.read_text(encoding="latin-1")
                except Exception:
                    logger.warning(f"Skipping unreadable file: {src_file}")
                    continue

            rel_path = src_file.relative_to(source_dir).as_posix()
            result = await _publish_import_raw(
                archiver._structure,
                rel_path,
                content,
                on_conflict=request.on_conflict,
                supersede_reason=request.supersede_reason,
            )
            skipped, superseded = _track_import_publish_result(
                result,
                enqueued_paths=enqueued_paths,
                conflict_paths=conflict_paths,
                security_blocked_paths=security_blocked_paths,
                security_redacted_paths=security_redacted_paths,
            )
            files_skipped_conflict += skipped
            files_superseded += superseded

        if enqueued_paths:
            archiver._queue.add_batch(enqueued_paths)
            if request.auto_compile:
                archiver._compiler.start_background_worker()
            else:
                _refresh_wiki_cognitive_map(
                    archiver,
                    WikiMapEventType.IMPORT,
                    f"Imported {len(enqueued_paths)} file(s) without auto-compile",
                    {"files_enqueued": len(enqueued_paths)},
                )

        if enqueued_paths or files_superseded > 0:
            await _after_wiki_vault_mutation(archiver, "import folder")

        if enqueued_paths:
            await _schedule_post_import_dedup_scan(agent_id)

        return ImportResultResponse(
            success=True,
            files_scanned=len(scanned_files),
            files_enqueued=len(enqueued_paths),
            files_skipped_conflict=files_skipped_conflict,
            files_superseded=files_superseded,
            files_security_blocked=len(security_blocked_paths),
            files_security_redacted=len(security_redacted_paths),
            conflict_paths=conflict_paths,
            security_blocked_paths=security_blocked_paths,
            security_redacted_paths=security_redacted_paths,
            message=_build_import_message(
                enqueued=len(enqueued_paths),
                skipped_conflict=files_skipped_conflict,
                superseded=files_superseded,
                security_blocked=len(security_blocked_paths),
                security_redacted=len(security_redacted_paths),
                auto_compile=request.auto_compile,
            ),
        )
    except FileNotFoundError as e:
        logger.warning("Folder import source not found: %s", e)
        raise HTTPException(status_code=404, detail="Source folder not found") from e
    except Exception as e:
        logger.error(f"Folder import failed: {e}")
        raise HTTPException(status_code=500, detail="Folder import failed") from e


@router.post("/import/zip", response_model=ImportResultResponse)
async def import_zip(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    file: UploadFile = File(..., description="ZIP file to import"),
    extensions: str = Query(".md,.txt,.org", description="Comma-separated extensions"),
    auto_compile: bool = Query(True, description="Start compilation after import"),
    on_conflict: Literal["skip", "supersede"] = Query(
        "skip",
        description="When a raw file already exists with different content",
    ),
    supersede_reason: str = Query("", description="Required when on_conflict is supersede"),
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> ImportResultResponse:
    """Upload and import a ZIP archive of documents into the wiki."""
    import tempfile
    import zipfile

    _MAX_ZIP_BYTES = 100 * 1024 * 1024  # 100 MB
    _validate_import_conflict_options(on_conflict, supersede_reason)

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    if file.size and file.size > _MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="ZIP file too large (max 100 MB)")

    ext_list = [e.strip() for e in extensions.split(",") if e.strip()]

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            zip_path = tmp_path / "upload.zip"

            content = await file.read()
            if len(content) > _MAX_ZIP_BYTES:
                raise HTTPException(status_code=413, detail="ZIP file too large (max 100 MB)")
            zip_path.write_bytes(content)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_path / "extracted")

            extracted_dir = tmp_path / "extracted"
            scanned_files = archiver._structure.scan_folder(extracted_dir, ext_list)

            if not scanned_files:
                return ImportResultResponse(
                    success=True,
                    files_scanned=0,
                    files_enqueued=0,
                    message="No matching files in ZIP",
                )

            enqueued_paths: list[Path] = []
            conflict_paths: list[str] = []
            security_blocked_paths: list[str] = []
            security_redacted_paths: list[str] = []
            files_skipped_conflict = 0
            files_superseded = 0

            for src_file in scanned_files:
                try:
                    file_content = src_file.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    try:
                        file_content = src_file.read_text(encoding="latin-1")
                    except Exception:
                        logger.warning(f"Skipping unreadable file in ZIP: {src_file}")
                        continue

                rel_path = src_file.relative_to(extracted_dir).as_posix()
                result = await _publish_import_raw(
                    archiver._structure,
                    rel_path,
                    file_content,
                    on_conflict=on_conflict,
                    supersede_reason=supersede_reason,
                )
                skipped, superseded = _track_import_publish_result(
                    result,
                    enqueued_paths=enqueued_paths,
                    conflict_paths=conflict_paths,
                    security_blocked_paths=security_blocked_paths,
                    security_redacted_paths=security_redacted_paths,
                )
                files_skipped_conflict += skipped
                files_superseded += superseded

            if enqueued_paths:
                archiver._queue.add_batch(enqueued_paths)
                if auto_compile:
                    archiver._compiler.start_background_worker()
                else:
                    _refresh_wiki_cognitive_map(
                        archiver,
                        WikiMapEventType.IMPORT,
                        f"Imported {len(enqueued_paths)} file(s) from ZIP without auto-compile",
                        {"files_enqueued": len(enqueued_paths)},
                    )

            if enqueued_paths or files_superseded > 0:
                await _after_wiki_vault_mutation(archiver, "import zip")

            if enqueued_paths:
                await _schedule_post_import_dedup_scan(agent_id)

            return ImportResultResponse(
                success=True,
                files_scanned=len(scanned_files),
                files_enqueued=len(enqueued_paths),
                files_skipped_conflict=files_skipped_conflict,
                files_superseded=files_superseded,
                files_security_blocked=len(security_blocked_paths),
                files_security_redacted=len(security_redacted_paths),
                conflict_paths=conflict_paths,
                security_blocked_paths=security_blocked_paths,
                security_redacted_paths=security_redacted_paths,
                message=_build_import_message(
                    enqueued=len(enqueued_paths),
                    skipped_conflict=files_skipped_conflict,
                    superseded=files_superseded,
                    security_blocked=len(security_blocked_paths),
                    security_redacted=len(security_redacted_paths),
                    auto_compile=auto_compile,
                    source_label=" from ZIP",
                ),
            )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ZIP import failed: {e}")
        raise HTTPException(status_code=500, detail="ZIP import failed") from e


async def _process_obsidian_vault(
    vault_root: Path,
    archiver: MemoryToWikiArchiver,
    auto_compile: bool,
    *,
    on_conflict: Literal["skip", "supersede"] = "skip",
    supersede_reason: str = "",
    source_label: str = "",
    agent_id: str | None = None,
) -> ObsidianImportResultResponse:
    """Shared logic for processing an Obsidian vault directory into Wiki."""
    from app.services.wiki.obsidian import (
        ObsidianImportStats,
        prepare_obsidian_file,
    )

    scanned_files = archiver._structure.scan_folder(vault_root, [".md"])
    stats = ObsidianImportStats(files_scanned=len(scanned_files))

    assets_dir = archiver._structure.wiki_dir / "assets"
    enqueued_paths: list[Path] = []
    conflict_paths: list[str] = []
    security_blocked_paths: list[str] = []
    security_redacted_paths: list[str] = []

    for src_file in scanned_files:
        try:
            prepared = prepare_obsidian_file(src_file, vault_root, assets_dir)
            if prepared is None:
                stats.files_skipped += 1
                continue

            result = await _publish_import_raw(
                archiver._structure,
                prepared.relative_path,
                prepared.content,
                on_conflict=on_conflict,
                supersede_reason=supersede_reason,
            )
            skipped_conflict, superseded = _track_import_publish_result(
                result,
                enqueued_paths=enqueued_paths,
                conflict_paths=conflict_paths,
                security_blocked_paths=security_blocked_paths,
                security_redacted_paths=security_redacted_paths,
            )
            stats.files_skipped_conflict += skipped_conflict
            stats.files_superseded += superseded

            if result.conflict_skipped or result.security_blocked:
                continue

            stats.files_processed += 1
            stats.images_copied += prepared.images_copied
            if prepared.metadata:
                stats.frontmatter_parsed += 1
                tags = prepared.metadata.get("tags")
                if isinstance(tags, list):
                    stats.tags_extracted += len(tags)
                elif tags:
                    stats.tags_extracted += 1
        except Exception as exc:
            stats.files_skipped += 1
            stats.errors.append(f"{src_file.name}: {exc}")
            logger.warning("Skipping Obsidian file %s: %s", src_file, exc)

    if enqueued_paths:
        archiver._queue.add_batch(enqueued_paths)
        if auto_compile:
            archiver._compiler.start_background_worker()
        else:
            _refresh_wiki_cognitive_map(
                archiver,
                WikiMapEventType.IMPORT,
                f"Imported {len(enqueued_paths)} Obsidian note(s) without auto-compile",
                {
                    "files_enqueued": len(enqueued_paths),
                    "source": source_label or "obsidian",
                },
            )

    suffix = f" from {source_label}" if source_label else ""
    message_parts = [
        f"Imported {stats.files_processed} Obsidian notes{suffix}",
        f"({stats.tags_extracted} tags, {stats.images_copied} images)",
    ]
    if stats.files_skipped_conflict:
        message_parts.append(f"{stats.files_skipped_conflict} conflict(s) skipped")
    if stats.files_superseded:
        message_parts.append(f"{stats.files_superseded} superseded")
    if security_blocked_paths:
        message_parts.append(f"{len(security_blocked_paths)} blocked (sensitive content)")
    if security_redacted_paths:
        message_parts.append(f"{len(security_redacted_paths)} redacted")
    if stats.files_skipped:
        message_parts.append(f"{stats.files_skipped} skipped")
    if auto_compile:
        message_parts.append("compilation started")
    if enqueued_paths or stats.files_superseded > 0:
        await _after_wiki_vault_mutation(archiver, "import obsidian")
    if enqueued_paths:
        await _schedule_post_import_dedup_scan(agent_id)
    if stats.images_copied > 0:
        from app.services.wiki.asset_index_service import schedule_wiki_asset_index

        schedule_wiki_asset_index(archiver, agent_id=agent_id)
    return ObsidianImportResultResponse(
        success=True,
        files_scanned=stats.files_scanned,
        files_processed=stats.files_processed,
        files_skipped=stats.files_skipped,
        files_skipped_conflict=stats.files_skipped_conflict,
        files_superseded=stats.files_superseded,
        files_security_blocked=len(security_blocked_paths),
        files_security_redacted=len(security_redacted_paths),
        conflict_paths=conflict_paths,
        security_blocked_paths=security_blocked_paths,
        security_redacted_paths=security_redacted_paths,
        tags_extracted=stats.tags_extracted,
        images_copied=stats.images_copied,
        message=", ".join(message_parts),
    )


@router.post("/import/obsidian", response_model=ObsidianImportResultResponse)
async def import_obsidian_vault(
    request: ObsidianImportRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> ObsidianImportResultResponse:
    """Import an Obsidian vault with frontmatter parsing and image embed handling."""
    _validate_import_conflict_options(request.on_conflict, request.supersede_reason)
    try:
        vault_root = Path(request.vault_path)
        if not vault_root.is_dir():
            raise HTTPException(
                status_code=404,
                detail=f"Vault directory not found: {request.vault_path}",
            )
        return await _process_obsidian_vault(
            vault_root,
            archiver,
            request.auto_compile,
            on_conflict=request.on_conflict,
            supersede_reason=request.supersede_reason,
            agent_id=agent_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Obsidian vault import failed: %s", e)
        raise HTTPException(status_code=500, detail="Obsidian vault import failed") from e


@router.post("/import/obsidian-zip", response_model=ObsidianImportResultResponse)
async def import_obsidian_zip(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    file: UploadFile = File(..., description="ZIP of Obsidian vault"),
    auto_compile: bool = Query(True),
    on_conflict: Literal["skip", "supersede"] = Query("skip"),
    supersede_reason: str = Query(""),
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> ObsidianImportResultResponse:
    """Upload an Obsidian vault as ZIP (for WebUI / cloud-hosted deployments)."""
    import tempfile
    import zipfile

    _MAX_ZIP_BYTES = 100 * 1024 * 1024
    _validate_import_conflict_options(on_conflict, supersede_reason)

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")
    if file.size and file.size > _MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="ZIP file too large (max 100 MB)")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            zip_path = tmp_path / "vault.zip"
            raw_bytes = await file.read()
            if len(raw_bytes) > _MAX_ZIP_BYTES:
                raise HTTPException(status_code=413, detail="ZIP file too large (max 100 MB)")
            zip_path.write_bytes(raw_bytes)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_path / "vault")

            vault_root = tmp_path / "vault"
            top_items = list(vault_root.iterdir())
            if len(top_items) == 1 and top_items[0].is_dir():
                vault_root = top_items[0]

            return await _process_obsidian_vault(
                vault_root,
                archiver,
                auto_compile,
                on_conflict=on_conflict,
                supersede_reason=supersede_reason,
                source_label="ZIP",
                agent_id=agent_id,
            )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Obsidian ZIP import failed: %s", e)
        raise HTTPException(status_code=500, detail="Obsidian ZIP import failed") from e


@router.post("/vault/reveal", response_model=OperationResult)
async def reveal_wiki_vault(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> OperationResult:
    """Reveal the agent wiki vault folder in the local file manager (local mode only)."""
    from app.config.deploy_mode import is_local_mode
    from app.services.files.reveal_utils import reveal_path_in_file_manager

    if not is_local_mode():
        raise HTTPException(status_code=403, detail="Vault reveal is only available in local mode")

    vault_path = archiver.get_wiki_path().resolve()
    if not vault_path.is_dir():
        raise HTTPException(status_code=404, detail="Wiki vault directory not found")

    reveal_path_in_file_manager(vault_path)
    return OperationResult(success=True, message=str(vault_path))


@router.post("/vault/open-obsidian", response_model=OperationResult)
async def open_wiki_vault_in_obsidian(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> OperationResult:
    """Open the wiki vault in Obsidian when available, otherwise reveal the folder (local mode only)."""
    from app.config.deploy_mode import is_local_mode
    from app.services.files.reveal_utils import (
        open_vault_in_obsidian_app,
        reveal_path_in_file_manager,
    )

    if not is_local_mode():
        raise HTTPException(status_code=403, detail="Obsidian open is only available in local mode")

    vault_path = archiver.get_wiki_path().resolve()
    if not vault_path.is_dir():
        raise HTTPException(status_code=404, detail="Wiki vault directory not found")

    if open_vault_in_obsidian_app(vault_path):
        return OperationResult(success=True, message=str(vault_path))

    reveal_path_in_file_manager(vault_path)
    return OperationResult(success=True, message=str(vault_path))


@router.get("/portability/export")
async def export_wiki_vault(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to export")] = None,
) -> StreamingResponse:
    """Export the full wiki vault as an Obsidian-ready ZIP (raw + wiki + graph preset)."""
    from myrm_agent_harness.toolkits.wiki.portability.vault_archive import (
        iter_vault_files,
    )

    from app.services.wiki.vault import build_wiki_export_zip

    structure = archiver._structure
    if not iter_vault_files(structure):
        raise HTTPException(status_code=400, detail="Wiki vault is empty")
    try:
        memory_file = await asyncio.to_thread(build_wiki_export_zip, structure, agent_id)
        scope = agent_id or "default"
        filename = f"myrm_wiki_obsidian_{scope}.zip"

        def iterfile() -> Iterator[bytes]:
            yield memory_file.read()

        return StreamingResponse(
            iterfile(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("Wiki vault export failed: %s", e)
        raise HTTPException(status_code=500, detail="Wiki vault export failed") from e


from app.api.wiki.ingest_stream import register_ingest_stream_routes  # noqa: E402
from app.api.wiki.routes.clip import router as wiki_clip_router  # noqa: E402
from app.api.wiki.sources import router as wiki_sources_router  # noqa: E402

register_ingest_stream_routes(router)
router.include_router(wiki_clip_router)
router.include_router(wiki_sources_router)
