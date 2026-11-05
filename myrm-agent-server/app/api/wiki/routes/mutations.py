"""Wiki 变更应用、复合消息、日报、模板与删除路由。

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes import shared
from app.api.wiki.routes.schemas import (
    OperationResult,
    WikiApplyRequestBody,
    WikiApplyResponse,
    WikiCompoundRequestBody,
    WikiCompoundResponse,
    WikiDailyReviewRequestBody,
    WikiDailyReviewResponse,
    WikiTemplateSeedRequest,
    WikiTemplateSeedResponse,
)
from app.api.wiki.routes.shared import (
    _wiki_apply_http_status,
    _wiki_compound_http_status,
)
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)


router = APIRouter(tags=["wiki"])


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

    await shared._after_wiki_vault_mutation(archiver, "apply mutation")
    return WikiApplyResponse(
        success=result.success,
        op=result.op.value,
        concept_name=result.concept_name,
        message=result.message,
        created=result.created,
        appended=result.appended,
        content_hash=result.content_hash,
        staged_for_review=result.staged_for_review,
        pending_edit_id=result.pending_edit_id,
    )


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


@router.post("/daily-review", response_model=WikiDailyReviewResponse)
async def ingest_daily_review_endpoint(
    request: WikiDailyReviewRequestBody,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> WikiDailyReviewResponse:
    """Ingest a daily-review journal verbatim into raw/DailyReview and enqueue compilation."""
    from app.services.wiki.daily_review import ingest_daily_review_text

    try:
        result = await ingest_daily_review_text(archiver, text=request.text, title=request.title)
    except Exception as exc:
        logger.error("Daily review ingest failed: %s", exc)
        raise HTTPException(status_code=500, detail="Daily review ingest failed") from exc

    if result.security_blocked:
        raise HTTPException(
            status_code=422,
            detail={"code": "security_blocked", "message": result.message},
        )
    if not result.success:
        raise HTTPException(
            status_code=500,
            detail={"code": "ingest_failed", "message": result.message},
        )

    await shared._after_wiki_vault_mutation(archiver, "daily review ingest")
    return WikiDailyReviewResponse(
        success=True,
        raw_path=result.raw_relative_path,
        enqueued=result.enqueued,
        skipped=result.skipped,
        message=result.message,
    )


@router.post("/templates/seed", response_model=WikiTemplateSeedResponse)
async def seed_standard_templates_endpoint(
    request: WikiTemplateSeedRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
) -> WikiTemplateSeedResponse:
    """Seed the four standard markdown templates into concepts/templates/ (idempotent)."""
    from app.services.wiki.daily_review import STANDARD_TEMPLATE_NAMES, seed_standard_templates

    seeded = seed_standard_templates(archiver._structure, force=request.force)
    return WikiTemplateSeedResponse(
        success=True,
        seeded=list(seeded),
        templates=list(STANDARD_TEMPLATE_NAMES),
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
        await shared._after_wiki_vault_mutation(archiver, "delete concept")
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
    await shared._after_wiki_vault_mutation(archiver, "forget raw source")
    return OperationResult(
        success=True,
        message=f"Forgot raw source {result.relative_path} ({affected} affected, {republished} republished)",
    )


# --- Queue Management Endpoints ---
