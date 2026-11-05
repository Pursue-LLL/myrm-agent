"""Wiki 查询、资产读取、编译与健康报告路由。

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes.response_mappers import (
    _citation_sources_to_snippets,
    _compile_run_response,
    _retrieval_trace_to_response,
)
from app.api.wiki.routes.schemas import (
    WikiCompileResponse,
    WikiQueryRequest,
    WikiQueryResponse,
)
from app.services.risk.refusal import reject_if_risky
from app.services.wiki import MemoryToWikiArchiver
from app.services.wiki.health_report_service import WikiHealthReportResponse

logger = logging.getLogger(__name__)


router = APIRouter(tags=["wiki"])


@router.post("/query", response_model=WikiQueryResponse)
async def query_wiki(
    request: WikiQueryRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiQueryResponse:
    # Outside the try below, which turns every exception, the 400 refusal included, into a 500.
    await reject_if_risky(request.question, session_id=agent_id)
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
            refused=query_result.refused,
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
    from myrm_agent_harness.core.security.path import safe_join_path

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


@router.post("/compile", response_model=WikiCompileResponse, status_code=202)
async def compile_wiki(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiCompileResponse:
    """Queue the sources that need compiling and wake the background worker, which every import also uses.

    A compile makes sequential model calls for minutes, longer than a proxy or the control plane's circuit breaker
    should be asked to wait on one request.
    """
    from app.services.wiki.asset_index_service import schedule_wiki_asset_index
    from app.services.wiki.ingest_events import publish_wiki_ingest_snapshot

    try:
        from app.services.wiki.dedup_runner import wiki_dedup_blocks_compile

        if wiki_dedup_blocks_compile(agent_id=agent_id):
            raise HTTPException(
                status_code=409,
                detail="Duplicate review required: resolve exact/normalized groups before compiling",
            )
        await archiver._compiler.enqueue_changed_sources()
        archiver._compiler.start_background_worker()
        schedule_wiki_asset_index(archiver, agent_id=agent_id)
        await publish_wiki_ingest_snapshot(archiver, agent_id=agent_id)
        stats = archiver._queue.get_stats()
        return WikiCompileResponse(
            pending=stats["pending"] + stats["processing"],
            compile_run=_compile_run_response(archiver),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Wiki compilation failed: {e}")
        raise HTTPException(status_code=500, detail="Wiki compilation failed") from e


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
