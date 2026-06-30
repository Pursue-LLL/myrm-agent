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
批量导入接口（folder/zip）
Artifact 内容写入接口

[POS]
业务层 Wiki API 路由。提供全量 REST 端点供前端 Brain Console 调用：
查询/编译/维护/ingest wiki。/concepts (CRUD)、/queue (状态控制)、/pending (人工审核)、
/import/folder + /import/zip (批量导入)、/ingest (artifact 内容写入)。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.memory import MemoryManager
from pydantic import BaseModel, Field

from app.api.dependencies import get_optional_llm_for_user
from app.api.memory.utils import get_optional_memory_manager
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])

# --- Request/Response Models ---


class WikiQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question to ask the wiki")


class WikiQueryResponse(BaseModel):
    answer: str
    related_articles: list[str] = Field(default_factory=list)


class WikiCompileResponse(BaseModel):
    concepts_count: int
    articles_generated: int
    backlinks_created: int
    duration_ms: int


class WikiMaintenanceResponse(BaseModel):
    issues_found: int
    issues_fixed: int
    connections_discovered: int
    duration_ms: int


class WikiStatsResponse(BaseModel):
    total_concepts: int
    total_articles: int
    total_raw_files: int
    wiki_path: str


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


class ConceptResponse(BaseModel):
    name: str
    content: str


class ConceptListResponse(BaseModel):
    concepts: list[str]
    total: int
    has_more: bool


class TreeNode(BaseModel):
    id: str
    name: str
    is_dir: bool
    children: list["TreeNode"] | None = None


class CreateFolderRequest(BaseModel):
    path: str = Field(..., min_length=1)


class MoveNodeRequest(BaseModel):
    source_path: str = Field(..., min_length=1)
    target_path: str = Field(..., min_length=1)


class DeleteFolderRequest(BaseModel):
    path: str = Field(..., min_length=1)


class ConceptUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class QueueStatusResponse(BaseModel):
    stats: dict[str, int]
    pending_items: list[dict[str, object]]


class PendingEditsResponse(BaseModel):
    stats: dict[str, int]
    pending_edits: list[dict[str, object]]


class OperationResult(BaseModel):
    success: bool
    message: str


async def _get_wiki_archiver(
    llm: Annotated[BaseChatModel, Depends(get_optional_llm_for_user)],
    manager: Annotated[MemoryManager | None, Depends(get_optional_memory_manager)],
) -> MemoryToWikiArchiver:
    """Get wiki archiver for current user."""
    return MemoryToWikiArchiver(llm, None, manager=manager)


# --- Core RAG & Compilation Endpoints ---


