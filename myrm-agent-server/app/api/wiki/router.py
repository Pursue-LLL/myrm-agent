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
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
    WikiCognitiveMapService,
    WikiMapEvent,
    WikiMapEventType,
)
from pydantic import BaseModel, Field

from app.api.dependencies import get_optional_llm_for_user
from app.api.memory.utils import get_optional_memory_manager
from app.services.wiki import MemoryToWikiArchiver

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
    snapshot_status: str = ""


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


class WikiClaimItem(BaseModel):
    id: str
    text: str
    status: str = "unknown"
    confidence: float = 0.0
    updated_at: str = ""
    evidence: list[WikiClaimEvidenceItem] = Field(default_factory=list)


class WikiStaleFileItem(BaseModel):
    relative_path: str


class WikiStaleSummaryResponse(BaseModel):
    stale_count: int
    last_compile_time: str | None = None
    stale_files: list[WikiStaleFileItem] = Field(default_factory=list)


class WikiQueryResponse(BaseModel):
    answer: str
    related_articles: list[str] = Field(default_factory=list)
    source_snippets: list[WikiSourceSnippet] = Field(default_factory=list)


class WikiCompileResponse(BaseModel):
    concepts_count: int
    articles_generated: int
    backlinks_created: int
    duration_ms: int
    articles_pending: int = 0
    articles_published: int = 0
    articles_blocked: int = 0
    compile_run: "CompileRunResponse | None" = None


class CompileRunResponse(BaseModel):
    state: Literal["running", "paused"]
    pause_reason: str = ""
    primary_error_kind: str = ""


class WikiMaintenanceResponse(BaseModel):
    issues_found: int
    issues_fixed: int
    connections_discovered: int
    duration_ms: int
    raw_security_removed: int = 0
    raw_security_removed_paths: list[str] = Field(default_factory=list)


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


