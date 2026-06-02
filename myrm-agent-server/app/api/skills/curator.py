"""Curator API — skill lifecycle management endpoints.

Provides REST endpoints for:
- Lifecycle actions: pin/unpin/restore/archive a skill
- Curator configuration: get/update CuratorConfig
- Manual trigger: run a curator sweep on demand
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/curator")


class LifecycleActionRequest(BaseModel):
    """Request to change a skill's lifecycle state."""

    action: Literal["pin", "unpin", "restore", "archive"]


class LifecycleActionResponse(BaseModel):
    """Response after lifecycle action."""

    skill_name: str
    action: str
    new_status: str
    pinned: bool


class CuratorConfigResponse(BaseModel):
    """Curator configuration response."""

    enabled: bool
    interval_hours: int
    stale_after_days: int
    archive_after_days: int
    grace_period_days: int
    min_success_rate: float
    max_skills: int
    protect_installed_skills: bool
    consolidation_enabled: bool
    consolidation_min_cluster_size: int
    consolidation_similarity_threshold: float


class CuratorConfigUpdateRequest(BaseModel):
    """Update curator configuration (partial)."""

    enabled: bool | None = None
    interval_hours: int | None = None
    stale_after_days: int | None = None
    archive_after_days: int | None = None
    grace_period_days: int | None = None
    min_success_rate: float | None = None
    max_skills: int | None = None
    protect_installed_skills: bool | None = None
    consolidation_enabled: bool | None = None
    consolidation_min_cluster_size: int | None = None
    consolidation_similarity_threshold: float | None = None


class CuratorRunResponse(BaseModel):
    """Result of a manual curator sweep."""

    skills_scanned: int
    total_transitions: int
    stale_count: int
    archived_count: int
    skipped_pinned: int
    transitions: list[dict[str, str]]


def _get_stats_collector() -> SkillStatsCollector:
    """Get the shared SkillStatsCollector instance."""
    from app.core.skills.curator_service import get_stats_collector

    return get_stats_collector()


