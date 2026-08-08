"""Wiki browser clip + wikiignore REST routes.

[INPUT]
- app.services.wiki.clip (POS: clip job orchestration + multipart cap)
- app.services.wiki.vault_service (POS: wiki archiver)
- myrm_agent_harness.toolkits.wiki.pipeline.ingress (POS: clip ingress + wikiignore)

[OUTPUT]
- POST/GET /clip · GET/PUT /wikiignore

[POS]
REST layer for browser extension wiki clip upload and vault .wikiignore rules.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.services.wiki.clip import (
    MAX_CLIP_PAYLOAD_BYTES,
    clip_form_payload_bytes,
    get_wiki_clip_job,
    schedule_wiki_clip,
)

router = APIRouter(tags=["wiki-clip"])


class WikiClipAcceptResponse(BaseModel):
    job_id: str
    accepted: bool = True


class WikiClipJobResponse(BaseModel):
    job_id: str
    state: str
    relative_path: str | None = None
    written: bool | None = None
    conflict: bool | None = None
    security_blocked: bool | None = None
    assets_localized: str | None = None
    error_message: str = ""


class WikiIgnoreContentResponse(BaseModel):
    content: str


class WikiIgnoreUpdateRequest(BaseModel):
    content: str = ""


@router.post("/clip", response_model=WikiClipAcceptResponse, status_code=202)
async def clip_page_to_wiki(
    source_url: Annotated[str, Form(min_length=1, max_length=4096)],
    title: Annotated[str, Form(max_length=512)] = "",
    clip_mode: Annotated[str, Form(pattern="^(full_page|selection)$")] = "full_page",
    html: Annotated[str, Form()] = "",
    markdown: Annotated[str, Form()] = "",
    folder_path: Annotated[str, Form(max_length=512)] = "",
    queue_compile: Annotated[str, Form()] = "false",
    asset_urls: Annotated[str, Form()] = "[]",
    asset_files: Annotated[list[UploadFile] | None, File()] = None,
    agent_id: Annotated[
        str | None, Query(description="Agent whose wiki vault to use")
    ] = None,
) -> WikiClipAcceptResponse:
    from myrm_agent_harness.toolkits.wiki.pipeline.ingress import (
        ClipAssetInput,
        ClipMode,
    )

    try:
        url_list: list[str] = json.loads(asset_urls) if asset_urls.strip() else []
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Invalid asset_urls JSON") from exc
    if not isinstance(url_list, list):
        raise HTTPException(status_code=422, detail="asset_urls must be a JSON array")
    if len(url_list) != len(asset_files or []):
        raise HTTPException(
            status_code=422,
            detail="asset_urls length must match uploaded asset_files count",
        )

    assets: list[ClipAssetInput] = []
    for idx, upload in enumerate(asset_files or []):
        data = await upload.read()
        content_type = upload.content_type or "application/octet-stream"
        source = str(url_list[idx]) if idx < len(url_list) else upload.filename or ""
        assets.append(
            ClipAssetInput(source_url=source, content_type=content_type, data=data)
        )

    payload_bytes = clip_form_payload_bytes(
        source_url=source_url,
        title=title,
        clip_mode=clip_mode,
        html=html,
        markdown=markdown,
        folder_path=folder_path,
        queue_compile=queue_compile,
        asset_urls=asset_urls,
        asset_file_bytes=tuple(item.data for item in assets),
    )
    if payload_bytes > MAX_CLIP_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Clip payload exceeds 8MB limit")

    mode = ClipMode.FULL_PAGE if clip_mode == "full_page" else ClipMode.SELECTION
    compile_after = queue_compile.strip().lower() in {"true", "1", "yes", "on"}
    job_id = await schedule_wiki_clip(
        agent_id=agent_id,
        source_url=source_url,
        title=title or source_url,
        clip_mode=mode,
        html=html,
        markdown=markdown,
        folder_path=folder_path,
        assets=tuple(assets),
        queue_compile=compile_after,
    )
    return WikiClipAcceptResponse(job_id=job_id)


@router.get("/clip/{job_id}", response_model=WikiClipJobResponse)
async def get_wiki_clip_job_status(job_id: str) -> WikiClipJobResponse:
    record = get_wiki_clip_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Clip job not found")
    result = record.result
    return WikiClipJobResponse(
        job_id=record.job_id,
        state=record.state.value,
        error_message=record.error_message,
        relative_path=result.relative_path if result else None,
        written=result.written if result else None,
        conflict=result.conflict if result else None,
        security_blocked=result.security_blocked if result else None,
        assets_localized=result.assets_localized if result else None,
    )


@router.get("/wikiignore", response_model=WikiIgnoreContentResponse)
async def get_wiki_ignore_rules(
    agent_id: Annotated[
        str | None, Query(description="Agent whose wiki vault to use")
    ] = None,
) -> WikiIgnoreContentResponse:
    from myrm_agent_harness.toolkits.wiki.pipeline.ingress.wikiignore import (
        wikiignore_path,
    )

    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    path = wikiignore_path(archiver._structure)
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    return WikiIgnoreContentResponse(content=content)


@router.put("/wikiignore", response_model=WikiIgnoreContentResponse)
async def put_wiki_ignore_rules(
    body: WikiIgnoreUpdateRequest,
    agent_id: Annotated[
        str | None, Query(description="Agent whose wiki vault to use")
    ] = None,
) -> WikiIgnoreContentResponse:
    from myrm_agent_harness.toolkits.wiki.pipeline.ingress.wikiignore import (
        write_wikiignore_patterns,
    )

    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id=agent_id)
    write_wikiignore_patterns(archiver._structure, body.content)
    return WikiIgnoreContentResponse(content=body.content)
