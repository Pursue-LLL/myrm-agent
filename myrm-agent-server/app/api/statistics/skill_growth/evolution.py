"""Skill inventory and recent evolution timeline.

[INPUT]
- app.core.skills.store.service::skills_service (POS: skill inventory)
- app.services.skills.experience_ledger::summarize_skill_growth_events (POS: evolution outcome counters)
- app.services.skills.growth.audit_queries::list_skill_growth_timeline (POS: unified growth timeline)
- app.api.statistics.skill_growth.models::SkillEvolutionEvent (POS: response contract)

[OUTPUT]
- SkillEvolutionSnapshot: Skill count, evolution counters and recent events
- fetch_skill_evolution_data: Read-only snapshot, empty when the services fail

[POS]
Evolution panel data of the growth dashboard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.api.statistics.skill_growth.models import SkillEvolutionEvent
from app.core.skills.store.service import skills_service
from app.services.skills.experience_ledger import summarize_skill_growth_events
from app.services.skills.growth.audit_queries import list_skill_growth_timeline

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SkillEvolutionSnapshot:
    total_skills: int = 0
    total_evolutions: int = 0
    approved: int = 0
    rejected: int = 0
    pending: int = 0
    apply_failed: int = 0
    events: list[SkillEvolutionEvent] = field(default_factory=list)


async def fetch_skill_evolution_data() -> SkillEvolutionSnapshot:
    """Fetch skill inventory + recent growth timeline from unified services."""
    try:
        skills = await skills_service.list_skills()
        total_skills = len(skills)
        summary = await summarize_skill_growth_events()
        timeline = await list_skill_growth_timeline(limit=20)
        events = [
            SkillEvolutionEvent(
                skill_id=item.skill_id,
                skill_name=item.skill_name,
                source=item.source.value,
                status=item.status.value,
                growth_type=item.growth_type,
                created_at=item.created_at.isoformat(),
                change_summary=item.change_summary,
            )
            for item in timeline
        ]
        return SkillEvolutionSnapshot(
            total_skills=total_skills,
            total_evolutions=summary.total_events,
            approved=summary.approved,
            rejected=summary.rejected,
            pending=summary.pending_events,
            apply_failed=summary.apply_failed,
            events=events,
        )
    except Exception as e:
        logger.warning("Failed to fetch skill evolution data: %s", e)
        return SkillEvolutionSnapshot()