@router.post("/query", response_model=WikiQueryResponse)
async def query_wiki(
    request: WikiQueryRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> WikiQueryResponse:
    try:
        answer = await archiver.query_wiki(request.question)
        return WikiQueryResponse(answer=answer, related_articles=[])
    except Exception as e:
        logger.error(f"Wiki query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/compile", response_model=WikiCompileResponse)
async def compile_wiki(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> WikiCompileResponse:
    try:
        result = await archiver._compiler.compile_all()
        return WikiCompileResponse(
            concepts_count=result.concepts_count,
            articles_generated=result.articles_generated,
            backlinks_created=result.backlinks_created,
            duration_ms=result.duration_ms,
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
        )
    except Exception as e:
        logger.error(f"Wiki maintenance failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/stats", response_model=WikiStatsResponse)
async def get_wiki_stats(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> WikiStatsResponse:
    try:
        concepts = archiver._structure.list_concepts()
        raw_files = archiver._structure.list_raw_files()
        return WikiStatsResponse(
            total_concepts=len(concepts),
            total_articles=len(concepts),
            total_raw_files=len(raw_files),
            wiki_path=str(archiver.get_wiki_path()),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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
    concepts_dir = archiver._structure.concepts_dir

    def build_tree(dir_path: Path, rel_base: Path) -> list[TreeNode]:
        nodes = []
        if not dir_path.exists():
            return nodes

        for item in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
            if item.is_dir():
                rel_id = str(item.relative_to(rel_base)).replace("\\", "/")
                children = build_tree(item, rel_base)
                nodes.append(TreeNode(id=rel_id, name=item.name, is_dir=True, children=children))
            elif item.suffix == ".md":
                rel_id = str(item.relative_to(rel_base).with_suffix("")).replace("\\", "/")
                nodes.append(TreeNode(id=rel_id, name=item.stem, is_dir=False))
        return nodes

    return build_tree(concepts_dir, concepts_dir)


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

        # Update indexer
        if old_path.is_file():
            await archiver._query_engine._indexer.delete(safe_source)
            content = new_path.read_text(encoding="utf-8")
            await archiver._query_engine._indexer.upsert(safe_target, content)
            archiver._query_engine._indexer.extract_and_upsert_edges(safe_target, content)
        else:
            # If it's a directory, we need to update indexer for all files inside
            for md_file in new_path.rglob("*.md"):
                rel_new = md_file.relative_to(concepts_dir)
                concept_new = str(rel_new.with_suffix("")).replace("\\", "/")

                # Calculate old concept name
                rel_to_new_dir = md_file.relative_to(new_path)
                old_md_file = old_path / rel_to_new_dir
                rel_old = old_md_file.relative_to(concepts_dir)
                concept_old = str(rel_old.with_suffix("")).replace("\\", "/")

                await archiver._query_engine._indexer.delete(concept_old)
                content = md_file.read_text(encoding="utf-8")
                await archiver._query_engine._indexer.upsert(concept_new, content)
                archiver._query_engine._indexer.extract_and_upsert_edges(concept_new, content)

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
    return ConceptResponse(name=name, content=path.read_text(encoding="utf-8"))


@router.put("/concepts/{name:path}", response_model=OperationResult)
async def update_concept(
    name: str, request: ConceptUpdateRequest, archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]
) -> OperationResult:
    """Update or create a concept file manually."""
    path = archiver._structure.get_concept_file_path(name)
    try:
        path.write_text(request.content, encoding="utf-8")
        await archiver._query_engine._indexer.upsert(name, request.content)
        archiver._query_engine._indexer.extract_and_upsert_edges(name, request.content)
        return OperationResult(success=True, message=f"Concept {name} updated")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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


# --- Queue Management Endpoints ---


@router.get("/queue", response_model=QueueStatusResponse)
async def get_queue_status(archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]) -> QueueStatusResponse:
    """Get ingestion queue statistics and pending items."""
    stats = archiver._queue.get_stats()
    items = archiver._queue.get_pending_items(limit=20)
    return QueueStatusResponse(stats=stats, pending_items=items)


@router.post("/queue/cancel", response_model=OperationResult)
async def cancel_queue(archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]) -> OperationResult:
    """Cancel all pending ingestion jobs."""
    count = archiver._queue.cancel_pending()
    return OperationResult(success=True, message=f"Cancelled {count} jobs")


@router.post("/queue/retry", response_model=OperationResult)
async def retry_queue_failed(archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]) -> OperationResult:
    """Reset all failed jobs back to pending."""
    count = archiver._queue.reset_failed()
    return OperationResult(success=True, message=f"Reset {count} failed jobs to pending")


# --- HITL Pending Edits Endpoints ---


@router.get("/pending", response_model=PendingEditsResponse)
async def get_pending_edits(archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]) -> PendingEditsResponse:
    """Get stats and list of pending Wiki edits (HITL)."""
    stats = archiver._pending_mgr.get_stats()
    edits = archiver._pending_mgr.get_pending_edits(limit=50)
    return PendingEditsResponse(stats=stats, pending_edits=edits)


