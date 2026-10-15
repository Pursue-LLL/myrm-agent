"""Skill panels of the growth dashboard: evolution, trends and health.

[INPUT]
- app.api.statistics.skill_growth.models / evolution / trends / health (POS: one module per panel)

[OUTPUT]
- Response models and the three read-only fetchers consumed by GET /statistics/growth-dashboard

[POS]
Facade of the skill-side data behind the growth dashboard.
"""

from __future__ import annotations

from app.api.statistics.skill_growth.evolution import SkillEvolutionSnapshot, fetch_skill_evolution_data
from app.api.statistics.skill_growth.health import fetch_skill_health
from app.api.statistics.skill_growth.models import (
    SkillEvolutionEvent,
    SkillHealthItem,
    SkillTrendPoint,
    SkillTrendSeries,
)
from app.api.statistics.skill_growth.trends import fetch_skill_trends

__all__ = [
    "SkillEvolutionEvent",
    "SkillEvolutionSnapshot",
    "SkillHealthItem",
    "SkillTrendPoint",
    "SkillTrendSeries",
    "fetch_skill_evolution_data",
    "fetch_skill_health",
    "fetch_skill_trends",
]