async def _get_wiki_archiver(
    llm: Annotated[BaseChatModel, Depends(get_optional_llm_for_user)],
    manager: Annotated[MemoryManager | None, Depends(get_optional_memory_manager)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> MemoryToWikiArchiver:
    """Get wiki archiver bound to an agent-scoped vault path."""
    from app.services.wiki.vault_service import get_wiki_archiver

    return get_wiki_archiver(llm, manager, agent_id=agent_id)


def _compile_run_response(archiver: MemoryToWikiArchiver) -> CompileRunResponse:
    snapshot = archiver._queue.get_compile_run()
    return CompileRunResponse(
        state=snapshot.state,
        pause_reason=snapshot.pause_reason,
        primary_error_kind=snapshot.primary_error_kind,
    )


def _claims_to_response_items(
    content: str,
    structure: "WikiStructure | None" = None,
) -> list[WikiClaimItem]:
    from myrm_agent_harness.toolkits.wiki.core.claims_contract import (
        parse_claims_from_content,
        resolve_evidence_snapshot_status,
    )

    items: list[WikiClaimItem] = []
    for claim in parse_claims_from_content(content):
        items.append(
            WikiClaimItem(
                id=claim.id,
                text=claim.text,
                status=claim.status,
                confidence=claim.confidence,
                updated_at=claim.updated_at,
                evidence=[
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
                        snapshot_status=resolve_evidence_snapshot_status(
                            evidence.path,
                            evidence.content_sha256,
                            structure,
                        ),
                    )
                    for evidence in claim.evidence
                ],
            )
        )
    return items


def _editor_sections_to_response(content: str) -> WikiEditorSectionsResponse:
    from myrm_agent_harness.toolkits.wiki.core.section_contract import parse_editor_sections

    sections = parse_editor_sections(content)
    return WikiEditorSectionsResponse(
        compiled_truth=sections.compiled_truth,
        timeline=sections.timeline,
        tags=list(sections.tags),
        aliases=list(sections.aliases),
    )


# --- Core RAG & Compilation Endpoints ---


@router.post("/query", response_model=WikiQueryResponse)
async def query_wiki(
    request: WikiQueryRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> WikiQueryResponse:
    try:
        result = await archiver.query_wiki(request.question, query_mode=request.mode)
        source_snippets = [
            WikiSourceSnippet(
                path=snippet.article_path,
                name=snippet.article_name,
                snippet=snippet.snippet,
                section=snippet.section,
                level=snippet.level,
                claim_id=snippet.claim_id,
                claim_text=snippet.claim_text,
                evidence_path=snippet.evidence_path,
                line_range=snippet.line_range,
                claim_status=snippet.claim_status,
                snapshot_status=snippet.evidence_snapshot_status,
            )
            for snippet in result.source_snippets
        ]
        return WikiQueryResponse(
            answer=result.answer,
            related_articles=result.related_articles,
            source_snippets=source_snippets,
        )
    except Exception as e:
        logger.error(f"Wiki query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/compile", response_model=WikiCompileResponse)
async def compile_wiki(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiCompileResponse:
    from app.services.wiki.ingest_events import publish_wiki_ingest_snapshot

    try:
        result = await archiver._compiler.compile_all()
        await publish_wiki_ingest_snapshot(archiver, agent_id=agent_id)
        return WikiCompileResponse(
            concepts_count=result.concepts_count,
            articles_generated=result.articles_generated,
            backlinks_created=result.backlinks_created,
            duration_ms=result.duration_ms,
            articles_pending=result.articles_pending,
            articles_published=result.articles_published,
            articles_blocked=result.articles_blocked,
            compile_run=_compile_run_response(archiver),
        )
    except Exception as e:
        logger.error(f"Wiki compilation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/maintain", response_model=WikiMaintenanceResponse)
async def maintain_wiki(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> WikiMaintenanceResponse:
    try:
        result = await archiver._linter.lint_and_maintain()
        return WikiMaintenanceResponse(
            issues_found=result.issues_found,
            issues_fixed=result.issues_fixed,
            connections_discovered=result.connections_discovered,
            duration_ms=result.duration_ms,
            raw_security_removed=result.raw_security_removed,
            raw_security_removed_paths=list(result.raw_security_removed_paths),
        )
    except Exception as e:
        logger.error(f"Wiki maintenance failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/stats", response_model=WikiStatsResponse)
async def get_wiki_stats(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiStatsResponse:
    try:
        from app.services.wiki.vault_resolver import is_legacy_migration_complete, is_vault_ready

        concepts = archiver._structure.list_concepts()
        raw_files = archiver._structure.list_raw_files()
        from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
            count_log_entries,
            hot_updated_at_iso,
        )

        index_path = archiver._structure.get_index_file_path()
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
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/stale-summary", response_model=WikiStaleSummaryResponse)
async def get_wiki_stale_summary(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> WikiStaleSummaryResponse:
    """Return raw files modified after the last wiki compilation."""
    from myrm_agent_harness.toolkits.wiki.maintenance.stale_summary import collect_stale_raw_files

    summary = collect_stale_raw_files(archiver._structure)
    return WikiStaleSummaryResponse(
        stale_count=summary.stale_count,
        last_compile_time=summary.last_compile_time,
        stale_files=[WikiStaleFileItem(relative_path=item.relative_path) for item in summary.stale_files],
    )


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
async def get_wiki_tree(archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]) -> list[TreeNode]:
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
                            "tracked-modified"
                            if concept_uses_stale_sources(concept_content, stale_paths)
                            else "tracked-clean"
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
async def get_wiki_raw_tree(archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]) -> list[TreeNode]:
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
    request: CreateFolderRequest, archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]
) -> OperationResult:
    """Create a new folder in the wiki concepts directory."""
    safe_path = archiver._structure._sanitize_path(request.path)
    folder_path = archiver._structure.concepts_dir / safe_path
    try:
        folder_path.mkdir(parents=True, exist_ok=True)
        return OperationResult(success=True, message=f"Folder {safe_path} created")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/tree/move", response_model=OperationResult)
async def move_wiki_node(
    request: MoveNodeRequest, archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]
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

        return OperationResult(success=True, message=f"Moved successfully. Updated {updated_count} files.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/tree/folder", response_model=OperationResult)
async def delete_wiki_folder(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    path: str = Query(..., min_length=1),
) -> OperationResult:
    """Safely delete a folder and clear all its files from the indexer."""
    try:
        deleted_count = await archiver._structure.delete_folder_safe(path, archiver._query_engine._indexer)
        return OperationResult(success=True, message=f"Folder deleted. Unindexed {deleted_count} files.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/concepts/{name:path}", response_model=ConceptResponse)
async def get_concept(name: str, archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]) -> ConceptResponse:
    """Get content of a specific concept."""
    path = archiver._structure.resolve_concept_file_path(name)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Concept not found")
    content = path.read_text(encoding="utf-8")
    from myrm_agent_harness.toolkits.wiki.core.canonical_registry import compute_page_lease_hash

    return ConceptResponse(
        name=name,
        content=content,
        content_hash=compute_page_lease_hash(content),
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
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return WikiApplyResponse(
        success=result.success,
        op=result.op.value,
        concept_name=result.concept_name,
        message=result.message,
        created=result.created,
        appended=result.appended,
        content_hash=result.content_hash,
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
        return OperationResult(success=True, message=f"Concept {name} deleted")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


class DeleteRawRequest(BaseModel):
    forget_reason: str = Field(..., min_length=1, description="Why this raw evidence is being removed")


@router.delete("/raw/{path:path}", response_model=OperationResult)
async def delete_raw_source(
    path: str,
    body: DeleteRawRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> OperationResult:
    """Forget a raw source file and re-anchor dependent compiled pages."""
    from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import RawGateError, forget_evidence

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
    return OperationResult(
        success=True,
        message=f"Forgot raw source {result.relative_path} ({affected} affected, {republished} republished)",
    )


# --- Queue Management Endpoints ---


@router.get("/queue", response_model=QueueStatusResponse)
async def get_queue_status(archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]) -> QueueStatusResponse:
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
async def get_pending_edits(archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]) -> PendingEditsResponse:
    """Get stats and list of pending Wiki edits (HITL)."""
    stats = archiver._pending_mgr.get_stats()
    edits = archiver._pending_mgr.get_pending_edits(limit=50)
    return PendingEditsResponse(stats=stats, pending_edits=edits)


@router.post("/pending/{edit_id}/approve", response_model=OperationResult)
async def approve_pending_edit(
    edit_id: int,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    request: ApprovePendingEditRequest = ApprovePendingEditRequest(),
) -> OperationResult:
    """Approve a pending edit and merge it to the wiki."""
    from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import FrontmatterValidationError
    from myrm_agent_harness.toolkits.wiki.pipeline.publication import StalePendingApprovalError

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
    from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import repair_missing_types

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
    from myrm_agent_harness.toolkits.wiki.pipeline.publication import repair_publication_status

    result = await repair_publication_status(archiver._structure, archiver._query_engine._indexer)
    message = (
        f"Repaired {result.files_repaired} of {result.files_scanned} scanned files; "
        f"reindexed {result.reindexed}"
    )
    if result.files_skipped_intentional_drafts > 0:
        message = (
            f"{message}; skipped {result.files_skipped_intentional_drafts} intentional draft pages"
        )
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
    return RepairPublicationResponse(
        success=len(result.errors) == 0,
        files_scanned=result.files_scanned,
        files_repaired=result.files_repaired,
        files_skipped=result.files_skipped,
        files_skipped_intentional_drafts=result.files_skipped_intentional_drafts,
        reindexed=result.reindexed,
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
        raise HTTPException(status_code=500, detail=str(e)) from e


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
        from myrm_agent_harness.toolkits.web_search.web_searcher import WebSearcher

        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.config_parsers import verify_search_service_available

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

        return OperationResult(success=True, message=f"Research on '{request.topic}' ingested, compilation started")
    except ImportError:
        return OperationResult(success=False, message="Web search toolkit not configured")
    except Exception as e:
        logger.error(f"Deep research failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


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
    from app.services.wiki.vault_service import get_wiki_archiver

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
        obj_id = vault_uri[len("vault://"):] if vault_uri.startswith("vault://") else vault_uri
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
        raise HTTPException(status_code=500, detail=str(e)) from e


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
        raise HTTPException(status_code=500, detail=str(e)) from e


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
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
    from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import (
        RawConflictPolicy,
        RawGateError,
        RawPublishRequest,
        RawPublishResult,
        publish_raw,
    )

    policy = (
        RawConflictPolicy.SUPERSEDE if on_conflict == "supersede" else RawConflictPolicy.SKIP
    )
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
) -> ImportResultResponse:
    """Batch import all text documents from a local folder into the wiki raw/ directory."""
    _validate_import_conflict_options(request.on_conflict, request.supersede_reason)
    try:
        source_dir = Path(request.folder_path)
        scanned_files = archiver._structure.scan_folder(source_dir, request.extensions)

        if not scanned_files:
            return ImportResultResponse(
                success=True, files_scanned=0, files_enqueued=0, message="No matching files found"
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
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Folder import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


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
                    success=True, files_scanned=0, files_enqueued=0, message="No matching files in ZIP"
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
        raise HTTPException(status_code=500, detail=str(e)) from e


async def _process_obsidian_vault(
    vault_root: Path,
    archiver: MemoryToWikiArchiver,
    auto_compile: bool,
    *,
    on_conflict: Literal["skip", "supersede"] = "skip",
    supersede_reason: str = "",
    source_label: str = "",
) -> ObsidianImportResultResponse:
    """Shared logic for processing an Obsidian vault directory into Wiki."""
    from app.services.wiki.obsidian_adapter import ObsidianImportStats, prepare_obsidian_file

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
                {"files_enqueued": len(enqueued_paths), "source": source_label or "obsidian"},
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
) -> ObsidianImportResultResponse:
    """Import an Obsidian vault with frontmatter parsing and image embed handling."""
    _validate_import_conflict_options(request.on_conflict, request.supersede_reason)
    try:
        vault_root = Path(request.vault_path)
        if not vault_root.is_dir():
            raise HTTPException(status_code=404, detail=f"Vault directory not found: {request.vault_path}")
        return await _process_obsidian_vault(
            vault_root,
            archiver,
            request.auto_compile,
            on_conflict=request.on_conflict,
            supersede_reason=request.supersede_reason,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Obsidian vault import failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/import/obsidian-zip", response_model=ObsidianImportResultResponse)
async def import_obsidian_zip(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    file: UploadFile = File(..., description="ZIP of Obsidian vault"),
    auto_compile: bool = Query(True),
    on_conflict: Literal["skip", "supersede"] = Query("skip"),
    supersede_reason: str = Query(""),
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
            )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Obsidian ZIP import failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/portability/export")
async def export_wiki_vault(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to export")] = None,
) -> StreamingResponse:
    """Export concepts, OKF index/log, and manifest as a portable ZIP archive."""
    from app.services.wiki.vault_export import build_wiki_export_zip

    structure = archiver._structure
    try:
        memory_file = await asyncio.to_thread(build_wiki_export_zip, structure, agent_id)
        scope = agent_id or "default"
        filename = f"myrm_wiki_export_{scope}.zip"

        def iterfile() -> Iterator[bytes]:
            yield memory_file.read()

        return StreamingResponse(
            iterfile(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("Wiki vault export failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


from app.api.wiki.ingest_stream import register_ingest_stream_routes

register_ingest_stream_routes(router)