@router.post("/pending/{edit_id}/approve", response_model=OperationResult)
async def approve_pending_edit(
    edit_id: int, archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)]
) -> OperationResult:
    """Approve a pending edit and merge it to the wiki."""
    success = await archiver._pending_mgr.approve_edit(edit_id)
    if not success:
        raise HTTPException(status_code=400, detail="Edit not found or already processed")
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
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> OperationResult:
    """Ingest an artifact's content into the wiki knowledge base."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.api.dependencies import get_workspace_root
    from app.database.connection import get_session
    from app.database.models.artifact import Artifact

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


class ImportResultResponse(BaseModel):
    success: bool
    files_scanned: int
    files_enqueued: int
    message: str


class ObsidianImportRequest(BaseModel):
    vault_path: str = Field(..., min_length=1, description="Absolute path to Obsidian vault folder")
    auto_compile: bool = Field(default=True, description="Start compilation after import")


class ObsidianImportResultResponse(BaseModel):
    success: bool
    files_scanned: int
    files_processed: int
    files_skipped: int
    tags_extracted: int
    images_copied: int
    message: str


@router.post("/import/folder", response_model=ImportResultResponse)
async def import_folder(
    request: ImportFolderRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> ImportResultResponse:
    """Batch import all text documents from a local folder into the wiki raw/ directory."""
    try:
        source_dir = Path(request.folder_path)
        scanned_files = archiver._structure.scan_folder(source_dir, request.extensions)

        if not scanned_files:
            return ImportResultResponse(
                success=True, files_scanned=0, files_enqueued=0, message="No matching files found"
            )

        enqueued_paths: list[Path] = []
        for src_file in scanned_files:
            try:
                content = src_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    content = src_file.read_text(encoding="latin-1")
                except Exception:
                    logger.warning(f"Skipping unreadable file: {src_file}")
                    continue

            # Preserve relative directory structure from source
            rel_path = src_file.relative_to(source_dir)
            raw_dest = archiver._structure.get_raw_file_path(str(rel_path))
            raw_dest.parent.mkdir(parents=True, exist_ok=True)
            raw_dest.write_text(content, encoding="utf-8")
            enqueued_paths.append(raw_dest)

        if enqueued_paths:
            archiver._queue.add_batch(enqueued_paths)
            if request.auto_compile:
                archiver._compiler.start_background_worker()

        return ImportResultResponse(
            success=True,
            files_scanned=len(scanned_files),
            files_enqueued=len(enqueued_paths),
            message=f"Imported {len(enqueued_paths)} files, compilation {'started' if request.auto_compile else 'queued'}",
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
) -> ImportResultResponse:
    """Upload and import a ZIP archive of documents into the wiki."""
    import tempfile
    import zipfile

    _MAX_ZIP_BYTES = 100 * 1024 * 1024  # 100 MB

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
            for src_file in scanned_files:
                try:
                    file_content = src_file.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    try:
                        file_content = src_file.read_text(encoding="latin-1")
                    except Exception:
                        logger.warning(f"Skipping unreadable file in ZIP: {src_file}")
                        continue

                rel_path = src_file.relative_to(extracted_dir)
                raw_dest = archiver._structure.get_raw_file_path(str(rel_path))
                raw_dest.parent.mkdir(parents=True, exist_ok=True)
                raw_dest.write_text(file_content, encoding="utf-8")
                enqueued_paths.append(raw_dest)

            if enqueued_paths:
                archiver._queue.add_batch(enqueued_paths)
                if auto_compile:
                    archiver._compiler.start_background_worker()

            return ImportResultResponse(
                success=True,
                files_scanned=len(scanned_files),
                files_enqueued=len(enqueued_paths),
                message=f"Imported {len(enqueued_paths)} files from ZIP, compilation {'started' if auto_compile else 'queued'}",
            )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ZIP import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


def _process_obsidian_vault(
    vault_root: Path,
    archiver: MemoryToWikiArchiver,
    auto_compile: bool,
    source_label: str = "",
) -> ObsidianImportResultResponse:
    """Shared logic for processing an Obsidian vault directory into Wiki."""
    from app.services.wiki.obsidian_adapter import (
        ObsidianImportStats,
        adapt_obsidian_file,
    )

    scanned_files = archiver._structure.scan_folder(vault_root, [".md"])
    stats = ObsidianImportStats(files_scanned=len(scanned_files))

    raw_dir = archiver._structure.raw_dir
    assets_dir = archiver._structure.wiki_dir / "assets"
    enqueued_paths: list[Path] = []

    for src_file in scanned_files:
        try:
            dest, metadata, imgs = adapt_obsidian_file(src_file, vault_root, raw_dir, assets_dir)
            if dest is None:
                stats.files_skipped += 1
                continue
            stats.files_processed += 1
            stats.images_copied += imgs
            if metadata:
                stats.frontmatter_parsed += 1
                tags = metadata.get("tags")
                if isinstance(tags, list):
                    stats.tags_extracted += len(tags)
                elif tags:
                    stats.tags_extracted += 1
            enqueued_paths.append(dest)
        except Exception as exc:
            stats.files_skipped += 1
            stats.errors.append(f"{src_file.name}: {exc}")
            logger.warning("Skipping Obsidian file %s: %s", src_file, exc)

    if enqueued_paths:
        archiver._queue.add_batch(enqueued_paths)
        if auto_compile:
            archiver._compiler.start_background_worker()

    suffix = f" from {source_label}" if source_label else ""
    return ObsidianImportResultResponse(
        success=True,
        files_scanned=stats.files_scanned,
        files_processed=stats.files_processed,
        files_skipped=stats.files_skipped,
        tags_extracted=stats.tags_extracted,
        images_copied=stats.images_copied,
        message=(
            f"Imported {stats.files_processed} Obsidian notes{suffix}"
            f" ({stats.tags_extracted} tags, {stats.images_copied} images)"
            f"{', compilation started' if auto_compile else ''}"
        ),
    )


@router.post("/import/obsidian", response_model=ObsidianImportResultResponse)
async def import_obsidian_vault(
    request: ObsidianImportRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> ObsidianImportResultResponse:
    """Import an Obsidian vault with frontmatter parsing and image embed handling."""
    try:
        vault_root = Path(request.vault_path)
        if not vault_root.is_dir():
            raise HTTPException(status_code=404, detail=f"Vault directory not found: {request.vault_path}")
        return _process_obsidian_vault(vault_root, archiver, request.auto_compile)
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
) -> ObsidianImportResultResponse:
    """Upload an Obsidian vault as ZIP (for WebUI / cloud-hosted deployments)."""
    import tempfile
    import zipfile

    _MAX_ZIP_BYTES = 100 * 1024 * 1024

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

            return _process_obsidian_vault(vault_root, archiver, auto_compile, source_label="ZIP")
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Obsidian ZIP import failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
