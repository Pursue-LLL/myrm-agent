"""Tencent ima import REST routes: credentials, library choice, sync control, status and item report.

[INPUT]
- app.services.wiki.source_sync.ima (POS: ima sync facade)
- app.api.dependencies::get_optional_llm_for_user (POS: compile-capable LLM)

[OUTPUT]
- GET /sources/ima · PUT/DELETE /sources/ima/credentials
- GET /sources/ima/libraries · PUT /sources/ima/config
- POST /sources/ima/sync/{start,pause,resume,retry-failed} · POST /sources/ima/compile
- GET /sources/ima/items

[POS]
REST layer of the ima card. Errors carry ``{code, message}``; the code is the contract the UI maps to wording,
the message is English for logs. The API key is write-only: no response ever echoes it.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from app.api.dependencies import get_optional_llm_for_user
from app.services.wiki.source_sync import ima
from app.services.wiki.source_sync.ima.schemas import ImaItemView, ImaLibrary, ImaStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources/ima", tags=["wiki-ima"])

AgentIdQuery = Annotated[str | None, Query(description="Agent whose wiki vault to use")]


class ImaCredentialsBody(BaseModel):
    client_id: str = Field(max_length=256)
    api_key: str = Field(max_length=512)


class ImaConfigBody(BaseModel):
    library_ids: list[str] = Field(default_factory=list, max_length=50)
    include_notes: bool = True


class ImaStartBody(BaseModel):
    locale: str = Field(default="en", max_length=16)


class ImaCountResponse(BaseModel):
    count: int


def _raise_for(exc: Exception) -> NoReturn:
    """Map failures to stable codes; raw upstream text never reaches the client."""
    if isinstance(exc, ima.ImaOperationError):
        status = 409 if exc.code == "dedup_review_required" else 400
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)}) from exc
    if isinstance(exc, ima.ImaAuthError):
        # Not 401/403: the web client signs the user out of Myrm on those, and this is ima refusing the key, not Myrm.
        raise HTTPException(
            status_code=400, detail={"code": "ima_auth_failed", "message": "ima rejected the credentials"}
        ) from exc
    if isinstance(exc, ima.ImaRateLimitError):
        raise HTTPException(status_code=429, detail={"code": "ima_rate_limited", "message": "ima rate limit reached"}) from exc
    if isinstance(exc, ima.ImaError):
        raise HTTPException(status_code=502, detail={"code": "ima_unreachable", "message": "ima could not be reached"}) from exc
    if isinstance(exc, ValueError):
        # The cron manager reports plan limits (job slots) and rejected job definitions as ValueError; the UI only
        # sees the plan wording, so the reason is logged to keep a defect from passing as a plan limit.
        logger.warning("ima sync was refused by the cron manager: %s", exc)
        raise HTTPException(status_code=409, detail={"code": "sync_unavailable", "message": str(exc)}) from exc
    logger.error("ima request failed: %s", exc)
    raise HTTPException(status_code=500, detail={"code": "ima_failed", "message": "ima request failed"}) from exc


@router.get("", response_model=ImaStatus)
async def get_ima_status(agent_id: AgentIdQuery = None) -> ImaStatus:
    return await ima.build_status(agent_id)


@router.put("/credentials", response_model=ImaStatus)
async def save_ima_credentials(body: ImaCredentialsBody, agent_id: AgentIdQuery = None) -> ImaStatus:
    try:
        await ima.connect(client_id=body.client_id, api_key=body.api_key, agent_id=agent_id)
    except Exception as exc:
        _raise_for(exc)
    return await ima.build_status(agent_id)


@router.delete("/credentials", response_model=ImaStatus)
async def delete_ima_credentials(agent_id: AgentIdQuery = None) -> ImaStatus:
    try:
        await ima.disconnect()
    except Exception as exc:
        _raise_for(exc)
    return await ima.build_status(agent_id)


@router.get("/libraries", response_model=list[ImaLibrary])
async def list_ima_libraries() -> list[ImaLibrary]:
    try:
        return await ima.list_libraries()
    except Exception as exc:
        _raise_for(exc)


@router.put("/config", response_model=ImaStatus)
async def save_ima_config(body: ImaConfigBody, agent_id: AgentIdQuery = None) -> ImaStatus:
    try:
        await ima.save_selection(library_ids=body.library_ids, include_notes=body.include_notes, agent_id=agent_id)
    except Exception as exc:
        _raise_for(exc)
    return await ima.build_status(agent_id)


@router.post("/sync/start", response_model=ImaStatus, status_code=202)
async def start_ima_sync(body: ImaStartBody, agent_id: AgentIdQuery = None) -> ImaStatus:
    try:
        await ima.start_sync(agent_id=agent_id, locale=body.locale)
    except Exception as exc:
        _raise_for(exc)
    return await ima.build_status(agent_id)


@router.post("/sync/pause", response_model=ImaStatus)
async def pause_ima_sync(agent_id: AgentIdQuery = None) -> ImaStatus:
    try:
        await ima.pause_sync(agent_id=agent_id)
    except Exception as exc:
        _raise_for(exc)
    return await ima.build_status(agent_id)


@router.post("/sync/resume", response_model=ImaStatus, status_code=202)
async def resume_ima_sync(agent_id: AgentIdQuery = None) -> ImaStatus:
    try:
        await ima.resume_sync(agent_id=agent_id)
    except Exception as exc:
        _raise_for(exc)
    return await ima.build_status(agent_id)


@router.post("/sync/retry-failed", response_model=ImaCountResponse, status_code=202)
async def retry_failed_ima_items(agent_id: AgentIdQuery = None) -> ImaCountResponse:
    try:
        return ImaCountResponse(count=await ima.retry_failed(agent_id=agent_id))
    except Exception as exc:
        _raise_for(exc)


@router.post("/compile", response_model=ImaCountResponse, status_code=202)
async def compile_imported_ima_items(
    llm: Annotated[BaseChatModel, Depends(get_optional_llm_for_user)],
    agent_id: AgentIdQuery = None,
) -> ImaCountResponse:
    try:
        return ImaCountResponse(count=await ima.compile_imported(llm=llm, agent_id=agent_id))
    except Exception as exc:
        _raise_for(exc)


@router.get("/items", response_model=list[ImaItemView])
async def list_ima_items(
    bucket: Annotated[Literal["attention", "lossy", "remote_deleted"], Query()] = "attention",
    agent_id: AgentIdQuery = None,
) -> list[ImaItemView]:
    return await ima.list_items(agent_id, bucket)
