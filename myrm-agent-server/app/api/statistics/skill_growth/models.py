"""Skill-side payload models of the growth dashboard.

[INPUT]
- pydantic::BaseModel (POS: response schema base)

[OUTPUT]
- SkillEvolutionEvent: Recent skill evolution log entry
- SkillTrendPoint / SkillTrendSeries: Per-skill daily usage and outcome trend
- SkillHealthItem: 7-day health verdict of one skill with the evidence behind it

[POS]
Response contract shared by the skill panels of GET /statistics/growth-dashboard.
"""

from __future__ import annotations

from pydantic import BaseModel


class SkillEvolutionEvent(BaseModel):
    """Recent skill evolution log entry."""

    skill_id: str | None = None
    skill_name: str
    source: str
    status: str
    growth_type: str
    created_at: str
    change_summary: str = ""


class SkillTrendPoint(BaseModel):
    """Single data point in a skill usage trend."""

    date: str
    """Calendar day (YYYY-MM-DD) in the timezone the dashboard was requested in."""
    success_rate: float | None
    """Share of the day's runs with an observed outcome that succeeded; None when none was observed."""
    observed_count: int
    """Runs of the day whose outcome was observed: the evidence behind ``success_rate``."""
    call_count: int


class SkillTrendSeries(BaseModel):
    """Daily usage trend of a single skill."""

    skill_name: str
    data_points: list[SkillTrendPoint]


class SkillHealthItem(BaseModel):
    """7-day health of a skill that ran in the window, evaluated by harness SkillHealthEvaluator."""

    skill_name: str
    health_score: float
    status: str
    call_count_7d: int
    call_count_total: int
    observed_count_7d: int
    """Runs of the week whose outcome was observed: the evidence behind the status."""
    min_observed_count: int
    """Observed outcomes needed before the success rate and a quality status are shown."""
    success_rate_7d: float | None
    """Share of the week's observed outcomes that succeeded; None until ``min_observed_count`` were observed."""
    actionable_recommendation: str | None = None
