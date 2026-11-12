"""[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryManager (POS: Pluggable memory system for AI agents.)
- app.api.dependencies::get_optional_llm_for_user (POS: API 层统一依赖注入入口。所有 FastAPI 端点的依赖应从此模块导入。)
- app.api.memory.utils::get_optional_memory_manager (POS: Memory API utilities — re-exports shared service-layer helpers for route modules.)
- app.api.wiki.archiver_dependency::get_scoped_wiki_archiver (POS: Single provider of the archiver for routes that compile, query or mutate a vault. Routes that only read or write vault files use ``app.services.wiki.vault.get_wiki_structure`` instead, so no compile worker is ever built without a model.)
- app.api.wiki.routes.schemas::GraphEdgeItem / GraphNodeItem / OperationResult / WikiGraphResponse (POS: Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。)
- app.services.wiki::MemoryToWikiArchiver (POS: Top-level wiki facade. Domain subpackages (vault / maintain / governance / obsidian / source_sync / clip / knowledge_pack) live under this package and expose their own facades.)

[OUTPUT]
- PurposeResponse: PurposeResponse
- PurposeUpdateRequest: PurposeUpdateRequest
- get_wiki_purpose: Get the knowledge base purpose/direction.
- update_wiki_purpose: Update the knowledge base purpose/direction.
- GraphInsightsResponse: GraphInsightsResponse
- get_graph_insights: Get graph structure insights: unexpected connections, knowledge gaps, communities.
- ResearchTopicRequest: ResearchTopicRequest
- research_topic_into_wiki: Research a topic via web search and ingest results into the wiki.
- IngestArtifactRequest: IngestArtifactRequest
- ingest_artifact: Ingest an artifact's content into the wiki knowledge base.
- get_wiki_graph: Fetch the full or progressive topology graph in O(1) DB read time.

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.memory import MemoryManager
from pydantic import BaseModel, Field

from app.api.dependencies import get_optional_llm_for_user
from app.api.memory.utils import get_optional_memory_manager
from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes.schemas import (
    GraphEdgeItem,
    GraphNodeItem,
    OperationResult,
    WikiGraphResponse,
)
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)


router = APIRouter(tags=["wiki"])


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


class ResearchTopicRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="Topic to research and add to wiki")
    search_queries: list[str] = Field(default_factory=list, description="Optional custom search queries")


@router.post("/research", response_model=OperationResult)
async def research_topic_into_wiki(
    request: ResearchTopicRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> OperationResult:
    """Research a topic via web search and ingest results into the wiki."""
    try:
        from myrm_agent_harness.toolkits.web_search.providers.web_searcher import (
            WebSearcher,
        )

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

    from app.database.connection import get_session
    from app.database.models.artifact import Artifact
    from app.services.chat.effective_workspace import resolve_chat_workspace_root
    from app.services.wiki.agent_scope import resolve_chat_agent_id
    from app.services.wiki.vault import get_wiki_archiver

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

        chat_id = cast("str | None", artifact.chat_id)
        effective_agent_id = agent_id or await resolve_chat_agent_id(chat_id)
        archiver = get_wiki_archiver(llm, manager, agent_id=effective_agent_id)

        latest_version = sorted(artifact.versions, key=lambda v: v.created_at, reverse=True)[0]
        vault = ArtifactVault(str(await resolve_chat_workspace_root(chat_id)))
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
        return WikiGraphResponse(
            nodes=[GraphNodeItem.model_validate(node) for node in graph["nodes"]],
            edges=[GraphEdgeItem.model_validate(edge) for edge in graph["edges"]],
        )
    except Exception as e:
        logger.error(f"Wiki graph retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Wiki graph retrieval failed") from e


# --- Batch Import Endpoints ---
