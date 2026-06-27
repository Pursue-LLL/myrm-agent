"""Memory CRUD — preferences.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)
app.schemas.memory.crud::MemoryItem (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.crud::UpdateMemoryStatusRequest (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.crud::TasteSummaryResponse (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.archive::*Import* / *Archive* (POS: 记忆归档与导入 API Schema 层)

[OUTPUT]
memory CRUD handler functions、状态变更、偏好摘要、偏好管理、服务端绑定导入、Memory Archive、导入后诊断和回滚预演端点

[POS]
记忆 API 操作层。提供标准记忆增删改查、偏好稳定性管理、单用户 archive 导出/校验，
以及 dry-run -> confirm -> diagnostic -> rollback preview -> rollback 的可审计导入流程。
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind

from app.schemas.memory.crud import (
    PreferenceFacetItem,
    PreferenceFacetListResponse,
    TasteSummaryResponse,
)
from app.services.memory.manager_deps import (
    get_crud_memory_manager,
)
from app.services.memory.operations.crud._common import _record_memory_event

logger = logging.getLogger(__name__)


async def get_taste_summary(
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> TasteSummaryResponse:
    """Get aggregated user preference summary from profile + active facets."""
    reply_style: str | None = None
    technical_depth: str | None = None
    proactivity: str | None = None

    try:
        reply_style = await manager.get_profile_attribute("reply_style")
        technical_depth = await manager.get_profile_attribute("cognitive_depth")
        proactivity = await manager.get_profile_attribute("proactivity")
    except Exception as e:
        logger.warning("Failed to read profile attributes: %s", e)

    style_keywords: list[str] = []
    preference_keywords: list[str] = []
    avoid_keywords: list[str] = []
    current_goals: list[str] = []
    memory_count = 0

    strategy = manager._preference_strategy
    if strategy is not None:
        try:
            from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
                PreferenceCategory,
                PreferenceLifecycle,
            )

            all_facets = await strategy._store.list_all()
            active_facets = [
                f
                for f in all_facets
                if f.lifecycle in (PreferenceLifecycle.ACTIVE, PreferenceLifecycle.PROVISIONAL)
                and not f.user_forgotten
            ]
            memory_count = len(active_facets)

            for f in active_facets:
                label = f.value or f.key
                if not label:
                    continue
                if f.category == PreferenceCategory.STYLE:
                    style_keywords.append(label)
                elif f.category == PreferenceCategory.VETO:
                    avoid_keywords.append(label)
                elif f.category == PreferenceCategory.GOAL:
                    current_goals.append(label)
                else:
                    preference_keywords.append(label)
        except Exception as e:
            logger.warning("Failed to aggregate preference facets: %s", e)

    summary = _build_taste_summary(style_keywords, preference_keywords, avoid_keywords, current_goals)

    return TasteSummaryResponse(
        reply_style=reply_style,
        technical_depth=technical_depth,
        proactivity=proactivity,
        style_keywords=style_keywords,
        preference_keywords=preference_keywords,
        avoid_keywords=avoid_keywords,
        current_goals=current_goals,
        summary=summary,
        memory_count=memory_count,
    )


def _build_taste_summary(
    style: list[str],
    preferences: list[str],
    avoid: list[str],
    goals: list[str],
) -> str:
    """Build a concise natural-language summary from keyword lists."""
    parts: list[str] = []
    if style:
        parts.append(f"Style: {', '.join(style[:5])}")
    if preferences:
        parts.append(f"Prefers: {', '.join(preferences[:5])}")
    if avoid:
        parts.append(f"Avoids: {', '.join(avoid[:5])}")
    if goals:
        parts.append(f"Goals: {', '.join(goals[:5])}")
    return ". ".join(parts)


# ── Preference Stability Endpoints ──────────────────────────────────


async def list_preferences(
    lifecycle: str | None = None,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> PreferenceFacetListResponse:
    """List user preference facets with optional lifecycle filter."""
    from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
        PreferenceLifecycle,
    )

    strategy = manager._preference_strategy
    if strategy is None:
        return PreferenceFacetListResponse(
            items=[],
            total=0,
            active_count=0,
            provisional_count=0,
            candidate_count=0,
        )

    if lifecycle:
        try:
            lc = PreferenceLifecycle(lifecycle)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid lifecycle '{lifecycle}'. Must be one of: active, provisional, candidate, dropped",
            ) from exc
        facets = await strategy._store.list_by_lifecycle(lc)
    else:
        facets = await strategy._store.list_all()

    items = [
        PreferenceFacetItem(
            id=f.id,
            key=f.key,
            value=f.value,
            category=f.category.value,
            cue=f.cue.value,
            lifecycle=f.lifecycle.value,
            stability=f.stability,
            evidence_count=f.evidence_count,
            memory_ids=f.memory_ids,
            first_seen=f.first_seen,
            last_seen=f.last_seen,
            user_pinned=f.user_pinned,
            user_forgotten=f.user_forgotten,
        )
        for f in facets
    ]

    active_count = sum(1 for f in facets if f.lifecycle.value == "active")
    provisional_count = sum(1 for f in facets if f.lifecycle.value == "provisional")
    candidate_count = sum(1 for f in facets if f.lifecycle.value == "candidate")

    return PreferenceFacetListResponse(
        items=items,
        total=len(items),
        active_count=active_count,
        provisional_count=provisional_count,
        candidate_count=candidate_count,
    )


async def pin_preference(
    facet_id: str,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, bool]:
    """Pin a preference so it never decays."""
    strategy = manager._preference_strategy
    if strategy is None:
        raise HTTPException(status_code=503, detail="Preference stability not available")

    facet = await strategy._store.find_by_id(facet_id)
    if facet is None:
        raise HTTPException(status_code=404, detail=f"Preference facet {facet_id} not found")

    facet.user_pinned = True
    facet.user_forgotten = False
    from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
        PreferenceLifecycle,
        StabilityScorer,
    )

    facet.stability = StabilityScorer.score(facet)
    facet.lifecycle = PreferenceLifecycle.ACTIVE
    await strategy._store.upsert(facet)
    return {"success": True}


async def forget_preference(
    facet_id: str,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, bool]:
    """Forget a preference so it is immediately dropped."""
    strategy = manager._preference_strategy
    if strategy is None:
        raise HTTPException(status_code=503, detail="Preference stability not available")

    facet = await strategy._store.find_by_id(facet_id)
    if facet is None:
        raise HTTPException(status_code=404, detail=f"Preference facet {facet_id} not found")

    facet.user_forgotten = True
    facet.user_pinned = False
    from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
        PreferenceLifecycle,
    )

    facet.stability = 0.0
    facet.lifecycle = PreferenceLifecycle.DROPPED
    await strategy._store.upsert(facet)
    await _record_memory_event(
        kind=MemoryOperationKind.FORGET,
        summary="Preference forgotten by user.",
        memory_id=facet_id,
        memory_type="preference",
        metadata={"facet_key": getattr(facet, "key", None)},
    )
    return {"success": True}


async def unpin_preference(
    facet_id: str,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, bool]:
    """Unpin a preference so it resumes natural decay."""
    strategy = manager._preference_strategy
    if strategy is None:
        raise HTTPException(status_code=503, detail="Preference stability not available")

    facet = await strategy._store.find_by_id(facet_id)
    if facet is None:
        raise HTTPException(status_code=404, detail=f"Preference facet {facet_id} not found")

    facet.user_pinned = False
    from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
        StabilityScorer,
    )

    facet.stability = StabilityScorer.score(facet)
    facet.lifecycle = StabilityScorer.classify(facet.stability)
    await strategy._store.upsert(facet)
    await _record_memory_event(
        kind=MemoryOperationKind.WRITE,
        summary="Preference unpinned by user.",
        memory_id=facet_id,
        memory_type="preference",
        metadata={"facet_key": getattr(facet, "key", None)},
    )
    return {"success": True}


async def unforget_preference(
    facet_id: str,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, bool]:
    """Restore a forgotten preference so it resumes lifecycle participation."""
    strategy = manager._preference_strategy
    if strategy is None:
        raise HTTPException(status_code=503, detail="Preference stability not available")

    facet = await strategy._store.find_by_id(facet_id)
    if facet is None:
        raise HTTPException(status_code=404, detail=f"Preference facet {facet_id} not found")

    facet.user_forgotten = False
    from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
        StabilityScorer,
    )

    facet.stability = StabilityScorer.score(facet)
    facet.lifecycle = StabilityScorer.classify(facet.stability)
    await strategy._store.upsert(facet)
    await _record_memory_event(
        kind=MemoryOperationKind.WRITE,
        summary="Preference restored (unforgotten) by user.",
        memory_id=facet_id,
        memory_type="preference",
        metadata={"facet_key": getattr(facet, "key", None)},
    )
    return {"success": True}
