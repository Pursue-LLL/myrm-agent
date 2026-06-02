from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.skills.growth_queries import (
    list_skill_growth_audit_entries,
    summarize_skill_growth_audit,
)

router = APIRouter()


@router.get("/rejections")
async def get_evolution_rejections(
    skill_id: str | None = Query(None, description="Filter by skill ID"),
    trigger_type: str | None = Query(None, description="Legacy filter alias; matches growth type or status"),
    limit: int = Query(100, ge=1, le=1000, description="Max number of records to return"),
) -> dict[str, object]:
    """Return unified skill-growth negative audit records via the legacy evolution endpoint."""
    entries = await list_skill_growth_audit_entries(limit=limit, days=365, skill_id=skill_id)
    if trigger_type:
        normalized = trigger_type.lower()
        entries = [
            entry
            for entry in entries
            if entry.growth_type.lower() == normalized or entry.status.value.lower() == normalized
        ]

    rejections = [
        {
            "skill_id": entry.skill_id or entry.skill_name,
            "trigger_type": entry.status.value.lower(),
            "proposed_type": entry.growth_type,
            "rejection_reason": entry.reason,
            "confidence": entry.confidence or 0.0,
            "trigger_context": entry.source.value,
            "rejected_at": entry.created_at.isoformat(),
            "status": entry.status.value,
            "skill_name": entry.skill_name,
            "severity": entry.severity,
        }
        for entry in entries
    ]
    return {
        "rejections": rejections,
        "total_count": len(rejections),
        "filters": {
            "skill_id": skill_id,
            "trigger_type": trigger_type,
            "limit": limit,
        },
    }


@router.get("/rejections/stats")
async def get_rejection_stats(
    time_range_days: int = Query(30, ge=1, le=365, description="Time range in days"),
) -> dict[str, object]:
    """Return unified skill-growth negative audit summary via the legacy evolution endpoint."""
    stats = await summarize_skill_growth_audit(time_range_days=time_range_days)
    return {
        "total_rejections": stats.total_events,
        "avg_confidence": stats.avg_confidence,
        "top_triggers": [
            {
                "trigger_type": item.key.lower(),
                "count": item.count,
                "percentage": item.percentage,
            }
            for item in stats.by_status
        ],
        "top_skills": [
            {
                "skill_id": item.skill_id or item.skill_name,
                "count": item.count,
                "percentage": item.percentage,
            }
            for item in stats.top_skills
        ],
        "time_range_days": time_range_days,
    }




