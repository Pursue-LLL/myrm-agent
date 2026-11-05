"""静态索引状态/刷新与技能池同步。

[POS]
技能发现域的子模块；由 routes.py 按原顺序挂载。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.api.skills.discovery.schemas import (
    SkillPoolSyncRequest,
    SkillPoolSyncResponse,
    StaticIndexStatusResponse,
)
from app.core.skills.marketplace.market_service import (
    market_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/static-index/status", response_model=StaticIndexStatusResponse)
async def get_static_index_status() -> StaticIndexStatusResponse:
    """Get the status and metadata of the centralized static skills index."""
    from myrm_agent_harness.agent.skills.market.sources.static_index import (
        StaticIndexSkillSource,
    )

    static_source = None
    for src in market_service._base._sources:
        if isinstance(src, StaticIndexSkillSource):
            static_source = src
            break

    if static_source is None:
        return StaticIndexStatusResponse(
            is_loaded=False,
            total_indexed_skills=0,
            source_name="static_index",
            source_url="",
            last_synced_at=0.0,
        )

    return StaticIndexStatusResponse(
        is_loaded=static_source._is_loaded,
        total_indexed_skills=static_source.total_indexed_skills,
        source_name=static_source.source_name,
        source_url=static_source._index_url,
        last_synced_at=static_source._last_synced_at,
    )


@router.post("/static-index/refresh", response_model=StaticIndexStatusResponse)
async def refresh_static_index() -> StaticIndexStatusResponse:
    """Trigger manual refresh of the centralized static skills index from CDN/mirror."""
    from myrm_agent_harness.agent.skills.market.sources.static_index import (
        StaticIndexSkillSource,
    )

    static_source = None
    for src in market_service._base._sources:
        if isinstance(src, StaticIndexSkillSource):
            static_source = src
            break

    if static_source is None:
        raise HTTPException(status_code=404, detail="Static index source is not registered")

    await static_source.force_refresh()

    return StaticIndexStatusResponse(
        is_loaded=static_source._is_loaded,
        total_indexed_skills=static_source.total_indexed_skills,
        source_name=static_source.source_name,
        source_url=static_source._index_url,
        last_synced_at=static_source._last_synced_at,
    )


# ---------------------------------------------------------------------------
# Skill Pool Cross-Agent Sync
# ---------------------------------------------------------------------------


@router.post("/pool/sync", response_model=SkillPoolSyncResponse)
async def sync_skill_pool(
    request: SkillPoolSyncRequest,
) -> SkillPoolSyncResponse:
    """Sync a skill into multiple Agent profiles' explicit allowlists."""
    from app.core.skills.config_version import bump_skill_config_version
    from app.core.skills.discovery.adopt import sync_skill_to_agents
    from app.services.event.app_event_bus import (
        AppEvent,
        AppEventType,
        get_event_bus,
    )

    results = await sync_skill_to_agents(
        request.skill_id,
        request.target_agent_ids,
    )
    synced = [aid for aid, success in results.items() if success]
    failed = [aid for aid, success in results.items() if not success]

    if synced:
        bump_skill_config_version()
        try:
            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.SKILL_POOL_UPDATED,
                    data={
                        "action": "sync",
                        "skill_id": request.skill_id,
                        "synced_agents": synced,
                    },
                )
            )
        except Exception as exc:
            logger.warning("Failed to broadcast SKILL_POOL_UPDATED on sync: %s", exc)

    return SkillPoolSyncResponse(
        success=bool(synced),
        skill_id=request.skill_id,
        synced_agents=synced,
        failed_agents=failed,
    )
