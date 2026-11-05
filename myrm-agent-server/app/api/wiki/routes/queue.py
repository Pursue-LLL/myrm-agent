"""Wiki 编译队列、待审编辑、修复与向量重建路由。

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
    WikiMapEventType,
)

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes import vault_effects
from app.api.wiki.routes.response_mappers import (
    _compile_run_response,
)
from app.api.wiki.routes.schemas import (
    ApprovePendingEditRequest,
    OperationResult,
    PendingEditsResponse,
    QueueStatusResponse,
    ReindexVectorsResponse,
    RepairPublicationResponse,
    RepairTypesResponse,
)
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)


router = APIRouter(tags=["wiki"])


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
        pending_items=[dict(item) for item in items],
        failed_items=[dict(item) for item in failed_items],
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
    limit: Annotated[int, Query(ge=1, le=200, description="Page size of pending drafts")] = 50,
    offset: Annotated[int, Query(ge=0, description="Skips older pages of pending drafts")] = 0,
) -> PendingEditsResponse:
    """Get stats and one page of pending Wiki edits (HITL); stats stay exact."""
    stats = archiver._pending_mgr.get_stats()
    stats["synthesis_pending"] = archiver._pending_mgr.count_synthesis_pending()
    edits = archiver._pending_mgr.get_pending_edits(limit=limit, offset=offset)
    return PendingEditsResponse(stats=stats, pending_edits=[dict(edit) for edit in edits])


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
    vault_effects._refresh_wiki_cognitive_map(
        archiver,
        WikiMapEventType.PENDING_APPROVE,
        f"Approved pending edit {edit_id}",
        {"edit_id": edit_id},
    )
    await vault_effects._after_wiki_vault_mutation(archiver, f"approve pending edit {edit_id}")
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
        vault_effects._refresh_wiki_cognitive_map(
            archiver,
            WikiMapEventType.REPAIR_TYPES,
            message,
            {
                "files_scanned": result.files_scanned,
                "files_repaired": result.files_repaired,
                "files_skipped": result.files_skipped,
            },
        )
        await vault_effects._after_wiki_vault_mutation(archiver, "repair frontmatter types")
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
        vault_effects._refresh_wiki_cognitive_map(
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
        await vault_effects._after_wiki_vault_mutation(archiver, "repair publication status")
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
        await vault_effects._after_wiki_vault_mutation(archiver, "reindex wiki vectors")
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