def _resolve_skill_path(skill_name: str) -> Path:
    """Resolve a skill name to its filesystem path."""
    from app.core.skills.curator_service import resolve_skill_path

    path = resolve_skill_path(skill_name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")
    return path


@router.patch("/{skill_name}/lifecycle", response_model=LifecycleActionResponse)
async def update_skill_lifecycle(
    skill_name: str,
    request: LifecycleActionRequest,
) -> LifecycleActionResponse:
    """Perform a lifecycle action on a skill (pin/unpin/restore/archive)."""
    skill_path = _resolve_skill_path(skill_name)
    collector = _get_stats_collector()

    action = request.action
    stats = collector.get_stats(skill_path)

    if action == "pin":
        collector.set_pinned(skill_path, pinned=True)
        return LifecycleActionResponse(
            skill_name=skill_name, action="pin", new_status=stats.lifecycle_status, pinned=True
        )
    elif action == "unpin":
        collector.set_pinned(skill_path, pinned=False)
        return LifecycleActionResponse(
            skill_name=skill_name, action="unpin", new_status=stats.lifecycle_status, pinned=False
        )
    elif action == "restore":
        collector.update_lifecycle_status(skill_path, SkillLifecycleStatus.ACTIVE)
        return LifecycleActionResponse(
            skill_name=skill_name, action="restore", new_status=SkillLifecycleStatus.ACTIVE, pinned=stats.pinned
        )
    elif action == "archive":
        if stats.pinned:
            raise HTTPException(
                status_code=409,
                detail=f"Skill '{skill_name}' is pinned — unpin it first before archiving",
            )
        collector.update_lifecycle_status(skill_path, SkillLifecycleStatus.ARCHIVED)
        return LifecycleActionResponse(
            skill_name=skill_name, action="archive", new_status=SkillLifecycleStatus.ARCHIVED, pinned=stats.pinned
        )
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")


@router.get("/config", response_model=CuratorConfigResponse)
async def get_curator_config() -> CuratorConfigResponse:
    """Get current curator configuration."""
    from app.core.skills.curator_service import get_curator_config

    config = get_curator_config()
    return CuratorConfigResponse(
        enabled=config.enabled,
        interval_hours=config.interval_hours,
        stale_after_days=config.stale_after_days,
        archive_after_days=config.archive_after_days,
        grace_period_days=config.grace_period_days,
        min_success_rate=config.min_success_rate,
        max_skills=config.max_skills,
        protect_installed_skills=config.protect_installed_skills,
        consolidation_enabled=config.consolidation_enabled,
        consolidation_min_cluster_size=config.consolidation_min_cluster_size,
        consolidation_similarity_threshold=config.consolidation_similarity_threshold,
    )


@router.patch("/config", response_model=CuratorConfigResponse)
async def update_curator_config(request: CuratorConfigUpdateRequest) -> CuratorConfigResponse:
    """Update curator configuration (partial update)."""
    from app.core.skills.curator_service import update_curator_config

    config = update_curator_config(request.model_dump(exclude_none=True))
    return CuratorConfigResponse(
        enabled=config.enabled,
        interval_hours=config.interval_hours,
        stale_after_days=config.stale_after_days,
        archive_after_days=config.archive_after_days,
        grace_period_days=config.grace_period_days,
        min_success_rate=config.min_success_rate,
        max_skills=config.max_skills,
        protect_installed_skills=config.protect_installed_skills,
        consolidation_enabled=config.consolidation_enabled,
        consolidation_min_cluster_size=config.consolidation_min_cluster_size,
        consolidation_similarity_threshold=config.consolidation_similarity_threshold,
    )


@router.post("/run", response_model=CuratorRunResponse)
async def run_curator() -> CuratorRunResponse:
    """Manually trigger a curator sweep."""
    from app.core.skills.curator_service import run_curator_sweep

    result = await run_curator_sweep(force=True, trigger="manual")
    return CuratorRunResponse(
        skills_scanned=result.skills_scanned,
        total_transitions=result.total_transitions,
        stale_count=result.stale_count,
        archived_count=result.archived_count,
        skipped_pinned=result.skipped_pinned,
        transitions=[
            {
                "skill_name": t.skill_name,
                "from_status": t.from_status,
                "to_status": t.to_status,
                "reason": t.reason_type,
            }
            for t in result.transitions
        ],
    )


class CuratorHistoryEntry(BaseModel):
    """A single curator run history entry."""

    timestamp: str
    trigger: str
    duration_ms: int
    skills_scanned: int
    total_transitions: int
    stale_count: int
    archived_count: int
    skipped_pinned: int
    transitions: list[dict[str, str]]
    errors: list[str]


@router.get("/history", response_model=list[CuratorHistoryEntry])
async def get_curator_history(limit: int = 10) -> list[CuratorHistoryEntry]:
    """Get recent curator sweep history records (newest first)."""
    from app.core.skills.curator_service import get_curator_history

    entries = get_curator_history(limit=limit)
    return [CuratorHistoryEntry(**e) for e in entries]


# ========== Consolidation (Umbrella Merge) ==========


class ConsolidationActionResponse(BaseModel):
    """A single consolidation action in the plan."""

    action_type: str
    target_skill: str
    source_skills: list[str]
    reasoning: str


class ConsolidationPreviewResponse(BaseModel):
    """Dry-run consolidation plan for user preview."""

    actions: list[ConsolidationActionResponse]
    total_skills_affected: int
    estimated_reduction: int
    preview_summary: str


class ConsolidationExecuteResponse(BaseModel):
    """Result of executing a consolidation plan."""

    success_count: int
    failure_count: int
    total_archived: int
    total_created: int
    net_reduction: int
    summary: str
    agent_refs_updated: int


@router.post("/consolidation/preview", response_model=ConsolidationPreviewResponse)
async def consolidation_preview() -> ConsolidationPreviewResponse:
    """Generate a consolidation plan (dry-run) without executing changes."""
    from app.core.skills.curator_service import run_consolidation_preview

    plan = await run_consolidation_preview()
    return ConsolidationPreviewResponse(
        actions=[
            ConsolidationActionResponse(
                action_type=a.action_type.value,
                target_skill=a.target_skill,
                source_skills=list(a.source_skills),
                reasoning=a.reasoning,
            )
            for a in plan.actions
        ],
        total_skills_affected=plan.total_skills_affected,
        estimated_reduction=plan.estimated_reduction,
        preview_summary=plan.preview_summary,
    )


@router.post("/consolidation/execute", response_model=ConsolidationExecuteResponse)
async def consolidation_execute() -> ConsolidationExecuteResponse:
    """Execute consolidation — merge fragmented skills into umbrellas."""
    from app.core.skills.curator_service import run_consolidation_execute

    result = await run_consolidation_execute()
    return result
