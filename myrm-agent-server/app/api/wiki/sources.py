"""Wiki external source sync API.

[INPUT]
- app.services.wiki.source_sync.config_store (POS: wikiSourceSync UserConfig persistence)
- app.services.wiki.source_sync.state_store (POS: wikiSourceSyncState last-run observability)
- app.services.wiki.source_sync.runner (POS: sync orchestration SSOT)
- app.api.dependencies::get_optional_llm_for_user (POS: compile-capable LLM)

[OUTPUT]
- GET/PUT /sources/config · POST /sources/sync（`agent_id` query · 含 `google_drive_authorized` · scoped sync state）

[POS]
REST layer for Settings Wiki external source configuration and manual sync triggers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_optional_llm_for_user
from app.database.connection import get_db
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER
from app.services.integrations.oauth_store import (
    google_workspace_drive_read_enabled,
    is_oauth_issuer_connected,
)
from app.services.wiki.source_sync.config_store import (
    load_wiki_source_sync_config,
    save_wiki_source_sync_config,
)
from app.services.wiki.source_sync.feishu import is_feishu_wiki_sync_available
from app.services.wiki.source_sync.runner import run_wiki_source_sync
from app.services.wiki.source_sync.schemas import (
    WikiSourceSyncConfig,
    WikiSourceSyncRunSummary,
    WikiSourceSyncState,
)
from app.services.wiki.source_sync.state_store import load_wiki_source_sync_state

router = APIRouter(prefix="/sources", tags=["wiki-sources"])


class WikiSourceSyncStatusResponse(BaseModel):
    config: WikiSourceSyncConfig
    google_connected: bool
    google_drive_authorized: bool
    feishu_connected: bool
    state: WikiSourceSyncState


async def _wiki_source_sync_status(
    db: AsyncSession,
    *,
    config: WikiSourceSyncConfig,
    state: WikiSourceSyncState,
) -> WikiSourceSyncStatusResponse:
    google_connected = await is_oauth_issuer_connected(db, GOOGLE_WORKSPACE_ISSUER)
    google_drive_authorized = await google_workspace_drive_read_enabled(db) if google_connected else False
    feishu_connected = await is_feishu_wiki_sync_available()
    return WikiSourceSyncStatusResponse(
        config=config,
        google_connected=google_connected,
        google_drive_authorized=google_drive_authorized,
        feishu_connected=feishu_connected,
        state=state,
    )


class WikiSourceSyncConfigUpdate(BaseModel):
    feishu_enabled: bool | None = None
    feishu_folder_token: str | None = Field(default=None, max_length=256)
    gmail_enabled: bool | None = None
    gmail_label: str | None = Field(default=None, max_length=128)
    gdrive_enabled: bool | None = None
    gdrive_folder_id: str | None = Field(default=None, max_length=256)
    rss_feeds: list[str] | None = None
    auto_compile: bool | None = None
    max_items_per_run: int | None = Field(default=None, ge=1, le=50)
    mirror_integrations_to_wiki: bool | None = None


@router.get("/config", response_model=WikiSourceSyncStatusResponse)
async def get_wiki_source_sync_config(
    db: AsyncSession = Depends(get_db),
    agent_id: Annotated[str | None, Query(description="Agent whose wiki source config to use")] = None,
) -> WikiSourceSyncStatusResponse:
    config = await load_wiki_source_sync_config(db, agent_id=agent_id)
    state = await load_wiki_source_sync_state(db, agent_id=agent_id)
    return await _wiki_source_sync_status(db, config=config, state=state)


@router.put("/config", response_model=WikiSourceSyncStatusResponse)
async def update_wiki_source_sync_config(
    body: WikiSourceSyncConfigUpdate,
    db: AsyncSession = Depends(get_db),
    agent_id: Annotated[str | None, Query(description="Agent whose wiki source config to use")] = None,
) -> WikiSourceSyncStatusResponse:
    current = await load_wiki_source_sync_config(db, agent_id=agent_id)
    updates = body.model_dump(exclude_unset=True)
    merged = current.model_copy(update=updates)
    saved = await save_wiki_source_sync_config(db, merged, agent_id=agent_id)
    state = await load_wiki_source_sync_state(db, agent_id=agent_id)
    return await _wiki_source_sync_status(db, config=saved, state=state)


@router.post("/sync", response_model=WikiSourceSyncRunSummary)
async def trigger_wiki_source_sync(
    llm: Annotated[BaseChatModel, Depends(get_optional_llm_for_user)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
    db: AsyncSession = Depends(get_db),
) -> WikiSourceSyncRunSummary:
    config = await load_wiki_source_sync_config(db, agent_id=agent_id)
    return await run_wiki_source_sync(llm=llm, agent_id=agent_id, config=config)
